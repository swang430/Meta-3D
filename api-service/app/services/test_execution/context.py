"""StepExecutionContext — what every executor receives at run time."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models.lab_profile import LabProfile
    from app.models.calibration import CalibrationCertificate
    from app.models.test_plan import TestStep, TestExecution


@dataclass
class StepExecutionContext:
    """Bundles everything an executor needs to run one TestStep.

    `lab_profile` is the bridge that lets executors avoid hard-coded chamber /
    instrument / calibration assumptions: chamber geometry comes from
    `lab_profile.chamber_config`, real-instrument endpoints from
    `lab_profile.instrument_bindings`, and the calibration to apply from
    `calibration_certificate` (resolved from step → testcase → lab default).
    """

    db: "Session"
    step: "TestStep"
    test_execution: "TestExecution"

    # Resolved per-execution environment
    lab_profile: Optional["LabProfile"] = None
    calibration_certificate: Optional["CalibrationCertificate"] = None

    # Convenience: parameters parsed from step
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Optional correlation id for log threading
    correlation_id: Optional[UUID] = None

    def require_lab_profile(self) -> "LabProfile":
        """Asserts a lab_profile is present; raises with a clear message otherwise."""
        if self.lab_profile is None:
            raise RuntimeError(
                f"Step {self.step.id} (type={self.step.type}) requires a LabProfile "
                "but none is bound to its TestCase or TestExecution."
            )
        return self.lab_profile

    def require_calibration(self) -> "CalibrationCertificate":
        """Asserts a calibration certificate is resolved; raises otherwise."""
        if self.calibration_certificate is None:
            raise RuntimeError(
                f"Step {self.step.id} (type={self.step.type}) requires a "
                "CalibrationCertificate but none is bound."
            )
        return self.calibration_certificate
