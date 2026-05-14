"""POST /lab-profiles — wizard-driven create flow (P0-2 roadmap).

The wizard collects a chamber + ≥1 instrument binding + a name, then
sends one POST. These tests pin:
  - Happy path: payload lands as a real LabProfile row, response shape
    matches GET summary.
  - 422 when the chamber FK doesn't resolve.
  - 422 when instrument_bindings is empty (acceptance forbids zero-
    instrument labs — wizard would let the operator stumble into a
    "Lab exists but no calibration possible" trap otherwise).
  - 409 when the name collides (uniqueness is the operator-facing
    error, not 500).
  - Defaults: is_active defaults to True so first-call can start
    immediately after wizard finishes.
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
from app.models.chamber import ChamberConfiguration
from app.models.lab_profile import LabProfile


# ---------------------------------------------------------------------------
# Per-test fresh SQLite (matches the rest of the suite — production is PG
# but the contract being pinned is dialect-agnostic)
# ---------------------------------------------------------------------------

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
def client(db_session):
    db, SessionLocal = db_session

    def _override():
        local = SessionLocal()
        try:
            yield local
        finally:
            local.close()

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c, db
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior


@pytest.fixture
def seeded_chamber(db_session):
    """A chamber row to FK against — created directly, not via the
    bootstrap seeder, so this test file is independent of seeder state."""
    db, _ = db_session
    chamber = ChamberConfiguration(
        id=uuid.uuid4(),
        name="Type-A Test Chamber",
        chamber_type="type_a",
        chamber_radius_m=3.0,
        quiet_zone_diameter_m=1.0,
        num_probes=32,
        num_polarizations=2,
        num_rings=4,
        is_system_preset=False,
        is_active=True,
    )
    db.add(chamber)
    db.commit()
    return chamber


def _instrument_category_id() -> str:
    """Stable but arbitrary UUID — the wizard only cares that the
    JSONB array stores it; FK to instrument_categories is not enforced
    on instrument_bindings (it's an embedded array of arbitrary IDs)."""
    return str(uuid.uuid4())


def _minimal_payload(chamber_id, *, name="CAICT-Lab-1") -> dict:
    return {
        "name": name,
        "chamber_config_id": str(chamber_id),
        "instrument_bindings": [
            {
                "category_id": _instrument_category_id(),
                "connection_endpoint": "192.168.1.10:5025",
                "driver_mode": "auto",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestCreateHappyPath:
    def test_201_returns_summary_shape(self, client, seeded_chamber):
        c, _ = client
        r = c.post(
            "/api/v1/lab-profiles",
            json=_minimal_payload(seeded_chamber.id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # Matches GET /lab-profiles summary shape so wizard can cache it.
        assert set(body.keys()) >= {
            "id", "name", "chamber_config_id", "chamber_name", "is_active",
        }
        assert body["name"] == "CAICT-Lab-1"
        assert body["chamber_config_id"] == str(seeded_chamber.id)
        assert body["chamber_name"] == "Type-A Test Chamber"
        assert body["is_active"] is True

    def test_row_actually_persisted(self, client, seeded_chamber, db_session):
        c, _ = client
        c.post("/api/v1/lab-profiles", json=_minimal_payload(seeded_chamber.id))

        _, SessionLocal = db_session
        db = SessionLocal()
        try:
            rows = db.query(LabProfile).all()
            assert len(rows) == 1
            row = rows[0]
            assert row.name == "CAICT-Lab-1"
            assert row.chamber_config_id == seeded_chamber.id
            assert row.is_active is True
            # JSONB array round-trips with the binding the wizard sent.
            assert len(row.instrument_bindings) == 1
            assert row.instrument_bindings[0]["connection_endpoint"] == "192.168.1.10:5025"
        finally:
            db.close()

    def test_name_is_trimmed(self, client, seeded_chamber):
        """Wizard input fields commonly leave leading/trailing spaces.
        Strip so the uniqueness constraint isn't fooled into accepting
        'foo ' and 'foo' as different names."""
        c, _ = client
        payload = _minimal_payload(seeded_chamber.id, name="  CAICT-Lab-Trim  ")
        r = c.post("/api/v1/lab-profiles", json=payload)
        assert r.status_code == 201, r.text
        assert r.json()["name"] == "CAICT-Lab-Trim"

    def test_optional_fields_default_to_null(self, client, seeded_chamber):
        c, _ = client
        r = c.post(
            "/api/v1/lab-profiles",
            json=_minimal_payload(seeded_chamber.id),
        )
        body = r.json()
        assert body["description"] is None
        assert body["organization"] is None
        assert body["location"] is None


# ---------------------------------------------------------------------------
# Validation: ≥1 instrument binding (acceptance criterion)
# ---------------------------------------------------------------------------

class TestInstrumentBindingsRequired:
    def test_empty_bindings_array_rejected_422(self, client, seeded_chamber):
        c, _ = client
        payload = _minimal_payload(seeded_chamber.id)
        payload["instrument_bindings"] = []
        r = c.post("/api/v1/lab-profiles", json=payload)
        assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Validation: chamber FK must resolve
# ---------------------------------------------------------------------------

class TestChamberMustExist:
    def test_unknown_chamber_id_returns_422(self, client):
        c, _ = client
        payload = _minimal_payload(uuid.uuid4())  # never inserted
        r = c.post("/api/v1/lab-profiles", json=payload)
        assert r.status_code == 422, r.text
        assert "chamber_config_id" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Duplicate name → 409 with actionable error
# ---------------------------------------------------------------------------

class TestNameUniqueness:
    def test_duplicate_name_returns_409(self, client, seeded_chamber):
        c, _ = client
        c.post(
            "/api/v1/lab-profiles",
            json=_minimal_payload(seeded_chamber.id, name="dup-name"),
        )
        r2 = c.post(
            "/api/v1/lab-profiles",
            json=_minimal_payload(seeded_chamber.id, name="dup-name"),
        )
        assert r2.status_code == 409, r2.text
        assert "already exists" in r2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# category_id must be a UUID — Codex P1 review on PR #18.
# ---------------------------------------------------------------------------
#
# `services/diagnostic_context._parse_instrument_bindings` joins
# bindings back to `InstrumentCategory.id` to populate `category_key`.
# Non-UUID `category_id` values silently degrade `category_key` to
# None, which collapses the *IDN? diagnostic sweep into "no HAL
# driver" for every binding. Pin both the rejection (so a future
# wizard regression that sends the catalog `key` string can't sneak
# through) and the happy path (so the resolver contract is exercised
# end-to-end).

class TestCategoryIdMustBeUuid:
    def test_string_category_key_rejected_422(self, client, seeded_chamber):
        c, _ = client
        payload = _minimal_payload(seeded_chamber.id, name="lab-cat-str")
        payload["instrument_bindings"][0]["category_id"] = "channelEmulator"
        r = c.post("/api/v1/lab-profiles", json=payload)
        assert r.status_code == 422, r.text
        # Pydantic surfaces the UUID-parse failure on the right field
        # so the wizard's notifications block can show something
        # actionable instead of a generic 500.
        body = r.json()
        assert any(
            "uuid" in (e.get("type") or "").lower()
            and "category_id" in (e.get("loc") or [])
            for e in body.get("detail", [])
        ), body

    def test_uuid_category_id_resolves_through_diagnostic_context(
        self, client, seeded_chamber, db_session,
    ):
        """End-to-end: persist a binding with a real InstrumentCategory.id,
        then ask the diagnostic context resolver to round-trip it.
        Guards against the original Codex regression where the wizard
        stored catalog keys and the resolver couldn't find them."""
        from app.models.instrument import InstrumentCategory
        from app.services.diagnostic_context import build_diagnostic_context

        db, _ = db_session
        cat = InstrumentCategory(
            id=uuid.uuid4(),
            category_key="channelEmulator",
            category_name="Channel Emulator",
            display_order=1,
            is_active=True,
        )
        db.add(cat)
        db.commit()

        c, _ = client
        payload = _minimal_payload(seeded_chamber.id, name="lab-resolves")
        payload["instrument_bindings"][0]["category_id"] = str(cat.id)
        payload["instrument_bindings"][0]["role"] = "primary_channel_emulator"
        r = c.post("/api/v1/lab-profiles", json=payload)
        assert r.status_code == 201, r.text
        lab_id = uuid.UUID(r.json()["id"])

        # The diagnostic context resolver should hydrate
        # category_key from the UUID we sent — proving the contract
        # the original bug broke. Skip rf-chain resolution; this
        # test only exercises the binding-resolve path.
        ctx = build_diagnostic_context(
            db, lab_profile_id=lab_id, resolve_rf_chains_too=False,
        )
        bindings = ctx.instrument_bindings
        assert len(bindings) == 1
        assert bindings[0].category_key == "channelEmulator"
        assert bindings[0].category_id == cat.id
