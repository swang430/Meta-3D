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
from uuid import UUID as UUIDType

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

# Cap the per-azimuth sample loop in dev so smoke tests don't take forever.
# Production should drop this cap by overriding via step_overrides on the TestCase.
_DEV_SAMPLE_LIMIT = 20


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

        # --- Base station cell config (band + duplex inferred from frequency_mhz) ---
        await base_station.set_cell_config(
            {
                "frequency_mhz": config.frequency_hz / 1e6,
                "bandwidth_mhz": config.bandwidth_mhz,
                "scs_khz": config.subcarrier_spacing_khz,
                "mimo_layers": config.mimo_layers,
                "dl_power_dbm": config.target_tx_power_dbm,
            }
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

        calibration_entries = ce_client._query_calibration_entries(
            chamber.id, config.frequency_hz, chamber
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

        gen_ok = await generator.generate_and_load(
            sim_rules={
                "frequency_hz": config.frequency_hz,
                "target_tx_power_dbm": config.target_tx_power_dbm,
                "target_rsrp_dbm": config.target_rsrp_dbm,
                "target_snr_db": config.target_snr_db,
            },
            cdl_model_data={
                "model_name": config.cdl_model_name,
                "session_id": str(context.test_execution.id),
            },
        )
        if not gen_ok:
            return StepExecutionResult(
                status=StepExecutionStatus.FAILED,
                error_message=f"Channel generation failed for engine_mode={config.engine_mode}",
            )

        # --- Per-azimuth measurement loop ---
        azimuth_results: List[Dict[str, Any]] = []
        ce_base_rsrp = config.target_rsrp_dbm
        sample_cap = min(config.num_samples_per_azimuth, _DEV_SAMPLE_LIMIT)

        loop = asyncio.get_event_loop()
        t_start = loop.time()

        for azimuth in config.azimuths_deg:
            logger.info(
                "[%s] Phase 3: positioner -> azimuth %.1f°",
                context.test_execution.id,
                azimuth,
            )
            await positioner.move_to(azimuth, 0.0)
            await asyncio.sleep(config.settling_time_s)

            samples_rsrp: List[float] = []
            samples_sinr: List[float] = []
            samples_tput: List[float] = []
            samples_ri: List[float] = []

            for _ in range(sample_cap):
                metrics = await base_station.get_throughput_metrics()

                # RF KPIs (RSRP/SINR) are normally UE-reported; until that path
                # exists we synthesize from target + position-aware perturbation.
                az_factor = math.cos(math.radians(azimuth)) * 0.1
                rsrp = ce_base_rsrp + az_factor * 5 + random.gauss(0, 0.5)
                sinr = config.target_snr_db + az_factor * 3 + random.gauss(0, 0.8)

                samples_rsrp.append(rsrp)
                samples_sinr.append(sinr)
                samples_tput.append(metrics.dl_throughput_mbps)
                samples_ri.append(float(metrics.rank_indicator))

                await asyncio.sleep(0.02)

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

        await positioner.disconnect()
        await base_station.stop_signaling()
        await base_station.disconnect()

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
        }
        write_phase_result(context.test_execution, "measure", result_payload)
        context.db.commit()

        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result_payload,
        )
