"""Phase 4: CTIA pass/fail analysis.

Replaces commissioning_service.phase4_analysis. Pure compute over the data
already in TestExecution.measurements — no instruments touched.
"""
import logging
from typing import Any, Dict, List

from app.services.mimo_ota.executors._helpers import (
    load_mimo_ota_config,
    read_phase_result,
    write_phase_result,
)
from app.services.test_execution import (
    IStepExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepExecutionStatus,
    register_executor,
)
from app.schemas.mimo_ota.config import MIMOOTAStepType

logger = logging.getLogger(__name__)


@register_executor(MIMOOTAStepType.ANALYSIS.value)
class AnalysisExecutor(IStepExecutor):
    """CTIA pass/fail verdict over Phase 3 azimuth data + Phase 1 QZ result."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        config = load_mimo_ota_config(context.test_execution)
        criteria = config.pass_criteria

        try:
            measure = read_phase_result(context.test_execution, "measure")
            precheck = read_phase_result(context.test_execution, "precheck")
        except RuntimeError as e:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message=str(e),
            )

        azimuth_results: List[Dict[str, Any]] = measure.get("azimuth_results", [])
        if not azimuth_results:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="No azimuth_results in measure phase output",
            )

        if measure.get("measurement_verified") is False:
            result: Dict[str, Any] = {
                "verdict": "UNKNOWN",
                "details": [
                    "N/A: measurement contains simulated instrument provenance; "
                    "formal KPI analysis was not performed"
                ],
                "measurement_verified": False,
                "avg_throughput_mbps": None,
                "throughput_ratio": None,
                "throughput_pass": None,
                "rsrp_variance_db": None,
                "rsrp_pass": None,
                "avg_sinr_db": None,
                "sinr_pass": None,
                "avg_rank_indicator": None,
                "rank_pass": None,
                "qz_pass": None,
                "margin_db": None,
            }
            write_phase_result(context.test_execution, "analysis", result)
            context.test_execution.validation_pass = None
            context.test_execution.validation_details = result
            context.db.commit()
            logger.warning(
                "[%s] Phase 4: UNKNOWN (simulated measurement provenance)",
                context.test_execution.id,
            )
            return StepExecutionResult(
                status=StepExecutionStatus.SUCCESS,
                measurements=result,
                warnings=["模拟测量不进入正式 KPI 判定，结论保持 UNKNOWN"],
            )

        details: List[str] = []
        result: Dict[str, Any] = {}

        # --- Throughput ---
        tputs = [az["throughput_mbps"] for az in azimuth_results]
        avg_tput = sum(tputs) / len(tputs)
        peak = config.theoretical_peak_throughput_mbps
        ratio = avg_tput / peak if peak > 0 else 0.0
        tput_pass = (
            ratio >= criteria.min_throughput_ratio
            and avg_tput >= criteria.min_throughput_mbps
        )
        result["avg_throughput_mbps"] = avg_tput
        result["throughput_ratio"] = ratio
        result["throughput_pass"] = tput_pass
        details.append(
            f"Throughput: {avg_tput:.0f} Mbps ({ratio:.0%} of {peak:.0f}), "
            f"{'PASS' if tput_pass else 'FAIL'}"
        )

        # --- RSRP variance ---
        rsrps = [az["rsrp_dbm"] for az in azimuth_results]
        rsrp_variance = max(rsrps) - min(rsrps)
        rsrp_pass = rsrp_variance <= criteria.max_rsrp_variance_db
        result["rsrp_variance_db"] = rsrp_variance
        result["rsrp_pass"] = rsrp_pass
        details.append(
            f"RSRP variance: {rsrp_variance:.1f} dB "
            f"(threshold {criteria.max_rsrp_variance_db:.1f}), "
            f"{'PASS' if rsrp_pass else 'FAIL'}"
        )

        # --- SINR ---
        sinrs = [az["sinr_db"] for az in azimuth_results]
        avg_sinr = sum(sinrs) / len(sinrs)
        sinr_pass = avg_sinr >= criteria.min_sinr_db
        result["avg_sinr_db"] = avg_sinr
        result["sinr_pass"] = sinr_pass
        details.append(
            f"SINR avg: {avg_sinr:.1f} dB "
            f"(threshold {criteria.min_sinr_db:.1f}), "
            f"{'PASS' if sinr_pass else 'FAIL'}"
        )

        # --- Rank indicator ---
        ris = [az["rank_indicator"] for az in azimuth_results]
        avg_ri = sum(ris) / len(ris)
        ri_pass = avg_ri >= criteria.min_avg_rank_indicator
        result["avg_rank_indicator"] = avg_ri
        result["rank_pass"] = ri_pass
        details.append(
            f"Rank Indicator avg: {avg_ri:.2f} "
            f"(threshold {criteria.min_avg_rank_indicator:.1f}), "
            f"{'PASS' if ri_pass else 'FAIL'}"
        )

        # --- Quiet zone (from Phase 1) ---
        qz_pass = bool(precheck.get("quiet_zone_pass", False))
        result["qz_pass"] = qz_pass

        # --- Overall verdict + margin ---
        all_pass = tput_pass and rsrp_pass and sinr_pass and ri_pass and qz_pass
        if all_pass:
            margins = [
                ratio - criteria.min_throughput_ratio,
                criteria.max_rsrp_variance_db - rsrp_variance,
                avg_sinr - criteria.min_sinr_db,
                avg_ri - criteria.min_avg_rank_indicator,
            ]
            margin_db = min(margins)
            verdict = "PASS" if margin_db > 0.1 else "MARGINAL"
            result["margin_db"] = margin_db
        else:
            verdict = "FAIL"
            result["margin_db"] = 0.0

        result["verdict"] = verdict
        result["details"] = details

        write_phase_result(context.test_execution, "analysis", result)
        # Also surface the verdict on the canonical execution-level fields
        context.test_execution.validation_pass = (verdict in ("PASS", "MARGINAL"))
        context.test_execution.validation_details = result
        context.db.commit()

        logger.info(
            "[%s] Phase 4: %s (margin=%.2f)",
            context.test_execution.id,
            verdict,
            result["margin_db"],
        )

        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result,
        )
