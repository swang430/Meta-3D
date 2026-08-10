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
        # `getLogger(__name__)` 是模块级 logger 的标准写法，跟 SCPI 无关 —— 放行。
        # （第一版把所有解析不出的都当违规，红在这上面：那是我判据写宽了，不是代码有问题。）
        if isinstance(arg, ast.Name) and arg.id == "__name__":
            continue
        if text is None:
            # ⚠️ 解析不出来的写法（变量名、字符串拼接、常量引用）**一律当违规**
            #    （外审 P2）：`_LOG = "app.hal.scpi"; getLogger(_LOG)` 或
            #    `getLogger("app.hal." + "scpi")` 会让 text 保持 None，
            #    原来 `continue` 掉等于门静默放行 —— 那条路照样不带来源标记。
            if wrapper_span[0] <= node.lineno <= wrapper_span[1]:
                continue
            offenders.append(
                f"line {node.lineno}: getLogger(<解析不出的表达式>) —— "
                f"本门只认字面量与 f-string，请改成字面量或走 _unverified_scpi_logger()"
            )
            continue
        if not text.startswith("app.hal.scpi"):
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


def test_connected_log_is_actually_emitted_with_source_fields():
    """⭐ 行为门（外审连续两轮要求）：真的跑一次 HAL 初始化，捕获那条日志。

    前两版都是「查源码里有没有这行」的检查，外审两次指出它防不住：
      - 第一版查「有没有调用 connected_log_fields」→ 把调用改成
        `logger.info(_msg)`（丢掉 extra）门照样绿；
      - 结构化字段丢了之后，混合模式下 hal_mode 又会回落成错误的全局值。

    这一版**真的驱动 `_initialize_from_db`**，断言那条记录的正文前缀、
    驱动类名、以及三个结构化字段都在。

    让它报错的改法：
      - 调用点改回自拼 f-string → 前缀/类名/字段全对不上；
      - 调用点只传 msg 不传 extra → 三个字段断言红；
      - `connected_log_fields` 里前缀改回读全局开关 → 前缀断言红。
    """
    import asyncio
    import uuid as _uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.db.database as dbmod
    from app.db.database import Base
    from app.models.instrument import (
        InstrumentCategory as CategoryModel,
        InstrumentModel,
    )
    from app.services import instrument_hal_service as hal_mod
    from app.services.instrument_hal_service import DriverMode, InstrumentHALService

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    captured = []

    class _RecordingLogger:
        def __getattr__(self, name):
            def _call(msg, *a, **kw):
                if name == "info":
                    captured.append((msg, kw.get("extra") or {}))
            return _call

    orig_session, orig_logger = dbmod.SessionLocal, hal_mod.logger
    try:
        dbmod.SessionLocal = Session
        hal_mod.logger = _RecordingLogger()

        db = Session()
        cat = CategoryModel(id=_uuid.uuid4(), category_key="vna", category_name="VNA",
                            is_active=True, display_order=1, driver_mode="mock")
        db.add(cat); db.commit(); db.refresh(cat)
        mdl = InstrumentModel(id=_uuid.uuid4(), category_id=cat.id,
                              vendor="Keysight", model="E5071C", capabilities={})
        db.add(mdl); db.commit(); db.refresh(mdl)
        cat.selected_model_id = mdl.id
        db.commit()
        db.close()

        svc = InstrumentHALService(mode=DriverMode.MOCK)
        asyncio.run(svc._initialize_from_db())
    finally:
        dbmod.SessionLocal, hal_mod.logger = orig_session, orig_logger
        Base.metadata.drop_all(bind=engine)

    connected = [(m, e) for m, e in captured if "connected →" in str(m)]
    assert connected, (
        f"没捕获到 connected 那行日志 —— 共 {len(captured)} 条 info。"
        f"前几条：{[str(m)[:60] for m, _ in captured[:3]]}"
    )
    msg, extra = connected[0]

    assert msg.startswith("[HAL-MOCK]"), f"装的是 Mock 驱动，正文却是：{msg[:50]}"
    assert "MockVNA" in msg, f"正文里没有实际驱动类名：{msg}"
    assert extra.get("driver_source") == "mock", (
        f"结构化字段 driver_source={extra.get('driver_source')!r} —— "
        f"调用点可能只传了 msg、没传 extra"
    )
    assert extra.get("simulated") is True
    assert extra.get("instrument_id") == "vna"


def test_scpi_logger_source_follows_the_transport_actually_used():
    """⭐ 外审抓出：走已加载的真驱动时，不能标「来源不确定」。

    `_get_loaded_hal_driver()` 只返回**真驱动**（Mock 会被它跳过），
    所以走那条路时来源是已知的。原实现无条件标 unverified —— 真仪器的往返
    被盖成「不确定」，是反方向的同一个毛病。

    让它报错的改法：把 `_run_command_via_hal` 里的 `_unverified_scpi_logger(driver)`
    改回 `_unverified_scpi_logger()` → 「真驱动应标 real」那条断言红。
    """
    from app.api.instrument import _unverified_scpi_logger
    from app.hal.rf_switch import EtslSwitchDriver
    from app.services.instrument_hal_service import MockVNA

    # 裸 socket：证明不了对面是谁
    _, kw = _unverified_scpi_logger().process("x", {})
    assert kw["extra"]["driver_source"] == "unverified"

    # 走真驱动：来源已知
    _, kw = _unverified_scpi_logger(EtslSwitchDriver.__new__(EtslSwitchDriver)).process("x", {})
    assert kw["extra"]["driver_source"] == "real", (
        f"走已加载的真驱动时应标 real，实际 {kw['extra']['driver_source']!r} —— "
        f"把真仪器的往返盖成「不确定」"
    )
    assert kw["extra"]["simulated"] is False

    # 走 mock 驱动（今天 _get_loaded_hal_driver 会跳过，但判据本身要对）
    _, kw = _unverified_scpi_logger(MockVNA.__new__(MockVNA)).process("x", {})
    assert kw["extra"]["driver_source"] == "mock"
    assert kw["extra"]["simulated"] is True


def test_run_command_via_hal_stamps_real_on_its_first_record():
    """⭐ 行为门（外审要求）：真的跑一次，看**第一条**记录标的是什么。

    上一版是 AST 检查「函数里有没有那句重绑定」，外审指出两个洞：
      - 把重绑定**挪到第一条日志之后** → AST 仍找得到那句赋值，门绿，
        而第一条 WRITE 记录仍被调用方的「不确定」标记盖住；
      - 它只检查「有任意参数」，`_unverified_scpi_logger(None)` 也能通过。

    让它报错的改法：把重绑定删掉、或挪到首条日志之后、或改成传 None。
    """
    import asyncio
    import logging as _logging

    from app.api import instrument as inst_mod
    from app.hal.rf_switch import EtslSwitchDriver

    records = []

    class _Sink(_logging.Handler):
        def emit(self, record):
            records.append(record)

    class _FakeRealDriver(EtslSwitchDriver):
        def __init__(self):  # 不跑父类 __init__
            self.instrument_id = "rfSwitch"

        async def _do_query(self, command, **kw):
            return "OK"

        async def _do_write(self, command, **kw):
            return None

    lg = _logging.getLogger("app.hal.scpi")
    sink = _Sink()
    lg.addHandler(sink)
    prev_level, prev_disabled = lg.level, lg.disabled
    lg.setLevel(_logging.DEBUG)
    lg.disabled = False          # 别的测试跑 alembic 会把 logger 禁掉
    try:
        asyncio.run(inst_mod._run_command_via_hal(
            _FakeRealDriver(), "*IDN?", inst_mod._unverified_scpi_logger(), "rfSwitch"))
    finally:
        lg.removeHandler(sink)
        lg.setLevel(prev_level)
        lg.disabled = prev_disabled

    assert records, "一条 SCPI 记录都没产生 —— 无法验证来源标记"
    first = records[0]
    assert getattr(first, "driver_source", None) == "real", (
        f"走真驱动时**第一条**记录标的是 "
        f"{getattr(first, 'driver_source', None)!r}，应为 real —— "
        f"重绑定可能被挪到了首条日志之后"
    )
    assert getattr(first, "simulated", "MISSING") is False


def test_probe_summary_is_stamped_after_the_driver_is_known():
    """探测那条路的摘要行，必须在「按 driver 重取日志器」之后才发。

    外审指出：摘要行原先在重绑定之前发出 → 摘要标「不确定」、
    同一次探测的命令记录标 real，自相矛盾。

    ⚠️ **如实标注档次**：这是**源码顺序检查**，不是行为门 ——
    跑真正的 probe 端点要拉起 DB + 租约 + 驱动，成本远超本片。
    它能防「把重绑定删掉」和「把摘要挪到重绑定之前」，
    防不住「重绑定传了个错的 driver」（那一格由上面那条行为门覆盖）。

    让它报错的改法：删掉 probe 分支里那句重绑定，或把它挪到摘要行之后。
    """
    import pathlib as _pl

    src = (_pl.Path(__file__).resolve().parents[1] / "app/api/instrument.py").read_text(encoding="utf-8")
    marker = '[SCPI-PROBE]'
    assert marker in src, "找不到 SCPI-PROBE 摘要行 —— 改写了？请更新本门"

    summary_at = src.index(marker)
    rebind = "scpi_logger = _unverified_scpi_logger(hal_driver)"
    assert rebind in src, (
        "探测分支里没有按 hal_driver 重取日志器 —— "
        "摘要行会被调用方的「来源不确定」标记盖住，而同一次探测的命令记录标 real"
    )
    assert src.index(rebind) < summary_at, (
        "那句重绑定出现在摘要行**之后** —— 摘要仍会被标成「不确定」"
    )
