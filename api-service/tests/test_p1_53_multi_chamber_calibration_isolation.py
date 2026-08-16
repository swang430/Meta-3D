"""P1-53: probe calibration data must never cross chamber boundaries."""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.api.probe_calibration import (
    check_link_validity as check_link_validity_api,
    get_amplitude_calibration_history,
    get_phase_calibration_history,
    get_polarization_calibration_history,
)
from app.api.path_loss_calibration import (
    get_path_loss_at_frequency,
    start_multi_frequency_calibration,
)
from app.models.chamber import ChamberConfiguration
from app.models.probe_calibration import (
    CalibrationStatus,
    LinkCalibration,
    MultiFrequencyPathLoss,
    ProbeAmplitudeCalibration,
    ProbePathLossCalibration,
    ProbePattern,
    ProbePhaseCalibration,
    ProbePolarizationCalibration,
    RFChainCalibration,
)
from app.schemas.probe_calibration import (
    StartMultiFrequencyPathLossRequest,
    StartAmplitudeCalibrationRequest,
    StartPatternCalibrationRequest,
    StartPhaseCalibrationRequest,
    StartPolarizationCalibrationRequest,
)
from app.services.calibration_report_generator import CalibrationReportGenerator
from app.services.calibration_orchestrator import CalibrationItem, CalibrationOrchestrator
from app.services.path_loss_calibration_service import (
    CalibrationResult,
    MultiFrequencyPathLossService,
    RFChainCalibrationService,
)
from app.services.pdf_generator import PDFGenerator
from app.services.probe_calibration_service import CalibrationValidityService, LinkCalibrationService
from app.services.probe_pattern.consumer import get_probe_gain_at_azimuth
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
        use_mock=False,
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


def _chamber(db, chamber_id, name):
    chamber = ChamberConfiguration(
        id=chamber_id,
        name=name,
        chamber_type="custom",
        chamber_radius_m=3.0,
        num_probes=32,
    )
    db.add(chamber)
    db.flush()
    return chamber


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


def test_invalidation_cannot_cross_chamber_and_link_remains_global(session):
    chamber_a, chamber_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.utcnow()
    foreign = _amplitude(
        session,
        chamber_id=chamber_b,
        probe_id=1,
        gain=9.0,
        calibrated_at=now,
    )
    session.commit()

    service = CalibrationValidityService()
    denied = service.invalidate_calibration(
        session,
        calibration_type="amplitude",
        calibration_id=str(foreign.id),
        chamber_id=chamber_a,
        reason="wrong chamber",
    )

    assert denied["success"] is False
    session.refresh(foreign)
    assert foreign.status == CalibrationStatus.VALID.value


def test_validity_report_uses_chamber_probe_count_and_rejects_phantoms(session):
    from fastapi import HTTPException
    from app.api.probe_calibration import get_validity_report

    chamber_id = uuid.uuid4()
    chamber = _chamber(session, chamber_id, "16 Probe Chamber")
    chamber.num_probes = 16
    session.commit()

    report = get_validity_report(chamber_id=chamber_id, probe_ids=None, db=session)
    assert report.total_probes == 16

    with pytest.raises(HTTPException) as exc:
        get_validity_report(chamber_id=chamber_id, probe_ids="15,16", db=session)
    assert exc.value.status_code == 400


def test_probe_report_collector_excludes_other_chambers_and_legacy(session):
    chamber_a, chamber_b = uuid.uuid4(), uuid.uuid4()
    _chamber(session, chamber_a, "Chamber A")
    _chamber(session, chamber_b, "Chamber B")
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


def test_probe_report_scopes_existing_path_loss_and_rf_chain_families(session):
    chamber_a, chamber_b = uuid.uuid4(), uuid.uuid4()
    _chamber(session, chamber_a, "Chamber A")
    _chamber(session, chamber_b, "Chamber B")
    now = datetime.utcnow()

    def path_loss(chamber_id, frequency):
        return ProbePathLossCalibration(
            chamber_id=chamber_id,
            frequency_mhz=frequency,
            probe_path_losses={"1": {"path_loss_db": 50.0}},
            sgh_model="P1-53 SGH",
            sgh_gain_dbi=10.0,
            use_mock=False,
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        )

    def rf_chain(chamber_id, frequency):
        return RFChainCalibration(
            chamber_id=chamber_id,
            chain_type="uplink",
            frequency_mhz=frequency,
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        )

    def multi_frequency(chamber_id, probe_id):
        return MultiFrequencyPathLoss(
            chamber_id=chamber_id,
            probe_id=probe_id,
            polarization="V",
            freq_start_mhz=3400.0,
            freq_stop_mhz=3600.0,
            freq_step_mhz=100.0,
            num_points=3,
            frequency_points_mhz=[3400.0, 3500.0, 3600.0],
            path_loss_db=[50.0, 51.0, 52.0],
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        )

    own = [
        path_loss(chamber_a, 3500.0),
        rf_chain(chamber_a, 3500.0),
        multi_frequency(chamber_a, 1),
    ]
    foreign = [
        path_loss(chamber_b, 3700.0),
        rf_chain(chamber_b, 3700.0),
        multi_frequency(chamber_b, 2),
    ]
    session.add_all([*own, *foreign])
    session.commit()

    data = CalibrationReportGenerator(session)._collect_probe_data(chamber_id=chamber_a)

    for section, expected in zip(
        ("path_loss", "rf_chain", "multi_freq_path_loss"),
        own,
    ):
        assert [row["id"] for row in data["probe_calibration"][section]] == [str(expected.id)]


def test_probe_report_keeps_mock_unknown_and_expired_out_of_formal_kpi(session):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Trust Chamber")
    now = datetime.utcnow()
    mock = _amplitude(
        session,
        chamber_id=chamber_id,
        probe_id=1,
        gain=88.0,
        calibrated_at=now,
    )
    mock.use_mock = True
    legacy = _amplitude(
        session,
        chamber_id=chamber_id,
        probe_id=3,
        gain=77.0,
        calibrated_at=now - timedelta(days=10),
    )
    legacy.use_mock = None
    expired = _amplitude(
        session,
        chamber_id=chamber_id,
        probe_id=2,
        gain=5.0,
        calibrated_at=now - timedelta(days=60),
    )
    expired.valid_until = now - timedelta(days=1)
    session.commit()

    data = CalibrationReportGenerator(session)._collect_probe_data(chamber_id=chamber_id)
    rows = data["probe_calibration"]["amplitude"]
    by_probe = {row["probe_id"]: row for row in rows}

    assert by_probe[1]["validation_pass"] is None
    assert by_probe[2]["validation_pass"] is False
    assert by_probe[3]["validation_pass"] is None
    assert data["execution_summary"]["total_executions"] == 1
    assert data["execution_summary"]["passed"] == 0

    validity = CalibrationValidityService()
    assert validity.check_validity(session, 1, chamber_id)["amplitude"] is None
    expiring_ids = {
        row["calibration_id"]
        for row in validity.get_expiring_calibrations(session, chamber_id, days_threshold=90)
    }
    assert str(mock.id) not in expiring_ids
    assert str(legacy.id) not in expiring_ids


def test_polarization_report_uses_persisted_isolation_and_does_not_crash(session):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Polarization Chamber")
    now = datetime.utcnow()
    session.add(ProbePolarizationCalibration(
        chamber_id=chamber_id,
        use_mock=False,
        probe_id=1,
        probe_type="dual_linear",
        v_to_h_isolation_db=24.0,
        h_to_v_isolation_db=22.0,
        calibrated_at=now,
        valid_until=now + timedelta(days=30),
        status=CalibrationStatus.VALID.value,
    ))
    session.commit()

    data = CalibrationReportGenerator(session)._collect_probe_data(
        chamber_id=chamber_id,
        calibration_type="polarization",
    )

    assert data["probe_calibration"]["polarization"][0]["xpd_db"] == 22.0


def test_pattern_consumer_rejects_mock_and_expired_rows(session):
    chamber_id = uuid.uuid4()
    now = datetime.utcnow()

    def pattern(*, use_mock, valid_until, gain):
        return ProbePattern(
            chamber_id=chamber_id,
            use_mock=use_mock,
            source="simulated" if use_mock else "in_chamber_measured",
            probe_id=0,
            polarization="V",
            frequency_mhz=3500.0,
            azimuth_deg=[0.0],
            elevation_deg=[90.0],
            gain_pattern_dbi=[gain],
            peak_gain_dbi=gain,
            measured_at=now,
            valid_until=valid_until,
            status=CalibrationStatus.VALID.value,
        )

    session.add(pattern(use_mock=True, valid_until=now + timedelta(days=30), gain=99.0))
    session.add(pattern(use_mock=False, valid_until=now - timedelta(days=1), gain=77.0))
    session.commit()
    assert get_probe_gain_at_azimuth(session, 1, 0, 3500, chamber_id=chamber_id) is None

    session.add(pattern(use_mock=False, valid_until=now + timedelta(days=30), gain=5.5))
    session.commit()
    assert get_probe_gain_at_azimuth(session, 1, 0, 3500, chamber_id=chamber_id) == 5.5


def test_probe_pdf_renders_every_family_counted_in_summary():
    elements = PDFGenerator()._generate_calibration_probe_section({
        "probe_calibration": {
            "rf_chain": [{
                "chain_type": "uplink", "frequency_mhz": 3500,
                "validation_pass": True, "calibrated_at": "2026-08-16",
            }],
            "multi_freq_path_loss": [{
                "probe_id": 1, "freq_start_mhz": 3400, "freq_stop_mhz": 3600,
                "validation_pass": True, "calibrated_at": "2026-08-16",
            }],
        },
    })
    rendered = " ".join(
        str(getattr(element, "text", ""))
        for element in elements
        if hasattr(element, "text")
    )
    assert "RF Chain Calibration" in rendered
    assert "Multi-Frequency Path Loss" in rendered


def test_mock_rf_multi_and_link_rows_are_unverified_and_excluded_from_summary(session):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Mock Provenance Chamber")
    now = datetime.utcnow()
    session.add_all([
        RFChainCalibration(
            chamber_id=chamber_id,
            use_mock=True,
            chain_type="uplink",
            frequency_mhz=3500.0,
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ),
        MultiFrequencyPathLoss(
            chamber_id=chamber_id,
            use_mock=True,
            probe_id=1,
            polarization="V",
            freq_start_mhz=3400.0,
            freq_stop_mhz=3600.0,
            freq_step_mhz=100.0,
            num_points=3,
            frequency_points_mhz=[3400.0, 3500.0, 3600.0],
            path_loss_db=[50.0, 51.0, 52.0],
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ),
        LinkCalibration(
            use_mock=True,
            calibration_type="weekly_check",
            validation_pass=True,
            threshold_db=1.0,
            calibrated_at=now,
        ),
    ])
    session.commit()

    data = CalibrationReportGenerator(session)._collect_probe_data(chamber_id=chamber_id)

    assert data["probe_calibration"]["rf_chain"][0]["validation_pass"] is None
    assert data["probe_calibration"]["multi_freq_path_loss"][0]["validation_pass"] is None
    assert data["probe_calibration"]["link"][0]["validation_pass"] is None
    assert data["execution_summary"]["total_executions"] == 0


def test_global_link_never_makes_an_uncalibrated_probe_valid(session):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Link Only Chamber")
    session.add(LinkCalibration(
        use_mock=False,
        calibration_type="weekly_check",
        validation_pass=True,
        threshold_db=1.0,
        calibrated_at=datetime.utcnow(),
    ))
    session.commit()

    result = CalibrationValidityService().check_validity(session, 1, chamber_id)

    assert result["link"] is not None
    assert result["overall_status"] == "unknown"


def test_mock_link_is_unknown_and_absent_from_validity_deadlines(session):
    now = datetime.utcnow()
    mock = LinkCalibration(
        use_mock=True,
        calibration_type="weekly_check",
        validation_pass=None,
        threshold_db=1.0,
        calibrated_at=now,
    )
    session.add(mock)
    session.commit()

    assert check_link_validity_api(db=session)["status"] == "unknown"

    validity = CalibrationValidityService(expiring_threshold_days=7)
    assert validity.get_expiring_calibrations(
        session, uuid.uuid4(), days_threshold=30, calibration_type="link"
    ) == []

    mock.calibrated_at = now - timedelta(days=30)
    session.commit()
    assert validity.get_expired_calibrations(
        session, uuid.uuid4(), calibration_type="link"
    ) == []


def test_chamber_report_excludes_untrusted_rf_and_multi_from_formal_kpi(session):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Chamber Report Provenance")
    now = datetime.utcnow()
    session.add_all([
        RFChainCalibration(
            chamber_id=chamber_id,
            use_mock=True,
            chain_type="uplink",
            frequency_mhz=3500.0,
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ),
        MultiFrequencyPathLoss(
            chamber_id=chamber_id,
            use_mock=None,
            probe_id=0,
            polarization="V",
            freq_start_mhz=3400.0,
            freq_stop_mhz=3600.0,
            freq_step_mhz=100.0,
            num_points=3,
            frequency_points_mhz=[3400.0, 3500.0, 3600.0],
            path_loss_db=[50.0, 51.0, 52.0],
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ),
    ])
    session.commit()

    data = CalibrationReportGenerator(session)._collect_chamber_calibration_data(chamber_id)
    assert data["chamber_calibration"]["uplink"][0]["validation_pass"] is None
    assert data["chamber_calibration"]["uplink"][0]["use_mock"] is True
    assert data["chamber_calibration"]["multi_frequency"][0]["validation_pass"] is None
    assert data["chamber_calibration"]["multi_frequency"][0]["use_mock"] is None
    assert data["execution_summary"]["total_executions"] == 0


def test_formal_rf_multi_consumers_ignore_untrusted_rows(session):
    chamber_id = uuid.uuid4()
    chamber = _chamber(session, chamber_id, "Formal Consumer Provenance")
    chamber.has_lna = True
    now = datetime.utcnow()
    session.add_all([
        RFChainCalibration(
            chamber_id=chamber_id,
            use_mock=True,
            chain_type="uplink",
            frequency_mhz=3500.0,
            total_chain_gain_db=99.0,
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ),
        MultiFrequencyPathLoss(
            chamber_id=chamber_id,
            use_mock=True,
            probe_id=0,
            polarization="V",
            freq_start_mhz=3400.0,
            freq_stop_mhz=3600.0,
            freq_step_mhz=100.0,
            num_points=3,
            frequency_points_mhz=[3400.0, 3500.0, 3600.0],
            path_loss_db=[50.0, 51.0, 52.0],
            calibrated_at=now,
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ),
    ])
    session.commit()

    assert RFChainCalibrationService(session, use_mock=False).get_latest_uplink_calibration(
        chamber_id, 3500.0
    ) is None
    assert MultiFrequencyPathLossService(session, use_mock=False).get_path_loss_at_frequency(
        chamber_id, 0, "V", 3500.0
    ) is None
    with pytest.raises(HTTPException) as exc_info:
        get_path_loss_at_frequency(
            chamber_id=chamber_id,
            probe_id=0,
            frequency_mhz=3500.0,
            polarization="V",
            db=session,
        )
    assert exc_info.value.status_code == 404
    status = CalibrationOrchestrator(session, use_mock=False).check_calibration_status(
        chamber_id, 3500.0
    )
    assert status[CalibrationItem.UPLINK_CHAIN].is_valid is False
    assert status[CalibrationItem.MULTI_FREQUENCY].is_valid is False


@pytest.mark.asyncio
async def test_multi_frequency_start_remains_explicitly_mock(session, monkeypatch):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Mock-only multi-frequency start")
    session.commit()
    observed = {}

    async def fake_sweep(service, **_kwargs):
        observed["use_mock"] = service.use_mock
        return CalibrationResult(success=True, message="mock", data={"calibration_ids": []})

    monkeypatch.setattr(
        MultiFrequencyPathLossService,
        "calibrate_frequency_sweep",
        fake_sweep,
    )
    request = StartMultiFrequencyPathLossRequest(
        chamber_id=chamber_id,
        probe_ids=[0],
        polarization="V",
        freq_start_mhz=3400.0,
        freq_stop_mhz=3600.0,
        freq_step_mhz=100.0,
        sgh_model="audit-only",
        sgh_gain_dbi=0.0,
        calibrated_by="test",
    )

    await start_multi_frequency_calibration(request=request, db=session)

    assert observed == {"use_mock": True}


def test_probe_history_exposes_provenance_and_trends_use_only_explicit_real(session):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "History provenance")
    now = datetime.utcnow()

    for days_ago, value, use_mock in (
        (90, 1.0, False),
        (60, 2.0, False),
        (30, 3.0, False),
        (0, 100.0, True),
    ):
        amplitude = _amplitude(
            session,
            chamber_id=chamber_id,
            probe_id=1,
            gain=value,
            calibrated_at=now - timedelta(days=days_ago),
        )
        amplitude.use_mock = use_mock
        session.add(ProbePhaseCalibration(
            chamber_id=chamber_id,
            use_mock=use_mock,
            probe_id=1,
            polarization="V",
            reference_probe_id=0,
            frequency_points_mhz=[3500.0],
            phase_offset_deg=[value * 10.0],
            group_delay_ns=[0.5],
            phase_uncertainty_deg=[1.0],
            calibrated_at=now - timedelta(days=days_ago),
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ))

    for days_ago, use_mock in ((2, False), (1, None), (0, True)):
        session.add(ProbePolarizationCalibration(
            chamber_id=chamber_id,
            use_mock=use_mock,
            probe_id=1,
            probe_type="dual_linear",
            v_to_h_isolation_db=24.0,
            h_to_v_isolation_db=22.0,
            frequency_points_mhz=[3500.0],
            calibrated_at=now - timedelta(days=days_ago),
            valid_until=now + timedelta(days=30),
            status=CalibrationStatus.VALID.value,
        ))
    session.commit()

    amplitude_history = get_amplitude_calibration_history(
        probe_id=1, chamber_id=chamber_id, limit=20, db=session,
    )
    phase_history = get_phase_calibration_history(
        probe_id=1, chamber_id=chamber_id, limit=20, db=session,
    )
    polarization_history = get_polarization_calibration_history(
        probe_id=1, chamber_id=chamber_id, limit=20, db=session,
    )

    assert [row.use_mock for row in amplitude_history.history] == [True, False, False, False]
    assert amplitude_history.trends == {
        "amplitude_drift_db_per_month": 1.0,
        "stability_rating": "drifting",
    }
    assert [row.use_mock for row in phase_history.history] == [True, False, False, False]
    assert phase_history.trends == {
        "phase_drift_deg_per_month": 10.0,
        "stability_rating": "drifting",
    }
    assert [row.use_mock for row in polarization_history.history] == [True, None, False]


def test_link_formal_validity_prefers_real_and_report_expires_after_seven_days(session):
    now = datetime.utcnow()
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Link Report")
    real = LinkCalibration(
        use_mock=False,
        calibration_type="weekly_check",
        validation_pass=True,
        threshold_db=1.0,
        calibrated_at=now - timedelta(days=1),
    )
    newer_mock = LinkCalibration(
        use_mock=True,
        calibration_type="weekly_check",
        validation_pass=None,
        threshold_db=1.0,
        calibrated_at=now,
    )
    session.add_all([real, newer_mock])
    session.commit()

    assert check_link_validity_api(db=session)["calibration_id"] == str(real.id)
    assert LinkCalibrationService().check_link_validity(session)["calibration_id"] == str(real.id)
    probe = CalibrationValidityService().check_validity(session, 0, uuid.uuid4())
    assert probe["link"]["calibration_id"] == str(real.id)

    real.calibrated_at = now - timedelta(days=8)
    session.commit()
    report = CalibrationReportGenerator(session)._collect_probe_data(
        chamber_id=chamber_id, calibration_type="link"
    )
    by_id = {row["id"]: row for row in report["probe_calibration"]["link"]}
    assert by_id[str(real.id)]["validation_pass"] is False
    assert report["execution_summary"]["passed"] == 0


def test_probe_overall_requires_all_four_scoped_families(session):
    chamber_id = uuid.uuid4()
    _chamber(session, chamber_id, "Partial Probe")
    _amplitude(
        session,
        chamber_id=chamber_id,
        probe_id=0,
        gain=4.0,
        calibrated_at=datetime.utcnow(),
    )
    session.commit()

    result = CalibrationValidityService().check_validity(session, 0, chamber_id)
    assert result["amplitude"]["status"] == "valid"
    assert result["overall_status"] == "partial"


def test_validity_report_preserves_each_probe_overall_status(session, monkeypatch):
    chamber_id = uuid.uuid4()
    service = CalibrationValidityService()
    statuses = {0: "valid", 1: "partial"}

    monkeypatch.setattr(
        service,
        "check_validity",
        lambda _db, probe_id, _chamber_id: {
            "probe_id": probe_id,
            "overall_status": statuses[probe_id],
        },
    )

    report = service.generate_validity_report(
        session,
        chamber_id,
        probe_ids=[0, 1],
    )

    assert report["valid_probes"] == 1
    assert report["partial_probes"] == 1
    assert report["probe_statuses"] == {0: "valid", 1: "partial"}
