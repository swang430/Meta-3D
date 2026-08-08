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

    占 HAL 的活跃 TestExecution  ∪  TestPlan ∈ (running, paused)   ← S4c 后只剩左边

**ARCH-1 S4c（2026-07-29）**: 计划那半截**已删**，判据收敛成单源 ——

    占 HAL 的活跃 TestExecution（含硬件 VRT 的 paused）

删得掉是因为 S4b 拆掉了计划 runner: 原先"暂停的计划仍持有驱动状态"这个
理由的前提是有东西在驱动，而现在没有了。留着反倒是害 —— 一行 brownfield
的 paused 计划会成为**永久** 409 blocker（cancel/complete/resume/PATCH
全随 S4b 删了），逼操作员用 force=true，而 force 会连真在跑的用例执行
一起绕过。

"占 HAL"不等于"非 VRT"（Codex #241 D1）：VRT 的 ``conducted``（强制
拓扑）与 ``ota``（走 MPAC）都占真硬件，只有 ``digital_twin`` 是纯数字
仿真不持驱动 —— 所以排除的是 digital_twin 这一种，不是整个 VRT。

The operator override is a ``force=true`` query param — they take
responsibility for the abort. We don't try to refuse harder than that
because in actual on-site debugging, the operator sometimes KNOWS
the test is hung on a bad driver and reload is the right escape hatch.

除执行行外，``instrument_test_lease`` 现在提供进程内活跃操作判据，覆盖正式
TestCase、commissioning、诊断序列、单次 SCPI 与 F64 控制操作。它既阻止这些
操作期间 HAL reload 拆驱动，也负责空闲关闭 F64/UXM 控制会话和监控门。
后台 metrics broadcaster 不作为 blocker；租约未开启监控门时它根本不读取 HAL。
(P2-5 原文写的是 TestPlan check —— S4c 拆完计划链后判据换成执行行。)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.test_plan import TestCase, TestExecution
from app.services.instrument_test_lease import active_test_lease_purpose

# VRT 里唯一不持有 HAL 驱动的模式 —— 纯数字仿真。conducted 需要拓扑、
# ota 走 MPAC 暗室, 两者都占真硬件, 必须照拦 (Codex #241 D1)。
NON_HAL_EXECUTION_MODE = "digital_twin"


@dataclass(frozen=True)
class ReloadBlocker:
    """One reason a HAL reload should be refused (without ``force=true``).

    ``kind`` lets blocker types coexist：数据库执行行发 ``test_execution``，
    进程内仪表租约发 ``instrument_lease``。
    (ARCH-1 S4c 之前这里发的是 ``"test_plan"`` —— 那半截已删,
    ``test_plan`` 自此是**唯一不可能**出现的值。)
    """

    kind: str  # "test_execution" | "instrument_lease"
    id: str
    name: str
    status: str
    detail: str


# ARCH-1 S4c: BLOCKING_TEST_PLAN_STATUSES 与 find_test_plan_blockers 已删,
# 见下方 find_reload_blockers 的注释。那份状态列表搬到了
# ``test_case_runner.LEGACY_ZOMBIE_PLAN_STATUSES`` —— 它在那边的语义不再是
# "会拦住重载", 而是"启动时该清掉的遗留状态"。


def find_execution_blockers(db: Session) -> List[ReloadBlocker]:
    """占着 HAL 驱动的活跃执行行 (ARCH-1 S3)。

    覆盖所有走 ``dispatch_step`` 的链 —— 用例直接执行 (case-runner)、
    计划链每步、暗室首测 run-all、单相位 run_phase、诊断 adhoc ——
    它们执行期间行处于 ``running``。

    **另加硬件 VRT 的 ``paused``**: VRT 的 pause 只改 DB 状态不释放任何
    东西, resume 直接回 running, 所以暂停期间驱动照样被占 (与本模块给
    TestPlan PAUSED 曾用的理由一致 —— 那半截 S4c 已删)。``paused`` 是
    TestExecution 里的
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
                # resume 时还在的硬件配置。这跟本模块曾给 TestPlan PAUSED 写的
                # 理由逐字一致 —— 那半截连同它的常量已随 S4c 删除, 理由本身
                # 在这里仍然成立 (因为 VRT 真的有东西在驱动)。
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

    ARCH-1 S4c: 计划那半截**已删** —— S3 的注释写的就是"等 S4 拆计划链时
    删除"。删得掉的理由: 那半截防的是"暂停的计划还占着驱动状态, 等着
    resume", 而 S4b 之后 **计划 runner 不存在了** —— 没有任何东西在驱动,
    保护恒空。

    留着反而有害: 一行 brownfield 的 paused 计划会成为**永久** 409 blocker
    (S4b 删光了 cancel/complete/resume/PATCH, 应用内无端点能清它),
    操作员只剩 force=true —— 而那会连真在跑的用例执行一起绕过, 正是本模块
    要防的事。删掉这半截, 这个风险从根上消失。

    遗留的 running/paused 计划行由 ``test_case_runner.
    reset_orphaned_plan_chain_rows`` 在启动时清成终态 (让封存表的数据如实,
    不再是"永远在跑"的谎)。
    """
    blockers = find_execution_blockers(db)
    active_lease = active_test_lease_purpose()
    if active_lease is not None:
        blockers.append(ReloadBlocker(
            kind="instrument_lease",
            id=active_lease,
            name=active_lease,
            status="running",
            detail=(
                f"进程内仪表操作 {active_lease!r} 正在使用 HAL；重载会拆掉它的"
                "驱动。请等待操作结束，或明确使用 force=true 放弃该操作。"
            ),
        ))
    return blockers
