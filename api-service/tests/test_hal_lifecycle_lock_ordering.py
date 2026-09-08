"""HAL 生命周期锁 ↔ 仪表租约锁的取锁顺序 —— 内审 F1。

2026-08-07 现场分支内审实测：两条 reload 路径的取锁顺序**相反**，
两个请求撞上就 ABBA 永久死锁，此后所有 F64/UXM 端点、正式执行、暗室首测、
诊断序列全部无限等待，**只能重启后端**。

  路径 A  `POST /hal/reload?force=true`（instrument.py:440，**不进** guard）
          → reload_hal_service_atomic → 取【生命周期锁】
          → _initialize_hal_service_inner → park_idle_instruments → 要【租约锁】

  路径 B  `POST /hal/reload`（非 force，instrument.py:444）/ `POST /hal/switch`
          → hal_mutation_guard → 取【租约锁】
          → reload_hal_service_atomic → 要【生命周期锁】

`force` 那条的注释写着"现场主动放弃在飞操作的逃生口" —— 正是现场出事时最容易
点的按钮。修法是把 park 移出生命周期锁（`_park_after_lifecycle` 在锁外调用）。

⚠ 这道门的由来：修复本身**此前只有一个放在临时目录里的探针脚本**，不在仓库。
内审把 park 挪回锁内（精确复现该 bug）后跑 81 个用例**全绿** —— 按 ⓪④
「门不过变异 = 门不算数」，那次修复当时不算数。本文件把探针收编进来。
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import instrument_hal_service as hal_service
from app.services import instrument_test_lease as lease_mod


@pytest.mark.asyncio
async def test_reload_paths_do_not_deadlock_on_opposite_lock_order(monkeypatch):
    """⭐ 行为门：两条取锁顺序相反的路径并发时必须都能返回。

    变异：把 `await _park_after_lifecycle()` 挪回 `reload_hal_service_atomic`
    的 `async with _get_lifecycle_lock():` 块内 → 本条红（2 秒超时）。

    ⚠ 判据是**两条都返回**，不是"没抛异常" —— 死锁的表现是永远不返回，
    没有异常可抓。用 `wait_for` 把"不返回"变成可观察的失败。
    """
    order: list[str] = []

    async def _initialize_without_database(_service) -> None:
        """锁顺序门只需要空 HAL；不得依赖开发库是否已升级到最新迁移。"""

    monkeypatch.setattr(
        hal_service.InstrumentHALService,
        "_initialize_from_db",
        _initialize_without_database,
    )

    # ⚠ 必须调**真函数**，不能手工复刻路径 —— 复刻等于测我自己写的副本，
    #   而且很容易把"修复前"的顺序抄进来当基线（本门第一版就这么假红的）。
    async def _path_a_force_reload() -> None:
        # `POST /hal/reload?force=true` 走的就是这条：不进 guard，直接 atomic
        order.append("A:start")
        await hal_service.reload_hal_service_atomic(hal_service.DriverMode.MOCK)
        order.append("A:done")

    async def _path_b_guarded_reload() -> None:
        # `POST /hal/reload`（非 force）/ `POST /hal/switch`：先 guard 再 atomic
        await asyncio.sleep(0.01)
        async with lease_mod.hal_mutation_guard():
            order.append("B:guard")
            await hal_service.reload_hal_service_atomic(hal_service.DriverMode.MOCK)
            order.append("B:done")

    try:
        await asyncio.wait_for(
            asyncio.gather(_path_a_force_reload(), _path_b_guarded_reload()),
            timeout=5.0,
        )
    except asyncio.TimeoutError:  # pragma: no cover - 只在回归时走到
        pytest.fail(
            "两条 reload 路径 ABBA 死锁（5 秒未完成）—— 租约锁被永久持有，"
            "此后所有 F64/UXM 端点、正式执行、诊断序列全部无限等待，只能重启后端。\n"
            f"实际进度: {order}"
        )

    assert "A:done" in order and "B:done" in order


def test_park_is_called_outside_the_lifecycle_lock():
    """⭐ 结构门：锁死"park 必须在锁外"这个修法本身。

    上面那条并发门在**单跑**时可能因调度巧合侥幸通过（两个 task 恰好不交错），
    这条从源码结构上钉死：`_park_after_lifecycle()` 的调用点不得落在
    `async with _get_lifecycle_lock():` 的缩进块内。

    变异：把调用挪进锁块 → 本条红。
    """
    import inspect
    import re

    src = inspect.getsource(hal_service)
    lines = src.splitlines()

    calls = [i for i, ln in enumerate(lines)
             if "await _park_after_lifecycle()" in ln]
    assert calls, "找不到 _park_after_lifecycle 的调用点 —— 门需要重新定位"

    for idx in calls:
        indent = len(lines[idx]) - len(lines[idx].lstrip())
        # 向上找最近的、缩进更浅的 `async with ... _get_lifecycle_lock()`
        for j in range(idx - 1, -1, -1):
            ln = lines[j]
            if not ln.strip():
                continue
            cur = len(ln) - len(ln.lstrip())
            if cur >= indent:
                continue
            if re.search(r"async with .*_get_lifecycle_lock\(\)", ln):
                pytest.fail(
                    f"第 {idx + 1} 行的 park 调用落在生命周期锁块内"
                    f"（锁在第 {j + 1} 行）—— ABBA 死锁会回来：\n"
                    f"  {lines[j].strip()}\n  ...\n  {lines[idx].strip()}"
                )
            break   # 只看最近的那层外围块


def test_category_activation_parks_outside_the_lifecycle_lock():
    """P2-72 类别激活也不得持生命周期锁再进入 idle park。"""
    import inspect

    src = inspect.getsource(hal_service.activate_hal_category_atomic)
    lines = src.splitlines()
    lock_line = next(
        i for i, line in enumerate(lines)
        if "async with _get_lifecycle_lock()" in line
    )
    park_line = next(
        i for i, line in enumerate(lines)
        if "await park_idle_instrument(category_key)" in line
    )
    guard_line = next(
        i for i, line in enumerate(lines)
        if "if result.status in" in line
    )
    lock_indent = len(lines[lock_line]) - len(lines[lock_line].lstrip())
    guard_indent = len(lines[guard_line]) - len(lines[guard_line].lstrip())

    assert park_line > guard_line > lock_line
    assert guard_indent == lock_indent
