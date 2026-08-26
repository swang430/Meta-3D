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
from app.services.mimo_ota.throughput_trust import throughput_scope_is_verified
from app.services.mimo_ota.path_loss_application import (
    path_loss_application_is_formally_verified,
)
from app.services.mimo_ota.rf_kpi_trust import rf_kpi_scope_is_verified
from app.services.mimo_ota.quiet_zone_evidence import (
    quiet_zone_scope_is_formally_verified,
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

        frequency_consistency = measure.get("frequency_consistency")
        frequency_identity_unverified = (
            isinstance(frequency_consistency, dict)
            and frequency_consistency.get("fully_verified") is False
        )
        simulated_measurement = measure.get("measurement_verified") is False
        path_loss_unverified = not (
            measure.get("path_loss_verified") is True
            and measure.get("path_loss_calibration_use_mock") is False
            and path_loss_application_is_formally_verified(
                measure.get("path_loss_application")
            )
        )
        throughput_unverified = not (
            measure.get("throughput_verified") is True
            and throughput_scope_is_verified(measure)
        )
        rf_kpi_unverified = not rf_kpi_scope_is_verified(measure)
        quiet_zone_unverified = not quiet_zone_scope_is_formally_verified(precheck)
        if (
            simulated_measurement
            or frequency_identity_unverified
            or path_loss_unverified
            or throughput_unverified
            or rf_kpi_unverified
            or quiet_zone_unverified
        ):
            if simulated_measurement:
                detail = (
                    "N/A: measurement contains simulated instrument provenance; "
                    "formal KPI analysis was not performed"
                )
                warning = "模拟测量不进入正式 KPI 判定，结论保持 UNKNOWN"
                log_reason = "simulated measurement provenance"
            elif frequency_identity_unverified:
                detail = (
                    "N/A: F64 frequency identity is not fully verified; "
                    "formal KPI analysis was not performed"
                )
                warning = "F64 频率身份未完整闭环，不进入正式 KPI 判定，结论保持 UNKNOWN"
                log_reason = "frequency identity not fully verified"
            elif path_loss_unverified:
                detail = (
                    "N/A: path-loss calibration is not explicitly verified as "
                    "real; formal KPI analysis was not performed"
                )
                warning = "路损校准未明确验证为真实来源，不进入正式 KPI 判定，结论保持 UNKNOWN"
                log_reason = "path-loss calibration not explicitly verified"
            elif throughput_unverified:
                detail = (
                    "N/A: one or more azimuths have no explicitly valid "
                    "throughput sample; formal KPI analysis was not performed"
                )
                warning = "吞吐 KPI 缺少显式有效样本，不进入正式 KPI 判定，结论保持 UNKNOWN"
                log_reason = "throughput KPI validity is incomplete"
            elif rf_kpi_unverified:
                detail = (
                    "N/A: RSRP/SINR/RI lack complete per-metric, per-azimuth "
                    "explicit-real evidence; formal KPI analysis was not performed"
                )
                warning = "RF KPI 缺少逐指标、逐方位真实证据，不进入正式 KPI 判定，结论保持 UNKNOWN"
                log_reason = "RF KPI provenance is incomplete"
            else:
                detail = (
                    "N/A: quiet-zone uniformity lacks authoritative multi-point "
                    "field-scan evidence; formal KPI analysis was not performed"
                )
                warning = "静区均匀度缺少权威多点场扫描证据，不进入正式 KPI 判定，结论保持 UNKNOWN"
                log_reason = "quiet-zone evidence is not formally verified"
            result: Dict[str, Any] = {
                "verdict": "UNKNOWN",
                "details": [detail],
                "measurement_verified": not simulated_measurement,
                "frequency_identity_verified": not frequency_identity_unverified,
                "path_loss_verified": not path_loss_unverified,
                "throughput_verified": not throughput_unverified,
                "rf_kpi_verified": not rf_kpi_unverified,
                "qz_verified": not quiet_zone_unverified,
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
                "[%s] Phase 4: UNKNOWN (%s)",
                context.test_execution.id,
                log_reason,
            )
            return StepExecutionResult(
                status=StepExecutionStatus.SUCCESS,
                measurements=result,
                warnings=[warning],
            )

        details: List[str] = []
        result: Dict[str, Any] = {}

        # --- Throughput ---
        tputs = [az["throughput_mbps"] for az in azimuth_results]
        avg_tput = sum(tputs) / len(tputs)
        peak = config.theoretical_peak_throughput_mbps
        ratio = avg_tput / peak if peak is not None else None
        tput_pass = (
            ratio >= criteria.min_throughput_ratio
            and avg_tput >= criteria.min_throughput_mbps
            if ratio is not None
            else None
        )
        result["avg_throughput_mbps"] = avg_tput
        result["throughput_ratio"] = ratio
        result["throughput_pass"] = tput_pass
        if ratio is None:
            details.append(
                f"Throughput: {avg_tput:.0f} Mbps; ratio N/A "
                "(theoretical peak not provided), UNKNOWN"
            )
        else:
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
        qz_pass = precheck.get("quiet_zone_pass") is True
        result["qz_pass"] = qz_pass

        # --- Overall verdict + margin ---
        all_pass = tput_pass and rsrp_pass and sinr_pass and ri_pass and qz_pass
        if tput_pass is None:
            verdict = "UNKNOWN"
            result["margin_db"] = None
        elif all_pass:
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
        context.test_execution.validation_pass = (
            None if verdict == "UNKNOWN" else verdict in ("PASS", "MARGINAL")
        )
        context.test_execution.validation_details = result
        context.db.commit()

        margin_text = (
            f"{result['margin_db']:.2f}"
            if result["margin_db"] is not None
            else "N/A"
        )
        logger.info(
            "[%s] Phase 4: %s (margin=%s)",
            context.test_execution.id,
            verdict,
            margin_text,
        )

        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result,
        )
