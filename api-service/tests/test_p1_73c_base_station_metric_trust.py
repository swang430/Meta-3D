from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.mimo_ota.base_station_execution_evidence import (
    evaluate_base_station_metric_trust,
)
from tests.p1_73c_evidence_fixtures import (
    POSITION,
    REQUESTED_CONFIG,
    valid_cmw_evidence,
)


@pytest.mark.parametrize(
    ("metric_name", "expected_value", "expected_unit"),
    [
        ("dl_throughput_mbps", 96.5, "Mbps"),
        ("dl_bler_percent", 0.4, "%"),
    ],
)
def test_metric_trust_returns_only_the_requested_metric(metric_name, expected_value, expected_unit):
    result = evaluate_base_station_metric_trust(
        valid_cmw_evidence(),
        metric_name,
        expected_config=REQUESTED_CONFIG,
        expected_position=POSITION,
    )

    assert result.status == "trusted"
    assert result.formal_value == expected_value
    assert result.diagnostic_value == expected_value
    assert result.unit == expected_unit


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["measurement_windows"][0].update(config_digest="other"),
        lambda value: value["measurement_windows"][0].update(route_digest="other"),
        lambda value: value["measurement_windows"][0]["position"].update(azimuth_deg=30.0),
        lambda value: value["measurement_windows"][0].update(ue_link_state="disconnected"),
        lambda value: value["measurement_windows"][0].update(running_confirmed=False),
        lambda value: value["measurement_windows"][0].update(closed_off_confirmed=False),
        lambda value: value["measurement_windows"][0].update(completed_at="2026-08-26T07:59:59Z"),
        lambda value: value["measurement_windows"][0]["metrics"]["dl_throughput_mbps"].update(unit="kbit/s"),
        lambda value: value["measurement_windows"][0]["metrics"]["dl_throughput_mbps"].update(exchange_ids=[]),
    ],
)
def test_metric_trust_rejects_wrong_window_scope_or_lifecycle(mutation):
    evidence = valid_cmw_evidence()
    mutation(evidence)

    result = evaluate_base_station_metric_trust(
        evidence,
        "dl_throughput_mbps",
        expected_config=REQUESTED_CONFIG,
        expected_position=POSITION,
    )

    assert result.status != "trusted"
    assert result.formal_value is None


def test_expected_values_are_exact_and_cannot_be_backfilled_from_current_state():
    evidence = valid_cmw_evidence()

    wrong_config = {**REQUESTED_CONFIG, "lte_dl_earfcn": 1400}
    wrong_position = {**POSITION, "azimuth_deg": 30.0}

    assert evaluate_base_station_metric_trust(
        evidence,
        "dl_throughput_mbps",
        expected_config=wrong_config,
        expected_position=POSITION,
    ).status == "unknown"
    assert evaluate_base_station_metric_trust(
        evidence,
        "dl_throughput_mbps",
        expected_config=REQUESTED_CONFIG,
        expected_position=wrong_position,
    ).status == "unknown"


def test_one_metric_can_be_unknown_without_erasing_the_independent_metric():
    evidence = valid_cmw_evidence()
    evidence["measurement_windows"][0]["metrics"]["dl_bler_percent"]["exchange_ids"] = []

    throughput = evaluate_base_station_metric_trust(
        evidence,
        "dl_throughput_mbps",
        expected_config=REQUESTED_CONFIG,
        expected_position=POSITION,
    )
    bler = evaluate_base_station_metric_trust(
        evidence,
        "dl_bler_percent",
        expected_config=REQUESTED_CONFIG,
        expected_position=POSITION,
    )

    assert throughput.status == "trusted"
    assert throughput.formal_value == 96.5
    assert bler.status != "trusted"
    assert bler.formal_value is None


def test_cross_attempt_or_session_metric_substitution_is_rejected():
    evidence = valid_cmw_evidence()
    metric = evidence["measurement_windows"][0]["metrics"]["dl_throughput_mbps"]
    metric["measurement_attempt_id"] = "attempt-old"
    metric["session_token"] = "session-old"

    result = evaluate_base_station_metric_trust(
        evidence,
        "dl_throughput_mbps",
        expected_config=REQUESTED_CONFIG,
        expected_position=POSITION,
    )

    assert result.status != "trusted"
    assert result.formal_value is None
