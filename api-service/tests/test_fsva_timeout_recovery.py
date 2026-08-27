"""FSVA 超时恢复：未完成 sweep 不得拖死后续 SCPI 会话。"""
from __future__ import annotations

import asyncio

import pyvisa
import pytest

from app.hal.rs_fsva import FsvaScpi, RealRsFsvaDriver


class _TriggerTimeoutSession:
    def __init__(self) -> None:
        self.timeout = 15000
        self.written: list[str] = []
        self.queried: list[str] = []

    def write(self, command: str) -> None:
        self.written.append(command.strip())

    def query(self, command: str) -> str:
        command = command.strip()
        self.queried.append(command)
        if command == FsvaScpi.TRIG:
            raise TimeoutError("sweep did not complete")
        raise AssertionError(f"unexpected query after trigger timeout: {command}")


@pytest.mark.parametrize(
    "operation",
    [
        lambda driver: driver.measure_channel_power(20e6),
        lambda driver: driver.measure_peak(),
        lambda driver: driver.get_trace(),
    ],
    ids=["channel-power", "peak", "trace"],
)
def test_trigger_timeout_aborts_current_measurement(operation):
    session = _TriggerTimeoutSession()
    driver = RealRsFsvaDriver("fsva-timeout", {"ip": "192.0.2.10"})
    driver._visa_session = session

    asyncio.run(operation(driver))

    assert FsvaScpi.ABORT in session.written


class _IdentityTimeoutSession:
    def __init__(self) -> None:
        self.read_termination = None
        self.write_termination = None
        self.closed = False

    def query(self, _command: str) -> str:
        raise TimeoutError("identity query timed out")

    def close(self) -> None:
        self.closed = True


class _FakeResourceManager:
    def __init__(self, session: _IdentityTimeoutSession) -> None:
        self.session = session

    def open_resource(self, _resource: str, **_kwargs):
        return self.session


def test_connect_identity_timeout_closes_its_opened_session(monkeypatch):
    session = _IdentityTimeoutSession()
    manager = _FakeResourceManager(session)
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda _backend: manager)
    driver = RealRsFsvaDriver("fsva-connect-timeout", {"ip": "192.0.2.10"})

    assert asyncio.run(driver.connect()) is False

    assert session.closed is True
    assert driver._visa_session is None
