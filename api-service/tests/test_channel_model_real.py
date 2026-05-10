"""Channel-model validation real-measurement tests (A2-1, 3GPP TR 38.151 § 7.3).

Pin the SA-driver acquisition path that replaced mock-only PDP / Doppler.
Covers:
  - run_temporal_calibration(use_mock=False) → SA.measure_pdp called, RMS
    delay computed from real PDP.
  - run_doppler_calibration(use_mock=False) → SA.measure_doppler_spectrum
    called, correlation vs Jakes reference.
  - Mock SignalAnalyzer's new methods (measure_pdp / measure_doppler_spectrum
    / capture_iq) return shapes the service expects.
  - Missing SA driver raises actionable error.

Mock path is already covered by test_channel_calibration.py — this file
targets the new async + driver-driven path.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.services.channel_calibration_service import ChannelCalibrationService


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


def _patched_hal(monkeypatch, *, sa=None):
    fake_hal = MagicMock()
    fake_hal.drivers = {}
    if sa is not None:
        fake_hal.drivers["signalAnalyzer"] = sa
    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service", lambda: fake_hal
    )


# ============================================================================
# Mock SA driver primitives (HAL extension)
# ============================================================================

class TestMockSignalAnalyzerExtensions:
    """The Mock SA must implement measure_pdp / measure_doppler_spectrum /
    capture_iq so dev environments can exercise channel-model validation
    without hardware."""

    @pytest.mark.asyncio
    async def test_mock_measure_pdp_returns_normalized_clusters(self):
        sa = MockSignalAnalyzer("sa-test", {})
        await sa.connect()
        delays, powers = await sa.measure_pdp(
            center_freq_hz=3.5e9, max_delay_ns=1000.0, resolution_ns=10.0,
        )
        assert len(delays) == 100
        assert len(powers) == 100
        # Peak normalized to 0 dB
        assert max(powers) == pytest.approx(0.0, abs=0.01)
        # Cluster structure: should have a peak near 0 ns (cluster #1)
        peak_idx = powers.index(max(powers))
        assert delays[peak_idx] < 100  # peak in first 10 bins (0 ns cluster)

    @pytest.mark.asyncio
    async def test_mock_measure_doppler_spectrum_jakes_shape(self):
        sa = MockSignalAnalyzer("sa-test", {})
        await sa.connect()
        freqs, powers = await sa.measure_doppler_spectrum(
            center_freq_hz=3.5e9, max_doppler_hz=200.0, num_bins=128,
        )
        assert len(freqs) == 128
        assert len(powers) == 128
        # Symmetric span around DC
        assert freqs[0] == pytest.approx(-200.0, abs=1e-6)
        assert freqs[-1] == pytest.approx(200.0, abs=1.0)
        # U-shape: power at edges (near ±f_d) higher than at DC
        # Account for noise — check edge avg vs center avg
        edge_power = (powers[5] + powers[-6]) / 2.0  # 5 bins in from edges
        center_power = powers[64]  # at DC
        assert edge_power > center_power - 5.0  # noise tolerance

    @pytest.mark.asyncio
    async def test_mock_capture_iq_returns_paired_lists(self):
        sa = MockSignalAnalyzer("sa-test", {})
        await sa.connect()
        i, q = await sa.capture_iq(
            center_freq_hz=3.5e9, sample_rate_hz=10e6, num_samples=1024,
        )
        assert len(i) == 1024
        assert len(q) == 1024


# ============================================================================
# Service: real path acquisition
# ============================================================================

class TestRunTemporalCalibrationReal:
    """run_temporal_calibration(use_mock=False) drives SA.measure_pdp."""

    @pytest.mark.asyncio
    async def test_real_path_calls_sa_measure_pdp(self, db, monkeypatch):
        sa = MagicMock()
        # Fabricate a PDP with peak at delay=200 ns (single cluster)
        delays = [i * 10.0 for i in range(100)]  # 0..990 ns
        powers_db = [-30.0] * 100
        powers_db[20] = 0.0  # peak at 200 ns
        sa.measure_pdp = AsyncMock(return_value=(delays, powers_db))
        _patched_hal(monkeypatch, sa=sa)

        svc = ChannelCalibrationService(db)
        cal = await svc.run_temporal_calibration(
            scenario_type="UMa",
            scenario_condition="LOS",
            fc_ghz=3.5,
            calibrated_by="test",
            use_mock=False,
        )
        sa.measure_pdp.assert_awaited_once()
        # Frequency translated to Hz
        assert sa.measure_pdp.await_args.kwargs["center_freq_hz"] == pytest.approx(3.5e9)
        # PDP stored in calibration record
        assert cal.measured_pdp is not None
        assert len(cal.measured_pdp["delay_bins_ns"]) == 100
        assert cal.measured_rms_delay_spread_ns is not None

    @pytest.mark.asyncio
    async def test_real_path_no_sa_driver_raises(self, db, monkeypatch):
        _patched_hal(monkeypatch)  # no sa driver
        svc = ChannelCalibrationService(db)
        with pytest.raises(RuntimeError, match="signalAnalyzer"):
            await svc.run_temporal_calibration(
                scenario_type="UMa",
                scenario_condition="LOS",
                fc_ghz=3.5,
                calibrated_by="test",
                use_mock=False,
            )


class TestRunDopplerCalibrationReal:
    """run_doppler_calibration(use_mock=False) drives SA.measure_doppler_spectrum."""

    @pytest.mark.asyncio
    async def test_real_path_calls_sa_doppler(self, db, monkeypatch):
        sa = MagicMock()
        # Reference spectrum length comes from generate_classical_doppler_spectrum;
        # default is 100 bins for 120 km/h @ 3.5 GHz. Provide a U-shape with
        # varied power so Pearson correlation is well-defined.
        n = 100
        # U-shape: |f| / max → ranges 0..1
        freqs = [(-1 + 2 * i / (n - 1)) for i in range(n)]
        powers = [(-10.0 + 10.0 * abs(f)) for f in freqs]  # -10 dB at center, 0 at edges
        sa.measure_doppler_spectrum = AsyncMock(return_value=(freqs, powers))
        _patched_hal(monkeypatch, sa=sa)

        svc = ChannelCalibrationService(db)
        cal = await svc.run_doppler_calibration(
            velocity_kmh=120,
            fc_ghz=3.5,
            calibrated_by="test",
            use_mock=False,
        )
        sa.measure_doppler_spectrum.assert_awaited_once()
        assert cal.expected_doppler_hz > 0
        assert cal.measured_spectrum is not None
        assert cal.spectral_correlation is not None

    @pytest.mark.asyncio
    async def test_real_path_no_sa_driver_raises(self, db, monkeypatch):
        _patched_hal(monkeypatch)
        svc = ChannelCalibrationService(db)
        with pytest.raises(RuntimeError, match="signalAnalyzer"):
            await svc.run_doppler_calibration(
                velocity_kmh=120,
                fc_ghz=3.5,
                calibrated_by="test",
                use_mock=False,
            )


class TestSpatialCorrelationMock:
    """Mock path: theoretical correlation → synthesized h1/h2 samples, no driver."""

    @pytest.mark.asyncio
    async def test_spatial_correlation_mock_unchanged(self, db):
        svc = ChannelCalibrationService(db)
        cal = await svc.run_spatial_correlation_calibration(
            scenario_type="UMa",
            scenario_condition="NLOS",
            fc_ghz=3.5,
            antenna_spacing_wavelengths=0.5,
            calibrated_by="test",
        )
        assert cal.id is not None
        assert cal.antenna_spacing_wavelengths == 0.5
        assert cal.measured_correlation_magnitude is not None
        assert cal.validation_pass is not None


class TestSpatialCorrelationReal:
    """A2-2 real path: positioner moves SGH between two antenna positions,
    SA captures IQ at each, Pearson correlation vs theoretical Laplacian."""

    @pytest.mark.asyncio
    async def test_real_path_drives_positioner_twice_and_captures_iq(
        self, db, monkeypatch
    ):
        sa = MagicMock()
        # Two IQ captures: identical signal → high correlation
        i1 = [1.0, 2.0, 3.0, 4.0, 5.0] * 100
        q1 = [0.5, 1.5, 2.5, 3.5, 4.5] * 100
        sa.capture_iq = AsyncMock(side_effect=[(i1, q1), (i1, q1)])
        positioner = MagicMock()
        positioner.move_to = AsyncMock(return_value=True)
        _patched_hal(monkeypatch, sa=sa)

        # Inject positioner into the same fake hal
        from app.services.instrument_hal_service import get_hal_service as _orig
        hal = _orig()
        hal.drivers["positioner"] = positioner

        svc = ChannelCalibrationService(db)
        cal = await svc.run_spatial_correlation_calibration(
            scenario_type="UMa",
            scenario_condition="NLOS",
            fc_ghz=3.5,
            antenna_spacing_wavelengths=0.5,
            antenna_spacing_m=0.043,  # 0.5λ at 3.5 GHz
            calibrated_by="test",
            use_mock=False,
            num_iq_samples=500,
        )
        # Positioner moved twice (two antenna positions)
        assert positioner.move_to.await_count == 2
        first = positioner.move_to.await_args_list[0]
        second = positioner.move_to.await_args_list[1]
        assert first.kwargs["azimuth"] == pytest.approx(0.0)
        assert second.kwargs["azimuth"] == pytest.approx(4.3, abs=0.01)  # 0.043 m → 4.3 cm
        # SA captured IQ twice
        assert sa.capture_iq.await_count == 2
        # Identical IQ → magnitude correlation ≈ 1
        assert cal.measured_correlation_magnitude == pytest.approx(1.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_real_path_no_positioner_raises(self, db, monkeypatch):
        sa = MagicMock()
        sa.capture_iq = AsyncMock(return_value=([0.0] * 100, [0.0] * 100))
        _patched_hal(monkeypatch, sa=sa)  # no positioner

        svc = ChannelCalibrationService(db)
        with pytest.raises(RuntimeError, match="positioner"):
            await svc.run_spatial_correlation_calibration(
                scenario_type="UMa", scenario_condition="NLOS",
                fc_ghz=3.5, antenna_spacing_wavelengths=0.5,
                antenna_spacing_m=0.043,
                calibrated_by="test", use_mock=False,
            )

    @pytest.mark.asyncio
    async def test_real_path_no_antenna_spacing_raises(self, db, monkeypatch):
        sa = MagicMock()
        sa.capture_iq = AsyncMock(return_value=([0.0] * 100, [0.0] * 100))
        positioner = MagicMock()
        positioner.move_to = AsyncMock(return_value=True)

        # Patch HAL to include both
        fake_hal = MagicMock()
        fake_hal.drivers = {"signalAnalyzer": sa, "positioner": positioner}
        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service", lambda: fake_hal
        )

        svc = ChannelCalibrationService(db)
        with pytest.raises(RuntimeError, match="antenna_spacing_m"):
            await svc.run_spatial_correlation_calibration(
                scenario_type="UMa", scenario_condition="NLOS",
                fc_ghz=3.5, antenna_spacing_wavelengths=0.5,
                # antenna_spacing_m intentionally omitted
                calibrated_by="test", use_mock=False,
            )


class TestOrchestratorCdlDispatch:
    """CalibrationOrchestrator.execute_calibration_plan now dispatches
    CDL_MODEL_VALIDATION → channel_service triple (PDP + Doppler + Spatial).
    """

    @pytest.mark.asyncio
    async def test_cdl_validation_runs_three_subtests_and_aggregates(
        self, db, monkeypatch
    ):
        from app.models.chamber import ChamberType, create_chamber_from_preset
        from app.services.calibration_orchestrator import (
            CalibrationItem, CalibrationOrchestrator,
        )

        c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="CDL Lab")
        db.add(c)
        db.commit()
        db.refresh(c)

        orch = CalibrationOrchestrator(db, use_mock=True)
        results = await orch.execute_calibration_plan(
            chamber_id=c.id,
            items=[CalibrationItem.CDL_MODEL_VALIDATION],
            frequency_mhz=3500.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
            calibrated_by="test",
        )
        cdl_result = results["results"]["cdl_model_validation"]
        assert cdl_result["success"] is True
        # All 3 sub-cals persisted
        assert cdl_result["data"]["pdp_calibration_id"]
        assert cdl_result["data"]["doppler_calibration_id"]
        assert cdl_result["data"]["spatial_calibration_id"]
        assert "overall_pass" in cdl_result["data"]
        # Message names all 3 sub-tests
        assert "PDP" in cdl_result["message"]
        assert "Doppler" in cdl_result["message"]
        assert "Spatial" in cdl_result["message"]
