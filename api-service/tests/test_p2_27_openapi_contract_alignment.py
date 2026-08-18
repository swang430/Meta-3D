"""P2-27: live and checked-in OpenAPI must describe serialized contracts."""

from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
import yaml

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]


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


def test_checked_in_openapi_mirrors_present_p2_27_response_contracts():
    schemas = yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())["components"]["schemas"]

    for schema_name in (
        "InstrumentCategory",
        "InstrumentModel",
        "InstrumentConnection",
        "HALReadinessResponse",
        "DriverReadinessRow",
        "LabProfileReadiness",
        "CalibrationReadiness",
        "DutAttachReadiness",
        "SubnetReachability",
        "TestExecutionItem",
        "SystemLogEntry",
        "SystemLogTailResponse",
    ):
        schema = schemas[schema_name]
        assert set(schema.get("required", [])) == set(schema["properties"]), (
            f"checked-in {schema_name} still marks serialized fields optional: "
            f"{sorted(set(schema['properties']) - set(schema.get('required', [])))}"
        )

    assert schemas["InstrumentModel"]["properties"]["status"]["enum"] == [
        "available",
        "pending_dev",
    ]
    assert schemas["DutAttachReadiness"]["properties"]["status"]["enum"] == [
        "not_implemented",
    ]


def test_pydantic_lower_bound_supports_serialization_required_config():
    requirements = (REPO_ROOT / "api-service/requirements.txt").read_text().splitlines()
    line = next(line for line in requirements if line.startswith("pydantic>="))
    requirement = Requirement(line.split("#", 1)[0].strip())

    assert Version("2.4.0") in requirement.specifier
    assert Version("2.3.0") not in requirement.specifier
