from __future__ import annotations

import inspect

import pytest

from app.hal.base_station import MockBaseStation
from app.hal.base_station_compatibility import (
    build_measure_execution_requirements_from_configuration,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.base_station_mac_profile import build_mac_throughput_command_inputs
from app.hal.scpi_evidence import record_exchange_intent, record_exchange_terminal
from app.hal.base_station import (
    BaseStationApplyReceipt,
    BaseStationFieldReceipt,
    MacThroughputConfigResult,
)
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


@pytest.mark.asyncio
async def test_uxm_profile_receipt_captures_existing_command_evidence(monkeypatch):
    profile = _nr_profile()
    driver = RealUxmDriver(
        "uxm",
        {"resource": "TCPIP0::192.0.2.1::INSTR"},
    )

    async def configured(**kwargs):
        record_exchange_intent(
            exchange_id="uxm-mac-write-1",
            instrument_id="uxm",
            operation="command",
            command="existing-sourced-command",
        )
        record_exchange_terminal(
            exchange_id="uxm-mac-write-1",
            result_type="ok",
        )
        record_exchange_intent(
            exchange_id="uxm-mac-error-1",
            instrument_id="uxm",
            operation="query",
            command="SYST:ERR?",
        )
        record_exchange_terminal(
            exchange_id="uxm-mac-error-1",
            result_type="response",
            response='0,"No error"',
        )
        receipt = BaseStationApplyReceipt(
            schema_version=1,
            operation="mac_throughput_config",
            fields=(
                BaseStationFieldReceipt(
                    field="mac_profile",
                    requested=kwargs["profile_payload"],
                    applied=None,
                    status="unknown",
                    reason="no full-profile readback",
                ),
            ),
            reason="command/error-queue path completed",
            simulated=False,
            operation_succeeded=True,
            profile_digest=kwargs["profile_digest"],
        )
        return MacThroughputConfigResult(
            receipt=receipt,
            profile_digest=kwargs["profile_digest"],
        )

    monkeypatch.setattr(driver, "_configure_mac_throughput_values", configured)

    result = await driver.configure_mac_throughput_test(profile)

    assert result.receipt is not None
    assert result.receipt.confirmed is False
    assert result.receipt.exchange_ids == (
        "uxm-mac-write-1",
        "uxm-mac-error-1",
    )
    assert tuple(item.exchange_id for item in result.application_exchanges) == (
        "uxm-mac-write-1",
        "uxm-mac-error-1",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("driver", "profile", "model_name"),
    (
        (
            RealUxmDriver("uxm", {"resource": "TCPIP0::192.0.2.1::INSTR"}),
            _nr_profile(),
            "UXM 5G E7515B",
        ),
        (
            RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"}),
            _lte_profile(),
            "CMW500",
        ),
    ),
)
async def test_real_and_mock_reuse_one_frozen_profile_command_input_builder(
    driver,
    profile,
    model_name,
    monkeypatch,
):
    captured = {}

    async def configure_values(**kwargs):
        captured.update(kwargs)
        return MacThroughputConfigResult(profile_digest=profile.profile_digest)

    monkeypatch.setattr(driver, "_configure_mac_throughput_values", configure_values)
    await driver.configure_mac_throughput_test(profile)

    expected = build_mac_throughput_command_inputs(profile)
    assert captured == expected

    mock = MockBaseStation(
        "mock-base-station",
        {"model": model_name},
        adapter_manifest=driver.adapter_manifest,
    )
    mock_result = await mock.configure_mac_throughput_test(profile)
    assert mock_result.receipt is not None
    assert {
        field.field: field.requested for field in mock_result.receipt.fields
    } == {
        key: value
        for key, value in expected.items()
        if key not in {"profile_payload", "profile_digest"}
    }
    assert mock_result.receipt.simulated is True
    assert mock_result.receipt.confirmed is False
