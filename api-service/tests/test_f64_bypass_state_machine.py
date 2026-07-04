"""P2-17 ①: F64 直通/衰落状态机 — STATIC 与回放互斥语义 (2026-07-03 实证)。

实证语义 (onsite-tasks-20260703 "F64 直通态建立"条):
- 运行态切 STATIC≠0 → F64 自动转 STOPPED (直通稳态 = STOPPED + STATIC 3);
- STATIC≠0 下 GO 被 -200 拒 (by design) → start_emulation 内建 GO 前清直通;
- 恢复衰落 = STATIC 0 + GO。
"""
from __future__ import annotations

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
