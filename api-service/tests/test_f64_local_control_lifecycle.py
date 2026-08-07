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
    assert metrics.metrics["control_mode"] == "local"
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
