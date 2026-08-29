from __future__ import annotations

import inspect

import pytest

from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.mimo_ota.executors.measure import MeasureExecutor


def test_cmw_manifest_freezes_one_pcell_authoritative_window():
    requests = MeasureExecutor._measurement_window_requests(
        RealCmw500Driver.adapter_manifest,
        throughput_scope="pcell",
        requested_sample_count=5,
        simulated_diagnostic=False,
    )

    assert len(requests) == 1
    assert requests[0].scope == "pcell"
    assert requests[0].lifecycle == "authoritative_closed"
    assert requests[0].cardinality == "single"
    assert requests[0].requested_window_count == 5
    assert requests[0].expected_window_count == 1
    assert requests[0].window_index == 0


def test_uxm_manifest_freezes_requested_diagnostic_windows_without_closed_claim():
    manifest = RealUxmDriver.adapter_manifest

    assert manifest.measurement is not None
    assert manifest.measurement.lifecycle == "unavailable"
    assert manifest.measurement.metrics == ()
    requests = MeasureExecutor._measurement_window_requests(
        manifest,
        throughput_scope="nr_all_cells",
        requested_sample_count=3,
        simulated_diagnostic=False,
    )

    assert len(requests) == 3
    assert [request.window_index for request in requests] == [0, 1, 2]
    assert {request.scope for request in requests} == {"all_cells"}
    assert {request.cardinality for request in requests} == {"requested"}
    assert {request.lifecycle for request in requests} == {"unavailable"}
    assert len({request.digest for request in requests}) == 3


def test_unbound_mock_gets_explicit_unavailable_diagnostic_plan():
    requests = MeasureExecutor._measurement_window_requests(
        None,
        throughput_scope="pcell",
        requested_sample_count=2,
        simulated_diagnostic=True,
    )

    assert len(requests) == 2
    assert all(request.lifecycle == "unavailable" for request in requests)
    assert all(request.cardinality == "requested" for request in requests)


def test_real_execution_cannot_invent_plan_when_manifest_has_no_measurement():
    with pytest.raises(ValueError, match="frozen manifest has no measurement"):
        MeasureExecutor._measurement_window_requests(
            None,
            throughput_scope="pcell",
            requested_sample_count=2,
            simulated_diagnostic=False,
        )


@pytest.mark.parametrize(
    ("manifest", "scope", "count", "message"),
    [
        (RealCmw500Driver.adapter_manifest, "nr_all_cells", 1, "scope"),
        (RealUxmDriver.adapter_manifest, "simulated", 1, "scope"),
        (RealUxmDriver.adapter_manifest, "pcell", 0, "positive"),
        (RealUxmDriver.adapter_manifest, "pcell", True, "positive"),
    ],
)
def test_frozen_plan_rejects_scope_and_count_drift(manifest, scope, count, message):
    with pytest.raises((TypeError, ValueError), match=message):
        MeasureExecutor._measurement_window_requests(
            manifest,
            throughput_scope=scope,
            requested_sample_count=count,
            simulated_diagnostic=False,
        )


def test_window_plan_builder_has_no_adapter_identity_branch():
    source = inspect.getsource(MeasureExecutor._measurement_window_requests)

    assert "cmw500" not in source.lower()
    assert "uxm" not in source.lower()
    assert "measurement_window_cardinality" not in source
