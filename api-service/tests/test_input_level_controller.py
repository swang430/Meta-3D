"""InputLevelController 闭环测试 (P0-8 Step 2 Phase 2).

跨 driver 服务的纯算法测试: mock BS + CE driver (耦合: F64 输入 avg = UXM 功率 - 线损,
simulate 真实闭环动态), 覆盖:
  - 一次收敛 (合理起点 + 干净信号)
  - clip 触发 → 降 UXM 重试
  - out-of-window-low → 升 UXM 重试
  - 首轮 autoset 失败 (无信号) → 升 UXM (heuristic) → 第二轮收敛
  - BS set_downlink_power / 模式 / burst trigger / measure_input / measure 各失败路径
  - 系统警告 cut-off → 降 UXM 重试
  - 不收敛 (max_iterations 用完)
  - AGC keep pathloss 模式 NotImplementedError
  - active_inputs 子集只对那些输入操作

设计依据: docs/architecture/f64-input-level-and-dynamic-range.md §4 / §3.4。
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple, Union

import pytest

from app.hal.propsim_f64 import F64InputMeasMode
from app.services.input_level_controller import (
    InputLevelController,
    InputLevelResult,
    InputOperatingPoint,
)


# ---------------------------------------------------------------------------
# Fake drivers
# ---------------------------------------------------------------------------

class _FakeBS:
    """假 UXM 驱动: 记录设功率调用 + 当前功率。set_downlink_power 默认 True;
    可设 set_response=False 测失败。"""

    def __init__(self, set_response: bool = True):
        self.set_response = set_response
        self.current_power: Optional[float] = None
        self.set_calls: List[float] = []

    async def set_downlink_power(self, power_dbm: float) -> bool:
        self.set_calls.append(power_dbm)
        if self.set_response:
            self.current_power = power_dbm
        return self.set_response


class _FakeCE:
    """假 F64 CE 驱动: measure 可取耦合函数 (依赖 bs.current_power), autoset 可序列化 (按轮)。"""

    def __init__(
        self,
        *,
        measure: Union[Callable[[int, float], Optional[Tuple[float, float]]],
                       Optional[Tuple[float, float]]] = None,
        autoset: Union[bool, List[bool]] = True,
        limits: Optional[Tuple[float, float]] = (-23.0, 0.0),
        clipping: Union[float, List[float], Callable[[], Optional[float]]] = 0.0,
        system_status: Optional[Tuple[bool, List[str]]] = (True, []),
        set_mode: bool = True,
        set_burst: bool = True,
    ):
        self._measure = measure
        self._autoset = autoset
        self._limits = limits
        self._clipping = clipping
        self._system_status = system_status
        self._set_mode = set_mode
        self._set_burst = set_burst
        self.autoset_calls: List[Tuple[List[int], float]] = []
        self.mode_calls: List[Tuple[int, F64InputMeasMode]] = []
        self.burst_calls: List[Tuple[int, float]] = []
        self.measure_calls: List[Tuple[int, float]] = []
        self._autoset_idx = 0
        self._clipping_idx = 0

    async def set_input_measurement_mode(self, in_num: int, mode: F64InputMeasMode) -> bool:
        self.mode_calls.append((in_num, mode))
        return self._set_mode

    async def set_burst_trigger_level(self, in_num: int, dbm: float) -> bool:
        self.burst_calls.append((in_num, dbm))
        return self._set_burst

    async def autoset_inputs(self, input_nums, t: float) -> bool:
        # 子集 autoset (PR #96 Codex fix): 只对 input_nums 操作, 不用 INP:LEV:AUTOSET 0
        self.autoset_calls.append((list(input_nums), t))
        if isinstance(self._autoset, list):
            i = self._autoset_idx
            self._autoset_idx += 1
            return self._autoset[i] if i < len(self._autoset) else self._autoset[-1]
        return bool(self._autoset)

    async def measure_input(self, in_num: int, t: float) -> Optional[Tuple[float, float]]:
        self.measure_calls.append((in_num, t))
        if callable(self._measure):
            return self._measure(in_num, t)
        return self._measure

    async def get_input_level_limits(self, in_num: int) -> Optional[Tuple[float, float]]:
        return self._limits

    async def get_group_clipping(self, group: int = 1, reset: bool = False) -> Optional[float]:
        if isinstance(self._clipping, list):
            i = self._clipping_idx
            self._clipping_idx += 1
            return self._clipping[i] if i < len(self._clipping) else self._clipping[-1]
        if callable(self._clipping):
            return self._clipping()
        return self._clipping

    async def get_system_status(self) -> Optional[Tuple[bool, List[str]]]:
        return self._system_status


def _coupled_measure(bs: _FakeBS, cable_loss_db: float = 10.0, crest_db: float = 10.0):
    """Build measure_input fn coupled to bs.current_power: F64 input avg = UXM - cable_loss。
    UXM 未设 → 返回 None (模拟无信号)。"""
    def _fn(in_num: int, t: float) -> Optional[Tuple[float, float]]:
        if bs.current_power is None:
            return None
        return (bs.current_power - cable_loss_db, crest_db)
    return _fn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOneShotConvergence:
    async def test_clean_signal_converges_first_iter(self):
        # 初始 UXM=-10, cable=10 → F64 input avg=-20。limits (-23, 0), target_max = 0-15 = -15。
        # avg=-20 ∈ [lo=-23, target_max=-15] → 收敛, 1 轮。
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs))
        ctrl = InputLevelController(ce, bs)
        result = await ctrl.establish()
        assert result.success is True
        assert result.iterations == 1
        assert result.uxm_dl_power_dbm == -10.0
        assert len(result.operating_point) == 4  # 默认 4 个输入
        assert all(op.avg_dbm == -20.0 for op in result.operating_point)
        # 每输入都设了 burst 模式 + 触发
        assert len(ce.mode_calls) == 4
        assert ce.mode_calls[0] == (1, F64InputMeasMode.BURST)
        assert len(ce.burst_calls) == 4


class TestUxmPowerAdjustment:
    async def test_clipping_triggers_uxm_down(self):
        # 初始 UXM=-10 → F64=-20 (本应收敛), 但 clipping=5‰ (>阈值 1‰) → 降 UXM。
        # 第二轮 UXM=-13 → F64=-23 (边界), clipping=0 → 收敛。
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs), clipping=[5.0, 0.0])
        ctrl = InputLevelController(ce, bs)
        result = await ctrl.establish()
        assert result.success is True
        assert result.iterations == 2
        assert result.uxm_dl_power_dbm == -13.0  # 降了 3 dB
        assert result.clipping_per_mille == 0.0

    async def test_out_of_window_high_triggers_uxm_down(self):
        # 初始 UXM=0 → F64=-10 > target_max=-15 → 降 UXM。
        # UXM=-3 → F64=-13 > -15 → 降。UXM=-6 → F64=-16 < -15, ≥ -23 → 收敛, 3 轮。
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs))
        ctrl = InputLevelController(ce, bs, initial_uxm_dl_power_dbm=0.0)
        result = await ctrl.establish()
        assert result.success is True
        assert result.iterations == 3
        assert result.uxm_dl_power_dbm == -6.0

    async def test_out_of_window_low_triggers_uxm_up(self):
        # 初始 UXM=-30 → F64=-40 < lo=-23 → 升 UXM。
        # UXM=-27 → F64=-37 < -23 → 升。UXM=-24 → F64=-34 → 升。UXM=-21→F64=-31→升。UXM=-18→F64=-28→升 (max_iter=5 用完)。
        # 默认 max_iter=5 不够; 用更大 max_iter 验证收敛。
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs))
        ctrl = InputLevelController(
            ce, bs, initial_uxm_dl_power_dbm=-30.0, max_iterations=10
        )
        result = await ctrl.establish()
        assert result.success is True
        # F64 进入窗口大概在 UXM=-12 (F64=-22, > -23) 附近; UXM 从 -30 每轮 +3
        assert result.uxm_dl_power_dbm >= -12.0


class TestAutosetFailLoudFlow:
    async def test_first_iter_autoset_fails_then_recovers_by_raising_uxm(self):
        # 第一轮 autoset False (no signal heuristic → 升 UXM), 第二轮 True 且测得正常 → 收敛。
        bs = _FakeBS()
        # 注意: measure 也耦合到 bs.current_power, 第二轮 UXM=-7 → F64=-17 ∈ window
        ce = _FakeCE(measure=_coupled_measure(bs), autoset=[False, True])
        ctrl = InputLevelController(ce, bs)
        result = await ctrl.establish()
        assert result.success is True
        assert result.iterations == 2
        assert result.uxm_dl_power_dbm == -7.0  # -10 + 3 (heuristic 升)


class TestFailFastPaths:
    async def test_uxm_set_failure_fails_fast(self):
        bs = _FakeBS(set_response=False)
        ce = _FakeCE(measure=_coupled_measure(bs))
        result = await InputLevelController(ce, bs).establish()
        assert result.success is False
        assert "set_downlink_power" in (result.failure_reason or "")
        assert result.iterations == 1

    async def test_mode_set_failure_fails_fast(self):
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs), set_mode=False)
        result = await InputLevelController(ce, bs).establish()
        assert result.success is False
        assert "BURST mode" in (result.failure_reason or "")

    async def test_burst_trigger_failure_fails_fast(self):
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs), set_burst=False)
        result = await InputLevelController(ce, bs).establish()
        assert result.success is False
        assert "burst trigger" in (result.failure_reason or "")

    async def test_measure_returns_none_after_autoset_fails_fast(self):
        # autoset 报成功但 measure 返回 None (异常路径)
        bs = _FakeBS()
        ce = _FakeCE(measure=None, autoset=True)  # measure 始终 None
        result = await InputLevelController(ce, bs).establish()
        assert result.success is False
        assert "measure_input" in (result.failure_reason or "")


class TestSystemWarningsAndCutoff:
    async def test_cut_off_warning_triggers_uxm_down(self):
        # 第一轮系统警告含 "Input cut-off" → 降 UXM; 第二轮无警告 → 收敛。
        bs = _FakeBS()
        ce = _FakeCE(
            measure=_coupled_measure(bs),
            system_status=(False, ["Warning: Input cut-off"]),  # 持续报, 但收敛靠 clip & window
        )
        # cut-off 持续会一直降直到不收敛或 max_iter。给一个能收敛的: status 切换。
        statuses = [(False, ["Warning: Input cut-off"]), (True, [])]
        idx = {"i": 0}
        orig = ce.get_system_status
        async def _seq_status():
            i = idx["i"]
            idx["i"] += 1
            return statuses[i] if i < len(statuses) else statuses[-1]
        ce.get_system_status = _seq_status  # type: ignore[method-assign]

        ctrl = InputLevelController(ce, bs)
        result = await ctrl.establish()
        assert result.success is True
        assert result.iterations == 2
        assert result.uxm_dl_power_dbm == -13.0  # 降了 3


class TestNotConverged:
    async def test_max_iterations_returns_failure(self):
        # 让 clipping 永远超阈值 → 永远降 UXM → max_iter 用完。
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs), clipping=10.0)
        ctrl = InputLevelController(ce, bs, max_iterations=3)
        result = await ctrl.establish()
        assert result.success is False
        assert result.iterations == 3
        assert "未收敛" in (result.failure_reason or "")


class TestAgcModeNotImplemented:
    async def test_agc_keep_pathloss_raises(self):
        bs = _FakeBS()
        ce = _FakeCE()
        with pytest.raises(NotImplementedError, match="AGC keep pathloss"):
            InputLevelController(ce, bs, mode="agc_keep_pathloss")


class TestActiveInputsSubset:
    async def test_only_specified_inputs_operated(self):
        # active_inputs=(1, 2) 只对 1 和 2 设 mode/trigger/measure/AUTOSET
        # (Codex on PR #96: autoset 必须用子集, 不能 INP:LEV:AUTOSET 0 触发未连接输入错误)
        bs = _FakeBS()
        ce = _FakeCE(measure=_coupled_measure(bs))
        ctrl = InputLevelController(ce, bs, active_inputs=(1, 2))
        result = await ctrl.establish()
        assert result.success is True
        assert len(result.operating_point) == 2
        assert [op.input_num for op in result.operating_point] == [1, 2]
        assert [c[0] for c in ce.mode_calls] == [1, 2]
        assert [c[0] for c in ce.burst_calls] == [1, 2]
        # autoset 必须只对子集 [1, 2], 而非 [0] (= 全部) —— 这是 Codex 修复的核心
        assert ce.autoset_calls == [([1, 2], 3.0)]


class TestLimitsUnreadable:
    """Codex on PR #96: 若 get_input_level_limits 失败 → fail-fast。
    不能默认通过 (无窗口就证明不了 avg 在限内)。"""

    async def test_limits_none_fails_fast_not_silent_success(self):
        bs = _FakeBS()
        # limits=None 模拟 SCPI 超时/格式错; clipping/status 干净 (旧逻辑会误报 success)
        ce = _FakeCE(
            measure=_coupled_measure(bs),
            limits=None,
            clipping=0.0,
            system_status=(True, []),
        )
        result = await InputLevelController(ce, bs).establish()
        assert result.success is False, "limits 不可读时不能默默成功"
        assert "get_input_level_limits" in (result.failure_reason or "")
        assert "窗口" in (result.failure_reason or "")
