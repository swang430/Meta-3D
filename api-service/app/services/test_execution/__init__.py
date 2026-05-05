"""TestStep execution framework — Phase 0.

Establishes the explicit dispatch path that was previously implicit:

    step (with type + parameters)
    + LabProfile (chamber + instruments + calibration)
    + TestExecution (DB persistence target)
        ──> EXECUTOR_REGISTRY[step.type]
            ──> IStepExecutor.execute(context) -> StepExecutionResult

Extension points for future executors:
    from app.services.test_execution import register_executor, IStepExecutor

    @register_executor("MIMO_OTA")
    class MIMOOTAExecutor(IStepExecutor):
        def execute(self, ctx): ...

This module intentionally contains only the framework. Concrete executors
(MIMO_OTA, TRP, TIS, VRT phases) are registered by their owning service
modules so the framework stays free of test-domain coupling.
"""
from app.services.test_execution.context import StepExecutionContext
from app.services.test_execution.executor_base import (
    IStepExecutor,
    StepExecutionResult,
    StepExecutionStatus,
)
from app.services.test_execution.registry import (
    EXECUTOR_REGISTRY,
    StepExecutorNotFoundError,
    dispatch_step,
    get_registered_step_types,
    register_executor,
)

__all__ = [
    "StepExecutionContext",
    "IStepExecutor",
    "StepExecutionResult",
    "StepExecutionStatus",
    "EXECUTOR_REGISTRY",
    "StepExecutorNotFoundError",
    "dispatch_step",
    "get_registered_step_types",
    "register_executor",
]
