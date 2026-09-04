"""Server-owned Channel Emulator site-certification value objects.

This module is deliberately free of instrument I/O.  Certification activation
and execution freezing are added in later slices; ordinary connection payloads
must never be able to construct or replace this server-owned state.
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


class ChannelEmulatorCertificationProofs(BaseModel):
    """Proof classes that must all be derived from one source execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_plan_asset: bool
    hardware_identity_options: bool
    operation_receipts: bool
    frequency: bool
    level: bool
    path_loss: bool
    safe_idle: bool
    transport_release: bool

    @model_validator(mode="after")
    def _all_proofs_are_required(self) -> "ChannelEmulatorCertificationProofs":
        if any(getattr(self, name) is not True for name in type(self).model_fields):
            raise ValueError(
                "channelEmulator site certification requires every proof class"
            )
        return self


class ChannelEmulatorSiteCertification(BaseModel):
    """Current certification bound to one exact CE site and evidence scope."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    schema_version: Literal[1]
    status: Literal["active", "revoked"]
    lab_profile_id: str
    instrument_connection_id: str
    instrument_model_id: str
    binding_digest: str
    adapter_id: str
    plan_digest: str
    asset_digest: str
    load_mode: Literal["native_model", "external_waveform", "parametric_tdl"]
    model: str
    firmware_version: str
    serial_number: str
    options: tuple[str, ...]
    identity_digest: str
    source_execution_id: str
    terminal_evidence_digest: str
    operation_receipts_digest: str
    measurement_evidence_digest: str
    required_proofs: ChannelEmulatorCertificationProofs
    certified_by: str
    certified_at: datetime
    reason: str
    revoked_by: str | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    @field_validator(
        "lab_profile_id",
        "instrument_connection_id",
        "instrument_model_id",
        "adapter_id",
        "model",
        "firmware_version",
        "serial_number",
        "source_execution_id",
        "certified_by",
        "reason",
    )
    @classmethod
    def _non_blank_identity_or_audit(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("channelEmulator site certification fields must be non-blank")
        return normalized

    @field_validator(
        "binding_digest",
        "plan_digest",
        "asset_digest",
        "identity_digest",
        "terminal_evidence_digest",
        "operation_receipts_digest",
        "measurement_evidence_digest",
    )
    @classmethod
    def _valid_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _DIGEST_RE.fullmatch(normalized):
            raise ValueError(
                "channelEmulator site certification digest must be lowercase sha256"
            )
        return normalized

    @field_validator("options")
    @classmethod
    def _canonical_options(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({value.strip() for value in values if value.strip()}))

    @model_validator(mode="after")
    def _revocation_audit_matches_status(self) -> "ChannelEmulatorSiteCertification":
        audit = (self.revoked_by, self.revoked_at, self.revocation_reason)
        if self.status == "active":
            if any(value is not None for value in audit):
                raise ValueError(
                    "active channelEmulator certification cannot contain revocation audit"
                )
            return self
        if any(value is None for value in audit):
            raise ValueError(
                "revoked channelEmulator certification requires complete revocation audit"
            )
        assert self.revoked_by is not None
        assert self.revocation_reason is not None
        if not self.revoked_by.strip() or not self.revocation_reason.strip():
            raise ValueError("revocation audit fields must be non-blank")
        return self

    @property
    def certification_digest(self) -> str:
        return _canonical_digest(self.model_dump(mode="json"))


def parse_channel_emulator_site_certification(
    raw: Any,
) -> ChannelEmulatorSiteCertification | None:
    """Parse current server-owned state; absence means not certified."""

    if raw is None:
        return None
    try:
        return ChannelEmulatorSiteCertification.model_validate(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "stored Channel Emulator site certification is invalid"
        ) from exc
