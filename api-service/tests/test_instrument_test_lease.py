"""仪表测试租约：空闲不轮询，测试结束归还 F64 前面板控制。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.hal.base_station import (
    BaseStationControlReleaseResult,
    BaseStationRemoteSessionResult,
)


class _FakeInstrument:
    def __init__(
        self,
        events: list[str],
        name: str,
        *,
        acquire_ok: bool = True,
        release_ok: bool = True,
    ):
        self.events = events
        self.name = name
        self.acquire_ok = acquire_ok
        self.release_ok = release_ok

    async def acquire_remote_control(self) -> bool:
        self.events.append(f"{self.name}-remote")
        return self.acquire_ok

    async def release_to_local_control(self) -> bool:
        self.events.append(f"{self.name}-local")
        return self.release_ok


class _FakeF64(_FakeInstrument):
    def __init__(self, events: list[str], *, release_ok: bool = True):
        super().__init__(events, "f64", release_ok=release_ok)


class _FakeUxm(_FakeInstrument):
    adapter_id = "uxm"

    def __init__(
        self,
        events: list[str],
        *,
        acquire_ok: bool = True,
        release_ok: bool = True,
    ):
        super().__init__(
            events,
            "uxm",
            acquire_ok=acquire_ok,
            release_ok=release_ok,
        )

    async def acquire_remote_control(self) -> BaseStationRemoteSessionResult:
        self.events.append("uxm-remote")
        return BaseStationRemoteSessionResult(
            adapter_id="uxm",
            session_token="uxm-session",
            acquired_confirmed=self.acquire_ok,
            warnings=(),
        )

    async def release_remote_session(
        self,
        expected_session_token: str,
        *,
        measurement_attempt_id: str | None = None,
        lease_id: str = "",
    ) -> BaseStationControlReleaseResult:
        self.events.append("uxm-local")
        return BaseStationControlReleaseResult(
            measurement_attempt_id=measurement_attempt_id,
            lease_id=lease_id,
            adapter_id="uxm",
            session_token=expected_session_token,
            remote_session_acquired_confirmed=self.acquire_ok,
            transport_session_released_confirmed=self.release_ok,
            front_panel_local_confirmed=None,
            warnings=(),
        )


class _FakeHAL:
    def __init__(self, driver, uxm=None):
        self.drivers = {"channelEmulator": driver}
        if uxm is not None:
            self.drivers["baseStation"] = uxm
        self.cache_clears = 0

    async def clear_metrics_cache(self) -> None:
        self.cache_clears += 1


@pytest.mark.asyncio
async def test_lease_acquires_remote_only_during_test_and_releases_after_success():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events))
    lease = InstrumentTestLease(lambda: hal)

    assert lease.is_active is False
    async with lease.hold("formal-case"):
        assert lease.is_active is True
        events.append("test")

    assert lease.is_active is False
    assert events == ["f64-remote", "test", "f64-local"]
    assert hal.cache_clears == 2


@pytest.mark.asyncio
async def test_standalone_operation_blocks_reload_without_opening_f64_or_polling():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events))
    lease = InstrumentTestLease(lambda: hal)

    async with lease.hold(
        "other-scpi-console",
        control_f64=False,
        control_uxm=False,
        enable_monitoring=False,
    ):
        assert lease.is_active is True
        assert lease.monitoring_enabled is False
        events.append("operation")

    assert events == ["operation"]


@pytest.mark.asyncio
async def test_lease_releases_local_after_test_failure_without_masking_failure():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    lease = InstrumentTestLease(lambda: _FakeHAL(_FakeF64(events)))

    with pytest.raises(RuntimeError, match="measurement failed"):
        async with lease.hold("diagnostic"):
            raise RuntimeError("measurement failed")

    assert lease.is_active is False
    assert events == ["f64-remote", "f64-local"]


@pytest.mark.asyncio
async def test_release_failure_is_not_hidden_by_the_operation_failure():
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseError,
        InstrumentTestLeaseReleaseError,
    )

    events: list[str] = []
    lease = InstrumentTestLease(
        lambda: _FakeHAL(_FakeF64(events, release_ok=False))
    )

    with pytest.raises(InstrumentTestLeaseError) as caught:
        async with lease.hold("diagnostic"):
            raise RuntimeError("measurement failed")

    assert isinstance(caught.value, InstrumentTestLeaseReleaseError)
    assert "measurement failed" in str(caught.value)
    assert "控制会话释放" in str(caught.value)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert events == ["f64-remote", "f64-local"]


@pytest.mark.asyncio
async def test_lease_releases_local_when_running_test_task_is_cancelled():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    entered = asyncio.Event()
    lease = InstrumentTestLease(lambda: _FakeHAL(_FakeF64(events)))

    async def _run() -> None:
        async with lease.hold("cancelled-test"):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(_run())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert lease.is_active is False
    assert events == ["f64-remote", "f64-local"]


@pytest.mark.asyncio
async def test_idle_parking_releases_f64_without_acquiring_remote():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events))
    lease = InstrumentTestLease(lambda: hal)

    assert await lease.park_idle_instruments() is True
    assert lease.is_active is False
    assert events == ["f64-local"]


@pytest.mark.asyncio
async def test_hal_lookup_failure_does_not_leak_exclusive_lock():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events))
    calls = 0

    def _get_hal():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("HAL unavailable")
        return hal

    lease = InstrumentTestLease(_get_hal)
    with pytest.raises(RuntimeError, match="HAL unavailable"):
        async with lease.hold("first"):
            pass

    async with asyncio.timeout(0.2):
        async with lease.hold("second"):
            events.append("test")

    assert events == ["f64-remote", "test", "f64-local"]


@pytest.mark.asyncio
async def test_default_test_lease_controls_f64_and_uxm_and_releases_reverse_order():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events), _FakeUxm(events))
    lease = InstrumentTestLease(lambda: hal)

    async with lease.hold("formal-case"):
        events.append("test")

    assert events == [
        "f64-remote",
        "uxm-remote",
        "test",
        "uxm-local",
        "f64-local",
    ]


@pytest.mark.asyncio
async def test_uxm_only_operation_does_not_open_f64_and_disables_monitoring():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events), _FakeUxm(events))
    lease = InstrumentTestLease(lambda: hal)

    async with lease.hold(
        "uxm-scpi-console",
        control_f64=False,
        control_uxm=True,
        enable_monitoring=False,
    ):
        events.append("operation")

    assert events == ["uxm-remote", "operation", "uxm-local"]


@pytest.mark.asyncio
async def test_pre_remote_validator_rejects_before_any_hal_io():
    """持久化配置与活动单会话不一致时，连 cache/Remote/Local 都不能碰。"""
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseError,
    )

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events), _FakeUxm(events))
    lease = InstrumentTestLease(lambda: hal)

    with pytest.raises(InstrumentTestLeaseError, match="重新加载 HAL"):
        async with lease.hold(
            "uxm-scpi-console",
            control_f64=False,
            control_uxm=True,
            validate_before_remote=lambda _hal: (
                "已保存配置与活动 HAL 会话目标不一致；请重新加载 HAL"
            ),
        ):
            pytest.fail("校验失败后不得进入操作体")

    assert events == []
    assert hal.cache_clears == 0


@pytest.mark.asyncio
async def test_idle_parking_releases_f64_and_uxm_without_acquiring_remote():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events), _FakeUxm(events))
    lease = InstrumentTestLease(lambda: hal)

    assert await lease.park_idle_instruments() is True
    assert events == ["uxm-local", "f64-local"]


@pytest.mark.asyncio
async def test_partial_acquire_failure_still_releases_both_instruments():
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseError,
    )

    events: list[str] = []
    hal = _FakeHAL(
        _FakeF64(events),
        _FakeUxm(events, acquire_ok=False),
    )
    lease = InstrumentTestLease(lambda: hal)

    with pytest.raises(InstrumentTestLeaseError, match="UXM Remote"):
        async with lease.hold("formal-case"):
            pytest.fail("UXM 取得失败后不得进入测试体")

    assert events == [
        "f64-remote",
        "uxm-remote",
        "uxm-local",
        "f64-local",
    ]


@pytest.mark.asyncio
async def test_uxm_release_failure_does_not_skip_f64_release():
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseError,
    )

    events: list[str] = []
    hal = _FakeHAL(_FakeF64(events), _FakeUxm(events, release_ok=False))
    lease = InstrumentTestLease(lambda: hal)

    with pytest.raises(InstrumentTestLeaseError, match="UXM 控制会话释放"):
        async with lease.hold("formal-case"):
            events.append("test")

    assert events == [
        "f64-remote",
        "uxm-remote",
        "test",
        "uxm-local",
        "f64-local",
    ]


@pytest.mark.asyncio
async def test_exit_cache_failure_still_attempts_and_reports_all_local_releases():
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseReleaseError,
    )

    class _ExitCacheFailureHAL(_FakeHAL):
        async def clear_metrics_cache(self) -> None:
            self.cache_clears += 1
            if self.cache_clears == 2:
                raise RuntimeError("exit cache clear failed")

    events: list[str] = []
    hal = _ExitCacheFailureHAL(
        _FakeF64(events, release_ok=False),
        _FakeUxm(events, release_ok=False),
    )
    lease = InstrumentTestLease(lambda: hal)

    with pytest.raises(InstrumentTestLeaseReleaseError) as caught:
        async with lease.hold("formal-case"):
            events.append("test")

    message = str(caught.value)
    assert "exit cache clear failed" in message
    assert "UXM" in message
    assert "F64" in message
    assert events == [
        "f64-remote",
        "uxm-remote",
        "test",
        "uxm-local",
        "f64-local",
    ]


@pytest.mark.asyncio
async def test_idle_cache_failure_still_attempts_all_local_releases():
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseReleaseError,
    )

    class _CacheFailureHAL(_FakeHAL):
        async def clear_metrics_cache(self) -> None:
            self.cache_clears += 1
            raise RuntimeError("idle cache clear failed")

    events: list[str] = []
    hal = _CacheFailureHAL(_FakeF64(events), _FakeUxm(events))
    lease = InstrumentTestLease(lambda: hal)

    with pytest.raises(InstrumentTestLeaseReleaseError, match="idle cache clear failed"):
        await lease.park_idle_instruments()

    assert events == ["uxm-local", "f64-local"]


@pytest.mark.asyncio
async def test_exit_cleanup_cancellation_still_attempts_all_local_releases():
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseReleaseError,
    )

    class _ExitCancelledHAL(_FakeHAL):
        async def clear_metrics_cache(self) -> None:
            self.cache_clears += 1
            if self.cache_clears == 2:
                raise asyncio.CancelledError("cancel during cleanup")

    events: list[str] = []
    hal = _ExitCancelledHAL(_FakeF64(events), _FakeUxm(events))
    lease = InstrumentTestLease(lambda: hal)

    with pytest.raises(InstrumentTestLeaseReleaseError, match="CancelledError"):
        async with lease.hold("formal-case"):
            events.append("test")

    assert events[-2:] == ["uxm-local", "f64-local"]


@pytest.mark.asyncio
async def test_lease_is_visible_while_remote_acquire_is_still_in_progress():
    from app.services.instrument_test_lease import InstrumentTestLease

    entered = asyncio.Event()
    release = asyncio.Event()

    class _SlowUxm(_FakeUxm):
        async def acquire_remote_control(self) -> BaseStationRemoteSessionResult:
            self.events.append("uxm-remote")
            entered.set()
            await release.wait()
            return BaseStationRemoteSessionResult(
                adapter_id="uxm",
                session_token="uxm-session",
                acquired_confirmed=True,
                warnings=(),
            )

    events: list[str] = []
    lease = InstrumentTestLease(
        lambda: _FakeHAL(_FakeF64(events), _SlowUxm(events))
    )

    async def _run():
        async with lease.hold("slow-acquire"):
            events.append("test")

    task = asyncio.create_task(_run())
    await entered.wait()
    assert lease.active_purpose == "slow-acquire"
    release.set()
    await task


@pytest.mark.asyncio
async def test_hal_mutation_guard_serializes_with_active_test_lease():
    from app.services.instrument_test_lease import InstrumentTestLease

    test_entered = asyncio.Event()
    release_test = asyncio.Event()
    mutation_entered = asyncio.Event()
    events: list[str] = []
    lease = InstrumentTestLease(lambda: _FakeHAL(_FakeF64(events)))

    async def _test():
        async with lease.hold("test", control_uxm=False):
            test_entered.set()
            await release_test.wait()

    async def _mutate():
        async with lease.hal_mutation_guard():
            mutation_entered.set()

    test_task = asyncio.create_task(_test())
    await test_entered.wait()
    mutation_task = asyncio.create_task(_mutate())
    await asyncio.sleep(0)
    assert mutation_entered.is_set() is False
    release_test.set()
    await test_task
    await mutation_task
    assert mutation_entered.is_set() is True


@pytest.mark.asyncio
async def test_idle_park_is_reentrant_inside_hal_mutation_guard():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    lease = InstrumentTestLease(lambda: _FakeHAL(_FakeF64(events)))

    async with asyncio.timeout(0.2):
        async with lease.hal_mutation_guard():
            assert await lease.park_idle_instruments() is True

    assert events == ["f64-local"]


@pytest.mark.asyncio
async def test_monitoring_source_does_not_touch_hal_while_no_test_is_active(
    monkeypatch,
):
    import app.api.monitoring as monitoring

    monkeypatch.setattr(monitoring, "is_test_monitoring_enabled", lambda: False)
    monkeypatch.setattr(
        monitoring,
        "get_hal_service",
        lambda: pytest.fail("空闲监控不应读取 HAL"),
    )

    assert await monitoring.generate_monitoring_data() == {}


@pytest.mark.asyncio
async def test_formal_case_background_task_holds_lease_for_whole_run(monkeypatch):
    import app.services.test_case_runner as runner

    events: list[str] = []

    execution = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        test_case_id=UUID("00000000-0000-0000-0000-000000000002"),
        config={
            "base_station_adapter_profile_freeze": {"digest": "formal-freeze"}
        }
    )
    test_case = SimpleNamespace(id=execution.test_case_id)

    class _Query:
        def __init__(self, model):
            self.model = model

        def filter(self, *_args):
            return self

        def first(self):
            return execution if self.model is runner.TestExecution else test_case

    class _DB:
        def query(self, model):
            return _Query(model)

        def close(self) -> None:
            events.append("db-close")

    async def _session(
        db, session_execution, session_test_case, *, purpose, step_type,
        validate_before_remote, operation,
    ):
        assert db.__class__ is _DB
        assert session_execution is execution
        assert session_test_case is test_case
        assert step_type == "MIMO_OTA_MEASURE"
        validator = validate_before_remote
        assert getattr(validator, "validation_identity", None) == "formal-freeze"
        events.append(f"session-enter:{purpose}")
        result = await operation()
        assert result.succeeded is True
        events.append("release-persisted")
        return result.value

    async def _loop(_db, _execution_id, *, defer_report=False):
        assert defer_report is True
        events.append("case-loop")
        return [
            {
                "id": "analysis",
                "type": "MIMO_OTA_ANALYSIS",
                "parameters": {},
            },
            {"id": "report", "type": "MIMO_OTA_REPORT", "parameters": {}},
        ]

    async def _formalize_after_release(_db, _execution_id, _raws) -> None:
        events.append("formalization-after-release")

    monkeypatch.setattr(runner, "SessionLocal", _DB)
    monkeypatch.setattr(runner, "run_base_station_execution_session", _session)
    monkeypatch.setattr(runner, "_run_case_loop", _loop)
    monkeypatch.setattr(
        runner,
        "_run_deferred_case_formalization",
        _formalize_after_release,
    )

    execution_id = str(execution.id)
    await runner._run_case(execution_id)

    assert events == [
        f"session-enter:formal-case:{execution_id}",
        "case-loop",
        "release-persisted",
        "formalization-after-release",
        "db-close",
    ]


@pytest.mark.asyncio
async def test_formal_case_defers_analysis_and_report_as_one_ordered_bundle(
    monkeypatch,
):
    import app.services.test_case_runner as runner

    execution = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000011"),
        test_case_id=UUID("00000000-0000-0000-0000-000000000012"),
        status="running",
        config={
            "step_descriptors": [
                {"id": "measure", "type": "MIMO_OTA_MEASURE", "parameters": {}},
                {
                    "id": "analysis",
                    "type": "MIMO_OTA_ANALYSIS",
                    "parameters": {},
                },
                {"id": "report", "type": "MIMO_OTA_REPORT", "parameters": {}},
            ],
            "phase_progress": [],
        },
    )
    test_case = SimpleNamespace(id=execution.test_case_id)

    class _Query:
        def __init__(self, model):
            self._model = model

        def filter(self, *_args):
            return self

        def first(self):
            return execution if self._model is runner.TestExecution else test_case

    class _DB:
        def query(self, model):
            return _Query(model)

        def expire(self, *_args):
            pass

        def refresh(self, *_args):
            pass

        def commit(self):
            pass

    dispatched: list[str] = []

    async def _dispatch(context):
        dispatched.append(context.type)
        return SimpleNamespace(status=SimpleNamespace(value="success"))

    monkeypatch.setattr(runner, "build_step_context", lambda *_args: _args[-1])
    monkeypatch.setattr(runner, "dispatch_step", _dispatch)
    monkeypatch.setattr(runner, "flag_modified", lambda *_args: None)

    bundle = await runner._run_case_loop(
        _DB(),
        execution.id,
        defer_report=True,
    )

    assert dispatched == ["MIMO_OTA_MEASURE"]
    assert [raw["type"] for raw in bundle] == [
        "MIMO_OTA_ANALYSIS",
        "MIMO_OTA_REPORT",
    ]
    assert execution.config["phase_progress"] == [
        {"type": "MIMO_OTA_MEASURE", "status": "success"}
    ]


@pytest.mark.asyncio
async def test_formal_case_rejects_non_terminal_analysis_report_sequence():
    import app.services.test_case_runner as runner

    execution = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000021"),
        test_case_id=UUID("00000000-0000-0000-0000-000000000022"),
        status="running",
        config={
            "step_descriptors": [
                {
                    "id": "analysis",
                    "type": "MIMO_OTA_ANALYSIS",
                    "parameters": {},
                },
                {"id": "measure", "type": "MIMO_OTA_MEASURE", "parameters": {}},
                {"id": "report", "type": "MIMO_OTA_REPORT", "parameters": {}},
            ]
        },
    )
    test_case = SimpleNamespace(id=execution.test_case_id)

    class _Query:
        def __init__(self, model):
            self._model = model

        def filter(self, *_args):
            return self

        def first(self):
            return execution if self._model is runner.TestExecution else test_case

    class _DB:
        def query(self, model):
            return _Query(model)

        def expire(self, *_args):
            pass

        def refresh(self, *_args):
            pass

    with pytest.raises(RuntimeError, match="ANALYSIS"):
        await runner._run_case_loop(_DB(), execution.id, defer_report=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["completed", "cancelled", "failed"])
async def test_formal_case_is_failed_when_local_handoff_fails_after_terminal_winner(
    monkeypatch, winner
):
    import app.services.test_case_runner as runner
    from app.services.instrument_test_lease import InstrumentTestLeaseReleaseError

    execution = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        test_case_id=UUID("00000000-0000-0000-0000-000000000013"),
        status="running",
        config={
            "error_message": "original phase outcome",
            "base_station_adapter_profile_freeze": {"digest": "formal-freeze"},
        },
        error_message="original persisted outcome",
        completed_at=None,
        duration_sec=None,
        started_at=None,
        executed_by=runner.RUNNER_MARKER,
    )

    class _Query:
        def filter(self, *_args):
            return self

        def first(self):
            return execution

        def update(self, values, synchronize_session=False):
            assert synchronize_session is False
            assert execution.status == winner
            for column, value in values.items():
                setattr(execution, column.key, value)
            return 1

    class _DB:
        def query(self, *_args):
            return _Query()

        def rollback(self):
            pass

        def commit(self):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    async def _session(*_args, operation, **_kwargs):
        await operation()
        raise InstrumentTestLeaseReleaseError("Local 交接失败")

    async def _loop(_db, _execution_id, *, defer_report=False):
        assert defer_report is True
        execution.status = winner
        return None

    alerts = []

    monkeypatch.setattr(runner, "SessionLocal", _DB)
    monkeypatch.setattr(runner, "run_base_station_execution_session", _session)
    monkeypatch.setattr(runner, "_run_case_loop", _loop)
    monkeypatch.setattr(runner, "flag_modified", lambda *_args: None)
    monkeypatch.setattr(runner, "_finalize_scpi_acceptance", lambda _ex: None)
    monkeypatch.setattr(runner, "emit_execution_failed_alert", alerts.append)

    await runner._run_case(UUID("00000000-0000-0000-0000-000000000003"))

    assert execution.status == "failed"
    assert execution.config["local_control_handoff_failed"] is True
    assert execution.config["local_control_handoff_previous_status"] == winner
    assert execution.config["local_control_handoff_previous_error"] == (
        "original persisted outcome"
    )
    assert "Local 交接失败" in execution.config["error_message"]
    assert "original persisted outcome" in execution.config["error_message"]
    assert execution.error_message == execution.config["error_message"]
    assert "Local 交接失败" in execution.config["local_control_handoff_error"]
    assert alerts == [execution.id]


@pytest.mark.asyncio
async def test_local_handoff_failure_retries_after_concurrent_cancel_wins(
    monkeypatch,
):
    import app.services.test_case_runner as runner
    from app.services.instrument_test_lease import InstrumentTestLeaseReleaseError

    execution = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000004"),
        test_case_id=UUID("00000000-0000-0000-0000-000000000014"),
        status="running",
        config={
            "phase_progress": [{"type": "MEASURE", "status": "success"}],
            "base_station_adapter_profile_freeze": {"digest": "formal-freeze"},
        },
        error_message=None,
        completed_at=None,
        duration_sec=None,
        started_at=None,
        executed_by=runner.RUNNER_MARKER,
    )

    class _Query:
        def filter(self, *_args):
            return self

        def first(self):
            return execution

    class _DB:
        def query(self, *_args):
            return _Query()

        def rollback(self):
            pass

        def commit(self):
            pass

        def flush(self):
            pass

        def expire(self, *_args):
            pass

        def refresh(self, *_args):
            pass

        def close(self):
            pass

    async def _session(*_args, operation, **_kwargs):
        await operation()
        raise InstrumentTestLeaseReleaseError("Local 交接失败")

    async def _loop(_db, _execution_id, *, defer_report=False):
        assert defer_report is True
        return None

    cas_attempts = []

    def _cas(_db, _execution_id, **kwargs):
        cas_attempts.append(kwargs)
        if len(cas_attempts) == 1:
            assert kwargs["expected_status"] == "running"
            execution.status = "cancelled"
            execution.config = {
                "phase_progress": [{"type": "MEASURE", "status": "success"}],
                "error_message": "operator cancelled",
            }
            return False
        assert kwargs["expected_status"] == "cancelled"
        execution.status = kwargs["terminal_status"]
        execution.config = kwargs["config"]
        return True

    alerts = []
    monkeypatch.setattr(runner, "SessionLocal", _DB)
    monkeypatch.setattr(runner, "run_base_station_execution_session", _session)
    monkeypatch.setattr(runner, "_run_case_loop", _loop)
    monkeypatch.setattr(runner, "_cas_case_execution_terminal", _cas)
    monkeypatch.setattr(runner, "_finalize_scpi_acceptance", lambda _ex: None)
    monkeypatch.setattr(runner, "emit_execution_failed_alert", alerts.append)

    await runner._run_case(execution.id)

    assert len(cas_attempts) == 2
    assert execution.status == "failed"
    assert execution.config["local_control_handoff_previous_error"] == (
        "operator cancelled"
    )
    assert "Local 交接失败" in execution.config["error_message"]
    assert "operator cancelled" in execution.config["error_message"]
    assert execution.config["local_control_handoff_previous_status"] == "cancelled"
    assert execution.config["local_control_handoff_failed"] is True
    assert alerts == [execution.id]


@pytest.mark.asyncio
async def test_remote_acquire_failure_is_not_mislabeled_as_local_handoff(
    monkeypatch,
):
    import app.services.test_case_runner as runner
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    execution = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000005"),
        test_case_id=UUID("00000000-0000-0000-0000-000000000015"),
        status="running",
        config={
            "base_station_adapter_profile_freeze": {"digest": "formal-freeze"}
        },
        error_message=None,
        completed_at=None,
        duration_sec=None,
        started_at=None,
        executed_by=runner.RUNNER_MARKER,
    )

    class _Query:
        def filter(self, *_args):
            return self

        def first(self):
            return execution

        def update(self, values, synchronize_session=False):
            for column, value in values.items():
                setattr(execution, column.key, value)
            return 1

    class _DB:
        def query(self, *_args):
            return _Query()

        def rollback(self):
            pass

        def commit(self):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    async def _session(*_args, **_kwargs):
        raise InstrumentTestLeaseError("无法取得 UXM Remote 控制")

    monkeypatch.setattr(runner, "SessionLocal", _DB)
    monkeypatch.setattr(runner, "run_base_station_execution_session", _session)
    monkeypatch.setattr(runner, "_finalize_scpi_acceptance", lambda _ex: None)
    monkeypatch.setattr(runner, "emit_execution_failed_alert", lambda _id: None)

    await runner._run_case(execution.id)

    assert execution.status == "failed"
    assert "local_control_handoff_failed" not in execution.config
    assert "无法取得 UXM Remote 控制" in execution.config["error_message"]


@pytest.mark.asyncio
async def test_diagnostic_sequence_holds_lease_around_sequence_run(monkeypatch):
    import app.api.diagnostic_sequence as api
    from app.diagnostics.protocol import SequenceMetadata, SequenceRunResult

    events: list[str] = []

    class _Context:
        lab_profile_name = "unit-test"

        def find_binding_by_category_key(self, _key):
            return None

        def find_binding_by_role(self, _key):
            return None

        def record_run(self, *_args, **_kwargs):
            return SimpleNamespace(
                id=UUID("00000000-0000-0000-0000-000000000002")
            )

    async def _run(_ctx, _hal, _params, *, log):
        events.append("sequence-run")
        return SequenceRunResult(success=True, summary="ok")

    sequence = SimpleNamespace(
        metadata=SequenceMetadata(
            name="probe",
            description="probe",
            required_categories=[],
            safe_during_test=True,
        ),
        run=_run,
    )

    @asynccontextmanager
    async def _lease(purpose: str, **kwargs):
        events.append(f"lease-enter:{purpose}:{kwargs}")
        try:
            yield
        finally:
            events.append("lease-exit")

    monkeypatch.setattr(api.loader, "get_sequence", lambda _key: sequence)
    monkeypatch.setattr(api, "build_diagnostic_context", lambda *_a, **_k: _Context())
    monkeypatch.setattr(api, "get_hal_service", lambda: object())
    monkeypatch.setattr(api, "instrument_test_lease", _lease, raising=False)

    response = await api.run_diagnostic_sequence(
        "probe",
        api.RunSequenceRequest(),
        db=object(),
    )

    assert response.success is True
    assert events == [
        "lease-enter:diagnostic-sequence:probe:{'control_f64': False, 'control_uxm': False}",
        "sequence-run",
        "lease-exit",
    ]


class TestLeaseErrorReachesTheOperator:
    """内审 F7：租约取不到控制权时，端点必须回 409 + 那句中文原因。

    `InstrumentTestLeaseError` 继承 `RuntimeError`，没有 exception_handler 时
    FastAPI 兜成 `{"detail": "Internal Server Error"}` —— 精心写的
    「测试 'xxx' 无法取得 F64 Remote 控制: <驱动原因>」只留在后端日志里，
    现场排障的人在 GUI 上只看得到"服务器错误"。
    """

    def test_lease_error_becomes_409_with_the_reason(self):
        """⭐ 行为门。变异：注释掉 main.py 的 @app.exception_handler → 本条红
        （裸 500 + detail 变成 'Internal Server Error'）。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.main import _instrument_lease_error_handler
        from app.services.instrument_test_lease import InstrumentTestLeaseError

        probe = FastAPI()
        probe.add_exception_handler(
            InstrumentTestLeaseError, _instrument_lease_error_handler
        )

        @probe.get("/boom")
        async def _boom():
            raise InstrumentTestLeaseError(
                "测试 'load-smu' 无法取得 F64 Remote 控制: 上次 ATE socket 关闭未确认"
            )

        resp = TestClient(probe, raise_server_exceptions=False).get("/boom")

        assert resp.status_code == 409, (
            f"租约冲突回了 {resp.status_code} —— 应当是 409（资源被占用），"
            "500 会让 GUI 只显示'服务器错误'"
        )
        detail = resp.json()["detail"]
        assert "无法取得 F64 Remote 控制" in detail, "驱动给的原因没到操作员手里"
        assert "Internal Server Error" not in detail

    def test_handler_is_actually_registered_on_the_real_app(self):
        """⭐ 生效端：上面那条用的是探针 app，证明不了**真 app** 接上了。

        变异：删掉 main.py 里的 `@app.exception_handler(...)` 装饰器 → 本条红。
        """
        from app.main import app
        from app.services.instrument_test_lease import InstrumentTestLeaseError

        assert InstrumentTestLeaseError in app.exception_handlers, (
            "真 app 上没注册 InstrumentTestLeaseError 处理器 —— "
            "15 个租约端点仍会裸 500"
        )


class TestNestedLeaseReusesInsteadOfTearingDown:
    """内审 F5：`hold()` 的 `finally` 原本**无条件**清 `_active_purpose` /
    `_monitoring_enabled` 并把 F64/UXM 交还 Local —— 嵌套时内层退出就把外层的
    控制权拆了，而外层还在跑：此后外层每条 SCPI 撞 Local 门，同时
    `hal_reload_policy` 的 blocker 消失，`POST /hal/reload` 会在正式执行进行中
    直接放行拆驱动。

    修法不是"禁止嵌套"（那跟校准链冲突：`acquire_sa_power_via_ce_tone` 是三个
    校准服务共用的最内层 primitive，租约必须加在它上面，而一次探头校准要跑
    32 探头 × 2 极化 = 64 次调用，每次 connect/close 的开销不可接受），
    而是**引用计数**：最外层取/放，内层复用、退出不拆。
    """

    def test_inner_exit_does_not_tear_down_the_outer_lease(self):
        """⭐ 本组最要紧的一条：内层退出后，外层必须**仍然**持有控制权。

        变异：把 `hold()` 里的 `if nested: yield; return` 快路径删掉（回到
        每层都走 finally 释放）→ 本条红。
        """
        import asyncio

        from app.services.instrument_test_lease import InstrumentTestLease

        lease = InstrumentTestLease(hal_getter=lambda: None)
        seen = []

        async def _scenario():
            async with lease.hold("outer", control_f64=False, control_uxm=False):
                seen.append(("outer-in", lease.is_active, lease.active_purpose))
                async with lease.hold("inner", control_f64=False, control_uxm=False):
                    seen.append(("inner-in", lease.is_active, lease.active_purpose))
                seen.append(("inner-out", lease.is_active, lease.active_purpose))
            seen.append(("outer-out", lease.is_active, lease.active_purpose))

        asyncio.run(_scenario())

        assert seen == [
            ("outer-in", True, "outer"),
            ("inner-in", True, "outer"),      # 嵌套不改写 active_purpose
            ("inner-out", True, "outer"),     # ★ 内层退出没拆外层
            ("outer-out", False, None),       # 最外层退出才真正释放
        ], f"嵌套租约的生命周期不对: {seen}"

    def test_inner_asking_for_wider_control_fails_loud(self):
        """内层要的控制权比外层宽 → 那台仪表根本没被 acquire，照跑会在第一条
        SCPI 上撞 Local 门。必须当场抛，不静默降级。

        变异：删掉 `widened` 校验 → 本条红。
        """
        import asyncio

        import pytest as _pytest

        from app.services.instrument_test_lease import (
            InstrumentTestLease,
            InstrumentTestLeaseError,
        )

        lease = InstrumentTestLease(hal_getter=lambda: None)

        async def _scenario():
            # 外层只持 UXM，内层却要 F64
            async with lease.hold("outer", control_f64=False, control_uxm=True):
                with _pytest.raises(InstrumentTestLeaseError) as ei:
                    async with lease.hold("inner", control_f64=True, control_uxm=False):
                        pass
                # 拒绝路径不能有副作用：外层必须原样持有
                assert lease.is_active and lease.active_purpose == "outer"
                return str(ei.value)

        msg = asyncio.run(_scenario())
        assert "F64" in msg and "outer" in msg and "inner" in msg

    def test_nested_validator_rechecks_same_frozen_identity_before_body(self):
        """同一 execution 的内层操作仍须在协调锁内复核活动 driver。"""
        import asyncio

        import pytest as _pytest

        from app.services.instrument_test_lease import (
            InstrumentTestLease,
            InstrumentTestLeaseError,
        )

        hal = SimpleNamespace(driver_generation="first", cache_clears=0)

        async def _clear_metrics_cache():
            hal.cache_clears += 1

        hal.clear_metrics_cache = _clear_metrics_cache

        class _Validator:
            validation_identity = "execution-freeze-digest"

            def __call__(self, current_hal):
                if current_hal.driver_generation != "first":
                    return "loaded driver no longer matches frozen execution"
                return None

        lease = InstrumentTestLease(lambda: hal)

        async def _scenario():
            validator = _Validator()
            async with lease.hold(
                "outer",
                control_f64=False,
                control_uxm=False,
                validate_before_remote=validator,
            ):
                assert hal.cache_clears == 1
                hal.driver_generation = "reloaded"
                with _pytest.raises(
                    InstrumentTestLeaseError,
                    match="no longer matches",
                ):
                    async with lease.hold(
                        "inner",
                        control_f64=False,
                        control_uxm=False,
                        validate_before_remote=validator,
                    ):
                        _pytest.fail("driver reload 后不得进入内层硬件操作")
                assert hal.cache_clears == 1

        asyncio.run(_scenario())

    def test_nested_lease_rejects_a_different_frozen_identity(self):
        """嵌套操作不能借用另一 execution 已取得的 Remote 控制。"""
        import asyncio

        import pytest as _pytest

        from app.services.instrument_test_lease import (
            InstrumentTestLease,
            InstrumentTestLeaseError,
        )

        class _Validator:
            def __init__(self, identity):
                self.validation_identity = identity

            def __call__(self, _hal):
                return None

        lease = InstrumentTestLease(lambda: None)

        async def _scenario():
            async with lease.hold(
                "outer",
                control_f64=False,
                control_uxm=False,
                validate_before_remote=_Validator("execution-a"),
            ):
                with _pytest.raises(
                    InstrumentTestLeaseError,
                    match="冻结身份",
                ):
                    async with lease.hold(
                        "inner",
                        control_f64=False,
                        control_uxm=False,
                        validate_before_remote=_Validator("execution-b"),
                    ):
                        pass

        asyncio.run(_scenario())

    def test_park_and_mutation_guard_stay_reentrant(self):
        """反向：可重入不能被一刀切掉 —— `park` / `hal_mutation_guard`
        那条同 task 路径必须照常工作（reload 初始化会走它）。
        """
        import asyncio

        from app.services.instrument_test_lease import InstrumentTestLease

        lease = InstrumentTestLease(hal_getter=lambda: None)

        async def _scenario():
            async with lease.hal_mutation_guard():
                async with lease.hal_mutation_guard():   # 同 task 重入
                    return True
            return False

        assert asyncio.run(_scenario()) is True, (
            "hal_mutation_guard 的同 task 重入被误伤 —— reload→park 那条路会自锁"
        )


class TestOptionalCategoryLease:
    """诊断序列的租约要不要覆盖 optional 依赖 —— 内审 F2/F3。

    **F3（零覆盖）**：`optional_categories` 进租约这条线此前没有任何测试。
    内审把它改回 `lease_categories = set(required)` （= 修之前的原状）后跑
    144 个用例**全绿** —— 上面那条 `test_diagnostic_sequence_holds_lease_...`
    用的探针两个 flag 都是 False，正好绕过这一格。

    **F2（判据不同源）**：租约按 metadata **声明**取，而序列体按
    `ctx.find_binding_by_category_key()` 判**本 lab 绑没绑**。HAL drivers 是
    全局的，线缆直连 lab（无 CE binding）撞上别的 setup 残留的 F64 驱动时，
    只按声明取会把**不属于本 lab** 的 F64 拽进 Remote —— 而手册原文
    （PROPSIM User Reference §20.1）说回 local 要操作员在 GUI 上点按钮，
    我们没法替它回去。
    """

    @staticmethod
    def _make(monkeypatch, *, optional, bound):
        """装一个 optional_categories=<optional>、本 lab 绑了 <bound> 的探针。"""
        import app.api.diagnostic_sequence as api
        from app.diagnostics.protocol import SequenceMetadata, SequenceRunResult

        seen: dict = {}

        class _Context:
            lab_profile_name = "unit-test"
            instrument_bindings: list = []

            def find_binding_by_category_key(self, key):
                return object() if key in bound else None

            def find_binding_by_role(self, _key):
                return None

            def record_run(self, *_args, **_kwargs):
                return SimpleNamespace(
                    id=UUID("00000000-0000-0000-0000-000000000003")
                )

        async def _run(_ctx, _hal, _params, *, log):
            return SequenceRunResult(success=True, summary="ok")

        sequence = SimpleNamespace(
            metadata=SequenceMetadata(
                name="probe", description="probe",
                required_categories=["baseStation"],
                optional_categories=list(optional),
                safe_during_test=True,
            ),
            run=_run,
        )

        @asynccontextmanager
        async def _lease(purpose: str, **kwargs):
            seen.update(kwargs)
            yield

        monkeypatch.setattr(api.loader, "get_sequence", lambda _key: sequence)
        monkeypatch.setattr(
            api, "build_diagnostic_context", lambda *_a, **_k: _Context())
        monkeypatch.setattr(api, "get_hal_service", lambda: object())
        monkeypatch.setattr(api, "instrument_test_lease", _lease, raising=False)
        return api, seen

    @pytest.mark.asyncio
    async def test_optional_category_takes_lease_when_this_lab_binds_it(
        self, monkeypatch
    ):
        """⭐ F3：声明了 optional CE **且本 lab 绑了** → 必须取 F64 租约。

        不取的话 F64 停在 park 后的 Local 态，序列体一调 `stop_emulation()`
        就返 False，报成「F64 状态机异常」——操作员会去查 F64，而真因是
        没给它发钥匙。

        变异：把 `lease_categories` 改回只含 required → 本条红。
        """
        api, seen = self._make(
            monkeypatch,
            optional=["channelEmulator"],
            bound={"baseStation", "channelEmulator"},
        )
        await api.run_diagnostic_sequence(
            "probe", api.RunSequenceRequest(), db=object())

        assert seen["control_f64"] is True, (
            "本 lab 绑了 CE 而租约没取 F64 —— 序列体调它会撞 Local 门"
        )
        assert seen["control_uxm"] is True, "required 的 baseStation 没取"

    @pytest.mark.asyncio
    async def test_optional_category_is_skipped_when_this_lab_does_not_bind_it(
        self, monkeypatch
    ):
        """⭐ F2：声明了 optional CE **但本 lab 没绑** → 不得取 F64 租约。

        线缆直连 lab 就是这一格。取了会：① 把别的 setup 的 F64 拽进 Remote
        且回不去 Local（手册 §20.1：要人在 GUI 上点）；② 那台 F64 不可达时
        acquire 失败抛 InstrumentTestLeaseError，整条序列 aborted ——
        「可选依赖」变成硬前置。

        变异：把 binding 过滤去掉（改回纯 `set(optional)`）→ 本条红。
        """
        api, seen = self._make(
            monkeypatch,
            optional=["channelEmulator"],
            bound={"baseStation"},          # 线缆直连：没有 CE binding
        )
        await api.run_diagnostic_sequence(
            "probe", api.RunSequenceRequest(), db=object())

        assert seen["control_f64"] is False, (
            "本 lab 没绑 CE 却去取了 F64 租约 —— 会把不属于本 lab 的 F64 "
            "拽进 Remote，而手册说它回不去 local 要人去点"
        )
        assert seen["control_uxm"] is True, "required 的 baseStation 仍要取"

    @pytest.mark.asyncio
    async def test_required_category_missing_binding_fails_loud_before_lease(
        self, monkeypatch
    ):
        """反向：required 缺 binding 时**在取租约之前**就 422 fail-loud。

        ⚠ 本条第一版写的是"required 不过 binding 过滤、照样取租约" —— 跑出来
        才发现端点在更早处就拦了（`Sequence 'probe' requires ['baseStation']
        but the lab has no binding for them`）。那才是对的行为：required 是真
        前置，缺了就该当场说清楚，而不是取个租约再到序列体里崩。
        门跟着事实走，不是跟着我预想的走。

        变异：把 required 也套上 binding 过滤（悄悄不取租约、继续往下跑）
        → 本条红（不再抛 422）。
        """
        import fastapi

        api, seen = self._make(
            monkeypatch,
            optional=[],
            bound=set(),                    # 什么都没绑
        )
        with pytest.raises(fastapi.HTTPException) as exc:
            await api.run_diagnostic_sequence(
                "probe", api.RunSequenceRequest(), db=object())

        assert exc.value.status_code == 422
        assert "baseStation" in str(exc.value.detail), (
            "422 没说清缺的是哪个类别 —— 操作员不知道该去绑什么"
        )
        assert seen == {}, "缺 required binding 却仍然取了租约"


class TestCalibrationToneHoldsLease:
    """校准链的共用 primitive 必须自己取 F64 租约 —— 内审 F5。

    HAL 初始化/重载后 `park_idle_instruments()` 把 F64 停回 Local 并立门，
    此后所有 F64 SCPI 直接抛 `F64LocalControlReservedError`。而校准链**不走**
    commissioning 的相位租约，于是「后端启动 → 操作员点路损校准」必然报
    "已交还本地控制" —— 错误文本跟操作员正在做的事完全对不上。

    租约加在 `acquire_sa_power_via_ce_tone` 这个共用 primitive 上，一处覆盖
    三个调用方（quiet_zone 3 处 / probe_calibration 1 处 / path_loss 自己）。

    内审把整圈租约换成 `if True:` 直调 inner 后跑 226 个用例**全绿** ——
    这条修复此前零覆盖。
    """

    @pytest.mark.asyncio
    async def test_tone_acquisition_runs_inside_an_f64_lease(self, monkeypatch):
        """⭐ 行为门：租约必须**包住** inner 的执行，且要 F64 不要 UXM。

        变异：去掉整圈 `async with instrument_test_lease(...)` → 本条红。
        """
        import app.services.path_loss_calibration_service as pl_mod
        from app.schemas.probe_calibration import PolarizationType

        events: list[str] = []
        seen: dict = {}

        @asynccontextmanager
        async def _lease(purpose: str, **kwargs):
            seen["purpose"] = purpose
            seen.update(kwargs)
            events.append("lease-enter")
            try:
                yield
            finally:
                events.append("lease-exit")

        monkeypatch.setattr(
            pl_mod, "instrument_test_lease", _lease, raising=False)
        monkeypatch.setattr(
            "app.services.instrument_test_lease.instrument_test_lease",
            _lease, raising=False)

        svc = pl_mod.ProbePathLossCalibrationService.__new__(
            pl_mod.ProbePathLossCalibrationService)

        async def _inner(**_kw):
            events.append("tone-measured")
            return (-42.0, 0.1, "CE-D")

        svc._acquire_sa_power_via_ce_tone_inner = _inner  # type: ignore[assignment]

        result = await pl_mod.ProbePathLossCalibrationService.\
            acquire_sa_power_via_ce_tone(
                svc, frequency_mhz=3550.0, probe_id=7,
                polarization=PolarizationType.V,
            )

        assert result == (-42.0, 0.1, "CE-D")
        assert events == ["lease-enter", "tone-measured", "lease-exit"], (
            "CE tone 测量没跑在租约里 —— park 之后每次校准都会撞 Local 门，"
            f"实际顺序: {events}"
        )
        assert seen["control_f64"] is True, "没取 F64 控制权，tone 下发会被拒"
        assert seen["control_uxm"] is False, (
            "多取了 UXM 控制权 —— 出 tone 用的是 CE/SG 角色，不该占用小区"
        )
        assert seen["enable_monitoring"] is False, (
            "没关监控 —— 1Hz 轮询会插在 CW tone 功率测量中间抢 SCPI 锁"
        )
        assert "probe7" in seen["purpose"], "租约用途没带探头号，现场看不出是谁在占用"
