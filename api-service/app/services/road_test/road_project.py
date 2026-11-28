"""核对已入库的道路场景版本及本次实际解析到的播放资产。"""
import hashlib
import json
import math
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict, Field


class RoadProjectReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    version: str = Field(pattern=r"^[a-f0-9]{64}$")


def manifest_clock(manifest):
    header = manifest.get("header")
    if not isinstance(header, dict):
        raise ValueError("模拟清单缺少播放文件头")
    count, rate = header.get("cir_count"), header.get("rate_hz")
    if type(count) is not int or count <= 1 or type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        raise ValueError("模拟清单缺少有效的响应数量和更新率")
    return dict(full_duration_s=(count - 1) / rate, duration_source="模拟文件首末响应间隔")


def project_playback(ref, mode, asset, registrations):
    from app.api.mpdb_projects import _file_digest, _scene_library

    directory = _scene_library() / ref.source_sha256 / ref.version
    scene = json.loads((directory / "scene.json").read_text())
    package = directory / "project.zip"
    if (scene["version"] != ref.version or scene["source_sha256"] != ref.source_sha256
            or scene["mode"] != mode or scene["direction"] != "downlink"
            or _file_digest(package) != scene["package_sha256"]):
        raise ValueError("道路工程的内容、方向或版本已变化")
    if not asset or len(registrations) != 1:
        raise ValueError("缺少唯一匹配的播放资产")
    times = scene.get("source_times_s")
    span = None if not times else times[-1] - times[0]
    if span is not None and (not math.isfinite(span) or span < 0):
        raise ValueError("源轨迹时间无效")
    evidence = dict(project_name=scene["name"], package_sha256=scene["package_sha256"],
                    source_duration_s=span, time_source=scene.get("time_source"))
    if asset.get("mock_only") is True:
        member = "dynamic/manifest.json" if mode == "ota" else "manifest.json"
        with ZipFile(package) as archive:
            raw = archive.read(member)
        if hashlib.sha256(raw).hexdigest() != asset["sha256"]:
            raise ValueError("实际采用的播放清单与所选工程不符")
        evidence.update(manifest_clock(json.loads(raw)))
    elif registrations[0].get("road_project_version") != ref.version:
        raise ValueError("设备工程登记未对应所选道路版本")
    return evidence
