from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.hal.scpi_evidence import EvidenceVerdict
from app.services.execution_evidence_outcome import (
    execution_evidence_blocks_formal_outputs,
    project_execution_evidence_outcome,
)
from app.services.execution_scpi_evidence import (
    ExecutionScpiEvidence,
    public_execution_scpi_evidence,
)
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.report_data_collector import ReportDataCollector
from app.services.report_service import ReportComparisonService
from tests.test_p2_66_execution_evidence_outcome import _execution


def _invalid_formal_execution():
    execution = _execution(include_base_station_evidence=False)
    execution.id = uuid4()
    execution.test_case_id = uuid4()
    execution.validation_pass = True
    execution.duration_sec = 1.0
    execution.executed_at = datetime(2026, 9, 1)
    execution.started_at = datetime(2026, 9, 1)
    execution.completed_at = datetime(2026, 9, 1)
    execution.error_message = None
    execution.execution_number = 1
    execution.executed_by = "test_case_runner"
    execution.measurements = {
        "finite_value": 123.0,
        "phases": {
            "precheck": {},
            "reference": {},
            "measure": {},
            "analysis": {
                "verdict": "PASS",
                "measurement_verified": True,
                "throughput_verified": True,
                "rf_kpi_verified": True,
                "avg_throughput_mbps": 123.0,
                "throughput_ratio": 0.9,
                "rsrp_variance_db": 1.0,
                "avg_sinr_db": 20.0,
            },
        },
    }
    execution.test_results = {"score": 99.0}
    execution.config["base_station_adapter_profile_freeze"]["binding_digest"] = (
        "c" * 64
    )
    return execution


def test_invalid_compatibility_is_a_shared_formal_output_blocker():
    execution = _invalid_formal_execution()

    assert project_execution_evidence_outcome(
        execution
    ).compatibility_classification == "invalid"
    assert execution_evidence_blocks_formal_outputs(execution) is True


def test_public_scpi_evidence_cannot_republish_formal_acceptance():
    execution = _invalid_formal_execution()
    evidence = ExecutionScpiEvidence(
        execution_id=str(execution.id),
        formal_verdict=EvidenceVerdict.PASSED,
        formal_acceptance=True,
        reason="all_mandatory_evidence_confirmed",
    )
    execution.config["scpi_evidence"] = evidence.model_dump(mode="json")

    public = public_execution_scpi_evidence(execution)

    assert public is not None
    assert public["formal_verdict"] == "unknown"
    assert public["formal_acceptance"] is False
    assert public["reason"] == "execution_compatibility_invalid"


def test_report_collector_excludes_invalid_compatibility_numbers_and_verdict():
    execution = _invalid_formal_execution()
    collector = ReportDataCollector()

    assert collector._extract_measurements([execution]) == {}
    summary = collector._build_execution_summary([execution])
    assert summary.passed == 0
    assert summary.failed == 0
    assert summary.pending == 0
    assert summary.undetermined == 1
    assert summary.pass_rate is None


def test_report_comparison_marks_invalid_compatibility_metrics_untrusted():
    entry = ReportComparisonService._extract_execution_metrics(
        _invalid_formal_execution()
    )

    assert entry["provenance"]["execution_classification"] == "formal"
    assert all(
        trusted is False
        for trusted in entry["provenance"]["metric_trust"].values()
    )
    assert all(value is None for value in entry["metrics"].values())


def test_report_persists_server_owned_invalid_outcome_and_no_success_title():
    execution = _invalid_formal_execution()

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 9, 1),
        "case",
    )

    outcome = content["execution_evidence_outcome"]
    assert outcome["compatibility_classification"] == "invalid"
    assert outcome["completion_semantic"] == "pipeline_completed"
    assert content["execution_classification"] == "formal"
    assert content["overall_result"] == "undetermined"
    assert content["pass_rate"] is None
    assert content["statistics"] == {}
    assert "证据无效" in content["title"]
