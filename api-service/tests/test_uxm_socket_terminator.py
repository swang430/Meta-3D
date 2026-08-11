from unittest.mock import MagicMock

import pytest

from app.hal.uxm_base_station import RealUxmDriver


class _Session:
    def __init__(self):
        self.read_termination = None
        self.write_termination = None
        self.closed = False

    def query(self, command):
        return {
            "*IDN?": "Keysight Technologies,E7515B TAF,MY123,1.0",
            "SYSTem:APPLication:NAME?": "LTE_NR_IRAT",
            "*OPC?": "1",
        }.get(command.strip(), "0")

    def write(self, _command):
        return None

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_lowercase_socket_resource_sets_terminators_on_connect(monkeypatch):
    driver = RealUxmDriver(
        "uxm-lower-socket",
        {"visa_resource": "TCPIP0::10.0.0.9::5125::socket"},
    )
    session = _Session()
    rm = MagicMock()
    rm.open_resource.return_value = session
    monkeypatch.setattr("pyvisa.ResourceManager", MagicMock(return_value=rm))
    monkeypatch.setattr(driver, "_probe_platform_identity", lambda _resource: None)

    assert await driver.connect() is True
    assert session.read_termination == "\n"
    assert session.write_termination == "\n"


def test_lowercase_socket_resource_sets_terminators_on_silent_reconnect():
    driver = RealUxmDriver("uxm-reconnect", {"ip": "10.0.0.9"})
    replacement = _Session()
    rm = MagicMock()
    rm.open_resource.return_value = replacement
    driver._visa_rm = rm
    driver._active_resource_string = "TCPIP0::10.0.0.9::5125::socket"

    assert driver._silent_reconnect_visa() is True
    assert replacement.read_termination == "\n"
    assert replacement.write_termination == "\n"


@pytest.mark.asyncio
async def test_socket_in_hislip_hostname_does_not_set_raw_terminators(monkeypatch):
    driver = RealUxmDriver(
        "uxm-hislip-hostname",
        {"visa_resource": "TCPIP0::uxm-socket-lab::hislip2::INSTR"},
    )
    session = _Session()
    rm = MagicMock()
    rm.open_resource.return_value = session
    monkeypatch.setattr("pyvisa.ResourceManager", MagicMock(return_value=rm))
    monkeypatch.setattr(driver, "_probe_platform_identity", lambda _resource: None)

    assert await driver.connect() is True
    assert session.read_termination is None
    assert session.write_termination is None


def test_socket_in_hislip_hostname_does_not_set_terminators_on_reconnect():
    driver = RealUxmDriver("uxm-hislip-reconnect", {"ip": "uxm-socket-lab"})
    replacement = _Session()
    rm = MagicMock()
    rm.open_resource.return_value = replacement
    driver._visa_rm = rm
    driver._active_resource_string = "TCPIP0::uxm-socket-lab::hislip2::INSTR"

    assert driver._silent_reconnect_visa() is True
    assert replacement.read_termination is None
    assert replacement.write_termination is None
