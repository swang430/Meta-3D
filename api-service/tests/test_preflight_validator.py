"""P1-1 — plan-level pre-flight validator + endpoint contract.

Pins both layers:

- ``app/services/preflight.validate_plan``: pure function over a TestPlan,
  LabProfile, db session, and a HAL drivers dict. Returns a typed
  PreflightResult.
- ``POST /api/v1/test-plans/{id}/preflight``: thin wrapper around the
  function — pins the operator-facing surface (response shape, error
  codes, the deliberate no-auto-resolve-lab decision).

Lab-scoping evolves over two Codex P1s on PR #22:
- 1st fix (commit 4daf3d0): only drivers whose CATEGORY the lab binds
  count toward "lab can satisfy this need".
- 2nd fix (this iteration): only drivers whose ENDPOINT also matches
  the binding count. Mismatches surface in `mismatched_drivers`
  separate from `not_loaded_categories` (different remediation hint).
Tests below cover both layers and the bound-but-not-loaded surface.

What it does NOT cover:
- Seeded sequence templates propagating ``needs`` into materialised
  TestSteps — that wiring is deferred to a follow-up PR. Tests here
  synthesise TestStep rows directly to exercise the contract end-to-end.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Sequence, Set, Tuple, Union
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
# Importing InstrumentCategory registers the instrument_categories
# table on Base so create_all builds it — the validator joins
# `lab.instrument_bindings[*].category_id` against this table to
# resolve UUID → category_key. Use `from … import` (not
# `import app.models.instrument`) to avoid shadowing the FastAPI
# `app` instance imported just above.
from app.models.instrument import InstrumentCategory
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


# Test-only endpoint used by both ``_mock_driver`` and ``_make_lab``
# default-path bindings. Keeping them identical means the realistic
# (strict) scoping path passes; tests that want to exercise endpoint
# mismatch override one side via explicit args.
DEFAULT_TEST_ENDPOINT = "10.0.0.1:5025"


def _mock_driver(
    capabilities: Set[str],
    *,
    endpoint: str = DEFAULT_TEST_ENDPOINT,
    ip: str = "",
    port: str = "",
) -> Any:
    """Stand-in for a real driver instance. The validator reads
    ``.capabilities`` (P2-2) and ``.config``'s endpoint aliases
    (Codex P1 + P2 follow-ups on #22).

    ``endpoint`` populates ``config["endpoint"]`` — for VISA-managed
    drivers this is the raw resource string
    (``TCPIP0::host::port::INSTR``).
    ``ip`` + ``port`` populate the parsed alias fields the HAL
    factory sets when ``InstrumentConnection`` had them. Setting both
    sides exercises the multi-candidate match path."""
    d = MagicMock()
    d.capabilities = set(capabilities)
    cfg: Dict[str, Any] = {"endpoint": endpoint}
    if ip:
        cfg["ip"] = ip
    if port:
        cfg["port"] = port
    d.config = cfg
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


def _ensure_category(db, key: str) -> InstrumentCategory:
    """Get-or-create an ``InstrumentCategory`` row for ``key``. The
    validator joins ``lab.instrument_bindings[*].category_id`` against
    this table to resolve UUID → category_key, so the row has to exist
    or the binding is silently dropped from scope."""
    cat = (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.category_key == key)
        .first()
    )
    if cat is not None:
        return cat
    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key=key,
        category_name=key,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _make_lab(
    db,
    *,
    binds: Sequence[Union[str, Tuple[str, str]]] = (),
) -> LabProfile:
    """Build a LabProfile bound to the given list of categories.

    Each ``binds`` entry is either:
    - a category-key string → endpoint defaults to ``DEFAULT_TEST_ENDPOINT``
      (matches ``_mock_driver``'s default — exercises the strict path)
    - a ``(category_key, endpoint)`` tuple → explicit endpoint, for
      mismatch tests where binding ≠ driver endpoint, or weak-binding
      tests where ``endpoint == ""``

    ``binds=[]`` (the default) produces a lab with no bindings — useful
    for "lab is unconfigured" tests.
    """
    bindings: List[Dict[str, Any]] = []
    for entry in binds:
        if isinstance(entry, tuple):
            key, endpoint = entry
        else:
            key, endpoint = entry, DEFAULT_TEST_ENDPOINT
        cat = _ensure_category(db, key)
        bindings.append({
            "category_id": str(cat.id),
            "connection_endpoint": endpoint,
            "driver_mode": "auto",
            "role": f"primary_{key}",
        })
    lab = LabProfile(
        id=uuid.uuid4(),
        name=f"Preflight-Lab-{uuid.uuid4().hex[:6]}",
        is_active=True,
        instrument_bindings=bindings,
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
        assert result.not_loaded_categories == []
        assert result.mismatched_drivers == []

    def test_step_with_empty_needs_is_permissive(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db)
        _add_step(db, plan, order=1, name="quiet step", needs=[])
        result = validate_plan(plan, lab, db, hal_drivers={})
        assert result.ready is True
        assert result.gaps == []

    def test_satisfied_need_no_gap(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator"])
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        # Lab default endpoint and driver default endpoint align —
        # this exercises the strict (endpoint-matched) scoping path.
        hal = {"channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR})}
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True
        assert result.gaps == []
        assert result.lab_capabilities == [CE_INTERFERENCE_GENERATOR]
        assert result.not_loaded_categories == []
        assert result.mismatched_drivers == []

    def test_unsatisfied_need_creates_gap(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator"])
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
        # Reason names both the missing token and the loaded
        # categories so the GUI has something actionable to show.
        assert CE_INTERFERENCE_GENERATOR in gap.reason
        assert "channelEmulator" in gap.reason

    def test_no_drivers_loaded_at_all(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator"])
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        # Lab binds CE but HAL has nothing → not_loaded surfaces, gap fires.
        result = validate_plan(plan, lab, db, hal_drivers={})
        assert result.ready is False
        assert len(result.gaps) == 1
        assert "channelEmulator" in result.not_loaded_categories
        # Reason explicitly tells the operator to reload HAL.
        assert "not loaded" in result.gaps[0].reason.lower()

    def test_unknown_token_warns_does_not_gap(self, db):
        """A typo in needs (or a token registered before the consumer
        landed) must not block the plan. Surfaces in unknown_tokens
        so the dev can fix the typo without losing the green light."""
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator"])
        _add_step(db, plan, order=1, name="typo step",
                  needs=["ce.not_a_real_token", CE_INTERFERENCE_GENERATOR])
        hal = {"channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR})}
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True, result.gaps  # gap list empty
        assert "ce.not_a_real_token" in result.unknown_tokens

    def test_multiple_steps_multiple_gaps_in_execution_order(self, db):
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator", "positioner"])
        _add_step(db, plan, order=1, name="positioner sweep",
                  needs=[POS_SINGLE_AXIS_AZ])
        _add_step(db, plan, order=2, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        _add_step(db, plan, order=3, name="user-align step",
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
        lab = _make_lab(db, binds=["channelEmulator", "positioner"])
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
# Lab-scoped semantics — Codex P1 on PR #22, fixed in PR #23
# ---------------------------------------------------------------------------

class TestLabScopedSemantics:
    """The validator must answer "can THIS lab run this plan?" — not
    "can the global HAL state run this plan?". These tests pin the
    Codex-flagged regression where capabilities from drivers HAL had
    loaded for OTHER labs leaked into the answer."""

    def test_unbound_loaded_driver_does_not_satisfy_need(self, db):
        """HAL has a channelEmulator with the right capability loaded,
        but THIS lab doesn't bind channelEmulator → must gap. Pre-fix
        this returned ready=true because the global union included
        the unbound driver."""
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["positioner"])  # CE not bound
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        # HAL has the CE driver loaded (e.g. from a different lab's
        # config), with the capability present.
        hal = {
            "channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR}),
            "positioner": _mock_driver(set()),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is False, (
            "channelEmulator is loaded globally but not bound to this "
            "lab — its capabilities must not satisfy this lab's needs"
        )
        assert result.gaps[0].missing_token == CE_INTERFERENCE_GENERATOR
        # lab_capabilities reflects only the in-scope driver (positioner,
        # which exposes nothing) — NOT the global CE driver's tokens.
        assert CE_INTERFERENCE_GENERATOR not in result.lab_capabilities

    def test_bound_but_not_loaded_surfaces_distinct_field(self, db):
        """Lab binds CE but HAL never loaded a CE driver → the
        not_loaded_categories field tells the GUI to direct the
        operator to "reload HAL", not "buy a license"."""
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator", "positioner"])
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        # Only positioner came up — CE binding orphaned at runtime.
        hal = {"positioner": _mock_driver(set())}
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is False
        assert result.not_loaded_categories == ["channelEmulator"]
        # The gap reason must surface the not-loaded hint explicitly
        # so the GUI doesn't need to re-derive it.
        assert "channelEmulator" in result.gaps[0].reason
        assert "not loaded" in result.gaps[0].reason.lower()

    def test_mismatched_endpoint_surfaces_distinct_field(self, db):
        """Lab binds CE at endpoint A. HAL has a CE driver loaded but
        at endpoint B (e.g., HAL was started from a different lab's
        config). Pre-2nd-fix this satisfied the need because category
        matched. Post-fix: driver doesn't contribute capabilities AND
        surfaces in mismatched_drivers with both endpoints, so the
        operator can decide between "reload HAL with this lab's
        config" vs "fix the lab binding endpoint".
        Codex P1 (2nd iteration) on PR #22."""
        plan = _make_plan(db)
        # Lab binds CE explicitly at endpoint A.
        lab = _make_lab(
            db, binds=[("channelEmulator", "192.168.10.100:5025")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        # HAL has CE driver up — has the right capability — but its
        # endpoint is for a DIFFERENT physical unit.
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="192.168.20.200:5025",
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is False, (
            "loaded driver is for a different unit — must NOT count "
            "toward satisfying this lab's needs"
        )
        # Mismatch is visible as its own field with both endpoints.
        assert len(result.mismatched_drivers) == 1
        m = result.mismatched_drivers[0]
        assert m.category == "channelEmulator"
        assert m.expected_endpoint == "192.168.10.100:5025"
        assert m.loaded_endpoint == "192.168.20.200:5025"
        # not_loaded should be empty — driver IS loaded, just for
        # the wrong unit. Different remediation hint from not-loaded.
        assert result.not_loaded_categories == []
        # lab_capabilities should NOT include the mismatched driver's
        # token — that's the whole point of the strict scoping.
        assert CE_INTERFERENCE_GENERATOR not in result.lab_capabilities
        # Gap reason should mention the mismatch path so the GUI's
        # text rendering doesn't need to re-derive remediation.
        reason_lower = result.gaps[0].reason.lower()
        assert "different unit" in reason_lower or "bound to a different" in reason_lower

    def test_endpoint_match_is_whitespace_and_case_insensitive(self, db):
        """Trivially-different endpoint strings must still match —
        otherwise the operator paranoia (typing IP with trailing
        space, mixed case for hostnames) breaks scoping false-negative."""
        plan = _make_plan(db)
        lab = _make_lab(
            db, binds=[("channelEmulator", "  192.168.0.10:5025  ")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="192.168.0.10:5025",
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True, (
            f"endpoints differ only by whitespace — should match. "
            f"mismatches={result.mismatched_drivers}"
        )
        assert result.mismatched_drivers == []

    def test_weak_binding_no_endpoint_falls_back_to_category_match(self, db):
        """Older lab profile rows (saved before the wizard collected
        endpoints) have ``connection_endpoint=""``. The validator
        cannot strict-match without an expected value, so it falls
        back to category-only match. Preserves backwards-compat for
        existing data; operators can tighten by re-saving via the
        wizard. The fallback is intentionally silent today — if it
        becomes a real source of false-positives we'll add a warning
        field."""
        plan = _make_plan(db)
        # Explicit empty endpoint = weak binding.
        lab = _make_lab(db, binds=[("channelEmulator", "")])
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="anywhere:1234",  # ignored — weak binding
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True
        assert result.mismatched_drivers == []
        assert CE_INTERFERENCE_GENERATOR in result.lab_capabilities

    def test_lab_with_no_bindings_treats_everything_as_out_of_scope(self, db):
        """An unconfigured lab (no instrument_bindings) cannot satisfy
        any needs, even if HAL has every driver loaded globally."""
        plan = _make_plan(db)
        lab = _make_lab(db, binds=[])
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {"channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR})}
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is False
        # No bindings → nothing is "not loaded" either; both lists
        # are empty and every need gaps.
        assert result.not_loaded_categories == []
        assert result.lab_capabilities == []
        # Reason explicitly names the "no bindings" case so the GUI
        # can route the operator to the lab profile editor.
        assert "no instrument_bindings" in result.gaps[0].reason

    # -----------------------------------------------------------------
    # VISA endpoint aliasing — Codex P2 on PR #24
    # -----------------------------------------------------------------
    # InstrumentHALService builds driver.config from
    # InstrumentConnection rows, which often have BOTH an `endpoint`
    # (raw VISA resource string from pyvisa) AND parsed `ip`/`port`
    # fields. Lab bindings are saved by the wizard as plain ip:port.
    # The validator must treat VISA-shaped and plain forms for the
    # same physical unit as equal — otherwise a perfectly runnable
    # plan gets blocked by a false-positive mismatch.

    def test_visa_endpoint_matches_plain_binding(self, db):
        """Driver.config.endpoint = TCPIP0::host::port::INSTR (VISA
        form), lab binds the same host:port in plain form. Must
        match — same physical unit."""
        plan = _make_plan(db)
        lab = _make_lab(
            db, binds=[("channelEmulator", "192.168.0.132:5025")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="TCPIP0::192.168.0.132::5025::INSTR",
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True, (
            f"VISA + plain forms for same unit should match. "
            f"mismatches={result.mismatched_drivers}"
        )
        assert result.mismatched_drivers == []
        assert CE_INTERFERENCE_GENERATOR in result.lab_capabilities

    def test_driver_with_both_visa_and_parsed_ip_port_matches_either(self, db):
        """When InstrumentHALService sets BOTH `endpoint` (VISA) AND
        parsed `ip`/`port` on the same config, the validator must
        accept a binding match against either form."""
        plan = _make_plan(db)
        lab = _make_lab(
            db, binds=[("channelEmulator", "10.20.30.40:5025")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="TCPIP0::10.20.30.40::5025::INSTR",
                ip="10.20.30.40",
                port="5025",
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True
        assert result.mismatched_drivers == []

    def test_visa_endpoint_genuine_mismatch_shows_clean_display(self, db):
        """When endpoints genuinely refer to different units, the
        mismatch display should surface the operator-friendly form
        (parsed ip:port) rather than the verbose VISA resource —
        the operator compares against the binding, which is plain."""
        plan = _make_plan(db)
        lab = _make_lab(
            db, binds=[("channelEmulator", "192.168.0.100:5025")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="TCPIP0::192.168.0.200::5025::INSTR",
                ip="192.168.0.200",
                port="5025",
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is False
        assert len(result.mismatched_drivers) == 1
        m = result.mismatched_drivers[0]
        # Display: clean ip:port, NOT the TCPIP0:: prefix or ::INSTR suffix
        assert m.loaded_endpoint == "192.168.0.200:5025"
        assert "tcpip" not in m.loaded_endpoint.lower()
        assert "instr" not in m.loaded_endpoint.lower()

    def test_visa_hislip_named_resource_matches_hostname_only(self, db):
        """HiSLIP named resources (TCPIP0::host::hislip0::INSTR) don't
        carry an explicit port — both binding-side and driver-side
        canonicalize to (host, '') so identical host bindings still
        match. Conservative: doesn't try to encode the HiSLIP default
        port 4880 since the user binding may or may not include one."""
        plan = _make_plan(db)
        lab = _make_lab(
            db,
            binds=[("channelEmulator", "TCPIP0::lab1.example::hislip0::INSTR")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="TCPIP0::lab1.example::hislip0::INSTR",
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True
        assert result.mismatched_drivers == []

    def test_endpoint_match_is_whitespace_and_case_insensitive_visa(self, db):
        """The earlier whitespace/case test covered plain ip:port.
        Re-confirm the same property holds after parsing through the
        VISA-aware path — operators commonly paste with stray case."""
        plan = _make_plan(db)
        lab = _make_lab(
            db,
            binds=[("channelEmulator", "  Tcpip0::HOST.EXAMPLE::5025::INSTR  ")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])
        hal = {
            "channelEmulator": _mock_driver(
                {CE_INTERFERENCE_GENERATOR},
                endpoint="host.example:5025",
            ),
        }
        result = validate_plan(plan, lab, db, hal_drivers=hal)
        assert result.ready is True, result.mismatched_drivers


# ---------------------------------------------------------------------------
# POST /test-plans/{id}/preflight — endpoint contract
# ---------------------------------------------------------------------------

class TestPreflightEndpoint:
    def test_happy_path_returns_ready_with_capabilities(self, db, monkeypatch):
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator"])
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
        assert body["not_loaded_categories"] == []
        assert body["mismatched_drivers"] == []

    def test_endpoint_returns_mismatched_drivers_field(self, db, monkeypatch):
        """End-to-end mismatch path through the HTTP surface — pins
        the JSON shape the GUI (PR B) will render."""
        plan = _make_plan(db)
        lab = _make_lab(
            db, binds=[("channelEmulator", "192.168.1.1:5025")],
        )
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])

        class _StubHal:
            drivers = {
                "channelEmulator": _mock_driver(
                    {CE_INTERFERENCE_GENERATOR},
                    endpoint="192.168.2.2:5025",
                ),
            }

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
        assert body["not_loaded_categories"] == []
        assert len(body["mismatched_drivers"]) == 1
        m = body["mismatched_drivers"][0]
        assert m["category"] == "channelEmulator"
        assert m["expected_endpoint"] == "192.168.1.1:5025"
        assert m["loaded_endpoint"] == "192.168.2.2:5025"

    def test_gap_path_returns_actionable_detail(self, db, monkeypatch):
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["channelEmulator"])
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

    def test_endpoint_propagates_lab_scoping(self, db, monkeypatch):
        """End-to-end: HAL has a globally-loaded CE driver, the lab
        only binds positioner — endpoint must still report gap."""
        plan = _make_plan(db)
        lab = _make_lab(db, binds=["positioner"])
        _add_step(db, plan, order=1, name="cal-tone",
                  needs=[CE_INTERFERENCE_GENERATOR])

        class _StubHal:
            drivers = {
                "channelEmulator": _mock_driver({CE_INTERFERENCE_GENERATOR}),
                "positioner": _mock_driver(set()),
            }

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
        assert CE_INTERFERENCE_GENERATOR not in body["lab_capabilities"]

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
