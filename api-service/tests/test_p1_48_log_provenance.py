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


def test_no_raw_scpi_logger_outside_the_wrapper():
    """所有拿 `app.hal.scpi` logger 的地方，都必须走那个包装函数。

    ⚠️ 用 AST 扫全部 `getLogger` 调用，**不是数字符串**（内审 F3）：
    原来那版数 `logging.getLogger("app.hal.scpi")` 出现几次 —— 只防「把已有的三处改回去」，
    **防不住「新开一条路」**：另写一句 `getLogger(f"app.hal.scpi.{key}")` 门照样绿。
    而 Adapter 的立论恰恰是「新开的点也自动带上」。
    单引号写法、`from logging import getLogger`、子 logger 名，数字符串也全绕得过。

    让它报错的改法：在 `instrument.py` 里任何地方新写一句
    `logging.getLogger("app.hal.scpi.xxx")`（不经包装）→ 报错。
    """
    import ast
    import pathlib as _pl

    src = _pl.Path(__file__).resolve().parents[1] / "app/api/instrument.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    # 先定位包装函数自身的行号区间 —— 它内部那一处是合法的
    wrapper_span = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_unverified_scpi_logger":
            wrapper_span = (node.lineno, node.end_lineno)
    assert wrapper_span, "找不到 _unverified_scpi_logger —— 它被改名或删了？请更新本门"

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else None)
        if name != "getLogger" or not node.args:
            continue
        arg = node.args[0]
        # 认字面量与 f-string 两种写法
        text = None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            text = arg.value
        elif isinstance(arg, ast.JoinedStr):
            text = "".join(v.value for v in arg.values
                           if isinstance(v, ast.Constant) and isinstance(v.value, str))
        if not text or not text.startswith("app.hal.scpi"):
            continue
        if wrapper_span[0] <= node.lineno <= wrapper_span[1]:
            continue  # 包装函数内部那一处
        offenders.append(f"line {node.lineno}: getLogger({text!r})")

    assert not offenders, (
        "这些地方直接拿了 app.hal.scpi 的 logger，绕开了包装 → 它们的日志不带来源标记：\n  "
        + "\n  ".join(offenders)
        + "\n改用 _unverified_scpi_logger()。"
    )


# ─────────────────────────────────────────────────────────────
# ③ 「connected →」那行：真假取这台驱动自己的（本片最主要的修复）
# ─────────────────────────────────────────────────────────────

def test_connected_line_uses_the_drivers_own_source_not_the_global_switch():
    """⭐ 内审 F1 抓出：这处修复原先零门守着 —— 把它改回按全局开关标，测试全绿。

    2026-08-07 实测：app.log 里 21 条 `[HAL-MOCK] channelEmulator: connected →
    Keysight PROPSIM F64`，而那台当时连的是真机。

    让它报错的改法：把 `connected_log_fields` 里的 `is_mock_driver(driver)`
    换成读全局开关 → 两个方向的断言都会红。
    """
    from app.hal.rf_switch import EtslSwitchDriver
    from app.services.instrument_hal_service import MockVNA, connected_log_fields

    mock_msg, mock_extra = connected_log_fields(
        MockVNA.__new__(MockVNA), "vna", "Keysight", "E5071C")
    assert mock_msg.startswith("[HAL-MOCK]"), f"模拟驱动应标 MOCK，实际：{mock_msg[:40]}"
    assert mock_extra["driver_source"] == "mock"
    assert mock_extra["simulated"] is True

    # 反向：真驱动必须标 REAL（只测单向的话，把常量写死成 MOCK 照样绿）
    real_msg, real_extra = connected_log_fields(
        EtslSwitchDriver.__new__(EtslSwitchDriver), "rfSwitch", "ETS", "EMCenter")
    assert real_msg.startswith("[HAL-REAL]"), f"真驱动应标 REAL，实际：{real_msg[:40]}"
    assert real_extra["driver_source"] == "real"
    assert real_extra["simulated"] is False


def test_connected_line_carries_the_actual_driver_class_name():
    """行内要带实际装上的驱动类名 —— 就绪表里早有，只有这行丢了它。"""
    from app.services.instrument_hal_service import MockVNA, connected_log_fields

    msg, _ = connected_log_fields(MockVNA.__new__(MockVNA), "vna", "V", "M")
    assert "MockVNA" in msg, f"行内应含实际驱动类名，实际：{msg}"


def test_connected_line_prefix_and_field_come_from_one_source():
    """文本前缀与结构化字段必须同源（内审 F4）。

    原先前缀用 `is_mock_driver(driver)`、字段用 `getattr(driver, "driver_source", "-")`，
    两个来源会打架；而 `"-"` 不在日志过滤器的白名单里，会静默回落成全局开关的值 ——
    于是同一行出现「文本写 [HAL-REAL]、字段写 mock」。

    让它报错的改法：把 extra 里的 driver_source 改回 getattr(driver, ...) 兜底 "-"，
    再喂一个 driver_source 被改坏的驱动 → 前缀与字段对不上。
    """
    from app.services.instrument_hal_service import MockVNA, connected_log_fields

    class _LiarVNA(MockVNA):
        driver_source = "-"       # 属性被改坏
        simulated = None

    msg, extra = connected_log_fields(_LiarVNA.__new__(_LiarVNA), "vna", "V", "M")
    prefix_says_mock = msg.startswith("[HAL-MOCK]")
    field_says_mock = extra["driver_source"] == "mock"
    assert prefix_says_mock == field_says_mock, (
        f"同一行里文本说 {'mock' if prefix_says_mock else 'real'}、"
        f"字段说 {extra['driver_source']!r} —— 两个来源打架了"
    )
    # 且字段值必须落在日志过滤器认的白名单里，否则会静默回落全局开关
    assert extra["driver_source"] in ("real", "mock", "unverified")


# ─────────────────────────────────────────────────────────────
# ④ 断言打在渲染出来的 JSON 上，不是中间量（内审 F2）
# ─────────────────────────────────────────────────────────────

def test_hal_mode_actually_reaches_the_rendered_log_line():
    """⭐ 内审 F2 抓出：门原先只断言 record.hal_mode 这个中间量。

    把 JsonFormatter 里渲染 hal_mode 的那行删掉，字段会从日志里**彻底消失**，
    而 230 个日志相关测试全绿 —— 用户打开的是日志文件，不是 record 对象。

    让它报错的改法：从 JsonFormatter.format 删掉 `"hal_mode": ...` 那一行。
    """
    import json

    from app.core.logging_config import JsonFormatter

    rec = _record(driver_source="mock")
    ContextFilter().filter(rec)
    line = json.loads(JsonFormatter().format(rec))

    assert "hal_mode" in line, "渲染出来的日志行里没有 hal_mode 字段 —— 用户看不到"
    assert line["hal_mode"] == "mock", (
        f"日志行里 hal_mode 是 {line['hal_mode']!r}，应为 mock"
    )
