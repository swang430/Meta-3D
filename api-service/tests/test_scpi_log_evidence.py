"""P1-30 门 — SCPI 往返日志的证据能力。

守三件事（每条门旁边的注释写明"改成什么会让它红"）：
  ① 不变量：ContextFilter 的 contextvar 只兜底，不得覆盖 extra= 显式给的
     instrument_id —— 原实现无条件覆盖，实测 759,894 行 SCPI 日志的
     instrument_id 恒为 "-"（100%）。
  ② 行为：往返抛异常时留下 direction=ERR 的证据，**且异常原样传出**。
  ③ 行为：响应超上限时消息体带 truncated 标记，且 resp_len 记**截断前**
     的真实长度 —— 原实现 [:200] 静默截断，实测 22,914 条 real RX 恰好
     200 字符，且 RX 最大长度就是 200（长响应从没在日志里露过全貌）。

⚠ 本文件断言 logger emit。in-process alembic 的 fileConfig
  (disable_existing_loggers=True) 会永久禁用已导入的 logger，导致全量顺序下
  flaky —— 所以每个用例都经 `scpi_capture` fixture 显式复位 .disabled。
  提交前跑**全量**而非单文件才能暴露这类污染。
"""

import asyncio
import logging
import time

import pytest

from app.config import Settings, settings
from app.core.logging_config import ContextFilter, current_instrument_id
from app.hal import base as hal_base
from app.hal.base import InstrumentDriver


class _RecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _StubDriver(InstrumentDriver):
    """最小驱动：_do_write / _do_query 的行为由构造参数决定。

    刻意**不**覆盖 _write / _query（base 的禁令：子类只覆盖 _do_*），
    这样门测的就是生产路径本身。
    """

    def __init__(self, instrument_id="stub", *, response="", raises=None,
                 is_async=False):
        super().__init__(instrument_id, {})
        self._response = response
        self._raises = raises
        self._is_async = is_async

    def _do_query(self, cmd, **kwargs):
        if self._is_async:
            return self._async_query()
        if self._raises:
            raise self._raises
        return self._response

    async def _async_query(self):
        if self._raises:
            raise self._raises
        return self._response

    def _do_write(self, cmd, **kwargs):
        if self._is_async:
            return self._async_write()
        if self._raises:
            raise self._raises
        return None

    async def _async_write(self):
        if self._raises:
            raise self._raises
        return None

    # InstrumentDriver 的抽象接口 —— 门用不到，给最小实现。
    async def connect(self): return True
    async def disconnect(self): return True
    async def configure(self, config): return True
    async def get_capabilities(self): return []
    async def get_metrics(self): return None
    async def reset(self): return True


@pytest.fixture
def scpi_capture():
    """挂一个 handler 到 app.hal.scpi，用完摘掉并复位 .disabled。"""
    logger = logging.getLogger("app.hal.scpi")
    handler = _RecordingHandler()
    prev_level, prev_disabled = logger.level, logger.disabled
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.disabled = False
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
        logger.disabled = prev_disabled


def _by_direction(handler, direction):
    return [r for r in handler.records
            if getattr(r, "direction", None) == direction]


# ── 门① 不变量：contextvar 只兜底，不覆盖 extra= ─────────────────

class TestContextFilterDoesNotClobber:
    """变异：把 filter 里的 `if not hasattr(...)` 去掉 → 第一个用例红。"""

    def test_explicit_instrument_id_survives(self):
        record = logging.LogRecord(
            "app.hal.scpi.f64-1", logging.DEBUG, __file__, 1, "TX: *IDN?",
            None, None,
        )
        # 模拟 logger.debug(..., extra={"instrument_id": ...}) 的效果
        record.instrument_id = "f64-1"

        assert ContextFilter().filter(record) is True
        assert record.instrument_id == "f64-1", (
            "extra= 显式给的 instrument_id 被 contextvar 覆盖了 —— "
            "这正是 759,894 行日志全变成 '-' 的根因"
        )

    def test_contextvar_still_fills_when_absent(self):
        """兜底能力不能因为收窄而丢失。"""
        token = current_instrument_id.set("from-ctx")
        try:
            record = logging.LogRecord(
                "app.some.module", logging.INFO, __file__, 1, "hi", None, None,
            )
            assert not hasattr(record, "instrument_id")
            ContextFilter().filter(record)
            assert record.instrument_id == "from-ctx"
        finally:
            current_instrument_id.reset(token)

    def test_scpi_path_end_to_end_carries_instrument_id(self, scpi_capture):
        """真实生效端：走 _query 的记录，过完 filter 后仍带真身份。"""
        driver = _StubDriver("f64-e2e", response="OK")
        driver._query("*IDN?")

        ctx_filter = ContextFilter()
        for record in scpi_capture.records:
            ctx_filter.filter(record)
        assert scpi_capture.records, "没有任何 SCPI 记录被捕获"
        assert {r.instrument_id for r in scpi_capture.records} == {"f64-e2e"}


# ── 门② 行为：异常留证据 + 原样重抛 ──────────────────────────────

class TestErrorLeavesEvidence:
    """变异：去掉 _query/_write 里的 except 分支 → ERR 断言红；
    把 `raise` 改成 `return None`（吞异常）→ pytest.raises 断言红。"""

    def test_sync_query_error_logged_and_reraised(self, scpi_capture):
        driver = _StubDriver("q-err", raises=TimeoutError("boom"))
        with pytest.raises(TimeoutError, match="boom"):
            driver._query("SYST:ERR?")

        errs = _by_direction(scpi_capture, "ERR")
        assert len(errs) == 1, "抛异常的查询没有留下 direction=ERR 的证据"
        assert errs[0].error_type == "TimeoutError"
        assert errs[0].query == "SYST:ERR?"
        assert errs[0].duration_ms >= 0
        # TX 仍在 —— "打算发"和"发失败了"是两条独立事实
        assert len(_by_direction(scpi_capture, "TX")) == 1

    def test_sync_write_error_logged_and_reraised(self, scpi_capture):
        driver = _StubDriver("w-err", raises=ConnectionResetError("gone"))
        with pytest.raises(ConnectionResetError):
            driver._write("INIT:IMM")

        errs = _by_direction(scpi_capture, "ERR")
        assert len(errs) == 1
        assert errs[0].error_type == "ConnectionResetError"
        assert not _by_direction(scpi_capture, "OK"), "失败的写不该记 OK"

    def test_async_query_error_logged_and_reraised(self, scpi_capture):
        """异步路径是最容易漏的一半 —— 异常在 await 时刻才抛，
        包在 _query 外层的 try 根本拦不住。"""
        driver = _StubDriver("aq-err", raises=OSError("socket"), is_async=True)
        with pytest.raises(OSError):
            asyncio.run(driver._query("*OPC?"))

        errs = _by_direction(scpi_capture, "ERR")
        assert len(errs) == 1, "异步查询的异常没留下 ERR 行（await 路径漏了）"
        assert errs[0].error_type == "OSError"

    def test_async_write_error_logged_and_reraised(self, scpi_capture):
        driver = _StubDriver("aw-err", raises=OSError("socket"), is_async=True)
        with pytest.raises(OSError):
            asyncio.run(driver._write("INP:LEV:AUTOSET 0,3"))

        assert len(_by_direction(scpi_capture, "ERR")) == 1
        assert not _by_direction(scpi_capture, "OK")


class TestWriteSuccessIsPaired:
    """变异：删掉 _write 里的 _log_scpi_done 调用 → 红。"""

    def test_sync_write_logs_ok_with_duration(self, scpi_capture):
        driver = _StubDriver("w-ok")
        driver._write("INIT:IMM")

        oks = _by_direction(scpi_capture, "OK")
        assert len(oks) == 1, "成功的写命令没有配对的完成记录"
        assert oks[0].duration_ms >= 0

    def test_async_write_logs_ok_after_await(self, scpi_capture):
        driver = _StubDriver("aw-ok", is_async=True)
        asyncio.run(driver._write("INIT:IMM"))

        assert len(_by_direction(scpi_capture, "OK")) == 1

    def test_async_write_ok_not_logged_before_await(self, scpi_capture):
        """OK 必须记在真正执行完之后 —— 只创建 coroutine 不 await 时
        不该出现 OK（否则 OK 就退化成"打算发"的同义词）。"""
        driver = _StubDriver("aw-lazy", is_async=True)
        coro = driver._write("INIT:IMM")
        try:
            assert not _by_direction(scpi_capture, "OK")
        finally:
            coro.close()


# ── 门③ 行为：截断显式化 + resp_len 记真实长度 ───────────────────

class TestTruncationIsExplicit:
    """变异：把 truncated 标记去掉 → 第一条红；
    把 resp_len 改成 len(截断后的 body) → 第二条红。"""

    def test_long_response_marked_and_true_length_recorded(
        self, scpi_capture, monkeypatch
    ):
        monkeypatch.setattr(hal_base, "_SCPI_LOG_RESP_MAX", 50)
        payload = "X" * 3412
        driver = _StubDriver("trunc", response=payload)
        driver._query("BSE:MEAS:...:JSON?")

        rx = _by_direction(scpi_capture, "RX")
        assert len(rx) == 1
        msg = rx[0].getMessage()
        assert "[truncated 50/3412]" in msg, (
            "长响应被砍了却没有任何标记 —— 读者无法区分"
            "'仪器就回这么短' 和 '被日志砍了'"
        )
        assert rx[0].resp_len == 3412, "resp_len 必须是截断前的真实长度"
        # 消息体确实短了（没有偷偷全量写进去）。
        # ⚠ 别用 msg.count("X") 当判据 —— "RX: " 前缀自己就带一个 X，
        #   会多算一个（写这条门时实际踩过）。锚在前缀上才精确。
        assert msg == f"RX: {'X' * 50}…[truncated 50/3412]"

    def test_short_response_not_marked(self, scpi_capture, monkeypatch):
        monkeypatch.setattr(hal_base, "_SCPI_LOG_RESP_MAX", 50)
        driver = _StubDriver("short", response="3550000000")
        driver._query("FREQ?")

        rx = _by_direction(scpi_capture, "RX")[0]
        assert "truncated" not in rx.getMessage()
        assert rx.resp_len == 10

    def test_empty_response_is_distinguishable(self, scpi_capture):
        """空回复要能跟'有去无回'区分开：前者有 RX 行 + resp_len=0 + 耗时，
        后者根本没有 RX 行。实测 real 模式 60,565 条空回复（占 RX 35.4%）。"""
        driver = _StubDriver("empty", response="")
        driver._query("INP:MEAS:RES:GET? 1")

        rx = _by_direction(scpi_capture, "RX")
        assert len(rx) == 1
        assert rx[0].resp_len == 0
        assert rx[0].duration_ms >= 0

    def test_whitespace_only_response_not_conflated_with_empty(self, scpi_capture):
        """⭐ 仪器回 `"   \\n"` 与什么都没回，是两件事（Codex #273 P2）。

        `resp_len` 量的必须是**原始响应**，不是 strip 之后的 —— 否则
        whitespace-only 与真空都成 0，而本片正是拿"空回复 60,565 条"
        当立项证据的，量错长度等于把证据量废。

        变异：把 `raw_len = len(response)` 改回 `len(response.strip())` → 红。
        """
        _StubDriver("ws", response="   \n")._query("INP:MEAS:RES:GET? 1")
        _StubDriver("nil", response="")._query("INP:MEAS:RES:GET? 2")

        ws, nil = _by_direction(scpi_capture, "RX")
        assert ws.resp_len == 4, "whitespace-only 响应被当成了空响应"
        assert nil.resp_len == 0
        assert ws.resp_len != nil.resp_len
        # 显示体仍然 strip（日志里不留一行看不见的空白）
        assert ws.getMessage() == "RX: "

    def test_resp_len_counts_raw_not_stripped(self, scpi_capture):
        """正常响应带尾部换行时，resp_len 记的是线上收到的字符数。"""
        _StubDriver("nl", response="3550000000\r\n")._query("FREQ?")
        rx = _by_direction(scpi_capture, "RX")[0]
        assert rx.resp_len == 12, "resp_len 应为原始 12 字符，不是 strip 后的 10"
        assert rx.getMessage() == "RX: 3550000000"

    def test_default_limit_is_2000(self):
        """默认上限从 200 放宽到 2000。

        ⚠ 断言的是 **field 声明的默认值**，不是 `settings` 实例的当前值 ——
        后者会被 `.env` 的 `LOG_SCPI_RESP_MAX` 改掉，而那正是我们**文档里
        承诺可以改**的旋钮。用实例值当断言等于"用一次旋钮测试套就红"
        （内审 F2 实证：`LOG_SCPI_RESP_MAX=200 pytest` → 1 failed，且失败
        信息把整个 Settings repr 连同 DATABASE_URL 一起打出来）。
        """
        assert Settings.model_fields["log_scpi_resp_max"].default == 2000

    def test_effective_limit_comes_from_settings_not_a_literal(self, monkeypatch):
        """⭐ 生效端门：**不 monkeypatch 那个模块常量**，从 `_log_scpi_response`
        的实际输出反推上限。

        内审 F1 实证：原来三条旋钮门只测 `_resolve_resp_max()` 的返回值，
        两条截断门又都 `monkeypatch.setattr(hal_base, "_SCPI_LOG_RESP_MAX", 50)`
        把生效端替换掉 —— 两边都碰不到"这个常量从哪来"这条链。把
        `_SCPI_LOG_RESP_MAX = _resolve_resp_max()` 改写成字面量 `200`，
        19 条门**全绿**，旋钮当场死掉而无人察觉。

        变异：把该行改成 `_SCPI_LOG_RESP_MAX = 200` → 本条红。

        ⚠ 期望值**从 settings 现算**，不写死 2000（Codex #273 P2）——
        初版把 `[truncated 2000/2001]` 硬写进断言，等于**又一次**把
        "文档承诺可调的旋钮"钉成测试契约：`.env` 配 `LOG_SCPI_RESP_MAX=200`
        的合法部署上，本条会红。这跟内审 F2 抓的是同一个错，我在**修 F2
        的那一次**顺手在替代门里重犯了一遍。
        """
        expected = hal_base._resolve_resp_max()   # 从 settings 现算，不写死
        assert hal_base._SCPI_LOG_RESP_MAX == expected, (
            f"模块常量 ({hal_base._SCPI_LOG_RESP_MAX}) 与 settings 现算值 "
            f"({expected}) 不一致 —— 它八成被写成了字面量，旋钮已失效"
        )
        # 生效端：造一条刚好比上限长 1 的响应，从实际输出反推用的是哪个上限
        driver = _StubDriver("eff", response="Y" * (expected + 1))
        capture = _RecordingHandler()
        logger = logging.getLogger("app.hal.scpi")
        prev_disabled = logger.disabled
        logger.addHandler(handler := capture)
        logger.setLevel(logging.DEBUG)
        logger.disabled = False
        try:
            driver._query("LONG?")
        finally:
            logger.removeHandler(handler)
            logger.disabled = prev_disabled

        rx = [r for r in capture.records
              if getattr(r, "direction", None) == "RX"][0]
        assert rx.resp_len == expected + 1
        assert f"[truncated {expected}/{expected + 1}]" in rx.getMessage(), (
            f"生效端用的上限不是 settings 的 {expected} —— 模块常量可能被"
            f"写成了字面量，或没有走 settings"
        )

    def test_reads_from_settings_not_os_environ(self, monkeypatch):
        """旋钮必须走 app.config.settings —— 本项目的 .env 由 pydantic-settings
        直接读进 Settings 对象，**不注入 os.environ**（实证：import app.config
        前后 os.environ 里都没有 DATABASE_URL）。用 os.getenv 取值会让 .env 里
        配的 log_scpi_resp_max 被静默忽略，旋钮形同虚设。

        变异：把 _resolve_resp_max 改回 os.getenv("SCPI_LOG_RESP_MAX") → 红。
        """
        monkeypatch.setattr(settings, "log_scpi_resp_max", 200)
        assert hal_base._resolve_resp_max() == 200

    def test_bad_value_falls_back(self, monkeypatch):
        monkeypatch.setattr(settings, "log_scpi_resp_max", "不是数字")
        assert hal_base._resolve_resp_max() == 2000

    def test_negative_value_clamped_to_zero(self, monkeypatch):
        monkeypatch.setattr(settings, "log_scpi_resp_max", -5)
        assert hal_base._resolve_resp_max() == 0


class TestQueryDurationRecorded:
    """⚠ `duration_ms >= 0` 是**恒真断言** —— 内审 F6 实证：把 base.py 里
    8 处 `(time.perf_counter() - t0) * 1000` 全换成常量 `0.0`，19 条门全绿。
    存在性只能防"字段完全没写"，防不住任何错值。所以这里断言的是
    **慢调用和快调用在数值上分得开**（行为档），不是"字段在不在"。
    """

    SLOW_S = 0.05

    class _SlowDriver(_StubDriver):
        def _do_query(self, cmd, **kwargs):
            time.sleep(TestQueryDurationRecorded.SLOW_S)
            return "ok"

    def test_sync_query_duration_tracks_real_elapsed(self, scpi_capture):
        """变异：duration 改成常量 → 慢查询的读数不再 ≥ 实际耗时 → 红。"""
        fast = _StubDriver("fast", response="ok")
        fast._query("*IDN?")
        self._SlowDriver("slow", response="ok")._query("SLOW?")

        rxs = _by_direction(scpi_capture, "RX")
        assert len(rxs) == 2
        fast_ms, slow_ms = rxs[0].duration_ms, rxs[1].duration_ms
        assert slow_ms >= self.SLOW_S * 1000 * 0.8, (
            f"慢查询(睡了 {self.SLOW_S}s)记成 {slow_ms}ms —— duration_ms 没在量真实耗时"
        )
        assert slow_ms > fast_ms * 5, (
            f"慢({slow_ms}ms)和快({fast_ms}ms)在读数上分不开 —— 该字段无判别力"
        )

    def test_async_query_duration_tracks_real_elapsed(self, scpi_capture):
        class _SlowAsync(_StubDriver):
            def _do_query(self, cmd, **kwargs):
                return self._slow()

            async def _slow(self):
                await asyncio.sleep(TestQueryDurationRecorded.SLOW_S)
                return "ok"

        asyncio.run(_SlowAsync("aslow")._query("SLOW?"))
        rx = _by_direction(scpi_capture, "RX")[0]
        assert rx.duration_ms >= self.SLOW_S * 1000 * 0.8

    def test_write_ok_duration_tracks_real_elapsed(self, scpi_capture):
        class _SlowWrite(_StubDriver):
            def _do_write(self, cmd, **kwargs):
                time.sleep(TestQueryDurationRecorded.SLOW_S)

        _SlowWrite("wslow")._write("INIT:IMM")
        ok = _by_direction(scpi_capture, "OK")[0]
        assert ok.duration_ms >= self.SLOW_S * 1000 * 0.8


class TestErrorDetailIsBounded:
    """变异：去掉 _log_scpi_error 里的 detail 截断 → 红。"""

    def test_long_exception_message_truncated(self, scpi_capture, monkeypatch):
        monkeypatch.setattr(hal_base, "_SCPI_LOG_RESP_MAX", 50)
        # 驱动里 `ValueError(f"Cannot parse '{raw}'")` 这类写法会把整段
        # 响应嵌进异常 —— 不设限的话，被 RX 挡住的长响应从 ERR 行原样漏出去。
        driver = _StubDriver("errcap", raises=ValueError("Z" * 900))
        with pytest.raises(ValueError):
            driver._query("PARSE?")

        msg = _by_direction(scpi_capture, "ERR")[0].getMessage()
        assert "[truncated 50/900]" in msg
        assert msg.count("Z") == 50
