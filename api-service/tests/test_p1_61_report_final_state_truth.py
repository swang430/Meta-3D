"""P1-61：正式 MIMO 报告必须消费同一份最终生命周期真值。"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.report import TestReport
from app.models.test_plan import TestExecution
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.pdf_generator import PDFGenerator


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


def test_historical_completed_missing_timing_stays_unknown_in_payload_and_pdf():
    """旧行没有时长/完成时间时必须显示 N/A，不能编成 0 秒或重建时刻。"""
    execution = _execution(status="completed", duration_sec=None, completed_at=None)

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 22, 2, 0, 0),
        "historical-missing-timing",
    )

    assert content["duration_s"] is None
    assert content["execution_summary"]["total_duration_sec"] is None
    assert content["execution_summary"]["last_execution"] is None

    table = next(
        element
        for element in PDFGenerator()._generate_execution_summary_section(content)
        if hasattr(element, "_cellvalues")
    )
    assert any(
        row[0] == "Total Duration" and row[1] == "N/A"
        for row in table._cellvalues
    )


def test_public_regeneration_cannot_claim_internal_report_while_execution_running(
    monkeypatch,
):
    """内部 REPORT 的 pending 建行窗口不能被公开恢复入口抢走。"""
    from app.services.report_service import (
        LegacyMimoRegenerationRejected,
        ReportService,
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        execution = TestExecution(
            status="running",
            started_at=datetime.utcnow() - timedelta(seconds=5),
            executed_by="test_case_runner",
            config={"step_descriptors": [{"type": "MIMO_OTA_REPORT"}]},
            measurements={"phases": {"measure": {}, "analysis": {}}},
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        service = ReportService()
        report = service.create_report(
            db=db,
            title="internal-pending",
            report_type="single_execution",
            format="pdf",
            generated_by="mimo_ota.executors.report",
            test_execution_ids=[execution.id],
            content_data={},
        )
        monkeypatch.setattr(
            "app.services.report_service.PDFGenerator.generate_report",
            lambda *_args, **_kwargs: pytest.fail(
                "公开恢复入口不应取得内部 pending 报告的 writer claim"
            ),
        )

        with pytest.raises(
            LegacyMimoRegenerationRejected,
            match="terminal|终态|still running",
        ):
            service.generate_report(db, report.id)

        db.refresh(report)
        assert report.status == "pending"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


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

    def _settle(_db, target, projection):
        target.status = projection.status
        target.completed_at = projection.completed_at
        target.duration_sec = projection.duration_sec
        _db.commit()
        return projection

    monkeypatch.setattr(
        "app.services.mimo_ota.executors.report._settle_execution_lifecycle",
        _settle,
    )

    context = StepExecutionContext(
        db=db,
        step=StepDescriptor(id="report", type="MIMO_OTA_REPORT"),
        test_execution=execution,
    )
    result = await ReportExecutor().execute(context)

    assert result.status.value == "success"
    assert captured["created"] == {}, "终态裁决前不得公开 completed content_data"
    content = captured["generated"]
    assert content["test_plan"]["status"] == "completed"
    assert content["execution_summary"]["undetermined"] == 1
    assert content["execution_summary"]["pending"] == 0
    assert content["duration_s"] > 89.0
    assert execution.status == "completed"
    assert execution.duration_sec == pytest.approx(content["duration_s"])
    assert execution.completed_at.isoformat() == content["execution_summary"]["last_execution"]
    assert commits[-1] == "completed"


@pytest.mark.asyncio
async def test_cancel_during_pdf_generation_rebuilds_report_from_cancelled_truth(
    monkeypatch, tmp_path,
):
    """取消与完成只能有一个数据库赢家，PDF 必须跟随赢家终态。"""
    from app.services.mimo_ota.executors.report import ReportExecutor
    from app.services.test_execution import StepDescriptor, StepExecutionContext

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    runner_db = Session()
    cancel_db = Session()
    try:
        execution = TestExecution(
            status="running",
            started_at=datetime.utcnow() - timedelta(seconds=12),
            executed_by="test_case_runner",
            config={
                "phase_progress": [],
                "step_descriptors": [{"type": "MIMO_OTA_REPORT"}],
            },
            measurements={"phases": {"measure": {}, "analysis": {"verdict": "UNKNOWN"}}},
        )
        runner_db.add(execution)
        runner_db.commit()
        runner_db.refresh(execution)
        generated_contents = []

        def _generate_pdf(_self, report_data, _template, output_path):
            generated_contents.append(deepcopy(report_data))
            if len(generated_contents) == 1:
                cancelled = cancel_db.get(TestExecution, execution.id)
                cancelled.status = "cancelled"
                cancelled.completed_at = datetime.utcnow()
                cancelled.config = {**(cancelled.config or {}), "cancel_requested": True}
                cancel_db.commit()
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"%PDF-1.4\n")
            return str(path)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "app.services.report_service.PDFGenerator.generate_report",
            _generate_pdf,
        )
        monkeypatch.setattr(
            "app.services.test_case_runner._finalize_scpi_acceptance",
            lambda _execution: None,
        )

        from app.services.mimo_ota.executors import report as report_module

        original_settle = report_module._settle_execution_lifecycle

        def _assert_unpublished_then_settle(db, target, projection):
            observer = Session()
            try:
                artifact = observer.query(TestReport).one()
                assert artifact.status == "generating"
                assert artifact.file_path is None
                assert (artifact.content_data or {}).get("overall_result") != "undetermined"
            finally:
                observer.close()
            return original_settle(db, target, projection)

        monkeypatch.setattr(
            report_module,
            "_settle_execution_lifecycle",
            _assert_unpublished_then_settle,
        )

        context = StepExecutionContext(
            db=runner_db,
            step=StepDescriptor(id="report", type="MIMO_OTA_REPORT"),
            test_execution=execution,
        )
        result = await ReportExecutor().execute(context)

        runner_db.refresh(execution)
        assert result.status.value == "success"
        assert execution.status == "cancelled"
        assert execution.duration_sec is not None
        assert len(generated_contents) == 2, "取消先赢后必须重建正式报告"
        rebuilt = generated_contents[-1]
        assert rebuilt["test_plan"]["status"] == "cancelled"
        assert rebuilt["overall_result"] == "incomplete"
        assert rebuilt["execution_summary"]["incomplete"] == 1
        assert rebuilt["execution_summary"]["pending"] == 0
        assert rebuilt["duration_s"] == pytest.approx(execution.duration_sec)
    finally:
        cancel_db.close()
        runner_db.close()
        Base.metadata.drop_all(bind=engine)
