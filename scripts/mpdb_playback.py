"""明确区分源帧时间、操作员给出的播放假设与输出采样率。"""

import math
import hashlib
import json
from itertools import accumulate

import numpy as np

if __package__:
    from .imt_conducted_spectrum import column
else:
    from imt_conducted_spectrum import column


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def output_grid(end, rate):
    length = end * rate
    if not math.isfinite(length):
        raise ValueError("输出时刻数超出允许范围")
    nearest = round(length)
    on_grid = abs(length - nearest) <= 4 * math.ulp(length)
    last = nearest if on_grid else math.floor(length)
    if not 1 <= last < 20000:
        raise ValueError("按所选时间轴和输出更新率计算，输出须在 2 至 20000 个时刻之间")
    grid = np.arange(last + 1, dtype=float) / rate
    if on_grid:
        grid[-1] = end  # 对齐浮点舍入范围内的末帧，保证区段掩码确实覆盖它。
    return grid


def inspect_timing(db, desc):
    records = desc.get("records", {})
    if "LINK" not in records:
        raise ValueError("缺少源帧链路记录")
    ids, tx, rx = [
        column(db, desc, "LINK", key).ravel()
        for key in ("FRAME_ID", "TX_ANT", "RX_ANT")
    ]
    frames, counts = np.unique(ids, return_counts=True)
    if ids.dtype.kind not in "iu" or not len(frames) or frames[0] < 0:
        raise ValueError("源帧编号无效")
    distances = [None] * (len(frames) - 1)
    if "RX_ANT_POSITION" in records["LINK"]:
        mask = (tx == 0) & (rx == 0)
        order = np.argsort(ids[mask])
        if not np.array_equal(ids[mask][order], frames):
            raise ValueError("无法逐帧唯一定位参考接收阵元")
        pos = column(db, desc, "LINK", "RX_ANT_POSITION")[mask][order].astype(float)
        if not np.isfinite(pos).all():
            raise ValueError("参考接收阵元的位置含无效数值")
        distances = np.linalg.norm(np.diff(pos, axis=0), axis=1).tolist()
    # LauraycsUtils/rt_timing.py: rtSampleTimesSeconds 以原始 FRAME_ID 索引；
    # 并非所有 MPDB 写端都透传这些字段。只读有明确秒单位的声明。
    declarations = []
    meta = desc["meta"]
    for label, obj in (
        ("meta", meta),
        ("meta.lauraycsPlatform", meta["lauraycsPlatform"]),
    ):
        if "rtFrameClock" in obj:
            clock = obj["rtFrameClock"]
            if (
                not isinstance(clock, dict)
                or clock.get("version") != 1
                or clock.get("mode") not in ("physical", "frame-only")
            ):
                raise ValueError("原始帧时钟声明无效")
        mode = obj.get("rtFrameClock", {}).get("mode")
        if mode == "physical" and "rtSampleTimesSeconds" not in obj:
            raise ValueError("原始文件声明物理时钟却缺少逐帧时间")
        if "rtSampleTimesSeconds" in obj:
            axis = obj["rtSampleTimesSeconds"]
            if (
                not isinstance(axis, list)
                or len(axis) <= frames[-1]
                or not all(map(finite, axis))
                or any(b <= a for a, b in zip(axis, axis[1:]))
            ):
                raise ValueError("原始逐帧时间缺失、顺序错误或包含无效值")
            declarations.append(
                (label + ".rtSampleTimesSeconds", [axis[f] for f in frames])
            )
        if "rtSampleIntervalSeconds" in obj:
            dt = obj["rtSampleIntervalSeconds"]
            if not finite(dt) or dt <= 0:
                raise ValueError("原始帧间隔必须为正的秒数")
            declarations.append(
                (
                    label + ".rtSampleIntervalSeconds",
                    (frames.astype(float) * dt).tolist(),
                )
            )
    table = records.get("FRAME", {})
    for key in ("TIME_SECONDS", "TIME_S"):
        if key in table:
            fid = column(db, desc, "FRAME", "FRAME_ID").ravel()
            t = column(db, desc, "FRAME", key).ravel()
            order = np.argsort(fid)
            if (
                fid.dtype.kind not in "iu"
                or not np.array_equal(fid[order], frames)
                or len(t) != len(frames)
            ):
                raise ValueError("逐帧时间与链路帧编号不符")
            declarations.insert(0, ("FRAME." + key, t[order].tolist()))
    declarations.sort(key=lambda item: item[0].endswith(".rtSampleIntervalSeconds"))
    source, axis = declarations[0] if declarations else (None, None)
    frame_only = any(
        obj.get("rtFrameClock", {}).get("mode") == "frame-only"
        for obj in (meta, meta["lauraycsPlatform"])
    )
    if declarations and frame_only:
        raise ValueError("文件同时声明只有帧编号和物理时间")
    for name, times in declarations:
        if (
            not all(map(finite, times))
            or any(b <= a for a, b in zip(times, times[1:]))
            or not np.allclose(np.diff(axis), np.diff(times), rtol=0, atol=1e-6)
            or (
                not name.endswith(".rtSampleIntervalSeconds")
                and not np.allclose(axis, times, rtol=0, atol=1e-6)
            )
        ):
            raise ValueError("原始文件中的时间声明无效或相互矛盾")
    try:
        doppler = column(db, desc, "CHANNEL", "DOPPLER")
        peak = float(np.max(np.abs(doppler.astype(float)))) if doppler.dtype.kind in "iuf" and np.isfinite(doppler).all() else None
    except (KeyError, ValueError, TypeError, OSError):
        peak = None  # 传导源帧不需要这个字段；动态生成时必须拒绝未知值。
    return dict(
        max_abs_doppler_hz=peak,
        frame_only=frame_only,
        frame_row_counts=counts.tolist(),
        frame_ids=frames.tolist(),
        distances_m=distances,
        source_times_s=axis,
        time_source=source,
    )


def match_plan(raw, platform, timing):
    if timing.get("frame_only"):
        raise ValueError("下行文件明确声明只有帧编号，与清单物理时钟冲突")
    doc = json.loads(raw)
    if (doc.get("protocol") != "lauraycs-compute-link-plan" or type(doc.get("protocolVersion")) is not int
            or doc["protocolVersion"] != 1 or doc.get("kind") != "compute-link-plan"):
        raise ValueError("不是支持的 Lauraycs 链路计算清单")
    if platform.get("direction") != "downlink" or platform.get("name") != "R0B0S0D.mpdb":
        raise ValueError("下行文件名或方向与平台记录不符")
    plans = [p for p in doc["plans"] if p.get("dataFile") == "R0B0S0D.arrow"
             or p.get("planIndex") == platform.get("linkIndex")
             or p.get("metadata", {}).get("linkKey") == platform.get("linkKey")]
    if len(plans) != 1:
        raise ValueError("清单中无法唯一对应下行链路")
    plan = plans[0]
    meta = plan["metadata"]
    if plan.get("dataFile") != "R0B0S0D.arrow" or type(plan.get("planIndex")) is not int or plan["planIndex"] != platform["linkIndex"]:
        raise ValueError("下行路径或计划索引不匹配")
    datasets = [d for d in doc.get("datasets", []) if d.get("datasetId") == "links"]
    if len(datasets) != 1:
        raise ValueError("清单没有唯一的链路分片目录")
    shards = [s for s in datasets[0]["shards"] if s.get("planIndex") == plan["planIndex"]
              or s.get("path", "").rsplit("/", 1)[-1] == plan["dataFile"]]
    if len(shards) != 1:
        raise ValueError("未找到唯一的下行链路分片")
    shard = shards[0]
    if (shard.get("path","").rsplit("/",1)[-1] != plan["dataFile"]
            or type(shard.get("planIndex")) is not int or shard["planIndex"] != plan["planIndex"]
            or type(plan.get("rowOffset")) is not int or plan["rowOffset"] < 0
            or type(shard.get("rowOffset")) is not int or shard["rowOffset"] != plan["rowOffset"]
            or type(plan.get("rowsPerFrame")) is not int or plan["rowsPerFrame"] <= 0
            or any(n != plan["rowsPerFrame"] for n in timing["frame_row_counts"])
            or type(shard.get("rowCount")) is not int
            or shard["rowCount"] != len(timing["frame_ids"]) * plan["rowsPerFrame"]):
        raise ValueError("下行分片的路径、计划索引或帧行数不匹配")
    for key in ("routeIndex","linkIndex","baseStationIndex","sectorIndex","transmitterIndex"):
        if type(meta.get(key)) is not int or type(platform.get(key)) is not int or meta[key] != platform[key]:
            raise ValueError("链路索引不匹配：" + key)
    for key, value in (("direction","downlink"),("linkKey",platform.get("linkKey")),
                       ("txNodeId",platform["transmitter"].get("nodeId")),
                       ("rxNodeId",platform["receiver"].get("nodeId"))):
        if not isinstance(value,str) or not value or meta.get(key) != value:
            raise ValueError("链路方向或收发节点不匹配：" + key)
    frames = timing["frame_ids"]
    times = meta.get("rtSampleTimesSeconds")
    clock = meta.get("rtFrameClock", {})
    if (clock.get("mode") != "physical" or type(clock.get("version")) is not int or clock["version"] != 1
            or any(type(x) is not int or x != len(frames) for x in (doc.get("frameCount"),plan.get("frameCount")))
            or frames != list(range(len(frames))) or not isinstance(times,list) or len(times) != len(frames)
            or not all(map(finite,times)) or any(b <= a for a,b in zip(times,times[1:]))):
        raise ValueError("清单的物理时钟、帧号或逐帧时间不匹配")
    if timing["source_times_s"] is not None and timing["source_times_s"] != times:
        raise ValueError("清单时间与下行文件内时间冲突")
    return {**timing,"source_times_s":times,"time_source":"compute-link-plan.manifest.json:rtSampleTimesSeconds",
            "plan_sha256":hashlib.sha256(raw).hexdigest()}


def resolve_playback(timing, speed, segments, quality):
    distances = timing["distances_m"]
    axis = timing["source_times_s"]
    if quality not in ("standard","dense") or not distances:
        raise ValueError("动态播放需要至少两个源帧和有效的更新率档位")
    if axis is not None:
        if speed is not None or segments is not None:
            raise ValueError("文件已提供帧时间，不能另行覆盖")
        times = [t - axis[0] for t in axis]
        source = timing["time_source"]
    else:
        if (speed is None) == (segments is None):
            raise ValueError("原文件没有时间，请明确选择假定恒速或提供各段时长")
        if speed is not None:
            if (
                not finite(speed)
                or speed <= 0
                or any(d is None or d <= 0 for d in distances)
            ):
                raise ValueError(
                    "假定恒速需要有效速度和各段非零位移；停留时请提供各段时长"
                )
            segments = [d / speed for d in distances]
        if len(segments) != len(distances) or not all(
            finite(s) and s > 0 for s in segments
        ):
            raise ValueError("每个相邻源帧区段都需要一个正的时长（秒）")
        times = list(accumulate(segments, initial=0.0))
        source = (
            "operator_constant_speed"
            if speed is not None
            else "operator_segment_durations"
        )
    if not all(map(finite,times)) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("帧时间必须严格递增")
    peak = timing.get("max_abs_doppler_hz")
    if not finite(peak) or peak < 0:
        raise ValueError("无法确认原始射线的最大多普勒频移，请检查源文件后重新导入")
    shortest = min(b-a for a,b in zip(times,times[1:]))
    bound = max(2*peak, 2/shortest)
    if not math.isfinite(bound):
        raise ValueError("所需更新率超出计算范围")
    standard = math.floor(bound)+1
    rate = standard * (2 if quality == "dense" else 1)
    output_grid(times[-1], rate)
    return dict(
        source_times_s=times,
        time_source=source,
        rate_source="source_doppler_and_frame_intervals",
        rate_quality=quality, max_abs_doppler_hz=peak, shortest_interval_s=shortest,
        standard_rate_hz=standard, plan_sha256=timing.get("plan_sha256"),
        rate_hz=rate,
        speed_m_s=speed,
        frame_ids=timing["frame_ids"],
        original_times_s=axis,
        distances_m=distances,
        segment_average_speeds_m_s=[
            None if d is None else d / (b - a)
            for d, a, b in zip(distances, times, times[1:])
        ],
    )
