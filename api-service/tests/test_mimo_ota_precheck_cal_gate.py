"""Cartesian tests for the P1-8 commissioning precheck cal-missing gate.

Why this file exists: PR #59 (P1-7) + Codex P2 review on PR #60 surfaced that
[`PrecheckExecutor`](../app/services/mimo_ota/executors/precheck.py) was
computing `overall_pass = critical_online and qz_pass and ue_cap_pass` —
calibration state was written into `result_payload` but **never entered the
gate**. An uncalibrated chamber could pass precheck and silently fall back to
`typical_cable_loss_db + duplexer - pa_gain` in the measure phase, producing
.asc files based on typical values rather than measured path-loss.

P1-8 fix:
  - Default `precheck_strict_cal=True`: cal missing/broken → precheck FAIL
  - Explicit opt-out `precheck_strict_cal=False`: cal gate bypassed but
    `cal_pass_reason` records "bypassed via precheck_strict_cal=False
    (would-fail-under-strict: ...)" so audit trails know

These tests pin the 12-cell cartesian:
  (path_loss_cal: present / missing)
    × (cal_cert: None / overall_pass=True / overall_pass=False)
    × (precheck_strict_cal: True / False)
  = 2 × 3 × 2 = 12 cases

Each case asserts:
  - `result.status` (SUCCESS / FAILED)
  - `result.measurements["overall_pass"]`
  - `result.measurements["cal_pass"]`
  - `result.measurements["cal_pass_reason"]` (substring match)
  - `result.error_message` contains the failure cause when FAILED
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.calibration import CalibrationCertificate
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile
from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePathLossCalibration,
)
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
# Fixtures — minimal scaffold to exercise PrecheckExecutor in isolation
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Cal-Gate-Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="Cal-Gate-Lab",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def instrument_categories(db):
    """Seed the critical InstrumentCategory rows so precheck's
    `critical_online` gate isn't the blocker we're testing."""
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


@pytest.fixture
def hal_with_mocks(instrument_categories):
    """Inject mock drivers so precheck's `_CRITICAL_INSTRUMENT_CATEGORIES`
    check passes. Cleared after the test."""
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
# Helpers — seed cal data + build StepExecutionContext
# ---------------------------------------------------------------------------

def _seed_path_loss_cal(db, chamber_id, frequency_mhz: float = 3500.0) -> None:
    """Write a minimal VALID ProbePathLossCalibration so
    `latest_pl is not None` and `result_payload["path_loss_calibration_valid"]
    = True`."""
    now = datetime.utcnow()
    cal = ProbePathLossCalibration(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        probe_path_losses={"0": {"path_loss_db": 5.0}, "1": {"path_loss_db": 5.2}},
        sgh_model="ETS-Lindgren 3164-06",
        sgh_gain_dbi=8.0,
        status=CalibrationStatus.VALID.value,
        calibrated_at=now,
        valid_until=now.replace(year=now.year + 1),  # 1 year validity
    )
    db.add(cal)
    db.commit()


def _make_cal_cert(overall_pass: bool) -> CalibrationCertificate:
    """Build a CalibrationCertificate row with a chosen `overall_pass`.

    Caller is responsible for db.add / commit if persistence is needed —
    `context.calibration_certificate` is set directly on StepExecutionContext
    so we don't even have to attach it to a TestCase. Keeping it detached
    avoids the LabProfile.active_calibration_certificate_id machinery that
    would otherwise interfere with the cert-state parametrization.
    """
    return CalibrationCertificate(
        certificate_number=f"CAL-GATE-TEST-{uuid.uuid4().hex[:8]}",
        calibration_date=datetime.utcnow(),
        valid_until=datetime.utcnow(),
        overall_pass=overall_pass,
    )


def _build_context(
    db,
    lab,
    *,
    cal_cert: Optional[CalibrationCertificate],
    strict_mode: bool,
) -> StepExecutionContext:
    """Build a TestCase + TestExecution + StepExecutionContext pinned to the
    given strict mode and (detached) cal cert."""
    test_case, _descriptors = build_mimo_ota_test_case(
        db,
        name=f"CalGateCase-{uuid.uuid4().hex[:8]}",
        description="P1-8 cartesian",
        lab_profile_id=lab.id,
        config_overrides={
            "precheck_strict_cal": strict_mode,
            # P1-9 (2026-05-19): dut gate disabled so it doesn't fight the
            # cal_pass test signal — dut gate is covered by
            # test_mimo_ota_precheck_dut_gate.py. Without this, the cartesian's
            # no-dut default would fail at dut_pass first and we couldn't
            # observe cal_pass behavior in isolation.
            "precheck_strict_dut": False,
            # Keep config defaults; pass_criteria.max_quiet_zone_ripple_db=1.0
            # so the precheck QZ ripple gate (default fallback 0.7 dB) passes.
        },
        created_by="pytest-cal-gate",
    )
    execution = TestExecution(
        test_case_id=test_case.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={"step_descriptors": []},
        executed_by="pytest-cal-gate",
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
        calibration_certificate=cal_cert,
    )


# ---------------------------------------------------------------------------
# 12-cell cartesian
# ---------------------------------------------------------------------------

# (path_loss_present, cal_cert_state, strict_mode)
#   - path_loss_present: bool — seed a VALID ProbePathLossCalibration or not
#   - cal_cert_state: "none" / "pass" / "fail" — None / overall_pass=True/False
#   - strict_mode: bool — config.precheck_strict_cal
# Expected (overall_pass, cal_pass, reason_keywords)
PARAMS = [
    # === STRICT (default) — gate active ===
    # path_loss present
    (True,  "none", True, True,  True,  ["ok"]),
    (True,  "pass", True, True,  True,  ["ok"]),
    (True,  "fail", True, False, False, ["not passed"]),
    # path_loss missing
    (False, "none", True, False, False, ["missing or invalid"]),
    (False, "pass", True, False, False, ["missing or invalid"]),
    (False, "fail", True, False, False, ["missing or invalid", "not passed"]),
    # === BYPASS — gate inert, audit trail records would-fail ===
    (True,  "none", False, True, True, ["bypassed"]),
    (True,  "pass", False, True, True, ["bypassed"]),
    (True,  "fail", False, True, True, ["bypassed", "cal_cert.overall_pass=False"]),
    (False, "none", False, True, True, ["bypassed", "path-loss calibration missing", "cal_cert is None"]),
    (False, "pass", False, True, True, ["bypassed", "path-loss calibration missing"]),
    (False, "fail", False, True, True, ["bypassed", "path-loss calibration missing", "cal_cert.overall_pass=False"]),
]


@pytest.mark.parametrize(
    "path_loss_present, cal_cert_state, strict_mode, "
    "expect_overall_pass, expect_cal_pass, expect_reason_keywords",
    PARAMS,
    ids=[
        f"{'pl_yes' if p else 'pl_no'}-cert_{c}-{'strict' if s else 'bypass'}"
        for (p, c, s, _o, _cp, _r) in PARAMS
    ],
)
@pytest.mark.asyncio
async def test_precheck_cal_gate_cartesian(
    db, lab, chamber, hal_with_mocks,
    path_loss_present: bool,
    cal_cert_state: str,
    strict_mode: bool,
    expect_overall_pass: bool,
    expect_cal_pass: bool,
    expect_reason_keywords: list[str],
):
    # Seed path-loss calibration if this case wants it
    if path_loss_present:
        _seed_path_loss_cal(db, chamber.id)

    # Build the cal_cert per state
    cal_cert: Optional[CalibrationCertificate]
    if cal_cert_state == "none":
        cal_cert = None
    elif cal_cert_state == "pass":
        cal_cert = _make_cal_cert(overall_pass=True)
    elif cal_cert_state == "fail":
        cal_cert = _make_cal_cert(overall_pass=False)
    else:  # pragma: no cover - parametrize bug guard
        raise AssertionError(f"unknown cal_cert_state {cal_cert_state!r}")

    ctx = _build_context(db, lab, cal_cert=cal_cert, strict_mode=strict_mode)
    result = await PrecheckExecutor().execute(ctx)

    measurements = result.measurements or {}

    assert measurements.get("overall_pass") == expect_overall_pass, (
        f"overall_pass mismatch: got {measurements.get('overall_pass')}, "
        f"expected {expect_overall_pass}; cal_pass_reason="
        f"{measurements.get('cal_pass_reason')!r}"
    )
    assert measurements.get("cal_pass") == expect_cal_pass, (
        f"cal_pass mismatch: got {measurements.get('cal_pass')}, "
        f"expected {expect_cal_pass}"
    )

    reason = measurements.get("cal_pass_reason", "") or ""
    for keyword in expect_reason_keywords:
        assert keyword in reason, (
            f"cal_pass_reason missing keyword {keyword!r}; got {reason!r}"
        )

    # Status correlates with overall_pass
    if expect_overall_pass:
        assert result.status == StepExecutionStatus.SUCCESS, (
            f"expected SUCCESS, got {result.status}: {result.error_message}"
        )
    else:
        assert result.status == StepExecutionStatus.FAILED, (
            f"expected FAILED, got {result.status}"
        )
        # error_message must mention the cal failure so on-site operator knows why
        assert result.error_message and "Pre-check failed:" in result.error_message
        # At least one of the cal-related keywords appears in the error
        cal_keywords = [k for k in expect_reason_keywords if k not in ("bypassed",)]
        assert any(k in result.error_message for k in cal_keywords), (
            f"error_message {result.error_message!r} missing cal keywords {cal_keywords}"
        )


# ---------------------------------------------------------------------------
# Frequency-window boundary tests (P1-8 Codex P1 follow-up on 42af8ca)
#
# Codex flagged that the initial P1-8 implementation just checked
# `path_loss_calibration_valid` set by a chamber-only query — an old/
# different-band VALID cert (e.g. 700 MHz cert for a 3500 MHz test) would
# pass precheck silently and then leave Phase 3 with no usable cert.
#
# Fix: precheck now goes through ProbePathLossCalibrationService.
# get_latest_calibration(chamber_id, freq_mhz), which applies the same ±5%
# frequency window measure.py uses. These tests pin that window contract:
#   - 3500 MHz target accepts certs in 3325-3675 MHz
#   - 700 MHz cert at 3500 MHz target → strict FAIL with audit trail showing
#     "frequency_out_of_window"
#   - bypass: same setup PASSes but cal_pass_reason still records would-fail
# ---------------------------------------------------------------------------


class TestFrequencyWindow:
    """Pin the ±5% frequency-matching contract between precheck and measure."""

    @pytest.mark.asyncio
    async def test_mismatched_frequency_strict_fails(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Cert at 700 MHz can't satisfy a 3500 MHz commissioning run."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=700.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.FAILED
        assert measurements["overall_pass"] is False
        assert measurements["cal_pass"] is False
        assert measurements["path_loss_calibration_valid"] is False
        # The cert exists for the chamber, just out of window — the audit
        # field disambiguates from "no cert at all" for operator UX
        assert measurements["path_loss_calibration_reason"] == "frequency_out_of_window"
        assert "missing or invalid" in measurements["cal_pass_reason"]

    @pytest.mark.asyncio
    async def test_mismatched_frequency_bypass_passes_with_audit(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Bypass lets the run continue but audit trail flags the mismatch."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=700.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=False)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["overall_pass"] is True
        assert measurements["cal_pass"] is True
        # path_loss_calibration_valid still reflects reality (mismatched)
        assert measurements["path_loss_calibration_valid"] is False
        assert measurements["path_loss_calibration_reason"] == "frequency_out_of_window"
        # Audit trail proves "this run happened despite the mismatch"
        assert "bypassed" in measurements["cal_pass_reason"]
        assert "path-loss calibration missing" in measurements["cal_pass_reason"]

    @pytest.mark.asyncio
    async def test_upper_boundary_within_window_passes(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """3500 × 1.05 = 3675 MHz cert ↔ 3500 MHz target: at-window edge,
        must pass strict."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3675.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["overall_pass"] is True
        assert measurements["cal_pass"] is True
        assert measurements["path_loss_calibration_valid"] is True
        assert measurements["path_loss_calibration_frequency_mhz"] == 3675.0

    @pytest.mark.asyncio
    async def test_lower_boundary_within_window_passes(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """3500 × 0.95 = 3325 MHz cert ↔ 3500 MHz target: at-window edge,
        must pass strict."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3325.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.SUCCESS
        assert measurements["overall_pass"] is True
        assert measurements["cal_pass"] is True
        assert measurements["path_loss_calibration_valid"] is True

    @pytest.mark.asyncio
    async def test_just_outside_upper_boundary_fails_strict(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """Just above the +5% window: 3676 MHz cert vs 3500 MHz target →
        out of window → FAIL strict."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3676.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert result.status == StepExecutionStatus.FAILED
        assert measurements["path_loss_calibration_reason"] == "frequency_out_of_window"

    @pytest.mark.asyncio
    async def test_target_frequency_recorded_in_audit_trail(
        self, db, lab, chamber, hal_with_mocks,
    ):
        """`path_loss_calibration_target_frequency_mhz` always written so
        operator / audit can correlate the cert window with the test config."""
        _seed_path_loss_cal(db, chamber.id, frequency_mhz=3500.0)
        ctx = _build_context(db, lab, cal_cert=None, strict_mode=True)
        result = await PrecheckExecutor().execute(ctx)
        measurements = result.measurements or {}

        assert measurements["path_loss_calibration_target_frequency_mhz"] == 3500.0
        assert measurements["path_loss_calibration_frequency_mhz"] == 3500.0
