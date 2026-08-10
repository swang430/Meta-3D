"""P1-48 日志线：日志里的真假标记要来自「这一行说的那台仪表」，不是全局开关。

治的毛病（用户 2026-08-09 手工测试时问的）：打开日志分不出哪台仪表是真的。
而且有几处标反了 —— 实测 2026-08-07 的 app.log 里有 21 条
`[HAL-MOCK] channelEmulator: connected → Keysight PROPSIM F64`，那台当时连的是真机。
"""
from __future__ import annotations

import logging

import pytest

from app.core.logging_config import ContextFilter


def _record(**extra) -> logging.LogRecord:
    r = logging.LogRecord("app.test", logging.INFO, __file__, 1, "msg", (), None)
    for k, v in extra.items():
        setattr(r, k, v)
    return r


# ─────────────────────────────────────────────────────────────
# ① 日志里的 hal_mode 优先用这一行自己带的来源
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("own_source", ["real", "mock", "unverified"])
def test_hal_mode_prefers_the_records_own_source(own_source):
    """这一行自己带了来源，就用它，不看全局开关。

    让它报错的改法：把过滤器改回无条件读全局模式 → 三个取值全对不上。
    """
    rec = _record(driver_source=own_source)
    ContextFilter().filter(rec)
    assert rec.hal_mode == own_source, (
        f"这条记录自己说来源是 {own_source}，日志里却写成 {rec.hal_mode} —— "
        f"又去读全局开关了"
    )


def test_hal_mode_falls_back_when_record_has_no_source(monkeypatch):
    """记录自己没带来源时，才回落到全局开关。"""
    from app.services import instrument_hal_service as hal_mod

    class _FakeSvc:
        class mode:
            value = "real"

    monkeypatch.setattr(hal_mod, "_hal_service", _FakeSvc(), raising=False)
    rec = _record()
    ContextFilter().filter(rec)
    assert rec.hal_mode == "real"


def test_hal_mode_never_creates_a_mock_singleton(monkeypatch):
    """⭐ 全局单例为空时写 "-"，**绝不当场造一个 mock 单例顶上**。

    原实现调 get_hal_service()，它发现单例为空会现场 new 一个 DriverMode.MOCK
    **并写回全局变量** —— 于是「这个进程还没初始化 HAL」被打成 mock，
    跟「真在跑 mock」分不开（实测每次热重载头 26 行都被误标），
    而且日志过滤器还留下了写副作用。

    让它报错的改法：把回落改回 `get_hal_service()` → 断言 hal_mode == "-" 会失败
    （会拿到 "mock"），且断言全局仍为 None 也会失败。
    """
    from app.services import instrument_hal_service as hal_mod

    monkeypatch.setattr(hal_mod, "_hal_service", None, raising=False)
    rec = _record()
    ContextFilter().filter(rec)

    assert rec.hal_mode == "-", (
        f"全局单例为空时应写 '-'（表示不知道），实际写了 {rec.hal_mode!r} —— "
        f"多半是又去调 get_hal_service() 了，那会当场造一个 mock 单例"
    )
    assert hal_mod._hal_service is None, (
        "日志过滤器把全局单例给创建出来了 —— 打条日志不该有这种副作用"
    )


# ─────────────────────────────────────────────────────────────
# ② 手敲 SCPI / 探测那几条路，标「来源不确定」
# ─────────────────────────────────────────────────────────────

def test_manual_scpi_path_marks_unverified():
    """那几条路绕开正规驱动、直接连数据库里配的地址 —— 连上了不等于对面是真仪器。

    ⚠️ 直接测 Adapter 的 process()，**不走真的 emit**：仓库里有测试会跑 alembic，
    而 in-process 的 fileConfig(disable_existing_loggers=True) 会把已存在的 logger
    全部禁用 —— 依赖 emit 的断言会变成「单跑绿、全量红」的假红
    （这个坑本仓库记过，本测试第一版就踩了）。

    让它报错的改法：把 Adapter 里那句 setdefault("driver_source", "unverified") 删掉。
    """
    from app.api.instrument import _unverified_scpi_logger

    _, kwargs = _unverified_scpi_logger().process("[SCPI-TERM] *IDN?", {})
    extra = kwargs.get("extra") or {}

    assert extra.get("driver_source") == "unverified", (
        f"手敲那条路的日志应标 unverified，实际 {extra.get('driver_source')!r} —— "
        f"标 real 会把「连上了某个端口」说成「真仪器回的数」"
    )
    assert extra.get("simulated") is None


def test_manual_scpi_path_does_not_override_explicit_extra():
    """调用方自己传了来源就用它的，包装只做兜底。"""
    from app.api.instrument import _unverified_scpi_logger

    _, kwargs = _unverified_scpi_logger().process("x", {"extra": {"driver_source": "real"}})
    assert (kwargs.get("extra") or {}).get("driver_source") == "real"


def test_all_three_manual_scpi_sites_use_the_wrapper():
    """三条路都得用包装过的 logger —— 漏一条那条就没标记。

    这是**数量对等**的检查，不是「有没有这个词」：
    直接 getLogger("app.hal.scpi") 的次数必须为 0。

    让它报错的改法：把任一处改回 `logging.getLogger("app.hal.scpi")` → 计数不为 0。
    """
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app/api/instrument.py"
    text = src.read_text(encoding="utf-8")
    raw = text.count('logging.getLogger("app.hal.scpi")')
    wrapped = text.count("_unverified_scpi_logger()")

    # Adapter 定义里那一处是合法的（它就是包装的实现）
    assert raw == 1, (
        f"app/api/instrument.py 里直接 getLogger('app.hal.scpi') 出现 {raw} 次，"
        f"应只剩 Adapter 定义里那一处 —— 其余都要走 _unverified_scpi_logger()"
    )
    assert wrapped >= 4, (
        f"_unverified_scpi_logger() 只用了 {wrapped} 次（定义 1 + 三条路 3 = 至少 4）"
    )
