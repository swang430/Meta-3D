"""Executor base interface + result envelope."""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.test_execution.context import StepExecutionContext


class StepExecutionStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    # Reserved for future async/long-running phases
    RUNNING = "running"


@dataclass
class StepExecutionResult:
    """What every executor returns. Persisted by the dispatcher to TestExecution.

    `measurements` and `details` are intentionally typed loosely — the schema
    of these blobs is defined by each step type's contract, not by the framework.
    """

    status: StepExecutionStatus
    measurements: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    duration_sec: Optional[float] = None


class IStepExecutor(ABC):
    """Contract every step executor must satisfy.

    Implementations live near their domain (e.g. commissioning, road_test) and
    register themselves with the registry via the `@register_executor("type")`
    decorator. Keep executors stateless; per-run state goes in the context and
    return value.
    """

    @abstractmethod
    def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        """Run one step. Must not raise on user-visible failures — return
        StepExecutionStatus.FAILED with a populated `error_message` instead.
        Framework-level bugs may still raise.
        """
        raise NotImplementedError
