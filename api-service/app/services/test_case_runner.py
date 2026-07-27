"""TestCase 直接执行 runner — ARCH-1 S1 (2026-07-27, 设计稿已过 review)。

正式测试的执行正门: 用例库点「执行」→ 本模块。从 test_plan_runner 抽出
5 相位循环骨架, **砍掉全部计划逻辑** —— 没有步骤表、没有 8 级状态机、没有
队列。执行语义与暗室首测链完全同源 (同一个 build_mimo_ota_test_case 快照 +
同一个 dispatch_step 相位分发):

  TestCase.configuration (唯一参数真值源, P0-2)
  → 执行快照 TestCase (参数固化, 不回写原例)
  → TestExecution(config 记 source_test_case_id)
  → 后台 task 逐相位 dispatch, failed 早停
  → 相位间协作式 cancel

设计要点 (对应设计稿 §2.3):
- **全局单飞**: 双 5 相位链交错打同一套 HAL 会互相污染 (test_plan_runner
  的既有论证)。本模块与计划 runner **互斥**: 任一在跑, 另一个的启动都拒
  (计划链 S4 拆除前的过渡期同样受保护)。
- **协作式 cancel**: cancel 端点把 execution.status 置 "cancelled", task
  在相位间 refresh 检查 — 反向判定 (非 running 一律停, 不枚举终态)。
  不做 pause/resume (拍板: 状态机简化)。
- **启动残留复位**: 后端重启时把本 runner 的 stale "running" 执行行置
  failed (谓词收窄到 executed_by == RUNNER_MARKER 的行 — 不碰暗室首测 /
  VRT 的执行行)。cancel 同样按这个谓词收窄。
- 进度写进 execution.config["phase_progress"] (JSON, flag_modified),
  GUI 轮询状态端点展示。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified

from app.db.database import SessionLocal
from app.models.test_plan import TestCase, TestExecution
from app.services.mimo_ota.factory import build_mimo_ota_test_case
from app.services.test_execution.hydrate import build_step_context
from app.services.test_execution.registry import dispatch_step

logger = logging.getLogger(__name__)

MIMO_OTA_TYPE = "MIMO_OTA"
RUNNER_MARKER = "test_case_runner"

# 模块级任务表: 单飞判据之一 + 持引用防 asyncio task 被 GC。
_RUNNING_TASKS: Dict[str, "asyncio.Task[None]"] = {}


def has_active_case_run() -> Optional[str]:
    """返回当前活跃的 case 执行 id (无则 None)。"""
    for key, task in _RUNNING_TASKS.items():
        if not task.done():
            return key
    return None


def _active_conflict() -> Optional[str]:
    """全局单飞: 本 runner 或计划 runner 任一在跑 → 返回冲突描述。

    过渡期 (S4 拆计划链前) 两条链都能打 HAL, 必须互斥 —— 双 5 相位链
    交错会让实验互相污染 (test_plan_runner.has_active_runner 的既有论证)。
    """
    active_case = has_active_case_run()
    if active_case is not None:
        return f"已有用例执行在跑 (execution {active_case})"
    from app.services.test_plan_runner import has_active_runner

    active_plan = has_active_runner()
    if active_plan is not None:
        return f"已有测试计划 runner 在跑 (plan {active_plan})"
    return None


class CaseRunBusy(RuntimeError):
    """单飞冲突 — API 层转 409。"""


class CaseNotExecutable(ValueError):
    """用例不可执行 (类型不支持等) — API 层转 422。"""


def launch_test_case_execution(db, test_case_id: UUID) -> TestExecution:
    """执行入口 (API 调用, 必须在事件循环内):

    校验 → 快照 → 建执行行 → 后台 task。返回已 commit 的 TestExecution。
    db 用请求 session (建行即返回); 后台 task 自建 session。
    """
    conflict = _active_conflict()
    if conflict is not None:
        raise CaseRunBusy(conflict)
    # DB 双判据 (镜像计划 runner): 进程内标志 + DB running 行。防的是
    # 重启后标志丢失但复位没跑到的窗口 — 宁可 409 也不双跑。
    dangling = (
        db.query(TestExecution)
        .filter(TestExecution.status == "running")
        .filter(TestExecution.executed_by == RUNNER_MARKER)
        .first()
    )
    if dangling is not None:
        raise CaseRunBusy(
            f"DB 里已有 running 的用例执行 {dangling.id} (可能是残留 — "
            f"重启后端会自动复位, 或先 cancel 它)"
        )

    source = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if source is None:
        raise LookupError(f"TestCase {test_case_id} 不存在")
    if source.test_type != MIMO_OTA_TYPE:
        raise CaseNotExecutable(
            f"用例类型 {source.test_type!r} 尚未接入直接执行 (当前只支持 "
            f"{MIMO_OTA_TYPE}; VRT 走虚拟路测面板) — 不假装执行"
        )

    # ── 执行快照: 参数固化 (factory 内含 MIMOOTAConfiguration 校验,
    #    非法参数在这里 fail-loud 直接 422, 不产生半截执行行) ──
    snap_name = (
        f"{source.name}"[:200]
        + f" [执行 {datetime.utcnow().strftime('%Y%m%d-%H%M%S')}]"
    )
    try:
        snapshot, descriptors = build_mimo_ota_test_case(
            db,
            name=snap_name,
            description=f"用例 {source.id} 的执行快照 (ARCH-1)",
            lab_profile_id=source.lab_profile_id,
            calibration_certificate_id=source.calibration_certificate_id,
            config_overrides=dict(source.configuration or {}),
            created_by=RUNNER_MARKER,
            tags=["case_run"],
        )
    except (LookupError, CaseNotExecutable):
        raise
    except Exception as e:  # noqa: BLE001 — 校验/lab 解析失败 → 422 语义
        db.rollback()
        raise CaseNotExecutable(f"用例参数无法构成有效执行配置: {e}") from e

    execution = TestExecution(
        test_case_id=snapshot.id,
        status="running",
        started_at=datetime.utcnow(),
        config={
            "step_descriptors": [
                {"id": d.id, "type": d.type, "parameters": d.parameters}
                for d in descriptors
            ],
            "source_test_case_id": str(source.id),
            "phase_progress": [],
        },
        executed_by=RUNNER_MARKER,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    task = asyncio.get_running_loop().create_task(_run_case(execution.id))
    key = str(execution.id)
    _RUNNING_TASKS[key] = task
    task.add_done_callback(lambda _t, _k=key: _RUNNING_TASKS.pop(_k, None))
    logger.info(
        "[case-runner] 用例 %s (%s) 开始执行, execution=%s snapshot=%s",
        source.id, source.name, execution.id, snapshot.id,
    )
    return execution


def request_cancel(db, execution_id: UUID) -> bool:
    """cancel 端点调用: 置 cancelled, task 在相位间尊重它。

    返回是否真的置了 (非 running 行返回 False, API 层转 409)。
    归属收窄 (agent F2): 只认 executed_by == RUNNER_MARKER 的行 — VRT 的
    状态枚举没有 cancelled (置了会让 VRT 面板 500), 计划链的行 cancel 了
    也不生效 (计划 runner 只看 plan.status, 收尾还会覆盖回去), 都按
    "不存在"处理 (404), 与启动复位同一刀。
    """
    execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution_id)
        .filter(TestExecution.executed_by == RUNNER_MARKER)
        .first()
    )
    if execution is None:
        raise LookupError(
            f"TestExecution {execution_id} 不存在或不属于用例执行链"
        )
    if execution.status != "running":
        return False
    execution.status = "cancelled"
    execution.completed_at = datetime.utcnow()
    db.commit()
    logger.info("[case-runner] execution %s 被请求取消 (相位间生效)", execution_id)
    return True


def reset_stale_running_case_executions() -> None:
    """启动复位 (lifespan 调用): 本 runner 的 stale running 行 → failed。

    谓词收窄到 executed_by == RUNNER_MARKER — 不碰暗室首测 (commissioning_api)
    / VRT / 计划 runner 的执行行, 各链自管各的复位语义。
    """
    db = SessionLocal()
    try:
        stale: List[TestExecution] = (
            db.query(TestExecution)
            .filter(TestExecution.status == "running")
            .filter(TestExecution.executed_by == RUNNER_MARKER)
            .all()
        )
        for ex in stale:
            ex.status = "failed"
            ex.completed_at = datetime.utcnow()
            cfg = dict(ex.config or {})
            cfg["error_message"] = "执行被进程重启中断 (runner 丢失) — 可重跑"
            ex.config = cfg
            flag_modified(ex, "config")
            logger.warning(
                "[case-runner] 启动复位 stale running 执行 %s → failed", ex.id
            )
        if stale:
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("[case-runner] stale 复位失败 (不阻塞启动)")
        db.rollback()
    finally:
        db.close()


async def _run_case(execution_id: UUID) -> None:
    """后台入口: 自建 session, 顶层兜底 (异常 → failed, 不静默消失)。"""
    db = SessionLocal()
    try:
        await _run_case_loop(db, execution_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("[case-runner] execution %s 执行器异常: %s", execution_id, e)
        try:
            db.rollback()
            ex = (
                db.query(TestExecution)
                .filter(TestExecution.id == execution_id).first()
            )
            if ex is not None and ex.status == "running":
                ex.status = "failed"
                ex.completed_at = datetime.utcnow()
                cfg = dict(ex.config or {})
                cfg["error_message"] = f"执行器异常: {e}"
                ex.config = cfg
                flag_modified(ex, "config")
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("[case-runner] execution %s 异常收尾也失败", execution_id)
    finally:
        db.close()


async def _run_case_loop(db, execution_id: UUID) -> None:
    execution = (
        db.query(TestExecution).filter(TestExecution.id == execution_id).first()
    )
    if execution is None:
        logger.error("[case-runner] execution %s 不存在", execution_id)
        return
    test_case = (
        db.query(TestCase).filter(TestCase.id == execution.test_case_id).first()
    )
    if test_case is None:
        execution.status = "failed"
        execution.completed_at = datetime.utcnow()
        db.commit()
        logger.error("[case-runner] execution %s 的快照 TestCase 不存在", execution_id)
        return

    descriptors = (execution.config or {}).get("step_descriptors") or []
    failed_phase: Optional[str] = None
    failed_message: Optional[str] = None

    for raw in descriptors:
        # ── 协作式 cancel: 相位间读最新状态, 反向判定 (非 running 一律停,
        #    cancel / 任何外部改状态都尊重, 不枚举具体终态) ──
        db.expire(execution)
        db.refresh(execution)
        if execution.status != "running":
            logger.info(
                "[case-runner] execution %s 状态已变为 %s, 停在相位 %s 前",
                execution_id, execution.status, raw.get("type"),
            )
            return

        d = _descriptor_from_dict(raw)
        ctx = build_step_context(db, execution, test_case, d)
        result = await dispatch_step(ctx)
        phase_status = result.status.value
        cfg = dict(execution.config or {})
        cfg.setdefault("phase_progress", []).append(
            {"type": d.type, "status": phase_status}
        )
        execution.config = cfg
        flag_modified(execution, "config")
        db.commit()
        if phase_status == "failed":
            failed_phase = d.type
            failed_message = result.error_message
            logger.warning(
                "[case-runner] execution %s 相位 %s 失败: %s",
                execution_id, d.type, result.error_message,
            )
            break

    db.expire(execution)
    db.refresh(execution)
    if execution.status != "running":
        return  # cancel 在最后一个相位后到达 — 尊重外部终态
    if failed_phase is not None:
        execution.status = "failed"
        cfg = dict(execution.config or {})
        cfg["failed_phase"] = failed_phase
        cfg["error_message"] = failed_message or "明细见相位日志"
        execution.config = cfg
        flag_modified(execution, "config")
    else:
        execution.status = "completed"
    execution.completed_at = datetime.utcnow()
    db.commit()
    logger.info(
        "[case-runner] execution %s 收尾: %s", execution_id, execution.status
    )


def _descriptor_from_dict(raw: dict):
    """config 里的描述符字典 → StepDescriptor (镜像暗室首测 _resolve_execution
    的重建逻辑)。"""
    from app.services.test_execution.context import StepDescriptor

    return StepDescriptor(
        id=raw["id"], type=raw["type"], parameters=raw.get("parameters") or {}
    )
