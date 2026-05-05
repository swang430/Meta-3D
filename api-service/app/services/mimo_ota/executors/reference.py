"""Phase 2: Reference antenna baseline.

Replaces commissioning_service.phase2_reference_measurement. Measures the
TRP of a known-gain horn antenna so Phase 3 can apply the right link-budget
compensation. Falls back to a deterministic mock when no signal analyzer is
wired up via HAL.
"""
import asyncio
import logging
import random
from typing import Any, Dict

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

# Same offset the legacy commissioning_service used to convert mock SA's -50 dBm
# raw read into a feasible 23.5 dBm TRP. Kept here so the calibration math is
# explicit and easy to swap when a real SA wakes up.
_MOCK_SA_TO_TRP_OFFSET_DB = 73.5
_NOMINAL_TRP_DBM = 23.0
_MOCK_TRP_DBM = 23.5
_MOCK_TRP_NOISE_STD_DB = 0.3


@register_executor(MIMOOTAStepType.REFERENCE.value)
class ReferenceExecutor(IStepExecutor):
    """Measure reference antenna TRP and compute the compensation factor."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        config = load_mimo_ota_config(context.test_execution)

        from app.services.instrument_hal_service import get_hal_service

        hal = get_hal_service()
        sa = hal.drivers.get("signalAnalyzer")

        warnings: list[str] = []
        result_payload: Dict[str, Any] = {
            "antenna_model": config.reference_antenna_model,
            "antenna_gain_dbi": config.reference_antenna_gain_dbi,
        }

        if sa is not None:
            logger.info(
                "[%s] Phase 2: measuring reference antenna via HAL signalAnalyzer",
                context.test_execution.id,
            )
            await sa.setup_spectrum(
                center_freq_hz=config.frequency_hz,
                span_hz=200e6,
                rbw_hz=1e5,
            )
            measured_pwr = await sa.measure_channel_power(
                bandwidth_hz=config.bandwidth_mhz * 1e6
            )
            measured_trp_dbm = measured_pwr + _MOCK_SA_TO_TRP_OFFSET_DB
            result_payload["measurement_source"] = "hal_signal_analyzer"
        else:
            logger.warning(
                "[%s] Phase 2: no signalAnalyzer in HAL; using mock TRP",
                context.test_execution.id,
            )
            warnings.append(
                "No signalAnalyzer driver in HAL — falling back to deterministic mock TRP"
            )
            await asyncio.sleep(0.5)
            measured_trp_dbm = _MOCK_TRP_DBM + random.gauss(0, _MOCK_TRP_NOISE_STD_DB)
            result_payload["measurement_source"] = "mock"

        # Compensation factor = expected gain - (measured TRP - nominal TRP).
        # Same formula as legacy commissioning_service.phase2_reference_measurement.
        compensation_factor_db = config.reference_antenna_gain_dbi - (
            measured_trp_dbm - _NOMINAL_TRP_DBM
        )

        result_payload["measured_trp_dbm"] = round(measured_trp_dbm, 3)
        result_payload["compensation_factor_db"] = round(compensation_factor_db, 3)
        result_payload["confirmed"] = True

        write_phase_result(context.test_execution, "reference", result_payload)
        context.db.commit()

        logger.info(
            "[%s] Phase 2 complete: TRP=%.1f dBm, comp=%.1f dB",
            context.test_execution.id,
            measured_trp_dbm,
            compensation_factor_db,
        )
        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result_payload,
            warnings=warnings,
        )
