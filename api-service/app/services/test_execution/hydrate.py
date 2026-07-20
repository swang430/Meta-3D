"""StepExecutionContext 水合 — commissioning run-all 与 test_plan_runner 共用。

从 TestCase 的 FK (lab_profile_id / calibration_certificate_id) 拉出
LabProfile + 证书, 组装 executor 需要的上下文。原为 api/commissioning.py
私有函数 `_build_context`, 开关 3 (计划 runner) 提升到服务层两处共用。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.calibration import CalibrationCertificate
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.services.test_execution.context import (
    StepDescriptor,
    StepExecutionContext,
)


def build_step_context(
    db: Session,
    execution: TestExecution,
    test_case: TestCase,
    step: StepDescriptor,
) -> StepExecutionContext:
    """Hydrate a StepExecutionContext: pull LabProfile + cert from FKs."""
    lab_profile = None
    if test_case.lab_profile_id is not None:
        lab_profile = (
            db.query(LabProfile)
            .filter(LabProfile.id == test_case.lab_profile_id)
            .first()
        )
    cert = None
    cert_id = test_case.calibration_certificate_id or (
        lab_profile.active_calibration_certificate_id if lab_profile else None
    )
    if cert_id is not None:
        cert = (
            db.query(CalibrationCertificate)
            .filter(CalibrationCertificate.id == cert_id)
            .first()
        )
    return StepExecutionContext(
        db=db,
        step=step,
        test_execution=execution,
        lab_profile=lab_profile,
        calibration_certificate=cert,
        parameters=dict(step.parameters or {}),
    )
