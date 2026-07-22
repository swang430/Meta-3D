"""P2-1 收口审查 (agent F1/F2) 的驱动层回归 — 钉住 2026-07-21 现场幂等豁免语义。

覆盖:
- F1: start_emulation GO 对"已运行态"报 -200 Wrong device state → 与 GOS 对称豁免为
      成功 (否则冷缓存放行场景假失败, 且反复 GO 往 PropSim 死锁累积); 其他 -200 仍 False。
- F2: set_bypass_mode(DISABLED=0) 首发被拒 → 回查 DIAG:SIMU:MODEL:STATIC? 消歧
      (与 GO 豁免对称): ==0 才幂等豁免, ≠0/读不到 fail-loud (session desync 不误吞);
      mode≠0 仍复位重试。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.hal.base import InstrumentStatus
from app.hal.propsim_f64 import F64BypassMode, F64Pipeline, RealPropsimF64Driver

WRONG_STATE = '-200,"Execution error;Wrong device state for command"'
STATIC_FAIL = '-200,"Execution error;Setting of simulation static model failed"'
OTHER_200 = '-200,"Execution error;GO genuinely rejected"'


def _driver(error_seq=None, static_val="0", raise_on_write=None):
    """error_seq: {写命令(精确): [该命令后依次返回的 SYST:ERR? 串]}, 用尽后 No error。
    static_val: DIAG:SIMU:MODEL:STATIC? 回值 (GO 豁免消歧用, 默认 "0" 衰落态)。
    raise_on_write: 命令子串, 命中的写命令抛 TimeoutError (模拟 VI_ERROR_TMO 异常路径)。
    *OPC? 恒答 1; 记录写序供断言。"""
    drv = RealPropsimF64Driver("f64-hotfix", {})
    drv._channel_count = 1
    visa = MagicMock()
    drv._visa_resource = visa
    seq = {k: list(v) for k, v in (error_seq or {}).items()}
    last = {"cmd": None}

    async def _w(cmd, timeout=None):
        last["cmd"] = cmd
        visa.write(cmd)
        if raise_on_write and raise_on_write in cmd:
            raise TimeoutError("VI_ERROR_TMO")

    async def _q(cmd, timeout=None):
        if cmd == "*OPC?":
            return "1"
        if cmd == "DIAG:SIMU:MODEL:STATIC?":
            return static_val
        if cmd == "SYST:ERR?":
            errs = seq.get(last["cmd"])
            if errs:
                return errs.pop(0)
            return '0,"No error"'
        return '0,"No error"'

    drv._write = _w  # type: ignore[assignment]
    drv._query = _q  # type: ignore[assignment]
    return drv, visa


def _writes(visa):
    return [c.args[0] for c in visa.write.call_args_list]


# ---------------------------------------------------------------------------
# F1 — GO "已运行态" 豁免
# ---------------------------------------------------------------------------

class TestGoWrongStateExempt:
    async def test_go_wrong_device_state_exempted_as_success(self):
        """GO 报 -200 Wrong device state (已在播放) → 豁免为成功。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]})
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is True
        assert drv._emulation_running is True
        assert drv._last_error is None or "-200" not in drv._last_error

    async def test_go_other_200_still_fails(self):
        """非 Wrong-state 的 -200 (真 GO 失败) 仍 fail-loud False — 豁免不误吞。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [OTHER_200]})
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is False
        assert drv._emulation_running is False
        assert "-200" in (drv._last_error or "")

    async def test_go_wrong_state_exempt_works_on_cold_cache(self):
        """agent F1 目标场景: 冷缓存 (_loaded_emulation_file=None, 后端重启后 F64
        仍在播衰落 STATIC=0) 放行到 GO, GO 报 Wrong state → 豁免成功 (放行不再假失败)。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]}, static_val="0")
        assert drv._loaded_emulation_file is None
        assert await drv.start_emulation() is True
        assert drv._emulation_running is True

    async def test_go_wrong_state_but_static_nonzero_fails(self):
        """Codex #221 P1: GO 报 Wrong device state 但 STATIC≠0 (清直通没生效, 仍在
        STATIC 3 直通) → fail-loud, 不豁免 (否则测量在无衰落直通路径跑假数据)。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]}, static_val="3")
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is False
        assert drv._emulation_running is False
        assert "STATIC=3" in (drv._last_error or "")

    async def test_go_wrong_state_static_unreadable_fails(self):
        """STATIC? 读不到 (None) → 保守 fail-loud, 不盲豁免。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]}, static_val="")
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is False
        assert drv._emulation_running is False


# ---------------------------------------------------------------------------
# F2 — STATIC 0 首发被拒直接豁免, 不进复位重试
# ---------------------------------------------------------------------------

class TestStaticDisabledExempt:
    async def test_disabled_rejected_static0_exempted_no_retry(self):
        """DISABLED(0) 首发被拒 + 回查 STATIC?=0 (真在禁用档) → 豁免为成功, 且
        **只写一次** STATIC 0 (无复位重试; 回查 STATIC? 是 query 不算 write)。"""
        drv, visa = _driver({"DIAG:SIMU:MODEL:STATIC 0": [STATIC_FAIL]}, static_val="0")
        assert await drv.set_bypass_mode(F64BypassMode.DISABLED) is True
        assert drv._bypass_mode == F64BypassMode.DISABLED
        static0_writes = [w for w in _writes(visa) if w == "DIAG:SIMU:MODEL:STATIC 0"]
        assert len(static0_writes) == 1, _writes(visa)  # 无重试的第二次

    async def test_calibration_rejected_then_retry_succeeds(self):
        """mode≠0: 首发被拒 → STATIC 0 复位 + drain + 重设目标档, 重试过 → True。"""
        drv, visa = _driver({"DIAG:SIMU:MODEL:STATIC 3": [STATIC_FAIL]})  # 只错首发
        assert await drv.set_bypass_mode(F64BypassMode.CALIBRATION) is True
        assert drv._bypass_mode == F64BypassMode.CALIBRATION
        w = _writes(visa)
        # 写序: STATIC 3 (首发拒) → STATIC 0 (复位) → STATIC 3 (重试成功)
        idx3 = [i for i, c in enumerate(w) if c == "DIAG:SIMU:MODEL:STATIC 3"]
        idx0 = [i for i, c in enumerate(w) if c == "DIAG:SIMU:MODEL:STATIC 0"]
        assert len(idx3) == 2 and len(idx0) == 1, w
        assert idx3[0] < idx0[0] < idx3[1], w

    async def test_calibration_retry_still_fails(self):
        """mode≠0 重试仍被拒 → fail-loud False, _bypass_mode 不动。"""
        drv, _ = _driver({"DIAG:SIMU:MODEL:STATIC 3": [STATIC_FAIL, STATIC_FAIL]})
        assert await drv.set_bypass_mode(F64BypassMode.CALIBRATION) is False
        assert drv._bypass_mode == F64BypassMode.DISABLED  # 未更新
        assert "-200" in (drv._last_error or "")

    async def test_disabled_rejected_static_nonzero_fails(self):
        """Codex #221 R5 P1: DISABLED 首发被拒 + 回查 STATIC?≠0 (session desync /
        仍在 STATIC 3 直通故障态) → fail-loud False, 不靠错误签名盲豁免 (否则真故障
        被吞成功、污染 clear_passthrough → 校准证书)。"""
        drv, _ = _driver({"DIAG:SIMU:MODEL:STATIC 0": [STATIC_FAIL]}, static_val="3")
        assert await drv.set_bypass_mode(F64BypassMode.DISABLED) is False
        assert "STATIC?=3" in (drv._last_error or "")

    async def test_disabled_rejected_static_unreadable_fails(self):
        """DISABLED 被拒 + STATIC? 读不到 (会话异常, 手册: -400/-360) → 保守
        fail-loud, 不盲豁免。"""
        drv, _ = _driver({"DIAG:SIMU:MODEL:STATIC 0": [STATIC_FAIL]}, static_val="")
        assert await drv.set_bypass_mode(F64BypassMode.DISABLED) is False
