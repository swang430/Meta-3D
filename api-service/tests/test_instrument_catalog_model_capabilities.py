"""Pin the catalog API's ``model_capabilities`` field (P2-3).

``GET /api/v1/instruments/catalog`` returns one ``model_capabilities``
list per model. The list is built at request time by looking up the
registered driver class via ``get_real_driver_class`` and reading its
``model_capabilities`` ClassVar. This is the GUI's data source for
"can this model satisfy plan-level capability needs?" at binding-edit
time, before any HAL Reload.

Pinned here so a future refactor that loses the field (e.g. catalog
endpoint rewrites, registry rewires) breaks the test before it breaks
the GUI's capability gap UX.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app


@pytest.fixture
def test_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine,
    )
    monkeypatch.setattr("app.db.database.engine", engine)
    monkeypatch.setattr("app.db.database.SessionLocal", TestSessionLocal)

    def _override():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    try:
        yield engine, TestSessionLocal
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=engine)


def _find_model(body: dict, category_key: str, model_name: str) -> dict:
    """Walk catalog response, return the model dict matching (cat, name)."""
    for cat in body.get("categories", []):
        if cat.get("key") != category_key:
            continue
        for m in cat.get("models", []):
            if m.get("model") == model_name:
                return m
    raise AssertionError(
        f"model {model_name!r} not found in category {category_key!r}; "
        f"got models={[(c['key'], [m['model'] for m in c['models']]) for c in body.get('categories', [])]}"
    )


class TestCatalogModelCapabilitiesField:
    def test_registered_base_station_models_expose_public_adapter_manifests(
        self, test_db
    ):
        with TestClient(app) as client:
            response = client.get("/api/v1/instruments/catalog")
        assert response.status_code == 200, response.text
        body = response.json()

        cmw = _find_model(body, "baseStation", "CMW500")
        uxm = _find_model(body, "baseStation", "UXM 5G E7515B")
        assert cmw["base_station_manifest"]["adapter_id"] == "cmw500"
        assert cmw["base_station_manifest"]["profile_requirement"] == "required"
        assert len(cmw["base_station_manifest"]["profile_fields"]) == 7
        assert cmw["base_station_manifest"]["formal_gate"] == "connection_approval"
        assert uxm["base_station_manifest"]["adapter_id"] == "uxm"
        assert uxm["base_station_manifest"]["profile_requirement"] == "not_applicable"
        assert uxm["base_station_manifest"]["profile_fields"] == []

    def test_non_base_station_models_have_no_adapter_manifest(self, test_db):
        with TestClient(app) as client:
            response = client.get("/api/v1/instruments/catalog")
        f64 = _find_model(response.json(), "channelEmulator", "PROPSIM F64")
        assert f64["base_station_manifest"] is None

    def test_f64_exposes_both_ce_tokens(self, test_db):
        with TestClient(app) as client:
            r = client.get("/api/v1/instruments/catalog")
            assert r.status_code == 200, r.text
            body = r.json()
        f64 = _find_model(body, "channelEmulator", "PROPSIM F64")
        assert "model_capabilities" in f64, f64
        assert sorted(f64["model_capabilities"]) == [
            "ce.interference_generator",
            "ce.user_alignment",
        ]
        # Field is independent of the legacy datasheet-derived
        # ``capabilities`` badges (which carry "MIMO 8x8" / "100 MHz BW"
        # / etc. text). Pin that they don't collide.
        assert isinstance(f64["capabilities"], list)
        assert "ce.interference_generator" not in f64["capabilities"]

    def test_fs16_exposes_empty_list(self, test_db):
        """FS16 declares no ce.* tokens. GUI uses empty list to drive
        "this model can't satisfy the plan's interference-gen need"
        warning at binding time — pin the empty-not-missing contract."""
        with TestClient(app) as client:
            r = client.get("/api/v1/instruments/catalog")
            body = r.json()
        fs16 = _find_model(body, "channelEmulator", "PROPSIM FS16")
        assert fs16["model_capabilities"] == []

    def test_aerotech_a3200_exposes_only_sourced_single_axis_token(self, test_db):
        with TestClient(app) as client:
            r = client.get("/api/v1/instruments/catalog")
            body = r.json()
        a3200 = _find_model(body, "positioner", "A3200")
        assert a3200["model_capabilities"] == ["pos.single_axis_az"]

    def test_model_without_real_driver_returns_empty_list(self, test_db):
        """Models seeded in the catalog that don't have a real-driver
        class registered (status: pending_dev) must still serialize
        ``model_capabilities: []`` — GUI iterates the field unconditionally
        and would crash on KeyError if it were elided."""
        with TestClient(app) as client:
            r = client.get("/api/v1/instruments/catalog")
            body = r.json()
        # Find any pending_dev model and assert the field is present.
        pending = [
            m
            for cat in body.get("categories", [])
            for m in cat.get("models", [])
            if m.get("status") == "pending_dev"
        ]
        if not pending:
            pytest.skip("seed catalog currently has no pending_dev models")
        for m in pending:
            assert m["model_capabilities"] == [], (m["model"], m)

    def test_all_models_in_response_include_field(self, test_db):
        """Schema-level pin: every model dict in the catalog response
        carries ``model_capabilities`` (even as []). Prevents a partial
        rollout from silently breaking GUI iteration."""
        with TestClient(app) as client:
            r = client.get("/api/v1/instruments/catalog")
            body = r.json()
        for cat in body.get("categories", []):
            for m in cat.get("models", []):
                assert "model_capabilities" in m, (cat["key"], m)
                assert isinstance(m["model_capabilities"], list), (cat["key"], m)
