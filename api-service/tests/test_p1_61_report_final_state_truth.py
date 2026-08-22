"""P1-61：正式 MIMO 报告必须消费同一份最终生命周期真值。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data


def _trusted_measure() -> dict:
    return {
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "throughput_scope": "pcell",
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [
            {
                "azimuth_deg": 0.0,
                "throughput_mbps": 123.0,
                "throughput_valid": True,
                "throughput_scope": "pcell",
            }
        ],
    }


def _execution(
    *,
    status: str,
    verdict: str = "UNKNOWN",
    validation_pass=None,
    trusted: bool = False,
    duration_sec=None,
    completed_at=None,
):
    measure = _trusted_measure() if trusted else {}
    return SimpleNamespace(
        id=uuid4(),
        measurements={
            "phases": {
                "measure": measure,
                "analysis": {"verdict": verdict},
            }
        },
        status=status,
        duration_sec=duration_sec,
        started_at=datetime(2026, 8, 22, 1, 0, 0),
        completed_at=completed_at,
        validation_pass=validation_pass,
    )


def _assert_one_state(summary: dict) -> None:
    assert sum(
        int(summary.get(key, 0))
        for key in ("passed", "failed", "pending", "undetermined", "incomplete")
    ) == 1


def test_completed_projection_replaces_running_zero_duration_and_pending_unknown():
    execution = _execution(status="running")
    completed_at = datetime(2026, 8, 22, 1, 1, 29, 195194, tzinfo=timezone.utc)
    projection = SimpleNamespace(
        status="completed",
        completed_at=completed_at,
        duration_sec=89.195194,
    )

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 22, 1, 1, 30, tzinfo=timezone.utc),
        "manual-run",
        lifecycle_projection=projection,
    )

    assert execution.status == "running", "报告投影不得提前修改 ORM 生命周期"
    assert execution.duration_sec is None
    assert content["test_plan"]["status"] == "completed"
    assert content["duration_s"] == pytest.approx(89.195194)
    summary = content["execution_summary"]
    assert summary["total_duration_sec"] == pytest.approx(89.195194)
    assert summary["pending"] == 0
    assert summary["undetermined"] == 1
    assert summary["pass_rate"] is None
    assert summary["last_execution"] == completed_at.isoformat()
    _assert_one_state(summary)


def test_historical_completed_unknown_is_undetermined_without_projection():
    completed_at = datetime(2026, 8, 22, 1, 1, 29)
    execution = _execution(
        status="completed",
        duration_sec=89.195194,
        completed_at=completed_at,
    )

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 22, 2, 0, 0),
        "historical-run",
    )

    summary = content["execution_summary"]
    assert summary["pending"] == 0
    assert summary["undetermined"] == 1
    assert summary["pass_rate"] is None
    assert summary["last_execution"] == completed_at.isoformat()
    _assert_one_state(summary)


@pytest.mark.parametrize(
    ("status", "verdict", "validation_pass", "trusted", "expected_state", "pass_rate"),
    [
        ("completed", "PASS", True, True, "passed", 100.0),
        ("completed", "FAIL", False, True, "failed", 0.0),
        ("completed", "UNKNOWN", None, False, "undetermined", None),
        ("pending", "UNKNOWN", None, False, "pending", None),
        ("running", "UNKNOWN", None, False, "incomplete", None),
        ("cancelled", "UNKNOWN", None, False, "incomplete", None),
        ("skipped", "UNKNOWN", None, False, "incomplete", None),
        ("failed", "UNKNOWN", None, False, "failed", 0.0),
    ],
)
def test_report_summary_uses_exactly_one_lifecycle_verdict_state(
    status,
    verdict,
    validation_pass,
    trusted,
    expected_state,
    pass_rate,
):
    execution = _execution(
        status=status,
        verdict=verdict,
        validation_pass=validation_pass,
        trusted=trusted,
        duration_sec=1.0,
        completed_at=datetime(2026, 8, 22, 1, 0, 1),
    )

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 22, 1, 0, 2),
        "state-table",
    )

    summary = content["execution_summary"]
    assert summary[expected_state] == 1
    assert summary["pass_rate"] == pass_rate
    _assert_one_state(summary)


@pytest.mark.asyncio
async def test_report_executor_projects_completed_content_without_early_orm_mutation(
    monkeypatch,
):
    from app.services.mimo_ota.executors.report import ReportExecutor, ReportService
    from app.services.test_execution import StepDescriptor, StepExecutionContext

    execution = _execution(status="running")
    execution.test_case_id = None
    execution.test_plan_id = None
    execution.started_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=89.195194)
    )
    commits = []
    db = SimpleNamespace(commit=lambda: commits.append(execution.status))
    captured = {}

    def _create_report(_self, **kwargs):
        assert execution.status == "running", "create_report 前不得提前提交 completed"
        captured["created"] = kwargs["content_data"]
        return SimpleNamespace(id=uuid4())

    def _generate_report(_self, **kwargs):
        assert execution.status == "running", "PDF 生成期间必须保留取消裁决窗口"
        captured["generated"] = kwargs["content_data_override"]
        return SimpleNamespace(file_path="projected.pdf", file_size_bytes=123)

    monkeypatch.setattr(ReportService, "create_report", _create_report)
    monkeypatch.setattr(ReportService, "generate_report", _generate_report)
    monkeypatch.setattr(
        "app.services.mimo_ota.executors.report.write_phase_result",
        lambda target, phase, value: target.measurements.setdefault("phases", {}).update(
            {phase: value}
        ),
    )
    monkeypatch.setattr(
        "app.services.test_case_runner._finalize_scpi_acceptance",
        lambda _execution: None,
    )

    context = StepExecutionContext(
        db=db,
        step=StepDescriptor(id="report", type="MIMO_OTA_REPORT"),
        test_execution=execution,
    )
    result = await ReportExecutor().execute(context)

    assert result.status.value == "success"
    assert captured["created"] is captured["generated"]
    content = captured["created"]
    assert content["test_plan"]["status"] == "completed"
    assert content["execution_summary"]["undetermined"] == 1
    assert content["execution_summary"]["pending"] == 0
    assert content["duration_s"] > 89.0
    assert execution.status == "completed"
    assert execution.duration_sec == pytest.approx(content["duration_s"])
    assert execution.completed_at.isoformat() == content["execution_summary"]["last_execution"]
    assert commits[-1] == "completed"
