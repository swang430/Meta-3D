"""P1-73B Task 9：CMW500 LTE 状态转换必须保守确认。"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.hal.base_station import (
    BaseStationControlReleaseResult,
    BaseStationRemoteSessionResult,
    CellState,
)
from app.hal.cmw500_base_station import RealCmw500Driver


class _Session:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.queries: list[str] = []
        self.writes: list[str] = []
        self.closed = False
        self.timeout = 5000

    def query(self, command: str) -> str:
        self.queries.append(command)
        return self.responses[command]

    def write(self, command: str) -> None:
        self.writes.append(command)

    def close(self) -> None:
        self.closed = True


class _ResourceManager:
    def __init__(self, session: _Session):
        self.session = session

    def open_resource(self, _resource: str, **_kwargs) -> _Session:
        return self.session


class _StateDriver(RealCmw500Driver):
    def __init__(self, responses: dict[str, str]):
        super().__init__("cmw-state", {"ip_address": "192.0.2.10"})
        self.responses = responses
        self.writes: list[str] = []
        self.queries: list[str] = []
        self._visa_session = _Session({})

    def _do_write(self, command: str) -> None:
        self.writes.append(command)

    def _do_query(self, command: str) -> str:
        self.queries.append(command)
        return self.responses[command]


def _identity_responses() -> dict[str, str]:
    return {
        "*IDN?": "Rohde&Schwarz,CMW,1201.0002K50/123456,4.0.250",
        "SYSTem:BASE:OPTion:LIST? SWOPtion,VALid": "CMW-KS520",
        "SYSTem:BASE:OPTion:LIST? HWOPtion,FUNCtional": "CMW-B570B",
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
    }


@pytest.mark.asyncio
async def test_each_real_connect_creates_a_new_opaque_session_token():
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    first = _Session(_identity_responses())
    second = _Session(_identity_responses())

    with patch("pyvisa.ResourceManager", return_value=_ResourceManager(first)):
        assert await driver.connect() is True
    acquired = await driver.acquire_remote_control()

    assert isinstance(acquired, BaseStationRemoteSessionResult)
    assert acquired.adapter_id == "cmw500"
    assert acquired.acquired_confirmed is True
    assert acquired.session_token

    first_token = acquired.session_token
    released = await driver.release_remote_session(first_token, lease_id="lease-1")
    assert released.transport_session_released_confirmed is True

    with patch("pyvisa.ResourceManager", return_value=_ResourceManager(second)):
        assert await driver.connect() is True
    reacquired = await driver.acquire_remote_control()
    assert reacquired.session_token != first_token


@pytest.mark.asyncio
async def test_release_token_mismatch_still_closes_transport_but_is_not_confirmed():
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    session = _Session(_identity_responses())
    with patch("pyvisa.ResourceManager", return_value=_ResourceManager(session)):
        assert await driver.connect() is True

    result = await driver.release_remote_session(
        "wrong-token",
        measurement_attempt_id="attempt-1",
        lease_id="lease-1",
    )

    assert isinstance(result, BaseStationControlReleaseResult)
    assert session.closed is True
    assert result.measurement_attempt_id == "attempt-1"
    assert result.transport_session_released_confirmed is False
    assert result.front_panel_local_confirmed is None
    assert any("token" in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
async def test_acquire_does_not_transparently_reconnect_a_half_present_session_identity():
    class _NoReconnectDriver(RealCmw500Driver):
        async def connect(self) -> bool:
            raise AssertionError("must not transparently reconnect")

    driver = _NoReconnectDriver("cmw", {"ip_address": "192.0.2.10"})
    existing_session = _Session({})
    driver._visa_session = existing_session
    driver._session_token = None

    result = await driver.acquire_remote_control()

    assert result.acquired_confirmed is False
    assert result.session_token == ""
    assert driver._visa_session is existing_session


@pytest.mark.asyncio
async def test_connect_is_idempotent_for_an_active_session_and_preserves_token():
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    session = _Session(_identity_responses())
    with patch("pyvisa.ResourceManager", return_value=_ResourceManager(session)):
        assert await driver.connect() is True
    token = driver._session_token

    with patch("pyvisa.ResourceManager", side_effect=AssertionError("no reconnect")):
        assert await driver.connect() is True

    assert driver._visa_session is session
    assert driver._session_token == token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial_state", "expected_writes", "expected"),
    [
        ("OFF,ADJ", [], True),
        ("ON,ADJ", ["SOURce:LTE:SIGN1:CELL:STATe OFF"], True),
        ("UNKNOWN,ADJ", [], False),
    ],
)
async def test_safe_idle_requires_exact_state_and_confirms_any_off_write(
    initial_state, expected_writes, expected
):
    states = [initial_state]
    if initial_state == "ON,ADJ":
        states.append("OFF,ADJ")

    class _SequenceDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command == "SOURce:LTE:SIGN1:CELL:STATe:ALL?":
                return states.pop(0)
            return self.responses[command]

    driver = _SequenceDriver(
        {"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'}
    )

    assert await driver.ensure_safe_idle() is expected
    assert driver.writes == expected_writes
    if initial_state == "ON,ADJ":
        assert driver.queries == [
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
            "*OPC?",
            "SYSTem:ERRor:ALL?",
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        ]


@pytest.mark.asyncio
async def test_config_error_queue_failure_does_not_update_cached_working_point():
    driver = _StateDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "*OPC?": "1",
            "SYSTem:ERRor:ALL?": '-221,"Settings conflict"',
        }
    )
    original = (driver._band, driver._earfcn, driver._bandwidth_mhz)

    result = await driver.set_cell_config(
        {"band": "B7", "earfcn": 2850, "bandwidth_mhz": 10.0}
    )

    assert result is False
    assert (driver._band, driver._earfcn, driver._bandwidth_mhz) == original
    assert driver.queries == [
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        "*OPC?",
        "SYSTem:ERRor:ALL?",
    ]


@pytest.mark.asyncio
async def test_config_requires_authoritative_readback_before_updating_cache():
    driver = _StateDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "*OPC?": "1",
            "SYSTem:ERRor:ALL?": '0,"No error"',
            "CONFigure:LTE:SIGN1:BAND?": "OB3",
            "CONFigure:LTE:SIGN1:CELL:BANDwidth:DL?": "B100",
            "CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL?": "1300",
            "CONFigure:LTE:SIGN1:DMODe?": "FDD",
        }
    )
    original = (driver._band, driver._earfcn, driver._bandwidth_mhz)

    result = await driver.set_cell_config(
        {
            "band": "B3",
            "earfcn": 1300,
            "bandwidth_mhz": 20.0,
            "duplex": "FDD",
        }
    )

    assert result is False
    assert (driver._band, driver._earfcn, driver._bandwidth_mhz) == original
    assert driver.queries[-4:] == [
        "CONFigure:LTE:SIGN1:BAND?",
        "CONFigure:LTE:SIGN1:CELL:BANDwidth:DL?",
        "CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL?",
        "CONFigure:LTE:SIGN1:DMODe?",
    ]


@pytest.mark.asyncio
async def test_config_requires_applied_two_antenna_readback_for_two_layers():
    driver = _StateDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "*OPC?": "1",
            "SYSTem:ERRor:ALL?": '0,"No error"',
            "CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL?": "1300",
            "CONFigure:LTE:SIGN1:CONNection:PCC:NENBantennas?": "FOUR",
        }
    )
    original = (driver._band, driver._earfcn, driver._bandwidth_mhz)

    result = await driver.set_cell_config(
        {"earfcn": 1300, "mimo_layers": 2}
    )

    assert result is False
    assert (driver._band, driver._earfcn, driver._bandwidth_mhz) == original
    assert (
        "CONFigure:LTE:SIGN1:CONNection:PCC:NENBantennas TWO"
        in driver.writes
    )
    assert driver.queries[-1] == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:NENBantennas?"
    )


@pytest.mark.asyncio
async def test_config_requires_exact_applied_lte_transmission_mode():
    driver = _StateDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "*OPC?": "1",
            "SYSTem:ERRor:ALL?": '0,"No error"',
            "CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL?": "1300",
            "CONFigure:LTE:SIGN1:CONNection:PCC:TRANsmission?": "TM4",
        }
    )
    original = (driver._band, driver._earfcn, driver._bandwidth_mhz)

    result = await driver.set_cell_config(
        {"earfcn": 1300, "lte_transmission_mode": "TM3"}
    )

    assert result is False
    assert (driver._band, driver._earfcn, driver._bandwidth_mhz) == original
    assert (
        "CONFigure:LTE:SIGN1:CONNection:PCC:TRANsmission TM3"
        in driver.writes
    )
    assert driver.queries[-1] == (
        "CONFigure:LTE:SIGN1:CONNection:PCC:TRANsmission?"
    )


@pytest.mark.asyncio
async def test_config_requires_exact_applied_downlink_rs_epre():
    driver = _StateDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "*OPC?": "1",
            "SYSTem:ERRor:ALL?": '0,"No error"',
            "CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL?": "1300",
            "CONFigure:LTE:SIGN1:DL:RSEPre:LEVel?": "-64.25",
        }
    )
    original = driver._dl_power_dbm

    result = await driver.set_cell_config(
        {"earfcn": 1300, "dl_power_dbm": -65.25}
    )

    assert result is False
    assert driver._dl_power_dbm == original
    assert "CONFigure:LTE:SIGN1:DL:RSEPre:LEVel -65.25" in driver.writes
    assert driver.queries[-1] == "CONFigure:LTE:SIGN1:DL:RSEPre:LEVel?"


@pytest.mark.asyncio
async def test_attach_accepts_only_documented_exact_states_and_restores_timeout():
    states = iter(["ON,ADJ", "ATT", "CEST"])

    class _AttachDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command in {
                "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
                "FETCh:LTE:SIGN1:PSWitched:STATe?",
            }:
                return next(states)
            return self.responses[command]

    driver = _AttachDriver(
        {"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'}
    )
    original_timeout = driver._visa_session.timeout

    async def _no_sleep(_seconds: float) -> None:
        return None

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        assert await driver.start_signaling(timeout_s=3.0) is True

    assert driver._visa_session.timeout == original_timeout
    assert "CALL:LTE:SIGN1:PSWitched:ACTion CONNect" in driver.writes
    assert all("ETABlish" not in command for command in driver.writes)
    assert driver._cell_state is CellState.CONNECTED


@pytest.mark.asyncio
async def test_connect_action_polls_documented_transitional_state_without_resending():
    states = iter(["ON,ADJ", "ATT", "CONN", "CEST"])

    class _ConnectingDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command in {
                "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
                "FETCh:LTE:SIGN1:PSWitched:STATe?",
            }:
                return next(states)
            return self.responses[command]

    driver = _ConnectingDriver(
        {"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'}
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        assert await driver.start_signaling(timeout_s=3.0) is True

    assert driver.writes.count(
        "CALL:LTE:SIGN1:PSWitched:ACTion CONNect"
    ) == 1
    assert driver._cell_state is CellState.CONNECTED


@pytest.mark.asyncio
async def test_cell_on_polls_pending_sync_state_without_resending():
    states = iter(["ON,PEND", "ON,ADJ", "ATT", "CEST"])

    class _PendingCellDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command in {
                "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
                "FETCh:LTE:SIGN1:PSWitched:STATe?",
            }:
                return next(states)
            return self.responses[command]

    driver = _PendingCellDriver(
        {"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'}
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        assert await driver.start_signaling(timeout_s=3.0) is True

    assert driver.writes.count("SOURce:LTE:SIGN1:CELL:STATe ON") == 1
    assert driver._cell_state is CellState.CONNECTED


def test_ps_state_parser_rejects_substrings_and_keeps_attached_distinct_from_connected():
    assert RealCmw500Driver._parse_ps_state("UNATTACHED") is None
    assert RealCmw500Driver._parse_ps_state("ATT") == "ATTACHED"
    assert RealCmw500Driver._parse_ps_state("ATTached") == "ATTACHED"
    assert RealCmw500Driver._parse_ps_state("CEST") == "CONNECTED"
    assert RealCmw500Driver._parse_ps_state("CESTablished") == "CONNECTED"


@pytest.mark.asyncio
async def test_get_ue_info_uses_live_ps_state_instead_of_cached_connected():
    driver = _StateDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "ON,ADJ",
            "FETCh:LTE:SIGN1:PSWitched:STATe?": "ATT",
            "SENSe:LTE:SIGN1:RRCState?": "CONN",
        }
    )
    driver._cell_state = CellState.CONNECTED

    info = await driver.get_ue_info()

    assert info["connected"] is False
    assert info["rrc_state"] == "CONN"


@pytest.mark.asyncio
async def test_unknown_attach_state_fails_and_performs_confirmed_safe_cleanup():
    cell_states = iter(["ON,ADJ", "OFF,ADJ"])

    class _UnknownAttachDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command == "SOURce:LTE:SIGN1:CELL:STATe:ALL?":
                return next(cell_states)
            return self.responses[command]

    driver = _UnknownAttachDriver(
        {
            "*OPC?": "1",
            "SYSTem:ERRor:ALL?": '0,"No error"',
            "FETCh:LTE:SIGN1:PSWitched:STATe?": "UNATTACHED",
        }
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        assert await driver.start_signaling(timeout_s=3.0) is False

    assert driver.writes[-1] == "SOURce:LTE:SIGN1:CELL:STATe OFF"
    assert driver._cell_state is CellState.OFF


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["frc", "power"])
async def test_remaining_configuration_writes_stop_before_io_when_safe_idle_is_unknown(
    operation
):
    driver = _StateDriver(
        {"SOURce:LTE:SIGN1:CELL:STATe:ALL?": "UNKNOWN,ADJ"}
    )

    if operation == "frc":
        result = await driver.set_frc_config("R.0")
    else:
        result = await driver.set_downlink_power(-45.0)

    assert result is False
    assert driver.writes == []


@pytest.mark.asyncio
async def test_cell_on_rejection_still_attempts_and_confirms_cell_off():
    errors = iter(['-221,"Settings conflict"', '0,"No error"'])

    class _RejectedCellDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command == "SYSTem:ERRor:ALL?":
                return next(errors)
            return self.responses[command]

    driver = _RejectedCellDriver(
        {
            "*OPC?": "1",
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
        }
    )

    assert await driver.start_signaling(timeout_s=3.0) is False

    assert driver.writes == [
        "SOURce:LTE:SIGN1:CELL:STATe ON",
        "SOURce:LTE:SIGN1:CELL:STATe OFF",
    ]
    assert driver._cell_state is CellState.OFF


@pytest.mark.asyncio
async def test_disconnect_preserves_transport_when_safe_cleanup_is_unconfirmed():
    class _CleanupFailureDriver(_StateDriver):
        async def ensure_safe_idle(self) -> bool:
            return False

    driver = _CleanupFailureDriver({})
    session = driver._visa_session
    driver._cell_state = CellState.CONNECTED

    assert await driver.disconnect() is False
    assert session.closed is False
    assert driver._visa_session is session


@pytest.mark.asyncio
async def test_disconnect_reads_live_cell_state_when_cache_still_says_off():
    cell_states = iter(["ON,ADJ", "OFF,ADJ"])

    class _LiveCellDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command == "SOURce:LTE:SIGN1:CELL:STATe:ALL?":
                return next(cell_states)
            return self.responses[command]

    driver = _LiveCellDriver(
        {"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'}
    )
    session = driver._visa_session
    assert driver._cell_state is CellState.OFF

    assert await driver.disconnect() is True

    assert driver.writes == ["SOURce:LTE:SIGN1:CELL:STATe OFF"]
    assert session.closed is True
    assert driver._visa_session is None


@pytest.mark.asyncio
async def test_cancel_restores_timeout_and_confirms_safe_cleanup_before_propagating():
    cell_states = iter(["ON,ADJ", "OFF,ADJ"])

    class _CancelledAttachDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command == "SOURce:LTE:SIGN1:CELL:STATe:ALL?":
                return next(cell_states)
            return self.responses[command]

    driver = _CancelledAttachDriver(
        {"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'}
    )
    original_timeout = driver._visa_session.timeout

    async def _cancel(_seconds: float) -> None:
        raise asyncio.CancelledError

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _cancel):
        with pytest.raises(asyncio.CancelledError):
            await driver.start_signaling(timeout_s=3.0)

    assert driver._visa_session.timeout == original_timeout
    assert driver.writes[-1] == "SOURce:LTE:SIGN1:CELL:STATe OFF"
    assert driver._cell_state is CellState.OFF
