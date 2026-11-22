"""对已有下行 MPDB 和同源成员表作离线分析，结果另存。"""

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

import numpy as np

if __package__:
    from .imt_conducted_spectrum import column
    from .mpdb_conducted_project import validate_members_container
else:
    from imt_conducted_spectrum import column
    from mpdb_conducted_project import validate_members_container

REFERENCE = Path(__file__).resolve().parents[1] / "docs/evidence/imt-three/members.npz"
PAIRS = {(t, r) for t in range(4) for r in range(2)}
LIMIT = 256 * 1024**2


def read_downlink(path):
    with zipfile.ZipFile(path) as outer:
        matches = [e for e in outer.infolist() if e.filename == "R0B0S0D.mpdb"]
        if len(matches) != 1 or matches[0].file_size > LIMIT:
            raise ValueError("需要一份大小不超过 256 MiB 的下行 MPDB")
        raw = outer.read(matches[0])
    digest = hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw)) as db:
        if sum(e.file_size for e in db.infolist()) > 2 * LIMIT:
            raise ValueError("展开后的下行数据超过 512 MiB")
        desc = json.loads(db.read("mpdb.json"))
        meta = desc["meta"]
        platform = meta["lauraycsPlatform"]
        if (
            platform.get("direction"),
            platform.get("angleCoordinateSystem"),
            meta.get("mode"),
            meta.get("numFrequency"),
        ) != ("downlink", "GCS", "CIR", 1):
            raise ValueError("需要具有全局角度和单一载频的下行冲激响应")

        def read_cols(table, names):
            return {
                n.lower(): column(db, desc, table, n).ravel() for n in names.split()
            }

        ports = read_cols("LINK", "FRAME_ID TX_ANT RX_ANT LINK_ID FREQUENCY")
        rays = read_cols("CHANNEL", "LINK_ID H DELAY AOA ZOA AOD ZOD")
    if not all(np.isfinite(v).all() for v in [*ports.values(), *rays.values()]):
        raise ValueError("输入含无效数值")
    identities = (
        ports["frame_id"],
        ports["tx_ant"],
        ports["rx_ant"],
        ports["link_id"],
        rays["link_id"],
    )
    if any(a.dtype.kind not in "iu" or (a < 0).any() for a in identities):
        raise ValueError("帧、端口、链路编号须为非负整数")
    if rays["h"].dtype.kind != "c" or any(
        rays[k].dtype.kind != "f" for k in ("delay", "aoa", "zoa", "aod", "zod")
    ):
        raise ValueError("需要复数射线系数以及实数时延和角度")
    return digest, ports, rays


def expected_rows(raw, source):
    if raw is None:
        return {}
    data = json.loads(raw)
    if data["source"] != source or data["schema"] != "joint-results/1":
        raise ValueError("工程汇总与输入文件的摘要或格式不一致")
    indexed = {}
    for row in data["rows"]:
        if any(
            type(row[k]) is not int or row[k] < 0
            for k in ("frame", "tx", "rx", "cluster")
        ):
            raise ValueError("工程汇总的帧、端口和簇编号须为非负整数")
        if any(
            type(row.get(k)) not in (float, int) or not math.isfinite(row[k])
            for k in ("real", "imag")
        ):
            raise ValueError("工程汇总的复系数无效")
        if "count" in row and (type(row["count"]) is not int or row["count"] < 0):
            raise ValueError("工程汇总的成员计数无效")
        key = tuple(row[k] for k in ("frame", "tx", "rx"))
        group = indexed.setdefault(key, {})
        cid = row["cluster"]
        if cid in group:
            raise ValueError("工程汇总含重复簇")
        group[cid] = {k: row[k] for k in ("real", "imag", "count") if k in row}
    return indexed


def analyze(args):
    if not (
        math.isfinite(args.bandwidth_mhz)
        and 0 < args.bandwidth_mhz <= 10000
        and 3 <= args.points <= 257
        and args.points % 2
    ):
        raise ValueError("分析带宽应在 0 至 10000 MHz 内，频点数须为 3 至 257 的奇数")
    if args.amplitude_floor is not None and not (
        math.isfinite(args.amplitude_floor) and args.amplitude_floor > 0
    ):
        raise ValueError("幅度可信下限必须为有限正数")
    digest, ports, rays = read_downlink(args.archive)
    lid = ports["link_id"]
    keys = list(zip(ports["frame_id"], ports["tx_ant"], ports["rx_ant"], strict=True))
    frames = sorted(set(ports["frame_id"].tolist()))
    if (
        len(set(lid)) != len(lid)
        or len(set(keys)) != len(keys)
        or set(keys) != {(f, t, r) for f in frames for t, r in PAIRS}
        or not np.isin(rays["link_id"], lid).all()
        or len(set(ports["frequency"])) != 1
        or ports["frequency"][0] <= 0
    ):
        raise ValueError("需要每帧同载频的四发两收唯一链路")
    members = args.members or REFERENCE
    with zipfile.ZipFile(members) as container:
        entries = set(container.namelist())
    available = {ident for ident in lid if f"L{ident}.npy" in entries}
    validate_members_container(members, available)
    source = {
        "mpdb": digest,
        "members": hashlib.sha256(members.read_bytes()).hexdigest(),
    }
    notes = []
    expected_sha = None
    try:
        raw = args.expected.read_bytes() if args.expected else None
        expected_sha = hashlib.sha256(raw).hexdigest() if raw is not None else None
        expected = expected_rows(raw, source)
        if set(expected).difference(keys):
            raise ValueError("工程汇总包含输入中不存在的帧或端口")
    except (KeyError, TypeError, ValueError, OSError) as error:
        expected = {}
        notes.append(f"已有工程汇总未核验：{error}")
    if (
        args.members
        and source["members"] != hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    ):
        notes.append(
            "外部成员表按同链路非零射线的源行顺序解释，分组方法和物理身份未核验。"
        )
    offsets = np.linspace(-0.5, 0.5, args.points) * args.bandwidth_mhz * 1e6
    by_key = dict(zip(keys, lid))
    result = []
    from mimo_ota_simulator.port_evidence import analyze_frame

    with np.load(members, allow_pickle=False) as groups:
        if str(groups["source_sha256"]) != digest:
            raise ValueError("没有与本批下行 MPDB 对应的成员表")
        for frame in frames:
            links = {}
            for tx, rx in sorted(PAIRS):
                key = (frame, tx, rx)
                ident = by_key[key]
                rows = np.flatnonzero((rays["link_id"] == ident) & (abs(rays["h"]) > 0))
                if ident not in available:
                    notes.append(f"帧 {frame} 发射 {tx} 接收 {rx} 缺少成员表，未核验。")
                    continue
                labels = groups[f"L{ident}"]
                if labels.shape != rows.shape or not np.all(
                    (labels >= 0) & (labels < 24)
                ):
                    notes.append(
                        f"帧 {frame} 发射 {tx} 接收 {rx} 的成员数量或编号不符，未核验。"
                    )
                    continue
                link = {k: v[rows] for k, v in rays.items() if k != "link_id"}
                if (link["delay"] < 0).any() or any(
                    ((link[k] < 0) | (link[k] > 180)).any() for k in ("zoa", "zod")
                ):
                    notes.append(
                        f"帧 {frame} 发射 {tx} 接收 {rx} 的时延或天顶角无效，未核验。"
                    )
                    continue
                link.update(labels=labels, row_ids=rows)
                if key in expected:
                    link["expected"] = expected[key]
                links[tx, rx] = link
            result.append(analyze_frame(frame, links, offsets, args.amplitude_floor))
    return dict(
        source=source,
        expected_sha256=expected_sha,
        bandwidth_source="操作员指定的分析频段",
        frames=result,
        notes=notes,
        member_row_order="同一 LINK_ID 下按源行顺序筛选 |H| > 0，行号从零开始",
        offsets_hz=offsets.tolist(),
        amplitude_floor=args.amplitude_floor,
        carrier_hz=float(ports["frequency"][0]),
    )


def summarize(report):
    frames = report["frames"]
    warnings = [w for frame in frames for w in frame["p2_106"]["warnings"]]
    clusters = [
        c
        for frame in frames
        for port in frame["p2_106"]["links"]
        for c in port["clusters"]
    ]
    verified = sum(
        all(c.get("checks", {}).get(k) == "matched" for k in ("real", "imag"))
        for c in clusters
    )
    counted = sum(c.get("checks", {}).get("count") == "matched" for c in clusters)
    lines = [
        f"共 {len(frames)} 个源帧，每帧四发两收。复系数与汇总吻合 {verified}/{len(clusters)} 条，成员数吻合 {counted}/{len(clusters)} 条，有证据的异常 {len(warnings)} 处。"
    ]
    lines.extend(report.get("notes", []))
    others = [
        c
        for f in frames
        for p in f["p2_106"]["links"]
        if (p["tx"], p["rx"]) != (0, 0)
        for c in p["clusters"]
    ]
    total = sum(c["count"] for c in others)
    distinct = sum(c.get("distinguishable_count", 0) for c in others)
    agree = sum(c.get("assigned_nearest_count", 0) for c in others)
    lines.append(
        f"其他七个端口共 {total} 条有效射线：{distinct} 条能从时延和收发方向区分最近簇，其中 {agree} 条与已有分组一致。该统计不确认物理路径身份。"
    )
    if any(c.get("checks", {}).get("count", "unverified") == "unverified" for c in clusters):
        lines.append("部分或全部簇的成员数缺少独立确认，详见逐簇核验结果。")
    grid = report["offsets_hz"]
    lines.append(
        f"分析频偏 {grid[0] / 1e6:g} 至 {grid[-1] / 1e6:g} MHz，共 {len(grid)} 点。带宽由操作员指定。"
    )
    if report.get("amplitude_floor") is not None:
        lines.append(
            f"分析采用相对相位幅度下限 {report['amplitude_floor']:g}（复系数幅值）。这是本次分析设置。"
        )
    metrics = {}
    for scheme, name in (("A", "各端口分别计算时延"), ("B", "八路共享时延")):
        ratios = []
        phase = []
        total = 0
        for frame in frames:
            response = frame["p2_107"]
            for point in response["matrix"]:
                value = point[scheme]["nmse"]
                if value is not None:
                    ratios.append((value, frame["frame"], point["offset_hz"]))
            for pair in response["phase_pairs"]:
                values = pair[scheme]["errors_deg"]
                total += len(values)
                phase.extend(
                    (abs(err), frame["frame"], pair["left"], pair["right"], grid[i])
                    for i, err in enumerate(values)
                    if err is not None
                )
        stats = dict(
            matrix_points=len(ratios),
            phase_points=len(phase),
            possible_phase_points=total,
        )
        if ratios:
            worst, frame_id, offset = max(ratios)
            stats.update(
                matrix_nmse_median=float(np.median([v[0] for v in ratios])),
                matrix_nmse_p95=float(np.percentile([v[0] for v in ratios], 95)),
                worst_matrix=dict(nmse=worst, frame=frame_id, offset_hz=offset),
            )
            lines.append(
                f"{name}：矩阵归一化平方误差中位数 {stats['matrix_nmse_median']:.4g}，第 95 百分位 {stats['matrix_nmse_p95']:.4g}。"
            )
        if phase:
            stats["phase_p95_abs_deg"] = float(np.percentile([v[0] for v in phase], 95))
            err, frame_id, left, right, offset = max(phase)
            stats["worst_phase"] = dict(
                abs_deg=err, frame=frame_id, left=left, right=right, offset_hz=offset
            )
            lines.append(
                f"该方案相对相位误差绝对值的第 95 百分位为 {stats['phase_p95_abs_deg']:.3g}°，有效 {len(phase)}/{total} 点。"
            )
        else:
            lines.append(f"该方案相对相位未核验，有效 0/{total} 点。")
        metrics[scheme] = stats
    return dict(
        status="warning" if warnings else ("partial" if clusters else "unverified"),
        warnings=warnings,
        summary=lines,
        message="成员复算和时延对照仅用于离线分析。跨端口物理路径身份未核验。",
        metrics=metrics,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "members", "expected", "output"):
        parser.add_argument(
            "--" + name, type=Path, required=name in ("archive", "output")
        )
    parser.add_argument("--bandwidth-mhz", type=float, required=True)
    parser.add_argument("--points", type=int, required=True)
    parser.add_argument("--amplitude-floor", type=float)
    args = parser.parse_args()
    try:
        report = analyze(args)
        report.update(summarize(report))
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        ImportError,
        zipfile.BadZipFile,
    ) as exc:
        report = dict(
            status="unverified",
            message=f"未核验：{exc}",
            summary=["请检查所选材料。"],
            frames=[],
            warnings=[],
        )
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(
            report, output, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )


if __name__ == "__main__":
    main()
