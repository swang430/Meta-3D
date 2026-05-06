"""P3 Phase 3: ad-hoc single-phase commissioning + HAL trace tail.

The ad-hoc endpoint creates a synthetic TestCase + TestExecution tagged
'diagnostic_ad_hoc', dispatches one MIMO_OTA executor, and writes a
diagnostic_run audit row. We verify:
  - tagging keeps the row out of the formal commissioning sessions list
  - phase_overrides land in descriptor.parameters before dispatch
  - audit row carries the right kind + run_by
  - HAL trace tail returns lines from a real log file
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.chamber import (
    ChamberType,
    create_chamber_from_preset,
)
from app.models.diagnostic_run import DiagnosticKind, DiagnosticRun
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="P3 P3 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab(db, chamber):
    lp = LabProfile(
        name="P3-Phase3-Lab",
        chamber_config_id=chamber.id,
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


class TestAdhocPhaseEndpoint:
    def test_unknown_phase_returns_400(self, lab):
        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "no_such_phase"},
        )
        assert resp.status_code == 400
        assert "Unknown phase" in resp.json()["detail"]

    def test_creates_tagged_test_execution(self, lab, db):
        """The TestCase should carry the 'diagnostic_ad_hoc' tag so the
        regular commissioning list view can hide these."""
        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={
                "lab_profile_id": str(lab.id),
                "phase_name": "precheck",
                "phase_overrides": {"skip_calibration_age_check": True},
                "run_by": "pytest",
            },
        )
        # Note: precheck may report failure (no instruments connected etc.)
        # but the endpoint itself should always 200 — we're testing that
        # creating + tagging works, not that the executor passes.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["phase"] == "precheck"
        assert body["test_execution_id"]
        assert body["diagnostic_run_id"]

        # The TestExecution config carries the diagnostic_ad_hoc flag
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(body["test_execution_id"]))
            .first()
        )
        assert execution is not None
        assert (execution.config or {}).get("diagnostic_ad_hoc") is True
        assert (execution.config or {}).get("phase_overrides") == {
            "skip_calibration_age_check": True
        }

    def test_diagnostic_run_recorded_with_correct_kind(self, lab, db):
        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={
                "lab_profile_id": str(lab.id),
                "phase_name": "analysis",
                "run_by": "ops-debug",
            },
        )
        assert resp.status_code == 200
        body = resp.json()

        run = (
            db.query(DiagnosticRun)
            .filter(DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"]))
            .first()
        )
        assert run is not None
        assert run.kind == DiagnosticKind.COMMISSIONING_PHASE.value
        assert run.target_name == "analysis"
        assert run.run_by == "ops-debug"
        assert run.lab_profile_id == lab.id
        # params should preserve test_execution_id pointer for cross-ref
        assert run.params is not None
        assert "test_execution_id" in run.params

    def test_phase_overrides_apply_to_descriptor(self, lab, db):
        """Operator passes phase_overrides — they should land in descriptor
        parameters before dispatch (verify by reading the persisted config)."""
        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={
                "lab_profile_id": str(lab.id),
                "phase_name": "mimo_test",
                "phase_overrides": {"settling_time_s": 0.1, "num_samples_per_azimuth": 1},
            },
        )
        assert resp.status_code == 200
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(resp.json()["test_execution_id"]))
            .first()
        )
        assert execution is not None
        descriptors = (execution.config or {}).get("step_descriptors") or []
        assert len(descriptors) == 1  # ad-hoc has just the requested phase
        params = descriptors[0].get("parameters") or {}
        assert params.get("settling_time_s") == 0.1
        assert params.get("num_samples_per_azimuth") == 1


class TestHALTraceTail:
    def test_returns_lines_when_log_present(self, tmp_path, monkeypatch):
        """If logs/measurement.log doesn't exist (test env), make a tiny one."""
        monkeypatch.chdir(tmp_path)
        os.makedirs("logs", exist_ok=True)
        with open("logs/measurement.log", "w") as f:
            for i in range(50):
                f.write(f"line {i}\n")

        resp = client.get(
            "/api/v1/commissioning/diagnostic/hal-trace-tail",
            params={"lines": 10},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["log_path"].endswith("measurement.log")
        assert body["total_lines_returned"] == 10
        # Should be the LAST 10 lines.
        assert body["lines"][0] == "line 40"
        assert body["lines"][-1] == "line 49"

    def test_returns_404_when_no_log_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No logs/ directory at all
        resp = client.get("/api/v1/commissioning/diagnostic/hal-trace-tail")
        assert resp.status_code == 404
