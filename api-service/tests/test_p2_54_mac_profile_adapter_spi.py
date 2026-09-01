from __future__ import annotations

import inspect

import pytest

from app.hal.base_station import MockBaseStation
from app.hal.base_station_compatibility import (
    build_measure_execution_requirements_from_configuration,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from tests.test_p2_51_cmw_mac_config import _MacDriver


def _lte_configuration():
    return {
        "component_carriers": [
            {
                "radio_technology": "lte",
                "frequency_hz": 1_842_500_000.0,
                "bandwidth_mhz": 20.0,
                "subcarrier_spacing_khz": None,
                "band": "B3",
                "duplex": "fdd",
                "lte_dl_earfcn": 1575,
                "lte_transmission_mode": "TM3",
                "role": "pcell",
            }
        ],
        "mimo_layers": 2,
        "theoretical_peak_throughput_mbps": None,
    }


def _nr_profile():
    return build_measure_execution_requirements_from_configuration({}).mac_profile


def _lte_profile():
    return build_measure_execution_requirements_from_configuration(
        _lte_configuration()
    ).mac_profile


@pytest.mark.parametrize(
    "driver_class",
    (RealUxmDriver, RealCmw500Driver, MockBaseStation),
)
def test_common_mac_spi_accepts_only_one_frozen_profile(driver_class):
    signature = inspect.signature(driver_class.configure_mac_throughput_test)

    assert list(signature.parameters) == ["self", "frozen_profile"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("driver", "profile"),
    (
        (
            RealUxmDriver("uxm", {"resource": "TCPIP0::192.0.2.1::INSTR"}),
            _lte_profile(),
        ),
        (
            RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"}),
            _nr_profile(),
        ),
    ),
)
async def test_cross_rat_profile_is_rejected_before_first_instrument_io(
    driver, profile, monkeypatch
):
    def unexpected_io(*_args, **_kwargs):
        raise AssertionError("profile rejection must precede instrument I/O")

    monkeypatch.setattr(driver, "_do_write", unexpected_io)
    monkeypatch.setattr(driver, "_do_query", unexpected_io)

    with pytest.raises(ValueError, match="MAC profile"):
        await driver.configure_mac_throughput_test(profile)


@pytest.mark.asyncio
async def test_profile_digest_tampering_is_rejected_before_first_instrument_io(
    monkeypatch,
):
    driver = RealUxmDriver(
        "uxm",
        {"resource": "TCPIP0::192.0.2.1::INSTR"},
    )
    corrupted = _nr_profile().model_copy(update={"profile_digest": "0" * 64})

    def unexpected_io(*_args, **_kwargs):
        raise AssertionError("digest rejection must precede instrument I/O")

    monkeypatch.setattr(driver, "_do_write", unexpected_io)
    monkeypatch.setattr(driver, "_do_query", unexpected_io)

    with pytest.raises(ValueError, match="profile_digest"):
        await driver.configure_mac_throughput_test(corrupted)


@pytest.mark.asyncio
async def test_cmw_profile_receipt_binds_digest_without_nr_no_equivalent_fields():
    profile = _lte_profile()
    driver = _MacDriver()

    result = await driver.configure_mac_throughput_test(profile)

    assert result.ok is True
    assert result.profile_digest == profile.profile_digest
    assert result.no_equivalent == ()
    assert result.receipt.profile_digest == profile.profile_digest
