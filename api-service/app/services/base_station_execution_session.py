"""BaseStation 测试执行的唯一应用层生命周期会话。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.services.execution_scpi_evidence import (
    begin_execution_base_station_measurement,
    persist_execution_base_station_release,
    record_execution_base_station_attempt_failure,
)
from app.services.instrument_test_lease import (
    InstrumentTestLeaseError,
    InstrumentTestLeaseReleaseError,
    instrument_test_lease,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseStationExecutionSessionError(InstrumentTestLeaseError):
    """BaseStation 会话未能留下完整、可正式化的执行证据。"""


class BaseStationExecutionSessionReleaseError(InstrumentTestLeaseReleaseError):
    """释放失败，同时保留已产生的业务结果供入口写诊断真值。"""

    def __init__(self, message: str, *, operation_value: object):
        super().__init__(message)
        self.operation_value = operation_value


@dataclass(frozen=True)
class BaseStationSessionOperationResult(Generic[T]):
    """业务值与业务成功真值；生命周期终态仍由会话服务决定。"""

    value: T
    succeeded: bool


def _get_base_station_driver():
    from app.services.instrument_hal_service import get_hal_service

    drivers = get_hal_service().drivers or {}
    return drivers.get("baseStation") or drivers.get("base_station")


def _is_measure_step(step_type: object) -> bool:
    return getattr(step_type, "value", step_type) in {
        "MEASURE",
        "MIMO_OTA_MEASURE",
    }


def _record_exception_terminal_state(
    db,
    execution_id,
    *,
    attempt_id: str | None,
    outcome,
    cancelled: bool,
) -> None:
    """尽力落 exact attempt；失败不能覆盖原业务异常或取消。"""

    if attempt_id is None:
        return
    try:
        record_execution_base_station_attempt_failure(
            db,
            execution_id,
            attempt_id=attempt_id,
            outcome=outcome,
            cancelled=cancelled,
        )
    except Exception:  # noqa: BLE001 — 调用方必须继续看到原始异常/取消
        logger.exception(
            "BaseStation execution session 无法落 measurement attempt 终态: %s",
            execution_id,
        )


async def run_base_station_execution_session(
    db,
    execution,
    test_case,
    *,
    purpose: str,
    step_type: object,
    validate_before_remote,
    operation: Callable[[], Awaitable[BaseStationSessionOperationResult[T]]],
) -> T:
    """按唯一顺序取得控制、绑定证据、执行、释放并落终态。"""

    attempt_id: str | None = None
    outcome = None
    operation_result: BaseStationSessionOperationResult[T] | None = None
    try:
        async with instrument_test_lease(
            purpose,
            measurement_attempt_id=None,
            enable_monitoring=False,
            validate_before_remote=validate_before_remote,
        ) as outcome:
            if _is_measure_step(step_type):
                attempt_id = begin_execution_base_station_measurement(
                    db,
                    execution,
                    test_case,
                    driver=_get_base_station_driver(),
                )
                outcome.measurement_attempt_id = attempt_id
            operation_result = await operation()
    except asyncio.CancelledError:
        _record_exception_terminal_state(
            db,
            execution.id,
            attempt_id=attempt_id,
            outcome=outcome,
            cancelled=True,
        )
        raise
    except InstrumentTestLeaseReleaseError as error:
        _record_exception_terminal_state(
            db,
            execution.id,
            attempt_id=attempt_id,
            outcome=outcome,
            cancelled=False,
        )
        if operation_result is None:
            raise
        raise BaseStationExecutionSessionReleaseError(
            str(error),
            operation_value=operation_result.value,
        ) from error
    except BaseException:
        _record_exception_terminal_state(
            db,
            execution.id,
            attempt_id=attempt_id,
            outcome=outcome,
            cancelled=False,
        )
        raise

    if operation_result is None:  # pragma: no cover - async context invariant
        raise BaseStationExecutionSessionError("BaseStation operation result is missing")

    if attempt_id is not None:
        if operation_result.succeeded:
            try:
                terminal_state = persist_execution_base_station_release(
                    db,
                    execution.id,
                    attempt_id=attempt_id,
                    outcome=outcome,
                )
            except BaseException:
                _record_exception_terminal_state(
                    db,
                    execution.id,
                    attempt_id=attempt_id,
                    outcome=outcome,
                    cancelled=False,
                )
                raise
            if terminal_state != "completed":
                raise BaseStationExecutionSessionError(
                    "BaseStation measurement lifecycle is incomplete"
                )
        else:
            record_execution_base_station_attempt_failure(
                db,
                execution.id,
                attempt_id=attempt_id,
                outcome=outcome,
                cancelled=getattr(execution, "status", None) == "cancelled",
            )
    return operation_result.value
