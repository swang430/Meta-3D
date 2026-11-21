"""按分析提供的分数行坐标对照真实下行 MPDB，报告逐帧宽带矩阵误差。"""

import argparse
import io
import json
import math
import zipfile
from pathlib import Path
import numpy as np
from inspect_mpdb import mpdb

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("archive", type=Path)
parser.add_argument("bundle", type=Path)
parser.add_argument(
    "alignment", type=Path, help="含 frame_rows 的源帧至 ASC 行坐标 JSON"
)
args = parser.parse_args()
with zipfile.ZipFile(args.archive) as z:
    data = z.read("R0B0S0D.mpdb")
with mpdb._archive(data) as archive:
    records = mpdb._json(archive.read("mpdb.json"))["records"]

    def col(table, key):
        return np.concatenate(
            [
                mpdb._tensor(archive.read(s["entry"]))[0]
                for s in records[table][key]["shards"]
            ]
        ).reshape(-1)

    frame, tx, rx, link = [
        col("LINK", k) for k in ("FRAME_ID", "TX_ANT", "RX_ANT", "LINK_ID")
    ]
    path, h, delay = [col("CHANNEL", k) for k in ("LINK_ID", "H", "DELAY")]
manifest = json.loads((args.bundle / "manifest.json").read_text())
if manifest["header"]["taps"] != 24:
    raise ValueError("本样本对照只支持每行 24 抽头")
expected = {(t, r): f"R0B0S0D_TX{t}_RX{r}_H.asc" for t in range(4) for r in range(2)}
links = manifest["links"]
if len(links) != 8 or {(e["tx"], e["rx"]): e["file"] for e in links} != expected:
    raise ValueError("传导清单必须逐项绑定八条下行链路")
asc = {}
for entry in links:
    payload = (args.bundle / entry["file"]).read_bytes()
    if mpdb.digest(payload) != entry["sha256"]:
        raise ValueError("ASC 与生成时的文件校验值不符")
    asc[entry["tx"], entry["rx"]] = np.loadtxt(
        io.BytesIO(payload), skiprows=12
    ).reshape(manifest["header"]["cir_count"], 24, 3)
pos = json.loads(args.alignment.read_text())["frame_rows"]
if set(pos) != set(map(str, set(frame))):
    raise ValueError("对齐表必须显式列出每个源帧，未覆盖帧使用 null")
offset = np.linspace(-50e6, 50e6, 101)


def asc_at(t, r, position):
    # 源帧可能落在两行之间。沿用样本分析的最近时延配对和局部复相位外推。
    data = asc[t, r]
    if not 0 <= position <= len(data) - 1:
        raise ValueError(f"帧坐标越界: {position}")
    if position == int(position):
        row = data[int(position)]
        return row[:, 0] * 1e-9, row[:, 1] + 1j * row[:, 2]
    # 紧靠末尾时以最后两行内插；其余沿用样本分析的向前外推。
    i = min(math.ceil(position - 1e-9), len(data) - 2)
    first, second = data[i : i + 2]
    pairs = np.abs(first[:, 0, None] - second[:, 0]).argmin(axis=1)
    after = second[pairs]
    h0 = first[:, 1] + 1j * first[:, 2]
    h1 = after[:, 1] + 1j * after[:, 2]
    result = h0.copy()
    active = (h0 != 0) & (h1 != 0)
    fraction = position - i
    result[active] *= np.exp(fraction * np.log(h1[active] / h0[active]))
    delays = first[:, 0] + fraction * (after[:, 0] - first[:, 0])
    return delays * 1e-9, result


rows = []
for f in sorted(set(frame)):
    p = pos[str(f)]
    if p is None:
        continue
    err = power = 0.0
    for t in range(4):
        for r in range(2):
            (idx,) = link[(frame == f) & (tx == t) & (rx == r)]
            use = path == idx
            true = np.exp(-2j * np.pi * np.outer(offset, delay[use])) @ h[use]
            d, c = asc_at(t, r, p)
            recon = np.exp(-2j * np.pi * np.outer(offset, d)) @ c
            err += np.sum(abs(recon - true) ** 2)
            power += np.sum(abs(true) ** 2)
    if power <= 0:
        raise ValueError("参考矩阵功率为零，误差未定义")
    rows.append(10 * np.log10(err / power))
    print(f"源帧 {f}，整矩阵归一化均方误差 {rows[-1]:.6f} dB")
if not rows:
    raise ValueError("无可对照片段")
print(
    "frames",
    len(rows),
    "matrix median nmse dB",
    np.median(rows),
    "missing",
    [k for k, v in pos.items() if v is None],
)
