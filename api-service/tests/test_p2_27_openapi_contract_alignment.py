"""P2-27: live OpenAPI must describe fields FastAPI always serializes."""

from app.main import app


SERIALIZED_RESPONSE_SCHEMAS = (
    "ProbeResponse",
    "DriverReadinessRowResponse",
    "SubnetReachabilityResponse",
    "LabProfileReadinessResponse",
    "CalibrationReadinessResponse",
    "DutAttachReadinessResponse",
    "HALReadinessResponse",
    "ExecutionHistoryItem",
    "LogEntry",
    "LogTailResponse",
    "FEInstrumentModel",
    "FEInstrumentConnection",
    "FEInstrumentCategory",
    "ChamberConfigurationResponse",
)


def test_live_openapi_requires_every_serialized_response_field():
    schemas = app.openapi()["components"]["schemas"]

    for schema_name in SERIALIZED_RESPONSE_SCHEMAS:
        schema = schemas[schema_name]
        assert set(schema.get("required", [])) == set(schema["properties"]), (
            f"{schema_name} marks runtime-serialized fields optional: "
            f"{sorted(set(schema['properties']) - set(schema.get('required', [])))}"
        )


def test_live_openapi_exposes_readiness_and_catalog_status_allowlists():
    schemas = app.openapi()["components"]["schemas"]

    assert schemas["DriverReadinessRowResponse"]["properties"]["status"]["enum"] == [
        "ok",
        "warn",
        "fail",
        "skipped",
    ]
    assert schemas["LabProfileReadinessResponse"]["properties"]["status"]["enum"] == [
        "ok",
        "inactive",
        "missing",
        "ambiguous",
    ]
    assert schemas["CalibrationReadinessResponse"]["properties"]["status"]["enum"] == [
        "valid",
        "expired",
        "missing",
        "no_lab",
    ]
    assert schemas["FEInstrumentModel"]["properties"]["status"]["enum"] == [
        "available",
        "pending_dev",
    ]
