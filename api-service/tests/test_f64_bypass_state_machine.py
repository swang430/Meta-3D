"""P2-17 ①: F64 直通/衰落状态机 — STATIC 与回放互斥语义 (2026-07-03 实证)。

实证语义 (onsite-tasks-20260703 "F64 直通态建立"条):
- 运行态切 STATIC≠0 → F64 自动转 STOPPED (直通稳态 = STOPPED + STATIC 3);
- STATIC≠0 下 GO 被 -200 拒 (by design) → start_emulation 内建 GO 前清直通;
- 恢复衰落 = STATIC 0 + GO。
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

from app.hal.base import InstrumentStatus
from app.hal.propsim_f64 import F64BypassMode, RealPropsimF64Driver


def _make_driver():
    drv = RealPropsimF64Driver("f64-bypass", {})
    drv._channel_count = 1
    visa = MagicMock()
    visa.query.side_effect = lambda cmd: "1" if cmd == "*OPC?" else '0,"No error"'
    visa.write.return_value = None
    drv._visa_resource = visa

    async def _w(cmd, timeout=None):
        visa.write(cmd)

    async def _q(cmd, timeout=None):
        return visa.query(cmd)

    drv._write = _w  # type: ignore[assignment]
    drv._query = _q  # type: ignore[assignment]
    return drv, visa


def _writes(visa):
    return [c.args[0] for c in visa.write.call_args_list]


class TestStaticPlaybackMutex:
    async def test_running_switch_to_static_syncs_stopped(self):
        """运行态切 STATIC 3 → F64 自动 STOPPED, 驱动状态必须同步。"""
        drv, _ = _make_driver()
        drv._emulation_running = True
        drv._status = InstrumentStatus.BUSY
        assert await drv.set_bypass_mode(F64BypassMode.CALIBRATION) is True
        assert drv._emulation_running is False  # 不同步会漂移 (冻结标注也依赖)
        assert drv._status == InstrumentStatus.READY
        assert drv._bypass_mode == F64BypassMode.CALIBRATION

    async def test_static_disable_keeps_running_state(self):
        """切回 STATIC 0 不影响运行态推断 (0 与回放不互斥)。"""
        drv, _ = _make_driver()
        drv._emulation_running = True
        assert await drv.set_bypass_mode(F64BypassMode.DISABLED) is True
        assert drv._emulation_running is True

    async def test_start_emulation_clears_static_before_go(self):
        """直通稳态下 GO — 必须先 STATIC 0 再 GO (不清必 -200)。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        drv._bypass_mode = F64BypassMode.CALIBRATION
        drv._passthrough_active = True
        assert await drv.start_emulation() is True
        w = _writes(visa)
        assert w.index("DIAG:SIMU:MODEL:STATIC 0") < w.index("DIAG:SIMU:GO"), w
        assert drv._bypass_mode == F64BypassMode.DISABLED
        assert drv._passthrough_active is False
        assert drv._emulation_running is True

    async def test_start_emulation_clears_static_even_on_cold_cache(self):
        """Codex #201 R2 P2: 缓存 DISABLED (如 HAL 重载后冷实例) 也无条件写
        STATIC 0 — 硬件可能还停在 attach 直通的 STATIC 3, 只信缓存 GO 必 -200。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        assert drv._bypass_mode == F64BypassMode.DISABLED  # 冷缓存
        assert await drv.start_emulation() is True
        w = _writes(visa)
        assert w.index("DIAG:SIMU:MODEL:STATIC 0") < w.index("DIAG:SIMU:GO"), w

    async def test_start_emulation_fails_when_go_rejected(self):
        """Codex #202 R2 P2: GO 失败只经 SYST:ERR? 报 (*OPC? 照答 1) — 错误
        队列门 fail-loud, 不许带着"没在跑"的 F64 返回 True。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        visa.query.side_effect = lambda cmd: (
            "1" if cmd == "*OPC?" else '-200,"Execution error;GO rejected"'
        )
        assert await drv.start_emulation() is False
        assert drv._emulation_running is False
        assert "-200" in (drv._last_error or "")

    async def test_start_rejected_from_passthrough_keeps_bypass_cache(self):
        """Codex #202 R8 P2: 直通态 start 被拒 (STATIC/GO 单门分不清哪步) →
        直通缓存不动 — 漂成"已退出直通"会让 cleanup/诊断漏查, 测量在无衰落
        直通路径上跑假数据; 保守保持 CALIBRATION 是安全侧 (下次 start 无条件
        STATIC 0 幂等)。R5 "被拒状态不动"的对称路径。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        drv._bypass_mode = F64BypassMode.CALIBRATION
        drv._passthrough_active = True
        visa.query.side_effect = lambda cmd: (
            "1" if cmd == "*OPC?" else '-200,"Execution error"'
        )
        assert await drv.start_emulation() is False
        assert drv._bypass_mode == F64BypassMode.CALIBRATION  # 未漂移
        assert drv._passthrough_active is True
        assert drv._emulation_running is False

    async def test_stale_error_before_go_not_misreported(self):
        """Codex #203 P2: GO 前先清 stale FIFO — 早先命令遗留的错误不得把
        成功的 GO 误判成被拒 (假阴性)。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        err_q = ['-113,"Undefined header (stale)"']  # 排水消费后队列即净

        def _q(cmd):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return err_q.pop(0) if err_q else '0,"No error"'
            return '0,"No error"'

        visa.query.side_effect = _q
        assert await drv.start_emulation() is True  # stale 被前置排掉, GO 判成功
        assert drv._emulation_running is True

    async def test_static_write_rejected_keeps_state(self):
        """Codex #202 R5: STATIC 写被拒 (只经 SYST:ERR? 报) → False 且
        _bypass_mode/_emulation_running/_status 全不动 (记了会与仪器实际漂移)。"""
        drv, visa = _make_driver()
        drv._emulation_running = True
        drv._status = InstrumentStatus.BUSY  # agent F2: _status 也要锁定不动
        visa.query.side_effect = lambda cmd: (
            "1" if cmd == "*OPC?" else '-200,"Execution error"'
        )
        assert await drv.set_bypass_mode(F64BypassMode.CALIBRATION) is False
        assert drv._bypass_mode == F64BypassMode.DISABLED  # 未更新
        assert drv._emulation_running is True              # 未同步 STOPPED
        assert drv._status == InstrumentStatus.BUSY        # 未被改写
        assert "-200" in (drv._last_error or "")

    async def test_stop_emulation_rejected_keeps_running(self):
        """Codex #202 R5: GOS 被拒 → False 且 running/_status 不动。"""
        drv, visa = _make_driver()
        drv._emulation_running = True
        drv._status = InstrumentStatus.BUSY
        visa.query.side_effect = lambda cmd: (
            "1" if cmd == "*OPC?" else '-113,"Undefined header"'
        )
        assert await drv.stop_emulation() is False
        assert drv._emulation_running is True
        assert drv._status == InstrumentStatus.BUSY
        assert "-113" in (drv._last_error or "")

    async def test_disconnect_propagates_stop_rejection(self):
        """Codex #206 R2: GOS 被拒时 disconnect 不得报"干净断开" — 断开照样
        完成 (重载必须能断) 但返回 False, 让重载日志暴露仪器可能仍在发射。"""
        drv, visa = _make_driver()
        drv._emulation_running = True
        visa.query.side_effect = lambda cmd: (
            "1" if cmd == "*OPC?" else '-113,"Undefined header"'
        )
        visa.close = lambda: None
        assert await drv.disconnect() is False  # 如实降级
        assert drv._visa_resource is None       # 断开本身仍完成
        assert drv._status == InstrumentStatus.DISCONNECTED

    async def test_stop_emulation_stale_error_not_misreported(self):
        """agent F3: stale FIFO 条目被前置 drain 清掉, 成功的 GOS 不误报被拒。"""
        drv, visa = _make_driver()
        drv._emulation_running = True
        err_q = ['-113,"Undefined header (stale)"']

        def _q(cmd):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return err_q.pop(0) if err_q else '0,"No error"'
            return '0,"No error"'

        visa.query.side_effect = _q
        assert await drv.stop_emulation() is True
        assert drv._emulation_running is False

    async def test_static_write_stale_error_not_misreported(self):
        """agent F3: 同上, STATIC 门的 stale-then-clean 正向路径。"""
        drv, visa = _make_driver()
        err_q = ['-221,"Settings conflict (stale)"']

        def _q(cmd):
            if cmd == "*OPC?":
                return "1"
            if cmd == "SYST:ERR?":
                return err_q.pop(0) if err_q else '0,"No error"'
            return '0,"No error"'

        visa.query.side_effect = _q
        assert await drv.set_bypass_mode(F64BypassMode.CALIBRATION) is True
        assert drv._bypass_mode == F64BypassMode.CALIBRATION

    async def test_go_sequence_atomic_vs_concurrent_poll(self):
        """Codex #203 R3 P2: GO 事务 (drain→STATIC→GO→OPC→错误门) 期间并发
        轮询不得插入 — 可重入 _scpi_lock 把整段收为一个临界区。"""
        drv = RealPropsimF64Driver("f64-go-atomic", {})
        drv._channel_count = 1
        drv._loaded_emulation_file = "X.smu"
        calls: list = []

        class _V:
            timeout = 5000

            def write(self, cmd):
                calls.append(cmd)
                time.sleep(0.002)

            def query(self, cmd):
                calls.append(cmd)
                time.sleep(0.002)
                return "1" if cmd == "*OPC?" else '0,"No error"'

        drv._visa_resource = _V()
        ok, _ = await asyncio.gather(drv.start_emulation(), drv._query("POLL?"))
        assert ok is True
        # 事务区间 = 首条 SYST:ERR? (drain) .. GO 后错误门的 SYST:ERR? — POLL?
        # 只能出现在区间之外 (之前或之后)
        first_err = calls.index("SYST:ERR?")
        last_err = len(calls) - 1 - calls[::-1].index("SYST:ERR?")
        assert "POLL?" not in calls[first_err:last_err + 1], calls

    async def test_passthrough_then_go_round_trip(self):
        """attach 默认态全回路: 直通稳态建立 → GO 自动恢复衰落。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        drv._emulation_running = True  # 假设衰落在跑
        assert await drv.set_passthrough_mode() is True   # STATIC 3, 自动 STOPPED
        assert drv._emulation_running is False
        assert drv._passthrough_active is True
        visa.write.reset_mock()
        assert await drv.start_emulation() is True        # 自动 STATIC 0 + GO
        w = _writes(visa)
        assert w[:2] == ["DIAG:SIMU:MODEL:STATIC 0", "DIAG:SIMU:GO"], w


class TestPassthroughModeSwitch:
    """开关 2 (2026-07-21 现场): set_passthrough_mode 的 mode 参数化。

    3=CALIBRATION 默认 (07-03 -96 RSRP 实证) / 2=BUTLER (官方为建 MIMO 链
    设计, ATE AN p12) / 1=CHANNEL_MODEL; 0/非法 → False (透传不能是"关闭")。
    """

    async def test_default_mode_is_calibration_static3(self):
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        assert await drv.set_passthrough_mode() is True
        assert "DIAG:SIMU:MODEL:STATIC 3" in _writes(visa)
        assert drv._passthrough_active is True

    async def test_butler_mode_writes_static2(self):
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        assert await drv.set_passthrough_mode(mode=2) is True
        w = _writes(visa)
        assert "DIAG:SIMU:MODEL:STATIC 2" in w, w
        assert not any("STATIC 3" in c for c in w), w
        assert drv._passthrough_active is True

    async def test_channel_model_mode_writes_static1(self):
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        assert await drv.set_passthrough_mode(mode=1) is True
        assert "DIAG:SIMU:MODEL:STATIC 1" in _writes(visa)

    async def test_mode_zero_rejected_no_write(self):
        """mode=0 (DISABLED) 不是透传 — 拒绝且不发任何 STATIC 写。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        assert await drv.set_passthrough_mode(mode=0) is False
        assert not any("STATIC" in c for c in _writes(visa)), _writes(visa)
        assert drv._passthrough_active is False

    async def test_invalid_mode_rejected_no_write(self):
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        assert await drv.set_passthrough_mode(mode="garbage") is False
        assert not any("STATIC" in c for c in _writes(visa)), _writes(visa)

    async def test_butler_then_go_clears_bypass(self):
        """Butler 直通后 GO 同样自动清直通 (GO 前清逻辑对任意非 0 档生效)。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        drv._emulation_running = True
        assert await drv.set_passthrough_mode(mode=2) is True
        assert drv._emulation_running is False  # 运行态切静态自动 STOPPED
        visa.write.reset_mock()
        assert await drv.start_emulation() is True
        w = _writes(visa)
        assert w[:2] == ["DIAG:SIMU:MODEL:STATIC 0", "DIAG:SIMU:GO"], w

    async def test_bool_mode_rejected(self):
        """门审 #216 F5: bool 是 int 子类 — mode=True 不得静默变 STATIC 1。"""
        drv, visa = _make_driver()
        drv._loaded_emulation_file = "X.smu"
        assert await drv.set_passthrough_mode(mode=True) is False
        assert not any("STATIC" in c for c in _writes(visa)), _writes(visa)
