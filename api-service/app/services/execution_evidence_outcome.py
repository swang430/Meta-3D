"""Execution-scoped evidence compatibility and completion semantics.

The projection in this module is deliberately pure: it reads immutable
evidence snapshots plus the execution row's authoritative lifecycle status.
It never consults the current adapter registry, LabProfile, connection, or
site certification.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError

from app.hal.base_station_compatibility import (
    BaseStationCompatibilityVerdict,
    BaseStationExecutionRequirements,
    canonical_payload_digest,
    manifest_compatibility_digest,
)
from app.hal.base_station_manifest import BaseStationAdapterManifest
from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    ExecutionQualification,
    validate_frozen_execution_qualification,
)


CompatibilityClassification = Literal[
    "compatible", "diagnostic", "legacy", "invalid"
]
CompletionSemantic = Literal[
    "valid_test_completed",
    "diagnostic_completed",
    "pipeline_completed",
    "not_completed",
]
QualificationClassification = Literal["formal", "diagnostic", "legacy"]


class ExecutionEvidenceOutcome(BaseModel):
    """Single server-owned projection for history, reports, and formal gates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    compatibility_classification: CompatibilityClassification
    completion_semantic: CompletionSemantic
    formal_eligible: bool
    compatibility_digest: str | None
    qualification_classification: QualificationClassification
    reasons: tuple[str, ...]
    pipeline_status: str


def _outer_freeze_digest_error(frozen: Mapping[str, Any]) -> str | None:
    digest = frozen.get("digest")
    if not isinstance(digest, str):
        return "frozen baseStation adapter profile digest is missing"
    payload = {key: value for key, value in frozen.items() if key != "digest"}
    if digest != canonical_payload_digest(payload):
        return "frozen baseStation adapter profile digest mismatch"
    return None


def _compatibility_snapshot_error(frozen: Mapping[str, Any]) -> str | None:
    compatibility = frozen.get("compatibility")
    if not isinstance(compatibility, Mapping):
        return "frozen compatibility payload is malformed"
    try:
        requirements = BaseStationExecutionRequirements.model_validate(
            compatibility.get("requirements")
        )
        verdict = BaseStationCompatibilityVerdict.model_validate(
            compatibility.get("verdict")
        )
    except (ValidationError, ValueError, TypeError):
        return "frozen compatibility payload does not parse"
    if requirements.digest != verdict.requirements_digest:
        return "frozen compatibility requirements digest drifted"
    if verdict.status == "incompatible" or verdict.compatible is not True:
        return "frozen compatibility verdict is incompatible"

    resolution = frozen.get("resolution")
    if not isinstance(resolution, Mapping):
        return "frozen adapter resolution is missing"
    if verdict.status == "no_adapter":
        if (
            resolution.get("status") != "diagnostic_unbound"
            or resolution.get("execution_mode") != "simulated"
            or resolution.get("adapter") is not None
        ):
            return (
                "frozen no_adapter verdict does not match simulated "
                "diagnostic_unbound resolution"
            )
    elif verdict.status != "compatible":
        return "frozen compatibility verdict status is invalid"
    elif resolution.get("status") not in {"configured", "not_applicable"}:
        return "frozen compatible verdict does not match binding status"
    adapter = resolution.get("adapter")
    if verdict.status == "compatible" and (
        not isinstance(adapter, str) or not adapter.strip()
    ):
        return "frozen compatible verdict is missing adapter identity"
    if resolution.get("execution_mode") not in {"real", "simulated"}:
        return "frozen compatible verdict has invalid execution mode"

    resolved_binding = frozen.get("resolved_binding")
    if not isinstance(resolved_binding, Mapping):
        return "frozen resolved binding is missing"
    if resolved_binding.get("binding_digest") != frozen.get("binding_digest"):
        return "frozen resolved binding digest does not match adapter freeze"
    if resolved_binding.get("status") != resolution.get("status"):
        return "frozen resolved binding status does not match adapter resolution"
    raw_manifest = resolved_binding.get("manifest")
    if verdict.status == "no_adapter":
        if raw_manifest is not None:
            return "frozen no_adapter verdict unexpectedly includes a manifest"
        return None
    try:
        manifest = BaseStationAdapterManifest.model_validate(raw_manifest)
    except (ValidationError, ValueError, TypeError):
        return "frozen resolved binding manifest does not parse"
    if manifest.adapter_id != adapter:
        return "frozen resolved binding manifest does not match adapter resolution"
    if manifest_compatibility_digest(manifest) != verdict.manifest_digest:
        return "frozen compatibility manifest does not match resolved binding"
    return None


def validate_frozen_compatibility_snapshot(frozen: Any) -> str | None:
    """Validate an explicit P1-75 freeze without consulting mutable state.

    ``None`` and snapshots created before the compatibility field existed are
    legacy and intentionally accepted here.  Once ``compatibility`` exists,
    malformed or tampered evidence fails closed.
    """

    if frozen is None:
        return None
    if not isinstance(frozen, Mapping):
        return "frozen baseStation adapter profile is malformed"
    if "compatibility" not in frozen:
        return None
    return _outer_freeze_digest_error(frozen) or _compatibility_snapshot_error(
        frozen
    )


def _qualification_projection(
    config: Mapping[str, Any],
) -> tuple[
    QualificationClassification,
    tuple[str, ...],
    ExecutionQualification | None,
]:
    if EXECUTION_QUALIFICATION_KEY not in config:
        return "legacy", (), None
    raw = config.get(EXECUTION_QUALIFICATION_KEY)
    error = validate_frozen_execution_qualification(raw)
    if error is not None:
        return "diagnostic", (error,), None
    qualification = ExecutionQualification.model_validate(raw)
    return qualification.classification, (), qualification


def _qualification_freeze_alignment_error(
    frozen: Mapping[str, Any],
    qualification: ExecutionQualification | None,
) -> str | None:
    if qualification is None:
        return None
    resolution = frozen.get("resolution")
    if not isinstance(resolution, Mapping):
        return "frozen qualification has no adapter resolution"
    expected = (
        frozen.get("binding_digest"),
        resolution.get("status"),
        resolution.get("execution_mode"),
        resolution.get("adapter"),
    )
    actual = (
        qualification.binding_digest,
        qualification.binding_status,
        qualification.execution_mode,
        qualification.adapter_id,
    )
    if actual != expected:
        return "frozen qualification does not match adapter binding"
    if qualification.classification == "formal" and (
        qualification.policy_mode != "formal"
        or qualification.execution_mode != "real"
        or qualification.binding_status != "configured"
        or qualification.adapter_id is None
    ):
        return "formal qualification does not describe a real configured adapter"
    return None


def project_execution_evidence_outcome(execution: Any) -> ExecutionEvidenceOutcome:
    """Project frozen evidence plus current lifecycle into shared semantics."""

    config = getattr(execution, "config", None)
    config = config if isinstance(config, Mapping) else {}
    pipeline_status = str(getattr(execution, "status", "unknown"))
    frozen = config.get(FREEZE_CONFIG_KEY)
    (
        qualification,
        qualification_reasons,
        qualification_snapshot,
    ) = _qualification_projection(config)

    reasons: list[str] = list(qualification_reasons)
    compatibility_digest: str | None = None
    if frozen is None or (
        isinstance(frozen, Mapping) and "compatibility" not in frozen
    ):
        classification: CompatibilityClassification = (
            "diagnostic" if qualification == "diagnostic" else "legacy"
        )
        reasons.append("execution has no frozen compatibility snapshot")
    else:
        error = validate_frozen_compatibility_snapshot(frozen)
        if error is not None:
            classification = "invalid"
            reasons.append(error)
        else:
            assert isinstance(frozen, Mapping)
            compatibility = frozen["compatibility"]
            assert isinstance(compatibility, Mapping)
            compatibility_digest = canonical_payload_digest(compatibility)
            verdict = BaseStationCompatibilityVerdict.model_validate(
                compatibility.get("verdict")
            )
            alignment_error = _qualification_freeze_alignment_error(
                frozen,
                qualification_snapshot,
            )
            if alignment_error is not None:
                classification = "invalid"
                reasons.append(alignment_error)
            elif verdict.status == "no_adapter" or qualification == "diagnostic":
                classification = "diagnostic"
            else:
                classification = "compatible"

    formal_eligible = (
        pipeline_status == "completed"
        and classification == "compatible"
        and qualification == "formal"
    )
    if pipeline_status != "completed":
        completion: CompletionSemantic = "not_completed"
    elif formal_eligible:
        completion = "valid_test_completed"
    elif classification == "diagnostic":
        completion = "diagnostic_completed"
    else:
        completion = "pipeline_completed"

    return ExecutionEvidenceOutcome(
        compatibility_classification=classification,
        completion_semantic=completion,
        formal_eligible=formal_eligible,
        compatibility_digest=compatibility_digest,
        qualification_classification=qualification,
        reasons=tuple(dict.fromkeys(reasons)),
        pipeline_status=pipeline_status,
    )


def execution_evidence_blocks_formal_outputs(execution: Any) -> bool:
    """Return whether this execution must be excluded from every formal output.

    Legacy rows intentionally retain the pre-P1-75 provenance rules.  Explicit
    diagnostic or invalid evidence is fail-closed everywhere.
    """

    return project_execution_evidence_outcome(
        execution
    ).compatibility_classification in {"diagnostic", "invalid"}
