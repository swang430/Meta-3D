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
    """fake: 首条命令超时 (TMO), 之后 SYST:ERR? 按脚本回放 (模拟排水)。"""

    def __init__(self, drain_script: List[str]):
        self.timeout = 5000
        self.calls: List[str] = []
        self._drain = list(drain_script)
        self._timed_out = False

    def query(self, cmd: str) -> str:
        self.calls.append(cmd)
        if not self._timed_out:
            self._timed_out = True
            raise _tmo_error()
        if self._drain:
            return self._drain.pop(0)
        return "0,\"No error\""

    def write(self, cmd: str) -> None:
        self.calls.append(cmd)


class TestTimeoutDrain:
    @pytest.mark.asyncio
    async def test_timeout_drains_and_reraises(self):
        """超时 → 排水到 '0,...' 停 → 原 TMO 异常仍上抛 (调用方知道失败)。"""
        drv = RealPropsimF64Driver("f64-drain", {})
        # 排水脚本: 第 1 条读到迟到应答 (垃圾), 第 2 条读到队列空
        visa = _TimeoutThenDrainVisa(["-3.21", "0,\"No error\""])
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("OUTP:MEAS:RES:GET? 1")
        # 原命令 1 + SYST:ERR? × 2 (读到 0 即停, 不多发)
        assert visa.calls[0] == "OUTP:MEAS:RES:GET? 1"
        drains = [c for c in visa.calls[1:] if c == "SYST:ERR?"]
        assert len(drains) == 2, visa.calls

    @pytest.mark.asyncio
    async def test_zero_prefixed_late_reply_does_not_end_drain(self):
        """Codex #199 P1: 迟到应答以 0 开头 ("0.0" 功率 / "0,-3.2" 元组) 不得
        被当成队列空提前停 — 只认 0,"No error" 形态。"""
        drv = RealPropsimF64Driver("f64-drain-zero", {})
        visa = _TimeoutThenDrainVisa(["0.0", "0,-3.2", '0,"No error"'])
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("OUTP:MEAS:RES:GET? 1")
        drains = [c for c in visa.calls if c == "SYST:ERR?"]
        assert len(drains) == 3, visa.calls  # 排过两条迟到杂音, 到真 no-error 才停

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
    async def test_syst_err_timeout_requires_two_clean_reads(self):
        """Codex #202 R2 P2: 超时命令本身是 SYST:ERR? 时, 迟到应答恰可能是合法
        no-error — 须连续两条才判净, 否则排水自己的应答留队列 (仍差一拍)。"""
        drv = RealPropsimF64Driver("f64-drain-self", {})
        visa = _TimeoutThenDrainVisa(['0,"No error"', '0,"No error"'])
        drv._visa_resource = visa
        with pytest.raises(pyvisa.errors.VisaIOError):
            await drv._query("SYST:ERR?")
        drains = [c for c in visa.calls[1:] if c == "SYST:ERR?"]
        assert len(drains) == 2, visa.calls  # 首条 (迟到) 不作数, 连续第二条才净

    @pytest.mark.asyncio
    async def test_session_usable_after_drain(self):
        """排水成功后, 下一条命令读到的是自己的应答 (不再错位)。"""
        drv = RealPropsimF64Driver("f64-post-drain", {})
        visa = _TimeoutThenDrainVisa(["0,\"No error\""])
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

        async def _fake_query(cmd, timeout=None):
            seen.append(timeout)
            return "-10.5,8.2"

        drv._query = _fake_query  # type: ignore[assignment]
        assert await drv.measure_input(1, measurement_time_s=20.0) == (-10.5, 8.2)
        assert seen == [25000]


class TestOutputFrozenAnnotation:
    @pytest.mark.asyncio
    async def test_metrics_flag_follows_emulation_state(self):
        drv = RealPropsimF64Driver("f64-frozen", {})
        drv._visa_resource = MagicMock()
        drv._tx_antennas, drv._rx_antennas = 1, 1

        async def _fake_query(cmd, timeout=None):
            return "-20.0"

        drv._query = _fake_query  # type: ignore[assignment]
        drv._emulation_running = False
        m = await drv.get_metrics()
        assert m.metrics["output_powers_frozen"] is True  # STOPPED: 读数不可信
        drv._emulation_running = True
        m = await drv.get_metrics()
        assert m.metrics["output_powers_frozen"] is False
