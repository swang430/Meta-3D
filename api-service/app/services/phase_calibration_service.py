"""
Phase Calibration Service

相位校准服务 - 确保 MIMO 通道间相位一致性。

CAL-04: 完善相位校准链路

核心功能:
1. 通道间相位偏移测量 (Inter-channel Phase Offset)
2. 相位一致性验证 (Phase Coherence Validation)
3. 相位补偿应用 (Phase Correction Application)

物理原理:
- MIMO 系统中，各通道间的相位一致性对波束赋形和空间复用至关重要
- 相位偏移来源：电缆长度差异、RF 组件相位响应、温度漂移
- 校准目标：通道间相位偏移 < ±10° (典型要求)
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.probe_calibration import ChannelPhaseCalibration

logger = logging.getLogger(__name__)


# ==================== 常量定义 ====================

# 相位校准有效期 (天)
PHASE_CALIBRATION_VALIDITY_DAYS = 30

# 相位一致性门限 (度)
PHASE_COHERENCE_THRESHOLD_DEG = 10.0

# 相位漂移警告门限 (度)
PHASE_DRIFT_WARNING_THRESHOLD_DEG = 5.0

# 参考通道索引
REFERENCE_CHANNEL_INDEX = 0


# ==================== 数据模型 ====================

class PhaseCalibrationStatus(str, Enum):
    """相位校准状态"""
    NOT_CALIBRATED = "not_calibrated"
    CALIBRATED = "calibrated"
    EXPIRED = "expired"
    DRIFT_WARNING = "drift_warning"
    FAILED = "failed"


@dataclass
class ChannelPhaseData:
    """通道相位数据"""
    channel_id: int
    frequency_mhz: float
    phase_offset_deg: float
    amplitude_db: float
    measurement_time: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "channel_id": self.channel_id,
            "frequency_mhz": self.frequency_mhz,
            "phase_offset_deg": self.phase_offset_deg,
            "amplitude_db": self.amplitude_db,
            "measurement_time": self.measurement_time.isoformat()
        }


@dataclass
class PhaseCalibrationResult:
    """相位校准结果"""
    id: UUID
    chamber_id: UUID
    frequency_mhz: float
    reference_channel: int
    channel_phases: List[ChannelPhaseData]
    coherence_score: float  # 0-1, 1 表示完全一致
    max_phase_deviation_deg: float
    rms_phase_error_deg: float
    pass_threshold: bool
    calibrated_at: datetime
    valid_until: datetime
    calibrated_by: str
    
    def to_dict(self) -> Dict:
        return {
            "id": str(self.id),
            "chamber_id": str(self.chamber_id),
            "frequency_mhz": self.frequency_mhz,
            "reference_channel": self.reference_channel,
            "channel_phases": [cp.to_dict() for cp in self.channel_phases],
            "coherence_score": self.coherence_score,
            "max_phase_deviation_deg": self.max_phase_deviation_deg,
            "rms_phase_error_deg": self.rms_phase_error_deg,
            "pass_threshold": self.pass_threshold,
            "calibrated_at": self.calibrated_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "calibrated_by": self.calibrated_by
        }


@dataclass
class PhaseCompensation:
    """相位补偿值"""
    channel_id: int
    frequency_mhz: float
    phase_correction_deg: float
    amplitude_correction_db: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "channel_id": self.channel_id,
            "frequency_mhz": self.frequency_mhz,
            "phase_correction_deg": self.phase_correction_deg,
            "amplitude_correction_db": self.amplitude_correction_db
        }


@dataclass
class PhaseCoherenceStatus:
    """相位一致性状态"""
    chamber_id: UUID
    status: PhaseCalibrationStatus
    coherence_score: float
    max_deviation_deg: float
    last_calibration: Optional[datetime]
    days_until_expiry: Optional[int]
    channels_requiring_attention: List[int]
    
    def to_dict(self) -> Dict:
        return {
            "chamber_id": str(self.chamber_id),
            "status": self.status.value,
            "coherence_score": self.coherence_score,
            "max_deviation_deg": self.max_deviation_deg,
            "last_calibration": self.last_calibration.isoformat() if self.last_calibration else None,
            "days_until_expiry": self.days_until_expiry,
            "channels_requiring_attention": self.channels_requiring_attention
        }


# ==================== 算法函数 ====================

def calculate_phase_coherence(phase_offsets_deg: np.ndarray) -> Tuple[float, float, float]:
    """
    计算相位一致性
    
    使用圆形统计 (circular statistics) 计算相位分散度。
    
    Args:
        phase_offsets_deg: 各通道相位偏移数组 (度)
        
    Returns:
        (coherence_score, max_deviation_deg, rms_error_deg)
        - coherence_score: 0-1, 1 表示所有相位完全一致
        - max_deviation_deg: 最大相位偏差
        - rms_error_deg: RMS 相位误差
    """
    # 转换为弧度
    phases_rad = np.deg2rad(phase_offsets_deg)
    
    # 计算单位向量的均值 (圆形统计)
    mean_sin = np.mean(np.sin(phases_rad))
    mean_cos = np.mean(np.cos(phases_rad))
    
    # 结果长度 R (0-1)
    # R = 1 表示所有相位相同，R = 0 表示相位均匀分布
    coherence_score = np.sqrt(mean_sin**2 + mean_cos**2)
    
    # 计算相对于参考通道的偏差
    reference_phase = phase_offsets_deg[REFERENCE_CHANNEL_INDEX]
    deviations = phase_offsets_deg - reference_phase
    
    # 将偏差映射到 [-180, 180]
    deviations = np.mod(deviations + 180, 360) - 180
    
    max_deviation_deg = np.max(np.abs(deviations))
    rms_error_deg = np.sqrt(np.mean(deviations**2))
    
    return coherence_score, max_deviation_deg, rms_error_deg


def generate_mock_phase_data(
    num_channels: int,
    frequency_mhz: float,
    phase_drift_deg: float = 5.0
) -> List[ChannelPhaseData]:
    """
    生成模拟相位测量数据 (用于测试)
    
    Args:
        num_channels: 通道数量
        frequency_mhz: 测量频率
        phase_drift_deg: 模拟的相位漂移标准差
        
    Returns:
        各通道的相位数据列表
    """
    np.random.seed(int(frequency_mhz * 100) % 2**31)
    
    channel_phases = []
    for ch in range(num_channels):
        # 模拟相位偏移 (参考通道为 0)
        if ch == REFERENCE_CHANNEL_INDEX:
            phase_offset = 0.0
        else:
            # 添加系统偏移和随机偏移
            system_offset = (ch * 15) % 360 - 180  # 系统性偏移
            random_offset = np.random.normal(0, phase_drift_deg)
            phase_offset = system_offset + random_offset
        
        # 模拟幅度
        amplitude_db = -30 + np.random.normal(0, 0.5)
        
        channel_phases.append(ChannelPhaseData(
            channel_id=ch,
            frequency_mhz=frequency_mhz,
            phase_offset_deg=phase_offset,
            amplitude_db=amplitude_db
        ))
    
    return channel_phases


# ==================== 服务类 ====================

class PhaseCalibrationService:
    """
    相位校准服务
    
    负责执行和管理 MIMO 通道间的相位校准。
    """
    
    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock
        self._calibration_cache: Dict[UUID, PhaseCalibrationResult] = {}
    
    async def measure_channel_phases(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        num_channels: int = 32,
        reference_channel: int = REFERENCE_CHANNEL_INDEX
    ) -> List[ChannelPhaseData]:
        """
        测量各通道的相位
        
        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 测量频率
            num_channels: 通道数量
            reference_channel: 参考通道索引
            
        Returns:
            各通道的相位测量数据
        """
        logger.info(f"开始相位测量: chamber={chamber_id}, freq={frequency_mhz} MHz")
        
        if self.use_mock:
            # 使用模拟数据
            channel_phases = generate_mock_phase_data(
                num_channels=num_channels,
                frequency_mhz=frequency_mhz
            )
        else:
            # TODO: 实际仪器测量
            # 需要：
            # 1. 配置信号发生器发送参考信号
            # 2. 依次切换到各通道
            # 3. 使用 VNA 或相位计测量相位
            raise NotImplementedError("真实仪器相位测量尚未实现")
        
        return channel_phases
    
    async def calibrate_phases(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        num_channels: int = 32,
        calibrated_by: str = "system"
    ) -> PhaseCalibrationResult:
        """
        执行相位校准
        
        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 校准频率
            num_channels: 通道数量
            calibrated_by: 校准人员
            
        Returns:
            相位校准结果
        """
        logger.info(f"执行相位校准: chamber={chamber_id}, freq={frequency_mhz} MHz")
        
        # 测量各通道相位
        channel_phases = await self.measure_channel_phases(
            chamber_id=chamber_id,
            frequency_mhz=frequency_mhz,
            num_channels=num_channels
        )
        
        # 计算相位一致性
        phase_offsets = np.array([cp.phase_offset_deg for cp in channel_phases])
        coherence_score, max_deviation, rms_error = calculate_phase_coherence(phase_offsets)
        
        # 判断是否通过
        pass_threshold = max_deviation <= PHASE_COHERENCE_THRESHOLD_DEG
        
        # 创建校准结果
        calibration_result = PhaseCalibrationResult(
            id=uuid4(),
            chamber_id=chamber_id,
            frequency_mhz=frequency_mhz,
            reference_channel=REFERENCE_CHANNEL_INDEX,
            channel_phases=channel_phases,
            coherence_score=coherence_score,
            max_phase_deviation_deg=max_deviation,
            rms_phase_error_deg=rms_error,
            pass_threshold=pass_threshold,
            calibrated_at=datetime.now(),
            valid_until=datetime.now() + timedelta(days=PHASE_CALIBRATION_VALIDITY_DAYS),
            calibrated_by=calibrated_by
        )
        
        # 缓存结果
        self._calibration_cache[chamber_id] = calibration_result
        
        # 持久化到数据库
        try:
            db_record = ChannelPhaseCalibration(
                id=calibration_result.id,
                chamber_id=chamber_id,
                frequency_mhz=frequency_mhz,
                reference_channel_id=REFERENCE_CHANNEL_INDEX,
                channel_phases=[cp.to_dict() for cp in channel_phases],
                coherence_score=coherence_score,
                max_phase_deviation_deg=max_deviation,
                mean_phase_deviation_deg=rms_error,
                std_phase_deviation_deg=float(np.std(phase_offsets)),
                phase_compensation=[
                    {"channel_id": cp.channel_id, "compensation_deg": -cp.phase_offset_deg}
                    for cp in channel_phases
                ],
                compensation_applied=False,
                measurement_method="vna",
                calibrated_at=calibration_result.calibrated_at,
                calibrated_by=calibrated_by,
                valid_until=calibration_result.valid_until,
                status="valid" if pass_threshold else "failed"
            )
            self.db.add(db_record)
            self.db.commit()
            logger.info(f"相位校准结果已持久化到数据库: {calibration_result.id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"相位校准结果持久化失败: {e}")
        
        logger.info(
            f"相位校准完成: coherence={coherence_score:.3f}, "
            f"max_deviation={max_deviation:.2f}°, pass={pass_threshold}"
        )
        
        return calibration_result
    
    def get_phase_coherence_status(
        self,
        chamber_id: UUID
    ) -> PhaseCoherenceStatus:
        """
        获取相位一致性状态
        
        Args:
            chamber_id: 暗室配置 ID
            
        Returns:
            相位一致性状态
        """
        # 从缓存获取
        calibration = self._calibration_cache.get(chamber_id)
        
        # 缓存未命中，回退到数据库
        if calibration is None:
            db_record = self.db.query(ChannelPhaseCalibration).filter(
                ChannelPhaseCalibration.chamber_id == chamber_id,
                ChannelPhaseCalibration.status == "valid"
            ).order_by(desc(ChannelPhaseCalibration.calibrated_at)).first()
            
            if db_record:
                # 从 DB 重建缓存对象
                channel_phases_data = db_record.channel_phases or []
                channel_phases = [
                    ChannelPhaseData(
                        channel_id=cp["channel_id"],
                        frequency_mhz=db_record.frequency_mhz,
                        phase_offset_deg=cp.get("phase_offset_deg", 0.0),
                        amplitude_db=cp.get("amplitude_db", 0.0)
                    )
                    for cp in channel_phases_data
                ]
                calibration = PhaseCalibrationResult(
                    id=db_record.id,
                    chamber_id=chamber_id,
                    frequency_mhz=db_record.frequency_mhz,
                    reference_channel=db_record.reference_channel_id or 0,
                    channel_phases=channel_phases,
                    coherence_score=db_record.coherence_score or 0.0,
                    max_phase_deviation_deg=db_record.max_phase_deviation_deg or 0.0,
                    rms_phase_error_deg=db_record.mean_phase_deviation_deg or 0.0,
                    pass_threshold=(db_record.max_phase_deviation_deg or 999) <= PHASE_COHERENCE_THRESHOLD_DEG,
                    calibrated_at=db_record.calibrated_at,
                    valid_until=db_record.valid_until,
                    calibrated_by=db_record.calibrated_by or "Unknown"
                )
                # 回填缓存
                self._calibration_cache[chamber_id] = calibration
                logger.info(f"从数据库加载相位校准数据: {db_record.id}")
        
        if calibration is None:
            return PhaseCoherenceStatus(
                chamber_id=chamber_id,
                status=PhaseCalibrationStatus.NOT_CALIBRATED,
                coherence_score=0.0,
                max_deviation_deg=0.0,
                last_calibration=None,
                days_until_expiry=None,
                channels_requiring_attention=[]
            )
        
        # 检查有效期
        now = datetime.now()
        if now > calibration.valid_until:
            status = PhaseCalibrationStatus.EXPIRED
            days_until_expiry = 0
        else:
            days_until_expiry = (calibration.valid_until - now).days
            if calibration.max_phase_deviation_deg > PHASE_DRIFT_WARNING_THRESHOLD_DEG:
                status = PhaseCalibrationStatus.DRIFT_WARNING
            else:
                status = PhaseCalibrationStatus.CALIBRATED
        
        # 找出需要关注的通道
        channels_requiring_attention = []
        for cp in calibration.channel_phases:
            if abs(cp.phase_offset_deg) > PHASE_DRIFT_WARNING_THRESHOLD_DEG:
                channels_requiring_attention.append(cp.channel_id)
        
        return PhaseCoherenceStatus(
            chamber_id=chamber_id,
            status=status,
            coherence_score=calibration.coherence_score,
            max_deviation_deg=calibration.max_phase_deviation_deg,
            last_calibration=calibration.calibrated_at,
            days_until_expiry=days_until_expiry,
            channels_requiring_attention=channels_requiring_attention
        )
    
    def calculate_phase_compensation(
        self,
        chamber_id: UUID,
        frequency_mhz: float
    ) -> List[PhaseCompensation]:
        """
        计算相位补偿值
        
        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 目标频率
            
        Returns:
            各通道的相位补偿值
        """
        calibration = self._calibration_cache.get(chamber_id)
        
        # 缓存未命中，尝试从 DB 加载
        if calibration is None:
            db_record = self.db.query(ChannelPhaseCalibration).filter(
                ChannelPhaseCalibration.chamber_id == chamber_id,
                ChannelPhaseCalibration.status == "valid"
            ).order_by(desc(ChannelPhaseCalibration.calibrated_at)).first()
            
            if db_record and db_record.channel_phases:
                channel_phases = [
                    ChannelPhaseData(
                        channel_id=cp["channel_id"],
                        frequency_mhz=db_record.frequency_mhz,
                        phase_offset_deg=cp.get("phase_offset_deg", 0.0),
                        amplitude_db=cp.get("amplitude_db", 0.0)
                    )
                    for cp in db_record.channel_phases
                ]
                calibration = PhaseCalibrationResult(
                    id=db_record.id,
                    chamber_id=chamber_id,
                    frequency_mhz=db_record.frequency_mhz,
                    reference_channel=db_record.reference_channel_id or 0,
                    channel_phases=channel_phases,
                    coherence_score=db_record.coherence_score or 0.0,
                    max_phase_deviation_deg=db_record.max_phase_deviation_deg or 0.0,
                    rms_phase_error_deg=db_record.mean_phase_deviation_deg or 0.0,
                    pass_threshold=True,
                    calibrated_at=db_record.calibrated_at,
                    valid_until=db_record.valid_until,
                    calibrated_by=db_record.calibrated_by or "Unknown"
                )
                self._calibration_cache[chamber_id] = calibration
        
        if calibration is None:
            logger.warning(f"暗室 {chamber_id} 无相位校准数据")
            return []
        
        compensations = []
        for cp in calibration.channel_phases:
            # 补偿值 = 负的测量偏移
            compensations.append(PhaseCompensation(
                channel_id=cp.channel_id,
                frequency_mhz=cp.frequency_mhz,
                phase_correction_deg=-cp.phase_offset_deg,
                amplitude_correction_db=0.0  # 可选的幅度补偿
            ))
        
        return compensations
    
    def apply_phase_compensation(
        self,
        signal_phases_deg: np.ndarray,
        compensations: List[PhaseCompensation]
    ) -> np.ndarray:
        """
        应用相位补偿
        
        Args:
            signal_phases_deg: 原始信号相位数组
            compensations: 补偿值列表
            
        Returns:
            补偿后的相位数组
        """
        corrected_phases = signal_phases_deg.copy()
        
        for comp in compensations:
            if comp.channel_id < len(corrected_phases):
                corrected_phases[comp.channel_id] += comp.phase_correction_deg
        
        # 归一化到 [-180, 180]
        corrected_phases = np.mod(corrected_phases + 180, 360) - 180
        
        return corrected_phases
    
    async def verify_phase_coherence(
        self,
        chamber_id: UUID,
        frequency_mhz: float
    ) -> Dict:
        """
        验证相位一致性
        
        在应用补偿后重新测量，验证补偿效果。
        
        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 验证频率
            
        Returns:
            验证结果
        """
        logger.info(f"验证相位一致性: chamber={chamber_id}")
        
        # 获取当前补偿值
        compensations = self.calculate_phase_compensation(chamber_id, frequency_mhz)
        
        if not compensations:
            return {
                "verification_passed": False,
                "error": "无校准数据，请先执行相位校准"
            }
        
        # 重新测量
        channel_phases = await self.measure_channel_phases(
            chamber_id=chamber_id,
            frequency_mhz=frequency_mhz
        )
        
        # 模拟应用补偿后的效果
        original_phases = np.array([cp.phase_offset_deg for cp in channel_phases])
        compensated_phases = self.apply_phase_compensation(original_phases, compensations)
        
        # 计算补偿后的一致性
        coherence, max_dev, rms_err = calculate_phase_coherence(compensated_phases)
        
        verification_passed = max_dev <= PHASE_COHERENCE_THRESHOLD_DEG
        
        return {
            "verification_passed": verification_passed,
            "original_max_deviation_deg": float(np.max(np.abs(original_phases))),
            "compensated_max_deviation_deg": float(max_dev),
            "coherence_score": float(coherence),
            "rms_error_deg": float(rms_err),
            "improvement_db": float(
                20 * np.log10(np.max(np.abs(original_phases)) / max_dev)
            ) if max_dev > 0 else float('inf')
        }
