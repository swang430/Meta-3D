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
        from app.services.channel_generation.gcm_strategy import NativeModelStrategy
        from app.services.instrument_hal_service import get_hal_service
        from app.services.mimo_ota.cleanup import cleanup_chamber_instruments
        from app.services.mimo_ota.switch_orchestrator import (
            orchestrate_switch_topology,
        )
        from app.services.probe_pattern.consumer import (
            get_probe_gain_at_azimuth,
            select_active_probe_id,
        )
        from app.hal.channel_emulator import ChannelLoadMode

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

            await base_station.set_cell_config(
                {
                    "frequency_mhz": pcell.frequency_hz / 1e6,
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

            # --- Phase 2c: verify SwitchTopology declares mimo_ota mode for this chamber ---
            # CAICT-Lab-1 has a fixed cabling, so this is a *declaration check*
            # rather than live switching: we surface the topology id, mode, and
            # CE-port→probe bindings into the result for traceability and
            # downstream channel-gen consumption. Missing topology is a warning,
            # not a hard failure.
            topology_result = orchestrate_switch_topology(
                context.db, chamber.id, mode_id="mimo_ota"
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

            calibration_entries = ce_client._query_calibration_entries(
                chamber.id, config.frequency_hz, chamber
            )

            # --- Phase 2a: apply chamber-level path-loss to the RSRP baseline ---
            # Per-probe (azimuth → probe_id) compensation lives in ANALYSIS together
            # with quiet-zone ripple; here we only correct the bulk RSRP target so
            # the synthesized samples land near what the DUT actually sees.
            from app.services.path_loss_calibration_service import (
                ProbePathLossCalibrationService,
            )

            pl_service = ProbePathLossCalibrationService(context.db, use_mock=False)
            path_loss_cert = pl_service.get_latest_calibration(
                chamber.id, config.frequency_hz / 1e6
            )
            if path_loss_cert is not None:
                avg_path_loss_db = float(path_loss_cert.avg_path_loss_db or 0.0)
                logger.info(
                    "[%s] Phase 2a: applying chamber path-loss avg=%.2f dB (cert=%s)",
                    context.test_execution.id,
                    avg_path_loss_db,
                    path_loss_cert.id,
                )
            else:
                avg_path_loss_db = 0.0
                logger.warning(
                    "[%s] Phase 2a: no path-loss calibration for chamber %s @ %.0f MHz; "
                    "RSRP baseline uncompensated",
                    context.test_execution.id,
                    chamber.id,
                    config.frequency_hz / 1e6,
                )

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

            # --- Per-azimuth measurement loop (Phase 2d windowed sampling) ---
            azimuth_results: List[Dict[str, Any]] = []
            # Path-loss attenuates DL signal at the DUT, so subtract from target.
            ce_base_rsrp = config.target_rsrp_dbm - avg_path_loss_db
            # One sample per stat window (≈ stat_count subframes × 1ms);
            # cap aggressively in dev so smoke tests don't wait minutes.
            num_windows = min(config.num_samples_per_azimuth, _DEV_SAMPLE_WINDOWS)
            window_s = max(config.stat_count / 1000.0, _MOCK_WINDOW_FLOOR_S)

            loop = asyncio.get_event_loop()
            t_start = loop.time()

            # Phase 2f: pre-resolve per-azimuth probe + pattern gain so the
            # inner sample loop doesn't hammer the DB. None entries fall back
            # to nominal chamber.probe_gain_dbi inside the loop.
            nominal_probe_gain_dbi = float(chamber.probe_gain_dbi or 0.0)
            azimuth_probe_gains: Dict[float, Dict[str, Any]] = {}
            for az_target in config.azimuths_deg:
                pid = select_active_probe_id(chamber.num_probes, az_target)
                pattern_gain_v = get_probe_gain_at_azimuth(
                    context.db, chamber.num_probes, az_target, config.frequency_hz / 1e6, "V"
                )
                azimuth_probe_gains[az_target] = {
                    "probe_id": pid,
                    "pattern_gain_dbi": pattern_gain_v,
                    "gain_offset_db": (
                        pattern_gain_v - nominal_probe_gain_dbi
                        if pattern_gain_v is not None else None
                    ),
                }
            patterns_used = sum(
                1 for v in azimuth_probe_gains.values() if v["pattern_gain_dbi"] is not None
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
                "asc_files_loaded": True,
                "azimuth_results": azimuth_results,
                "total_duration_s": total_duration,
                "engine_mode": config.engine_mode,
                "calibration_entries_used": len(calibration_entries) if calibration_entries else 0,
                "path_loss_compensation_db": avg_path_loss_db,
                "path_loss_certificate_id": (
                    str(path_loss_cert.id) if path_loss_cert is not None else None
                ),
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
            }
        finally:
            cleanup_warnings = await cleanup_chamber_instruments(
                hal, context.test_execution.id
            )

        if cleanup_warnings:
            result_payload["cleanup_warnings"] = cleanup_warnings
        write_phase_result(context.test_execution, "measure", result_payload)
        context.db.commit()

        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result_payload,
            warnings=cleanup_warnings or None,
        )
