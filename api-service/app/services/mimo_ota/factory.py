"""Build a MIMO_OTA TestCase + its 5-phase step descriptor sequence.

`build_mimo_ota_test_case` is the canonical entrypoint replacing the legacy
`CommissioningService.create_session`. It:

1. Resolves the LabProfile (caller passes id, or we look up the active default).
2. Merges Pydantic defaults + caller overrides into a MIMOOTAConfiguration.
3. Persists a TestCase row with test_type='MIMO_OTA' bound to the LabProfile
   and (optionally) a specific calibration certificate.
4. Returns the TestCase + an in-memory list of 5 StepDescriptors that the
   dispatcher will iterate through. Step descriptors do NOT land in the
   `test_steps` table — they are an internal split of one TestCase, not
   independently reusable units.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestCaseType
from app.schemas.mimo_ota.config import (
    MIMO_OTA_DEFAULT_STEPS,
    MIMO_OTA_TEST_TYPE,
    MIMOOTAConfiguration,
)
from app.services.test_execution import StepDescriptor


def _resolve_lab_profile(
    db: Session, lab_profile_id: Optional[UUID]
) -> LabProfile:
    """Look up the requested LabProfile, or the unique active one as fallback."""
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
            "No active LabProfile in DB. Run scripts/seed_caict_lab_profile.py "
            "to create one before building a MIMO_OTA TestCase."
        )
    if len(active) > 1:
        names = ", ".join(p.name for p in active)
        raise ValueError(
            f"Multiple active LabProfiles found ({names}); pass an explicit "
            "lab_profile_id to disambiguate."
        )
    return active[0]


def _build_step_descriptors(
    config: MIMOOTAConfiguration,
) -> List[StepDescriptor]:
    """Generate the 5 step descriptors. Each step gets a small parameter dict
    pulled from the configuration; the executor reads context.parameters at
    run time (and may also read context.test_execution.measurements for
    cross-step state from earlier phases).
    """
    overrides: Dict[str, Dict[str, Any]] = config.step_overrides or {}
    descriptors: List[StepDescriptor] = []
    for idx, step_type in enumerate(MIMO_OTA_DEFAULT_STEPS):
        params: Dict[str, Any] = {"phase_index": idx}
        # Merge in user-supplied per-step overrides if present
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


def build_mimo_ota_test_case(
    db: Session,
    *,
    name: str,
    description: Optional[str] = None,
    lab_profile_id: Optional[UUID] = None,
    calibration_certificate_id: Optional[UUID] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
    created_by: str = "mimo_ota_factory",
    is_template: bool = False,
    template_category: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Tuple[TestCase, List[StepDescriptor]]:
    """Persist a MIMO_OTA TestCase + return it together with its 5 step descriptors.

    The TestCase row is created and committed. The step descriptors are
    in-memory objects the caller passes through dispatch_step one by one.
    """
    profile = _resolve_lab_profile(db, lab_profile_id)

    # Resolve calibration cert: explicit > LabProfile.active > None
    cert_id = calibration_certificate_id or profile.active_calibration_certificate_id

    # Build & validate the MIMOOTAConfiguration with user overrides applied
    overrides = config_overrides or {}
    config = MIMOOTAConfiguration.model_validate(overrides)

    # Derive convenience columns from the validated config
    test_case = TestCase(
        name=name,
        description=description,
        test_type=TestCaseType.MIMO_OTA.value,
        configuration=config.model_dump(mode="json"),
        pass_criteria=config.pass_criteria.model_dump(mode="json"),
        channel_model=config.cdl_model_name,
        frequency_mhz=config.frequency_hz / 1e6,
        bandwidth_mhz=config.bandwidth_mhz,
        tx_power_dbm=config.target_tx_power_dbm,
        test_duration_sec=(
            (config.measurement_duration_s + config.settling_time_s)
            * len(config.azimuths_deg)
        ),
        is_template=is_template,
        template_category=template_category or "MIMO OTA 吞吐量",
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
