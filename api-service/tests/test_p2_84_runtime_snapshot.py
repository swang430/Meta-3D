"""运行态快照只读内存，不夺回 ATE、不把默认值变成实测。"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.hal.base import InstrumentStatus
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.services import instrument_hal_service


@pytest.fixture
def driver(monkeypatch):
    driver = RealPropsimF64Driver("f64-test", {"ip_address": "127.0.0.1"})
    def forbidden(*args, **kwargs):
        raise AssertionError("只读快照不得触发硬件 I/O")
    for name in ("_query", "_write", "get_metrics", "get_channel_state"):
        monkeypatch.setattr(driver, name, forbidden)
    monkeypatch.setattr(instrument_hal_service, "get_hal_service", lambda: SimpleNamespace(drivers={"channelEmulator": driver}))
    return driver


def snapshot():
    response = TestClient(app).get("/api/v1/instruments/channelEmulator/runtime-snapshot")
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_driver_never_presents_constructor_defaults_as_observations(driver):
    result = snapshot()
    fields = {field["key"]: field for field in result["fields"]}
    assert result["diagnostic_only"] is True
    assert fields["center_frequency_mhz"]["value"] is None
    assert fields["emulation_running"]["value"] is None
    assert fields["input_power"]["value"] is None
    assert fields["output_power"]["value"] is None


def test_live_cache_is_not_current_or_execution_evidence_and_refresh_is_io_free(driver):
    driver._status = InstrumentStatus.READY
    driver._visa_resource = object()
    driver._identity_response = "Keysight Technologies,F8800A,serial,8.0"
    driver._loaded_emulation_file = "example.smu"
    driver._emulation_running = True
    driver._active_output_ports = [1, 2]
    driver._readback_center_freq_mhz = 1960.0
    driver._local_control_reserved = True
    result = snapshot()
    fields = {field["key"]: field for field in result["fields"]}
    assert fields["loaded_emulation_file"]["value"] == "example.smu"
    assert fields["emulation_running"]["value"] is True
    assert fields["center_frequency_mhz"]["value"] == 1960.0
    assert fields["output_ports"]["source"] == "readback_cache"
    assert result["local_control_reserved"] is True
    for field in fields.values():
        assert field["observed_at"] is None
        assert field["execution_id"] is None
        assert field["session_id"] is None
        assert field["freshness"] == "unknown"
    driver._apply_session_reset()
    assert {field["key"]: field["value"] for field in snapshot()["fields"]}["loaded_emulation_file"] is None


def test_unloaded_hal_has_explicit_no_snapshot(monkeypatch):
    monkeypatch.setattr(instrument_hal_service, "get_hal_service", lambda: SimpleNamespace(drivers={}))
    assert snapshot()["availability"] == "driver_not_loaded"


def test_other_adapter_is_not_mislabelled_as_f64(monkeypatch):
    monkeypatch.setattr(instrument_hal_service, "get_hal_service", lambda: SimpleNamespace(drivers={"channelEmulator": object()}))
    assert snapshot()["availability"] == "unsupported_adapter"


def test_disconnected_driver_does_not_expose_leftover_session_cache(driver):
    driver._loaded_emulation_file = "old-session.smu"
    driver._active_output_ports = [1, 2]
    driver._readback_center_freq_mhz = 1960.0
    assert all(field["value"] is None for field in snapshot()["fields"])


def test_mock_cache_cannot_be_displayed_as_real_f64(monkeypatch):
    from app.hal.channel_emulator import MockChannelEmulator
    driver = MockChannelEmulator("mock-ce", {})
    monkeypatch.setattr(instrument_hal_service, "get_hal_service", lambda: SimpleNamespace(drivers={"channelEmulator": driver}))
    result = snapshot()
    assert result["availability"] == "simulated"
    assert result["fields"] == []


def test_snapshot_api_contract_has_checked_schema_and_ts_mirrors():
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[2]
    path = "/api/v1/instruments/channelEmulator/runtime-snapshot"
    checked = yaml.safe_load((root / "api/openapi.yaml").read_text())
    for schema in (app.openapi(), checked):
        assert schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/F64RuntimeSnapshot")
        assert schema["components"]["schemas"]["F64RuntimeSnapshot"]["properties"]["diagnostic_only"]["const"] is True
    for name in ("api.generated.ts", "api.ts"):
        assert "F64RuntimeSnapshot" in (root / "gui/src/types" / name).read_text()
