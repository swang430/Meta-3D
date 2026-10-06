"""Operator confirmation binds sync to the server's saved configuration, not HAL state."""
from uuid import uuid4

import pytest

from tests.test_lab_profile_api import setup_db, db, lab, chamber, client  # noqa: F401
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel


@pytest.fixture
def saved(db, lab):
    category = InstrumentCategory(category_key="vna", category_name="VNA", driver_mode="mock")
    db.add(category)
    db.flush()
    model = InstrumentModel(category_id=category.id, vendor="vendor", model="model", capabilities={})
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    connection = InstrumentConnection(category_id=category.id, endpoint="saved:5025", protocol="socket", connection_params={"timeout_ms": 3000})
    db.add(connection)
    lab.instrument_bindings = []
    db.commit()
    return category, model, connection


def catalog_token():
    response = client.get("/api/v1/instruments/catalog")
    assert response.status_code == 200
    return response.json()["categories"][0]["savedConfigurationDigest"]


def sync(lab, token):
    return client.put(f"/api/v1/lab-profiles/{lab.id}/instrument-bindings/vna/sync-current", json={"expected_saved_configuration_digest": token})


def test_sync_requires_explicit_operator_confirmation(saved, lab, db):
    response = client.put(f"/api/v1/lab-profiles/{lab.id}/instrument-bindings/vna/sync-current")
    assert response.status_code == 422
    db.refresh(lab)
    assert lab.instrument_bindings == []


def test_confirmed_sync_uses_saved_config(saved, lab, db):
    token = catalog_token()
    assert len(token) == 64
    response = sync(lab, token)
    assert response.status_code == 200, response.text
    db.refresh(lab)
    assert lab.instrument_bindings[0]["connection_endpoint"] == "saved:5025"


@pytest.mark.parametrize("field", ["endpoint", "protocol", "notes", "connection_params", "selected_model_id", "driver_mode", "is_active"])
def test_saved_drift_is_conflict_without_mutating_binding(saved, lab, db, field):
    category, model, connection = saved
    token = catalog_token()
    if field == "selected_model_id":
        other = InstrumentModel(id=uuid4(), category_id=category.id, vendor="other", model="other", capabilities={})
        db.add(other)
        category.selected_model_id = other.id
    elif field == "driver_mode":
        category.driver_mode = "real"
    elif field == "is_active":
        category.is_active = False
    else:
        setattr(connection, field, {"timeout_ms": 4000} if field == "connection_params" else "changed")
    db.commit()
    response = sync(lab, token)
    assert response.status_code == 409, response.text
    db.refresh(lab)
    assert lab.instrument_bindings == []


def test_runtime_observation_does_not_change_saved_token(saved, db):
    token = catalog_token()
    saved[2].status = "connected"
    saved[2].last_error = "observed"
    db.commit()
    assert catalog_token() == token


def test_malformed_confirmation_is_rejected(saved, lab):
    assert sync(lab, "not-a-digest").status_code == 422


def test_unsaved_base_station_has_no_confirmable_snapshot(saved, db):
    from app.services.instrument_saved_configuration import saved_configuration_digest
    category, model, connection = saved
    category.category_key = "baseStation"
    connection.base_station_model_presets = {}
    assert saved_configuration_digest(category, model, connection) is None


def test_base_station_runtime_params_are_not_saved_revision(saved):
    from app.services.instrument_saved_configuration import saved_configuration_digest
    category, model, connection = saved
    category.category_key = "baseStation"
    connection.base_station_model_presets = {str(model.id): {
        "schema_version": 1, "model_id": str(model.id), "endpoint": "saved:5025",
        "controller": "socket", "notes": "", "connection_params": {"timeout_ms": 3000},
        "base_station_adapter_profile": None,
    }}
    token = saved_configuration_digest(category, model, connection)
    assert token
    connection.connection_params = {"timeout_ms": 3000, "detected_test_app": "observation"}
    assert saved_configuration_digest(category, model, connection) == token


def test_confirmation_contract_four_mirrors():
    from pathlib import Path
    import yaml
    from app.main import app
    root = Path(__file__).resolve().parents[2]
    live = app.openapi()
    checked = yaml.safe_load((root / "api/openapi.yaml").read_text())
    path = "/api/v1/lab-profiles/{lab_profile_id}/instrument-bindings/{category_key}/sync-current"
    for schema in (live, checked):
        assert schema["paths"][path]["put"]["requestBody"]["required"] is True
        request = schema["components"]["schemas"]["InstrumentBindingSyncRequest"]
        assert request["required"] == ["expected_saved_configuration_digest"]
        assert request["properties"]["expected_saved_configuration_digest"]["pattern"] == "^[0-9a-f]{64}$"
    assert "savedConfigurationDigest" in live["components"]["schemas"]["FEInstrumentCategory"]["properties"]
    assert "savedConfigurationDigest" in checked["components"]["schemas"]["InstrumentCategory"]["properties"]
    for file in ("api.generated.ts", "api.ts"):
        source = (root / "gui/src/types" / file).read_text()
        assert "expected_saved_configuration_digest" in source
        assert "savedConfigurationDigest" in source
