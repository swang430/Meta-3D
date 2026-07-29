"""measure executor 的手动输入基准 / 仪表参数分支 —— 行为锁定。

**这些测试原本搭便车放在 `test_test_plan_runner.py` 里**, 而它们测的既不是
计划 runner 也不是计划链, 是 `app/services/mimo_ota/executors/measure.py`
(case-runner 的 5 相位链正在用) 与 `app/schemas/mimo_ota/config.py`。
ARCH-1 S4b 整删那个文件时差点把它们一起带走 (内审 F3) —— 搬到这里。

保留下来的 `test_measure_topology_getters_f64r2.py` 只覆盖这两个方法里
**跟拓扑相关**的 3 条分支 (见它自己的 class docstring), 与本文件不重叠。

各条守的东西:
- initial_dl_power 透传: 不给就用 controller 默认 -10 dBm, 比 EMQuest -46
  基线**热 36 dB** (门审 #216 F3 披露的雷) —— 透传静默失效 = 闭环从热
  36 dB 的点起步冲 F64 输入;
- 手动基准 happy path / 驱动拒绝 fail-loud / mock CE skip / crest 中途被拒;
- 输出增益按**真实端口**下发 (不是 tx×rx 猜) / 拓扑未知拒发 / 失败点名端口;
- f64_bypass_mode=0 被 schema 的 ge=1 拒。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestManualInputReference:
    """开关 3 块 2: f64_input_ref_dbm 手动定标路径 (跳过 AUTOSET 闭环)。"""

    def _executor_and_config(self, **cfg):
        from app.services.mimo_ota.executors.measure import MeasureExecutor
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        return MeasureExecutor(), MIMOOTAConfiguration(**cfg)

    @pytest.mark.asyncio
    async def test_manual_ref_sets_and_reads_back(self):
        ex, cfg = self._executor_and_config(
            f64_input_ref_dbm=-15.0, f64_crest_db=12.0
        )
        emu = AsyncMock()
        emu._tx_antennas = 4
        # F64R-2: 逐输入口下发用驱动回读的**端口号列表** (同步 getter)。必须显式给
        # MagicMock —— AsyncMock 自动生成的同名属性返回 coroutine, 会被 _read_port_list
        # 判成"不是端口号"→ 未知 (这正是它该做的防御)。
        emu.get_active_input_ports = MagicMock(return_value=[1, 2, 3, 4])
        emu.get_active_input_count = MagicMock(return_value=4)
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.set_crest_factor = AsyncMock(return_value=True)
        emu.measure_input = AsyncMock(return_value=(-15.2, 11.8))
        payload = await ex._apply_manual_input_reference(
            emulator=emu, config=cfg, execution_id="t",
        )
        assert payload["success"] is True and payload["mode"] == "manual"
        emu.set_baseband_power.assert_awaited_once_with(-15.0)
        assert emu.set_crest_factor.await_count == 4  # 每输入
        assert len(payload["readback"]) == 4
        assert payload["readback"][0]["avg_dbm"] == -15.2

    @pytest.mark.asyncio
    async def test_manual_ref_rejected_fails_loud(self):
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)
        emu = AsyncMock()
        emu._tx_antennas = 4
        emu.set_baseband_power = AsyncMock(return_value=False)  # 下发被拒
        payload = await ex._apply_manual_input_reference(
            emulator=emu, config=cfg, execution_id="t",
        )
        assert payload["success"] is False and not payload["skipped"]
        assert "被拒" in payload["failure_reason"]

    @pytest.mark.asyncio
    async def test_manual_ref_skipped_on_mock_ce(self):
        """CE 缺能力 (mock/非 F64) → skipped (与闭环 capability-skip 一致)。"""
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)

        class _Bare:  # 无 set_baseband_power
            pass

        payload = await ex._apply_manual_input_reference(
            emulator=_Bare(), config=cfg, execution_id="t",
        )
        assert payload["skipped"] is True and payload["success"] is False

    @pytest.mark.asyncio
    async def test_crest_rejected_fails_loud(self):
        ex, cfg = self._executor_and_config(
            f64_input_ref_dbm=-15.0, f64_crest_db=12.0
        )
        emu = AsyncMock()
        emu._tx_antennas = 4
        # F64R-2: 逐输入口下发用驱动回读的**端口号列表** (同步 getter)。必须显式给
        # MagicMock —— AsyncMock 自动生成的同名属性返回 coroutine, 会被 _read_port_list
        # 判成"不是端口号"→ 未知 (这正是它该做的防御)。
        emu.get_active_input_ports = MagicMock(return_value=[1, 2, 3, 4])
        emu.get_active_input_count = MagicMock(return_value=4)
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.set_crest_factor = AsyncMock(side_effect=[True, False])  # input2 被拒
        payload = await ex._apply_manual_input_reference(
            emulator=emu, config=cfg, execution_id="t",
        )
        assert payload["success"] is False
        assert "crest" in payload["failure_reason"]



class TestInstrumentParamBranches:
    """门审 #217 F7: measure 新分支 (bypass/output_gain) 驱动级用例。"""

    def _executor_config(self, **cfg):
        from app.services.mimo_ota.executors.measure import MeasureExecutor
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        return MeasureExecutor(), MIMOOTAConfiguration(**cfg)

    @pytest.mark.asyncio
    async def test_output_gain_dispatched_to_real_ports_not_tx_times_rx(self):
        """F64R-2: 输出增益下发到**驱动回读的真实输出口号**, 与 tx×rx / channel_count 无关。

        取代原 `test_output_gain_loop_bound_is_active_outputs` —— 那个测试造了 emu 和
        side_effect 却一次都不调被测代码, 最后只断言自己算的 `min(4*4,64)==16`(自证式,
        永远绿), 而且钉的正是本 PR 证明错了的口径: tx×rx 是**逻辑通道**数, OTA 下
        4 输入×32 探头 = 128 通道而输出口只有 32, 按 16 配会漏掉 17-32 号探头。

        这里用**非连续端口** {2,4,6,8,10}: tx×rx 这类算法无论怎么算都推不出这个集合,
        所以它同时钉住"口数对"和"口号对"。"""
        from app.services.mimo_ota.executors.measure import MeasureExecutor

        calls: list = []

        async def _gain(out, g):
            calls.append((out, g))
            return True

        emu = AsyncMock()
        emu._tx_antennas, emu._rx_antennas, emu._channel_count = 4, 4, 64  # 旧公式会说 16
        emu.get_active_output_ports = MagicMock(return_value=[2, 4, 6, 8, 10])
        emu.set_output_gain = AsyncMock(side_effect=_gain)

        err = await MeasureExecutor()._apply_output_gain(
            emulator=emu, gain_db=-3.0, execution_id="t",
        )
        assert err is None
        assert [c[0] for c in calls] == [2, 4, 6, 8, 10]   # 真实口号, 非 1..N 也非 1..16
        assert all(c[1] == -3.0 for c in calls)

    @pytest.mark.asyncio
    async def test_output_gain_refuses_when_topology_unknown(self):
        """拓扑未知 → 判 FAILED 且**一条 SCPI 都不发** (不回退猜口数)。"""
        from app.services.mimo_ota.executors.measure import MeasureExecutor

        emu = AsyncMock()
        emu._tx_antennas, emu._rx_antennas, emu._channel_count = 4, 4, 64  # 有得猜也不许猜
        emu.get_active_output_ports = MagicMock(return_value=None)
        emu.set_output_gain = AsyncMock(return_value=True)

        err = await MeasureExecutor()._apply_output_gain(
            emulator=emu, gain_db=-3.0, execution_id="t",
        )
        assert err is not None and "物理输出口未知" in err
        emu.set_output_gain.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_output_gain_reports_failing_port(self):
        """某个口被拒 → 立即停并在错误里点名是哪个口 (别让操作员猜)。"""
        from app.services.mimo_ota.executors.measure import MeasureExecutor

        emu = AsyncMock()
        emu.get_active_output_ports = MagicMock(return_value=[1, 2, 3])
        emu.set_output_gain = AsyncMock(side_effect=[True, False])

        err = await MeasureExecutor()._apply_output_gain(
            emulator=emu, gain_db=-3.0, execution_id="t",
        )
        assert err is not None and "output=2" in err
        assert emu.set_output_gain.await_count == 2   # 撞墙即停, 不继续发第 3 个

    @pytest.mark.asyncio
    async def test_bypass_mode_zero_rejected_by_schema(self):
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            MIMOOTAConfiguration(f64_bypass_mode=0)

    @pytest.mark.asyncio
    async def test_initial_dl_power_forwarded_to_controller(self):
        """input_loop_initial_dl_power_dbm 透传 InputLevelController 起点。"""
        ex, cfg = self._executor_config(input_loop_initial_dl_power_dbm=-46.0)
        captured = {}

        class _FakeController:
            def __init__(self, **kw):
                captured.update(kw)

            async def establish(self):
                from app.services.input_level_controller import InputLevelResult
                return InputLevelResult(
                    success=True, uxm_dl_power_dbm=-46.0,
                    clipping_per_mille=0.0, iterations=1,
                    operating_point=[], system_warnings=[],
                    failure_reason=None,
                )

        emu = AsyncMock()
        bs = AsyncMock()
        emu._tx_antennas = 4  # active_inputs 推导比较用, 不能留 AsyncMock
        # F64R-2 (Codex #224 P1 后): AsyncMock 自动生成的拓扑 getter 返回 coroutine →
        # 被判"拓扑感知但读不到" → fail-loud。本用例测的是 initial_dl_power 透传,
        # 给同步 getter 返回真实口号让闭环正常起来。
        emu.get_active_input_count = lambda: 4
        emu.get_active_input_ports = lambda: [1, 2, 3, 4]
        emu.ensure_topology = AsyncMock(return_value=True)
        for m in ("autoset_inputs", "measure_input", "get_input_level_limits",
                  "set_input_measurement_mode", "set_burst_trigger_level",
                  "get_group_clipping", "get_system_status"):
            setattr(emu, m, AsyncMock())
        bs.set_downlink_power = AsyncMock(return_value=True)
        with patch(
            "app.services.input_level_controller.InputLevelController",
            _FakeController,
        ):
            payload = await ex._run_input_level_closed_loop(
                emulator=emu, base_station=bs, config=cfg, execution_id="t",
            )
        assert captured.get("initial_uxm_dl_power_dbm") == -46.0
        assert payload.get("success") is True


