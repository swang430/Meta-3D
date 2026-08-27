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
    field_validator,
    model_validator,
)


BASE_STATION_EXECUTION_EVIDENCE_FIELD = "base_station_execution_evidence"
BASE_STATION_EXECUTION_EVIDENCE_SCHEMA_VERSION = 1
MIMO_OTA_FROZEN_THEORETICAL_PEAK_FIELD = (
    "mimo_ota_theoretical_peak_throughput_mbps"
)
_METRIC_UNITS = {
    "dl_throughput_mbps": "Mbps",
    "dl_bler_percent": "%",
}


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


class BaseStationMetricEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_attempt_id: str
    session_token: str
    value: float | None
    unit: str
    exchange_ids: list[str] = Field(default_factory=list)

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


class BaseStationCleanupEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_signaling_confirmed: StrictBool
    safe_idle_confirmed: StrictBool
    warnings: list[str]


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
    try:
        parsed = BaseStationExecutionEvidence.model_validate(value)
    except Exception:
        return None
    normalized = parsed.model_dump(mode="json")
    return normalized if normalized == value else None


def _parsed(value: Any) -> BaseStationExecutionEvidence | None:
    normalized = parse_base_station_execution_evidence(value)
    if normalized is None:
        return None
    return BaseStationExecutionEvidence.model_validate(normalized)


def _position_key(position: PositionSnapshot) -> tuple[float, float]:
    return position.azimuth_deg, position.elevation_deg


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

    requested_keys = [_position_key(item) for item in evidence.requested_positions]
    if not requested_keys or len(set(requested_keys)) != len(requested_keys):
        return False, "requested_positions_invalid", []
    windows = [
        window
        for window in evidence.measurement_windows
        if window.measurement_attempt_id == attempt_id
    ]
    window_keys = [_position_key(window.position) for window in windows]
    if len(windows) != len(requested_keys) or sorted(window_keys) != sorted(requested_keys):
        return False, "current_attempt_positions_mismatch", []
    if len(set(window.window_id for window in windows)) != len(windows):
        return False, "current_attempt_window_ids_not_unique", []

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
        return False, "current_attempt_control_releases_mismatch", []
    releases_by_lease = {release.lease_id: release for release in releases}
    if len(releases_by_lease) != len(releases):
        return False, "current_attempt_control_releases_not_unique", []

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


def _formal_envelope(
    evidence: BaseStationExecutionEvidence,
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
        if approval.enabled is not True:
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
            "CMW-KS500" if duplex == "fdd" else "CMW-KS550" if duplex == "tdd" else None
        )
        installed_options = {item.upper() for item in evidence.identity.options}
        if (
            required_duplex_option is None
            or not {"CMW-KS520", required_duplex_option}.issubset(installed_options)
        ):
            return False, "formal_capability_options_not_confirmed", []
        if evidence.route_confirmed is not True:
            return False, "route_not_confirmed", []
        if evidence.requested_route != evidence.applied_route:
            return False, "route_readback_mismatch", []
    attempt_id = evidence.current_measurement_attempt_id
    if not attempt_id or evidence.current_measurement_attempt_state != "completed":
        return False, "current_attempt_not_completed", []
    accepted, reason, windows = _attempt_lifecycle_envelope(evidence, attempt_id)
    if not accepted:
        return False, reason, []
    return True, "formal_envelope_confirmed", windows


def base_station_execution_evidence_is_formally_acceptable(value: Any) -> bool:
    evidence = _parsed(value)
    if evidence is None:
        return False
    accepted, _, _ = _formal_envelope(evidence)
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
) -> FormalMetricTrust:
    """Evaluate one base-station-native metric against execution-frozen scope."""

    try:
        position = PositionSnapshot.model_validate(expected_position)
    except Exception:
        return _untrusted(evidence, metric_name, "invalid_expected_position")
    position_payload = position.model_dump(mode="json")
    if metric_name not in _METRIC_UNITS:
        return _untrusted(
            evidence, metric_name, "unsupported_metric", position_payload
        )
    parsed = _parsed(evidence)
    if parsed is None:
        return _untrusted(
            evidence, metric_name, "invalid_evidence_schema", position_payload
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

    accepted, reason, windows = _formal_envelope(parsed)
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
    expected_unit = _METRIC_UNITS[metric_name]
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
) -> list[dict[str, Any]]:
    """Project both native metrics independently for every frozen position."""

    rows: list[dict[str, Any]] = []
    for expected_position in expected_positions:
        position = PositionSnapshot.model_validate(expected_position).model_dump(
            mode="json"
        )
        rows.append(
            {
                "position": position,
                "dl_throughput_mbps": evaluate_base_station_metric_trust(
                    evidence,
                    "dl_throughput_mbps",
                    expected_config,
                    position,
                ),
                "dl_bler_percent": evaluate_base_station_metric_trust(
                    evidence,
                    "dl_bler_percent",
                    expected_config,
                    position,
                ),
            }
        )
    return rows
