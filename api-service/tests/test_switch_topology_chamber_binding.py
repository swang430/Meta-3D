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


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    # Per-test dep override (see test_lab_profile_api for why module-scoped
    # overrides collide between test modules).
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


class TestListFilterByChamber:
    """Two chambers can each own their own topology row. The list endpoint
    must support filtering by chamber_id so TopologyEditor can pull the
    chamber-specific row without sweeping in others'."""

    def test_chamber_id_filter_returns_only_matching_chamber(self, db, chamber):
        """Two topologies for the same switch, different chambers — filter
        by chamber must narrow to one."""
        # Second chamber for the same switch
        chamber_b = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Chamber-B")
        db.add(chamber_b)
        db.commit()
        db.refresh(chamber_b)

        switch_cat_id = uuid.uuid4()
        topo_a = SwitchTopology(
            switch_category_id=switch_cat_id,
            chamber_id=chamber.id,
            name="topo-for-A",
            nodes=[], connections=[], operating_modes=[],
            is_active=True,
        )
        topo_b = SwitchTopology(
            switch_category_id=switch_cat_id,
            chamber_id=chamber_b.id,
            name="topo-for-B",
            nodes=[], connections=[], operating_modes=[],
            is_active=True,
        )
        db.add(topo_a)
        db.add(topo_b)
        db.commit()

        # No filter: both rows visible.
        all_resp = client.get(
            "/api/v1/switch-topologies",
            params={"switch_category_id": str(switch_cat_id)},
        )
        assert all_resp.status_code == 200
        assert all_resp.json()["total"] == 2

        # Filter by chamber A: only topo-for-A.
        a_resp = client.get(
            "/api/v1/switch-topologies",
            params={
                "switch_category_id": str(switch_cat_id),
                "chamber_id": str(chamber.id),
            },
        )
        assert a_resp.status_code == 200
        a_items = a_resp.json()["items"]
        assert len(a_items) == 1
        assert a_items[0]["name"] == "topo-for-A"
        assert a_items[0]["chamber_id"] == str(chamber.id)

        # Filter by chamber B: only topo-for-B.
        b_resp = client.get(
            "/api/v1/switch-topologies",
            params={
                "switch_category_id": str(switch_cat_id),
                "chamber_id": str(chamber_b.id),
            },
        )
        assert b_resp.status_code == 200
        b_items = b_resp.json()["items"]
        assert len(b_items) == 1
        assert b_items[0]["name"] == "topo-for-B"
        assert b_items[0]["chamber_id"] == str(chamber_b.id)

    def test_chamber_id_filter_excludes_legacy_null_chamber_rows(self, db, chamber):
        """Legacy rows with chamber_id=NULL must NOT match a chamber filter,
        since SQL '= chamber_uuid' excludes NULL by definition."""
        switch_cat_id = uuid.uuid4()
        legacy = SwitchTopology(
            switch_category_id=switch_cat_id,
            chamber_id=None,
            name="legacy-null",
            nodes=[], connections=[], operating_modes=[],
            is_active=True,
        )
        bound = SwitchTopology(
            switch_category_id=switch_cat_id,
            chamber_id=chamber.id,
            name="bound",
            nodes=[], connections=[], operating_modes=[],
            is_active=True,
        )
        db.add(legacy)
        db.add(bound)
        db.commit()

        # No filter: both visible.
        no_filter = client.get(
            "/api/v1/switch-topologies",
            params={"switch_category_id": str(switch_cat_id)},
        ).json()
        assert no_filter["total"] == 2

        # With chamber filter: only the bound one.
        with_filter = client.get(
            "/api/v1/switch-topologies",
            params={
                "switch_category_id": str(switch_cat_id),
                "chamber_id": str(chamber.id),
            },
        ).json()
        assert with_filter["total"] == 1
        assert with_filter["items"][0]["name"] == "bound"
