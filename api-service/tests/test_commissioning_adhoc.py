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
from contextlib import asynccontextmanager
from datetime import datetime

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
from app.models.alert import Alert
from app.models.lab_profile import LabProfile
from app.models.instrument import InstrumentCategory, InstrumentConnection
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
def setup_db(monkeypatch):
    Base.metadata.create_all(bind=engine)
    from app.hal import MockBaseStation
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    saved_base_station = hal.drivers.get("baseStation")
    hal.drivers["baseStation"] = MockBaseStation("mock-bs", {"model": "Mock"})
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "app.services.execution_failure_alerts.SessionLocal",
        TestingSessionLocal,
    )
    try:
        yield
    finally:
        if saved_base_station is None:
            hal.drivers.pop("baseStation", None)
        else:
            hal.drivers["baseStation"] = saved_base_station
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
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="基站仿真器",
        driver_mode="mock",
        is_active=True,
    )
    db.add(category)
    db.flush()
    db.add(InstrumentConnection(
        category_id=category.id,
        endpoint=None,
        connection_params=None,
        created_by="test",
    ))
    lp = LabProfile(
        name="P3-Phase3-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[{
            "category_id": str(category.id),
            "instrument_model_id": None,
            "connection_endpoint": None,
            "driver_mode": "mock",
            "role": "baseStation",
        }],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


class TestAdhocPhaseEndpoint:
    def test_adhoc_phase_holds_instrument_lease(self, lab, monkeypatch):
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        events = []

        @asynccontextmanager
        async def _lease(purpose, **_kwargs):
            events.append(f"enter:{purpose}")
            try:
                yield
            finally:
                events.append("exit")

        async def _dispatch(_ctx):
            events.append("dispatch")
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr(
            "app.api.commissioning.instrument_test_lease", _lease, raising=False
        )
        monkeypatch.setattr("app.api.commissioning.dispatch_step", _dispatch)

        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "precheck"},
        )

        assert resp.status_code == 200, resp.text
        assert events == ["enter:commissioning-adhoc:precheck", "dispatch", "exit"]

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

    def test_report_phase_preserves_executor_owned_terminal_lifecycle(
        self, lab, db, monkeypatch
    ):
        """REPORT 已裁决的终态/时间不得被 adhoc 包装层用请求耗时覆盖。"""
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        terminal_at = datetime(2026, 8, 22, 3, 4, 5)
        events = []

        @asynccontextmanager
        async def _lease(_purpose, **_kwargs):
            events.append("lease-enter")
            try:
                yield
            finally:
                events.append("lease-exit")

        async def _fake_dispatch(ctx):
            events.append("report-dispatch")
            ctx.test_execution.status = "completed"
            ctx.test_execution.completed_at = terminal_at
            ctx.test_execution.duration_sec = 89.195194
            ctx.db.commit()
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr(
            "app.api.commissioning.instrument_test_lease", _lease, raising=False
        )
        monkeypatch.setattr("app.api.commissioning.dispatch_step", _fake_dispatch)

        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "report"},
        )
        assert resp.status_code == 200, resp.text
        execution = db.get(
            TestExecution, uuid.UUID(resp.json()["test_execution_id"])
        )
        assert execution.status == "completed"
        assert execution.completed_at == terminal_at
        assert execution.duration_sec == pytest.approx(89.195194)
        assert events == ["lease-enter", "lease-exit", "report-dispatch"]

    def test_phase_local_handoff_failure_persists_failed_truth(
        self, lab, db, monkeypatch
    ):
        from app.services.instrument_test_lease import (
            InstrumentTestLeaseReleaseError,
        )
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        @asynccontextmanager
        async def _lease(_purpose, **_kwargs):
            yield
            raise InstrumentTestLeaseReleaseError("UXM Local 交接失败")

        async def _dispatch(_ctx):
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="预检业务失败",
            )

        monkeypatch.setattr(
            "app.api.commissioning.instrument_test_lease", _lease, raising=False
        )
        monkeypatch.setattr("app.api.commissioning.dispatch_step", _dispatch)
        sess = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id)},
        )
        sid = sess.json()["session_id"]

        resp = client.post(
            f"/api/v1/commissioning/sessions/{sid}/phase/precheck"
        )

        assert resp.status_code == 409, resp.text
        assert "UXM Local 交接失败" in resp.json()["detail"]
        assert "预检业务失败" in resp.json()["detail"]
        db.expire_all()
        execution = db.get(TestExecution, uuid.UUID(sid))
        assert execution.status == "failed"
        assert "UXM Local 交接失败" in execution.error_message
        assert "预检业务失败" in execution.error_message
        assert (execution.config or {})["local_control_handoff_failed"] is True
        assert db.query(Alert).filter(
            Alert.related_entity_id == execution.id,
        ).count() == 1

    def test_adhoc_handoff_failure_response_and_audit_keep_business_error(
        self, lab, db, monkeypatch
    ):
        from app.services.instrument_test_lease import (
            InstrumentTestLeaseReleaseError,
        )
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        @asynccontextmanager
        async def _lease(_purpose, **_kwargs):
            yield
            raise InstrumentTestLeaseReleaseError("UXM Local 交接失败")

        async def _dispatch(_ctx):
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="adhoc 业务失败",
            )

        monkeypatch.setattr(
            "app.api.commissioning.instrument_test_lease", _lease, raising=False
        )
        monkeypatch.setattr("app.api.commissioning.dispatch_step", _dispatch)

        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "precheck"},
        )

        assert resp.status_code == 200, resp.text
        assert "UXM Local 交接失败" in resp.json()["error_message"]
        assert "adhoc 业务失败" in resp.json()["error_message"]
        audit = db.get(
            DiagnosticRun,
            uuid.UUID(resp.json()["diagnostic_run_id"]),
        )
        assert "adhoc 业务失败" in audit.error_message
        assert "adhoc 业务失败" in audit.output_excerpt

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
    def test_ad_hoc_runs_hidden_by_default(self, lab, db):
        """Ad-hoc rows shouldn't appear in the regular sessions list."""
        # Create a regular session via the legacy endpoint
        regular = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id), "frequency_hz": 3.5e9},
        )
        assert regular.status_code == 201
        regular_id = regular.json()["session_id"]
        regular_execution = db.query(TestExecution).filter(
            TestExecution.id == uuid.UUID(regular_id)
        ).first()
        assert (regular_execution.config or {}).get("managed_rf_attach") is True, (
            "暗室首测与测试管理必须复用按 TestCase 初始化后受控 attach 的标准流程"
        )

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


class TestExecutionStatusVisibleToReloadGate:
    def test_saved_session_single_phase_holds_instrument_lease(
        self, lab, monkeypatch
    ):
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        events = []

        @asynccontextmanager
        async def _lease(purpose, **_kwargs):
            events.append(f"enter:{purpose}")
            try:
                yield
            finally:
                events.append("exit")

        async def _dispatch(ctx):
            events.append(f"dispatch:{ctx.step.type}")
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr(
            "app.api.commissioning.instrument_test_lease", _lease, raising=False
        )
        monkeypatch.setattr("app.api.commissioning.dispatch_step", _dispatch)
        sess = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id)},
        )
        sid = sess.json()["session_id"]

        resp = client.post(
            f"/api/v1/commissioning/sessions/{sid}/phase/precheck"
        )

        assert resp.status_code == 200, resp.text
        assert events == [
            f"enter:commissioning-phase:{sid}:precheck",
            "dispatch:MIMO_OTA_PRECHECK",
            "exit",
        ]

    def test_run_all_holds_one_lease_across_every_phase(self, lab, monkeypatch):
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        events = []

        @asynccontextmanager
        async def _lease(purpose, **_kwargs):
            events.append(f"enter:{purpose}")
            try:
                yield
            finally:
                events.append("exit")

        async def _dispatch(ctx):
            events.append(f"dispatch:{ctx.step.type}")
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr(
            "app.api.commissioning.instrument_test_lease", _lease, raising=False
        )
        monkeypatch.setattr("app.api.commissioning.dispatch_step", _dispatch)
        sess = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id)},
        )
        sid = sess.json()["session_id"]

        resp = client.post(f"/api/v1/commissioning/sessions/{sid}/run-all")

        assert resp.status_code == 200, resp.text
        assert events[0] == f"enter:commissioning-run-all:{sid}"
        assert events[-2:] == ["exit", "dispatch:MIMO_OTA_REPORT"]
        assert len([event for event in events if event.startswith("dispatch:")]) == 5
    """ARCH-1 S3: 三个 commissioning 入口在跑相位期间必须把行标 running,
    否则 HAL reload 闸门看不见它们 (现场最常用的链会裸奔)。

    变异: 砍 _execution_marked_running / 砍 adhoc 的 running 写入 → 各红。
    """

    def test_adhoc_marks_running_during_dispatch(self, lab, db, monkeypatch):
        """生效端断言: 在 dispatch 那一刻去查库, 行必须是 running
        (不是查跑完之后的终态 —— 那证明不了闸门期间看得见)。"""
        seen = {}

        async def _fake_dispatch(ctx):
            probe = TestingSessionLocal()
            try:
                row = (
                    probe.query(TestExecution)
                    .filter(TestExecution.id == ctx.test_execution.id)
                    .first()
                )
                seen["status"] = row.status if row else None
            finally:
                probe.close()
            from app.services.test_execution.executor_base import (
                StepExecutionResult,
                StepExecutionStatus,
            )
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr(
            "app.api.commissioning.dispatch_step", _fake_dispatch)

        resp = client.post(
            "/api/v1/commissioning/diagnostic/run-phase",
            json={"lab_profile_id": str(lab.id), "phase_name": "precheck",
                  "run_by": "pytest"},
        )
        assert resp.status_code == 200, resp.text
        assert seen.get("status") == "running", (
            "相位执行期间行不是 running — HAL reload 闸门看不见这条链"
        )

    def test_stale_running_commissioning_rows_are_reset(self, lab, db, monkeypatch):
        """闸门变严的配套: 进程重启留下的僵尸 running 行必须被复位,
        否则会**永久拦死** reload (比原来的空窗更难受)。"""
        import app.api.commissioning as comm
        from app.api.commissioning import (
            reset_stale_running_commissioning_executions,
        )

        # 复位函数自建 session — 指到测试库 (与 case-runner 测试同法)
        monkeypatch.setattr(comm, "SessionLocal", TestingSessionLocal)

        rows = []
        for marker in ("commissioning_api", "commissioning_adhoc"):
            ex = TestExecution(
                id=uuid.uuid4(), status="running", executed_by=marker,
                started_at=datetime.utcnow(),
            )
            db.add(ex)
            rows.append(ex)
        # 不该被这条复位碰的: 别人家的链 (各链自管各的复位语义)
        other = TestExecution(
            id=uuid.uuid4(), status="running", executed_by="test_case_runner",
            started_at=datetime.utcnow(),
        )
        db.add(other)
        db.commit()

        reset_stale_running_commissioning_executions()

        for ex in rows:
            db.refresh(ex)
            assert ex.status == "failed", f"{ex.executed_by} 的僵尸行没被复位"
            assert ex.completed_at is not None
        assert db.query(Alert).filter(
            Alert.related_entity_id == rows[0].id,
        ).count() == 1
        assert db.query(Alert).filter(
            Alert.related_entity_id == rows[1].id,
        ).count() == 0, "commissioning_adhoc 调试失败不应进入正式活动告警"
        db.refresh(other)
        assert other.status == "running", "越界复位了别的链的行"

    def test_run_all_marks_running_and_gate_sees_it(self, lab, db, monkeypatch):
        """内审 F2: 本 PR 的主机制 (run-all 期间标 running) 此前无门 ——
        把 _execution_marked_running 整段 no-op 掉, 41 个测试照样全绿。
        生效端断言: 相位跑到一半时**闸门真看得见** (不是查行状态字符串)。
        """
        from app.services.hal_reload_policy import find_execution_blockers

        seen = {}

        async def _fake_dispatch(ctx):
            probe = TestingSessionLocal()
            try:
                seen["blockers"] = len(find_execution_blockers(probe))
            finally:
                probe.close()
            from app.services.test_execution.executor_base import (
                StepExecutionResult, StepExecutionStatus,
            )
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr("app.api.commissioning.dispatch_step", _fake_dispatch)
        sess = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id), "precheck_strict_cal": False,
                  "precheck_strict_dut": False},
        )
        assert sess.status_code in (200, 201), sess.text
        sid = sess.json()["session_id"]

        resp = client.post(f"/api/v1/commissioning/sessions/{sid}/run-all")
        assert resp.status_code == 200, resp.text
        assert seen.get("blockers", 0) >= 1, (
            "run-all 相位期间 HAL reload 闸门看不见这条链 — 暗室首测裸奔"
        )

    def test_run_all_local_handoff_failure_is_failed_not_pending(
        self, lab, db, monkeypatch
    ):
        from app.services.instrument_test_lease import (
            InstrumentTestLeaseReleaseError,
        )
        from app.services.test_execution.executor_base import (
            StepExecutionResult,
            StepExecutionStatus,
        )

        @asynccontextmanager
        async def _lease(_purpose, **_kwargs):
            yield
            raise InstrumentTestLeaseReleaseError("F64 Local 交接失败")

        async def _dispatch(_ctx):
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="链路业务失败",
            )

        monkeypatch.setattr(
            "app.api.commissioning.instrument_test_lease", _lease, raising=False
        )
        monkeypatch.setattr("app.api.commissioning.dispatch_step", _dispatch)
        sess = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id)},
        )
        sid = sess.json()["session_id"]

        resp = client.post(f"/api/v1/commissioning/sessions/{sid}/run-all")

        assert resp.status_code == 409, resp.text
        assert "F64 Local 交接失败" in resp.json()["detail"]
        assert "链路业务失败" in resp.json()["detail"]
        db.expire_all()
        execution = db.get(TestExecution, uuid.UUID(sid))
        assert execution.status == "failed"
        assert "F64 Local 交接失败" in execution.error_message
        assert "链路业务失败" in execution.error_message
        assert (execution.config or {})["local_control_handoff_failed"] is True
        assert db.query(Alert).filter(
            Alert.related_entity_id == execution.id,
        ).count() == 1

    def test_run_all_aborted_chain_is_failed_not_completed(
        self, lab, db, monkeypatch
    ):
        """内审 F1: 中途 failed 会 break 而**不抛异常** (dispatch_step 从不
        上抛), 拿"没异常"当成功判据会把中止的会话记成 completed —— 它会
        混进待归档报告列表、被算进成功率。
        变异 = 把终态交回 contextmanager 的"无异常即 completed" → 本条红。
        """
        calls = {"n": 0}

        async def _fake_dispatch(ctx):
            from app.services.test_execution.executor_base import (
                StepExecutionResult, StepExecutionStatus,
            )
            calls["n"] += 1
            if calls["n"] == 2:  # 第二个相位失败 → 链中止
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message="参考功率偏差超限",
                )
            return StepExecutionResult(status=StepExecutionStatus.SUCCESS)

        monkeypatch.setattr("app.api.commissioning.dispatch_step", _fake_dispatch)
        sess = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id), "precheck_strict_cal": False,
                  "precheck_strict_dut": False},
        )
        sid = sess.json()["session_id"]
        client.post(f"/api/v1/commissioning/sessions/{sid}/run-all")

        row = (
            db.query(TestExecution)
            .filter(TestExecution.id == uuid.UUID(sid))
            .first()
        )
        db.refresh(row)
        assert row.status == "failed", (
            f"中止的链被记成 {row.status!r} — 会混进待归档报告并算进成功率"
        )
        assert "中止" in (row.error_message or "")
        alert = db.query(Alert).filter(
            Alert.alert_type == "execution_failed",
            Alert.related_entity_id == row.id,
        ).one()
        assert alert.status == "active"
        assert alert.source == "commissioning_api"

    def test_commissioning_endpoints_reject_other_chains_rows(self, lab, db):
        """内审 F5: 用例执行的快照用例同样是 MIMO_OTA, 拿它的 execution id
        打 run-all 会并发同一套 HAL 且改写它的终态 (case-runner 下个相位
        边界看到非 running 就静默 return, 正式测试无声中断)。
        变异 = 砍 _resolve_execution 的 executed_by 收窄 → 本条红。
        """
        foreign = TestExecution(
            id=uuid.uuid4(), status="running",
            executed_by="test_case_runner",  # 别的链
            config={"step_descriptors": []},
        )
        db.add(foreign)
        db.commit()

        for path in ("/run-all", "/phase/precheck"):
            resp = client.post(
                f"/api/v1/commissioning/sessions/{foreign.id}{path}")
            assert resp.status_code == 404, (
                f"{path} 放行了别的链的执行行: {resp.status_code}"
            )
        db.refresh(foreign)
        assert foreign.status == "running", "别的链的行被改写了"

    def test_concurrent_phase_on_same_session_rejected(self, lab, db):
        """Codex #242 C2: 并发相位打同一 session 会让第一个退出时把行恢复
        成 pending, 而第二个还在用 HAL → reload 保护提前失效。用 DB 状态
        当判据拒绝并发 (跨 worker 可见, 不引进程内锁)。
        变异 = 砍掉进入时的 running 检查 → 本条红。
        """
        sess = client.post(
            "/api/v1/commissioning/sessions",
            json={"lab_profile_id": str(lab.id), "precheck_strict_cal": False,
                  "precheck_strict_dut": False},
        )
        sid = sess.json()["session_id"]
        # 模拟"已有相位在跑": 行处于 running
        row = db.query(TestExecution).filter(
            TestExecution.id == uuid.UUID(sid)).first()
        row.status = "running"
        db.commit()

        for path in ("/run-all", "/phase/precheck"):
            resp = client.post(f"/api/v1/commissioning/sessions/{sid}{path}")
            assert resp.status_code == 409, (
                f"{path} 放行了并发相位: {resp.status_code}"
            )
            assert "已有相位在执行中" in resp.json()["detail"]

    def test_list_sessions_matches_addressable_routes(self, lab, db):
        """Codex #242 C3: 列表与详情/执行路由必须同源 —— 否则 case-runner
        的行列得出来、点进去却 404 ("列得出、点不动")。
        变异 = 砍 list_sessions 的链谓词 → 本条红。
        """
        from app.services.mimo_ota.factory import build_mimo_ota_test_case

        snapshot, _ = build_mimo_ota_test_case(
            db, name="用例执行快照", lab_profile_id=lab.id,
            config_overrides={}, created_by="test",
        )
        foreign = TestExecution(
            id=uuid.uuid4(), test_case_id=snapshot.id, status="completed",
            executed_by="test_case_runner",
            config={"source_test_case_id": str(snapshot.id)},  # 无 ad_hoc/step 标记
        )
        db.add(foreign)
        db.commit()

        listed = client.get("/api/v1/commissioning/sessions").json()
        listed_ids = {s["session_id"] for s in listed}
        assert str(foreign.id) not in listed_ids, (
            "别的链的执行被列进会话列表 — 点进去会 404"
        )
        # 生效端交叉验证: 列出来的每一个都必须真能取到详情
        for sid in listed_ids:
            r = client.get(f"/api/v1/commissioning/sessions/{sid}")
            assert r.status_code == 200, f"列表里的 {sid} 取详情 {r.status_code}"
