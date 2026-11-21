"""复算 RT-IMT-2030 八条传导链路的多普勒谱。只接受已核对的这一批输入。"""

import argparse
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np

EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/imt-dynamic"
OFFSETS = np.array([-50e6, 0.0, 50e6])


def column(db, desc, table, name):
    if len(db.namelist()) != len(set(db.namelist())):
        raise ValueError("传播数据库中存在同名文件，无法确认分片来源")
    records = desc["records"][table]
    info = records[name]
    rows = info.get("rowCount")
    shape = info.get("shape")
    error = f"{table}.{name} 的分片行范围、形状或数据与列声明不一致"
    if (type(rows) is not int or rows <= 0 or not isinstance(shape, list)
            or not shape or any(type(n) is not int or n <= 0 for n in shape)
            or shape[0] != rows or any(c.get("rowCount") != rows for c in records.values())):
        raise ValueError(error)
    if name in {"FRAME_ID", "TX_ANT", "RX_ANT", "LINK_ID", "FREQUENCY", "H",
                "DELAY", "AOA", "ZOA", "AOD", "ZOD", "DOPPLER"} and shape[1:] not in ([], [1]):
        raise ValueError(error)
    if name == "RX_ANT_POSITION" and shape[1:] != [3]:
        raise ValueError(error)
    entries = [shard["entry"] for c in records.values() for shard in c["shards"]]
    if len(set(entries)) != len(entries):
        raise ValueError(error)
    types = {"I32": "<i4", "I64": "<i8", "F32": "<f4", "F64": "<f8",
             "C64": "<c8", "C128": "<c16"}
    parts = []
    cursor = 0
    for shard in sorted(info["shards"], key=lambda item: item["rowStart"]):
        start, end = shard.get("rowStart"), shard.get("rowEnd")
        if (type(start) is not int or type(end) is not int or start != cursor
                or not start < end <= rows):
            raise ValueError(error)
        raw = db.read(shard["entry"])
        size = int.from_bytes(raw[:8], "little")
        if not 0 < size <= len(raw) - 8:
            raise ValueError(error)
        meta = json.loads(raw[8 : 8 + size])["data"]
        if meta.get("dtype") not in types:
            raise ValueError(error)
        dtype = np.dtype(types[meta["dtype"]])
        expected_shape = [end - start, *shape[1:]]
        byte_count = math.prod(expected_shape) * dtype.itemsize
        if (info.get("dtype") != "torch." + dtype.name or meta.get("shape") != expected_shape
                or meta.get("data_offsets") != [0, byte_count] or len(raw) != 8 + size + byte_count):
            raise ValueError(error)
        parts.append(np.frombuffer(raw, dtype=dtype, offset=8 + size).reshape(expected_shape))
        cursor = end
    if cursor != rows:
        raise ValueError(error)
    return np.concatenate(parts)


def reconstruct(groups, anchors, grid):
    response = np.empty((len(grid), len(OFFSETS)), complex)
    for i, (left, right) in enumerate(zip(anchors, anchors[1:])):
        mask = (grid >= left) & (
            grid <= right if i == len(anchors) - 2 else grid < right
        )
        t = grid[mask]
        u = (t - left) / (right - left)
        blend = (3 * u**2 - 2 * u**3)[:, None]

        def advance(group, delta):
            h, delay, fd = group
            spatial = h[:, None] * np.exp(-2j * np.pi * delay[:, None] * OFFSETS)
            return np.exp(2j * np.pi * delta[:, None] * fd) @ spatial

        response[mask] = (1 - blend) * advance(groups[i], t - left) + blend * advance(
            groups[i + 1], t - right
        )
    return response


def spectrum(signal, rate):
    # 包含尾端窗，所有比较使用同一组起点。不去均值，保留静态分量。
    n = 256
    starts = sorted(set(range(0, len(signal) - n + 1, n // 2)) | {len(signal) - n})
    w = np.hanning(n)
    power = np.mean(
        [abs(np.fft.fft(signal[i : i + n] * w)) ** 2 for i in starts], axis=0
    ) / (rate * (w @ w))
    return np.fft.fftshift(np.fft.fftfreq(n, 1 / rate)), np.fft.fftshift(power)


def describe(f, p, bound):
    prob = p / p.sum()
    center = prob @ f
    return dict(
        peak_hz=float(f[np.argmax(p)]),
        mean_hz=center,
        rms_width_hz=np.sqrt(prob @ (f - center) ** 2),
        negative_fraction=prob[f < 0].sum(),
        positive_fraction=prob[f > 0].sum(),
        outside_motion_band_fraction=prob[abs(f) > bound].sum(),
    )


def run(root):
    audit = json.loads((EVIDENCE / "timeline-audit.json").read_text())
    archive = root / audit["archive"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != audit["archive_sha256"]:
        raise ValueError("MPDB 与时间审计记录不匹配")
    with (
        zipfile.ZipFile(archive) as outer,
        zipfile.ZipFile(io.BytesIO(outer.read("R0B0S0D.mpdb"))) as db,
    ):
        desc = json.loads(db.read("mpdb.json"))
        tx, rx, frame, link, carrier = [
            column(db, desc, "LINK", k).ravel()
            for k in ("TX_ANT", "RX_ANT", "FRAME_ID", "LINK_ID", "FREQUENCY")
        ]
        pos = column(db, desc, "LINK", "RX_ANT_POSITION").reshape(-1, 3).astype(float)
        ids, h, delay, fd = [
            column(db, desc, "CHANNEL", k).ravel()
            for k in ("LINK_ID", "H", "DELAY", "DOPPLER")
        ]
    times = np.r_[
        0,
        np.cumsum(
            np.linalg.norm(
                np.diff(
                    pos[(tx == 0) & (rx == 0)][
                        np.argsort(frame[(tx == 0) & (rx == 0)])
                    ],
                    axis=0,
                ),
                axis=1,
            )
            / 5
        ),
    ]
    rows = []
    for ref in audit["conducted_reference"]:
        path = root / ref["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError(f"传导参考文件内容不匹配：{path.name}")
        t, r = [int(part[-1]) for part in path.stem.split("_")[1:3]]
        rate = ref["rate_hz"]
        asc = np.loadtxt(path, skiprows=12).reshape(ref["rows"], 24, 3)
        grid = np.arange(len(asc)) / rate
        assert grid[-1] <= times[-1]
        groups = []
        for k in range(len(times)):
            (lid,) = link[(tx == t) & (rx == r) & (frame == k)]
            m = (ids == lid) & (abs(h) > 0)
            groups.append(
                (h[m].astype(complex), delay[m].astype(float), fd[m].astype(float))
            )
        reference = (
            (asc[:, :, 1] + 1j * asc[:, :, 2])[:, :, None]
            * np.exp(-2j * np.pi * asc[:, :, 0, None] * 1e-9 * OFFSETS)
        ).sum(axis=1)
        for label, axis in [
            ("distance", times),
            ("uniform_interior", np.r_[np.arange(37), times[-1]]),
        ]:
            model = reconstruct(groups, axis, grid)
            for j, off in enumerate(OFFSETS):
                f, a = spectrum(reference[:, j], rate)
                _, b = spectrum(model[:, j], rate)
                bound = (float(carrier[0]) + off) * 5 / 299792458
                rows.append(
                    dict(
                        tx=t,
                        rx=r,
                        offset_hz=off,
                        time_axis=label,
                        asc=describe(f, a, bound),
                        rebuilt=describe(f, b, bound),
                        power_ratio_db=10 * np.log10(b.sum() / a.sum()),
                        spectral_overlap=np.minimum(a / a.sum(), b / b.sum()).sum(),
                        psd_asc=a.tolist(),
                        psd_rebuilt=b.tolist(),
                    )
                )
    return dict(
        method="双边功率谱，256 点 Hann 窗，步进 128 点，追加末窗，不去均值",
        rate_hz=rate,
        common_samples=len(grid),
        distance_anchor_times_s=times.tolist(),
        frequency_bins_hz=f.tolist(),
        results=rows,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    args.output.write_text(
        json.dumps(run(args.source), ensure_ascii=False, allow_nan=False) + "\n"
    )
