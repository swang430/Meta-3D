from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.mimo_ota.base_station_execution_evidence import (
    project_base_station_metrics_by_position,
)
from app.services.mimo_ota.executors.analysis import AnalysisExecutor
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.mimo_ota.rf_kpi_trust import (
    build_rf_kpi_trust,
    trusted_rf_kpi_values,
)
from app.services.report_service import (
    _base_station_projection_is_sanitized,
    _strip_untrusted_report_attestation,
    ReportComparisonService,
)
from app.services.test_execution.executor_base import StepExecutionStatus
from tests.p1_73c_evidence_fixtures import (
    POSITION,
    REQUESTED_CONFIG,
    valid_cmw_evidence,
)


def test_position_projection_keeps_throughput_when_bler_is_untrusted():
    evidence = valid_cmw_evidence()
    evidence["measurement_windows"][0]["metrics"]["dl_bler_percent"][
        "exchange_ids"
    ] = []

    rows = project_base_station_metrics_by_position(
        evidence,
        expected_config=REQUESTED_CONFIG,
        expected_positions=[POSITION],
    )

    assert len(rows) == 1
    assert rows[0]["dl_throughput_mbps"].status == "trusted"
    assert rows[0]["dl_throughput_mbps"].formal_value == 96.5
    assert rows[0]["dl_bler_percent"].status != "trusted"
    assert rows[0]["dl_bler_percent"].formal_value is None


def test_diagnostic_projection_uses_only_the_current_requested_position():
    evidence = valid_cmw_evidence()
    second_position = {"azimuth_deg": 90.0, "elevation_deg": 0.0}
    evidence["requested_positions"].append(second_position)
    second_window = deepcopy(evidence["measurement_windows"][0])
    second_window["window_id"] = "window-2"
    second_window["lease_id"] = "lease-2"
    second_window["position"] = second_position
    second_window["metrics"]["dl_throughput_mbps"]["value"] = 48.25
    evidence["measurement_windows"].append(second_window)
    evidence["current_measurement_attempt_state"] = "failed"

    rows = project_base_station_metrics_by_position(
        evidence,
        expected_config=REQUESTED_CONFIG,
        expected_positions=[POSITION, second_position],
    )

    assert rows[0]["dl_throughput_mbps"].diagnostic_value == 96.5
    assert rows[1]["dl_throughput_mbps"].diagnostic_value == 48.25


def test_rf_metric_scope_is_independent_per_metric():
    row = {
        "azimuth_deg": 0.0,
        "measurement_source": "instrument",
        "measurement_verified": True,
        "rsrp_dbm": -80.0,
        "rsrp_valid": True,
        "sinr_db": 20.0,
        "sinr_valid": False,
        "rank_indicator": 2.0,
        "rank_indicator_valid": True,
    }
    measure = {
        "measurement_source": "instrument",
        "measurement_verified": True,
        "simulated_sources": [],
        "azimuth_results": [row],
        "rf_kpi_trust": build_rf_kpi_trust(
            requested_azimuths=[0.0],
            azimuth_results=[row],
            source="explicit_real",
        ),
    }

    assert trusted_rf_kpi_values(measure, "rsrp_dbm") == [-80.0]
    assert trusted_rf_kpi_values(measure, "sinr_db") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current_peak", "frozen_peak", "expected_ratio"),
    [(100.0, 200.0, 0.4825), (100.0, None, None)],
)
async def test_analysis_recomputes_throughput_from_window_trust_not_raw_flags(
    monkeypatch,
    current_peak,
    frozen_peak,
    expected_ratio,
):
    from app.services.mimo_ota.executors import analysis as analysis_module

    evidence = valid_cmw_evidence()
    config = SimpleNamespace(
        theoretical_peak_throughput_mbps=current_peak,
        pass_criteria=SimpleNamespace(
            min_throughput_ratio=0.5,
            min_throughput_mbps=50.0,
            max_rsrp_variance_db=8.0,
            min_sinr_db=10.0,
            min_avg_rank_indicator=1.5,
        ),
    )
    measure = {
        "measurement_verified": True,
        "frequency_consistency": {"fully_verified": True},
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "path_loss_application": {},
        "throughput_verified": True,
        "azimuth_results": [
            {
                "azimuth_deg": 0.0,
                "throughput_mbps": 999.0,
                "bler": 99.0,
                "rsrp_dbm": -80.0,
                "sinr_db": 25.0,
                "rank_indicator": 2.0,
            }
        ],
    }
    execution_config = {"base_station_execution_evidence": deepcopy(evidence)}
    if frozen_peak is not None:
        execution_config[
            "mimo_ota_theoretical_peak_throughput_mbps"
        ] = frozen_peak
    execution = SimpleNamespace(
        id="execution-1",
        config=execution_config,
        validation_pass=True,
        validation_details=None,
    )
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )
    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _e: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _e, phase: measure if phase == "measure" else {"quiet_zone_pass": True},
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_args: None)
    monkeypatch.setattr(
        analysis_module, "path_loss_application_is_formally_verified", lambda _v: True
    )
    monkeypatch.setattr(analysis_module, "throughput_scope_is_verified", lambda _v: True)
    monkeypatch.setattr(analysis_module, "rf_kpi_scope_is_verified", lambda _v: True)
    monkeypatch.setattr(
        analysis_module, "quiet_zone_scope_is_formally_verified", lambda _v: True
    )
    monkeypatch.setattr(
        analysis_module,
        "base_station_expected_scope",
        lambda _config: (REQUESTED_CONFIG, [POSITION]),
        raising=False,
    )

    result = await AnalysisExecutor().execute(context)

    assert result.status == StepExecutionStatus.SUCCESS
    assert result.measurements["avg_throughput_mbps"] == pytest.approx(96.5)
    if expected_ratio is None:
        assert result.measurements["throughput_ratio"] is None
        assert result.measurements["throughput_pass"] is None
    else:
        assert result.measurements["throughput_ratio"] == pytest.approx(expected_ratio)


def test_commissioning_response_uses_server_metric_projection(monkeypatch):
    from app.api import commissioning

    evidence = valid_cmw_evidence()
    evidence["measurement_windows"][0]["metrics"]["dl_bler_percent"][
        "exchange_ids"
    ] = []
    execution = SimpleNamespace(
        id="execution-1",
        status="completed",
        started_at=None,
        completed_at=None,
        config={"base_station_execution_evidence": deepcopy(evidence)},
        measurements={
            "phases": {
                "measure": {
                    "overall_pass": True,
                    "measurement_verified": True,
                    "azimuth_results": [
                        {
                            "azimuth_deg": 0.0,
                            "throughput_mbps": 999.0,
                            "bler": 99.0,
                        }
                    ],
                }
            }
        },
    )
    test_case = SimpleNamespace(configuration={})
    response = commissioning._execution_to_session_response(execution, test_case)

    projection = response.mimo_test["base_station_metric_projection"][0]
    assert projection["dl_throughput_mbps"]["status"] == "trusted"
    assert projection["dl_throughput_mbps"]["formal_value"] == 96.5
    assert projection["dl_bler_percent"]["status"] != "trusted"
    assert projection["dl_bler_percent"]["formal_value"] is None


def test_report_recomputes_base_station_metrics_from_final_windows():
    evidence = valid_cmw_evidence()
    raw_row = {
        "azimuth_deg": 0.0,
        "measurement_source": "instrument",
        "measurement_verified": True,
        "rsrp_dbm": -80.0,
        "rsrp_valid": True,
        "sinr_db": 20.0,
        "sinr_valid": True,
        "rank_indicator": 2.0,
        "rank_indicator_valid": True,
        "throughput_mbps": 999.0,
        "throughput_valid": True,
        "throughput_scope": "pcell",
    }
    measure = {
        "measurement_source": "instrument",
        "measurement_verified": True,
        "simulated_sources": [],
        "path_loss_application": {
            "schema_version": 1,
            "status": "applied",
            "provenance": "real",
            "reason": "selected",
            "gate_mode": "strict",
            "certificate_id": "cert-1",
            "value_disclosure": "verified",
        },
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "throughput_scope": "pcell",
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [raw_row],
        "rf_kpi_trust": build_rf_kpi_trust(
            requested_azimuths=[0.0],
            azimuth_results=[raw_row],
            source="explicit_real",
        ),
        "formal_rf_kpi_verified": True,
    }
    execution = SimpleNamespace(
        config={"base_station_execution_evidence": deepcopy(evidence)},
        measurements={
            "phases": {
                "precheck": {},
                "reference": {"trp_verified": True},
                "measure": measure,
                "analysis": {"verdict": "PASS"},
            }
        },
        validation_pass=True,
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1),
    )

    with patch(
        "app.services.mimo_ota.executors.report."
        "quiet_zone_evidence_is_formally_verified",
        return_value=True,
    ):
        content = _build_mimo_ota_content_data(execution, datetime(2026, 1, 1))

    assert content["table_data"][0]["Throughput (Mbps)"] == "96.5"
    assert content["table_data"][0]["BLER (%)"] == "0.4"
    assert content["base_station_metric_trust_schema_version"] == 1
    assert _base_station_projection_is_sanitized(
        content["base_station_metric_projection"],
        content["base_station_metric_projection_attestation"],
    ) is True


def test_report_even_position_statistics_use_the_arithmetic_median():
    evidence = valid_cmw_evidence()
    second_position = {"azimuth_deg": 90.0, "elevation_deg": 0.0}
    evidence["requested_positions"].append(second_position)
    second_window = deepcopy(evidence["measurement_windows"][0])
    second_window.update(
        {
            "window_id": "window-2",
            "lease_id": "lease-2",
            "session_token": "session-2",
            "position": second_position,
            "started_at": "2026-08-26T08:00:03Z",
            "completed_at": "2026-08-26T08:00:04Z",
            "lifecycle_exchange_ids": ["life-3", "life-4"],
        }
    )
    second_window["metrics"]["dl_throughput_mbps"].update(
        {
            "session_token": "session-2",
            "value": 48.5,
            "exchange_ids": ["metric-throughput-2"],
        }
    )
    second_window["metrics"]["dl_bler_percent"].update(
        {
            "session_token": "session-2",
            "value": 3.0,
            "exchange_ids": ["metric-bler-2"],
        }
    )
    evidence["measurement_windows"].append(second_window)
    second_release = deepcopy(evidence["control_releases"][0])
    second_release.update({"lease_id": "lease-2", "session_token": "session-2"})
    evidence["control_releases"].append(second_release)
    evidence["exchange_ids"].extend(
        ["life-3", "life-4", "metric-throughput-2", "metric-bler-2"]
    )
    evidence["measurement_windows"][0]["metrics"]["dl_bler_percent"][
        "value"
    ] = 1.0
    execution = SimpleNamespace(
        config={"base_station_execution_evidence": evidence},
        measurements={
            "phases": {
                "precheck": {},
                "reference": {},
                "measure": {
                    "azimuth_results": [
                        {"azimuth_deg": 0.0},
                        {"azimuth_deg": 90.0},
                    ],
                    "path_loss_verified": True,
                    "path_loss_calibration_use_mock": False,
                    "path_loss_application": {},
                },
                "analysis": {"verdict": "UNKNOWN"},
            }
        },
        validation_pass=None,
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1),
    )

    with patch(
        "app.services.mimo_ota.executors.report."
        "path_loss_application_is_formally_verified",
        return_value=True,
    ):
        content = _build_mimo_ota_content_data(execution, datetime(2026, 1, 1))

    assert content["statistics"]["Throughput_Mbps"]["median"] == 72.5
    assert content["statistics"]["BLER_%"]["median"] == 2.0


def test_report_does_not_aggregate_a_partial_base_station_metric_scope():
    evidence = valid_cmw_evidence()
    second_position = {"azimuth_deg": 90.0, "elevation_deg": 0.0}
    evidence["requested_positions"].append(second_position)
    second_window = deepcopy(evidence["measurement_windows"][0])
    second_window["window_id"] = "window-2"
    second_window["lease_id"] = "lease-2"
    second_window["position"] = second_position
    second_window["metrics"]["dl_throughput_mbps"]["exchange_ids"] = []
    evidence["measurement_windows"].append(second_window)
    second_release = deepcopy(evidence["control_releases"][0])
    second_release["lease_id"] = "lease-2"
    evidence["control_releases"].append(second_release)
    raw_rows = [
        {"azimuth_deg": 0.0, "throughput_mbps": 999.0},
        {"azimuth_deg": 90.0, "throughput_mbps": 999.0},
    ]
    execution = SimpleNamespace(
        config={"base_station_execution_evidence": evidence},
        measurements={
            "phases": {
                "precheck": {},
                "reference": {},
                "measure": {
                    "azimuth_results": raw_rows,
                    "path_loss_verified": True,
                    "path_loss_calibration_use_mock": False,
                    "path_loss_application": {},
                },
                "analysis": {"verdict": "UNKNOWN"},
            }
        },
        validation_pass=None,
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1),
    )

    with patch(
        "app.services.mimo_ota.executors.report."
        "path_loss_application_is_formally_verified",
        return_value=True,
    ):
        content = _build_mimo_ota_content_data(execution, datetime(2026, 1, 1))

    assert "Throughput_Mbps" not in content["statistics"]
    assert content["table_data"][0]["Throughput (Mbps)"] == "N/A"
    assert content["table_data"][1]["Throughput (Mbps)"] == "N/A"


def test_client_cannot_self_attest_base_station_metric_projection():
    forged = {
        "title": "client payload",
        "base_station_metric_trust_schema_version": 1,
        "base_station_metric_projection": [],
        "base_station_metric_projection_attestation": {
            "schema_version": 1,
            "evidence_digest": "0" * 64,
            "metric_registry_digest": "1" * 64,
            "projection_digest": "2" * 64,
        },
    }

    assert _strip_untrusted_report_attestation(forged) == {
        "title": "client payload"
    }


@pytest.mark.parametrize(
    ("release_confirmed", "expected_throughput"),
    [(True, 96.5), (False, None)],
)
def test_comparison_rebuilds_throughput_from_current_window_truth(
    release_confirmed,
    expected_throughput,
):
    evidence = valid_cmw_evidence()
    evidence["control_releases"][0][
        "transport_session_released_confirmed"
    ] = release_confirmed
    execution = SimpleNamespace(
        id="execution-1",
        test_case_id="case-1",
        status="completed",
        started_at=None,
        config={
            "base_station_execution_evidence": evidence,
            "mimo_ota_theoretical_peak_throughput_mbps": 100.0,
        },
        measurements={
            "phases": {
                "measure": {},
                "analysis": {
                    "measurement_verified": True,
                    "throughput_verified": True,
                    "avg_throughput_mbps": 999.0,
                    "throughput_ratio": 9.99,
                    "rsrp_variance_db": 1.0,
                    "avg_sinr_db": 20.0,
                },
            }
        },
    )

    entry = ReportComparisonService._extract_execution_metrics(execution)

    assert entry["metrics"]["avg_throughput_mbps"] == expected_throughput
    assert entry["metrics"]["throughput_ratio"] == (
        pytest.approx(0.965) if release_confirmed else None
    )


def test_comparison_cmw_missing_evidence_cannot_fall_back_to_raw_flags():
    execution = SimpleNamespace(
        id="execution-1",
        test_case_id="case-1",
        status="completed",
        started_at=None,
        config={
            "base_station_adapter_profile_freeze": {
                "resolution": {"adapter": "cmw500"}
            },
            "mimo_ota_theoretical_peak_throughput_mbps": 100.0,
        },
        measurements={
            "phases": {
                "measure": {},
                "analysis": {
                    "measurement_verified": True,
                    "throughput_verified": True,
                    "avg_throughput_mbps": 999.0,
                    "throughput_ratio": 9.99,
                    "rsrp_variance_db": 1.0,
                    "avg_sinr_db": 20.0,
                    "rf_kpi_verified": True,
                },
            }
        },
    )

    entry = ReportComparisonService._extract_execution_metrics(execution)

    assert entry["metrics"] == {
        "avg_throughput_mbps": None,
        "throughput_ratio": None,
        "rsrp_variance_db": None,
        "avg_sinr_db": None,
    }
    assert all(
        trusted is False
        for trusted in entry["provenance"]["metric_trust"].values()
    )


def test_history_does_not_restore_pass_from_raw_throughput_flags(monkeypatch):
    from app.api import test_execution as history

    evidence = valid_cmw_evidence()
    evidence["control_releases"][0]["transport_session_released_confirmed"] = False
    execution = SimpleNamespace(
        config={"base_station_execution_evidence": evidence},
        measurements={
            "phases": {
                "precheck": {},
                "measure": {
                    "path_loss_verified": True,
                    "path_loss_calibration_use_mock": False,
                    "path_loss_application": {},
                    "throughput_verified": True,
                },
            }
        },
        validation_pass=True,
    )
    monkeypatch.setattr(
        history, "quiet_zone_scope_is_formally_verified", lambda _value: True
    )
    monkeypatch.setattr(
        history, "path_loss_application_is_formally_verified", lambda _value: True
    )
    monkeypatch.setattr(history, "throughput_scope_is_verified", lambda _value: True)
    monkeypatch.setattr(history, "rf_kpi_scope_is_verified", lambda _value: True)

    assert history._formal_validation_pass(execution, "MIMO_OTA") is None
