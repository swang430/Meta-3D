"""Lifespan auto-seed tests for P0-1 (first-call roadmap).

The contract we're pinning: when ``TestClient(app)`` enters FastAPI's
lifespan on a fresh DB, the bootstrap step seeds factory defaults so
the operator sees ``GET /chambers`` return 4 system presets, ``GET
/instruments/categories`` return a populated catalog, etc. — without
anyone running ``python -m scripts.bootstrap`` first.

Why this is a separate test file from ``test_bootstrap_and_duplicate``:
the existing file pokes ``run_all()`` directly in test code; this file
pokes the **lifespan wire-up** in [api-service/app/main.py]
(``settings.bootstrap_on_startup`` branch). Two different defects can
hide here — the seeders themselves regress, OR the lifespan stops
calling them — and the two layers must stay independently covered.

The pre-existing manual escape hatch (``python -m scripts.bootstrap``)
keeps working regardless; this file does not need to re-test it.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.database import Base, get_db
from app.main import app
from app.models.bootstrap_history import BootstrapHistory
from app.models.chamber import ChamberConfiguration


# ---------------------------------------------------------------------------
# Per-test fresh SQLite + monkey-patched SessionLocal/engine
# ---------------------------------------------------------------------------
#
# The lifespan path uses ``app.db.database.SessionLocal`` directly (not
# ``get_db``), so an in-memory engine has to be installed at the module-
# level binding before TestClient enters lifespan. The same SessionLocal
# is then re-used to override ``get_db`` so the API endpoints see the
# same seeded rows.

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

    # Swap the module-level bindings. ``init_db`` uses ``engine`` and
    # the bootstrap wrapper imports ``SessionLocal`` at call time, so
    # both will pick up the patched values inside lifespan.
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


# ---------------------------------------------------------------------------
# Cold start: empty DB → factory defaults visible after lifespan startup
# ---------------------------------------------------------------------------

class TestLifespanColdStart:
    """A brand-new deployment must not strand the operator on 'create
    your first chamber' — the four canonical system presets land in the
    DB automatically when the API process boots."""

    def test_four_chamber_presets_visible_after_startup(self, test_db):
        engine, _ = test_db
        # Sanity: DB is empty before TestClient triggers lifespan.
        with engine.connect() as conn:
            from sqlalchemy import text
            n = conn.execute(text(
                "SELECT COUNT(*) FROM chamber_configurations"
            )).scalar()
        assert n == 0

        with TestClient(app) as client:
            r = client.get("/api/v1/chambers")
            assert r.status_code == 200, r.text
            body = r.json()
            presets = [c for c in body["items"] if c.get("is_system_preset")]
            assert len(presets) == 4, [c["name"] for c in body["items"]]
            # All four canonical chamber types are present.
            assert {p["chamber_type"] for p in presets} == {
                "type_a", "type_b", "type_c", "type_d",
            }

    def test_bootstrap_history_records_each_seeder(self, test_db):
        _, TestSessionLocal = test_db
        with TestClient(app):
            pass  # Lifespan ran on enter; nothing else needed for this test.

        db = TestSessionLocal()
        try:
            history = db.query(BootstrapHistory).all()
        finally:
            db.close()
        names = {h.seeder_name for h in history}
        # All six registered seeders must appear in bootstrap_history.
        assert names == {
            "chamber_presets",
            "probes",
            "instruments",
            "sequences",
            "report_templates",
            "test_case_templates",
        }, names

    def test_instrument_catalog_seeded_with_at_least_twelve(self, test_db):
        """Roadmap acceptance: 12+ instrument models on empty DB."""
        with TestClient(app) as client:
            r = client.get("/api/v1/instruments/catalog")
            assert r.status_code == 200, r.text
            body = r.json()
        # FEInstrumentsResponse: {categories: [{models: [...]}, ...]}
        models = [
            m for cat in body.get("categories", [])
            for m in cat.get("models", [])
        ]
        assert len(models) >= 12, f"only {len(models)} instrument models seeded"


# ---------------------------------------------------------------------------
# Warm restart: lifespan re-entry is a true no-op (no duplicates)
# ---------------------------------------------------------------------------

class TestLifespanWarmRestart:
    """A second start on an already-seeded DB must not double-insert.
    This is what protects production from running ``docker-compose
    restart`` and accidentally getting 8 chamber presets."""

    def test_second_lifespan_is_idempotent(self, test_db):
        _, TestSessionLocal = test_db

        with TestClient(app):
            pass

        with TestClient(app):
            pass

        db = TestSessionLocal()
        try:
            chambers = db.query(ChamberConfiguration).filter(
                ChamberConfiguration.is_system_preset.is_(True)
            ).count()
            history_rows = db.query(BootstrapHistory).count()
        finally:
            db.close()
        assert chambers == 4
        # bootstrap_history has one row per seeder name (PK enforced).
        assert history_rows == 6


# ---------------------------------------------------------------------------
# Escape hatch: BOOTSTRAP_ON_STARTUP=false
# ---------------------------------------------------------------------------

class TestEnvVarDisablesBootstrap:
    """Ops who want to manage seed data out-of-band (custom deploy
    script, snapshot restore, etc.) need a hard off-switch. The flag
    must be 'true zero writes' — not 'still inserts but doesn't log'."""

    def test_disabled_flag_writes_nothing(self, test_db, monkeypatch):
        monkeypatch.setattr(settings, "bootstrap_on_startup", False)
        _, TestSessionLocal = test_db

        with TestClient(app):
            pass

        db = TestSessionLocal()
        try:
            chambers = db.query(ChamberConfiguration).count()
            history = db.query(BootstrapHistory).count()
        finally:
            db.close()
        assert chambers == 0
        assert history == 0

    def test_disabled_then_enabled_seeds_normally(
        self, test_db, monkeypatch,
    ):
        """After flipping the flag back on, a restart must catch up —
        defends against ops accidentally leaving the flag off and then
        wondering why their dashboard is empty."""
        _, TestSessionLocal = test_db

        monkeypatch.setattr(settings, "bootstrap_on_startup", False)
        with TestClient(app):
            pass

        monkeypatch.setattr(settings, "bootstrap_on_startup", True)
        with TestClient(app):
            pass

        db = TestSessionLocal()
        try:
            n = db.query(ChamberConfiguration).filter(
                ChamberConfiguration.is_system_preset.is_(True)
            ).count()
        finally:
            db.close()
        assert n == 4
