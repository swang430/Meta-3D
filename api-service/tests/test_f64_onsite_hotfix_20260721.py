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


def _driver(error_seq=None, static_val="0", raise_on_write=None, state_val=None):
    """error_seq: {写命令(精确): [该命令后依次返回的 SYST:ERR? 串]}, 用尽后 No error。
    static_val: DIAG:SIMU:MODEL:STATIC? 回值 (旁路档回读, 默认 "0" 衰落态)。
    state_val: DIAG:SIMU:STATE? 回值; None → 按最后一条播放命令推终态 (F64R-1 判据)。
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

    async def _q(cmd, timeout=None, **_kw):
        if cmd == "*OPC?":
            return "1"
        if cmd == "DIAG:SIMU:STATE?":
            # F64R-1: GO/GOS 判定改看 STATE?。默认按"最后一条播放命令"推终态;
            # state_val 显式给则以它为准 (用例造"GO 被拒且没在跑"等场景)。
            if state_val is not None:
                return state_val
            lp = last["cmd"] or ""
            if lp == "DIAG:SIMU:GO":
                return "RUNNING"
            if lp in ("DIAG:SIMU:GOS", "DIAG:SIMU:STOP"):
                return "STOPPED"
            return "STOPPED"
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
    """GO 的成败判据 (F64R-1 起): **看 `STATE?` 终态到没到 RUNNING**, 不看 SYST:ERR?
    的文字像不像 benign。

    历史: #221 曾用"回查 `STATIC?==0`"给 GO 的 -200 做豁免消歧 —— 但 STATIC? 只报
    **旁路档**, 根本不报运行态, 于是"STATIC=0 且 STOPPED"(非旁路但停着) 会被误判成
    "已在播放", 测量在**没有衰落播放**的状态下跑假数据。信号源选错, 豁免逻辑再精细
    也是错的。本类现在钉的是换掉信号源之后的行为。"""

    async def test_go_rejected_but_running_is_success(self):
        """GO 报 -200 但 STATE?=RUNNING (幂等"已在跑") → 目标达成, 成功。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]}, state_val="RUNNING")
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is True
        assert drv._emulation_running is True
        assert drv._last_error is None or "-200" not in drv._last_error

    async def test_go_rejected_and_stopped_fails_loud(self):
        """★ #221 误豁免场景的直接回归: GO 被拒且 STATE?=STOPPED (**没在跑**) →
        fail-loud。旧判据在这里会因 STATIC=0 判成"已在播放"放行, 让测量跑假数据。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]},
                         static_val="0", state_val="STOPPED")
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is False
        assert drv._emulation_running is False
        assert "STOPPED" in (drv._last_error or "")

    async def test_go_clean_but_not_running_fails_loud(self):
        """★ `*OPC?`=1 骗人场景 (手册 §20.6.1.2 原文警告): 没有任何错误、但 STATE?
        没到 RUNNING → 假启动, 必须 fail-loud。旧的"只看错误队列"判据这里会放行。"""
        drv, _ = _driver(state_val="STOPPED")          # SYST:ERR? 全 clean
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is False
        assert drv._emulation_running is False

    async def test_go_running_on_cold_cache(self):
        """冷缓存 (_loaded_emulation_file=None, 后端重启后 F64 仍在播) 放行到 GO,
        STATE?=RUNNING → 成功 (冷缓存不做 gate 的既有语义不变)。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]}, state_val="RUNNING")
        assert drv._loaded_emulation_file is None
        assert await drv.start_emulation() is True
        assert drv._emulation_running is True

    async def test_go_other_200_still_fails(self):
        """非 Wrong-state 的 -200 且没到 RUNNING → fail-loud (错误文本进 _last_error 供排障)。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [OTHER_200]}, state_val="STOPPED")
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is False
        assert drv._emulation_running is False
        assert "-200" in (drv._last_error or "")

    async def test_go_state_unreadable_fails_loud(self):
        """STATE? 读不到 (None) → 无法确认 → 保守 fail-loud, 不盲信。"""
        drv, _ = _driver({"DIAG:SIMU:GO": [WRONG_STATE]}, state_val="")
        drv._loaded_emulation_file = "X.smu"
        assert await drv.start_emulation() is False


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
