"""路线航点上的确定性演示模型，只用于模拟回放。"""
import hashlib
import json
import math
from datetime import datetime

from fastapi import HTTPException


def freeze(scenario, config):
    params = config.get("model_parameters", {})
    if not isinstance(params, dict) or params.keys() - {"seed"}:
        raise HTTPException(422, "模型参数只接受整数种子。")
    seed = params.get("seed", 0)
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise HTTPException(422, "模型种子须为 0 至 2147483647 的整数。")
    speed = config.get("acceleration_factor", 1)
    if type(speed) not in (int, float) or not 0 < speed <= 10000:
        raise HTTPException(422, "回放倍率须大于零且不超过 10000。")
    snapshot = scenario.model_dump(mode="json", exclude={"created_at", "updated_at"})
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    route = snapshot["route"]
    times = [point["time_s"] for point in route["waypoints"]]
    if (not times or not math.isfinite(route["duration_s"]) or route["duration_s"] <= 0
            or not all(0 <= t <= route["duration_s"] for t in times)
            or times != sorted(set(times))):
        raise HTTPException(422, "路线须有有效时长，航点时刻须在路线内按顺序递增。")
    return dict(scenario_snapshot=snapshot, scenario_sha256=digest, model_version="demo-v1",
                model_parameters={"seed": seed}, acceleration_factor=speed, provenance="simulated")


def elapsed(row, now):
    runtime = row.vrt_runtime_status or {}
    seconds = runtime.get("twin_elapsed_s", 0)
    if row.status == "running" and runtime.get("twin_running_since"):
        since = datetime.fromisoformat(runtime["twin_running_since"])
        seconds += max(0, (now - since).total_seconds()) * row.vrt_twin_input["acceleration_factor"]
    return min(seconds, row.vrt_twin_input["scenario_snapshot"]["route"]["duration_s"])


def timeline(row, now):
    setup = row.vrt_twin_input
    if row.mode != "digital_twin" or not setup or setup["model_version"] != "demo-v1":
        raise HTTPException(409, "本次执行没有可回放的数字孪生输入。")
    if row.status == "idle":
        raise HTTPException(409, "请先启动数字孪生执行。")
    route = setup["scenario_snapshot"]["route"]
    cutoff = elapsed(row, now)
    points = []
    for waypoint in route["waypoints"]:
        t = waypoint["time_s"]
        if row.started_at is None or t > cutoff:
            break
        key = f"{setup['scenario_sha256']}/{setup['model_parameters']['seed']}/{t}"
        number = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")
        points.append(dict(source_frame_time_s=t, dl_throughput_mbps=round(100 * number / 0xffffffff, 3),
                           provenance="simulated"))
    return dict(points=points, provenance="simulated", formal_kpi=False)


def compare(twin, setup, points, observations):
    differences = []
    by_time = {p["source_frame_time_s"]: p["dl_throughput_mbps"] for p in points}
    reason = "场景版本不一致或缺少冻结资料。"
    if setup.get("scenario_sha256") == twin["scenario_sha256"]:
        reason = "仅列出来源已核验且路线时刻相同的下行样本，其余时刻未核验。"
        for item in observations:
            t = item.source_frame_time_s
            if (item.metric == "dl_throughput_mbps" and item.provenance == "server_measured"
                    and t in by_time and item.device_playback_time_s == t):
                differences.append(dict(source_frame_time_s=t,
                                        delta_dl_throughput_mbps=round(by_time[t] - item.value, 3)))
    return dict(comparable=bool(differences), reason=reason, differences=differences, formal_kpi=False)
