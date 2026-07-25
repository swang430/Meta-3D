"""P1-21: HAL 会话卫生 — SCPI 互斥 / 超时排水 / INP deferred 超时 / 输出冻结。

2026-07-03 现场全天串线/wedge 的系统性正解:
- ① broadcaster (1s 循环 32+ 查询) 与测量序列共用 F64 单 socket 无互斥 →
  应答串线/错位/僵死 (当日 P1 根因) → per-driver _scpi_lock 串行化;
- ② 超时后应答迟到留在会话里, 下一条 query 读错位 → 锁内 SYST:ERR? 排水
  (实测 2 条即净, 上限 4), 原异常照抛但会话已净 (替代"超时必重载"纪律);
- ③ INP 测量族 deferred-response (结果就绪才回) → 超时按测量时长动态;
- ④ 输出功率测量 STOPPED 态冻结 → metrics 显式标注。
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import List, Optional
from unittest.mock import MagicMock

import pyvisa
import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver, VISA_TIMEOUT_AUTOSET
from app.hal.propsim_fs16 import RealPropsimFs16Driver


def _tmo_error() -> pyvisa.errors.VisaIOError:
    return pyvisa.errors.VisaIOError(pyvisa.constants.VI_ERROR_TMO)


class _ConcurrencyProbe:
    """fake visa resource: 记录 query/write 临界区的最大并发度。"""

    def __init__(self, delay_s: float = 0.005):
        self._delay = delay_s
        self._active = 0
        self._lock = threading.Lock()
        self.max_concurrency = 0
        self.calls: List[str] = []
        self.timeout = 5000

    def _enter(self, cmd: str):
        with self._lock:
            self._active += 1
            self.max_concurrency = max(self.max_concurrency, self._active)
            self.calls.append(cmd)
        time.sleep(self._delay)

    def _exit(self):
        with self._lock:
            self._active -= 1

    def query(self, cmd: str) -> str:
        self._enter(cmd)
        try:
            return "0,\"No error\""
        finally:
            self._exit()

    def write(self, cmd: str) -> None:
        self._enter(cmd)
        self._exit()


class TestScpiMutex:
    @pytest.mark.asyncio
    async def test_concurrent_f64_io_serialized(self):
        """20 路并发 query+write → 临界区最大并发度必须是 1 (锁生效)。"""
        drv = RealPropsimF64Driver("f64-mutex", {})
        probe = _ConcurrencyProbe()
        drv._visa_resource = probe
        tasks = []
        for i in range(10):
            tasks.append(drv._query(f"Q{i}?"))
            tasks.append(drv._write(f"W{i}"))
        await asyncio.gather(*tasks)
        assert probe.max_concurrency == 1, (
            f"SCPI 临界区并发度 {probe.max_concurrency} > 1 — 应答会串线"
        )
        assert len(probe.calls) == 20

    @pytest.mark.asyncio
    async def test_concurrent_fs16_io_serialized(self):
        drv = RealPropsimFs16Driver("fs16-mutex", {})
        probe = _ConcurrencyProbe()
        drv._visa_resource = probe
        await asyncio.gather(*[drv._query(f"Q{i}?") for i in range(10)])
        assert probe.max_concurrency == 1


class _TimeoutThenDrainVisa:
    """fake: 首条命令超时 (TMO); 迟到应答走**裸 read** 通道 (late_replies),
    SYST:ERR? 错误队列按 drain_script 回放 — 对齐两步式排水语义。"""

    def __init__(self, drain_script: List[str], late_replies: Optional[List[str]] = None):
        self.timeout = 5000
        self.calls: List[str] = []
        self.read_calls = 0
        self._drain = list(drain_script)
        self._late = list(late_replies or [])
        self._timed_out = False

    def query(self, cmd: str) -> str:
        self.calls.append(cmd)
        if not self._timed_out:
            self._timed_out = True
            raise _tmo_error()
        if self._drain:
            return self._drain.pop(0)
        return "0,\"No error\""

    def read(self) -> str:
        self.read_calls += 1
        if self._late:
            return self._late.pop(0)
        raise _tmo_error()  # 无残留 → 读超时 (对齐信号)

    def write(self, cmd: str) -> None:
        self.calls.append(cmd)


class TestTimeoutDrain:
    @pytest.mark.asyncio
    async def test_timeout_drains_and_reraises(self):
        """超时 → 裸 read 吃迟到应答 + SYST:ERR? 清队列 → 原 TMO 异常仍上抛。"""
        drv = RealPropsimF64Driver("f64-drain", {})
        visa = _TimeoutThenDrainVisa(['0,"No error"'], late_replies=["-3.21"])
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("OUTP:MEAS:RES:GET? 1")
        assert visa.calls[0] == "OUTP:MEAS:RES:GET? 1"
        assert visa.read_calls >= 2  # 吃掉 1 条迟到 + 1 次超时确认对齐
        drains = [c for c in visa.calls[1:] if c == "SYST:ERR?"]
        assert len(drains) == 1, visa.calls  # 对齐后 1 条 no-error 即净

    @pytest.mark.asyncio
    async def test_zero_prefixed_late_reply_eaten_by_bare_read(self):
        """Codex #199→#203 收敛: 以 0 开头的迟到应答 ("0.0") 由裸 read 根治;
        ERR 队列通道的杂音仍只认 0,"No error" 可解析形态。"""
        drv = RealPropsimF64Driver("f64-drain-zero", {})
        visa = _TimeoutThenDrainVisa(
            ['-200,"stale"', '0,"No error"'], late_replies=["0.0"]
        )
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("OUTP:MEAS:RES:GET? 1")
        drains = [c for c in visa.calls if c == "SYST:ERR?"]
        assert len(drains) == 2, visa.calls  # ERR 队列 1 条真错误 + 1 条净

    @pytest.mark.asyncio
    async def test_drain_caps_at_four(self):
        """错误队列淹没时排水 4 条止损 (不无限循环), 原异常照抛。"""
        drv = RealPropsimF64Driver("f64-drain-cap", {})
        visa = _TimeoutThenDrainVisa(["-200,\"e\""] * 10)
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("*OPC?")
        drains = [c for c in visa.calls if c == "SYST:ERR?"]
        assert len(drains) == 4, visa.calls

    @pytest.mark.asyncio
    async def test_syst_err_self_timeout_realigned_by_bare_read(self):
        """Codex #202/#203: 超时命令本身是 SYST:ERR?、迟到应答恰是合法 no-error —
        "连续 N 条 clean" 在错位链上不收敛 (每条都合法), 裸 read 吃残留才是
        重对齐手段; 对齐后 1 条即净, 无需 streak 特判。"""
        drv = RealPropsimF64Driver("f64-drain-self", {})
        visa = _TimeoutThenDrainVisa([], late_replies=['0,"No error"'])
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("SYST:ERR?")
        assert visa.read_calls >= 2  # 吃掉自指迟到应答 + 超时确认对齐
        drains = [c for c in visa.calls[1:] if c == "SYST:ERR?"]
        assert len(drains) == 1, visa.calls

    @pytest.mark.asyncio
    async def test_session_usable_after_drain(self):
        """排水成功后, 下一条命令读到的是自己的应答 (不再错位)。"""
        drv = RealPropsimF64Driver("f64-post-drain", {})
        visa = _TimeoutThenDrainVisa(["0,\"No error\""], late_replies=["late-junk"])
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("SLOW:CMD?")
        visa._drain = ["fresh-answer"]  # 会话已净, 下一条正常回
        assert await drv._query("FAST:CMD?") == "fresh-answer"


class TestInpDeferredTimeout:
    def test_timeout_scales_with_measurement_time(self):
        f = RealPropsimF64Driver._inp_meas_timeout_ms
        assert f(3.0) == VISA_TIMEOUT_AUTOSET       # 短测量走下限
        assert f(10.0) == VISA_TIMEOUT_AUTOSET      # 10s 档: (10+5)s = 下限
        assert f(20.0) == 25000                     # 长测量: 时长 + 5s 缓冲

    @pytest.mark.asyncio
    async def test_measure_input_passes_dynamic_timeout(self):
        drv = RealPropsimF64Driver("f64-inp", {})
        drv._visa_resource = MagicMock()
        seen: List[Optional[int]] = []

        async def _fake_query(cmd, timeout=None, **_kw):
            seen.append(timeout)
            return "-10.5,8.2"

        drv._query = _fake_query  # type: ignore[assignment]
        assert await drv.measure_input(1, measurement_time_s=20.0) == (-10.5, 8.2)
        assert seen == [25000]


class TestAutosetSubsetTimeout:
    @pytest.mark.asyncio
    async def test_autoset_inputs_subset_uses_dynamic_timeout(self):
        """Codex #202 R3: 子集版 *OPC? 原 (t+2)s 在 3s 档只给 5s — 必须走
        _inp_meas_timeout_ms (15s 下限, deferred-response 命令族)。"""
        drv = RealPropsimF64Driver("f64-inp-subset", {})
        drv._visa_resource = MagicMock()
        seen: List[Optional[int]] = []

        async def _fake_query(cmd, timeout=None, **_kw):
            if cmd == "*OPC?":
                seen.append(timeout)
                return "1"
            return '0,"No error"'

        async def _fake_write(cmd, timeout=None):
            return None

        drv._query = _fake_query  # type: ignore[assignment]
        drv._write = _fake_write  # type: ignore[assignment]
        assert await drv.autoset_inputs([1], measurement_time_s=3.0) is True
        assert seen == [VISA_TIMEOUT_AUTOSET], seen  # 3s 档走 15s 下限 (原 bug 5s)


class TestOutputFrozenAnnotation:
    @pytest.mark.asyncio
    async def test_metrics_flag_follows_emulation_state(self):
        drv = RealPropsimF64Driver("f64-frozen", {})
        drv._visa_resource = MagicMock()
        drv._tx_antennas, drv._rx_antennas = 1, 1

        # F64R-1: get_metrics 的 emulation_running 改问仪器 (STATE?), 不再读缓存 —
        # fake 要按命令分流, 由 `_state` 驱动本用例想造的运行态。
        _state = {"v": "STOPPED"}

        async def _fake_query(cmd, timeout=None, **_kw):
            if cmd == "DIAG:SIMU:STATE?":
                return _state["v"]
            return "-20.0"

        drv._query = _fake_query  # type: ignore[assignment]
        m = await drv.get_metrics()
        assert m.metrics["emulation_running"] is False
        assert m.metrics["output_powers_frozen"] is True  # STOPPED: 读数不可信
        _state["v"] = "RUNNING"
        m = await drv.get_metrics()
        assert m.metrics["emulation_running"] is True
        assert m.metrics["output_powers_frozen"] is False
