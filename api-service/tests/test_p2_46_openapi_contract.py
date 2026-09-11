"""P2-46: live and checked-in capability manifest v2 stay aligned."""

from pathlib import Path

import yaml

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_FIELDS = {
    "schema_version",
    "adapter_id",
    "model_name",
    "vendor",
    "rats",
    "capabilities",
    "rat_capabilities",
    "operations",
    "mac_profiles",
    "config_fields",
    "attach_stages",
    "measurement",
    "profile_requirement",
    "profile_schema_version",
    "profile_fields",
    "manual_sources",
    "diagnostic_supported",
    "formal_gate",
}
NESTED_SCHEMAS = {
    "BaseStationRatCapability",
    "BaseStationConfigFieldCapability",
    "BaseStationAttachStageCapability",
    "BaseStationMeasurementCapability",
    "BaseStationMetricCapability",
    "BaseStationMacProfileCapability",
    "BaseStationMacDimensionCapability",
    "BaseStationMacDimensionValueCapability",
}
MAC_CAPABILITY_SHAPES = {
    "BaseStationMacProfileCapability": (
        {
            "kind",
            "profile_version",
            "rat",
            "application_evidence",
            "source_reference",
            "dimensions",
        },
        {
            "kind",
            "profile_version",
            "rat",
            "application_evidence",
            "source_reference",
        },
    ),
    "BaseStationMacDimensionCapability": (
        {"dimension", "values"},
        {"dimension", "values"},
    ),
    "BaseStationMacDimensionValueCapability": (
        {
            "value",
            "support",
            "satisfying_options",
            "required_options",
            "minimum_firmware",
            "requires",
            "reason",
            "source_reference",
        },
        {"value", "support", "reason", "source_reference"},
    ),
}


def _checked() -> dict:
    return yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())


def _allowed_values(property_schema: dict) -> list:
    if "enum" in property_schema:
        return property_schema["enum"]
    return [property_schema["const"]]


def test_live_and_checked_openapi_require_the_complete_manifest_v2_shape():
    live = app.openapi()["components"]["schemas"]
    checked = _checked()["components"]["schemas"]

    for schemas in (live, checked):
        manifest = schemas["BaseStationAdapterManifest"]
        assert set(manifest["properties"]) == MANIFEST_FIELDS
        assert set(manifest["required"]) == MANIFEST_FIELDS
        assert manifest["additionalProperties"] is False
        assert _allowed_values(manifest["properties"]["schema_version"]) == [2]
        assert NESTED_SCHEMAS <= set(schemas)
        for name in NESTED_SCHEMAS:
            assert schemas[name]["additionalProperties"] is False


def test_profile_version_and_nullable_capability_fields_are_not_manifest_version_mirrors():
    live = app.openapi()["components"]["schemas"]
    checked = _checked()["components"]["schemas"]

    for schemas in (live, checked):
        manifest = schemas["BaseStationAdapterManifest"]
        assert "profile_schema_version" in manifest["required"]
        assert "measurement" in manifest["required"]
        assert "profile_schema_version" in manifest["properties"]
        assert "measurement" in manifest["properties"]
        assert manifest["properties"]["profile_requirement"]["enum"] == [
            "required",
            "not_applicable",
        ]

        metric = schemas["BaseStationMetricCapability"]
        assert "ratio" in metric["properties"]["unit"]["enum"]
        assert metric["properties"]["evidence"]["enum"] == [
            "authoritative",
            "diagnostic_only",
            "unavailable",
        ]
        attach = schemas["BaseStationAttachStageCapability"]
        assert attach["properties"]["evidence"]["enum"] == [
            "authoritative",
            "diagnostic_only",
            "unavailable",
            "not_applicable",
        ]


def test_live_and_checked_openapi_define_the_same_mac_dimension_contract():
    live = app.openapi()["components"]["schemas"]
    checked = _checked()["components"]["schemas"]

    for schemas in (live, checked):
        assert set(MAC_CAPABILITY_SHAPES) <= set(schemas)
        for name, (properties, required) in MAC_CAPABILITY_SHAPES.items():
            schema = schemas[name]
            assert set(schema["properties"]) == properties
            assert set(schema["required"]) == required
            assert schema["additionalProperties"] is False

        profile = schemas["BaseStationMacProfileCapability"]
        assert profile["properties"]["dimensions"]["items"]["$ref"].endswith(
            "/BaseStationMacDimensionCapability"
        )
        dimension = schemas["BaseStationMacDimensionCapability"]
        assert dimension["properties"]["values"]["items"]["$ref"].endswith(
            "/BaseStationMacDimensionValueCapability"
        )
        value = schemas["BaseStationMacDimensionValueCapability"]["properties"]
        assert {branch["type"] for branch in value["value"]["anyOf"]} == {
            "string",
            "integer",
            "boolean",
            "null",
        }
        assert value["support"]["enum"] == [
            "authoritative",
            "diagnostic_only",
            "not_applicable",
        ]
        assert value["requires"]["items"]["const"] == "normal_cyclic_prefix"
