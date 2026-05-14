"""Phase 5: Report archival.

Replaces commissioning_service.phase5_report. Pulls phase results out of
TestExecution.measurements (written by precheck/reference/measure/analysis),
creates a TestReport row, and triggers PDFGenerator with a content-data
override so the executor doesn't need to retrofit ReportDataCollector for
MIMO_OTA-specific shapes.

If PDF generation fails (template missing, disk error, etc.) the execution
is still marked completed — the warning surfaces in the result payload so
the operator sees what happened, but a missing PDF should not roll back a
finished measurement.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.report import ReportFormat, ReportType
from app.services.mimo_ota.executors._helpers import write_phase_result
from app.services.report_service import ReportService
from app.services.test_execution import (
    IStepExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepExecutionStatus,
    register_executor,
)
from app.schemas.mimo_ota.config import MIMOOTAStepType

logger = logging.getLogger(__name__)


@register_executor(MIMOOTAStepType.REPORT.value)
class ReportExecutor(IStepExecutor):
    """Generate a PDF report from prior phases, mark execution completed."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        execution = context.test_execution
        now = datetime.now(timezone.utc)
        report_id_human = (
            f"MIMO_OTA-{str(execution.id)[:8]}-{now.strftime('%Y%m%d%H%M%S')}"
        )

        warnings: List[str] = []
        report_db_id: Optional[str] = None
        report_file_path: Optional[str] = None

        try:
            content_data = _build_mimo_ota_content_data(execution, now)
            svc = ReportService()
            # MIMO_OTA executions come from a TestCase, not a TestPlan, so
            # test_plan_id is typically None and `execution.test_plan` is
            # always None. The relationship itself is commented out in the
            # TestExecution model (see app/models/test_plan.py L249), so
            # accessing it as an attribute would raise AttributeError —
            # use getattr() to keep the null-guard semantics working.
            test_plan_for_title = getattr(execution, "test_plan", None)
            report = svc.create_report(
                db=context.db,
                title=(
                    f"MIMO OTA Test Report — "
                    f"{test_plan_for_title.name if test_plan_for_title else 'Unknown Plan'}"
                ),
                report_type=ReportType.SINGLE_EXECUTION.value,
                format=ReportFormat.PDF.value,
                generated_by="mimo_ota.executors.report",
                test_plan_id=execution.test_plan_id,
                test_execution_ids=[execution.id],
                content_data=content_data,
            )
            report_db_id = str(report.id)
            generated = svc.generate_report(
                db=context.db,
                report_id=report.id,
                content_data_override=content_data,
            )
            if generated and generated.file_path:
                report_file_path = generated.file_path
                logger.info(
                    "[%s] Phase 5: PDF generated → %s (%d bytes)",
                    execution.id, generated.file_path, generated.file_size_bytes or 0,
                )
            else:
                warnings.append("PDF generation returned no file_path")
        except Exception as e:  # noqa: BLE001
            # Don't tank the execution — log + warn so operator can re-trigger
            # report from the GUI without re-running the test.
            warnings.append(f"PDF generation failed: {e}")
            logger.exception("[%s] Phase 5: PDF generation failed", execution.id)

        result: Dict[str, Any] = {
            "report_id": report_id_human,
            "report_db_id": report_db_id,
            "report_file_path": report_file_path,
            "generated_at": now.isoformat(),
            "report_type": "single_execution",
            "format": "pdf" if report_file_path else "stub",
        }
        if warnings:
            result["warnings"] = warnings

        write_phase_result(execution, "report", result)

        # Mark execution lifecycle complete regardless of PDF outcome
        execution.status = "completed"
        execution.completed_at = now.replace(tzinfo=None)
        if execution.started_at:
            delta = (now.replace(tzinfo=None) - execution.started_at).total_seconds()
            execution.duration_sec = delta
        context.db.commit()

        logger.info("[%s] Phase 5: report_id=%s pdf=%s",
                    execution.id, report_id_human, bool(report_file_path))
        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result,
            warnings=warnings or None,
        )


def _build_mimo_ota_content_data(execution: Any, now: datetime) -> Dict[str, Any]:
    """Pack the 4 prior phase results into the dict shape PDFGenerator expects.

    PDFGenerator._auto_generate_sections inspects keys (test_plan,
    execution_summary, statistics, table_data, step_results) and emits one
    PDF section per recognized key. We populate every key for which we have
    real data; unrecognized keys are ignored harmlessly.
    """
    measurements = execution.measurements or {}
    phases = measurements.get("phases", {})
    precheck = phases.get("precheck", {}) or {}
    reference = phases.get("reference", {}) or {}
    measure = phases.get("measure", {}) or {}
    analysis = phases.get("analysis", {}) or {}

    # See report.execute(): `execution.test_plan` may be unset (commented-
    # out relationship) or None (MIMO_OTA sessions are TestCase-based, not
    # Plan-based). getattr keeps both branches safe.
    test_plan = getattr(execution, "test_plan", None)
    plan_info = {
        "name": test_plan.name if test_plan else "Unknown Plan",
        "description": (test_plan.description if test_plan else None) or "—",
        "status": execution.status,
        "created_by": (test_plan.created_by if test_plan else None) or "system",
    }

    overall_pass = bool(analysis.get("overall_pass", False))
    duration_sec = float(execution.duration_sec or 0.0)

    summary = {
        "total_executions": 1,
        "passed": 1 if overall_pass else 0,
        "failed": 0 if overall_pass else 1,
        "pending": 0,
        "pass_rate": 100.0 if overall_pass else 0.0,
        "total_duration_sec": duration_sec,
        "first_execution": execution.started_at.isoformat() if execution.started_at else None,
        "last_execution": execution.completed_at.isoformat() if execution.completed_at else now.isoformat(),
    }

    # Aggregate per-azimuth stats into one stat-row per KPI
    azimuth_results: List[Dict[str, Any]] = measure.get("azimuth_results") or []
    statistics = {}
    table_data = []
    if azimuth_results:
        for kpi_key, kpi_label, unit in [
            ("rsrp_dbm", "RSRP", "dBm"),
            ("sinr_db", "SINR", "dB"),
            ("throughput_mbps", "Throughput", "Mbps"),
            ("rank_indicator", "RankIndicator", ""),
        ]:
            values = [a.get(kpi_key) for a in azimuth_results if a.get(kpi_key) is not None]
            if values:
                vmin, vmax = min(values), max(values)
                vavg = sum(values) / len(values)
                vstd = _std(values)
                statistics[f"{kpi_label}_{unit}".strip("_")] = {
                    "metric_name": f"{kpi_label} ({unit})" if unit else kpi_label,
                    "mean": round(vavg, 3),
                    "median": round(sorted(values)[len(values) // 2], 3),
                    "std": round(vstd, 3),
                    "min": round(vmin, 3),
                    "max": round(vmax, 3),
                    "count": len(values),
                }

        for a in azimuth_results:
            table_data.append({
                "Azimuth (°)": f"{a.get('azimuth_deg', 0):.1f}",
                "RSRP (dBm)": f"{a.get('rsrp_dbm', 0):.1f}",
                "SINR (dB)": f"{a.get('sinr_db', 0):.1f}",
                "Throughput (Mbps)": f"{a.get('throughput_mbps', 0):.1f}",
                "RI": f"{a.get('rank_indicator', 0):.2f}",
            })

    step_results = [
        {"phase": "precheck", "status": "PASS" if precheck.get("overall_pass") else "FAIL",
         "messages": precheck.get("messages", [])},
        {"phase": "reference",
         "trp_dbm": reference.get("measured_trp_dbm"),
         "compensation_db": reference.get("compensation_factor_db")},
        {"phase": "measure",
         "frequency_ghz": measure.get("frequency_ghz"),
         "mimo_config": measure.get("mimo_config"),
         "cdl_model": measure.get("cdl_model_name"),
         "path_loss_compensation_db": measure.get("path_loss_compensation_db"),
         "azimuths_tested": len(azimuth_results)},
        {"phase": "analysis",
         "overall_pass": analysis.get("overall_pass"),
         "pass_criteria_summary": analysis.get("pass_criteria_summary")},
    ]

    return {
        "title": f"MIMO OTA Test Report — {plan_info['name']}",
        "generated_by": "MIMO OTA System",
        "generated_at": now.isoformat(),
        "overall_result": "passed" if overall_pass else "failed",
        "duration_s": duration_sec,
        "test_plan": plan_info,
        "execution_summary": summary,
        "statistics": statistics,
        "table_data": table_data,
        "step_results": step_results,
    }


def _std(values: List[float]) -> float:
    """Population stddev; returns 0 on <2 samples to avoid div-by-zero."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return var ** 0.5
