"""P2-27: live OpenAPI must describe fields FastAPI always serializes."""

from app.main import app


SERIALIZED_RESPONSE_SCHEMAS = (
    "ProbeResponse",
    "HALReadinessResponse",
    "ExecutionHistoryItem",
    "LogEntry",
    "LogTailResponse",
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
