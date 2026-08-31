"""基站测量窗口的版本化正式证据与唯一逐指标信任入口。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)


BASE_STATION_EXECUTION_EVIDENCE_FIELD = "base_station_execution_evidence"
BASE_STATION_EXECUTION_EVIDENCE_SCHEMA_VERSION = 1
MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD = (
    "mimo_ota_theoretical_peak_throughput_mbps"
)
_LEGACY_METRIC_UNITS = {
    "dl_throughput_mbps": "Mbps",
    "dl_bler_percent": "%",
}


def base_station_metric_projection_required(
    execution_config: Any,
) -> bool:
    """Centralize the strict new-evidence boundary and legacy compatibility.

    Any execution carrying the versioned envelope must use it.  Before the
    common envelope existed, UXM executions used an older independently
    attested throughput path, while CMW500 never had such a formal legacy
    path.  Keep that historical distinction here at the certification
    boundary so downstream consumers never select behavior by vendor.
    """

    config = execution_config if isinstance(execution_config, dict) else {}
    if config.get(BASE_STATION_EXECUTION_EVIDENCE_FIELD) is not None:
        return True
    frozen = config.get("base_station_adapter_profile_freeze")
    resolution = frozen.get("resolution") if isinstance(frozen, dict) else None
    return (
        isinstance(resolution, dict)
        and resolution.get("adapter") == "cmw500"
    )


def canonical_snapshot_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _unique_non_empty(values: list[str], field_name: str) -> list[str]:
    if not values or len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique values")
    for value in values:
        _non_empty(value, field_name)
    return values


def _firmware_at_least(value: str | None, minimum: tuple[int, ...]) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"\d+(?:\.\d+)+", value) is None:
        return False
    parsed = tuple(int(part) for part in value.split("."))
    width = max(len(parsed), len(minimum))
    return parsed + (0,) * (width - len(parsed)) >= minimum + (0,) * (
        width - len(minimum)
    )


class BaseStationIdentitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: Literal["uxm", "cmw500"]
    model: str
    firmware_version: str | None
    options: list[str]
    instrument_connection_id: str
    adapter_profile_digest: str | None

    @field_validator("model", "instrument_connection_id")
    @classmethod
    def _required_identity(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @field_validator("firmware_version")
    @classmethod
    def _firmware_when_present(cls, value: str | None):
        if value is not None:
            return _non_empty(value, "firmware_version")
        return value

    @field_validator("options")
    @classmethod
    def _unique_options(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("options must be unique")
        return [_non_empty(item, "options") for item in value]


class BaseStationFormalCapabilityApprovalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    status: Literal["configured", "not_applicable"]
    instrument_connection_id: str | None
    capability: Literal["cmw500_lte_2x2"] | None
    enabled: StrictBool | None
    updated_at: datetime | None

    @model_validator(mode="after")
    def _valid_combination(self):
        if self.status == "configured":
            if (
                not self.instrument_connection_id
                or self.capability != "cmw500_lte_2x2"
                or type(self.enabled) is not bool
                or (self.enabled is True and self.updated_at is None)
            ):
                raise ValueError("configured approval is incomplete")
        elif any(
            value is not None
            for value in (
                self.instrument_connection_id,
                self.capability,
                self.enabled,
                self.updated_at,
            )
        ):
            raise ValueError("not_applicable approval must contain only null values")
        return self


class FrozenPayloadSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, JsonValue]
    digest: str

    @field_validator("digest")
    @classmethod
    def _non_empty_digest(cls, value: str):
        return _non_empty(value, "digest")

    @model_validator(mode="after")
    def _digest_matches_payload(self):
        if canonical_snapshot_digest(self.payload) != self.digest:
            raise ValueError("snapshot digest does not match payload")
        return self


class BaseStationAdapterFieldEvidence(BaseModel):
    """JSON-safe copy of one vendor-neutral adapter field receipt."""

    model_config = ConfigDict(extra="forbid")

    field: str
    requested: JsonValue
    applied: JsonValue
    status: Literal["confirmed", "unknown", "not_applicable"]
    reason: str
    exchange_ids: list[str]

    @field_validator("field", "reason")
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @field_validator("exchange_ids")
    @classmethod
    def _unique_exchange_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("field exchange ids must be unique")
        return [_non_empty(item, "exchange_ids") for item in value]

    @model_validator(mode="after")
    def _status_shape(self):
        if self.status == "confirmed":
            if self.applied is None or self.applied != self.requested:
                raise ValueError("confirmed adapter field must match requested")
        elif self.status == "unknown":
            if self.applied is not None:
                raise ValueError("unknown adapter field cannot carry applied truth")
        elif self.requested is not None or self.applied is not None:
            raise ValueError("not-applicable adapter field must contain null values")
        return self


class BaseStationAdapterOperationEvidence(BaseModel):
    """One adapter operation bound to the active execution lease identity."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    measurement_attempt_id: str
    lease_id: str
    adapter: Literal["uxm", "cmw500"]
    session_token: str
    operation: Literal["config", "route"]
    frozen_request_digest: str | None
    fields: list[BaseStationAdapterFieldEvidence]
    confirmed: StrictBool
    simulated: StrictBool
    reason: str
    exchange_ids: list[str]

    @field_validator(
        "measurement_attempt_id",
        "lease_id",
        "session_token",
        "reason",
    )
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @field_validator("frozen_request_digest")
    @classmethod
    def _optional_digest(cls, value: str | None):
        return None if value is None else _non_empty(value, "frozen_request_digest")

    @field_validator("exchange_ids")
    @classmethod
    def _unique_exchange_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("adapter operation exchange ids must be unique")
        return [_non_empty(item, "exchange_ids") for item in value]

    @model_validator(mode="after")
    def _derived_confirmation(self):
        if not self.fields:
            raise ValueError("adapter operation requires field evidence")
        applicable = [
            field for field in self.fields if field.status != "not_applicable"
        ]
        if applicable and self.frozen_request_digest is None:
            raise ValueError("applicable adapter operation requires a frozen request")
        if not applicable and self.frozen_request_digest is not None:
            raise ValueError("not-applicable adapter operation has no frozen request")
        expected = (
            bool(applicable)
            and all(field.status == "confirmed" for field in applicable)
            and self.simulated is False
        )
        if self.confirmed is not expected:
            raise ValueError("adapter operation confirmation must be derived")
        return self


class BaseStationAttachStageEvidence(BaseModel):
    """JSON-safe truth for one common attach milestone."""

    model_config = ConfigDict(extra="forbid")

    stage: Literal[
        "cell_ready",
        "ue_registered",
        "rrc_connected",
        "data_bearer_established",
    ]
    requested: StrictBool | None
    applied: StrictBool | None
    status: Literal["confirmed", "unknown", "not_applicable"]
    evidence: Literal[
        "authoritative",
        "diagnostic_only",
        "unavailable",
        "not_applicable",
    ]
    reason: str
    exchange_ids: list[str]

    @field_validator("reason")
    @classmethod
    def _required_reason(cls, value: str):
        return _non_empty(value, "reason")

    @field_validator("exchange_ids")
    @classmethod
    def _unique_exchange_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("attach stage exchange ids must be unique")
        return [_non_empty(item, "exchange_ids") for item in value]

    @model_validator(mode="after")
    def _truth_shape(self):
        if self.evidence == "unavailable" and self.status != "unknown":
            raise ValueError("unavailable attach evidence must be unknown")
        if self.evidence == "not_applicable" and self.status != "not_applicable":
            raise ValueError("not-applicable attach evidence has invalid status")
        if self.status == "not_applicable":
            if (
                self.evidence != "not_applicable"
                or self.requested is not None
                or self.applied is not None
                or self.exchange_ids
            ):
                raise ValueError("not-applicable attach stage has invalid truth")
        elif self.requested is not True:
            raise ValueError("applicable attach stage must be requested")
        if self.status == "confirmed":
            if self.applied is None or not self.exchange_ids:
                raise ValueError("confirmed attach stage requires instrument truth")
        elif self.status == "unknown" and (
            self.applied is not None or self.exchange_ids
        ):
            raise ValueError("unknown attach stage cannot carry applied truth")
        return self


class BaseStationAttachOperationEvidence(BaseModel):
    """One attach operation bound to the current execution lease."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    measurement_attempt_id: str
    lease_id: str
    adapter: Literal["uxm", "cmw500"]
    session_token: str
    stages: list[BaseStationAttachStageEvidence]
    terminal_stage: Literal[
        "cell_ready",
        "ue_registered",
        "rrc_connected",
        "data_bearer_established",
    ] | None
    formally_confirmed: StrictBool
    simulated: StrictBool
    reason: str
    exchange_ids: list[str]

    @field_validator(
        "measurement_attempt_id", "lease_id", "session_token", "reason"
    )
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @field_validator("exchange_ids")
    @classmethod
    def _unique_exchange_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("attach operation exchange ids must be unique")
        return [_non_empty(item, "exchange_ids") for item in value]

    @model_validator(mode="after")
    def _derived_shape(self):
        expected_stages = [
            "cell_ready",
            "ue_registered",
            "rrc_connected",
            "data_bearer_established",
        ]
        if [item.stage for item in self.stages] != expected_stages:
            raise ValueError("attach evidence requires exact ordered stages")
        terminal = next(
            (
                item
                for item in reversed(self.stages)
                if item.evidence not in {"unavailable", "not_applicable"}
            ),
            None,
        )
        if self.terminal_stage != (terminal.stage if terminal else None):
            raise ValueError("attach terminal stage must be derived")
        authoritative = [
            item for item in self.stages if item.evidence == "authoritative"
        ]
        expected_formal = bool(
            not self.simulated
            and terminal is not None
            and terminal.evidence == "authoritative"
            and terminal.status == "confirmed"
            and terminal.applied is True
            and authoritative
            and all(
                item.status == "confirmed"
                and item.applied is True
                and bool(item.exchange_ids)
                for item in authoritative
            )
        )
        if self.formally_confirmed is not expected_formal:
            raise ValueError("attach formal confirmation must be derived")
        stage_exchange_ids = []
        for item in self.stages:
            for exchange_id in item.exchange_ids:
                if exchange_id not in stage_exchange_ids:
                    stage_exchange_ids.append(exchange_id)
        if self.exchange_ids != stage_exchange_ids:
            raise ValueError("attach operation exchange ids must be derived")
        return self


class PositionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    azimuth_deg: float
    elevation_deg: float

    @field_validator("azimuth_deg", "elevation_deg")
    @classmethod
    def _finite_position(cls, value: float):
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError("position must be finite")
        return float(value)


class BaseStationMetricCapabilityEvidence(BaseModel):
    """JSON-safe immutable copy of one adapter metric declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    direction: Literal["downlink", "uplink", "link", "not_applicable"]
    unit: Literal[
        "mbps", "percent", "ratio", "index", "raw", "not_applicable"
    ]
    scopes: tuple[Literal["pcell", "all_cells"], ...]
    evidence: Literal["authoritative", "diagnostic_only", "unavailable"]
    source_reference: str | None

    @field_validator("key")
    @classmethod
    def _required_key(cls, value: str):
        return _non_empty(value, "key")

    @field_validator("scopes")
    @classmethod
    def _unique_scopes(cls, value: tuple[str, ...]):
        if not value or len(set(value)) != len(value):
            raise ValueError("metric capability scopes must be non-empty and unique")
        return value

    @field_validator("source_reference")
    @classmethod
    def _optional_source(cls, value: str | None):
        return None if value is None else _non_empty(value, "source_reference")

    @model_validator(mode="after")
    def _authoritative_source(self):
        if self.evidence == "authoritative" and self.source_reference is None:
            raise ValueError("authoritative metric requires a source reference")
        return self


class BaseStationMetricRegistryEvidence(BaseModel):
    """Execution-frozen adapter/profile metric semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    adapter_id: Literal["uxm", "cmw500"]
    profile_id: str
    metrics: tuple[BaseStationMetricCapabilityEvidence, ...]
    digest: str

    @field_validator("profile_id", "digest")
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @model_validator(mode="after")
    def _stable_registry(self):
        if not self.metrics:
            raise ValueError("metric registry requires capabilities")
        keys = tuple(item.key for item in self.metrics)
        if len(set(keys)) != len(keys) or keys != tuple(sorted(keys)):
            raise ValueError("metric registry keys must be unique and sorted")
        payload = {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "profile_id": self.profile_id,
            "metrics": [item.model_dump(mode="json") for item in self.metrics],
        }
        if canonical_snapshot_digest(payload) != self.digest:
            raise ValueError("metric registry digest mismatch")
        return self

    def capability(self, key: str) -> BaseStationMetricCapabilityEvidence:
        for item in self.metrics:
            if item.key == key:
                return item
        raise KeyError(key)


class BaseStationExecutionPlanItemEvidence(BaseModel):
    """一条 execution-frozen 能力计划项的 JSON-safe 镜像（P2-50）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planned: StrictBool
    capability_source: str
    reason: str

    @field_validator("capability_source", "reason")
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)


class BaseStationExecutionPlanEvidence(BaseModel):
    """Execution-frozen、vendor-neutral 的能力执行计划（P2-50）。

    窗口维度只引用既有 P2-48 冻结契约版本，不重造窗口计划。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    adapter_id: Literal["uxm", "cmw500"]
    scell: BaseStationExecutionPlanItemEvidence
    mac_throughput: BaseStationExecutionPlanItemEvidence
    rrc_reconfiguration: BaseStationExecutionPlanItemEvidence
    input_level_control: BaseStationExecutionPlanItemEvidence
    measurement_window_contract_version: Literal[1]
    digest: str

    @field_validator("digest")
    @classmethod
    def _required_digest(cls, value: str):
        return _non_empty(value, "digest")

    @model_validator(mode="after")
    def _stable_plan(self):
        payload = {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "scell": self.scell.model_dump(mode="json"),
            "mac_throughput": self.mac_throughput.model_dump(mode="json"),
            "rrc_reconfiguration": self.rrc_reconfiguration.model_dump(mode="json"),
            "input_level_control": self.input_level_control.model_dump(mode="json"),
            "measurement_window_contract_version": (
                self.measurement_window_contract_version
            ),
        }
        if canonical_snapshot_digest(payload) != self.digest:
            raise ValueError("execution plan digest mismatch")
        return self


class BaseStationMetricEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_attempt_id: str
    session_token: str
    value: float | None
    unit: str
    exchange_ids: list[str] = Field(default_factory=list)
    registry_digest: str | None = None
    scope: Literal["pcell", "all_cells"] | None = None
    direction: Literal["downlink", "uplink", "link", "not_applicable"] | None = None
    evidence: Literal["authoritative", "diagnostic_only", "unavailable"] | None = None
    source_reference: str | None = None
    simulated: StrictBool | None = None
    reason: str | None = None

    @field_validator("measurement_attempt_id", "session_token", "unit")
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @field_validator("value")
    @classmethod
    def _finite_value(cls, value: float | None):
        if value is not None and (
            isinstance(value, bool) or not math.isfinite(float(value))
        ):
            raise ValueError("metric value must be finite")
        return None if value is None else float(value)

    @field_validator("registry_digest", "source_reference", "reason")
    @classmethod
    def _optional_text(cls, value: str | None, info):
        return None if value is None else _non_empty(value, info.field_name)

    @field_validator("exchange_ids")
    @classmethod
    def _unique_metric_exchange_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("metric exchange ids must be unique")
        return [_non_empty(item, "exchange_ids") for item in value]


class BaseStationCleanupEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_signaling_confirmed: StrictBool
    safe_idle_confirmed: StrictBool
    warnings: list[str]


class BaseStationMeasurementWindowRequestEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    scope: Literal["pcell", "all_cells"]
    lifecycle: Literal["authoritative_closed", "clear_read_only", "unavailable"]
    cardinality: Literal["single", "requested"]
    requested_window_count: int
    expected_window_count: int
    window_index: int
    # P1-74：与 HAL 的 BaseStationMeasurementWindowRequest 同形；历史证据没有
    # 这个键，缺省即 None。
    # 外审 R1 修复期实测：普通 `int` 下 Pydantic 会把 `True` 静默归一成 `1`，
    # 于是 validator 里的 `isinstance(..., bool)` 恒为 False —— 那是一道
    # 永不触发的假门。`StrictInt` 在类型层直接拒 bool/float/str。
    statistical_basis_subframes: StrictInt | None = None

    @model_validator(mode="after")
    def _valid_shape(self):
        counts = (
            self.requested_window_count,
            self.expected_window_count,
            self.window_index,
        )
        if any(isinstance(value, bool) for value in counts):
            raise ValueError("measurement window counts must be integers")
        if self.requested_window_count <= 0 or self.expected_window_count <= 0:
            raise ValueError("measurement window counts must be positive")
        expected = 1 if self.cardinality == "single" else self.requested_window_count
        if self.expected_window_count != expected:
            raise ValueError("measurement window cardinality/count mismatch")
        if not 0 <= self.window_index < self.expected_window_count:
            raise ValueError("measurement window index is outside the frozen plan")
        if (
            self.statistical_basis_subframes is not None
            and self.statistical_basis_subframes <= 0
        ):
            # 类型由 StrictInt 在字段层把关；此处只管值域。
            raise ValueError("statistical basis subframes must be positive")
        return self

    @property
    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        # P1-74：omit-when-None，与 HAL 侧 digest 逐字同规则 —— 否则历史
        # request_digest 全部失配（该字段是后加的，旧载荷里根本没有这个键）。
        if payload.get("statistical_basis_subframes") is None:
            payload.pop("statistical_basis_subframes", None)
        return canonical_snapshot_digest(payload)


class BaseStationMeasurementStageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["clear", "run", "ready", "closed"]
    status: Literal["confirmed", "unknown", "unavailable"]
    reason: str
    exchange_ids: list[str]

    @field_validator("reason")
    @classmethod
    def _required_reason(cls, value: str):
        return _non_empty(value, "reason")

    @field_validator("exchange_ids")
    @classmethod
    def _unique_exchange_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("measurement stage exchange ids must be unique")
        return [_non_empty(item, "exchange_ids") for item in value]

    @model_validator(mode="after")
    def _status_shape(self):
        if self.status == "confirmed" and not self.exchange_ids:
            raise ValueError("confirmed measurement stage requires exchange ids")
        if self.status != "confirmed" and self.exchange_ids:
            raise ValueError("unconfirmed measurement stage cannot carry exchange ids")
        return self


class BaseStationMeasurementWindowTrustEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    request: BaseStationMeasurementWindowRequestEvidence
    request_digest: str
    stages: list[BaseStationMeasurementStageEvidence]
    simulated: StrictBool
    exchange_ids: list[str]
    reason: str
    context_confirmed: StrictBool

    @field_validator("request_digest", "reason")
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @field_validator("exchange_ids")
    @classmethod
    def _unique_exchange_ids(cls, value: list[str]):
        if len(set(value)) != len(value):
            raise ValueError("measurement window exchange ids must be unique")
        return [_non_empty(item, "exchange_ids") for item in value]

    @model_validator(mode="after")
    def _derived_truth(self):
        if self.request_digest != self.request.digest:
            raise ValueError("measurement window request digest mismatch")
        if [stage.stage for stage in self.stages] != [
            "clear", "run", "ready", "closed"
        ]:
            raise ValueError("measurement window stages must be exact and ordered")
        stage_ids = {
            exchange_id
            for stage in self.stages
            for exchange_id in stage.exchange_ids
        }
        if not stage_ids.issubset(set(self.exchange_ids)):
            raise ValueError("measurement stage proof is outside its window")
        if self.simulated and any(
            stage.status == "confirmed" for stage in self.stages
        ):
            raise ValueError("simulated window cannot confirm lifecycle truth")
        return self

    @property
    def formally_confirmed(self) -> bool:
        return (
            self.simulated is False
            and self.context_confirmed is True
            and self.request.lifecycle == "authoritative_closed"
            and all(stage.status == "confirmed" for stage in self.stages)
            and bool(self.exchange_ids)
        )

    @property
    def diagnostic_execution_allowed(self) -> bool:
        """Mirror the HAL receipt without promoting diagnostic truth to formal."""

        if self.simulated:
            return True
        if self.formally_confirmed:
            return True
        return (
            self.request.lifecycle in {"clear_read_only", "unavailable"}
            and bool(self.exchange_ids)
        )


class BaseStationMeasurementWindowEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_id: str
    measurement_attempt_id: str
    lease_id: str
    adapter: Literal["uxm", "cmw500"]
    session_token: str
    config_digest: str
    route_digest: str | None
    position: PositionSnapshot
    ue_link_state: Literal["connected"]
    started_at: datetime
    completed_at: datetime
    preclear_off_confirmed: StrictBool
    running_confirmed: StrictBool
    ready_confirmed: StrictBool
    closed_off_confirmed: StrictBool
    cleanup: BaseStationCleanupEvidence
    lifecycle_exchange_ids: list[str]
    metrics: dict[str, BaseStationMetricEvidence]
    trust: BaseStationMeasurementWindowTrustEvidence | None = None
    metric_registry_digest: str | None = None

    @field_validator(
        "window_id",
        "measurement_attempt_id",
        "lease_id",
        "session_token",
        "config_digest",
    )
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)

    @model_validator(mode="after")
    def _ordered_window(self):
        if self.completed_at <= self.started_at:
            raise ValueError("measurement window must have positive duration")
        return self


class BaseStationControlReleaseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_attempt_id: str | None
    lease_id: str
    adapter_id: Literal["uxm", "cmw500"]
    session_token: str
    remote_session_acquired_confirmed: StrictBool
    transport_session_released_confirmed: StrictBool
    front_panel_local_confirmed: StrictBool | None
    warnings: list[str]

    @field_validator("lease_id", "session_token")
    @classmethod
    def _required_text(cls, value: str, info):
        return _non_empty(value, info.field_name)


class BaseStationExecutionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    execution_id: str
    adapter: Literal["uxm", "cmw500"]
    execution_mode: Literal["real", "simulated"]
    identity: BaseStationIdentitySnapshot
    formal_capability_approval: BaseStationFormalCapabilityApprovalSnapshot
    mode: Literal["dispatch"]
    config_confirmed: StrictBool
    route_confirmed: StrictBool | None
    requested_config: FrozenPayloadSnapshot
    requested_route: FrozenPayloadSnapshot | None
    applied_route: FrozenPayloadSnapshot | None
    requested_positions: list[PositionSnapshot]
    current_measurement_attempt_id: str | None
    current_measurement_attempt_state: Literal[
        "running", "completed", "failed", "cancelled"
    ] | None
    adapter_operations: list[BaseStationAdapterOperationEvidence] = Field(
        default_factory=list
    )
    attach_operations: list[BaseStationAttachOperationEvidence] | None = None
    measurement_window_contract_version: Literal[1] | None = None
    metric_registry_contract_version: Literal[1] | None = None
    metric_registry: BaseStationMetricRegistryEvidence | None = None
    execution_plan_contract_version: Literal[1] | None = None
    execution_plan: BaseStationExecutionPlanEvidence | None = None
    measurement_windows: list[BaseStationMeasurementWindowEvidence]
    control_releases: list[BaseStationControlReleaseEvidence]
    exchange_ids: list[str]

    @field_validator("execution_id")
    @classmethod
    def _required_execution_id(cls, value: str):
        return _non_empty(value, "execution_id")

    @model_validator(mode="after")
    def _cross_field_shape(self):
        if (self.current_measurement_attempt_id is None) != (
            self.current_measurement_attempt_state is None
        ):
            raise ValueError("current attempt id and state must be present together")
        if self.identity.adapter != self.adapter:
            raise ValueError("identity adapter mismatch")
        if any(window.adapter != self.adapter for window in self.measurement_windows):
            raise ValueError("window adapter mismatch")
        if self.measurement_window_contract_version == 1 and any(
            window.trust is None for window in self.measurement_windows
        ):
            raise ValueError("current measurement windows require trust receipts")
        if self.metric_registry_contract_version == 1:
            registry = self.metric_registry
            if registry is None or registry.adapter_id != self.adapter:
                raise ValueError("current execution requires its adapter metric registry")
            for window in self.measurement_windows:
                if window.trust is None:
                    raise ValueError("registered metric window requires trust receipt")
                if window.metric_registry_digest != registry.digest:
                    raise ValueError("measurement window metric registry drift")
                capabilities = {
                    item.key: item
                    for item in registry.metrics
                    if window.trust.request.scope in item.scopes
                }
                if set(window.metrics) != set(capabilities):
                    raise ValueError("measurement metrics do not cover registry scope")
                for key, metric in window.metrics.items():
                    capability = capabilities[key]
                    if (
                        metric.registry_digest != registry.digest
                        or metric.scope != window.trust.request.scope
                        or metric.direction != capability.direction
                        or metric.unit != capability.unit
                        or metric.evidence != capability.evidence
                        or metric.source_reference != capability.source_reference
                        or metric.simulated is not window.trust.simulated
                        or metric.reason is None
                        or not set(metric.exchange_ids).issubset(
                            set(window.lifecycle_exchange_ids)
                        )
                    ):
                        raise ValueError("measurement metric semantics drifted")
        elif self.metric_registry is not None:
            raise ValueError("historical evidence cannot carry an unfrozen registry")
        if self.execution_plan_contract_version == 1:
            plan = self.execution_plan
            if plan is None or plan.adapter_id != self.adapter:
                raise ValueError(
                    "current execution requires its adapter execution plan"
                )
            if (
                plan.measurement_window_contract_version
                != self.measurement_window_contract_version
            ):
                raise ValueError(
                    "execution plan window reference disagrees with evidence contract"
                )
        elif self.execution_plan is not None:
            raise ValueError(
                "historical evidence cannot carry an unfrozen execution plan"
            )
        if any(row.adapter != self.adapter for row in self.adapter_operations):
            raise ValueError("adapter operation mismatch")
        if self.attach_operations is not None and any(
            row.adapter != self.adapter for row in self.attach_operations
        ):
            raise ValueError("attach operation mismatch")
        if any(release.adapter_id != self.adapter for release in self.control_releases):
            raise ValueError("control release adapter mismatch")
        if self.adapter == "cmw500":
            approval = self.formal_capability_approval
            if (
                approval.status != "configured"
                or approval.instrument_connection_id
                != self.identity.instrument_connection_id
                or not self.identity.adapter_profile_digest
                or self.route_confirmed is None
                or self.requested_route is None
            ):
                raise ValueError("CMW500 evidence is missing its frozen approval or route")
            if self.route_confirmed is True and self.applied_route is None:
                raise ValueError("confirmed CMW500 route requires an applied snapshot")
        else:
            if (
                self.formal_capability_approval.status != "not_applicable"
                or self.identity.adapter_profile_digest is not None
                or self.route_confirmed is not None
                or self.requested_route is not None
                or self.applied_route is not None
            ):
                raise ValueError("UXM evidence must not carry CMW500 approval or route")
        return self


class FormalMetricTrust(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["trusted", "diagnostic", "unknown"]
    formal_value: float | None
    diagnostic_value: float | None
    unit: str | None
    reason: str
    exchange_ids: tuple[str, ...] = ()


def parse_base_station_execution_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if "attach_operations" in value and value.get("attach_operations") is None:
        return None
    if (
        "measurement_window_contract_version" in value
        and value.get("measurement_window_contract_version") is None
    ):
        return None
    if (
        "metric_registry_contract_version" in value
        and value.get("metric_registry_contract_version") is None
    ):
        return None
    if (
        "execution_plan_contract_version" in value
        and value.get("execution_plan_contract_version") is None
    ):
        return None
    try:
        parsed = BaseStationExecutionEvidence.model_validate(value)
    except Exception:
        return None
    normalized = parsed.model_dump(mode="json")
    # Version-1 brownfield rows predate adapter operation receipts.  Absence is
    # preserved as absence so strict equality does not relabel every historical
    # row malformed; once the writer appends an operation the field is explicit.
    if "adapter_operations" not in value:
        normalized.pop("adapter_operations", None)
    if "attach_operations" not in value:
        normalized.pop("attach_operations", None)
    if "measurement_window_contract_version" not in value:
        normalized.pop("measurement_window_contract_version", None)
    if "metric_registry_contract_version" not in value:
        normalized.pop("metric_registry_contract_version", None)
    if "metric_registry" not in value:
        normalized.pop("metric_registry", None)
    if "execution_plan_contract_version" not in value:
        normalized.pop("execution_plan_contract_version", None)
    if "execution_plan" not in value:
        normalized.pop("execution_plan", None)
    raw_windows = value.get("measurement_windows")
    normalized_windows = normalized.get("measurement_windows")
    if isinstance(raw_windows, list) and isinstance(normalized_windows, list):
        for raw_window, normalized_window in zip(raw_windows, normalized_windows):
            if isinstance(raw_window, dict) and "trust" not in raw_window:
                normalized_window.pop("trust", None)
            if isinstance(raw_window, dict) and "metric_registry_digest" not in raw_window:
                normalized_window.pop("metric_registry_digest", None)
            # P1-74 brownfield：统计基是后加的槽位，历史窗口请求里根本没有这个
            # 键。缺席保留为缺席，否则 normalized != value 会把**每一行**历史
            # BaseStation 证据判成 malformed（同 adapter_operations 的处理）。
            raw_trust = (
                raw_window.get("trust") if isinstance(raw_window, dict) else None
            )
            normalized_trust = normalized_window.get("trust")
            if isinstance(raw_trust, dict) and isinstance(normalized_trust, dict):
                raw_request = raw_trust.get("request")
                normalized_request = normalized_trust.get("request")
                if (
                    isinstance(raw_request, dict)
                    and isinstance(normalized_request, dict)
                    and "statistical_basis_subframes" not in raw_request
                ):
                    normalized_request.pop("statistical_basis_subframes", None)
            raw_metrics = raw_window.get("metrics") if isinstance(raw_window, dict) else None
            normalized_metrics = normalized_window.get("metrics")
            if isinstance(raw_metrics, dict) and isinstance(normalized_metrics, dict):
                optional_metric_fields = (
                    "registry_digest",
                    "scope",
                    "direction",
                    "evidence",
                    "source_reference",
                    "simulated",
                    "reason",
                )
                for key, raw_metric in raw_metrics.items():
                    normalized_metric = normalized_metrics.get(key)
                    if isinstance(raw_metric, dict) and isinstance(normalized_metric, dict):
                        for field in optional_metric_fields:
                            if field not in raw_metric:
                                normalized_metric.pop(field, None)
    return normalized if normalized == value else None


def _parsed(value: Any) -> BaseStationExecutionEvidence | None:
    normalized = parse_base_station_execution_evidence(value)
    if normalized is None:
        return None
    return BaseStationExecutionEvidence.model_validate(normalized)


def _position_key(position: PositionSnapshot) -> tuple[float, float]:
    return position.azimuth_deg, position.elevation_deg


def _attempt_window_shape_envelope(
    evidence: BaseStationExecutionEvidence,
    attempt_id: str,
) -> tuple[
    bool,
    str,
    list[BaseStationMeasurementWindowEvidence],
    dict[str, BaseStationControlReleaseEvidence],
]:
    """Validate requested-position, window-cardinality, and release shape."""

    requested_keys = [_position_key(item) for item in evidence.requested_positions]
    if not requested_keys or len(set(requested_keys)) != len(requested_keys):
        return False, "requested_positions_invalid", [], {}
    windows = [
        window
        for window in evidence.measurement_windows
        if window.measurement_attempt_id == attempt_id
    ]
    window_keys = [_position_key(window.position) for window in windows]
    current_window_contract = evidence.measurement_window_contract_version == 1
    if current_window_contract:
        grouped: dict[tuple[float, float], list[BaseStationMeasurementWindowEvidence]] = {
            key: [] for key in requested_keys
        }
        for window, key in zip(windows, window_keys):
            if key not in grouped:
                return False, "current_attempt_positions_mismatch", [], {}
            grouped[key].append(window)
        if any(not group for group in grouped.values()):
            return False, "current_attempt_positions_mismatch", [], {}
        frozen_shape: tuple[str, str, str, int, int] | None = None
        for group in grouped.values():
            trusts = [window.trust for window in group]
            if any(trust is None for trust in trusts):
                return False, "measurement_window_trust_missing", [], {}
            requests = [trust.request for trust in trusts if trust is not None]
            reference = requests[0]
            common_shape = (
                reference.scope,
                reference.lifecycle,
                reference.cardinality,
                reference.requested_window_count,
                reference.expected_window_count,
            )
            if frozen_shape is None:
                frozen_shape = common_shape
            elif common_shape != frozen_shape:
                return False, "measurement_window_shape_drift", [], {}
            if (
                len(group) != reference.expected_window_count
                or {request.window_index for request in requests}
                != set(range(reference.expected_window_count))
                or any(
                    (
                        request.scope,
                        request.lifecycle,
                        request.cardinality,
                        request.requested_window_count,
                        request.expected_window_count,
                    )
                    != common_shape
                    for request in requests
                )
            ):
                return False, "measurement_window_cardinality_mismatch", [], {}
    elif len(windows) != len(requested_keys) or sorted(window_keys) != sorted(
        requested_keys
    ):
        return False, "current_attempt_positions_mismatch", [], {}
    if len(set(window.window_id for window in windows)) != len(windows):
        return False, "current_attempt_window_ids_not_unique", [], {}

    releases = [
        release
        for release in evidence.control_releases
        if release.measurement_attempt_id == attempt_id
    ]
    expected_lease_ids = {window.lease_id for window in windows}
    if (
        len(releases) != len(expected_lease_ids)
        or {release.lease_id for release in releases} != expected_lease_ids
    ):
        return False, "current_attempt_control_releases_mismatch", [], {}
    releases_by_lease = {release.lease_id: release for release in releases}
    if len(releases_by_lease) != len(releases):
        return False, "current_attempt_control_releases_not_unique", [], {}
    return True, "attempt_window_shape_confirmed", windows, releases_by_lease


def _attempt_lifecycle_envelope(
    evidence: BaseStationExecutionEvidence,
    attempt_id: str,
) -> tuple[bool, str, list[BaseStationMeasurementWindowEvidence]]:
    """Validate one attempt's complete hardware lifecycle, independent of KPI trust."""

    if evidence.current_measurement_attempt_id != attempt_id:
        return False, "measurement_attempt_not_current", []
    if evidence.config_confirmed is not True:
        return False, "config_not_confirmed", []
    if evidence.adapter == "cmw500" and (
        evidence.route_confirmed is not True
        or evidence.requested_route != evidence.applied_route
    ):
        return False, "route_not_confirmed", []
    try:
        _unique_non_empty(evidence.exchange_ids, "exchange_ids")
    except ValueError:
        return False, "execution_exchange_ids_invalid", []
    accepted, reason, windows, releases_by_lease = _attempt_window_shape_envelope(
        evidence, attempt_id
    )
    if not accepted:
        return False, reason, []
    current_window_contract = evidence.measurement_window_contract_version == 1

    for window in windows:
        release = releases_by_lease[window.lease_id]
        if (
            window.config_digest != evidence.requested_config.digest
            or window.route_digest
            != (evidence.requested_route.digest if evidence.requested_route else None)
            or window.preclear_off_confirmed is not True
            or window.running_confirmed is not True
            or window.ready_confirmed is not True
            or window.closed_off_confirmed is not True
            or window.cleanup.stop_signaling_confirmed is not True
            or window.cleanup.safe_idle_confirmed is not True
            or release.session_token != window.session_token
            or release.remote_session_acquired_confirmed is not True
            or release.transport_session_released_confirmed is not True
        ):
            return False, "current_attempt_lifecycle_not_confirmed", []
        if current_window_contract and (
            window.trust is None
            or window.trust.formally_confirmed is not True
            or window.trust.exchange_ids != window.lifecycle_exchange_ids
        ):
            return False, "measurement_window_trust_not_confirmed", []
        try:
            _unique_non_empty(window.lifecycle_exchange_ids, "lifecycle_exchange_ids")
        except ValueError:
            return False, "lifecycle_exchange_ids_invalid", []
        if not set(window.lifecycle_exchange_ids).issubset(evidence.exchange_ids):
            return False, "lifecycle_exchange_ids_not_in_execution", []
    return True, "attempt_lifecycle_confirmed", windows


def base_station_attempt_lifecycle_is_complete(value: Any, attempt_id: str) -> bool:
    """Return true only after every requested position and release is confirmed."""

    evidence = _parsed(value)
    if evidence is None or not isinstance(attempt_id, str) or not attempt_id:
        return False
    accepted, _, _ = _attempt_lifecycle_envelope(evidence, attempt_id)
    return accepted


def base_station_attempt_diagnostic_lifecycle_is_complete(
    value: Any, attempt_id: str
) -> bool:
    """Confirm diagnostic scheduling, cleanup, and release without formal truth."""

    evidence = _parsed(value)
    if (
        evidence is None
        or not isinstance(attempt_id, str)
        or not attempt_id
        or evidence.current_measurement_attempt_id != attempt_id
        or evidence.measurement_window_contract_version != 1
    ):
        return False
    accepted, _, windows, releases_by_lease = _attempt_window_shape_envelope(
        evidence, attempt_id
    )
    if not accepted:
        return False
    for window in windows:
        release = releases_by_lease[window.lease_id]
        trust = window.trust
        if (
            window.config_digest != evidence.requested_config.digest
            or window.route_digest
            != (evidence.requested_route.digest if evidence.requested_route else None)
            or trust is None
            or trust.diagnostic_execution_allowed is not True
            or window.cleanup.stop_signaling_confirmed is not True
            or window.cleanup.safe_idle_confirmed is not True
            or release.session_token != window.session_token
            or release.remote_session_acquired_confirmed is not True
            or release.transport_session_released_confirmed is not True
        ):
            return False
        if trust.exchange_ids:
            if (
                trust.exchange_ids != window.lifecycle_exchange_ids
                or not set(window.lifecycle_exchange_ids).issubset(
                    evidence.exchange_ids
                )
            ):
                return False
    return True


def _formal_envelope(
    evidence: BaseStationExecutionEvidence,
    *,
    site_qualification_confirmed: bool = False,
) -> tuple[bool, str, list[BaseStationMeasurementWindowEvidence]]:
    if evidence.execution_mode != "real":
        return False, "execution_mode_not_real", []
    if not evidence.identity.firmware_version:
        return False, "identity_incomplete", []
    if evidence.config_confirmed is not True:
        return False, "config_not_confirmed", []
    if evidence.adapter == "cmw500":
        approval = evidence.formal_capability_approval
        if evidence.identity.model != "CMW" or not _firmware_at_least(
            evidence.identity.firmware_version, (3, 5, 40)
        ):
            return False, "cmw500_identity_not_supported", []
        if approval.enabled is not True and not site_qualification_confirmed:
            return False, "formal_capability_not_approved", []
        if evidence.requested_config.payload.get("mimo_layers") != 2:
            return False, "cmw500_mimo_layers_not_2x2", []
        # R&S CMW500 LTE UE User Manual 1173.9628.02-41, Table 2-32,
        # printed pp. 65-66: for an nx2 carrier, only TM3/TM4/TM8/TM9
        # provide a dual-layer spatial-multiplexing/beamforming scheme.
        if evidence.requested_config.payload.get("lte_transmission_mode") not in {
            "TM3",
            "TM4",
            "TM8",
            "TM9",
        }:
            return False, "cmw500_transmission_mode_not_2x2", []
        duplex = evidence.requested_config.payload.get("duplex")
        required_duplex_option = (
            "KS500" if duplex == "fdd" else "KS550" if duplex == "tdd" else None
        )
        installed_options = {
            item.strip().upper().removeprefix("CMW-")
            for item in evidence.identity.options
        }
        if (
            required_duplex_option is None
            or not {"KS520", required_duplex_option}.issubset(installed_options)
        ):
            return False, "formal_capability_options_not_confirmed", []
        if evidence.route_confirmed is not True:
            return False, "route_not_confirmed", []
        if evidence.requested_route != evidence.applied_route:
            return False, "route_readback_mismatch", []
    attempt_id = evidence.current_measurement_attempt_id
    if not attempt_id or evidence.current_measurement_attempt_state != "completed":
        return False, "current_attempt_not_completed", []
    if evidence.attach_operations is not None:
        attach_operations = [
            item
            for item in evidence.attach_operations
            if item.measurement_attempt_id == attempt_id
        ]
        if len(attach_operations) != 1:
            return False, "current_attempt_attach_receipt_missing", []
        attach_operation = attach_operations[0]
        if (
            attach_operation.formally_confirmed is not True
            or attach_operation.simulated is True
            or not set(attach_operation.exchange_ids).issubset(evidence.exchange_ids)
        ):
            return False, "current_attempt_attach_not_confirmed", []
    accepted, reason, windows = _attempt_lifecycle_envelope(evidence, attempt_id)
    if not accepted:
        return False, reason, []
    if evidence.attach_operations is not None:
        attach_operation = [
            item
            for item in evidence.attach_operations
            if item.measurement_attempt_id == attempt_id
        ][0]
        if not any(
            window.lease_id == attach_operation.lease_id
            and window.session_token == attach_operation.session_token
            for window in windows
        ):
            return False, "current_attempt_attach_lease_mismatch", []
    return True, "formal_envelope_confirmed", windows


def _site_qualification_gate(
    evidence: BaseStationExecutionEvidence,
    execution_config: Any,
) -> tuple[bool | None, str]:
    """Bind new formal admission to this execution's certified live identity.

    ``None`` preserves the pre-P2-45 legacy approval contract only for rows that
    genuinely predate the qualification snapshot.  Once the snapshot key is
    present, malformed, diagnostic, stale, or identity-mismatched state fails
    closed and can never fall back to the retired CMW approval flag.
    """

    from app.services.execution_qualification import (
        EXECUTION_QUALIFICATION_KEY,
        ExecutionQualification,
        validate_frozen_execution_qualification,
    )

    if (
        not isinstance(execution_config, dict)
        or EXECUTION_QUALIFICATION_KEY not in execution_config
    ):
        if evidence.metric_registry_contract_version == 1:
            return False, "execution_qualification_missing"
        return None, "legacy_qualification_absent"
    raw = execution_config.get(EXECUTION_QUALIFICATION_KEY)
    if validate_frozen_execution_qualification(raw) is not None:
        return False, "execution_qualification_invalid"
    qualification = ExecutionQualification.model_validate(raw)
    certification = qualification.site_certification
    if qualification.classification != "formal":
        return False, "execution_qualification_not_formal"
    if (
        certification is None
        or certification.status != "active"
        or certification.binding_digest != qualification.binding_digest
        or certification.adapter_id != qualification.adapter_id
        or certification.adapter_id != evidence.adapter
        or certification.instrument_connection_id
        != evidence.identity.instrument_connection_id
    ):
        return False, "site_certification_scope_mismatch"
    if (
        certification.model != evidence.identity.model
        or certification.firmware_version != evidence.identity.firmware_version
        or certification.options != tuple(sorted(set(evidence.identity.options)))
    ):
        return False, "site_certification_identity_mismatch"
    return True, "site_certification_identity_confirmed"


def base_station_execution_evidence_is_formally_acceptable(
    value: Any,
    *,
    execution_config: Any = None,
) -> bool:
    evidence = _parsed(value)
    if evidence is None:
        return False
    qualified, _ = _site_qualification_gate(evidence, execution_config)
    if qualified is False:
        return False
    accepted, _, _ = _formal_envelope(
        evidence,
        site_qualification_confirmed=qualified is True,
    )
    return accepted


def _raw_metric(
    value: Any,
    metric_name: str,
    expected_position: Any | None = None,
) -> tuple[float | None, str | None]:
    if not isinstance(value, dict):
        return None, None
    attempt_id = value.get("current_measurement_attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id:
        return None, None
    try:
        position = PositionSnapshot.model_validate(expected_position)
    except Exception:
        return None, None
    windows = value.get("measurement_windows")
    if not isinstance(windows, list):
        return None, None
    matching: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        if window.get("measurement_attempt_id") != attempt_id:
            continue
        try:
            window_position = PositionSnapshot.model_validate(window.get("position"))
        except Exception:
            continue
        if _position_key(window_position) != _position_key(position):
            continue
        metrics = window.get("metrics")
        metric = metrics.get(metric_name) if isinstance(metrics, dict) else None
        if not isinstance(metric, dict):
            continue
        if (
            metric.get("measurement_attempt_id") != attempt_id
            or metric.get("session_token") != window.get("session_token")
        ):
            continue
        matching.append((window, metric))
    if len(matching) != 1:
        return None, None
    _, metric = matching[0]
    number = metric.get("value")
    unit = metric.get("unit")
    if (
        not isinstance(number, bool)
        and isinstance(number, (int, float))
        and math.isfinite(float(number))
        and isinstance(unit, str)
    ):
        return float(number), unit
    return None, None


def _untrusted(
    value: Any,
    metric_name: str,
    reason: str,
    expected_position: Any | None = None,
) -> FormalMetricTrust:
    diagnostic_value, unit = _raw_metric(value, metric_name, expected_position)
    return FormalMetricTrust(
        status="diagnostic" if diagnostic_value is not None else "unknown",
        formal_value=None,
        diagnostic_value=diagnostic_value,
        unit=unit,
        reason=reason,
    )


def evaluate_base_station_metric_trust(
    evidence: Any,
    metric_name: str,
    expected_config: Any,
    expected_position: Any,
    *,
    execution_config: Any = None,
) -> FormalMetricTrust:
    """Evaluate one base-station-native metric against execution-frozen scope."""

    try:
        position = PositionSnapshot.model_validate(expected_position)
    except Exception:
        return _untrusted(evidence, metric_name, "invalid_expected_position")
    position_payload = position.model_dump(mode="json")
    parsed = _parsed(evidence)
    if parsed is None:
        return _untrusted(
            evidence, metric_name, "invalid_evidence_schema", position_payload
        )
    capability = None
    if parsed.metric_registry_contract_version == 1:
        registry = parsed.metric_registry
        if registry is None:  # guarded by model validation
            return _untrusted(
                evidence, metric_name, "metric_registry_missing", position_payload
            )
        try:
            capability = registry.capability(metric_name)
        except KeyError:
            return _untrusted(
                evidence,
                metric_name,
                "metric_not_declared_in_registry",
                position_payload,
            )
        expected_unit = capability.unit
    else:
        expected_unit = _LEGACY_METRIC_UNITS.get(metric_name)
        if expected_unit is None:
            return _untrusted(
                evidence, metric_name, "unsupported_metric", position_payload
            )
    if expected_config != parsed.requested_config.payload:
        return FormalMetricTrust(
            status="unknown",
            formal_value=None,
            diagnostic_value=None,
            unit=None,
            reason="expected_config_mismatch",
        )
    if _position_key(position) not in {
        _position_key(item) for item in parsed.requested_positions
    }:
        return FormalMetricTrust(
            status="unknown",
            formal_value=None,
            diagnostic_value=None,
            unit=None,
            reason="expected_position_not_requested",
        )

    qualified, qualification_reason = _site_qualification_gate(
        parsed,
        execution_config,
    )
    if qualified is False:
        return _untrusted(
            evidence,
            metric_name,
            qualification_reason,
            position_payload,
        )
    accepted, reason, windows = _formal_envelope(
        parsed,
        site_qualification_confirmed=qualified is True,
    )
    if not accepted:
        return _untrusted(evidence, metric_name, reason, position_payload)
    matching = [
        window for window in windows if _position_key(window.position) == _position_key(position)
    ]
    if len(matching) != 1:
        return _untrusted(
            evidence,
            metric_name,
            "expected_position_window_not_unique",
            position_payload,
        )
    window = matching[0]
    metric = window.metrics.get(metric_name)
    if (
        metric is None
        or metric.measurement_attempt_id != parsed.current_measurement_attempt_id
        or metric.session_token != window.session_token
        or metric.value is None
        or metric.unit != expected_unit
    ):
        return _untrusted(
            evidence, metric_name, "metric_evidence_mismatch", position_payload
        )
    if parsed.metric_registry_contract_version == 1 and (
        capability is None
        or capability.evidence != "authoritative"
        or metric.registry_digest != parsed.metric_registry.digest
        or metric.evidence != capability.evidence
        or metric.source_reference != capability.source_reference
        or metric.simulated is not False
        or metric.scope is None
    ):
        return _untrusted(
            evidence,
            metric_name,
            "metric_semantics_not_authoritative",
            position_payload,
        )
    try:
        exchange_ids = _unique_non_empty(metric.exchange_ids, "metric_exchange_ids")
    except ValueError:
        return _untrusted(
            evidence, metric_name, "metric_exchange_ids_invalid", position_payload
        )
    if not set(exchange_ids).issubset(parsed.exchange_ids):
        return _untrusted(
            evidence,
            metric_name,
            "metric_exchange_ids_not_in_execution",
            position_payload,
        )
    return FormalMetricTrust(
        status="trusted",
        formal_value=metric.value,
        diagnostic_value=metric.value,
        unit=metric.unit,
        reason="formal_metric_confirmed",
        exchange_ids=tuple(exchange_ids),
    )


def base_station_expected_scope_from_evidence(
    evidence: Any,
) -> tuple[dict[str, Any] | None, list[dict[str, float]]]:
    """Read the immutable requested scope from this execution's strict snapshot."""

    parsed = _parsed(evidence)
    if parsed is None:
        return None, []
    return (
        parsed.requested_config.payload,
        [position.model_dump(mode="json") for position in parsed.requested_positions],
    )


def project_base_station_metrics_by_position(
    evidence: Any,
    *,
    expected_config: Any,
    expected_positions: list[dict[str, Any]],
    execution_config: Any = None,
) -> list[dict[str, Any]]:
    """Project every frozen registry metric plus two stable compatibility mirrors."""

    parsed = _parsed(evidence)
    metric_names = (
        [item.key for item in parsed.metric_registry.metrics]
        if parsed is not None
        and parsed.metric_registry_contract_version == 1
        and parsed.metric_registry is not None
        else list(_LEGACY_METRIC_UNITS)
    )
    rows: list[dict[str, Any]] = []
    for expected_position in expected_positions:
        position = PositionSnapshot.model_validate(expected_position).model_dump(
            mode="json"
        )
        metrics = {
            metric_name: evaluate_base_station_metric_trust(
                evidence,
                metric_name,
                expected_config,
                position,
                execution_config=execution_config,
            )
            for metric_name in metric_names
        }
        compatibility = {
            metric_name: metrics.get(metric_name)
            or evaluate_base_station_metric_trust(
                evidence,
                metric_name,
                expected_config,
                position,
                execution_config=execution_config,
            )
            for metric_name in _LEGACY_METRIC_UNITS
        }
        rows.append({"position": position, "metrics": metrics, **compatibility})
    return rows
