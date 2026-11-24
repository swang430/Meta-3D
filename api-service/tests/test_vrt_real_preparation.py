from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("station_mode,bandwidth", [("real", 100), ("simulated", 100), ("real", 20)])
def test_real_preflight_separates_bindings_working_point_and_calibration(monkeypatch, station_mode, bandwidth):
    from app.api import road_test_conducted as api
    from tests.test_smu_project_inventory import _OLD_SCD

    station = SimpleNamespace(status="configured", execution_mode=station_mode,
                              binding_digest="station", instrument_connection_id="uxm")
    monkeypatch.setattr(api, "resolve_base_station_binding", lambda *_: station)
    asset = SimpleNamespace(payload={"scd_config": dict(_OLD_SCD, bandwidth_mhz=100)})
    network = SimpleNamespace(band=_OLD_SCD["band"], bandwidth_mhz=bandwidth)
    evidence, reasons = api.real_preflight(None, None, None, asset, network)
    assert evidence["center_frequency_hz"] == 3600000000
    assert evidence["base_station_binding_digest"] == "station"
    assert any("传导校准" in r for r in reasons)
    assert any("真实基站" in r for r in reasons) == (station_mode != "real")
    assert any("带宽" in r for r in reasons) == (bandwidth != 100)
