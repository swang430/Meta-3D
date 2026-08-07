"""仪表测试租约：空闲不轮询，测试结束归还 F64 前面板控制。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest


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
async def test_lease_is_visible_while_remote_acquire_is_still_in_progress():
    from app.services.instrument_test_lease import InstrumentTestLease

    entered = asyncio.Event()
    release = asyncio.Event()

    class _SlowUxm(_FakeUxm):
        async def acquire_remote_control(self) -> bool:
            self.events.append("uxm-remote")
            entered.set()
            await release.wait()
            return True

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

    class _DB:
        def close(self) -> None:
            events.append("db-close")

    @asynccontextmanager
    async def _lease(purpose: str, **kwargs):
        events.append(f"lease-enter:{purpose}:{kwargs}")
        try:
            yield
        finally:
            events.append("lease-exit")

    async def _loop(_db, _execution_id) -> None:
        events.append("case-loop")

    monkeypatch.setattr(runner, "SessionLocal", _DB)
    monkeypatch.setattr(runner, "instrument_test_lease", _lease)
    monkeypatch.setattr(runner, "_run_case_loop", _loop)

    execution_id = "00000000-0000-0000-0000-000000000001"
    await runner._run_case(execution_id)

    assert events == [
        f"lease-enter:formal-case:{execution_id}:{{}}",
        "case-loop",
        "lease-exit",
        "db-close",
    ]


@pytest.mark.asyncio
async def test_formal_case_is_failed_when_local_handoff_fails_after_success(
    monkeypatch,
):
    from contextlib import asynccontextmanager

    import app.services.test_case_runner as runner
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    execution = SimpleNamespace(status="running", config={}, completed_at=None)

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

        def close(self):
            pass

    @asynccontextmanager
    async def _lease(_purpose):
        yield
        raise InstrumentTestLeaseError("Local 交接失败")

    async def _loop(_db, _execution_id):
        execution.status = "completed"

    monkeypatch.setattr(runner, "SessionLocal", _DB)
    monkeypatch.setattr(runner, "instrument_test_lease", _lease)
    monkeypatch.setattr(runner, "_run_case_loop", _loop)
    monkeypatch.setattr(runner, "flag_modified", lambda *_args: None)
    monkeypatch.setattr(runner, "_finalize_scpi_acceptance", lambda _ex: None)

    await runner._run_case(UUID("00000000-0000-0000-0000-000000000003"))

    assert execution.status == "failed"
    assert execution.config["local_control_handoff_failed"] is True


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
