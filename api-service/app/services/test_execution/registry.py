"""Step executor registry + dispatch.

Registry is a process-global dict keyed by `step.type` string. Executors
register themselves at import time via `@register_executor("MIMO_OTA")`.
Dispatch wraps the executor call with timing + uniform exception handling so
individual executors don't have to.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Type

from app.services.test_execution.context import StepExecutionContext
from app.services.test_execution.executor_base import (
    IStepExecutor,
    StepExecutionResult,
    StepExecutionStatus,
)

logger = logging.getLogger(__name__)

EXECUTOR_REGISTRY: Dict[str, Type[IStepExecutor]] = {}


class StepExecutorNotFoundError(KeyError):
    """Raised when dispatch_step is called for a step.type with no registered executor."""


def register_executor(step_type: str):
    """Decorator: register an IStepExecutor subclass for a given step.type.

    Re-registering the same step_type overwrites the prior entry and emits a
    warning — typical when modules are reloaded in dev. In production startup
    each executor is registered exactly once.
    """

    def _wrap(cls: Type[IStepExecutor]) -> Type[IStepExecutor]:
        if not issubclass(cls, IStepExecutor):
            raise TypeError(
                f"{cls.__name__} must subclass IStepExecutor to be registered"
            )
        if step_type in EXECUTOR_REGISTRY:
            logger.warning(
                "Overwriting existing executor for step_type=%r (was %s, now %s)",
                step_type,
                EXECUTOR_REGISTRY[step_type].__name__,
                cls.__name__,
            )
        EXECUTOR_REGISTRY[step_type] = cls
        logger.info("Registered step executor: %s -> %s", step_type, cls.__name__)
        return cls

    return _wrap


def get_registered_step_types() -> List[str]:
    """Snapshot of currently-registered step types — useful for /health and debugging."""
    return sorted(EXECUTOR_REGISTRY.keys())


def dispatch_step(context: StepExecutionContext) -> StepExecutionResult:
    """Run the registered executor for `context.step.type`.

    Wraps the call with:
    - timing (populates result.duration_sec if executor didn't)
    - uniform exception → FAILED conversion (executor bugs don't crash the runner)

    Raises StepExecutorNotFoundError if no executor is registered for the type.
    """
    step_type = context.step.type
    executor_cls = EXECUTOR_REGISTRY.get(step_type)
    if executor_cls is None:
        raise StepExecutorNotFoundError(
            f"No executor registered for step.type={step_type!r}. "
            f"Registered types: {get_registered_step_types()}"
        )

    executor = executor_cls()
    started = time.monotonic()
    try:
        result = executor.execute(context)
    except Exception as exc:  # pragma: no cover — defensive boundary
        elapsed = time.monotonic() - started
        logger.exception(
            "Executor %s raised for step %s (type=%s)",
            executor_cls.__name__,
            context.step.id,
            step_type,
        )
        return StepExecutionResult(
            status=StepExecutionStatus.FAILED,
            error_message=f"{type(exc).__name__}: {exc}",
            duration_sec=elapsed,
        )

    if result.duration_sec is None:
        result.duration_sec = time.monotonic() - started
    return result
