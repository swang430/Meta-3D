"""P2-44: live/checked-in BaseStation binding contract must stay aligned."""

from pathlib import Path

import yaml

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]


def _checked() -> dict:
    return yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())


def test_catalog_manifest_is_typed_and_nullable_in_both_openapi_documents():
    live = app.openapi()["components"]["schemas"]
    live_property = live["FEInstrumentModel"]["properties"]["base_station_manifest"]
    assert live_property["anyOf"][0] == {
        "$ref": "#/components/schemas/BaseStationAdapterManifest"
    }
    assert {item.get("type") for item in live_property["anyOf"]} == {None, "null"}

    checked = _checked()["components"]["schemas"]
    checked_property = checked["InstrumentModel"]["properties"]["base_station_manifest"]
    assert checked_property == {
        "allOf": [{"$ref": "#/components/schemas/BaseStationAdapterManifest"}],
        "nullable": True,
    }
    assert checked["BaseStationAdapterManifest"]["additionalProperties"] is False
    assert len(checked["BaseStationProfileFieldManifest"]["required"]) == 5


def test_preview_sync_and_readiness_publish_one_binding_shape():
    checked = _checked()
    schemas = checked["components"]["schemas"]
    paths = checked["paths"]
    preview_ref = "#/components/schemas/BaseStationBindingPreviewResponse"

    assert paths[
        "/api/v1/lab-profiles/{lab_profile_id}/instrument-bindings/baseStation/preview"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": preview_ref
    }
    assert paths[
        "/api/v1/lab-profiles/{lab_profile_id}/instrument-bindings/{category_key}/sync-current"
    ]["put"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/InstrumentBindingSyncResponse"
    }
    assert schemas["InstrumentBindingSyncResponse"]["properties"]["resolved"] == {
        "allOf": [{"$ref": preview_ref}],
        "nullable": True,
    }
    assert schemas["HALReadinessResponse"]["properties"]["base_station_binding"] == {
        "allOf": [{"$ref": preview_ref}],
        "nullable": True,
    }
    assert "binding_digest" in schemas["Cmw500Lte2x2Readiness"]["required"]

