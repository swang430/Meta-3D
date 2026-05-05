"""P2: lab-profile API + RF chain resolution endpoint.

The calibration UI calls GET /lab-profiles to populate the picker, then
GET /lab-profiles/{id}/rf-chains?operating_mode=mimo_ota to render the
preview before the operator hits Start. These tests cover both reads.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.chamber import (
    ChamberType,
    create_chamber_from_preset,
)
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    # Setting the dep override inside the fixture (not at module scope) avoids
    # collisions with other test modules that also override get_db. Pytest
    # imports every test module first, so module-level overrides clobber each
    # other; per-test scope keeps each file's override pointing at its own engine.
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P2 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="P2-Test-Lab",
        description="Created by test",
        organization="Test Org",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def topology(db, chamber):
    """Active mimo_ota topology with one chain (probe 0 V)."""
    t = SwitchTopology(
        switch_category_id=uuid.uuid4(),
        chamber_id=chamber.id,
        name="P2 Topology",
        nodes=[
            {"id": "ce_b1", "type": "ce_port", "label": "B1.1", "params": {}},
            {"id": "probe_0_v", "type": "probe", "label": "Probe 0 V",
             "params": {"probe_id": 0, "polarization": "V"}},
        ],
        connections=[
            {"id": "conn_p0v", "source": "ce_b1", "target": "probe_0_v",
             "calibrated_loss_db": 0.42, "modes": ["mimo_ota"]},
        ],
        operating_modes=[
            {"id": "mimo_ota", "name": "MIMO OTA", "active_connections": ["conn_p0v"]},
        ],
        is_active=True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestListLabProfiles:
    def test_returns_active_only_by_default(self, db, lab):
        # Inactive lab shouldn't show up.
        inactive = LabProfile(name="Inactive-Lab", is_active=False)
        db.add(inactive)
        db.commit()

        resp = client.get("/api/v1/lab-profiles")
        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()]
        assert "P2-Test-Lab" in names
        assert "Inactive-Lab" not in names

    def test_includes_chamber_name(self, lab, chamber):
        resp = client.get("/api/v1/lab-profiles")
        body = resp.json()
        entry = next((it for it in body if it["id"] == str(lab.id)), None)
        assert entry is not None
        assert entry["chamber_config_id"] == str(chamber.id)
        assert entry["chamber_name"] == chamber.name


class TestGetRFChains:
    def test_resolves_active_mimo_ota_chains(self, lab, topology):
        resp = client.get(
            f"/api/v1/lab-profiles/{lab.id}/rf-chains",
            params={"operating_mode": "mimo_ota"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["lab_name"] == "P2-Test-Lab"
        assert body["topology_name"] == topology.name
        assert len(body["chains"]) == 1
        chain = body["chains"][0]
        assert chain["chain_id"] == "conn_p0v"
        assert chain["probe_id"] == 0
        assert chain["polarization"] == "V"
        assert chain["cable_loss_db"] == 0.42

    def test_unknown_mode_returns_success_false_with_warning(self, lab, topology):
        resp = client.get(
            f"/api/v1/lab-profiles/{lab.id}/rf-chains",
            params={"operating_mode": "trp_only"},
        )
        # Endpoint stays 200 but `success=False` + warnings carry actionable info
        # so the GUI can render an empty-state with "go fix the topology".
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["chains"] == []
        assert any("trp_only" in w for w in body["warnings"])

    def test_unknown_lab_returns_422(self):
        resp = client.get(
            f"/api/v1/lab-profiles/{uuid.uuid4()}/rf-chains",
            params={"operating_mode": "mimo_ota"},
        )
        assert resp.status_code == 422
