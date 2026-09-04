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


class ChannelEmulatorCertificationIdentity(BaseModel):
    """Pure snapshot of identity/options already observed on one live driver."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
    )

    schema_version: Literal[1]
    instrument_id: str
    adapter_id: str
    model: str | None
    firmware_version: str | None
    serial_number: str | None
    options: tuple[str, ...]
    options_observed: bool
    simulated: bool
    captured_from_live_connection: bool
    digest: str

    @field_validator("instrument_id", "adapter_id")
    @classmethod
    def _required_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("channelEmulator certification identity must be non-blank")
        return normalized

    @field_validator("model", "firmware_version", "serial_number")
    @classmethod
    def _optional_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("options", mode="before")
    @classmethod
    def _canonical_identity_options(cls, values: Any) -> tuple[str, ...]:
        if not isinstance(values, (list, tuple)):
            raise ValueError("channelEmulator certification options must be an array")
        return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))

    @field_validator("digest")
    @classmethod
    def _identity_digest_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _DIGEST_RE.fullmatch(normalized):
            raise ValueError("channelEmulator certification identity digest is invalid")
        return normalized

    @model_validator(mode="after")
    def _validate_identity_state_and_digest(self) -> "ChannelEmulatorCertificationIdentity":
        if self.simulated and (
            self.captured_from_live_connection or self.options_observed
        ):
            raise ValueError("simulated channelEmulator cannot claim live identity/options")
        payload = self.model_dump(mode="json", exclude={"digest"})
        if self.digest != _canonical_digest(payload):
            raise ValueError("channelEmulator certification identity digest mismatch")
        return self

    @property
    def certification_eligible(self) -> bool:
        return (
            self.simulated is False
            and self.captured_from_live_connection is True
            and self.options_observed is True
            and all(
                value is not None
                for value in (self.model, self.firmware_version, self.serial_number)
            )
        )


def build_channel_emulator_certification_identity(
    *,
    instrument_id: str,
    adapter_id: str,
    model: str | None,
    firmware_version: str | None,
    serial_number: str | None,
    options: tuple[str, ...] | list[str],
    options_observed: bool,
    simulated: bool,
    captured_from_live_connection: bool,
) -> ChannelEmulatorCertificationIdentity:
    payload = {
        "schema_version": 1,
        "instrument_id": instrument_id,
        "adapter_id": adapter_id,
        "model": model,
        "firmware_version": firmware_version,
        "serial_number": serial_number,
        "options": tuple(sorted({value.strip() for value in options if value.strip()})),
        "options_observed": options_observed,
        "simulated": simulated,
        "captured_from_live_connection": captured_from_live_connection,
    }
    return ChannelEmulatorCertificationIdentity.model_validate(
        {**payload, "digest": _canonical_digest(payload)}
    )


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
