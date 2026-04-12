"""
Relative Calibration Service

相对校准服务：通过建立基线，实现快速校准。

核心功能：
1. 建立基线 (create_baseline) - 全量校准，计算 Delta 矩阵
2. 快速校准 (quick_calibrate) - 仅测量参考通道，推导其他通道
3. 漂移检测 (check_drift) - 对比快速校准结果与基线
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID
from dataclasses import dataclass
from enum import Enum

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import desc

logger = logging.getLogger(__name__)


# ==================== 常量 ====================

BASELINE_VALIDITY_DAYS = 90  # 基线有效期（天）
DEFAULT_DRIFT_THRESHOLD_DB = 0.3  # 默认幅度漂移阈值
DEFAULT_DRIFT_THRESHOLD_DEG = 2.0  # 默认相位漂移阈值


# ==================== 数据类 ====================

class CalibrationType(str, Enum):
    """校准类型"""
    AMPLITUDE = "amplitude"
    PHASE = "phase"
    PATH_LOSS = "path_loss"


@dataclass
class ChannelDelta:
    """通道 Delta 偏移"""
    channel_id: int
    delta_db: float
    delta_deg: float
    uncertainty_db: float = 0.1


@dataclass
class BaselineStatus:
    """基线状态"""
    calibration_type: str
    frequency_mhz: float
    status: str
    baseline_date: Optional[datetime]
    valid_until: Optional[datetime]
    days_remaining: int
    total_channels: int
    reference_channel_id: int
    drift_within_threshold: bool


@dataclass
class QuickCalibrationResult:
    """快速校准结果"""
    success: bool
    calibration_type: str
    frequency_mhz: float
    reference_channel_id: int
    reference_value_db: float
    derived_channels: List[Dict[str, Any]]
    drift_detected: bool
    max_drift_db: float
    max_drift_deg: float
    calibrated_at: datetime


@dataclass
class DriftCheckResult:
    """漂移检测结果"""
    baseline_id: str
    within_threshold: bool
    max_drift_db: float
    max_drift_deg: float
    channels_exceeding_threshold: List[int]
    recommendation: str


# ==================== 服务类 ====================

class RelativeCalibrationService:
    """
    相对校准服务
    
    通过建立各通道相对于参考通道的 Delta 基线，
    后续仅需测量参考通道即可推导其他通道数值。
    """

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock

    def create_baseline(
        self,
        chamber_id: UUID,
        calibration_type: CalibrationType,
        frequency_mhz: float,
        reference_channel_id: int = 0,
        calibrated_by: str = "system",
    ) -> Dict[str, Any]:
        """
        建立校准基线
        
        执行全量校准，测量所有通道，计算相对于参考通道的 Delta 矩阵。
        
        Args:
            chamber_id: 暗室 ID
            calibration_type: 校准类型 (amplitude, phase, path_loss)
            frequency_mhz: 校准频率
            reference_channel_id: 参考通道 ID
            calibrated_by: 校准人员
            
        Returns:
            基线创建结果
        """
        logger.info(
            f"Creating baseline: chamber={chamber_id}, type={calibration_type}, "
            f"freq={frequency_mhz}MHz, ref_channel={reference_channel_id}"
        )

        # 获取通道数量（从暗室配置）
        total_channels = self._get_total_channels(chamber_id)

        # 执行全量测量
        measurements = self._measure_all_channels(
            chamber_id, calibration_type, frequency_mhz, total_channels
        )

        # 计算 Delta 矩阵
        reference_value = measurements[reference_channel_id]
        delta_matrix = {}
        
        for channel_id, value in measurements.items():
            if channel_id == reference_channel_id:
                continue
            delta_matrix[str(channel_id)] = {
                "delta_db": value["amplitude_db"] - reference_value["amplitude_db"],
                "delta_deg": value["phase_deg"] - reference_value["phase_deg"],
                "uncertainty_db": 0.1,
            }

        # 保存到数据库
        from app.models.probe_calibration import CalibrationBaseline, CalibrationStatus

        baseline = CalibrationBaseline(
            chamber_id=chamber_id,
            calibration_type=calibration_type.value,
            frequency_mhz=frequency_mhz,
            reference_channel_id=reference_channel_id,
            reference_value_db=reference_value["amplitude_db"],
            reference_value_deg=reference_value["phase_deg"],
            delta_matrix=delta_matrix,
            total_channels=total_channels,
            drift_threshold_db=DEFAULT_DRIFT_THRESHOLD_DB,
            drift_threshold_deg=DEFAULT_DRIFT_THRESHOLD_DEG,
            baseline_date=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=BASELINE_VALIDITY_DAYS),
            status=CalibrationStatus.VALID.value,
        )

        self.db.add(baseline)
        self.db.commit()
        self.db.refresh(baseline)

        logger.info(f"Baseline created: id={baseline.id}")

        return {
            "success": True,
            "baseline_id": str(baseline.id),
            "calibration_type": calibration_type.value,
            "frequency_mhz": frequency_mhz,
            "reference_channel_id": reference_channel_id,
            "total_channels": total_channels,
            "delta_channels": len(delta_matrix),
            "valid_until": baseline.valid_until.isoformat(),
            "created_at": baseline.baseline_date.isoformat(),
        }

    def quick_calibrate(
        self,
        chamber_id: UUID,
        calibration_type: CalibrationType,
        frequency_mhz: float,
    ) -> QuickCalibrationResult:
        """
        快速校准
        
        仅测量参考通道，基于 Delta 基线推导其他通道数值。
        
        Args:
            chamber_id: 暗室 ID
            calibration_type: 校准类型
            frequency_mhz: 校准频率
            
        Returns:
            快速校准结果
        """
        logger.info(
            f"Quick calibration: chamber={chamber_id}, type={calibration_type}, "
            f"freq={frequency_mhz}MHz"
        )

        # 获取有效基线
        baseline = self._get_valid_baseline(chamber_id, calibration_type, frequency_mhz)
        
        if not baseline:
            raise ValueError(
                f"No valid baseline found for {calibration_type} at {frequency_mhz}MHz. "
                "Please create a baseline first."
            )

        # 仅测量参考通道
        ref_measurement = self._measure_single_channel(
            chamber_id, calibration_type, frequency_mhz, baseline.reference_channel_id
        )

        # 推导其他通道
        derived_channels = []
        reference_value_db = ref_measurement["amplitude_db"]
        reference_value_deg = ref_measurement["phase_deg"]

        for channel_id_str, delta in baseline.delta_matrix.items():
            channel_id = int(channel_id_str)
            derived_db = reference_value_db + delta["delta_db"]
            derived_deg = reference_value_deg + delta["delta_deg"]
            
            derived_channels.append({
                "channel_id": channel_id,
                "derived_amplitude_db": derived_db,
                "derived_phase_deg": derived_deg,
                "delta_db": delta["delta_db"],
                "delta_deg": delta["delta_deg"],
            })

        # 漂移检测
        drift_db = abs(reference_value_db - baseline.reference_value_db)
        drift_deg = abs(reference_value_deg - baseline.reference_value_deg)
        drift_detected = (
            drift_db > baseline.drift_threshold_db or
            drift_deg > baseline.drift_threshold_deg
        )

        # 更新基线的漂移检测记录
        baseline.last_drift_check_at = datetime.utcnow()
        baseline.last_drift_db = drift_db
        baseline.last_drift_deg = drift_deg
        baseline.drift_within_threshold = not drift_detected
        self.db.commit()

        return QuickCalibrationResult(
            success=True,
            calibration_type=calibration_type.value,
            frequency_mhz=frequency_mhz,
            reference_channel_id=baseline.reference_channel_id,
            reference_value_db=reference_value_db,
            derived_channels=derived_channels,
            drift_detected=drift_detected,
            max_drift_db=drift_db,
            max_drift_deg=drift_deg,
            calibrated_at=datetime.utcnow(),
        )

    def check_drift(
        self,
        chamber_id: UUID,
        calibration_type: CalibrationType,
        frequency_mhz: float,
    ) -> DriftCheckResult:
        """
        漂移检测
        
        对比当前测量值与基线，检测是否存在超阈值漂移。
        
        Args:
            chamber_id: 暗室 ID
            calibration_type: 校准类型
            frequency_mhz: 校准频率
            
        Returns:
            漂移检测结果
        """
        logger.info(f"Checking drift: chamber={chamber_id}, type={calibration_type}")

        # 获取基线
        baseline = self._get_valid_baseline(chamber_id, calibration_type, frequency_mhz)
        
        if not baseline:
            raise ValueError("No valid baseline found")

        # 测量所有通道
        measurements = self._measure_all_channels(
            chamber_id, calibration_type, frequency_mhz, baseline.total_channels
        )

        # 计算当前 Delta
        ref_value = measurements[baseline.reference_channel_id]
        channels_exceeding = []
        max_drift_db = 0.0
        max_drift_deg = 0.0

        for channel_id_str, original_delta in baseline.delta_matrix.items():
            channel_id = int(channel_id_str)
            current_value = measurements[channel_id]
            
            current_delta_db = current_value["amplitude_db"] - ref_value["amplitude_db"]
            current_delta_deg = current_value["phase_deg"] - ref_value["phase_deg"]
            
            drift_db = abs(current_delta_db - original_delta["delta_db"])
            drift_deg = abs(current_delta_deg - original_delta["delta_deg"])
            
            max_drift_db = max(max_drift_db, drift_db)
            max_drift_deg = max(max_drift_deg, drift_deg)
            
            if drift_db > baseline.drift_threshold_db or drift_deg > baseline.drift_threshold_deg:
                channels_exceeding.append(channel_id)

        within_threshold = len(channels_exceeding) == 0

        # 生成建议
        if within_threshold:
            recommendation = "漂移在阈值范围内，基线有效"
        elif len(channels_exceeding) <= 2:
            recommendation = f"通道 {channels_exceeding} 漂移超阈值，建议检查或重新建立基线"
        else:
            recommendation = "多个通道漂移超阈值，建议重新执行全量校准"

        # 更新基线记录
        baseline.last_drift_check_at = datetime.utcnow()
        baseline.last_drift_db = max_drift_db
        baseline.last_drift_deg = max_drift_deg
        baseline.drift_within_threshold = within_threshold
        self.db.commit()

        return DriftCheckResult(
            baseline_id=str(baseline.id),
            within_threshold=within_threshold,
            max_drift_db=max_drift_db,
            max_drift_deg=max_drift_deg,
            channels_exceeding_threshold=channels_exceeding,
            recommendation=recommendation,
        )

    def get_baseline_status(self, chamber_id: UUID) -> List[BaselineStatus]:
        """
        获取暗室所有基线的状态
        
        Args:
            chamber_id: 暗室 ID
            
        Returns:
            基线状态列表
        """
        from app.models.probe_calibration import CalibrationBaseline

        baselines = self.db.query(CalibrationBaseline).filter(
            CalibrationBaseline.chamber_id == chamber_id
        ).order_by(desc(CalibrationBaseline.baseline_date)).all()

        result = []
        now = datetime.utcnow()

        for bl in baselines:
            days_remaining = (bl.valid_until - now).days if bl.valid_until > now else 0
            
            result.append(BaselineStatus(
                calibration_type=bl.calibration_type,
                frequency_mhz=bl.frequency_mhz,
                status=bl.status,
                baseline_date=bl.baseline_date,
                valid_until=bl.valid_until,
                days_remaining=days_remaining,
                total_channels=bl.total_channels or 0,
                reference_channel_id=bl.reference_channel_id,
                drift_within_threshold=bl.drift_within_threshold,
            ))

        return result

    def invalidate_baseline(self, baseline_id: UUID) -> bool:
        """使基线失效"""
        from app.models.probe_calibration import CalibrationBaseline, CalibrationStatus

        baseline = self.db.query(CalibrationBaseline).filter(
            CalibrationBaseline.id == baseline_id
        ).first()

        if baseline:
            baseline.status = CalibrationStatus.INVALIDATED.value
            self.db.commit()
            return True
        return False

    # ==================== 私有方法 ====================

    def _get_total_channels(self, chamber_id: UUID) -> int:
        """获取暗室通道数"""
        # 从暗室配置获取，默认 16 通道
        try:
            from app.models.chamber import ChamberConfiguration
            chamber = self.db.query(ChamberConfiguration).filter(
                ChamberConfiguration.id == chamber_id
            ).first()
            return chamber.num_probes if chamber else 16
        except Exception:
            return 16

    def _get_valid_baseline(
        self,
        chamber_id: UUID,
        calibration_type: CalibrationType,
        frequency_mhz: float,
    ):
        """获取有效基线"""
        from app.models.probe_calibration import CalibrationBaseline, CalibrationStatus

        return self.db.query(CalibrationBaseline).filter(
            CalibrationBaseline.chamber_id == chamber_id,
            CalibrationBaseline.calibration_type == calibration_type.value,
            CalibrationBaseline.frequency_mhz == frequency_mhz,
            CalibrationBaseline.status == CalibrationStatus.VALID.value,
            CalibrationBaseline.valid_until > datetime.utcnow(),
        ).order_by(desc(CalibrationBaseline.baseline_date)).first()

    def _measure_all_channels(
        self,
        chamber_id: UUID,
        calibration_type: CalibrationType,
        frequency_mhz: float,
        total_channels: int,
    ) -> Dict[int, Dict[str, float]]:
        """测量所有通道"""
        if self.use_mock:
            return self._generate_mock_measurements(total_channels, calibration_type)
        
        # TODO: 集成真实 HAL 仪器驱动
        raise NotImplementedError("Real measurement not implemented")

    def _measure_single_channel(
        self,
        chamber_id: UUID,
        calibration_type: CalibrationType,
        frequency_mhz: float,
        channel_id: int,
    ) -> Dict[str, float]:
        """测量单个通道"""
        if self.use_mock:
            # 生成模拟数据，添加少量随机漂移
            base_amplitude = -45.0 + channel_id * 0.5
            base_phase = channel_id * 10.0
            
            return {
                "amplitude_db": base_amplitude + np.random.uniform(-0.2, 0.2),
                "phase_deg": base_phase + np.random.uniform(-1.0, 1.0),
            }
        
        # TODO: 集成真实 HAL 仪器驱动
        raise NotImplementedError("Real measurement not implemented")

    def _generate_mock_measurements(
        self,
        total_channels: int,
        calibration_type: CalibrationType,
    ) -> Dict[int, Dict[str, float]]:
        """生成模拟测量数据"""
        measurements = {}
        
        for ch in range(total_channels):
            # 模拟真实场景：各通道有固有偏差
            base_amplitude = -45.0 + ch * 0.5  # 基础幅度
            base_phase = ch * 10.0  # 基础相位（模拟线阵延迟）
            
            measurements[ch] = {
                "amplitude_db": base_amplitude + np.random.uniform(-0.1, 0.1),
                "phase_deg": base_phase + np.random.uniform(-0.5, 0.5),
            }
        
        return measurements
