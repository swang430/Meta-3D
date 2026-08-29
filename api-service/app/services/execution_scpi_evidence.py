"""P1-47C：把仪器证据摘要绑定到产生它的 TestExecution。

原始响应仍只保存在 ``scpi.log``。这里持久化可公开消费的脱敏摘要，并以
``execution_id + exchange_ids`` 回链原始往返。正式判定采用 fail-closed：
必需项缺失、unknown、rejected 或环境范围不成立时均不得显示“正式通过”。
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm.attributes import flag_modified

from app.core.logging_config import current_execution_id
from app.hal.base import (
    redact_instrument_command_text,
    redact_instrument_log_text,
)
from app.hal.base_station import (
    BaseStationAttachReceipt,
    BaseStationApplyReceipt,
    BaseStationCleanupResult,
    BaseStationControlReleaseResult,
    BaseStationIdentity,
    BaseStationMeasurementWindow,
    BaseStationRequestedConfig,
)
from app.hal.base_station_manifest import BaseStationAdapterManifest
from app.hal.base_station_adapter_profile import BaseStationAdapterProfileResolution
from app.models.test_plan import TestExecution
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    InstrumentEnvironment,
    InstrumentEvidenceItem,
    ScpiExchangeRef,
    exchange_matches_catalog_role,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    BASE_STATION_EXECUTION_EVIDENCE_FIELD,
    BaseStationAdapterOperationEvidence,
    BaseStationAttachOperationEvidence,
    BaseStationControlReleaseEvidence,
    BaseStationExecutionEvidence,
    BaseStationMeasurementWindowEvidence,
    FrozenPayloadSnapshot,
    PositionSnapshot,
    base_station_attempt_lifecycle_is_complete,
    canonical_snapshot_digest,
    parse_base_station_execution_evidence,
)
from app.services.base_station_adapter_profile import CMW_FORMAL_CAPABILITY_KEY
from app.services.instrument_test_lease import (
    ActiveBaseStationLeaseIdentity,
    active_base_station_lease_identity,
)
from app.services.positioner_coordinate_profile import PositionerCoordinateProfile


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


def _base_station_driver_identity(
    driver,
    *,
    adapter: Literal["uxm", "cmw500"],
    execution_mode: Literal["real", "simulated"],
) -> BaseStationIdentity:
    """Read only the already-captured driver identity; never query hardware here."""

    if getattr(driver, "adapter_id", None) != adapter:
        raise ValueError("loaded driver adapter does not match frozen adapter")
    simulated = getattr(driver, "simulated", False) is True
    if execution_mode == "real":
        if simulated:
            raise ValueError("real execution cannot use a simulated baseStation driver")
        if adapter == "cmw500":
            if getattr(driver, "identity_snapshot_verified", False) is not True:
                raise ValueError("CMW500 driver identity snapshot is not verified")
            getter = getattr(driver, "get_base_station_identity", None)
            identity = getter() if callable(getter) else None
        else:
            capture = getattr(driver, "capture_evidence_environment", None)
            environment = capture() if callable(capture) else None
            if (
                environment is None
                or getattr(environment, "captured_from_live_connection", False)
                is not True
            ):
                raise ValueError("UXM driver identity snapshot is not verified")
            identity = BaseStationIdentity(
                adapter_id="uxm",
                model=getattr(environment, "model", None),
                firmware_version=getattr(environment, "firmware_version", None),
                options=tuple(getattr(environment, "options", ()) or ()),
            )
        if not isinstance(identity, BaseStationIdentity):
            raise ValueError("loaded driver did not provide a baseStation identity")
        if identity.adapter_id != adapter:
            raise ValueError("driver identity adapter does not match frozen adapter")
        return identity

    if not simulated:
        raise ValueError("simulated execution requires the authoritative mock driver")
    return BaseStationIdentity(
        adapter_id=adapter,
        model=f"simulated:{type(driver).__name__}",
        firmware_version=None,
        options=(),
    )


def _initial_base_station_execution_evidence(
    execution,
    *,
    frozen_adapter: dict[str, Any],
    requested_config: BaseStationRequestedConfig,
    requested_positions: list[dict[str, Any]],
    driver,
) -> BaseStationExecutionEvidence:
    """Build the immutable evidence envelope from execution/server-owned sources."""

    if not isinstance(frozen_adapter, dict):
        raise ValueError("frozen baseStation adapter snapshot is missing")
    frozen_digest = frozen_adapter.get("digest")
    frozen_payload = {key: value for key, value in frozen_adapter.items() if key != "digest"}
    if (
        not isinstance(frozen_digest, str)
        or canonical_snapshot_digest(frozen_payload) != frozen_digest
    ):
        raise ValueError("frozen baseStation adapter digest mismatch")
    try:
        resolution = BaseStationAdapterProfileResolution.model_validate(
            frozen_adapter.get("resolution")
        )
    except Exception as exc:
        raise ValueError("frozen baseStation adapter resolution is invalid") from exc
    if resolution.adapter not in {"uxm", "cmw500"}:
        raise ValueError("unbound baseStation diagnostics have no execution adapter")
    if not isinstance(requested_config, BaseStationRequestedConfig):
        raise TypeError("requested_config must be BaseStationRequestedConfig")

    adapter = resolution.adapter
    execution_mode = resolution.execution_mode
    identity = _base_station_driver_identity(
        driver,
        adapter=adapter,
        execution_mode=execution_mode,
    )
    connection_id = frozen_adapter.get("instrument_connection_id")
    if not isinstance(connection_id, str) or not connection_id:
        raise ValueError("frozen baseStation connection identity is missing")

    route_snapshot = None
    if adapter == "cmw500":
        approval = frozen_adapter.get(CMW_FORMAL_CAPABILITY_KEY)
        if not isinstance(approval, dict):
            raise ValueError("frozen CMW500 formal capability approval is missing")
        if approval.get("instrument_connection_id") != connection_id:
            raise ValueError("frozen CMW500 approval connection mismatch")
        formal_approval = {
            "schema_version": 1,
            "status": "configured",
            "instrument_connection_id": connection_id,
            "capability": "cmw500_lte_2x2",
            "enabled": approval.get("enabled"),
            "updated_at": approval.get("updated_at"),
        }
        if resolution.profile is None:  # pragma: no cover - model invariant
            raise ValueError("frozen CMW500 route profile is missing")
        route_payload = resolution.profile.lte_2x2_internal_route.model_dump(
            mode="json"
        )
        route_snapshot = {
            "payload": route_payload,
            "digest": canonical_snapshot_digest(route_payload),
        }
    else:
        formal_approval = {
            "schema_version": 1,
            "status": "not_applicable",
            "instrument_connection_id": None,
            "capability": None,
            "enabled": None,
            "updated_at": None,
        }

    config_payload = asdict(requested_config)
    positions = [PositionSnapshot.model_validate(item) for item in requested_positions]
    return BaseStationExecutionEvidence.model_validate(
        {
            "schema_version": 1,
            "execution_id": str(execution.id),
            "adapter": adapter,
            "execution_mode": execution_mode,
            "identity": {
                "adapter": adapter,
                "model": identity.model,
                "firmware_version": identity.firmware_version,
                "options": sorted(set(identity.options)),
                "instrument_connection_id": connection_id,
                "adapter_profile_digest": (
                    frozen_digest if adapter == "cmw500" else None
                ),
            },
            "formal_capability_approval": formal_approval,
            "mode": "dispatch",
            "config_confirmed": False,
            "route_confirmed": False if adapter == "cmw500" else None,
            "requested_config": {
                "payload": config_payload,
                "digest": canonical_snapshot_digest(config_payload),
            },
            "requested_route": route_snapshot,
            "applied_route": None,
            "requested_positions": positions,
            "current_measurement_attempt_id": None,
            "current_measurement_attempt_state": None,
            "attach_operations": [],
            "measurement_windows": [],
            "control_releases": [],
            "exchange_ids": [],
        }
    )


def initialize_base_station_execution_evidence(
    execution,
    *,
    frozen_adapter: dict[str, Any],
    requested_config: BaseStationRequestedConfig,
    requested_positions: list[dict[str, Any]],
    driver,
) -> dict[str, Any]:
    """Persist one immutable execution scope without clearing prior attempts."""

    candidate = _initial_base_station_execution_evidence(
        execution,
        frozen_adapter=frozen_adapter,
        requested_config=requested_config,
        requested_positions=requested_positions,
        driver=driver,
    )
    existing_raw = load_base_station_execution_evidence(execution)
    if existing_raw is not None:
        existing = BaseStationExecutionEvidence.model_validate(existing_raw)
        immutable_fields = (
            "schema_version",
            "execution_id",
            "adapter",
            "execution_mode",
            "identity",
            "formal_capability_approval",
            "mode",
            "requested_config",
            "requested_route",
            "requested_positions",
        )
        if any(
            getattr(existing, field) != getattr(candidate, field)
            for field in immutable_fields
        ):
            raise ValueError("baseStation evidence immutable scope mismatch")
        return existing.model_dump(mode="json")
    return save_base_station_execution_evidence(execution, candidate)


def _append_unique_exchange_ids(
    evidence: BaseStationExecutionEvidence,
    exchange_ids: list[str],
) -> None:
    for exchange_id in exchange_ids:
        if not isinstance(exchange_id, str) or not exchange_id:
            raise ValueError("baseStation exchange ids must be non-empty strings")
        if exchange_id not in evidence.exchange_ids:
            evidence.exchange_ids.append(exchange_id)


def _current_running_base_station_evidence(
    db,
    execution_id,
    *,
    attempt_id: str,
) -> tuple[Any, BaseStationExecutionEvidence]:
    execution = _locked_execution(db, execution_id)
    raw = load_base_station_execution_evidence(execution)
    if raw is None:
        raise ValueError("canonical base station execution evidence is missing")
    evidence = BaseStationExecutionEvidence.model_validate(raw)
    if (
        evidence.current_measurement_attempt_id != attempt_id
        or evidence.current_measurement_attempt_state != "running"
    ):
        raise ValueError("measurement attempt is not the current running attempt")
    return execution, evidence


def _adapter_operation_evidence(
    evidence: BaseStationExecutionEvidence,
    *,
    attempt_id: str,
    lease_identity: ActiveBaseStationLeaseIdentity,
    receipt: BaseStationApplyReceipt,
) -> BaseStationAdapterOperationEvidence:
    if not isinstance(receipt, BaseStationApplyReceipt):
        raise TypeError("adapter operation must be a BaseStationApplyReceipt")
    active_identity = active_base_station_lease_identity()
    if active_identity != lease_identity:
        raise ValueError("baseStation lease identity is not the active lease truth")
    if (
        lease_identity.measurement_attempt_id != attempt_id
        or lease_identity.adapter_id != evidence.adapter
        or not lease_identity.lease_id
        or not lease_identity.session_token
    ):
        raise ValueError("baseStation lease identity does not match current evidence")

    if receipt.operation == "config":
        frozen_snapshot = evidence.requested_config
        frozen_payload = frozen_snapshot.payload
        applicable_frozen_fields = {
            key for key, value in frozen_payload.items() if value is not None
        }
        if {field.field for field in receipt.fields} != applicable_frozen_fields:
            raise ValueError("configuration receipt does not cover frozen request")
        for field in receipt.fields:
            if field.status == "not_applicable":
                raise ValueError("configuration fields cannot be not_applicable")
            if (
                field.field not in frozen_payload
                or frozen_payload[field.field] != field.requested
            ):
                raise ValueError("adapter receipt does not match frozen request")
    else:
        if evidence.requested_route is None:
            if any(field.status != "not_applicable" for field in receipt.fields):
                raise ValueError("route receipt does not match frozen request")
            frozen_snapshot = None
        else:
            frozen_snapshot = evidence.requested_route
            frozen_payload = frozen_snapshot.payload
            if {field.field for field in receipt.fields} != set(frozen_payload):
                raise ValueError("route receipt does not cover frozen request")
            if any(
                field.requested != frozen_payload[field.field]
                for field in receipt.fields
            ):
                raise ValueError("adapter receipt does not match frozen request")

    exchange_ids = list(receipt.exchange_ids)
    applicable = [
        field for field in receipt.fields if field.status != "not_applicable"
    ]
    if receipt.confirmed is True and applicable and not exchange_ids:
        raise ValueError("confirmed adapter receipt requires exchange ids")
    return BaseStationAdapterOperationEvidence.model_validate(
        {
            "schema_version": receipt.schema_version,
            "measurement_attempt_id": attempt_id,
            "lease_id": lease_identity.lease_id,
            "adapter": evidence.adapter,
            "session_token": lease_identity.session_token,
            "operation": receipt.operation,
            "frozen_request_digest": (
                frozen_snapshot.digest if frozen_snapshot is not None else None
            ),
            "fields": [
                {
                    "field": field.field,
                    "requested": field.requested,
                    "applied": field.applied,
                    "status": field.status,
                    "reason": field.reason,
                    "exchange_ids": list(field.exchange_ids),
                }
                for field in receipt.fields
            ],
            "confirmed": receipt.confirmed is True and receipt.simulated is False,
            "simulated": receipt.simulated,
            "reason": receipt.reason,
            "exchange_ids": exchange_ids,
        }
    )


def confirm_base_station_configuration_and_route(
    db,
    execution_id,
    *,
    attempt_id: str,
    lease_identity: ActiveBaseStationLeaseIdentity,
    config_receipt: BaseStationApplyReceipt,
    route_receipt: BaseStationApplyReceipt,
) -> None:
    """Persist only versioned vendor-neutral adapter operation receipts."""

    execution, evidence = _current_running_base_station_evidence(
        db, execution_id, attempt_id=attempt_id
    )
    config_operation = _adapter_operation_evidence(
        evidence,
        attempt_id=attempt_id,
        lease_identity=lease_identity,
        receipt=config_receipt,
    )
    route_operation = _adapter_operation_evidence(
        evidence,
        attempt_id=attempt_id,
        lease_identity=lease_identity,
        receipt=route_receipt,
    )
    if config_operation.operation != "config" or route_operation.operation != "route":
        raise ValueError("baseStation config/route receipt operations are reversed")
    keys = {
        (row.measurement_attempt_id, row.lease_id, row.operation)
        for row in evidence.adapter_operations
    }
    for operation in (config_operation, route_operation):
        key = (
            operation.measurement_attempt_id,
            operation.lease_id,
            operation.operation,
        )
        if key in keys:
            raise ValueError("baseStation adapter operation already persisted")
        keys.add(key)

    evidence.adapter_operations.extend((config_operation, route_operation))
    evidence.config_confirmed = config_operation.confirmed is True
    _append_unique_exchange_ids(evidence, config_operation.exchange_ids)
    _append_unique_exchange_ids(evidence, route_operation.exchange_ids)

    if evidence.adapter == "cmw500":
        route_payload = {
            field.field: field.applied for field in route_operation.fields
        }
        evidence.route_confirmed = route_operation.confirmed is True
        evidence.applied_route = (
            FrozenPayloadSnapshot.model_validate(
                {
                    "payload": route_payload,
                    "digest": canonical_snapshot_digest(route_payload),
                }
            )
            if route_operation.confirmed is True
            else None
        )
    else:
        evidence.route_confirmed = None
        evidence.applied_route = None

    save_base_station_execution_evidence(execution, evidence)
    db.flush()


def confirm_base_station_attach(
    db,
    execution_id,
    *,
    attempt_id: str,
    lease_identity: ActiveBaseStationLeaseIdentity,
    manifest: BaseStationAdapterManifest,
    receipt: BaseStationAttachReceipt,
) -> None:
    """Persist one manifest-checked attach receipt for the active lease."""

    if not isinstance(manifest, BaseStationAdapterManifest):
        raise TypeError("manifest must be a BaseStationAdapterManifest")
    if not isinstance(receipt, BaseStationAttachReceipt):
        raise TypeError("receipt must be a BaseStationAttachReceipt")
    execution, evidence = _current_running_base_station_evidence(
        db, execution_id, attempt_id=attempt_id
    )
    active_identity = active_base_station_lease_identity()
    if active_identity != lease_identity:
        raise ValueError("baseStation lease identity is not the active lease truth")
    if (
        lease_identity.measurement_attempt_id != attempt_id
        or lease_identity.adapter_id != evidence.adapter
        or not lease_identity.lease_id
        or not lease_identity.session_token
    ):
        raise ValueError("baseStation lease identity does not match current evidence")
    if (
        manifest.adapter_id != evidence.adapter
        or receipt.adapter_id != evidence.adapter
    ):
        raise ValueError("baseStation attach manifest does not match current adapter")
    manifest_stages = {item.stage: item for item in manifest.attach_stages}
    if any(
        manifest_stages.get(stage.stage) is None
        or manifest_stages[stage.stage].evidence != stage.evidence
        for stage in receipt.stages
    ):
        raise ValueError("baseStation attach receipt disagrees with manifest")

    if evidence.attach_operations is None:
        evidence.attach_operations = []
    key = (attempt_id, lease_identity.lease_id)
    if any(
        (item.measurement_attempt_id, item.lease_id) == key
        for item in evidence.attach_operations
    ):
        raise ValueError("baseStation attach operation already persisted")
    operation = BaseStationAttachOperationEvidence.model_validate(
        {
            "schema_version": receipt.schema_version,
            "measurement_attempt_id": attempt_id,
            "lease_id": lease_identity.lease_id,
            "adapter": evidence.adapter,
            "session_token": lease_identity.session_token,
            "stages": [
                {
                    "stage": stage.stage,
                    "requested": stage.requested,
                    "applied": stage.applied,
                    "status": stage.status,
                    "evidence": stage.evidence,
                    "reason": stage.reason,
                    "exchange_ids": list(stage.exchange_ids),
                }
                for stage in receipt.stages
            ],
            "terminal_stage": receipt.terminal_stage,
            "formally_confirmed": receipt.formally_confirmed,
            "simulated": receipt.simulated,
            "reason": receipt.reason,
            "exchange_ids": list(receipt.exchange_ids),
        }
    )
    evidence.attach_operations.append(operation)
    _append_unique_exchange_ids(evidence, operation.exchange_ids)
    save_base_station_execution_evidence(execution, evidence)
    db.flush()


def mark_base_station_configuration_unconfirmed(
    db,
    execution_id,
    *,
    attempt_id: str,
) -> None:
    """Only downgrade formal configuration truth; never manufacture success."""

    execution, evidence = _current_running_base_station_evidence(
        db, execution_id, attempt_id=attempt_id
    )
    evidence.config_confirmed = False
    save_base_station_execution_evidence(execution, evidence)
    db.flush()


def append_base_station_measurement_window(
    db,
    execution_id,
    *,
    attempt_id: str,
    lease_identity: ActiveBaseStationLeaseIdentity,
    position: dict[str, Any],
    ue_link_state: Literal["connected"],
    window: BaseStationMeasurementWindow,
    cleanup: BaseStationCleanupResult,
) -> None:
    """Append one driver-native window bound to current attempt and active lease."""

    if not isinstance(lease_identity, ActiveBaseStationLeaseIdentity):
        raise TypeError("lease_identity must be ActiveBaseStationLeaseIdentity")
    if not isinstance(window, BaseStationMeasurementWindow):
        raise TypeError("window must be BaseStationMeasurementWindow")
    if not isinstance(cleanup, BaseStationCleanupResult):
        raise TypeError("cleanup must be BaseStationCleanupResult")
    if (
        lease_identity.measurement_attempt_id != attempt_id
        or not lease_identity.lease_id
        or not lease_identity.session_token
    ):
        raise ValueError("active lease identity does not match measurement attempt")

    execution, evidence = _current_running_base_station_evidence(
        db, execution_id, attempt_id=attempt_id
    )
    if lease_identity.adapter_id != evidence.adapter:
        raise ValueError("active lease adapter does not match execution evidence")
    parsed_position = PositionSnapshot.model_validate(position)
    if parsed_position not in evidence.requested_positions:
        raise ValueError("measurement window position was not requested")
    if any(item.window_id == window.window_id for item in evidence.measurement_windows):
        raise ValueError("duplicate measurement window id")
    if window.completed_at is None:
        raise ValueError("measurement window completion is missing")

    lifecycle_exchange_ids: list[str] = []
    for item in window.evidence:
        for exchange_id in item.exchange_ids:
            if exchange_id in lifecycle_exchange_ids:
                raise ValueError("measurement window exchange ids must be unique")
            lifecycle_exchange_ids.append(exchange_id)
    _append_unique_exchange_ids(evidence, lifecycle_exchange_ids)

    metrics = window.metrics
    metric_rows = {
        "dl_throughput_mbps": {
            "measurement_attempt_id": attempt_id,
            "session_token": lease_identity.session_token,
            "value": (
                metrics.dl_throughput_mbps
                if metrics.kpi_valid.get("dl_throughput") is True
                else None
            ),
            "unit": "Mbps",
            "exchange_ids": lifecycle_exchange_ids,
        },
        "dl_bler_percent": {
            "measurement_attempt_id": attempt_id,
            "session_token": lease_identity.session_token,
            "value": (
                metrics.dl_bler
                if metrics.kpi_valid.get("dl_bler") is True
                else None
            ),
            "unit": "%",
            "exchange_ids": lifecycle_exchange_ids,
        },
    }
    evidence.measurement_windows.append(
        BaseStationMeasurementWindowEvidence.model_validate(
            {
                "window_id": window.window_id,
                "measurement_attempt_id": attempt_id,
                "lease_id": lease_identity.lease_id,
                "adapter": evidence.adapter,
                "session_token": lease_identity.session_token,
                "config_digest": evidence.requested_config.digest,
                "route_digest": (
                    evidence.requested_route.digest
                    if evidence.requested_route is not None
                    else None
                ),
                "position": parsed_position,
                "ue_link_state": ue_link_state,
                "started_at": window.started_at,
                "completed_at": window.completed_at,
                "preclear_off_confirmed": window.preclear_off_confirmed is True,
                "running_confirmed": window.running_confirmed is True,
                "ready_confirmed": window.ready_confirmed is True,
                "closed_off_confirmed": window.closed_off_confirmed is True,
                "cleanup": {
                    "stop_signaling_confirmed": (
                        cleanup.stop_signaling_confirmed is True
                    ),
                    "safe_idle_confirmed": cleanup.safe_idle_confirmed is True,
                    "warnings": list(cleanup.warnings),
                },
                "lifecycle_exchange_ids": lifecycle_exchange_ids,
                "metrics": metric_rows,
            }
        )
    )
    save_base_station_execution_evidence(execution, evidence)
    db.flush()


def save_base_station_execution_evidence(
    execution,
    evidence: BaseStationExecutionEvidence | dict[str, Any],
) -> dict[str, Any]:
    """Persist only a canonical, execution-bound server evidence snapshot."""

    parsed = BaseStationExecutionEvidence.model_validate(evidence)
    if parsed.execution_id != str(execution.id):
        raise ValueError("base station evidence execution_id mismatch")
    normalized = parsed.model_dump(mode="json")
    if parsed.attach_operations is None:
        normalized.pop("attach_operations", None)
    cfg = dict(execution.config or {})
    cfg[BASE_STATION_EXECUTION_EVIDENCE_FIELD] = normalized
    execution.config = cfg
    flag_modified(execution, "config")
    return normalized


def load_base_station_execution_evidence(execution) -> dict[str, Any] | None:
    """Read brownfield rows strictly; malformed or cross-execution data is unknown."""

    cfg = execution.config if isinstance(execution.config, dict) else {}
    parsed = parse_base_station_execution_evidence(
        cfg.get(BASE_STATION_EXECUTION_EVIDENCE_FIELD)
    )
    if parsed is None or parsed.get("execution_id") != str(execution.id):
        return None
    return parsed


def _locked_execution(db, execution_id):
    execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution_id)
        .with_for_update()
        .one_or_none()
    )
    if execution is None:
        raise ValueError("test execution not found")
    return execution


def begin_base_station_measurement_attempt(db, execution_id) -> str:
    """Lock the execution and switch current truth before any MEASURE I/O."""

    execution = _locked_execution(db, execution_id)
    raw = load_base_station_execution_evidence(execution)
    if raw is None:
        raise ValueError("canonical base station execution evidence is missing")
    evidence = BaseStationExecutionEvidence.model_validate(raw)
    if evidence.current_measurement_attempt_state == "running":
        raise ValueError("base station measurement attempt is already running")
    attempt_id = str(uuid4())
    evidence.current_measurement_attempt_id = attempt_id
    evidence.current_measurement_attempt_state = "running"
    save_base_station_execution_evidence(execution, evidence)
    db.flush()
    return attempt_id


def set_base_station_measurement_attempt_state(
    db,
    execution_id,
    *,
    attempt_id: str,
    state: Literal["completed", "failed", "cancelled"],
) -> None:
    """Finalize only the execution's still-current server-owned attempt."""

    execution = _locked_execution(db, execution_id)
    raw = load_base_station_execution_evidence(execution)
    if raw is None:
        raise ValueError("canonical base station execution evidence is missing")
    evidence = BaseStationExecutionEvidence.model_validate(raw)
    if (
        evidence.current_measurement_attempt_id != attempt_id
        or evidence.current_measurement_attempt_state != "running"
    ):
        raise ValueError("measurement attempt is not the current running attempt")
    evidence.current_measurement_attempt_state = state
    save_base_station_execution_evidence(execution, evidence)
    db.flush()


def append_base_station_control_release(
    db,
    execution_id,
    result: BaseStationControlReleaseResult,
) -> None:
    """Append one actual lease-owner result without replacing prior audit rows."""

    if not isinstance(result, BaseStationControlReleaseResult):
        raise TypeError("result must be BaseStationControlReleaseResult")
    execution = _locked_execution(db, execution_id)
    raw = load_base_station_execution_evidence(execution)
    if raw is None:
        raise ValueError("canonical base station execution evidence is missing")
    evidence = BaseStationExecutionEvidence.model_validate(raw)
    candidate = {
        "measurement_attempt_id": result.measurement_attempt_id,
        "lease_id": result.lease_id,
        "adapter_id": result.adapter_id,
        "session_token": result.session_token,
        "remote_session_acquired_confirmed": (
            result.remote_session_acquired_confirmed
        ),
        "transport_session_released_confirmed": (
            result.transport_session_released_confirmed
        ),
        "front_panel_local_confirmed": result.front_panel_local_confirmed,
        "warnings": list(result.warnings),
    }
    same_lease = [
        item
        for item in evidence.control_releases
        if item.lease_id == result.lease_id
    ]
    if same_lease:
        if len(same_lease) != 1 or same_lease[0].model_dump(mode="json") != candidate:
            raise ValueError("conflicting control release for lease_id")
        return
    evidence.control_releases.append(
        BaseStationControlReleaseEvidence.model_validate(candidate)
    )
    save_base_station_execution_evidence(execution, evidence)
    db.flush()


def begin_execution_base_station_measurement(
    db,
    execution,
    test_case,
    *,
    driver,
) -> str | None:
    """Create the CMW evidence scope after acquire and before measurement I/O.

    P1-73C does not rewrite the established UXM evidence path.  A frozen CMW
    execution, however, cannot enter measurement I/O until its active transport
    identity, immutable request scope, and server-owned attempt id are committed.
    """

    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.mimo_ota.base_station_execution_evidence import (
        MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD,
    )
    from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
    from app.services.mimo_ota.executors.measure import (
        _build_pcell_requested_config,
    )

    frozen = (execution.config or {}).get(FREEZE_CONFIG_KEY)
    resolution = frozen.get("resolution") if isinstance(frozen, dict) else None
    if not isinstance(resolution, dict) or resolution.get("adapter") != "cmw500":
        return None
    config = MIMOOTAConfiguration.model_validate(test_case.configuration)
    execution_config = dict(execution.config or {})
    frozen_peak = config.theoretical_peak_throughput_mbps
    if MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD in execution_config:
        if (
            execution_config[MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD]
            != frozen_peak
        ):
            raise ValueError("frozen theoretical peak changed within execution")
    else:
        execution_config[MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD] = frozen_peak
        execution.config = execution_config
    initialize_base_station_execution_evidence(
        execution,
        frozen_adapter=frozen,
        requested_config=_build_pcell_requested_config(config),
        requested_positions=[
            {"azimuth_deg": float(azimuth), "elevation_deg": 0.0}
            for azimuth in config.azimuths_deg
        ],
        driver=driver,
    )
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)
    db.commit()
    return attempt_id


def persist_execution_base_station_release(
    db,
    execution_id,
    *,
    attempt_id: str | None,
    outcome,
) -> Literal["completed", "failed", "cancelled"] | None:
    """Append the actual lease release and finalize only its exact attempt."""

    if attempt_id is None:
        return None
    release = getattr(outcome, "base_station_release", None)
    if release is None:
        raise RuntimeError("CMW measurement lease did not produce control release evidence")
    append_base_station_control_release(db, execution_id, release)
    execution = (
        db.query(TestExecution).filter(TestExecution.id == execution_id).first()
    )
    execution_status = getattr(execution, "status", None)
    if (
        execution_status == "running"
        and release.transport_session_released_confirmed is True
        and base_station_attempt_lifecycle_is_complete(
            load_base_station_execution_evidence(execution), attempt_id
        )
    ):
        state = "completed"
    elif execution_status == "cancelled":
        state = "cancelled"
    else:
        state = "failed"
    set_base_station_measurement_attempt_state(
        db,
        execution_id,
        attempt_id=attempt_id,
        state=state,
    )
    db.commit()
    if release.transport_session_released_confirmed is not True:
        raise RuntimeError("CMW measurement transport release is unconfirmed")
    return state


def record_execution_base_station_attempt_failure(
    db,
    execution_id,
    *,
    attempt_id: str | None,
    outcome,
    cancelled: bool,
) -> None:
    """Fail/cancel the supplied attempt without re-reading a mutable pointer."""

    if attempt_id is None:
        return
    db.rollback()
    release = getattr(outcome, "base_station_release", None)
    if release is not None:
        append_base_station_control_release(db, execution_id, release)
    set_base_station_measurement_attempt_state(
        db,
        execution_id,
        attempt_id=attempt_id,
        state="cancelled" if cancelled else "failed",
    )
    db.commit()


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
    frozen_positioner: dict[str, Any],
    driver,
    exchanges: list[ScpiExchangeRef],
) -> None:
    resolution = frozen_positioner.get("resolution")
    raw_profile = frozen_positioner.get("profile")
    profile = None
    if (
        isinstance(resolution, dict)
        and resolution.get("execution_mode") == "real"
        and resolution.get("status") == "verified"
        and resolution.get("adapter") == "aerotech"
        and isinstance(raw_profile, dict)
    ):
        profile = PositionerCoordinateProfile.model_validate(raw_profile)
    az_axis = profile.azimuth_axis if profile is not None else str(
        getattr(driver, "az_axis", "X")
    ).strip().upper()
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
        coordinate_offset_deg=(
            profile.coordinate_offset_deg if profile is not None else None
        ),
        offset_calibrated=profile is not None,
        tolerance_deg=(
            profile.position_tolerance_deg if profile is not None else 1.0
        ),
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
