from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.hal.base_station import (
    BASE_STATION_MEASUREMENT_WINDOW_STAGES,
    BaseStationMeasurementStageReceipt,
    BaseStationMeasurementWindowRequest,
    BaseStationMeasurementWindowTrust,
)


def _request(**overrides):
    values = {
        "schema_version": 1,
        "scope": "pcell",
        "lifecycle": "authoritative_closed",
        "cardinality": "single",
        "requested_window_count": 3,
        "expected_window_count": 1,
        "window_index": 0,
    }
    values.update(overrides)
    return BaseStationMeasurementWindowRequest(**values)


def _stage(stage: str, status: str = "confirmed"):
    return BaseStationMeasurementStageReceipt(
        stage=stage,
        status=status,
        reason=f"{stage} {status}",
        exchange_ids=(f"{stage}-exchange",) if status == "confirmed" else (),
    )


def _trust(
    request=None,
    *,
    stages=None,
    simulated=False,
    exchange_ids=None,
    context_confirmed=True,
):
    request = _request() if request is None else request
    stages = (
        tuple(_stage(stage) for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES)
        if stages is None
        else stages
    )
    if exchange_ids is None:
        exchange_ids = tuple(
            exchange_id
            for stage in stages
            for exchange_id in stage.exchange_ids
        )
    return BaseStationMeasurementWindowTrust(
        schema_version=1,
        request=request,
        request_digest=request.digest,
        stages=stages,
        simulated=simulated,
        exchange_ids=exchange_ids,
        reason="window truth",
        context_confirmed=context_confirmed,
    )


def test_request_freezes_scope_cardinality_count_index_and_stable_digest():
    request = _request()

    assert request.digest == _request().digest
    assert request.expected_window_count == 1
    assert request.window_index == 0
    with pytest.raises(FrozenInstanceError):
        request.scope = "all_cells"
    with pytest.raises(TypeError, match="must not be used as bool"):
        bool(request)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema_version": 2}, "schema"),
        ({"scope": "simulated"}, "scope"),
        ({"requested_window_count": True}, "requested window count"),
        ({"requested_window_count": 0}, "requested window count"),
        ({"expected_window_count": 2}, "single cardinality"),
        (
            {
                "cardinality": "requested",
                "expected_window_count": 2,
            },
            "requested cardinality",
        ),
        ({"window_index": 1}, "window index"),
    ],
)
def test_request_rejects_invalid_or_split_frozen_shape(overrides, message):
    with pytest.raises((TypeError, ValueError), match=message):
        _request(**overrides)


def test_authoritative_closed_trust_is_formal_only_with_all_four_stage_proofs():
    trust = _trust()

    assert tuple(stage.stage for stage in trust.stages) == (
        "clear",
        "run",
        "ready",
        "closed",
    )
    assert trust.formally_confirmed is True
    assert trust.diagnostic_execution_allowed is True
    with pytest.raises(TypeError, match="must not be used as bool"):
        bool(trust)


def test_window_trust_requires_explicit_context_confirmation():
    request = _request()
    stages = tuple(
        _stage(stage) for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
    )

    with pytest.raises(TypeError, match="context_confirmed"):
        BaseStationMeasurementWindowTrust(
            schema_version=1,
            request=request,
            request_digest=request.digest,
            stages=stages,
            simulated=False,
            exchange_ids=tuple(
                exchange_id
                for stage in stages
                for exchange_id in stage.exchange_ids
            ),
            reason="window truth",
        )


def test_authoritative_lifecycle_with_one_unknown_stage_blocks_execution():
    stages = tuple(
        _stage(stage, "unknown" if stage == "closed" else "confirmed")
        for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
    )
    trust = _trust(stages=stages)

    assert trust.formally_confirmed is False
    assert trust.diagnostic_execution_allowed is False


def test_clear_read_only_and_unavailable_lifecycle_remain_diagnostic():
    clear_request = _request(
        lifecycle="clear_read_only",
        cardinality="requested",
        expected_window_count=3,
        window_index=1,
    )
    clear_stages = (
        _stage("clear", "confirmed"),
        _stage("run", "unavailable"),
        _stage("ready", "unavailable"),
        _stage("closed", "unavailable"),
    )
    clear_trust = _trust(clear_request, stages=clear_stages)
    unavailable_request = _request(
        lifecycle="unavailable",
        cardinality="requested",
        expected_window_count=3,
        window_index=2,
    )
    unavailable_stages = tuple(
        _stage(stage, "unavailable")
        for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
    )
    unavailable_trust = _trust(
        unavailable_request,
        stages=unavailable_stages,
        exchange_ids=("metric-read",),
    )

    assert clear_trust.formally_confirmed is False
    assert clear_trust.diagnostic_execution_allowed is True
    assert unavailable_trust.formally_confirmed is False
    assert unavailable_trust.diagnostic_execution_allowed is True


def test_simulated_window_is_diagnostic_even_without_transport_exchanges():
    request = _request(
        lifecycle="unavailable",
        cardinality="requested",
        expected_window_count=3,
        window_index=0,
    )
    stages = tuple(
        _stage(stage, "unavailable")
        for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
    )
    trust = _trust(
        request,
        stages=stages,
        simulated=True,
        exchange_ids=(),
    )

    assert trust.formally_confirmed is False
    assert trust.diagnostic_execution_allowed is True


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda values: values.update(request_digest="wrong"), "request digest"),
        (
            lambda values: values.update(
                stages=tuple(
                    _stage(stage)
                    for stage in ("clear", "run", "ready", "ready")
                )
            ),
            "exact ordered",
        ),
        (
            lambda values: values.update(exchange_ids=("clear-exchange",) * 2),
            "unique",
        ),
        (
            lambda values: values.update(
                stages=(
                    _stage("clear"),
                    _stage("run", "unavailable"),
                    _stage("ready", "unavailable"),
                    _stage("closed"),
                ),
                request=_request(lifecycle="clear_read_only"),
            ),
            "closed boundary",
        ),
        (
            lambda values: values.update(
                stages=tuple(
                    _stage(stage)
                    for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
                ),
                request=_request(lifecycle="unavailable"),
            ),
            "unavailable lifecycle",
        ),
        (lambda values: values.update(simulated=True), "simulated"),
    ],
)
def test_trust_rejects_digest_stage_lifecycle_and_simulation_drift(mutator, message):
    request = _request()
    stages = tuple(
        _stage(stage) for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
    )
    values = {
        "schema_version": 1,
        "request": request,
        "request_digest": request.digest,
        "stages": stages,
        "simulated": False,
        "exchange_ids": tuple(
            exchange_id
            for stage in stages
            for exchange_id in stage.exchange_ids
        ),
        "reason": "window truth",
        "context_confirmed": True,
    }
    mutator(values)
    if (
        message != "request digest"
        and isinstance(values.get("request"), BaseStationMeasurementWindowRequest)
    ):
        values["request_digest"] = values["request"].digest

    with pytest.raises((TypeError, ValueError), match=message):
        BaseStationMeasurementWindowTrust(**values)


def test_stage_receipt_requires_exact_truth_and_exchange_shape():
    with pytest.raises(ValueError, match="confirmed stage requires exchange ids"):
        BaseStationMeasurementStageReceipt(
            stage="clear",
            status="confirmed",
            reason="clear confirmed",
        )
    with pytest.raises(ValueError, match="cannot carry exchange ids"):
        BaseStationMeasurementStageReceipt(
            stage="clear",
            status="unknown",
            reason="clear unknown",
            exchange_ids=("stale",),
        )
