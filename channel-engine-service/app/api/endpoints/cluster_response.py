"""在聚簇轨迹的原始采样时刻计算模型频响。"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictFloat

router = APIRouter()


class TrajectoryRequest(BaseModel):
    direction: Literal["downlink", "uplink"]
    trajectory: dict
    offsets_hz: list[StrictFloat] = Field(min_length=1, max_length=129)


@router.post("/cluster-response")
def calculate_cluster_response(request: TrajectoryRequest):
    if request.trajectory.get("direction") != request.direction:
        raise HTTPException(422, "计算方向与交换文件声明不一致")
    try:
        from mimo_ota_simulator.imported_cluster_trajectory import synthesize_sampled_trajectory
    except ImportError as exc:
        raise HTTPException(503, "计算服务缺少逐帧频响计算模块") from exc

    try:
        result = synthesize_sampled_trajectory(request.trajectory, request.offsets_hz, direction=request.direction)
        rows = result["frames"]
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(422, f"无法计算这份聚簇轨迹：{exc}") from exc

    frames = request.trajectory["frames"]
    if len(rows) != len(frames):
        raise HTTPException(502, "计算结果没有覆盖全部输入帧")
    for frame, row in zip(frames, rows):
        if any(row[key] != frame[key] for key in ("sampleIndex", "timeSeconds", "frameId", "internalLinkId")):
            raise HTTPException(502, "计算结果与输入帧的次序或时刻不一致")
    return {**result, "hardware_verified": False}
