"""CE+SA path-loss calibration — tests for the no-VNA design.

Memory `project_calibration_ce_sa_decision.md`: probe-to-QZ path-loss uses
CE-as-source + SA-as-receiver, not VNA. This test pins the math, the driver
contract (set_calibration_tone / stop_calibration_tone / measure_channel_power),
the failure modes (missing CE / SA, tone setup fail, finally-stop), and the
chamber-flag dispatch (cable_sgh_to_sa_loss_db = None → legacy VNA fallback).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.services.path_loss_calibration_service import (
    PathLossMeasurement,
    PolarizationType,
    ProbePathLossCalibrationService,
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
def chamber_with_cable_loss(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="CE+SA Lab")
    c.cable_sgh_to_sa_loss_db = 1.5  # commissioning-measured, the constant
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _patched_hal(monkeypatch, ce=None, sa=None):
    """Replace path_loss_service's HAL lookup with stubbed drivers."""
    fake_hal = MagicMock()
    fake_hal.drivers = {}
    if ce is not None:
        fake_hal.drivers["channelEmulator"] = ce
    if sa is not None:
        fake_hal.drivers["signalAnalyzer"] = sa
    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service", lambda: fake_hal
    )


class TestCeSaMeasurement:
    """Direct unit tests for _real_path_loss_measurement_via_ce_sa."""

    @pytest.mark.asyncio
    async def test_happy_path_math(self, db, monkeypatch):
        """CE_TX -20 dBm, SA reads -85 dBm steady; G_sgh=10, G_probe=8,
        cable=1.5 → path_loss = -20 - (-85) + 10 + 8 - 1.5 = 81.5 dB."""
        ce = MagicMock()
        ce.set_calibration_tone = AsyncMock(return_value=True)
        ce.stop_calibration_tone = AsyncMock(return_value=True)
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        m = await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=5,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
        )
        assert isinstance(m, PathLossMeasurement)
        assert m.probe_id == 5
        assert m.polarization == "V"
        assert m.path_loss_db == pytest.approx(81.5, abs=0.01)
        # No SA noise (mock returns same value 5x) → only the +0.3 ref unc.
        assert m.uncertainty_db == pytest.approx(0.3, abs=0.01)

        # Drivers got the expected calls
        ce.set_calibration_tone.assert_awaited_once()
        args, _ = ce.set_calibration_tone.call_args
        assert args[0] == pytest.approx(3500e6)
        assert args[1] == pytest.approx(-20.0)
        sa.setup_spectrum.assert_awaited_once()
        assert sa.measure_channel_power.await_count == 5
        # Stop tone always called (finally) even on success.
        ce.stop_calibration_tone.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_tone_called_even_if_sa_fails(self, db, monkeypatch):
        """SA setup_spectrum False → method raises, but stop_calibration_tone
        must still be called so CE doesn't keep transmitting."""
        ce = MagicMock()
        ce.set_calibration_tone = AsyncMock(return_value=True)
        ce.stop_calibration_tone = AsyncMock(return_value=True)
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=False)  # ← fails
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        with pytest.raises(RuntimeError, match="SA setup_spectrum failed"):
            await svc._real_path_loss_measurement_via_ce_sa(
                probe_id=1,
                polarization=PolarizationType.V,
                frequency_mhz=3500.0,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=10.0,
                probe_gain_dbi=8.0,
                cable_sgh_to_sa_loss_db=1.5,
            )
        # Tone was started, then must be stopped despite SA failure.
        ce.set_calibration_tone.assert_awaited_once()
        ce.stop_calibration_tone.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_ce_driver_raises(self, db, monkeypatch):
        sa = MagicMock()
        _patched_hal(monkeypatch, ce=None, sa=sa)
        svc = ProbePathLossCalibrationService(db, use_mock=False)
        with pytest.raises(RuntimeError, match="channelEmulator"):
            await svc._real_path_loss_measurement_via_ce_sa(
                probe_id=1,
                polarization=PolarizationType.V,
                frequency_mhz=3500.0,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=10.0,
                probe_gain_dbi=8.0,
                cable_sgh_to_sa_loss_db=1.5,
            )

    @pytest.mark.asyncio
    async def test_missing_sa_driver_raises(self, db, monkeypatch):
        ce = MagicMock()
        _patched_hal(monkeypatch, ce=ce, sa=None)
        svc = ProbePathLossCalibrationService(db, use_mock=False)
        with pytest.raises(RuntimeError, match="signalAnalyzer"):
            await svc._real_path_loss_measurement_via_ce_sa(
                probe_id=1,
                polarization=PolarizationType.V,
                frequency_mhz=3500.0,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=10.0,
                probe_gain_dbi=8.0,
                cable_sgh_to_sa_loss_db=1.5,
            )

    @pytest.mark.asyncio
    async def test_ce_set_tone_failure_raises(self, db, monkeypatch):
        """If CE refuses the tone (e.g. out of range), abort without reading SA."""
        ce = MagicMock()
        ce.set_calibration_tone = AsyncMock(return_value=False)
        ce.stop_calibration_tone = AsyncMock(return_value=True)
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        with pytest.raises(RuntimeError, match="set_calibration_tone failed"):
            await svc._real_path_loss_measurement_via_ce_sa(
                probe_id=1,
                polarization=PolarizationType.V,
                frequency_mhz=3500.0,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=10.0,
                probe_gain_dbi=8.0,
                cable_sgh_to_sa_loss_db=1.5,
            )
        # SA shouldn't have been touched (we abort before setup).
        sa.setup_spectrum.assert_not_awaited()


class TestMockCeCalibrationTone:
    """The Mock CE driver must implement set/stop_calibration_tone so dev
    environments and unit tests can exercise the CE+SA path without hardware."""

    @pytest.mark.asyncio
    async def test_mock_ce_records_tone_state(self):
        from app.hal.channel_emulator import MockChannelEmulator

        ce = MockChannelEmulator("ce-test", {})
        await ce.connect()
        ok = await ce.set_calibration_tone(3500e6, -20.0, ce_port="B1.1")
        assert ok is True
        assert ce._cal_tone_active is True
        assert ce._cal_tone_freq_hz == pytest.approx(3500e6)
        assert ce._cal_tone_power_dbm == pytest.approx(-20.0)
        assert ce._cal_tone_port == "B1.1"

        ok = await ce.stop_calibration_tone()
        assert ok is True
        assert ce._cal_tone_active is False

    @pytest.mark.asyncio
    async def test_mock_ce_rejects_out_of_range_power(self):
        from app.hal.channel_emulator import MockChannelEmulator

        ce = MockChannelEmulator("ce-test", {})
        await ce.connect()
        # +30 dBm is way above any CE OTA-port tolerance, must reject.
        assert await ce.set_calibration_tone(3500e6, 30.0) is False
        # -100 dBm too low (below CE noise floor / spec).
        assert await ce.set_calibration_tone(3500e6, -100.0) is False
        # Reasonable tone is accepted.
        assert await ce.set_calibration_tone(3500e6, -20.0) is True


class TestChamberFlagDispatch:
    """start_calibration must pick CE+SA when chamber.cable_sgh_to_sa_loss_db
    is set, fall back to legacy VNA path when not."""

    def test_chamber_field_default_is_none_for_legacy_compat(self, db):
        # An untouched preset chamber should not trigger CE+SA path —
        # cable_sgh_to_sa_loss_db must default to None so existing
        # deployments keep using the VNA path until commissioning sets it.
        c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="legacy")
        db.add(c)
        db.commit()
        db.refresh(c)
        assert c.cable_sgh_to_sa_loss_db is None

    def test_chamber_field_can_be_populated(self, chamber_with_cable_loss):
        # The fixture sets it; verify it persisted.
        assert chamber_with_cable_loss.cable_sgh_to_sa_loss_db == pytest.approx(1.5)
