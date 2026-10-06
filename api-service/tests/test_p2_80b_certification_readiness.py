"""P2-80B：坏认证不能被 Readiness 洗成缺失，HAL 两个响应分支同义。"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app
from app.models.lab_profile import LabProfile
from app.schemas.base_station_binding import BaseStationBindingPreviewResponse
from app.services.base_station_compatibility import build_not_evaluated_base_station_compatibility
from app.services.readiness import DutAttachReadiness, ReadinessReport
from tests.test_p2_68_catalog_invalid_stored_fields import (
    catalog_db, _set, VALID_BS_CERTIFICATION, REPO_ROOT,
)


@pytest.mark.parametrize("hal_available", [False, True])
@pytest.mark.parametrize("raw,status", [
    (None, "missing"), ({}, "invalid"), ([], "invalid"),
    (False, "invalid"), (0, "invalid"), ("broken", "invalid"),
    (VALID_BS_CERTIFICATION, "valid"),
    ({**VALID_BS_CERTIFICATION, "status": "revoked", "revoked_by": "operator",
      "revoked_at": "2026-10-06T00:00:00Z", "revocation_reason": "撤销"}, "valid"),
])
def test_readiness_exposes_authoritative_certification_state(catalog_db, monkeypatch, hal_available, raw, status):
    Session, ids = catalog_db
    _set(Session, ids["bs_conn"], "base_station_site_certification", raw)
    with Session() as db:
        from app.models.instrument import InstrumentConnection
        connection = db.get(InstrumentConnection, ids["bs_conn"])
        lab = LabProfile(id=uuid4(), name="认证状态", is_active=True, instrument_bindings=[{
            "category_id": str(connection.category_id),
            "connection_endpoint": connection.endpoint,
            "driver_mode": "mock", "role": "baseStation",
        }])
        db.add(lab)
        db.commit()
        lab_id = str(lab.id)
    binding = BaseStationBindingPreviewResponse(
        status="configured", binding_digest="a" * 64, execution_mode="real",
        adapter_id="uxm_5g_e7515b", model_name="UXM 5G E7515B",
        category_id=None, instrument_model_id=None,
        instrument_connection_id=str(ids["bs_conn"]), lab_profile_id=lab_id,
        resolved_binding=None, runtime_driver=None, detail="测试只替换 binding 解析边界",
    )
    compatibility = build_not_evaluated_base_station_compatibility(lab_profile_id=lab_id, reason="未选择用例")
    monkeypatch.setattr("app.services.base_station_compatibility.build_base_station_preview_bundle", lambda *a, **k: (binding, compatibility))
    report = ReadinessReport(drivers=[], lab_profile=None, calibration=None, dut_attach=DutAttachReadiness(), generated_at_iso="2026-10-06T00:00:00") if hal_available else None
    monkeypatch.setattr("app.services.instrument_hal_service.get_hal_service", lambda: SimpleNamespace(last_readiness_report=report))
    response = TestClient(app).get("/api/v1/instruments/hal/readiness")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is hal_available
    assert body["base_station_site_certification_status"] == status
    assert bool(body["base_station_site_certification_error"]) is (status == "invalid")
    assert body["base_station_site_certification"] == (raw if status == "valid" else None)
    with Session() as db:
        from app.models.instrument import InstrumentConnection
        assert db.get(InstrumentConnection, ids["bs_conn"]).base_station_site_certification == raw


def test_certification_state_contract_in_live_and_checked_openapi():
    for document in (app.openapi(), yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())):
        schema = document["components"]["schemas"]["HALReadinessResponse"]
        assert schema["properties"]["base_station_site_certification_status"]["enum"] == ["missing", "invalid", "valid"]
        assert "base_station_site_certification_status" in schema["required"]
        assert "base_station_site_certification_error" in schema["required"]


def test_missing_driver_does_not_hide_stored_certification_damage(catalog_db, monkeypatch):
    Session, ids = catalog_db
    _set(Session, ids["bs_conn"], "base_station_site_certification", {})
    from app.models.instrument import InstrumentConnection
    with Session() as db:
        connection = db.get(InstrumentConnection, ids["bs_conn"])
        lab = LabProfile(id=uuid4(), name="HAL 未加载", is_active=True, instrument_bindings=[{
            "category_id": str(connection.category_id),
            "connection_endpoint": connection.endpoint,
            "driver_mode": "mock", "role": "baseStation",
        }])
        db.add(lab)
        db.commit()
    monkeypatch.setattr("app.services.instrument_hal_service.get_hal_service", lambda: None)
    response = TestClient(app).get("/api/v1/instruments/hal/readiness")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["base_station_binding"]["status"] == "invalid"
    assert body["base_station_site_certification_status"] == "invalid"
    assert body["base_station_site_certification_error"]
