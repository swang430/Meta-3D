"""CE+SA path-loss calibration — tests for the no-VNA design.

Memory `project_calibration_ce_sa_decision.md`: probe-to-QZ path-loss uses
CE-as-source + SA-as-receiver, not VNA. This test pins the math, the driver
contract (D path: set_calibration_tone / stop_calibration_tone; B path:
set_passthrough_mode / clear_passthrough_mode + upstream SG.set_cw / start_tx
/ stop_tx; common: SA.measure_channel_power), the failure modes (missing CE
/ SA, tone setup fail, finally-stop, missing upstream source on B path), and
the chamber-flag dispatch (cable_sgh_to_sa_loss_db = None → legacy VNA fallback).

The two CE-side paths (D = CE-internal CW gen, B = SG/BSE upstream + CE
passthrough) are dispatched by ChannelEmulatorDriver.get_calibration_tone_capabilities():
PROPSIM with Internal Interference Generator option goes D, anything else
falls back to B.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.channel_emulator import CalibrationToneCapability
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


def _patched_hal(monkeypatch, ce=None, sa=None, sg=None, bse=None, rf_switch=None):
    """Replace path_loss_service's HAL lookup with stubbed drivers.

    sg / bse are the optional upstream sources for the B (passthrough) path —
    omit them to test the failure mode where a PASSTHROUGH_ONLY CE has nothing
    to drive it.

    rf_switch optional: omit to simulate fixed-cabling sites (CAICT-Lab-1
    style) where no relay matrix exists — service must skip routing silently.
    """
    fake_hal = MagicMock()
    fake_hal.drivers = {}
    if ce is not None:
        fake_hal.drivers["channelEmulator"] = ce
    if sa is not None:
        fake_hal.drivers["signalAnalyzer"] = sa
    if sg is not None:
        fake_hal.drivers["signalGenerator"] = sg
    if bse is not None:
        fake_hal.drivers["baseStation"] = bse
    if rf_switch is not None:
        fake_hal.drivers["rfSwitch"] = rf_switch
    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service", lambda: fake_hal
    )


def _make_rf_switch(*, set_path_ok=True):
    sw = MagicMock()
    sw.set_mapped_path = AsyncMock(return_value=set_path_ok)
    return sw


def _make_ce(caps, *, internal_ok=True, passthrough_ok=True):
    """Build a MagicMock CE that declares `caps` and stubs both paths' SCPI.

    `caps` is a list of CalibrationToneCapability — controls dispatch.
    internal_ok / passthrough_ok flip the corresponding driver returns to
    False so we can exercise mid-flight failure handling without conflating
    the two paths.
    """
    ce = MagicMock()
    # capabilities is a sync method, not async — the abstract returns a list
    ce.get_calibration_tone_capabilities = MagicMock(return_value=list(caps))
    # D path stubs
    ce.set_calibration_tone = AsyncMock(return_value=internal_ok)
    ce.stop_calibration_tone = AsyncMock(return_value=True)
    # B path stubs
    ce.set_passthrough_mode = AsyncMock(return_value=passthrough_ok)
    ce.clear_passthrough_mode = AsyncMock(return_value=True)
    return ce


def _make_sg(*, set_cw_ok=True, start_ok=True):
    sg = MagicMock()
    sg.set_cw = AsyncMock(return_value=set_cw_ok)
    sg.start_tx = AsyncMock(return_value=start_ok)
    sg.stop_tx = AsyncMock(return_value=True)
    return sg


class TestCeSaMeasurement:
    """Unit tests for _real_path_loss_measurement_via_ce_sa — D path (CE
    declares INTERNAL_CW_GENERATOR, single-instrument tone source).
    """

    @pytest.mark.asyncio
    async def test_happy_path_math(self, db, monkeypatch):
        """CE_TX -20 dBm, SA reads -85 dBm steady; G_sgh=10, G_probe=8,
        cable=1.5 → path_loss = -20 - (-85) + 10 + 8 - 1.5 = 81.5 dB."""
        ce = _make_ce([CalibrationToneCapability.INTERNAL_CW_GENERATOR])
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
        ce = _make_ce([CalibrationToneCapability.INTERNAL_CW_GENERATOR])
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
        ce = _make_ce([CalibrationToneCapability.INTERNAL_CW_GENERATOR])
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
        ce = _make_ce(
            [CalibrationToneCapability.INTERNAL_CW_GENERATOR], internal_ok=False,
        )
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


class TestPassthroughBPath:
    """B path: CE declares only PASSTHROUGH_ONLY → service must drive an
    upstream SG.set_cw + start_tx + (later) stop_tx + ce.clear_passthrough."""

    @pytest.mark.asyncio
    async def test_passthrough_happy_path(self, db, monkeypatch):
        """Same math as D path (SG output = CE output, 0 dB passthrough),
        but driver calls hit set_passthrough_mode + SG.set_cw / start_tx
        instead of CE.set_calibration_tone."""
        ce = _make_ce([CalibrationToneCapability.PASSTHROUGH_ONLY])
        sg = _make_sg()
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa, sg=sg)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        m = await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=7,
            polarization=PolarizationType.H,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
        )
        # Same algebra: -20 - (-85) + 10 + 8 - 1.5 = 81.5 dB
        assert m.path_loss_db == pytest.approx(81.5, abs=0.01)
        assert m.polarization == "H"

        # D path SCPI must NOT be touched
        ce.set_calibration_tone.assert_not_awaited()
        ce.stop_calibration_tone.assert_not_awaited()
        # B path SCPI in the right order
        ce.set_passthrough_mode.assert_awaited_once()
        sg.set_cw.assert_awaited_once()
        cw_args, _ = sg.set_cw.call_args
        assert cw_args[0] == pytest.approx(3500e6)
        assert cw_args[1] == pytest.approx(-20.0)
        sg.start_tx.assert_awaited_once()
        # Cleanup: stop_tx + clear_passthrough always run, even on success
        sg.stop_tx.assert_awaited_once()
        ce.clear_passthrough_mode.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passthrough_uses_bse_when_only_bse_present(self, db, monkeypatch):
        """B path with only baseStation bound: BSE drives CW (it implements
        set_cw / start_tx / stop_tx for testmode CW emission)."""
        ce = _make_ce([CalibrationToneCapability.PASSTHROUGH_ONLY])
        bse = _make_sg()  # same shape as SG — set_cw/start_tx/stop_tx
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa, bse=bse)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        m = await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=1,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
        )
        assert isinstance(m, PathLossMeasurement)
        bse.set_cw.assert_awaited_once()
        bse.stop_tx.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passthrough_prefers_bse_over_sg_when_both_present(
        self, db, monkeypatch
    ):
        """When both BSE and SG bound: must pick BSE (it's the production-time
        upstream source, so calibration path stays identical to test path).
        SG must NOT be touched."""
        ce = _make_ce([CalibrationToneCapability.PASSTHROUGH_ONLY])
        bse = _make_sg()
        sg = _make_sg()
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa, bse=bse, sg=sg)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=1,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
        )
        bse.set_cw.assert_awaited_once()
        bse.start_tx.assert_awaited_once()
        bse.stop_tx.assert_awaited_once()
        # SG present but unused — keeps cal/test path identical
        sg.set_cw.assert_not_awaited()
        sg.start_tx.assert_not_awaited()
        sg.stop_tx.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passthrough_without_upstream_source_raises(self, db, monkeypatch):
        """PASSTHROUGH_ONLY CE with no SG and no BSE → must fail loudly with
        actionable error, never silently proceed."""
        ce = _make_ce([CalibrationToneCapability.PASSTHROUGH_ONLY])
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa)  # no sg, no bse

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        with pytest.raises(RuntimeError, match="PASSTHROUGH_ONLY"):
            await svc._real_path_loss_measurement_via_ce_sa(
                probe_id=1,
                polarization=PolarizationType.V,
                frequency_mhz=3500.0,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=10.0,
                probe_gain_dbi=8.0,
                cable_sgh_to_sa_loss_db=1.5,
            )
        # Neither path was touched
        ce.set_calibration_tone.assert_not_awaited()
        ce.set_passthrough_mode.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passthrough_stop_tx_called_when_sa_fails(self, db, monkeypatch):
        """SG started → SA setup fails → SG.stop_tx + ce.clear_passthrough
        must STILL run (no leaking RF on the bench)."""
        ce = _make_ce([CalibrationToneCapability.PASSTHROUGH_ONLY])
        sg = _make_sg()
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=False)  # ← fails after SG running
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa, sg=sg)

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
        sg.start_tx.assert_awaited_once()
        sg.stop_tx.assert_awaited_once()  # critical: RF off
        ce.clear_passthrough_mode.assert_awaited_once()  # critical: passthrough off

    @pytest.mark.asyncio
    async def test_dispatch_prefers_internal_when_both_caps_declared(
        self, db, monkeypatch
    ):
        """When CE declares BOTH caps, service must prefer D (single-instrument
        is simpler / one less failure mode), NOT touch SG even if bound."""
        ce = _make_ce([
            CalibrationToneCapability.INTERNAL_CW_GENERATOR,
            CalibrationToneCapability.PASSTHROUGH_ONLY,
        ])
        sg = _make_sg()
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa, sg=sg)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=1,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
        )
        # D was used, B was not
        ce.set_calibration_tone.assert_awaited_once()
        ce.set_passthrough_mode.assert_not_awaited()
        sg.set_cw.assert_not_awaited()


class TestSwitchAutoRouting:
    """C1: when caller passes route_target (typically RFChainSpec.chain_id),
    service must drive rfSwitch.set_mapped_path. Three regimes:
      - rfSwitch driver bound       → set_mapped_path called with chain_id
      - no rfSwitch driver bound    → fixed cabling, skip silently (CAICT-Lab-1)
      - set_mapped_path returns False → loud RuntimeError, don't measure on
                                        the wrong probe
    """

    @pytest.mark.asyncio
    async def test_route_target_drives_switch_when_driver_bound(
        self, db, monkeypatch
    ):
        """rfSwitch bound + route_target → set_mapped_path called once with the
        chain_id BEFORE the CE tone goes on (so the right probe is energized).
        """
        ce = _make_ce([CalibrationToneCapability.INTERNAL_CW_GENERATOR])
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        sw = _make_rf_switch()
        _patched_hal(monkeypatch, ce=ce, sa=sa, rf_switch=sw)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=5,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
            ce_port="B1.1",
            route_target="conn-42",
        )
        sw.set_mapped_path.assert_awaited_once_with("conn-42")
        # ce_port must thread through to set_calibration_tone (PROPSIM SCPI
        # OUTPut:INTERFerence:ADD <ce_port>, ... requires it).
        ce.set_calibration_tone.assert_awaited_once()
        _, kwargs = ce.set_calibration_tone.call_args
        assert kwargs.get("ce_port") == "B1.1"

    @pytest.mark.asyncio
    async def test_no_switch_driver_means_fixed_cabling_skip_silently(
        self, db, monkeypatch
    ):
        """Fixed-cabling site (CAICT-Lab-1): no rfSwitch driver bound. Service
        must NOT raise — every CE port is permanently wired to one probe, so
        ce_port selection alone routes the signal."""
        ce = _make_ce([CalibrationToneCapability.INTERNAL_CW_GENERATOR])
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa)  # ← no rf_switch

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        m = await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=5,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
            ce_port="B1.1",
            route_target="conn-42",  # given but no driver → no-op
        )
        assert m.path_loss_db == pytest.approx(81.5, abs=0.01)
        # Measurement still went through; ce_port still threaded.
        ce.set_calibration_tone.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_switch_set_mapped_path_failure_raises(
        self, db, monkeypatch
    ):
        """rfSwitch can't reach the requested chain → must abort BEFORE turning
        on CE tone (otherwise we'd measure the wrong probe and silently corrupt
        the calibration cert)."""
        ce = _make_ce([CalibrationToneCapability.INTERNAL_CW_GENERATOR])
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        sw = _make_rf_switch(set_path_ok=False)  # ← can't route
        _patched_hal(monkeypatch, ce=ce, sa=sa, rf_switch=sw)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        with pytest.raises(RuntimeError, match="set_mapped_path.*returned False"):
            await svc._real_path_loss_measurement_via_ce_sa(
                probe_id=5,
                polarization=PolarizationType.V,
                frequency_mhz=3500.0,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=10.0,
                probe_gain_dbi=8.0,
                cable_sgh_to_sa_loss_db=1.5,
                ce_port="B1.1",
                route_target="conn-missing",
            )
        # Critical: CE tone must NOT have been turned on (would emit on wrong probe).
        ce.set_calibration_tone.assert_not_awaited()
        ce.set_passthrough_mode.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_route_target_warns_and_proceeds(self, db, monkeypatch):
        """Legacy chamber-keyed entry point doesn't supply route_target. Service
        must proceed (operator pre-routed manually) but log a warning."""
        ce = _make_ce([CalibrationToneCapability.INTERNAL_CW_GENERATOR])
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        sw = _make_rf_switch()  # bound, but should NOT be called
        _patched_hal(monkeypatch, ce=ce, sa=sa, rf_switch=sw)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=5,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
            # route_target intentionally omitted
        )
        # Without route_target we don't know what chain to route to —
        # don't touch the switch.
        sw.set_mapped_path.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passthrough_b_path_threads_ce_port_too(self, db, monkeypatch):
        """B path: ce_port must thread to set_passthrough_mode so the right
        OTA output port is the passthrough sink."""
        ce = _make_ce([CalibrationToneCapability.PASSTHROUGH_ONLY])
        bse = _make_sg()
        sa = MagicMock()
        sa.setup_spectrum = AsyncMock(return_value=True)
        sa.measure_channel_power = AsyncMock(return_value=-85.0)
        _patched_hal(monkeypatch, ce=ce, sa=sa, bse=bse)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        await svc._real_path_loss_measurement_via_ce_sa(
            probe_id=5,
            polarization=PolarizationType.V,
            frequency_mhz=3500.0,
            ce_tx_power_dbm=-20.0,
            sgh_gain_dbi=10.0,
            probe_gain_dbi=8.0,
            cable_sgh_to_sa_loss_db=1.5,
            ce_port="B2.3",
        )
        ce.set_passthrough_mode.assert_awaited_once()
        _, kwargs = ce.set_passthrough_mode.call_args
        assert kwargs.get("ce_port") == "B2.3"


class TestCapabilityGating:
    """A CE driver that declares no capabilities at all must be rejected with
    a clear error — silent fall-through to either path is the worst outcome."""

    @pytest.mark.asyncio
    async def test_empty_capabilities_raises(self, db, monkeypatch):
        ce = _make_ce([])  # ← no caps declared
        sa = MagicMock()
        _patched_hal(monkeypatch, ce=ce, sa=sa)

        svc = ProbePathLossCalibrationService(db, use_mock=False)
        with pytest.raises(RuntimeError, match="no calibration-tone capabilities"):
            await svc._real_path_loss_measurement_via_ce_sa(
                probe_id=1,
                polarization=PolarizationType.V,
                frequency_mhz=3500.0,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=10.0,
                probe_gain_dbi=8.0,
                cable_sgh_to_sa_loss_db=1.5,
            )


class TestMockCeCalibrationTone:
    """The Mock CE must implement BOTH paths so dev environments and unit
    tests can cover the full dispatch matrix without hardware."""

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

    @pytest.mark.asyncio
    async def test_mock_ce_supports_passthrough_path(self):
        from app.hal.channel_emulator import MockChannelEmulator

        ce = MockChannelEmulator("ce-test", {})
        await ce.connect()
        ok = await ce.set_passthrough_mode(ce_port="B1.1", ce_input_port="A1")
        assert ok is True
        assert ce._passthrough_active is True
        assert ce._passthrough_out_port == "B1.1"
        assert ce._passthrough_in_port == "A1"

        ok = await ce.clear_passthrough_mode()
        assert ok is True
        assert ce._passthrough_active is False

    def test_mock_ce_declares_both_caps(self):
        from app.hal.channel_emulator import MockChannelEmulator

        ce = MockChannelEmulator("ce-test", {})
        caps = ce.get_calibration_tone_capabilities()
        assert CalibrationToneCapability.INTERNAL_CW_GENERATOR in caps
        assert CalibrationToneCapability.PASSTHROUGH_ONLY in caps


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
