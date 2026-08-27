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
        primary_carrier = config.primary_carrier

        # 现场显式选择“无校准测试”时，REFERENCE 也必须真正跳过。原实现只在
        # PRECHECK 放行，随后仍主动驱动 FSVA，既违背旁路语义，也会制造假的
        # TRP/补偿数值。
        if config.precheck_strict_cal is False:
            result_payload: Dict[str, Any] = {
                "antenna_model": config.reference_antenna_model,
                "antenna_gain_dbi": config.reference_antenna_gain_dbi,
                "measurement_source": "calibration_bypass",
                "trp_verified": False,
                "confirmed": False,
                "bypassed": True,
            }
            write_phase_result(context.test_execution, "reference", result_payload)
            context.db.commit()
            return StepExecutionResult(
                status=StepExecutionStatus.SKIPPED,
                measurements=result_payload,
                warnings=["校准旁路已启用：未执行 FSVA 参考测量，未产生 TRP 或补偿数值"],
            )

        from app.services.instrument_hal_service import get_hal_service, is_mock_driver

        hal = get_hal_service()
        sa = hal.drivers.get("signalAnalyzer")
        # P1-12 audit: a real reference TRP needs a REAL signal analyzer. Two
        # non-real cases must both be flagged 未验证(兜底值): (a) no SA driver →
        # _MOCK_TRP_DBM constant; (b) a *mock* SA driver → simulated power that
        # gets the "hal_signal_analyzer" source label but is NOT a real measure.
        sa_is_real = sa is not None and not is_mock_driver(sa)

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
            try:
                setup_confirmed = await sa.setup_spectrum(
                    center_freq_hz=primary_carrier.frequency_hz,
                    span_hz=200e6,
                    rbw_hz=1e5,
                )
                if setup_confirmed is not True:
                    raise RuntimeError("FSVA spectrum setup was not confirmed")
                measured_pwr = await sa.measure_channel_power(
                    bandwidth_hz=primary_carrier.bandwidth_mhz * 1e6
                )
            except Exception as exc:
                result_payload.update(
                    {
                        "measurement_source": (
                            "hal_signal_analyzer"
                            if sa_is_real
                            else "hal_signal_analyzer_mock"
                        ),
                        "trp_verified": False,
                        "confirmed": False,
                    }
                )
                write_phase_result(
                    context.test_execution, "reference", result_payload
                )
                context.db.commit()
                return StepExecutionResult(
                    status=StepExecutionStatus.FAILED,
                    measurements=result_payload,
                    error_message=str(exc),
                )
            measured_trp_dbm = measured_pwr + _MOCK_SA_TO_TRP_OFFSET_DB
            # 「来源」这一栏要说实话（P1-48）：SA 挂着但是 mock 驱动时，
            # 这个功率是仿真出来的，写 "hal_signal_analyzer" 会让读报告的人
            # 以为是实测。旁边虽然有一句 warning，但那句进不了「来源」这一栏，
            # 于是同一份 PDF 上「来源：hal_signal_analyzer」和「验证：未验证(mock/兜底值)」
            # 并排打架 —— 一句真话一句假话。
            result_payload["measurement_source"] = (
                "hal_signal_analyzer" if sa_is_real else "hal_signal_analyzer_mock"
            )
            if not sa_is_real:
                # SA driver present but it's a MOCK — the "hal_signal_analyzer"
                # label is misleading; the power is simulated, not measured.
                warnings.append(
                    "⚠️ 参考 TRP 未验证: signalAnalyzer 是 mock driver, 测得功率为仿真值"
                    "非实测 (补偿因子因此也非实测)。真实参考测量需 real SA (P0-4)。"
                )
        else:
            logger.warning(
                "[%s] Phase 2: no signalAnalyzer in HAL; using mock TRP",
                context.test_execution.id,
            )
            warnings.append(
                "⚠️ 参考 TRP 未验证: 无 signalAnalyzer driver, 套用兜底默认值 "
                f"{_MOCK_TRP_DBM} dBm (非实测; 补偿因子因此也非实测)。真实参考测量需 "
                "SA 入 HAL (P0-4) + 喇叭天线。"
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
        # P1-12 audit: same pattern as the QZ fallback (PR #79). trp_verified is
        # True ONLY when a real SA produced the measurement — covers both the
        # no-SA constant fallback and the mock-SA simulated case (the latter
        # carries the "hal_signal_analyzer" source label but is NOT real). When
        # False the TRP + the compensation factor derived from it are not real
        # measurements → report/GUI mark "未验证(兜底值)". Mark, don't fail —
        # mock rehearsal must still run.
        result_payload["trp_verified"] = sa_is_real

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
