"""Cartesian tests for the P1-9 commissioning precheck DUT-attach gate.

Sibling to test_mimo_ota_precheck_cal_gate.py — same shape, different gate.

Why this file exists: P1-8 audit (PR #62 Current Focus discussion) surfaced
that `PrecheckExecutor` had a second `overall_pass` blind spot beyond the
cal-missing one: `dut_attach` is recorded into `result_payload` and emits a
warning when missing, but **never gates `overall_pass`**. measure.py doesn't
read `dut_attach` either (`grep dut_attach measure.py` → 0 hits). So an
operator who forgets to POST /attach-dut can run a full 5-phase commissioning
and get plausible-looking PASS criteria — measure phase synthesizes RSRP from
target + path-loss and BS mock returns canned throughput numbers.

P1-9 fix mirrors P1-8 exactly:
  - Default `precheck_strict_dut=True`: dut_attach missing OR rrc_connected
    != True → precheck FAIL
  - Explicit opt-out `precheck_strict_dut=False`: gate inert, audit trail
    records "bypassed via precheck_strict_dut=False (would-fail-under-strict:
    ...)"

6-cell cartesian:
  (dut_state: missing / present_rrc_false / present_rrc_true)
    × (precheck_strict_dut: True / False)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services.mimo_ota import build_mimo_ota_test_case
from app.services.mimo_ota.executors.precheck import PrecheckExecutor
from app.services.test_execution import (
    StepDescriptor,
    StepExecutionContext,
    StepExecutionStatus,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Fixtures — same scaffold as test_mimo_ota_precheck_cal_gate.py
# ---------------------------------------------------------------------------

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


@pytest.fixture
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="DUT-Gate-Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="DUT-Gate-Lab",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def instrument_categories(db):
    """Seed critical InstrumentCategory rows so `critical_online` is not the
    blocker."""
    rows = [
        InstrumentCategory(
            category_key="channelEmulator",
            category_name="信道仿真器",
            driver_mode="mock",
            is_active=True,
            display_order=1,
        ),
        InstrumentCategory(
            category_key="baseStation",
            category_name="基站仿真器",
            driver_mode="mock",
            is_active=True,
            display_order=2,
        ),
    ]
    for r in rows:
        db.add(r)
    db.commit()
    return rows


class _RealLikeBaseStation:
    """A non-mock baseStation stand-in.

    P1-9 runtime mock-awareness (Codex on PR #75): the strict DUT gate only
    engages against a **real** baseStation (`is_mock_driver()` False). These
    cartesian tests are about the strict gate's logic, so they need a BS that
    reads as real — a `MockBaseStation` would now auto-skip the gate. Only the
    surface precheck touches matters: `query_ue_capability()`.
    """

    async def query_ue_capability(self):
        # source != "unavailable" → live_ue_query_state == "available";
        # max_dl_layers 4 ≥ requested 2 → ue_cap_pass. Mirrors what the old
        # MockBaseStation returned so the cartesian's expectations hold.
        return {"max_dl_layers": 4, "max_ul_layers": 2, "source": "real"}


class _RealLikeChannelEmulator:
    """Non-mock channelEmulator stand-in so the strict CAL gate engages (it
    too is now keyed on real hardware). precheck only optionally calls
    get_user_alignment_status / list_external_units (both hasattr-guarded), so
    a bare instance is enough — those are simply skipped."""


@pytest.fixture
def hal_with_mocks(instrument_categories):
    """Inject *real-like* (non-mock) drivers so precheck's critical_online
    check passes AND the strict DUT/CAL gates actually engage — a MockBaseStation
    / MockChannelEmulator would now auto-skip the gates (P1-9 runtime
    mock-awareness, Codex on PR #75). See `_RealLikeBaseStation` /
    `_RealLikeChannelEmulator`."""
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["channelEmulator"] = _RealLikeChannelEmulator()
    hal.drivers["baseStation"] = _RealLikeBaseStation()
    yield hal
    hal.drivers.clear()
    hal.drivers.update(saved)


@pytest.fixture
def hal_with_mock_bs(instrument_categories):
    """Like `hal_with_mocks` but baseStation is a real **mock** driver —
    used to verify the runtime auto-skip (P1-9 mock-awareness): strict DUT gate
    must be N/A when there's no real BS, even with precheck_strict_dut=True."""
    from app.hal import MockBaseStation, MockChannelEmulator
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["channelEmulator"] = MockChannelEmulator("mock-ce", {"model": "Mock"})
    hal.drivers["baseStation"] = MockBaseStation("mock-bs", {"model": "Mock"})
    yield hal
    hal.drivers.clear()
    hal.drivers.update(saved)


# ---------------------------------------------------------------------------
# Helpers — seed VALID cal so cal_pass doesn't co-fail and obscure dut_pass
# ---------------------------------------------------------------------------

def _seed_valid_cal(db, chamber_id, frequency_mhz: float = 3500.0) -> None:
    """Write a VALID ProbePathLossCalibration so the cal gate PASSes — we
    want to isolate the dut gate's behavior."""
    from app.models.probe_calibration import (
        CalibrationStatus,
        ProbePathLossCalibration,
    )

    now = datetime.utcnow()
    cal = ProbePathLossCalibration(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        probe_path_losses={"0": {"path_loss_db": 5.0}},
        sgh_model="ETS-Lindgren 3164-06",
        sgh_gain_dbi=8.0,
        status=CalibrationStatus.VALID.value,
        calibrated_at=now,
        valid_until=now.replace(year=now.year + 1),
    )
    db.add(cal)
    db.commit()


def _build_context(
    db, lab, *,
    dut_attach: Optional[Dict[str, Any]],
    strict_mode: bool,
) -> StepExecutionContext:
    """Build TestCase + TestExecution + StepExecutionContext with the chosen
    DUT-attach state and strict_dut flag.

    dut_attach lives in `TestExecution.measurements["dut_attach"]` (this is
    the contract section 2.4 of precheck.py reads from).
    """
    test_case, _descriptors = build_mimo_ota_test_case(
        db,
        name=f"DutGateCase-{uuid.uuid4().hex[:8]}",
        description="P1-9 cartesian",
        lab_profile_id=lab.id,
        config_overrides={
            "precheck_strict_dut": strict_mode,
            # Cal gate disabled so it doesn't fight the dut_pass test signal —
            # cal gate is covered by test_mimo_ota_precheck_cal_gate.py.
            # Without this, the cartesian's no-cal default config would fail
            # at cal_pass first and we couldn't observe dut_pass behavior.
            "precheck_strict_cal": False,
        },
        created_by="pytest-dut-gate",
    )
    measurements: Dict[str, Any] = {}
    if dut_attach is not None:
        measurements["dut_attach"] = dut_attach

    execution = TestExecution(
        test_case_id=test_case.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={"step_descriptors": []},
        measurements=measurements,
        executed_by="pytest-dut-gate",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    step = StepDescriptor(
        id="precheck-step", type="MIMO_OTA_PRECHECK", parameters={},
    )
    return StepExecutionContext(
        db=db,
        step=step,
        test_execution=execution,
        lab_profile=lab,
        calibration_certificate=None,
    )


# ---------------------------------------------------------------------------
# 6-cell cartesian — (dut_state) × (strict_mode)
# ---------------------------------------------------------------------------

# dut_state values mapped to dut_attach dict (or None for missing):
_DUT_STATES = {
    "missing": None,
    "present_rrc_false": {
        "imsi": "001010123456789",
        "dut_model": "TestDUT-1",
        "rrc_connected": False,
    },
    "present_rrc_true": {
        "imsi": "001010123456789",
        "dut_model": "TestDUT-1",
        "rrc_connected": True,
    },
}

# (dut_state, strict_mode) → (overall_pass, dut_pass, reason_keywords)
PARAMS = [
    # === STRICT ===
    ("missing",           True, False, False, ["DUT attach record missing"]),
    ("present_rrc_false", True, False, False, ["rrc_connected=False"]),
    ("present_rrc_true",  True, True,  True,  ["ok"]),
    # === BYPASS ===
    ("missing",           False, True, True, ["bypassed", "dut_attach missing"]),
    ("present_rrc_false", False, True, True, ["bypassed", "rrc_connected=False"]),
    ("present_rrc_true",  False, True, True, ["bypassed"]),
]


@pytest.mark.parametrize(
    "dut_state, strict_mode, expect_overall_pass, expect_dut_pass, expect_reason_keywords",
    PARAMS,
    ids=[f"{ds}-{'strict' if s else 'bypass'}" for (ds, s, _o, _dp, _r) in PARAMS],
)
@pytest.mark.asyncio
async def test_precheck_dut_gate_cartesian(
    db, lab, chamber, hal_with_mocks,
    dut_state: str,
    strict_mode: bool,
    expect_overall_pass: bool,
    expect_dut_pass: bool,
    expect_reason_keywords: list[str],
):
    # Seed valid cal so cal_pass isn't the blocker (we set strict_cal=False
    # in config too, but seeding adds belt-and-suspenders signal isolation).
    _seed_valid_cal(db, chamber.id)

    ctx = _build_context(
        db, lab,
        dut_attach=_DUT_STATES[dut_state],
        strict_mode=strict_mode,
    )
    result = await PrecheckExecutor().execute(ctx)
    measurements = result.measurements or {}

    assert measurements.get("overall_pass") == expect_overall_pass, (
        f"overall_pass mismatch: got {measurements.get('overall_pass')}, "
        f"expected {expect_overall_pass}; dut_pass_reason="
        f"{measurements.get('dut_pass_reason')!r}"
    )
    assert measurements.get("dut_pass") == expect_dut_pass, (
        f"dut_pass mismatch: got {measurements.get('dut_pass')}, "
        f"expected {expect_dut_pass}"
    )

    reason = measurements.get("dut_pass_reason", "") or ""
    for keyword in expect_reason_keywords:
        assert keyword in reason, (
            f"dut_pass_reason missing keyword {keyword!r}; got {reason!r}"
        )

    # Status correlates with overall_pass
    if expect_overall_pass:
        assert result.status == StepExecutionStatus.SUCCESS, (
            f"expected SUCCESS, got {result.status}: {result.error_message}"
        )
    else:
        assert result.status == StepExecutionStatus.FAILED
        assert result.error_message and "Pre-check failed:" in result.error_message
        # cal_pass is False'd because no cal seeded? wait we seeded it.
        # The dut keywords should appear in error_message.
        dut_keywords = [k for k in expect_reason_keywords if k != "bypassed"]
        assert any(k in result.error_message for k in dut_keywords), (
            f"error_message {result.error_message!r} missing dut keywords {dut_keywords}"
        )


# ---------------------------------------------------------------------------
# Runtime mock-awareness (Codex on PR #75): mock/absent BS auto-skips the gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_baseStation_auto_skips_strict_dut_gate(
    db, lab, chamber, hal_with_mock_bs,
):
    """precheck_strict_dut=True + NO DUT attach, but baseStation is a mock
    driver → the gate is N/A (a real DUT can't attach to a mock BS), so
    dut_pass is True and the run isn't blocked. This is the local-rehearsal
    path that must 'just work' without any toggle."""
    _seed_valid_cal(db, chamber.id)
    ctx = _build_context(db, lab, dut_attach=None, strict_mode=True)
    result = await PrecheckExecutor().execute(ctx)
    measurements = result.measurements or {}

    assert measurements.get("dut_pass") is True, (
        f"mock BS should auto-skip the DUT gate; got dut_pass="
        f"{measurements.get('dut_pass')}, reason={measurements.get('dut_pass_reason')!r}"
    )
    reason = measurements.get("dut_pass_reason", "") or ""
    assert "gate N/A" in reason and "mock" in reason, (
        f"expected mock-auto-skip reason, got {reason!r}"
    )
    # And with cal seeded + dut auto-skipped, the whole precheck passes.
    assert measurements.get("overall_pass") is True
    assert result.status == StepExecutionStatus.SUCCESS


# ---------------------------------------------------------------------------
# Independence from cal gate — verify dut_pass and cal_pass don't conflate
# ---------------------------------------------------------------------------

class TestDutAndCalGatesIndependent:
    """Pin that dut_pass and cal_pass are computed and reported separately,
    so an operator can see which gate failed without the audit trail of one
    swallowing the other."""

    @pytest.mark.asyncio
    async def test_both_gates_fail_both_in_error(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """No cal + no DUT, both strict — error_message must mention both."""
        # Don't seed cal. Don't attach DUT.
        test_case, _ = build_mimo_ota_test_case(
            db,
            name=f"BothFailCase-{uuid.uuid4().hex[:8]}",
            description="P1-9 independence",
            lab_profile_id=lab.id,
            config_overrides={
                "precheck_strict_dut": True,
                "precheck_strict_cal": True,
            },
            created_by="pytest-dut-gate",
        )
        execution = TestExecution(
            test_case_id=test_case.id,
            status="pending",
            started_at=datetime.utcnow(),
            config={"step_descriptors": []},
            measurements={},
            executed_by="pytest-dut-gate",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        ctx = StepExecutionContext(
            db=db,
            step=StepDescriptor(id="s", type="MIMO_OTA_PRECHECK", parameters={}),
            test_execution=execution,
            lab_profile=lab,
            calibration_certificate=None,
        )
        result = await PrecheckExecutor().execute(ctx)

        assert result.status == StepExecutionStatus.FAILED
        msg = result.error_message or ""
        assert "path-loss calibration missing" in msg, (
            f"error_message missing cal failure: {msg!r}"
        )
        assert "DUT attach record missing" in msg, (
            f"error_message missing dut failure: {msg!r}"
        )

        measurements = result.measurements or {}
        assert measurements["cal_pass"] is False
        assert measurements["dut_pass"] is False
        # Reasons stored separately
        assert "calibration missing" in (measurements.get("cal_pass_reason") or "")
        assert "DUT attach record missing" in (measurements.get("dut_pass_reason") or "")


# ---------------------------------------------------------------------------
# Live BS query verification (P1-9 Codex P2 follow-up on commit 655d7e3)
#
# Codex flagged that the initial P1-9 gate trusted the cached
# measurements['dut_attach'].rrc_connected snapshot. If the DUT attached
# successfully but then dropped RRC before precheck runs, the gate still
# passed because nothing re-verified the live state. Fix reuses the
# bs.query_ue_capability() call already happening in section 2.5 and exposes
# its result as `live_ue_query_state` ("available" / "unavailable" /
# "unknown"). The strict dut gate now requires "available" — anything else
# means the cached snapshot can't be trusted.
# ---------------------------------------------------------------------------


def _patch_mock_bs_to_unavailable(hal):
    """Force the mock BS to report `source: 'unavailable'` so we can test the
    live-unverified branch of the dut gate.

    Mock default returns `source: 'mock'` which maps to live_ue_query_state
    = 'available', so the cartesian above never exercises the unavailable
    path. This helper monkey-patches the in-memory mock for one test."""
    mock_bs = hal.drivers["baseStation"]

    async def _unavailable_cap() -> Dict[str, Any]:
        return {
            "max_dl_layers": None,
            "max_ul_layers": None,
            "source": "unavailable",
        }

    mock_bs.query_ue_capability = _unavailable_cap  # type: ignore[method-assign]
    return mock_bs


class TestLiveQueryVerification:
    """Pin that strict dut gate requires live BS query confirmation, not
    just the cached attach snapshot."""

    @pytest.mark.asyncio
    async def test_cached_rrc_true_but_live_unavailable_strict_fails(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Worst case: attach said RRC connected, but DUT has since dropped
        — live query reports unavailable, strict gate must FAIL despite the
        cached snapshot saying connected."""
        _seed_valid_cal(db, chamber.id)
        _patch_mock_bs_to_unavailable(hal_with_mocks)

        ctx = _build_context(
            db, lab,
            dut_attach=_DUT_STATES["present_rrc_true"],  # cached says connected
            strict_mode=True,
        )
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.FAILED
        assert measurements["dut_pass"] is False
        assert measurements["live_ue_query_state"] == "unavailable"
        reason = measurements["dut_pass_reason"]
        assert "live BS query state" in reason
        assert "stale" in reason

    @pytest.mark.asyncio
    async def test_cached_rrc_true_but_live_unavailable_bypass_passes_with_audit(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Bypass lets the run continue but audit trail records the mismatch."""
        _seed_valid_cal(db, chamber.id)
        _patch_mock_bs_to_unavailable(hal_with_mocks)

        ctx = _build_context(
            db, lab,
            dut_attach=_DUT_STATES["present_rrc_true"],
            strict_mode=False,
        )
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["overall_pass"] is True
        assert measurements["dut_pass"] is True  # forced by bypass
        assert measurements["live_ue_query_state"] == "unavailable"
        reason = measurements["dut_pass_reason"]
        assert "bypassed" in reason
        assert "live_ue_query_state='unavailable'" in reason

    @pytest.mark.asyncio
    async def test_cached_rrc_true_and_live_available_strict_passes(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Sanity: mock BS default returns 'mock' source → 'available' →
        gate passes (regression guard so we don't break the happy path)."""
        _seed_valid_cal(db, chamber.id)
        # Don't patch — default mock returns source="mock"
        ctx = _build_context(
            db, lab,
            dut_attach=_DUT_STATES["present_rrc_true"],
            strict_mode=True,
        )
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["dut_pass"] is True
        assert measurements["live_ue_query_state"] == "available"

    @pytest.mark.asyncio
    async def test_no_bs_driver_strict_run_still_fails_via_critical_online(
        self, db, lab, chamber, instrument_categories,
    ):
        """Without a baseStation driver, the run must still FAIL — but under
        P1-9 runtime mock-awareness (Codex on PR #75) the protection now comes
        from critical_online (baseStation offline), NOT the DUT gate: with no
        real BS, no real DUT can attach, so the DUT gate is N/A (dut_pass=True,
        gate-N/A reason). The important invariant is overall_pass=False — we
        never measure real PDSCH with no baseStation."""
        from app.hal import MockChannelEmulator
        from app.services.instrument_hal_service import get_hal_service

        hal = get_hal_service()
        saved = dict(hal.drivers)
        hal.drivers["channelEmulator"] = MockChannelEmulator(
            "mock-ce", {"model": "Mock"}
        )
        # NOTE: deliberately no baseStation driver
        try:
            _seed_valid_cal(db, chamber.id)
            ctx = _build_context(
                db, lab,
                dut_attach=_DUT_STATES["present_rrc_true"],
                strict_mode=True,
            )
            result = await PrecheckExecutor().execute(ctx)
            measurements = result.measurements or {}

            # Run fails — but via critical_online (baseStation offline), the
            # real safety net here. The DUT gate itself is N/A (no real BS).
            assert result.status == StepExecutionStatus.FAILED
            assert measurements["critical_instruments_online"] is False
            assert measurements["dut_pass"] is True  # gate N/A — absent BS
            assert "gate N/A" in measurements["dut_pass_reason"]
            assert measurements["live_ue_query_state"] == "unknown"
        finally:
            hal.drivers.clear()
            hal.drivers.update(saved)


# ---------------------------------------------------------------------------
# QZ ripple fallback must be marked "未验证(兜底值)", not a clean PASS (P1-12 audit)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qz_ripple_fallback_marked_unverified(
    db, lab, chamber, hal_with_mock_bs,
):
    """No ProbePattern data → QZ ripple falls back to the legacy 0.7 dB
    constant. That is NOT a measured quiet-zone qualification, so precheck must
    flag it: quiet_zone_verified=False + a 未验证 message (so report/GUI show it
    显著). The run still proceeds (qz_pass stays True — we mark, not fail-loud,
    so local/mock rehearsal without pattern data can still run)."""
    _seed_valid_cal(db, chamber.id)
    ctx = _build_context(db, lab, dut_attach=None, strict_mode=True)
    result = await PrecheckExecutor().execute(ctx)
    m = result.measurements or {}

    assert m.get("quiet_zone_ripple_source") == "fallback_default", m.get("quiet_zone_ripple_source")
    assert m.get("quiet_zone_verified") is False, "fallback QZ must be marked unverified"
    assert m.get("quiet_zone_pass") is True, "marking, not failing — run still proceeds"
    assert any("未验证" in msg for msg in m.get("messages", [])), (
        f"expected a 未验证 QZ message, got {m.get('messages')!r}"
    )
    # The fallback QZ did NOT silently block the run (DUT auto-skipped via mock
    # BS, cal seeded) — overall passes but with QZ flagged unverified.
    assert m.get("overall_pass") is True
