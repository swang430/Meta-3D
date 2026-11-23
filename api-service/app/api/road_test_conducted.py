"""传导准备与建档。设备控制由执行器负责。"""
import hashlib
import json
import re
from pathlib import Path as Directory
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.api.road_test import _get_custom_scenario
from app.data.scenario_library import get_scenario_by_id
from app.db.database import get_db
from app.models.channel_asset import ChannelAsset
from app.models.lab_profile import LabProfile
from app.models.topology import Topology
from app.schemas.road_test import TestExecution, TestMode
from app.services.channel_emulator_binding import resolve_channel_emulator_binding
from app.services.instrument_hal_service import get_hal_service, is_mock_driver
from app.services.base_station_binding import resolve_base_station_binding
from app.services.channel_asset_service import _has_verified_smu_project_truth, vendor_scd_frequency_identity
from app.services.road_test.network_topology_service import network_topology_service
from app.services.road_test.vrt_execution_service import vrt_execution_service

router = APIRouter(prefix="/road-test/conducted", tags=["Virtual Road Test"])


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1)
    direction: str = "downlink"
    lab_profile_id: UUID | None = None
    topology_id: UUID | None = None
    asset_id: UUID | None = None


def _options(db, model):
    query = db.query(model).filter(model.is_active.is_(True))
    if model is Topology:
        query = query.filter(Topology.topology_type == "conducted")
    if model is ChannelAsset:
        query = query.filter(ChannelAsset.source_type == "vendor_file")
    return [{"id": str(row.id), "name": row.name} for row in query.order_by(model.name, model.id)]


def mock_asset(directory: Directory, name: str):
    raw = (directory / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    links = manifest["links"]
    if manifest.get("mode") != "conducted" or manifest.get("direction") != "downlink" or len(links) != 8:
        raise ValueError("清单必须包含下行传导的八路文件。")
    seen = set()
    verified = []
    for link in links:
        tx, rx, filename = link["tx"], link["rx"], link["file"]
        match = re.fullmatch(r"[A-Za-z0-9_-]+_TX(\d+)_RX(\d+)_H\.asc", filename)
        if (type(tx) != int or type(rx) != int or not match
                or (tx, rx) != tuple(map(int, match.groups()))
                or tx not in range(4) or rx not in range(2) or (tx, rx) in seen):
            raise ValueError("清单中的文件名、发收编号或八路组合不一致。")
        seen.add((tx, rx))
        with (directory / filename).open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != link["sha256"]:
            raise ValueError(f"文件 {filename} 的内容与登记摘要不一致。")
        verified.append(dict(tx=tx, rx=rx, file=filename, sha256=digest))
    digest = hashlib.sha256(raw).hexdigest()
    return {"kind": "asc_manifest", "mock_only": True, "mock_ref": "mock-asc:" + digest,
            "name": name, "sha256": digest, "links": verified}


def _registrations(lab):
    metadata = lab.extra_metadata if lab and isinstance(lab.extra_metadata, dict) else {}
    entries = metadata.get("vrt_conducted")
    return [r for r in entries if isinstance(r, dict)] if isinstance(entries, list) else []


@router.get("/options")
def options(db: Session = Depends(get_db)):
    assets = {a["id"]: a for a in _options(db, ChannelAsset)}
    for lab in db.query(LabProfile).filter(LabProfile.is_active.is_(True)):
        for r in _registrations(lab):
            if r.get("kind") == "asc_manifest" and isinstance(r.get("asset_id"), str):
                assets.setdefault(r["asset_id"], {"id": r["asset_id"], "name": r.get("name") or "八路传导（仅模拟）",
                                                  "mock_only": True})
    return {"labs": _options(db, LabProfile), "topologies": _options(db, Topology),
            "assets": list(assets.values())}


class Path(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    tx: int = Field(ge=1, le=4)
    rx: int = Field(ge=1, le=2)
    input_port: int = Field(ge=1)
    output_port: int = Field(ge=1)


def _mapping(rows, topology):
    try:
        paths = [Path.model_validate(row) for row in rows]
    except (TypeError, ValidationError):
        return [], "八路映射缺少有效的发射、接收或仿真器端口编号。"
    if len(paths) != 8 or len({(p.tx, p.rx) for p in paths}) != 8:
        return [], "下行四发二收需要八个互不重复的发收组合。"
    bs, emu, dut = topology.base_station, topology.channel_emulator, topology.dut
    if not all((bs.device_id, emu.device_id, dut.device_id)) or len({bs.device_id, emu.device_id, dut.device_id}) != 3:
        return [], "拓扑中三个设备的标识缺失或重复。"
    cables = {(c.source_device_id, c.source_port, c.target_device_id, c.target_port) for c in topology.connections}
    needed = set()
    for p in paths:
        if p.tx > bs.tx_ports or p.rx > dut.antenna_ports or p.input_port > emu.input_ports or p.output_port > emu.output_ports:
            return [], "八路映射使用了已登记设备范围以外的端口。"
        needed.add((bs.device_id, p.tx, emu.device_id, p.input_port))
        needed.add((emu.device_id, p.output_port, dut.device_id, p.rx))
    if needed != cables or len(needed) != 6 or len(topology.connections) != 6 or len({c[:2] for c in needed}) != 6 or len({c[2:] for c in needed}) != 6:
        return [], "八路映射与拓扑电缆不一致，或多个电缆占用了同一端口。"
    return [p.model_dump() for p in paths], None


def real_preflight(db, hal, lab, asset, network):
    """核对真实设备所需的已登记证据；此处不取得控制权。"""
    scd = asset.payload["scd_config"]
    working_point = vendor_scd_frequency_identity(scd, allow_legacy_nr=True)
    evidence = {"center_frequency_hz": working_point.center_frequency_hz,
                "bandwidth_mhz": working_point.bandwidth_mhz}
    reasons = []
    if scd["band"].casefold() != network.band.casefold():
        reasons.append("工程登记的频段与场景不一致。")
    if working_point.bandwidth_mhz != network.bandwidth_mhz:
        reasons.append("工程登记的带宽与场景不一致。")
    try:
        station = resolve_base_station_binding(db, hal, lab)
    except ValueError as exc:
        reasons.append(f"实验室的基站绑定未就绪：{exc}")
    else:
        evidence["base_station_binding_digest"] = station.binding_digest
        evidence["base_station_connection_id"] = station.instrument_connection_id
        if station.execution_mode != "real" or not station.instrument_connection_id or station.status == "diagnostic_unbound":
            reasons.append("该实验室未绑定可用于此次执行的真实基站。")
    reasons.append("尚无逐段绑定基站输出、仿真器端口和车载设备输入端口的传导校准核验，无法确认实际输入功率。")
    return evidence, reasons


def resolve(db: Session, selection: Selection, *, playback_files=None):
    ids = selection.model_dump(mode="json")
    scenario = get_scenario_by_id(selection.scenario_id) or _get_custom_scenario(db, selection.scenario_id)
    if not scenario:
        raise HTTPException(404, "所选场景不存在。")
    scenario_snapshot = scenario.model_dump(mode="json", exclude={"created_at", "updated_at"})
    canonical = json.dumps(scenario_snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    scenario_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    reasons = []
    if selection.direction != "downlink":
        reasons.append("当前仅有下行四发二收的准备流程。")
    lab = db.get(LabProfile, selection.lab_profile_id) if selection.lab_profile_id else None
    if not lab or not lab.is_active:
        reasons.append("请选择已启用的实验室。")
    record = db.get(Topology, selection.topology_id) if selection.topology_id else None
    topology = None
    if record and record.is_active and record.topology_type == "conducted":
        try:
            topology = network_topology_service.get(db, str(record.id))
        except (ValueError, KeyError, TypeError):
            reasons.append("接线拓扑的设备或电缆登记不完整。")
    if not topology or not topology.is_validated or topology.validation_errors:
        reasons.append("请选择已验证的传导接线拓扑。")
    registration_key = {key: ids[key] for key in ("scenario_id", "direction", "topology_id", "asset_id")}
    registration_key["scenario_version"] = scenario.version
    candidates = [entry for entry in _registrations(lab)
                  if all(entry.get(key) == value for key, value in registration_key.items())]
    matches = [entry for entry in candidates if entry.get("scenario_sha256") == scenario_sha256]
    if candidates and not matches:
        reasons.append("实验室登记缺少当前场景内容的摘要，或场景已修改，请重新核对登记。")
    asset = db.get(ChannelAsset, selection.asset_id) if selection.asset_id else None
    summary = None
    mock_registration = matches[0] if len(matches) == 1 and matches[0].get("kind") == "asc_manifest" else None
    if mock_registration:
        try:
            summary = mock_asset(Directory(mock_registration["manifest_dir"]), mock_registration["name"])
            summary["id"] = ids["asset_id"]
            if playback_files is not None:
                playback_files["directory"] = mock_registration["manifest_dir"]
        except (KeyError, TypeError, ValueError, OSError) as exc:
            reasons.append(f"模拟资产清单校验失败：{exc}")
        drivers = get_hal_service().drivers
        if not all(is_mock_driver(drivers.get(key)) for key in ("baseStation", "channelEmulator")):
            reasons.append("八路 ASC 清单仅限模拟，基站和信道仿真器必须同时使用模拟驱动。")
    elif asset and asset.is_active and asset.source_type == "vendor_file" and _has_verified_smu_project_truth(
        asset.payload, asset.associated_file_path, asset.center_frequency_hz
    ) and (asset.associated_file_path or "").lower().endswith(".smu"):
        summary = {"id": str(asset.id), "name": asset.name, "sha256": asset.payload["smu_project_truth"]["sha256"],
                   "instrument_path": asset.associated_file_path,
                   "instrument_connection_id": str(asset.instrument_connection_id) if asset.instrument_connection_id else None}
    else:
        reasons.append("请选择已扫描并保存文件摘要的可播放工程。")
    binding = None
    if mock_registration:
        binding = {"execution_mode": "simulated", "mock_only": True}
    elif summary and lab and lab.is_active:
        try:
            bound = resolve_channel_emulator_binding(db, get_hal_service(), lab)
        except ValueError as exc:
            reasons.append(f"实验室的信道仿真器绑定未就绪：{exc}")
        else:
            binding = {"execution_mode": bound.execution_mode, "binding_digest": bound.binding_digest,
                       "instrument_connection_id": bound.instrument_connection_id,
                       "instrument_model_id": bound.instrument_model_id}
            if bound.execution_mode == "real":
                evidence, blockers = real_preflight(db, get_hal_service(), lab, asset, scenario.network)
                binding["real_preflight"] = evidence
                reasons.extend(blockers)
            if (bound.status != "configured" or not asset.instrument_connection_id
                    or not asset.instrument_model_id
                    or str(asset.instrument_connection_id) != bound.instrument_connection_id
                    or str(asset.instrument_model_id) != bound.instrument_model_id):
                reasons.append("工程所属的仪器型号或连接与实验室绑定不一致。")
        if str(asset.payload["scd_config"].get("mimo", "")).lower() != "4x2":
            reasons.append("工程登记的天线规模与下行四发二收不一致。")
    mapping = []
    if len(matches) != 1 or not summary or matches[0].get("sha256") != summary["sha256"]:
        reasons.append("实验室缺少唯一匹配场景版本、方向、拓扑和工程文件摘要的八路登记。")
    elif topology:
        mapping, error = _mapping(matches[0].get("port_mapping"), topology)
        if error:
            reasons.append(error)
    return {**ids, "scenario_version": scenario.version, "scenario_sha256": scenario_sha256,
            "scenario_snapshot": scenario_snapshot, "lab_name": lab.name if lab else None,
            "asset": summary, "binding": binding, "port_mapping": mapping, "ready": not reasons, "reasons": reasons}


@router.post("/prepare")
def prepare(selection: Selection, db: Session = Depends(get_db)):
    return resolve(db, selection)


@router.post("/executions", response_model=TestExecution, status_code=201)
def create(selection: Selection, db: Session = Depends(get_db)):
    snapshot = resolve(db, selection)
    row = vrt_execution_service.create(db, mode=TestMode.CONDUCTED, scenario_id=selection.scenario_id,
                                       topology_id=snapshot["topology_id"], conducted_setup=snapshot)
    return vrt_execution_service.to_test_execution(row)
