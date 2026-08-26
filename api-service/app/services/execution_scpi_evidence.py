"""P1-47C：把仪器证据摘要绑定到产生它的 TestExecution。

原始响应仍只保存在 ``scpi.log``。这里持久化可公开消费的脱敏摘要，并以
``execution_id + exchange_ids`` 回链原始往返。正式判定采用 fail-closed：
必需项缺失、unknown、rejected 或环境范围不成立时均不得显示“正式通过”。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm.attributes import flag_modified

from app.core.logging_config import current_execution_id
from app.hal.base import (
    redact_instrument_command_text,
    redact_instrument_log_text,
)
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    InstrumentEnvironment,
    InstrumentEvidenceItem,
    ScpiExchangeRef,
    exchange_matches_catalog_role,
)


_SENSITIVE_KEYS = {
    "auth", "authentication", "ki", "opc", "password", "passwd",
    "secret", "token", "authentication_key",
}


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(
        (
            "_password",
            "_passwd",
            "_secret",
            "_token",
            "_api_key",
            "_auth_key",
            "_private_key",
            "_encryption_key",
        )
    )


def _sanitize(value: Any, *, parent_key: Optional[str] = None) -> Any:
    """递归生成 JSON-safe 公共副本；不把认证秘密带入执行表。"""
    if parent_key is not None and _is_sensitive_key(parent_key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(key): _sanitize(item, parent_key=str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_instrument_log_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_instrument_log_text(str(value))


def _environment_fingerprint(environment: Any) -> str:
    """给脱敏后的环境快照生成稳定指纹，防同类仪器热换后借用旧证据。"""
    payload = json.dumps(
        _sanitize(environment),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class RequiredEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    evidence_key: str
    requested: Any = None
    required_evidence_level: EvidenceLevel = EvidenceLevel.TRANSPORT


class ExecutionEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    instrument: str
    evidence_key: str
    requested: Any
    command_sent: Optional[str]
    readback: Any = None
    exchange_ids: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel
    source_reference: Optional[str]
    verdict: EvidenceVerdict
    reason: str


class ExecutionScpiEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    execution_id: str
    environments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    required: list[RequiredEvidence] = Field(default_factory=list)
    items: list[ExecutionEvidenceItem] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    formal_verdict: EvidenceVerdict = EvidenceVerdict.UNKNOWN
    formal_acceptance: bool = False
    reason: str = "not_finalized"


def _empty(execution) -> ExecutionScpiEvidence:
    return ExecutionScpiEvidence(execution_id=str(execution.id))


def _load(execution) -> ExecutionScpiEvidence:
    raw_config = getattr(execution, "config", None)
    cfg = raw_config if isinstance(raw_config, dict) else {}
    raw = cfg.get("scpi_evidence")
    if not isinstance(raw, dict):
        return _empty(execution)
    try:
        evidence = ExecutionScpiEvidence.model_validate(raw)
    except Exception:
        # Brownfield/畸形数据不能污染新执行；公开读取另走严格的 None 降级。
        return _empty(execution)
    if evidence.execution_id != str(execution.id):
        return _empty(execution)
    return evidence


def _save(execution, evidence: ExecutionScpiEvidence) -> None:
    cfg = dict(execution.config or {})
    cfg["scpi_evidence"] = evidence.model_dump(mode="json")
    execution.config = cfg
    flag_modified(execution, "config")


def _load_provenance(execution) -> dict[str, dict[str, Any]]:
    raw_config = getattr(execution, "config", None)
    cfg = raw_config if isinstance(raw_config, dict) else {}
    raw = cfg.get("scpi_evidence_provenance")
    return dict(raw) if isinstance(raw, dict) else {}


def _save_provenance(execution, provenance: dict[str, dict[str, Any]]) -> None:
    cfg = dict(execution.config or {})
    cfg["scpi_evidence_provenance"] = provenance
    execution.config = cfg
    flag_modified(execution, "config")


def register_required_scpi_evidence(
    execution,
    *,
    requirement_id: str,
    evidence_key: str,
    requested: Any,
    required_evidence_level: EvidenceLevel = EvidenceLevel.TRANSPORT,
) -> None:
    """登记本次执行必须具备的一项证据；同 id 幂等更新。"""
    evidence = _load(execution)
    requirement = RequiredEvidence(
        requirement_id=requirement_id,
        evidence_key=evidence_key,
        requested=_sanitize(requested),
        required_evidence_level=required_evidence_level,
    )
    evidence.required = [
        item for item in evidence.required if item.requirement_id != requirement_id
    ]
    evidence.required.append(requirement)
    provenance = _load_provenance(execution)
    provenance.pop(requirement_id, None)
    evidence.formal_verdict = EvidenceVerdict.UNKNOWN
    evidence.formal_acceptance = False
    evidence.reason = "not_finalized"
    _save(execution, evidence)
    _save_provenance(execution, provenance)


def record_execution_scpi_evidence(
    execution,
    *,
    requirement_id: str,
    item: InstrumentEvidenceItem,
    environment: Optional[InstrumentEnvironment] = None,
    exchanges: Optional[list[ScpiExchangeRef]] = None,
) -> None:
    """记录固定摘要；拒绝把另一次执行上下文的证据挂到当前行。"""
    active = current_execution_id.get("-")
    if active != str(execution.id):
        raise ValueError(
            f"execution context mismatch: active={active!r}, target={execution.id}"
        )
    evidence = _load(execution)
    requirement = next(
        (req for req in evidence.required if req.requirement_id == requirement_id),
        None,
    )
    if requirement is None:
        raise ValueError(f"SCPI evidence requirement not registered: {requirement_id}")
    if requirement.evidence_key != item.evidence_key:
        raise ValueError(
            "SCPI evidence key mismatch: "
            f"required={requirement.evidence_key}, item={item.evidence_key}"
        )

    selected = list(exchanges or [])
    selected_by_id = {exchange.exchange_id: exchange for exchange in selected}
    referenced = [selected_by_id.get(exchange_id) for exchange_id in item.exchange_ids]
    provenance_errors: list[str] = []
    if not item.exchange_ids:
        provenance_errors.append("exchange_ids_empty")
    if len(selected_by_id) != len(selected):
        provenance_errors.append("capture_has_duplicate_exchange_ids")
    if any(exchange is None for exchange in referenced):
        provenance_errors.append("exchange_id_not_in_capture")
    present = [exchange for exchange in referenced if exchange is not None]
    if present:
        if any(exchange.simulated for exchange in present):
            provenance_errors.append("simulated_exchange_not_authoritative")
        if [exchange.exchange_id for exchange in selected if exchange.exchange_id in item.exchange_ids] != item.exchange_ids:
            provenance_errors.append("exchange_ids_not_in_capture_order")
        if {exchange.execution_id for exchange in present} != {str(execution.id)}:
            provenance_errors.append("exchange_execution_mismatch")
        capture_ids = {exchange.capture_id for exchange in present}
        if len(capture_ids) != 1 or "" in capture_ids:
            provenance_errors.append("exchange_capture_mismatch")
        if environment is not None and {
            exchange.instrument_id for exchange in present
        } != {environment.instrument_id}:
            provenance_errors.append("exchange_instrument_mismatch")
    if not item.source_reference:
        provenance_errors.append("source_reference_missing")
    if (
        environment is None
        or not environment.captured_from_live_connection
        or environment.instrument != item.instrument
    ):
        provenance_errors.append("live_environment_missing_or_mismatched")

    public_verdict = item.verdict
    public_reason = item.reason
    if provenance_errors:
        public_verdict = EvidenceVerdict.UNKNOWN
        public_reason = "invalid_evidence_provenance:" + ",".join(provenance_errors)

    public_item = ExecutionEvidenceItem(
        requirement_id=requirement_id,
        instrument=item.instrument,
        evidence_key=item.evidence_key,
        requested=_sanitize(item.requested),
        command_sent=(
            redact_instrument_command_text(item.command_sent)
            if item.command_sent is not None else None
        ),
        readback=_sanitize(item.readback),
        exchange_ids=list(item.exchange_ids),
        evidence_level=item.evidence_level,
        source_reference=_sanitize(item.source_reference),
        verdict=public_verdict,
        reason=redact_instrument_log_text(public_reason),
    )
    evidence.items = [
        existing
        for existing in evidence.items
        if existing.requirement_id != requirement_id
    ]
    evidence.items.append(public_item)
    sanitized_environment = None
    if environment is not None:
        sanitized_environment = _sanitize(environment.model_dump(mode="json"))
        evidence.environments[environment.instrument_id] = sanitized_environment
    provenance = _load_provenance(execution)
    if not provenance_errors and present:
        provenance[requirement_id] = {
            "execution_id": str(execution.id),
            "capture_id": present[0].capture_id,
            "exchange_ids": list(item.exchange_ids),
            "instrument_id": environment.instrument_id,
            "environment_fingerprint": _environment_fingerprint(
                sanitized_environment
            ),
        }
    else:
        provenance.pop(requirement_id, None)
    evidence.formal_verdict = EvidenceVerdict.UNKNOWN
    evidence.formal_acceptance = False
    evidence.reason = "not_finalized"
    _save(execution, evidence)
    _save_provenance(execution, provenance)


def finalize_execution_scpi_evidence(execution) -> ExecutionScpiEvidence:
    """计算正式总判定。无必需项也不是通过，防“空集合全绿”。"""
    evidence = _load(execution)
    by_requirement = {item.requirement_id: item for item in evidence.items}
    provenance = _load_provenance(execution)
    evidence.missing_requirements = [
        req.requirement_id
        for req in evidence.required
        if req.requirement_id not in by_requirement
    ]
    mandatory_items = [
        by_requirement[req.requirement_id]
        for req in evidence.required
        if req.requirement_id in by_requirement
    ]
    rejected = [
        item.requirement_id
        for item in mandatory_items
        if item.verdict is EvidenceVerdict.REJECTED
    ]
    unknown = [
        item.requirement_id
        for item in mandatory_items
        if item.verdict is not EvidenceVerdict.PASSED
    ]
    level_order = {
        EvidenceLevel.INTENT: 0,
        EvidenceLevel.TRANSPORT: 1,
        EvidenceLevel.ACCEPTED: 2,
        EvidenceLevel.APPLIED: 3,
        EvidenceLevel.OUTCOME: 4,
    }
    insufficient = [
        req.requirement_id
        for req in evidence.required
        if (
            (item := by_requirement.get(req.requirement_id)) is not None
            and item.verdict is EvidenceVerdict.PASSED
            and level_order[item.evidence_level]
            < level_order[req.required_evidence_level]
        )
    ]
    requested_mismatch = [
        req.requirement_id
        for req in evidence.required
        if (
            (item := by_requirement.get(req.requirement_id)) is not None
            and item.requested != req.requested
        )
    ]
    invalid_provenance = []
    for req in evidence.required:
        item = by_requirement.get(req.requirement_id)
        if item is None:
            continue
        origin = provenance.get(req.requirement_id)
        instrument_id = origin.get("instrument_id") if isinstance(origin, dict) else None
        environment = evidence.environments.get(instrument_id) if instrument_id else None
        live_environment = (
            isinstance(environment, dict)
            and environment.get("instrument") == item.instrument
            and environment.get("captured_from_live_connection") is True
            and origin.get("environment_fingerprint")
            == _environment_fingerprint(environment)
        )
        if (
            not isinstance(origin, dict)
            or origin.get("execution_id") != str(execution.id)
            or not origin.get("capture_id")
            or origin.get("exchange_ids") != item.exchange_ids
            or not item.exchange_ids
            or not item.source_reference
            or not live_environment
        ):
            invalid_provenance.append(req.requirement_id)

    raw_measurements = getattr(execution, "measurements", None)
    measurements = raw_measurements if isinstance(raw_measurements, dict) else {}
    phases = measurements.get("phases")
    measure = phases.get("measure") if isinstance(phases, dict) else None
    frequency_consistency = (
        measure.get("frequency_consistency") if isinstance(measure, dict) else None
    )
    frequency_identity_unverified = (
        isinstance(frequency_consistency, dict)
        and frequency_consistency.get("fully_verified") is not True
    )

    if rejected:
        evidence.formal_verdict = EvidenceVerdict.REJECTED
        evidence.reason = "mandatory_evidence_rejected:" + ",".join(rejected)
    elif frequency_identity_unverified:
        evidence.formal_verdict = EvidenceVerdict.UNKNOWN
        evidence.reason = "frequency_identity_not_fully_verified"
    elif not evidence.required:
        evidence.formal_verdict = EvidenceVerdict.UNKNOWN
        evidence.reason = "no_mandatory_evidence_registered"
    elif evidence.missing_requirements:
        evidence.formal_verdict = EvidenceVerdict.UNKNOWN
        evidence.reason = "mandatory_evidence_missing:" + ",".join(
            evidence.missing_requirements
        )
    elif requested_mismatch:
        evidence.formal_verdict = EvidenceVerdict.UNKNOWN
        evidence.reason = "mandatory_requested_mismatch:" + ",".join(
            requested_mismatch
        )
    elif invalid_provenance:
        evidence.formal_verdict = EvidenceVerdict.UNKNOWN
        evidence.reason = "mandatory_evidence_provenance_invalid:" + ",".join(
            invalid_provenance
        )
    elif unknown:
        evidence.formal_verdict = EvidenceVerdict.UNKNOWN
        evidence.reason = "mandatory_evidence_unconfirmed:" + ",".join(unknown)
    elif insufficient:
        evidence.formal_verdict = EvidenceVerdict.UNKNOWN
        evidence.reason = "mandatory_evidence_level_insufficient:" + ",".join(
            insufficient
        )
    else:
        evidence.formal_verdict = EvidenceVerdict.PASSED
        evidence.reason = "all_mandatory_evidence_confirmed"
    evidence.formal_acceptance = evidence.formal_verdict is EvidenceVerdict.PASSED
    _save(execution, evidence)
    return evidence


def public_execution_scpi_evidence(execution) -> Optional[dict[str, Any]]:
    """API/报告只读取能通过严格模型且属于本执行的脱敏摘要。"""
    raw_config = getattr(execution, "config", None)
    cfg = raw_config if isinstance(raw_config, dict) else {}
    raw = cfg.get("scpi_evidence")
    if not isinstance(raw, dict):
        return None
    if any(
        str(item.get("requirement_id", "")).startswith("uxm.")
        or str(item.get("evidence_key", "")).startswith("uxm.")
        for item in [*(raw.get("required") or []), *(raw.get("items") or [])]
        if isinstance(item, dict)
    ):
        raw = translate_legacy_uxm_execution_evidence(
            raw, execution_id=str(execution.id)
        )
        if raw is None:
            return None
    try:
        evidence = ExecutionScpiEvidence.model_validate(raw)
    except Exception:
        return None
    if evidence.execution_id != str(execution.id):
        return None
    # 再脱敏一次，防 brownfield 行绕过当前写入口。
    return _sanitize(evidence.model_dump(mode="json"))


_LEGACY_UXM_REQUIREMENT_IDS = {
    "uxm.pcell.config_applied": "base_station.pcell.config_applied",
    "uxm.pcell.arfcn": "base_station.pcell.channel_number",
}
_LEGACY_UXM_EVIDENCE_KEYS = {
    "uxm.config_apply": "base_station.config_apply",
    "uxm.config_readback": "base_station.config_readback",
    "uxm.dl_throughput": "base_station.dl_throughput",
}


def _translate_legacy_uxm_requirement_id(value: Any) -> Optional[str]:
    text = str(value)
    if text in _LEGACY_UXM_REQUIREMENT_IDS:
        return _LEGACY_UXM_REQUIREMENT_IDS[text]
    prefix = "uxm.throughput.azimuth."
    if text.startswith(prefix) and text[len(prefix):].isdigit():
        return "base_station.throughput.azimuth." + text[len(prefix):]
    return None


def translate_legacy_uxm_execution_evidence(
    raw: Any, *, execution_id: str
) -> Optional[dict[str, Any]]:
    """窄读旧 UXM 摘要；身份、字段或映射冲突时整体降级 unknown。

    该 translator 只服务 brownfield 读取。新写方必须直接产生
    ``base_station.*``，不得借此继续写旧键。
    """
    if not isinstance(raw, dict) or raw.get("execution_id") != execution_id:
        return None
    environments = raw.get("environments")
    environment = (
        environments.get("baseStation")
        if isinstance(environments, dict)
        else None
    )
    if not isinstance(environment, dict):
        return None
    if (
        environment.get("instrument") != "uxm"
        or environment.get("captured_from_live_connection") is not True
        or not str(environment.get("model") or "").strip()
        or not str(environment.get("firmware_version") or "").strip()
    ):
        return None

    translated = _sanitize(raw)
    translated_environment = translated["environments"]["baseStation"]
    translated_environment["adapter_id"] = "uxm"
    translated_environment.setdefault("options", [])

    for requirement in translated.get("required", []):
        if not isinstance(requirement, dict):
            return None
        raw_requirement_id = str(requirement.get("requirement_id"))
        raw_evidence_key = str(requirement.get("evidence_key"))
        is_legacy_requirement = raw_requirement_id.startswith("uxm.")
        is_legacy_key = raw_evidence_key.startswith("uxm.")
        if not is_legacy_requirement and not is_legacy_key:
            continue
        if is_legacy_requirement != is_legacy_key:
            return None
        requirement_id = _translate_legacy_uxm_requirement_id(
            raw_requirement_id
        )
        evidence_key = _LEGACY_UXM_EVIDENCE_KEYS.get(raw_evidence_key)
        if requirement_id is None or evidence_key is None:
            return None
        requirement["requirement_id"] = requirement_id
        requirement["evidence_key"] = evidence_key

    for item in translated.get("items", []):
        if not isinstance(item, dict):
            return None
        raw_requirement_id = str(item.get("requirement_id"))
        raw_evidence_key = str(item.get("evidence_key"))
        is_legacy_item = (
            item.get("instrument") == "uxm"
            or raw_requirement_id.startswith("uxm.")
            or raw_evidence_key.startswith("uxm.")
        )
        if not is_legacy_item:
            continue
        if (
            item.get("instrument") != "uxm"
            or not raw_requirement_id.startswith("uxm.")
            or not raw_evidence_key.startswith("uxm.")
        ):
            return None
        requirement_id = _translate_legacy_uxm_requirement_id(
            raw_requirement_id
        )
        evidence_key = _LEGACY_UXM_EVIDENCE_KEYS.get(raw_evidence_key)
        if requirement_id is None or evidence_key is None:
            return None
        item["requirement_id"] = requirement_id
        item["evidence_key"] = evidence_key

    translated_missing: list[str] = []
    for value in translated.get("missing_requirements", []):
        if not str(value).startswith("uxm."):
            translated_missing.append(str(value))
            continue
        mapped = _translate_legacy_uxm_requirement_id(value)
        if mapped is None:
            return None
        translated_missing.append(mapped)
    translated["missing_requirements"] = translated_missing
    return translated


def _find_exchange(
    exchanges: list[ScpiExchangeRef],
    evidence_key: str,
    field_name: str,
    *,
    optional_bse: bool = False,
    reverse: bool = False,
) -> Optional[ScpiExchangeRef]:
    source = reversed(exchanges) if reverse else exchanges
    return next(
        (
            exchange
            for exchange in source
            if exchange_matches_catalog_role(
                exchange, evidence_key, field_name, optional_bse=optional_bse
            )
        ),
        None,
    )


def record_base_station_config_capture(
    execution,
    *,
    requirement_id: str,
    requested: Any,
    driver,
    exchanges: list[ScpiExchangeRef],
    _stored_evidence_key: str = "base_station.config_apply",
) -> None:
    """绑定 PCell 写→回读→（APPLY 或 CELL ON）→协议状态事务。"""
    from app.hal.scpi_evidence import exchange_matches_uxm_cell_activation

    command = next(
        (
            exchange
            for exchange in exchanges
            if exchange.operation == "command"
            and "ARFCN" in exchange.command.upper()
            and exchange_matches_catalog_role(
                exchange, "uxm.config_readback", "command", optional_bse=True
            )
        ),
        None,
    )
    query = None
    if command is not None:
        command_header = command.command.strip().split(maxsplit=1)[0].upper()
        command_header = command_header.removeprefix("BSE:")
        query = next(
            (
                exchange
                for exchange in exchanges
                if exchange.operation == "query"
                and exchange.command.strip().split(maxsplit=1)[0]
                .upper().removesuffix("?").removeprefix("BSE:")
                == command_header
            ),
            None,
        )
    item = driver.build_p0_5_config_evidence(
        evidence_key="uxm.config_apply",
        requested=requested,
        command_exchange=command,
        readback_exchange=query,
        apply_exchange=_find_exchange(
            exchanges, "uxm.config_apply", "command", optional_bse=True
        ),
        protocol_state_exchange=_find_exchange(
            exchanges, "uxm.cell_status", "query", optional_bse=True, reverse=True
        ),
        activation_exchange=next(
            (
                exchange
                for exchange in exchanges
                if exchange_matches_uxm_cell_activation(exchange)
                and (command is None or exchange.sequence > command.sequence)
            ),
            None,
        ),
    )
    item = item.model_copy(update={"evidence_key": _stored_evidence_key})
    record_execution_scpi_evidence(
        execution,
        requirement_id=requirement_id,
        item=item,
        environment=driver.capture_evidence_environment(),
        exchanges=exchanges,
    )


def record_uxm_config_capture(*args, **kwargs) -> None:
    """Deprecated compatibility wrapper; new writers use BaseStation naming."""
    record_base_station_config_capture(
        *args, _stored_evidence_key="uxm.config_apply", **kwargs
    )


def record_f64_command_capture(
    execution,
    *,
    requirement_id: str,
    evidence_key: str,
    requested: Any,
    driver,
    exchanges: list[ScpiExchangeRef],
) -> None:
    """记录 F64 写入的 OPC/错误门/回读；缺任何一段由 B 层判 unknown。"""
    command = _find_exchange(
        exchanges,
        evidence_key,
        "command",
        reverse=evidence_key == "f64.bypass_mode",
    )
    command_index = exchanges.index(command) if command in exchanges else len(exchanges)
    # 只取紧邻目标写入之前的清队列段；更早的错误查询若隔着其它命令，不能
    # 冒充本事务的 preclear，也不该让合法的后一个 preclear 因“跨段”假失败。
    preclear_reversed: list[ScpiExchangeRef] = []
    for exchange in reversed(exchanges[:command_index]):
        if not exchange_matches_catalog_role(exchange, "f64.error_queue", "query"):
            break
        preclear_reversed.append(exchange)
    preclear = list(reversed(preclear_reversed))
    after = exchanges[command_index + 1 :] if command in exchanges else []
    opc_exchange = _find_exchange(after, "f64.operation_complete", "query")
    opc_index = after.index(opc_exchange) if opc_exchange in after else -1
    after_opc = after[opc_index + 1 :] if opc_index >= 0 else after
    error_exchange = _find_exchange(after_opc, "f64.error_queue", "query")
    error_index = (
        after_opc.index(error_exchange) if error_exchange in after_opc else -1
    )
    after_error = after_opc[error_index + 1 :] if error_index >= 0 else after_opc
    if evidence_key == "f64.simulation_state":
        readback_key = "f64.simulation_state"
    elif evidence_key == "f64.bypass_mode":
        readback_key = "f64.bypass_mode"
    else:
        readback_key = "f64.model_state"
    item = driver.build_p0_5_command_evidence(
        evidence_key=evidence_key,
        requested=requested,
        preclear_exchanges=preclear,
        command_exchange=command,
        opc_exchange=opc_exchange,
        error_exchange=error_exchange,
        readback_exchange=_find_exchange(
            after_error,
            readback_key,
            "query",
        ),
        state_exchange=_find_exchange(
            after_error, "f64.simulation_state", "query", reverse=True
        ),
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id=requirement_id,
        item=item,
        environment=driver.capture_evidence_environment(),
        exchanges=exchanges,
    )


def record_positioner_capture(
    execution,
    *,
    requirement_id: str,
    requested_angle_deg: float,
    driver,
    exchanges: list[ScpiExchangeRef],
) -> None:
    az_axis = str(getattr(driver, "az_axis", "X")).strip().upper()
    feedback = next(
        (
            exchange
            for exchange in reversed(exchanges)
            if exchange_matches_catalog_role(
                exchange, "positioner.position_feedback", "query"
            )
            and "".join(exchange.command.upper().split()) == f"PFBK({az_axis})"
        ),
        None,
    )
    item = driver.build_p0_5_position_evidence(
        requested_angle_deg=requested_angle_deg,
        coordinate_offset_deg=None,
        offset_calibrated=False,
        tolerance_deg=1.0,
        move_exchange=_find_exchange(
            exchanges, "positioner.move_absolute", "command"
        ),
        # 双轴 move_to 最后一条 PFBK 是 elevation；必须精确绑定 az_axis，
        # 否则会拿俯仰反馈核对方位请求。
        feedback_exchange=feedback,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id=requirement_id,
        item=item,
        environment=driver.capture_evidence_environment(),
        exchanges=exchanges,
    )


def record_base_station_throughput_capture(
    execution,
    *,
    requirement_id: str,
    requested: Any,
    driver,
    exchanges: list[ScpiExchangeRef],
    _stored_evidence_key: str = "base_station.dl_throughput",
) -> None:
    item = driver.build_p0_5_throughput_evidence(
        requested=requested,
        throughput_exchange=_find_exchange(
            exchanges, "uxm.dl_throughput", "query", reverse=True
        ),
    )
    item = item.model_copy(update={"evidence_key": _stored_evidence_key})
    record_execution_scpi_evidence(
        execution,
        requirement_id=requirement_id,
        item=item,
        environment=driver.capture_evidence_environment(),
        exchanges=exchanges,
    )


def record_uxm_throughput_capture(*args, **kwargs) -> None:
    """Deprecated compatibility wrapper; new writers use BaseStation naming."""
    record_base_station_throughput_capture(
        *args, _stored_evidence_key="uxm.dl_throughput", **kwargs
    )
