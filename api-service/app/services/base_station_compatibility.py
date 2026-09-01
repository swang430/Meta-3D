"""Read-only TestCase × BaseStation binding compatibility projection.

This service is deliberately separate from binding resolution: compatibility
depends on a saved TestCase, while the binding digest remains the identity of
the persisted LabProfile/model/connection truth alone.  No function in this
module performs instrument I/O.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.hal.base_station_compatibility import (
    BaseStationCompatibilityVerdict,
    BaseStationExecutionRequirements,
    build_compatibility_payload,
    build_measure_execution_requirements_from_configuration,
)
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase
from app.services.base_station_binding import (
    BaseStationBindingPreview,
    ResolvedBaseStationBinding,
    resolve_base_station_binding,
)


class BaseStationCompatibilityPreview(BaseModel):
    """One explicit compatibility result for preview/readiness consumers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    status: Literal[
        "compatible",
        "incompatible",
        "no_adapter",
        "not_evaluated",
        "invalid",
    ]
    compatible: bool | None
    test_case_id: str | None
    lab_profile_id: str | None
    binding_digest: str | None
    execution_mode: Literal["real", "simulated"] | None
    requirements: BaseStationExecutionRequirements | None
    verdict: BaseStationCompatibilityVerdict | None
    reasons: tuple[str, ...]
    detail: str


def build_not_evaluated_base_station_compatibility(
    *,
    lab_profile_id: object | None,
    reason: str = "No saved TestCase context was supplied for compatibility evaluation",
) -> BaseStationCompatibilityPreview:
    """Return an explicit non-ready result instead of implying compatibility."""

    return BaseStationCompatibilityPreview(
        status="not_evaluated",
        compatible=None,
        test_case_id=None,
        lab_profile_id=(
            str(lab_profile_id) if lab_profile_id is not None else None
        ),
        binding_digest=None,
        execution_mode=None,
        requirements=None,
        verdict=None,
        reasons=(reason,),
        detail=reason,
    )


def _invalid_preview(
    *,
    test_case_id: object | None,
    lab_profile_id: object | None,
    reason: str,
) -> BaseStationCompatibilityPreview:
    return BaseStationCompatibilityPreview(
        status="invalid",
        compatible=False,
        test_case_id=(str(test_case_id) if test_case_id is not None else None),
        lab_profile_id=(
            str(lab_profile_id) if lab_profile_id is not None else None
        ),
        binding_digest=None,
        execution_mode=None,
        requirements=None,
        verdict=None,
        reasons=(reason,),
        detail=reason,
    )


def project_resolved_base_station_compatibility(
    *,
    test_case: TestCase,
    resolved: ResolvedBaseStationBinding,
) -> BaseStationCompatibilityPreview:
    """Project saved TestCase requirements against one resolved binding."""

    requirements = build_measure_execution_requirements_from_configuration(
        test_case.configuration
    )
    payload = build_compatibility_payload(requirements, resolved.manifest)
    verdict = BaseStationCompatibilityVerdict.model_validate(payload["verdict"])
    return BaseStationCompatibilityPreview(
        status=verdict.status,
        compatible=verdict.compatible,
        test_case_id=str(test_case.id),
        lab_profile_id=str(resolved.lab_profile_id),
        binding_digest=resolved.binding_digest,
        execution_mode=resolved.execution_mode,
        requirements=requirements,
        verdict=verdict,
        reasons=verdict.reasons,
        detail=(
            "Saved TestCase requirements are compatible with the resolved "
            "BaseStation adapter"
            if verdict.status == "compatible"
            else (
                "No registered BaseStation adapter is bound; compatibility is "
                "diagnostic only"
                if verdict.status == "no_adapter"
                else "; ".join(verdict.reasons)
            )
        ),
    )


def build_base_station_compatibility_preview(
    db,
    hal,
    selected_lab_profile: LabProfile,
    *,
    test_case_id: object | None,
) -> BaseStationCompatibilityPreview:
    """Resolve server truth and evaluate one saved TestCase without hardware I/O."""

    _, compatibility = build_base_station_preview_bundle(
        db,
        hal,
        selected_lab_profile,
        test_case_id=test_case_id,
    )
    return compatibility


def build_compatibility_preview_for_resolved(
    db,
    selected_lab_profile: LabProfile,
    *,
    test_case_id: object | None,
    resolved: ResolvedBaseStationBinding,
) -> BaseStationCompatibilityPreview:
    """Evaluate saved TestCase truth against an already resolved binding."""

    if test_case_id is None:
        return build_not_evaluated_base_station_compatibility(
            lab_profile_id=selected_lab_profile.id
        )
    test_case = (
        db.query(TestCase).filter(TestCase.id == test_case_id).one_or_none()
    )
    if test_case is None:
        return _invalid_preview(
            test_case_id=test_case_id,
            lab_profile_id=selected_lab_profile.id,
            reason="Saved TestCase does not exist",
        )
    if test_case.test_type != "MIMO_OTA":
        return _invalid_preview(
            test_case_id=test_case.id,
            lab_profile_id=selected_lab_profile.id,
            reason="Saved TestCase is not a MIMO_OTA TestCase",
        )
    if test_case.lab_profile_id != selected_lab_profile.id:
        return _invalid_preview(
            test_case_id=test_case.id,
            lab_profile_id=selected_lab_profile.id,
            reason="Saved TestCase does not target the selected LabProfile",
        )
    try:
        return project_resolved_base_station_compatibility(
            test_case=test_case,
            resolved=resolved,
        )
    except (TypeError, ValueError) as exc:
        return _invalid_preview(
            test_case_id=test_case.id,
            lab_profile_id=selected_lab_profile.id,
            reason=str(exc),
        )


def build_base_station_preview_bundle(
    db,
    hal,
    selected_lab_profile: LabProfile,
    *,
    test_case_id: object | None,
) -> tuple[BaseStationBindingPreview, BaseStationCompatibilityPreview]:
    """Resolve once, then project binding and TestCase compatibility together."""

    try:
        resolved = resolve_base_station_binding(db, hal, selected_lab_profile)
    except ValueError as exc:
        detail = str(exc)
        return (
            BaseStationBindingPreview.invalid(selected_lab_profile.id, detail),
            _invalid_preview(
                test_case_id=test_case_id,
                lab_profile_id=selected_lab_profile.id,
                reason=detail,
            ),
        )
    return (
        BaseStationBindingPreview.from_resolved(resolved),
        build_compatibility_preview_for_resolved(
            db,
            selected_lab_profile,
            test_case_id=test_case_id,
            resolved=resolved,
        ),
    )
