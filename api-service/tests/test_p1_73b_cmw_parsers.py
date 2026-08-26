"""P1-73B Task 6：CMW500 route/Extended BLER 回读严格解析。"""

import asyncio

import pytest

from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.cmw500_command_profile import Cmw500LteCommandProfile


def test_route_readback_requires_exact_tro_nx2_shape():
    parsed = Cmw500LteCommandProfile.parse_route_readback(
        "TRO,ignored,RF1C,RX1,RF1C,TX1,RF2C,TX2"
    )

    assert parsed.scenario == "TRO"
    assert parsed.rx_connector == "RF1C"
    assert parsed.tx1_connector == "RF1C"
    assert parsed.tx2_connector == "RF2C"


@pytest.mark.parametrize(
    "response",
    [
        "SCEL,ignored,RF1C,RX1,RF1C,TX1,RF2C,TX2",
        "TRO,ignored,RF1C,RX1,RF1C,TX1,RF2C",
        "TRO,ignored,RF1C,RX1,RF1C,TX1,RF2C,TX2,EXTRA",
        "TRO,ignored,NAV,RX1,RF1C,TX1,RF2C,TX2",
        "TRO,ignored,RF1C,,RF1C,TX1,RF2C,TX2",
    ],
)
def test_route_readback_rejects_wrong_scenario_shape_or_sentinel(response: str):
    with pytest.raises(ValueError):
        Cmw500LteCommandProfile.parse_route_readback(response)


def test_absolute_parser_uses_field_five_as_kbit_per_second():
    parsed = Cmw500LteCommandProfile.parse_ebler_absolute(
        "0,900,100,1000,123456.5,120000,125000,0,1000,15"
    )

    assert parsed.reliability == 0
    assert parsed.throughput_average_kbit_per_s == 123456.5
    assert parsed.median_cqi == 15


def test_relative_parser_uses_field_four_as_bler_percent():
    parsed = Cmw500LteCommandProfile.parse_ebler_relative(
        "0,99.5,0.5,0.5,87.25,0"
    )

    assert parsed.reliability == 0
    assert parsed.bler_percent == 0.5
    assert parsed.throughput_average_percent == 87.25


@pytest.mark.parametrize(
    "parser,response",
    [
        ("absolute", "0,900,100"),
        ("absolute", "0,900,100,1000,NAV,120000,125000,0,1000,15"),
        ("absolute", "0,900,100,1000,nan,120000,125000,0,1000,15"),
        ("absolute", "0,900,100,1000,inf,120000,125000,0,1000,15"),
        ("absolute", "1,900,100,1000,123456,120000,125000,0,1000,15"),
        ("relative", "0,99.5,0.5"),
        ("relative", "0,99.5,0.5,bad,87.25,0"),
        ("relative", "0,99.5,0.5,101,87.25,0"),
        ("relative", "21,99.5,0.5,0.5,87.25,0"),
    ],
)
def test_extended_bler_parsers_fail_closed(parser: str, response: str):
    parse = getattr(Cmw500LteCommandProfile, f"parse_ebler_{parser}")
    with pytest.raises(ValueError):
        parse(response)


@pytest.mark.parametrize("state", ["OFF", "RUN", "RDY"])
def test_state_parser_accepts_only_manual_enum(state: str):
    assert Cmw500LteCommandProfile.parse_ebler_state(state) == state


@pytest.mark.parametrize("state", ["", "NAV", "READY", "run", "RUN,ACT"])
def test_state_parser_rejects_unknown_enum(state: str):
    with pytest.raises(ValueError):
        Cmw500LteCommandProfile.parse_ebler_state(state)


def test_legacy_polling_no_longer_treats_absolute_reliability_as_bler():
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})

    def query(command: str) -> str:
        if "EBLer:PCC:ABSolute?" in command:
            return "0,900,100,1000,123456.5,120000,125000,0,1000,15"
        return ""

    driver._query = query  # type: ignore[method-assign]
    metrics = asyncio.run(driver.get_throughput_metrics())

    assert metrics.dl_bler == 0.0
    assert metrics.is_valid("dl_throughput") is False
