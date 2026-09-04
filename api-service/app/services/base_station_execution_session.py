"""BaseStation 测试执行的唯一应用层生命周期会话。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from app.services.execution_scpi_evidence import (
    begin_execution_base_station_measurement,
    persist_execution_base_station_release,
    record_execution_base_station_attempt_failure,
)
from app.services.channel_emulator_binding import CE_FREEZE_CONFIG_KEY
from app.services.channel_emulator_execution_plan import CE_PLAN_FREEZE_CONFIG_KEY
from app.services.channel_emulator_execution_session import (
    channel_emulator_execution_scope,
)
from app.services.instrument_test_lease import (
    InstrumentTestLeaseError,
    InstrumentTestLeaseReleaseError,
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


def _get_hal_service():
    from app.services.instrument_hal_service import get_hal_service

    return get_hal_service()


def _get_base_station_driver():
    drivers = _get_hal_service().drivers or {}
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
    execution_config = execution.config if isinstance(execution.config, dict) else {}
    binding = execution_config.get(CE_FREEZE_CONFIG_KEY)
    plan = execution_config.get(CE_PLAN_FREEZE_CONFIG_KEY)
    if binding is None or plan is None:
        raise BaseStationExecutionSessionError(
            "channelEmulator binding / execution plan is not frozen"
        )
    hal = _get_hal_service()

    # P2-59①/③：严格路损资格是整个 run 的第一道纯门，而不是 MEASURE 内
    # 已经 acquire 两台仪器后的迟到检查。它在租约协调锁内执行，但只读冻结配置
    # 与数据库证书，绝不访问传入 HAL；随后才轮到 CE binding/plan 与 BS 对账。
    def _path_loss_preflight(_locked_hal) -> str | None:
        from app.models.lab_profile import LabProfile
        from app.services.mimo_ota.executors._helpers import load_mimo_ota_config
        from app.services.mimo_ota.path_loss_preflight import (
            evaluate_path_loss_preflight,
        )

        if not isinstance(binding, Mapping):
            return None  # CE strict parser owns this malformed-freeze error.
        config = load_mimo_ota_config(execution)
        lab_profile_id = binding.get("lab_profile_id") or test_case.lab_profile_id
        try:
            lab_profile_pk = (
                UUID(str(lab_profile_id)) if lab_profile_id is not None else None
            )
        except (TypeError, ValueError, AttributeError):
            return "path-loss preflight has an invalid frozen LabProfile identity"
        lab = db.get(LabProfile, lab_profile_pk) if lab_profile_pk is not None else None
        chamber = lab.chamber_config if lab is not None else None
        if chamber is None:
            return "path-loss preflight requires a frozen LabProfile chamber"
        verdict = evaluate_path_loss_preflight(
            db,
            execution,
            chamber_id=chamber.id,
            frequency_mhz=config.primary_carrier.frequency_hz / 1e6,
            operating_mode=config.switch_mode_id,
            precheck_strict_cal=config.precheck_strict_cal,
            channel_emulator_execution_mode=str(binding.get("execution_mode")),
        )
        if verdict.blocker is None:
            return None
        return (
            "P1-27 calibration provenance gate failed before hardware connect: "
            f"{verdict.blocker}"
        )

    try:
        async with channel_emulator_execution_scope(
            db,
            execution,
            purpose=purpose,
            binding=binding,
            plan=plan,
            hal=hal,
            validate_before_remote=validate_before_remote,
            preflight_before_remote=_path_loss_preflight,
        ) as outcome:
            lease_outcome = getattr(outcome, "lease_outcome", outcome)
            if _is_measure_step(step_type):
                attempt_id = begin_execution_base_station_measurement(
                    db,
                    execution,
                    test_case,
                    driver=_get_base_station_driver(),
                )
                lease_outcome.measurement_attempt_id = attempt_id
            operation_result = await operation()
            mark_operation_result = getattr(outcome, "mark_operation_result", None)
            if callable(mark_operation_result):
                mark_operation_result(operation_result.succeeded)
            outcome = lease_outcome
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
