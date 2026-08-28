"""P2-43：两家 BaseStation adapter 共用同一执行与窗口认证入口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.hal.base_station import (
    BaseStationDriver,
    BaseStationMeasurementWindow,
    MockBaseStation,
    ThroughputMetrics,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.scpi_evidence import record_exchange_intent, record_exchange_terminal
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

    def unconfirmed_window_allows_diagnostic_execution(self, window):
        return (
            self.simulated is True
            and window.metrics.throughput_scope
            == ThroughputMetrics.SCOPE_SIMULATED
        )


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
async def test_common_window_preserves_exchanges_for_generic_evidence_writer():
    driver = _CertifiedAdapter(adapter_id="uxm", requested_window_count=1)

    async def window_with_exchange(_window_s, *, throughput_scope):
        exchange_id = "uxm-window-exchange"
        record_exchange_intent(
            exchange_id=exchange_id,
            instrument_id="baseStation",
            operation="query",
            command="EXISTING:WINDOW?",
        )
        record_exchange_terminal(
            exchange_id=exchange_id,
            result_type="response",
            response="10.0",
        )
        return await _CertifiedAdapter.measure_base_station_window(
            driver,
            _window_s,
            throughput_scope=throughput_scope,
        )

    driver.measure_base_station_window = window_with_exchange

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=1,
    )

    assert [item.exchange_id for item in samples[0].exchanges] == [
        "uxm-window-exchange"
    ]


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


@pytest.mark.asyncio
async def test_real_unconfirmed_window_continues_only_with_explicit_adapter_policy():
    driver = _CertifiedAdapter(
        adapter_id="uxm",
        requested_window_count=1,
    )

    async def unconfirmed(_window_s, *, throughput_scope):
        started = datetime.now(timezone.utc)
        return BaseStationMeasurementWindow(
            window_id="uxm-unconfirmed",
            started_at=started,
            completed_at=started + timedelta(seconds=1),
            metrics=ThroughputMetrics(
                dl_throughput_mbps=10.0,
                throughput_scope=throughput_scope,
                kpi_valid={"dl_throughput": True},
            ),
            preclear_off_confirmed=False,
            running_confirmed=False,
            ready_confirmed=False,
            closed_off_confirmed=False,
            evidence=(),
            confirmed=False,
            reason="legacy UXM window has no sourced closed boundary",
        )

    driver.measure_base_station_window = unconfirmed
    driver.unconfirmed_window_allows_diagnostic_execution = lambda _window: True

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=1,
    )

    assert len(samples) == 1
    assert samples[0].metrics.kpi_valid["dl_throughput"] is True


@pytest.mark.asyncio
async def test_real_uxm_window_preserves_existing_per_metric_attestation():
    driver = RealUxmDriver("uxm", {"ip": "192.0.2.1"})
    metrics = ThroughputMetrics(
        dl_throughput_mbps=10.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        kpi_valid={"dl_throughput": True},
    )
    driver.measure_throughput_window = AsyncMock(return_value=metrics)

    window = await driver.measure_base_station_window(
        0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
    )

    assert window.confirmed is False
    assert window.metrics.kpi_valid["dl_throughput"] is True
    assert driver.unconfirmed_window_allows_diagnostic_execution(window) is True


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


def test_existing_uxm_execution_without_new_envelope_keeps_legacy_attested_path(
    monkeypatch,
):
    execution = _execution(adapter="uxm")
    execution.config.pop("base_station_execution_evidence")
    execution.config["base_station_adapter_profile_freeze"] = {
        "resolution": {
            "schema_version": 1,
            "adapter": "uxm",
            "execution_mode": "real",
        }
    }
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-legacy-uxm",
        measurement_attempt_id=None,
        adapter_id="uxm",
        session_token="session-legacy-uxm",
    )
    monkeypatch.setattr(
        instrument_test_lease,
        "active_base_station_lease_identity",
        lambda: lease,
    )

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=_Db(execution)),
        SimpleNamespace(adapter_id="uxm", simulated=False),
    )

    assert resolved.attempt_id is None
    assert resolved.lease_identity == lease
    assert resolved.simulated_diagnostic is False


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
