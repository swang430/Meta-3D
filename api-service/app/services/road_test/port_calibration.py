"""核对传导校准签发原文及本次工作点，无设备访问。"""
import base64
import csv
import hashlib
import io
import math
import os
import stat
from pathlib import Path
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.vrt_port_calibration import VrtPortCalibration

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Positive = Annotated[Number, Field(gt=0)]
Port = Annotated[int, Field(strict=True, gt=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportRecord(StrictModel):
    report_file: Text


class CalibrationScope(StrictModel):
    lab_profile_id: UUID
    topology_id: UUID
    topology_sha256: Digest
    scenario_sha256: Digest
    asset_sha256: Digest
    base_station_binding_digest: Digest
    channel_emulator_binding_digest: Digest
    direction: Literal["downlink"]
    center_frequency_hz: Positive
    bandwidth_mhz: Positive
    tx_power_dbm: Number
    base_station_id: Text
    channel_emulator_id: Text
    dut_id: Text


class Measurement(StrictModel):
    """参考面最大实测输入，加上不确定度后与允许上限比较。"""
    peak_dbm: Number
    uncertainty_db: Annotated[Number, Field(ge=0)]
    max_safe_input_dbm: Number
    limit_source: Text
    # 原始仪器读数与单位，dBm 原文必须能还原到该参考面的实测峰值。
    instrument_reply_dbm: Text

    @model_validator(mode="after")
    def check_readback(self):
        if not math.isfinite(self.max_safe_input_dbm - self.peak_dbm - self.uncertainty_db):
            raise ValueError("输入功率安全余量超出可计算范围")
        if float(self.instrument_reply_dbm) != self.peak_dbm:
            raise ValueError("原始功率读数与登记的实测峰值不一致")
        return self


class MeasuredPath(StrictModel):
    tx: Port
    rx: Port
    input_port: Port
    output_port: Port
    tx_reference_plane: Text
    emulator_input_reference_plane: Text
    emulator_output_reference_plane: Text
    dut_reference_plane: Text
    emulator_input: Measurement
    dut_input: Measurement


class CalibrationEvidence(StrictModel):
    schema_version: Literal["vrt_conducted_port_calibration_v1"]
    issuer: Text
    readings_file: Text
    readings_sha256: Digest
    source: Literal["physical_instrument_measurement"]
    # 要求信道工程按本次工作点全路同时播放；DUT端读数包含同时到达的所有通路。
    method: Literal["all_paths_active_peak_at_input_planes"]
    report_number: Text
    meter_serial: Text
    meter_certificate: Text
    meter_certificate_expires_at: AwareDatetime
    measured_at: AwareDatetime
    valid_until: AwareDatetime
    required_margin_db: Positive
    scope: CalibrationScope
    ports: list[MeasuredPath] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def complete(self):
        if not self.measured_at < self.valid_until <= self.meter_certificate_expires_at:
            raise ValueError("校准有效期必须晚于采集时间，且不能超过测量仪器证书有效期")
        if {(p.tx, p.rx) for p in self.ports} != {(t, r) for t in range(1, 5) for r in range(1, 3)}:
            raise ValueError("校准记录须覆盖四发二收的全部八个不同组合")
        for p in self.ports:
            expected = reference_planes(self.scope, p)
            if any(getattr(p, key) != value for key, value in expected.items()):
                raise ValueError("校准记录的参考面与设备和物理端口不符")
        return self


def reference_planes(scope, port):
    return {"tx_reference_plane": f"{scope.base_station_id}/out/{port.tx}",
            "emulator_input_reference_plane": f"{scope.channel_emulator_id}/in/{port.input_port}",
            "emulator_output_reference_plane": f"{scope.channel_emulator_id}/out/{port.output_port}",
            "dut_reference_plane": f"{scope.dut_id}/in/{port.rx}"}


def _read_approved_file(name, suffix):
    # 文件目录由实验室管理员在服务端配置。HTTP 接口只有读权限，不接受路径或上传。
    root = os.environ.get("VRT_CALIBRATION_APPROVED_DIR")
    if not root or not Path(root).is_absolute():
        raise ValueError("服务端尚未配置实验室已审核校准原件目录。")
    if Path(name).name != name or "/" in name or chr(92) in name or not name.endswith(suffix):
        raise ValueError("仅可选择已审核目录内的文件名。")
    path = Path(root) / name
    try:
        if path.is_symlink():
            raise ValueError("审核目录内的符号链接不能作校准原件。")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("已审核目录缺少可读取的普通文件。") from exc
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("校准原件必须是普通文件。")
        data = stream.read(2_000_001)
    if not data or len(data) > 2_000_000:
        raise ValueError("现场校准原件为空或超过大小限制。")
    return data


def read_report(filename):
    data = _read_approved_file(filename, ".json")
    evidence = CalibrationEvidence.model_validate_json(data)
    readings = _read_approved_file(evidence.readings_file, ".csv")
    if hashlib.sha256(readings).hexdigest() != evidence.readings_sha256:
        raise ValueError("仪器原始读数文件的摘要与已审核报告不一致。")
    raw = {}
    reader = csv.DictReader(io.StringIO(readings.decode("utf-8-sig")))
    fields = reader.fieldnames or []
    if len(set(fields)) != len(fields):
        raise ValueError("仪器原始读数文件含有重复列名。")
    for row in reader:
        key = tuple(int(row[field]) for field in ("tx", "rx", "input_port", "output_port"))
        if key in raw or row["source"] != "physical_instrument_measurement" or row["meter_serial"] != evidence.meter_serial:
            raise ValueError("原始仪器读数存在重复通路、模拟来源或仪器身份不符。")
        values = {k: float(row[k]) for k in ("base_station_output_dbm", "emulator_input_dbm",
                                              "emulator_output_dbm", "dut_input_dbm")}
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError("原始仪器读数必须为有限值。")
        raw[key] = values
    if set(raw) != {(p.tx, p.rx, p.input_port, p.output_port) for p in evidence.ports}:
        raise ValueError("原始仪器读数未覆盖报告的八路物理接线。")
    for p in evidence.ports:
        values = raw[p.tx, p.rx, p.input_port, p.output_port]
        if values["emulator_input_dbm"] != p.emulator_input.peak_dbm or values["dut_input_dbm"] != p.dut_input.peak_dbm:
            raise ValueError("原始输入端峰值与报告不符。")
        values["tx_cable_loss_db"] = values["base_station_output_dbm"] - values["emulator_input_dbm"]
        values["rx_cable_loss_db"] = values["emulator_output_dbm"] - values["dut_input_dbm"]
        if not all(math.isfinite(v) for v in values.values()) or min(values["tx_cable_loss_db"], values["rx_cable_loss_db"]) < 0:
            raise ValueError("被动电缆两端读数显示增益，请核对参考面与测量原文。")
    return evidence, data, readings, raw


def applicability(db, calibration_id, scope, mapping, *, duration_s=0):
    result = {"id": str(calibration_id) if calibration_id else None, "scope": scope,
              "applicable": False, "reasons": [], "ports": []}
    reasons = result["reasons"]
    row = db.get(VrtPortCalibration, calibration_id, populate_existing=True) if calibration_id else None
    if row is None:
        reasons.append("请选择已有现场测量原文的逐端口传导校准记录。")
        return result
    try:
        evidence, data, readings, raw = read_report(row.report_file)
        digest = hashlib.sha256(data).hexdigest()
        if data != base64.b64decode(row.evidence_b64) or readings != base64.b64decode(row.readings_b64):
            raise ValueError("已审核原文与登记时不一致。")
    except (OSError, KeyError, TypeError, ValueError, csv.Error) as exc:
        reasons.append(f"传导校准来源核验失败：{exc}")
        return result
    result.update(evidence_sha256=digest, issuer=row.issuer, report_number=evidence.report_number,
                  valid_until=evidence.valid_until.isoformat(), readings_sha256=evidence.readings_sha256,
                  meter_serial=evidence.meter_serial, meter_certificate=evidence.meter_certificate,
                  measured_at=evidence.measured_at.isoformat(), source=evidence.source, required_margin_db=evidence.required_margin_db)
    if row.revoked_at is not None:
        reasons.append(f"传导校准已撤销：{row.revocation_reason}")
    if row.evidence_sha256 != digest:
        reasons.append("传导校准原文与存档摘要不符。")
    now = datetime.now(timezone.utc)
    if not evidence.measured_at <= now < evidence.valid_until:
        reasons.append("当前时间不在传导校准有效期内。")
    elif not math.isfinite(duration_s) or duration_s < 0 or (evidence.valid_until - now).total_seconds() <= duration_s:
        reasons.append("传导校准有效期未覆盖整段播放。")
    if evidence.scope.model_dump(mode="json") != scope:
        reasons.append("传导校准的实验室、绑定、接线、工程或功率工作点与本次执行不一致。")
    measured = {(p.tx, p.rx, p.input_port, p.output_port) for p in evidence.ports}
    if measured != {tuple(p[k] for k in ("tx", "rx", "input_port", "output_port")) for p in mapping}:
        reasons.append("传导校准的八路物理端口映射与本次接线不一致。")
    for p in evidence.ports:
        item = {**p.model_dump(), **raw[p.tx, p.rx, p.input_port, p.output_port]}
        for key in ("emulator_input", "dut_input"):
            reading = getattr(p, key)
            margin = reading.max_safe_input_dbm - reading.peak_dbm - reading.uncertainty_db
            item[key + "_margin_db"] = margin
            if margin < evidence.required_margin_db:
                reasons.append(f"发射端口 {p.tx} 至接收端口 {p.rx} 的{ '仿真器' if key == 'emulator_input' else '被测设备'}输入功率安全余量不足。")
        result["ports"].append(item)
    result["applicable"] = not reasons
    return result
