"""P2-5 — HAL Reload refuse/force policy + concurrency lock.

Pins both layers:

- ``app/services/hal_reload_policy.find_reload_blockers``: pure SQL
  over ``TestExecution`` —— 占 HAL 的活跃执行行 (任意 ``running`` 行 +
  硬件 VRT 的 ``paused``, 排除 ``digital_twin``)。空列表 = 无事在飞。
  ⚠️ ARCH-1 S4c 之前还并上 ``TestPlan ∈ (running, paused)``, 那半截
  随计划链拆除删掉了 (见 H-b)。
- ``POST /api/v1/instruments/hal/reload``: thin wrapper around the
  finder + the atomic shutdown/reinit helper.
  - default (``force=false``) returns HTTP 409 with the blocker
    payload when any execution row is holding the drivers.
  - ``?force=true`` proceeds despite blockers, marks the success
    response ``forced=true`` so audit trails can distinguish.
- ``reload_hal_service_atomic``: shutdown + reinit under a single
  ``asyncio.Lock`` so concurrent reload calls serialise instead of
  racing the global ``_hal_service`` assignment.

What is NOT covered:

- Diagnostic sequences / SCPI commands in-flight via the request
  thread. Those don't write a DB row until they finish, so there's
  nothing for the finder to query. P2-5's scope docs name this as
  deferred; a follow-up P3 item would add an in-process active-ops
  registry.
- The "improve error message on closed VISA session" piece — that's
  a log-format change in the driver layer, not in scope here.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.test_plan import TestPlan, TestPlanStatus
from app.services.hal_reload_policy import (
    ReloadBlocker,
    find_reload_blockers,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _make_plan(
    db,
    *,
    name: str = "Test Plan",
    status: str = "draft",
) -> TestPlan:
    plan = TestPlan(
        id=uuid.uuid4(),
        name=name,
        status=status,
        test_case_ids=[],
        created_by="pytest",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ============================================================
# Layer 1: pure-SQL blocker finder
# ============================================================


# ARCH-1 S4c: TestFindTestPlanBlockers (8 条) 随 find_test_plan_blockers 删除。
# 那半截防的是"暂停的计划还占着驱动状态等 resume", 而 S4b 拆掉计划 runner 后
# 没有任何东西在驱动, 保护恒空; 留着反倒让 brownfield 的 paused 计划成为永久
# 409 blocker (应用内已无端点能清)。判据自此单源: 占 HAL 的活跃 TestExecution。

# ============================================================
# Layer 2: HTTP endpoint refuse / force behaviour
# ============================================================


class TestReloadEndpointRefuse:
    """``POST /api/v1/instruments/hal/reload`` should return HTTP 409
    with a structured blocker payload when blockers exist and
    ``force=true`` was NOT passed."""

    def test_refuses_with_409_and_payload_when_running_execution_present(self, db):
        # ARCH-1 S4c 换源: 原先造一行 running **计划**当 blocker, 而计划半截已删。
        # 换成 running **执行行** —— 判据自此单源, 端点行为(409 + 结构化 payload)不变。
        _make_execution(db, executed_by="test_case_runner", case_name="Calibration sweep")
        # Patch reload helpers so the test stays pure-API (doesn't
        # actually go through HAL shutdown/init on a real DB-less
        # service instance).
        with patch(
            "app.services.instrument_hal_service.reload_hal_service_atomic",
            new=AsyncMock(),
        ):
            resp = client.post("/api/v1/instruments/hal/reload")
        assert resp.status_code == 409
        # Codex P2 fix on this PR: 409 body IS the documented
        # HalReloadRefusedResult — top-level fields, not nested under
        # ``detail``. Pin top-level so a future regression to the
        # ``HTTPException(detail=...)`` form fails this assertion
        # instead of silently shifting consumers' parse path.
        payload = resp.json()
        assert "detail" not in payload  # not the FastAPI HTTPException wrapper
        assert payload["refused"] is True
        assert "1 active blocker" in payload["reason"]
        assert "?force=true" in payload["reason"]
        assert len(payload["blockers"]) == 1
        b = payload["blockers"][0]
        assert b["kind"] == "test_execution"
        assert b["name"] == "Calibration sweep"
        assert b["status"] == "running"
        assert payload["force_hint"]  # non-empty UX hint

    def test_force_true_proceeds_despite_blockers(self, db):
        _make_execution(db, executed_by="test_case_runner", case_name="Sweep")

        async def _fake_reload(mode):
            return None

        # Stub atomic reload + a get_hal_service result so the success
        # branch can compose the response without touching real HAL.
        class FakeHal:
            mode = type("M", (), {"value": "mock"})()
            drivers = {"channelEmulator": object(), "vna": object()}

        with patch(
            "app.services.instrument_hal_service.reload_hal_service_atomic",
            new=AsyncMock(side_effect=_fake_reload),
        ), patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.post("/api/v1/instruments/hal/reload?force=true")
        assert resp.status_code == 200
        body = resp.json()
        # ``forced`` flag distinguishes audit/log readers between
        # "natural reload" and "operator override".
        assert body["forced"] is True
        assert sorted(body["drivers"]) == ["channelEmulator", "vna"]
        assert body["drivers_loaded"] == 2

    def test_default_force_false_proceeds_when_no_blockers(self, db):
        """Reload should succeed silently when no test plan is in
        flight — the refuse arm only triggers when there ARE blockers."""

        class FakeHal:
            mode = type("M", (), {"value": "mock"})()
            drivers = {"channelEmulator": object()}

        with patch(
            "app.services.instrument_hal_service.reload_hal_service_atomic",
            new=AsyncMock(),
        ), patch(
            "app.services.instrument_hal_service.get_hal_service",
            return_value=FakeHal(),
        ):
            resp = client.post("/api/v1/instruments/hal/reload")
        assert resp.status_code == 200
        body = resp.json()
        assert body["forced"] is False
        assert body["drivers"] == ["channelEmulator"]

    def test_refused_response_lists_multiple_blockers(self, db):
        _make_execution(db, executed_by="test_case_runner", case_name="用例 A")
        # 硬件 VRT 的 paused 也占驱动 (pause 不释放任何东西) —— 两种形态各一条。
        _make_execution(db, status="paused", mode="ota",
                        executed_by="vrt-user", case_name="VRT B")
        with patch(
            "app.services.instrument_hal_service.reload_hal_service_atomic",
            new=AsyncMock(),
        ):
            resp = client.post("/api/v1/instruments/hal/reload")
        assert resp.status_code == 409
        # See Codex P2 fix note above — top-level body, not detail-wrapped.
        payload = resp.json()
        assert "detail" not in payload
        assert "2 active blocker" in payload["reason"]
        kinds = {b["kind"] for b in payload["blockers"]}
        statuses = {b["status"] for b in payload["blockers"]}
        names = {b["name"] for b in payload["blockers"]}
        assert kinds == {"test_execution"}
        assert statuses == {"running", "paused"}
        assert names == {"用例 A", "VRT B"}


# ============================================================
# Layer 3: lifecycle lock serialises concurrent reloads
# ============================================================


class TestLifecycleLock:
    """The lifecycle lock guarantees only one shutdown/init runs at a
    time. Without it, concurrent reload requests would each tear down
    + reinit the global ``_hal_service``, and the second one's init
    could clobber the first's mid-flight."""

    def test_concurrent_reloads_serialise(self):
        """Race the lock: launch two ``reload_hal_service_atomic``
        coroutines and assert the inner shutdown/init bodies don't
        interleave. We instrument the inner functions to record entry +
        exit order; if the lock works, you see [shutdown1, init1,
        shutdown2, init2] — never [shutdown1, shutdown2, ...]."""
        # Build an isolated module-level lock test — we patch the
        # inner shutdown/init to record calls + yield to the scheduler.
        import app.services.instrument_hal_service as svc

        # Reset the lock so each test run starts clean; pytest may
        # carry a stale lock from a previous test that ran on a
        # different event loop.
        svc._hal_lifecycle_lock = None

        order: list[str] = []

        async def fake_shutdown_inner():
            order.append(f"shutdown_start")
            # yield so the OTHER coroutine has a chance to barge in if
            # the lock is broken. With the lock, it'll wait.
            await asyncio.sleep(0.01)
            order.append(f"shutdown_end")

        async def fake_init_inner(mode):
            order.append(f"init_start")
            await asyncio.sleep(0.01)
            order.append(f"init_end")

        async def runner():
            with patch.object(svc, "_shutdown_hal_service_inner", new=fake_shutdown_inner), \
                 patch.object(svc, "_initialize_hal_service_inner", new=fake_init_inner):
                # Two concurrent reloads.
                await asyncio.gather(
                    svc.reload_hal_service_atomic(svc.DriverMode.MOCK),
                    svc.reload_hal_service_atomic(svc.DriverMode.MOCK),
                )

        asyncio.run(runner())

        # Two complete shutdown→init cycles, no interleave. The
        # exact 8-element shape pins the lock semantics: each call's
        # shutdown_start/end and init_start/end must run consecutively
        # before the other call's shutdown_start fires.
        assert order == [
            "shutdown_start", "shutdown_end",
            "init_start", "init_end",
            "shutdown_start", "shutdown_end",
            "init_start", "init_end",
        ]

    def test_atomic_calls_inner_helpers_in_order(self):
        """Sanity: ``reload_hal_service_atomic`` does the shutdown
        BEFORE the init, every time. Catches a future refactor that
        accidentally flips them."""
        import app.services.instrument_hal_service as svc

        svc._hal_lifecycle_lock = None
        order: list[str] = []

        async def fake_shutdown_inner():
            order.append("shutdown")

        async def fake_init_inner(mode):
            order.append("init")

        async def runner():
            with patch.object(svc, "_shutdown_hal_service_inner", new=fake_shutdown_inner), \
                 patch.object(svc, "_initialize_hal_service_inner", new=fake_init_inner):
                await svc.reload_hal_service_atomic(svc.DriverMode.MOCK)

        asyncio.run(runner())
        assert order == ["shutdown", "init"]


# ============================================================
# ARCH-1 S3 — 闸门换源: 占 HAL 的活跃执行行也要拦 reload
#
# 背景: P2-5 写这个闸门时"正式测试"就等于 TestPlan。ARCH-1 S1 之后
# 正式测试是 TestCase 直接执行 (case-runner), 它不写 TestPlan ——
# 从 S1 上线 (124d7e5) 起, 跑着用例点重载会静默拆掉驱动。
#
# 变异自验对应表 (⚠️ ARCH-1 S4c 重写 —— 计划半截删除后, 原表两行与实况
# 相反/已不存在: "砍 find_execution_blockers 只留 plan 判据"物理上做不到了,
# "删 plan 半截 → H-b 红"正好说反 —— S4c 删的就是它, H-b 现在**绿**):
# - 把 plan 半截加回去 (find_reload_blockers 再并上计划查询) → H-b 第一段红
#   (``find_reload_blockers(db) == []`` 不再成立)
# - 砍 find_execution_blockers → H-a/H-c/H-b 第二段全红 (判据自此单源, 砍了
#   就什么都拦不住)
# - 谓词写成 mode IS NULL (排除全部 VRT) → H-g 红 (硬件 VRT 被放过,
#   这正是 Codex #241 D1 抓到的、我第一版设计稿的错版)
# - 谓词写成 status != completed → H-d 红 (历史 pending 僵尸行拦死 reload)
# ============================================================

from app.models.test_plan import TestCase, TestExecution  # noqa: E402
from app.services.hal_reload_policy import (  # noqa: E402
    NON_HAL_EXECUTION_MODE,
    find_execution_blockers,
)


def _make_execution(
    db,
    *,
    status: str = "running",
    executed_by: str = "test_case_runner",
    mode: str | None = None,
    case_name: str | None = None,
) -> TestExecution:
    case_id = None
    if case_name is not None:
        case = TestCase(
            id=uuid.uuid4(),
            name=case_name,
            test_type="MIMO_OTA",
            configuration={},
            created_by="pytest",
        )
        db.add(case)
        db.commit()
        case_id = case.id
    ex = TestExecution(
        id=uuid.uuid4(),
        test_case_id=case_id,
        status=status,
        mode=mode,
        executed_by=executed_by,
    )
    db.add(ex)
    db.commit()
    return ex


def test_ha_running_case_execution_blocks_reload(db):
    """H-a: 用例直接执行 (S1 正门) 跑着时必须拦住 reload。
    这条就是 S1 上线以来的生产空窗 —— 变异 (砍执行行判据) 会让它红。"""
    _make_execution(db, executed_by="test_case_runner", case_name="吞吐用例")

    blockers = find_reload_blockers(db)
    assert len(blockers) == 1
    assert blockers[0].kind == "test_execution"
    assert "吞吐用例" in blockers[0].name
    # 拒绝文案要说清去哪取消 (设计稿 §5.1 风险点)
    assert "取消" in blockers[0].detail


def test_active_in_process_instrument_lease_blocks_reload(db, monkeypatch):
    import app.services.hal_reload_policy as policy

    monkeypatch.setattr(
        policy,
        "active_test_lease_purpose",
        lambda: "diagnostic-sequence:uxm-health",
        raising=False,
    )

    blockers = policy.find_reload_blockers(db)

    assert len(blockers) == 1
    assert blockers[0].kind == "instrument_lease"
    assert "uxm-health" in blockers[0].detail


def test_hb_legacy_plan_rows_no_longer_block(db):
    """H-b **契约已变** (ARCH-1 S4c) —— 这条从"并集不是替换"翻面成
    "计划半截已删"。**不是回归, 是有意的**:

    S3 写这条时的理由是"计划 PAUSED 期间步骤间没有 running 执行行, 但驱动
    状态仍被持有" —— 那个理由的前提是**有东西在驱动**。S4b 拆掉了计划
    runner, 计划再也不会被执行, 前提消失, 保护恒空。

    留着反而有害: 一行 brownfield 的 paused 计划会成为**永久** 409 blocker
    (cancel/complete/resume/PATCH 全随 S4b 删了, 应用内无端点能清它),
    逼操作员用 force=true —— 而 force 会连真在跑的用例执行一起绕过,
    正是本模块要防的事。

    遗留行由 test_case_runner.reset_orphaned_plan_chain_rows 启动时清成终态
    (见 test_arch1_case_runner.TestOrphanedPlanChainReset)。
    """
    _make_plan(db, name="暂停的遗留计划", status=TestPlanStatus.PAUSED.value)
    _make_plan(db, name="在跑的遗留计划", status=TestPlanStatus.RUNNING.value)

    assert find_reload_blockers(db) == [], (
        "计划行不该再拦 HAL 重载 —— S4c 已把闸门的计划半截删掉"
    )

    # 反向: 判据换成执行行之后, 保护本身没弱
    _make_execution(db, executed_by="test_case_runner", case_name="真在跑的用例")
    blockers = find_reload_blockers(db)
    assert len(blockers) == 1 and blockers[0].kind == "test_execution", (
        "换源后活跃执行行必须仍然拦得住 —— 否则这次删除削弱了保护"
    )


def test_hc_commissioning_chains_block_reload(db):
    """H-c: 暗室首测 / 单相位诊断 (现场最常用的链) 也要拦。"""
    for marker in ("commissioning_api", "commissioning_adhoc"):
        ex = _make_execution(db, executed_by=marker, case_name=f"{marker} 用例")
        blockers = find_execution_blockers(db)
        assert len(blockers) == 1, f"{marker} 没被拦住"
        assert blockers[0].kind == "test_execution"
        db.delete(ex)
        db.commit()


def test_hd_historical_pending_rows_do_not_block(db):
    """H-d 不变量: 历史 pending 僵尸行不许成为 blocker —— 谓词写宽
    (如 status != completed) 会让 reload 被永久拦死。"""
    for i in range(50):
        _make_execution(db, status="pending", executed_by="commissioning_api")

    assert find_execution_blockers(db) == []


def test_hf_digital_twin_does_not_block(db):
    """H-f: 纯数字仿真不持驱动, 不该拦 reload。"""
    _make_execution(db, mode=NON_HAL_EXECUTION_MODE, executed_by="vrt-user")

    assert find_execution_blockers(db) == []


def test_hg_hardware_vrt_still_blocks(db):
    """H-g: conducted / ota 是**真硬件** VRT, 必须照拦。

    Codex #241 D1: 我第一版设计稿写的是 `mode IS NULL`(排除全部 VRT),
    那会把这两种硬件模式一起放过 —— 硬件路测跑着时 reload 照样拆驱动。
    变异 = 把谓词还原成 mode IS NULL → 本条红。
    """
    for hw_mode in ("conducted", "ota"):
        ex = _make_execution(db, mode=hw_mode, executed_by="vrt-user")
        blockers = find_execution_blockers(db)
        assert len(blockers) == 1, f"硬件 VRT ({hw_mode}) 没被拦住"
        db.delete(ex)
        db.commit()


def test_he_force_still_bypasses_execution_blockers(db):
    """H-e: force=true 的既有语义不许因换源而变 —— 现场有时明知测试
    卡在坏驱动上, reload 才是逃生口。"""
    _make_execution(db, executed_by="test_case_runner", case_name="卡住的用例")

    with patch(
        "app.services.instrument_hal_service.reload_hal_service_atomic",
        new=AsyncMock(return_value=(True, "reloaded", ["channelEmulator"])),
    ):
        resp = client.post("/api/v1/instruments/hal/reload?force=true")

    assert resp.status_code == 200, resp.text
    assert resp.json().get("forced") is True


def test_hh_paused_hardware_vrt_blocks(db):
    """Codex #242 第二轮: 硬件 VRT 的 **paused** 也占着驱动。

    VRTExecutionService.pause() 只做 _transition(PAUSED) —— 什么都不释放,
    resume() 直接回 running。暂停期间 reload 会拆掉它期望 resume 时还在的
    硬件配置。这跟本模块**曾**给 TestPlan PAUSED 写的理由逐字一致 ——
    那半截 S4c 已删 (计划不再被执行), 但 VRT 这支理由仍成立 (真有东西在驱动)。

    内在一致性: 本 PR 已承认 conducted/ota 占真硬件 (据此让 running 的
    它们拦 reload), 就不能说 paused 时不占。
    变异 = 谓词只留 status == "running" → 本条红。
    """
    for hw_mode in ("conducted", "ota"):
        ex = _make_execution(db, status="paused", mode=hw_mode,
                             executed_by="vrt-user")
        blockers = find_execution_blockers(db)
        assert len(blockers) == 1, f"paused 的硬件 VRT ({hw_mode}) 没被拦住"
        db.delete(ex)
        db.commit()


def test_hh_paused_digital_twin_does_not_block(db):
    """反方向: 纯仿真的 paused 照样不拦 (它本来就不占驱动)。"""
    _make_execution(db, status="paused", mode=NON_HAL_EXECUTION_MODE,
                    executed_by="vrt-user")
    assert find_execution_blockers(db) == []


def test_hh_paused_non_vrt_row_does_not_block(db):
    """反方向: paused 是 TestExecution 里的 VRT-specific 状态 —— 非 VRT
    行不该因为这个新分支被误拦 (谓词那支要求 mode 非空)。"""
    _make_execution(db, status="paused", mode=None,
                    executed_by="test_case_runner")
    assert find_execution_blockers(db) == []
