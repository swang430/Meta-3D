"""Probe pattern calibration real-measurement tests (A4).

Pin the CE+SA + positioner integration that replaced NotImplementedError in
PatternCalibrationService._real_pattern_measurements. Covers: positioner
moves to each (az, el), CE+SA tone fires per point, gain math = SA_rx -
CE_tx + FSPL - G_sgh - chain_correction, missing positioner driver raises
actionable error, positioner failure aborts scan.

Mock pattern path was already covered by tests/test_probe_calibration_service.py
— this file targets the real path specifically.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.channel_emulator import CalibrationToneCapability
from app.models.probe_calibration import ProbePattern
from app.schemas.probe_calibration import PolarizationType
from app.services.probe_calibration_service import PatternCalibrationService


TEST_CHAMBER_ID = UUID("cccccccc-0000-0000-0000-000000000053")


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


def _make_ce_d_path():
    ce = MagicMock()
    ce.get_calibration_tone_capabilities = MagicMock(
        return_value=[CalibrationToneCapability.INTERNAL_CW_GENERATOR]
    )
    ce.set_calibration_tone = AsyncMock(return_value=True)
    ce.stop_calibration_tone = AsyncMock(return_value=True)
    return ce


def _make_sa_constant(power_dbm=-85.0):
    sa = MagicMock()
    sa.setup_spectrum = AsyncMock(return_value=True)
    sa.measure_channel_power = AsyncMock(return_value=power_dbm)
    return sa


def _make_sa_gaussian_pattern(
    peak_dbm=-60.0, hpbw_deg=60.0, peak_az=180.0, peak_el=0.0,
    n_samples_per_point=5,
):
    """SA returns power that follows a Gaussian beam centered at (peak_az, peak_el).

    Default peak at az=180 (middle of 0..360 grid) so calculate_hpbw can find
    -3dB points on both sides of the peak (it doesn't wrap around 360°).

    n_samples_per_point: acquire_sa_power_via_ce_tone calls measure_channel_power
    5 times for averaging.
    """
    half_hpbw = hpbw_deg / 2.0
    # att_dB = 3 * (θ/half_hpbw)^2 → att = 3 dB exactly at θ = half_hpbw
    sa = MagicMock()
    sa.setup_spectrum = AsyncMock(return_value=True)

    call_counter = {"i": 0}
    angle_log: list[tuple[float, float]] = []

    def _power(*_args, **_kwargs):
        idx = call_counter["i"] // n_samples_per_point
        call_counter["i"] += 1
        if idx >= len(angle_log):
            return peak_dbm
        az, el = angle_log[idx]
        az_diff = abs(az - peak_az)
        # Wrap az_diff to [0, 180]
        az_diff = min(az_diff, 360.0 - az_diff)
        el_diff = abs(el - peak_el)
        att_db = 3.0 * (
            (az_diff / half_hpbw) ** 2
            + (el_diff / half_hpbw) ** 2
        )
        return peak_dbm - float(att_db)

    sa.measure_channel_power = AsyncMock(side_effect=_power)
    return sa, angle_log


def _make_positioner(*, move_ok=True, log=None):
    pos = MagicMock()
    if log is None:
        async def _move(azimuth, elevation):
            return move_ok
        pos.move_to = AsyncMock(side_effect=_move)
    else:
        async def _move(azimuth, elevation):
            log.append((float(azimuth), float(elevation)))
            return move_ok
        pos.move_to = AsyncMock(side_effect=_move)
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
# Real pattern measurement tests
# ============================================================================

class TestRealPatternMeasurement:

    @pytest.mark.asyncio
    async def test_drives_positioner_per_grid_point(self, db, monkeypatch):
        """4 az × 2 el = 8 grid points → 8 positioner moves + 8 CE bursts."""
        ce = _make_ce_d_path()
        sa = _make_sa_constant(power_dbm=-85.0)
        pos = _make_positioner()
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = PatternCalibrationService()
        result = await svc.execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=90.0,    # 4 points: 0, 90, 180, 270
            elevation_step_deg=180.0,  # 2 points: 0, 180
            measurement_distance_m=3.0,
            ce_port="B1.1",
            calibrated_by="test",
            use_mock=False,
        )
        assert result.success, result.message
        assert pos.move_to.await_count == 8
        assert ce.set_calibration_tone.await_count == 8

        # ce_port threaded through
        for call in ce.set_calibration_tone.await_args_list:
            assert call.kwargs.get("ce_port") == "B1.1"

        # Persisted record
        cal = db.query(ProbePattern).filter_by(probe_id=0).one()
        assert len(cal.gain_pattern_dbi) == 8
        assert cal.frequency_mhz == 3500.0

    @pytest.mark.asyncio
    async def test_cleanup_warning_reaches_pattern_result(self, db, monkeypatch):
        ce = _make_ce_d_path()
        ce.stop_calibration_tone = AsyncMock(return_value=False)
        sa = _make_sa_constant(power_dbm=-85.0)
        pos = _make_positioner()
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        result = await PatternCalibrationService().execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=360.0,
            elevation_step_deg=181.0,
            calibrated_by="test",
            use_mock=False,
        )

        assert result.success
        assert any("pattern probe 0 V" in warning for warning in result.warnings)
        assert any("stop_calibration_tone" in warning for warning in result.warnings)

    @pytest.mark.asyncio
    async def test_gain_math_matches_formula(self, db, monkeypatch):
        """With constant SA power, gain_dbi = sa_dbm - ce_tx + FSPL - G_sgh - correction.
        For SA=-85, CE_tx=-20, d=3m, f=3500 MHz, G_sgh=10, correction=0:
          FSPL = 20*log10(3) + 20*log10(3500) - 27.55 ≈ 52.87 dB
          gain = -85 - (-20) + 52.87 - 10 - 0 = -22.13 dBi
        """
        ce = _make_ce_d_path()
        sa = _make_sa_constant(power_dbm=-85.0)
        pos = _make_positioner()
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = PatternCalibrationService()
        result = await svc.execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=180.0,    # 2 points
            elevation_step_deg=180.0,
            measurement_distance_m=3.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            chain_correction_db=0.0,
            ce_port="B1.1",
            calibrated_by="test",
            use_mock=False,
        )
        assert result.success
        cal = db.query(ProbePattern).filter_by(probe_id=0).one()
        # All 4 points should have ~the same gain (constant SA reading)
        expected_gain = -85.0 - (-20.0) + 52.87 - 10.0 - 0.0
        for g in cal.gain_pattern_dbi:
            assert g == pytest.approx(expected_gain, abs=0.1)

    @pytest.mark.asyncio
    async def test_chain_correction_subtracts_from_gain(self, db, monkeypatch):
        """chain_correction_db should subtract: caller passes 60 dB chain gain
        (PA + switch + cable end-to-end) → gain comes out 60 dB lower."""
        ce = _make_ce_d_path()
        sa = _make_sa_constant(power_dbm=-85.0)
        pos = _make_positioner()
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = PatternCalibrationService()
        await svc.execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[1],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=180.0,
            elevation_step_deg=180.0,
            measurement_distance_m=3.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            chain_correction_db=60.0,  # ← pretend chain has 60 dB end-to-end gain
            ce_port="B1.1",
            calibrated_by="test",
            use_mock=False,
        )
        cal = db.query(ProbePattern).filter_by(probe_id=1).one()
        # Without correction would be ~-22.13 dBi; with -60: ~-82.13 dBi
        for g in cal.gain_pattern_dbi:
            assert g == pytest.approx(-82.13, abs=0.1)

    @pytest.mark.asyncio
    async def test_no_positioner_driver_raises_actionable(self, db, monkeypatch):
        ce = _make_ce_d_path()
        sa = _make_sa_constant()
        _patched_hal(monkeypatch, ce=ce, sa=sa)  # no positioner

        svc = PatternCalibrationService()
        result = await svc.execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=180.0,
            elevation_step_deg=180.0,
            calibrated_by="test",
            use_mock=False,
        )
        assert result.success is False
        assert "positioner" in result.message.lower()

    @pytest.mark.asyncio
    async def test_positioner_failure_aborts_scan(self, db, monkeypatch):
        ce = _make_ce_d_path()
        sa = _make_sa_constant()
        pos = _make_positioner(move_ok=False)
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = PatternCalibrationService()
        result = await svc.execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=180.0,
            elevation_step_deg=180.0,
            calibrated_by="test",
            use_mock=False,
        )
        assert result.success is False
        assert "move_to" in result.message
        # CE tone must NOT have fired (we'd be measuring at unknown angle)
        ce.set_calibration_tone.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_grid_ordering_elevation_outer_azimuth_inner(
        self, db, monkeypatch
    ):
        """Match mock data ordering: elev outer loop, az inner loop. Means peak
        / HPBW math downstream uses the same flat-index → (el_idx, az_idx)."""
        move_log: list[tuple[float, float]] = []
        ce = _make_ce_d_path()
        sa = _make_sa_constant()
        pos = _make_positioner(log=move_log)
        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = PatternCalibrationService()
        await svc.execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=90.0,    # 4 points
            elevation_step_deg=90.0,   # 3 points: 0, 90, 180
            calibrated_by="test",
            use_mock=False,
        )
        # First 4 calls share elevation=0, az walks 0/90/180/270
        assert move_log[0] == (0.0, 0.0)
        assert move_log[1] == (90.0, 0.0)
        assert move_log[2] == (180.0, 0.0)
        assert move_log[3] == (270.0, 0.0)
        # Then elevation=90, az walks again
        assert move_log[4] == (0.0, 90.0)
        assert move_log[7] == (270.0, 90.0)

    @pytest.mark.asyncio
    async def test_gaussian_beam_recovers_peak_and_hpbw(self, db, monkeypatch):
        """SA returns Gaussian beam centered at (180, 0) with HPBW ~60°.

        Peak placed mid-array (az=180) so calculate_hpbw can find -3 dB on
        both sides — it's a 1D scan, doesn't wrap around 360°. Verify
        peak_azimuth ≈ 180 ± step, hpbw_azimuth_deg ≈ 60° (within tolerance).
        """
        ce = _make_ce_d_path()
        sa, angle_log = _make_sa_gaussian_pattern(
            peak_dbm=-60.0, hpbw_deg=60.0, peak_az=180.0,
        )
        pos = _make_positioner()
        # Wire angle log: positioner.move_to populates angle_log so SA knows
        # which (az, el) we're at. Order of mock side-effects: positioner first,
        # then SA acquires (5x), positioner again, etc.
        async def _move_logging(azimuth, elevation):
            angle_log.append((float(azimuth), float(elevation)))
            return True
        pos.move_to = AsyncMock(side_effect=_move_logging)

        _patched_hal(monkeypatch, ce=ce, sa=sa, positioner=pos)

        svc = PatternCalibrationService()
        # 24 az pts × 1 el pt for a clean 1D azimuth pattern
        result = await svc.execute_pattern_calibration(
            db=db,
            chamber_id=TEST_CHAMBER_ID,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500.0,
            azimuth_step_deg=15.0,    # 24 az points: 0, 15, ..., 345
            elevation_step_deg=180.0,  # 1 effective el point at 0 boresight
            measurement_distance_m=3.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            ce_port="B1.1",
            calibrated_by="test",
            use_mock=False,
        )
        assert result.success
        cal = db.query(ProbePattern).filter_by(probe_id=0).one()
        # Peak should land at az=180 (within 1 step of 15° resolution)
        assert cal.peak_azimuth_deg == pytest.approx(180.0, abs=15.1)
        # HPBW close to 60° (interpolated -3 dB search, tolerance ±15°)
        assert cal.hpbw_azimuth_deg is not None
        assert 45.0 <= cal.hpbw_azimuth_deg <= 75.0
