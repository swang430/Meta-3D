"""在聚簇轨迹的原始采样时刻计算模型频响。"""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, StrictFloat

router = APIRouter()


class TrajectoryRequest(BaseModel):
    direction: Literal["downlink", "uplink"]
    trajectory: dict
    offsets_hz: list[StrictFloat] = Field(min_length=1, max_length=129)


@router.post("/cluster-response")
def calculate_cluster_response(request: TrajectoryRequest):
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


@router.post("/cluster-trajectory/import")
def import_cluster_trajectory(
    archive: UploadFile, clusters: UploadFile, quality: UploadFile,
    direction: Literal["downlink", "uplink"] = Form(...),
    speed_m_s: float = Form(..., gt=0), coordinate_units: Literal["metres"] = Form(...),
):
    """用操作员确认的恒速、米制位置及上下行原始文件还原单个方向的时间轴。"""
    repository = str(Path(__file__).resolve().parents[4])
    if repository not in sys.path:
        sys.path.append(repository)
    from scripts.inspect_mpdb import mpdb
    from scripts.s5_evaluation.export_trajectory import convert
    from scripts.s5_evaluation.run import sha

    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        try:
            for upload in (archive, clusters, quality):
                name = upload.filename or ""
                if not name or Path(name).name != name or name in {".", ".."}:
                    raise ValueError("文件名无效")
                with (folder / name).open("xb") as output:
                    while chunk := upload.file.read(1024 * 1024):
                        if output.tell() + len(chunk) > mpdb.MAX_BYTES:
                            raise ValueError("文件超过允许读取的大小")
                        output.write(chunk)
            document = mpdb.inspect_mpdb(folder / archive.filename, speed_m_s=speed_m_s,
                                         coordinate_units=coordinate_units, speed_source="user_confirmed")
            source = next(d for d in document["directions"] if d["direction"] == direction)
            stem = Path(source["source_document"]["meta"]["lauraycsPlatform"]["name"]).stem
            if (clusters.filename, quality.filename) != (f"{stem}_cluster_cdl.csv", f"{stem}_cluster_quality.csv"):
                raise ValueError("所选方向与聚簇文件、质量文件的名称不匹配")
            hashes = {item["path"]: item["sha256"] for item in document["source_files"]}
            hashes.update({u.filename: sha(folder / u.filename) for u in (clusters, quality)})
            return convert(document, source, folder, hashes)
        except (ValueError, KeyError, OverflowError, FileExistsError) as exc:
            raise HTTPException(422, f"无法导入轨迹：{exc}") from exc
