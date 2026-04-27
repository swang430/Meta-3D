"""
Phase Compensation Executor (相位补偿硬件执行器)

闭环实现：将 PhaseCalibrationService 计算的补偿值
通过真实 SCPI 命令下发到 Keysight PROPSIM F64 信道仿真器。

架构位置:
    PhaseCalibrationService (计算层)
         ↓ compensation_deg 数组
    PhaseCompensationExecutor (本模块 - 执行层)
         ↓ SCPI: OUTP:PHA:DEG:CH / INP:PHA:DEG:CH
    F64 硬件 (物理层)

为什么需要这个模块:
    在上一轮审计中发现，相位校准服务已经能正确计算 phase_correction_deg，
    并且补偿值已通过 _query_phase_compensation() 注入到 CE Payload 中。
    但这只是"数据层面"的注入——Channel Engine 在计算波场合成时会使用这些值。
    而 F64 硬件本身的输出通道仍然存在物理相位偏差，需要通过 SCPI 命令
    在仪器端也应用相位补偿，才能实现完整的闭环。

支持的补偿模式:
    1. OUTPUT_PHASE: 在 F64 输出端补偿 (OUTP:PHA:DEG:CH)
       - 适用于: 线缆相位差
       - 优势: 不影响信道模型的空间相位关系
    2. INPUT_PHASE: 在 F64 输入端补偿 (INP:PHA:DEG:CH)
       - 适用于: 基站仿真器各端口的相位不一致
       - 注意: 通常不需要
    3. CE_PAYLOAD: 仅在信道模型中补偿 (不下发 SCPI)
       - 适用于: 无法通过仪器补偿的场景
       - 已由 channel_engine_client._query_phase_compensation() 实现
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.hal.base import InstrumentDriver, InstrumentStatus
from app.models.probe_calibration import ChannelPhaseCalibration

logger = logging.getLogger(__name__)


class PhaseCompensationMode(str, Enum):
    """相位补偿应用模式"""
    OUTPUT_PHASE = "output_phase"  # F64 输出端补偿
    INPUT_PHASE = "input_phase"    # F64 输入端补偿
    CE_PAYLOAD = "ce_payload"      # 仅在 CE Payload 中补偿（软件补偿）
    BOTH = "both"                  # 硬件 + 软件双重补偿


class PhaseCompensationResult:
    """补偿执行结果"""

    def __init__(self):
        self.applied_channels: int = 0
        self.failed_channels: int = 0
        self.skipped_channels: int = 0
        self.mode: Optional[PhaseCompensationMode] = None
        self.errors: List[str] = []

    @property
    def success(self) -> bool:
        return self.failed_channels == 0 and self.applied_channels > 0

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "applied_channels": self.applied_channels,
            "failed_channels": self.failed_channels,
            "skipped_channels": self.skipped_channels,
            "mode": self.mode.value if self.mode else None,
            "errors": self.errors,
        }


class PhaseCompensationExecutor:
    """
    相位补偿硬件执行器

    将 ChannelPhaseCalibration 表中的补偿值下发到 F64 硬件。
    这是相位校准闭环中"最后一公里"的实现。
    """

    def __init__(self, db: Session):
        self.db = db

    async def apply_compensation(
        self,
        chamber_id: UUID,
        channel_emulator: InstrumentDriver,
        mode: PhaseCompensationMode = PhaseCompensationMode.OUTPUT_PHASE,
    ) -> PhaseCompensationResult:
        """
        从数据库加载相位补偿值并下发到硬件。

        完整流程:
        1. 查询 ChannelPhaseCalibration 表中最新的有效补偿数据
        2. 提取 phase_compensation 数组
        3. 根据 mode 选择 SCPI 命令
        4. 逐通道下发补偿值
        5. 更新 compensation_applied 标记

        Args:
            chamber_id: 暗室配置 ID
            channel_emulator: 信道仿真器驱动实例 (需要 RealPropsimF64Driver)
            mode: 补偿应用模式

        Returns:
            PhaseCompensationResult
        """
        result = PhaseCompensationResult()
        result.mode = mode

        # ------ Step 1: 从 DB 加载补偿数据 ------
        latest_cal = self.db.query(ChannelPhaseCalibration).filter(
            ChannelPhaseCalibration.chamber_id == chamber_id,
            ChannelPhaseCalibration.status == "valid",
        ).order_by(
            desc(ChannelPhaseCalibration.calibrated_at)
        ).first()

        if not latest_cal:
            logger.warning(
                f"[PhaseExecutor] 暗室 {chamber_id} 无有效的相位校准数据"
            )
            result.errors.append("无有效的相位校准数据")
            return result

        compensation_data = latest_cal.phase_compensation
        if not compensation_data:
            logger.warning(
                f"[PhaseExecutor] 校准 {latest_cal.id} 的补偿数据为空"
            )
            result.errors.append("补偿数据为空")
            return result

        logger.info(
            f"[PhaseExecutor] 加载相位补偿: calibration_id={latest_cal.id}, "
            f"{len(compensation_data)} channels, mode={mode.value}"
        )

        # ------ Step 2: CE_PAYLOAD 模式不需要硬件下发 ------
        if mode == PhaseCompensationMode.CE_PAYLOAD:
            result.applied_channels = len(compensation_data)
            result.skipped_channels = 0
            logger.info(
                "[PhaseExecutor] CE_PAYLOAD 模式: 补偿值仅在 Channel Engine "
                "Payload 中应用 (由 _query_phase_compensation 处理)"
            )
            return result

        # ------ Step 3: 验证仪器状态 ------
        if channel_emulator.status not in (
            InstrumentStatus.CONNECTED,
            InstrumentStatus.READY,
        ):
            result.errors.append(
                f"信道仿真器未就绪 (status={channel_emulator.status.value})"
            )
            return result

        # ------ Step 4: 逐通道下发 SCPI 补偿命令 ------
        for comp_entry in compensation_data:
            ch_id = comp_entry.get("channel_id")
            comp_deg = comp_entry.get("compensation_deg", 0.0)

            if ch_id is None:
                result.skipped_channels += 1
                continue

            # 跳过补偿值接近零的通道 (避免不必要的 SCPI 开销)
            if abs(comp_deg) < 0.1:
                result.skipped_channels += 1
                continue

            try:
                ok = False
                if mode in (
                    PhaseCompensationMode.OUTPUT_PHASE,
                    PhaseCompensationMode.BOTH,
                ):
                    # F64 SCPI: OUTP:PHA:DEG:CH <output>,<phase_degrees>
                    ok = await channel_emulator.set_output_phase(
                        int(ch_id), float(comp_deg)
                    )

                if mode == PhaseCompensationMode.INPUT_PHASE:
                    # F64 SCPI: INP:PHA:DEG:CH <input>,<phase_degrees>
                    ok = await channel_emulator.set_input_phase(
                        int(ch_id), float(comp_deg)
                    )

                if ok:
                    result.applied_channels += 1
                else:
                    result.failed_channels += 1
                    result.errors.append(
                        f"通道 {ch_id} 补偿下发失败 (返回 False)"
                    )

            except AttributeError:
                # 驱动不支持 set_output_phase (可能是 Mock)
                logger.warning(
                    f"[PhaseExecutor] 驱动 {type(channel_emulator).__name__} "
                    f"不支持 set_output_phase/set_input_phase, 跳过硬件补偿"
                )
                result.skipped_channels += 1

            except Exception as e:
                result.failed_channels += 1
                result.errors.append(
                    f"通道 {ch_id} 补偿异常: {e}"
                )

        # ------ Step 5: 更新数据库标记 ------
        if result.success:
            try:
                latest_cal.compensation_applied = True
                self.db.commit()
                logger.info(
                    f"[PhaseExecutor] 补偿已应用并标记: "
                    f"{result.applied_channels} 通道成功, "
                    f"{result.skipped_channels} 跳过"
                )
            except Exception as e:
                self.db.rollback()
                logger.error(f"[PhaseExecutor] 更新 compensation_applied 失败: {e}")

        return result

    async def clear_compensation(
        self,
        channel_emulator: InstrumentDriver,
        num_channels: int = 64,
    ) -> bool:
        """
        清除所有通道的相位补偿（归零）。

        在重新校准前或切换暗室配置时使用。

        Args:
            channel_emulator: 信道仿真器驱动
            num_channels: 通道总数

        Returns:
            True if all channels cleared
        """
        logger.info(f"[PhaseExecutor] 清除 {num_channels} 通道的相位补偿")
        failed = 0

        for ch in range(1, num_channels + 1):
            try:
                ok = await channel_emulator.set_output_phase(ch, 0.0)
                if not ok:
                    failed += 1
            except Exception:
                failed += 1

        if failed > 0:
            logger.warning(f"[PhaseExecutor] 清除补偿失败: {failed}/{num_channels}")
            return False

        logger.info(f"[PhaseExecutor] 所有 {num_channels} 通道相位已归零")
        return True

    async def verify_applied_compensation(
        self,
        channel_emulator: InstrumentDriver,
        expected_compensations: Dict[int, float],
        tolerance_deg: float = 0.5,
    ) -> Dict[str, Any]:
        """
        验证硬件端的相位补偿是否已正确应用。

        通过 OUTP:CALIB:GET? 查询当前的输出校准值，
        与期望的补偿值对比。

        Args:
            channel_emulator: 信道仿真器驱动
            expected_compensations: {channel_id: expected_phase_deg}
            tolerance_deg: 允许的误差 (度)

        Returns:
            验证结果字典
        """
        mismatches = []
        verified = 0

        for ch_id, expected_deg in expected_compensations.items():
            try:
                cal_data = await channel_emulator.get_output_calibration(ch_id)
                if cal_data is None:
                    mismatches.append({
                        "channel": ch_id,
                        "expected_deg": expected_deg,
                        "actual_deg": None,
                        "error": "无法读取校准数据",
                    })
                    continue

                actual_deg = cal_data.get("phase_deg", 0.0)
                diff = abs(actual_deg - expected_deg)

                if diff > tolerance_deg:
                    mismatches.append({
                        "channel": ch_id,
                        "expected_deg": expected_deg,
                        "actual_deg": actual_deg,
                        "diff_deg": diff,
                    })
                else:
                    verified += 1

            except Exception as e:
                mismatches.append({
                    "channel": ch_id,
                    "error": str(e),
                })

        return {
            "verified_channels": verified,
            "mismatched_channels": len(mismatches),
            "total_channels": len(expected_compensations),
            "pass": len(mismatches) == 0,
            "mismatches": mismatches,
        }
