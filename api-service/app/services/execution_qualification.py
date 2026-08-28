"""Server-owned Diagnostic/Formal execution qualification contracts.

This module contains persistence-safe value objects only.  It never connects to
an instrument and never infers authority from client configuration fields.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TestCaseExecutionPolicy(BaseModel):
    """Current server-owned TestCase execution policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    mode: Literal["formal", "diagnostic"]
    reason: str
    updated_by: str
    updated_at: datetime

    @field_validator("reason", "updated_by")
    @classmethod
    def _non_blank_audit_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("execution policy audit fields must be non-blank")
        return normalized


class BaseStationCertificationProofs(BaseModel):
    """Proof classes required before a site certification may become active."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_readback: bool
    route_readback: bool
    route_not_applicable: bool
    cleanup: bool
    transport_release: bool

    @model_validator(mode="after")
    def _all_required_proofs_are_explicit(self):
        if self.config_readback is not True:
            raise ValueError("site certification requires config readback")
        if self.cleanup is not True:
            raise ValueError("site certification requires cleanup confirmation")
        if self.transport_release is not True:
            raise ValueError("site certification requires transport release")
        if (self.route_readback is True) == (self.route_not_applicable is True):
            raise ValueError(
                "site certification requires exactly one route proof outcome"
            )
        return self


class BaseStationSiteCertification(BaseModel):
    """Current certification bound to one resolved lab/connection truth."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    status: Literal["active", "revoked"]
    lab_profile_id: str
    instrument_connection_id: str
    binding_digest: str
    adapter_id: str
    model: str
    firmware_version: str
    options: tuple[str, ...]
    source_execution_id: str
    evidence_digest: str
    required_proofs: BaseStationCertificationProofs
    certified_by: str
    certified_at: datetime
    reason: str
    revoked_by: str | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    @field_validator(
        "lab_profile_id",
        "instrument_connection_id",
        "adapter_id",
        "model",
        "firmware_version",
        "source_execution_id",
        "certified_by",
        "reason",
    )
    @classmethod
    def _non_blank_identity_or_audit(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("site certification fields must be non-blank")
        return normalized

    @field_validator("binding_digest", "evidence_digest")
    @classmethod
    def _valid_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _DIGEST_RE.fullmatch(normalized):
            raise ValueError("site certification digest must be lowercase sha256")
        return normalized

    @field_validator("options")
    @classmethod
    def _canonical_options(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({value.strip() for value in values if value.strip()}))
        return normalized

    @model_validator(mode="after")
    def _revocation_audit_matches_status(self):
        revoke_values = (
            self.revoked_by,
            self.revoked_at,
            self.revocation_reason,
        )
        if self.status == "active":
            if any(value is not None for value in revoke_values):
                raise ValueError("active site certification cannot contain revocation audit")
            return self
        if any(value is None for value in revoke_values):
            raise ValueError("revoked site certification requires complete revocation audit")
        assert self.revoked_by is not None
        assert self.revocation_reason is not None
        if not self.revoked_by.strip() or not self.revocation_reason.strip():
            raise ValueError("revocation audit fields must be non-blank")
        return self

    @property
    def certification_digest(self) -> str:
        return _canonical_digest(self.model_dump(mode="json"))


def parse_test_case_execution_policy(
    raw: Any,
) -> TestCaseExecutionPolicy | None:
    """Parse explicit policy; absent means the backward-compatible formal default."""

    if raw is None:
        return None
    try:
        return TestCaseExecutionPolicy.model_validate(raw)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError("stored TestCase execution policy is invalid") from exc


def parse_base_station_site_certification(
    raw: Any,
) -> BaseStationSiteCertification | None:
    """Parse explicit certification; absent means no formal site qualification."""

    if raw is None:
        return None
    try:
        return BaseStationSiteCertification.model_validate(raw)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError("stored BaseStation site certification is invalid") from exc


def _audit_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be non-blank")
    return normalized


def activate_base_station_site_certification(
    db,
    hal,
    *,
    connection_id,
    source_execution_id,
    certified_by: str,
    reason: str,
) -> BaseStationSiteCertification:
    """Derive certification only from one completed real execution envelope."""

    from app.models.instrument import InstrumentConnection
    from app.models.lab_profile import LabProfile
    from app.models.test_plan import TestCase, TestExecution
    from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
    from app.services.base_station_binding import resolve_base_station_binding
    from app.services.execution_scpi_evidence import (
        load_base_station_execution_evidence,
    )
    from app.services.mimo_ota.base_station_execution_evidence import (
        BaseStationExecutionEvidence,
        base_station_attempt_lifecycle_is_complete,
        canonical_snapshot_digest,
    )

    actor = _audit_text(certified_by, "certified_by")
    audit_reason = _audit_text(reason, "reason")
    connection = (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.id == connection_id)
        .with_for_update()
        .one_or_none()
    )
    if connection is None:
        raise LookupError("instrument connection not found")
    execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == source_execution_id)
        .with_for_update()
        .one_or_none()
    )
    if execution is None:
        raise LookupError("source execution not found")
    if execution.status != "completed" or execution.test_case_id is None:
        raise ValueError("site certification requires a completed TestCase execution")
    test_case = db.query(TestCase).filter(TestCase.id == execution.test_case_id).one_or_none()
    if test_case is None or test_case.lab_profile_id is None:
        raise ValueError("source execution has no bound LabProfile")
    lab = (
        db.query(LabProfile)
        .filter(LabProfile.id == test_case.lab_profile_id)
        .with_for_update()
        .one_or_none()
    )
    if lab is None:
        raise ValueError("source execution LabProfile is missing")

    resolved = resolve_base_station_binding(db, hal, lab, lock=True)
    if (
        resolved.execution_mode != "real"
        or resolved.manifest is None
        or resolved.instrument_connection_id != str(connection.id)
    ):
        raise ValueError("site certification requires the current real BaseStation binding")

    config = execution.config if isinstance(execution.config, dict) else {}
    frozen = config.get(FREEZE_CONFIG_KEY)
    if not isinstance(frozen, dict):
        raise ValueError("source execution binding freeze is missing")
    if (
        frozen.get("binding_digest") != resolved.binding_digest
        or frozen.get("instrument_connection_id") != str(connection.id)
        or frozen.get("lab_profile_id") != str(lab.id)
        or frozen.get("resolution", {}).get("adapter")
        != resolved.manifest.adapter_id
        or frozen.get("resolution", {}).get("execution_mode") != "real"
    ):
        raise ValueError("source execution binding does not match current server truth")

    raw_evidence = load_base_station_execution_evidence(execution)
    if raw_evidence is None:
        raise ValueError("source execution evidence is missing or malformed")
    evidence = BaseStationExecutionEvidence.model_validate(raw_evidence)
    attempt_id = evidence.current_measurement_attempt_id
    if (
        evidence.execution_id != str(execution.id)
        or evidence.execution_mode != "real"
        or evidence.adapter != resolved.manifest.adapter_id
        or evidence.identity.instrument_connection_id != str(connection.id)
        or evidence.identity.firmware_version is None
        or evidence.config_confirmed is not True
        or attempt_id is None
        or evidence.current_measurement_attempt_state != "completed"
        or not base_station_attempt_lifecycle_is_complete(raw_evidence, attempt_id)
    ):
        raise ValueError("source execution does not contain complete formal hardware evidence")

    if evidence.adapter == "cmw500":
        route_readback = (
            evidence.route_confirmed is True
            and evidence.requested_route == evidence.applied_route
        )
        route_not_applicable = False
    else:
        route_readback = False
        route_not_applicable = (
            evidence.route_confirmed is None
            and evidence.requested_route is None
            and evidence.applied_route is None
        )
    proofs = BaseStationCertificationProofs(
        config_readback=True,
        route_readback=route_readback,
        route_not_applicable=route_not_applicable,
        cleanup=True,
        transport_release=True,
    )
    certification = BaseStationSiteCertification(
        schema_version=1,
        status="active",
        lab_profile_id=str(lab.id),
        instrument_connection_id=str(connection.id),
        binding_digest=resolved.binding_digest,
        adapter_id=evidence.adapter,
        model=evidence.identity.model,
        firmware_version=evidence.identity.firmware_version,
        options=tuple(evidence.identity.options),
        source_execution_id=str(execution.id),
        evidence_digest=canonical_snapshot_digest(raw_evidence),
        required_proofs=proofs,
        certified_by=actor,
        certified_at=datetime.now(timezone.utc),
        reason=audit_reason,
    )
    connection.base_station_site_certification = certification.model_dump(mode="json")
    db.commit()
    db.refresh(connection)
    return certification


def revoke_base_station_site_certification(
    db,
    *,
    connection_id,
    revoked_by: str,
    reason: str,
) -> BaseStationSiteCertification:
    """Revoke without deleting the source proof or historical certification."""

    from app.models.instrument import InstrumentConnection

    actor = _audit_text(revoked_by, "revoked_by")
    audit_reason = _audit_text(reason, "reason")
    connection = (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.id == connection_id)
        .with_for_update()
        .one_or_none()
    )
    if connection is None:
        raise LookupError("instrument connection not found")
    current = parse_base_station_site_certification(
        connection.base_station_site_certification
    )
    if current is None or current.status != "active":
        raise ValueError("active BaseStation site certification is missing")
    revoked = current.model_copy(
        update={
            "status": "revoked",
            "revoked_by": actor,
            "revoked_at": datetime.now(timezone.utc),
            "revocation_reason": audit_reason,
        }
    )
    revoked = BaseStationSiteCertification.model_validate(revoked)
    connection.base_station_site_certification = revoked.model_dump(mode="json")
    db.commit()
    db.refresh(connection)
    return revoked
