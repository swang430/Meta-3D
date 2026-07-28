"""P2-5 — refuse / force policy for HAL Reload mid-test.

Pre-P2-5 ``POST /api/v1/instruments/hal/reload`` would tear down every
driver and reinitialise unconditionally. Concurrent reloads could race
the global service assignment (see ``reload_hal_service_atomic`` for
the mutex fix), AND a reload mid-test would silently abort the test —
the test plan's ``status='running'`` row stayed in the DB, the in-flight
sequence's HTTP request hung until ~30s VISA timeout, then surfaced a
cryptic ``visa.Error`` instead of a user-comprehensible "you reloaded
the HAL while a test was running".

This module supplies the *refuse* arm of the A+D policy chosen for
P2-5. The endpoint returns HTTP 409 with a structured payload listing
the blocker(s) so the GUI can render a precise message ("3 test plans
are running: …") instead of a generic "busy".

**ARCH-1 S3 换源（2026-07-28）**: P2-5 写这个模块时"正式测试"就等于
``TestPlan``，所以只查计划状态就够了。ARCH-1 S1 之后正式测试是
**TestCase 直接执行**（case-runner），它根本不写 TestPlan —— 那条判据
从 S1 上线（``124d7e5``）起就对正门失效了，跑着用例点重载会静默拆掉
驱动。现在的判据是**并集**：

    占 HAL 的活跃 TestExecution  ∪  TestPlan ∈ (running, paused)

计划那半截保留到 ARCH-1 S4 拆计划链时再删 —— 现在删会让 **paused**
的计划失去保护（暂停期间步骤间没有 running 的执行行，但驱动状态仍被
持有，见 ``BLOCKING_TEST_PLAN_STATUSES`` 的注释）。

"占 HAL"不等于"非 VRT"（Codex #241 D1）：VRT 的 ``conducted``（强制
拓扑）与 ``ota``（走 MPAC）都占真硬件，只有 ``digital_twin`` 是纯数字
仿真不持驱动 —— 所以排除的是 digital_twin 这一种，不是整个 VRT。

The operator override is a ``force=true`` query param — they take
responsibility for the abort. We don't try to refuse harder than that
because in actual on-site debugging, the operator sometimes KNOWS
the test is hung on a bad driver and reload is the right escape hatch.

**What this module does NOT detect**:

- In-flight diagnostic sequences (``app/api/diagnostic_sequence.py``)
  run synchronously on the FastAPI request thread; no DB row exists
  until the run completes, so there's nothing to query.
- Live SCPI commands via ``/instruments/{cat}/scpi-command``: same —
  request-thread bound, no in-flight registry.
- Background metrics broadcaster: continuously polling; not a "user
  initiated" operation worth refusing for.

A future P3 item could add an in-process active-operations registry
on the HAL service for the diagnostic / SCPI paths to opt-in to. For
P2-5 the TestPlan check covers the most consequential case (a multi-
minute formal test) and the warning log on shutdown (with the active
driver list) gives post-mortem context for the unguarded cases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.test_plan import TestCase, TestExecution, TestPlan, TestPlanStatus

# VRT 里唯一不持有 HAL 驱动的模式 —— 纯数字仿真。conducted 需要拓扑、
# ota 走 MPAC 暗室, 两者都占真硬件, 必须照拦 (Codex #241 D1)。
NON_HAL_EXECUTION_MODE = "digital_twin"


@dataclass(frozen=True)
class ReloadBlocker:
    """One reason a HAL reload should be refused (without ``force=true``).

    ``kind`` lets future blocker types coexist — today only ``"test_plan"``
    is emitted, but the registry / GUI rendering can branch on this when
    additional check sources (in-flight diagnostics, calibration session,
    etc.) get wired in later.
    """

    kind: str  # "test_plan" today; future: "diagnostic_run", "calibration"
    id: str
    name: str
    status: str
    detail: str


# TestPlan statuses that mean "a test session is actively bound to the
# drivers — tearing the HAL down will corrupt it". 'paused' is included
# because a paused test plan typically still holds driver state (a
# resume is expected); reload between pause + resume would surface the
# corruption on resume rather than failing visibly during the reload.
BLOCKING_TEST_PLAN_STATUSES = (
    TestPlanStatus.RUNNING.value,
    TestPlanStatus.PAUSED.value,
)


def find_test_plan_blockers(db: Session) -> List[ReloadBlocker]:
    """Return one ``ReloadBlocker`` per ``TestPlan`` row whose status
    would be invalidated by a HAL teardown.

    Pure SQL — no HAL coupling. The reload endpoint composes this with
    future check helpers when they're added.
    """
    plans = (
        db.query(TestPlan)
        .filter(TestPlan.status.in_(BLOCKING_TEST_PLAN_STATUSES))
        .order_by(TestPlan.started_at.desc().nullslast())
        .all()
    )
    return [
        ReloadBlocker(
            kind="test_plan",
            id=str(plan.id),
            name=plan.name or "(unnamed)",
            status=plan.status,
            detail=(
                f"test plan {plan.name!r} is {plan.status} — "
                "tearing down HAL will abort its in-flight driver work"
            ),
        )
        for plan in plans
    ]


def find_execution_blockers(db: Session) -> List[ReloadBlocker]:
    """占着 HAL 驱动的活跃执行行 (ARCH-1 S3)。

    覆盖所有走 ``dispatch_step`` 的链 —— 用例直接执行 (case-runner)、
    计划链每步、暗室首测 run-all、单相位 run_phase、诊断 adhoc ——
    它们执行期间行处于 ``running``。

    **另加硬件 VRT 的 ``paused``**: VRT 的 pause 只改 DB 状态不释放任何
    东西, resume 直接回 running, 所以暂停期间驱动照样被占 (与本模块给
    TestPlan PAUSED 的理由一致)。``paused`` 是 TestExecution 里的
    VRT-specific 状态, 该支要求 ``mode`` 非空。

    唯一排除的是 ``digital_twin``: 纯数字仿真不碰驱动, 拦它等于让一次
    软件回放堵住整个机台。conducted / ota 是真硬件 VRT, running 与
    paused 都照拦。
    """
    rows = (
        db.query(TestExecution, TestCase.name)
        .outerjoin(TestCase, TestExecution.test_case_id == TestCase.id)
        .filter(
            or_(
                TestExecution.status == "running",
                # 硬件 VRT 的 paused 也占着驱动 (Codex #242 第二轮):
                # VRTExecutionService.pause() 只改 DB 状态, **什么都不释放**,
                # resume() 直接回 running —— 暂停期间 reload 会拆掉它期望
                # resume 时还在的硬件配置。这跟本模块给 TestPlan PAUSED 写的
                # 理由逐字一致 (见 BLOCKING_TEST_PLAN_STATUSES 注释)。
                # paused 是 TestExecution 里的 VRT-specific 状态, 所以这支
                # 要求 mode 非空 —— 非 VRT 行不会有 paused。
                and_(
                    TestExecution.status == "paused",
                    TestExecution.mode.isnot(None),
                ),
            )
        )
        .filter(
            or_(
                TestExecution.mode.is_(None),
                TestExecution.mode != NON_HAL_EXECUTION_MODE,
            )
        )
        .order_by(TestExecution.started_at.desc().nullslast())
        .all()
    )
    return [
        ReloadBlocker(
            kind="test_execution",
            id=str(execution.id),
            name=case_name or f"execution {str(execution.id)[:8]}",
            status=execution.status,
            detail=(
                f"执行 {str(execution.id)[:8]} ({case_name or '未命名用例'}) "
                f"正在跑 [{execution.executed_by or '未知来源'}] — "
                f"重载会拆掉它正在用的驱动。先取消该执行, "
                f"或确认要放弃它再用 force=true。"
            ),
        )
        for execution, case_name in rows
    ]


def find_reload_blockers(db: Session) -> List[ReloadBlocker]:
    """Composite of every blocker source.

    ARCH-1 S3: **并集** —— 活跃执行行 + 计划状态。计划那半截等 S4 拆
    计划链时删除; 现在删会让 paused 的计划失去保护 (模块 docstring)。
    """
    return find_execution_blockers(db) + find_test_plan_blockers(db)
