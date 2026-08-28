"""Reference-phase TRP must be flagged 未验证(兜底值) unless a REAL signal
analyzer produced it (P1-12 audit, sibling to the QZ marking in PR #79).

Two non-real cases must both be flagged trp_verified=False + a 未验证 warning:
  - no signalAnalyzer driver → _MOCK_TRP_DBM constant (source="mock")
  - a *mock* signalAnalyzer → simulated power that carries the
    "hal_signal_analyzer" source label but is NOT a real measurement.
The run still SUCCEEDs (we mark, not fail — mock rehearsal must run).
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services.mimo_ota import build_mimo_ota_test_case
from app.services.mimo_ota.executors.reference import ReferenceExecutor
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
def lab(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Ref-Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    lp = LabProfile(name="Ref-Lab", chamber_config_id=c.id, is_active=True)
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _ctx(db, lab, *, config_overrides=None, diagnostic=False) -> StepExecutionContext:
    tc, _ = build_mimo_ota_test_case(
        db,
        name=f"Ref-{uuid.uuid4().hex[:8]}",
        lab_profile_id=lab.id,
        config_overrides=config_overrides or {},
        created_by="pytest-ref",
        execution_policy=(
            {
                "schema_version": 1,
                "mode": "diagnostic",
                "reason": "reference-free diagnostic fixture",
                "updated_by": "pytest-ref",
                "updated_at": "2026-08-29T00:00:00Z",
            }
            if diagnostic
            else None
        ),
    )
    ex = TestExecution(
        test_case_id=tc.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={"step_descriptors": []},
        executed_by="pytest-ref",
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return StepExecutionContext(
        db=db,
        step=StepDescriptor(id="ref-step", type="MIMO_OTA_REFERENCE", parameters={}),
        test_execution=ex,
        lab_profile=lab,
        calibration_certificate=None,
    )


class _RealLikeSA:
    """Non-mock signalAnalyzer stand-in (is_mock_driver() False → trp_verified
    True). Implements just the surface ReferenceExecutor calls."""

    async def setup_spectrum(self, **kwargs):
        return True

    async def measure_channel_power(self, **kwargs):
        return -50.0  # +73.5 offset → 23.5 dBm TRP


class _RecordingSA(_RealLikeSA):
    def __init__(self):
        self.calls: list[str] = []

    async def setup_spectrum(self, **kwargs):
        self.calls.append("setup")
        return True

    async def measure_channel_power(self, **kwargs):
        self.calls.append("measure")
        return -50.0


class _FailedPowerSA(_RealLikeSA):
    async def measure_channel_power(self, **kwargs):
        raise RuntimeError("FSVA sweep timed out")


def _swap_sa(driver):
    """Set (or remove, when driver is None) the signalAnalyzer in the live HAL;
    returns (hal, saved) so the caller restores in a finally."""
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved = dict(hal.drivers)
    if driver is None:
        hal.drivers.pop("signalAnalyzer", None)
    else:
        hal.drivers["signalAnalyzer"] = driver
    return hal, saved


@pytest.mark.asyncio
async def test_no_sa_trp_marked_unverified(db, lab):
    hal, saved = _swap_sa(None)
    try:
        result = await ReferenceExecutor().execute(_ctx(db, lab))
    finally:
        hal.drivers.clear()
        hal.drivers.update(saved)
    m = result.measurements or {}
    assert m["measurement_source"] == "mock"
    assert m["trp_verified"] is False
    assert result.status == StepExecutionStatus.SUCCESS  # mark, not fail
    assert any("未验证" in w for w in (result.warnings or [])), result.warnings


@pytest.mark.asyncio
async def test_mock_sa_trp_marked_unverified(db, lab):
    """SA 挂着但是 mock 驱动 → 来源如实标成 `hal_signal_analyzer_mock`，且不算已验证。

    ⚠️ 2026-08-10（P1-48）改了断言：原来断言标签是 `hal_signal_analyzer`，
    而这条测试自己的 docstring 当时就写着「yet NOT a real measurement」——
    **它把一个已知会误导读者的标签钉成了契约**。现在来源如实说是 mock 驱动。
    核心意图（mock SA 不算已验证）不变。
    """
    from app.hal import MockSignalAnalyzer

    hal, saved = _swap_sa(MockSignalAnalyzer("mock-sa", {"model": "Mock"}))
    try:
        result = await ReferenceExecutor().execute(_ctx(db, lab))
    finally:
        hal.drivers.clear()
        hal.drivers.update(saved)
    m = result.measurements or {}
    assert m["measurement_source"] == "hal_signal_analyzer_mock"
    assert m["trp_verified"] is False, "mock SA must not count as verified"
    assert any("未验证" in w for w in (result.warnings or [])), result.warnings


@pytest.mark.asyncio
async def test_real_sa_trp_verified(db, lab):
    hal, saved = _swap_sa(_RealLikeSA())
    try:
        result = await ReferenceExecutor().execute(_ctx(db, lab))
    finally:
        hal.drivers.clear()
        hal.drivers.update(saved)
    m = result.measurements or {}
    assert m["measurement_source"] == "hal_signal_analyzer"
    assert m["trp_verified"] is True
    assert not any("未验证" in w for w in (result.warnings or [])), result.warnings


@pytest.mark.asyncio
async def test_calibration_bypass_skips_reference_without_touching_sa(db, lab):
    sa = _RecordingSA()
    hal, saved = _swap_sa(sa)
    try:
        result = await ReferenceExecutor().execute(
            _ctx(db, lab, diagnostic=True)
        )
    finally:
        hal.drivers.clear()
        hal.drivers.update(saved)

    assert result.status == StepExecutionStatus.SKIPPED
    assert sa.calls == []
    assert "measured_trp_dbm" not in (result.measurements or {})
    assert "compensation_factor_db" not in (result.measurements or {})


@pytest.mark.asyncio
async def test_reference_measurement_failure_does_not_persist_numeric_trp(db, lab):
    hal, saved = _swap_sa(_FailedPowerSA())
    try:
        result = await ReferenceExecutor().execute(_ctx(db, lab))
    finally:
        hal.drivers.clear()
        hal.drivers.update(saved)

    assert result.status == StepExecutionStatus.FAILED
    assert "FSVA sweep timed out" in (result.error_message or "")
    assert "measured_trp_dbm" not in (result.measurements or {})
    assert "compensation_factor_db" not in (result.measurements or {})
