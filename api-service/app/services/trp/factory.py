"""Build a TRP TestCase + 5-phase step descriptor sequence.

Mirrors `mimo_ota.factory.build_mimo_ota_test_case` to validate the pattern
generalizes. Differences:
  - TestCaseType.TRP instead of MIMO_OTA
  - TRPConfiguration / TRP_DEFAULT_STEPS imports
  - test_duration estimate uses spatial_grid.total_points() instead of
    azimuths_deg
  - tx_power_dbm column gets dut_tx_power_target_dbm (registered deviation)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestCaseType
from app.schemas.trp.config import (
    TRP_DEFAULT_STEPS,
    TRP_TEST_TYPE,
    TRPConfiguration,
)
from app.services.test_execution import StepDescriptor


def _resolve_lab_profile(
    db: Session, lab_profile_id: Optional[UUID]
) -> LabProfile:
    """Same as mimo_ota.factory; copied rather than abstracted (rule of three
    not yet triggered — 2 callers, not 3)."""
    if lab_profile_id is not None:
        profile = db.query(LabProfile).filter(LabProfile.id == lab_profile_id).first()
        if not profile:
            raise ValueError(f"LabProfile {lab_profile_id} not found")
        if not profile.is_active:
            raise ValueError(f"LabProfile {lab_profile_id} is inactive")
        return profile

    active = db.query(LabProfile).filter(LabProfile.is_active.is_(True)).all()
    if not active:
        raise ValueError(
            "No active LabProfile in DB. Run scripts/seed_caict_lab_profile.py"
        )
    if len(active) > 1:
        names = ", ".join(p.name for p in active)
        raise ValueError(
            f"Multiple active LabProfiles found ({names}); pass an explicit "
            "lab_profile_id to disambiguate."
        )
    return active[0]


def _build_step_descriptors(
    config: TRPConfiguration,
) -> List[StepDescriptor]:
    overrides: Dict[str, Dict[str, Any]] = config.step_overrides or {}
    descriptors: List[StepDescriptor] = []
    for idx, step_type in enumerate(TRP_DEFAULT_STEPS):
        params: Dict[str, Any] = {"phase_index": idx}
        if step_type.value in overrides:
            params.update(overrides[step_type.value])
        descriptors.append(
            StepDescriptor(
                id=f"{step_type.value}-{idx}",
                type=step_type.value,
                parameters=params,
            )
        )
    return descriptors


def build_trp_test_case(
    db: Session,
    *,
    name: str,
    description: Optional[str] = None,
    lab_profile_id: Optional[UUID] = None,
    calibration_certificate_id: Optional[UUID] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
    created_by: str = "trp_factory",
    is_template: bool = False,
    template_category: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Tuple[TestCase, List[StepDescriptor]]:
    profile = _resolve_lab_profile(db, lab_profile_id)
    cert_id = calibration_certificate_id or profile.active_calibration_certificate_id

    overrides = config_overrides or {}
    config = TRPConfiguration.model_validate(overrides)

    # Estimate duration: settling + measurement per spatial position
    n_points = config.spatial_grid.total_points()
    per_point_s = config.settling_time_s + (config.num_samples_per_position * 0.05)

    test_case = TestCase(
        name=name,
        description=description,
        test_type=TestCaseType.TRP.value,
        configuration=config.model_dump(mode="json"),
        pass_criteria=config.pass_criteria.model_dump(mode="json"),
        # TRP 不走 cdl_model_name; channel_model 留 None
        frequency_mhz=config.frequency_hz / 1e6,
        bandwidth_mhz=config.bandwidth_mhz,
        # REGISTERED DEVIATION: DUT-side transmit power
        # (vs MIMO_OTA where this column is BS-side target_tx_power_dbm)
        tx_power_dbm=config.dut_tx_power_target_dbm,
        test_duration_sec=n_points * per_point_s,
        is_template=is_template,
        template_category=template_category or "TRP 整机辐射功率",
        created_by=created_by,
        tags=tags,
        lab_profile_id=profile.id,
        calibration_certificate_id=cert_id,
    )
    db.add(test_case)
    db.commit()
    db.refresh(test_case)

    descriptors = _build_step_descriptors(config)
    return test_case, descriptors
