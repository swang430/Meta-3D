"""P1-53: probe calibration data must never cross chamber boundaries."""

import json
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
    ProbePattern,
    ProbePhaseCalibration,
)
from app.schemas.probe_calibration import (
    StartAmplitudeCalibrationRequest,
    StartPatternCalibrationRequest,
    StartPhaseCalibrationRequest,
    StartPolarizationCalibrationRequest,
)
from app.services.calibration_report_generator import CalibrationReportGenerator
from app.services.probe_calibration_service import CalibrationValidityService
from app.services.probe_pattern.import_service import import_probe_pattern
from app.services.probe_phase_calibration_import import import_phase_calibration_from_csv


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


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            StartAmplitudeCalibrationRequest,
            {
                "probe_ids": [1],
                "polarizations": ["V"],
                "frequency_range": {"start_mhz": 3400, "stop_mhz": 3600, "step_mhz": 100},
                "calibrated_by": "operator",
            },
        ),
        (
            StartPhaseCalibrationRequest,
            {
                "probe_ids": [1],
                "polarizations": ["V"],
                "reference_probe_id": 0,
                "frequency_range": {"start_mhz": 3400, "stop_mhz": 3600, "step_mhz": 100},
                "calibrated_by": "operator",
            },
        ),
        (
            StartPolarizationCalibrationRequest,
            {
                "probe_ids": [1],
                "probe_type": "dual_linear",
                "frequency_range": {"start_mhz": 3400, "stop_mhz": 3600, "step_mhz": 100},
                "calibrated_by": "operator",
            },
        ),
        (
            StartPatternCalibrationRequest,
            {
                "probe_ids": [1],
                "polarizations": ["V"],
                "frequency_mhz": 3500,
                "calibrated_by": "operator",
            },
        ),
    ],
)
def test_start_contract_requires_explicit_chamber_id(schema, payload):
    with pytest.raises(ValidationError):
        schema.model_validate(payload)

    chamber_id = uuid.uuid4()
    parsed = schema.model_validate({**payload, "chamber_id": str(chamber_id)})
    assert parsed.chamber_id == chamber_id


def test_phase_import_invalidates_only_same_chamber(session):
    chamber_a, chamber_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.utcnow()
    csv_data = (
        "frequency_mhz,phase_offset_deg,group_delay_ns,phase_uncertainty_deg\n"
        "3500,10,0.5,1.0\n"
    )
    old_a = ProbePhaseCalibration(
        chamber_id=chamber_a, probe_id=1, polarization="V", reference_probe_id=0,
        frequency_points_mhz=[3500.0], phase_offset_deg=[1.0], group_delay_ns=[0.5],
        phase_uncertainty_deg=[1.0], calibrated_at=now, valid_until=now + timedelta(days=30),
        status=CalibrationStatus.VALID.value,
    )
    old_b = ProbePhaseCalibration(
        chamber_id=chamber_b, probe_id=1, polarization="V", reference_probe_id=0,
        frequency_points_mhz=[3500.0], phase_offset_deg=[2.0], group_delay_ns=[0.5],
        phase_uncertainty_deg=[1.0], calibrated_at=now, valid_until=now + timedelta(days=30),
        status=CalibrationStatus.VALID.value,
    )
    session.add_all([old_a, old_b])
    session.commit()

    result = import_phase_calibration_from_csv(
        session, chamber_id=chamber_a, file_content=csv_data, probe_id=1,
        polarization="V", reference_probe_id=0,
    )

    assert result.success is True
    session.refresh(old_a)
    session.refresh(old_b)
    assert old_a.status == CalibrationStatus.INVALIDATED.value
    assert old_b.status == CalibrationStatus.VALID.value
    created = session.get(ProbePhaseCalibration, uuid.UUID(result.calibration_id))
    assert created.chamber_id == chamber_a


def test_pattern_import_invalidates_only_same_chamber(session):
    chamber_a, chamber_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.utcnow()
    def old_pattern(chamber_id, peak):
        return ProbePattern(
            chamber_id=chamber_id, probe_id=1, polarization="V", frequency_mhz=3500,
            azimuth_deg=[0.0, 180.0], elevation_deg=[90.0], gain_pattern_dbi=[peak, 0.0],
            peak_gain_dbi=peak, measured_at=now, valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        )
    old_a, old_b = old_pattern(chamber_a, 1.0), old_pattern(chamber_b, 2.0)
    session.add_all([old_a, old_b])
    session.commit()

    result = import_probe_pattern(
        session, chamber_id=chamber_a,
        file_content=json.dumps({
            "azimuth_deg": [0.0, 180.0], "elevation_deg": [90.0],
            "gain_pattern_dbi": [3.0, 0.0],
        }),
        filename="pattern.json", probe_id=1, polarization="V", frequency_mhz=3500,
    )

    assert result.success is True
    session.refresh(old_a)
    session.refresh(old_b)
    assert old_a.status == CalibrationStatus.INVALIDATED.value
    assert old_b.status == CalibrationStatus.VALID.value
    created = session.get(ProbePattern, uuid.UUID(result.pattern_id))
    assert created.chamber_id == chamber_a


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
