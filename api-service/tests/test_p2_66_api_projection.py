from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import yaml

from app.api import report as report_api
from app.api.report import _report_execution_outcome_state, _report_summary
from app.api.test_execution import _to_history_item
from app.api.test_plan import get_case_execution_status
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
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


def test_history_returns_the_shared_execution_evidence_outcome():
    execution = _invalid_formal_execution()

    item = _to_history_item(execution, "case", "MIMO_OTA")

    assert item.status == "completed"
    assert item.validation_pass is None
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
