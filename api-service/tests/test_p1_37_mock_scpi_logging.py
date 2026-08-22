"""P1-37: mock 驱动留下真实命令意图，模拟回包不可冒充真机。"""

from __future__ import annotations

import logging
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.hal.base import InstrumentStatus
from app.hal.base_station import MockBaseStation
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.positioner import MockPositioner
from app.hal.rf_switch import MockRfSwitch
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.hal.scpi_evidence import _transport_succeeded, capture_scpi_exchanges


def _scpi_records(caplog, instrument_id: str) -> list[logging.LogRecord]:
    return [
        record for record in caplog.records
        if record.name == f"app.hal.scpi.{instrument_id}"
    ]


def _assert_simulated_exchange(
    records: list[logging.LogRecord],
    *,
    instrument_id: str,
    command: str,
) -> None:
    matching = [
        record for record in records
        if getattr(record, "command", None) == command
    ]
    assert {getattr(record, "direction", None) for record in matching} == {"TX", "RX"}
    assert len({getattr(record, "exchange_id", None) for record in matching}) == 1
    assert all(record.instrument_id == instrument_id for record in matching)
    assert all(record.driver_source == "mock" for record in matching)
    assert all(record.simulated is True for record in matching)


@pytest.mark.asyncio
async def test_mock_base_station_emits_selected_uxm_dialect(caplog):
    instrument_id = "baseStation-onsite"
    driver = MockBaseStation(
        instrument_id,
        {"model": "UXM 5G E7515B", "detected_test_app": "LTE_NR_IRAT"},
    )
    caplog.set_level(logging.DEBUG, logger=f"app.hal.scpi.{instrument_id}")

    assert await driver.set_downlink_power(-46.0) is True

    records = _scpi_records(caplog, instrument_id)
    assert any(
        record.command == "BSE:CONFig:NR5G:CELL0:DL:POWer -46.0"
        and record.direction == "TX"
        for record in records
    )
    _assert_simulated_exchange(
        records, instrument_id=instrument_id, command="*OPC?",
    )


@pytest.mark.asyncio
async def test_mock_channel_emulator_emits_f64_go_sequence(caplog, monkeypatch):
    instrument_id = "channelEmulator-onsite"
    driver = MockChannelEmulator(instrument_id, {"model": "PROPSIM F64"})
    driver._set_status(InstrumentStatus.READY)
    caplog.set_level(logging.DEBUG, logger=f"app.hal.scpi.{instrument_id}")

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.hal.channel_emulator.asyncio.sleep", _no_sleep)
    assert await driver.start_emulation() is True

    records = _scpi_records(caplog, instrument_id)
    assert any(
        record.command == "DIAG:SIMU:GO" and record.direction == "TX"
        for record in records
    )
    _assert_simulated_exchange(
        records, instrument_id=instrument_id, command="DIAG:SIMU:STATE?",
    )


@pytest.mark.asyncio
async def test_mock_signal_analyzer_emits_x_series_setup(caplog):
    instrument_id = "signalAnalyzer-onsite"
    driver = MockSignalAnalyzer(instrument_id, {"model": "N9020B MXA"})
    caplog.set_level(logging.DEBUG, logger=f"app.hal.scpi.{instrument_id}")

    assert await driver.setup_spectrum(3.55e9, 100e6, 100e3) is True

    records = _scpi_records(caplog, instrument_id)
    commands = {
        record.command for record in records
        if getattr(record, "direction", None) == "TX"
    }
    assert {
        "SENSe:FREQuency:CENTer 3550000000.0",
        "SENSe:FREQuency:SPAN 100000000.0",
        "SENSe:BANDwidth:RESolution 100000.0",
    } <= commands
    _assert_simulated_exchange(
        records, instrument_id=instrument_id, command="*OPC?",
    )


@pytest.mark.asyncio
async def test_mock_positioner_emits_position_query(caplog):
    instrument_id = "positioner-onsite"
    driver = MockPositioner(instrument_id, {"model": "EMCenter"})
    caplog.set_level(logging.DEBUG, logger=f"app.hal.scpi.{instrument_id}")

    assert await driver.get_position() == (0.0, 0.0)

    _assert_simulated_exchange(
        _scpi_records(caplog, instrument_id),
        instrument_id=instrument_id,
        command="SOURce:POSition? 1",
    )


@pytest.mark.asyncio
async def test_mock_rf_switch_emits_emcenter_command(caplog, monkeypatch):
    instrument_id = "rfSwitch-onsite"
    driver = MockRfSwitch(instrument_id, {"model": "EMCenter Switch"})
    caplog.set_level(logging.DEBUG, logger=f"app.hal.scpi.{instrument_id}")

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.hal.rf_switch.asyncio.sleep", _no_sleep)
    assert await driver.switch_path("1:INT_RELAY_A", 1, "NO") is True

    matching = [
        record for record in _scpi_records(caplog, instrument_id)
        if getattr(record, "command", None) == "1:INT_RELAY_A_NO"
    ]
    assert {getattr(record, "direction", None) for record in matching} == {"TX", "OK"}
    assert {getattr(record, "operation", None) for record in matching} == {"write"}
    assert all(record.driver_source == "mock" for record in matching)
    assert all(record.simulated is True for record in matching)


def test_driver_source_is_not_derived_from_global_hal_mode():
    driver = MockSignalAnalyzer("forced-mock-under-real", {"model": "N9020B MXA"})
    assert driver.driver_source == "mock"
    assert driver.simulated is True


@pytest.mark.asyncio
async def test_simulated_exchange_cannot_satisfy_authoritative_transport_gate():
    driver = MockSignalAnalyzer("mock-evidence", {"model": "N9020B MXA"})

    with capture_scpi_exchanges() as exchanges:
        assert await driver.setup_spectrum(3.55e9, 100e6, 100e3) is True

    assert exchanges
    assert all(exchange.simulated is True for exchange in exchanges)
    assert all(not _transport_succeeded(exchange) for exchange in exchanges)


def test_simulated_measurement_serializes_as_unknown_na_report():
    from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data

    execution = SimpleNamespace(
        id="exec-simulated",
        status="completed",
        validation_pass=False,
        duration_sec=1.0,
        started_at=None,
        completed_at=None,
        config={},
        measurements={
            "phases": {
                "precheck": {},
                "reference": {},
                "measure": {
                    "measurement_source": "simulated",
                    "measurement_verified": False,
                    "azimuth_results": [{
                        "azimuth_deg": 0.0,
                        "rsrp_dbm": None,
                        "sinr_db": None,
                        "throughput_mbps": None,
                        "rank_indicator": None,
                    }],
                },
                "analysis": {"verdict": "UNKNOWN"},
            },
        },
    )

    content = _build_mimo_ota_content_data(
        execution, datetime(2026, 8, 7), "Mock case",
    )

    assert content["overall_result"] == "undetermined"
    assert content["execution_summary"]["pending"] == 0
    assert content["execution_summary"]["undetermined"] == 1
    assert content["execution_summary"]["pass_rate"] is None
    assert content["statistics"] == {}
    assert set(content["table_data"][0].values()) >= {"N/A"}
    measure_step = next(item for item in content["step_results"] if item["phase"] == "measure")
    assert "未验证" in measure_step["parameters"]["测量验证"]
