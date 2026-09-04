"""measure phase 内 F64 输入操作点闭环 wiring 测试 (P0-8 Step 2 Phase 2b).

设计: docs/architecture/f64-input-level-and-dynamic-range.md §4 闭环 in
InputLevelController 单独测过 (test_input_level_controller.py); 本文件钉死
**wiring 行为**: measure.py 的 `_run_input_level_closed_loop` helper 怎么
- 用 hasattr capability 判定 CE+BS 是否双方都支持 (mock 跳, real-like 跑);
- 把 controller 结果展开成 input_level_calibration payload;
- 在 strict 失败时让上层 execute() 触发 phase FAILED 早期 return + finally cleanup;
- 在 opt-out 失败时降级为 warning 继续。

测试分两层:
- helper-level (轻量, 不需要完整 phase fixture): capability/success/fail/opt-out 路径。
- phase-level (1 个端到端 case): 验证 strict fail 真的让 measure.execute() return FAILED
  且 result_payload.measurements 里有 input_level_calibration 子字段。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock

import pytest

from app.hal.propsim_f64 import F64InputMeasMode
from app.services.input_level_controller import (
    InputLevelResult,
    InputOperatingPoint,
)
from app.hal.base_station import resolve_base_station_execution_plan
from app.services.mimo_ota.executors.measure import MeasureExecutor
from tests.channel_emulator_plan_helpers import runtime_measure_plan


def _input_plan(base_station):
    """P2-50：由驱动声明推导输入闭环计划项（测试消费入口同产线）。"""

    return resolve_base_station_execution_plan(
        base_station, manifest=None
    ).input_level_control


# ---------------------------------------------------------------------------
# Fakes — minimal CE/BS that just satisfy hasattr capability detection
# ---------------------------------------------------------------------------


class _FakeRealCE:
    """Real-like CE: provides every atomic method InputLevelController needs.

    Default behavior is the §4 happy path: avg=-30 dBm, crest=10 dB, limits=
    (-60, -10), clipping=0.2‰, no system warnings. Tests override individual
    methods to inject failure modes.
    """

    def __init__(self, *, tx_antennas: int = 4, avg_dbm: float = -30.0):
        self._tx_antennas = tx_antennas  # mimics propsim_f64 internal attr
        self._avg = avg_dbm
        self.calls: Dict[str, int] = {}

    def get_active_input_ports(self):
        """F64R-2: 真实输入口**号**列表。默认造连续口 1..tx_antennas, 测试可覆写成
        非连续 (如 [3,5]) 钉住"闭环用回读口号而不是 range(1,n+1)"。
        ⚠ 真驱动里口数和口号是同一处赋值 (全有或全无), fake 也保持一致。"""
        n = getattr(self, "_tx_antennas", None)
        return list(range(1, n + 1)) if n else None

    def get_active_input_count(self):
        """F64R-2: 驱动改用**从仿真回读的物理输入口数** (MODEL:INFO? 的 inputs) 而不再
        读 _tx_antennas 缓存。本 fake 让该 getter 承载 tx_antennas 构造参数;
        **不设该属性的子类 → 返回 None** = 模拟"拓扑未回读到", sanity bound 应跳过
        (与旧的 `_tx_antennas` 缺失降级语义一致)。"""
        return getattr(self, "_tx_antennas", None)

    def _tick(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    async def set_input_measurement_mode(
        self, input_num: int, mode: F64InputMeasMode
    ) -> bool:
        self._tick("set_input_measurement_mode")
        return True

    async def set_burst_trigger_level(self, input_num: int, dbm: float) -> bool:
        self._tick("set_burst_trigger_level")
        return True

    async def autoset_inputs(
        self, input_nums: Tuple[int, ...], measurement_time_s: float
    ) -> bool:
        self._tick("autoset_inputs")
        return True

    async def measure_input(
        self, input_num: int, measurement_time_s: float
    ) -> Optional[Tuple[float, float]]:
        self._tick("measure_input")
        return (self._avg, 10.0)

    async def get_input_level_limits(
        self, input_num: int
    ) -> Optional[Tuple[float, float]]:
        self._tick("get_input_level_limits")
        return (-60.0, -10.0)

    async def get_group_clipping(
        self, group_num: int, reset: bool = False
    ) -> Optional[float]:
        self._tick("get_group_clipping")
        return 0.2

    async def get_system_status(
        self,
    ) -> Optional[Tuple[Dict[str, Any], List[str]]]:
        self._tick("get_system_status")
        return ({"raw_status": 0}, [])


class _FakeRealBS:
    """Real-like BS: just set_downlink_power. Tracks set values."""

    adapter_id = "uxm"
    input_level_control_supported = True
    input_level_legacy_power_field = "uxm_dl_power_dbm"

    def __init__(self):
        self.set_calls: List[float] = []

    async def set_downlink_power(self, power_dbm: float) -> bool:
        self.set_calls.append(power_dbm)
        return True


class _FakeMockCE:
    """Stand-in for MockChannelEmulator: no input-level atomic methods → wiring
    must skip the closed loop. We deliberately don't define them so hasattr
    returns False, matching the production capability detection."""

    pass


class _FakeMockBS:
    """Stand-in for a BS that never declared the input-level capability. (The
    real MockBaseStation keeps the default opt-out too; this fake only exists
    to test the CE-yes-BS-no half of the capability matrix.)"""

    adapter_id = "uxm"


# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------


@dataclass
class _MiniConfig:
    """Minimal config surface used by `_run_input_level_closed_loop`.
    Only the two attrs the helper actually reads — keeps tests independent
    of MIMOOTAConfiguration's many other defaults (which evolve)."""
    mimo_layers: int = 4
    precheck_strict_input_level: bool = True


# ---------------------------------------------------------------------------
# helper-level tests (capability + payload shape)
# ---------------------------------------------------------------------------


class TestCapabilityDetection:
    """hasattr 检测应让 mock 自然跳, real-like 跑 — 而不是显式判 driver 类。"""

    async def test_mock_ce_skips_without_calling_controller(self):
        executor = MeasureExecutor()
        ce = _FakeMockCE()
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(implemented=()),
        )
        assert payload["skipped"] is True
        assert "CE 缺接口" in payload["reason"]
        # BS 不应被调用 (跳过路径)
        assert bs.set_calls == []

    async def test_mock_bs_skips_without_calling_controller(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE()
        bs = _FakeMockBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        assert payload["skipped"] is True
        assert "BS 未显式开放 input_level_control capability" in payload["reason"]
        # CE 不应被调用 (跳过路径, controller 都没起来)
        assert ce.calls == {}

    async def test_both_real_like_invokes_controller(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE()
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        # controller 跑了 → 不是 skipped
        assert payload.get("skipped") is not True
        # autoset / measure / limits / clipping / status 都被调过
        assert ce.calls.get("autoset_inputs", 0) >= 1
        assert ce.calls.get("measure_input", 0) >= 1


class TestActiveInputsDerivation:
    """active_inputs 应来自 config.mimo_layers (= BS 实际驱动的 layer 数), CE
    _tx_antennas 只用作 sanity bound。Codex on PR #98: 反过来用 _tx_antennas
    会让 autoset 跑去 unconnected input → no-signal → strict 早死。"""

    async def test_uses_config_mimo_layers_not_emulator_tx_antennas(self):
        """Codex regression: 默认 .smu (3600M, 4x4) + config.mimo_layers=2 →
        BS 只发 2 路, active_inputs 必须是 [1,2] 不能是 [1,2,3,4]。"""
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(mimo_layers=2), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        assert payload["active_inputs"] == [1, 2]

    async def test_no_topology_validation_when_emulator_lacks_tx_attr(self):
        """CE 没暴露 _tx_antennas → 没 sanity bound 可查, 直接信 config.mimo_layers
        (跟 production F64 driver 一定有这个 attr 的预期相反, 但 fake CE 还要能用)。"""
        executor = MeasureExecutor()

        class _CEWithoutTxAttr(_FakeRealCE):
            # 本意 = "**无拓扑能力**的 CE" (mock/非 F64)。显式摘掉继承的 getter ——
            # Codex #224 P1 后语义收紧: getter **存在**但返回 None = 拓扑感知驱动读不到
            # → fail-loud; 只有连 getter 都没有才允许退回 1..n 推导。
            get_active_input_ports = None
            get_active_input_count = None

            def __init__(self):
                self._avg = -30.0
                self.calls = {}

        ce = _CEWithoutTxAttr()
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(mimo_layers=2), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(implemented=(
                "autoset_inputs", "measure_input", "get_input_level_limits",
                "set_input_measurement_mode", "set_burst_trigger_level",
                "get_group_clipping", "get_system_status",
            )),
        )
        # 无 sanity bound, 直接 config.mimo_layers=2
        assert payload["active_inputs"] == [1, 2]
        # 跑通了 controller (没 topology_mismatch 短路)
        assert payload.get("topology_mismatch") is None
        assert payload.get("success") is True

    async def test_uses_readback_port_numbers_not_one_to_n(self):
        """★ F64R-2: 闭环 autoset/measure 的是**回读的真实口号**, 不是 range(1,n+1)。

        仿真只占输入口 {3,5} 时, 按 1..n 会打到口 1、2 → 无信号 → measure phase 在
        azimuth loop 之前早死。而同一个 TestCase 只要给了 f64_input_ref_dbm 就走手动
        定标路 (已用回读口号) —— 不修这里, 同一配置换个开关走两套口号。"""
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=2)
        ce.get_active_input_ports = lambda: [3, 5]        # 非连续口
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(mimo_layers=2), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        assert payload["active_inputs"] == [3, 5], "按 1..n 推了, 没用回读口号"

    async def test_sanity_gate_sees_post_ensure_topology_not_cold_value(self):
        """★ 补读必须在 sanity 门**之前** (变异: 把 ensure 挪到门之后这条会红)。

        冷缓存时门读到 None → 跳过; 随后补读回 2 个口 → `[:n_layers]` 把 mimo_layers=4
        静默截成 2 个口 → BS 发 4 层只定标 2 路、另 2 路留工程默认, 闭环却报 success。
        判定与下发必须同源。"""
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=2)
        ce._cold = True

        async def _ensure():
            ce._cold = False                       # 补读后才知道只有 2 个口
            return True

        ce.ensure_topology = _ensure
        ce.get_active_input_count = lambda: None if ce._cold else 2
        ce.get_active_input_ports = lambda: None if ce._cold else [3, 5]
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs),
            channel_emulator_plan=runtime_measure_plan(),
            config=_MiniConfig(mimo_layers=4),      # 4 层 > 实际 2 个输入口
            execution_id="t1",
        )
        assert payload["success"] is False, "门读了补读前的冷值 → 少配的层被静默判成功"
        assert payload["topology_mismatch"] is True
        assert ce.calls == {}, "早期短路: controller 不该被调"

    async def test_port_list_shorter_than_layers_fails_loud(self):
        """口数门放行但口**号**列表更短 → 也不许静默只定标前几路。"""
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)
        ce.get_active_input_count = lambda: 4       # 口数说有 4 个
        ce.get_active_input_ports = lambda: [3, 5]  # 口号只回读到 2 个 (不一致)
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(mimo_layers=4), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        assert payload["success"] is False
        assert payload["topology_mismatch"] is True

    async def test_topology_aware_driver_with_unknown_ports_fails_loud(self):
        """★ Codex #224 P1: 驱动**有** getter 但补读后仍 None (真机不支持 GROUP:* 的
        形态) → fail-loud, **不许**退回猜 1..n —— 猜出的口号会被 controller 当显式端口
        传下去, 而显式端口按契约绕过驱动侧 fail-loud 门, 在错误的输入口上定标/读数。"""
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)
        ce.get_active_input_ports = lambda: None       # 有能力、读不到
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(mimo_layers=2), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        assert payload["success"] is False
        assert payload["topology_mismatch"] is True
        assert ce.calls == {}, "早期短路: controller 不该被调"

    async def test_falls_back_to_one_to_n_only_without_topology_capability(self):
        """无拓扑能力的驱动 (连 getter 都没有, mock/非 F64) → 才允许退回 1..n 推导。"""
        executor = MeasureExecutor()

        class _NoTopoCE(_FakeRealCE):
            get_active_input_ports = None
            get_active_input_count = None

            def __init__(self):
                self._tx_antennas = 4
                self._avg = -30.0
                self.calls = {}

        ce = _NoTopoCE()
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(mimo_layers=2), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(implemented=(
                "autoset_inputs", "measure_input", "get_input_level_limits",
                "set_input_measurement_mode", "set_burst_trigger_level",
                "get_group_clipping", "get_system_status",
            )),
        )
        assert payload["active_inputs"] == [1, 2]
        assert payload.get("success") is True


class TestTopologyMismatch:
    """BS 想发的 layer 数 > CE **物理输入口数** (.smu 输入端口数) = 物理上跑不了,
    早期 fail with audit fields, 不调 controller。Codex on PR #98;
    F64R-2 起口数来自驱动 get_active_input_count() 回读真值, 不再读 _tx_antennas。"""

    async def test_layers_exceeding_ce_tx_fails_loud(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)  # 当前 .smu 4x4
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs),
            channel_emulator_plan=runtime_measure_plan(),
            config=_MiniConfig(mimo_layers=8),  # BS 想发 8 layer > 4 端口
            execution_id="t1",
        )
        assert payload["success"] is False
        assert payload["topology_mismatch"] is True
        assert payload["ce_input_ports"] == 4   # F64R-2 改名: 装的是物理输入口数
        assert payload["config_mimo_layers"] == 8
        assert "拓扑不匹配" in payload["failure_reason"]
        # 早期 short-circuit: controller 没被调
        assert ce.calls == {}
        assert bs.set_calls == []

    async def test_layers_equal_ce_tx_runs_controller(self):
        """边界: layers == _tx_antennas 是 OK 的 (e.g. 4x4 .smu + 4 layer BS)。"""
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs),
            channel_emulator_plan=runtime_measure_plan(),
            config=_MiniConfig(mimo_layers=4),
            execution_id="t1",
        )
        assert payload.get("topology_mismatch") is None
        assert payload.get("success") is True
        assert payload["active_inputs"] == [1, 2, 3, 4]


class TestPayloadShape:
    """成功跑通后 payload 应该有完整结构, 便于 cockpit / 报告消费。"""

    async def test_success_payload_has_all_fields(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        assert payload["success"] is True
        assert payload["failure_reason"] is None
        assert payload["uxm_dl_power_dbm"] == -10.0  # initial UXM = -10
        assert payload["clipping_per_mille"] == 0.2
        assert payload["iterations"] == 1
        assert payload["system_warnings"] == []
        assert payload["active_inputs"] == [1, 2, 3, 4]
        assert payload["strict"] is True
        # operating_point 每输入一个 entry, 结构: input_num / avg_dbm / crest_db
        assert len(payload["operating_point"]) == 4
        for op in payload["operating_point"]:
            assert set(op.keys()) == {"input_num", "avg_dbm", "crest_db"}
            assert op["avg_dbm"] == -30.0
            assert op["crest_db"] == 10.0

    async def test_fail_payload_carries_failure_reason(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE()
        ce.autoset_inputs = AsyncMock(return_value=False)  # always fail
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs), config=_MiniConfig(), execution_id="t1",
            channel_emulator_plan=runtime_measure_plan(),
        )
        assert payload["success"] is False
        # InputLevelController 跑满 max_iter (default=5) 还是不收敛 → 5 轮未收敛
        assert "5" in payload["failure_reason"] or "未收敛" in payload["failure_reason"]
        assert payload["iterations"] == 5
        assert payload["strict"] is True  # 默认 strict


class TestStrictFlagInPayload:
    """strict / opt-out 在 payload 里有显式 audit 字段。"""

    async def test_opt_out_recorded_in_payload(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE()
        ce.autoset_inputs = AsyncMock(return_value=False)
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, plan=_input_plan(bs),
            channel_emulator_plan=runtime_measure_plan(),
            config=_MiniConfig(precheck_strict_input_level=False),
            execution_id="t1",
        )
        assert payload["success"] is False
        assert payload["strict"] is False  # opt-out 留在 payload 给报告/cockpit
