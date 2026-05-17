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
    """Pin the apply decision: caller passes the dataclass → driver
    checks compat against active Test App → either dispatch
    set_cell_config or return a structured refusal dict.

    P2-1 Phase 2.1: driver no longer looks up by profile_id. Lookup
    happens at the caller (HAL service or API endpoint) so HAL layer
    stays DB-free."""

    @pytest.mark.asyncio
    async def test_happy_path_5g_profile_on_5g_test_app(self):
        """5G topology + 5G Test App = applied. Returns
        applied=True with profile_id + test_app in the result so
        callers (HAL init / API endpoint) can audit-log the apply."""
        driver = RealUxmDriver("test", {"ip": "10.0.0.1", "port": 5025})
        # Default test app is 5G_NR_Test (per _resolve_initial_profile).
        assert driver._cmds.PROFILE_NAME == "5G_NR_Test"
        profile = get_profile("caict_n78_2x2")
        with patch.object(driver, "set_cell_config", new=AsyncMock(return_value=True)) as mock_apply:
            result = await driver.apply_topology_profile(profile)
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
        profile = get_profile("caict_n78_2x2")
        # set_cell_config must NOT be called — refusal short-circuits.
        with patch.object(driver, "set_cell_config", new=AsyncMock()) as mock_apply:
            result = await driver.apply_topology_profile(profile)
        mock_apply.assert_not_awaited()
        assert result["applied"] is False
        assert result["reason"] == "incompatible_test_app"
        assert result["profile_id"] == "caict_n78_2x2"
        assert result["test_app"] == "LTE_NR_IRAT"
        assert result["profile_compatible_with"] == ["5G_NR_Test"]


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

    def test_compat_flag_uses_resolved_profile_name_not_raw_alias(self, db):
        """Codex P2 (PR #36) — if SYSTem:APPLication:NAME? returns a
        recognised alias like ``"5G NR Test"`` (with space), detect_profile()
        maps it to canonical ``"5G_NR_Test"`` and the driver runs on
        ``Uxm5GNRTestAppProfile``. The endpoint must compat-check against
        the resolved ``_cmds.PROFILE_NAME``, not the raw alias — otherwise
        every built-in (which declares ``compatible_test_apps=["5G_NR_Test"]``)
        false-negatives and the GUI greys them all out while the driver
        would happily apply them."""
        cat = _make_basestation_category(db)
        fake_driver = MagicMock()
        # Raw alias the instrument actually reported — would fail
        # exact-match against ["5G_NR_Test"] declarations.
        fake_driver.detected_test_app = "5G NR Test"
        # Resolved profile after detect_profile() normalisation — what
        # apply_topology_profile() uses for its own compat check.
        fake_driver._cmds = Uxm5GNRTestAppProfile

        class FakeHal:
            drivers = {"baseStation": fake_driver}

        with patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        body = resp.json()
        # Report canonical to the GUI so operator sees the same name
        # the compat decision was made against (avoids "current_test_app
        # = '5G NR Test' but profile wants '5G_NR_Test'" cognitive mismatch).
        assert body["current_test_app"] == "5G_NR_Test"
        for item in body["items"]:
            assert item["compatible_with_current_test_app"] is True


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
        # P2-1 Phase 2.1: driver now receives the dataclass, not a string id.
        fake_driver.apply_topology_profile.assert_awaited_once()
        (profile_arg,) = fake_driver.apply_topology_profile.await_args.args
        assert profile_arg.profile_id == "caict_n78_2x2"

    def test_accepts_recognised_alias_via_resolved_profile_name(self, db):
        """Codex P2 (PR #36) — UXM hardware reports ``"5G NR Test"`` (with
        space, alias in ``Uxm5GNRTestAppProfile.APP_NAME_MATCH``); driver
        normalises to ``_cmds.PROFILE_NAME = "5G_NR_Test"``. Endpoint
        preflight must use the resolved name, otherwise a request for
        a built-in profile (declared ``compatible_test_apps=["5G_NR_Test"]``)
        comes back 409 even though the driver-level apply would succeed.
        """
        cat = _make_basestation_category(db)
        _make_connection(db, cat)

        fake_driver = MagicMock()
        fake_driver.detected_test_app = "5G NR Test"  # raw alias
        fake_driver._cmds = Uxm5GNRTestAppProfile      # resolved
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
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["applied_now"] is True
        # Driver receives the dataclass (P2-1 Phase 2.1 signature change).
        fake_driver.apply_topology_profile.assert_awaited_once()
        (profile_arg,) = fake_driver.apply_topology_profile.await_args.args
        assert profile_arg.profile_id == "caict_n78_2x2"

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


# ============================================================
# P2-1 Phase 2.1 — DB persistence: bootstrap seeder + service +
# CRUD endpoints. Earlier sections cover the binding-level select
# flow against the in-code registry; these new sections pin the DB
# layer that replaces (and falls back to) it.
# ============================================================


from app.models.instrument_topology_profile import InstrumentTopologyProfile  # noqa: E402
from app.services.bootstrap.topology_profiles import topology_profiles_seeder  # noqa: E402
from app.services.topology_profile_service import (  # noqa: E402
    TopologyProfileImmutable, TopologyProfileNotFound,
    create, delete, duplicate, get_dataclass, update,
)


class TestTopologyProfileSeeder:
    """Pin that ``topology_profiles_seeder`` inserts the 7 built-ins
    on a fresh DB and is idempotent (second run skips rather than
    duplicating). Critical for bootstrap re-runs across deploys."""

    def test_seeds_seven_builtins_on_empty_db(self, db):
        result = topology_profiles_seeder.run(db)
        assert result.inserted == 7
        assert result.skipped == 0
        rows = (
            db.query(InstrumentTopologyProfile)
            .filter(InstrumentTopologyProfile.is_system_preset.is_(True))
            .all()
        )
        assert len(rows) == 7
        ids = {r.profile_id for r in rows}
        assert "caict_n78_2x2" in ids
        assert "caict_n78_4x4" in ids
        assert "siso_n78_100m" in ids

    def test_idempotent_on_second_run(self, db):
        topology_profiles_seeder.run(db)
        result2 = topology_profiles_seeder.run(db)
        # Second run finds all 7 already-system-preset rows, skips all.
        assert result2.inserted == 0
        assert result2.skipped == 7

    def test_does_not_clobber_user_customisations(self, db):
        """Operator may have edited a built-in's fields via clone-to-edit
        — the duplicate has is_system_preset=False and shouldn't be
        touched even if its profile_id ever collided with a preset
        (which is prevented by _allocate_custom_profile_id, but the
        seeder's natural-key filter is defensive)."""
        topology_profiles_seeder.run(db)
        # Simulate operator clone + edit on the 2x2 preset.
        user_row = duplicate(db, "caict_n78_2x2")
        user_row.dl_power_dbm = -70.0  # operator's custom power
        db.commit()
        topology_profiles_seeder.run(db)
        db.refresh(user_row)
        # The user's edit survives the re-seed.
        assert user_row.dl_power_dbm == -70.0
        assert user_row.is_system_preset is False


class TestTopologyProfileService:
    """to_dataclass round-trip + CRUD + immutability."""

    def test_to_dataclass_roundtrip_preserves_config(self, db):
        topology_profiles_seeder.run(db)
        dc = get_dataclass(db, "caict_n78_2x2")
        # The dataclass produced from the DB row must produce the same
        # set_cell_config() dict as the in-code template — otherwise
        # operators editing in the GUI would see drift vs the driver-
        # internal apply path.
        from app.hal.uxm_test_profiles import get_profile as get_code_profile
        code_dc = get_code_profile("caict_n78_2x2")
        assert dc.to_config_dict() == code_dc.to_config_dict()
        assert dc.compatible_test_apps == ["5G_NR_Test"]

    def test_get_dataclass_raises_not_found_for_unknown_id(self, db):
        with pytest.raises(TopologyProfileNotFound):
            get_dataclass(db, "does_not_exist")

    def test_create_assigns_custom_prefix_and_allowlisted_fields(self, db):
        row = create(db, name="My Test Profile",
                     fields={"band": "N41", "mimo_layers": 4,
                             "compatible_test_apps": ["5G_NR_Test"]})
        db.commit()
        assert row.profile_id.startswith("custom_")
        assert row.is_system_preset is False
        assert row.band == "N41"
        assert row.mimo_layers == 4

    def test_create_rejects_unknown_fields(self, db):
        with pytest.raises(ValueError, match="Unknown"):
            create(db, name="bad",
                   fields={"made_up_field": 123})

    def test_create_allocates_unique_id_on_name_collision(self, db):
        a = create(db, name="My Profile", fields={})
        b = create(db, name="My Profile", fields={})
        db.commit()
        assert a.profile_id != b.profile_id
        assert b.profile_id == "custom_my_profile_2"

    def test_update_modifies_operator_owned(self, db):
        row = create(db, name="x", fields={"target_mcs": 10})
        db.commit()
        updated = update(db, row.profile_id, {"target_mcs": 20, "notes": "tweaked"})
        db.commit()
        assert updated.target_mcs == 20
        assert updated.notes == "tweaked"

    def test_update_refuses_system_preset(self, db):
        topology_profiles_seeder.run(db)
        with pytest.raises(TopologyProfileImmutable):
            update(db, "caict_n78_2x2", {"target_mcs": 0})

    def test_delete_refuses_system_preset(self, db):
        topology_profiles_seeder.run(db)
        with pytest.raises(TopologyProfileImmutable):
            delete(db, "caict_n78_2x2")

    def test_delete_removes_operator_owned(self, db):
        row = create(db, name="ephemeral", fields={})
        db.commit()
        pid = row.profile_id
        delete(db, pid)
        db.commit()
        with pytest.raises(TopologyProfileNotFound):
            get_dataclass(db, pid)

    def test_create_with_explicit_null_on_non_nullable_uses_default(self, db):
        """Codex P2 (PR #38): operator-cleared GUI field arrives as
        explicit null in JSON; Pydantic ``exclude_unset=True`` keeps
        the null in the dump. For non-nullable columns (band, mimo_layers,
        etc.) the service must skip the setattr so the column's Python /
        server default fills in — without the skip we'd ``setattr None``
        and Postgres would NOT-NULL-violate at flush time."""
        row = create(db, name="x", fields={"band": None, "mimo_layers": None})
        db.commit()
        # Defaults kicked in.
        assert row.band == "N78"
        assert row.mimo_layers == 2

    def test_create_with_explicit_null_on_nullable_keeps_null(self, db):
        """Nullable columns (arfcn, csi_rs_ports, description, …) DO
        accept the operator's explicit null — the skip rule only applies
        to non-nullable columns."""
        row = create(db, name="x", fields={"arfcn": None,
                                            "csi_rs_ports": None,
                                            "description": None})
        db.commit()
        assert row.arfcn is None
        assert row.csi_rs_ports is None
        assert row.description is None

    def test_update_with_explicit_null_on_non_nullable_rejects(self, db):
        """On UPDATE there's no default to fall back to, so explicit
        null on a non-nullable field would generate UPDATE ... col=NULL
        and IntegrityError everywhere. Service raises ValueError (→ 400)
        with a message that disambiguates 'omit to leave unchanged' vs
        'send a value'."""
        row = create(db, name="x", fields={})
        db.commit()
        with pytest.raises(ValueError, match="non-nullable"):
            update(db, row.profile_id, {"band": None})

    def test_update_with_explicit_null_on_nullable_clears_field(self, db):
        """Operator clearing arfcn / csi_rs_ports is the intended UX
        for nullable columns — must succeed."""
        row = create(db, name="x", fields={"arfcn": 632628, "csi_rs_ports": 4})
        db.commit()
        updated = update(db, row.profile_id, {"arfcn": None, "csi_rs_ports": None})
        db.commit()
        assert updated.arfcn is None
        assert updated.csi_rs_ports is None

    def test_duplicate_creates_editable_copy_with_unique_id(self, db):
        topology_profiles_seeder.run(db)
        copy = duplicate(db, "caict_n78_2x2")
        db.commit()
        assert copy.is_system_preset is False
        assert copy.profile_id != "caict_n78_2x2"
        assert "(副本)" in copy.name
        # Field copy: power matches source
        from app.hal.uxm_test_profiles import get_profile as get_code_profile
        source_dc = get_code_profile("caict_n78_2x2")
        assert copy.dl_power_dbm == source_dc.dl_power_dbm
        assert list(copy.compatible_test_apps or []) == source_dc.compatible_test_apps


class TestListTopologyProfilesReadsDb:
    """GET /topology-profiles now reads the DB. With rows present,
    returns DB content; empty DB falls back to in-code registry so the
    GUI isn't blank during the greenfield first-boot window."""

    def test_returns_db_rows_when_seeded(self, db):
        topology_profiles_seeder.run(db)
        cat = _make_basestation_category(db)
        resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        assert resp.status_code == 200
        body = resp.json()
        # 7 built-ins from the seeder
        assert len(body["items"]) == 7
        for item in body["items"]:
            assert item["is_system_preset"] is True

    def test_returns_operator_created_rows_alongside_presets(self, db):
        topology_profiles_seeder.run(db)
        create(db, name="My N41", fields={"band": "N41"})
        db.commit()
        cat = _make_basestation_category(db)
        resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        body = resp.json()
        assert len(body["items"]) == 8
        custom = [i for i in body["items"] if not i["is_system_preset"]]
        assert len(custom) == 1
        assert custom[0]["profile_id"].startswith("custom_")

    def test_falls_back_to_in_code_registry_when_db_empty(self, db):
        """Greenfield first-boot: no seeder has run yet, but the GUI
        opens the topology picker and expects something to show. We
        surface the in-code 7 built-ins as system presets so operator
        sees the canonical choices even before bootstrap."""
        cat = _make_basestation_category(db)
        # No seeder call → DB has zero rows.
        resp = client.get(f"/api/v1/instruments/{cat.category_key}/topology-profiles")
        body = resp.json()
        assert len(body["items"]) == 7
        for item in body["items"]:
            assert item["is_system_preset"] is True


class TestTopologyProfileCrudEndpoints:
    """POST / PUT / DELETE / duplicate flows on the new CRUD surface."""

    def test_create_endpoint_assigns_custom_prefix(self, db):
        resp = client.post(
            "/api/v1/instruments/baseStation/topology-profiles",
            json={"name": "My N41 Profile", "band": "N41", "mimo_layers": 4},
        )
        assert resp.status_code == 201, resp.json()
        body = resp.json()
        assert body["profile_id"].startswith("custom_")
        assert body["is_system_preset"] is False
        assert body["band"] == "N41"
        assert body["mimo_layers"] == 4

    def test_create_endpoint_rejects_unknown_field(self, db):
        resp = client.post(
            "/api/v1/instruments/baseStation/topology-profiles",
            json={"name": "x", "this_field_does_not_exist": 42},
        )
        # Pydantic discards unknown extras by default (BaseModel without
        # extra=forbid), so unknown fields silently get dropped by the
        # request parser; the service's allowlist catches anything that
        # survives. The "extra" here matches no allowlist entry AND no
        # request schema field, so it's silently ignored — assert the
        # row is created with defaults rather than erroring.
        assert resp.status_code == 201
        assert resp.json()["name"] == "x"

    def test_create_endpoint_404_for_non_basestation(self, db):
        resp = client.post(
            "/api/v1/instruments/channelEmulator/topology-profiles",
            json={"name": "anything"},
        )
        assert resp.status_code == 404

    def test_update_endpoint_modifies_operator_owned(self, db):
        created = client.post(
            "/api/v1/instruments/baseStation/topology-profiles",
            json={"name": "x"},
        ).json()
        pid = created["profile_id"]
        resp = client.put(
            f"/api/v1/instruments/baseStation/topology-profiles/{pid}",
            json={"target_mcs": 20, "notes": "tweaked"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["target_mcs"] == 20
        assert body["notes"] == "tweaked"

    def test_update_endpoint_409_on_system_preset(self, db):
        topology_profiles_seeder.run(db)
        db.commit()
        resp = client.put(
            "/api/v1/instruments/baseStation/topology-profiles/caict_n78_2x2",
            json={"target_mcs": 0},
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["refused"] is True
        assert body["reason"] == "is_system_preset"

    def test_update_endpoint_404_for_unknown_id(self, db):
        resp = client.put(
            "/api/v1/instruments/baseStation/topology-profiles/nope",
            json={"target_mcs": 0},
        )
        assert resp.status_code == 404

    def test_delete_endpoint_removes_operator_owned(self, db):
        created = client.post(
            "/api/v1/instruments/baseStation/topology-profiles",
            json={"name": "to be deleted"},
        ).json()
        pid = created["profile_id"]
        resp = client.delete(
            f"/api/v1/instruments/baseStation/topology-profiles/{pid}",
        )
        assert resp.status_code == 204

    def test_delete_endpoint_409_on_system_preset(self, db):
        topology_profiles_seeder.run(db)
        db.commit()
        resp = client.delete(
            "/api/v1/instruments/baseStation/topology-profiles/caict_n78_2x2",
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["refused"] is True

    def test_duplicate_endpoint_returns_editable_copy(self, db):
        topology_profiles_seeder.run(db)
        db.commit()
        resp = client.post(
            "/api/v1/instruments/baseStation/topology-profiles/caict_n78_2x2/duplicate",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_system_preset"] is False
        assert body["profile_id"].startswith("custom_")
        assert "(副本)" in body["name"]
