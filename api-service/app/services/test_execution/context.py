"""StepExecutionContext — what every executor receives at run time."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models.lab_profile import LabProfile
    from app.models.calibration import CalibrationCertificate
    from app.models.test_plan import TestExecution


class StepLike(Protocol):
    """Minimal contract a step object must satisfy to be dispatchable.

    ARCH-1 S5（2026-07-30）更正: 原文写「ORM ``TestStep`` 行和轻量
    ``StepDescriptor`` 都满足本协议」—— **ORM 那一支现在没有生产者了**。
    ``build_step_context`` 只有两个调用方（``api/commissioning.py`` 与
    ``services/test_case_runner.py``），两个传的都是 ``StepDescriptor``；
    唯一会materialize ORM ``TestStep`` 行的计划 runner 已随 ARCH-1 S4b 删除。

    协议本身保持宽松（不收窄成 ``StepDescriptor``）—— 那是行为改动，且宽松
    没有坏处。这里只是把注释改回真话: 今天走到这儿的 **只有** ``StepDescriptor``。
    """

    id: Any
    type: str
    parameters: Dict[str, Any]


@dataclass
class StepDescriptor:
    """Lightweight, in-memory step representation.

    Used when a TestCase fully describes its steps in `configuration.steps`
    rather than materializing rows in the `test_steps` table. This is the path
    taken by VRT and now by MIMO_OTA — keeps the schema simpler when steps
    are an internal split of one TestCase, not independently reusable units.
    """

    id: str
    type: str
    parameters: Dict[str, Any] = field(default_factory=dict)


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
    step: StepLike  # 实际只会是 StepDescriptor (ARCH-1 S4b 后 ORM TestStep 无生产者)
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
