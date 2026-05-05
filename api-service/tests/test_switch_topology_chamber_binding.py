"""P1: chamber_id is required when importing or saving a SwitchTopology.

Before P1, importing /switch-topologies/import/caict-default left chamber_id
NULL, and PATCH could clear it again — the topology row existed but had no
chamber to point at, so calibration / measure couldn't resolve it. P1 makes
chamber_id required at the API layer for new imports + active saves.
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


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P1 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


class TestImportCaictDefaultRequiresChamber:
    def test_import_without_chamber_id_returns_422(self):
        # FastAPI returns 422 for missing required query param.
        resp = client.post(
            "/api/v1/switch-topologies/import/caict-default",
            params={"switch_category_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422

    def test_import_with_unknown_chamber_id_returns_422(self):
        resp = client.post(
            "/api/v1/switch-topologies/import/caict-default",
            params={
                "switch_category_id": str(uuid.uuid4()),
                "chamber_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 422
        assert "Chamber" in resp.json()["detail"]

    def test_import_with_valid_chamber_succeeds(self, chamber):
        resp = client.post(
            "/api/v1/switch-topologies/import/caict-default",
            params={
                "switch_category_id": str(uuid.uuid4()),
                "chamber_id": str(chamber.id),
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chamber_id"] == str(chamber.id)


class TestActiveTopologyRequiresChamber:
    def test_patch_active_topology_to_null_chamber_returns_422(self, db, chamber):
        topo = SwitchTopology(
            switch_category_id=uuid.uuid4(),
            chamber_id=chamber.id,
            name="P1 patch test",
            nodes=[],
            connections=[],
            operating_modes=[],
            is_active=True,
        )
        db.add(topo)
        db.commit()
        db.refresh(topo)

        # Operator tries to clear chamber_id — backend must refuse because
        # the topology stays active and downstream consumers couldn't resolve it.
        resp = client.patch(
            f"/api/v1/switch-topologies/{topo.id}",
            json={"chamber_id": None},
        )
        assert resp.status_code == 422
        assert "chamber_id" in resp.json()["detail"]

    def test_patch_legacy_inactive_topology_without_chamber_allowed(self, db):
        # Legacy rows from before P1 may have chamber_id=NULL. Editing them
        # while inactive shouldn't be blocked — only reactivation must come
        # with a chamber binding.
        topo = SwitchTopology(
            switch_category_id=uuid.uuid4(),
            chamber_id=None,
            name="legacy",
            nodes=[],
            connections=[],
            operating_modes=[],
            is_active=False,
        )
        db.add(topo)
        db.commit()
        db.refresh(topo)

        resp = client.patch(
            f"/api/v1/switch-topologies/{topo.id}",
            json={"name": "renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

    def test_patch_assigns_chamber_to_legacy_topology(self, db, chamber):
        topo = SwitchTopology(
            switch_category_id=uuid.uuid4(),
            chamber_id=None,
            name="legacy-fixme",
            nodes=[],
            connections=[],
            operating_modes=[],
            is_active=True,  # would normally fail save, but stored directly
        )
        db.add(topo)
        db.commit()
        db.refresh(topo)

        resp = client.patch(
            f"/api/v1/switch-topologies/{topo.id}",
            json={"chamber_id": str(chamber.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["chamber_id"] == str(chamber.id)
