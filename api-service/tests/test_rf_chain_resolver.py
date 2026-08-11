"""P0: tests for the lab-profile + topology aware path-loss flow.

These tests cover:
- rf_chain_resolver: LabProfile → SwitchTopology → list of RFChainSpec
- ProbePathLossCalibrationService.start_calibration_for_lab_profile:
    iterates resolver chains, persists per-chain insertion loss in addition
    to the legacy per-probe aggregate.
- The cert exposes path_loss_db_by_rf_chain that measure.py can consume.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import (
    ChamberConfiguration,
    ChamberType,
    create_chamber_from_preset,
)
from app.models.lab_profile import LabProfile
from app.models.probe_calibration import ProbePathLossCalibration
from app.models.switch_topology import SwitchTopology
from app.services.calibration.rf_chain_resolver import (
    resolve_rf_chains,
)
from app.services.path_loss_calibration_service import (
    ProbePathLossCalibrationService,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def db_session():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def chamber(db_session):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P0 Chamber")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def topology_two_chains(db_session, chamber):
    """A minimal topology declaring 2 active chains in 'mimo_ota' mode.

    probe 0 V via connection conn_p0v with 0.5 dB cable loss
    probe 0 H via connection conn_p0h with 0.7 dB cable loss
    """
    topo = SwitchTopology(
        switch_category_id=uuid.uuid4(),  # not validated by FK in SQLite tests
        chamber_id=chamber.id,
        name="P0 Test Topology",
        version="1.0",
        nodes=[
            {"id": "ce_b1", "type": "ce_port", "label": "B1.1", "params": {}},
            {"id": "ce_b2", "type": "ce_port", "label": "B1.2", "params": {}},
            {"id": "probe_0_v", "type": "probe", "label": "Probe 0 V",
             "params": {"probe_id": 0, "polarization": "V"}},
            {"id": "probe_0_h", "type": "probe", "label": "Probe 0 H",
             "params": {"probe_id": 0, "polarization": "H"}},
        ],
        connections=[
            {"id": "conn_p0v", "source": "ce_b1", "target": "probe_0_v",
             "calibrated_loss_db": 0.5, "modes": ["mimo_ota"]},
            {"id": "conn_p0h", "source": "ce_b2", "target": "probe_0_h",
             "calibrated_loss_db": 0.7, "modes": ["mimo_ota"]},
        ],
        operating_modes=[
            {"id": "mimo_ota", "name": "MIMO OTA",
             "active_connections": ["conn_p0v", "conn_p0h"]},
        ],
        is_active=True,
    )
    db_session.add(topo)
    db_session.commit()
    db_session.refresh(topo)
    return topo


@pytest.fixture
def lab_profile(db_session, chamber, topology_two_chains):
    lab = LabProfile(
        name="P0-Test-Lab",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db_session.add(lab)
    db_session.commit()
    db_session.refresh(lab)
    return lab


class TestRFChainResolver:
    def test_resolves_two_chains_for_mimo_ota(self, db_session, lab_profile):
        result = resolve_rf_chains(db_session, lab_profile.id, "mimo_ota")
        assert result.success
        assert result.chamber_id == lab_profile.chamber_config_id
        assert len(result.chains) == 2

        chain_ids = {c.chain_id for c in result.chains}
        assert chain_ids == {"conn_p0v", "conn_p0h"}

        v_chain = result.chain_for(probe_id=0, polarization="V")
        assert v_chain is not None
        assert v_chain.cable_loss_db == 0.5

        h_chain = result.chain_for(probe_id=0, polarization="H")
        assert h_chain is not None
        assert h_chain.cable_loss_db == 0.7

    def test_unknown_lab_profile_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            resolve_rf_chains(db_session, uuid.uuid4(), "mimo_ota")

    def test_unknown_mode_returns_failure_with_warning(self, db_session, lab_profile):
        result = resolve_rf_chains(db_session, lab_profile.id, "trp_only")
        assert not result.success
        assert any("trp_only" in w for w in result.warnings)

    def test_lab_without_chamber_raises(self, db_session):
        lab = LabProfile(name="No-Chamber-Lab", is_active=True)
        db_session.add(lab)
        db_session.commit()
        with pytest.raises(ValueError, match="no chamber_config_id"):
            resolve_rf_chains(db_session, lab.id, "mimo_ota")


class TestPathLossForLabProfile:
    @pytest.mark.asyncio
    async def test_per_chain_breakdown_persisted(self, db_session, lab_profile):
        service = ProbePathLossCalibrationService(db_session, use_mock=True)
        result = await service.start_calibration_for_lab_profile(
            lab_profile_id=lab_profile.id,
            operating_mode="mimo_ota",
            frequency_mhz=3500.0,
            sgh_model="ETS-Lindgren 3164-06",
            sgh_gain_dbi=10.0,
            calibrated_by="pytest",
        )
        assert result.success, result.message
        assert result.data["num_chains"] == 2
        assert result.data["num_probes"] == 1  # both chains are probe 0

        cert = (
            db_session.query(ProbePathLossCalibration)
            .filter(ProbePathLossCalibration.id == uuid.UUID(result.data["calibration_id"]))
            .first()
        )
        assert cert is not None
        assert cert.lab_profile_id == lab_profile.id
        assert cert.operating_mode == "mimo_ota"
        assert cert.use_mock is True

        per_chain = cert.path_loss_db_by_rf_chain
        assert isinstance(per_chain, dict)
        assert set(per_chain.keys()) == {"conn_p0v", "conn_p0h"}

        v = per_chain["conn_p0v"]
        h = per_chain["conn_p0h"]
        assert v["probe_id"] == 0 and v["polarization"] == "V"
        assert h["probe_id"] == 0 and h["polarization"] == "H"
        # total = space + cable; with cable=0.5 vs 0.7, totals must differ.
        assert v["cable_loss_db"] == 0.5
        assert h["cable_loss_db"] == 0.7
        assert v["total_insertion_loss_db"] == pytest.approx(
            v["space_loss_db"] + 0.5, abs=1e-6
        )
        assert h["total_insertion_loss_db"] == pytest.approx(
            h["space_loss_db"] + 0.7, abs=1e-6
        )

    @pytest.mark.asyncio
    async def test_legacy_per_probe_aggregate_still_populated(self, db_session, lab_profile):
        service = ProbePathLossCalibrationService(db_session, use_mock=True)
        result = await service.start_calibration_for_lab_profile(
            lab_profile_id=lab_profile.id,
            operating_mode="mimo_ota",
            frequency_mhz=3500.0,
            sgh_model="SGH",
            sgh_gain_dbi=10.0,
            calibrated_by="pytest",
        )
        cert = (
            db_session.query(ProbePathLossCalibration)
            .filter(ProbePathLossCalibration.id == uuid.UUID(result.data["calibration_id"]))
            .first()
        )
        # measure.py's get_path_loss_for_probe still has to work for legacy callers.
        assert "0" in cert.probe_path_losses
        entry = cert.probe_path_losses["0"]
        assert entry["pol_v_db"] is not None
        assert entry["pol_h_db"] is not None

    @pytest.mark.asyncio
    async def test_missing_topology_returns_actionable_failure(self, db_session, chamber):
        lab = LabProfile(name="No-Topology-Lab", chamber_config_id=chamber.id, is_active=True)
        db_session.add(lab)
        db_session.commit()

        service = ProbePathLossCalibrationService(db_session, use_mock=True)
        result = await service.start_calibration_for_lab_profile(
            lab_profile_id=lab.id,
            operating_mode="mimo_ota",
            frequency_mhz=3500.0,
            sgh_model="SGH",
            sgh_gain_dbi=10.0,
            calibrated_by="pytest",
        )
        assert not result.success
        assert "Seed SwitchTopology" in result.message
