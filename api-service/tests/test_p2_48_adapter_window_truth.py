from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.hal.base_station import (
    BASE_STATION_MEASUREMENT_WINDOW_STAGES,
    BaseStationMeasurementStageReceipt,
    BaseStationMeasurementWindow,
    BaseStationMeasurementWindowRequest,
    BaseStationMeasurementWindowTrust,
    MockBaseStation,
    ThroughputMetrics,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.scpi_evidence import record_exchange_intent, record_exchange_terminal
from app.services.mimo_ota.executors.measure import MeasureExecutor


def _request(*, lifecycle="authoritative_closed", index=0, expected=1):
    cardinality = "single" if expected == 1 else "requested"
    return BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope="pcell",
        lifecycle=lifecycle,
        cardinality=cardinality,
        requested_window_count=3,
        expected_window_count=expected,
        window_index=index,
    )


def _trust(request, *, confirmed=True, simulated=False):
    statuses = (
        "confirmed" if confirmed else
        "unavailable" if request.lifecycle == "unavailable" else
        "unknown"
    )
    stages = tuple(
        BaseStationMeasurementStageReceipt(
            stage=stage,
            status=statuses,
            reason=f"{stage} {statuses}",
            exchange_ids=(f"{stage}-1",) if statuses == "confirmed" else (),
        )
        for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
    )
    exchange_ids = tuple(
        exchange_id for stage in stages for exchange_id in stage.exchange_ids
    )
    if not exchange_ids and not simulated:
        exchange_ids = ("metric-1",)
    return BaseStationMeasurementWindowTrust(
        schema_version=1,
        request=request,
        request_digest=request.digest,
        stages=stages,
        simulated=simulated,
        exchange_ids=exchange_ids,
        reason="window trust",
        context_confirmed=confirmed,
    )


def _window(request, *, confirmed=True, simulated=False):
    started = datetime.now(timezone.utc)
    trust = _trust(request, confirmed=confirmed, simulated=simulated)
    return BaseStationMeasurementWindow(
        window_id="window-1",
        started_at=started,
        completed_at=started + timedelta(seconds=1),
        metrics=ThroughputMetrics(
            dl_throughput_mbps=10.0,
            throughput_scope=(
                ThroughputMetrics.SCOPE_SIMULATED
                if simulated
                else ThroughputMetrics.SCOPE_PCELL
            ),
            kpi_valid={"dl_throughput": not simulated},
        ),
        preclear_off_confirmed=confirmed,
        running_confirmed=confirmed,
        ready_confirmed=confirmed,
        closed_off_confirmed=confirmed,
        evidence=(),
        confirmed=confirmed,
        reason="window",
        trust=trust,
    )


def test_window_rejects_legacy_confirmed_boolean_that_disagrees_with_trust():
    request = _request(lifecycle="unavailable", expected=3)
    trust = _trust(request, confirmed=False)
    started = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="confirmed mirror"):
        BaseStationMeasurementWindow(
            window_id="window-1",
            started_at=started,
            completed_at=started + timedelta(seconds=1),
            metrics=ThroughputMetrics(throughput_scope="pcell"),
            preclear_off_confirmed=False,
            running_confirmed=False,
            ready_confirmed=False,
            closed_off_confirmed=False,
            evidence=(),
            confirmed=True,
            reason="legacy bool lies",
            trust=trust,
        )


@pytest.mark.asyncio
async def test_uxm_maps_existing_read_window_to_clear_read_only_diagnostic_trust():
    """P2-52：lifecycle 升级为 clear_read_only 后，窗口内没发成 CLEar 时
    clear 阶段必须如实记 unavailable —— 声明升级不制造证据。"""
    driver = RealUxmDriver("uxm", {"ip": "192.0.2.1"})
    async def diagnostic_window(*_args, **_kwargs):
        record_exchange_intent(
            exchange_id="uxm-metric-1",
            instrument_id="baseStation",
            operation="query",
            command="EXISTING:UXM:METRIC?",
        )
        record_exchange_terminal(
            exchange_id="uxm-metric-1",
            result_type="response",
            response="10.0",
        )
        return ThroughputMetrics(
            dl_throughput_mbps=10.0,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            kpi_valid={"dl_throughput": True},
        )
    driver.measure_throughput_window = AsyncMock(side_effect=diagnostic_window)
    request = _request(lifecycle="clear_read_only", expected=3)

    window = await driver.measure_base_station_window(0.0, request=request)

    assert window.trust is not None
    assert window.trust.request == request
    assert window.trust.formally_confirmed is False
    assert window.trust.diagnostic_execution_allowed is True
    assert window.confirmed is False
    assert window.preclear_off_confirmed is False
    assert all(stage.status == "unavailable" for stage in window.trust.stages)


@pytest.mark.asyncio
async def test_uxm_rejects_request_lifecycle_that_disagrees_with_manifest():
    """冻结请求与驱动 manifest 漂移必须 fail-loud，不静默换档。"""
    driver = RealUxmDriver("uxm", {"ip": "192.0.2.1"})
    request = _request(lifecycle="unavailable", expected=3)

    with pytest.raises(ValueError, match="frozen manifest"):
        await driver.measure_base_station_window(0.0, request=request)


@pytest.mark.asyncio
async def test_mock_echoes_frozen_request_but_never_confirms_hardware_truth():
    driver = registered_mock_base_station("mock", {"model": "CMW500"})
    request = _request()

    window = await driver.measure_base_station_window(0.0, request=request)

    assert window.trust is not None
    assert window.trust.request == request
    assert window.trust.simulated is True
    assert window.trust.formally_confirmed is False
    assert window.trust.diagnostic_execution_allowed is True
    assert window.metrics.throughput_scope == ThroughputMetrics.SCOPE_SIMULATED


class _Driver:
    simulated = False

    def __init__(self, window):
        self.window = window
        self.calls = []

    async def measure_base_station_window(self, _window_s, *, request):
        self.calls.append(request)
        return self.window if len(self.calls) == 1 else replace(
            self.window,
            window_id=f"window-{len(self.calls)}",
            trust=replace(
                self.window.trust,
                request=request,
                request_digest=request.digest,
            ),
        )


@pytest.mark.asyncio
async def test_measure_executor_uses_frozen_requests_not_driver_count_or_policy():
    requests = MeasureExecutor._measurement_window_requests(
        RealCmw500Driver.adapter_manifest,
        throughput_scope="pcell",
        requested_sample_count=3,
        simulated_diagnostic=False,
        statistical_basis_subframes=5000,
    )
    driver = _Driver(_window(requests[0]))

    samples = await MeasureExecutor._measure_base_station_samples(
        driver,
        window_s=0.0,
        throughput_scope="pcell",
        requested_sample_count=3,
        manifest=RealCmw500Driver.adapter_manifest,
        simulated_diagnostic=False,
        statistical_basis_subframes=5000,
    )

    assert driver.calls == list(requests)
    assert len(samples) == 1
    assert samples[0].window.trust.request == requests[0]


def test_production_window_path_has_no_legacy_count_policy_or_boolean_gate():
    import inspect

    source = inspect.getsource(MeasureExecutor._measure_base_station_samples)

    assert "measurement_window_count" not in source
    assert "unconfirmed_window_allows_diagnostic_execution" not in source
    assert "window.confirmed" not in source


@pytest.mark.asyncio
async def test_measure_executor_rejects_missing_or_mismatched_window_trust():
    request = _request()
    legacy = replace(_window(request), trust=None)
    with pytest.raises(RuntimeError, match="trust receipt is missing"):
        await MeasureExecutor._measure_base_station_samples(
            _Driver(legacy),
            window_s=0.0,
            throughput_scope="pcell",
            requested_sample_count=3,
            manifest=RealCmw500Driver.adapter_manifest,
            simulated_diagnostic=False,
            statistical_basis_subframes=5000,
        )

    other = replace(request, requested_window_count=4)
    mismatched = _window(other)
    with pytest.raises(RuntimeError, match="frozen request mismatch"):
        await MeasureExecutor._measure_base_station_samples(
            _Driver(mismatched),
            window_s=0.0,
            throughput_scope="pcell",
            requested_sample_count=3,
            manifest=RealCmw500Driver.adapter_manifest,
            simulated_diagnostic=False,
            statistical_basis_subframes=5000,
        )
