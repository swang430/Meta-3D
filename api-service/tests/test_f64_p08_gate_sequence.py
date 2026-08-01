"""P0-8a 门序列 (`propsim_f64_p08_gate`) 的 D-1 行为门。

测试形态 = **真驱动 + 假 SCPI 层** (沿 test_f64_bypass_state_machine 的
_make_driver 样板): 序列走的是真 RealPropsimF64Driver 的生产原子
(load_local_scenario / autoset_inputs / start_emulation / set_bypass_mode /
set_output_gain / stop_emulation), fake 只在 `_write`/`_query` 层按手册 +
2026-07-03 现场实证建模仪器行为 —— 比 stub 驱动方法强一档: stub 掉
load_local_scenario 就等于没测加载事务的编排。

fake 建模的行为都有出处:
- AUTOSET 是 stopped 态命令 (§20.4.4.7) → 非 STOPPED 下发压 -200。
  这条是"AUTOSET 必须排在 GO 前"时序纠错的**行为锁** (变异: 把序列的
  AUTOSET 块挪到 GO 后 → 这里红)。
- 运行态切 STATIC≠0 → 自动暂停 (2026-07-03 实证); 退旁路 STATIC 0 默认
  **不**自动续跑 (同实证, 恢复衰落 = STATIC 0 + GO), auto_resume 参数化
  另一种固件行为 (手册 ATE AN §2.4.5 说续跑)。
- OUTP:GAIN:CH 超范围**静默钳位** (§20.4.5.8) — 序列的回读断言负责现形。
- 失败测量 (无信号) = 设备错误进队列, **无哨兵返回值** (§20.4.4.6/7)。
- 未路由的查询一律 AssertionError —— 这是"禁盲试"的结构锁: 序列若开始发
  手册没核过的新查询, 这里直接炸, 不会静默装没事。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.diagnostics.sequences.propsim_f64_p08_gate import run as run_gate
from app.hal.propsim_f64 import RealPropsimF64Driver


# ---------------------------------------------------------------------------
# 按手册 + 2026-07-03 实证建模的假 F64 (SCPI 层)
# ---------------------------------------------------------------------------

class _FakeF64Scpi:
    """自持仪器态 (绝不回读驱动缓存 —— fake 自己出考题, 见 bypass 测试 agent F9)。"""

    def __init__(
        self,
        *,
        state: str = "CLOSED",
        gain_limits: tuple = (-45.0, 0.0),
        auto_resume_on_bypass_exit: bool = False,
        no_input_signal: bool = False,
        syst_stat: str = "1",
        ignore_gain_writes: bool = False,
        reject_go: bool = False,
        reject_static0: bool = False,
        reject_file_load: bool = False,
        leak_error_on_meas: bool = False,
        signal_lost_after_autoset: bool = False,
    ) -> None:
        self.state = state
        self.bypass = "0"
        self.gains: Dict[int, float] = {}
        self.gain_limits = gain_limits
        self.errors: List[str] = []
        self.writes: List[str] = []
        self._auto_resume = auto_resume_on_bypass_exit
        self._no_signal = no_input_signal
        self._syst_stat = syst_stat
        self._ignore_gain = ignore_gain_writes
        self._reject_go = reject_go
        self._reject_static0 = reject_static0
        self._reject_file = reject_file_load
        self._leak_on_meas = leak_error_on_meas
        self._signal_lost = signal_lost_after_autoset
        self._was_running_before_bypass = False

    def _err(self, entry: str = '-200,"Execution error;Wrong device state for command"') -> None:
        self.errors.append(entry)

    async def write(self, cmd: str, timeout: Optional[int] = None, **_kw) -> None:
        self.writes.append(cmd)
        if cmd == "*CLS":
            self.errors.clear()
        elif cmd == "DIAG:SIMU:CLOSE":
            self.state = "CLOSED"
        elif cmd.startswith("CALC:FILT:FILE"):
            if self._reject_file:
                self._err('-256,"File name not found"')
            else:
                self.state = "STOPPED"
        elif cmd == "DIAG:SIMU:GO":
            if self._reject_go:
                self._err()
            elif self.state == "RUNNING":
                self._err()
            elif self.bypass != "0":
                self._err()  # STATIC≠0 下 GO 被 -200 拒 (2026-07-03 实证, by design)
            else:
                self.state = "RUNNING"
        elif cmd in ("DIAG:SIMU:GOS", "DIAG:SIMU:STOP"):
            self.state = "STOPPED"
        elif cmd.startswith("DIAG:SIMU:MODEL:STATIC "):
            mode = cmd.rsplit(" ", 1)[1]
            if mode == "0":
                if self._reject_static0 and self.bypass != "0":
                    self._err('-200,"Setting of simulation static model failed"')
                elif self.bypass == "0":
                    # 0→0 幂等怪叫 (2026-07-21 现场实证) — start_emulation 会吞
                    self._err('-200,"Setting of simulation static model failed"')
                else:
                    self.bypass = "0"
                    if self._auto_resume and self._was_running_before_bypass:
                        self.state = "RUNNING"
            else:
                self._was_running_before_bypass = self.state == "RUNNING"
                self.bypass = mode
                self.state = "STOPPED"  # 2026-07-03: 进旁路自动暂停
        elif cmd.startswith("INP:LEV:AUTOSET"):
            if self.state != "STOPPED":
                self._err()  # §20.4.4.7: stopped 态命令 — AUTOSET 排 GO 后的行为锁
            elif self._no_signal:
                self._err('-300,"Device specific error;No input signal"')
        elif cmd.startswith("OUTP:GAIN:CH "):
            body = cmd[len("OUTP:GAIN:CH "):]
            out_s, gain_s = body.split(",")
            if not self._ignore_gain:
                lo, hi = self.gain_limits
                # §20.4.5.8: 超范围静默钳到最近合法值
                self.gains[int(out_s)] = min(hi, max(lo, float(gain_s)))
        # 其余写命令: 收下不叫 (fake 只建模剧本会走到的族)

    async def query(self, cmd: str, timeout: Optional[int] = None, **_kw) -> str:
        if cmd == "DIAG:SIMU:STATE?":
            return self.state
        if cmd == "DIAG:SIMU:MODEL:STATIC?":
            return self.bypass
        if cmd == "*OPC?":
            return "1"
        if cmd == "SYST:ERR?":
            return self.errors.pop(0) if self.errors else '0,"No error"'
        if cmd == "SYST:STAT?":
            return self._syst_stat
        if cmd.startswith("CALC:FILT:CENT:CH?"):
            return "3549.99"
        if cmd == "DIAG:SIMU:MODEL:INFO?":
            return "1,1,1"
        if cmd == "GROUP:GET?":
            return "1"
        if cmd.startswith("GROUP:CHANNELS:GET?"):
            return "1"
        if cmd.startswith("GROUP:INPUTS:GET?"):
            return "1"
        if cmd.startswith("GROUP:OUTPUTS:GET?"):
            return "1"
        if cmd.startswith("INP:LEV:MEAS?"):
            if self._leak_on_meas:
                # 无主告警混着一次成功测量 — 零残留检查的考题
                self._err('-222,"Data out of range"')
            if self._no_signal or self._signal_lost:
                self._err('-300,"Device specific error;No input signal"')
                return ""
            return "-21.5,4.0" if self.bypass != "0" else "-21.4,4.0"
        if cmd.startswith("OUTP:GAIN:CH?"):
            out = int(cmd.rsplit(" ", 1)[1])
            return f"{self.gains.get(out, 0.0):g}"
        if cmd.startswith("OUTP:GAIN:LIM?"):
            return f"{self.gain_limits[0]:g},{self.gain_limits[1]:g}"
        raise AssertionError(f"剧本/驱动发了未路由的查询 (禁盲试结构锁): {cmd!r}")


class _FakeHal:
    def __init__(self, ce: Any) -> None:
        self.drivers = {"channelEmulator": ce}


def _make(**fake_kw):
    fake = _FakeF64Scpi(**fake_kw)
    drv = RealPropsimF64Driver("f64-p08", {})
    drv._channel_count = 1
    drv._visa_resource = object()  # 非 None 即可 — 读写全走 monkeypatch
    drv._write = fake.write  # type: ignore[assignment]
    drv._query = fake.query  # type: ignore[assignment]
    return drv, fake


_OK_PARAMS = {
    "uxm_dl_confirmed": True,
    "smu_path": "D:\\emulations\\p08_n78_636666_bw40.smu",
    "input_num": 1,
    "output_num": 1,
    "gain_delta_db": 1.0,
}


async def _run(drv, params=None):
    logs: List[str] = []
    result = await run_gate(
        None, _FakeHal(drv), dict(_OK_PARAMS if params is None else params),
        log=logs.append,
    )
    return result, logs


def _labels(result, *, only_failed=False):
    return [s.label for s in result.steps if (not s.success) or not only_failed]


class TestHappyPath:
    async def test_full_gate_passes_and_archives(self):
        drv, fake = _make()
        result, _ = await _run(drv)
        assert result.success, [f"{s.label}: {s.detail}" for s in result.steps if not s.success]
        assert "PASS" in result.summary
        # P0-8a 判据逐条落在步骤里
        assert any(s.label == "GO 后 STATE?" and s.success for s in result.steps)
        assert any(s.label == "恢复后 STATE?" and s.success for s in result.steps)
        assert any(s.label == "AUTOSET 后 SYST:STAT?" and s.success for s in result.steps)
        # 归档: 两态电平 + 增益往返 + 旁路下状态字面值
        assert result.extra["fading_level"]["avg_dbm"] == -21.4
        assert result.extra["bypass_level"]["avg_dbm"] == -21.5
        assert result.extra["gain_orig_db"] == 0.0
        # 默认 orig=0 / hi=0 → +1 越上限 → 往下走 -1 (窗口分支)
        assert result.extra["gain_target_db"] == -1.0
        assert result.extra["state_in_bypass"] == "STOPPED"
        # 关键数值必须在 summary (归档 2048B 截断保头部)
        assert "-21.4" in result.summary and "-21.5" in result.summary

    async def test_autoset_ordered_before_go(self):
        """时序锁: AUTOSET 是 stopped 态命令, 必须在首个 GO 之前。
        变异 (把序列 AUTOSET 块挪到 GO 后) → fake 压 -200 → 本测试红。"""
        drv, fake = _make()
        result, _ = await _run(drv)
        assert result.success
        autoset_idx = next(i for i, w in enumerate(fake.writes)
                           if w.startswith("INP:LEV:AUTOSET"))
        go_idx = next(i for i, w in enumerate(fake.writes) if w == "DIAG:SIMU:GO")
        assert autoset_idx < go_idx

    async def test_no_auto_resume_firmware_gets_explicit_go(self):
        """2026-07-03 实证固件: 退旁路不续跑 → 序列必须显式 GO 恢复 (RUNNING 断言 #2)。
        变异 (删显式 GO 分支) → 恢复后 STATE?≠RUNNING → 本测试红。"""
        drv, fake = _make(auto_resume_on_bypass_exit=False)
        result, _ = await _run(drv)
        assert result.success
        assert fake.writes.count("DIAG:SIMU:GO") == 2  # 首次 GO + 退旁路后显式恢复
        assert any(s.label == "显式 GO 恢复 (固件未自动续跑)" and s.success
                   for s in result.steps)

    async def test_auto_resume_firmware_skips_explicit_go(self):
        """手册语义固件 (ATE AN §2.4.5 续跑): 不多发 GO, 如实记录续跑字面值。"""
        drv, fake = _make(auto_resume_on_bypass_exit=True)
        result, _ = await _run(drv)
        assert result.success
        assert fake.writes.count("DIAG:SIMU:GO") == 1
        assert result.extra["state_after_bypass_exit"] == "RUNNING"

    async def test_instrument_left_tidy(self):
        """收尾稳态: 场景包留驻 + STOPPED + 衰落 (STATIC 0) + 增益还原。
        且**不发 CLOSE 收尾** (直发会让驱动身份缓存 stale, docstring 排雷 #2):
        唯一一次 CLOSE 是加载事务自己的 preflight。"""
        drv, fake = _make()
        result, _ = await _run(drv)
        assert result.success
        assert fake.state == "STOPPED"
        assert fake.bypass == "0"
        assert fake.gains[1] == 0.0  # 还原到原值
        assert fake.writes.count("DIAG:SIMU:CLOSE") == 1  # 仅加载 preflight 那次
        assert drv._loaded_emulation_file == _OK_PARAMS["smu_path"]  # 身份缓存没被绕坏


class TestFailClosed:
    async def test_load_failure_stops_everything(self):
        drv, fake = _make(reject_file_load=True)
        result, _ = await _run(drv)
        assert not result.success
        assert "加载失败" in result.summary
        assert not any(w.startswith("INP:LEV:AUTOSET") for w in fake.writes)
        assert "DIAG:SIMU:GO" not in fake.writes
        # CLOSED = 未加载的干净稳态 — 收尾不该喊"请人工核对" (内审 F2)
        assert any(s.label == "收尾停住 (无需)" and s.success and "CLOSED" in s.detail
                   for s in result.steps)

    async def test_autoset_failure_aborts_before_go(self):
        """无信号 → AUTOSET 设备错误 (无哨兵返回值, §20.4.4.7) → 不带病 GO。
        变异 (删 AUTOSET 失败后的 _Abort) → GO 照发 → 本测试红。"""
        drv, fake = _make(no_input_signal=True)
        result, _ = await _run(drv)
        assert not result.success
        assert "UXM" in result.summary  # 指路: 先查 DL 是否真在发
        assert "DIAG:SIMU:GO" not in fake.writes
        assert not any(w.startswith("OUTP:GAIN:CH ") for w in fake.writes)

    async def test_syst_stat_warning_blocks_go(self):
        """AUTOSET 后 SYST:STAT? 不干净 (Input cut-off) = 参考没收敛, 不 GO。"""
        drv, fake = _make(syst_stat="0,Input cut-off")
        result, _ = await _run(drv)
        assert not result.success
        assert "DIAG:SIMU:GO" not in fake.writes
        assert any("Input cut-off" in (s.detail or "") for s in result.steps)

    async def test_gain_write_ineffective_detected(self):
        """写入被仪器无声丢弃 (等价于钳位/未生效) → 回读断言现形。
        变异 (删回读比对) → 本测试红。"""
        drv, fake = _make(ignore_gain_writes=True)
        result, _ = await _run(drv)
        assert not result.success
        assert "没真生效或被钳位" in result.summary

    async def test_gain_window_too_narrow_refuses_write(self):
        """窗口 [lo,hi] 放不下 ±Δ 往返 → 拒写 (不硬写让钳位背锅)。"""
        drv, fake = _make(gain_limits=(-0.5, 0.0))
        result, _ = await _run(drv)
        assert not result.success
        assert not any(w.startswith("OUTP:GAIN:CH ") for w in fake.writes)

    async def test_stray_error_after_measure_is_caught(self):
        """测量成功但队列里混进无主告警 → 零残留检查抓住 (下一个生产原子的
        drain 会把它静默吞掉 — 这正是测量后补 residue 的理由)。
        变异 (删衰落态测量后的 residue) → 本测试红。"""
        drv, fake = _make(leak_error_on_meas=True)
        result, _ = await _run(drv)
        assert not result.success
        assert any(s.label == "衰落态测量后错误队列" and not s.success
                   for s in result.steps)
        # 中止发生在**首个**泄漏站点 — 旁路态那次根本没走到 (F4 收窄)
        assert not any(s.label == "旁路态测量后错误队列" for s in result.steps)
        # 队列被 residue 排干归档, 不是被下一个原子的 drain 静默吞掉
        assert fake.errors == []

    async def test_go_rejected_aborts_with_tidy_instrument(self):
        """GO 被拒 (增益未动/旁路未进) → 中止且不留侧效应。"""
        drv, fake = _make(reject_go=True)
        result, _ = await _run(drv)
        assert not result.success
        assert not any(w.startswith("OUTP:GAIN:CH ") for w in fake.writes)
        assert fake.bypass == "0"

    async def test_abort_archives_queue_before_restore(self):
        """内审 F1: AUTOSET 成功但衰落测量设备错误 (现场最可能的失败形态) →
        -300 字面值必须出现在归档里, 且不被还原原子的 drain 静默吞掉 —— 归档
        末尾写假"零残留"正是本序列存在理由的反面。
        变异 (删收尾段的"中止后错误队列"residue) → 本测试红。"""
        drv, fake = _make(signal_lost_after_autoset=True)
        result, _ = await _run(drv)
        assert not result.success
        step = next(s for s in result.steps
                    if s.label == "中止后错误队列 (先归档再还原)")
        assert not step.success and "-300" in (step.raw or "")
        assert fake.errors == []          # 队列被归档排干
        assert fake.gains[1] == 0.0       # 还原段照常走完 (增益放回原值)

    async def test_bypass_exit_rejected_still_restores_gain(self):
        """退旁路被拒 → 中止, 但还原段仍要把增益放回原值 + 再试退旁路并如实报。
        (state_machine 同款教训: 还原是所有退出路径的共同出口。)"""
        drv, fake = _make(reject_static0=True)
        result, _ = await _run(drv)
        assert not result.success
        assert fake.gains[1] == 0.0  # 增益已还原
        assert any(s.label.startswith("还原旁路档") for s in result.steps)
        assert "旁路" in result.summary


class TestParamGates:
    async def test_uxm_dl_not_confirmed_refused(self):
        drv, fake = _make()
        for bad in ({}, {"uxm_dl_confirmed": False}, {"uxm_dl_confirmed": "true"},
                    {"uxm_dl_confirmed": 1}):
            params = {**_OK_PARAMS, **bad}
            if "uxm_dl_confirmed" not in bad:
                params.pop("uxm_dl_confirmed")
            result, _ = await _run(drv, params)
            assert not result.success
            assert "uxm_dl_confirmed" in result.summary
        assert fake.writes == []  # 一条 SCPI 都不该发

    async def test_empty_smu_path_refused_with_scd_pointer(self):
        drv, fake = _make()
        result, _ = await _run(drv, {**_OK_PARAMS, "smu_path": ""})
        assert not result.success
        assert "standard_channel_definitions" in result.summary  # 指路 SCD
        assert fake.writes == []

    async def test_bad_ports_and_delta_refused(self):
        drv, fake = _make()
        for bad in ({"input_num": 0}, {"input_num": True}, {"output_num": 1.0},
                    {"gain_delta_db": 0}, {"gain_delta_db": 5.0},
                    {"gain_delta_db": True}, {"gain_delta_db": "1"}):
            result, _ = await _run(drv, {**_OK_PARAMS, **bad})
            assert not result.success, bad
        assert fake.writes == []

    async def test_mock_driver_refused(self):
        class MockChannelEmulator:  # 名字就是判据 (protocol.mock_driver_refusal_summary)
            pass

        result, _ = await _run(MockChannelEmulator())
        assert not result.success
        assert "mock" in result.summary

    async def test_non_f64_driver_refused(self):
        class RealSomethingElse:
            async def _query(self, cmd):  # 有通道但没有生产原子
                return ""

        result, _ = await _run(RealSomethingElse())
        assert not result.success
        assert "生产原子" in result.summary
