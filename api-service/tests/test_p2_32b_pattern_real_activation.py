"""P2-32B probe-pattern production activation contracts."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.probe_calibration import ProbePattern
from app.schemas.probe_calibration import (
    PatternCalibrationResponse,
    StartPatternCalibrationRequest,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _pattern(**overrides):
    now = datetime.utcnow()
    values = {
        "probe_id": 1,
        "chamber_id": uuid4(),
        "use_mock": False,
        "source": "in_chamber_measured",
        "polarization": "V",
        "frequency_mhz": 3500.0,
        "azimuth_deg": [0.0],
        "elevation_deg": [90.0],
        "gain_pattern_dbi": [5.0],
        "peak_gain_dbi": 5.0,
        "measured_at": now,
        "valid_until": now + timedelta(days=365),
        "status": "valid",
    }
    values.update(overrides)
    return ProbePattern(**values)


def test_probe_pattern_persists_execution_provenance_and_warnings():
    columns = {column.key for column in inspect(ProbePattern).columns}
    assert {
        "warnings",
        "lab_profile_id",
        "operating_mode",
        "topology_id",
        "chain_id",
        "ce_port",
    } <= columns

    db = _session()
    lab_profile_id = uuid4()
    pattern = _pattern(
        warnings=["tone cleanup rejected"],
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
        topology_id="topology-1",
        chain_id="chain-1",
        ce_port="B1.1",
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    assert pattern.warnings == ["tone cleanup rejected"]
    assert pattern.lab_profile_id == lab_profile_id
    assert pattern.operating_mode == "mimo_ota"
    assert pattern.topology_id == "topology-1"
    assert pattern.chain_id == "chain-1"
    assert pattern.ce_port == "B1.1"

    response = PatternCalibrationResponse.model_validate(pattern)
    assert response.warnings == ["tone cleanup rejected"]
    assert response.lab_profile_id == lab_profile_id
    assert response.topology_id == "topology-1"
    assert response.chain_id == "chain-1"
    assert response.ce_port == "B1.1"
    db.close()


def test_probe_pattern_warning_null_and_empty_list_remain_distinct():
    db = _session()
    historical = _pattern(probe_id=1, warnings=None)
    newly_recorded = _pattern(probe_id=2, warnings=[])
    db.add_all([historical, newly_recorded])
    db.commit()

    assert db.query(ProbePattern).filter_by(probe_id=1).one().warnings is None
    assert db.query(ProbePattern).filter_by(probe_id=2).one().warnings == []
    db.close()


def test_pattern_start_request_carries_explicit_execution_context():
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    request = StartPatternCalibrationRequest(
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        operating_mode="mimo_ota",
        probe_ids=[1, 2],
        polarizations=["V", "H"],
        frequency_mhz=3500.0,
        ce_tx_power_dbm=-20.0,
        sgh_gain_dbi=10.0,
        use_mock=False,
        calibrated_by="operator",
    )

    assert request.lab_profile_id == lab_profile_id
    assert request.chamber_id == chamber_id
    assert request.operating_mode == "mimo_ota"
    assert request.ce_tx_power_dbm == -20.0
    assert request.sgh_gain_dbi == 10.0
    assert request.use_mock is False


def test_pattern_start_request_preserves_mock_compatibility_default():
    request = StartPatternCalibrationRequest(
        lab_profile_id=uuid4(),
        chamber_id=uuid4(),
        probe_ids=[1],
        frequency_mhz=3500.0,
        calibrated_by="operator",
    )

    assert request.use_mock is True
    assert request.operating_mode == "mimo_ota"
