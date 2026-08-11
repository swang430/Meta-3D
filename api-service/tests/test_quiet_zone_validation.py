"""Quiet-Zone validation tests (3GPP TR 38.151 § 7.2).

Pin two cert sub-tests:
  - **Field uniformity**: 5-point grid scan + std/range check vs ±1 dB spec.
    Verify positioner.move_to fires once per grid point, CE+SA tone fires
    once per point, persistence to QuietZoneCalibration captures grid + stats.
  - **XPD / cross-pol isolation**: V vs H probe power ratio vs 25 dB spec.
    Verify two CE+SA acquisitions (co-pol + cross-pol), XPD math = co - cross.

Also pin the failure paths: positioner unbound, positioner.move_to False,
chamber not found, threshold breach (FAIL but record persists).
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
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.schemas.probe_calibration import PolarizationType
from app.services.quiet_zone_validation_service import (
    DEFAULT_SCAN_OFFSETS_CM,
    QZ_AMPLITUDE_THRESHOLD_DB,
    XPD_THRESHOLD_DB,
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
    """Mock path: synthetic uniform field → PASS, no driver wiring needed."""

    @pytest.mark.asyncio
    async def test_mock_returns_pass_with_5pt_grid(self, db, chamber):
        svc = QuietZoneValidationService(db, use_mock=True)
        np.random.seed(42)  # deterministic mock noise
        result = await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success
        assert result.data["field_uniformity_pass"] is True
        assert result.data["grid_points"] == 5  # default 5-point grid
        assert result.data["threshold_db"] == QZ_AMPLITUDE_THRESHOLD_DB

        # Persistence: a QuietZoneCalibration row exists, grid stored
        from uuid import UUID as _UUID
        cal = db.query(QuietZoneCalibration).filter_by(
            id=_UUID(result.data["calibration_id"])
        ).one()
        assert cal.validation_type == "field_uniformity"
        assert cal.validation_pass is True
        assert len(cal.grid_data) == 5
        assert cal.field_uniformity_db is not None  # range stored
        assert cal.measurement_method == "mock"


class TestFieldUniformityRealCeSa:
    """Real path: positioner moves to each grid point, CE+SA acquires power
    at each, std/range vs ±1 dB threshold."""

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
        assert result.success
        assert result.data["field_uniformity_pass"] is True
        # 5 grid points → 5 positioner moves + 5 CE tone bursts
        assert pos.move_to.await_count == 5
        assert ce.set_calibration_tone.await_count == 5

        # First move is to (0,0) (grid center)
        first_call = pos.move_to.await_args_list[0]
        assert first_call.kwargs["azimuth"] == 0.0
        assert first_call.kwargs["elevation"] == 0.0
        # Subsequent moves walk DEFAULT_SCAN_OFFSETS_CM
        called_offsets = {
            (call.kwargs["azimuth"], call.kwargs["elevation"])
            for call in pos.move_to.await_args_list
        }
        expected_offsets = {(x, y) for x, y, _ in DEFAULT_SCAN_OFFSETS_CM}
        assert called_offsets == expected_offsets

        # CE port threaded to driver (PROPSIM SCPI requires it)
        for call in ce.set_calibration_tone.await_args_list:
            assert call.kwargs.get("ce_port") == "B1.1"

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

        assert result.success
        assert any("grid point" in warning for warning in result.warnings)
        assert any("stop_calibration_tone" in warning for warning in result.warnings)

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
        assert result.success  # measurement completed, just FAILED spec
        assert result.data["field_uniformity_pass"] is False
        assert result.data["field_range_db"] >= 5.0  # got 10 dB range
        assert any("FAIL" in w for w in result.warnings)

        from uuid import UUID as _UUID
        cal = db.query(QuietZoneCalibration).filter_by(
            id=_UUID(result.data["calibration_id"])
        ).one()
        assert cal.validation_pass is False

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
        assert "positioner" in result.message.lower()

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
        assert "move_to" in result.message
        # CE tone must NOT have fired (we'd be measuring the wrong point)
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
# XPD / cross-pol isolation (§ 7.2.x)
# ============================================================================

class TestXpdValidation:
    """V vs H probe power ratio vs 25 dB spec (3GPP MIMO OTA)."""

    @pytest.mark.asyncio
    async def test_mock_xpd_passes_with_30db(self, db, chamber):
        np.random.seed(42)
        svc = QuietZoneValidationService(db, use_mock=True)
        result = await svc.run_xpd_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success
        assert result.data["xpd_pass"] is True
        assert result.data["xpd_db"] > XPD_THRESHOLD_DB
        assert result.data["threshold_db"] == XPD_THRESHOLD_DB

    @pytest.mark.asyncio
    async def test_real_xpd_two_acquisitions(self, db, chamber, monkeypatch):
        """Real path: two CE+SA acquisitions (co + cross), XPD = co - cross."""
        ce = _make_ce_d_path()
        # Co-pol -85 dBm, cross-pol -115 dBm → XPD = 30 dB
        powers = iter([
            -85.0, -85.0, -85.0, -85.0, -85.0,    # co-pol acquisition × 5 samples
            -115.0, -115.0, -115.0, -115.0, -115.0,  # cross-pol × 5
        ])
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(side_effect=lambda *_: next(powers))
        _patched_hal(monkeypatch, ce=ce, sa=sa)

        svc = QuietZoneValidationService(db, use_mock=False)
        result = await svc.run_xpd_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
            ce_port_co="B1.1",   # V probe ce_port
            ce_port_cross="B1.2",  # H probe ce_port
        )
        assert result.success
        assert result.data["xpd_db"] == pytest.approx(30.0, abs=0.01)
        assert result.data["xpd_pass"] is True
        # Two CE tone bursts (one per pol)
        assert ce.set_calibration_tone.await_count == 2
        ce_ports_used = [
            call.kwargs.get("ce_port")
            for call in ce.set_calibration_tone.await_args_list
        ]
        assert ce_ports_used == ["B1.1", "B1.2"]

    @pytest.mark.asyncio
    async def test_real_xpd_preserves_cleanup_warnings_from_both_acquisitions(
        self, db, chamber, monkeypatch
    ):
        ce = _make_ce_d_path()
        ce.stop_calibration_tone = AsyncMock(return_value=False)
        powers = iter([-85.0] * 5 + [-115.0] * 5)
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(side_effect=lambda *_: next(powers))
        _patched_hal(monkeypatch, ce=ce, sa=sa)

        result = await QuietZoneValidationService(
            db, use_mock=False
        ).run_xpd_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )

        assert result.success
        assert any("XPD co-pol" in warning for warning in result.warnings)
        assert any("XPD cross-pol" in warning for warning in result.warnings)

    @pytest.mark.asyncio
    async def test_real_xpd_below_threshold_records_fail(
        self, db, chamber, monkeypatch
    ):
        ce = _make_ce_d_path()
        # Co-pol -85, cross-pol -100 → XPD = 15 dB (below 25 dB spec)
        powers = iter([-85.0] * 5 + [-100.0] * 5)
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(side_effect=lambda *_: next(powers))
        _patched_hal(monkeypatch, ce=ce, sa=sa)

        svc = QuietZoneValidationService(db, use_mock=False)
        result = await svc.run_xpd_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        assert result.success  # measurement completed
        assert result.data["xpd_db"] == pytest.approx(15.0, abs=0.01)
        assert result.data["xpd_pass"] is False

        from uuid import UUID as _UUID
        cal = db.query(QuietZoneCalibration).filter_by(
            id=_UUID(result.data["calibration_id"])
        ).one()
        assert cal.validation_type == "probe_coupling"
        assert cal.coupling_pass is False


# ============================================================================
# Service helpers
# ============================================================================

class TestQzLookup:
    @pytest.mark.asyncio
    async def test_get_latest_validation_returns_most_recent(
        self, db, chamber
    ):
        svc = QuietZoneValidationService(db, use_mock=True)
        np.random.seed(1)
        await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3400.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        np.random.seed(2)
        result2 = await svc.run_field_uniformity_validation(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )
        latest = svc.get_latest_validation(chamber.id, "field_uniformity")
        assert latest is not None
        assert str(latest.id) == result2.data["calibration_id"]
        assert latest.frequency_mhz == 3500.0
