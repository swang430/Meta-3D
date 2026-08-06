"""P1-28: 当前暗室唯一真值源与校准引用完整性。"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.diagnostics.sequences import chamber_configuration_integrity
from app.main import app
from app.models.chamber import ChamberConfiguration
from app.models.lab_profile import LabProfile
from app.models.probe_calibration import ProbeCalibrationValidity
from app.models.probe_calibration import ProbeAmplitudeCalibration
from app.services.chamber_resolution import (
    audit_chamber_integrity,
    resolve_current_chamber,
)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _db_setup():
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def two_chambers_and_lab(db):
    legacy = ChamberConfiguration(
        name="Legacy flag chamber",
        chamber_radius_m=4.0,
        num_probes=8,
        is_active=True,
    )
    bound = ChamberConfiguration(
        name="Lab-bound chamber",
        chamber_radius_m=4.0,
        num_probes=12,
        is_active=False,
    )
    db.add_all([legacy, bound])
    db.flush()
    lab = LabProfile(
        name="P1-28 Lab",
        chamber_config_id=bound.id,
        is_active=True,
    )
    db.add(lab)
    db.commit()
    return legacy, bound, lab


def test_resolver_ignores_legacy_active_flag(db, two_chambers_and_lab):
    legacy, bound, lab = two_chambers_and_lab

    resolved = resolve_current_chamber(db, lab.id)

    assert resolved.id == bound.id
    assert resolved.id != legacy.id


def test_active_endpoint_and_list_derive_state_from_lab_binding(two_chambers_and_lab):
    legacy, bound, lab = two_chambers_and_lab
    client = TestClient(app)

    active = client.get(f"/api/v1/chambers/active?lab_profile_id={lab.id}")
    listing = client.get(f"/api/v1/chambers?lab_profile_id={lab.id}")

    assert active.status_code == 200, active.text
    assert active.json()["id"] == str(bound.id)
    by_id = {item["id"]: item for item in listing.json()["items"]}
    assert by_id[str(bound.id)]["is_active"] is True
    assert by_id[str(legacy.id)]["is_active"] is False


def test_activate_rebinds_lab_without_mutating_legacy_flags(db, two_chambers_and_lab):
    legacy, bound, lab = two_chambers_and_lab
    replacement = ChamberConfiguration(
        name="Replacement",
        chamber_radius_m=4.0,
        num_probes=16,
        is_active=False,
    )
    db.add(replacement)
    db.commit()
    replacement_id = replacement.id
    client = TestClient(app)

    response = client.post(
        f"/api/v1/chambers/{replacement_id}/activate?lab_profile_id={lab.id}"
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(LabProfile, lab.id).chamber_config_id == replacement_id
    assert db.get(ChamberConfiguration, legacy.id).is_active is True
    assert db.get(ChamberConfiguration, replacement_id).is_active is False
    assert response.json()["is_active"] is True


def test_active_endpoint_fails_loud_when_active_lab_is_ambiguous(db, two_chambers_and_lab):
    _, bound, _ = two_chambers_and_lab
    db.add(LabProfile(name="Second active lab", chamber_config_id=bound.id, is_active=True))
    db.commit()

    response = TestClient(app).get("/api/v1/chambers/active")

    assert response.status_code == 422
    assert "Multiple active LabProfiles" in response.text


def test_plain_list_remains_available_when_selected_lab_binding_is_broken(
    db, two_chambers_and_lab,
):
    _, _, lab = two_chambers_and_lab
    lab.chamber_config_id = None
    db.commit()
    client = TestClient(app)

    listing = client.get(f"/api/v1/chambers?lab_profile_id={lab.id}")
    active = client.get(f"/api/v1/chambers/active?lab_profile_id={lab.id}")

    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 2
    assert all(item["is_active"] is False for item in listing.json()["items"])
    assert active.status_code == 422


@pytest.mark.parametrize("lab_state", ["missing", "inactive"])
def test_plain_list_rejects_invalid_explicit_lab_identity(
    db, two_chambers_and_lab, lab_state,
):
    _, _, lab = two_chambers_and_lab
    if lab_state == "inactive":
        lab.is_active = False
        db.commit()
        lab_id = lab.id
    else:
        lab_id = uuid.uuid4()

    response = TestClient(app).get(f"/api/v1/chambers?lab_profile_id={lab_id}")

    assert response.status_code == 422
    assert lab_state in response.text.lower() or "not found" in response.text.lower()


def test_is_active_is_not_a_writable_chamber_field(two_chambers_and_lab):
    _, bound, lab = two_chambers_and_lab

    response = TestClient(app).put(
        f"/api/v1/chambers/{bound.id}?lab_profile_id={lab.id}",
        json={"is_active": True},
    )

    assert response.status_code == 422


def test_integrity_audit_reports_orphan_calibration_reference(db, two_chambers_and_lab):
    _, _, lab = two_chambers_and_lab
    orphan_id = uuid.uuid4()
    db.add(ProbeCalibrationValidity(probe_id=77, chamber_id=orphan_id))
    db.commit()

    report = audit_chamber_integrity(db, lab.id)

    assert report.current_chamber_id == lab.chamber_config_id
    assert report.ok is False
    assert report.orphan_references["probe_calibration_validity"] == [str(orphan_id)]


def test_integrity_diagnostic_fails_loud_on_orphan(db, two_chambers_and_lab):
    _, _, lab = two_chambers_and_lab
    db.add(ProbeCalibrationValidity(probe_id=78, chamber_id=uuid.uuid4()))
    db.commit()
    from app.services.diagnostic_context import build_diagnostic_context

    ctx = build_diagnostic_context(
        db, lab_profile_id=lab.id, audit_chamber_integrity_too=True,
    )
    result = asyncio.run(
        chamber_configuration_integrity.run(ctx, MagicMock(), {}, log=lambda _: None)
    )

    assert result.success is False
    assert any(step.label == "校准暗室引用完整性" and not step.success for step in result.steps)


def test_integrity_diagnostic_endpoint_populates_read_only_audit(two_chambers_and_lab):
    _, _, lab = two_chambers_and_lab

    response = TestClient(app).post(
        "/api/v1/diagnostic-sequences/chamber_configuration_integrity/run",
        json={"lab_profile_id": str(lab.id), "params": {}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert response.json()["extra"]["current_chamber_id"] == str(lab.chamber_config_id)


def test_workflow_auto_probe_ids_uses_resolved_lab_chamber(db, two_chambers_and_lab):
    _, bound, lab = two_chambers_and_lab
    from app.services.workflow_engine import WorkflowExecutor

    probe_ids = WorkflowExecutor(db)._resolve_probe_ids(
        {"probe_ids": "auto", "lab_profile_id": str(lab.id)}
    )

    assert probe_ids == list(range(bound.num_probes))


def test_probe_workflow_persists_calibration_against_resolved_chamber(
    db, two_chambers_and_lab,
):
    """真正执行校准服务，而不是只验证 auto 展开辅助函数。"""
    _, bound, lab = two_chambers_and_lab
    from app.services.workflow_engine import (
        StepStatus,
        WorkflowExecutor,
        WorkflowParser,
        WorkflowStatus,
    )

    workflow = WorkflowParser.parse_string(
        f"""
name: "P1-28 chamber-scoped probe calibration"
settings:
  retry_count: 0
parameters:
  lab_profile_id: "{lab.id}"
  calibrated_by: "p1-28-test"
steps:
  - id: amplitude
    type: probe_calibration
    calibration_type: amplitude
    parameters:
      probe_ids: [0, 1]
      polarizations: [V]
      frequency_range:
        start_mhz: 3300
        stop_mhz: 3400
        step_mhz: 100
      use_mock: true
"""
    )
    executor = WorkflowExecutor(db)

    execution = executor.run(executor.create_execution(workflow))

    assert execution.status == WorkflowStatus.COMPLETED
    assert execution.step_results["amplitude"].status == StepStatus.COMPLETED
    rows = db.query(ProbeAmplitudeCalibration).order_by(
        ProbeAmplitudeCalibration.probe_id
    ).all()
    assert [row.probe_id for row in rows] == [0, 1]
    assert {row.chamber_id for row in rows} == {bound.id}


def test_probe_workflow_api_runs_async_service_off_endpoint_loop(
    db, two_chambers_and_lab,
):
    _, bound, lab = two_chambers_and_lab
    yaml_content = f"""
name: "P1-28 API probe calibration"
settings:
  retry_count: 0
parameters:
  lab_profile_id: "{lab.id}"
steps:
  - id: amplitude
    type: probe_calibration
    calibration_type: amplitude
    parameters:
      probe_ids: auto
      polarizations: [H]
      frequency_range:
        start_mhz: 3300
        stop_mhz: 3400
        step_mhz: 100
      use_mock: true
"""

    response = TestClient(app).post(
        "/api/v1/workflows/execute", json={"yaml_content": yaml_content}
    )

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "completed"
    db.expire_all()
    rows = db.query(ProbeAmplitudeCalibration).order_by(
        ProbeAmplitudeCalibration.probe_id
    ).all()
    assert [row.probe_id for row in rows] == list(range(bound.num_probes))
    assert {row.chamber_id for row in rows} == {bound.id}


def test_probe_workflow_rejects_explicit_probe_outside_current_chamber(
    db, two_chambers_and_lab,
):
    _, _, lab = two_chambers_and_lab
    from app.services.workflow_engine import WorkflowExecutor, WorkflowParser, WorkflowStatus

    workflow = WorkflowParser.parse_string(
        f"""
name: "P1-28 reject out-of-range probe"
settings:
  retry_count: 0
parameters:
  lab_profile_id: "{lab.id}"
steps:
  - id: amplitude
    type: probe_calibration
    calibration_type: amplitude
    parameters:
      probe_ids: [99]
      frequency_range:
        start_mhz: 3300
        stop_mhz: 3400
        step_mhz: 100
"""
    )

    executor = WorkflowExecutor(db)
    execution = executor.run(executor.create_execution(workflow))

    assert execution.status == WorkflowStatus.FAILED
    assert "outside chamber range" in execution.step_results["amplitude"].error_message
    assert db.query(ProbeAmplitudeCalibration).count() == 0


def test_failed_probe_calibration_attempt_rolls_back_partial_rows_before_retry(
    db, two_chambers_and_lab, monkeypatch,
):
    _, _, lab = two_chambers_and_lab
    from app.services.probe_calibration_service import AmplitudeCalibrationService
    from app.services.workflow_engine import WorkflowExecutor, WorkflowParser, WorkflowStatus

    original_measurements = AmplitudeCalibrationService._mock_measurements

    def fail_after_first_probe(self, probe_id, polarization, freq_points):
        if probe_id == 1:
            raise RuntimeError("injected second-probe failure")
        return original_measurements(self, probe_id, polarization, freq_points)

    monkeypatch.setattr(
        AmplitudeCalibrationService, "_mock_measurements", fail_after_first_probe,
    )
    workflow = WorkflowParser.parse_string(
        f"""
name: "P1-28 atomic failed attempt"
settings:
  retry_count: 1
  retry_delay_seconds: 0
parameters:
  lab_profile_id: "{lab.id}"
steps:
  - id: amplitude
    type: probe_calibration
    calibration_type: amplitude
    parameters:
      probe_ids: [0, 1]
      frequency_range:
        start_mhz: 3300
        stop_mhz: 3400
        step_mhz: 100
"""
    )
    executor = WorkflowExecutor(db)

    execution = executor.run(executor.create_execution(workflow))

    assert execution.status == WorkflowStatus.FAILED
    assert execution.step_results["amplitude"].retry_count == 2
    assert db.query(ProbeAmplitudeCalibration).count() == 0
