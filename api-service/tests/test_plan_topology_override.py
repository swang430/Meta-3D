"""P2-1 Phase 2.3 — per-plan UXM topology override.

Pins three layers:

1. **TestPlan.topology_profile_id column** + Pydantic schema flow-through:
   ``POST /test-plans`` accepts the field; row stores it.
2. **PUT /test-plans/{id}/topology-profile** dedicated set/clear/validate
   endpoint (mirrors `PUT /instruments/{cat}/topology-profile` shape).
3. **TestExecutionService.apply_plan_topology_profile_if_set** — best-
   effort apply at plan start, all failure modes return a structured
   dict rather than raising. Pin every reason value the GUI may need
   to render.

Test isolation: SQLite in-memory with `Base.metadata.create_all` (same
pattern as test_uxm_topology_profile.py).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.uxm_command_profiles import Uxm5GNRTestAppProfile
from app.main import app
from app.models.test_plan import (
    TestPlan as TestPlanModel,
    TestPlanStatus,
)
from app.services.bootstrap.topology_profiles import topology_profiles_seeder
from app.services.test_plan_service import TestExecutionService


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


def _make_ready_plan(
    db, *, topology_profile_id: str | None = None,
) -> TestPlanModel:
    plan = TestPlanModel(
        id=uuid.uuid4(),
        name="t",
        created_by="tester",
        status=TestPlanStatus.READY,
        topology_profile_id=topology_profile_id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ============================================================
# Layer 1: column + Pydantic flow-through
# ============================================================


class TestPlanTopologyProfileColumn:
    def test_create_plan_persists_topology_profile_id(self, db):
        resp = client.post(
            "/api/v1/test-plans",
            json={
                "name": "p", "created_by": "tester",
                "topology_profile_id": "caict_n78_2x2",
            },
        )
        assert resp.status_code == 201, resp.json()
        body = resp.json()
        assert body["topology_profile_id"] == "caict_n78_2x2"
        # DB round-trip (UUID column needs uuid.UUID, not raw string,
        # for SQLite's adapter — same pattern as the binding tests).
        plan = (
            db.query(TestPlanModel)
            .filter(TestPlanModel.id == uuid.UUID(body["id"]))
            .first()
        )
        assert plan.topology_profile_id == "caict_n78_2x2"

    def test_create_plan_topology_field_optional(self, db):
        """No topology_profile_id key → column stays null. Operator who
        doesn't care about plan-level override doesn't have to."""
        resp = client.post(
            "/api/v1/test-plans",
            json={"name": "p", "created_by": "tester"},
        )
        assert resp.status_code == 201
        assert resp.json()["topology_profile_id"] is None


# ============================================================
# Layer 2: PUT /test-plans/{id}/topology-profile
# ============================================================


class TestSetPlanTopologyProfileEndpoint:
    def test_404_for_unknown_plan(self, db):
        resp = client.put(
            f"/api/v1/test-plans/{uuid.uuid4()}/topology-profile",
            json={"profile_id": "caict_n78_2x2"},
        )
        assert resp.status_code == 404

    def test_set_validates_profile_exists_via_in_code_fallback(self, db):
        """Greenfield path: bootstrap seeder hasn't run, but the
        in-code registry has 'caict_n78_2x2' so validation succeeds."""
        plan = _make_ready_plan(db)
        resp = client.put(
            f"/api/v1/test-plans/{plan.id}/topology-profile",
            json={"profile_id": "caict_n78_2x2"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["persisted"] is True
        assert body["profile_id"] == "caict_n78_2x2"
        db.expire_all()
        refreshed = db.query(TestPlanModel).filter(TestPlanModel.id == plan.id).first()
        assert refreshed.topology_profile_id == "caict_n78_2x2"

    def test_set_validates_profile_exists_via_db(self, db):
        """When the seeder has run, validation hits the DB row first."""
        topology_profiles_seeder.run(db)
        plan = _make_ready_plan(db)
        resp = client.put(
            f"/api/v1/test-plans/{plan.id}/topology-profile",
            json={"profile_id": "caict_n78_4x4"},
        )
        assert resp.status_code == 200
        assert resp.json()["profile_id"] == "caict_n78_4x4"

    def test_set_404_for_unknown_profile(self, db):
        plan = _make_ready_plan(db)
        resp = client.put(
            f"/api/v1/test-plans/{plan.id}/topology-profile",
            json={"profile_id": "does_not_exist"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
        # DB unchanged — refuses bail before persist
        db.expire_all()
        refreshed = db.query(TestPlanModel).filter(TestPlanModel.id == plan.id).first()
        assert refreshed.topology_profile_id is None

    def test_clear_succeeds(self, db):
        """Setting profile_id=null clears the override — the dedicated
        endpoint exists precisely to handle this case (the generic PATCH
        endpoint's value-is-not-None filter would block explicit-null
        clearing)."""
        plan = _make_ready_plan(db, topology_profile_id="caict_n78_2x2")
        resp = client.put(
            f"/api/v1/test-plans/{plan.id}/topology-profile",
            json={"profile_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["profile_id"] is None
        db.expire_all()
        refreshed = db.query(TestPlanModel).filter(TestPlanModel.id == plan.id).first()
        assert refreshed.topology_profile_id is None


# ============================================================
# Layer 3: apply_plan_topology_profile_if_set semantics
# ============================================================


class TestApplyPlanTopologyProfile:
    """Pin every reason value the GUI may need to render. All failure
    modes return a dict (never raise) — plan is already RUNNING by the
    time we attempt the apply, so we can't ergonomically abort it."""

    @pytest.mark.asyncio
    async def test_no_plan_override_returns_skip_reason(self, db):
        plan = _make_ready_plan(db)
        service = TestExecutionService()
        result = await service.apply_plan_topology_profile_if_set(db, plan)
        assert result == {"applied": False, "reason": "no_plan_override"}

    @pytest.mark.asyncio
    async def test_no_live_driver(self, db):
        plan = _make_ready_plan(db, topology_profile_id="caict_n78_2x2")
        service = TestExecutionService()
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=None,
        ):
            result = await service.apply_plan_topology_profile_if_set(db, plan)
        assert result == {"applied": False, "reason": "no_live_driver"}

    @pytest.mark.asyncio
    async def test_driver_lacks_apply_topology_profile(self, db):
        plan = _make_ready_plan(db, topology_profile_id="caict_n78_2x2")
        # Mock driver without apply_topology_profile attr; spec=[] keeps
        # MagicMock from auto-fabricating one.
        fake_driver = MagicMock(spec=[])

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        service = TestExecutionService()
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            result = await service.apply_plan_topology_profile_if_set(db, plan)
        assert result == {
            "applied": False,
            "reason": "driver_does_not_support_topology_profiles",
        }

    @pytest.mark.asyncio
    async def test_unknown_profile_id_returns_not_found(self, db):
        plan = _make_ready_plan(db, topology_profile_id="not_a_real_profile")
        fake_driver = MagicMock()
        fake_driver._cmds = Uxm5GNRTestAppProfile
        fake_driver.apply_topology_profile = AsyncMock()

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        service = TestExecutionService()
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            result = await service.apply_plan_topology_profile_if_set(db, plan)
        assert result["applied"] is False
        assert result["reason"] == "profile_not_found"
        assert result["profile_id"] == "not_a_real_profile"
        # Driver apply NOT called — bail before invoking driver
        fake_driver.apply_topology_profile.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_happy_path_passes_dataclass_to_driver(self, db):
        plan = _make_ready_plan(db, topology_profile_id="caict_n78_2x2")
        fake_driver = MagicMock()
        fake_driver._cmds = Uxm5GNRTestAppProfile
        fake_driver.apply_topology_profile = AsyncMock(
            return_value={"applied": True, "profile_id": "caict_n78_2x2",
                          "test_app": "5G_NR_Test"},
        )

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        service = TestExecutionService()
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            result = await service.apply_plan_topology_profile_if_set(db, plan)
        assert result["applied"] is True
        assert result["test_app"] == "5G_NR_Test"
        fake_driver.apply_topology_profile.assert_awaited_once()
        # Driver receives dataclass (Phase 2.1 contract)
        (profile_arg,) = fake_driver.apply_topology_profile.await_args.args
        assert profile_arg.profile_id == "caict_n78_2x2"

    @pytest.mark.asyncio
    async def test_apply_raised_is_caught(self, db):
        """Even a misbehaving driver doesn't fail the start — the plan
        is already RUNNING, the apply is best-effort follow-up."""
        plan = _make_ready_plan(db, topology_profile_id="caict_n78_2x2")
        fake_driver = MagicMock()
        fake_driver._cmds = Uxm5GNRTestAppProfile
        fake_driver.apply_topology_profile = AsyncMock(
            side_effect=RuntimeError("SCPI timeout"),
        )

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        service = TestExecutionService()
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            result = await service.apply_plan_topology_profile_if_set(db, plan)
        assert result["applied"] is False
        assert result["reason"] == "apply_raised"
        assert "RuntimeError" in result["error"]
        assert "SCPI timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_incompatible_test_app_surfaces_driver_reason(self, db):
        """When the dataclass passes lookup but the driver refuses
        because the running Test App doesn't match the profile's
        compat list, the driver's structured refusal flows through
        verbatim (caller sees the same shape as binding-level)."""
        plan = _make_ready_plan(db, topology_profile_id="caict_n78_2x2")
        fake_driver = MagicMock()
        fake_driver._cmds = Uxm5GNRTestAppProfile
        fake_driver.apply_topology_profile = AsyncMock(
            return_value={
                "applied": False,
                "reason": "incompatible_test_app",
                "profile_id": "caict_n78_2x2",
                "test_app": "LTE_NR_IRAT",
                "profile_compatible_with": ["5G_NR_Test"],
            },
        )

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        service = TestExecutionService()
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            result = await service.apply_plan_topology_profile_if_set(db, plan)
        assert result["applied"] is False
        assert result["reason"] == "incompatible_test_app"
        assert result["test_app"] == "LTE_NR_IRAT"
        assert result["profile_compatible_with"] == ["5G_NR_Test"]


# ============================================================
# Integration: POST /test-plans/{id}/start invokes the apply path
# ============================================================


class TestStartTestPlanInvokesTopologyApply:
    def test_start_with_topology_calls_apply(self, db):
        """End-to-end: a plan with topology_profile_id transitions to
        RUNNING AND the apply path is reached. We mock the driver to
        avoid needing live HAL and assert the await happened."""
        plan = _make_ready_plan(db, topology_profile_id="caict_n78_2x2")
        fake_driver = MagicMock()
        fake_driver._cmds = Uxm5GNRTestAppProfile
        fake_driver.apply_topology_profile = AsyncMock(
            return_value={"applied": True, "profile_id": "caict_n78_2x2",
                          "test_app": "5G_NR_Test"},
        )

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.post(
                f"/api/v1/test-plans/{plan.id}/start",
                json={"started_by": "tester"},
            )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["status"] == "running"
        assert body["topology_profile_id"] == "caict_n78_2x2"
        # Driver was actually called
        fake_driver.apply_topology_profile.assert_awaited_once()

    def test_start_without_topology_is_noop_for_driver(self, db):
        """No plan-level override → apply path returns
        no_plan_override; driver isn't touched even if one is bound."""
        plan = _make_ready_plan(db)  # no override
        fake_driver = MagicMock()
        fake_driver._cmds = Uxm5GNRTestAppProfile
        fake_driver.apply_topology_profile = AsyncMock()

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.post(
                f"/api/v1/test-plans/{plan.id}/start",
                json={"started_by": "tester"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        fake_driver.apply_topology_profile.assert_not_awaited()
