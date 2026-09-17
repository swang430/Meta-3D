from __future__ import annotations

import inspect
import pydantic
import pytest

from app.hal.base import InstrumentMetrics
from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.mimo_ota.executors.measure import MeasureExecutor
from app.services.mimo_ota.attach_power_observation import (
    run_attach_power_observation,
)


class _BaseStation:
    async def read_configured_downlink_power_dbm(self):
        return -50.25


class _ChannelEmulator:
    def __init__(self, snapshots):
        self._snapshots = iter(snapshots)

    async def get_metrics(self):
        return InstrumentMetrics.model_validate(next(self._snapshots))


def _metrics(*, input_1=-17.2, input_2=-17.4, output_1=-50.5):
    return {
        "timestamp": "2026-09-16T04:00:00Z",
        "status": "normal",
        "metrics": {
            "loaded_file": "F9809A TS LTE MIMO OTA 2x2/1.0 RC1",
            "simulation_state": "RUNNING",
            "active_inputs": 2,
            "active_outputs": 2,
            "active_channels": 4,
            "active_input_ports": [1, 2],
            "active_output_ports": [1, 2],
            "topology_source": "readback",
            "input_powers_dbm": {1: input_1, 2: input_2},
            "output_powers_dbm": {1: output_1, 2: -50.7},
            "output_powers_frozen": False,
        },
    }


def test_attach_power_observation_window_has_bounded_explicit_contract():
    assert MIMOOTAConfiguration().attach_power_observation_s == 0.0
    assert (
        MIMOOTAConfiguration(attach_power_observation_s=60.0)
        .attach_power_observation_s
        == 60.0
    )
    with pytest.raises(pydantic.ValidationError):
        MIMOOTAConfiguration(attach_power_observation_s=-0.1)
    with pytest.raises(pydantic.ValidationError):
        MIMOOTAConfiguration(attach_power_observation_s=300.1)


@pytest.mark.asyncio
async def test_observation_records_cmw_config_and_f64_smu_power_topology():
    result = await run_attach_power_observation(
        base_station=_BaseStation(),
        channel_emulator=_ChannelEmulator([_metrics()]),
        observation_s=0.0,
        strict_input_level=True,
        execution_id="execution-1",
    )

    assert result["accepted"] is True
    # 只表示「读到了数」，不表示功率在：真机无信号读出来是很低的有限值（-108 dBm），不是空值。
    assert result["status"] == "recorded"
    assert len(result["samples"]) == 1
    sample = result["samples"][0]
    assert sample["cmw_configured_rs_epre_dbm"] == -50.25
    assert sample["loaded_file"] == "F9809A TS LTE MIMO OTA 2x2/1.0 RC1"
    assert sample["topology"] == {
        "source": "readback",
        "active_inputs": 2,
        "active_outputs": 2,
        "active_channels": 4,
        "active_input_ports": [1, 2],
        "active_output_ports": [1, 2],
    }
    assert sample["input_powers_dbm"] == [
        {"port": 1, "value_dbm": -17.2},
        {"port": 2, "value_dbm": -17.4},
    ]
    assert sample["output_powers_dbm"][0] == {
        "port": 1,
        "value_dbm": -50.5,
    }


@pytest.mark.asyncio
async def test_strict_observation_rejects_missing_active_input_without_waiting():
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    result = await run_attach_power_observation(
        base_station=_BaseStation(),
        channel_emulator=_ChannelEmulator([_metrics(input_2=None)]),
        observation_s=60.0,
        strict_input_level=True,
        execution_id="execution-2",
        sleep=_sleep,
    )

    assert result["accepted"] is False
    assert result["status"] == "rejected"
    assert result["invalid_input_ports"] == [2]
    assert "F64 活动输入口缺少有效实测功率" in result["failure_reason"]
    assert sleeps == []


@pytest.mark.asyncio
async def test_non_strict_window_samples_again_after_full_observation_delay():
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    result = await run_attach_power_observation(
        base_station=_BaseStation(),
        channel_emulator=_ChannelEmulator(
            [_metrics(input_2=None), _metrics(input_1=-18.1, input_2=-18.3)]
        ),
        observation_s=2.5,
        strict_input_level=False,
        execution_id="execution-3",
        sleep=_sleep,
    )

    assert result["accepted"] is True
    assert result["status"] == "warning"
    assert [sample["phase"] for sample in result["samples"]] == [
        "cell_ready",
        "observation_complete",
    ]
    assert sleeps == [1.0, 1.0, 0.5]


@pytest.mark.asyncio
async def test_observation_window_honors_cooperative_cancel_each_second():
    checks = iter([False, True])
    sleeps: list[float] = []

    async def _cancelled() -> bool:
        return next(checks)

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    result = await run_attach_power_observation(
        base_station=_BaseStation(),
        channel_emulator=_ChannelEmulator([_metrics()]),
        observation_s=60.0,
        strict_input_level=True,
        execution_id="execution-4",
        is_cancelled=_cancelled,
        sleep=_sleep,
    )

    assert result["accepted"] is False
    assert result["status"] == "cancelled"
    assert sleeps == [1.0]


def test_measure_wires_observation_through_the_capability_predicate():
    # 源码文本只是粗筛：execute 必须经能力判据接线，且不得再按基站厂商身份分支。
    source = inspect.getsource(MeasureExecutor.execute)

    assert "_cell_ready_power_observation_is_wired(base_station, ce_plan)" in source
    assert 'adapter_id == "cmw500"' not in source
    assert "_observe_cell_ready_power(" in source
    assert "_attach_power_observation_failure(" in source
    assert "on_cell_ready=_observe_attach_power" in source
    # 落库由 test_cell_ready_hook_* 两条行为测试断言，不再靠源码文本。
    assert 'result_payload["attach_power_observation"]' in source


def test_observation_predicate_follows_driver_capability_not_vendor_identity():
    from types import SimpleNamespace

    from app.services.mimo_ota.executors.measure import (
        _cell_ready_power_observation_is_wired,
    )

    class _WithReadback:
        adapter_id = "some_other_vendor"

        async def read_configured_downlink_power_dbm(self):
            return -50.0

    class _WithoutReadback:
        adapter_id = "cmw500"  # 身份像 CMW500，但没有该只读能力（Mock 即如此）

    f64_plan = SimpleNamespace(adapter_id="propsim_f64")
    mock_plan = SimpleNamespace(adapter_id="mock_channel_emulator")

    assert _cell_ready_power_observation_is_wired(_WithReadback(), f64_plan) is True
    assert _cell_ready_power_observation_is_wired(_WithoutReadback(), f64_plan) is False
    assert _cell_ready_power_observation_is_wired(_WithReadback(), mock_plan) is False


@pytest.mark.asyncio
async def test_finite_but_absent_signal_reading_is_recorded_not_judged():
    # 2026-09-16 执行 f8f5fd90：F64 输入口 2 两次采样均为 -108.0 dBm（无信号），输入口 1 约 -29 dBm。
    # 观察不凭数值判断有无信号，所以这里必须仍放行 —— 但状态不得读成「通过」。
    result = await run_attach_power_observation(
        base_station=_BaseStation(),
        channel_emulator=_ChannelEmulator([_metrics(input_1=-28.9, input_2=-108.0)]),
        observation_s=0.0,
        strict_input_level=True,
        execution_id="execution-5",
    )

    assert result["accepted"] is True
    assert result["status"] == "recorded"
    assert result["invalid_input_ports"] == []
    assert result["samples"][0]["input_powers_dbm"][1] == {"port": 2, "value_dbm": -108.0}


class _ExecutionRow:
    def __init__(self) -> None:
        self.id = "execution-hook"
        self.status = "running"
        self.measurements = {"phases": {"precheck": {"ok": True}}}


class _Db:
    def __init__(self) -> None:
        self.commits = 0

    def expire(self, _row) -> None:
        return None

    def refresh(self, _row) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1


def _hook_context():
    from types import SimpleNamespace

    return SimpleNamespace(db=_Db(), test_execution=_ExecutionRow())


@pytest.mark.asyncio
async def test_cell_ready_hook_blocks_attach_and_persists_a_rejected_observation(monkeypatch):
    from app.services.mimo_ota.executors import measure as measure_module

    monkeypatch.setattr(measure_module, "flag_modified", lambda *_args: None)
    context = _hook_context()
    holder: dict = {}

    allowed = await measure_module._observe_cell_ready_power(
        context=context,
        base_station=_BaseStation(),
        channel_emulator=_ChannelEmulator([_metrics(input_2=None)]),
        config=MIMOOTAConfiguration(),  # 默认：0 秒 + 严格
        holder=holder,
    )

    assert allowed is False
    stored = context.test_execution.measurements["attach_power_observation"]
    assert stored is holder["result"]
    assert stored["status"] == "rejected"
    assert context.test_execution.measurements["phases"] == {"precheck": {"ok": True}}
    assert context.db.commits == 1
    message = measure_module._attach_power_observation_failure(stored)
    assert message is not None
    assert "UE attach 尚未开始" in message
    assert "F64 活动输入口缺少有效实测功率" in message


@pytest.mark.asyncio
async def test_cell_ready_hook_allows_attach_when_readings_are_complete(monkeypatch):
    from app.services.mimo_ota.executors import measure as measure_module

    monkeypatch.setattr(measure_module, "flag_modified", lambda *_args: None)
    context = _hook_context()
    holder: dict = {}

    allowed = await measure_module._observe_cell_ready_power(
        context=context,
        base_station=_BaseStation(),
        channel_emulator=_ChannelEmulator([_metrics()]),
        config=MIMOOTAConfiguration(),
        holder=holder,
    )

    assert allowed is True
    assert measure_module._attach_power_observation_failure(holder["result"]) is None
    assert measure_module._attach_power_observation_failure(None) is None
