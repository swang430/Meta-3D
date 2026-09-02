from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi import HTTPException

from app.api import commissioning as commissioning_api
from app.api import report as report_api
from app.api.report import _report_execution_outcome_state, _report_summary
from app.api.test_execution import _to_history_item
from app.api.test_plan import get_case_execution_status
from app.schemas.report import ReportCreate
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence
from tests.test_p2_66_execution_evidence_outcome import _execution
from tests.test_p2_66_formal_consumers import _invalid_formal_execution


REPO_ROOT = Path(__file__).resolve().parents[2]


class _SingleResultQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.value


class _SingleResultDb:
    def __init__(self, value):
        self.value = value

    def query(self, *_args, **_kwargs):
        return _SingleResultQuery(self.value)


class _ExecutionMapDb:
    def __init__(self, *executions):
        self.executions = {
            str(execution.id): execution
            for execution in executions
        }

    def get(self, _model, execution_id):
        return self.executions.get(str(execution_id))


def test_history_returns_the_shared_execution_evidence_outcome():
    execution = _invalid_formal_execution()

    item = _to_history_item(execution, "case", "MIMO_OTA")

    assert item.status == "completed"
    assert item.validation_pass is None
    assert item.execution_classification == "formal"
    assert item.execution_evidence_outcome.compatibility_classification == "invalid"
    assert item.execution_evidence_outcome.completion_semantic == "pipeline_completed"


def test_case_status_returns_the_same_execution_evidence_outcome():
    execution = _invalid_formal_execution()

    response = get_case_execution_status(
        execution.id,
        db=_SingleResultDb(execution),
    )

    assert response.status == "completed"
    assert response.execution_evidence_outcome.compatibility_classification == "invalid"
    assert response.execution_evidence_outcome.completion_semantic == "pipeline_completed"


def test_commissioning_response_sanitizes_invalid_measurement_and_analysis():
    execution = _invalid_formal_execution()
    execution.measurements["phases"]["measure"] = {
        "overall_pass": True,
        "measurement_verified": True,
        "azimuth_results": [
            {
                "azimuth_deg": 0.0,
                "throughput_mbps": 123.0,
                "rsrp_dbm": -80.0,
            }
        ],
    }
    test_case = SimpleNamespace(configuration={})

    response = commissioning_api._execution_to_session_response(
        execution,
        test_case,
    )

    assert response.mimo_test == {
        "execution_classification": "formal",
        "overall_pass": None,
        "base_station_metric_projection": [],
    }
    assert response.analysis["execution_classification"] == "formal"
    assert response.analysis["verdict"] == "UNKNOWN"
    assert response.analysis["avg_throughput_mbps"] is None
    assert response.analysis["throughput_ratio"] is None
    assert response.analysis["rsrp_variance_db"] is None
    assert response.analysis["avg_sinr_db"] is None
    assert "123.0" not in str(response.analysis)


def test_commissioning_projection_sanitizes_diagnostic_without_metric_evidence():
    execution = _execution(
        qualification="diagnostic",
        include_base_station_evidence=False,
    )
    measure = {
        "overall_pass": True,
        "azimuth_results": [{"throughput_mbps": 123.0}],
    }
    analysis = {"verdict": "PASS", "avg_throughput_mbps": 123.0}

    projected_measure = commissioning_api._commissioning_measure_projection(
        execution,
        SimpleNamespace(),
        measure,
    )
    projected_analysis = commissioning_api._commissioning_analysis_projection(
        execution,
        analysis,
    )

    assert projected_measure == {
        "execution_classification": "diagnostic",
        "overall_pass": None,
        "base_station_metric_projection": [],
    }
    assert projected_analysis["verdict"] == "UNKNOWN"
    assert projected_analysis["avg_throughput_mbps"] is None
    assert "123.0" not in str(projected_analysis)


def test_commissioning_projection_keeps_only_diagnostic_metric_rows_when_blocked():
    execution = _invalid_formal_execution()
    execution.config["base_station_execution_evidence"] = valid_cmw_evidence()
    measure = {
        "overall_pass": True,
        "measurement_verified": True,
        "formal_rf_kpi_verified": True,
        "path_loss_application": {
            "formal_eligible": True,
            "compensation_db": 7.5,
        },
        "azimuth_results": [
            {
                "azimuth_deg": 0.0,
                "throughput_mbps": 123.0,
                "rsrp_dbm": -80.0,
                "sinr_db": 20.0,
                "rank_indicator": 2.0,
            }
        ],
    }

    projected = commissioning_api._commissioning_measure_projection(
        execution,
        SimpleNamespace(),
        measure,
    )

    assert set(projected) == {
        "execution_classification",
        "overall_pass",
        "base_station_metric_projection",
    }
    assert projected["overall_pass"] is None
    assert projected["base_station_metric_projection"]
    metrics = projected["base_station_metric_projection"][0]["metrics"]
    assert metrics["dl_throughput_mbps"]["formal_value"] is None
    assert metrics["dl_throughput_mbps"]["diagnostic_value"] == 96.5


def test_report_summary_exposes_the_server_owned_execution_outcome(monkeypatch):
    execution = _invalid_formal_execution()
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    report = SimpleNamespace(
        id=execution.id,
        title=content["title"],
        report_type="single_execution",
        format="pdf",
        status="completed",
        progress_percent=100,
        file_size_bytes=1,
        generated_by="operator",
        generated_at=execution.completed_at,
        test_execution_ids=[execution.id],
        road_test_execution_id=None,
        content_data=content,
    )
    monkeypatch.setattr(
        report_api,
        "_mimo_report_is_provenance_sanitized",
        lambda _db, _report: True,
    )

    summary = _report_summary(_SingleResultDb(execution), report)

    assert summary.execution_evidence_outcome.compatibility_classification == "invalid"
    assert summary.execution_evidence_outcome.completion_semantic == "pipeline_completed"


def test_report_detail_reprojects_the_current_terminal_lifecycle(monkeypatch):
    execution = _invalid_formal_execution()
    execution.status = "running"
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    report = SimpleNamespace(
        id=execution.id,
        test_execution_ids=[execution.id],
        road_test_execution_id=None,
        content_data=content,
    )
    execution.status = "completed"
    monkeypatch.setattr(
        report_api.report_service,
        "get_report",
        lambda _db, _report_id: report,
    )
    monkeypatch.setattr(
        report_api,
        "_reject_untrusted_mimo_report",
        lambda _db, _report: None,
    )
    monkeypatch.setattr(
        report_api,
        "_reject_untrusted_vrt_report",
        lambda _report: None,
    )

    response = report_api.get_report(
        execution.id,
        db=_SingleResultDb(execution),
    )

    assert response.execution_evidence_outcome.pipeline_status == "completed"
    assert (
        response.execution_evidence_outcome.completion_semantic
        == "pipeline_completed"
    )


def test_generic_report_create_cannot_submit_server_owned_outcome(monkeypatch):
    monkeypatch.setattr(
        report_api.report_service,
        "create_report",
        lambda **_kwargs: SimpleNamespace(),
    )
    request = ReportCreate(
        title="client report",
        report_type="single_execution",
        generated_by="operator",
        content_data={"execution_evidence_outcome": {}},
    )

    with pytest.raises(HTTPException) as exc_info:
        report_api.create_report(request, db=object())

    assert exc_info.value.status_code == 422
    assert "server-owned" in str(exc_info.value.detail)


def test_report_projection_drift_is_explicitly_invalid_not_silently_trusted():
    execution = _invalid_formal_execution()
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    content["execution_evidence_outcome"]["compatibility_classification"] = (
        "compatible"
    )
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=[execution.id],
        content_data=content,
    )

    outcome, matches = _report_execution_outcome_state(
        _SingleResultDb(execution),
        report,
    )

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == "invalid"
    assert outcome.completion_semantic == "pipeline_completed"
    assert any("stored report" in reason for reason in outcome.reasons)


def test_malformed_stored_report_projection_fails_closed_without_crashing():
    execution = _invalid_formal_execution()
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    content["execution_evidence_outcome"] = {"pipeline_status": "completed"}
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=[execution.id],
        content_data=content,
    )

    outcome, matches = _report_execution_outcome_state(
        _SingleResultDb(execution),
        report,
    )

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any("malformed" in reason for reason in outcome.reasons)


def test_report_projection_allows_expected_running_to_completed_transition():
    execution = _invalid_formal_execution()
    execution.status = "running"
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=[execution.id],
        content_data=content,
    )
    execution.status = "completed"

    outcome, matches = _report_execution_outcome_state(
        _SingleResultDb(execution),
        report,
    )

    assert matches is True
    assert outcome is not None
    assert outcome.pipeline_status == "completed"
    assert outcome.completion_semantic == "pipeline_completed"


def test_report_projection_rejects_running_to_failed_terminal_transition():
    execution = _invalid_formal_execution()
    execution.status = "running"
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=[execution.id],
        content_data=content,
    )
    execution.status = "failed"

    outcome, matches = _report_execution_outcome_state(
        _SingleResultDb(execution),
        report,
    )

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == "invalid"
    assert any("lifecycle" in reason for reason in outcome.reasons)


def test_report_projection_cannot_be_trusted_after_source_execution_disappears():
    execution = _invalid_formal_execution()
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=[execution.id],
        content_data=content,
    )

    outcome, matches = _report_execution_outcome_state(
        _SingleResultDb(None),
        report,
    )

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == "invalid"
    assert any("source execution" in reason for reason in outcome.reasons)


def test_legacy_mimo_report_without_outcome_fails_closed_when_source_disappears():
    execution = _invalid_formal_execution()
    content = _build_mimo_ota_content_data(
        execution,
        execution.completed_at,
        "case",
    )
    content.pop("execution_evidence_outcome")
    report = SimpleNamespace(
        status="completed",
        report_type="single_execution",
        test_execution_ids=[execution.id],
        road_test_execution_id=None,
        content_data=content,
    )

    outcome, matches = _report_execution_outcome_state(
        _SingleResultDb(None),
        report,
    )

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any("source execution" in reason for reason in outcome.reasons)


@pytest.mark.parametrize(
    ("source_kind", "expected_classification"),
    [
        ("diagnostic", "diagnostic"),
        ("invalid", "invalid"),
        ("nonterminal", "compatible"),
        ("missing", "invalid"),
    ],
)
def test_multi_execution_report_aggregates_every_source_fail_closed(
    source_kind,
    expected_classification,
):
    formal = _execution()
    formal.id = uuid4()
    source = _execution()
    source.id = uuid4()
    if source_kind == "diagnostic":
        source = _execution(qualification="diagnostic")
        source.id = uuid4()
    elif source_kind == "invalid":
        source = _invalid_formal_execution()
    elif source_kind == "nonterminal":
        source = _execution(status="running")
        source.id = uuid4()

    missing_id = uuid4()
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=[
            formal.id,
            missing_id if source_kind == "missing" else source.id,
        ],
        content_data={},
    )
    db = _ExecutionMapDb(formal, *(() if source_kind == "missing" else (source,)))

    outcome, matches = _report_execution_outcome_state(db, report)

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == expected_classification
    assert outcome.completion_semantic != "valid_test_completed"
    assert outcome.formal_eligible is False


def test_multi_execution_report_is_formal_only_when_every_source_is_formal():
    executions = [_execution(), _execution()]
    for execution in executions:
        execution.id = uuid4()
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=[execution.id for execution in executions],
        content_data={},
    )

    outcome, matches = _report_execution_outcome_state(
        _ExecutionMapDb(*executions),
        report,
    )

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == "compatible"
    assert outcome.completion_semantic == "valid_test_completed"
    assert outcome.formal_eligible is True

    report.content_data = {
        "execution_evidence_outcome": outcome.model_dump(mode="json"),
    }
    frozen_outcome, frozen_matches = _report_execution_outcome_state(
        _ExecutionMapDb(*executions),
        report,
    )

    assert frozen_matches is True
    assert frozen_outcome == outcome


@pytest.mark.parametrize(
    "execution_ids",
    [
        [str(uuid4()), "not-a-uuid"],
        lambda execution_id: [execution_id, execution_id],
    ],
)
def test_multi_execution_report_rejects_malformed_or_duplicate_source_ids(
    execution_ids,
):
    execution = _execution()
    execution.id = uuid4()
    raw_ids = (
        execution_ids(execution.id)
        if callable(execution_ids)
        else execution_ids
    )
    report = SimpleNamespace(
        status="completed",
        test_execution_ids=raw_ids,
        content_data={},
    )

    outcome, matches = _report_execution_outcome_state(
        _ExecutionMapDb(execution),
        report,
    )

    assert matches is False
    assert outcome is not None
    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False


def test_live_and_checked_contracts_publish_the_shared_execution_outcome():
    from app.main import app

    live = app.openapi()["components"]["schemas"]
    checked = yaml.safe_load(
        (REPO_ROOT / "api/openapi.yaml").read_text()
    )["components"]["schemas"]

    assert "ExecutionEvidenceOutcome" in live
    assert "execution_evidence_outcome" in live["ExecutionHistoryItem"]["properties"]
    assert "execution_evidence_outcome" in live["CaseExecutionStatusResponse"]["properties"]
    assert "execution_evidence_outcome" in live["ReportSummary"]["properties"]

    assert "ExecutionEvidenceOutcome" in checked
    assert "execution_evidence_outcome" in checked["TestExecutionItem"]["properties"]
    assert "execution_evidence_outcome" in checked["CaseExecutionStatusResponse"]["properties"]
    assert "execution_evidence_outcome" in checked["ReportSummary"]["properties"]
