"""Server-owned Channel Emulator site-certification value objects.

This module is deliberately free of instrument I/O.  Certification activation
and execution freezing are added in later slices; ordinary connection payloads
must never be able to construct or replace this server-owned state.
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
    ValidationError,
    field_validator,
    model_validator,
)


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
CE_EXECUTION_QUALIFICATION_CONFIG_KEY = "channel_emulator_execution_qualification"


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


class ChannelEmulatorExecutionQualification(BaseModel):
    """Immutable classification for one execution's frozen CE scope."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    schema_version: Literal[1]
    classification: Literal["formal", "diagnostic"]
    policy_mode: Literal["formal", "diagnostic"]
    diagnostic_actor: str | None
    diagnostic_reasons: tuple[str, ...]
    base_station_qualification_digest: str
    lab_profile_id: str
    instrument_connection_id: str | None
    instrument_model_id: str | None
    binding_digest: str
    plan_digest: str
    asset_digest: str
    adapter_id: str
    load_mode: Literal["native_model", "external_waveform", "parametric_tdl"]
    site_certification: ChannelEmulatorSiteCertification | None
    site_certification_digest: str | None
    identity_digest: str | None
    reasons: tuple[str, ...]
    frozen_at: datetime
    qualification_digest: str

    @field_validator(
        "lab_profile_id",
        "binding_digest",
        "plan_digest",
        "asset_digest",
        "adapter_id",
    )
    @classmethod
    def _qualification_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("channelEmulator execution qualification fields must be non-blank")
        return normalized

    @field_validator(
        "base_station_qualification_digest",
        "binding_digest",
        "plan_digest",
        "asset_digest",
        "site_certification_digest",
        "identity_digest",
        "qualification_digest",
    )
    @classmethod
    def _qualification_digest_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not _DIGEST_RE.fullmatch(normalized):
            raise ValueError("channelEmulator execution qualification digest is invalid")
        return normalized

    @field_validator("diagnostic_reasons", "reasons", mode="before")
    @classmethod
    def _qualification_reasons_array(cls, values: Any) -> tuple[str, ...]:
        if not isinstance(values, (list, tuple)):
            raise ValueError("channelEmulator execution qualification reasons must be an array")
        return tuple(str(value).strip() for value in values if str(value).strip())

    @model_validator(mode="after")
    def _qualification_is_consistent_and_digest_bound(
        self,
    ) -> "ChannelEmulatorExecutionQualification":
        if self.classification == "formal" and self.reasons:
            raise ValueError("formal channelEmulator qualification cannot contain reasons")
        if self.classification == "diagnostic" and not self.reasons:
            raise ValueError("diagnostic channelEmulator qualification requires reasons")
        expected_cert_digest = (
            self.site_certification.certification_digest
            if self.site_certification is not None
            else None
        )
        if self.site_certification_digest != expected_cert_digest:
            raise ValueError("channelEmulator qualification certification digest mismatch")
        expected_identity_digest = (
            self.site_certification.identity_digest
            if self.site_certification is not None
            else None
        )
        if self.identity_digest != expected_identity_digest:
            raise ValueError("channelEmulator qualification identity digest mismatch")
        payload = self.model_dump(mode="json", exclude={"qualification_digest"})
        if self.qualification_digest != _canonical_digest(payload):
            raise ValueError("channelEmulator execution qualification digest mismatch")
        return self


class ChannelEmulatorCertificationPreview(BaseModel):
    """Server-owned readiness projection for the current CE binding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["formal_ready", "diagnostic", "invalid", "not_applicable"]
    binding_digest: str | None
    adapter_id: str | None
    instrument_model_id: str | None
    instrument_connection_id: str | None
    lab_profile_id: str | None
    site_certification: ChannelEmulatorSiteCertification | None
    site_certification_digest: str | None
    reasons: tuple[str, ...]
    detail: str


class ChannelEmulatorCertificationPreviewScope(BaseModel):
    """Current server-resolved plan/asset/identity scope used by readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    plan_digest: str
    asset_digest: str
    load_mode: Literal["native_model", "external_waveform", "parametric_tdl"]
    identity_digest: str

    @field_validator("plan_digest", "asset_digest", "identity_digest")
    @classmethod
    def _valid_scope_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _DIGEST_RE.fullmatch(normalized):
            raise ValueError("channelEmulator certification preview digest is invalid")
        return normalized


def build_channel_emulator_certification_preview(
    binding_preview: Any | None,
    raw_certification: Any,
    *,
    current_scope: ChannelEmulatorCertificationPreviewScope | None = None,
) -> ChannelEmulatorCertificationPreview:
    """Project current server truth without consulting a transport or client state."""

    if binding_preview is None:
        return ChannelEmulatorCertificationPreview(
            status="not_applicable",
            binding_digest=None,
            adapter_id=None,
            instrument_model_id=None,
            instrument_connection_id=None,
            lab_profile_id=None,
            site_certification=None,
            site_certification_digest=None,
            reasons=("lab_profile_not_resolved",),
            detail="未解析 LabProfile，信道仿真器现场认证不适用",
        )
    binding_status = getattr(binding_preview, "status", None)
    common = {
        "binding_digest": getattr(binding_preview, "binding_digest", None),
        "adapter_id": getattr(binding_preview, "adapter_id", None),
        "instrument_model_id": getattr(
            binding_preview, "instrument_model_id", None
        ),
        "instrument_connection_id": getattr(
            binding_preview, "instrument_connection_id", None
        ),
        "lab_profile_id": getattr(binding_preview, "lab_profile_id", None),
    }
    if binding_status == "invalid":
        return ChannelEmulatorCertificationPreview(
            status="invalid",
            **common,
            site_certification=None,
            site_certification_digest=None,
            reasons=("channel_emulator_binding_invalid",),
            detail="信道仿真器 binding 无效，正式 KPI 保持 UNKNOWN/N/A",
        )
    if (
        binding_status != "configured"
        or getattr(binding_preview, "execution_mode", None) != "real"
    ):
        return ChannelEmulatorCertificationPreview(
            status="diagnostic",
            **common,
            site_certification=None,
            site_certification_digest=None,
            reasons=("channel_emulator_execution_not_real",),
            detail="当前仅允许诊断执行，正式 KPI 保持 UNKNOWN/N/A",
        )
    try:
        certification = parse_channel_emulator_site_certification(raw_certification)
    except ValueError:
        return ChannelEmulatorCertificationPreview(
            status="invalid",
            **common,
            site_certification=None,
            site_certification_digest=None,
            reasons=("site_certification_invalid",),
            detail="服务器保存的信道仿真器现场认证无效",
        )
    if certification is None or certification.status != "active":
        return ChannelEmulatorCertificationPreview(
            status="diagnostic",
            **common,
            site_certification=certification,
            site_certification_digest=(
                certification.certification_digest
                if certification is not None
                else None
            ),
            reasons=("site_certification_not_active",),
            detail="信道仿真器未持有活动现场认证，正式 KPI 保持 UNKNOWN/N/A",
        )
    expected_scope = (
        common["lab_profile_id"],
        common["instrument_connection_id"],
        common["instrument_model_id"],
        common["binding_digest"],
        common["adapter_id"],
    )
    certification_scope = (
        certification.lab_profile_id,
        certification.instrument_connection_id,
        certification.instrument_model_id,
        certification.binding_digest,
        certification.adapter_id,
    )
    if certification_scope != expected_scope:
        return ChannelEmulatorCertificationPreview(
            status="diagnostic",
            **common,
            site_certification=certification,
            site_certification_digest=certification.certification_digest,
            reasons=("site_certification_scope_mismatch",),
            detail="现场认证与当前 binding 不一致，正式 KPI 保持 UNKNOWN/N/A",
        )
    if current_scope is None:
        return ChannelEmulatorCertificationPreview(
            status="diagnostic",
            **common,
            site_certification=certification,
            site_certification_digest=certification.certification_digest,
            reasons=("certification_scope_not_evaluated",),
            detail="尚未解析当前 TestCase 的计划、资产与硬件身份，正式 KPI 保持 UNKNOWN/N/A",
        )
    expected_execution_scope = (
        certification.plan_digest,
        certification.asset_digest,
        certification.load_mode,
        certification.identity_digest,
    )
    current_execution_scope = (
        current_scope.plan_digest,
        current_scope.asset_digest,
        current_scope.load_mode,
        current_scope.identity_digest,
    )
    if current_execution_scope != expected_execution_scope:
        return ChannelEmulatorCertificationPreview(
            status="diagnostic",
            **common,
            site_certification=certification,
            site_certification_digest=certification.certification_digest,
            reasons=("site_certification_scope_mismatch",),
            detail="现场认证与当前计划、资产或硬件身份不一致，正式 KPI 保持 UNKNOWN/N/A",
        )
    return ChannelEmulatorCertificationPreview(
        status="formal_ready",
        **common,
        site_certification=certification,
        site_certification_digest=certification.certification_digest,
        reasons=(),
        detail="当前信道仿真器 binding 已匹配服务器现场认证",
    )


def resolve_channel_emulator_certification_preview_scope(
    db,
    hal,
    test_case,
    binding_preview: Any,
) -> ChannelEmulatorCertificationPreviewScope:
    """Resolve the saved TestCase's exact current plan/asset/live-identity scope.

    This is a read-only preview of the same inputs frozen at execution launch.
    It never consults client claims and the driver identity projector performs
    no transport I/O.
    """

    from app.hal.base_station_compatibility import canonical_payload_digest
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.base_station_adapter_profile import (
        canonicalize_mimo_ota_configuration_payload,
    )
    from app.services.channel_emulator_execution_plan import (
        build_channel_emulator_load_request,
        channel_emulator_for_execution_plan,
        freeze_channel_asset_resolution,
        resolve_live_channel_emulator_execution_plan,
        validate_frozen_channel_emulator_load_request,
    )

    if getattr(binding_preview, "status", None) != "configured":
        raise ValueError("channelEmulator binding is not configured")
    if getattr(binding_preview, "execution_mode", None) != "real":
        raise ValueError("channelEmulator binding is not real")
    if getattr(test_case, "test_type", None) != "MIMO_OTA":
        raise ValueError("channelEmulator certification preview requires MIMO_OTA TestCase")
    if str(getattr(test_case, "lab_profile_id", "")) != str(
        getattr(binding_preview, "lab_profile_id", "")
    ):
        raise ValueError("TestCase LabProfile does not match channelEmulator binding")
    raw_configuration = getattr(test_case, "configuration", None)
    if not isinstance(raw_configuration, dict):
        raise ValueError("TestCase MIMO configuration is missing")
    frozen_configuration = canonicalize_mimo_ota_configuration_payload(
        dict(raw_configuration)
    )
    configuration = MIMOOTAConfiguration.model_validate(frozen_configuration)
    frozen_asset = freeze_channel_asset_resolution(db, configuration)
    load_request = build_channel_emulator_load_request(
        configuration,
        configuration_payload=frozen_configuration,
        frozen_asset=frozen_asset,
    )
    binding_digest = getattr(binding_preview, "binding_digest", None)
    if not isinstance(binding_digest, str) or not binding_digest:
        raise ValueError("channelEmulator binding digest is missing")
    plan = resolve_live_channel_emulator_execution_plan(
        hal,
        engine_mode=load_request["effective_engine_mode"],
        binding_digest=binding_digest,
    )
    if not plan.load_mode_planned:
        raise ValueError("channelEmulator current load mode is not planned")
    request_payload = {
        "schema_version": 1,
        **load_request,
        "plan_digest": plan.digest,
    }
    frozen_request = validate_frozen_channel_emulator_load_request(
        {
            **request_payload,
            "digest": canonical_payload_digest(request_payload),
        }
    )
    driver, _source = channel_emulator_for_execution_plan(hal)
    projector = getattr(driver, "capture_channel_emulator_certification_identity", None)
    if not callable(projector):
        raise ValueError("channelEmulator live identity projector is unavailable")
    identity = projector()
    if not isinstance(identity, ChannelEmulatorCertificationIdentity):
        identity = ChannelEmulatorCertificationIdentity.model_validate(identity)
    if not identity.certification_eligible:
        raise ValueError("channelEmulator live identity/options are incomplete")
    if identity.adapter_id != getattr(binding_preview, "adapter_id", None):
        raise ValueError("channelEmulator live identity adapter does not match binding")
    return ChannelEmulatorCertificationPreviewScope(
        schema_version=1,
        plan_digest=plan.digest,
        asset_digest=(
            frozen_asset["digest"]
            if frozen_asset is not None
            else frozen_request["digest"]
        ),
        load_mode=plan.requested_load_mode,
        identity_digest=identity.digest,
    )


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


def validate_frozen_channel_emulator_execution_qualification(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return "frozen channelEmulator execution qualification is missing or malformed"
    try:
        ChannelEmulatorExecutionQualification.model_validate(raw)
    except (TypeError, ValueError, ValidationError):
        return "frozen channelEmulator execution qualification is invalid"
    return None


def validate_acquired_channel_emulator_certification_identity(
    execution_config: Any,
    acquired_identity: Any,
) -> str | None:
    """Bind a frozen formal qualification to identity observed after acquire.

    F64 Local handoff deliberately clears its live identity cache.  Qualification
    freeze therefore validates only immutable certification scope; the actual
    hardware identity is compared here, after the lease has acquired Remote and
    before the execution body can issue any test operation.
    """

    if not isinstance(execution_config, dict):
        return "frozen channelEmulator execution qualification is missing or malformed"
    raw_qualification = execution_config.get(
        CE_EXECUTION_QUALIFICATION_CONFIG_KEY
    )
    if validate_frozen_channel_emulator_execution_qualification(
        raw_qualification
    ) is not None:
        return "frozen channelEmulator execution qualification is invalid"
    qualification = ChannelEmulatorExecutionQualification.model_validate(
        raw_qualification
    )
    if qualification.classification != "formal":
        return None
    try:
        identity = (
            acquired_identity
            if isinstance(acquired_identity, ChannelEmulatorCertificationIdentity)
            else ChannelEmulatorCertificationIdentity.model_validate(acquired_identity)
        )
    except (TypeError, ValueError, ValidationError):
        return "acquired channelEmulator certification identity is invalid"
    if (
        not identity.certification_eligible
        or identity.adapter_id != qualification.adapter_id
        or identity.digest != qualification.identity_digest
    ):
        return (
            "acquired channelEmulator identity does not match frozen site certification"
        )
    return None


def freeze_channel_emulator_execution_qualification(
    db,
    hal,
    execution,
    test_case,
) -> ChannelEmulatorExecutionQualification:
    """Freeze current CE certification against the already-frozen scope once."""

    from sqlalchemy.orm.attributes import flag_modified

    from app.models.instrument import InstrumentConnection
    from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
    from app.services.channel_emulator_binding import (
        CE_FREEZE_CONFIG_KEY,
        validate_frozen_channel_emulator_binding,
    )
    from app.services.channel_emulator_execution_plan import (
        CHANNEL_ASSET_RESOLUTION_FREEZE_KEY,
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
        validate_frozen_channel_emulator_execution_plan,
        validate_frozen_channel_emulator_load_context,
    )
    from app.services.execution_qualification import (
        EXECUTION_QUALIFICATION_KEY,
        ExecutionQualification,
        validate_frozen_execution_qualification,
    )

    config = execution.config if isinstance(execution.config, dict) else {}
    if CE_EXECUTION_QUALIFICATION_CONFIG_KEY in config:
        existing = config.get(CE_EXECUTION_QUALIFICATION_CONFIG_KEY)
        error = validate_frozen_channel_emulator_execution_qualification(existing)
        if error is not None:
            raise ValueError(error)
        return ChannelEmulatorExecutionQualification.model_validate(existing)
    has_progress = any(
        value not in (None, {}, [])
        for value in (
            getattr(execution, "measurements", None),
            getattr(execution, "test_results", None),
            getattr(execution, "phase_results", None),
            config.get("phase_progress"),
        )
    )
    if has_progress:
        raise ValueError(
            "execution already has hardware/phase progress; channelEmulator "
            "qualification cannot be backfilled"
        )
    raw_base_station_qualification = config.get(EXECUTION_QUALIFICATION_KEY)
    if (
        validate_frozen_execution_qualification(raw_base_station_qualification)
        is not None
    ):
        raise ValueError(
            "baseStation execution qualification must be frozen and valid before "
            "channelEmulator qualification"
        )
    base_station_qualification = ExecutionQualification.model_validate(
        raw_base_station_qualification
    )
    try:
        binding = validate_frozen_channel_emulator_binding(
            config[CE_FREEZE_CONFIG_KEY]
        )
        plan = validate_frozen_channel_emulator_execution_plan(
            config[CE_PLAN_FREEZE_CONFIG_KEY]
        )
        load_request, _configuration = validate_frozen_channel_emulator_load_context(
            config,
            plan,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "channelEmulator binding/plan/asset must be frozen before qualification"
        ) from exc
    if getattr(test_case, "id", None) != getattr(execution, "test_case_id", None):
        raise ValueError("channelEmulator qualification TestCase identity mismatch")
    if (
        getattr(test_case, "lab_profile_id", None) is None
        or str(test_case.lab_profile_id) != binding.get("lab_profile_id")
    ):
        raise ValueError("channelEmulator qualification LabProfile identity mismatch")
    resolved = binding["resolved_binding"]
    connection_id = binding.get("instrument_connection_id")
    certification = None
    if connection_id is not None:
        connection = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.id == connection_id)
            .with_for_update()
            .one_or_none()
        )
        if connection is None:
            raise ValueError("frozen channelEmulator connection no longer exists")
        certification = parse_channel_emulator_site_certification(
            connection.channel_emulator_site_certification
        )
    base_freeze = config.get(FREEZE_CONFIG_KEY)
    asset = (
        base_freeze.get(CHANNEL_ASSET_RESOLUTION_FREEZE_KEY)
        if isinstance(base_freeze, dict)
        else None
    )
    asset_digest = (
        asset.get("digest")
        if isinstance(asset, dict) and isinstance(asset.get("digest"), str)
        else load_request["digest"]
    )
    reasons: list[str] = []
    if base_station_qualification.classification == "diagnostic":
        reasons.append("execution_policy_diagnostic")
    if binding.get("execution_mode") != "real" or resolved.get("status") != "configured":
        reasons.append("channel_emulator_execution_not_real")
    if certification is None or certification.status != "active":
        reasons.append("site_certification_not_active")
    else:
        expected = {
            "lab_profile_id": str(test_case.lab_profile_id),
            "instrument_connection_id": str(connection_id),
            "instrument_model_id": str(binding.get("instrument_model_id")),
            "binding_digest": binding["binding_digest"],
            "adapter_id": plan["adapter_id"],
            "plan_digest": plan["digest"],
            "asset_digest": asset_digest,
            "load_mode": plan["requested_load_mode"],
        }
        if any(getattr(certification, key) != value for key, value in expected.items()):
            reasons.append("site_certification_scope_mismatch")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "classification": "diagnostic" if reasons else "formal",
        "policy_mode": base_station_qualification.policy_mode,
        "diagnostic_actor": (
            base_station_qualification.policy.updated_by
            if base_station_qualification.policy is not None
            and base_station_qualification.policy_mode == "diagnostic"
            else None
        ),
        "diagnostic_reasons": list(base_station_qualification.reasons),
        "base_station_qualification_digest": (
            base_station_qualification.qualification_digest
        ),
        "lab_profile_id": str(test_case.lab_profile_id),
        "instrument_connection_id": (
            str(connection_id) if connection_id is not None else None
        ),
        "instrument_model_id": (
            str(binding.get("instrument_model_id"))
            if binding.get("instrument_model_id") is not None
            else None
        ),
        "binding_digest": binding["binding_digest"],
        "plan_digest": plan["digest"],
        "asset_digest": asset_digest,
        "adapter_id": plan["adapter_id"],
        "load_mode": plan["requested_load_mode"],
        "site_certification": (
            certification.model_dump(mode="json")
            if certification is not None
            else None
        ),
        "site_certification_digest": (
            certification.certification_digest
            if certification is not None
            else None
        ),
        "identity_digest": (
            certification.identity_digest
            if certification is not None
            else None
        ),
        "reasons": reasons,
        "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    payload["qualification_digest"] = _canonical_digest(payload)
    frozen = ChannelEmulatorExecutionQualification.model_validate(payload)
    execution.config = {
        **config,
        CE_EXECUTION_QUALIFICATION_CONFIG_KEY: frozen.model_dump(mode="json"),
    }
    flag_modified(execution, "config")
    db.flush()
    return frozen


def _audit_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be non-blank")
    return normalized


def derive_channel_emulator_site_certification_from_execution(
    execution,
    *,
    connection_id: str,
    current_binding_digest: str,
    current_adapter_id: str,
    certified_by: str,
    reason: str,
    certified_at: datetime | None = None,
) -> ChannelEmulatorSiteCertification:
    """Derive one certification solely from an immutable completed execution.

    Current mutable state is supplied only as the exact scope expected by the
    already-locked caller.  No value is read from a driver or reconstructed
    from a report.
    """

    from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
    from app.services.channel_emulator_binding import (
        CE_FREEZE_CONFIG_KEY,
        validate_frozen_channel_emulator_binding,
    )
    from app.services.channel_emulator_execution_plan import (
        CHANNEL_ASSET_RESOLUTION_FREEZE_KEY,
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
        validate_frozen_channel_emulator_execution_plan,
        validate_frozen_channel_emulator_load_context,
    )
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
        validate_channel_emulator_terminal_evidence,
    )
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        validate_channel_emulator_operation_receipt,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_qualification_alignment_error,
        _channel_emulator_qualification_projection,
        _channel_emulator_terminal_projection,
    )
    from app.services.mimo_ota.path_loss_application import (
        path_loss_application_is_formally_verified,
    )

    actor = _audit_text(certified_by, "certified_by")
    audit_reason = _audit_text(reason, "reason")
    if getattr(execution, "status", None) != "completed":
        raise ValueError("channelEmulator certification requires completed execution")
    if getattr(execution, "executed_by", None) != "commissioning_api":
        raise ValueError(
            "channelEmulator certification requires a commissioning_api execution"
        )
    config = execution.config if isinstance(execution.config, dict) else {}
    try:
        binding = validate_frozen_channel_emulator_binding(
            config[CE_FREEZE_CONFIG_KEY]
        )
        plan = validate_frozen_channel_emulator_execution_plan(
            config[CE_PLAN_FREEZE_CONFIG_KEY]
        )
        load_request, _configuration = validate_frozen_channel_emulator_load_context(
            config,
            plan,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("channelEmulator certification binding/plan/asset proof is invalid") from exc
    resolved = binding["resolved_binding"]
    expected_scope = (
        binding.get("execution_mode") == "real"
        and resolved.get("status") == "configured"
        and binding.get("instrument_connection_id") == str(connection_id)
        and binding.get("binding_digest") == current_binding_digest
        and plan.get("binding_digest") == current_binding_digest
        and plan.get("adapter_id") == current_adapter_id
    )
    if not expected_scope:
        raise ValueError("channelEmulator certification source scope does not match current binding")

    (
        qualification_classification,
        qualification_reasons,
        qualification,
    ) = _channel_emulator_qualification_projection(config)
    qualification_alignment_error = (
        _channel_emulator_qualification_alignment_error(config, qualification)
    )
    commissioning_bootstrap = (
        qualification_classification == "diagnostic"
        and qualification is not None
        and qualification.policy_mode == "formal"
        and not qualification.diagnostic_reasons
        and qualification.reasons == ("site_certification_not_active",)
    )
    if (
        (
            qualification_classification != "formal"
            and not commissioning_bootstrap
        )
        or qualification_alignment_error is not None
    ):
        qualification_detail = qualification_alignment_error or "; ".join(
            qualification_reasons
        )
        raise ValueError(
            "channelEmulator certification execution qualification is invalid"
            + (f": {qualification_detail}" if qualification_detail else "")
        )

    classification, terminal_reason = _channel_emulator_terminal_projection(
        config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )
    if classification is not None:
        raise ValueError(
            "channelEmulator certification terminal/receipt proof is invalid: "
            + (terminal_reason or classification)
        )
    raw_terminals = config.get(CE_TERMINAL_EVIDENCE_CONFIG_KEY)
    if not isinstance(raw_terminals, list) or not raw_terminals:
        raise ValueError("channelEmulator certification requires terminal v3 proof")
    terminals = [
        validate_channel_emulator_terminal_evidence(dict(item))
        for item in raw_terminals
    ]
    effective_terminals: list[dict[str, Any]] = []
    latest_by_scope: dict[str, dict[str, Any]] = {}
    for item in terminals:
        operation_scope = item.get("operation_scope")
        if isinstance(operation_scope, str):
            latest_by_scope[operation_scope] = item
        else:
            effective_terminals.append(item)
    effective_terminals.extend(latest_by_scope.values())
    if any(item.get("schema_version") != 3 for item in effective_terminals):
        raise ValueError("channelEmulator certification requires terminal v3 proof")
    identities = [
        ChannelEmulatorCertificationIdentity.model_validate(item.get("hardware_identity"))
        for item in effective_terminals
    ]
    identity = identities[0]
    if (
        not identity.certification_eligible
        or any(item != identity for item in identities[1:])
        or any(identity.instrument_id != item.get("instrument_id") for item in effective_terminals)
        or identity.adapter_id != current_adapter_id
    ):
        raise ValueError("channelEmulator certification hardware identity/options proof is invalid")

    raw_receipts = config.get(CE_OPERATION_RECEIPTS_CONFIG_KEY)
    if not isinstance(raw_receipts, list) or not raw_receipts:
        raise ValueError("channelEmulator certification operation receipt proof is missing")
    receipts = [
        validate_channel_emulator_operation_receipt(dict(item))
        for item in raw_receipts
    ]
    attempt_evidence = config.get("base_station_execution_evidence")
    current_attempt_id = (
        attempt_evidence.get("current_measurement_attempt_id")
        if isinstance(attempt_evidence, dict)
        and attempt_evidence.get("current_measurement_attempt_state") == "completed"
        else None
    )
    if not isinstance(current_attempt_id, str) or not current_attempt_id:
        raise ValueError("channelEmulator certification current measurement attempt is missing")
    attempt_terminals = [
        item
        for item in effective_terminals
        if item.get("measurement_attempt_id") == current_attempt_id
    ]
    if not attempt_terminals:
        raise ValueError("channelEmulator certification terminal does not bind current attempt")
    referenced_receipt_ids = {
        receipt_id
        for item in attempt_terminals
        for receipt_id in item.get("operation_receipt_ids", ())
    }
    attempt_receipts = [
        item
        for item in receipts
        if item.get("receipt_id") in referenced_receipt_ids
        and item.get("measurement_attempt_id") == current_attempt_id
        and item.get("instrument_id") == identity.instrument_id
        and item.get("execution_id") == str(execution.id)
        and item.get("simulated") is False
    ]

    def _has_confirmed(operation: str, field: str) -> bool:
        return any(
            receipt.get("operation") == operation
            and receipt.get("terminal_state") == "completed"
            and receipt.get("operation_succeeded") is True
            and any(
                item.get("field") == field and item.get("status") == "confirmed"
                for item in receipt.get("fields", ())
            )
            for receipt in attempt_receipts
        )

    if not _has_confirmed("set_output_level_dbm", "level_dbm"):
        raise ValueError("channelEmulator certification level proof is missing")
    if not _has_confirmed("set_output_gain", "gain_db"):
        raise ValueError("channelEmulator certification path-loss receipt proof is missing")

    measurements = execution.measurements if isinstance(execution.measurements, dict) else {}
    phases = measurements.get("phases")
    measure = phases.get("measure") if isinstance(phases, dict) else None
    if not isinstance(measure, dict):
        raise ValueError("channelEmulator certification measurement proof is missing")
    frequency = measure.get("frequency_consistency")
    per_instrument = (
        frequency.get("per_instrument") if isinstance(frequency, dict) else None
    )
    f64_frequency_proven = (
        current_adapter_id == "propsim_f64"
        and isinstance(per_instrument, dict)
        and isinstance(per_instrument.get("F64"), str)
        and per_instrument.get("F64") != "未报告(跳过)"
        and isinstance(frequency.get("f64_center_readback_mhz"), (int, float))
        and frequency.get("f64_bandwidth_source")
        == "channel_asset_or_scd_declared"
        and "F64" not in (frequency.get("unverified") or ())
    )
    if (
        not isinstance(frequency, dict)
        or frequency.get("fully_verified") is not True
        or not f64_frequency_proven
    ):
        raise ValueError("channelEmulator certification frequency proof is incomplete")
    if (
        measure.get("path_loss_verified") is not True
        or not path_loss_application_is_formally_verified(
            measure.get("path_loss_application")
        )
    ):
        raise ValueError("channelEmulator certification path-loss proof is not formally verified")

    base_freeze = config.get(FREEZE_CONFIG_KEY)
    asset = (
        base_freeze.get(CHANNEL_ASSET_RESOLUTION_FREEZE_KEY)
        if isinstance(base_freeze, dict)
        else None
    )
    asset_digest = (
        asset.get("digest")
        if isinstance(asset, dict) and isinstance(asset.get("digest"), str)
        else load_request.get("digest")
    )
    if not isinstance(asset_digest, str):
        raise ValueError("channelEmulator certification asset digest is missing")
    terminal_evidence_digest = _canonical_digest(
        {
            "schema_version": 1,
            "terminal_digests": [item["digest"] for item in effective_terminals],
        }
    )
    operation_receipts_digest = _canonical_digest(
        {
            "schema_version": 1,
            "receipt_chain_digests": [
                item["operation_receipts_digest"] for item in effective_terminals
            ],
        }
    )
    measurement_evidence_digest = _canonical_digest(measure)
    return ChannelEmulatorSiteCertification(
        schema_version=1,
        status="active",
        lab_profile_id=binding["lab_profile_id"],
        instrument_connection_id=binding["instrument_connection_id"],
        instrument_model_id=binding["instrument_model_id"],
        binding_digest=binding["binding_digest"],
        adapter_id=plan["adapter_id"],
        plan_digest=plan["digest"],
        asset_digest=asset_digest,
        load_mode=plan["requested_load_mode"],
        model=identity.model,
        firmware_version=identity.firmware_version,
        serial_number=identity.serial_number,
        options=identity.options,
        identity_digest=identity.digest,
        source_execution_id=str(execution.id),
        terminal_evidence_digest=terminal_evidence_digest,
        operation_receipts_digest=operation_receipts_digest,
        measurement_evidence_digest=measurement_evidence_digest,
        required_proofs=ChannelEmulatorCertificationProofs(
            binding_plan_asset=True,
            hardware_identity_options=True,
            operation_receipts=True,
            frequency=True,
            level=True,
            path_loss=True,
            safe_idle=True,
            transport_release=True,
        ),
        certified_by=actor,
        certified_at=certified_at or datetime.now(timezone.utc),
        reason=audit_reason,
    )


def revoke_channel_emulator_site_certification(
    db,
    *,
    connection_id,
    revoked_by: str,
    reason: str,
) -> ChannelEmulatorSiteCertification:
    """Revoke the current certification while preserving its source evidence."""

    from app.models.instrument import InstrumentConnection

    try:
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
        current = parse_channel_emulator_site_certification(
            connection.channel_emulator_site_certification
        )
        if current is None or current.status != "active":
            raise ValueError("active Channel Emulator site certification is missing")
        revoked = ChannelEmulatorSiteCertification.model_validate(
            current.model_copy(
                update={
                    "status": "revoked",
                    "revoked_by": actor,
                    "revoked_at": datetime.now(timezone.utc),
                    "revocation_reason": audit_reason,
                }
            )
        )
        connection.channel_emulator_site_certification = revoked.model_dump(
            mode="json"
        )
        db.commit()
        db.refresh(connection)
        return revoked
    except BaseException:
        db.rollback()
        raise


def activate_channel_emulator_site_certification(
    db,
    hal,
    *,
    connection_id,
    source_execution_id,
    certified_by: str,
    reason: str,
) -> ChannelEmulatorSiteCertification:
    """Activate from one completed execution under the repository lock order."""

    from app.models.instrument import InstrumentConnection
    from app.models.lab_profile import LabProfile
    from app.models.test_plan import TestCase, TestExecution
    from app.services.channel_emulator_binding import (
        resolve_channel_emulator_binding,
    )

    try:
        # Read-only existence preflight avoids taking the connection lock before
        # the source execution.  The resolver later owns category→lab→connection.
        requested_connection_id = (
            db.query(InstrumentConnection.id)
            .filter(InstrumentConnection.id == connection_id)
            .scalar()
        )
        if requested_connection_id is None:
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
            raise ValueError(
                "channelEmulator certification requires a completed TestCase execution"
            )
        test_case = (
            db.query(TestCase)
            .filter(TestCase.id == execution.test_case_id)
            .one_or_none()
        )
        if test_case is None or test_case.lab_profile_id is None:
            raise ValueError("source execution has no bound LabProfile")
        lab = (
            db.query(LabProfile)
            .filter(LabProfile.id == test_case.lab_profile_id)
            .one_or_none()
        )
        if lab is None:
            raise ValueError("source execution LabProfile is missing")
        resolved = resolve_channel_emulator_binding(db, hal, lab, lock=True)
        if (
            resolved.execution_mode != "real"
            or resolved.manifest is None
            or resolved.instrument_connection_id != str(requested_connection_id)
            or resolved.instrument_model_id is None
        ):
            raise ValueError(
                "channelEmulator certification requires current real binding"
            )
        # The resolver already locked the exact row after category and lab.
        connection = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.id == requested_connection_id)
            .one()
        )
        certification = derive_channel_emulator_site_certification_from_execution(
            execution,
            connection_id=str(connection.id),
            current_binding_digest=resolved.binding_digest,
            current_adapter_id=resolved.manifest.adapter_id,
            certified_by=certified_by,
            reason=reason,
        )
        if certification.instrument_model_id != str(resolved.instrument_model_id):
            raise ValueError(
                "channelEmulator certification source model does not match current binding"
            )
        connection.channel_emulator_site_certification = certification.model_dump(
            mode="json"
        )
        db.commit()
        db.refresh(connection)
        return certification
    except BaseException:
        db.rollback()
        raise
