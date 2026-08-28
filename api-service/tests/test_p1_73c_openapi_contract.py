"""P1-73C Task 16: live, checked-in and generated CMW contracts stay aligned."""

from pathlib import Path

import yaml

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
READINESS_FIELDS = {
    "status",
    "adapter_registered",
    "connection_id",
    "model",
    "identity_verified",
    "firmware_version",
    "options",
    "formal_enabled",
    "formal_updated_at",
    "fdd_ready",
    "tdd_ready",
    "detail",
    "binding_digest",
}


def test_live_and_checked_openapi_publish_the_same_cmw_readiness_contract():
    live = app.openapi()["components"]["schemas"]
    checked = yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())[
        "components"
    ]["schemas"]

    live_readiness = live["Cmw500Lte2x2ReadinessResponse"]
    checked_readiness = checked["Cmw500Lte2x2Readiness"]
    for schema in (live_readiness, checked_readiness):
        assert set(schema["properties"]) == READINESS_FIELDS
        assert set(schema["required"]) == READINESS_FIELDS
        assert schema["additionalProperties"] is False
        assert schema["properties"]["status"]["enum"] == [
            "ready",
            "warning",
            "diagnostic",
            "not_applicable",
        ]

    live_hal = live["HALReadinessResponse"]
    checked_hal = checked["HALReadinessResponse"]
    assert "cmw500_lte_2x2" in live_hal["required"]
    assert "cmw500_lte_2x2" in checked_hal["required"]
    assert live_hal["properties"]["cmw500_lte_2x2"]["anyOf"][0]["$ref"].endswith(
        "/Cmw500Lte2x2ReadinessResponse"
    )
    assert checked_hal["properties"]["cmw500_lte_2x2"]["allOf"][0]["$ref"] == (
        "#/components/schemas/Cmw500Lte2x2Readiness"
    )
    assert checked_hal["properties"]["cmw500_lte_2x2"]["nullable"] is True


def test_checked_openapi_keeps_formal_approval_on_the_dedicated_endpoint():
    document = yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())
    operation = document["paths"][
        "/api/v1/instruments/connections/{connection_id}/formal-capabilities/"
        "cmw500-lte-2x2"
    ]["put"]

    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Cmw500FormalCapabilityUpdate"
    }
    assert operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/Cmw500FormalCapabilityResponse"}
