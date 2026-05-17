"""P3-8 — VRT companion TestCase filter.

Pins the contract that auto-generated VRT companion TestCases
(``configuration == {auto_generated, scenario_id, steps_count}``,
created by ``TestPlanService._create_road_test_steps`` so
``TestExecution.test_case_id`` NOT NULL FK has a target on
legacy scenario-based TestPlans) are NOT enumerated as VRT
scenarios by ``vrt_service.list_vrt_test_cases`` and are NOT
convertible by ``vrt_service.vrt_test_case_to_scenario``.

Before this fix, ``GET /road-test/scenarios`` iterated every
VRT TestCase including companions and crashed with 8 missing-
field Pydantic ``ValidationError`` on the companion's placeholder
configuration, returning 500 to all 28
test_road_test_{scenarios,executions,websocket} integration
tests.

Test isolation: in-memory SQLite (same pattern as
``test_plan_topology_override.py`` and ``test_uxm_topology_profile.py``).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.scenario_library import get_all_scenarios
from app.db.database import Base
from app.models.test_plan import TestCase, TestCaseType
from app.services.road_test.vrt_service import (
    VRTService,
    is_companion_test_case,
    vrt_service,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
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


def _make_companion(db, *, scenario_id: str = "abc-123", steps: int = 8) -> TestCase:
    """Mirror the shape produced by TestPlanService._create_road_test_steps."""
    tc = TestCase(
        name=f"VRT: Test Plan from Scenario",
        description=f"自动生成的虚拟路测用例 — 关联场景 {scenario_id}",
        test_type=TestCaseType.VIRTUAL_ROAD_TEST.value,
        configuration={
            "auto_generated": True,
            "scenario_id": scenario_id,
            "steps_count": steps,
        },
        is_template=False,
        tags=["VRT", "自动生成"],
        created_by="system",
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return tc


def _make_real_vrt(db, name: str = "Test Scenario") -> TestCase:
    """A full-shape VRT TestCase carrying all required
    VirtualRoadTestConfig fields. Built by projecting a known-valid
    standard scenario (from scenario_library) through
    ``scenario_to_vrt_config`` to avoid duplicating the schema shape.
    """
    standard = get_all_scenarios()[0]
    config = VRTService.scenario_to_vrt_config(standard)
    tc = TestCase(
        name=name,
        description="real scenario",
        test_type=TestCaseType.VIRTUAL_ROAD_TEST.value,
        configuration=config.model_dump(mode="json"),
        is_template=False,
        tags=["VRT"],
        created_by="tester",
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return tc


# ──────────────────────────────────────────────────────────────────────────
# is_companion_test_case helper
# ──────────────────────────────────────────────────────────────────────────


class TestIsCompanionTestCase:
    def test_detects_auto_generated_placeholder(self, db):
        tc = _make_companion(db)
        assert is_companion_test_case(tc) is True

    def test_real_vrt_is_not_companion(self, db):
        tc = _make_real_vrt(db)
        assert is_companion_test_case(tc) is False

    def test_empty_configuration_is_not_companion(self, db):
        """A row with empty config shouldn't be misclassified — it's a
        broken row, but not the placeholder we filter. (Detection is
        narrow on purpose: only the marker key counts.)
        """
        tc = TestCase(
            name="empty",
            test_type=TestCaseType.VIRTUAL_ROAD_TEST.value,
            configuration={},
            created_by="x",
        )
        db.add(tc); db.commit(); db.refresh(tc)
        assert is_companion_test_case(tc) is False

    def test_auto_generated_false_is_not_companion(self, db):
        """Defensive: only ``auto_generated is True`` triggers the
        filter — falsy or missing key doesn't.
        """
        tc = TestCase(
            name="manually marked",
            test_type=TestCaseType.VIRTUAL_ROAD_TEST.value,
            configuration={"auto_generated": False, "scenario_id": "x"},
            created_by="x",
        )
        db.add(tc); db.commit(); db.refresh(tc)
        assert is_companion_test_case(tc) is False


# ──────────────────────────────────────────────────────────────────────────
# list_vrt_test_cases — default excludes companions
# ──────────────────────────────────────────────────────────────────────────


class TestListVrtTestCasesCompanionFilter:
    def test_default_excludes_companions(self, db):
        real = _make_real_vrt(db, name="real-1")
        companion = _make_companion(db)
        rows = vrt_service.list_vrt_test_cases(db)
        ids = {tc.id for tc in rows}
        assert real.id in ids
        assert companion.id not in ids

    def test_include_companions_true_returns_both(self, db):
        real = _make_real_vrt(db, name="real-1")
        companion = _make_companion(db)
        rows = vrt_service.list_vrt_test_cases(db, include_companions=True)
        ids = {tc.id for tc in rows}
        assert real.id in ids
        assert companion.id in ids

    def test_pagination_applied_after_companion_filter(self, db):
        """``limit`` reflects the real scenario count, not the raw row
        count. Critical: SQL LIMIT followed by Python filter would
        silently shrink the page (e.g. limit=3 returning 2 real
        scenarios because one of the three was a filtered companion).
        """
        _make_companion(db, scenario_id="s1")
        _make_companion(db, scenario_id="s2")
        _make_real_vrt(db, name="r1")
        _make_real_vrt(db, name="r2")
        _make_real_vrt(db, name="r3")
        rows = vrt_service.list_vrt_test_cases(db, limit=3)
        assert len(rows) == 3
        assert all(not is_companion_test_case(r) for r in rows)


# ──────────────────────────────────────────────────────────────────────────
# vrt_test_case_to_scenario — refuses companions explicitly
# ──────────────────────────────────────────────────────────────────────────


class TestVrtTestCaseToScenarioCompanionRefuse:
    def test_companion_raises_value_error_not_validation_error(self, db):
        """Pre-fix this raised Pydantic ValidationError (8 missing fields,
        opaque). Post-fix it raises a clean ValueError naming the
        cause + the alternative API (``include_companions=False``)."""
        companion = _make_companion(db)
        with pytest.raises(ValueError, match="companion"):
            VRTService.vrt_test_case_to_scenario(companion)

    def test_real_vrt_converts_successfully(self, db):
        real = _make_real_vrt(db, name="convert-me")
        scenario = VRTService.vrt_test_case_to_scenario(real)
        assert scenario.name == "convert-me"
        assert scenario.category.value == "standard"
