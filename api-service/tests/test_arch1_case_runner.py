"""ARCH-1 S1: TestCase 直接执行 runner — 行为锁定。

核心契约 (设计稿 §2.3 + 验收):
  ① 执行 = 快照 TestCase + TestExecution(记 source_test_case_id) + 5 相位链
     (相位 dispatch mock, 执行链本体由 commissioning/P0-2 测试覆盖);
  ② 快照独立: 执行后改原用例不影响快照;
  ③ 全局单飞: case-runner 自身互斥 + 与计划 runner 互斥 + DB 双判据 → 409;
  ④ 协作式 cancel: 相位间生效, 反向判定;
  ⑤ 相位失败 → failed + failed_phase/error_message 落 config;
  ⑥ 启动复位: 只复位本 runner 的 stale running 行 (谓词收窄, 不碰暗室首测);
  ⑦ 非 MIMO_OTA → 422 (不假装执行)。

变异自验对应表 (⓪-④):
- 砍相位间 cancel 检查 → test_cancel_between_phases 红
- 砍 _active_conflict (单飞) → test_second_launch_busy / test_plan_runner_mutex 红
- 砍谓词收窄 (复位全部 running) → test_stale_reset_scoped 红
- 砍计划 start/resume 的 case 互斥 (agent F1) → test_plan_start_resume_rejected_while_case_running 红
- 砍 cancel 的 executed_by 收窄 (agent F2) → test_cancel_other_chains_rows_rejected 红
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.services.test_execution.executor_base import (
    StepExecutionResult,
    StepExecutionStatus,
)
from app.services import test_case_runner as tcr

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _db_schema(monkeypatch):
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)

    def _override():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    # 后台 task / 复位函数自建 session — 指到测试库
    monkeypatch.setattr(tcr, "SessionLocal", TestingSessionLocal)
    yield
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev
    tcr._RUNNING_TASKS.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def lab(db):
    chamber = create_chamber_from_preset(
        ChamberType.TYPE_C.value, name="CaseRunnerLab Chamber")
    db.add(chamber)
    db.commit()
    lp = LabProfile(
        name="CaseRunner-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _make_case(db, lab, name="case-A", test_type=None, **cfg_overrides):
    from app.services.mimo_ota.factory import build_mimo_ota_test_case

    tc, _ = build_mimo_ota_test_case(
        db, name=name, lab_profile_id=lab.id,
        config_overrides=cfg_overrides or {}, created_by="test",
    )
    if test_type is not None:
        tc.test_type = test_type
        db.commit()
        db.refresh(tc)
    return tc


def _ok():
    return StepExecutionResult(status=StepExecutionStatus.SUCCESS)


def _failed(msg="phase boom"):
    return StepExecutionResult(
        status=StepExecutionStatus.FAILED, error_message=msg)


async def _launch_and_wait(db, case_id):
    """launch + 等后台 task 收尾, 返回刷新后的 execution。"""
    execution = tcr.launch_test_case_execution(db, case_id)
    task = tcr._RUNNING_TASKS.get(str(execution.id))
    if task is not None:
        await task
    db.expire_all()
    return db.query(TestExecution).filter(
        TestExecution.id == execution.id).first()


# ─────────────────────────────────────────────────────────────────────
# ① 快照 + 5 相位 happy path
# ─────────────────────────────────────────────────────────────────────

class TestExecuteHappyPath:
    @pytest.mark.asyncio
    async def test_five_phases_and_snapshot(self, db, lab):
        source = _make_case(db, lab, name="正式-4方位吞吐")
        with patch.object(tcr, "dispatch_step",
                          new=AsyncMock(return_value=_ok())) as mocked:
            ex = await _launch_and_wait(db, source.id)
        assert ex.status == "completed"
        assert mocked.await_count == 5  # 5 相位全跑
        cfg = ex.config or {}
        assert cfg.get("source_test_case_id") == str(source.id)
        assert len(cfg.get("phase_progress") or []) == 5
        # 快照是独立行, 不是原用例
        assert ex.test_case_id != source.id
        snap = db.query(TestCase).filter(
            TestCase.id == ex.test_case_id).first()
        assert snap is not None and snap.created_by == tcr.RUNNER_MARKER

    @pytest.mark.asyncio
    async def test_snapshot_independent_of_source_edit(self, db, lab):
        source = _make_case(db, lab, name="快照独立", mimo_layers=2)
        with patch.object(tcr, "dispatch_step",
                          new=AsyncMock(return_value=_ok())):
            ex = await _launch_and_wait(db, source.id)
        snap = db.query(TestCase).filter(
            TestCase.id == ex.test_case_id).first()
        frozen = dict(snap.configuration or {})
        # 执行后改原用例 → 快照纹丝不动 (执行历史参数可追溯)
        src = db.query(TestCase).filter(TestCase.id == source.id).first()
        new_cfg = dict(src.configuration or {})
        new_cfg["mimo_layers"] = 4
        src.configuration = new_cfg
        db.commit()
        db.expire_all()
        snap2 = db.query(TestCase).filter(
            TestCase.id == ex.test_case_id).first()
        assert (snap2.configuration or {}) == frozen

    @pytest.mark.asyncio
    async def test_dispatch_exception_failsafe(self, db, lab):
        """dispatch 穿透异常 (非 failed 结果, 直接 raise) → 顶层兜底置
        failed + "执行器异常", 不静默消失 (agent F4②)。"""
        source = _make_case(db, lab, name="执行器异常")
        with patch.object(
            tcr, "dispatch_step",
            new=AsyncMock(side_effect=RuntimeError("boom-dispatch")),
        ):
            ex = await _launch_and_wait(db, source.id)
        assert ex.status == "failed"
        assert ex.completed_at is not None
        assert "执行器异常" in ((ex.config or {}).get("error_message") or "")
        assert "boom-dispatch" in ((ex.config or {}).get("error_message") or "")

    @pytest.mark.asyncio
    async def test_phase_failure_recorded_and_early_stop(self, db, lab):
        source = _make_case(db, lab, name="相位失败")
        # 第 2 相位失败 → 早停, 后 3 相位不跑
        results = [_ok(), _failed("REFERENCE 炸了"), _ok(), _ok(), _ok()]
        with patch.object(tcr, "dispatch_step",
                          new=AsyncMock(side_effect=results)) as mocked:
            ex = await _launch_and_wait(db, source.id)
        assert ex.status == "failed"
        assert mocked.await_count == 2
        cfg = ex.config or {}
        assert cfg.get("failed_phase") is not None
        assert "REFERENCE 炸了" in (cfg.get("error_message") or "")


# ─────────────────────────────────────────────────────────────────────
# ③ 单飞
# ─────────────────────────────────────────────────────────────────────

class TestSingleFlight:
    @pytest.mark.asyncio
    async def test_second_launch_busy(self, db, lab):
        source = _make_case(db, lab, name="单飞-A")
        other = _make_case(db, lab, name="单飞-B")
        gate = asyncio.Event()

        async def _blocking_dispatch(ctx):
            await gate.wait()
            return _ok()

        with patch.object(tcr, "dispatch_step", new=_blocking_dispatch):
            first = tcr.launch_test_case_execution(db, source.id)
            with pytest.raises(tcr.CaseRunBusy):
                tcr.launch_test_case_execution(db, other.id)
            gate.set()
            await tcr._RUNNING_TASKS[str(first.id)]

    @pytest.mark.asyncio
    async def test_plan_runner_mutex(self, db, lab, monkeypatch):
        """过渡期与计划 runner 互斥 — 双 5 相位链交错打 HAL 会互相污染。"""
        source = _make_case(db, lab, name="互斥")
        import app.services.test_plan_runner as tpr
        monkeypatch.setattr(tpr, "has_active_runner", lambda: "plan-xyz")
        with pytest.raises(tcr.CaseRunBusy):
            tcr.launch_test_case_execution(db, source.id)

    def test_plan_start_resume_rejected_while_case_running(
        self, db, lab, monkeypatch
    ):
        """互斥的反方向 (agent F1): 用例执行在跑时, 计划 start/resume 都
        409 — 否则双 5 相位链并发打同一套 HAL (变异: 砍掉端点里的
        has_active_case_run 检查 → 红, 会落到 400/其它)。"""
        monkeypatch.setattr(tcr, "has_active_case_run", lambda: "exec-xyz")
        client = TestClient(app)
        r = client.post(
            f"/api/v1/test-plans/{uuid.uuid4()}/start",
            json={"started_by": "tester"},
        )
        assert r.status_code == 409
        assert "用例执行" in r.json()["detail"]
        r2 = client.post(
            f"/api/v1/test-plans/{uuid.uuid4()}/resume",
            json={"resumed_by": "tester"},
        )
        assert r2.status_code == 409
        assert "用例执行" in r2.json()["detail"]

    @pytest.mark.asyncio
    async def test_db_dangling_running_row_blocks(self, db, lab):
        """DB 双判据: 进程标志空但 DB 有本 runner 的 running 行 → 拒。"""
        source = _make_case(db, lab, name="残留")
        db.add(TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(), executed_by=tcr.RUNNER_MARKER,
            config={"source_test_case_id": str(uuid.uuid4())},
        ))
        db.commit()
        with pytest.raises(tcr.CaseRunBusy):
            tcr.launch_test_case_execution(db, source.id)


# ─────────────────────────────────────────────────────────────────────
# ④ 协作式 cancel
# ─────────────────────────────────────────────────────────────────────

class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_between_phases(self, db, lab):
        """相位 1 期间发 cancel → 相位 2 前停下 (变异: 砍相位间检查 → 红)。"""
        source = _make_case(db, lab, name="取消")
        calls = {"n": 0}

        async def _dispatch(ctx):
            calls["n"] += 1
            if calls["n"] == 1:
                # 相位 1 执行中, 外部发 cancel (独立 session, 模拟 API)
                s2 = TestingSessionLocal()
                try:
                    ex_id = ctx.test_execution.id
                    tcr.request_cancel(s2, ex_id)
                finally:
                    s2.close()
            return _ok()

        with patch.object(tcr, "dispatch_step", new=_dispatch):
            ex = await _launch_and_wait(db, source.id)
        assert ex.status == "cancelled"
        assert calls["n"] == 1, "cancel 后相位 2 不该再跑"

    @pytest.mark.asyncio
    async def test_cancel_during_final_phase_respected(self, db, lab):
        """cancel 落在最后一个相位执行期间 → 收尾不把 cancelled 覆盖成
        completed (agent F4③: 锁住收尾"只改 config 不整行赋值"的行为,
        将来改成整行覆盖会在这红)。"""
        source = _make_case(db, lab, name="末相位取消")
        calls = {"n": 0}

        async def _dispatch(ctx):
            calls["n"] += 1
            if calls["n"] == 5:
                s2 = TestingSessionLocal()
                try:
                    tcr.request_cancel(s2, ctx.test_execution.id)
                finally:
                    s2.close()
            return _ok()

        with patch.object(tcr, "dispatch_step", new=_dispatch):
            ex = await _launch_and_wait(db, source.id)
        assert calls["n"] == 5
        assert ex.status == "cancelled", (
            "收尾把外部 cancelled 覆盖掉了 — 外部终态必须被尊重"
        )
        assert len((ex.config or {}).get("phase_progress") or []) == 5

    @pytest.mark.asyncio
    async def test_cancel_other_chains_rows_rejected(self, db, lab):
        """归属收窄 (agent F2): VRT / 计划链的 running 行不归本 cancel 管 —
        VRT 状态枚举没有 cancelled (置了会 500 毒化面板), 计划链置了也是
        假成功。端点 404, 行原样 (变异: 砍 executed_by 过滤 → 红)。"""
        source = _make_case(db, lab, name="别链行")
        vrt_like = TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(), executed_by="road_test_user",
            config={},
        )
        plan_like = TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(), executed_by="test_plan_runner",
            config={},
        )
        db.add_all([vrt_like, plan_like])
        db.commit()
        client = TestClient(app)
        for row in (vrt_like, plan_like):
            r = client.post(f"/api/v1/test-executions/{row.id}/cancel")
            assert r.status_code == 404
        db.expire_all()
        assert db.query(TestExecution).get(vrt_like.id).status == "running"
        assert db.query(TestExecution).get(plan_like.id).status == "running"

    @pytest.mark.asyncio
    async def test_cancel_non_running_returns_false(self, db, lab):
        source = _make_case(db, lab, name="取消-非running")
        with patch.object(tcr, "dispatch_step",
                          new=AsyncMock(return_value=_ok())):
            ex = await _launch_and_wait(db, source.id)
        assert ex.status == "completed"
        assert tcr.request_cancel(db, ex.id) is False


# ─────────────────────────────────────────────────────────────────────
# ⑥ 启动复位 (谓词收窄)
# ─────────────────────────────────────────────────────────────────────

class TestStaleReset:
    def test_stale_reset_scoped(self, db, lab):
        """只复位本 runner 的行; 暗室首测的 running 行不碰 (变异: 去掉
        executed_by 过滤 → 红)。"""
        source = _make_case(db, lab, name="复位")
        mine = TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(), executed_by=tcr.RUNNER_MARKER,
            config={"source_test_case_id": "x"},
        )
        theirs = TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(), executed_by="commissioning_api",
            config={},
        )
        db.add_all([mine, theirs])
        db.commit()
        mine_id, theirs_id = mine.id, theirs.id

        tcr.reset_stale_running_case_executions()

        db.expire_all()
        assert db.query(TestExecution).get(mine_id).status == "failed"
        assert db.query(TestExecution).get(theirs_id).status == "running", (
            "暗室首测的执行行被误复位 — 谓词收窄失效"
        )


# ─────────────────────────────────────────────────────────────────────
# ⑦ 端点层 (404/422/cancel 契约)
# ─────────────────────────────────────────────────────────────────────

class TestEndpoints:
    def test_execute_unknown_case_404(self):
        client = TestClient(app)
        r = client.post(f"/api/v1/test-plans/cases/{uuid.uuid4()}/execute")
        assert r.status_code == 404

    def test_execute_non_mimo_ota_422(self, db, lab):
        source = _make_case(db, lab, name="TRP例", test_type="TRP")
        client = TestClient(app)
        r = client.post(f"/api/v1/test-plans/cases/{source.id}/execute")
        assert r.status_code == 422
        assert "尚未接入" in r.json()["detail"]

    def test_execute_corrupted_configuration_422(self, db, lab):
        """建例后 configuration 被改坏 (现实输入: 手编/迁移残留) → 快照
        factory 校验 fail-loud → 422, 不产生半截执行行 (agent F4①)。"""
        source = _make_case(db, lab, name="坏配置")
        src = db.query(TestCase).filter(TestCase.id == source.id).first()
        bad = dict(src.configuration or {})
        bad["mimo_layers"] = "不是数字"
        src.configuration = bad
        db.commit()
        client = TestClient(app)
        r = client.post(f"/api/v1/test-plans/cases/{source.id}/execute")
        assert r.status_code == 422
        assert "无法构成有效执行配置" in r.json()["detail"]
        # 不留半截执行行
        leftovers = (
            db.query(TestExecution)
            .filter(TestExecution.executed_by == tcr.RUNNER_MARKER)
            .count()
        )
        assert leftovers == 0

    def test_cancel_endpoint_contract(self, db, lab):
        source = _make_case(db, lab, name="cancel端点")
        ex = TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(), executed_by=tcr.RUNNER_MARKER,
            config={},
        )
        db.add(ex)
        db.commit()
        client = TestClient(app)
        r = client.post(f"/api/v1/test-executions/{ex.id}/cancel")
        assert r.status_code == 200
        db.expire_all()
        assert db.query(TestExecution).get(ex.id).status == "cancelled"
        # 再取消 → 409 (已不在 running)
        r2 = client.post(f"/api/v1/test-executions/{ex.id}/cancel")
        assert r2.status_code == 409

    def test_status_endpoint(self, db, lab):
        source = _make_case(db, lab, name="状态端点")
        ex = TestExecution(
            test_case_id=source.id, status="failed",
            started_at=datetime.utcnow(), completed_at=datetime.utcnow(),
            executed_by=tcr.RUNNER_MARKER,
            config={
                "source_test_case_id": str(source.id),
                "phase_progress": [{"type": "MIMO_OTA_PRECHECK",
                                    "status": "success"}],
                "failed_phase": "MIMO_OTA_REFERENCE",
                "error_message": "boom",
            },
        )
        db.add(ex)
        db.commit()
        client = TestClient(app)
        r = client.get(f"/api/v1/test-plans/cases/executions/{ex.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "failed"
        assert body["failed_phase"] == "MIMO_OTA_REFERENCE"
        assert body["source_test_case_id"] == str(source.id)
        assert len(body["phase_progress"]) == 1
