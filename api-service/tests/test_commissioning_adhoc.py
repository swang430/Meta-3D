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
        # Codex #238 迟到 C-2: 行必须收尾 — 不许永久停在建行时的
        # pending (执行历史/仪表盘里会显示"待执行"僵尸行)。
        # 变异 = 砍 handler 的收尾回写块 → 这三条红。
        assert execution.status in ("completed", "failed")
        assert execution.completed_at is not None
        assert execution.duration_sec is not None

    def test_skipped_phase_row_is_not_marked_failed(self, lab, db, monkeypatch):
        """收尾映射按相位状态四态走: skipped 不许被记成 failed
        (StepExecutionStatus 有 success/failed/skipped/running, 二分映射
        会把"跳过"栽赃成"失败" — 自查发现)。
        变异 = 把映射改回二分 → 本条红。"""
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        async def _fake_dispatch(ctx):
            return StepExecutionResult(status=StepExecutionStatus.SKIPPED)

        monkeypatch.setattr(
            "app.api.commissioning.dispatch_step", _fake_dispatch)

        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={
                "lab_profile_id": str(lab.id),
                "phase_name": "precheck",
                "run_by": "pytest",
            },
        )
        assert resp.status_code == 200, resp.text
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(resp.json()["test_execution_id"]))
            .first()
        )
        assert execution.status == "skipped"
        assert execution.completed_at is not None

    def test_failed_phase_row_records_failure_and_message(self, lab, db, monkeypatch):
        """收尾映射的两个方向都要有门 (内审 F3): 失败相位必须落 failed
        且错误文本进列 —— 记成 completed 是假绿, 且会经"待归档"通道
        变成可归档报告候选。
        变异 = 默认值改成 completed / 砍 error_message 回写 → 本条红。"""
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        async def _fake_dispatch(ctx):
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="precheck 失败: 静区未验证",
            )

        monkeypatch.setattr(
            "app.api.commissioning.dispatch_step", _fake_dispatch)

        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "precheck",
                  "run_by": "pytest"},
        )
        assert resp.status_code == 200, resp.text
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(resp.json()["test_execution_id"]))
            .first()
        )
        assert execution.status == "failed"
        assert execution.error_message == "precheck 失败: 静区未验证"

    def test_success_phase_row_marked_completed(self, lab, db, monkeypatch):
        """成功方向同样钉死 (内审 F3): success → completed。"""
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        async def _fake_dispatch(ctx):
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr(
            "app.api.commissioning.dispatch_step", _fake_dispatch)

        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "precheck",
                  "run_by": "pytest"},
        )
        assert resp.status_code == 200, resp.text
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(resp.json()["test_execution_id"]))
            .first()
        )
        assert execution.status == "completed"
        assert execution.duration_sec is not None

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


class TestSessionsListFilter:
    def test_ad_hoc_runs_hidden_by_default(self, lab):
        """Ad-hoc rows shouldn't appear in the regular sessions list."""
        # Create a regular session via the legacy endpoint
        regular = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id), "frequency_hz": 3.5e9},
        )
        assert regular.status_code == 201
        regular_id = regular.json()["session_id"]

        # And an ad-hoc one
        adhoc = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "precheck"},
        )
        assert adhoc.status_code == 200
        adhoc_id = adhoc.json()["test_execution_id"]

        # Default list: regular present, ad-hoc absent.
        listed = client.get("/api/v1/commissioning/sessions").json()
        ids = [s["session_id"] for s in listed]
        assert regular_id in ids
        assert adhoc_id not in ids

        # include_ad_hoc=true: both present.
        full = client.get(
            "/api/v1/commissioning/sessions",
            params={"include_ad_hoc": True},
        ).json()
        ids = [s["session_id"] for s in full]
        assert regular_id in ids
        assert adhoc_id in ids


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
