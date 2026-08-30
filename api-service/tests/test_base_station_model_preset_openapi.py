from pathlib import Path

import yaml

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_base_station_model_presets_are_typed_in_all_api_mirrors():
    live = app.openapi()["components"]["schemas"]
    live_property = live["FEInstrumentConnection"]["properties"][
        "base_station_model_presets"
    ]
    assert live_property["additionalProperties"] == {
        "$ref": "#/components/schemas/BaseStationModelPreset"
    }
    assert "base_station_model_presets" in live["FEInstrumentConnection"]["required"]

    checked = yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())[
        "components"
    ]["schemas"]
    assert checked["InstrumentConnection"]["properties"][
        "base_station_model_presets"
    ]["additionalProperties"] == {
        "$ref": "#/components/schemas/BaseStationModelPreset"
    }
    assert checked["BaseStationModelPreset"]["additionalProperties"] is False
    assert set(checked["BaseStationModelPreset"]["required"]) == {
        "schema_version",
        "model_id",
        "endpoint",
        "controller",
        "notes",
        "connection_params",
        "base_station_adapter_profile",
    }

    generated = (REPO_ROOT / "gui/src/types/api.generated.ts").read_text()
    manual = (REPO_ROOT / "gui/src/types/api.ts").read_text()
    assert 'base_station_model_presets: {\n                [key: string]: components["schemas"]["BaseStationModelPreset"]' in generated
    assert "export type BaseStationModelPreset" in manual
    assert "base_station_model_presets?: Record<string, BaseStationModelPreset>" in manual
