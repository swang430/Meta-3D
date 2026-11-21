"""从下行 MPDB 生成四发两收的联合聚簇源帧工程。"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import numpy as np

if __package__:
    from .imt_conducted import inspect
    from .imt_conducted_spectrum import column
else:
    from imt_conducted import inspect
    from imt_conducted_spectrum import column

PAIRS = [(tx, rx) for tx in range(4) for rx in range(2)]


def hyperrt_executable():
    configured = os.environ.get("HYPERRT_PATH")
    executable = shutil.which(configured or "HyperRT")
    if executable is None:
        raise FileNotFoundError(
            "找不到可执行的 HyperRT。请将 HYPERRT_PATH 设为发行目录中 HyperRT 可执行文件的路径，"
            "或将发行目录加入 PATH。"
        )
    return Path(executable).resolve()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_asc(path, frames, width, carrier):
    # PROPSIM User Reference §21.1，时延列单位 ns。每行对应一个源帧。
    with path.open("w", encoding="ascii") as stream:
        stream.write(f"***** Header *****\n{len(frames)} CIRs\n{width} Taps/CIR\n"
                     f"{carrier} Carrier_Frequency\nRoute_Open\nCIRUpdateRate_Locked\n"
                     "CarrierFrequency_Locked\n5 Delay_Resolution\n2 Sample_Density\n"
                     "1 CIR_Update_Rate\n***** Tap data *****\n")
        print("\t".join(["Delay\tRe\tIm"] * width), file=stream)
        for frame in frames:
            taps = sorted((row["delay_s"] * 1e9, row["real"], row["imag"]) for row in frame)
            taps.extend([(taps[-1][0], 0, 0)] * (width - len(taps)))
            print("\t".join(str(number) for tap in taps for number in tap), file=stream)
    return inspect(path)


class ChooseClustering(ValueError):
    pass


def validate_members_container(members, lid):
    with zipfile.ZipFile(members) as container:
        entries = container.infolist()
        names = {"source_sha256.npy", *(f"L{i}.npy" for i in lid)}
        if (len(entries) != len(names) or sum(e.file_size for e in entries) > 128 * 1024**2
                or {e.filename for e in entries} != names):
            raise ValueError("成员表条目数量、大小或唯一性不符")
        # 在 numpy 分配数组前核对声明长度和实际条目大小。
        for entry in entries:
            with container.open(entry) as stream:
                if np.lib.format.read_magic(stream) != (1, 0):
                    raise ValueError("成员表数组格式不受支持")
                shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
                if entry.filename == "source_sha256.npy":
                    valid = shape == () and dtype.kind == "U" and dtype.itemsize <= 256
                    count = 1
                else:
                    valid = len(shape) == 1 and dtype.kind in "iu"
                    count = shape[0] if valid else 0
                if not valid or stream.tell() + count * dtype.itemsize != entry.file_size:
                    raise ValueError("成员表数组类型或声明长度与文件不符")


def assemble(dbpath, stage, method=None, supplied=None):
    with zipfile.ZipFile(dbpath) as db:
        desc = json.loads(db.read("mpdb.json"))

        meta = desc.get("meta", {})
        platform = meta.get("lauraycsPlatform", {})
        if platform.get("direction") != "downlink":
            raise ValueError("工程需要明确标为下行的传播数据")
        if (platform.get("angleCoordinateSystem") != "GCS" or meta.get("mode") != "CIR"
                or type(meta.get("numFrequency")) is not int or meta["numFrequency"] != 1):
            raise ValueError("工程需要采用全局角度坐标、单一载频的信道冲激响应数据")

        def columns(table, names):
            return [column(db, desc, table, name).ravel() for name in names.split()]

        fr, tx, rx, lid, fc = columns("LINK", "FRAME_ID TX_ANT RX_ANT LINK_ID FREQUENCY")
        ids, h, delay, aoa, fd, aod, zoa, zod = columns(
            "CHANNEL", "LINK_ID H DELAY AOA DOPPLER AOD ZOA ZOD")
    frames = sorted(set(fr.tolist()))
    keys = list(zip(fr, tx, rx, strict=True))
    lookup = dict(zip(keys, lid, strict=True))
    if (not frames or frames[0] < 0 or len(set(lid)) != len(keys)
            or len(lookup) != len(keys)
            or set(keys) != {(f, t, r) for f in frames for t, r in PAIRS}):
        raise ValueError("每个源帧都需要四发两收的八条唯一链路")
    if (len(fc) != len(keys) or len(set(fc)) != 1 or not np.isfinite(fc[0])
            or fc[0] <= 0):
        raise ValueError("八条链路需要同一个有效载频")
    if any(len(c) != len(ids) or not np.isfinite(c).all()
           for c in (h, delay, aoa, fd, aod, zoa, zod)) or not np.isin(ids, lid).all():
        raise ValueError("射线记录缺失、数值无效或链路编号未知")

    members = stage / "members.npz"
    db_hash = digest(dbpath)
    reference = Path(__file__).resolve().parents[1] / "docs/evidence/imt-three/members.npz"
    match = supplied
    if match is None and reference.is_file():
        with np.load(reference, allow_pickle=False) as known:
            if str(known["source_sha256"]) == db_hash:
                match = reference
    if match is not None:
        shutil.copyfile(match, members)
        origin = "supplied_members" if supplied is not None else "reference_members"
    elif method == "hyperrt":
        runtime = hyperrt_executable()
        subprocess.run([runtime, Path(__file__).resolve().with_name("imt_joint_members.py"),
                        dbpath, members], cwd=runtime.parent, check=True)
        origin = method
    elif method == "delay_bins":
        # Common frame-wide boundaries for all eight links; not angular clustering.
        groups = {}
        for frame in frames:
            link_ids = lid[fr == frame]
            selected = np.isin(ids, link_ids) & (abs(h) > 0)
            if not selected.any():
                raise ValueError("本帧没有有效射线")
            edges = np.linspace(delay[selected].min(), delay[selected].max(), 25)[1:-1]
            for ident in link_ids:
                values = delay[(ids == ident) & (abs(h) > 0)]
                groups[f"L{ident}"] = np.searchsorted(edges, values).astype(np.int32)
        np.savez_compressed(members, source_sha256=db_hash, **groups)
        origin = method
    else:
        raise ChooseClustering("未找到与下行 MPDB 匹配的成员表，请选择聚簇方式。")
    validate_members_container(members, lid)
    if engine := os.environ.get("CHANNEL_ENGINE_PATH"):
        sys.path.insert(0, engine)
    from mimo_ota_simulator.joint_cluster_response import reduce_link
    source = dict(mpdb=db_hash, members=digest(members))
    results, evidence = [], []
    by_pair = {pair: [] for pair in PAIRS}
    with np.load(members, allow_pickle=False) as table:
        if str(table["source_sha256"]) != source["mpdb"]:
            raise ValueError("成员表与本次输入不符")
        for frame in frames:
            for t, r in PAIRS:
                ident = lookup[frame, t, r]
                mask = (ids == ident) & (abs(h) > 0)
                labels = table[f"L{ident}"]
                if (labels.shape != (int(mask.sum()),) or labels.dtype.kind not in "iu"
                        or np.any(labels < 0) or np.any(labels >= 24)):
                    raise ValueError(f"链路 {ident} 的成员数量或簇编号无效")
                rays = h[mask].astype(complex)
                frequencies = fd[mask].astype(float)
                clusters = reduce_link(labels, rays, delay[mask], aoa[mask], frequencies,
                                       departure_azimuth_deg=aod[mask], arrival_zenith_deg=zoa[mask],
                                       departure_zenith_deg=zod[mask])
                if not clusters:
                    raise ValueError(f"源帧 {frame} 的阵元对 {t}/{r} 没有有效射线")
                rows = []
                for cid, stats in clusters.items():
                    key = dict(frame=frame, tx=t, rx=r, cluster=cid)
                    coeff = stats.pop("coefficient")
                    rows.append(dict(**key, **stats, real=coeff.real, imag=coeff.imag,
                                     doppler=stats["doppler_mean_hz"]))
                results.extend(rows)
                by_pair[t, r].append(rows)
                for cid in np.unique(labels):
                    selected = labels == cid
                    values = rays[selected]
                    freq = frequencies[selected]
                    evidence.append(dict(frame=frame, tx=t, rx=r, cluster=int(cid),
                                         count=len(values), sumReal=math.fsum(values.real),
                                         sumImag=math.fsum(values.imag), sumAbs=math.fsum(abs(values)),
                                         minHz=float(freq.min()), maxHz=float(freq.max())))
    for name, rows in (("results", results), ("evidence", evidence)):
        save(stage / f"{name}.json", dict(schema=f"joint-{name}/1", source=source, rows=rows))
    width = max(len(row) for groups in by_pair.values() for row in groups)
    links = []
    for (t, r), groups in by_pair.items():
        path = stage / f"R0B0S0D_TX{t}_RX{r}_H.asc"
        header = write_asc(path, groups, width, float(fc[0]))
        links.append(dict(tx=t, rx=r, file=path.name, sha256=digest(path)))
    return dict(source=source, clustering_method=origin, direction="downlink", mode="conducted", frames=frames, links=links,
                time_axis="每行对应一个源帧。文件头的 1 Hz 仅用于按序查看，不代表原始帧率。"
                          "未生成帧间多普勒相位演进，簇编号仅在同一帧内共用。",
                software=dict(asc_files_checked=len(links), cluster_rows=len(results)),
                header=header, rate_source="source_frame_viewer_placeholder",
                evidence="offline_asc_validation", smu_built=False, hardware_verified=False)


def build(archive: Path, output: Path, method=None, supplied=None):
    if os.path.lexists(output):
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(dir=output.parent.resolve()) as tmp:
        stage = Path(tmp) / "project"
        stage.mkdir()
        with zipfile.ZipFile(archive) as outer:
            downlinks = [entry for entry in outer.infolist() if entry.filename == "R0B0S0D.mpdb"]
            if len(downlinks) > 1:
                raise ValueError("压缩包内有多份同名下行 R0B0S0D.mpdb，无法确定计算来源")
            if downlinks:
                dbpath = Path(tmp) / "downlink.mpdb"
                with outer.open(downlinks[0]) as src, dbpath.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif "mpdb.json" in outer.namelist():
                dbpath = archive.resolve()
            else:
                raise ValueError("压缩包缺少下行 R0B0S0D.mpdb 或独立数据库的 mpdb.json")
        manifest = assemble(dbpath, stage, method, supplied)
        manifest["archive_sha256"] = digest(archive)
        save(stage / "manifest.json", manifest)
        stage.rename(output)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--members", type=Path)
    parser.add_argument("--method", choices=["hyperrt", "delay_bins"])
    args = parser.parse_args()
    build(args.archive, args.output, args.method, args.members)
