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
