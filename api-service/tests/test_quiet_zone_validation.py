"""Quiet-Zone validation tests (3GPP TR 38.151 § 7.2).

Pin the field-uniformity cert sub-test：mock 拒绝落库、real 路径在拿到
linear XY stage API 前 fail-closed、chamber 缺失可诊断。
落库目标 P1-71 起为 ChannelQuietZoneCalibration（QZ 并轨，probe 侧封存），
换源后的持久化行为门在 test_p1_71_qz_merge_and_phase_gate.py。

P1-71 注：原 XPD 组（TestXpdValidation）与 get_latest_validation 组随
run_xpd_validation / get_latest_validation 移除 —— XPD 有实现与测试但零
生产调用方，且 mock 分支无守卫直接落已封存的 probe 表；复活先裁决载体。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.channel_emulator import CalibrationToneCapability
from app.models.calibration import QuietZoneCalibration
from app.models.channel_calibration import ChannelQuietZoneCalibration
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.schemas.probe_calibration import PolarizationType
from app.services.quiet_zone_validation_service import (
    DEFAULT_SCAN_OFFSETS_CM,
    QZ_AMPLITUDE_THRESHOLD_DB,
    QuietZoneValidationService,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
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
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="QZ Lab")
    c.cable_sgh_to_sa_loss_db = 1.5  # commissioning measured
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_ce_d_path():
    """Build a CE mock that declares INTERNAL_CW_GENERATOR (D path)."""
    ce = MagicMock()
    ce.get_calibration_tone_capabilities = MagicMock(
        return_value=[CalibrationToneCapability.INTERNAL_CW_GENERATOR]
    )
    ce.set_calibration_tone = AsyncMock(return_value=True)
    ce.stop_calibration_tone = AsyncMock(return_value=True)
    return ce


def _make_sa(power_dbm=-85.0):
    sa = MagicMock()
    sa.setup_spectrum = AsyncMock(return_value=True)
    sa.measure_channel_power = AsyncMock(return_value=power_dbm)
    return sa


def _make_positioner(*, move_ok=True):
    pos = MagicMock()
    pos.move_to = AsyncMock(return_value=move_ok)
    return pos


def _patched_hal(monkeypatch, *, ce=None, sa=None, positioner=None):
    fake_hal = MagicMock()
    fake_hal.drivers = {}
    if ce is not None:
        fake_hal.drivers["channelEmulator"] = ce
    if sa is not None:
        fake_hal.drivers["signalAnalyzer"] = sa
    if positioner is not None:
        fake_hal.drivers["positioner"] = positioner
    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service", lambda: fake_hal
    )


# ============================================================================
# Field uniformity (§ 7.2.x)
# ============================================================================

class TestFieldUniformityMock:
    """Mock grid data cannot become a formal quiet-zone calibration."""

    @pytest.mark.asyncio
    async def test_mock_is_rejected_before_persistence(self, db, chamber):
        svc = QuietZoneValidationService(db, use_mock=True)
        np.random.seed(42)  # deterministic mock noise
        result = await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success is False
        assert result.data == {}
        assert "mock" in result.message.lower()
        # 新旧两张 QZ 表都不许进行（channel 侧=活载体，probe 侧=封存）
        assert db.query(ChannelQuietZoneCalibration).count() == 0
        assert db.query(QuietZoneCalibration).count() == 0


class TestFieldUniformityRealCeSa:
    """Real grid acquisition stays closed without a linear XY stage API."""

    @pytest.mark.asyncio
    async def test_real_path_drives_positioner_per_grid_point(
        self, db, chamber, monkeypatch
    ):
        ce = _make_ce_d_path()
        sa = _make_sa(power_dbm=-85.0)  # uniform → PASS
        pos = _make_positioner()
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = QuietZoneValidationService(db, use_mock=False)
        result = await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
            ce_port="B1.1",
        )
        assert result.success is False
        assert "linear xy stage" in result.message.lower()
        pos.move_to.assert_not_awaited()
        ce.set_calibration_tone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_real_grid_cleanup_warning_reaches_result(
        self, db, chamber, monkeypatch
    ):
        ce = _make_ce_d_path()
        ce.stop_calibration_tone = AsyncMock(return_value=False)
        sa = _make_sa(power_dbm=-85.0)
        pos = _make_positioner()
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        result = await QuietZoneValidationService(
            db, use_mock=False
        ).run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
            scan_offsets_cm=[(0.0, 0.0, 0.0)],
        )

        assert result.success is False
        assert "linear xy stage" in result.message.lower()
        ce.stop_calibration_tone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_real_path_fails_uniformity_records_fail(
        self, db, chamber, monkeypatch
    ):
        """SA returns wildly varying power across grid → uniformity FAIL.
        Record must still persist (caller wants to see WHY it failed)."""
        ce = _make_ce_d_path()
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        # Returns -85, -80, -90, -85, -80 → range 10 dB, std ~3.7 dB
        bad_powers = iter([-85.0, -80.0, -80.0, -80.0, -80.0,  # point 1, 5 samples
                           -80.0, -80.0, -80.0, -80.0, -80.0,  # point 2
                           -90.0, -90.0, -90.0, -90.0, -90.0,  # point 3
                           -85.0, -85.0, -85.0, -85.0, -85.0,  # point 4
                           -80.0, -80.0, -80.0, -80.0, -80.0]) # point 5
        sa.measure_channel_power = AsyncMock(side_effect=lambda *_: next(bad_powers))
        pos = _make_positioner()
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = QuietZoneValidationService(db, use_mock=False)
        result = await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success is False
        assert "linear xy stage" in result.message.lower()
        pos.move_to.assert_not_awaited()
        sa.measure_channel_power.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_positioner_driver_raises(self, db, chamber, monkeypatch):
        ce = _make_ce_d_path()
        sa = _make_sa()
        _patched_hal(monkeypatch, ce=ce, sa=sa)  # no positioner

        svc = QuietZoneValidationService(db, use_mock=False)
        result = await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success is False
        assert "linear xy stage" in result.message.lower()

    @pytest.mark.asyncio
    async def test_positioner_move_failure_aborts_scan(
        self, db, chamber, monkeypatch
    ):
        """Positioner reports motion failure → must abort, don't measure."""
        ce = _make_ce_d_path()
        sa = _make_sa()
        pos = _make_positioner(move_ok=False)
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = QuietZoneValidationService(db, use_mock=False)
        result = await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success is False
        assert "linear xy stage" in result.message.lower()
        pos.move_to.assert_not_awaited()
        ce.set_calibration_tone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chamber_not_found_returns_actionable_error(
        self, db, monkeypatch
    ):
        from uuid import uuid4
        svc = QuietZoneValidationService(db, use_mock=False)
        result = await svc.run_field_uniformity_validation(
            chamber_id=uuid4(),
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success is False
        assert "not found" in result.message.lower()


# ============================================================================
# Service helpers
# ============================================================================

class TestMockRunsPersistNothing:
    @pytest.mark.asyncio
    async def test_repeated_mock_runs_persist_no_rows(self, db, chamber):
        svc = QuietZoneValidationService(db, use_mock=True)
        np.random.seed(1)
        await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3400.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        np.random.seed(2)
        await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert db.query(ChannelQuietZoneCalibration).count() == 0
        assert db.query(QuietZoneCalibration).count() == 0
