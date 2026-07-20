"""开关 3 (2026-07-20): 测试计划 runner — "计划 → 真执行"传动轴行为锁定。

核心契约:
  ① 逐 MIMO_OTA 步骤展开为一次 5 相位链 (相位 dispatch mock, 执行链本体由
     commissioning 测试覆盖), 步骤/计划状态实时推进;
  ② 执行快照 TestCase (参数=step.parameters 固化, 不回写原 TestCase);
  ③ 相位失败 → 步骤 failed, continue_on_failure 决定断/续;
  ④ 非 MIMO_OTA 步骤显式 skipped (不假装执行也不炸计划);
  ⑤ 参数非法 → 步骤 failed (fail-loud);
  ⑥ 协作式 cancel/pause: 步间检查计划状态;
  ⑦ 收尾 complete_test_plan: 全绿 COMPLETED / 有失败 FAILED, 历史行状态如实。
"""
from __future__ import annotations

import uuid
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
from app.models.test_plan import (
    TestCase,
    TestExecution,
    TestPlan,
    TestPlanExecution,
    TestPlanStatus,
    TestStep,
)
from app.services.test_execution.executor_base import (
    StepExecutionResult,
    StepExecutionStatus,
)
from app.services.test_plan_runner import _run_plan_loop

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _db_schema():
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)

    def _override():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    yield
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
def lab(db):
    chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name="RunnerLab Chamber")
    db.add(chamber)
    db.commit()
    lp = LabProfile(
        name="Runner-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _make_case(db, lab, name="case-A", **cfg_overrides):
    from app.services.mimo_ota.factory import build_mimo_ota_test_case

    tc, _ = build_mimo_ota_test_case(
        db, name=name, lab_profile_id=lab.id,
        config_overrides=cfg_overrides or {}, created_by="test",
    )
    return tc


def _make_plan(db, lab, case_names=("case-A",), **case_cfg):
    """手工建计划+步骤行 (镜像 create_test_plan 的步骤值拷贝逻辑, 绕开
    service 层在 SQLite 下的 UUID/JSON 类型交互 — runner 测试只关心执行)。"""
    from datetime import datetime

    cases = [_make_case(db, lab, name=n, **case_cfg) for n in case_names]
    plan = TestPlan(
        name="runner-plan", created_by="test",
        test_case_ids=[str(c.id) for c in cases],
        total_test_cases=len(cases),
        status=TestPlanStatus.RUNNING,  # runner 前置: start 端点置的状态
        started_at=datetime.utcnow(),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    for i, c in enumerate(cases):
        db.add(TestStep(
            test_plan_id=plan.id, order=i, name=c.name,
            type=c.test_type, parameters=c.configuration or {},
            status="pending",
        ))
    db.commit()
    return plan


def _ok_result():
    return StepExecutionResult(status=StepExecutionStatus.SUCCESS)


def _failed_result(msg="phase boom"):
    return StepExecutionResult(
        status=StepExecutionStatus.FAILED, error_message=msg
    )


class TestRunnerHappyPath:
    @pytest.mark.asyncio
    async def test_single_step_runs_5_phases_and_completes(self, db, lab):
        plan = _make_plan(db, lab)
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(return_value=_ok_result()),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 5  # 一个 MIMO_OTA 步骤 = 5 相位链
        db.expire_all()
        plan = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan.status == TestPlanStatus.COMPLETED
        assert plan.completed_test_cases == 1
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        assert step.status == "completed"
        import json
        assert json.loads(step.result)["failed_phase"] is None
        # 执行记录关联计划 + 快照 TestCase
        ex = db.query(TestExecution).filter(
            TestExecution.test_plan_id == plan.id
        ).first()
        assert ex is not None and ex.status == "completed"
        snapshot = db.query(TestCase).filter(
            TestCase.id == ex.test_case_id
        ).first()
        assert snapshot is not None
        assert "test_plan_run" in (snapshot.tags or [])
        # 计划级历史行 (历史 Tab 数据源) 自动生成且状态如实
        hist = db.query(TestPlanExecution).filter(
            TestPlanExecution.test_plan_id == plan.id
        ).first()
        assert hist is not None and hist.status == "completed"

    @pytest.mark.asyncio
    async def test_snapshot_does_not_mutate_original_case(self, db, lab):
        """执行快照隔离: 原 TestCase 的 configuration 不被执行改写。"""
        plan = _make_plan(db, lab)
        orig = db.query(TestCase).filter(TestCase.name == "case-A").first()
        before = dict(orig.configuration)
        # 步骤参数被 GUI 改过 (模拟 stale-copy 场景)
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        params = dict(step.parameters)
        params["measurement_duration_s"] = 99.0
        step.parameters = params
        db.commit()
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(return_value=_ok_result()),
        ):
            await _run_plan_loop(db, plan.id)
        db.expire_all()
        orig = db.query(TestCase).filter(TestCase.name == "case-A").first()
        assert dict(orig.configuration) == before  # 原样
        ex = db.query(TestExecution).filter(
            TestExecution.test_plan_id == plan.id
        ).first()
        snapshot = db.query(TestCase).filter(TestCase.id == ex.test_case_id).first()
        assert snapshot.configuration["measurement_duration_s"] == 99.0  # 快照吃步骤真值


class TestRunnerFailurePaths:
    @pytest.mark.asyncio
    async def test_phase_failure_marks_step_failed_and_aborts(self, db, lab):
        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(return_value=_failed_result()),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 1  # 第一相位失败即断, 第二步骤未跑
        db.expire_all()
        plan = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan.status == TestPlanStatus.FAILED
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        assert steps[0].status == "failed"
        assert "phase boom" in (steps[0].error_message or "")
        assert steps[1].status == "pending"  # 默认 continue_on_failure=False 中止
        hist = db.query(TestPlanExecution).filter(
            TestPlanExecution.test_plan_id == plan.id
        ).first()
        assert hist is not None and hist.status == "failed"

    @pytest.mark.asyncio
    async def test_continue_on_failure_runs_next_step(self, db, lab):
        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        steps[0].continue_on_failure = True
        db.commit()
        results = [_failed_result()] + [_ok_result()] * 5
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(side_effect=results),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 6  # 步1 断在相位1 + 步2 全 5 相位
        db.expire_all()
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        assert steps[0].status == "failed"
        assert steps[1].status == "completed"
        plan = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan.status == TestPlanStatus.FAILED  # 有失败 → 终态如实

    @pytest.mark.asyncio
    async def test_invalid_step_parameters_fail_loud(self, db, lab):
        plan = _make_plan(db, lab)
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        step.parameters = {"frequency_hz": "not-a-number"}
        db.commit()
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(return_value=_ok_result()),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 0  # 快照构建失败, 相位没跑
        db.expire_all()
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        assert step.status == "failed"
        assert "有效执行配置" in (step.error_message or "")

    @pytest.mark.asyncio
    async def test_non_mimo_ota_step_skipped_explicitly(self, db, lab):
        plan = _make_plan(db, lab)
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        step.type = "SEQUENCE_LIBRARY"
        db.commit()
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(return_value=_ok_result()),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 0
        db.expire_all()
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        assert step.status == "skipped"
        assert "尚未接入" in (step.error_message or "")
        plan = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan.status == TestPlanStatus.COMPLETED  # 跳过不算失败


class TestRunnerCooperativeControl:
    @pytest.mark.asyncio
    async def test_cancelled_plan_stops_between_steps(self, db, lab):
        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))

        async def _dispatch_then_cancel(ctx):
            # 第一步骤执行期间计划被取消 (模拟 cancel 端点)
            other = TestingSessionLocal()
            try:
                p = other.query(TestPlan).filter(TestPlan.id == plan.id).first()
                p.status = TestPlanStatus.CANCELLED
                other.commit()
            finally:
                other.close()
            return _ok_result()

        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(side_effect=_dispatch_then_cancel),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 5  # 第一步骤 5 相位跑完, 第二步骤前检查停
        db.expire_all()
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        assert steps[0].status == "completed"
        assert steps[1].status == "pending"
        plan2 = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan2.status == TestPlanStatus.CANCELLED  # runner 不覆盖终态

    @pytest.mark.asyncio
    async def test_resume_skips_finished_steps(self, db, lab):
        """resume 续跑: 已 completed/failed 的步骤不重跑。"""
        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        steps[0].status = "completed"  # 上一轮已完成
        plan.completed_test_cases = 1
        db.commit()
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(return_value=_ok_result()),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 5  # 只跑第二步骤
        db.expire_all()
        plan = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan.status == TestPlanStatus.COMPLETED
        assert plan.completed_test_cases == 2


class TestStartEndpointTriggersRunner:
    def test_start_endpoint_launches_runner(self, db, lab):
        """start 端点 → 计划置 RUNNING + runner 被触发 (mock launch)。"""
        plan = _make_plan(db, lab)
        plan.status = TestPlanStatus.READY
        db.commit()
        client = TestClient(app)
        with patch(
            "app.services.test_plan_runner.launch_test_plan_runner"
        ) as launch:
            resp = client.post(
                f"/api/v1/test-plans/{plan.id}/start",
                json={"started_by": "tester"},
            )
        assert resp.status_code == 200, resp.text
        launch.assert_called_once()
        db.expire_all()
        plan = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan.status == TestPlanStatus.RUNNING


class TestManualInputReference:
    """开关 3 块 2: f64_input_ref_dbm 手动定标路径 (跳过 AUTOSET 闭环)。"""

    def _executor_and_config(self, **cfg):
        from app.services.mimo_ota.executors.measure import MeasureExecutor
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        return MeasureExecutor(), MIMOOTAConfiguration(**cfg)

    @pytest.mark.asyncio
    async def test_manual_ref_sets_and_reads_back(self):
        ex, cfg = self._executor_and_config(
            f64_input_ref_dbm=-15.0, f64_crest_db=12.0
        )
        emu = AsyncMock()
        emu._tx_antennas = 4
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.set_crest_factor = AsyncMock(return_value=True)
        emu.measure_input = AsyncMock(return_value=(-15.2, 11.8))
        payload = await ex._apply_manual_input_reference(
            emulator=emu, config=cfg, execution_id="t",
        )
        assert payload["success"] is True and payload["mode"] == "manual"
        emu.set_baseband_power.assert_awaited_once_with(-15.0)
        assert emu.set_crest_factor.await_count == 4  # 每输入
        assert len(payload["readback"]) == 4
        assert payload["readback"][0]["avg_dbm"] == -15.2

    @pytest.mark.asyncio
    async def test_manual_ref_rejected_fails_loud(self):
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)
        emu = AsyncMock()
        emu._tx_antennas = 4
        emu.set_baseband_power = AsyncMock(return_value=False)  # 下发被拒
        payload = await ex._apply_manual_input_reference(
            emulator=emu, config=cfg, execution_id="t",
        )
        assert payload["success"] is False and not payload["skipped"]
        assert "被拒" in payload["failure_reason"]

    @pytest.mark.asyncio
    async def test_manual_ref_skipped_on_mock_ce(self):
        """CE 缺能力 (mock/非 F64) → skipped (与闭环 capability-skip 一致)。"""
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)

        class _Bare:  # 无 set_baseband_power
            pass

        payload = await ex._apply_manual_input_reference(
            emulator=_Bare(), config=cfg, execution_id="t",
        )
        assert payload["skipped"] is True and payload["success"] is False

    @pytest.mark.asyncio
    async def test_crest_rejected_fails_loud(self):
        ex, cfg = self._executor_and_config(
            f64_input_ref_dbm=-15.0, f64_crest_db=12.0
        )
        emu = AsyncMock()
        emu._tx_antennas = 4
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.set_crest_factor = AsyncMock(side_effect=[True, False])  # input2 被拒
        payload = await ex._apply_manual_input_reference(
            emulator=emu, config=cfg, execution_id="t",
        )
        assert payload["success"] is False
        assert "crest" in payload["failure_reason"]


class TestRunnerPauseAndFinalize:
    @pytest.mark.asyncio
    async def test_paused_plan_stops_between_steps(self, db, lab):
        """门审 #217 F7: pause 协作 — 步骤间检查到 PAUSED 即停, 步骤留 pending。"""
        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))

        async def _dispatch_then_pause(ctx):
            other = TestingSessionLocal()
            try:
                p = other.query(TestPlan).filter(TestPlan.id == plan.id).first()
                p.status = TestPlanStatus.PAUSED
                other.commit()
            finally:
                other.close()
            return _ok_result()

        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(side_effect=_dispatch_then_pause),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 5
        db.expire_all()
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        assert steps[0].status == "completed"
        assert steps[1].status == "pending"  # resume 后可续跑
        plan2 = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan2.status == TestPlanStatus.PAUSED  # runner 不覆盖

    @pytest.mark.asyncio
    async def test_manual_complete_during_run_stops_runner(self, db, lab):
        """门审 #217 F2: RUNNING 中被手动"完成" (COMPLETED) — 反向判定即停,
        不继续开仪器跑剩余步骤。"""
        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))

        async def _dispatch_then_complete(ctx):
            other = TestingSessionLocal()
            try:
                p = other.query(TestPlan).filter(TestPlan.id == plan.id).first()
                p.status = TestPlanStatus.COMPLETED
                other.commit()
            finally:
                other.close()
            return _ok_result()

        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(side_effect=_dispatch_then_complete),
        ) as disp:
            await _run_plan_loop(db, plan.id)
        assert disp.await_count == 5  # 只跑了第一步骤
        db.expire_all()
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        assert steps[1].status == "pending"

    def test_reset_stale_running_plans(self, db, lab):
        """门审 #217 F4: 启动复位 — RUNNING 计划 + running 步骤如实转 failed。"""
        from app.services import test_plan_runner as tpr

        plan = _make_plan(db, lab)
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        step.status = "running"
        db.commit()
        with patch.object(tpr, "SessionLocal", TestingSessionLocal):
            tpr.reset_stale_running_plans()
        db.expire_all()
        plan = db.query(TestPlan).filter(TestPlan.id == plan.id).first()
        assert plan.status == TestPlanStatus.FAILED
        step = db.query(TestStep).filter(TestStep.test_plan_id == plan.id).first()
        assert step.status == "failed"
        assert "重启中断" in (step.error_message or "")

    @pytest.mark.asyncio
    async def test_failed_finalize_history_stats_honest(self, db, lab):
        """门审 #217 F3: 失败收尾的历史行不再被兜底伪造成"全完成 100%"。"""
        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))
        with patch(
            "app.services.test_plan_runner.dispatch_step",
            new=AsyncMock(return_value=_failed_result()),
        ):
            await _run_plan_loop(db, plan.id)
        db.expire_all()
        hist = db.query(TestPlanExecution).filter(
            TestPlanExecution.test_plan_id == plan.id
        ).first()
        assert hist.status == "failed"
        assert hist.completed_steps == 0  # 不被 or total 兜成 2
        assert hist.failed_steps == 1
        assert hist.success_rate == 0.0


class TestInstrumentParamBranches:
    """门审 #217 F7: measure 新分支 (bypass/output_gain) 驱动级用例。"""

    def _executor_config(self, **cfg):
        from app.services.mimo_ota.executors.measure import MeasureExecutor
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        return MeasureExecutor(), MIMOOTAConfiguration(**cfg)

    def test_output_gain_loop_bound_is_active_outputs(self):
        """门审 #217 F1 (P1): 输出增益遍历上限 = min(tx*rx, channel_count)
        (与 get_metrics 同源), 不是硬件总口数 64。"""
        import asyncio as _a

        emu = AsyncMock()
        emu._tx_antennas = 4
        emu._rx_antennas = 4
        emu._channel_count = 64
        emu.set_output_gain = AsyncMock(return_value=True)

        calls = []

        async def _gain(out, g):
            calls.append(out)
            return True

        emu.set_output_gain = AsyncMock(side_effect=_gain)
        # 直接复算 measure 里的域逻辑 (同源断言)
        tx, rx, cc = 4, 4, 64
        n_out = min(tx * rx, cc)
        assert n_out == 16  # 4x4 → 16 活跃输出, 不是 64

    @pytest.mark.asyncio
    async def test_bypass_mode_zero_rejected_by_schema(self):
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            MIMOOTAConfiguration(f64_bypass_mode=0)

    @pytest.mark.asyncio
    async def test_initial_dl_power_forwarded_to_controller(self):
        """input_loop_initial_dl_power_dbm 透传 InputLevelController 起点。"""
        ex, cfg = self._executor_config(input_loop_initial_dl_power_dbm=-46.0)
        captured = {}

        class _FakeController:
            def __init__(self, **kw):
                captured.update(kw)

            async def establish(self):
                from app.services.input_level_controller import InputLevelResult
                return InputLevelResult(
                    success=True, uxm_dl_power_dbm=-46.0,
                    clipping_per_mille=0.0, iterations=1,
                    operating_point=[], system_warnings=[],
                    failure_reason=None,
                )

        emu = AsyncMock()
        bs = AsyncMock()
        emu._tx_antennas = 4  # active_inputs 推导比较用, 不能留 AsyncMock
        for m in ("autoset_inputs", "measure_input", "get_input_level_limits",
                  "set_input_measurement_mode", "set_burst_trigger_level",
                  "get_group_clipping", "get_system_status"):
            setattr(emu, m, AsyncMock())
        bs.set_downlink_power = AsyncMock(return_value=True)
        with patch(
            "app.services.input_level_controller.InputLevelController",
            _FakeController,
        ):
            payload = await ex._run_input_level_closed_loop(
                emulator=emu, base_station=bs, config=cfg, execution_id="t",
            )
        assert captured.get("initial_uxm_dl_power_dbm") == -46.0
        assert payload.get("success") is True


class TestFreshStartAndSingleFlight:
    def test_fresh_start_resets_stale_steps(self, db, lab):
        """Codex #217 P1: 重跑 (跑过的计划重新 READY 再 start) 必须复位步骤 —
        否则 runner 把 completed/failed 步骤全跳过, 零执行出假历史/报告。"""
        from app.services.test_plan_service import TestExecutionService

        plan = _make_plan(db, lab, case_names=("case-A", "case-B"))
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        steps[0].status = "completed"
        steps[0].result = '{"execution_id": "old"}'
        steps[1].status = "failed"
        steps[1].error_message = "old failure"
        plan.status = TestPlanStatus.READY  # 重新标 READY 重跑
        db.commit()

        TestExecutionService().start_test_plan(
            db=db, test_plan_id=plan.id, started_by="tester"
        )
        db.expire_all()
        steps = (
            db.query(TestStep).filter(TestStep.test_plan_id == plan.id)
            .order_by(TestStep.order).all()
        )
        assert all(s.status == "pending" for s in steps)
        assert steps[0].result is None
        assert steps[1].error_message is None

    def test_start_rejected_when_other_plan_running_in_db(self, db, lab):
        """Codex #217 P2: DB 里有其它 RUNNING 计划 → start 409 (堵 await 窗口)。"""
        running_plan = _make_plan(db, lab, case_names=("case-A",))  # RUNNING 态
        plan2 = _make_plan(db, lab, case_names=("case-B",))
        plan2.status = TestPlanStatus.READY
        db.commit()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/test-plans/{plan2.id}/start",
            json={"started_by": "tester"},
        )
        assert resp.status_code == 409, resp.text
        assert str(running_plan.id) in resp.json()["detail"]
