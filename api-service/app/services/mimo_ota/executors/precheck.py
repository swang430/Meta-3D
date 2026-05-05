"""Phase 1: System Pre-check.

Checks instrument connectivity, calibration validity, and quiet-zone quality.
Replaces commissioning_service.phase1_system_precheck — same checks, but the
chamber and instrument lookups now go through the bound LabProfile instead
of relying on a global "is_active" chamber row.
"""
import logging
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import desc

from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePathLossCalibration,
)
from app.services.mimo_ota.executors._helpers import (
    load_mimo_ota_config,
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

# Categories that must be online for any MIMO OTA test to proceed
_CRITICAL_INSTRUMENT_CATEGORIES = ["baseStation", "channelEmulator"]


@register_executor(MIMOOTAStepType.PRECHECK.value)
class PrecheckExecutor(IStepExecutor):
    """Verify the lab is ready: chamber bound, instruments online, calibration valid."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        lab = context.require_lab_profile()
        config = load_mimo_ota_config(context.test_execution)
        criteria = config.pass_criteria

        messages: list[str] = []
        result_payload: Dict[str, Any] = {}
        warnings: list[str] = []

        # --- 1. Chamber binding ---
        chamber = lab.chamber_config
        if chamber is None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message=f"LabProfile {lab.name} has no chamber_config bound",
            )
        result_payload["chamber_id"] = str(chamber.id)
        result_payload["chamber_name"] = chamber.name
        messages.append(f"Chamber: {chamber.name} ({chamber.num_probes} probes)")

        # --- 2. Instrument connectivity (HAL) ---
        from app.services.instrument_hal_service import get_hal_service
        from app.models.instrument import InstrumentCategory

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
        online_n = sum(1 for v in instruments_online.values() if v)
        messages.append(f"Instruments (HAL): {online_n}/{len(instruments_online)} online")

        # --- 2.5 UE Capability check (Phase 2e: 4x4 阻塞前防御) ---
        bs = hal.drivers.get("baseStation")
        ue_cap_pass = True  # default pass when bs unavailable (no DUT to check)
        if bs is not None and hasattr(bs, "query_ue_capability"):
            try:
                cap = await bs.query_ue_capability()
                result_payload["ue_capability"] = cap
                cap_max_dl = cap.get("max_dl_layers")
                if cap_max_dl is not None and cap_max_dl < config.mimo_layers:
                    ue_cap_pass = False
                    messages.append(
                        f"UE Capability: max_dl_layers={cap_max_dl} < requested "
                        f"{config.mimo_layers} — DUT will fall back to {cap_max_dl} layer DL"
                    )
                elif cap.get("source") == "unavailable":
                    warnings.append(
                        "UE capability unavailable (DUT may not be attached yet); "
                        "proceeding without 4x4 layer verification"
                    )
                    messages.append(
                        f"UE Capability: unavailable ({config.mimo_layers}-layer "
                        "request unverified)"
                    )
                else:
                    messages.append(
                        f"UE Capability: max_dl_layers={cap_max_dl} ≥ requested "
                        f"{config.mimo_layers} (PASS)"
                    )
            except Exception as e:  # noqa: BLE001
                warnings.append(f"UE capability query raised: {e}; skipped")
        result_payload["ue_capability_pass"] = ue_cap_pass

        # --- 3. Calibration validity ---
        cal_cert = context.calibration_certificate
        if cal_cert is not None:
            result_payload["calibration_certificate_id"] = str(cal_cert.id)
            result_payload["calibration_certificate_number"] = cal_cert.certificate_number
            result_payload["calibration_overall_pass"] = cal_cert.overall_pass
            messages.append(
                f"Calibration certificate: {cal_cert.certificate_number} "
                f"(overall_pass={cal_cert.overall_pass})"
            )
        else:
            warnings.append("No calibration_certificate bound to TestCase or LabProfile")

        # Path-loss calibration row (used by Phase 3 generation pipeline)
        chamber_id_hex = (
            chamber.id.hex if hasattr(chamber.id, "hex") else str(chamber.id).replace("-", "")
        )
        latest_pl = (
            context.db.query(ProbePathLossCalibration)
            .filter(
                ProbePathLossCalibration.chamber_id == chamber_id_hex,
                ProbePathLossCalibration.status == CalibrationStatus.VALID.value,
            )
            .order_by(desc(ProbePathLossCalibration.calibrated_at))
            .first()
        )
        if latest_pl is not None:
            age_h = (datetime.utcnow() - latest_pl.calibrated_at).total_seconds() / 3600.0
            result_payload["path_loss_calibration_valid"] = True
            result_payload["path_loss_calibration_age_hours"] = age_h
            messages.append(f"Path-loss calibration: VALID (age {age_h:.1f}h)")
        else:
            result_payload["path_loss_calibration_valid"] = False
            warnings.append(
                "No valid ProbePathLossCalibration for this chamber — "
                "Phase 3 will fall back to default cable loss"
            )

        # --- 4. Quiet zone ripple (Phase 2f: cross-probe pattern variation proxy) ---
        from app.services.probe_pattern.consumer import estimate_quiet_zone_ripple_db

        ripple_db = estimate_quiet_zone_ripple_db(
            context.db,
            num_probes=chamber.num_probes,
            frequency_mhz=config.frequency_hz / 1e6,
            polarization="V",
        )
        if ripple_db is None:
            # Conservative legacy fallback when no ProbePattern data exists yet
            ripple_db = 0.7
            result_payload["quiet_zone_ripple_source"] = "fallback_default"
            warnings.append(
                "No ProbePattern data for QZ ripple estimate; using legacy default 0.7 dB. "
                "Import vendor patterns via /api/v1/calibration/probe/pattern/import."
            )
        else:
            result_payload["quiet_zone_ripple_source"] = "probe_pattern_peak_spread"
        result_payload["quiet_zone_ripple_db"] = ripple_db
        qz_pass = ripple_db <= criteria.max_quiet_zone_ripple_db
        result_payload["quiet_zone_pass"] = qz_pass
        messages.append(
            f"Quiet zone ripple: ±{ripple_db:.1f} dB "
            f"({'PASS' if qz_pass else 'FAIL'}, threshold ±{criteria.max_quiet_zone_ripple_db:.1f}) "
            f"[{result_payload['quiet_zone_ripple_source']}]"
        )

        # --- 5. Overall verdict ---
        critical_online = all(
            instruments_online.get(k, False) for k in _CRITICAL_INSTRUMENT_CATEGORIES
        )
        overall_pass = critical_online and qz_pass and ue_cap_pass
        result_payload["critical_instruments_online"] = critical_online
        result_payload["overall_pass"] = overall_pass
        result_payload["messages"] = messages

        # Persist on TestExecution.measurements for downstream phases
        write_phase_result(context.test_execution, "precheck", result_payload)
        context.db.commit()

        if not overall_pass:
            failure_reason = []
            if not critical_online:
                failure_reason.append(
                    f"critical instruments offline: "
                    f"{[k for k in _CRITICAL_INSTRUMENT_CATEGORIES if not instruments_online.get(k)]}"
                )
            if not qz_pass:
                failure_reason.append(
                    f"quiet zone ripple ±{ripple_db} dB > threshold "
                    f"±{criteria.max_quiet_zone_ripple_db} dB"
                )
            if not ue_cap_pass:
                ue_cap = result_payload.get("ue_capability") or {}
                failure_reason.append(
                    f"UE max_dl_layers={ue_cap.get('max_dl_layers')} < requested "
                    f"{config.mimo_layers}"
                )
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                measurements=result_payload,
                warnings=warnings,
                error_message="Pre-check failed: " + "; ".join(failure_reason),
            )

        logger.info(
            "[%s] Pre-check PASS — %d/%d instruments, ripple ±%.2f dB",
            context.test_execution.id,
            online_n,
            len(instruments_online),
            ripple_db,
        )
        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result_payload,
            warnings=warnings,
        )
