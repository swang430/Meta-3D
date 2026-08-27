"""P1-73B Task 8：CMW500 内部 LTE 2x2 route 必须按手册写后确认。"""

from __future__ import annotations

import pytest

from app.hal.cmw500_base_station import RealCmw500Driver


def _frozen_route(**overrides) -> dict:
    route = {
        "pcc_bb_board": "BB1",
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
    def __init__(self, responses: dict[str, str]):
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
        return self.responses[cmd]


def _driver(
    *,
    readback: str = "TRO,BB1,RF1C,RX1,RF1C,TX1,RF2C,TX2",
    error: str = '0,"No error"',
) -> _RouteDriver:
    return _RouteDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "SYSTem:ERRor:ALL?": error,
            "ROUTe:LTE:SIGN1?": readback,
        }
    )


@pytest.mark.asyncio
async def test_route_ignores_irrelevant_controller_readback_and_confirms_physical_paths():
    driver = _driver(
        readback='TRO,"No Connection",RF1C,RX1,RF1C,TX1,RF2C,TX2'
    )

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is True
    assert result.applied == result.requested


@pytest.mark.asyncio
async def test_route_uses_only_the_complete_execution_frozen_profile_and_confirms_all_paths():
    driver = _driver()

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert driver.writes == [
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible "
        "BB1,RF1C,RX1,RF1C,TX1,RF2C,TX2"
    ]
    assert driver.queries == [
        "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
        "SYSTem:ERRor:ALL?",
        "ROUTe:LTE:SIGN1?",
    ]
    assert result.confirmed is True
    assert result.requested == {
        "pcc_bb_board": "BB1",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    assert result.applied == result.requested
    assert "1173.9628.02-41" in result.source_reference
    assert len(result.exchange_ids) == 3
    assert not hasattr(result, "rf_router")


@pytest.mark.asyncio
async def test_route_accepts_ks520_token_exactly_as_cmw500_reports_it():
    driver = _driver()
    driver._installed_options = ["KS520"]

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is True


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
    driver = _driver(readback="TRO,BB1,RF1C,RX1,RF1C,TX1,RF3C,TX2")

    result = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert result.confirmed is False
    assert "readback" in result.reason
    assert result.applied is not None


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
