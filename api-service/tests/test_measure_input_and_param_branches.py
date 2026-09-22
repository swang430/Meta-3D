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
from app.hal.channel_emulator_manifest import channel_emulator_manifest_for
from tests.channel_emulator_plan_helpers import runtime_measure_plan

# P2-59 ①：手动定标的能力判据改为冻结计划；测试里按替身的 manifest 派生计划（行为等价），
# 没有 manifest 的替身 → 什么都没计划（与此前「无 manifest → 不支持」同义）。
from app.hal.channel_emulator_execution_plan import (  # noqa: E402
    resolve_channel_emulator_execution_plan as _resolve_ce_plan,
)
from app.hal.channel_emulator_manifest import (  # noqa: E402
    channel_emulator_manifest_of as _ce_manifest_of,
)


def _plan_for(emulator):
    manifest = _ce_manifest_of(emulator) or channel_emulator_manifest_for(
        adapter_id="bare_emu", model_name="Bare Emu", vendor="test", implemented=(),
    )
    return _resolve_ce_plan(
        manifest=manifest, driver_source="hal",
        requested_load_mode="external_waveform", binding_digest="t" * 64,
    )


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
        # P2-57：能力由 manifest 回答，替身必须自述
        type(emu).adapter_manifest = channel_emulator_manifest_for(
            adapter_id="manual_ref_emu", model_name="Manual Ref Emu",
            vendor="test", implemented=(
                "set_baseband_power", "set_crest_factor", "measure_input",
            ),
        )
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
            emulator=emu, plan=_plan_for(emu), config=cfg, execution_id="t",
        )
        assert payload["success"] is True and payload["mode"] == "manual"
        emu.set_baseband_power.assert_awaited_once_with(-15.0)
        assert emu.set_crest_factor.await_count == 4  # 每输入
        assert len(payload["readback"]) == 4
        assert payload["readback"][0]["avg_dbm"] == -15.2

    @pytest.mark.asyncio
    async def test_manual_ref_empty_pre_cell_readback_is_pending_not_success(self):
        """旧故障：Cell ON 前两路 ``measure_input`` 都为空仍被写成 success=true。"""
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)
        emu = AsyncMock()
        type(emu).adapter_manifest = channel_emulator_manifest_for(
            adapter_id="manual_ref_emu", model_name="Manual Ref Emu",
            vendor="test", implemented=("set_baseband_power", "measure_input"),
        )
        emu.get_active_input_ports = MagicMock(return_value=[1, 2])
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.measure_input = AsyncMock(return_value=None)

        payload = await ex._apply_manual_input_reference(
            emulator=emu, plan=_plan_for(emu), config=cfg, execution_id="t",
        )

        assert payload["application_succeeded"] is True
        assert payload["success"] is False
        assert payload["verification_status"] == "pending_cell_ready"
        assert payload["readback"] == []
        assert [row["avg_dbm"] for row in payload["pre_cell_readback"]] == [
            None,
            None,
        ]
        assert "Cell ON" in payload["failure_reason"]

    @pytest.mark.asyncio
    async def test_manual_ref_partial_pre_cell_readback_is_not_success(self):
        """只读到一路也不能把两路输入工作点整体判成功。"""
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)
        emu = AsyncMock()
        type(emu).adapter_manifest = channel_emulator_manifest_for(
            adapter_id="manual_ref_emu", model_name="Manual Ref Emu",
            vendor="test", implemented=("set_baseband_power", "measure_input"),
        )
        emu.get_active_input_ports = MagicMock(return_value=[1, 2])
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.measure_input = AsyncMock(side_effect=[(-15.2, 11.8), None])

        payload = await ex._apply_manual_input_reference(
            emulator=emu, plan=_plan_for(emu), config=cfg, execution_id="t",
        )

        assert payload["application_succeeded"] is True
        assert payload["success"] is False
        assert payload["verification_status"] == "pending_cell_ready"
        assert payload["readback"] == []

    def test_pending_manual_ref_does_not_abort_before_cell_on(self):
        """成功下发但待 Cell-ready 验证时必须继续，否则永远得不到后置真值。"""
        from app.services.mimo_ota.executors import measure as measure_module

        pending = {
            "skipped": False,
            "success": False,
            "application_succeeded": True,
            "verification_status": "pending_cell_ready",
        }
        rejected = {**pending, "application_succeeded": False}

        assert measure_module._manual_input_initialization_failure(pending) is None
        assert measure_module._manual_input_initialization_failure(rejected)

    def test_cell_ready_observation_finalizes_same_execution_manual_truth(self):
        """同次执行的活动输入功率齐全后，才允许把手动定标记为成功。"""
        from app.services.mimo_ota.executors import measure as measure_module

        pending = {
            "mode": "manual",
            "skipped": False,
            "success": False,
            "application_succeeded": True,
            "verification_status": "pending_cell_ready",
            "verification_source": None,
            "input_ports": [1, 2],
            "pre_cell_readback": [
                {"input_num": 1, "avg_dbm": None, "crest_db": None},
                {"input_num": 2, "avg_dbm": None, "crest_db": None},
            ],
            "readback": [],
            "failure_reason": "pending",
        }
        observation = {
            "accepted": True,
            "status": "recorded",
            "failure_reason": None,
            "samples": [{
                "phase": "cell_ready",
                "input_topology_known": True,
                "invalid_input_ports": [],
                "topology": {"active_input_ports": [1, 2]},
                "input_powers_dbm": [
                    {"port": 1, "value_dbm": -29.0},
                    {"port": 2, "value_dbm": -28.0},
                ],
            }],
        }

        result = measure_module._finalize_manual_input_reference(
            pending, observation
        )

        assert result["success"] is True
        assert result["verification_status"] == "verified_cell_ready"
        assert result["verification_source"] == "attach_power_observation"
        assert result["failure_reason"] is None
        assert result["readback"] == [
            {"input_num": 1, "avg_dbm": -29.0, "crest_db": None},
            {"input_num": 2, "avg_dbm": -28.0, "crest_db": None},
        ]

    @pytest.mark.parametrize(
        ("observation", "reason_fragment"),
        [
            (None, "未取得 Cell ON 后"),
            (
                {
                    "accepted": True,
                    "status": "warning",
                    "failure_reason": None,
                    "samples": [{
                        "phase": "cell_ready",
                        "input_topology_known": True,
                        "invalid_input_ports": [2],
                        "topology": {"active_input_ports": [1, 2]},
                        "input_powers_dbm": [
                            {"port": 1, "value_dbm": -29.0},
                            {"port": 2, "value_dbm": None},
                        ],
                    }],
                },
                "缺少有效实测功率",
            ),
        ],
    )
    def test_missing_or_partial_cell_ready_truth_stays_false(
        self, observation, reason_fragment
    ):
        """非严格观察即使 accepted=true，也不能把部分功率读数洗成成功。"""
        from app.services.mimo_ota.executors import measure as measure_module

        pending = {
            "mode": "manual",
            "skipped": False,
            "success": False,
            "application_succeeded": True,
            "verification_status": "pending_cell_ready",
            "verification_source": None,
            "input_ports": [1, 2],
            "pre_cell_readback": [],
            "readback": [],
            "failure_reason": "pending",
        }

        result = measure_module._finalize_manual_input_reference(
            pending, observation
        )

        assert result["success"] is False
        assert result["verification_status"] == "failed"
        assert result["readback"] == []
        assert reason_fragment in result["failure_reason"]

    @pytest.mark.asyncio
    async def test_manual_ref_rejected_fails_loud(self):
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)
        emu = AsyncMock()
        # P2-57：能力由 manifest 回答，替身必须自述
        type(emu).adapter_manifest = channel_emulator_manifest_for(
            adapter_id="manual_ref_emu", model_name="Manual Ref Emu",
            vendor="test", implemented=("set_baseband_power", "set_crest_factor"),
        )
        emu._tx_antennas = 4
        emu.set_baseband_power = AsyncMock(return_value=False)  # 下发被拒
        payload = await ex._apply_manual_input_reference(
            emulator=emu, plan=_plan_for(emu), config=cfg, execution_id="t",
        )
        assert payload["success"] is False and not payload["skipped"]
        assert "被拒" in payload["failure_reason"]

    @pytest.mark.asyncio
    async def test_manual_ref_skipped_on_mock_ce(self):
        """冻结计划未包含 set_baseband_power（无 manifest 的替身什么都没计划）→ skipped
        (与闭环 capability-skip 一致；P2-59 ① 起判据是计划不是驱动探测)。"""
        ex, cfg = self._executor_and_config(f64_input_ref_dbm=-15.0)

        class _Bare:  # 无 set_baseband_power
            pass

        bare = _Bare()
        payload = await ex._apply_manual_input_reference(
            emulator=bare, plan=_plan_for(bare), config=cfg, execution_id="t",
        )
        assert payload["skipped"] is True and payload["success"] is False

    @pytest.mark.asyncio
    async def test_crest_rejected_fails_loud(self):
        ex, cfg = self._executor_and_config(
            f64_input_ref_dbm=-15.0, f64_crest_db=12.0
        )
        emu = AsyncMock()
        # P2-57：能力由 manifest 回答，替身必须自述
        type(emu).adapter_manifest = channel_emulator_manifest_for(
            adapter_id="manual_ref_emu", model_name="Manual Ref Emu",
            vendor="test", implemented=("set_baseband_power",),
        )
        emu._tx_antennas = 4
        # F64R-2: 逐输入口下发用驱动回读的**端口号列表** (同步 getter)。必须显式给
        # MagicMock —— AsyncMock 自动生成的同名属性返回 coroutine, 会被 _read_port_list
        # 判成"不是端口号"→ 未知 (这正是它该做的防御)。
        emu.get_active_input_ports = MagicMock(return_value=[1, 2, 3, 4])
        emu.get_active_input_count = MagicMock(return_value=4)
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.set_crest_factor = AsyncMock(side_effect=[True, False])  # input2 被拒
        payload = await ex._apply_manual_input_reference(
            emulator=emu, plan=_plan_for(emu), config=cfg, execution_id="t",
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
            plan=runtime_measure_plan(),
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
            plan=runtime_measure_plan(),
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
            plan=runtime_measure_plan(),
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
                    success=True, base_station_dl_power_dbm=-46.0,
                    clipping_per_mille=0.0, iterations=1,
                    operating_point=[], system_warnings=[],
                    failure_reason=None,
                )

        emu = AsyncMock()
        bs = AsyncMock()
        bs.adapter_id = "uxm"
        bs.input_level_control_supported = True
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
            from app.hal.base_station import resolve_base_station_execution_plan

            payload = await ex._run_input_level_closed_loop(
                emulator=emu, base_station=bs, config=cfg, execution_id="t",
                channel_emulator_plan=runtime_measure_plan(),
                plan=resolve_base_station_execution_plan(
                    bs, manifest=None
                ).input_level_control,
            )
        assert captured.get("initial_base_station_dl_power_dbm") == -46.0
        assert payload.get("success") is True
