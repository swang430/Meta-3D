"""P2-1 Phase 1 — UXM two-layer architecture: Test App auto-detect
+ Topology profile operator workflow.

Pins three layers:

1. **`UxmTestProfile.compatible_test_apps`** dataclass field + the
   `is_compatible_with()` decision table. Empty list = any; non-empty
   list = case-insensitive exact match. None argument = "no Test App
   detected" treated as compatible (mock / pre-connect / offline mode).
2. **`RealUxmDriver.apply_topology_profile(id)`** decision: refuses
   incompatible profile with a structured dict (not raise) so the
   caller can surface `test_app` + `profile_compatible_with` to the
   operator instead of a generic "apply failed".
3. **HTTP endpoints**: `GET /instruments/{cat}/topology-profiles`
   shape including live-driver compat flag; `PUT /instruments/{cat}/topology-profile`
   refuse-or-persist flow with 409 on incompatible.

What is NOT covered:
- HAL-init auto-apply at the bootstrap path (would require full HAL
  service spin-up; that integration test would exercise hardware
  paths the unit tests are deliberately mocked away from).
- GUI rendering — covered by TypeScript compilation + manual smoke.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)
from app.hal.uxm_test_profiles import (
    UxmTestProfile,
    get_profile,
    list_profiles,
)
from app.main import app
from app.models.instrument import (
    InstrumentCategory as InstrumentCategoryModel,
    InstrumentConnection as InstrumentConnectionDB,
)


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


def _make_basestation_category(db) -> InstrumentCategoryModel:
    cat = InstrumentCategoryModel(
        id=uuid.uuid4(),
        category_key="baseStation",
        category_name="Base Station",
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _make_connection(
    db, cat: InstrumentCategoryModel, params: Dict[str, Any] | None = None,
) -> InstrumentConnectionDB:
    conn = InstrumentConnectionDB(
        id=uuid.uuid4(),
        category_id=cat.id,
        controller_ip="10.0.0.1",
        port="5025",
        protocol="SOCKET",
        connection_params=params or {},
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


# ============================================================
# Layer 1: UxmTestProfile.compatible_test_apps semantics
# ============================================================


class TestProfileCompatDeclaration:
    """Pin the compat decision table — these directly drive the
    operator-facing refuse path."""

    def test_empty_compat_list_means_any_test_app(self):
        profile = UxmTestProfile(profile_id="any", name="any")
        assert profile.compatible_test_apps == []
        assert profile.is_compatible_with("5G_NR_Test") is True
        assert profile.is_compatible_with("LTE_NR_IRAT") is True
        assert profile.is_compatible_with("future_app_we_havent_seen") is True
        assert profile.is_compatible_with(None) is True

    def test_specific_test_app_only_matches_that_app(self):
        profile = UxmTestProfile(
            profile_id="5g_only", name="5G only",
            compatible_test_apps=["5G_NR_Test"],
        )
        assert profile.is_compatible_with("5G_NR_Test") is True
        assert profile.is_compatible_with("LTE_NR_IRAT") is False

    def test_case_insensitive_match(self):
        """Profile declares `5G_NR_Test`; driver may report
        `5G_NR_test` or `5g_nr_test` depending on firmware version
        formatting. The compat check must be case-insensitive."""
        profile = UxmTestProfile(
            profile_id="5g", name="5G",
            compatible_test_apps=["5G_NR_Test"],
        )
        assert profile.is_compatible_with("5g_nr_test") is True
        assert profile.is_compatible_with("5G_NR_TEST") is True
        assert profile.is_compatible_with("5G_NR_Test") is True

    def test_none_test_app_treated_as_compatible(self):
        """`None` = "we don't know which Test App is running" (mock
        mode, offline, pre-connect). Don't refuse the operator's
        selection — apply will catch real incompat later if needed."""
        profile = UxmTestProfile(
            profile_id="5g_only", name="5G",
            compatible_test_apps=["5G_NR_Test"],
        )
        assert profile.is_compatible_with(None) is True

    def test_all_builtin_templates_declare_5g_compat(self):
        """All 7 built-in templates use `cell_id="CELL0"` which only
        works on 5G_NR_Test (IRAT's primary cell is CELL1). Pin that
        they all DECLARE this constraint explicitly — a future template
        for IRAT must declare its own compat (not silently inherit
        empty=any and break at SCPI time)."""
        templates = list_profiles()
        assert len(templates) == 7
        for entry in templates:
            full = get_profile(entry["profile_id"])
            assert full.compatible_test_apps == ["5G_NR_Test"], (
                f"profile {full.profile_id!r} doesn't declare "
                f"compatible_test_apps — got {full.compatible_test_apps}"
            )


# ============================================================
# Layer 2: RealUxmDriver.apply_topology_profile
# ============================================================


class TestApplyTopologyProfile:
    """Pin the apply decision: load profile → check compat against
    active Test App → either dispatch set_cell_config or return a
    structured refusal dict."""

    @pytest.mark.asyncio
    async def test_happy_path_5g_profile_on_5g_test_app(self):
        """5G topology + 5G Test App = applied. Returns
        applied=True with profile_id + test_app in the result so
        callers (HAL init / API endpoint) can audit-log the apply."""
        driver = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        # Default test app is 5G_NR_Test (per _resolve_initial_profile).
        assert driver._cmds.PROFILE_NAME == "5G_NR_Test"
        with patch.object(driver, "set_cell_config", new=AsyncMock(return_value=True)) as mock_apply:
            result = await driver.apply_topology_profile("caict_n78_2x2")
        assert result["applied"] is True
        assert result["profile_id"] == "caict_n78_2x2"
        assert result["test_app"] == "5G_NR_Test"
        # set_cell_config was actually invoked with the topology's config
        mock_apply.assert_awaited_once()
        config_arg = mock_apply.await_args.args[0]
        assert config_arg["band"] == "N78"
        assert config_arg["mimo_layers"] == 2

    @pytest.mark.asyncio
    async def test_refuses_5g_profile_on_irat_test_app(self):
        """5G topology + IRAT Test App = refused (5G profile declares
        compat with 5G_NR_Test only, IRAT's PROFILE_NAME is
        'LTE_NR_IRAT'). Refusal dict must carry the FOUR fields that
        the GUI needs to render the message: applied=False, reason,
        test_app, profile_compatible_with."""
        driver = RealUxmDriver(
            "test", {"ip": "10.0.0.1", "port": 5025, "uxm_profile": "irat"},
        )
        # IRAT profile is class-level; instantiated as type ref.
        assert driver._cmds.PROFILE_NAME == "LTE_NR_IRAT"
        # set_cell_config must NOT be called — refusal short-circuits.
        with patch.object(driver, "set_cell_config", new=AsyncMock()) as mock_apply:
            result = await driver.apply_topology_profile("caict_n78_2x2")
        mock_apply.assert_not_awaited()
        assert result["applied"] is False
        assert result["reason"] == "incompatible_test_app"
        assert result["profile_id"] == "caict_n78_2x2"
        assert result["test_app"] == "LTE_NR_IRAT"
        assert result["profile_compatible_with"] == ["5G_NR_Test"]

    @pytest.mark.asyncio
    async def test_unknown_profile_id_raises_keyerror(self):
        """Bogus profile_id propagates KeyError from get_profile —
        the API endpoint maps that to 404. Driver doesn't pretty-print
        the error; staying close to the registry contract."""
        driver = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        with pytest.raises(KeyError, match="not found"):
            await driver.apply_topology_profile("does_not_exist")


# ============================================================
# Layer 3: readiness_metadata + connect-time audit
# ============================================================


class TestReadinessMetadata:
    """Pin the UXM driver's P3-5 readiness_metadata override —
    exposes Test App layer state so the readiness panel can show
    which app + cell-index conventions the driver landed on."""

    def test_pre_connect_returns_unknown_test_app(self):
        driver = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        meta = driver.readiness_metadata()
        # detected_test_app is None until connect() runs SCPI probe.
        assert meta["detected_test_app"] is None
        # command_profile reflects the initial _resolve_initial_profile result.
        assert meta["command_profile"] == "5G_NR_Test"
        # Layer state exposed (primary_cell, hislip_index) so operator
        # can tell which cell-indexing conventions are in play.
        assert meta["primary_cell"] == "CELL0"
        assert meta["hislip_index"] == 0

    def test_irat_hint_changes_metadata(self):
        driver = RealUxmDriver(
            "test", {"ip": "10.0.0.1", "port": 5025, "uxm_profile": "irat"},
        )
        meta = driver.readiness_metadata()
        assert meta["command_profile"] == "LTE_NR_IRAT"
        assert meta["primary_cell"] == "CELL1"
        assert meta["hislip_index"] == 2

    def test_detected_test_app_reflects_live_probe(self):
        """When connect() has run + SYSTem:APPLication:NAME? returned
        a value, detected_test_app is the RAW string the instrument
        reported (not the profile name we mapped it to). Differentiating
        these lets the readiness panel show 'instrument reports X,
        driver mapped to profile Y' — useful for diagnosing
        detect_profile() registry gaps."""
        driver = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        # Simulate post-connect state.
        driver.detected_test_app = "LTE_NR_IRAT"
        meta = driver.readiness_metadata()
        assert meta["detected_test_app"] == "LTE_NR_IRAT"


# ============================================================
# Layer 4: HTTP endpoint GET /instruments/{cat}/topology-profiles
# ============================================================


class TestListTopologyProfilesEndpoint:
    def test_returns_404_when_category_not_found(self, db):
        resp = client.get("/api/v1/instruments/nonexistent/topology-profiles")
        assert resp.status_code == 404

    def test_returns_not_a_uxm_for_non_basestation(self, db):
        """Today only baseStation has topology profiles; other
        categories (channelEmulator, vna, etc.) return empty list
        with reason='not_a_uxm' so the GUI can hide the picker."""
        cat = InstrumentCategoryModel(
            id=uuid.uuid4(), category_key="vna", category_name="VNA",
        )
        db.add(cat)
        db.commit()
        resp = client.get("/api/v1/instruments/vna/topology-profiles")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["reason"] == "not_a_uxm"

    def test_returns_builtin_templates_for_basestation(self, db):
        cat = _make_basestation_category(db)
        resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 7
        ids = sorted(item["profile_id"] for item in body["items"])
        # Pin the canonical set so a future template drop is loud.
        assert "caict_n78_2x2" in ids
        assert "caict_n78_4x4" in ids
        # No live HAL in tests → current_test_app is null,
        # compatible_with_current_test_app is null per item.
        assert body["current_test_app"] is None
        for item in body["items"]:
            assert item["compatible_with_current_test_app"] is None

    def test_compat_flag_set_when_live_driver_present(self, db):
        """With a live UXM driver reporting detected_test_app='5G_NR_Test',
        each item's compat flag reflects the per-template
        compatible_test_apps list."""
        cat = _make_basestation_category(db)

        # Stub a live driver via the HAL service.
        fake_driver = MagicMock()
        fake_driver.detected_test_app = "5G_NR_Test"

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        body = resp.json()
        assert body["current_test_app"] == "5G_NR_Test"
        # All 7 templates declare compat with 5G_NR_Test → all True.
        for item in body["items"]:
            assert item["compatible_with_current_test_app"] is True

    def test_compat_flag_false_when_test_app_differs(self, db):
        cat = _make_basestation_category(db)
        fake_driver = MagicMock()
        fake_driver.detected_test_app = "LTE_NR_IRAT"

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        body = resp.json()
        # All built-ins declare 5G_NR_Test only — incompat with IRAT.
        for item in body["items"]:
            assert item["compatible_with_current_test_app"] is False

    def test_returns_persisted_selection(self, db):
        cat = _make_basestation_category(db)
        _make_connection(db, cat, params={"topology_profile_id": "caict_n78_2x2"})
        resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        body = resp.json()
        assert body["selected_topology_profile_id"] == "caict_n78_2x2"


# ============================================================
# Layer 5: HTTP endpoint PUT /instruments/{cat}/topology-profile
# ============================================================


class TestSelectTopologyProfileEndpoint:
    def test_persists_selection_when_no_live_driver(self, db):
        """No HAL driver bound → persist to connection_params,
        applied_now=False with apply_skipped_reason='no_live_driver'.
        Takes effect on next HAL reload."""
        cat = _make_basestation_category(db)
        _make_connection(db, cat)
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=None,
        ):
            resp = client.put(
                f"/api/v1/instruments/{cat.category_key}/topology-profile",
                json={"profile_id": "caict_n78_2x2"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["persisted"] is True
        assert body["profile_id"] == "caict_n78_2x2"
        assert body["applied_now"] is False
        assert body["apply_skipped_reason"] == "no_live_driver"
        # DB write verified
        db.expire_all()
        conn = db.query(InstrumentConnectionDB).filter_by(category_id=cat.id).first()
        assert conn.connection_params["topology_profile_id"] == "caict_n78_2x2"

    def test_clears_selection_when_profile_id_null(self, db):
        """Operator can null the selection — connection_params drops
        the key so next HAL reload won't auto-apply anything."""
        cat = _make_basestation_category(db)
        _make_connection(db, cat, params={"topology_profile_id": "caict_n78_2x2", "other": "keep"})
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=None,
        ):
            resp = client.put(
                f"/api/v1/instruments/{cat.category_key}/topology-profile",
                json={"profile_id": None},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["persisted"] is True
        assert body["profile_id"] is None
        assert body["apply_skipped_reason"] == "no_selection"
        db.expire_all()
        conn = db.query(InstrumentConnectionDB).filter_by(category_id=cat.id).first()
        # Key removed but other params preserved (not blown away).
        assert "topology_profile_id" not in conn.connection_params
        assert conn.connection_params["other"] == "keep"

    def test_unknown_profile_id_returns_404(self, db):
        cat = _make_basestation_category(db)
        _make_connection(db, cat)
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=None,
        ):
            resp = client.put(
                f"/api/v1/instruments/{cat.category_key}/topology-profile",
                json={"profile_id": "does_not_exist"},
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_409_when_incompatible_with_live_test_app(self, db):
        """Refuses arm: live driver reports IRAT, operator picks a 5G
        profile → 409 with the structured payload (refused: true,
        reason, profile_id, test_app, profile_compatible_with). DB
        must NOT be written — refuses bail before persist."""
        cat = _make_basestation_category(db)
        _make_connection(db, cat)

        fake_driver = MagicMock()
        fake_driver.detected_test_app = "LTE_NR_IRAT"
        # Make hasattr() return True for apply_topology_profile so the
        # endpoint's compat pre-flight path runs.
        fake_driver.apply_topology_profile = AsyncMock()

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.put(
                f"/api/v1/instruments/{cat.category_key}/topology-profile",
                json={"profile_id": "caict_n78_2x2"},
            )
        assert resp.status_code == 409
        body = resp.json()
        # Codex P2 lesson from PR #35 — verify top-level shape, no
        # detail-wrapper. This endpoint also returns JSONResponse to
        # avoid HTTPException's automatic detail wrap.
        assert body["refused"] is True
        assert body["reason"] == "incompatible_test_app"
        assert body["test_app"] == "LTE_NR_IRAT"
        assert body["profile_compatible_with"] == ["5G_NR_Test"]
        # apply_topology_profile must NOT be called (compat pre-flight
        # rejected before the driver-level apply).
        fake_driver.apply_topology_profile.assert_not_awaited()
        # DB stays untouched — refuses don't persist.
        db.expire_all()
        conn = db.query(InstrumentConnectionDB).filter_by(category_id=cat.id).first()
        assert "topology_profile_id" not in (conn.connection_params or {})

    def test_applies_immediately_when_live_driver_compatible(self, db):
        """Happy path: live driver compat, PUT persists AND calls
        apply on the driver. applied_now=True in response."""
        cat = _make_basestation_category(db)
        _make_connection(db, cat)

        fake_driver = MagicMock()
        fake_driver.detected_test_app = "5G_NR_Test"
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
            resp = client.put(
                f"/api/v1/instruments/{cat.category_key}/topology-profile",
                json={"profile_id": "caict_n78_2x2"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["persisted"] is True
        assert body["applied_now"] is True
        assert body["test_app"] == "5G_NR_Test"
        fake_driver.apply_topology_profile.assert_awaited_once_with("caict_n78_2x2")

    def test_404_when_no_connection_row(self, db):
        """Operator must configure endpoint first — without a
        connection row there's nowhere to persist the selection."""
        cat = _make_basestation_category(db)
        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=None,
        ):
            resp = client.put(
                f"/api/v1/instruments/{cat.category_key}/topology-profile",
                json={"profile_id": "caict_n78_2x2"},
            )
        assert resp.status_code == 404
        assert "configure endpoint first" in resp.json()["detail"]
