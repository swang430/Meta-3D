"""P1-53: probe calibration data must never cross chamber boundaries."""

import uuid
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.probe_calibration import (
    CalibrationStatus,
    ProbeAmplitudeCalibration,
)
from app.schemas.probe_calibration import StartAmplitudeCalibrationRequest
from app.services.calibration_report_generator import CalibrationReportGenerator
from app.services.probe_calibration_service import CalibrationValidityService


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


def _amplitude(
    db,
    *,
    chamber_id,
    probe_id: int,
    gain: float,
    calibrated_at: datetime,
) -> ProbeAmplitudeCalibration:
    record = ProbeAmplitudeCalibration(
        chamber_id=chamber_id,
        probe_id=probe_id,
        polarization="V",
        frequency_points_mhz=[3500.0],
        tx_gain_dbi=[gain],
        rx_gain_dbi=[gain],
        tx_gain_uncertainty_db=[0.2],
        rx_gain_uncertainty_db=[0.2],
        calibrated_at=calibrated_at,
        calibrated_by="p1-53",
        valid_until=datetime.utcnow() + timedelta(days=30),
        status=CalibrationStatus.VALID.value,
    )
    db.add(record)
    db.flush()
    return record


def test_start_contract_requires_explicit_chamber_id():
    payload = {
        "probe_ids": [1],
        "polarizations": ["V"],
        "frequency_range": {"start_mhz": 3400, "stop_mhz": 3600, "step_mhz": 100},
        "calibrated_by": "operator",
    }

    with pytest.raises(ValidationError):
        StartAmplitudeCalibrationRequest.model_validate(payload)

    chamber_id = uuid.uuid4()
    parsed = StartAmplitudeCalibrationRequest.model_validate(
        {**payload, "chamber_id": str(chamber_id)}
    )
    assert parsed.chamber_id == chamber_id


def test_validity_uses_only_requested_chamber(session):
    chamber_a, chamber_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.utcnow()
    a = _amplitude(
        session,
        chamber_id=chamber_a,
        probe_id=1,
        gain=11.0,
        calibrated_at=now - timedelta(days=2),
    )
    _amplitude(
        session,
        chamber_id=chamber_b,
        probe_id=1,
        gain=99.0,
        calibrated_at=now,
    )
    _amplitude(
        session,
        chamber_id=None,
        probe_id=1,
        gain=77.0,
        calibrated_at=now + timedelta(seconds=1),
    )

    result = CalibrationValidityService().check_validity(
        session,
        probe_id=1,
        chamber_id=chamber_a,
    )

    assert result["chamber_id"] == str(chamber_a)
    assert result["amplitude"]["calibration_id"] == str(a.id)


def test_probe_report_collector_excludes_other_chambers_and_legacy(session):
    chamber_a, chamber_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.utcnow()
    own = _amplitude(
        session,
        chamber_id=chamber_a,
        probe_id=1,
        gain=12.0,
        calibrated_at=now - timedelta(days=2),
    )
    _amplitude(
        session,
        chamber_id=chamber_b,
        probe_id=1,
        gain=98.0,
        calibrated_at=now,
    )
    _amplitude(
        session,
        chamber_id=None,
        probe_id=1,
        gain=76.0,
        calibrated_at=now + timedelta(seconds=1),
    )

    data = CalibrationReportGenerator(session)._collect_probe_data(
        chamber_id=chamber_a,
        probe_ids=[1],
        calibration_type="amplitude",
    )

    rows = data["probe_calibration"]["amplitude"]
    assert [row["id"] for row in rows] == [str(own.id)]
    assert rows[0]["chamber_id"] == str(chamber_a)

