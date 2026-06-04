"""Phase 3: Static MIMO throughput measurement (the core of MIMO OTA).

Replaces commissioning_service.phase3_static_mimo_test. The flow:

1. Set base station cell config + 3GPP MAC throughput parameters from the
   bound TestCase.configuration (no longer hard-coded in the service).
2. Generate the CDL channel via ChannelEngineClient and load it into the
   channel emulator (ASC or GCM strategy depending on engine_mode).
3. Walk the turntable through each azimuth in config.azimuths_deg, sample
   throughput from the base station + simulate RSRP/SINR (since the BS does
   not currently report those), and aggregate per-azimuth statistics.

LabProfile contributes the chamber row (calibration entries, geometry).
TestCase.calibration_certificate_id (optional) is referenced for traceability;
the actual per-probe path-loss data still comes from chamber-keyed
ProbePathLossCalibration rows.

── 路径 A/B 边界 (P2-11 Phase 5 固化) ──────────────────────────────────────
本 executor 是**路径 B (正式测试) 的核心**: 仪表关键参数全由 TestCase
(MIMOOTAConfiguration) 单一真值源驱动, **不读 HAL-init 默认** —— UXM
set_cell_config(arfcn=freq→ARFCN) / F64 emulation_file(GCM)+ engine 频率 /
switch orchestrate(switch_mode_id)/ 路损 cert(operating_mode 过滤)/ SA /
positioner 全 TestCase 派生, 下发后多方频率一致性 + GCM .smu + switch mode 三道
fail-loud 门挡静默错配 (Phase 1/2/3)。路径 A (bring-up 默认: P0-8 F64 .smu /
P1-17 UXM profile) 主要在 HAL-init 用 —— F64 .smu 这里由 emulation_file 覆盖,
**但 UXM 默认 profile 的 port routing / TDD / scheduler 等字段 set_cell_config
没覆盖 → 会残留进本 path B** (Codex on PR #112; roadmap "Discovered" backlog,
待补成 TestCase 驱动或显式 reset)。边界总览见
docs/architecture/testcase-driven-instrument-config.md §2/§6/§6.1。
"""
import asyncio
import logging
import math
import random
from typing import Any, Dict, List

from app.models.chamber import ChamberConfiguration
from app.services.mimo_ota.executors._helpers import (
    load_mimo_ota_config,
    stddev,
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

# Phase 2d: each "sample" is now an independent UXM stat window (≈ stat_count
# subframes ≈ stat_count ms), not a 20ms poll. Production wants ≥ 5-12 windows
# per azimuth for stable std; dev caps at 3 to keep smoke tests fast.
_DEV_SAMPLE_WINDOWS = 3
# Floor for window duration so mock paths still take a perceptible amount of
# time (helps surface ordering bugs) but don't actually wait 5s in unit tests.
_MOCK_WINDOW_FLOOR_S = 0.05

# Phase 2m: DUT 掉线检测周期 (每 N 个 azimuth 检查一次而非每窗口, 节省 SCPI 流量)
# 单 azimuth 内不检查 (统计窗口本身已 >= 50ms, 中途掉线被 measure_throughput_window
# 内部 retry 兜底). azimuth 间隔检查能在转台移动期间发现, 是最佳折衷.
_DUT_HEALTH_CHECK_EVERY_N_AZIMUTHS = 1


@register_executor(MIMOOTAStepType.MEASURE.value)
class MeasureExecutor(IStepExecutor):
    """Drive the chamber + base station through the azimuth grid, collect KPIs."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        lab = context.require_lab_profile()
        config = load_mimo_ota_config(context.test_execution)

        from app.services.channel_engine_client import ChannelEngineClient
        from app.services.channel_generation.asc_strategy import (
            ExternalWaveformStrategy,
        )
        from app.services.channel_generation.base_generator import EngineMode
        from app.services.channel_generation.external_asc_strategy import (
            ExternalAscPathStrategy,
        )
        from app.services.channel_generation.gcm_strategy import NativeModelStrategy
        from app.services.instrument_hal_service import get_hal_service, is_mock_driver
        from app.services.mimo_ota.cleanup import cleanup_chamber_instruments
        from app.services.mimo_ota.emulation_file_gate import (
            evaluate_emulation_file_gate,
        )
        from app.services.mimo_ota.switch_mode_gate import (
            evaluate_switch_mode_gate,
        )
        from app.services.mimo_ota.switch_orchestrator import (
            orchestrate_switch_topology,
        )
        from app.services.probe_pattern.consumer import (
            get_probe_gain_at_azimuth,
            select_active_probe_id,
        )
        from app.hal.channel_emulator import ChannelLoadMode
        from app.hal.nr_arfcn import freq_mhz_to_nr_arfcn

        hal = get_hal_service()
        positioner = hal.drivers.get("positioner")
        base_station = hal.drivers.get("baseStation")
        if positioner is None or base_station is None:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message="positioner + baseStation drivers required (HAL)",
            )

        await positioner.connect()
        await base_station.connect()
        # Anything from here through the azimuth loop must be wrapped so an
        # exception (HAL hiccup, channel-gen timeout, DUT drop) doesn't leave
        # UXM signaling, F64 emulating, and the turntable mid-rotation.
        cleanup_warnings: List[str] = []
        try:
            # --- Phase 2g: PCell from component_carriers[0] (always populated
            # by MIMOOTAConfiguration._resolve_component_carriers); SCells
            # added below before start_signaling so RRC reconfig sees full set.
            ccs = list(config.component_carriers or [])
            pcell = ccs[0] if ccs else None
            if pcell is None:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=(
                        "component_carriers is empty after schema validation — "
                        "this should be impossible; check MIMOOTAConfiguration validator"
                    ),
                )
            scells = ccs[1:]

            # P2-11 (Codex on PR #109 P1): 从 TestCase 中心频推导规范 ARFCN 显式下发。
            # 不传 arfcn 时 RealUxmDriver.set_cell_config fallback 到 NR_BAND_ARFCN_MAP
            # [band] (N78→632628=3489.42 MHz), 让 UXM 实际下发频率 ≠ TestCase, 下面的
            # 频率一致性校验会正确判失败 → 任何 TestCase 频率 ≠ band fallback 的真实
            # run 都被误杀。ARFCN 是频率真值 (frequency_mhz 只是派生视图), 必须显式驱动。
            pcell_freq_mhz = pcell.frequency_hz / 1e6
            await base_station.set_cell_config(
                {
                    "frequency_mhz": pcell_freq_mhz,
                    "arfcn": freq_mhz_to_nr_arfcn(pcell_freq_mhz),
                    "bandwidth_mhz": pcell.bandwidth_mhz,
                    "scs_khz": pcell.subcarrier_spacing_khz,
                    "band": pcell.band,
                    "mimo_layers": config.mimo_layers,
                    "dl_power_dbm": config.target_tx_power_dbm,
                }
            )

            # --- Phase 2g: SCell add + activate for CA scenarios ---
            scells_added: List[Dict[str, Any]] = []
            if scells and hasattr(base_station, "add_secondary_cell"):
                for cc_idx, scell in enumerate(scells, start=1):
                    # SCell 走 SCELL_CONF_FREQ 直接按 frequency_mhz 程控 (无 ARFCN
                    # band fallback, 见 add_secondary_cell) → 没有 PCell 那个坑, 不需
                    # 显式 arfcn。频率一致性校验也只比 PCell。
                    ok = await base_station.add_secondary_cell(
                        cc_idx,
                        {
                            "frequency_mhz": scell.frequency_hz / 1e6,
                            "bandwidth_mhz": scell.bandwidth_mhz,
                            "scs_khz": scell.subcarrier_spacing_khz,
                            "band": scell.band,
                        },
                    )
                    if ok:
                        scells_added.append({
                            "cc_index": cc_idx,
                            "frequency_ghz": scell.frequency_hz / 1e9,
                            "bandwidth_mhz": scell.bandwidth_mhz,
                            "band": scell.band,
                        })
                    else:
                        logger.warning(
                            "[%s] SCell %d add failed; CA may run with fewer carriers than requested",
                            context.test_execution.id, cc_idx,
                        )
                if scells_added and hasattr(base_station, "activate_secondary_cells"):
                    await base_station.activate_secondary_cells()
                logger.info(
                    "[%s] Phase 2g: PCell %.2fGHz + %d SCell(s)",
                    context.test_execution.id,
                    pcell.frequency_hz / 1e9, len(scells_added),
                )
            elif scells:
                logger.warning(
                    "[%s] Config has %d SCell(s) but baseStation driver lacks "
                    "add_secondary_cell — running PCell-only",
                    context.test_execution.id, len(scells),
                )

            # --- 3GPP MAC throughput config (was hard-coded; now from TestCase) ---
            if hasattr(base_station, "configure_mac_throughput_test"):
                await base_station.configure_mac_throughput_test(
                    mimo_layers=config.mimo_layers,
                    mcs=config.mcs,
                    enable_amc=config.enable_amc,
                    tdd_pattern=config.tdd_pattern,
                    tdd_period=config.tdd_period,
                    harq_max_trans=config.harq_max_trans,
                    harq_processes=config.harq_processes,
                    stat_count=config.stat_count,
                )

            await base_station.start_signaling()

            # --- Phase 2e: RRC reconfig pushes new layer/modulation to attached UE.
            # Some UXM firmware applies cell-config changes via RRC automatically;
            # explicit reconfig is a no-op there but harmless. Old firmware needs it.
            if hasattr(base_station, "reconfigure_rrc"):
                rrc_ok = await base_station.reconfigure_rrc(
                    mimo_layers=config.mimo_layers,
                    modulation=config.modulation,
                )
                if not rrc_ok:
                    logger.warning(
                        "[%s] RRC reconfig returned False; UE may still be on prior layer/modulation",
                        context.test_execution.id,
                    )

            # --- Resolve chamber from LabProfile, then run channel generation ---
            chamber: ChamberConfiguration = lab.chamber_config
            if chamber is None:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=f"LabProfile {lab.name} has no chamber_config",
                )

            ce_client = ChannelEngineClient(context.db)
            emulator = hal.drivers.get("channelEmulator")
            if emulator is None:
                from app.hal.channel_emulator import MockChannelEmulator

                logger.warning(
                    "[%s] No channelEmulator in HAL — falling back to MockChannelEmulator",
                    context.test_execution.id,
                )
                emulator = MockChannelEmulator(
                    instrument_id="mock_ce_mimo_ota",
                    config={"model": "Mock"},
                )
                await emulator.connect()

            # --- Phase 2c: resolve TestCase-driven switch mode for this chamber ---
            # P2-11 Phase 3: mode_id 由 TestCase.switch_mode_id 驱动 (chamber active
            # SwitchTopology + TestCase 选哪个 operating mode), 不再硬编码 "mimo_ota"。
            # CAICT 固定布线时这是 *declaration check* 非 live switching: surface
            # topology id/mode/CE→probe 绑定供下游 channel-gen 消费。无 active topology
            # row = warning (固定布线手工接线, 见下面门放行); 有 topology 但请求 mode
            # 不提供 = strict FAIL (switch_mode_gate)。
            topology_result = orchestrate_switch_topology(
                context.db, chamber.id, mode_id=config.switch_mode_id
            )
            if topology_result.success:
                logger.info(
                    "[%s] Phase 2c: switch topology '%s' v%s mode=%s, %d probe bindings",
                    context.test_execution.id,
                    topology_result.topology_name,
                    topology_result.topology_version,
                    topology_result.mode_id,
                    len(topology_result.probe_bindings),
                )
            else:
                for w in topology_result.warnings:
                    logger.warning("[%s] %s", context.test_execution.id, w)
            # P2-11 Phase 3 门: 有 active topology 但 TestCase 请求的 mode 未解析 →
            # strict FAIL (无 topology row 时放行 —— 固定布线 orchestrator 已 warn)。
            switch_gate = evaluate_switch_mode_gate(
                topology_present=topology_result.topology_id is not None,
                mode_resolved=topology_result.success,
                requested_mode_id=config.switch_mode_id,
                strict=config.precheck_strict_switch_mode,
            )
            if switch_gate.should_fail:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=switch_gate.message,
                )
            if switch_gate.should_warn:
                logger.warning(
                    "[%s] %s", context.test_execution.id, switch_gate.message
                )

            # P2-11 Phase 3 (Codex on PR #111): 校准 cert 按 TestCase 的 switch
            # operating mode 过滤 —— 否则多 mode 同频校准的 lab 会喂错 RF 通路的损耗。
            calibration_entries = ce_client._query_calibration_entries(
                chamber.id, config.frequency_hz, chamber,
                operating_mode=config.switch_mode_id,
            )

            # --- Phase 2a / P0: path-loss compensation ---
            # Old: chamber-wide avg (`avg_path_loss_db`) applied uniformly.
            # New: per-RFChain `total_insertion_loss_db` looked up by
            #   (active_probe_id, polarization) → connection_id, populated
            #   when the cert was created via /calibration/path-loss/start-for-lab.
            # Falls back to avg when the cert is legacy (no per-chain map) so
            # existing chamber-keyed calibrations still work.
            from app.services.path_loss_calibration_service import (
                ProbePathLossCalibrationService,
            )

            pl_service = ProbePathLossCalibrationService(context.db, use_mock=False)
            # P2-11 Phase 3 (Codex on PR #111): 按 TestCase switch_mode_id 过滤 cert,
            # 让 per-chain 线损来自请求的 RF 通路 (精确优先, 退回 legacy NULL)。
            path_loss_cert = pl_service.get_latest_calibration(
                chamber.id, config.frequency_hz / 1e6,
                operating_mode=config.switch_mode_id,
            )
            if path_loss_cert is not None:
                avg_path_loss_db = float(path_loss_cert.avg_path_loss_db or 0.0)
                per_chain_pl: Dict[str, Any] = (
                    getattr(path_loss_cert, "path_loss_db_by_rf_chain", None) or {}
                )
                logger.info(
                    "[%s] Phase 2a/P0: path-loss avg=%.2f dB cert=%s mode=%s "
                    "(req=%s, per-chain entries: %d)",
                    context.test_execution.id,
                    avg_path_loss_db, path_loss_cert.id,
                    getattr(path_loss_cert, "operating_mode", None),
                    config.switch_mode_id, len(per_chain_pl),
                )
            else:
                avg_path_loss_db = 0.0
                per_chain_pl = {}
                logger.warning(
                    "[%s] Phase 2a: no path-loss calibration for chamber %s @ %.0f MHz; "
                    "RSRP baseline uncompensated",
                    context.test_execution.id,
                    chamber.id,
                    config.frequency_hz / 1e6,
                )

            # P0: invert per_chain_pl into a (probe_id, pol) → total_insertion_loss_db map.
            # Each entry already has probe_id + polarization stamped at calibration
            # time, so we don't have to re-resolve the topology here — saving a
            # query and keeping the compensation pinned to whatever topology was
            # active when the cert was issued.
            chain_pl_by_probe_pol: Dict[tuple, float] = {}
            for entry in per_chain_pl.values():
                if not isinstance(entry, dict):
                    continue
                pid = entry.get("probe_id")
                pol = entry.get("polarization")
                total = entry.get("total_insertion_loss_db")
                if pid is not None and pol and total is not None:
                    chain_pl_by_probe_pol[(int(pid), str(pol).upper())] = float(total)

            # P2-12 slice 4: scd_id 引用优先于裸 emulation_file。但 SCD/.smu **只 GCM 相关**
            # (ASC 按 frequency 生成 .asc 不用 .smu)。这里给 ASC / 非 GCM 路径的默认值: 裸
            # emulation_file (ASC strategy 忽略它) + 无 SCD 频率 (不进一致性网)。SCD 解析只在
            # 下方 GCM 分支做 —— Codex on #122: 在 GCM 选了 SCD 再切 ASC 时 config 残留 scd_id,
            # 不该让 ASC run 去 resolve (SCD 删了/非法会误 fail) 或撞 SCD 频率门 (ASC 不用 SCD)。
            resolved_emulation_file = config.emulation_file
            scd_freq_identity = None

            engine_mode = EngineMode(config.engine_mode)
            if engine_mode == EngineMode.GCM_NATIVE:
                supported = emulator.get_supported_load_modes()
                if ChannelLoadMode.NATIVE_MODEL not in supported:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            f"channelEmulator ({type(emulator).__name__}) does not support "
                            f"native model loading; engine_mode=GCM_NATIVE rejected. "
                            f"Supported modes: {[m.value for m in supported]}"
                        ),
                    )
                generator = NativeModelStrategy(emulator, chamber, calibration_entries)
                # P2-12 slice 4: 只在 GCM 分支 resolve scd_id → SCD (associated .smu + 声明
                # ARFCN 喂下方频率门)。ASC config 残留的 scd_id 在此不触发 (Codex on #122)。
                from app.services.standard_channel_service import (
                    StandardChannelError,
                    resolve_emulation_for_measure,
                )
                try:
                    resolved_emulation_file, scd_freq_identity = resolve_emulation_for_measure(
                        context.db,
                        scd_id=config.scd_id,
                        fallback_emulation_file=config.emulation_file,
                    )
                except (StandardChannelError, ValueError) as e:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=f"P2-12 slice 4: scd_id={config.scd_id} 无效/不存在: {e}",
                    )
                # P2-11 Phase 2: GCM 的 .smu 必须由 TestCase 驱动 (路径 B), 不能静默
                # fallback 到 F64 驱动默认 .smu —— 默认频率可能跟 TestCase 错配。strict
                # 默认 FAIL; opt-out (bring-up 路径 A) 降级 warning 用驱动默认。下面
                # sim_rules 透传 emulation_file 给 F64。门只对**真 F64** 生效 (mock-aware,
                # 读 LIVE HAL, 同 precheck cal/dut 门 Codex on PR #75); 决策见
                # emulation_file_gate.evaluate_emulation_file_gate。
                # P2-12 (Codex #120 后端另一半): 同一道门还校验 resolved_emulation_file
                # 扩展非 .smu (.rtc/.asc) → strict FAIL, 抓 API 直传 / 绕过前端 #120
                # filter 的非 GCM 原生文件 (覆盖 scd_id 解析 + 裸路径两路)。
                emulation_gate = evaluate_emulation_file_gate(
                    emulator_is_real=(
                        emulator is not None and not is_mock_driver(emulator)
                    ),
                    emulation_file=resolved_emulation_file,
                    strict=config.precheck_strict_emulation_file,
                )
                if emulation_gate.should_fail:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=emulation_gate.message,
                    )
                if emulation_gate.should_warn:
                    logger.warning(
                        "[%s] %s", context.test_execution.id, emulation_gate.message
                    )
            elif engine_mode == EngineMode.EXTERNAL_ASC:
                # 2026-05-18 P0-7: operator-supplied .asc directory; skip
                # channel-engine-service entirely. Schema already validated
                # asc_source_path is set; path-exists check happens in
                # ExternalAscPathStrategy.generate_and_load so failures land
                # with the same logging context as other generator failures.
                generator = ExternalAscPathStrategy(
                    emulator,
                    chamber,
                    calibration_entries,
                    asc_source_path=config.asc_source_path,
                )
            else:
                generator = ExternalWaveformStrategy(
                    emulator, ce_client, chamber, calibration_entries
                )

            sim_rules = {
                "frequency_hz": config.frequency_hz,
                "target_tx_power_dbm": config.target_tx_power_dbm,
                "target_rsrp_dbm": config.target_rsrp_dbm,
                "target_snr_db": config.target_snr_db,
            }
            # P2-11 Phase 2: TestCase 显式指定 .smu → 透传给 F64 GCM
            # (NativeModelStrategy → load_channel parameters["emulation_file"],
            # propsim_f64 line 745 优先于驱动默认; 加载失败 P0-8 gate fail-loud)。
            # slice 4: resolved = SCD 解析的 .smu (scd_id 优先) 或裸 emulation_file (legacy)
            if resolved_emulation_file:
                sim_rules["emulation_file"] = resolved_emulation_file
            cdl_model_data = {
                "model_name": config.cdl_model_name,
                "session_id": str(context.test_execution.id),
            }
            gen_ok = await generator.generate_and_load(sim_rules, cdl_model_data)
            if not gen_ok:
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    error_message=f"Channel generation failed for engine_mode={config.engine_mode}",
                )

            # --- P2-11 Phase 1: 多方频率一致性 fail-loud 校验 ---
            # UXM (set_cell_config 后, _arfcn 已设) + F64 (信道加载后) 都已配置; 把各
            # 仪表归一到 (中心 ARFCN, 带宽) 跟 TestCase 精确比对。不一致 = 静默错配
            # (GCM 模式 F64 默认 .smu 3600 但 TestCase 3500, 或 UXM 没传 arfcn → 实际
            # 下发 632628=3489 ≠ 标称), strict 模式 FAIL。频率错了下面 input level /
            # RSRP / 吞吐都不可信, 所以放在 Phase 2b input level 之前。
            from app.hal.nr_arfcn import FrequencyIdentity
            from app.services.mimo_ota.frequency_consistency import (
                check_frequency_consistency,
            )
            freq_result = check_frequency_consistency(
                FrequencyIdentity.from_center_freq_mhz(
                    pcell.frequency_hz / 1e6, pcell.bandwidth_mhz
                ),
                {
                    "UXM": base_station.get_frequency_identity()
                    if hasattr(base_station, "get_frequency_identity") else None,
                    "F64": emulator.get_frequency_identity()
                    if hasattr(emulator, "get_frequency_identity") else None,
                    # slice 4: SCD 声明 ARFCN 进一致性网 (scd_id 给了才非 None; None 时忽略)
                    "SCD": scd_freq_identity,
                },
            )
            if not freq_result.consistent:
                if config.precheck_strict_frequency:
                    return StepExecutionResult(
                        status=StepExecutionStatus.FAILED,
                        error_message=(
                            "P2-11 频率一致性校验失败: "
                            + (freq_result.failure_reason() or "")
                        ),
                        measurements={"frequency_consistency": freq_result.to_payload()},
                    )
                logger.warning(
                    "[%s] P2-11 频率不一致 (precheck_strict_frequency=False, 继续): %s",
                    context.test_execution.id, freq_result.failure_reason(),
                )

            # --- P2-11 Phase 6: UXM cell config 下发后一致性 (吞吐链版频率校验) ---
            # set_cell_config + RRC reconfig 后, 拿 **UE 协商能力** (max_dl_layers) 跟
            # TestCase 请求层数比 —— 请求 4 层但 UE 只支持 2 → UXM 静默 clamp, 吞吐其实
            # 2 层却当 4 层测 (跟频率错配同等危害)。Codex on PR #114: 读 UE 能力而非
            # CONF:...:LAY? 配置旋钮 (后者回读只原样返回配置值, 抓不到 clamp)。UE 未
            # attach / firmware 不支持 (mock / dry-run) → skipped 跳过 (同 Phase 1)。
            if hasattr(base_station, "get_applied_cell_config"):
                from app.services.mimo_ota.cell_config_consistency import (
                    check_cell_config_consistency,
                )
                cc_result = check_cell_config_consistency(
                    requested_mimo_layers=config.mimo_layers,
                    applied=await base_station.get_applied_cell_config(),
                )
                if not cc_result.consistent:
                    if config.precheck_strict_cell_config:
                        return StepExecutionResult(
                            status=StepExecutionStatus.FAILED,
                            error_message=(
                                "P2-11 Phase 6 cell config 一致性校验失败: "
                                + (cc_result.failure_reason() or "")
                            ),
                            measurements={
                                "cell_config_consistency": cc_result.to_payload()
                            },
                        )
                    logger.warning(
                        "[%s] P2-11 Phase 6 cell config 不一致 "
                        "(precheck_strict_cell_config=False, 继续): %s",
                        context.test_execution.id, cc_result.failure_reason(),
                    )

            # --- P0-8 Step 2 Phase 2b: F64 输入操作点闭环 (CE↔BS) ---
            # F64 fading 已经载入、UXM DL 已开 → 此时 F64 输入端信号即真实工作条件,
            # 跑 §4 A-F 闭环锁住 avg+crest 在窗口内、clipping 不爆、无 cut-off。
            # capability 检测 (hasattr) 跟项目 pattern 一致 (get_user_alignment_status /
            # reconfigure_rrc / add_secondary_cell) — 任一方缺接口 (mock driver /
            # 新 vendor 未实现) 自动跳, 不影响 mock dry-run。
            # 设计依据: docs/architecture/f64-input-level-and-dynamic-range.md §4.
            input_level_payload = await self._run_input_level_closed_loop(
                emulator=emulator,
                base_station=base_station,
                config=config,
                execution_id=context.test_execution.id,
            )
            if (
                not input_level_payload.get("skipped")
                and not input_level_payload.get("success")
                and config.precheck_strict_input_level
            ):
                # strict 模式: 操作点未确定 → 后续 RSRP/吞吐都是 garbage, fail-loud。
                # finally 块仍会做 cleanup (UXM stop / F64 stop / 转台 home)。
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    measurements={"input_level_calibration": input_level_payload},
                    error_message=(
                        f"Input-level closed loop did not converge: "
                        f"{input_level_payload.get('failure_reason')}. "
                        "操作点未确定 → 跳过 azimuth 测量 (后续 RSRP/吞吐失去物理意义)。"
                        " 现场调试可临时设 precheck_strict_input_level=False 降级为 warning。"
                    ),
                )

            # --- Per-azimuth measurement loop (Phase 2d windowed sampling) ---
            azimuth_results: List[Dict[str, Any]] = []
            # P0: ce_base_rsrp is now per-azimuth (computed inside loop) since
            # path-loss varies by chain. avg_path_loss_db is the fallback.
            # One sample per stat window (≈ stat_count subframes × 1ms);
            # cap aggressively in dev so smoke tests don't wait minutes.
            num_windows = min(config.num_samples_per_azimuth, _DEV_SAMPLE_WINDOWS)
            window_s = max(config.stat_count / 1000.0, _MOCK_WINDOW_FLOOR_S)

            loop = asyncio.get_event_loop()
            t_start = loop.time()

            # Phase 2f / P0: pre-resolve per-azimuth probe + pattern gain +
            # per-chain path-loss so the inner sample loop doesn't hammer the
            # DB. Chain lookup uses "V" by default — current measurement
            # synthesis is also V-pol; H-pol gets the same value (acceptable
            # until per-azimuth pol switching is wired).
            nominal_probe_gain_dbi = float(chamber.probe_gain_dbi or 0.0)
            azimuth_probe_gains: Dict[float, Dict[str, Any]] = {}
            for az_target in config.azimuths_deg:
                pid = select_active_probe_id(chamber.num_probes, az_target)
                pattern_gain_v = get_probe_gain_at_azimuth(
                    context.db, chamber.num_probes, az_target, config.frequency_hz / 1e6, "V"
                )
                chain_pl_db = chain_pl_by_probe_pol.get((pid, "V"))
                azimuth_probe_gains[az_target] = {
                    "probe_id": pid,
                    "pattern_gain_dbi": pattern_gain_v,
                    "gain_offset_db": (
                        pattern_gain_v - nominal_probe_gain_dbi
                        if pattern_gain_v is not None else None
                    ),
                    # Per-chain path-loss; None falls back to chamber avg in loop.
                    "path_loss_db": chain_pl_db,
                }
            patterns_used = sum(
                1 for v in azimuth_probe_gains.values() if v["pattern_gain_dbi"] is not None
            )
            chains_used = sum(
                1 for v in azimuth_probe_gains.values() if v["path_loss_db"] is not None
            )
            if chains_used:
                logger.info(
                    "[%s] P0: per-RFChain path-loss applied for %d/%d azimuths",
                    context.test_execution.id, chains_used, len(config.azimuths_deg),
                )
            elif per_chain_pl:
                logger.warning(
                    "[%s] P0: cert has %d chain entries but none matched any "
                    "azimuth's active probe (V) — falling back to avg path-loss",
                    context.test_execution.id, len(per_chain_pl),
                )
            if patterns_used == 0:
                logger.warning(
                    "[%s] Phase 2f: no ProbePattern data for any azimuth — RSRP/SINR "
                    "synthesis falls back to position-aware approximation",
                    context.test_execution.id,
                )
            else:
                logger.info(
                    "[%s] Phase 2f: ProbePattern available for %d/%d azimuths",
                    context.test_execution.id, patterns_used, len(config.azimuths_deg),
                )

            dut_disconnect_warnings: List[str] = []
            for az_idx, azimuth in enumerate(config.azimuths_deg):
                # --- Phase 2m: DUT health check before each azimuth ---
                if az_idx % _DUT_HEALTH_CHECK_EVERY_N_AZIMUTHS == 0 and hasattr(
                    base_station, "get_ue_info"
                ):
                    try:
                        ue_info = await base_station.get_ue_info()
                        if not ue_info.get("connected", True):
                            msg = (
                                f"DUT disconnected before azimuth {azimuth:.0f}° "
                                f"(az_idx={az_idx}/{len(config.azimuths_deg)}); "
                                "aborting measurement loop"
                            )
                            logger.error("[%s] %s", context.test_execution.id, msg)
                            dut_disconnect_warnings.append(msg)
                            break  # stop loop; finally cleans up
                    except Exception as e:  # noqa: BLE001
                        logger.debug(
                            "[%s] DUT health check skipped: %s",
                            context.test_execution.id, e,
                        )

                logger.info(
                    "[%s] Phase 3: positioner -> azimuth %.1f° (%d windows × %.2fs)",
                    context.test_execution.id,
                    azimuth,
                    num_windows,
                    window_s,
                )
                await positioner.move_to(azimuth, 0.0)
                await asyncio.sleep(config.settling_time_s)

                samples_rsrp: List[float] = []
                samples_sinr: List[float] = []
                samples_tput: List[float] = []
                samples_ri: List[float] = []

                az_meta = azimuth_probe_gains.get(azimuth, {})
                gain_offset = az_meta.get("gain_offset_db")
                # P0: per-chain path-loss when available; falls back to avg.
                az_path_loss_db = az_meta.get("path_loss_db")
                if az_path_loss_db is None:
                    az_path_loss_db = avg_path_loss_db
                ce_base_rsrp = config.target_rsrp_dbm - az_path_loss_db

                for _ in range(num_windows):
                    metrics = await base_station.measure_throughput_window(window_s)

                    # RF KPIs (RSRP/SINR) are normally UE-reported; until that
                    # path exists we synthesize from target + per-probe pattern
                    # offset (Phase 2f) when available, falling back to a coarse
                    # cos(az) approximation when no pattern is loaded.
                    if gain_offset is not None:
                        rsrp = ce_base_rsrp + gain_offset + random.gauss(0, 0.3)
                        sinr = config.target_snr_db + gain_offset * 0.5 + random.gauss(0, 0.5)
                    else:
                        az_factor = math.cos(math.radians(azimuth)) * 0.1
                        rsrp = ce_base_rsrp + az_factor * 5 + random.gauss(0, 0.5)
                        sinr = config.target_snr_db + az_factor * 3 + random.gauss(0, 0.8)

                    samples_rsrp.append(rsrp)
                    samples_sinr.append(sinr)
                    samples_tput.append(metrics.dl_throughput_mbps)
                    samples_ri.append(float(metrics.rank_indicator))

                az = {
                    "azimuth_deg": azimuth,
                    "rsrp_dbm": sum(samples_rsrp) / len(samples_rsrp),
                    "sinr_db": sum(samples_sinr) / len(samples_sinr),
                    "throughput_mbps": sum(samples_tput) / len(samples_tput),
                    "rank_indicator": sum(samples_ri) / len(samples_ri),
                    "num_samples": len(samples_rsrp),
                    "rsrp_std_db": stddev(samples_rsrp),
                    "sinr_std_db": stddev(samples_sinr),
                    "throughput_std_mbps": stddev(samples_tput),
                    "active_probe_id": az_meta.get("probe_id"),
                    "probe_pattern_gain_dbi": az_meta.get("pattern_gain_dbi"),
                    "path_loss_compensation_db": az_path_loss_db,
                    "path_loss_source": (
                        "rf_chain" if az_meta.get("path_loss_db") is not None else "chamber_avg"
                    ),
                }
                azimuth_results.append(az)

                logger.info(
                    "  azimuth=%.0f°: RSRP=%.1f, SINR=%.1f, Tput=%.0f Mbps, RI=%.2f",
                    azimuth,
                    az["rsrp_dbm"],
                    az["sinr_db"],
                    az["throughput_mbps"],
                    az["rank_indicator"],
                )

            total_duration = loop.time() - t_start

            result_payload: Dict[str, Any] = {
                "cdl_model_name": config.cdl_model_name,
                "frequency_ghz": config.frequency_hz / 1e9,
                "mimo_config": f"{config.mimo_layers}x{config.mimo_layers}",
                "azimuth_results": azimuth_results,
                "total_duration_s": total_duration,
                "engine_mode": config.engine_mode,
                "calibration_entries_used": len(calibration_entries) if calibration_entries else 0,
                "path_loss_compensation_db": avg_path_loss_db,
                "path_loss_certificate_id": (
                    str(path_loss_cert.id) if path_loss_cert is not None else None
                ),
                "path_loss_per_chain_used": chains_used,
                "path_loss_per_chain_available": len(per_chain_pl),
                # P1-12 audit (sibling QZ #79 / TRP #80): no path-loss cert →
                # avg_path_loss_db=0.0, RSRP baseline UNcompensated. The RSRP /
                # throughput numbers then aren't calibrated — flag explicitly so
                # report/GUI mark 未验证(无路损校准) rather than presenting them as
                # calibrated. (Real mode is already gated by P1-8 precheck cal
                # gate; this marks the mock/bypass path + carries provenance.)
                "path_loss_verified": path_loss_cert is not None,
                "switch_topology": topology_result.to_payload(),
                "sampling": {
                    "num_windows_per_azimuth": num_windows,
                    "window_duration_s": window_s,
                    "stat_count_subframes": config.stat_count,
                },
                "carrier_aggregation": {
                    "num_component_carriers": len(ccs),
                    "pcell": {
                        "frequency_ghz": pcell.frequency_hz / 1e9,
                        "bandwidth_mhz": pcell.bandwidth_mhz,
                        "band": pcell.band,
                    },
                    "scells": scells_added,
                },
                "dut_disconnect_warnings": dut_disconnect_warnings,
                "azimuths_completed": len(azimuth_results),
                "azimuths_requested": len(config.azimuths_deg),
                # Phase 2b: input-level closed-loop telemetry (success/skipped/
                # opt-out audit). strict-fail 路径不会到这里 — 早期 return 时
                # input_level_calibration 已经塞进 measurements。
                "input_level_calibration": input_level_payload,
                # P2-11 Phase 1: 多方频率一致性校验 (一致/opt-out 路径留 audit;
                # strict-fail 路径早期 return 时已塞进 measurements)。
                "frequency_consistency": freq_result.to_payload(),
            }

            # ``asc_files_loaded`` is ASC-specific (ExternalWaveformStrategy /
            # ExternalAscPathStrategy): GCM mode (NativeModelStrategy) doesn't
            # consume .asc files at all — the channel is generated inside
            # Keysight GCM Studio's native runtime. Audit 2026-05-17 Y2 (PR #53)
            # established the omit-in-GCM rule; 2026-05-18 P0-7 extended it to
            # also cover the new EXTERNAL_ASC mode (still ASC-based, so the
            # diagnostic signal "emulator loaded waveforms" remains meaningful).
            # In EXTERNAL_ASC mode we additionally stamp the operator-provided
            # source path for audit-trail traceability.
            if engine_mode != EngineMode.GCM_NATIVE:
                result_payload["asc_files_loaded"] = True
                if engine_mode == EngineMode.EXTERNAL_ASC:
                    result_payload["asc_source"] = "external"
                    result_payload["external_asc_source_path"] = config.asc_source_path
                else:
                    result_payload["asc_source"] = "channel_engine_service"
            else:
                # P2-11 Phase 2: GCM .smu 来源 audit (TestCase 驱动 vs 驱动默认 fallback)
                result_payload["emulation_file"] = config.emulation_file
                result_payload["emulation_file_source"] = (
                    "testcase" if config.emulation_file else "driver_default"
                )
        finally:
            cleanup_warnings = await cleanup_chamber_instruments(
                hal, context.test_execution.id
            )

        if cleanup_warnings:
            result_payload["cleanup_warnings"] = cleanup_warnings

        # Surface the uncalibrated-path-loss case as a result warning (not just
        # a server-side log) so it rides into the report / operator view.
        measure_warnings: List[str] = list(cleanup_warnings or [])
        if not result_payload.get("path_loss_verified"):
            measure_warnings.insert(
                0,
                "⚠️ 路损未校准: 无 path-loss certificate, RSRP 基线未补偿 (兜底 0 dB) — "
                "RSRP / 吞吐量为非校准值。运行 CAL-01 路损校准 (P0-3) 后重测。",
            )

        write_phase_result(context.test_execution, "measure", result_payload)
        context.db.commit()

        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result_payload,
            warnings=measure_warnings or None,
        )

    # ---------------------------------------------------------------------
    # P0-8 Step 2 Phase 2b: F64 输入操作点闭环 wiring
    # ---------------------------------------------------------------------
    async def _run_input_level_closed_loop(
        self,
        *,
        emulator: Any,
        base_station: Any,
        config: Any,
        execution_id: Any,
    ) -> Dict[str, Any]:
        """跑 InputLevelController + 落遥测。返回 input_level_calibration payload。

        capability hasattr 检测 (mock CE / 未实现 atomic 的 vendor 自动跳); 跑过
        controller 后无论成败都返回结构化 payload, 上层据 success/skipped + strict
        flag 决定 phase verdict。
        """
        required_ce_methods = (
            "autoset_inputs",
            "measure_input",
            "get_input_level_limits",
            "set_input_measurement_mode",
            "set_burst_trigger_level",
            "get_group_clipping",
            "get_system_status",
        )
        ce_caps = {m: hasattr(emulator, m) for m in required_ce_methods}
        ce_supports = all(ce_caps.values())
        bs_supports = hasattr(base_station, "set_downlink_power")

        if not ce_supports or not bs_supports:
            reason_parts: List[str] = []
            missing_ce = [m for m, ok in ce_caps.items() if not ok]
            if missing_ce:
                reason_parts.append(f"CE 缺接口: {missing_ce}")
            if not bs_supports:
                reason_parts.append("BS 缺 set_downlink_power")
            skip_reason = (
                "; ".join(reason_parts)
                + " — 至少一方缺 capability (e.g. mock driver / 未实现 atomic 的 vendor), "
                "跳过闭环 (不影响 mock dry-run)"
            )
            logger.info(
                "[%s] Phase 2b: input-level closed loop SKIPPED — %s",
                execution_id, skip_reason,
            )
            return {"skipped": True, "reason": skip_reason}

        # active_inputs 推导 (Codex on PR #98): **跟 BS 实际驱动的 layer 数 1:1**,
        # 不是 CE 的 _tx_antennas。execute() 早期已经 set_cell_config(mimo_layers=
        # config.mimo_layers), BS 只发 config.mimo_layers 路 → F64 也只有这几路
        # input 有信号; 多 autoset 一路 = 在 unconnected 端口上 autoset, no-signal
        # fail-loud, strict 模式把 measure phase 早死在 azimuth loop 之前。
        # CE _tx_antennas (.smu 的 TX 端口数) 只用作 sanity bound: BS layers 超过
        # 它 = 物理上跑不了 (e.g. 2x2 .smu 上 BS 想发 4 layer)。
        n_layers = int(config.mimo_layers)
        ce_tx = getattr(emulator, "_tx_antennas", None)
        if ce_tx is not None and n_layers > ce_tx:
            msg = (
                f"拓扑不匹配: config.mimo_layers={n_layers} > CE _tx_antennas={ce_tx} "
                f"(BS 想发的 layer 数超过当前 .smu 输入端口数, 物理上跑不了)。"
                f" 操作员应调整 config.mimo_layers 或换 .smu "
                f"(默认 3600M 是 4x4, set_mimo_config 可改)。"
            )
            logger.error("[%s] Phase 2b: %s", execution_id, msg)
            return {
                "success": False,
                "failure_reason": msg,
                "topology_mismatch": True,
                "ce_tx_antennas": ce_tx,
                "config_mimo_layers": n_layers,
                "iterations": 0,
                "uxm_dl_power_dbm": None,
                "clipping_per_mille": None,
                "system_warnings": [],
                "operating_point": [],
                "active_inputs": list(range(1, n_layers + 1)),
                "strict": bool(config.precheck_strict_input_level),
            }
        active_inputs = tuple(range(1, n_layers + 1))

        from app.services.input_level_controller import InputLevelController

        controller = InputLevelController(
            ce_driver=emulator,
            bs_driver=base_station,
            active_inputs=active_inputs,
        )
        logger.info(
            "[%s] Phase 2b: input-level closed loop START — active_inputs=%s",
            execution_id, active_inputs,
        )
        il_result = await controller.establish()

        payload: Dict[str, Any] = {
            "success": il_result.success,
            "uxm_dl_power_dbm": il_result.uxm_dl_power_dbm,
            "clipping_per_mille": il_result.clipping_per_mille,
            "iterations": il_result.iterations,
            "system_warnings": il_result.system_warnings,
            "operating_point": [
                {
                    "input_num": op.input_num,
                    "avg_dbm": op.avg_dbm,
                    "crest_db": op.crest_db,
                }
                for op in il_result.operating_point
            ],
            "failure_reason": il_result.failure_reason,
            "active_inputs": list(active_inputs),
            "strict": config.precheck_strict_input_level,
        }

        if il_result.success:
            logger.info(
                "[%s] Phase 2b: input-level closed loop CONVERGED "
                "(iter=%d, UXM=%.1f dBm, clipping=%s‰)",
                execution_id,
                il_result.iterations,
                il_result.uxm_dl_power_dbm,
                il_result.clipping_per_mille,
            )
        elif config.precheck_strict_input_level:
            # strict-fail: 这里只 log, 上层根据 success 字段触发早期 FAILED return。
            logger.error(
                "[%s] Phase 2b: input-level closed loop FAILED (strict) — %s",
                execution_id, il_result.failure_reason,
            )
        else:
            # opt-out: 降级为 warning, 继续 azimuth 扫描 (audit-only)
            logger.warning(
                "[%s] Phase 2b: input-level closed loop FAILED "
                "(precheck_strict_input_level=False, audit-only) — %s",
                execution_id, il_result.failure_reason,
            )
        return payload
