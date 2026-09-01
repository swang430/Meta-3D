"""Execution-scoped evidence compatibility and completion semantics.

The projection in this module is deliberately pure: it reads only immutable
snapshots already stored on one execution.  It never consults the current
adapter registry, LabProfile, connection, or site certification.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError

from app.hal.base_station_compatibility import (
    BaseStationCompatibilityVerdict,
    BaseStationExecutionRequirements,
    canonical_payload_digest,
)
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
        return None

    if verdict.status != "compatible":
        return "frozen compatibility verdict status is invalid"
    if resolution.get("status") not in {"configured", "not_applicable"}:
        return "frozen compatible verdict does not match binding status"
    adapter = resolution.get("adapter")
    if not isinstance(adapter, str) or not adapter.strip():
        return "frozen compatible verdict is missing adapter identity"
    if resolution.get("execution_mode") not in {"real", "simulated"}:
        return "frozen compatible verdict has invalid execution mode"
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
) -> tuple[QualificationClassification, tuple[str, ...]]:
    if EXECUTION_QUALIFICATION_KEY not in config:
        return "legacy", ()
    raw = config.get(EXECUTION_QUALIFICATION_KEY)
    error = validate_frozen_execution_qualification(raw)
    if error is not None:
        return "diagnostic", (error,)
    qualification = ExecutionQualification.model_validate(raw)
    return qualification.classification, ()


def project_execution_evidence_outcome(execution: Any) -> ExecutionEvidenceOutcome:
    """Project one execution's immutable evidence into display/gating semantics."""

    config = getattr(execution, "config", None)
    config = config if isinstance(config, Mapping) else {}
    pipeline_status = str(getattr(execution, "status", "unknown"))
    frozen = config.get(FREEZE_CONFIG_KEY)
    qualification, qualification_reasons = _qualification_projection(config)

    reasons: list[str] = list(qualification_reasons)
    compatibility_digest: str | None = None
    if frozen is None or (
        isinstance(frozen, Mapping) and "compatibility" not in frozen
    ):
        classification: CompatibilityClassification = "legacy"
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
            if verdict.status == "no_adapter" or qualification == "diagnostic":
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
