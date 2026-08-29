from __future__ import annotations

from unittest.mock import patch

import pytest

from app.hal.base_station import BaseStationAttachReceipt, CellState
from app.hal.scpi_evidence import capture_scpi_exchanges
from tests.test_p1_73b_cmw_state_machine import _StateDriver


async def _no_sleep(_seconds: float) -> None:
    return None


def _driver_with_states(states: list[str]):
    iterator = iter(states)

    class _AttachDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            self.queries.append(command)
            if command in {
                "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
                "FETCh:LTE:SIGN1:PSWitched:STATe?",
            }:
                return next(iterator)
            return self.responses[command]

    return _AttachDriver(
        {"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'}
    )


@pytest.mark.asyncio
async def test_cmw_attach_maps_each_existing_authoritative_readback_to_its_stage():
    driver = _driver_with_states(["ON,ADJ", "ATT", "CEST"])

    with capture_scpi_exchanges() as exchanges:
        with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
            receipt = await driver.attach(timeout_s=3.0)

    assert isinstance(receipt, BaseStationAttachReceipt)
    stages = {stage.stage: stage for stage in receipt.stages}
    assert stages["cell_ready"].applied is True
    assert stages["cell_ready"].evidence == "authoritative"
    assert stages["ue_registered"].applied is True
    assert stages["ue_registered"].evidence == "authoritative"
    assert stages["rrc_connected"].status == "unknown"
    assert stages["rrc_connected"].evidence == "unavailable"
    assert stages["data_bearer_established"].applied is True
    assert stages["data_bearer_established"].evidence == "authoritative"
    assert receipt.diagnostic_execution_allowed is True
    assert receipt.formally_confirmed is True
    assert driver._cell_state is CellState.CONNECTED

    command_by_id = {exchange.exchange_id: exchange.command for exchange in exchanges}
    assert {
        command_by_id[exchange_id]
        for exchange_id in stages["cell_ready"].exchange_ids
    } == {"SOURce:LTE:SIGN1:CELL:STATe:ALL?"}
    assert {
        command_by_id[exchange_id]
        for exchange_id in stages["ue_registered"].exchange_ids
    } == {"FETCh:LTE:SIGN1:PSWitched:STATe?"}
    assert {
        command_by_id[exchange_id]
        for exchange_id in stages["data_bearer_established"].exchange_ids
    } == {"FETCh:LTE:SIGN1:PSWitched:STATe?"}
    compatibility_driver = _driver_with_states(["ON,ADJ", "ATT", "CEST"])
    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        assert await compatibility_driver.start_signaling(timeout_s=3.0) is True


@pytest.mark.asyncio
async def test_cmw_attach_failure_keeps_only_current_operation_proven_stage_truth():
    driver = _driver_with_states(["ON,ADJ", "ON", "OFF,ADJ"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        receipt = await driver.attach(timeout_s=3.0)

    stages = {stage.stage: stage for stage in receipt.stages}
    assert stages["cell_ready"].status == "confirmed"
    assert stages["cell_ready"].applied is True
    assert stages["ue_registered"].status == "confirmed"
    assert stages["ue_registered"].applied is False
    assert stages["data_bearer_established"].status == "unknown"
    assert stages["data_bearer_established"].applied is None
    assert receipt.diagnostic_execution_allowed is False
    assert receipt.formally_confirmed is False
    assert driver._cell_state is CellState.OFF


@pytest.mark.asyncio
async def test_cmw_unknown_ps_reply_is_unknown_not_confirmed_false_or_cached_truth():
    driver = _driver_with_states(["ON,ADJ", "UNATTACHED", "OFF,ADJ"])
    driver._cell_state = CellState.CONNECTED

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        receipt = await driver.attach(timeout_s=3.0)

    stages = {stage.stage: stage for stage in receipt.stages}
    assert stages["ue_registered"].status == "unknown"
    assert stages["ue_registered"].applied is None
    assert stages["data_bearer_established"].status == "unknown"
    assert receipt.exchange_ids == stages["cell_ready"].exchange_ids
