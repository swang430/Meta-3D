"""P2-5 — HAL Reload refuse/force policy + concurrency lock.

Pins both layers:

- ``app/services/hal_reload_policy.find_reload_blockers``: pure SQL
  over ``TestPlan``. Returns one ``ReloadBlocker`` per running /
  paused row. Empty list when nothing's in flight.
- ``POST /api/v1/instruments/hal/reload``: thin wrapper around the
  finder + the atomic shutdown/reinit helper.
  - default (``force=false``) returns HTTP 409 with the blocker
    payload when any TestPlan is running / paused.
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
    BLOCKING_TEST_PLAN_STATUSES,
    ReloadBlocker,
    find_reload_blockers,
    find_test_plan_blockers,
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


class TestFindTestPlanBlockers:
    """Pin the per-status filter semantics — these directly drive the
    refuse decision, so the boundary between "blocks" and "doesn't
    block" needs explicit pins per status value."""

    def test_no_plans_at_all_returns_empty(self, db):
        assert find_test_plan_blockers(db) == []

    def test_draft_plan_does_not_block(self, db):
        _make_plan(db, name="Draft Plan", status=TestPlanStatus.DRAFT.value)
        assert find_test_plan_blockers(db) == []

    def test_running_plan_blocks(self, db):
        plan = _make_plan(db, name="Running Plan", status=TestPlanStatus.RUNNING.value)
        blockers = find_test_plan_blockers(db)
        assert len(blockers) == 1
        b = blockers[0]
        assert b.kind == "test_plan"
        assert b.id == str(plan.id)
        assert b.name == "Running Plan"
        assert b.status == "running"
        assert "running" in b.detail.lower()

    def test_paused_plan_blocks(self, db):
        """Paused is included intentionally — a paused test plan still
        owns driver state (a resume is expected), so HAL teardown
        between pause + resume corrupts the state silently. Documenting
        the choice here so a future "make paused not block" PR has to
        revisit the reasoning."""
        _make_plan(db, name="Paused Plan", status=TestPlanStatus.PAUSED.value)
        blockers = find_test_plan_blockers(db)
        assert len(blockers) == 1
        assert blockers[0].status == "paused"

    def test_completed_failed_cancelled_do_not_block(self, db):
        for status in (
            TestPlanStatus.COMPLETED.value,
            TestPlanStatus.FAILED.value,
            TestPlanStatus.CANCELLED.value,
        ):
            _make_plan(db, name=f"{status} plan", status=status)
        assert find_test_plan_blockers(db) == []

    def test_queued_does_not_block(self, db):
        """Queued = enqueued for execution, not yet acquired drivers.
        Reload during queue is fine — the runner will pick up the
        post-reload HAL state when it dequeues."""
        _make_plan(db, name="Queued Plan", status=TestPlanStatus.QUEUED.value)
        assert find_test_plan_blockers(db) == []

    def test_multiple_running_plans_each_become_a_blocker(self, db):
        _make_plan(db, name="Plan A", status=TestPlanStatus.RUNNING.value)
        _make_plan(db, name="Plan B", status=TestPlanStatus.PAUSED.value)
        _make_plan(db, name="Plan C", status=TestPlanStatus.RUNNING.value)
        blockers = find_test_plan_blockers(db)
        assert len(blockers) == 3
        names = sorted(b.name for b in blockers)
        assert names == ["Plan A", "Plan B", "Plan C"]

    def test_blocking_statuses_constant_matches_finder_behaviour(self, db):
        """Guard rail: ``BLOCKING_TEST_PLAN_STATUSES`` is the
        documentation source for which statuses block. Pin that adding
        a new TestPlanStatus value DOESN'T silently start blocking —
        the constant has to be edited explicitly. Catches a future
        refactor that uses the enum directly."""
        assert set(BLOCKING_TEST_PLAN_STATUSES) == {"running", "paused"}

    def test_find_reload_blockers_composes_test_plan_source(self, db):
        """``find_reload_blockers`` is the public surface used by the
        endpoint — it should delegate to (and stay equivalent to) the
        TestPlan finder while only TestPlan is wired in."""
        _make_plan(db, name="Running Plan", status=TestPlanStatus.RUNNING.value)
        composite = find_reload_blockers(db)
        tp_only = find_test_plan_blockers(db)
        assert [b.kind for b in composite] == [b.kind for b in tp_only]
        assert [b.id for b in composite] == [b.id for b in tp_only]


# ============================================================
# Layer 2: HTTP endpoint refuse / force behaviour
# ============================================================


class TestReloadEndpointRefuse:
    """``POST /api/v1/instruments/hal/reload`` should return HTTP 409
    with a structured blocker payload when blockers exist and
    ``force=true`` was NOT passed."""

    def test_refuses_with_409_and_payload_when_running_plan_present(self, db):
        _make_plan(db, name="Calibration sweep", status=TestPlanStatus.RUNNING.value)
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
        assert b["kind"] == "test_plan"
        assert b["name"] == "Calibration sweep"
        assert b["status"] == "running"
        assert payload["force_hint"]  # non-empty UX hint

    def test_force_true_proceeds_despite_blockers(self, db):
        _make_plan(db, name="Sweep", status=TestPlanStatus.RUNNING.value)

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
        _make_plan(db, name="Plan A", status=TestPlanStatus.RUNNING.value)
        _make_plan(db, name="Plan B", status=TestPlanStatus.PAUSED.value)
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
        assert kinds == {"test_plan"}
        assert statuses == {"running", "paused"}
        assert names == {"Plan A", "Plan B"}


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
# 变异自验对应表:
# - 砍 find_execution_blockers (只留 plan 判据) → H-a/H-c 红 (今天的实况)
# - 并集改成只查 TestExecution (删 plan 半截) → H-b 红 (paused 保护退化)
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


def test_hb_paused_plan_still_blocks_after_resource_switch(db):
    """H-b: 并集不是替换 —— 计划 PAUSED 时步骤间没有 running 执行行,
    但驱动状态仍被持有, 保护不许退化。"""
    _make_plan(db, name="暂停的计划", status=TestPlanStatus.PAUSED.value)

    blockers = find_reload_blockers(db)
    assert len(blockers) == 1
    assert blockers[0].kind == "test_plan"


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
