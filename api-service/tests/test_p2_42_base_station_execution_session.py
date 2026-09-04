from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


def _install_lifecycle(
    monkeypatch,
    module,
    events: list[str],
    *,
    release_error: BaseException | None = None,
    terminal_state: str = "completed",
    persist_error: BaseException | None = None,
):
    outcome = SimpleNamespace(
        lease_id="lease-1",
        measurement_attempt_id=None,
        base_station_release=None,
    )

    @asynccontextmanager
    async def lease(db, execution, *, purpose, binding, plan, hal, **kwargs):
        events.append("acquire")
        assert db is _DB
        assert execution.id == "execution-1"
        assert purpose == "formal-case:execution-1"
        assert binding is _CE_BINDING
        assert plan is _CE_PLAN
        assert hal is _HAL
        assert kwargs["validate_before_remote"] is _VALIDATOR
        try:
            yield outcome
        finally:
            events.append("release")
            outcome.base_station_release = object()
        if release_error is not None:
            raise release_error

    def begin(db, execution, test_case, *, driver):
        events.append("begin")
        assert driver is _DRIVER
        return "attempt-1"

    def persist(db, execution_id, *, attempt_id, outcome):
        events.append("persist")
        assert execution_id == "execution-1"
        assert attempt_id == "attempt-1"
        assert outcome.measurement_attempt_id == "attempt-1"
        assert outcome.base_station_release is not None
        if persist_error is not None:
            raise persist_error
        return terminal_state

    def fail(db, execution_id, *, attempt_id, outcome, cancelled):
        events.append("cancel" if cancelled else "fail")
        assert execution_id == "execution-1"
        assert attempt_id == "attempt-1"
        assert outcome.measurement_attempt_id == "attempt-1"

    monkeypatch.setattr(module, "channel_emulator_execution_scope", lease)
    monkeypatch.setattr(module, "begin_execution_base_station_measurement", begin)
    monkeypatch.setattr(module, "persist_execution_base_station_release", persist)
    monkeypatch.setattr(
        module, "record_execution_base_station_attempt_failure", fail
    )
    monkeypatch.setattr(module, "_get_base_station_driver", lambda: _DRIVER)
    monkeypatch.setattr(module, "_get_hal_service", lambda: _HAL)
    return outcome


_VALIDATOR = object()
_DRIVER = object()
_DB = object()
_CE_BINDING = {"binding": "frozen"}
_CE_PLAN = {"plan": "frozen"}
_HAL = object()
_EXECUTION = SimpleNamespace(
    id="execution-1",
    config={
        "channel_emulator_binding_freeze": _CE_BINDING,
        "channel_emulator_execution_plan_freeze": _CE_PLAN,
    },
)
_TEST_CASE = object()


@pytest.mark.asyncio
async def test_session_orders_acquire_attempt_operation_release_and_terminal_evidence(
    monkeypatch,
):
    from app.services import base_station_execution_session as module

    events: list[str] = []
    _install_lifecycle(monkeypatch, module, events)

    async def operation():
        events.append("operation")
        return module.BaseStationSessionOperationResult(value="ok", succeeded=True)

    result = await module.run_base_station_execution_session(
        _DB,
        _EXECUTION,
        _TEST_CASE,
        purpose="formal-case:execution-1",
        step_type="MEASURE",
        validate_before_remote=_VALIDATOR,
        operation=operation,
    )

    assert result == "ok"
    assert events == ["acquire", "begin", "operation", "release", "persist"]


@pytest.mark.asyncio
async def test_returned_business_failure_is_recorded_after_actual_release(monkeypatch):
    from app.services import base_station_execution_session as module

    events: list[str] = []
    _install_lifecycle(monkeypatch, module, events)

    async def operation():
        events.append("operation")
        return module.BaseStationSessionOperationResult(value="rejected", succeeded=False)

    result = await module.run_base_station_execution_session(
        _DB,
        _EXECUTION,
        _TEST_CASE,
        purpose="formal-case:execution-1",
        step_type="MEASURE",
        validate_before_remote=_VALIDATOR,
        operation=operation,
    )

    assert result == "rejected"
    assert events == ["acquire", "begin", "operation", "release", "fail"]


@pytest.mark.asyncio
async def test_externally_cancelled_row_keeps_cancelled_attempt_truth(monkeypatch):
    from app.services import base_station_execution_session as module

    events: list[str] = []
    _install_lifecycle(monkeypatch, module, events)
    execution = SimpleNamespace(
        id="execution-1", status="cancelled", config=_EXECUTION.config
    )

    async def operation():
        events.append("operation")
        return module.BaseStationSessionOperationResult(value=None, succeeded=False)

    assert await module.run_base_station_execution_session(
        _DB,
        execution,
        _TEST_CASE,
        purpose="formal-case:execution-1",
        step_type="MIMO_OTA_MEASURE",
        validate_before_remote=_VALIDATOR,
        operation=operation,
    ) is None

    assert events == ["acquire", "begin", "operation", "release", "cancel"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "terminal_event"),
    [(RuntimeError("operation failed"), "fail"), (asyncio.CancelledError(), "cancel")],
)
async def test_exception_and_cancellation_share_release_then_terminal_path(
    monkeypatch, error, terminal_event
):
    from app.services import base_station_execution_session as module

    events: list[str] = []
    _install_lifecycle(monkeypatch, module, events)

    async def operation():
        events.append("operation")
        raise error

    with pytest.raises(type(error)):
        await module.run_base_station_execution_session(
            _DB,
            _EXECUTION,
            _TEST_CASE,
            purpose="formal-case:execution-1",
            step_type="MEASURE",
            validate_before_remote=_VALIDATOR,
            operation=operation,
        )

    assert events == [
        "acquire",
        "begin",
        "operation",
        "release",
        terminal_event,
    ]


@pytest.mark.asyncio
async def test_acquire_failure_never_creates_or_fabricates_an_attempt(monkeypatch):
    from app.services import base_station_execution_session as module

    events: list[str] = []

    @asynccontextmanager
    async def lease(*_args, **kwargs):
        events.append("acquire")
        raise RuntimeError("acquire failed")
        yield  # pragma: no cover

    monkeypatch.setattr(module, "channel_emulator_execution_scope", lease)
    monkeypatch.setattr(
        module,
        "begin_execution_base_station_measurement",
        lambda *_args, **_kwargs: events.append("begin"),
    )
    monkeypatch.setattr(
        module,
        "record_execution_base_station_attempt_failure",
        lambda *_args, **_kwargs: events.append("fail"),
    )
    monkeypatch.setattr(module, "_get_hal_service", lambda: _HAL)

    with pytest.raises(RuntimeError, match="acquire failed"):
        await module.run_base_station_execution_session(
            _DB,
            _EXECUTION,
            _TEST_CASE,
            purpose="formal-case:execution-1",
            step_type="MEASURE",
            validate_before_remote=_VALIDATOR,
            operation=lambda: None,
        )

    assert events == ["acquire"]


@pytest.mark.asyncio
async def test_release_failure_records_the_exact_attempt_before_propagating(monkeypatch):
    from app.services import base_station_execution_session as module
    from app.services.instrument_test_lease import InstrumentTestLeaseReleaseError

    events: list[str] = []
    _install_lifecycle(
        monkeypatch,
        module,
        events,
        release_error=InstrumentTestLeaseReleaseError("release failed"),
    )

    async def operation():
        events.append("operation")
        return module.BaseStationSessionOperationResult(value="ok", succeeded=True)

    with pytest.raises(
        module.BaseStationExecutionSessionReleaseError,
        match="release failed",
    ) as exc_info:
        await module.run_base_station_execution_session(
            _DB,
            _EXECUTION,
            _TEST_CASE,
            purpose="formal-case:execution-1",
            step_type="MEASURE",
            validate_before_remote=_VALIDATOR,
            operation=operation,
        )

    assert isinstance(exc_info.value, InstrumentTestLeaseReleaseError)
    assert exc_info.value.operation_value == "ok"
    assert events == ["acquire", "begin", "operation", "release", "fail"]


@pytest.mark.asyncio
async def test_successful_business_result_fails_loud_when_attempt_is_incomplete(
    monkeypatch,
):
    from app.services import base_station_execution_session as module

    events: list[str] = []
    _install_lifecycle(monkeypatch, module, events, terminal_state="failed")

    async def operation():
        events.append("operation")
        return module.BaseStationSessionOperationResult(value="ok", succeeded=True)

    with pytest.raises(module.BaseStationExecutionSessionError, match="incomplete"):
        await module.run_base_station_execution_session(
            _DB,
            _EXECUTION,
            _TEST_CASE,
            purpose="formal-case:execution-1",
            step_type="MEASURE",
            validate_before_remote=_VALIDATOR,
            operation=operation,
        )

    # persist 已将 exact current attempt 终结为 failed；不得二次覆盖。
    assert events == ["acquire", "begin", "operation", "release", "persist"]


@pytest.mark.asyncio
async def test_terminal_persistence_failure_fails_exact_attempt_without_masking_error(
    monkeypatch,
):
    from app.services import base_station_execution_session as module

    events: list[str] = []
    _install_lifecycle(
        monkeypatch,
        module,
        events,
        persist_error=ValueError("release evidence mismatch"),
    )

    async def operation():
        events.append("operation")
        return module.BaseStationSessionOperationResult(value="ok", succeeded=True)

    with pytest.raises(ValueError, match="release evidence mismatch"):
        await module.run_base_station_execution_session(
            _DB,
            _EXECUTION,
            _TEST_CASE,
            purpose="formal-case:execution-1",
            step_type="MEASURE",
            validate_before_remote=_VALIDATOR,
            operation=operation,
        )

    assert events == [
        "acquire",
        "begin",
        "operation",
        "release",
        "persist",
        "fail",
    ]
