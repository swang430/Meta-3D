"""Control-flow semantics for the UXM RF App maximum DL diagnostic."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.diagnostics.sequences import uxm_rf_app_max_dl_throughput as sequence


class _Commands:
    PROFILE_NAME = "IRAT_LITE"


class RealRfAppDriver:
    def __init__(self, samples=None, sample_error: BaseException | None = None):
        self._cmds = _Commands()
        self.samples = list(samples or [])
        self.sample_error = sample_error
        self.active = False
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def rf_app_dl_throughput_cleanup_required(self):
        return self.active

    async def get_rf_app_dl_throughput_context(self, cell):
        return {
            "identity": "Keysight Technologies,C8714000A RF Application Framework,SN,3.5",
            "app_name": "IRAT_LITE",
            "detected_test_app": "IRAT_LITE",
            "command_profile": "IRAT_LITE",
            "preexisting_scpi_errors": [],
            "cell_config": {
                "cell": cell,
                "status": "CONN",
                "band": "N66",
                "dl_arfcn": 429000,
                "dl_bandwidth": "10",
                "ul_bandwidth": "10",
                "dl_power_dbm_per_bw": -12.0,
            },
        }

    async def start_rf_app_max_dl_throughput(self, cell, length):
        self.start_calls += 1
        self.active = True
        return {"cell": cell, "measurement_length_slots": length}

    async def read_rf_app_max_dl_throughput(self, cell):
        if self.sample_error is not None:
            raise self.sample_error
        if self.samples:
            return self.samples.pop(0)
        return {
            "timestamp": "2026-07-13T12:00:00.000Z",
            "valid": False,
            "source": "none",
            "dl_throughput_mbps": None,
            "dl_bler": None,
            "raw_btput": '"0,0,0,0,0,0,NaN,NaN,NaN"',
            "raw_tmonitor": '"NaN,NaN,NaN,0"',
        }

    async def stop_rf_app_max_dl_throughput(self):
        self.stop_calls += 1
        self.active = False
        return {"stopped": True, "restored": {}, "scpi_errors": []}

    async def get_rf_app_dl_throughput_final_status(self, cell):
        return {"cell_status": "CONN", "btput_state": 0, "scpi_errors": []}


def _sample(throughput=5.88, bler=0.65):
    return {
        "timestamp": "2026-07-13T12:00:00.000Z",
        "valid": True,
        "source": "btput",
        "dl_throughput_mbps": throughput,
        "dl_bler": bler,
        "progress_count": 160,
        "tmonitor_peak_mbps": 12.14,
        "raw_btput": f'"160,56,104,0,104,104,{bler},{throughput},0.35"',
        "raw_tmonitor": f'"{throughput},12.14,8.5,900000000"',
    }


async def _run(driver, monkeypatch, params=None):
    monkeypatch.setattr(sequence.asyncio, "sleep", AsyncMock())
    hal = SimpleNamespace(drivers={"baseStation": driver})
    return await sequence.run(
        MagicMock(),
        hal,
        params or {"duration_s": 1, "sample_interval_s": 1},
        log=MagicMock(),
    )


@pytest.mark.asyncio
async def test_high_bler_is_informational_and_control_flow_succeeds(monkeypatch):
    driver = RealRfAppDriver(samples=[_sample(5.88, 0.65)])
    result = await _run(driver, monkeypatch)

    assert result.success is True
    assert driver.start_calls == 1
    assert driver.stop_calls == 1
    assert result.extra["kpi_summary"]["dl_bler"]["mean"] == pytest.approx(0.65)
    assert result.extra["uxm_rf_app_dl_throughput"]["no_performance_threshold"] is True
    assert result.extra["cell_config"]["band"] == "N66"


@pytest.mark.asyncio
async def test_all_empty_samples_fail_but_still_stop(monkeypatch):
    driver = RealRfAppDriver()
    result = await _run(driver, monkeypatch)

    assert result.success is False
    assert "未读取到有效DL吞吐样本" in result.summary
    assert driver.stop_calls == 1
    assert result.extra["cleanup"]["stopped"] is True


@pytest.mark.asyncio
async def test_sampling_exception_still_stops(monkeypatch):
    driver = RealRfAppDriver(sample_error=RuntimeError("sample timeout"))
    result = await _run(driver, monkeypatch)

    assert result.success is False
    assert "sample timeout" in result.summary
    assert driver.stop_calls == 1
    assert any(step.label == "连续采样真实DL吞吐/BLER" and not step.success for step in result.steps)


@pytest.mark.asyncio
async def test_task_cancellation_still_stops(monkeypatch):
    driver = RealRfAppDriver(sample_error=asyncio.CancelledError())
    monkeypatch.setattr(sequence.asyncio, "sleep", AsyncMock())
    hal = SimpleNamespace(drivers={"baseStation": driver})

    with pytest.raises(asyncio.CancelledError):
        await sequence.run(
            MagicMock(),
            hal,
            {"duration_s": 1, "sample_interval_s": 1},
            log=MagicMock(),
        )
    assert driver.stop_calls == 1


@pytest.mark.asyncio
async def test_non_irat_profile_is_rejected_without_start(monkeypatch):
    driver = RealRfAppDriver(samples=[_sample()])
    driver._cmds = SimpleNamespace(PROFILE_NAME="5G_NR_Test")
    result = await _run(driver, monkeypatch)

    assert result.success is False
    assert "IRAT_LITE" in result.summary
    assert driver.start_calls == 0
    assert driver.stop_calls == 0


@pytest.mark.asyncio
async def test_parameter_validation_rejects_invalid_window(monkeypatch):
    driver = RealRfAppDriver(samples=[_sample()])
    result = await _run(
        driver,
        monkeypatch,
        {"duration_s": 30, "sample_interval_s": 1, "measurement_length_slots": 201},
    )

    assert result.success is False
    assert "参数校验失败" in result.summary
    assert driver.start_calls == 0
