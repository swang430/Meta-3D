"""P2-45: Diagnostic/Formal qualification must be public and mirrored."""

from pathlib import Path

import yaml

from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]


def _checked() -> dict:
    return yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())


def test_registered_adapters_declare_the_site_certification_formal_gate():
    assert RealCmw500Driver.adapter_manifest.formal_gate == "site_certification"
    assert RealUxmDriver.adapter_manifest.formal_gate == "site_certification"


def test_live_and_checked_contracts_publish_policy_certification_and_qualification():
    live = app.openapi()["components"]["schemas"]
    checked_doc = _checked()
    checked = checked_doc["components"]["schemas"]

    for schemas in (live, checked):
        assert "TestCaseExecutionPolicy" in schemas
        assert "BaseStationSiteCertification" in schemas
        assert "ExecutionQualification" in schemas

    assert "execution_policy" in live["TestCaseResponse"]["properties"]
    assert "execution_classification" in live["ExecutionHistoryItem"]["properties"]
    assert "execution_qualification" in live["SessionResponse"]["properties"]
    assert "base_station_site_certification" in live["FEInstrumentConnection"]["properties"]

    assert "execution_policy" in checked["TestCaseResponse"]["properties"]
    assert "execution_classification" in checked["TestExecutionItem"]["properties"]
    assert "execution_qualification" in checked["SessionResponse"]["properties"]
    assert "base_station_site_certification" in checked["InstrumentConnection"]["properties"]


def test_checked_contract_exposes_dedicated_server_owned_write_endpoints():
    paths = _checked()["paths"]
    assert "/api/v1/test-plans/cases/{test_case_id}/execution-policy" in paths
    certify = paths[
        "/api/v1/instruments/connections/{connection_id}/base-station-site-certification"
    ]["put"]
    revoke = paths[
        "/api/v1/instruments/connections/{connection_id}/base-station-site-certification/revoke"
    ]["put"]
    for operation in (certify, revoke):
        request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        assert "proof" not in str(request_schema).lower()
        assert "identity" not in str(request_schema).lower()
