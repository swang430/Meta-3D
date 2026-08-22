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
- **全局单飞**: 正式执行与破坏性诊断交错打同一套 HAL 会互相污染。正式执行
  判据是进程内任务表 + DB 里的 running 行 (防重启后标志丢失的窗口)；
  破坏性诊断另有进程内 token，由双方入口双向检查。
  ARCH-1 S4b 拆掉计划链后, 原先"与计划 runner 互斥"那一条随之删除
  (计划 runner 不存在了, 该分支恒 None)。
- **协作式 cancel**: cancel 端点把 execution.status 置 "cancelled", task
  在相位间 refresh 检查 — 反向判定 (非 running 一律停, 不枚举终态)。
  不做 pause/resume (拍板: 状态机简化)。
- **启动残留复位**: 后端重启时把本 runner 的 stale "running" 执行行置
  failed (谓词收窄到 executed_by == RUNNER_MARKER 的行 — 不碰暗室首测 /
  VRT 的执行行)。cancel 同样按这个谓词收窄。
  ARCH-1 S4b 起本模块**另有**一个 ``reset_orphaned_plan_chain_rows``,
  接管已删除的 test_plan_runner 遗留的三类僵尸行 —— 单独一个函数,
  不并进上面那个, 免得 "case_executions" 名不副实。
- 进度写进 execution.config["phase_progress"] (JSON, flag_modified),
  GUI 轮询状态端点展示。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified

from app.core.logging_config import close_execution_log, current_execution_id
from app.db.database import SessionLocal
from app.hal.positioner import retain_positioner_stop_generation
from app.models.test_plan import (
    TestCase,
    TestExecution,
    TestPlan,
    TestPlanStatus,
    TestStep,
)
from app.services.mimo_ota.factory import build_mimo_ota_test_case
from app.services.execution_exclusion_guard import active_unsafe_diagnostic
from app.services.test_execution.hydrate import build_step_context
from app.services.test_execution.registry import dispatch_step
from app.utils.human_time import format_human_local_timestamp
from app.services.instrument_test_lease import (
    InstrumentTestLeaseError,
    instrument_test_lease,
)
from app.services.instrument_hal_service import get_hal_service
from app.services.execution_failure_alerts import emit_execution_failed_alert

logger = logging.getLogger(__name__)

MIMO_OTA_TYPE = "MIMO_OTA"
RUNNER_MARKER = "test_case_runner"

# 模块级任务表: 单飞判据之一 + 持引用防 asyncio task 被 GC。
_RUNNING_TASKS: Dict[str, "asyncio.Task[None]"] = {}


def _finalize_scpi_acceptance(execution):
    """P1-47C：仪器证据是正式通过的必要条件，不替代业务判定。"""
    from app.services.execution_scpi_evidence import (
        finalize_execution_scpi_evidence,
    )

    summary = finalize_execution_scpi_evidence(execution)
    if not summary.formal_acceptance:
        # 只做 AND 门：证据不完整强制不通过；证据通过也不能替业务分析判绿。
        execution.validation_pass = False
    return summary


def has_active_case_run() -> Optional[str]:
    """返回当前活跃的 case 执行 id (无则 None)。"""
    for key, task in _RUNNING_TASKS.items():
        if not task.done():
            return key
    return None


def _active_conflict() -> Optional[str]:
    """全局单飞：本 runner 或破坏性诊断在跑 → 返回冲突描述。

    ARCH-1 S4b: 原先这里还查一次 ``test_plan_runner.has_active_runner`` ——
    过渡期两条链都能打 HAL, 必须互斥。计划链拆除后计划 runner 不存在了,
    那个分支恒 None, 连同 import 一并删除 (留着 = 模块删掉后每次执行都
    ModuleNotFoundError)。

    ⚠️ 正式 runner 防重入的两条判据**都还在**, 没被这次删除削弱:
      ① 进程内任务表 (``has_active_case_run``, 本函数);
      ② DB 里的 running 行 (``launch_test_case_execution`` 的 dangling 双判据)。
    此外，本函数检查独立的破坏性诊断 token，形成诊断 → 正式执行的反向门。
    """
    active_case = has_active_case_run()
    if active_case is not None:
        return f"已有用例执行在跑 (execution {active_case})"
    active_diagnostic = active_unsafe_diagnostic()
    if active_diagnostic is not None:
        return f"已有破坏性诊断在跑 (diagnostic {active_diagnostic})"
    return None


def has_running_case_run_row(db) -> Optional[str]:
    """返回 DB 中本 runner 的 running 行 id；用于另一执行入口的双判据。"""
    running = (
        db.query(TestExecution)
        .filter(TestExecution.status == "running")
        .filter(TestExecution.executed_by == RUNNER_MARKER)
        .first()
    )
    return str(running.id) if running is not None else None


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
    dangling = has_running_case_run_row(db)
    if dangling is not None:
        raise CaseRunBusy(
            f"DB 里已有 running 的用例执行 {dangling} (可能是残留 — "
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
        + " [执行 "
        + format_human_local_timestamp(datetime.now(timezone.utc))
        + "]"
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
            # 所有正式 MIMO OTA 吞吐量执行都由 MEASURE 按本次 TestCase 建立
            # UXM/F64/开关矩阵工作态并受控 attach。PRECHECK 只做无需 attach
            # 的静态门，不能再要求操作员提前借用仪表遗留状态登记 DUT。
            "managed_rf_attach": True,
            "phase_progress": [],
        },
        executed_by=RUNNER_MARKER,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    # P1-36（Codex #286 R1）：**请求侧**也要设。
    # 早前只在后台任务 `_run_case` 里设 —— 于是下面那条「开始执行」是在
    # 请求上下文里打的，`execution_id` 为 `-`；按返回的 id 过滤日志会**漏掉
    # 这次执行的起点**（生命周期记录反而不在链上）。
    # ⚠ 必须在 `create_task` **之前** —— 子任务继承的是创建那一刻的上下文。
    current_execution_id.set(str(execution.id))

    positioner = get_hal_service().drivers.get("positioner")
    # create_task inherits ContextVars at this exact point.  Capture before the
    # request returns 202 so an operator stop while the task is still waiting
    # for scheduler time / the instrument lease remains visible in MEASURE.
    with retain_positioner_stop_generation(positioner):
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
    completed_at = datetime.utcnow()
    duration_sec = None
    if execution.started_at is not None:
        duration_sec = max(
            0.0,
            (completed_at - execution.started_at).total_seconds(),
        )
    # SELECT 只用于归属、当前状态与 started_at；结束该读事务后，
    # 取消与 REPORT completion 在同一个 `running -> terminal` 数据库 CAS 上
    # 竞争。迟到取消不得用旧 ORM 快照把已完成赢家反向覆盖成 cancelled。
    db.rollback()
    updated = (
        db.query(TestExecution)
        .filter(
            TestExecution.id == execution_id,
            TestExecution.executed_by == RUNNER_MARKER,
            TestExecution.status == "running",
        )
        .update(
            {
                TestExecution.status: "cancelled",
                TestExecution.completed_at: completed_at,
                TestExecution.duration_sec: duration_sec,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if updated != 1:
        return False
    # P1-36（Codex #286 R1）：取消也是这次执行的生命周期事件，
    # 不设的话「谁在什么时候取消的」不在这条链上。
    current_execution_id.set(str(execution_id))
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
            for ex in stale:
                emit_execution_failed_alert(ex.id)
    except Exception:  # noqa: BLE001
        logger.exception("[case-runner] stale 复位失败 (不阻塞启动)")
        db.rollback()
    finally:
        db.close()


# 计划链自己的启动复位归 test_plan_runner.reset_stale_running_plans 管,
# 而 ARCH-1 S4b 把那个模块整个删了 —— 下面这个函数接管它遗留的清理职责。
LEGACY_PLAN_RUNNER_MARKER = "test_plan_runner"

# 遗留计划行里"该在启动时清掉"的状态。
# ARCH-1 S4c 之前这份列表住在 hal_reload_policy (语义是"会拦住 HAL 重载"),
# 复位这边 import 过来用以保持同源 (内审 F1)。S4c 删掉了闸门的计划半截 ——
# 计划 runner 都不存在了, 拦谁呢 —— 于是这份列表的语义只剩一个:
# **哪些状态属于"进程重启遗留的僵尸"**, 归属自然落到复位这边。
LEGACY_ZOMBIE_PLAN_STATUSES = (
    TestPlanStatus.RUNNING,
    TestPlanStatus.PAUSED,
)


def reset_orphaned_plan_chain_rows() -> None:
    """启动复位 **计划链遗留的僵尸行**（ARCH-1 S4b 接管）。

    为什么单独一个函数, 不并进 ``reset_stale_running_case_executions``:
    那个函数的 docstring 明写"谓词收窄到 RUNNER_MARKER — 各链自管各的复位语义",
    把计划行塞进一个叫 ``case_executions`` 的函数里是名不副实。这里保持
    "一个函数管一条链"的既有约定, 只是这条链的管理者换成了本模块 ——
    因为 ``test_plan_runner`` 已经不存在了, 而复位职责必须有人接。

    **三类行, 缺一不可** (原 ``reset_stale_running_plans`` 就是复位这三种):

    ① ``TestPlan.status == RUNNING``   → FAILED
    ② 其下 ``TestStep.status == 'running'`` → failed
    ③ ``TestExecution(executed_by='test_plan_runner', status='running')`` → failed

    ⚠️ **为什么必须做 —— 理由变过两次, 现在成立的是第三条**。写全是为了让
    下一个人别再顺着已作废的理由去改判据 (那两条都还散落在别处过):

      ✗ (S4b 原写) "①② 会被 dashboard 计进 active_test_plans" —— **错归因**:
        dashboard 数的是 RUNNING+QUEUED, 且该字段 S4b 自己已删。顺着它枚举
        就漏掉了 PAUSED 这一态 (S4b 内审 F1 抓到)。
      ✗ (S4b 修正后) "①② 卡住 HAL 重载闸门" —— S4c 删掉了闸门的计划半截,
        **计划行不再拦任何东西**。
      ✓ **现在成立的**:
        (a) 让封存表的数据**如实** —— 一行永远写着 "running"/"paused" 的
            计划是个谎, 而这几张表是现场机器唯一的历史可追溯来源;
        (b) 它是 **S4c 敢删闸门计划半截的前提** (见
            ``hal_reload_policy.find_reload_blockers`` 的 docstring);
        (c) ③ 那类**执行行**仍会永久 409 拦住 HAL reload —— 这条一直成立,
            与 ①② 不同, 因为闸门的执行行半截没删。

    S4b 之后不再产生新的 ①②③ 行 (产生方全删了), 但**存量还在两台现场机器的库里**,
    所以这是每次启动都要跑的清理, 不是一次性迁移 —— 迁移只跑一次, 复位是持续的。
    """
    db = SessionLocal()
    try:
        # RUNNING 与 PAUSED 都算僵尸 (LEGACY_ZOMBIE_PLAN_STATUSES)。
        # 只清 RUNNING 是 S4b 内审 F1 抓到的洞: 当时 HAL 闸门还认 paused,
        # 一行 brownfield 的 paused 计划就是永久 409 blocker。S4c 删掉闸门的
        # 计划半截后那个后果没了, 但**这里仍然两态都清** —— 让封存表的数据
        # 如实 (一行永远写着 "paused" 的计划是个谎), 且不依赖闸门还认不认它。
        stale_plans: List[TestPlan] = (
            db.query(TestPlan)
            .filter(TestPlan.status.in_(LEGACY_ZOMBIE_PLAN_STATUSES))
            .all()
        )
        for plan in stale_plans:
            plan.status = TestPlanStatus.FAILED
            plan.completed_at = datetime.utcnow()
            running_steps: List[TestStep] = (
                db.query(TestStep)
                .filter(
                    TestStep.test_plan_id == plan.id,
                    TestStep.status == "running",
                )
                .all()
            )
            for step in running_steps:
                step.status = "failed"
                step.error_message = (
                    "计划链已于 ARCH-1 S4b 拆除 — 该步骤是进程重启遗留的僵尸行"
                )
                step.completed_at = datetime.utcnow()
            logger.warning(
                "[s4b-cleanup] 复位遗留 RUNNING 计划 %s (%s) → FAILED (含 %d 个 running 步骤)",
                plan.id, plan.name, len(running_steps),
            )

        # ③ 独立于 plan 状态判定: plan 可能已被别处置成终态, 执行行仍卡 running。
        stale_execs: List[TestExecution] = (
            db.query(TestExecution)
            .filter(TestExecution.status == "running")
            .filter(TestExecution.executed_by == LEGACY_PLAN_RUNNER_MARKER)
            .all()
        )
        for ex in stale_execs:
            ex.status = "failed"
            ex.completed_at = datetime.utcnow()
            cfg = dict(ex.config or {})
            cfg["error_message"] = (
                "计划链已于 ARCH-1 S4b 拆除 — 该执行是进程重启遗留的僵尸行"
            )
            ex.config = cfg
            flag_modified(ex, "config")
            logger.warning(
                "[s4b-cleanup] 复位遗留 running 计划执行行 %s → failed", ex.id
            )

        if stale_plans or stale_execs:
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("[s4b-cleanup] 计划链僵尸行复位失败 (不阻塞启动)")
        db.rollback()
    finally:
        db.close()


async def _run_case(execution_id: UUID) -> None:
    """后台入口: 自建 session, 顶层兜底 (异常 → failed, 不静默消失)。"""
    # P1-36: 这次执行期间的**全部**日志 (runner / HAL / SCPI) 自动带上执行身份
    # —— `ContextFilter` 已在给每条 LogRecord 注入 `execution_id`，这里 set 一次
    # 就够，**零调用点改动**。
    #
    # ⚠ 本任务由 `create_task` 拉起，会**继承**发起它的那个 HTTP 请求的
    # `session_id` —— 那是有用的溯源（哪次点击起的这次执行），刻意保留。
    # 但读日志时别把它当成"那个请求还在跑"：请求早返回了，执行还在后台。
    current_execution_id.set(str(execution_id))
    db = SessionLocal()
    try:
        async with instrument_test_lease(f"formal-case:{execution_id}"):
            await _run_case_loop(db, execution_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("[case-runner] execution %s 执行器异常: %s", execution_id, e)
        try:
            db.rollback()
            ex = (
                db.query(TestExecution)
                .filter(TestExecution.id == execution_id).first()
            )
            lease_failed = isinstance(e, InstrumentTestLeaseError)
            if ex is not None and (ex.status == "running" or lease_failed):
                # Local 交接是执行完整性的一部分：业务相位全绿但 F64 仍被 Remote
                # 占着，不得继续显示 completed。cancelled/failed 本来已是非成功，
                # 只补证据；completed/running 才降级为 failed。
                if ex.status in {"running", "completed"}:
                    ex.status = "failed"
                    ex.completed_at = datetime.utcnow()
                cfg = dict(ex.config or {})
                cfg["error_message"] = f"执行器异常: {e}"
                if lease_failed:
                    cfg["local_control_handoff_failed"] = True
                ex.config = cfg
                flag_modified(ex, "config")
                _finalize_scpi_acceptance(ex)
                db.commit()
                if ex.status == "failed":
                    emit_execution_failed_alert(ex.id)
        except Exception:  # noqa: BLE001
            logger.exception("[case-runner] execution %s 异常收尾也失败", execution_id)
    finally:
        try:
            close_execution_log(str(execution_id))
        except Exception:  # logging cleanup must not change execution outcome
            token = current_execution_id.set("-")
            try:
                logger.exception(
                    "[case-runner] execution %s 日志收尾失败",
                    execution_id,
                )
            finally:
                current_execution_id.reset(token)
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
        emit_execution_failed_alert(execution.id)
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
            _finalize_scpi_acceptance(execution)
            db.commit()
            logger.info(
                "[case-runner] execution %s 状态已变为 %s, 停在相位 %s 前",
                execution_id, execution.status, raw.get("type"),
            )
            return

        d = _descriptor_from_dict(raw)
        ctx = build_step_context(db, execution, test_case, d)
        result = await dispatch_step(ctx)
        phase_status = result.status.value
        # 相位执行期间别的 writer 可能已更新执行行；先刷最新再 append，
        # 不用相位前的 stale JSON 快照覆盖进度。
        db.expire(execution)
        db.refresh(execution)
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
            # ERROR 级 — 执行终态失败对操作员是 error 事件, 主控台面板按
            # ERROR 过滤排障 (2026-07-31 P2-11: warning 级失败行被轮询 INFO
            # 冲出面板不可见); 本函数其余终态 (execution/快照不存在) 同为 error。
            logger.error(
                "[case-runner] execution %s 相位 %s 失败: %s",
                execution_id, d.type, result.error_message,
            )
            break

    db.expire(execution)
    db.refresh(execution)
    evidence_summary = _finalize_scpi_acceptance(execution)
    if execution.status != "running":
        db.commit()
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
    if execution.status == "failed":
        emit_execution_failed_alert(execution.id)
    logger.info(
        "[case-runner] execution %s 收尾: %s, SCPI formal=%s (%s)",
        execution_id,
        execution.status,
        evidence_summary.formal_verdict.value,
        evidence_summary.reason,
    )


def _descriptor_from_dict(raw: dict):
    """config 里的描述符字典 → StepDescriptor (镜像暗室首测 _resolve_execution
    的重建逻辑)。"""
    from app.services.test_execution.context import StepDescriptor

    return StepDescriptor(
        id=raw["id"], type=raw["type"], parameters=raw.get("parameters") or {}
    )
