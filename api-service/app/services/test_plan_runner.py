"""测试计划执行 runner — "正常测试流程"的传动轴 (开关 3, 2026-07-20)。

现状缺口: POST /test-plans/{id}/start 只把计划置 RUNNING, 步骤永停 pending —
计划与执行之间没有"照单干活"的环节。本模块补上:

  逐 MIMO_OTA 步骤 → 执行快照 TestCase (参数 = 步骤编辑真值 step.parameters)
  → TestExecution(test_plan_id 关联) → 5 相位链 (precheck/reference/mimo_test/
  analysis/report, 与 commissioning run-all **同一套 executors**) → 步骤/计划
  状态实时推进 → complete_test_plan 收尾 (计划级历史 + 自动报告)。

设计要点:
- **执行快照 TestCase** (build_mimo_ota_test_case): 步骤参数在执行时刻固化成
  独立 TestCase 行, 不回写原 TestCase — 多计划共享同一测试例互不污染
  (P2-16 stale-copy 教训); lab/证书由 factory 解析 (active lab 兜底)。
- **协作式 pause/cancel**: 每步开始前 refresh 计划状态 — PAUSED 停在步间
  (resume 端点重新触发, 续跑跳过非 pending 步骤), CANCELLED 中止。
- **fail-loud**: 参数校验失败 / 任一相位 FAILED → 步骤 failed + error_message;
  `step.continue_on_failure` 决定断/续 (默认断)。
- 非 MIMO_OTA 步骤标 skipped + 告警 (序列库步骤的执行是后续工作, 不静默
  假装跑过, 也不炸整计划)。
- 后台任务自建 DB session (请求 session 在响应后已关)。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.test_plan import (
    TestExecution,
    TestPlan,
    TestPlanStatus,
    TestStep,
)
from app.services.mimo_ota.factory import build_mimo_ota_test_case
from app.services.test_execution.hydrate import build_step_context
from app.services.test_execution.registry import dispatch_step

logger = logging.getLogger(__name__)

MIMO_OTA_STEP_TYPE = "MIMO_OTA"

# 模块级任务表: 防同计划并发 runner + 持有引用防 GC 回收 asyncio task。
_RUNNING_TASKS: Dict[str, "asyncio.Task[None]"] = {}


def has_active_runner() -> Optional[str]:
    """门审 #217 F8: 全局单飞 — 返回当前活跃 runner 的 plan_id (无则 None)。

    两个计划并发执行会让双 5 相位链交错打同一套 HAL (驱动层互斥锁只保
    命令级不保执行语义, 实验互相污染)。start/resume 端点在置状态前调本
    函数, 有活跃 runner 即拒 409。单 worker 部署 (docker-entrypoint 无
    --workers) 下模块级状态够用。
    """
    for key, task in _RUNNING_TASKS.items():
        if not task.done():
            return key
    return None


def launch_test_plan_runner(plan_id: UUID) -> bool:
    """start/resume 端点调用: 后台启动计划 runner。

    Returns False (不启动) 当同计划已有 runner 在跑 — start_test_plan 的
    状态校验 (READY/QUEUED→RUNNING) 已挡重复 start, 这里是 resume 竞态与
    进程内二次触发的兜底。
    """
    key = str(plan_id)
    existing = _RUNNING_TASKS.get(key)
    if existing is not None and not existing.done():
        logger.warning("[runner] plan %s 已有 runner 在跑, 忽略重复触发", key)
        return False
    # 调用方必须在事件循环内 (async 端点); 同步端点在线程池里没有 loop,
    # get_running_loop 会 fail-loud 而不是静默拿错 loop
    task = asyncio.get_running_loop().create_task(run_test_plan(plan_id))
    _RUNNING_TASKS[key] = task
    task.add_done_callback(lambda _t, _k=key: _RUNNING_TASKS.pop(_k, None))
    return True


def reset_stale_running_plans() -> None:
    """门审 #217 F4: 进程启动时复位无 runner 的 stale RUNNING 计划。

    真硬件步骤 30min+ 期间重启 uvicorn (现场常态) → asyncio task 消失,
    计划卡 RUNNING + 步骤卡 "running" 永驻: start/resume 都拒、HAL reload
    被 409 挡。启动时 (此刻必然没有任何 runner) 把 RUNNING 计划置 FAILED
    (如实: 执行被中断) + running 步骤置 failed, 操作员可改参重跑。
    在 app lifespan 启动段调用。
    """
    db = SessionLocal()
    try:
        stale = (
            db.query(TestPlan)
            .filter(TestPlan.status == TestPlanStatus.RUNNING)
            .all()
        )
        for plan in stale:
            plan.status = TestPlanStatus.FAILED
            plan.completed_at = datetime.utcnow()
            running_steps = (
                db.query(TestStep)
                .filter(
                    TestStep.test_plan_id == plan.id,
                    TestStep.status == "running",
                )
                .all()
            )
            for s in running_steps:
                s.status = "failed"
                s.error_message = "执行被进程重启中断 (runner 丢失) — 可重跑"
                s.completed_at = datetime.utcnow()
            logger.warning(
                "[runner] 启动复位 stale RUNNING 计划 %s (%s) → FAILED "
                "(含 %d 个 running 步骤)",
                plan.id, plan.name, len(running_steps),
            )
        if stale:
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("[runner] stale RUNNING 复位失败 (不阻塞启动)")
        db.rollback()
    finally:
        db.close()


async def run_test_plan(plan_id: UUID) -> None:
    """后台入口: 自建 session, 顶层兜底 (异常 → 计划 FAILED, 不静默消失)。"""
    db = SessionLocal()
    try:
        await _run_plan_loop(db, plan_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("[runner] plan %s 执行器异常: %s", plan_id, e)
        try:
            db.rollback()
            plan = db.query(TestPlan).filter(TestPlan.id == plan_id).first()
            if plan is not None and plan.status == TestPlanStatus.RUNNING:
                plan.status = TestPlanStatus.FAILED
                plan.completed_at = datetime.utcnow()
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("[runner] plan %s 异常收尾也失败", plan_id)
    finally:
        db.close()


async def _run_plan_loop(db: Session, plan_id: UUID) -> None:
    plan = db.query(TestPlan).filter(TestPlan.id == plan_id).first()
    if plan is None:
        logger.error("[runner] plan %s 不存在", plan_id)
        return
    if plan.status != TestPlanStatus.RUNNING:
        logger.warning(
            "[runner] plan %s 状态 %s ≠ RUNNING, 不执行 (start/resume 先置状态)",
            plan_id, plan.status,
        )
        return

    steps = (
        db.query(TestStep)
        .filter(TestStep.test_plan_id == plan_id)
        .order_by(TestStep.order)
        .all()
    )
    if not steps:
        logger.warning("[runner] plan %s 无步骤 — 直接收尾", plan_id)
        _finalize(db, plan)
        return

    logger.info("[runner] plan %s (%s) 开始执行, %d 步", plan_id, plan.name, len(steps))

    for step in steps:
        # 协作式 pause/cancel: 每步前读最新计划状态 (别的请求会改它)
        db.expire(plan)
        db.refresh(plan)
        # 门审 #217 F2: 反向判定 — 非 RUNNING 一律停 (cancel/pause/手动"完成"/
        # 任何外部改状态都尊重), 不枚举具体终态 (枚举会漏)
        if plan.status != TestPlanStatus.RUNNING:
            logger.info(
                "[runner] plan %s 状态已变为 %s, 停在步骤 %s 前",
                plan_id, plan.status, step.order,
            )
            return
        if step.status != "pending":
            continue  # resume 续跑: 已完成/失败/跳过的步骤不重跑

        if step.type != MIMO_OTA_STEP_TYPE:
            step.status = "skipped"
            step.error_message = (
                f"步骤类型 {step.type!r} 的执行尚未接入 runner (当前只执行 "
                f"{MIMO_OTA_STEP_TYPE}) — 显式跳过, 不假装执行"
            )
            db.commit()
            logger.warning(
                "[runner] plan %s 步骤 %s (%s) 类型 %s 跳过",
                plan_id, step.order, step.name, step.type,
            )
            continue

        ok = await _run_mimo_ota_step(db, plan, step)
        if not ok and not bool(step.continue_on_failure):
            logger.warning(
                "[runner] plan %s 步骤 %s 失败且 continue_on_failure=False, 中止后续步骤",
                plan_id, step.order,
            )
            break

    _finalize(db, plan)


async def _run_mimo_ota_step(db: Session, plan: TestPlan, step: TestStep) -> bool:
    """单 MIMO_OTA 步骤 = 执行快照 TestCase + 一次 5 相位链。返回是否成功。"""
    step.status = "running"
    step.started_at = datetime.utcnow()
    plan.current_test_case_index = step.order
    db.commit()
    logger.info("[runner] plan %s 步骤 %s (%s) 开始", plan.id, step.order, step.name)

    # ── 执行快照 TestCase: 步骤参数固化 + lab/证书解析 (factory 内含
    #    MIMOOTAConfiguration 校验, 非法参数在这里 fail-loud) ──
    # 门审 #217 F6: 按 plan.test_case_ids[order] 反查原 TestCase, 透传其
    # lab/证书 FK — 不透传会静默换成 active lab (违反 TestCase 单一真值源)。
    # 位置对应在 reorder 后会漂: 越界/查不到 → 不传 (factory 解析 active
    # lab) + 显式告警, 不猜。
    _orig_lab_id = None
    _orig_cert_id = None
    _tc_ids = list(plan.test_case_ids or [])
    if 0 <= step.order < len(_tc_ids):
        from app.models.test_plan import TestCase as _TestCase

        try:
            # test_case_ids JSON 存 str — UUID 列比较前显式转型
            # (SQLite fallback 类型对 str 直比会炸, PG 也不该赌隐式转换)
            _tc_uuid = UUID(str(_tc_ids[step.order]))
        except (ValueError, TypeError):
            _tc_uuid = None
        _orig = (
            db.query(_TestCase).filter(_TestCase.id == _tc_uuid).first()
            if _tc_uuid is not None else None
        )
        if _orig is not None:
            _orig_lab_id = _orig.lab_profile_id
            _orig_cert_id = _orig.calibration_certificate_id
    if _orig_lab_id is None:
        logger.warning(
            "[runner] plan %s 步骤 %s 反查不到原 TestCase 的 lab 绑定 "
            "(reorder 漂移/例已删?) — 快照将解析 active lab",
            plan.id, step.order,
        )
    # 快照名截断 (门审 #217 F11: TestCase.name 是 String(255), 溢出会被
    # except 吞成"参数无效"误导排查)
    _snap_name = (
        f"{plan.name} · 步骤{step.order} {step.name}"[:200]
        + f" [{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}]"
    )
    try:
        test_case, descriptors = build_mimo_ota_test_case(
            db,
            name=_snap_name,
            description=f"测试计划 {plan.id} 步骤 {step.id} 的执行快照",
            lab_profile_id=_orig_lab_id,
            calibration_certificate_id=_orig_cert_id,
            config_overrides=dict(step.parameters or {}),
            created_by="test_plan_runner",
            tags=["test_plan_run"],
        )
    except Exception as e:  # noqa: BLE001 — 校验/lab 解析失败都归步骤失败
        db.rollback()
        step.status = "failed"
        step.error_message = f"步骤参数无法构成有效执行配置: {e}"
        step.completed_at = datetime.utcnow()
        plan.failed_test_cases = (plan.failed_test_cases or 0) + 1
        db.commit()
        logger.error(
            "[runner] plan %s 步骤 %s 快照构建失败: %s", plan.id, step.order, e
        )
        return False

    execution = TestExecution(
        test_plan_id=plan.id,
        test_case_id=test_case.id,
        execution_order=step.order,
        status="running",
        started_at=datetime.utcnow(),
        config={
            "step_descriptors": [
                {"id": d.id, "type": d.type, "parameters": d.parameters}
                for d in descriptors
            ],
            "test_step_id": str(step.id),
        },
        executed_by="test_plan_runner",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # ── 5 相位链 (与 commissioning run-all 同一循环语义: failed 早停) ──
    failed_phase: Optional[str] = None
    failed_message: Optional[str] = None
    for d in descriptors:
        ctx = build_step_context(db, execution, test_case, d)
        result = await dispatch_step(ctx)
        if result.status.value == "failed":
            failed_phase = d.type
            failed_message = result.error_message
            logger.warning(
                "[runner] plan %s 步骤 %s 相位 %s 失败: %s",
                plan.id, step.order, d.type, result.error_message,
            )
            break

    step.completed_at = datetime.utcnow()
    # result 列是 Text — 存 JSON 字符串 (execution_id 是追溯执行明细的钥匙)
    import json

    step.result = json.dumps({
        "execution_id": str(execution.id),
        "test_case_id": str(test_case.id),
        "failed_phase": failed_phase,
    }, ensure_ascii=False)
    if failed_phase is not None:
        step.status = "failed"
        step.error_message = f"相位 {failed_phase} 失败: {failed_message or '明细见执行记录'}"
        execution.status = "failed"
        plan.failed_test_cases = (plan.failed_test_cases or 0) + 1
    else:
        step.status = "completed"
        execution.status = "completed"
        plan.completed_test_cases = (plan.completed_test_cases or 0) + 1
    execution.completed_at = datetime.utcnow()
    db.commit()
    logger.info(
        "[runner] plan %s 步骤 %s %s (execution=%s)",
        plan.id, step.order, step.status, execution.id,
    )
    return failed_phase is None


def _finalize(db: Session, plan: TestPlan) -> None:
    """正常走完 (未被 pause/cancel 截停) 的终态收尾。

    复用 complete_test_plan (计划级历史行 + measurement 归档 + 自动报告);
    失败终态传 final_status=FAILED — 历史 Tab / 报告照样生成, 状态如实。
    """
    db.expire(plan)
    db.refresh(plan)
    if plan.status != TestPlanStatus.RUNNING:
        # pause/cancel 截停: 状态已由对应端点管理, runner 不碰
        logger.info("[runner] plan %s 终态 %s (非 runner 收尾)", plan.id, plan.status)
        return
    from app.services.test_plan_service import TestExecutionService

    final = (
        TestPlanStatus.FAILED
        if (plan.failed_test_cases or 0) > 0
        else TestPlanStatus.COMPLETED
    )
    try:
        TestExecutionService().complete_test_plan(db, plan.id, final_status=final)
        logger.info("[runner] plan %s 收尾完成, 终态 %s", plan.id, final.value)
    except Exception as e:  # noqa: BLE001
        logger.exception("[runner] plan %s complete_test_plan 收尾失败: %s", plan.id, e)
        plan.status = final
        plan.completed_at = datetime.utcnow()
        db.commit()
