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
    assert result["status"] == "accepted"
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


def test_measure_wires_observation_only_for_frozen_cmw500_f64_pair():
    source = inspect.getsource(MeasureExecutor.execute)

    assert 'execution_plan.adapter_id == "cmw500"' in source
    assert 'ce_plan.adapter_id == "propsim_f64"' in source
    assert "run_attach_power_observation(" in source
    assert "on_cell_ready=_observe_attach_power" in source
    assert 'measurements["attach_power_observation"]' in source
    assert 'result_payload["attach_power_observation"]' in source
