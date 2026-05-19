"""Phase 1: System Pre-check.

Checks instrument connectivity, calibration validity, and quiet-zone quality.
Replaces commissioning_service.phase1_system_precheck — same checks, but the
chamber and instrument lookups now go through the bound LabProfile instead
of relying on a global "is_active" chamber row.
"""
import logging
from datetime import datetime
from typing import Any, Dict

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

        # --- 2.4 DUT attach record check (Phase 2l: 防对错 IMSI 测试) ---
        # P1-9 (2026-05-19): missing/broken dut_attach now drives the strict
        # DUT gate at section 5b. Warning text reflects whether the run will
        # actually FAIL or only carry an audit trail (depends on
        # config.precheck_strict_dut). The dut_attach value is set here in
        # all cases; the gate below consumes it.
        dut_attach = (context.test_execution.measurements or {}).get("dut_attach")
        if dut_attach:
            result_payload["dut_attach"] = dut_attach
            messages.append(
                f"DUT: imsi={dut_attach.get('imsi', '?')[:8]}... "
                f"model={dut_attach.get('dut_model') or 'unspecified'} "
                f"rrc_connected={dut_attach.get('rrc_connected')}"
            )
        else:
            if config.precheck_strict_dut:
                # Will be turned into FAIL at section 5b; emit explanatory
                # warning here so the operator-facing log makes the chain
                # of cause-and-effect obvious.
                warnings.append(
                    "No DUT attach record on this execution — strict DUT gate "
                    "will fail this precheck. "
                    "POST /api/v1/test-executions/{id}/attach-dut before retry, "
                    "or set precheck_strict_dut=False for lab smoke."
                )
            else:
                warnings.append(
                    "No DUT attach record on this execution; "
                    "precheck_strict_dut=False — will proceed assuming DUT "
                    "is already in chamber (audit trail in dut_pass_reason)."
                )

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

        # --- 2.6 Channel emulator user alignment (PROPSIM F64 §17) ---
        # F64 user alignment 补偿内部通道相位/增益的时间&温度漂移. 重启后
        # 必须 SYST:CALIB:USER:SET 重新激活 — connect() 已经做过, 这里只
        # 上报状态供操作员判断当天 alignment 数据是否新鲜. 不在 alignment
        # 状态上 hard-fail: 这是 OPTIONAL license, 多数现场不一定激活.
        ce = hal.drivers.get("channelEmulator")
        if ce is not None and hasattr(ce, "get_user_alignment_status"):
            try:
                alignment = await ce.get_user_alignment_status()
            except Exception as e:  # noqa: BLE001
                alignment = None
                warnings.append(f"CE user-alignment query raised: {e}; skipped")
            if alignment:
                result_payload["channel_emulator_user_alignment"] = alignment
                messages.append(
                    f"CE user alignment: ACTIVE "
                    f"(name={alignment.get('alignment_name')!r})"
                )
            else:
                result_payload["channel_emulator_user_alignment"] = None
                warnings.append(
                    "Channel emulator has no user alignment loaded; "
                    "internal channel phase/gain consistency relies on "
                    "factory calibration only. Re-load via "
                    "SYST:CALIB:USER:SET if the emulator was just restarted."
                )
            if hasattr(ce, "list_external_units"):
                try:
                    units = await ce.list_external_units()
                    result_payload["channel_emulator_external_units"] = units
                    if units:
                        messages.append(
                            f"CE external alignment units: "
                            f"{len(units)} detected ({[u.get('unit') for u in units]})"
                        )
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"CE external-unit list raised: {e}; skipped")

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

        # Path-loss calibration row (used by Phase 3 generation pipeline).
        # 2026-05-19 P1-8 (Codex P1 on commit 42af8ca): use the same
        # frequency-matched lookup that the measure phase uses, otherwise
        # an old/different-band VALID cert could pass precheck but leave
        # measure phase with no usable cert (silent fallback we're trying
        # to prevent). The ProbePathLossCalibrationService applies a ±5%
        # frequency window (e.g. 3500 MHz target matches 3325-3675 MHz certs)
        # — same windowing measure.py uses at
        # api-service/app/services/mimo_ota/executors/measure.py:254.
        from app.services.path_loss_calibration_service import (
            ProbePathLossCalibrationService,
        )

        target_freq_mhz = config.frequency_hz / 1e6
        pl_service = ProbePathLossCalibrationService(context.db, use_mock=False)
        latest_pl = pl_service.get_latest_calibration(chamber.id, target_freq_mhz)

        result_payload["path_loss_calibration_target_frequency_mhz"] = target_freq_mhz
        if latest_pl is not None:
            age_h = (datetime.utcnow() - latest_pl.calibrated_at).total_seconds() / 3600.0
            result_payload["path_loss_calibration_valid"] = True
            result_payload["path_loss_calibration_age_hours"] = age_h
            result_payload["path_loss_calibration_frequency_mhz"] = latest_pl.frequency_mhz
            messages.append(
                f"Path-loss calibration: VALID (age {age_h:.1f}h, "
                f"cert@{latest_pl.frequency_mhz:.0f} MHz matches target "
                f"{target_freq_mhz:.0f} MHz within ±5% window)"
            )
        else:
            # Disambiguate the two failure modes for audit trail / operator UX:
            # - chamber has no VALID cert at all
            # - chamber has VALID cert(s), just none in the ±5% window
            any_valid_for_chamber = (
                context.db.query(ProbePathLossCalibration)
                .filter(
                    ProbePathLossCalibration.chamber_id == chamber.id,
                    ProbePathLossCalibration.status == CalibrationStatus.VALID.value,
                )
                .first()
            )
            result_payload["path_loss_calibration_valid"] = False
            if any_valid_for_chamber is not None:
                result_payload["path_loss_calibration_reason"] = "frequency_out_of_window"
                warnings.append(
                    f"No ProbePathLossCalibration in ±5% window of "
                    f"{target_freq_mhz:.0f} MHz for this chamber "
                    f"(chamber has VALID cert(s) but none at matching frequency) — "
                    f"Phase 3 will fall back to default cable loss"
                )
            else:
                result_payload["path_loss_calibration_reason"] = "no_cert_for_chamber"
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

        # --- 5. Calibration gate (P1-8, 2026-05-19) ---
        # 默认 strict: path_loss_cal 必有 + cal_cert 若存在则 overall_pass=True;
        # 显式 opt-out (config.precheck_strict_cal=False) 跳过 gate 维持 audit-only 行为.
        path_loss_valid = result_payload.get("path_loss_calibration_valid", False)
        cal_cert_broken = cal_cert is not None and not cal_cert.overall_pass
        cal_cert_missing_only = cal_cert is None  # warning, not FAIL — see P1-8 design #1

        if config.precheck_strict_cal:
            cal_pass = path_loss_valid and (not cal_cert_broken)
            cal_pass_reason_parts: list[str] = []
            if not path_loss_valid:
                cal_pass_reason_parts.append(
                    "path-loss calibration missing or invalid "
                    "(no VALID ProbePathLossCalibration for this chamber)"
                )
            if cal_cert_broken:
                cal_pass_reason_parts.append(
                    f"calibration_certificate not passed "
                    f"(cert={cal_cert.certificate_number}, overall_pass=False)"
                )
            cal_pass_reason = "; ".join(cal_pass_reason_parts) if cal_pass_reason_parts else "ok"
        else:
            # Bypass: cal_pass forced True but audit trail tells you which
            # gate(s) would have failed under strict mode. Lets ops grep the
            # measurements row to know "this run happened despite missing cal".
            cal_pass = True
            bypass_parts: list[str] = []
            if not path_loss_valid:
                bypass_parts.append("path-loss calibration missing")
            if cal_cert_broken:
                bypass_parts.append("cal_cert.overall_pass=False")
            if cal_cert_missing_only:
                bypass_parts.append("cal_cert is None")
            bypass_suffix = f" (would-fail-under-strict: {', '.join(bypass_parts)})" if bypass_parts else ""
            cal_pass_reason = f"bypassed via precheck_strict_cal=False{bypass_suffix}"

        result_payload["cal_pass"] = cal_pass
        result_payload["cal_pass_reason"] = cal_pass_reason

        # --- 5b. DUT attach gate (P1-9, 2026-05-19) ---
        # 默认 strict: dut_attach 必须存在 + rrc_connected == True.
        # 显式 opt-out (config.precheck_strict_dut=False) 跳过 gate, 维持
        # 旧的 "warning only" 行为. dut_attach 在 section 2.4 已经写进
        # result_payload (when present).
        dut_attach_missing = dut_attach is None or not dut_attach
        dut_rrc_state = (
            dut_attach.get("rrc_connected") if isinstance(dut_attach, dict) else None
        )
        dut_rrc_broken = (not dut_attach_missing) and (dut_rrc_state is not True)

        if config.precheck_strict_dut:
            dut_pass = (not dut_attach_missing) and (not dut_rrc_broken)
            dut_reason_parts: list[str] = []
            if dut_attach_missing:
                dut_reason_parts.append(
                    "DUT attach record missing "
                    "(POST /api/v1/test-executions/{id}/attach-dut before precheck)"
                )
            if dut_rrc_broken:
                dut_reason_parts.append(
                    f"DUT attached but rrc_connected={dut_rrc_state!r} "
                    "(expected True — measure phase needs RRC for PDSCH)"
                )
            dut_pass_reason = "; ".join(dut_reason_parts) if dut_reason_parts else "ok"
        else:
            dut_pass = True
            bypass_parts: list[str] = []
            if dut_attach_missing:
                bypass_parts.append("dut_attach missing")
            if dut_rrc_broken:
                bypass_parts.append(f"rrc_connected={dut_rrc_state!r}")
            bypass_suffix = (
                f" (would-fail-under-strict: {', '.join(bypass_parts)})"
                if bypass_parts else ""
            )
            dut_pass_reason = f"bypassed via precheck_strict_dut=False{bypass_suffix}"

        result_payload["dut_pass"] = dut_pass
        result_payload["dut_pass_reason"] = dut_pass_reason

        # --- 6. Overall verdict ---
        critical_online = all(
            instruments_online.get(k, False) for k in _CRITICAL_INSTRUMENT_CATEGORIES
        )
        overall_pass = (
            critical_online and qz_pass and ue_cap_pass and cal_pass and dut_pass
        )
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
            if not cal_pass:
                failure_reason.append(cal_pass_reason)
            if not dut_pass:
                failure_reason.append(dut_pass_reason)
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
