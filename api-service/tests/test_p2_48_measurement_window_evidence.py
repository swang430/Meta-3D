from __future__ import annotations

from copy import deepcopy

import pytest

from app.hal.base_station import (
    BASE_STATION_MEASUREMENT_WINDOW_STAGES,
    BaseStationCleanupResult,
    BaseStationMeasurementStageReceipt,
    BaseStationMeasurementWindow,
    BaseStationMeasurementWindowRequest,
    BaseStationMeasurementWindowTrust,
)
from app.services.execution_scpi_evidence import (
    append_base_station_measurement_window,
)
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota.base_station_execution_evidence import (
    base_station_execution_evidence_is_formally_acceptable,
    canonical_snapshot_digest,
    parse_base_station_execution_evidence,
)
from tests.p1_73c_evidence_fixtures import POSITION, valid_cmw_evidence
from tests.test_p1_73c_base_station_window_writer import _Db, _execution, _window


def _trust_window() -> BaseStationMeasurementWindow:
    request = BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope="pcell",
        lifecycle="authoritative_closed",
        cardinality="single",
        requested_window_count=3,
        expected_window_count=1,
        window_index=0,
    )
    exchange_ids = ("life-1", "metric-1")
    trust = BaseStationMeasurementWindowTrust(
        schema_version=1,
        request=request,
        request_digest=request.digest,
        stages=tuple(
            BaseStationMeasurementStageReceipt(
                stage=stage,
                status="confirmed",
                reason="current window stage confirmed",
                exchange_ids=exchange_ids,
            )
            for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
        ),
        simulated=False,
        exchange_ids=exchange_ids,
        reason="current window trust confirmed",
        context_confirmed=True,
    )
    legacy = _window()
    return BaseStationMeasurementWindow(**{**legacy.__dict__, "trust": trust})


def _append(execution, window):
    append_base_station_measurement_window(
        _Db(execution),
        execution.id,
        attempt_id="attempt-new",
        lease_identity=ActiveBaseStationLeaseIdentity(
            lease_id="lease-new",
            measurement_attempt_id="attempt-new",
            adapter_id="cmw500",
            session_token="session-new",
        ),
        position=POSITION,
        ue_link_state="connected",
        window=window,
        cleanup=BaseStationCleanupResult(True, True, ()),
    )


def test_current_contract_rejects_a_window_without_common_trust():
    execution = _execution()
    evidence = execution.config["base_station_execution_evidence"]
    evidence["measurement_window_contract_version"] = 1

    with pytest.raises(ValueError, match="trust receipt"):
        _append(execution, _window())


def test_current_writer_persists_exact_frozen_request_and_trust():
    execution = _execution()
    evidence = execution.config["base_station_execution_evidence"]
    evidence["measurement_window_contract_version"] = 1

    _append(execution, _trust_window())

    stored = execution.config["base_station_execution_evidence"]
    row = stored["measurement_windows"][0]
    assert row["trust"]["request"]["requested_window_count"] == 3
    assert row["trust"]["request"]["expected_window_count"] == 1
    assert row["trust"]["request"]["window_index"] == 0
    assert row["trust"]["request_digest"] == _trust_window().trust.request.digest
    assert row["trust"]["context_confirmed"] is True
    assert row["lifecycle_exchange_ids"] == ["life-1", "metric-1"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(measurement_window_contract_version=None),
        lambda value: value["measurement_windows"][0].pop("trust"),
        lambda value: value["measurement_windows"][0]["trust"].update(
            request_digest="wrong"
        ),
        lambda value: value["measurement_windows"][0]["trust"]["request"].update(
            window_index=1
        ),
    ],
)
def test_explicit_current_contract_fails_closed_when_malformed(mutate):
    execution = _execution()
    evidence = execution.config["base_station_execution_evidence"]
    evidence["measurement_window_contract_version"] = 1
    _append(execution, _trust_window())
    value = deepcopy(execution.config["base_station_execution_evidence"])

    mutate(value)

    assert parse_base_station_execution_evidence(value) is None


def test_historical_absence_remains_canonical_without_synthesizing_new_truth():
    execution = _execution()
    _append(execution, _window())
    value = execution.config["base_station_execution_evidence"]

    assert "measurement_window_contract_version" not in value
    assert "trust" not in value["measurement_windows"][0]
    assert parse_base_station_execution_evidence(value) == value


def _current_formal_value():
    value = valid_cmw_evidence()
    value["measurement_window_contract_version"] = 1
    row = value["measurement_windows"][0]
    request = {
        "schema_version": 1,
        "scope": "pcell",
        "lifecycle": "authoritative_closed",
        "cardinality": "single",
        "requested_window_count": 3,
        "expected_window_count": 1,
        "window_index": 0,
    }
    exchange_ids = row["lifecycle_exchange_ids"]
    row["trust"] = {
        "schema_version": 1,
        "request": request,
        "request_digest": canonical_snapshot_digest(request),
        "stages": [
            {
                "stage": stage,
                "status": "confirmed",
                "reason": "current window stage confirmed",
                "exchange_ids": exchange_ids,
            }
            for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
        ],
        "simulated": False,
        "exchange_ids": exchange_ids,
        "reason": "current window trust confirmed",
        "context_confirmed": True,
    }
    return value


def test_current_formal_envelope_requires_common_trust_and_exact_cardinality():
    value = _current_formal_value()
    assert base_station_execution_evidence_is_formally_acceptable(value) is True

    context_drift = deepcopy(value)
    context_drift["measurement_windows"][0]["trust"]["context_confirmed"] = False
    assert base_station_execution_evidence_is_formally_acceptable(context_drift) is False

    cardinality_drift = deepcopy(value)
    request = cardinality_drift["measurement_windows"][0]["trust"]["request"]
    request.update(
        cardinality="requested",
        requested_window_count=2,
        expected_window_count=2,
    )
    cardinality_drift["measurement_windows"][0]["trust"][
        "request_digest"
    ] = canonical_snapshot_digest(request)
    assert base_station_execution_evidence_is_formally_acceptable(
        cardinality_drift
    ) is False


def test_current_formal_envelope_requires_one_window_shape_across_positions():
    value = _current_formal_value()
    second_position = {"azimuth_deg": 90.0, "elevation_deg": 0.0}
    value["requested_positions"].append(second_position)

    second_window = deepcopy(value["measurement_windows"][0])
    second_window.update(
        window_id="window-2",
        lease_id="lease-2",
        position=second_position,
    )
    second_request = second_window["trust"]["request"]
    second_request["scope"] = "all_cells"
    second_window["trust"]["request_digest"] = canonical_snapshot_digest(
        second_request
    )
    value["measurement_windows"].append(second_window)

    second_release = deepcopy(value["control_releases"][0])
    second_release["lease_id"] = "lease-2"
    value["control_releases"].append(second_release)

    assert base_station_execution_evidence_is_formally_acceptable(value) is False
