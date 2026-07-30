"""ARCH-1 S1: TestCase 直接执行 runner — 行为锁定。

核心契约 (设计稿 §2.3 + 验收):
  ① 执行 = 快照 TestCase + TestExecution(记 source_test_case_id) + 5 相位链
     (相位 dispatch mock, 执行链本体由 commissioning/P0-2 测试覆盖);
  ② 快照独立: 执行后改原用例不影响快照;
  ③ 全局单飞: case-runner 自身互斥 + DB 双判据 → 409 (S4b: 与计划 runner 互斥那半边随计划链删);
  ④ 协作式 cancel: 相位间生效, 反向判定;
  ⑤ 相位失败 → failed + failed_phase/error_message 落 config;
  ⑥ 启动复位: 只复位本 runner 的 stale running 行 (谓词收窄, 不碰暗室首测);
  ⑦ 非 MIMO_OTA → 422 (不假装执行)。

变异自验对应表 (⓪-④):
- 砍相位间 cancel 检查 → test_cancel_between_phases 红
- 砍 _active_conflict (单飞) → test_second_launch_busy 红
- 砍谓词收窄 (复位全部 running) → test_stale_reset_scoped 红
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

    # ARCH-1 S4b: test_plan_runner_mutex 随计划链删除 —— 它断言的是
    # _active_conflict 里"计划 runner 在跑就拒"那个分支, 而计划 runner 已不存在。
    # 反方向那条 (test_plan_start_resume_rejected_while_case_running) 测的是
    # 计划 start/resume 端点, 随 B2 删路由时一并删。

    # ARCH-1 S4b: test_plan_start_resume_rejected_while_case_running 随计划
    # start/resume 端点一并删除 (互斥的反方向 —— 计划端点已不存在)。

    # ARCH-1 S4b: test_plan_start_rejected_by_db_case_row 随计划
    # start/resume 端点一并删除 (互斥的反方向 —— 计划端点已不存在)。

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
        """cancel 落在最后一个相位 (REPORT) 执行期间 → 终态必须是 cancelled
        (agent F4③ + Codex #237 C5)。fake 复刻真 REPORT executor 的关键行为:
        它会把 execution.status 直接写 "completed" 并 commit (report.py
        "Mark execution lifecycle complete"), 把 cancel 端点刚写的 cancelled
        覆盖掉 — 收尾必须凭 config.cancel_requested 痕迹救回。
        变异: 砍收尾的 cancel_requested 检查 → 本测试红 (终态错成 completed)。"""
        source = _make_case(db, lab, name="末相位取消")
        calls = {"n": 0}

        async def _dispatch(ctx):
            calls["n"] += 1
            if calls["n"] == 5:
                # 先到 cancel (独立 session, 模拟 API)
                s2 = TestingSessionLocal()
                try:
                    tcr.request_cancel(s2, ctx.test_execution.id)
                finally:
                    s2.close()
                # 再复刻真 REPORT executor: 同 runner session 直接覆盖 status
                from datetime import datetime as _dt
                ctx.test_execution.status = "completed"
                ctx.test_execution.completed_at = _dt.utcnow()
                ctx.db.commit()
            return _ok()

        with patch.object(tcr, "dispatch_step", new=_dispatch):
            ex = await _launch_and_wait(db, source.id)
        assert calls["n"] == 5
        assert ex.status == "cancelled", (
            "REPORT executor 把 cancelled 覆盖成 completed 后收尾没救回 — "
            "取消不许被相位收尾吃掉"
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
# 门 D-i (ARCH-1 S4b): 计划链遗留僵尸行 —— 三类全清
# ─────────────────────────────────────────────────────────────────────

class TestOrphanedPlanChainReset:
    """S4b 删掉 test_plan_runner 后, 它的启动复位职责由本模块接管。

    ⚠️ 是**三类**行不是一类 —— 原 reset_stale_running_plans 复位 TestPlan /
    TestStep / TestExecution 三种, 设计稿 v1 只想到第三种。
    后果不对称, 前两类更难受: 第三类卡 HAL reload 闸门 (409, 但 blocker
    列表里看得见); 前两类被 dashboard 计进 active_test_plans, 而 S4b 之后
    **已经没有 cancel/complete 端点能改回来** → 永久残留无法自愈。

    变异实跑 (⓪-④):
      - 只复位 execution 行 (设计稿 v1 的方案) → 本测试 ①② 断言红
      - 谓词写成"所有 running 执行行"(不按 executed_by 收窄) → 隔离断言红
    """

    def test_three_row_types_all_reset(self, db, lab):
        from app.models.test_plan import (
            TestPlan, TestPlanStatus, TestStep, TestExecution,
        )

        source = _make_case(db, lab, name="僵尸行清理")

        # ① 卡 RUNNING 的计划
        plan = TestPlan(
            name="进程重启遗留的计划",
            test_case_ids=[str(source.id)],
            status=TestPlanStatus.RUNNING,
            created_by="test_plan_runner",
        )
        # ①b **PAUSED 也算**。S4b 内审 F1 抓到时的理由是"HAL 闸门认两态",
        # 而 S4c 已把闸门的计划半截删掉 —— **理由换了, 结论没换**:
        # 现在两态都清是为了让封存表的数据如实 (一行永远写着 paused 的计划
        # 是个谎), 且这正是 S4c 敢删闸门计划半截的前提。
        paused_plan = TestPlan(
            name="brownfield 暂停计划",
            test_case_ids=[str(source.id)],
            status=TestPlanStatus.PAUSED,
            created_by="test_plan_runner",
        )
        db.add_all([plan, paused_plan])
        db.commit()
        db.refresh(plan)
        db.refresh(paused_plan)

        # ② 该计划下卡 running 的步骤
        step = TestStep(
            test_plan_id=plan.id,
            name="遗留步骤",
            type="MIMO_OTA",
            parameters={},
            order=0,
            status="running",
        )
        # ③ 计划 runner 写的、卡 running 的执行行
        legacy_exec = TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(),
            executed_by=tcr.LEGACY_PLAN_RUNNER_MARKER,
            config={},
        )
        # 隔离对照: 暗室首测的 running 行不该被这个函数碰
        commissioning_exec = TestExecution(
            test_case_id=source.id, status="running",
            started_at=datetime.utcnow(), executed_by="commissioning_api",
            config={},
        )
        db.add_all([step, legacy_exec, commissioning_exec])
        db.commit()
        plan_id, step_id, paused_id = plan.id, step.id, paused_plan.id
        legacy_id, commissioning_id = legacy_exec.id, commissioning_exec.id

        tcr.reset_orphaned_plan_chain_rows()

        db.expire_all()
        assert db.query(TestPlan).get(plan_id).status == TestPlanStatus.FAILED, (
            "① RUNNING 计划没被复位 —— 它会被 dashboard 计进 active_test_plans, "
            "而 S4b 之后没有任何端点能把它改回来"
        )
        assert db.query(TestPlan).get(paused_id).status == TestPlanStatus.FAILED, (
            "①b PAUSED 计划没被复位 —— 封存表里留下一行永远写着 paused 的"
            "计划是个谎; 且这条复位是 S4c 敢删掉闸门计划半截的前提"
        )
        assert db.query(TestStep).get(step_id).status == "failed", (
            "② running 步骤没被复位 (同① 无端点可自愈)"
        )
        assert db.query(TestExecution).get(legacy_id).status == "failed", (
            "③ 计划 runner 的 running 执行行没被复位 —— 会永久 409 拦住 HAL reload"
        )
        assert (
            db.query(TestExecution).get(commissioning_id).status == "running"
        ), "暗室首测的执行行被误复位 —— 谓词收窄失效"

    def test_lifespan_wiring_clears_blockers(self, db, lab):
        """打在**生效端**, 而且走**真实 lifespan** (内审 F5)。

        为什么不直调 helper: main.py 里那个调用包在 try/except 里 —— 函数改名 /
        移模块 / import 打错, 启动只打一句 warning, 僵尸行永不复位、HAL reload
        永久 409, 而直调 helper 的断言**全绿**。设计稿 §4 风险 2 点名的正是
        这一处"删错了但一切照跑"。所以断言必须穿过 with TestClient(app)。
        """
        from app.models.test_plan import TestExecution
        from app.services.hal_reload_policy import find_reload_blockers

        source = _make_case(db, lab, name="闸门")
        from app.models.test_plan import TestPlan, TestPlanStatus
        db.add_all([
            TestExecution(
                test_case_id=source.id, status="running",
                started_at=datetime.utcnow(),
                executed_by=tcr.LEGACY_PLAN_RUNNER_MARKER, config={},
            ),
            TestPlan(
                name="暂停的僵尸计划", test_case_ids=[str(source.id)],
                status=TestPlanStatus.PAUSED, created_by="test_plan_runner",
            ),
        ])
        db.commit()

        assert find_reload_blockers(db), (
            "前提不成立: 僵尸行本应拦住 HAL reload (S3a 闸门), 这条测试才有意义"
        )

        with TestClient(app):   # 走真实启动流程 (lifespan 里那串复位)
            pass
        db.expire_all()

        assert not find_reload_blockers(db), (
            "过完真实 lifespan 后 HAL reload 仍被拦 —— 要么复位没接进 lifespan "
            "(main.py 的 try/except 把接线错误吞成 warning), 要么谓词跟闸门不同源"
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
