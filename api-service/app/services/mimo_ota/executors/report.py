"""Phase 5: Report archival.

Replaces commissioning_service.phase5_report. For now this is a thin stub that
emits a deterministic report_id and marks TestExecution as completed; a future
phase will plug in the standard TestReport template pipeline (single_execution
type, MIMO_OTA template).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.services.mimo_ota.executors._helpers import write_phase_result
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
    """Generate a report id, mark execution completed."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        execution = context.test_execution
        now = datetime.now(timezone.utc)
        report_id = (
            f"MIMO_OTA-{str(execution.id)[:8]}-{now.strftime('%Y%m%d%H%M%S')}"
        )

        result: Dict[str, Any] = {
            "report_id": report_id,
            "generated_at": now.isoformat(),
            "report_type": "single_execution",
            "format": "stub",  # TODO(phase1.x): wire into TestReport service for PDF
        }
        write_phase_result(execution, "report", result)

        # Mark execution lifecycle complete
        execution.status = "completed"
        execution.completed_at = now.replace(tzinfo=None)
        if execution.started_at:
            delta = (now.replace(tzinfo=None) - execution.started_at).total_seconds()
            execution.duration_sec = delta
        context.db.commit()

        logger.info("[%s] Phase 5: report_id=%s", execution.id, report_id)
        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result,
        )
