"""Tests for the bootstrap framework + chamber duplicate / write-protection.

Covers the commercial-deployment workflow added in Phase 2-onwards:

  - ``scripts.bootstrap`` seeds canonical chamber presets idempotently.
  - System-preset rows reject PUT/DELETE with 409.
  - ``POST /chambers/{id}/duplicate`` returns an editable copy with
    ``is_system_preset=False``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.bootstrap_history import BootstrapHistory
from app.models.chamber import ChamberConfiguration
from app.services.bootstrap import ALL_SEEDERS, run_all
from app.services.bootstrap.chamber_presets import chamber_presets_seeder


# Each test gets its own in-memory SQLite DB to keep state isolated.
@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db, SessionLocal
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_client(db_session):
    db, SessionLocal = db_session

    def _override():
        local = SessionLocal()
        try:
            yield local
        finally:
            local.close()

    # Other test modules (e.g. test_chamber_configuration) install a
    # module-level override at import time. Save and restore it so we
    # don't leave them broken after our teardown.
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior


# ============================================================================
# Bootstrap framework
# ============================================================================

class TestBootstrapChamberPresets:

    def test_first_run_inserts_four_presets(self, db_session):
        db, _ = db_session
        report = run_all(db, [chamber_presets_seeder])

        assert len(report) == 1
        seeder, result, status = report[0]
        assert status == "ran"
        assert result.inserted == 4
        assert result.skipped == 0

        rows = db.query(ChamberConfiguration).filter(
            ChamberConfiguration.is_system_preset.is_(True)
        ).all()
        assert len(rows) == 4
        assert all(r.created_by == "system" for r in rows)
        assert all(r.is_active is False for r in rows)
        assert all(r.name.startswith("默认 -") for r in rows)

    def test_re_run_is_no_op(self, db_session):
        db, _ = db_session
        run_all(db, [chamber_presets_seeder])
        report = run_all(db, [chamber_presets_seeder])

        seeder, result, status = report[0]
        assert status == "skipped (up-to-date)"
        assert result is None  # Skipped path returns no metrics

        # Still exactly 4 rows — no duplicates.
        assert db.query(ChamberConfiguration).filter(
            ChamberConfiguration.is_system_preset.is_(True)
        ).count() == 4

    def test_force_reruns_but_does_not_duplicate(self, db_session):
        db, _ = db_session
        run_all(db, [chamber_presets_seeder])
        report = run_all(db, [chamber_presets_seeder], force=True)

        seeder, result, status = report[0]
        assert status == "ran"
        assert result.inserted == 0  # All 4 already exist
        assert result.skipped == 4

    def test_dry_run_writes_nothing(self, db_session):
        db, _ = db_session
        report = run_all(db, [chamber_presets_seeder], dry_run=True)

        seeder, result, status = report[0]
        assert status == "skipped (dry-run)"
        assert db.query(ChamberConfiguration).count() == 0
        assert db.query(BootstrapHistory).count() == 0

    def test_user_chambers_are_not_touched_by_force_rerun(self, db_session):
        """A user-modified row sharing a chamber_type with a preset must
        not be overwritten when bootstrap re-runs."""
        db, _ = db_session
        run_all(db, [chamber_presets_seeder])

        # Manually create a user chamber of the same chamber_type
        user_chamber = ChamberConfiguration(
            name="My Custom Type-A",
            chamber_type="type_a",
            chamber_radius_m=2.0,
            quiet_zone_diameter_m=0.6,
            num_probes=8,
            num_polarizations=2,
            num_rings=2,
            is_system_preset=False,
        )
        db.add(user_chamber)
        db.commit()
        user_id = user_chamber.id

        run_all(db, [chamber_presets_seeder], force=True)

        reread = db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == user_id
        ).first()
        assert reread is not None
        assert reread.name == "My Custom Type-A"  # Untouched
        assert reread.num_probes == 8
        assert reread.is_system_preset is False

    def test_history_row_is_recorded(self, db_session):
        db, _ = db_session
        run_all(db, [chamber_presets_seeder])

        history = db.query(BootstrapHistory).filter(
            BootstrapHistory.seeder_name == "chamber_presets"
        ).first()
        assert history is not None
        assert history.seeder_version == chamber_presets_seeder.version
        assert history.rows_inserted == 4
        assert history.rows_skipped == 0


# ============================================================================
# /chambers/{id}/duplicate + write protection
# ============================================================================

class TestChamberDuplicateAndWriteProtection:

    def _seed_presets(self, db):
        run_all(db, [chamber_presets_seeder])

    def _get_a_preset(self, client) -> dict:
        resp = client.get("/api/v1/chambers")
        items = resp.json()["items"]
        for c in items:
            if c.get("is_system_preset"):
                return c
        raise AssertionError("No system preset found in API response")

    def test_duplicate_returns_editable_copy(self, api_client):
        client, db = api_client
        self._seed_presets(db)
        preset = self._get_a_preset(client)

        resp = client.post(f"/api/v1/chambers/{preset['id']}/duplicate")
        assert resp.status_code == 201, resp.text
        clone = resp.json()

        assert clone["id"] != preset["id"]
        assert clone["is_system_preset"] is False
        assert clone["is_active"] is False
        assert clone["name"] == f"{preset['name']} (副本)"
        # Same physical params — it's a clone, not a fresh chamber
        assert clone["chamber_type"] == preset["chamber_type"]
        assert clone["chamber_radius_m"] == preset["chamber_radius_m"]
        assert clone["num_probes"] == preset["num_probes"]

    def test_put_on_system_preset_returns_409(self, api_client):
        client, db = api_client
        self._seed_presets(db)
        preset = self._get_a_preset(client)

        resp = client.put(
            f"/api/v1/chambers/{preset['id']}",
            json={"name": "should not stick"},
        )
        assert resp.status_code == 409, resp.text
        assert "system preset" in resp.json()["detail"].lower()

        # Confirm row is unchanged
        check = client.get(f"/api/v1/chambers/{preset['id']}").json()
        assert check["name"] == preset["name"]

    def test_delete_on_system_preset_returns_409(self, api_client):
        client, db = api_client
        self._seed_presets(db)
        preset = self._get_a_preset(client)

        resp = client.delete(f"/api/v1/chambers/{preset['id']}")
        assert resp.status_code == 409, resp.text
        assert "预设" in resp.json()["detail"]  # 系统预设不可删 (中文文案)

        # Row still exists
        assert client.get(f"/api/v1/chambers/{preset['id']}").status_code == 200

    def test_put_on_duplicated_clone_succeeds(self, api_client):
        """Sanity: clone is editable."""
        client, db = api_client
        self._seed_presets(db)
        preset = self._get_a_preset(client)

        clone = client.post(f"/api/v1/chambers/{preset['id']}/duplicate").json()
        resp = client.put(
            f"/api/v1/chambers/{clone['id']}",
            json={"name": "我的暗室"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "我的暗室"

    def test_delete_on_duplicated_clone_succeeds(self, api_client):
        client, db = api_client
        self._seed_presets(db)
        preset = self._get_a_preset(client)
        clone = client.post(f"/api/v1/chambers/{preset['id']}/duplicate").json()

        resp = client.delete(f"/api/v1/chambers/{clone['id']}")
        assert resp.status_code == 200, resp.text
        assert client.get(f"/api/v1/chambers/{clone['id']}").status_code == 404


# ============================================================================
# Sanity: registered seeders include chamber_presets
# ============================================================================

def test_chamber_presets_is_registered():
    assert chamber_presets_seeder in ALL_SEEDERS
    # Names must be unique — bootstrap_history uses name as PK
    names = [s.name for s in ALL_SEEDERS]
    assert len(names) == len(set(names))
