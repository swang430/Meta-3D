"""P2-43：两家 BaseStation adapter 共用同一执行与窗口认证入口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.hal.base_station import (
    BASE_STATION_MEASUREMENT_WINDOW_STAGES,
    BaseStationApplyReceipt,
    BaseStationDriver,
    BaseStationFieldReceipt,
    BaseStationMeasurementStageReceipt,
    BaseStationMeasurementWindow,
    BaseStationMeasurementWindowRequest,
    BaseStationMeasurementWindowTrust,
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


def _manifest(adapter_id: str):
    return (
        RealCmw500Driver.adapter_manifest
        if adapter_id == "cmw500"
        else RealUxmDriver.adapter_manifest
    )


def _window_trust(
    request: BaseStationMeasurementWindowRequest,
    *,
    simulated: bool,
    exchange_id: str = "window-observation",
) -> BaseStationMeasurementWindowTrust:
    formal = not simulated and request.lifecycle == "authoritative_closed"
    exchange_ids = () if simulated else (exchange_id,)
    return BaseStationMeasurementWindowTrust(
        schema_version=1,
        request=request,
        request_digest=request.digest,
        stages=tuple(
            BaseStationMeasurementStageReceipt(
                stage=stage,
                status="confirmed" if formal else "unavailable",
                reason="test common window trust",
                exchange_ids=exchange_ids if formal else (),
            )
            for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
        ),
        simulated=simulated,
        exchange_ids=exchange_ids,
        reason="test common window trust",
    )


def _partial_config_receipt(*, operation_succeeded: bool):
    return BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=(
            BaseStationFieldReceipt(
                field="bandwidth_mhz",
                requested=100.0,
                applied=100.0,
                status="confirmed",
                reason="authoritative hardware readback matched",
            ),
            BaseStationFieldReceipt(
                field="frequency_mhz",
                requested=3500.0,
                applied=None,
                status="unknown",
                reason="metadata has no authoritative hardware readback",
            ),
        ),
        reason="complete evidence remains partial",
        simulated=False,
        operation_succeeded=operation_succeeded,
    )


def test_config_operation_success_allows_diagnostic_while_formal_receipt_stays_partial():
    receipt = _partial_config_receipt(operation_succeeded=True)

    assert receipt.confirmed is False
    assert receipt.diagnostic_execution_allowed is True


def test_config_operation_rejection_blocks_diagnostic_even_with_matching_fields():
    receipt = _partial_config_receipt(operation_succeeded=False)

    assert receipt.confirmed is False
    assert receipt.diagnostic_execution_allowed is False


def test_measure_execution_uses_operation_truth_not_formal_receipt_completeness():
    import inspect

    source = inspect.getsource(MeasureExecutor.execute)

    assert "config_receipt.diagnostic_execution_allowed" in source
    assert "config_receipt.confirmed is not True" not in source


@dataclass
class _CertifiedAdapter:
    adapter_id: str
    simulated: bool = False
    requested_window_count: int = 2
    native_calls: int = 0
    legacy_calls: int = 0

    async def measure_base_station_window(self, _window_s, *, request):
        self.native_calls += 1
        started = datetime.now(timezone.utc)
        simulated = self.simulated is True
        trust = _window_trust(request, simulated=simulated)
        return BaseStationMeasurementWindow(
            window_id=f"{self.adapter_id}-{self.native_calls}",
            started_at=started,
            completed_at=started + timedelta(seconds=1),
            metrics=ThroughputMetrics(
                dl_throughput_mbps=10.0,
                throughput_scope=(
                    ThroughputMetrics.SCOPE_SIMULATED
                    if simulated
                    else (
                        ThroughputMetrics.SCOPE_PCELL
                        if request.scope == "pcell"
                        else ThroughputMetrics.SCOPE_NR_ALL_CELLS
                    )
                ),
                kpi_valid={"dl_throughput": not simulated},
            ),
            preclear_off_confirmed=trust.stages[0].status == "confirmed",
            running_confirmed=trust.stages[1].status == "confirmed",
            ready_confirmed=trust.stages[2].status == "confirmed",
            closed_off_confirmed=trust.stages[3].status == "confirmed",
            evidence=(),
            confirmed=trust.formally_confirmed,
            reason="simulated diagnostic" if simulated else "confirmed",
            trust=trust,
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
        manifest=_manifest(adapter_id),
        simulated_diagnostic=False,
    )

    assert driver.native_calls == (1 if adapter_id == "cmw500" else 3)
    assert driver.legacy_calls == 0
    assert len(samples) == (1 if adapter_id == "cmw500" else 3)
    assert all(sample.window is not None for sample in samples)


@pytest.mark.asyncio
async def test_common_window_preserves_exchanges_for_generic_evidence_writer():
    driver = _CertifiedAdapter(adapter_id="uxm", requested_window_count=1)

    async def window_with_exchange(_window_s, *, request):
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
            request=request,
        )

    driver.measure_base_station_window = window_with_exchange

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=1,
        manifest=RealUxmDriver.adapter_manifest,
        simulated_diagnostic=False,
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
        manifest=None,
        simulated_diagnostic=True,
    )

    assert len(samples) == 3
    assert samples[0].window.confirmed is False
    assert samples[0].metrics.throughput_scope == ThroughputMetrics.SCOPE_SIMULATED
    assert samples[0].metrics.kpi_valid["dl_throughput"] is False


@pytest.mark.asyncio
async def test_real_unconfirmed_window_continues_only_with_auditable_common_trust():
    driver = _CertifiedAdapter(
        adapter_id="uxm",
        requested_window_count=1,
    )

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=1,
        manifest=RealUxmDriver.adapter_manifest,
        simulated_diagnostic=False,
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
        request=MeasureExecutor._measurement_window_requests(
            RealUxmDriver.adapter_manifest,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            requested_sample_count=1,
            simulated_diagnostic=False,
        )[0],
    )

    assert window.confirmed is False
    assert window.metrics.kpi_valid["dl_throughput"] is True
    assert window.trust is not None
    assert window.trust.formally_confirmed is False
    assert window.trust.diagnostic_execution_allowed is False


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


def test_registered_manifests_own_their_common_window_cardinality_and_contract():
    assert RealCmw500Driver.adapter_manifest.measurement.cardinality == "single"
    assert RealUxmDriver.adapter_manifest.measurement.cardinality == "requested"
    assert (
        RealUxmDriver.measure_base_station_window
        is not BaseStationDriver.measure_base_station_window
    )
    assert (
        MockBaseStation.measure_base_station_window
        is not BaseStationDriver.measure_base_station_window
    )
