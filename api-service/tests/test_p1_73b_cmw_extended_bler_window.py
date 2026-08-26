"""P1-73B Task 10：CMW500 Extended BLER 必须形成独立可信窗口。"""

from __future__ import annotations

import asyncio
from collections import deque
from unittest.mock import patch

import pytest

from app.hal.base_station import ThroughputMetrics
from app.hal.cmw500_base_station import RealCmw500Driver


ABSOLUTE = "0,900,100,1000,123456.5,120000,125000,0,1000,15"
RELATIVE = "0,99.5,0.5,0.5,87.25,0"


class _WindowDriver(RealCmw500Driver):
    def __init__(
        self,
        *,
        states: list[str],
        errors: list[str] | None = None,
        absolute: str | Exception = ABSOLUTE,
        relative: str | Exception = RELATIVE,
    ) -> None:
        super().__init__("cmw-window", {"ip_address": "192.0.2.10"})
        self._visa_session = object()
        self.states = deque(states)
        self.errors = deque(errors or ['0,"No error"'] * 8)
        self.absolute = absolute
        self.relative = relative
        self.writes: list[str] = []
        self.queries: list[str] = []

    def _do_write(self, command: str) -> None:
        self.writes.append(command)

    def _do_query(self, command: str) -> str:
        self.queries.append(command)
        if command == "FETCh:LTE:SIGN1:EBLer:STATe?":
            return self.states.popleft()
        if command == "SYSTem:ERRor:ALL?":
            return self.errors.popleft()
        if command == "*OPC?":
            return "1"
        if command == "FETCh:LTE:SIGN1:EBLer:PCC:ABSolute?":
            if isinstance(self.absolute, Exception):
                raise self.absolute
            return self.absolute
        if command == "FETCh:LTE:SIGN1:EBLer:PCC:RELative?":
            if isinstance(self.relative, Exception):
                raise self.relative
            return self.relative
        raise AssertionError(f"unexpected query: {command}")


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_extended_bler_window_confirms_full_lifecycle_and_shared_metrics():
    driver = _WindowDriver(states=["OFF", "RUN", "RUN", "RDY", "OFF"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(0.1)

    assert window.confirmed is True
    assert window.preclear_off_confirmed is True
    assert window.running_confirmed is True
    assert window.ready_confirmed is True
    assert window.closed_off_confirmed is True
    assert window.completed_at is not None
    assert window.window_id
    assert window.metrics.throughput_scope == ThroughputMetrics.SCOPE_PCELL
    assert window.metrics.dl_throughput_mbps == pytest.approx(123.4565)
    assert window.metrics.dl_bler == pytest.approx(0.5)
    assert window.metrics.is_valid("dl_throughput") is True
    assert window.metrics.is_valid("dl_bler") is True
    assert window.metrics.ul_throughput_mbps is None
    assert window.metrics.is_valid("ul_throughput") is False
    assert window.evidence
    assert window.evidence[0].exchange_ids
    assert driver.writes == [
        "ABORt:LTE:SIGN1:EBLer",
        "CONFigure:LTE:SIGN1:EBLer:TOUT 0",
        "CONFigure:LTE:SIGN1:EBLer:REPetition CONTinuous",
        "CONFigure:LTE:SIGN1:EBLer:SCONdition NONE",
        "INITiate:LTE:SIGN1:EBLer",
        "STOP:LTE:SIGN1:EBLer",
        "ABORt:LTE:SIGN1:EBLer",
    ]


@pytest.mark.asyncio
async def test_continuous_window_rejects_uncommanded_early_ready():
    driver = _WindowDriver(states=["OFF", "RUN", "RDY", "OFF"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(0.1)

    assert window.confirmed is False
    assert "STOP:LTE:SIGN1:EBLer" not in driver.writes
    assert not any(
        "ABSolute?" in query or "RELative?" in query for query in driver.queries
    )


@pytest.mark.asyncio
async def test_pcc_window_rejects_an_all_cells_scope_before_instrument_io():
    driver = _WindowDriver(states=[])

    with pytest.raises(ValueError, match="pcell"):
        await driver.measure_base_station_window(
            0.1,
            throughput_scope=ThroughputMetrics.SCOPE_NR_ALL_CELLS,
        )

    assert driver.writes == []
    assert driver.queries == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("absolute", "relative", "throughput_valid", "bler_valid"),
    [
        (ABSOLUTE, "0,99.5,0.5,NAV,87.25,0", True, False),
        ("1,900,100,1000,123456.5,120000,125000,0,1000,15", RELATIVE, False, True),
        (RuntimeError("absolute fetch failed"), RELATIVE, False, True),
    ],
)
async def test_kpi_fields_fail_independently_without_borrowing_each_other(
    absolute, relative, throughput_valid, bler_valid
):
    driver = _WindowDriver(
        states=["OFF", "RUN", "RUN", "RDY", "OFF"],
        absolute=absolute,
        relative=relative,
    )

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(0.1)

    assert window.confirmed is True
    assert window.metrics.is_valid("dl_throughput") is throughput_valid
    assert window.metrics.is_valid("dl_bler") is bler_valid
    assert (window.metrics.dl_throughput_mbps is not None) is throughput_valid
    assert (window.metrics.dl_bler is not None) is bler_valid


@pytest.mark.asyncio
async def test_stop_rejection_prevents_fetch_and_still_confirms_final_abort():
    driver = _WindowDriver(
        states=["OFF", "RUN", "RUN", "OFF"],
        errors=[
            '0,"No error"',
            '0,"No error"',
            '0,"No error"',
            '0,"No error"',
            '0,"No error"',
            '-221,"Settings conflict"',
            '0,"No error"',
        ],
    )

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(0.1)

    assert window.confirmed is False
    assert window.ready_confirmed is False
    assert window.closed_off_confirmed is True
    assert window.metrics.dl_throughput_mbps is None
    assert window.metrics.dl_bler is None
    assert not any("ABSolute?" in query or "RELative?" in query for query in driver.queries)
    assert driver.writes[-1] == "ABORt:LTE:SIGN1:EBLer"


@pytest.mark.asyncio
async def test_final_off_failure_discards_previously_fetched_formal_values():
    driver = _WindowDriver(states=["OFF", "RUN", "RUN", "RDY", "RUN"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        window = await driver.measure_base_station_window(0.1)

    assert window.confirmed is False
    assert window.closed_off_confirmed is False
    assert window.metrics.dl_throughput_mbps is None
    assert window.metrics.dl_bler is None
    assert window.metrics.is_valid("dl_throughput") is False
    assert window.metrics.is_valid("dl_bler") is False
    assert "final" in window.reason.lower()


@pytest.mark.asyncio
async def test_cancel_propagates_only_after_final_abort_and_off_confirmation():
    driver = _WindowDriver(states=["OFF", "RUN", "RDY", "OFF"])

    async def _cancel(_seconds: float) -> None:
        raise asyncio.CancelledError

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _cancel):
        with pytest.raises(asyncio.CancelledError):
            await driver.measure_base_station_window(0.1)

    assert driver.writes[-1] == "ABORt:LTE:SIGN1:EBLer"
    assert driver.states == deque()


@pytest.mark.asyncio
async def test_legacy_measurement_entry_remains_unverified_until_task_c_consumes_window():
    driver = _WindowDriver(states=[])
    driver.responses = {
        "SENSe:LTE:SIGN1:CONNection:ETHRoughput:DL:PCC?": "diagnostic",
        "SENSe:LTE:SIGN1:CONNection:ETHRoughput:UL:PCC?": "diagnostic",
        "FETCh:LTE:SIGN1:EBLer:PCC:ABSolute?": ABSOLUTE,
        "FETCh:LTE:SIGN1:EBLer:PCC:RELative?": RELATIVE,
        "FETCh:LTE:SIGN1:EBLer:PCC:CQIReporting:STReam1?": "15",
        "SENSe:LTE:SIGN1:UEReport:RSRP?": "",
        "SENSe:LTE:SIGN1:UEReport:SINR?": "",
    }
    driver._do_query = lambda command: driver.responses[command]  # type: ignore[method-assign]

    metrics = await driver.measure_throughput_window(0.0)

    assert metrics.dl_throughput_mbps is None
    assert metrics.dl_bler is None
    assert metrics.is_valid("dl_throughput") is False
    assert metrics.is_valid("dl_bler") is False
