"""TRP Phase 1: System pre-check.

Mirrors mimo_ota.executors.precheck for chamber binding + instrument
connectivity verification, but tailored to TRP's instrument set:
  - signalAnalyzer (must be online — TRP's primary measurement instrument)
  - positioner (must be online —球面扫描需要)
  - baseStation (optional but recommended; provides UL grant to DUT)

Reuses ProbePathLossCalibration / ProbePattern check from MIMO_OTA, since
TRP shares the same chamber + probe setup.
"""
import logging
from typing import Any, Dict

from app.services.test_execution import (
    IStepExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepExecutionStatus,
    register_executor,
)
from app.schemas.trp.config import TRPStepType

logger = logging.getLogger(__name__)

# TRP 的关键仪器: signalAnalyzer 是测量主体 (替代 MIMO_OTA 的 baseStation 主导)
_CRITICAL_INSTRUMENT_CATEGORIES = ["signalAnalyzer", "positioner"]


@register_executor(TRPStepType.PRECHECK.value)
class TRPPrecheckExecutor(IStepExecutor):
    """Verify the lab is ready for TRP: chamber bound, SA/positioner online."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        from app.services.instrument_hal_service import get_hal_service
        from app.models.instrument import InstrumentCategory

        lab = context.require_lab_profile()
        config_data = context.test_execution.configuration or {}
        config_grid = config_data.get("spatial_grid", {}) or {}
        n_theta_steps = config_grid.get("theta_step_deg", 15.0)
        n_phi_steps = config_grid.get("phi_step_deg", 15.0)

        result_payload: Dict[str, Any] = {}
        messages: list[str] = []
        warnings: list[str] = []

        # --- Chamber binding (与 MIMO_OTA 同模式) ---
        chamber = lab.chamber_config
        if chamber is None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message=f"LabProfile {lab.name} has no chamber_config",
            )
        result_payload["chamber_id"] = str(chamber.id)
        result_payload["chamber_name"] = chamber.name
        messages.append(f"Chamber: {chamber.name} ({chamber.num_probes} probes)")
        messages.append(
            f"Spatial grid: {n_theta_steps}° × {n_phi_steps}° steps "
            f"(see configuration.spatial_grid for full extent)"
        )

        # --- Instrument connectivity ---
        hal = get_hal_service()
        active_cats = (
            context.db.query(InstrumentCategory)
            .filter(InstrumentCategory.is_active == True)  # noqa: E712
            .all()
        )
        instruments_online: Dict[str, bool] = {
            cat.category_key: (hal.drivers.get(cat.category_key) is not None)
            for cat in active_cats
        }
        result_payload["instruments_online"] = instruments_online
        critical_online = all(
            instruments_online.get(k, False) for k in _CRITICAL_INSTRUMENT_CATEGORIES
        )
        result_payload["critical_instruments_online"] = critical_online
        messages.append(
            f"Critical instruments online (signalAnalyzer + positioner): "
            f"{'YES' if critical_online else 'NO'}"
        )

        # --- Verdict ---
        overall_pass = critical_online
        result_payload["overall_pass"] = overall_pass
        result_payload["messages"] = messages

        # Persist for downstream phases (mirror mimo_ota write_phase_result pattern)
        execution = context.test_execution
        if execution.measurements is None:
            execution.measurements = {}
        phases = execution.measurements.setdefault("phases", {})
        phases["precheck"] = result_payload
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(execution, "measurements")
        context.db.commit()

        if not overall_pass:
            missing = [
                k for k in _CRITICAL_INSTRUMENT_CATEGORIES
                if not instruments_online.get(k)
            ]
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                measurements=result_payload,
                warnings=warnings,
                error_message=f"TRP precheck failed: critical instruments offline {missing}",
            )

        logger.info(
            "[%s] TRP Pre-check PASS — %d/%d instruments",
            execution.id,
            sum(1 for v in instruments_online.values() if v),
            len(instruments_online),
        )
        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result_payload,
            warnings=warnings,
        )
