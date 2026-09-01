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

from tests.base_station_mock_factory import registered_mock_base_station

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
    surface precheck touches matters: `get_cell_state()` + `query_ue_capability()`.

    ⚠ 2026-08-08（外审 #304 P1）起**连通性判据换成小区状态** —— 能力查询只
    用于层数协商校验。理由：`query_ue_capability` 查的是"支持几层"（能力）
    不是"连上了没有"（状态），而 LTE_NR_IRAT 上那几条命令模板全是 None，
    即使小区已回 CONN 也恒报 unavailable → 严格门永远判 DUT 没挂上。
    所以这个桩必须同时提供两个面，否则测的就不是门的逻辑了。
    """

    #: 让用例能改：CONNECTED = DUT 挂上了；ON = 小区开着但没 UE
    cell_state = None    # 在 __init__ 里填，避免类属性被跨用例共享

    def __init__(self):
        from app.hal.base_station import CellState
        self.cell_state = CellState.CONNECTED

    async def get_cell_state(self):
        return self.cell_state

    async def query_ue_capability(self):
        # max_dl_layers 4 ≥ requested 2 → ue_cap_pass。
        # ⚠ 这里的 source 不再影响连通性判定（那已换源到 get_cell_state）。
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
    hal.drivers["channelEmulator"] = MockChannelEmulator("mock-ce", {"model": "UXM 5G E7515B"})
    hal.drivers["baseStation"] = registered_mock_base_station("mock-bs", {"model": "UXM 5G E7515B"})
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
        },
        created_by="pytest-dut-gate",
        execution_policy={
            "schema_version": 1,
            "mode": "diagnostic",
            "reason": "isolate DUT gate from calibration",
            "updated_by": "pytest-dut-gate",
            "updated_at": "2026-08-29T00:00:00Z",
        },
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

    expected_overall = None if expect_overall_pass else False
    assert measurements.get("overall_pass") is expected_overall, (
        f"overall_pass mismatch: got {measurements.get('overall_pass')}, "
        f"expected {expected_overall}; dut_pass_reason="
        f"{measurements.get('dut_pass_reason')!r}"
    )
    assert measurements.get("operational_ready") is expect_overall_pass
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


@pytest.mark.asyncio
async def test_managed_rf_attach_defers_live_dut_gate_until_measure(
    db, lab, chamber, hal_with_mocks,
):
    """标准吞吐量流程在 PRECHECK 时还没有初始化仪表，不能要求旧 attach。

    静态预检应通过并明确记录“动态门延后”；随后 MEASURE 必须在按 TestCase
    初始化并受控 attach 后重新执行真实连接门。这里仅锁定前半段边界。
    """
    _seed_valid_cal(db, chamber.id)
    ctx = _build_context(db, lab, dut_attach=None, strict_mode=True)
    cfg = dict(ctx.test_execution.config or {})
    cfg["managed_rf_attach"] = True
    ctx.test_execution.config = cfg
    db.commit()

    result = await PrecheckExecutor().execute(ctx)
    measurements = result.measurements or {}

    assert result.status == StepExecutionStatus.SUCCESS
    assert measurements.get("dut_pass") is True
    assert measurements.get("dut_gate_deferred") is True
    assert measurements.get("live_ue_query_state") == "deferred"
    assert measurements.get("ue_capability_deferred") is True
    assert "MEASURE" in (measurements.get("dut_pass_reason") or "")


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
    assert measurements.get("operational_ready") is True
    assert measurements.get("overall_pass") is None
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
    """让 BS 报「DUT 没挂上」，用来测严格门的 live-unverified 分支。

    ⚠ 2026-08-08（外审 #304 P1）起换源：连通性判据是 **`get_cell_state()`**，
    不再是 `query_ue_capability` 的 source 字段。所以模拟"DUT 掉线"要打的是
    小区状态 —— 打 `ON`（小区开着但没 UE 连上），那正是 2026-08-07 现场后两轮
    60 秒 attach 超时时读到的值。
    能力查询一并打成 unavailable，保持"掉线时两个面一致"，但**它不再决定
    这条分支走哪边** —— 只打它的话本 helper 会失效（换源后 source 不参与判定）。
    """
    mock_bs = hal.drivers["baseStation"]

    from app.hal.base_station import CellState

    async def _cell_not_connected() -> CellState:
        return CellState.ON

    async def _unavailable_cap() -> Dict[str, Any]:
        return {
            "max_dl_layers": None,
            "max_ul_layers": None,
            "source": "unavailable",
        }

    mock_bs.get_cell_state = _cell_not_connected  # type: ignore[method-assign]
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
        assert measurements["operational_ready"] is True
        assert measurements["overall_pass"] is None
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
            "mock-ce", {"model": "UXM 5G E7515B"}
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
# QZ evidence must stay tri-state and never publish a fallback/proxy PASS.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qz_ripple_fallback_marked_unverified(
    db, lab, chamber, hal_with_mock_bs,
):
    """No pattern or grid evidence means UNKNOWN, while diagnostics continue."""
    _seed_valid_cal(db, chamber.id)
    ctx = _build_context(db, lab, dut_attach=None, strict_mode=True)
    result = await PrecheckExecutor().execute(ctx)
    m = result.measurements or {}

    assert m.get("quiet_zone_ripple_db") is None
    assert m.get("quiet_zone_proxy_ripple_db") is None
    assert m.get("quiet_zone_verified") is False
    assert m.get("quiet_zone_pass") is None
    assert m.get("quiet_zone_can_continue") is True
    assert m.get("quiet_zone_evidence") == {
        "schema_version": 1,
        "status": "unavailable",
        "source": "missing",
        "formal_verified": False,
        "measured_ripple_db": None,
        "proxy_ripple_db": None,
        "calibration_id": None,
    }
    assert any("未判定" in msg for msg in m.get("messages", [])), (
        f"expected a 未判定 QZ message, got {m.get('messages')!r}"
    )
    assert result.status == StepExecutionStatus.SUCCESS
    assert m.get("operational_ready") is True
    assert m.get("overall_pass") is None


@pytest.mark.asyncio
async def test_qz_probe_pattern_spread_is_diagnostic_only(
    db, lab, chamber, hal_with_mock_bs, monkeypatch,
):
    monkeypatch.setattr(
        "app.services.probe_pattern.consumer.estimate_quiet_zone_ripple_db",
        lambda *_args, **_kwargs: 0.42,
    )
    _seed_valid_cal(db, chamber.id)
    ctx = _build_context(db, lab, dut_attach=None, strict_mode=True)

    result = await PrecheckExecutor().execute(ctx)
    m = result.measurements or {}

    assert result.status == StepExecutionStatus.SUCCESS
    assert m.get("quiet_zone_ripple_db") is None
    assert m.get("quiet_zone_proxy_ripple_db") == pytest.approx(0.42)
    assert m.get("quiet_zone_pass") is None
    assert m.get("quiet_zone_verified") is False
    assert m.get("overall_pass") is None
    assert m.get("quiet_zone_evidence", {}).get("status") == "diagnostic_proxy"
    assert any(
        "诊断代理" in msg and "非静区" in msg and "实测" in msg
        for msg in m["messages"]
    )
