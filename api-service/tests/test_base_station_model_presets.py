from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.instrument import InstrumentConnection
from app.schemas.instrument import FEConnectionUpdate
from app.services.base_station_model_preset import BaseStationModelPreset


def _cmw_profile() -> dict:
    return {
        "schema_version": 1,
        "adapter": "cmw500",
        "lte_2x2_internal_route": {
            "pcc_bb_board": "SUA1",
            "rx_connector": "RF1C",
            "rx_converter": "RX1",
            "tx1_connector": "RF1O",
            "tx1_converter": "TX1",
            "tx2_connector": "RF3C",
            "tx2_converter": "TX2",
        },
    }


def test_preset_is_strict_json_safe_and_keeps_model_specific_profile():
    model_id = uuid4()

    preset = BaseStationModelPreset.model_validate(
        {
            "schema_version": 1,
            "model_id": str(model_id),
            "endpoint": "TCPIP0::192.168.0.149::hislip0::INSTR",
            "controller": "hislip",
            "notes": "site CMW500",
            "connection_params": {"timeout_sec": 30},
            "base_station_adapter_profile": _cmw_profile(),
        }
    )

    assert preset.model_id == model_id
    assert preset.model_dump(mode="json")["base_station_adapter_profile"] == _cmw_profile()
    with pytest.raises(ValidationError):
        BaseStationModelPreset.model_validate(
            {**preset.model_dump(mode="json"), "unexpected": True}
        )


def test_preset_rejects_blank_endpoint_and_embedded_profile_in_generic_params():
    payload = {
        "schema_version": 1,
        "model_id": str(uuid4()),
        "endpoint": "   ",
        "controller": "",
        "notes": "",
        "connection_params": {"base_station_adapter_profile": _cmw_profile()},
        "base_station_adapter_profile": None,
    }
    with pytest.raises(ValidationError):
        BaseStationModelPreset.model_validate(payload)


def test_server_owned_preset_map_has_dedicated_storage_and_no_write_field():
    assert hasattr(InstrumentConnection, "base_station_model_presets")
    assert "base_station_model_presets" not in FEConnectionUpdate.model_fields


def test_preset_backfill_never_promotes_runtime_detected_app_to_saved_truth():
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "f2a4c6e8b0d1_add_base_station_model_presets.py"
    ).read_text(encoding="utf-8")
    assert 'params.pop("detected_test_app", None)' in migration


def test_hal_connect_does_not_persist_runtime_detected_test_app():
    source = (
        Path(__file__).parents[1]
        / "app/services/instrument_hal_service.py"
    ).read_text(encoding="utf-8")
    assert 'params["detected_test_app"] = detected' not in source
