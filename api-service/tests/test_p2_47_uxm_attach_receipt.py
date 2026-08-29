from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.hal.base_station import BaseStationAttachReceipt
from app.hal.scpi_evidence import capture_scpi_exchanges
from app.hal.uxm_base_station import RealUxmDriver
from tests.test_p02_uxm_truth_source import _FakeUxmSession, _mk_irat_driver

_REAL_SLEEP = asyncio.sleep


async def _instant_sleep(_seconds: float) -> None:
    await _REAL_SLEEP(0)


@pytest.mark.asyncio
async def test_uxm_connected_status_is_diagnostic_rrc_not_authoritative_bearer():
    driver, _ = _mk_irat_driver(
        {
            "*OPC?": "1",
            "BSE:STATus:NR5G:CELL1?": "CONNected",
        }
    )

    with capture_scpi_exchanges() as exchanges:
        with patch("app.hal.uxm_base_station.asyncio.sleep", _instant_sleep):
            receipt = await driver.attach(timeout_s=4.0)

    assert isinstance(receipt, BaseStationAttachReceipt)
    stages = {stage.stage: stage for stage in receipt.stages}
    assert stages["cell_ready"].status == "confirmed"
    assert stages["cell_ready"].applied is True
    assert stages["cell_ready"].evidence == "diagnostic_only"
    assert stages["ue_registered"].status == "unknown"
    assert stages["ue_registered"].evidence == "diagnostic_only"
    assert stages["rrc_connected"].status == "confirmed"
    assert stages["rrc_connected"].applied is True
    assert stages["rrc_connected"].evidence == "diagnostic_only"
    assert stages["data_bearer_established"].status == "unknown"
    assert stages["data_bearer_established"].evidence == "unavailable"
    assert receipt.terminal_stage == "rrc_connected"
    assert receipt.diagnostic_execution_allowed is True
    assert receipt.formally_confirmed is False

    commands = {exchange.exchange_id: exchange.command for exchange in exchanges}
    assert {
        commands[exchange_id]
        for exchange_id in stages["rrc_connected"].exchange_ids
    } == {"BSE:STATus:NR5G:CELL1?"}


@pytest.mark.asyncio
async def test_uxm_idle_confirms_cell_ready_but_not_rrc_or_registration():
    driver, _ = _mk_irat_driver(
        {
            "*OPC?": "1",
            "BSE:STATus:NR5G:CELL1?": "IDLE",
        }
    )
    with patch("app.hal.uxm_base_station.asyncio.sleep", _instant_sleep):
        receipt = await driver.attach(timeout_s=4.0)

    stages = {stage.stage: stage for stage in receipt.stages}
    assert stages["cell_ready"].applied is True
    assert stages["rrc_connected"].status == "confirmed"
    assert stages["rrc_connected"].applied is False
    assert stages["ue_registered"].status == "unknown"
    assert receipt.diagnostic_execution_allowed is False


@pytest.mark.asyncio
async def test_uxm_out_of_enum_reply_does_not_reuse_cached_connected_state():
    driver, _ = _mk_irat_driver(
        {
            "*OPC?": "1",
            "BSE:STATus:NR5G:CELL1?": "1",
        }
    )
    driver._cell_state = driver._parse_cell_status("CONNected")
    with patch("app.hal.uxm_base_station.asyncio.sleep", _instant_sleep):
        receipt = await driver.attach(timeout_s=2.0)

    assert all(stage.applied is None for stage in receipt.stages)
    assert all(stage.status == "unknown" for stage in receipt.stages)
    assert receipt.exchange_ids == ()
    assert receipt.diagnostic_execution_allowed is False


@pytest.mark.asyncio
async def test_uxm_legacy_profile_fallback_stays_diagnostic_and_bool_compatible():
    driver = RealUxmDriver("uxm-5g", {"ip": "10.0.0.1"})
    session = _FakeUxmSession(
        {
            "*OPC?": "1",
            "ACTive:STATe?": "CONN",
        }
    )
    driver._visa_session = session

    with patch("app.hal.uxm_base_station.asyncio.sleep", _instant_sleep):
        receipt = await driver.attach(timeout_s=4.0)
    assert receipt.diagnostic_execution_allowed is True
    assert receipt.formally_confirmed is False
    assert any("ACTive:STATe?" in query for query in session.queried)

    compatibility = RealUxmDriver("uxm-5g-compat", {"ip": "10.0.0.1"})
    compatibility._visa_session = _FakeUxmSession(
        {"*OPC?": "1", "ACTive:STATe?": "CONN"}
    )
    with patch("app.hal.uxm_base_station.asyncio.sleep", _instant_sleep):
        assert await compatibility.start_signaling(timeout_s=4.0) is True
