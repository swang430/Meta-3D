"""P2-43：两家 BaseStation adapter 共用同一执行与窗口认证入口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.hal.base_station import (
    BaseStationDriver,
    BaseStationMeasurementWindow,
    MockBaseStation,
    ThroughputMetrics,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services import instrument_test_lease
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota.executors.measure import MeasureExecutor
from tests.test_p2_43_base_station_adapter_evidence import _Db, _execution


@dataclass
class _CertifiedAdapter:
    adapter_id: str
    simulated: bool = False
    requested_window_count: int = 2
    native_calls: int = 0
    legacy_calls: int = 0

    def measurement_window_count(self, requested: int) -> int:
        assert requested > 0
        return self.requested_window_count

    async def measure_base_station_window(self, _window_s, *, throughput_scope):
        self.native_calls += 1
        started = datetime.now(timezone.utc)
        simulated = self.simulated is True
        return BaseStationMeasurementWindow(
            window_id=f"{self.adapter_id}-{self.native_calls}",
            started_at=started,
            completed_at=started + timedelta(seconds=1),
            metrics=ThroughputMetrics(
                dl_throughput_mbps=10.0,
                throughput_scope=(
                    ThroughputMetrics.SCOPE_SIMULATED
                    if simulated
                    else throughput_scope
                ),
                kpi_valid={"dl_throughput": not simulated},
            ),
            preclear_off_confirmed=not simulated,
            running_confirmed=not simulated,
            ready_confirmed=not simulated,
            closed_off_confirmed=not simulated,
            evidence=(),
            confirmed=not simulated,
            reason="simulated diagnostic" if simulated else "confirmed",
        )

    async def measure_throughput_window(self, *_args, **_kwargs):
        self.legacy_calls += 1
        raise AssertionError("production MEASURE must not use the legacy polling API")


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_id", ["uxm", "cmw500"])
async def test_each_adapter_uses_only_the_common_native_window_contract(adapter_id):
    driver = _CertifiedAdapter(adapter_id=adapter_id)

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=1.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=3,
    )

    assert driver.native_calls == 2
    assert driver.legacy_calls == 0
    assert len(samples) == 2
    assert all(sample.window is not None for sample in samples)


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_id", ["uxm", "cmw500"])
async def test_simulated_common_window_remains_diagnostic_for_each_adapter(adapter_id):
    driver = _CertifiedAdapter(
        adapter_id=adapter_id,
        simulated=True,
        requested_window_count=1,
    )

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=3,
    )

    assert len(samples) == 1
    assert samples[0].window.confirmed is False
    assert samples[0].metrics.throughput_scope == ThroughputMetrics.SCOPE_SIMULATED
    assert samples[0].metrics.kpi_valid["dl_throughput"] is False


@pytest.mark.parametrize("adapter_id", ["uxm", "cmw500"])
def test_current_attempt_and_lease_context_is_vendor_neutral(adapter_id, monkeypatch):
    execution = _execution(adapter=adapter_id)
    execution.config["base_station_adapter_profile_freeze"] = {
        "resolution": {
            "schema_version": 1,
            "adapter": adapter_id,
            "execution_mode": "real",
        }
    }
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-1",
        measurement_attempt_id="attempt-1",
        adapter_id=adapter_id,
        session_token="session-1",
    )
    monkeypatch.setattr(
        instrument_test_lease,
        "active_base_station_lease_identity",
        lambda: lease,
    )

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=_Db(execution)),
        SimpleNamespace(adapter_id=adapter_id, simulated=False),
    )

    assert resolved.attempt_id == "attempt-1"
    assert resolved.lease_identity == lease
    assert resolved.frozen_adapter == execution.config[
        "base_station_adapter_profile_freeze"
    ]


def test_unbound_authoritative_mock_keeps_diagnostic_session_without_evidence(
    monkeypatch,
):
    execution = _execution(adapter="uxm")
    execution.config.pop("scpi_evidence", None)
    execution.config["base_station_adapter_profile_freeze"] = {
        "resolution": {
            "schema_version": 1,
            "adapter": None,
            "status": "diagnostic_unbound",
            "execution_mode": "simulated",
            "profile": None,
        }
    }
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-diagnostic",
        measurement_attempt_id=None,
        adapter_id="uxm",
        session_token="session-diagnostic",
    )
    monkeypatch.setattr(
        instrument_test_lease,
        "active_base_station_lease_identity",
        lambda: lease,
    )

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=_Db(execution)),
        SimpleNamespace(adapter_id="uxm", simulated=True),
    )

    assert resolved.attempt_id is None
    assert resolved.lease_identity == lease
    assert resolved.simulated_diagnostic is True


def test_measure_window_selector_contains_no_vendor_or_legacy_branch():
    import inspect

    source = inspect.getsource(MeasureExecutor._measure_base_station_samples)

    assert "adapter_id" not in source
    assert "measure_throughput_window" not in source


def test_registered_adapters_own_their_common_window_cardinality_and_contract():
    assert RealCmw500Driver.measurement_window_cardinality == "single"
    assert RealUxmDriver.measurement_window_cardinality == "requested"
    assert MockBaseStation.measurement_window_cardinality == "requested"
    assert (
        RealUxmDriver.measure_base_station_window
        is not BaseStationDriver.measure_base_station_window
    )
    assert (
        MockBaseStation.measure_base_station_window
        is not BaseStationDriver.measure_base_station_window
    )
