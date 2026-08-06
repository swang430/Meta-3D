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


def _make_driver(*, initial_state="STOPPED"):
    drv = RealPropsimF64Driver("f64-bypass", {})
    drv._channel_count = 1
    visa = MagicMock()
    visa.write.return_value = None
    drv._visa_resource = visa
    # F64R-1: GO/GOS 判定改看 STATE? 终态 (不看错误文字), fake 要给出合理终态 ——
    # 按最后一条播放命令推: GO→RUNNING, GOS/STOP→STOPPED, CLOSE→CLOSED。
    # 手册 §20.4.6.25: 切 STATIC≠0 时仿真被暂停 → STOPPED。
    #
    # ⚠ agent F9: 仪器态**必须由 fake 自己持有**, 绝不能回读 `drv._emulation_running`
    # 推导。那样等于让被测对象自己出考题 —— 驱动缓存漂了 (正是本 PR 要治的病:
    # 后端重启后缓存 False 而硬件在播), fake 会跟着一起漂, "缓存 vs 真值不一致"的
    # 场景在测试里根本构造不出来, 相关断言全成空转。
    _sim = {"state": initial_state, "static": "0"}

    def _router(cmd):
        if cmd == "*OPC?":
            return "1"
        if cmd == "DIAG:SIMU:STATE?":
            return _sim["state"]
        if cmd == "DIAG:SIMU:MODEL:STATIC?":
            return _sim["static"]
        return '0,"No error"'

    visa.query.side_effect = _router

    async def _w(cmd, timeout=None):
        # 命令 → 仪器态迁移 (fake 自持, 与驱动缓存无关)
        if cmd == "DIAG:SIMU:GO":
            _sim["state"] = "RUNNING"
        elif cmd in ("DIAG:SIMU:GOS", "DIAG:SIMU:STOP"):
            _sim["state"] = "STOPPED"
        elif cmd == "DIAG:SIMU:CLOSE":
            _sim["state"] = "CLOSED"
        elif cmd.startswith("DIAG:SIMU:MODEL:STATIC") and not cmd.endswith(" 0"):
            _sim["state"] = "STOPPED"     # 手册 §20.4.6.25: 进旁路 → 仿真暂停
            _sim["static"] = cmd.rsplit(maxsplit=1)[-1]
        elif cmd == "DIAG:SIMU:MODEL:STATIC 0":
            _sim["static"] = "0"
        visa.write(cmd)

    async def _q(cmd, timeout=None, **_kw):
        return visa.query(cmd)

    drv._write = _w  # type: ignore[assignment]
    drv._query = _q  # type: ignore[assignment]
    return drv, visa


def _writes(visa):
    return [c.args[0] for c in visa.write.call_args_list]


class TestStaticPlaybackMutex:
    async def test_running_switch_to_static_syncs_stopped(self):
        """运行态切 STATIC 3 → F64 自动暂停, 驱动状态必须同步。

        F64R-1 分工调整: `set_bypass_mode` 只管**档位**, 不再内联猜 running (手册说
        进旁路暂停、退旁路可能恢复, 方向取决于进旁路前的状态, 驱动自己推必然漂);
        running 由 `set_passthrough_mode` / `clear_passthrough_mode` 在旁路操作后按
        **STATE? 真值**刷新。所以这条从"内部方法置 False"改成钉**对外行为**。"""
        drv, _ = _make_driver()
        drv._emulation_running = True
        drv._status = InstrumentStatus.BUSY
        assert await drv.set_passthrough_mode(mode=3) is True
        assert drv._emulation_running is False  # 来自 fake 的 STATE?=STOPPED (进旁路暂停)
        assert drv._status == InstrumentStatus.READY
        assert drv._bypass_mode == F64BypassMode.CALIBRATION

    async def test_static_disable_resumes_running_when_instrument_says_so(self):
        """退旁路 (STATIC 0) 后仪器报 RUNNING → running=True。

        手册 ATE AN §2.4.5: 退出旁路时**若之前在跑则继续运行** —— 方向取决于进旁路
        前的状态, 所以驱动不推、只问 STATE?。"""
        drv, _ = _make_driver(initial_state="RUNNING")
        drv._emulation_running = False          # 缓存还没跟上
        assert await drv.set_bypass_mode(F64BypassMode.DISABLED) is True
        assert drv._emulation_running is True   # 以仪器为准

    async def test_static_disable_corrects_lying_cache(self):
        """★ 反向: 缓存说"在跑"而仪器报 STOPPED → 按真值纠正成 False。

        这正是 F64R-1 要治的漂移形态 (后端重启 / 前面板并发操作后缓存与硬件不一致)。
        旧实现在这里"保持缓存不变", 于是谎报一路传到仪表盘和测量前置检查。"""
        drv, _ = _make_driver(initial_state="STOPPED")
        drv._emulation_running = True
        assert await drv.set_bypass_mode(F64BypassMode.DISABLED) is True
        assert drv._emulation_running is False

    async def test_bypass_refresh_covers_direct_callers_not_only_passthrough(self):
        """agent F7: 真值刷新在 `set_bypass_mode` 内, 所以**直接调它**的路径 (校准
        tone B 路径等) 也能纠正缓存 —— 不是只有 set_passthrough_mode 包装里才刷。"""
        drv, _ = _make_driver(initial_state="RUNNING")
        drv._emulation_running = False
        assert await drv.set_bypass_mode(F64BypassMode.BUTLER) is True
        # 进旁路会把仪器打到 STOPPED (fake 按手册 §20.4.6.25 迁移), 驱动据此记 False
        assert drv._emulation_running is False
        assert drv._bypass_mode == F64BypassMode.BUTLER

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

        def _q(cmd, **_kw):
            if cmd == "*OPC?":
                return "1"
            if cmd == "DIAG:SIMU:STATE?":
                return "RUNNING"          # F64R-1: GO 成败看 STATE? 终态
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

        def _q(cmd, **_kw):
            if cmd == "*OPC?":
                return "1"
            if cmd == "DIAG:SIMU:STATE?":
                return "STOPPED"          # F64R-1: GOS 成败看 STATE? 终态
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

        def _q(cmd, **_kw):
            if cmd == "*OPC?":
                return "1"
            if cmd == "DIAG:SIMU:MODEL:STATIC?":
                return "3"
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
                if cmd == "*OPC?":
                    return "1"
                if cmd == "DIAG:SIMU:STATE?":
                    return "RUNNING"      # F64R-1: GO 成败看 STATE? 终态
                return '0,"No error"'

        drv._visa_resource = _V()
        ok, _ = await asyncio.gather(drv.start_emulation(), drv._query("POLL?"))
        assert ok is True
        # 事务区间 = 首条 SYST:ERR? (drain) .. 确认闭环末尾的 STATE? — POLL? 只能
        # 出现在区间之外。F64R-1 后确认闭环 (*OPC?→SYST:ERR?→STATE?) 也在事务内,
        # 所以区间右端从"最后一条 SYST:ERR?"延到 STATE? (判定读到的状态必须与 GO
        # 同属一个临界区, 否则并发换状态会让判定读到别人的结果)。
        first_err = calls.index("SYST:ERR?")
        last_confirm = len(calls) - 1 - calls[::-1].index("DIAG:SIMU:STATE?")
        assert "POLL?" not in calls[first_err:last_confirm + 1], calls

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

    async def test_passthrough_confirms_opc_error_and_static_readback_in_order(self):
        """正式旁路证据的驱动来源必须完整闭环：写档位后依次等完成、查错、
        回读同一个档位，再读取运行态；不能拿模型状态替代 STATIC?。"""
        drv, visa = _make_driver()
        seen: list[str] = []
        original_query = drv._query

        async def _q(cmd, timeout=None, **kwargs):
            seen.append(cmd)
            return await original_query(cmd, timeout, **kwargs)

        drv._query = _q  # type: ignore[assignment]
        assert await drv.set_passthrough_mode(mode=3) is True
        tail = [
            cmd for cmd in seen
            if cmd in (
                "*OPC?",
                "SYST:ERR?",
                "DIAG:SIMU:MODEL:STATIC?",
                "DIAG:SIMU:STATE?",
            )
        ]
        assert tail[-4:] == [
            "*OPC?",
            "SYST:ERR?",
            "DIAG:SIMU:MODEL:STATIC?",
            "DIAG:SIMU:STATE?",
        ], tail
        assert "DIAG:SIMU:MODEL:STATIC 3" in _writes(visa)

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
