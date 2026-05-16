"""P1-1 — plan-level pre-flight validator + endpoint contract.

Pins both layers:

- ``app/services/preflight.validate_plan``: pure function over a TestPlan,
  LabProfile, db session, and a HAL drivers dict. Returns a typed
  PreflightResult.
- ``POST /api/v1/test-plans/{id}/preflight``: thin wrapper around the
  function — pins the operator-facing surface (response shape, error
  codes, the deliberate no-auto-resolve-lab decision).

What it does NOT cover:
- Seeded sequence templates propagating ``needs`` into materialised
  TestSteps — that wiring is deferred to a follow-up PR. Tests here
  synthesise TestStep rows directly to exercise the contract end-to-end.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Set
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.capabilities import (
    CE_INTERFERENCE_GENERATOR,
    CE_USER_ALIGNMENT,
    POS_SINGLE_AXIS_AZ,
)
from app.main import app
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestPlan, TestStep
from app.services.preflight import validate_plan


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
    try:
        yield
    finally:
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


def _mock_driver(capabilities: Set[str]) -> Any:
    """Stand-in for a real driver instance. The validator only reads
    `.capabilities`; nothing else on the driver matters here."""
    d = MagicMock()
    d.capabilities = set(capabilities)
    return d


def _make_plan(db, *, name="Pre-flight Test Plan") -> TestPlan:
    plan = TestPlan(
        id=uuid.uuid4(),
        name=name,
        status="ready",
        test_case_ids=[],
        created_by="pytest",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _make_lab(db) -> LabProfile:
    lab = LabProfile(
        id=uuid.uuid4(),
        name=f"Preflight-Lab-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def _add_step(
    db, plan: TestPlan, *, order: int, name: str, needs: List[str],
) -> TestStep:
    step = TestStep(
        id=uuid.uuid4(),
        test_plan_id=plan.id,
        name=name,
        type="run_measurement",
        parameters={},
        order=order,
        needs=needs,
        status="pending",
    )
    db.add(step)
    db.commit()
    return step


# ---------------------------------------------------------------------------
# validate_plan — pure function contract
# ---------------------------------------------------------------------------

class TestValidatorPureFunction:
    def test_empty_plan_is_ready(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        result = validate_plan(plan, lab, db, hal_drivers={})
        assert result.ready is True
        assert result.gaps == []
        assert result.unknown_tokens == []
        assert result.lab_capabilities == []

    def test_step_with_empty_needs_is_permissive(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        _add_step(db, plan, order=1, name="quiet step", needs=[])
        result = validate_plan(plan, lab, db, hal_drivers={})
        assert result.ready is True
        assert result.gaps == []

    def test_satisfied_need_no_gap(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {"channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR})}
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True
        assert result.gaps == []
        assert result.lab_capabilities == [CE_INTERFERENCE_GENERATOR]

    def test_unsatisfied_need_creates_gap(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        step = _add_step(
            db, plan, order=1, name="cal-tone",
            needs=[CE_INTERFERENCE_GENERATOR],
        )
        # Driver loaded but lacks the required token.
        hal = {"channelEmulator": _mock_driver(set())}
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is False
        assert len(result.gaps) == 1
        gap = result.gaps[0]
        assert gap.step_id == step.id
        assert gap.step_name == "cal-tone"
        assert gap.step_order == 1
        assert gap.missing_token == CE_INTERFERENCE_GENERATOR
        # Reason must name both the missing token and the loaded
        # categories so the GUI has something actionable to show.
        assert CE_INTERFERENCE_GENERATOR in gap.reason
        assert "channelEmulator" in gap.reason

    def test_no_drivers_loaded_at_all(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        result = validate_plan(plan, lab, db, hal_drivers={})
        assert result.ready is False
        assert len(result.gaps) == 1
        assert "(none)" in result.gaps[0].reason

    def test_unknown_token_warns_does_not_gap(self, db):
        """A typo in needs (or a token registered before the consumer
        landed) must not block the plan. Surfaces in unknown_tokens
        so the dev can fix the typo without losing the green light."""
        plan = _make_plan(db)
        lab = _make_lab(db)
        _add_step(db, plan, order=1, name="typo step",
                  needs=["ce.not_a_real_token", CE_INTERFERENCE_GENERATOR])
        hal = {"channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR})}
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True, result.gaps  # gap list empty
        assert "ce.not_a_real_token" in result.unknown_tokens

    def test_multiple_steps_multiple_gaps_in_execution_order(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        s_ok = _add_step(db, plan, order=1, name="positioner sweep",
                         needs=[POS_SINGLE_AXIS_AZ])
        s_gap1 = _add_step(db, plan, order=2, name="cal-tone",
                           needs=[CE_INTERFERENCE_GENERATOR])
        s_gap2 = _add_step(db, plan, order=3, name="user-align step",
                           needs=[CE_USER_ALIGNMENT])
        # Only positioner is fully satisfied.
        hal = {
            "positioner": _mock_driver({POS_SINGLE_AXIS_AZ}),
            "channelEmulator": _mock_driver(set()),  # missing both CE tokens
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is False
        # Gaps preserve plan execution order so the GUI can list them
        # in the order the operator will see failures.
        assert [g.step_order for g in result.gaps] == [2, 3]
        assert {g.missing_token for g in result.gaps} == {
            CE_INTERFERENCE_GENERATOR, CE_USER_ALIGNMENT,
        }

    def test_lab_capabilities_aggregated_and_sorted(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        hal = {
            "channelEmulator": _mock_driver({
                CE_INTERFERENCE_GENERATOR, CE_USER_ALIGNMENT,
            }),
            "positioner": _mock_driver({POS_SINGLE_AXIS_AZ}),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        # Sorted union — stable shape for the GUI.
        assert result.lab_capabilities == sorted({
            CE_INTERFERENCE_GENERATOR,
            CE_USER_ALIGNMENT,
            POS_SINGLE_AXIS_AZ,
        })


# ---------------------------------------------------------------------------
# POST /test-plans/{id}/preflight — endpoint contract
# ---------------------------------------------------------------------------

class TestPreflightEndpoint:
    def test_happy_path_returns_ready_with_capabilities(self, db, monkeypatch):
        plan = _make_plan(db)
        lab = _make_lab(db)
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])

        class _StubHal:
            drivers = {"channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR})}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: _StubHal(),
        )
        r = client.post(
            f"/api/v1/test-plans/{plan.id}/preflight",
            params={"lab_profile_id": str(lab.id)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ready"] is True
        assert body["gaps"] == []
        assert body["unknown_tokens"] == []
        assert body["plan_id"] == str(plan.id)
        assert body["lab_profile_id"] == str(lab.id)
        assert CE_INTERFERENCE_GENERATOR in body["lab_capabilities"]

    def test_gap_path_returns_actionable_detail(self, db, monkeypatch):
        plan = _make_plan(db)
        lab = _make_lab(db)
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])

        class _StubHal:
            drivers = {"channelEmulator": _mock_driver(set())}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: _StubHal(),
        )
        r = client.post(
            f"/api/v1/test-plans/{plan.id}/preflight",
            params={"lab_profile_id": str(lab.id)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ready"] is False
        assert len(body["gaps"]) == 1
        gap = body["gaps"][0]
        assert gap["missing_token"] == CE_INTERFERENCE_GENERATOR
        assert gap["step_name"] == "cal-tone"
        assert "channelEmulator" in gap["reason"]

    def test_missing_lab_profile_id_query_returns_422(self, db, monkeypatch):
        """No magic auto-resolve — the GUI must pass a lab explicitly.
        Pre-fix this would have inherited the commissioning factory's
        500-on-multiple-active-labs trap (see "Discovered during P2-2"
        backlog). FastAPI's required-Query enforcement is what makes
        this clean."""
        plan = _make_plan(db)

        class _StubHal:
            drivers = {}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: _StubHal(),
        )
        r = client.post(f"/api/v1/test-plans/{plan.id}/preflight")
        assert r.status_code == 422, r.text

    def test_unknown_plan_returns_404(self, db, monkeypatch):
        bogus = uuid.uuid4()
        lab = _make_lab(db)

        class _StubHal:
            drivers = {}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: _StubHal(),
        )
        r = client.post(
            f"/api/v1/test-plans/{bogus}/preflight",
            params={"lab_profile_id": str(lab.id)},
        )
        assert r.status_code == 404, r.text

    def test_unknown_lab_returns_422_with_id_named(self, db, monkeypatch):
        plan = _make_plan(db)
        bogus_lab = uuid.uuid4()

        class _StubHal:
            drivers = {}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: _StubHal(),
        )
        r = client.post(
            f"/api/v1/test-plans/{plan.id}/preflight",
            params={"lab_profile_id": str(bogus_lab)},
        )
        assert r.status_code == 422, r.text
        assert str(bogus_lab) in r.json()["detail"]
