"""P2-65: compatibility readiness stays aligned across API mirrors."""

from pathlib import Path

import yaml

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIEW_PATH = (
    "/api/v1/lab-profiles/{lab_profile_id}/instrument-bindings/"
    "baseStation/preview"
)
SYNC_PATH = (
    "/api/v1/lab-profiles/{lab_profile_id}/instrument-bindings/"
    "{category_key}/sync-current"
)
READINESS_PATH = "/api/v1/instruments/hal/readiness"
COMPATIBILITY_REF = "#/components/schemas/BaseStationCompatibilityPreviewResponse"


def _checked() -> dict:
    return yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())


def _parameter(operation: dict, name: str) -> dict:
    return next(item for item in operation["parameters"] if item["name"] == name)


def test_live_and_checked_openapi_publish_optional_saved_testcase_context():
    live = app.openapi()
    checked = _checked()

    for document in (live, checked):
        for path, method in (
            (PREVIEW_PATH, "get"),
            (SYNC_PATH, "put"),
            (READINESS_PATH, "get"),
        ):
            parameter = _parameter(document["paths"][path][method], "test_case_id")
            assert parameter["in"] == "query"
            assert parameter["required"] is False


def test_checked_openapi_publishes_one_shared_compatibility_projection():
    schemas = _checked()["components"]["schemas"]
    compatibility = schemas["BaseStationCompatibilityPreviewResponse"]

    assert compatibility["additionalProperties"] is False
    assert set(compatibility["properties"]) == {
        "schema_version",
        "status",
        "compatible",
        "test_case_id",
        "lab_profile_id",
        "binding_digest",
        "execution_mode",
        "requirements",
        "verdict",
        "reasons",
        "detail",
    }
    assert set(compatibility["required"]) == set(compatibility["properties"])
    assert compatibility["properties"]["status"]["enum"] == [
        "compatible",
        "incompatible",
        "no_adapter",
        "not_evaluated",
        "invalid",
    ]

    binding_property = schemas["BaseStationBindingPreviewResponse"]["properties"]
    assert binding_property["testcase_compatibility"] == {
        "allOf": [{"$ref": COMPATIBILITY_REF}],
        "nullable": True,
    }
    sync_property = schemas["InstrumentBindingSyncResponse"]["properties"]
    assert sync_property["testcase_compatibility"] == {
        "allOf": [{"$ref": COMPATIBILITY_REF}],
        "nullable": True,
    }
    readiness = schemas["HALReadinessResponse"]
    assert readiness["properties"]["base_station_testcase_compatibility"] == {
        "$ref": COMPATIBILITY_REF
    }
    assert "base_station_testcase_compatibility" in readiness["required"]


def test_live_openapi_exposes_the_same_compatibility_consumers():
    schemas = app.openapi()["components"]["schemas"]

    assert "BaseStationCompatibilityPreviewResponse" in schemas
    assert schemas["BaseStationBindingPreviewResponse"]["properties"][
        "testcase_compatibility"
    ]["anyOf"][0] == {"$ref": COMPATIBILITY_REF}
    assert schemas["InstrumentBindingSyncResponse"]["properties"][
        "testcase_compatibility"
    ]["anyOf"][0] == {"$ref": COMPATIBILITY_REF}
    assert schemas["HALReadinessResponse"]["properties"][
        "base_station_testcase_compatibility"
    ] == {"$ref": COMPATIBILITY_REF}
