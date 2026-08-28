"""Server-owned Diagnostic/Formal execution qualification contracts.

This module contains persistence-safe value objects only.  It never connects to
an instrument and never infers authority from client configuration fields.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
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
