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
        managed_rf_attach = bool(
            (context.test_execution.config or {}).get("managed_rf_attach")
        )

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
        from app.services.instrument_hal_service import get_hal_service, is_mock_driver
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

        # --- 2.3a 载入 DUTProfile (供 2.3 声明校验 + 2.5b 交叉核对共用) ---
        # config.dut_profile_id 指向 DUTProfile 时载入一次; 非法 UUID / 不存在 → None + warn。
        # 2.5b 交叉核对要复用这个 dut_profile, 所以载入提到函数作用域 (不留在 2.3 局部块)。
        dut_profile = None
        if config.dut_profile_id:
            from app.models.dut_profile import DUTProfile
            from uuid import UUID as _UUID

            try:
                _dut_id = _UUID(str(config.dut_profile_id))
            except (ValueError, TypeError, AttributeError):
                _dut_id = None  # dut_profile_id 非法 UUID (填错) → 当不存在处理
            dut_profile = (
                context.db.query(DUTProfile).filter(DUTProfile.id == _dut_id).first()
                if _dut_id is not None
                else None
            )
            if dut_profile is None:
                warnings.append(
                    f"config.dut_profile_id={config.dut_profile_id} 指向的 DUTProfile 不存在 "
                    "(已删 / 填错 / 非法 id) — 跳过声明校验"
                )

        # --- 2.3 DUT 声明能力校验 (规划期, attach 前) ---
        # 拿 TestCase 请求跟 DUT **声明**能力比 (请求 > 声明 → 提前 fail, 不浪费真跑)。跟 2.5b
        # 交叉核对互补: 这个最早 (查 DB 声明不需硬件, 请求 vs 声明单向); 2.5b 是 attach 后
        # 声明 vs 实测协商双向。strict 可经 bring-up bypass 关 (precheck_strict_dut_capability)。
        if dut_profile is not None:
            from app.services.mimo_ota.dut_capability_check import check_dut_capability

            dut_cap = check_dut_capability(
                requested_layers=config.mimo_layers,
                requested_modulation=config.modulation,
                declared_max_dl_layers=dut_profile.max_dl_layers,
                declared_max_modulation_dl=dut_profile.max_modulation_dl,
            )
            result_payload["dut_capability_check"] = {
                "dut_profile": dut_profile.name,
                "consistent": dut_cap.consistent,
                "violations": dut_cap.violations,
            }
            if not dut_cap.consistent:
                if config.precheck_strict_dut_capability:
                    # Codex P2 (3083096): 早期 return 必须先持久化 precheck phase
                    # result —— 否则 execution.measurements.phases.precheck 为空,
                    # session 读出来还是 pending, UI/API 看不到 dut_capability_check
                    # violations (即便 phase 已 fail)。对齐 section 6 正常失败路径:
                    # write_phase_result + commit, return 带 measurements/warnings。
                    # 保留 fail-fast (请求层数根本超声明时, 不必再查 QZ/cal)。
                    result_payload["overall_pass"] = False
                    result_payload["messages"] = messages
                    write_phase_result(
                        context.test_execution, "precheck", result_payload
                    )
                    context.db.commit()
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        measurements=result_payload,
                        warnings=warnings,
                        error_message=(
                            f"DUT '{dut_profile.name}' 声明能力不满足 TestCase 请求: "
                            + "; ".join(dut_cap.violations)
                            + " (规划期提前 fail, 不浪费真跑; "
                            "precheck_strict_dut_capability=False 可绕)"
                        ),
                    )
                warnings.append(
                    f"DUT '{dut_profile.name}' 声明能力不满足请求 "
                    f"(precheck_strict_dut_capability=False, 继续): "
                    + "; ".join(dut_cap.violations)
                )
            else:
                messages.append(
                    f"DUT 声明能力校验: '{dut_profile.name}' 满足请求 "
                    f"({config.mimo_layers} 层 / {config.modulation})"
                )

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
        elif not managed_rf_attach:
            if config.precheck_strict_dut:
                # May be turned into FAIL at section 5b — the strict DUT gate
                # only engages against a real baseStation (mock/absent BS
                # auto-skips it, see section 5b). Emit the heads-up here so the
                # operator-facing log makes the cause-and-effect obvious.
                warnings.append(
                    "No DUT attach record on this execution — strict DUT gate "
                    "will fail this precheck when run against a real baseStation "
                    "(mock/absent baseStation auto-skips the gate). "
                    "用暗室首测面板的「登记 DUT」按钮登记 IMSI 后重试 "
                    "(等价于 POST /api/v1/test-executions/{id}/attach-dut), "
                    "or set precheck_strict_dut=False to override on real hardware."
                )
            else:
                warnings.append(
                    "No DUT attach record on this execution; "
                    "precheck_strict_dut=False — will proceed assuming DUT "
                    "is already in chamber (audit trail in dut_pass_reason)."
                )
        else:
            messages.append(
                "DUT live gate deferred: MEASURE 将先按本次 TestCase 初始化 "
                "UXM/F64/开关矩阵，再执行受控 attach 与动态核对"
            )

        # --- 2.4b SIM 身份核对 (P2-13 Phase 2: 防插错卡) ---
        # config.sim_profile_id 指向声明卡时, 拿 **实测**(优先 ue_info_snapshot.imsi)/attach 手敲
        # IMSI 跟 SIMProfile.imsi 比 —— 不一致 = 实际 attach 的卡跟 TestCase 选的卡对不上 (插错卡 /
        # IMSI 敲错), 测的不是预期那张, 结果无意义。
        # strict (precheck_strict_sim_identity, 默认 True) → FAIL; opt-out → warn。mock-aware:
        # 无 sim_profile_id / SIMProfile 不存在 / 卡无声明 imsi / 无 dut_attach → 跳过。
        if config.sim_profile_id and not managed_rf_attach:
            from app.models.sim_profile import SIMProfile
            from uuid import UUID as _UUID

            try:
                _sim_id = _UUID(str(config.sim_profile_id))
            except (ValueError, TypeError, AttributeError):
                _sim_id = None  # 非法 UUID (填错) → 当不存在
            sim_profile = (
                context.db.query(SIMProfile).filter(SIMProfile.id == _sim_id).first()
                if _sim_id is not None
                else None
            )
            if sim_profile is None:
                warnings.append(
                    f"config.sim_profile_id={config.sim_profile_id} 指向的 SIMProfile 不存在 "
                    "(已删 / 填错 / 非法 id) — 跳过 SIM 身份核对"
                )
            else:
                # 优先 modem **实测** IMSI (ue_info_snapshot.imsi), 没有再 fallback 操作员**手敲**的
                # dut_attach.imsi —— Codex P2 #141: 只比手敲值会被"号码敲对但插错卡"假通过, 真·防插错卡
                # 要比 modem 上报的实测身份 (feedback_test_real_dispatch_not_display_field: 测真实生效
                # 值, 不是标称/自填字段)。query_ue_capability 当前不报 imsi → 多数情况 fallback 到手敲值
                # (仍能 catch TestCase 选卡 vs attach 手敲不一致); 等档 A 驱动报实测 imsi 后自动升级成
                # 真观测比对。
                _snapshot = (dut_attach or {}).get("ue_info_snapshot") or {}
                _observed_imsi = _snapshot.get("imsi")
                _attached_imsi = _observed_imsi or (dut_attach or {}).get("imsi")
                _imsi_source = "observed" if _observed_imsi else "declared"
                if sim_profile.imsi and _attached_imsi:
                    from app.services.mimo_ota.sim_identity_check import check_sim_identity

                    sim_id = check_sim_identity(
                        declared_imsi=sim_profile.imsi,
                        attached_imsi=_attached_imsi,
                    )
                    result_payload["sim_identity_check"] = {
                        "sim_profile": sim_profile.name,
                        "consistent": sim_id.consistent,
                        "imsi_source": _imsi_source,  # observed=modem 实测 / declared=操作员手敲
                        "declared_imsi": sim_id.declared_imsi_masked,
                        "attached_imsi": sim_id.attached_imsi_masked,
                    }
                    _src_txt = "实测协商" if _imsi_source == "observed" else "attach 记录(手敲)"
                    if not sim_id.consistent:
                        if config.precheck_strict_sim_identity:
                            # 早期 fail 持久化 phase result (同 dut_capability strict, Codex P2 #135)
                            result_payload["overall_pass"] = False
                            result_payload["messages"] = messages
                            write_phase_result(
                                context.test_execution, "precheck", result_payload
                            )
                            context.db.commit()
                            return StepExecutionResult(
                                status=StepExecutionStatus.FAILED,
                                measurements=result_payload,
                                warnings=warnings,
                                error_message=(
                                    f"SIM 身份不符: TestCase 选的卡 '{sim_profile.name}' 声明 IMSI "
                                    f"({sim_id.declared_imsi_masked}) 跟 {_src_txt} IMSI "
                                    f"({sim_id.attached_imsi_masked}) 不一致 —— 可能插错卡 / IMSI 敲错; "
                                    "precheck_strict_sim_identity=False 可绕"
                                ),
                            )
                        warnings.append(
                            f"SIM 身份不符 (precheck_strict_sim_identity=False, 继续): TestCase 选卡 "
                            f"'{sim_profile.name}' 声明 IMSI 跟 {_src_txt} IMSI 不一致"
                        )
                    else:
                        messages.append(
                            f"SIM 身份核对 ({_imsi_source}): IMSI 匹配 TestCase 选的卡 "
                            f"'{sim_profile.name}'"
                        )

        # --- 2.5 UE Capability check (Phase 2e: 4x4 阻塞前防御) ---
        # P1-9 (Codex P2 on 655d7e3, 2026-05-19): 同时设 `live_ue_query_state`
        # 给 section 5b 的 DUT gate 用 — cached `dut_attach.rrc_connected`
        # 快照可能在 attach 跟 precheck 之间 stale (DUT 掉线), strict 模式
        # 必须 cross-check 实时 query 状态。"available" = query 成功且 source
        # 非 unavailable; "unavailable" = query 报 unavailable; "unknown" =
        # 没有 BS / 没有 query_ue_capability / query 抛异常。
        bs = hal.drivers.get("baseStation")
        ue_cap_pass = True  # default pass when bs unavailable (no DUT to check)
        live_ue_query_state: str = "unknown"
        if managed_rf_attach:
            # 标准吞吐量流程尚未开始本次 TestCase 的 RF 初始化，此时读取
            # UE 状态/能力只会把上一轮残留状态误当成本轮证据。明确记为延期，
            # 由 MEASURE 在 UXM/F64/开关矩阵配置完成且 attach 后重新采集。
            live_ue_query_state = "deferred"
            result_payload["ue_capability_deferred"] = True

        # ⚠ **连通性**判据取小区状态，不取 UE 能力（外审 #304 P1）。
        #   `live_ue_query_state` 喂给下面 §5b 的严格 DUT 门，而
        #   `query_ue_capability` 查的是能力不是状态：LTE_NR_IRAT 上那几条
        #   命令模板全是 None，即使小区已回 CONN 它也恒报 unavailable →
        #   严格门永远判 DUT 没挂上。同 measure `_probe_ue_attached` 与
        #   attach-dut 端点，三处同源。
        if (
            not managed_rf_attach
            and bs is not None
            and hasattr(bs, "get_cell_state")
        ):
            try:
                from app.hal.base_station import CellState

                _state = await bs.get_cell_state()
                result_payload["cell_state"] = getattr(_state, "value", _state)
                live_ue_query_state = (
                    "available" if _state == CellState.CONNECTED else "unavailable"
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[precheck] 小区状态查询失败: %s", e)
                live_ue_query_state = "unknown"

        # 能力查询仍然做，但只用于**层数协商校验**，不再决定连通性
        if (
            not managed_rf_attach
            and bs is not None
            and hasattr(bs, "query_ue_capability")
        ):
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
                elif cap_max_dl is None:
                    # ⚠ 判据换成"能力**读到了没有**"，不再借 live_ue_query_state
                    #   （那个现在表示小区连通性，跟能力读没读到是两回事）。
                    warnings.append(
                        "UE 能力读不到（DUT 可能尚未接入，或本方言无 UEINFO 命令）；"
                        "跳过层数协商校验"
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

                # --- 2.5b DUTProfile 声明 vs 实测协商交叉核对 (阶段 4) ---
                # 声明 (DUTProfile, 规划期) vs 协商 (query_ue_capability, attach 后) 双向比;
                # 不一致 = 有用发现 (固件 / SIM / 声明过时), **audit-only surface, 不 fail
                # 不覆盖声明**。observed 单独记 measurements, operator 在 DUT 声明页**显式**
                # 反写。仅真实 UE (source==real_ue) 核对; mock / unavailable → skipped (避免假阳)。
                if dut_profile is not None:
                    from app.services.mimo_ota.dut_capability_crosscheck import (
                        canonical_modulation,
                        check_dut_capability_mismatch,
                    )

                    observed_source = cap.get("source")
                    # Codex P2 (#137): 在记录边界 (拿到原始 UE 上报处) 把调制归一化到 canonical
                    # 一次 —— observed payload + mismatch.observed 都用它, GUI「采纳实测值」PUT
                    # 回 DUTProfile 时发的就是后端接受的 '64QAM' (而非上报的 'QAM64' 被 400 拒)。
                    obs_mod_dl = canonical_modulation(cap.get("max_modulation_dl"))
                    obs_mod_ul = canonical_modulation(cap.get("max_modulation_ul"))
                    mismatch = check_dut_capability_mismatch(
                        declared_max_dl_layers=dut_profile.max_dl_layers,
                        declared_max_ul_layers=dut_profile.max_ul_layers,
                        declared_max_modulation_dl=dut_profile.max_modulation_dl,
                        declared_max_modulation_ul=dut_profile.max_modulation_ul,
                        observed_max_dl_layers=cap.get("max_dl_layers"),
                        observed_max_ul_layers=cap.get("max_ul_layers"),
                        observed_max_modulation_dl=obs_mod_dl,
                        observed_max_modulation_ul=obs_mod_ul,
                        observed_available=(observed_source == "real_ue"),
                    )
                    # observed 单独记录 (含 dut_profile_id 供 GUI 反写定位); 永不写回声明。
                    # 调制用 canonical (供采纳反写); 层数原值。
                    result_payload["dut_capability_observed"] = {
                        "dut_profile_id": str(dut_profile.id),
                        "dut_profile_name": dut_profile.name,
                        "source": observed_source,
                        "max_dl_layers": cap.get("max_dl_layers"),
                        "max_ul_layers": cap.get("max_ul_layers"),
                        "max_modulation_dl": obs_mod_dl,
                        "max_modulation_ul": obs_mod_ul,
                    }
                    result_payload["dut_capability_mismatch"] = mismatch.to_payload()
                    if mismatch.mismatches:
                        warnings.append(
                            f"DUT '{dut_profile.name}' 声明 vs 实测协商不一致 (audit, 不影响 "
                            f"pass; 可在 DUT 声明页采纳实测值): " + (mismatch.failure_reason() or "")
                        )
                        messages.append(
                            f"DUT 能力交叉核对: 声明 vs 实测协商有 "
                            f"{len(mismatch.mismatches)} 处不一致 (见 dut_capability_mismatch)"
                        )
                    elif not mismatch.skipped:
                        messages.append(
                            f"DUT 能力交叉核对: '{dut_profile.name}' 声明跟实测协商一致"
                        )
            except Exception as e:  # noqa: BLE001
                warnings.append(f"UE capability query raised: {e}; skipped")
                live_ue_query_state = "unknown"
        result_payload["ue_capability_pass"] = ue_cap_pass
        result_payload["live_ue_query_state"] = live_ue_query_state

        # --- 2.6 Channel emulator user alignment (PROPSIM F64 §17) ---
        # F64 user alignment 补偿内部通道相位/增益的时间&温度漂移. 重启后
        # 必须 SYST:CALIB:USER:SET 重新激活 — connect() 已经做过, 这里只
        # 上报状态供操作员判断当天 alignment 数据是否新鲜. 不在 alignment
        # 状态上 hard-fail: 这是 OPTIONAL license, 多数现场不一定激活.
        ce = hal.drivers.get("channelEmulator")
        ce_is_real = ce is not None and not is_mock_driver(ce)
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
                # P2-10 Step 3: alignment 新鲜度 (标定数据该不该重标)。注释 159 说"供操作员
                # 判断当天数据是否新鲜" —— 这里把判断从人工眼看升级成 info 时间戳解析 + 阈值。
                if hasattr(ce, "alignment_freshness"):
                    from datetime import date
                    fresh = ce.alignment_freshness(
                        alignment.get("info"), today=date.today()
                    )
                    result_payload["channel_emulator_alignment_freshness"] = fresh
                    if fresh["freshness"] == "stale":
                        warnings.append(
                            f"CE user alignment STALE: 标定于 {fresh['calibrated_date']} "
                            f"({fresh['age_days']} 天前 > {fresh['max_age_days']} 天阈值), "
                            f"建议重标 (温度/时间漂移补偿已可能失效)"
                        )
                    elif fresh["freshness"] == "fresh":
                        messages.append(
                            f"CE alignment 新鲜 (标定 {fresh['age_days']} 天前, "
                            f"阈值 {fresh['max_age_days']} 天)"
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
        # P2-11 Phase 3 (Codex on PR #111): 按 TestCase switch_mode_id 过滤, 否则 cal
        # gate 会拿别的 operating mode 的 cert 通过 precheck, 但 measure 用对的 mode 查
        # 不到 → precheck 通过却 measure 静默退兜底 (P1-8 要防的正是这种 gate↔measure 漂移)。
        latest_pl = pl_service.get_latest_calibration(
            chamber.id,
            target_freq_mhz,
            operating_mode=config.switch_mode_id,
            require_real=ce_is_real,
        )
        if latest_pl is None and ce_is_real:
            # 保留“不可信证书存在”的诊断事实；正式执行先从 real 白名单选，
            # 只有白名单为空才回读任意来源用于 fail-loud 原因，绝不应用其数值。
            latest_pl = pl_service.get_latest_calibration(
                chamber.id,
                target_freq_mhz,
                operating_mode=config.switch_mode_id,
            )

        result_payload["path_loss_calibration_target_frequency_mhz"] = target_freq_mhz
        if latest_pl is not None:
            age_h = (datetime.utcnow() - latest_pl.calibrated_at).total_seconds() / 3600.0
            path_loss_use_mock = latest_pl.use_mock
            result_payload["path_loss_calibration_valid"] = True
            result_payload["path_loss_calibration_age_hours"] = age_h
            result_payload["path_loss_calibration_frequency_mhz"] = latest_pl.frequency_mhz
            result_payload["path_loss_calibration_use_mock"] = path_loss_use_mock
            provenance_label = (
                "simulated" if path_loss_use_mock is True
                else "real" if path_loss_use_mock is False
                else "unknown"
            )
            messages.append(
                f"Path-loss calibration: VALID (age {age_h:.1f}h, "
                f"cert@{latest_pl.frequency_mhz:.0f} MHz matches target "
                f"{target_freq_mhz:.0f} MHz within ±5% window, "
                f"provenance={provenance_label})"
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
                    ProbePathLossCalibration.valid_until > datetime.utcnow(),
                )
                .first()
            )
            result_payload["path_loss_calibration_valid"] = False
            result_payload["path_loss_calibration_use_mock"] = None
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
            chamber_id=chamber.id,
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
        # P1-12 audit (2026-05-25): QZ qualification is the heart of the
        # software-defined quiet zone. When there's no real ProbePattern data we
        # fall back to a legacy 0.7 dB constant — that's NOT a measured QZ
        # qualification, so we must NOT report it as a clean PASS. We don't
        # fail-loud (local/mock rehearsal has no pattern data and must still
        # run); instead the result is explicitly flagged "未验证(兜底值)" in the
        # precheck payload + message + downstream report/GUI, so an operator can
        # never mistake a fallback for a real measured QZ.
        qz_verified = result_payload["quiet_zone_ripple_source"] != "fallback_default"
        result_payload["quiet_zone_verified"] = qz_verified
        if qz_verified:
            messages.append(
                f"Quiet zone ripple: ±{ripple_db:.1f} dB "
                f"({'PASS' if qz_pass else 'FAIL'}, threshold ±{criteria.max_quiet_zone_ripple_db:.1f}) "
                f"[{result_payload['quiet_zone_ripple_source']}]"
            )
        else:
            # P1-48 (外审): 这条消息会被 report.py 渲染进正式报告的「提示」栏，
            # 所以**绝不能带兜底数字** —— 上一轮只把 quiet_zone_ripple_db 字段
            # 置空是不够的，同一个 0.7 从这条文案里照样印进 PDF。
            # 阈值 (max_quiet_zone_ripple_db) 是配置里的真值，可以印；
            # ripple_db 是兜底默认值，只进日志不进报告。
            logger.info(
                "[%s] 静区均匀度未验证，兜底波纹值 ±%.1f dB（仅日志，不进报告）",
                context.test_execution.id, ripple_db,
            )
            messages.append(
                "⚠️ 静区均匀度未验证: 无 ProbePattern 实测数据, 波纹值不可用 "
                f"(阈值 ±{criteria.max_quiet_zone_ripple_db:.1f} dB; 非实测合格) "
                "[fallback_default]"
            )

        # --- 5. Calibration gate (P1-8, 2026-05-19) ---
        # 默认 strict: path_loss_cal 必有 + cal_cert 若存在则 overall_pass=True;
        # 显式 opt-out (config.precheck_strict_cal=False) 跳过 gate 维持 audit-only 行为.
        #
        # Runtime mock-awareness (Codex on PR #75): the gate is evaluated against
        # LIVE HAL here, not a flag frozen at session-create. A mock/absent
        # channelEmulator means the measurement is simulated, so the cal gate is
        # moot → auto-N/A. Re-deriving live (rather than freezing at create)
        # closes the mock-create-then-switch-to-real bypass: a session built in
        # mock but RUN against real hardware still gets the strict gate.
        path_loss_valid = result_payload.get("path_loss_calibration_valid", False)
        path_loss_use_mock = result_payload.get("path_loss_calibration_use_mock")
        path_loss_provenance_untrusted = (
            path_loss_valid and path_loss_use_mock is not False
        )
        cal_cert_broken = cal_cert is not None and not cal_cert.overall_pass
        cal_cert_missing_only = cal_cert is None  # warning, not FAIL — see P1-8 design #1

        if config.precheck_strict_cal and ce_is_real:
            cal_pass = (
                path_loss_valid
                and (not path_loss_provenance_untrusted)
                and (not cal_cert_broken)
            )
            cal_pass_reason_parts: list[str] = []
            if not path_loss_valid:
                cal_pass_reason_parts.append(
                    "path-loss calibration missing or invalid "
                    "(no VALID ProbePathLossCalibration for this chamber)"
                )
            elif path_loss_use_mock is True:
                cal_pass_reason_parts.append(
                    "path-loss calibration has simulated provenance "
                    "(use_mock=True; real measurement requires use_mock=False)"
                )
            elif path_loss_use_mock is None:
                cal_pass_reason_parts.append(
                    "path-loss calibration provenance is unknown "
                    "(use_mock=NULL/legacy; real measurement requires explicit "
                    "use_mock=False)"
                )
            if cal_cert_broken:
                cal_pass_reason_parts.append(
                    f"calibration_certificate not passed "
                    f"(cert={cal_cert.certificate_number}, overall_pass=False)"
                )
            cal_pass_reason = "; ".join(cal_pass_reason_parts) if cal_pass_reason_parts else "ok"
        else:
            # Bypass: cal_pass forced True but audit trail tells you which
            # gate(s) would have failed under strict mode, and WHY the gate
            # was inactive (mock measurement vs operator opt-out).
            cal_pass = True
            bypass_parts: list[str] = []
            if not path_loss_valid:
                bypass_parts.append("path-loss calibration missing")
            elif path_loss_use_mock is True:
                bypass_parts.append(
                    "path-loss calibration simulated provenance (use_mock=True)"
                )
            elif path_loss_use_mock is None:
                bypass_parts.append(
                    "path-loss calibration unknown provenance (use_mock=NULL/legacy)"
                )
            if cal_cert_broken:
                bypass_parts.append("cal_cert.overall_pass=False")
            if cal_cert_missing_only:
                bypass_parts.append("cal_cert is None")
            bypass_suffix = f" (would-fail-under-strict: {', '.join(bypass_parts)})" if bypass_parts else ""
            if not ce_is_real:
                cal_pass_reason = (
                    f"gate N/A — channelEmulator is mock/absent (simulated "
                    f"measurement, calibration moot){bypass_suffix}"
                )
            else:
                cal_pass_reason = f"bypassed via precheck_strict_cal=False{bypass_suffix}"

        result_payload["cal_pass"] = cal_pass
        result_payload["cal_pass_reason"] = cal_pass_reason

        # --- 5b. DUT attach gate (P1-9, 2026-05-19; Codex P2 on 655d7e3) ---
        # 默认 strict: dut_attach 必须存在 + rrc_connected == True + live BS
        # query 必须 confirm "available" (cached snapshot 可能 stale: DUT 在
        # attach 跟 precheck 之间掉线 / RRC re-establishment 失败 / UE 死机).
        # 显式 opt-out (config.precheck_strict_dut=False) 跳过 gate, 维持
        # 旧的 "warning only" 行为. dut_attach 在 section 2.4 已经写进
        # result_payload (when present); live_ue_query_state 在 section 2.5
        # 通过 bs.query_ue_capability() 实时获取.
        dut_attach_missing = dut_attach is None or not dut_attach
        dut_rrc_state = (
            dut_attach.get("rrc_connected") if isinstance(dut_attach, dict) else None
        )
        dut_rrc_broken = (not dut_attach_missing) and (dut_rrc_state is not True)
        # live verification: cached snapshot 单独不够, 因为 attach 到 precheck
        # 之间 DUT 可能掉线. 但 mock BS 永远返回 source="mock" (available),
        # 所以 mock smoke 自然 pass; 真生产 (UXM) 时 RRC 掉线 query 会返回
        # source="unavailable", 这里 catch.
        live_unverified = live_ue_query_state != "available"

        # Runtime mock-awareness (Codex on PR #75): a real DUT can only attach
        # to a real baseStation. A mock/absent BS ⇒ no real DUT possible ⇒ the
        # DUT gate is moot → auto-N/A. Evaluated against LIVE HAL (not a flag
        # frozen at session-create), so a mock-created session RUN on real
        # hardware still gets the strict gate — no silent P1-9 bypass.
        bs_is_real = bs is not None and not is_mock_driver(bs)

        if managed_rf_attach:
            # 标准吞吐量执行的动态门必须落在本次 RF 配置真正生效、UE attach
            # 之后。这里不是绕过：MEASURE 会消费同一个 strict 配置并 fail-loud。
            dut_pass = True
            dut_pass_reason = (
                "deferred to MEASURE after TestCase-driven RF initialization "
                "and controlled UE attach"
            )
            result_payload["dut_gate_deferred"] = True
        elif config.precheck_strict_dut and bs_is_real:
            dut_pass = (
                (not dut_attach_missing)
                and (not dut_rrc_broken)
                and (not live_unverified)
            )
            dut_reason_parts: list[str] = []
            if dut_attach_missing:
                dut_reason_parts.append(
                    "DUT attach record missing "
                    "(用暗室首测面板的「登记 DUT」按钮登记 IMSI; 等价端点 "
                    "POST /api/v1/test-executions/{id}/attach-dut)"
                )
            if dut_rrc_broken:
                dut_reason_parts.append(
                    f"DUT attached but rrc_connected={dut_rrc_state!r} "
                    "(expected True — measure phase needs RRC for PDSCH)"
                )
            if live_unverified and not dut_attach_missing:
                # Only call out live failure when there's an attach record
                # claiming connected; otherwise the "missing" message above
                # already covers it.
                dut_reason_parts.append(
                    f"live BS query state={live_ue_query_state!r} "
                    "(cached rrc_connected snapshot may be stale — "
                    "DUT may have dropped between attach and precheck)"
                )
            dut_pass_reason = "; ".join(dut_reason_parts) if dut_reason_parts else "ok"
        else:
            dut_pass = True
            bypass_parts: list[str] = []
            if dut_attach_missing:
                bypass_parts.append("dut_attach missing")
            if dut_rrc_broken:
                bypass_parts.append(f"rrc_connected={dut_rrc_state!r}")
            if live_unverified:
                bypass_parts.append(f"live_ue_query_state={live_ue_query_state!r}")
            bypass_suffix = (
                f" (would-fail-under-strict: {', '.join(bypass_parts)})"
                if bypass_parts else ""
            )
            if not bs_is_real:
                dut_pass_reason = (
                    f"gate N/A — baseStation is mock/absent (no real DUT can "
                    f"attach){bypass_suffix}"
                )
            else:
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
