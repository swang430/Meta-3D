"""Pin the HTTP layer's handling of LabProfile-resolution edge cases
on ``POST /api/v1/commissioning/sessions``.

The legacy behavior raised ValueError that propagated uncaught,
surfacing as **500 Internal Server Error** to the GUI ("初始化失败
错误代码500" — what the operator actually saw during P2-2 smoke
when 3 orphan active labs accumulated in dev PG).

Post-fix:
- 0 active labs        → 422 detail.kind = "none"
- 2+ active labs       → 422 detail.kind = "ambiguous" + active_labs[]
- explicit unknown id  → 422 detail (plain str)
- 1 active lab + no id → 201 (back-compat with single-lab dev/test)
- explicit valid id    → 201

The 422 detail.active_labs[] shape is the GUI's contract — it builds
the picker straight from this response without re-fetching, so pin
the field names + types exactly.
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
from app.hal import MockBaseStation
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile
from app.services.instrument_hal_service import get_hal_service


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    hal = get_hal_service()
    prior_base_station = hal.drivers.get("baseStation")
    hal.drivers["baseStation"] = MockBaseStation("mock-bs", {"model": "Mock"})
    with TestingSessionLocal() as db:
        db.add(InstrumentCategory(
            category_key="baseStation",
            category_name="Base Station",
            driver_mode="mock",
        ))
        db.commit()
    try:
        yield
    finally:
        if prior_base_station is None:
            hal.drivers.pop("baseStation", None)
        else:
            hal.drivers["baseStation"] = prior_base_station
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _add_lab(db, *, name: str, active: bool = True) -> LabProfile:
    category = db.query(InstrumentCategory).filter_by(
        category_key="baseStation"
    ).one()
    lab = LabProfile(
        id=uuid.uuid4(),
        name=name,
        is_active=active,
        instrument_bindings=[{
            "category_id": str(category.id),
            "instrument_model_id": None,
            "connection_endpoint": None,
            "driver_mode": "mock",
            "role": "baseStation",
        }],
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


# ---------------------------------------------------------------------------

class TestCreateSessionLabResolution:
    def test_zero_active_returns_422_kind_none(self, db):
        # No labs at all → fallback can't pick anything.
        r = client.post("/api/v1/commissioning/sessions", json={})
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert detail["kind"] == "none"
        assert detail["active_labs"] == []
        assert "No active LabProfile" in detail["message"]

    def test_two_active_returns_422_kind_ambiguous_with_picker_data(self, db):
        """The GUI's commissioning sandbox renders detail.active_labs
        as a picker. Pin shape: list of {id: str, name: str}, sorted
        by name (stable across requests)."""
        lab_b = _add_lab(db, name="b-second-lab")
        lab_a = _add_lab(db, name="a-first-lab")

        r = client.post("/api/v1/commissioning/sessions", json={})
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert detail["kind"] == "ambiguous"
        assert len(detail["active_labs"]) == 2
        # JSON-safe shape: id is a string (not UUID object), sorted by name
        assert detail["active_labs"][0] == {
            "id": str(lab_a.id), "name": "a-first-lab",
        }
        assert detail["active_labs"][1] == {
            "id": str(lab_b.id), "name": "b-second-lab",
        }
        assert "Multiple active" in detail["message"]

    def test_one_active_with_no_id_returns_201(self, db):
        """Back-compat: single-active fallback is intentionally preserved
        so existing scripts / dev installs keep working."""
        _add_lab(db, name="solo-lab")
        r = client.post("/api/v1/commissioning/sessions", json={})
        assert r.status_code == 201, r.text

    def test_explicit_id_returns_201(self, db):
        """Picking from the ambiguous list is exactly this path:
        operator chooses lab_profile_id explicitly, no fallback runs."""
        # ambiguity exists, but explicit id resolves it
        lab = _add_lab(db, name="chosen-lab")
        _add_lab(db, name="other-lab")
        r = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id)},
        )
        assert r.status_code == 201, r.text

    def test_explicit_unknown_id_returns_422(self, db):
        """Passing a bogus id is also a 422 (not 500). Detail is a
        plain string here, not the structured ambiguous payload —
        the caller already chose, so there's no picker to render."""
        bogus = uuid.uuid4()
        r = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(bogus)},
        )
        assert r.status_code == 422, r.text
        assert str(bogus) in r.json()["detail"]
        assert "not found" in r.json()["detail"]

    def test_explicit_inactive_id_returns_422(self, db):
        lab = _add_lab(db, name="dormant-lab", active=False)
        r = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id)},
        )
        assert r.status_code == 422, r.text
        assert "inactive" in r.json()["detail"]
