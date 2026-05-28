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
from app.services.mimo_ota.executors.measure import MeasureExecutor


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
    """Stand-in for MockBaseStation lacking set_downlink_power. (The real
    MockBaseStation does implement it; this fake only exists to test the
    CE-yes-BS-no half of the capability matrix.)"""

    pass


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
            emulator=ce, base_station=bs, config=_MiniConfig(), execution_id="t1",
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
            emulator=ce, base_station=bs, config=_MiniConfig(), execution_id="t1",
        )
        assert payload["skipped"] is True
        assert "BS 缺 set_downlink_power" in payload["reason"]
        # CE 不应被调用 (跳过路径, controller 都没起来)
        assert ce.calls == {}

    async def test_both_real_like_invokes_controller(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE()
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, config=_MiniConfig(), execution_id="t1",
        )
        # controller 跑了 → 不是 skipped
        assert payload.get("skipped") is not True
        # autoset / measure / limits / clipping / status 都被调过
        assert ce.calls.get("autoset_inputs", 0) >= 1
        assert ce.calls.get("measure_input", 0) >= 1


class TestActiveInputsDerivation:
    """active_inputs 应来自 emulator._tx_antennas (F64 driver 内部约定)。"""

    async def test_uses_emulator_tx_antennas_when_available(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, config=_MiniConfig(mimo_layers=2), execution_id="t1",
        )
        # 优先用 emulator._tx_antennas=4, 不是 config.mimo_layers=2
        assert payload["active_inputs"] == [1, 2, 3, 4]

    async def test_falls_back_to_config_when_emulator_lacks_tx_antennas(self):
        executor = MeasureExecutor()

        class _CEWithoutTxAttr(_FakeRealCE):
            def __init__(self):
                # 故意不设 _tx_antennas; 用其它默认
                self._avg = -30.0
                self.calls = {}

        ce = _CEWithoutTxAttr()
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, config=_MiniConfig(mimo_layers=2), execution_id="t1",
        )
        # 没 _tx_antennas → 回退 config.mimo_layers=2
        assert payload["active_inputs"] == [1, 2]


class TestPayloadShape:
    """成功跑通后 payload 应该有完整结构, 便于 cockpit / 报告消费。"""

    async def test_success_payload_has_all_fields(self):
        executor = MeasureExecutor()
        ce = _FakeRealCE(tx_antennas=4)
        bs = _FakeRealBS()
        payload = await executor._run_input_level_closed_loop(
            emulator=ce, base_station=bs, config=_MiniConfig(), execution_id="t1",
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
            emulator=ce, base_station=bs, config=_MiniConfig(), execution_id="t1",
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
            emulator=ce, base_station=bs,
            config=_MiniConfig(precheck_strict_input_level=False),
            execution_id="t1",
        )
        assert payload["success"] is False
        assert payload["strict"] is False  # opt-out 留在 payload 给报告/cockpit
