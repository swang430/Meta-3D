from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.test_execution import _formal_validation_pass
from app.api.commissioning import _commissioning_measure_projection
from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    _qualification_payload_digest,
    execution_is_diagnostic,
)
from app.services.report_data_collector import ReportDataCollector
from app.services.report_service import (
    ReportComparisonService,
    report_has_provenance_trust,
)
from app.services.mimo_ota.executors.analysis import AnalysisExecutor
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.mimo_ota.executors.measure import (
    _evaluate_path_loss_provenance_for_measure,
)
from app.services.test_execution.executor_base import StepExecutionStatus
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence


def _diagnostic_qualification() -> dict:
    payload = {
        "schema_version": 1,
        "classification": "diagnostic",
        "policy_mode": "diagnostic",
        "policy": {
            "schema_version": 1,
            "mode": "diagnostic",
            "reason": "现场调试",
            "updated_by": "operator",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "binding_digest": "a" * 64,
        "binding_status": "configured",
        "execution_mode": "real",
        "adapter_id": "cmw500",
        "site_certification": None,
        "site_certification_digest": None,
        "reasons": ["test_case_policy_diagnostic"],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["qualification_digest"] = _qualification_payload_digest(payload)
    return payload


def _execution(*, qualification=True):
    config = {
        "step_descriptors": [{"type": "MIMO_OTA_MEASURE"}],
    }
    if qualification:
        config[EXECUTION_QUALIFICATION_KEY] = _diagnostic_qualification()
    return SimpleNamespace(
        id=uuid4(),
        test_case_id=uuid4(),
        status="completed",
        started_at=None,
        executed_at=None,
        duration_sec=1.0,
        validation_pass=True,
        config=config,
        measurements={
            "finite_diagnostic_value": 123.0,
            "phases": {
                "analysis": {
                    "verdict": "PASS",
                    "measurement_verified": True,
                    "throughput_verified": True,
                    "rf_kpi_verified": True,
                    "avg_throughput_mbps": 123.0,
                    "throughput_ratio": 0.9,
                    "rsrp_variance_db": 1.0,
                    "avg_sinr_db": 20.0,
                }
            },
        },
        test_results={"score": 99.0},
    )


def test_qualification_parser_is_legacy_compatible_and_fail_closed():
    assert execution_is_diagnostic(_execution(qualification=False)) is False
    execution = _execution()
    assert execution_is_diagnostic(execution) is True

    execution.config[EXECUTION_QUALIFICATION_KEY]["classification"] = "formal"
    assert execution_is_diagnostic(execution) is True


def test_history_never_republishes_diagnostic_validation_pass():
    assert _formal_validation_pass(_execution(), "MIMO_OTA") is None


def test_diagnostic_measure_never_applies_even_real_path_loss_certificate():
    usable, blocker = _evaluate_path_loss_provenance_for_measure(
        False,
        channel_emulator_is_real=True,
        strict=False,
        diagnostic=True,
    )

    assert usable is False
    assert blocker is None


def test_report_collector_excludes_diagnostic_numbers_and_verdict():
    execution = _execution()
    collector = ReportDataCollector()

    assert collector._extract_measurements([execution]) == {}
    summary = collector._build_execution_summary([execution])
    assert summary.passed == 0
    assert summary.failed == 0
    assert summary.pending == 0
    assert summary.undetermined == 1
    assert summary.pass_rate is None


def test_report_comparison_marks_every_diagnostic_metric_untrusted():
    entry = ReportComparisonService._extract_execution_metrics(_execution())

    assert entry["provenance"]["execution_classification"] == "diagnostic"
    assert all(
        trusted is False
        for trusted in entry["provenance"]["metric_trust"].values()
    )
    assert all(value is None for value in entry["metrics"].values())


def test_commissioning_projection_never_labels_diagnostic_metric_formal():
    execution = _execution()
    execution.config["base_station_execution_evidence"] = valid_cmw_evidence()
    projected = _commissioning_measure_projection(
        execution,
        SimpleNamespace(),
        {"azimuth_results": [{"azimuth_deg": 0.0, "throughput_mbps": 123.0}]},
    )

    assert projected["execution_classification"] == "diagnostic"
    metric = projected["base_station_metric_projection"][0][
        "dl_throughput_mbps"
    ]
    assert metric["status"] == "diagnostic"
    assert metric["formal_value"] is None
    assert metric["diagnostic_value"] == pytest.approx(96.5)


@pytest.mark.asyncio
async def test_analysis_keeps_finite_diagnostic_measurements_out_of_kpi(monkeypatch):
    from app.services.mimo_ota.executors import analysis as analysis_module

    execution = _execution()
    config = SimpleNamespace(
        theoretical_peak_throughput_mbps=200.0,
        pass_criteria=SimpleNamespace(
            min_throughput_ratio=0.5,
            min_throughput_mbps=50.0,
            max_rsrp_variance_db=8.0,
            min_sinr_db=10.0,
            min_avg_rank_indicator=1.5,
        ),
    )
    measure = {
        "azimuth_results": [{
            "azimuth_deg": 0.0,
            "throughput_mbps": 123.0,
            "rsrp_dbm": -80.0,
            "sinr_db": 20.0,
            "rank_indicator": 2.0,
        }]
    }
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )
    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _e: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _e, phase: measure if phase == "measure" else {},
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_args: None)

    result = await AnalysisExecutor().execute(context)

    assert result.status == StepExecutionStatus.SUCCESS
    assert result.measurements["execution_classification"] == "diagnostic"
    assert result.measurements["verdict"] == "UNKNOWN"
    assert result.measurements["avg_throughput_mbps"] is None
    assert execution.validation_pass is None


def test_report_marks_diagnostic_and_hides_every_formal_metric():
    evidence = valid_cmw_evidence()
    execution = _execution()
    execution.config["base_station_execution_evidence"] = deepcopy(evidence)
    execution.measurements = {
        "phases": {
            "precheck": {},
            "reference": {"trp_verified": True},
            "measure": {
                "measurement_source": "instrument",
                "measurement_verified": True,
                "path_loss_verified": True,
                "path_loss_calibration_use_mock": False,
                "path_loss_application": {
                    "schema_version": 1,
                    "status": "applied",
                    "provenance": "real",
                    "reason": "selected",
                    "gate_mode": "strict",
                    "certificate_id": "cert-1",
                    "value_disclosure": "verified",
                },
                "azimuth_results": [{
                    "azimuth_deg": 0.0,
                    "throughput_mbps": 123.0,
                    "rsrp_dbm": -80.0,
                    "sinr_db": 20.0,
                    "rank_indicator": 2.0,
                }],
            },
            "analysis": {"verdict": "PASS", "avg_throughput_mbps": 123.0},
        }
    }
    execution.completed_at = datetime(2026, 1, 1)

    content = _build_mimo_ota_content_data(execution, datetime(2026, 1, 1))

    assert content["execution_classification"] == "diagnostic"
    assert content["overall_result"] == "undetermined"
    assert content["statistics"] == {}
    assert content["pass_rate"] is None
    assert content["formal_path_loss_verified"] is False
    assert content["formal_throughput_verified"] is False
    assert content["formal_rf_kpi_verified"] is False
    assert content["formal_quiet_zone_verified"] is False
    metric = content["base_station_metric_projection"][0][
        "dl_throughput_mbps"
    ]
    assert metric["status"] == "diagnostic"
    assert metric["formal_value"] is None
    assert report_has_provenance_trust(content) is True
    assert content["step_results"][-1]["parameters"]["verdict"] == "UNKNOWN"
    for row in content["table_data"]:
        assert row["Throughput (Mbps)"] == "N/A"
        assert row["BLER (%)"] == "N/A"
