"""传导准备与建档。设备控制由执行器负责。"""
import hashlib
import json
import re
from pathlib import Path as Directory
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.api import vrt_port_calibration
from app.services.road_test.port_calibration import applicability
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

router.include_router(vrt_port_calibration.router)


class ReceiverPowerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    reference_frame: int = Field(ge=0)
    targets_dbm: dict[int, float] = Field(default_factory=dict)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1)
    direction: str = "downlink"
    lab_profile_id: UUID | None = None
    topology_id: UUID | None = None
    asset_id: UUID | None = None
    calibration_id: UUID | None = None
    receiver_power: ReceiverPowerRequest | None = None


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


class ConductedOption(BaseModel):
    id: str
    name: str
    mock_only: bool | None = None


class ConductedOptions(BaseModel):
    labs: list[ConductedOption]
    topologies: list[ConductedOption]
    assets: list[ConductedOption]


@router.get("/options", response_model=ConductedOptions, response_model_exclude_unset=True)
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


def real_preflight(db, hal, lab, asset, network, *, calibration_id=None, scope=None, mapping=(), duration_s=0, frequency_mhz=None):
    """核对真实设备所需的已登记证据；此处不取得控制权。"""
    scd = asset.payload["scd_config"]
    working_point = vendor_scd_frequency_identity(scd, allow_legacy_nr=True)
    evidence = {"center_frequency_hz": working_point.center_frequency_hz,
                "bandwidth_mhz": working_point.bandwidth_mhz}
    reasons = []
    if frequency_mhz is not None and frequency_mhz * 1e6 != working_point.center_frequency_hz:
        reasons.append("场景指定的中心频率与工程工作点不一致。")
    if scope is not None and scope.get("tx_power_dbm") is None:
        reasons.append("需要唯一的基站小区功率工作点，物理端口功率另从现场读数核对。")
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
        if station.execution_mode != "real" or not station.instrument_connection_id or station.status not in ("configured", "not_applicable"):
            reasons.append("该实验室未绑定可用于此次执行的真实基站。")
    scope = {**(scope or {}), "center_frequency_hz": working_point.center_frequency_hz,
             "bandwidth_mhz": working_point.bandwidth_mhz,
             "base_station_binding_digest": evidence.get("base_station_binding_digest")}
    calibration = applicability(db, calibration_id, scope, mapping, duration_s=duration_s)
    evidence["calibration"] = calibration
    reasons.extend(calibration["reasons"])
    return evidence, reasons


def resolve(db: Session, selection: Selection, *, playback_files=None):
    ids = selection.model_dump(mode="json")
    if selection.receiver_power is None:
        ids.pop("receiver_power")
    if selection.calibration_id is None:
        ids.pop("calibration_id")
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
    mapping = []
    if len(matches) != 1 or not summary or matches[0].get("sha256") != summary["sha256"]:
        reasons.append("实验室缺少唯一匹配场景版本、方向、拓扑和工程文件摘要的八路登记。")
    elif topology:
        mapping, error = _mapping(matches[0].get("port_mapping"), topology)
        if error:
            reasons.append(error)
    binding = None
    if mock_registration:
        if selection.calibration_id:
            reasons.append("模拟资产不能使用真实传导校准记录。")
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
                # 接线标识和实际电缆资料均参与比对，改接或更换电缆会使旧记录失效。
                wiring = topology.model_dump(mode="json", include={"base_station", "channel_emulator", "dut", "connections"}) if topology else {}
                wiring_digest = hashlib.sha256(json.dumps(wiring, sort_keys=True, separators=(",", ":"),
                                                          ensure_ascii=False).encode()).hexdigest()
                scope = {"lab_profile_id": str(lab.id), "topology_id": ids["topology_id"],
                         "topology_sha256": wiring_digest, "scenario_sha256": scenario_sha256,
                         "asset_sha256": summary["sha256"], "channel_emulator_binding_digest": bound.binding_digest,
                         "direction": selection.direction,
                         "base_station_id": topology.base_station.device_id if topology else None,
                         "channel_emulator_id": topology.channel_emulator.device_id if topology else None,
                         "dut_id": topology.dut.device_id if topology else None,
                         "tx_power_dbm": scenario.base_stations[0].tx_power_dbm if len(scenario.base_stations) == 1 else None}
                steps = scenario.step_configuration
                net_step = steps.network_config if steps else None
                evidence, blockers = real_preflight(db, get_hal_service(), lab, asset, scenario.network,
                                                    calibration_id=selection.calibration_id, scope=scope, mapping=mapping,
                                                    duration_s=scenario.route.duration_s,
                                                    frequency_mhz=net_step.frequency_mhz if net_step else None)
                binding["real_preflight"] = evidence
                reasons.extend(blockers)
            if (bound.status != "configured" or not asset.instrument_connection_id
                    or not asset.instrument_model_id
                    or str(asset.instrument_connection_id) != bound.instrument_connection_id
                    or str(asset.instrument_model_id) != bound.instrument_model_id):
                reasons.append("工程所属的仪器型号或连接与实验室绑定不一致。")
        if str(asset.payload["scd_config"].get("mimo", "")).lower() != "4x2":
            reasons.append("工程登记的天线规模与下行四发二收不一致。")
    if selection.receiver_power is not None:
        from app.services.road_test.receiver_power_plan import registered_plan
        try:
            if not summary or len(matches) != 1 or not binding:
                raise ValueError("请先选定与当前场景、工程和端口匹配的登记")
            calibration = (binding.get("real_preflight") or {}).get("calibration") or {}
            plan = registered_plan(matches[0], summary["sha256"], scenario.network.bandwidth_mhz,
                                   selection.receiver_power.reference_frame,
                                   selection.receiver_power.targets_dbm, calibration)
            binding["receiver_power_plan"] = plan
            if binding.get("execution_mode") == "real" and not plan["verified_operating_point"]:
                reasons.append("需核对工程电平参考面、输出范围及目标平均功率工作点，方可按此预测发射。")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            reasons.append(f"接收功率计划未通过核对：{exc}")
    return {**ids, "scenario_version": scenario.version, "scenario_sha256": scenario_sha256,
            "scenario_snapshot": scenario_snapshot, "lab_name": lab.name if lab else None,
            "asset": summary, "binding": binding, "port_mapping": mapping, "ready": not reasons, "reasons": reasons}


class CalibrationApplicability(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None
    applicable: bool
    reasons: list[str]
    scope: dict
    ports: list[dict]
    evidence_sha256: str | None = None


class ConductedPreflight(BaseModel):
    model_config = ConfigDict(extra="allow")
    center_frequency_hz: float | None
    bandwidth_mhz: float | None
    calibration: CalibrationApplicability


class ConductedBinding(BaseModel):
    model_config = ConfigDict(extra="allow")
    execution_mode: str | None
    real_preflight: ConductedPreflight | None = None


class ConductedPreparation(Selection):
    scenario_sha256: str
    scenario_version: str
    scenario_snapshot: dict
    lab_name: str | None
    asset: dict | None
    binding: ConductedBinding | None
    port_mapping: list[Path]
    ready: bool
    reasons: list[str]


@router.post("/prepare", response_model=ConductedPreparation, response_model_exclude_unset=True)
def prepare(selection: Selection, db: Session = Depends(get_db)):
    return resolve(db, selection)


@router.post("/executions", response_model=TestExecution, status_code=201)
def create(selection: Selection, db: Session = Depends(get_db)):
    snapshot = resolve(db, selection)
    row = vrt_execution_service.create(db, mode=TestMode.CONDUCTED, scenario_id=selection.scenario_id,
                                       topology_id=snapshot["topology_id"], conducted_setup=snapshot)
    return vrt_execution_service.to_test_execution(row)
