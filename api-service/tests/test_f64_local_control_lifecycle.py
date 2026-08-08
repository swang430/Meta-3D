"""F64 Remote/Local control ownership lifecycle.

The F64 enters Remote mode whenever an ATE command arrives.  Returning the
front panel to Local therefore requires more than closing one call site: the
long-lived VISA socket must be closed and background polling must stay
suppressed until the operator explicitly asks for Remote control again.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.hal.base import InstrumentStatus
from app.hal.propsim_f64 import RealPropsimF64Driver


class _Resource:
    def __init__(self) -> None:
        self.closed = False
        self.queries: list[str] = []

    def close(self) -> None:
        self.closed = True

    def query(self, command: str) -> str:
        self.queries.append(command)
        return "unexpected"


class _ResourceManager:
    def __init__(self, resource: _Resource) -> None:
        self.resource = resource

    def open_resource(self, *_args, **_kwargs):
        return self.resource


class _CloseFailResource(_Resource):
    def close(self) -> None:
        raise OSError("close failed")


@pytest.mark.asyncio
async def test_connect_failure_closes_socket_that_already_entered_remote_mode():
    resource = _Resource()
    manager = _ResourceManager(resource)
    driver = RealPropsimF64Driver("f64-connect-cleanup", {"ip": "192.0.2.10"})
    driver._query = AsyncMock(side_effect=RuntimeError("IDN failed"))  # type: ignore[method-assign]

    with patch("pyvisa.ResourceManager", return_value=manager):
        assert await driver.connect() is False

    assert resource.closed is True
    assert driver._visa_resource is None
    assert driver._rm is None


@pytest.mark.asyncio
async def test_release_to_local_is_non_destructive_and_blocks_background_queries():
    resource = _Resource()
    driver = RealPropsimF64Driver("f64-local", {"ip": "192.0.2.10"})
    driver._visa_resource = resource
    driver._rm = object()
    driver._loaded_emulation_file = r"D:\live.smu"
    driver._emulation_running = True

    assert await driver.release_to_local_control() is True

    assert resource.closed is True
    assert driver._visa_resource is None
    assert driver._rm is None
    assert driver.local_control_reserved is True
    # No GOS / CLOSE / other ATE command may be sent while handing control
    # back; closing the socket is the complete remote-side action.
    assert resource.queries == []

    metrics = await driver.get_metrics()
    assert metrics.metrics["control_mode"] == "ate_socket_released"
    assert metrics.metrics["remote_polling_suppressed"] is True
    assert resource.queries == []


@pytest.mark.asyncio
async def test_remote_control_must_be_explicitly_reacquired():
    driver = RealPropsimF64Driver("f64-reacquire", {"ip": "192.0.2.10"})
    driver._local_control_reserved = True
    driver.connect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    assert await driver.acquire_remote_control() is True
    assert driver.local_control_reserved is False
    driver.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_remote_reacquire_keeps_local_reservation():
    driver = RealPropsimF64Driver("f64-reacquire-fail", {"ip": "192.0.2.10"})
    driver._local_control_reserved = True
    driver.connect = AsyncMock(return_value=False)  # type: ignore[method-assign]

    assert await driver.acquire_remote_control() is False
    assert driver.local_control_reserved is True


@pytest.mark.asyncio
async def test_release_close_failure_retains_handle_for_retry():
    driver = RealPropsimF64Driver("f64", {"ip": "192.0.2.1"})
    resource = _CloseFailResource()
    driver._visa_resource = resource

    assert await driver.release_to_local_control() is False
    assert driver._visa_resource is resource
    assert driver.local_control_reserved is True
    assert driver.local_release_failed is True


@pytest.mark.asyncio
async def test_remote_acquire_is_idempotent_when_session_is_already_ready():
    driver = RealPropsimF64Driver("f64", {"ip": "192.0.2.1"})
    driver._visa_resource = _Resource()
    driver._status = InstrumentStatus.READY
    driver.connect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    assert await driver.acquire_remote_control() is True
    driver.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_connect_closes_socket_opened_before_handshake():
    resource = _Resource()
    manager = _ResourceManager(resource)
    driver = RealPropsimF64Driver("f64", {"ip": "192.0.2.1"})
    driver._query = AsyncMock(side_effect=asyncio.CancelledError())  # type: ignore[method-assign]

    with patch("pyvisa.ResourceManager", return_value=manager):
        with pytest.raises(asyncio.CancelledError):
            await driver.connect()

    assert resource.closed is True
    assert driver._visa_resource is None


@pytest.mark.asyncio
@pytest.mark.parametrize("state,expected", [("STOPPED", True), ("EDITING", False)])
async def test_load_confirmation_only_accepts_stopped_steady_state(state, expected):
    driver = RealPropsimF64Driver("f64", {"ip": "192.0.2.1"})
    driver._visa_resource = _Resource()
    driver._loaded_emulation_file = r"D:\x.smu"
    driver._query_simulation_state = AsyncMock(return_value=state)  # type: ignore[method-assign]
    driver._apply_state_truth_confirmed = AsyncMock(  # type: ignore[method-assign]
        return_value=(False, state)
    )

    result = await driver.confirm_scenario_loaded()
    assert result["confirmed"] is expected


@pytest.mark.asyncio
async def test_cancelled_local_release_marks_handoff_unconfirmed_and_keeps_handle():
    driver = RealPropsimF64Driver("f64", {"ip": "192.0.2.1"})
    resource = _Resource()
    driver._visa_resource = resource

    with patch(
        "app.hal.propsim_f64.asyncio.to_thread",
        AsyncMock(side_effect=asyncio.CancelledError()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await driver.release_to_local_control()

    assert driver.local_control_reserved is True
    assert driver.local_release_failed is True
    assert driver._visa_resource is resource


@pytest.mark.asyncio
async def test_cancelled_remote_acquire_restores_local_reservation():
    driver = RealPropsimF64Driver("f64", {"ip": "192.0.2.1"})
    driver._local_control_reserved = True
    driver.connect = AsyncMock(side_effect=asyncio.CancelledError())  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await driver.acquire_remote_control()

    assert driver.local_control_reserved is True


# ── Local 门的生效端 —— 内审 F3：4 个生效端 3 个零覆盖 ──────────────
#
# `release_to_local_control()` 存在的**唯一理由**是让操作员能拿回前面板。
# 它靠的不是一条 SCPI（手册说回 Local 要人在 F64 GUI 上点），而是我们这端
# 关掉 socket 并把 `_local_control_reserved` 立成门，此后所有出口一律拒绝。
# 门有五个出口，下面三个此前**零覆盖**（内审造的 M2/M3/M4 变异全绿）。


@pytest.mark.asyncio
async def test_silent_reconnect_must_not_steal_remote_back():
    """⭐ 最要命的一个：后台静默重连**不得**夺回 Remote。

    F64 收到任何一条 ATE 命令就进 Remote。若懒重连在 Local 保留期间重建会话，
    操作员正在面板上操作时会被后台一声不响地抢走控制权 —— 而这正是
    `release_to_local_control` 要防的那件事，它却一直没有门。

    变异：把 `_silent_reconnect_visa` 里的 `if self._local_control_reserved:`
    去掉 → 本条红（会话被重建、Remote 被夺回）。
    """
    # ⚠ 必须用 close 失败那条路。正常 release 会把 `_rm` 也置 None，而
    #   `_silent_reconnect_visa` 里 Local 检查的**下一行**就是
    #   `if self._rm is None: return False` —— 两道拦截，去掉 Local 那道另一道
    #   还在，变异照样全绿（实测过）。close 失败时句柄与 `_rm` 都保留
    #   （见 test_release_close_failure_retains_handle_for_retry），
    #   这才造出「Local 保留 + 资源还在」这个唯一分得开的状态。
    resource = _CloseFailResource()
    driver = RealPropsimF64Driver("f64-local", {"ip": "192.0.2.10"})
    driver._visa_resource = resource
    driver._rm = _ResourceManager(resource)

    assert await driver.release_to_local_control() is False
    assert driver.local_control_reserved is True
    assert driver._visa_resource is resource, "夹具前提错了：本例要资源仍在"

    # ⚠ 判据不能用返回值：门失效时它会真去连 192.0.2.10、连不上照样返回 False，
    #   `rebuilt is False` 在"拦住了"和"没拦住但连接失败"下**都成立**（实测：
    #   去掉门之后本条仍绿）。要问的是**它有没有动手去连** —— 那才是
    #   "会不会把 F64 拽回 Remote" 的生效端。
    attempts: list[str] = []

    def _tracking_open(*args, **kwargs):
        attempts.append(str(args))
        return resource

    with patch("pyvisa.ResourceManager") as rm_cls:
        rm_cls.return_value.open_resource.side_effect = _tracking_open
        rebuilt = await driver._silent_reconnect_visa()

    assert attempts == [], (
        f"Local 保留期间静默重连仍去开了 VISA 会话 ({attempts}) —— "
        "F64 收到任何 ATE 命令即进 Remote，操作员的前面板会被后台抢走"
    )
    assert rebuilt is False
    assert driver.local_control_reserved is True, "Local 保留被重连清掉了"
    assert resource.queries == [], "Local 期间不得有任何 ATE 往返"


@pytest.mark.asyncio
async def test_scpi_write_and_query_are_refused_while_local_is_reserved():
    """⭐ 拒绝必须是**抛异常**，不是静默返回空 —— 静默会让调用方
    把"没发出去"当成"发了没结果"，在报告里变成一个看不出来的空洞。

    变异：把 `_do_write` / `_do_query` 里的 `raise` 改成 `return None`
    → 本条红。
    """
    from app.hal.propsim_f64 import F64LocalControlReservedError

    resource = _Resource()
    driver = RealPropsimF64Driver("f64-local", {"ip": "192.0.2.10"})
    driver._visa_resource = resource
    driver._rm = object()
    await driver.release_to_local_control()

    with pytest.raises(F64LocalControlReservedError):
        await driver._do_write("OUTP:LEV:AMP:CH 1,-50.00")
    with pytest.raises(F64LocalControlReservedError):
        await driver._do_query("DIAG:SIMU:STATE?")

    assert resource.queries == [], "被拒的命令仍然发到了仪器上"


# ⛔ 没有为 `confirm_scenario_loaded` 的 Local 分支立门 —— 那处检查是**冗余**的：
#    去掉 `self._local_control_reserved or` 之后，往下走会撞 `_do_query` 的
#    Local 门抛异常、被 catch 成 confirmed=False，行为一模一样（变异实测全绿）。
#    给一个恒绿的断言起个名字，只会让人以为那里有保护。真正的底线是下面那条
#    `_do_write` / `_do_query` 门，它是五个生效端里唯一变异会红的。
