"""P1-73B Task 8：CMW500 内部 LTE 2x2 route 必须按手册写后确认。"""

from __future__ import annotations

import pytest

from app.hal.base_station import BaseStationApplyReceipt
from app.hal.cmw500_base_station import RealCmw500Driver


def _frozen_route(**overrides) -> dict:
    route = {
        "pcc_bb_board": "SUA1",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
        **overrides,
    }
    return {
        "resolution": {
            "schema_version": 1,
            "adapter": "cmw500",
            "status": "configured",
            "execution_mode": "real",
            "profile": {
                "schema_version": 1,
                "adapter": "cmw500",
                "lte_2x2_internal_route": route,
            },
        }
    }


class _RouteDriver(RealCmw500Driver):
    def __init__(self, responses: dict[str, str | list[str] | BaseException]):
        super().__init__("cmw-route", {"ip_address": "192.0.2.10"})
        self.responses = responses
        self.writes: list[str] = []
        self.queries: list[str] = []
        self._firmware_version = "3.5.40"
        self._installed_options = ["CMW-KS520"]

    def _do_write(self, cmd: str) -> None:
        self.writes.append(cmd)

    def _do_query(self, cmd: str) -> str:
        self.queries.append(cmd)
        response = self.responses[cmd]
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, list):
            return response.pop(0)
        return response


def _driver(
    *,
    nx2_readback: str | BaseException | None = (
        "SUA1,RF1C,RX1,RF1C,TX1,RF2C,TX2"
    ),
    readback: str = "TRO,Controller,RF1C,RX1,RF1C,TX1,RF2C,TX2",
    error: str | list[str] = '0,"No error"',
) -> _RouteDriver:
    responses = {
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
        "SYSTem:ERRor:ALL?": error,
        "ROUTe:LTE:SIGN1?": readback,
    }
    if nx2_readback is not None:
        responses["ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?"] = nx2_readback
    return _RouteDriver(responses)


@pytest.mark.asyncio
async def test_route_uses_specific_query_not_generic_controller_to_confirm_pcc_board():
    driver = _driver(
        readback='TRO,"No Connection",RF1C,RX1,RF1C,TX1,RF2C,TX2'
    )

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is True
    assert result.applied == {
        "pcc_bb_board": "SUA1",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    assert result.reason == "CMW500 route write and both readbacks confirmed"


@pytest.mark.asyncio
async def test_common_route_receipt_confirms_each_authoritatively_read_field():
    driver = _driver()

    receipt = await driver.apply_route(_frozen_route())

    assert isinstance(receipt, BaseStationApplyReceipt)
    assert receipt.operation == "route"
    assert receipt.confirmed is True
    assert {field.field: field.status for field in receipt.fields} == {
        "pcc_bb_board": "confirmed",
        "rx_connector": "confirmed",
        "rx_converter": "confirmed",
        "tx1_connector": "confirmed",
        "tx1_converter": "confirmed",
        "tx2_connector": "confirmed",
        "tx2_converter": "confirmed",
    }
    assert len(receipt.exchange_ids) == 5


@pytest.mark.asyncio
async def test_common_route_receipt_keeps_only_pcc_unknown_when_specific_query_fails():
    driver = _driver(
        nx2_readback=TimeoutError("setting query unsupported"),
        error=['0,"No error"', '-113,"Undefined header"', '0,"No error"'],
    )

    receipt = await driver.apply_route(_frozen_route())

    fields = {field.field: field for field in receipt.fields}
    assert receipt.confirmed is False
    assert fields["pcc_bb_board"].status == "unknown"
    assert fields["pcc_bb_board"].applied is None
    for name in {
        "rx_connector",
        "rx_converter",
        "tx1_connector",
        "tx1_converter",
        "tx2_connector",
        "tx2_converter",
    }:
        assert fields[name].status == "confirmed"
        assert fields[name].applied == fields[name].requested


@pytest.mark.asyncio
async def test_route_uses_only_the_complete_execution_frozen_profile_and_reads_all_physical_paths():
    driver = _driver()

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert driver.writes == [
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible "
        "SUA1,RF1C,RX1,RF1C,TX1,RF2C,TX2"
    ]
    assert driver.queries == [
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        "SYSTem:ERRor:ALL?",
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?",
        "ROUTe:LTE:SIGN1?",
        "SYSTem:ERRor:ALL?",
    ]
    assert result.confirmed is True
    assert result.requested == {
        "pcc_bb_board": "SUA1",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    assert result.applied == {
        "pcc_bb_board": "SUA1",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    assert result.reason == "CMW500 route write and both readbacks confirmed"
    assert "1173.9628.02-41" in result.source_reference
    assert "1179.4592.02-04" in result.source_reference
    assert len(result.exchange_ids) == 5
    assert not hasattr(result, "rf_router")


@pytest.mark.asyncio
async def test_route_accepts_ks520_token_exactly_as_cmw500_reports_it():
    driver = _driver()
    driver._installed_options = ["KS520"]

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert driver.writes != []
    assert "requires KS520" not in result.reason


@pytest.mark.asyncio
async def test_missing_frozen_route_does_not_reuse_current_state_or_choose_defaults():
    driver = _driver()

    result = await driver.apply_internal_lte_2x2_route({"resolution": {}})

    assert result.confirmed is False
    assert result.requested is None
    assert driver.writes == []
    assert driver.queries == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("firmware", "options", "reason"),
    [
        ("3.5.39", ["CMW-KS520"], "firmware"),
        ("3.5.40", [], "KS520"),
    ],
)
async def test_route_requires_sourced_firmware_and_option_before_write(
    firmware, options, reason
):
    driver = _driver()
    driver._firmware_version = firmware
    driver._installed_options = options

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert reason in result.reason
    assert driver.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"tx2_connector": "RF1C"}, "connector"),
        ({"tx2_converter": "TX1"}, "converter"),
    ],
)
async def test_route_rejects_tx_connector_and_converter_reuse_independently(
    overrides, reason
):
    driver = _driver()

    result = await driver.apply_internal_lte_2x2_route(_frozen_route(**overrides))

    assert result.confirmed is False
    assert reason in result.reason
    assert driver.writes == []


@pytest.mark.asyncio
async def test_route_readback_mismatch_keeps_confirmation_false():
    driver = _driver(readback="TRO,Controller,RF1C,RX1,RF1C,TX1,RF3C,TX2")

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert "readback" in result.reason
    assert result.applied is None


@pytest.mark.asyncio
async def test_route_pcc_board_mismatch_keeps_confirmation_false_without_backfill():
    driver = _driver(
        nx2_readback="SUA2,RF1C,RX1,RF1C,TX1,RF2C,TX2",
    )

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert result.applied == {
        "pcc_bb_board": "SUA2",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    assert "readback" in result.reason


@pytest.mark.asyncio
async def test_route_specific_query_unavailable_keeps_confirmation_false():
    driver = _driver(
        nx2_readback=TimeoutError("setting query unsupported"),
        error=['0,"No error"', '-113,"Undefined header"', '0,"No error"'],
    )

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert result.applied == {
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    assert "diagnostic execution only" in result.reason
    assert "Undefined header" in result.reason
    assert driver.queries == [
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        "SYSTem:ERRor:ALL?",
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?",
        "SYSTem:ERRor:ALL?",
        "ROUTe:LTE:SIGN1?",
        "SYSTem:ERRor:ALL?",
    ]


@pytest.mark.asyncio
async def test_route_readback_error_queue_entry_blocks_confirmation():
    driver = _driver(
        error=['0,"No error"', '-200,"Execution error"'],
    )

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert "readback error queue" in result.reason
    assert driver.queries == [
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        "SYSTem:ERRor:ALL?",
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?",
        "ROUTe:LTE:SIGN1?",
        "SYSTem:ERRor:ALL?",
    ]


@pytest.mark.asyncio
async def test_route_error_queue_entry_blocks_readback_and_confirmation():
    driver = _driver(error='-221,"Settings conflict"')

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert "error queue" in result.reason
    assert driver.queries == [
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        "SYSTem:ERRor:ALL?",
    ]


@pytest.mark.asyncio
async def test_route_error_queue_zero_prefix_cannot_hide_a_following_error():
    driver = _driver(error='0,"No error";-221,"Settings conflict"')

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert "error queue" in result.reason
    assert driver.queries == [
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        "SYSTem:ERRor:ALL?",
    ]
