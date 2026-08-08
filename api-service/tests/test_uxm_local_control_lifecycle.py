"""UXM 空闲控制权生命周期。

UXM 手册没有证实可切回 Local 的 SCPI，因此交接只能关闭本进程持有的
VISA/HiSLIP 会话；不得顺带停小区、停信令或发送任何查询。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.hal.base import InstrumentStatus
from app.hal.uxm_base_station import RealUxmDriver, UxmLocalControlReservedError


class _Session:
    def __init__(self, *, close_error: Exception | None = None) -> None:
        self.close_error = close_error
        self.closed = False
        self.writes: list[str] = []
        self.queries: list[str] = []

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        self.queries.append(command)
        return "unexpected"


class _ResourceManager:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def open_resource(self, *_args, **_kwargs):
        return self.session


@pytest.mark.asyncio
async def test_release_to_local_only_closes_control_session_without_stopping_cell():
    session = _Session()
    driver = RealUxmDriver("uxm-local", {"ip": "192.0.2.20"})
    driver._visa_session = session
    driver._visa_rm = object()
    driver._status = InstrumentStatus.READY
    driver.stop_signaling = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("Local 交接不得停止小区或信令")
    )

    assert await driver.release_to_local_control() is True

    assert session.closed is True
    assert session.writes == []
    assert session.queries == []
    assert driver._visa_session is None
    assert driver._visa_rm is None
    assert driver.local_control_reserved is True
    assert driver.status == InstrumentStatus.DISCONNECTED
    driver.stop_signaling.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_reservation_blocks_queries_writes_and_silent_reconnect():
    session = _Session()
    driver = RealUxmDriver("uxm-local", {"ip": "192.0.2.20"})
    driver._visa_session = session
    driver._visa_rm = object()
    driver._active_resource_string = "TCPIP::192.0.2.20::hislip2::INSTR"
    driver._local_control_reserved = True

    with pytest.raises(UxmLocalControlReservedError):
        driver._do_query("*IDN?")
    with pytest.raises(UxmLocalControlReservedError):
        driver._do_write("*CLS")

    assert driver._silent_reconnect_visa() is False
    assert session.writes == []
    assert session.queries == []


@pytest.mark.asyncio
async def test_metrics_are_scpi_free_while_local_control_is_reserved():
    driver = RealUxmDriver("uxm-local", {"ip": "192.0.2.20"})
    driver._local_control_reserved = True
    driver.get_cell_state = AsyncMock(  # type: ignore[method-assign]
        side_effect=AssertionError("空闲 Local 状态不得轮询 UXM")
    )

    metrics = await driver.get_metrics()

    assert metrics.metrics == {
        "control_mode": "ate_socket_released",
        "remote_polling_suppressed": True,
    }
    driver.get_cell_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_remote_control_is_reacquired_only_for_explicit_operation():
    driver = RealUxmDriver("uxm-reacquire", {"ip": "192.0.2.20"})
    driver._local_control_reserved = True
    driver.connect = AsyncMock(return_value=True)  # type: ignore[method-assign]

    assert await driver.acquire_remote_control() is True
    assert driver.local_control_reserved is False
    driver.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_or_cancelled_reacquire_restores_local_reservation():
    driver = RealUxmDriver("uxm-reacquire", {"ip": "192.0.2.20"})
    driver._local_control_reserved = True
    driver.connect = AsyncMock(return_value=False)  # type: ignore[method-assign]

    assert await driver.acquire_remote_control() is False
    assert driver.local_control_reserved is True

    driver.connect = AsyncMock(side_effect=asyncio.CancelledError())  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        await driver.acquire_remote_control()
    assert driver.local_control_reserved is True


@pytest.mark.asyncio
async def test_failed_session_close_keeps_local_gate_and_handle_for_retry():
    session = _Session(close_error=OSError("close failed"))
    driver = RealUxmDriver("uxm-local", {"ip": "192.0.2.20"})
    driver._visa_session = session

    assert await driver.release_to_local_control() is False
    assert driver.local_control_reserved is True
    assert driver.local_release_failed is True
    assert driver._visa_session is session


@pytest.mark.asyncio
async def test_cancelled_session_close_keeps_local_gate_and_handle():
    session = _Session()
    driver = RealUxmDriver("uxm-local", {"ip": "192.0.2.20"})
    driver._visa_session = session

    with patch(
        "app.hal.uxm_base_station.asyncio.to_thread",
        AsyncMock(side_effect=asyncio.CancelledError()),
    ):
        with pytest.raises(asyncio.CancelledError):
            await driver.release_to_local_control()

    assert driver.local_control_reserved is True
    assert driver.local_release_failed is True
    assert driver._visa_session is session


@pytest.mark.asyncio
async def test_connect_handshake_failure_closes_unregistered_session():
    session = _Session()
    driver = RealUxmDriver("uxm-connect", {"ip": "192.0.2.20"})
    driver._query = MagicMock(side_effect=RuntimeError("IDN failed"))  # type: ignore[method-assign]

    with patch("pyvisa.ResourceManager", return_value=_ResourceManager(session)):
        assert await driver.connect() is False

    assert session.closed is True
    assert driver._visa_session is None
    assert driver._visa_rm is None


@pytest.mark.asyncio
async def test_cancelled_connect_closes_unregistered_session():
    session = _Session()
    driver = RealUxmDriver("uxm-connect", {"ip": "192.0.2.20"})
    driver._query = MagicMock(side_effect=asyncio.CancelledError())  # type: ignore[method-assign]

    with patch("pyvisa.ResourceManager", return_value=_ResourceManager(session)):
        with pytest.raises(asyncio.CancelledError):
            await driver.connect()

    assert session.closed is True
    assert driver._visa_session is None
    assert driver._visa_rm is None
