"""
Probe Calibration Services

探头校准业务逻辑实现。

TASK-P04: 幅度校准服务层
- 增益计算算法
- 互易性验证 (|Tx - Rx| < 0.5 dB)
- 不确定度评估

参考: docs/features/calibration/probe-calibration.md
"""
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging

from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    ProbePhaseCalibration,
    ProbePolarizationCalibration,
    ProbePattern,
    LinkCalibration,
    ProbeCalibrationValidity,
    CalibrationStatus,
    Polarization,
)
from app.schemas.probe_calibration import (
    FrequencyRange,
    PolarizationType,
    CalibrationJobStatus,
)

logger = logging.getLogger(__name__)


# ==================== 校准常数 ====================

# 互易性验证阈值 (dB)
RECIPROCITY_THRESHOLD_DB = 0.5

# 增益不确定度上限 (dB)
MAX_GAIN_UNCERTAINTY_DB = 0.3

# 校准有效期 (天)
DEFAULT_VALIDITY_DAYS = 90

# 探头 ID 范围
PROBE_ID_MIN = 0
PROBE_ID_MAX = 63


# ==================== 数据类 ====================

class GainMeasurement:
    """增益测量结果"""
    def __init__(
        self,
        frequency_mhz: float,
        tx_gain_dbi: float,
        rx_gain_dbi: float,
        tx_uncertainty_db: float = 0.0,
        rx_uncertainty_db: float = 0.0
    ):
        self.frequency_mhz = frequency_mhz
        self.tx_gain_dbi = tx_gain_dbi
        self.rx_gain_dbi = rx_gain_dbi
        self.tx_uncertainty_db = tx_uncertainty_db
        self.rx_uncertainty_db = rx_uncertainty_db

    @property
    def reciprocity_error_db(self) -> float:
        """计算互易性误差"""
        return abs(self.tx_gain_dbi - self.rx_gain_dbi)

    @property
    def is_reciprocal(self) -> bool:
        """验证互易性"""
        return self.reciprocity_error_db < RECIPROCITY_THRESHOLD_DB


class CalibrationResult:
    """校准结果"""
    def __init__(
        self,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None
    ):
        self.success = success
        self.message = message
        self.data = data or {}
        self.warnings = warnings or []


# ==================== 增益计算算法 ====================

def calculate_gain_from_power(
    received_power_dbm: float,
    transmitted_power_dbm: float,
    path_loss_db: float,
    reference_gain_dbi: float = 0.0
) -> float:
    """
    根据功率测量计算增益

    公式: G = P_rx - P_tx + PathLoss + G_ref

    Args:
        received_power_dbm: 接收功率 (dBm)
        transmitted_power_dbm: 发射功率 (dBm)
        path_loss_db: 路径损耗 (dB)，正值
        reference_gain_dbi: 参考天线增益 (dBi)

    Returns:
        增益 (dBi)
    """
    gain_dbi = received_power_dbm - transmitted_power_dbm + path_loss_db + reference_gain_dbi
    return gain_dbi


def calculate_path_loss(
    frequency_mhz: float,
    distance_m: float
) -> float:
    """
    计算自由空间路径损耗 (Friis 公式)

    FSPL = 20*log10(d) + 20*log10(f) + 20*log10(4π/c)
         = 20*log10(d) + 20*log10(f) - 147.55  (d in m, f in Hz)
         = 20*log10(d) + 20*log10(f*1e6) - 147.55
         = 20*log10(d) + 20*log10(f) + 120 - 147.55
         = 20*log10(d) + 20*log10(f) - 27.55  (d in m, f in MHz)

    Args:
        frequency_mhz: 频率 (MHz)
        distance_m: 距离 (m)

    Returns:
        路径损耗 (dB)，正值
    """
    if distance_m <= 0 or frequency_mhz <= 0:
        raise ValueError("Distance and frequency must be positive")

    fspl_db = 20 * np.log10(distance_m) + 20 * np.log10(frequency_mhz) - 27.55
    return fspl_db


def calculate_uncertainty(
    measurement_std: float,
    systematic_error: float = 0.1,
    instrument_accuracy: float = 0.05,
    coverage_factor: float = 2.0
) -> float:
    """
    计算测量不确定度 (GUM 方法)

    u_c = k * sqrt(u_A^2 + u_B^2)

    Args:
        measurement_std: A 类不确定度 (测量标准差)
        systematic_error: B 类不确定度 (系统误差)
        instrument_accuracy: 仪器精度不确定度
        coverage_factor: 包含因子 (k=2 对应 95% 置信度)

    Returns:
        扩展不确定度 (dB)
    """
    u_a = measurement_std
    u_b = np.sqrt(systematic_error**2 + instrument_accuracy**2)
    u_combined = np.sqrt(u_a**2 + u_b**2)
    u_expanded = coverage_factor * u_combined
    return u_expanded


def verify_reciprocity(
    tx_gain_dbi: float,
    rx_gain_dbi: float,
    threshold_db: float = RECIPROCITY_THRESHOLD_DB
) -> Tuple[bool, float]:
    """
    验证探头互易性

    互易性原理: 对于互易天线，发射增益 = 接收增益

    Args:
        tx_gain_dbi: 发射增益 (dBi)
        rx_gain_dbi: 接收增益 (dBi)
        threshold_db: 允许误差阈值 (dB)

    Returns:
        (is_reciprocal, error_db)
    """
    error_db = abs(tx_gain_dbi - rx_gain_dbi)
    is_reciprocal = error_db < threshold_db
    return is_reciprocal, error_db


def generate_frequency_points(freq_range: FrequencyRange) -> List[float]:
    """
    根据频率范围生成频率点列表

    Args:
        freq_range: 频率范围配置

    Returns:
        频率点列表 (MHz)
    """
    freq_points = []
    freq = freq_range.start_mhz
    while freq <= freq_range.stop_mhz:
        freq_points.append(freq)
        freq += freq_range.step_mhz
    return freq_points


# ==================== 幅度校准服务 ====================

class AmplitudeCalibrationService:
    """
    幅度校准服务

    负责探头幅度校准的完整流程:
    1. 测量发射增益 (Tx Gain)
    2. 测量接收增益 (Rx Gain)
    3. 验证互易性
    4. 计算不确定度
    5. 保存校准记录
    """

    def __init__(self, instruments=None):
        """
        初始化服务

        Args:
            instruments: 仪器控制接口 (可选，用于实际测量)
        """
        self.instruments = instruments

    async def execute_amplitude_calibration(
        self,
        db: Session,
        probe_ids: List[int],
        polarizations: List[PolarizationType],
        frequency_range: FrequencyRange,
        calibrated_by: str,
        reference_antenna_id: Optional[str] = None,
        power_meter_id: Optional[str] = None,
        use_mock: bool = True
    ) -> CalibrationResult:
        """
        执行幅度校准

        Args:
            db: 数据库会话
            probe_ids: 要校准的探头 ID 列表
            polarizations: 要校准的极化类型列表
            frequency_range: 频率范围
            calibrated_by: 校准人员
            reference_antenna_id: 参考天线 ID
            power_meter_id: 功率计 ID
            use_mock: 是否使用 mock 数据

        Returns:
            CalibrationResult
        """
        logger.info(f"Starting amplitude calibration for probes {probe_ids}")

        # 验证探头 ID
        for probe_id in probe_ids:
            if probe_id < PROBE_ID_MIN or probe_id > PROBE_ID_MAX:
                return CalibrationResult(
                    success=False,
                    message=f"Invalid probe_id {probe_id}, must be {PROBE_ID_MIN}-{PROBE_ID_MAX}"
                )

        # 生成频率点
        freq_points = generate_frequency_points(frequency_range)
        num_points = len(freq_points)

        logger.info(f"Calibrating {len(probe_ids)} probes, {len(polarizations)} polarizations, {num_points} frequency points")

        calibration_ids = []
        warnings = []

        for probe_id in probe_ids:
            for pol in polarizations:
                try:
                    # 执行测量 (mock 或实际)
                    if use_mock:
                        measurements = self._mock_measurements(probe_id, pol, freq_points)
                    else:
                        measurements = await self._real_measurements(
                            probe_id, pol, freq_points,
                            reference_antenna_id, power_meter_id
                        )

                    # 提取数据
                    tx_gains = [m.tx_gain_dbi for m in measurements]
                    rx_gains = [m.rx_gain_dbi for m in measurements]
                    tx_uncertainties = [m.tx_uncertainty_db for m in measurements]
                    rx_uncertainties = [m.rx_uncertainty_db for m in measurements]

                    # 验证互易性
                    reciprocity_errors = [m.reciprocity_error_db for m in measurements]
                    max_reciprocity_error = max(reciprocity_errors)
                    if max_reciprocity_error >= RECIPROCITY_THRESHOLD_DB:
                        warnings.append(
                            f"Probe {probe_id} pol {pol.value}: reciprocity error {max_reciprocity_error:.2f} dB exceeds threshold"
                        )

                    # 创建校准记录
                    calibration = ProbeAmplitudeCalibration(
                        probe_id=probe_id,
                        polarization=pol.value,
                        frequency_points_mhz=freq_points,
                        tx_gain_dbi=tx_gains,
                        rx_gain_dbi=rx_gains,
                        tx_gain_uncertainty_db=tx_uncertainties,
                        rx_gain_uncertainty_db=rx_uncertainties,
                        reference_antenna=reference_antenna_id,
                        reference_power_meter=power_meter_id,
                        calibrated_at=datetime.utcnow(),
                        calibrated_by=calibrated_by,
                        valid_until=datetime.utcnow() + timedelta(days=DEFAULT_VALIDITY_DAYS),
                        status=CalibrationStatus.VALID
                    )

                    db.add(calibration)
                    db.flush()  # 获取 ID
                    calibration_ids.append(str(calibration.id))

                    logger.info(f"Probe {probe_id} pol {pol.value} calibration completed")

                except Exception as e:
                    logger.error(f"Calibration failed for probe {probe_id} pol {pol.value}: {e}")
                    return CalibrationResult(
                        success=False,
                        message=f"Calibration failed: {str(e)}"
                    )

        db.commit()

        return CalibrationResult(
            success=True,
            message=f"Calibration completed for {len(probe_ids)} probes",
            data={
                "calibration_ids": calibration_ids,
                "num_probes": len(probe_ids),
                "num_polarizations": len(polarizations),
                "num_frequencies": num_points
            },
            warnings=warnings
        )

    def _mock_measurements(
        self,
        probe_id: int,
        polarization: PolarizationType,
        freq_points: List[float]
    ) -> List[GainMeasurement]:
        """
        生成 mock 测量数据

        模拟真实的探头特性:
        - 基础增益约 5 dBi
        - 频率响应变化 (中频最佳)
        - 少量随机噪声
        - Tx/Rx 增益接近 (互易性)
        """
        measurements = []
        base_gain = 5.0  # dBi

        # 探头间的增益差异 (每个探头略有不同)
        probe_offset = (probe_id % 10 - 5) * 0.05  # ±0.25 dB

        # 极化差异
        pol_offset = 0.0 if polarization == PolarizationType.V else 0.1

        for freq in freq_points:
            # 频率响应 (3500 MHz 为最佳)
            freq_response = -0.001 * (freq - 3500) ** 2 / 10000

            # 随机噪声
            noise_tx = np.random.normal(0, 0.05)
            noise_rx = np.random.normal(0, 0.05)

            # 计算增益
            tx_gain = base_gain + probe_offset + pol_offset + freq_response + noise_tx
            rx_gain = base_gain + probe_offset + pol_offset + freq_response + noise_rx

            # 不确定度
            uncertainty = calculate_uncertainty(
                measurement_std=0.05,
                systematic_error=0.1,
                instrument_accuracy=0.05
            )

            measurements.append(GainMeasurement(
                frequency_mhz=freq,
                tx_gain_dbi=tx_gain,
                rx_gain_dbi=rx_gain,
                tx_uncertainty_db=uncertainty,
                rx_uncertainty_db=uncertainty
            ))

        return measurements

    async def _real_measurements(
        self,
        probe_id: int,
        polarization: PolarizationType,
        freq_points: List[float],
        reference_antenna_id: Optional[str],
        power_meter_id: Optional[str]
    ) -> List[GainMeasurement]:
        """
        执行实际测量 (需要仪器接口)

        TODO: 实现与实际仪器的通信
        """
        if not self.instruments:
            raise RuntimeError("No instruments connected for real measurements")

        # TODO: 实际测量实现
        # 1. 配置信号源频率
        # 2. 选择探头和极化
        # 3. 测量 Tx 功率
        # 4. 测量 Rx 功率
        # 5. 计算增益

        raise NotImplementedError("Real measurements not yet implemented")

    def get_latest_calibration(
        self,
        db: Session,
        probe_id: int,
        polarization: Optional[str] = None
    ) -> Optional[ProbeAmplitudeCalibration]:
        """
        获取探头的最新幅度校准记录

        Args:
            db: 数据库会话
            probe_id: 探头 ID
            polarization: 可选的极化过滤

        Returns:
            最新的校准记录，或 None
        """
        query = db.query(ProbeAmplitudeCalibration).filter(
            ProbeAmplitudeCalibration.probe_id == probe_id
        )

        if polarization:
            query = query.filter(ProbeAmplitudeCalibration.polarization == polarization)

        return query.order_by(desc(ProbeAmplitudeCalibration.calibrated_at)).first()

    def get_calibration_history(
        self,
        db: Session,
        probe_id: int,
        limit: int = 20
    ) -> List[ProbeAmplitudeCalibration]:
        """
        获取探头的校准历史

        Args:
            db: 数据库会话
            probe_id: 探头 ID
            limit: 返回记录数量

        Returns:
            校准历史列表
        """
        return db.query(ProbeAmplitudeCalibration).filter(
            ProbeAmplitudeCalibration.probe_id == probe_id
        ).order_by(
            desc(ProbeAmplitudeCalibration.calibrated_at)
        ).limit(limit).all()

    def analyze_gain_trend(
        self,
        calibrations: List[ProbeAmplitudeCalibration]
    ) -> Optional[Dict[str, Any]]:
        """
        分析增益变化趋势

        Args:
            calibrations: 校准记录列表 (按时间排序)

        Returns:
            趋势分析结果
        """
        if len(calibrations) < 3:
            return None

        # 计算平均增益
        avg_gains = []
        timestamps = []

        for cal in calibrations:
            if cal.tx_gain_dbi:
                avg_gain = sum(cal.tx_gain_dbi) / len(cal.tx_gain_dbi)
                avg_gains.append(avg_gain)
                timestamps.append(cal.calibrated_at)

        if len(avg_gains) < 3:
            return None

        # 线性回归计算漂移率
        time_days = [(t - timestamps[-1]).total_seconds() / 86400 for t in timestamps]
        slope, _ = np.polyfit(time_days, avg_gains, 1)

        # 月漂移率
        drift_per_month = slope * 30

        # 稳定性评级
        if abs(drift_per_month) < 0.05:
            stability = "excellent"
        elif abs(drift_per_month) < 0.1:
            stability = "good"
        elif abs(drift_per_month) < 0.2:
            stability = "acceptable"
        else:
            stability = "needs_attention"

        return {
            "amplitude_drift_db_per_month": round(drift_per_month, 4),
            "stability_rating": stability,
            "num_calibrations": len(avg_gains),
            "time_span_days": abs(time_days[0])
        }


# ==================== 相位校准服务 (TASK-P05) ====================

# 相位校准常数
PHASE_UNCERTAINTY_THRESHOLD_DEG = 5.0  # 相位不确定度上限 (度)
GROUP_DELAY_MAX_NS = 10.0  # 群时延上限 (ns)


class PhaseMeasurement:
    """相位测量结果"""
    def __init__(
        self,
        frequency_mhz: float,
        phase_offset_deg: float,
        group_delay_ns: float,
        uncertainty_deg: float = 0.0
    ):
        self.frequency_mhz = frequency_mhz
        self.phase_offset_deg = phase_offset_deg
        self.group_delay_ns = group_delay_ns
        self.uncertainty_deg = uncertainty_deg

    @property
    def is_valid(self) -> bool:
        """验证相位测量是否在有效范围内"""
        return (
            self.uncertainty_deg < PHASE_UNCERTAINTY_THRESHOLD_DEG and
            abs(self.group_delay_ns) < GROUP_DELAY_MAX_NS
        )


def calculate_group_delay(
    phase_deg: List[float],
    freq_mhz: List[float]
) -> List[float]:
    """
    计算群时延

    群时延 = -dφ/dω = -(1/360) * dφ/df  (单位: 秒)

    Args:
        phase_deg: 相位数组 (度)
        freq_mhz: 频率数组 (MHz)

    Returns:
        群时延数组 (ns)
    """
    if len(phase_deg) < 2:
        return [0.0]

    group_delays = []
    for i in range(len(phase_deg) - 1):
        d_phase = phase_deg[i + 1] - phase_deg[i]
        d_freq = (freq_mhz[i + 1] - freq_mhz[i]) * 1e6  # MHz to Hz

        if d_freq == 0:
            group_delays.append(0.0)
        else:
            # τ = -(1/360) * dφ/df (秒)
            tau_sec = -(d_phase / 360.0) / d_freq
            tau_ns = tau_sec * 1e9
            group_delays.append(tau_ns)

    # 最后一个点使用前一个值
    group_delays.append(group_delays[-1] if group_delays else 0.0)
    return group_delays


def unwrap_phase(phase_deg: List[float]) -> List[float]:
    """
    相位解缠绕

    将相位跳变 (>180°) 展开为连续相位

    Args:
        phase_deg: 原始相位数组 (度)

    Returns:
        解缠绕后的相位数组 (度)
    """
    if not phase_deg:
        return []

    unwrapped = [phase_deg[0]]
    for i in range(1, len(phase_deg)):
        diff = phase_deg[i] - phase_deg[i - 1]
        # 检测跳变
        while diff > 180:
            diff -= 360
        while diff < -180:
            diff += 360
        unwrapped.append(unwrapped[-1] + diff)

    return unwrapped


class PhaseCalibrationService:
    """
    相位校准服务

    负责探头相位校准的完整流程:
    1. 测量相对于参考探头的相位偏移
    2. 计算群时延
    3. 相位解缠绕
    4. 不确定度评估
    5. 保存校准记录
    """

    def __init__(self, instruments=None):
        self.instruments = instruments

    async def execute_phase_calibration(
        self,
        db: Session,
        probe_ids: List[int],
        polarizations: List[PolarizationType],
        frequency_range: FrequencyRange,
        reference_probe_id: int,
        calibrated_by: str,
        vna_id: Optional[str] = None,
        use_mock: bool = True
    ) -> CalibrationResult:
        """
        执行相位校准

        Args:
            db: 数据库会话
            probe_ids: 要校准的探头 ID 列表
            polarizations: 极化类型列表
            frequency_range: 频率范围
            reference_probe_id: 参考探头 ID
            calibrated_by: 校准人员
            vna_id: VNA 设备 ID
            use_mock: 是否使用 mock 数据

        Returns:
            CalibrationResult
        """
        logger.info(f"Starting phase calibration for probes {probe_ids}, ref={reference_probe_id}")

        # 验证探头 ID
        for probe_id in probe_ids:
            if probe_id < PROBE_ID_MIN or probe_id > PROBE_ID_MAX:
                return CalibrationResult(
                    success=False,
                    message=f"Invalid probe_id {probe_id}"
                )

        if reference_probe_id < PROBE_ID_MIN or reference_probe_id > PROBE_ID_MAX:
            return CalibrationResult(
                success=False,
                message=f"Invalid reference_probe_id {reference_probe_id}"
            )

        freq_points = generate_frequency_points(frequency_range)
        calibration_ids = []
        warnings = []

        for probe_id in probe_ids:
            for pol in polarizations:
                try:
                    if use_mock:
                        measurements = self._mock_phase_measurements(
                            probe_id, reference_probe_id, pol, freq_points
                        )
                    else:
                        measurements = await self._real_phase_measurements(
                            probe_id, reference_probe_id, pol, freq_points, vna_id
                        )

                    # 提取数据
                    phase_offsets = [m.phase_offset_deg for m in measurements]
                    group_delays = [m.group_delay_ns for m in measurements]
                    uncertainties = [m.uncertainty_deg for m in measurements]

                    # 检查不确定度
                    max_uncertainty = max(uncertainties)
                    if max_uncertainty >= PHASE_UNCERTAINTY_THRESHOLD_DEG:
                        warnings.append(
                            f"Probe {probe_id} pol {pol.value}: uncertainty {max_uncertainty:.1f}° exceeds threshold"
                        )

                    calibration = ProbePhaseCalibration(
                        probe_id=probe_id,
                        polarization=pol.value,
                        reference_probe_id=reference_probe_id,
                        frequency_points_mhz=freq_points,
                        phase_offset_deg=phase_offsets,
                        group_delay_ns=group_delays,
                        phase_uncertainty_deg=uncertainties,
                        vna_model="Mock VNA" if use_mock else vna_id,
                        calibrated_at=datetime.utcnow(),
                        calibrated_by=calibrated_by,
                        valid_until=datetime.utcnow() + timedelta(days=DEFAULT_VALIDITY_DAYS),
                        status=CalibrationStatus.VALID
                    )

                    db.add(calibration)
                    db.flush()
                    calibration_ids.append(str(calibration.id))

                except Exception as e:
                    logger.error(f"Phase calibration failed for probe {probe_id}: {e}")
                    return CalibrationResult(
                        success=False,
                        message=f"Calibration failed: {str(e)}"
                    )

        db.commit()

        return CalibrationResult(
            success=True,
            message=f"Phase calibration completed for {len(probe_ids)} probes",
            data={
                "calibration_ids": calibration_ids,
                "reference_probe_id": reference_probe_id
            },
            warnings=warnings
        )

    def _mock_phase_measurements(
        self,
        probe_id: int,
        reference_probe_id: int,
        polarization: PolarizationType,
        freq_points: List[float]
    ) -> List[PhaseMeasurement]:
        """生成 mock 相位测量数据"""
        measurements = []

        # 基于探头位置的相位偏移
        position_offset = (probe_id - reference_probe_id) * 12.0  # 每个探头约 12° 差异

        # 频率相关的相位变化
        for i, freq in enumerate(freq_points):
            # 频率引起的相位变化 (线性近似)
            freq_phase = 0.1 * (freq - freq_points[0])

            # 添加噪声
            noise = np.random.normal(0, 1.5)

            phase_offset = position_offset + freq_phase + noise

            # 群时延
            base_delay = 0.8 + (probe_id % 10) * 0.05
            delay_noise = np.random.normal(0, 0.03)
            group_delay = base_delay + delay_noise

            measurements.append(PhaseMeasurement(
                frequency_mhz=freq,
                phase_offset_deg=phase_offset,
                group_delay_ns=group_delay,
                uncertainty_deg=3.0  # 典型不确定度
            ))

        return measurements

    async def _real_phase_measurements(
        self,
        probe_id: int,
        reference_probe_id: int,
        polarization: PolarizationType,
        freq_points: List[float],
        vna_id: Optional[str]
    ) -> List[PhaseMeasurement]:
        """执行实际相位测量"""
        if not self.instruments:
            raise RuntimeError("No instruments connected")
        raise NotImplementedError("Real phase measurements not yet implemented")

    def get_latest_calibration(
        self,
        db: Session,
        probe_id: int,
        polarization: Optional[str] = None
    ) -> Optional[ProbePhaseCalibration]:
        """获取最新相位校准记录"""
        query = db.query(ProbePhaseCalibration).filter(
            ProbePhaseCalibration.probe_id == probe_id
        )
        if polarization:
            query = query.filter(ProbePhaseCalibration.polarization == polarization)
        return query.order_by(desc(ProbePhaseCalibration.calibrated_at)).first()

    def analyze_phase_trend(
        self,
        calibrations: List[ProbePhaseCalibration]
    ) -> Optional[Dict[str, Any]]:
        """分析相位漂移趋势"""
        if len(calibrations) < 3:
            return None

        avg_phases = []
        timestamps = []

        for cal in calibrations:
            if cal.phase_offset_deg:
                avg_phase = sum(cal.phase_offset_deg) / len(cal.phase_offset_deg)
                avg_phases.append(avg_phase)
                timestamps.append(cal.calibrated_at)

        if len(avg_phases) < 3:
            return None

        time_days = [(t - timestamps[-1]).total_seconds() / 86400 for t in timestamps]
        slope, _ = np.polyfit(time_days, avg_phases, 1)
        drift_per_month = slope * 30

        if abs(drift_per_month) < 0.5:
            stability = "excellent"
        elif abs(drift_per_month) < 1.0:
            stability = "good"
        elif abs(drift_per_month) < 2.0:
            stability = "acceptable"
        else:
            stability = "needs_attention"

        return {
            "phase_drift_deg_per_month": round(drift_per_month, 3),
            "stability_rating": stability,
            "num_calibrations": len(avg_phases)
        }


# ==================== 极化校准服务 (TASK-P06) ====================

# 极化校准常数
XPD_MIN_THRESHOLD_DB = 20.0  # 交叉极化鉴别度最小值 (dB)
XPD_EXCELLENT_THRESHOLD_DB = 30.0  # 优秀 XPD 阈值 (dB)
AXIAL_RATIO_MAX_DB = 3.0  # 圆极化轴比上限 (dB)
AXIAL_RATIO_EXCELLENT_DB = 1.0  # 优秀轴比阈值 (dB)
POLARIZATION_VALIDITY_DAYS = 180  # 极化校准有效期 (天)


class PolarizationMeasurement:
    """极化测量结果"""
    def __init__(
        self,
        frequency_mhz: float,
        # 线极化数据
        v_to_h_isolation_db: Optional[float] = None,
        h_to_v_isolation_db: Optional[float] = None,
        # 圆极化数据
        axial_ratio_db: Optional[float] = None,
        polarization_hand: Optional[str] = None,
        # 不确定度
        uncertainty_db: float = 0.0
    ):
        self.frequency_mhz = frequency_mhz
        self.v_to_h_isolation_db = v_to_h_isolation_db
        self.h_to_v_isolation_db = h_to_v_isolation_db
        self.axial_ratio_db = axial_ratio_db
        self.polarization_hand = polarization_hand
        self.uncertainty_db = uncertainty_db

    @property
    def xpd_db(self) -> Optional[float]:
        """交叉极化鉴别度 (取较小值)"""
        if self.v_to_h_isolation_db is not None and self.h_to_v_isolation_db is not None:
            return min(self.v_to_h_isolation_db, self.h_to_v_isolation_db)
        return None

    @property
    def is_linear_valid(self) -> bool:
        """验证线极化是否合格"""
        xpd = self.xpd_db
        return xpd is not None and xpd >= XPD_MIN_THRESHOLD_DB

    @property
    def is_circular_valid(self) -> bool:
        """验证圆极化是否合格"""
        return self.axial_ratio_db is not None and self.axial_ratio_db <= AXIAL_RATIO_MAX_DB


def calculate_xpd(
    co_polar_power_dbm: float,
    cross_polar_power_dbm: float
) -> float:
    """
    计算交叉极化鉴别度 (XPD)

    XPD = P_co - P_cross (dB)

    Args:
        co_polar_power_dbm: 主极化功率 (dBm)
        cross_polar_power_dbm: 交叉极化功率 (dBm)

    Returns:
        XPD (dB)，正值表示良好隔离
    """
    return co_polar_power_dbm - cross_polar_power_dbm


def calculate_axial_ratio(
    e_major: float,
    e_minor: float
) -> float:
    """
    计算轴比 (Axial Ratio)

    AR = 20 * log10(E_major / E_minor) (dB)

    对于理想圆极化，AR = 0 dB (E_major = E_minor)

    Args:
        e_major: 椭圆主轴电场强度
        e_minor: 椭圆副轴电场强度

    Returns:
        轴比 (dB)，0 dB 为理想圆极化
    """
    if e_minor <= 0:
        return float('inf')
    if e_major < e_minor:
        # 交换，确保 major >= minor
        e_major, e_minor = e_minor, e_major
    return 20 * np.log10(e_major / e_minor)


def calculate_axial_ratio_from_amplitudes(
    e_lhcp: float,
    e_rhcp: float
) -> Tuple[float, str]:
    """
    从 LHCP 和 RHCP 分量计算轴比和旋向

    当 E_LHCP >> E_RHCP 时为 LHCP，反之为 RHCP

    Args:
        e_lhcp: 左旋圆极化分量振幅
        e_rhcp: 右旋圆极化分量振幅

    Returns:
        (axial_ratio_db, polarization_hand)
    """
    if e_lhcp <= 0 and e_rhcp <= 0:
        return float('inf'), "unknown"

    # 主旋向
    if e_lhcp >= e_rhcp:
        e_major = e_lhcp
        e_minor = e_rhcp
        hand = "LHCP"
    else:
        e_major = e_rhcp
        e_minor = e_lhcp
        hand = "RHCP"

    # 轴比
    if e_minor <= 0:
        ar_db = 40.0  # 限制最大值
    else:
        # AR = 20*log10((E_maj + E_min)/(E_maj - E_min))
        # 简化版：当 E_maj >> E_min 时，AR ≈ 20*log10(E_maj/E_min)
        ar_linear = (e_major + e_minor) / max(e_major - e_minor, 1e-10)
        ar_db = 20 * np.log10(ar_linear)

    return ar_db, hand


class PolarizationCalibrationService:
    """
    极化校准服务

    负责探头极化校准的完整流程:
    1. 线极化探头: 测量 V-H 交叉极化隔离度 (XPD)
    2. 圆极化探头: 测量轴比 (AR)
    3. 频率相关特性测量
    4. 保存校准记录
    """

    def __init__(self, instruments=None):
        self.instruments = instruments

    async def execute_polarization_calibration(
        self,
        db: Session,
        probe_ids: List[int],
        probe_type: str,
        frequency_range: FrequencyRange,
        calibrated_by: str,
        reference_antenna_id: Optional[str] = None,
        positioner_id: Optional[str] = None,
        use_mock: bool = True
    ) -> CalibrationResult:
        """
        执行极化校准

        Args:
            db: 数据库会话
            probe_ids: 要校准的探头 ID 列表
            probe_type: 探头类型 (dual_linear, dual_slant, circular)
            frequency_range: 频率范围
            calibrated_by: 校准人员
            reference_antenna_id: 参考天线 ID
            positioner_id: 转台 ID
            use_mock: 是否使用 mock 数据

        Returns:
            CalibrationResult
        """
        logger.info(f"Starting polarization calibration for probes {probe_ids}, type={probe_type}")

        # 验证探头 ID
        for probe_id in probe_ids:
            if probe_id < PROBE_ID_MIN or probe_id > PROBE_ID_MAX:
                return CalibrationResult(
                    success=False,
                    message=f"Invalid probe_id {probe_id}"
                )

        freq_points = generate_frequency_points(frequency_range)
        calibration_ids = []
        warnings = []

        for probe_id in probe_ids:
            try:
                if use_mock:
                    measurements = self._mock_polarization_measurements(
                        probe_id, probe_type, freq_points
                    )
                else:
                    measurements = await self._real_polarization_measurements(
                        probe_id, probe_type, freq_points,
                        reference_antenna_id, positioner_id
                    )

                # 根据探头类型提取数据
                if probe_type in ("dual_linear", "dual_slant"):
                    # 线极化
                    v_to_h_isolations = [m.v_to_h_isolation_db for m in measurements]
                    h_to_v_isolations = [m.h_to_v_isolation_db for m in measurements]

                    avg_v_to_h = sum(v_to_h_isolations) / len(v_to_h_isolations)
                    avg_h_to_v = sum(h_to_v_isolations) / len(h_to_v_isolations)

                    # 检查 XPD
                    min_xpd = min(min(v_to_h_isolations), min(h_to_v_isolations))
                    if min_xpd < XPD_MIN_THRESHOLD_DB:
                        warnings.append(
                            f"Probe {probe_id}: XPD {min_xpd:.1f} dB below threshold {XPD_MIN_THRESHOLD_DB} dB"
                        )

                    calibration = ProbePolarizationCalibration(
                        probe_id=probe_id,
                        probe_type=probe_type,
                        v_to_h_isolation_db=avg_v_to_h,
                        h_to_v_isolation_db=avg_h_to_v,
                        frequency_points_mhz=freq_points,
                        isolation_vs_frequency_db=v_to_h_isolations,  # 使用 V-H 作为主要指标
                        reference_antenna=reference_antenna_id,
                        positioner=positioner_id,
                        calibrated_at=datetime.utcnow(),
                        calibrated_by=calibrated_by,
                        valid_until=datetime.utcnow() + timedelta(days=POLARIZATION_VALIDITY_DAYS),
                        status=CalibrationStatus.VALID
                    )
                else:
                    # 圆极化
                    axial_ratios = [m.axial_ratio_db for m in measurements]
                    hand = measurements[0].polarization_hand if measurements else "LHCP"

                    avg_ar = sum(axial_ratios) / len(axial_ratios)

                    # 检查轴比
                    max_ar = max(axial_ratios)
                    if max_ar > AXIAL_RATIO_MAX_DB:
                        warnings.append(
                            f"Probe {probe_id}: Axial ratio {max_ar:.2f} dB exceeds threshold {AXIAL_RATIO_MAX_DB} dB"
                        )

                    calibration = ProbePolarizationCalibration(
                        probe_id=probe_id,
                        probe_type=probe_type,
                        polarization_hand=hand,
                        axial_ratio_db=avg_ar,
                        frequency_points_mhz=freq_points,
                        axial_ratio_vs_frequency_db=axial_ratios,
                        reference_antenna=reference_antenna_id,
                        positioner=positioner_id,
                        calibrated_at=datetime.utcnow(),
                        calibrated_by=calibrated_by,
                        valid_until=datetime.utcnow() + timedelta(days=POLARIZATION_VALIDITY_DAYS),
                        status=CalibrationStatus.VALID
                    )

                db.add(calibration)
                db.flush()
                calibration_ids.append(str(calibration.id))

            except Exception as e:
                logger.error(f"Polarization calibration failed for probe {probe_id}: {e}")
                return CalibrationResult(
                    success=False,
                    message=f"Calibration failed: {str(e)}"
                )

        db.commit()

        return CalibrationResult(
            success=True,
            message=f"Polarization calibration completed for {len(probe_ids)} probes",
            data={
                "calibration_ids": calibration_ids,
                "probe_type": probe_type
            },
            warnings=warnings
        )

    def _mock_polarization_measurements(
        self,
        probe_id: int,
        probe_type: str,
        freq_points: List[float]
    ) -> List[PolarizationMeasurement]:
        """生成 mock 极化测量数据"""
        measurements = []

        # 探头间的变异
        probe_variation = (probe_id % 10 - 5) * 0.5  # ±2.5 dB

        for freq in freq_points:
            # 频率响应 (中频最佳)
            freq_response = -0.01 * abs(freq - 3500)

            if probe_type in ("dual_linear", "dual_slant"):
                # 线极化: 生成 XPD 数据
                base_xpd = 28.0  # 典型 XPD 约 28 dB
                v_to_h = base_xpd + probe_variation + freq_response + np.random.normal(0, 1.0)
                h_to_v = base_xpd + probe_variation + freq_response + np.random.normal(0, 1.0)

                measurements.append(PolarizationMeasurement(
                    frequency_mhz=freq,
                    v_to_h_isolation_db=v_to_h,
                    h_to_v_isolation_db=h_to_v,
                    uncertainty_db=0.5
                ))
            else:
                # 圆极化: 生成轴比数据
                base_ar = 1.5  # 典型轴比约 1.5 dB
                ar = base_ar + abs(probe_variation * 0.2) + abs(freq_response * 0.1) + abs(np.random.normal(0, 0.2))
                # 旋向: 偶数探头 LHCP，奇数探头 RHCP
                hand = "LHCP" if probe_id % 2 == 0 else "RHCP"

                measurements.append(PolarizationMeasurement(
                    frequency_mhz=freq,
                    axial_ratio_db=ar,
                    polarization_hand=hand,
                    uncertainty_db=0.2
                ))

        return measurements

    async def _real_polarization_measurements(
        self,
        probe_id: int,
        probe_type: str,
        freq_points: List[float],
        reference_antenna_id: Optional[str],
        positioner_id: Optional[str]
    ) -> List[PolarizationMeasurement]:
        """执行实际极化测量"""
        if not self.instruments:
            raise RuntimeError("No instruments connected")
        raise NotImplementedError("Real polarization measurements not yet implemented")

    def get_latest_calibration(
        self,
        db: Session,
        probe_id: int
    ) -> Optional[ProbePolarizationCalibration]:
        """获取最新极化校准记录"""
        return db.query(ProbePolarizationCalibration).filter(
            ProbePolarizationCalibration.probe_id == probe_id
        ).order_by(desc(ProbePolarizationCalibration.calibrated_at)).first()

    def get_calibration_history(
        self,
        db: Session,
        probe_id: int,
        limit: int = 20
    ) -> List[ProbePolarizationCalibration]:
        """获取极化校准历史"""
        return db.query(ProbePolarizationCalibration).filter(
            ProbePolarizationCalibration.probe_id == probe_id
        ).order_by(
            desc(ProbePolarizationCalibration.calibrated_at)
        ).limit(limit).all()

    def evaluate_polarization_quality(
        self,
        calibration: ProbePolarizationCalibration
    ) -> Dict[str, Any]:
        """
        评估极化校准质量

        Args:
            calibration: 校准记录

        Returns:
            质量评估结果
        """
        if calibration.probe_type in ("dual_linear", "dual_slant"):
            # 线极化评估
            v_to_h = calibration.v_to_h_isolation_db or 0
            h_to_v = calibration.h_to_v_isolation_db or 0
            min_xpd = min(v_to_h, h_to_v)

            if min_xpd >= XPD_EXCELLENT_THRESHOLD_DB:
                quality = "excellent"
            elif min_xpd >= XPD_MIN_THRESHOLD_DB:
                quality = "good"
            elif min_xpd >= XPD_MIN_THRESHOLD_DB - 5:
                quality = "marginal"
            else:
                quality = "poor"

            return {
                "type": "linear",
                "min_xpd_db": min_xpd,
                "quality": quality,
                "pass": min_xpd >= XPD_MIN_THRESHOLD_DB
            }
        else:
            # 圆极化评估
            ar = calibration.axial_ratio_db or float('inf')

            if ar <= AXIAL_RATIO_EXCELLENT_DB:
                quality = "excellent"
            elif ar <= AXIAL_RATIO_MAX_DB:
                quality = "good"
            elif ar <= AXIAL_RATIO_MAX_DB + 1:
                quality = "marginal"
            else:
                quality = "poor"

            return {
                "type": "circular",
                "axial_ratio_db": ar,
                "polarization_hand": calibration.polarization_hand,
                "quality": quality,
                "pass": ar <= AXIAL_RATIO_MAX_DB
            }


# ==================== 方向图校准服务 (TASK-P07) ====================

# 方向图校准常数
PATTERN_VALIDITY_DAYS = 365  # 方向图校准有效期 (天)
DEFAULT_AZIMUTH_STEP_DEG = 5.0  # 默认方位角步进 (度)
DEFAULT_ELEVATION_STEP_DEG = 5.0  # 默认俯仰角步进 (度)
SPEED_OF_LIGHT_M_S = 299792458.0  # 光速 (m/s)
FAR_FIELD_FACTOR = 2.0  # 远场因子: d > 2D²/λ


def calculate_far_field_distance(
    antenna_diameter_m: float,
    frequency_mhz: float
) -> float:
    """
    计算远场距离

    远场条件: d > 2D²/λ

    Args:
        antenna_diameter_m: 天线口径 (m)
        frequency_mhz: 频率 (MHz)

    Returns:
        最小远场距离 (m)
    """
    wavelength_m = SPEED_OF_LIGHT_M_S / (frequency_mhz * 1e6)
    return FAR_FIELD_FACTOR * (antenna_diameter_m ** 2) / wavelength_m


def validate_far_field_condition(
    measurement_distance_m: float,
    antenna_diameter_m: float,
    frequency_mhz: float
) -> Tuple[bool, float]:
    """
    验证远场条件

    Args:
        measurement_distance_m: 测量距离 (m)
        antenna_diameter_m: 天线口径 (m)
        frequency_mhz: 频率 (MHz)

    Returns:
        (is_valid, min_distance_m)
    """
    min_distance = calculate_far_field_distance(antenna_diameter_m, frequency_mhz)
    return measurement_distance_m >= min_distance, min_distance


def calculate_hpbw(
    angles_deg: List[float],
    gains_dbi: List[float]
) -> Optional[float]:
    """
    计算半功率波束宽度 (HPBW)

    HPBW 是增益从峰值下降 3 dB 时对应的角度范围。

    Args:
        angles_deg: 角度数组 (度)
        gains_dbi: 增益数组 (dBi)

    Returns:
        HPBW (度)，如果无法计算则返回 None
    """
    if len(angles_deg) < 3 or len(gains_dbi) != len(angles_deg):
        return None

    # 找到峰值
    peak_idx = int(np.argmax(gains_dbi))
    peak_gain = gains_dbi[peak_idx]
    half_power_threshold = peak_gain - 3.0  # -3 dB 阈值

    # 向左搜索 -3 dB 点
    left_idx = peak_idx
    while left_idx > 0 and gains_dbi[left_idx] > half_power_threshold:
        left_idx -= 1

    # 向右搜索 -3 dB 点
    right_idx = peak_idx
    while right_idx < len(gains_dbi) - 1 and gains_dbi[right_idx] > half_power_threshold:
        right_idx += 1

    # 计算 HPBW
    if left_idx == 0 and gains_dbi[0] > half_power_threshold:
        # 左边未找到 -3 dB 点
        return None
    if right_idx == len(gains_dbi) - 1 and gains_dbi[-1] > half_power_threshold:
        # 右边未找到 -3 dB 点
        return None

    # 线性插值获得更精确的 -3 dB 角度
    # 左边界插值
    if left_idx < peak_idx and gains_dbi[left_idx] <= half_power_threshold < gains_dbi[left_idx + 1]:
        frac = (half_power_threshold - gains_dbi[left_idx]) / (gains_dbi[left_idx + 1] - gains_dbi[left_idx])
        left_angle = angles_deg[left_idx] + frac * (angles_deg[left_idx + 1] - angles_deg[left_idx])
    else:
        left_angle = angles_deg[left_idx]

    # 右边界插值
    if right_idx > peak_idx and gains_dbi[right_idx] <= half_power_threshold < gains_dbi[right_idx - 1]:
        frac = (half_power_threshold - gains_dbi[right_idx]) / (gains_dbi[right_idx - 1] - gains_dbi[right_idx])
        right_angle = angles_deg[right_idx] - frac * (angles_deg[right_idx] - angles_deg[right_idx - 1])
    else:
        right_angle = angles_deg[right_idx]

    return abs(right_angle - left_angle)


def calculate_front_to_back_ratio(
    gains_dbi: List[float],
    azimuth_deg: List[float]
) -> Optional[float]:
    """
    计算前后比

    前后比 = 主瓣增益 - 背瓣增益 (dB)

    Args:
        gains_dbi: 增益数组 (dBi)
        azimuth_deg: 方位角数组 (度)

    Returns:
        前后比 (dB)
    """
    if len(gains_dbi) < 2:
        return None

    # 找到峰值 (前向)
    peak_idx = int(np.argmax(gains_dbi))
    peak_gain = gains_dbi[peak_idx]
    peak_angle = azimuth_deg[peak_idx]

    # 找到背向 (与峰值相差约 180°)
    back_angle = (peak_angle + 180) % 360

    # 找到最接近背向的角度索引
    back_idx = int(np.argmin([abs((a - back_angle + 180) % 360 - 180) for a in azimuth_deg]))
    back_gain = gains_dbi[back_idx]

    return peak_gain - back_gain


class PatternMeasurement:
    """方向图测量结果"""
    def __init__(
        self,
        azimuth_deg: float,
        elevation_deg: float,
        gain_dbi: float,
        uncertainty_db: float = 0.0
    ):
        self.azimuth_deg = azimuth_deg
        self.elevation_deg = elevation_deg
        self.gain_dbi = gain_dbi
        self.uncertainty_db = uncertainty_db


class PatternCalibrationService:
    """
    方向图校准服务

    负责探头方向图校准的完整流程:
    1. 远场条件验证
    2. 方位角/俯仰角扫描测量
    3. HPBW 计算
    4. 前后比计算
    5. 保存校准记录
    """

    def __init__(self, instruments=None):
        self.instruments = instruments

    async def execute_pattern_calibration(
        self,
        db: Session,
        probe_ids: List[int],
        polarizations: List[PolarizationType],
        frequency_mhz: float,
        calibrated_by: str,
        azimuth_step_deg: float = DEFAULT_AZIMUTH_STEP_DEG,
        elevation_step_deg: float = DEFAULT_ELEVATION_STEP_DEG,
        measurement_distance_m: float = 3.0,
        reference_antenna_id: Optional[str] = None,
        turntable_id: Optional[str] = None,
        use_mock: bool = True
    ) -> CalibrationResult:
        """
        执行方向图校准

        Args:
            db: 数据库会话
            probe_ids: 要校准的探头 ID 列表
            polarizations: 极化类型列表
            frequency_mhz: 测量频率 (MHz)
            calibrated_by: 校准人员
            azimuth_step_deg: 方位角步进 (度)
            elevation_step_deg: 俯仰角步进 (度)
            measurement_distance_m: 测量距离 (m)
            reference_antenna_id: 参考天线 ID
            turntable_id: 转台 ID
            use_mock: 是否使用 mock 数据

        Returns:
            CalibrationResult
        """
        logger.info(
            f"Starting pattern calibration for probes {probe_ids}, "
            f"frequency={frequency_mhz} MHz"
        )

        # 验证探头 ID
        for probe_id in probe_ids:
            if probe_id < PROBE_ID_MIN or probe_id > PROBE_ID_MAX:
                return CalibrationResult(
                    success=False,
                    message=f"Invalid probe_id {probe_id}"
                )

        # 验证远场条件 (假设探头口径约 0.1m)
        antenna_diameter_m = 0.1
        is_far_field, min_distance = validate_far_field_condition(
            measurement_distance_m, antenna_diameter_m, frequency_mhz
        )

        warnings = []
        if not is_far_field:
            warnings.append(
                f"Measurement distance {measurement_distance_m}m may not satisfy "
                f"far-field condition (min: {min_distance:.2f}m)"
            )

        # 生成角度网格
        azimuth_deg = list(np.arange(0, 360, azimuth_step_deg))
        elevation_deg = list(np.arange(0, 181, elevation_step_deg))

        calibration_ids = []

        for probe_id in probe_ids:
            for polarization in polarizations:
                try:
                    if use_mock:
                        measurements = self._mock_pattern_measurements(
                            probe_id, polarization, azimuth_deg, elevation_deg, frequency_mhz
                        )
                    else:
                        measurements = await self._real_pattern_measurements(
                            probe_id, polarization, azimuth_deg, elevation_deg,
                            frequency_mhz, reference_antenna_id, turntable_id
                        )

                    # 提取增益数据 (行优先存储: elevation 外循环, azimuth 内循环)
                    gain_pattern = []
                    for m in measurements:
                        gain_pattern.append(m.gain_dbi)

                    # 计算方向图参数
                    # 使用方位面切片 (elevation = 90°, 即水平面)
                    mid_elev_idx = len(elevation_deg) // 2
                    azimuth_slice_start = mid_elev_idx * len(azimuth_deg)
                    azimuth_slice_end = azimuth_slice_start + len(azimuth_deg)
                    azimuth_slice_gains = gain_pattern[azimuth_slice_start:azimuth_slice_end]

                    # 峰值增益和方向
                    peak_gain = max(gain_pattern)
                    peak_idx = gain_pattern.index(peak_gain)
                    peak_elev_idx = peak_idx // len(azimuth_deg)
                    peak_az_idx = peak_idx % len(azimuth_deg)
                    peak_azimuth = azimuth_deg[peak_az_idx]
                    peak_elevation = elevation_deg[peak_elev_idx]

                    # HPBW
                    hpbw_azimuth = calculate_hpbw(azimuth_deg, azimuth_slice_gains)

                    # 俯仰面切片 (azimuth = peak_azimuth)
                    elevation_slice_gains = [
                        gain_pattern[e * len(azimuth_deg) + peak_az_idx]
                        for e in range(len(elevation_deg))
                    ]
                    hpbw_elevation = calculate_hpbw(elevation_deg, elevation_slice_gains)

                    # 前后比
                    ftb_ratio = calculate_front_to_back_ratio(azimuth_slice_gains, azimuth_deg)

                    # 转换 numpy 类型为原生 Python 类型 (避免 JSON 序列化问题)
                    azimuth_deg_native = [float(x) for x in azimuth_deg]
                    elevation_deg_native = [float(x) for x in elevation_deg]
                    gain_pattern_native = [float(x) for x in gain_pattern]

                    calibration = ProbePattern(
                        probe_id=probe_id,
                        polarization=polarization.value if hasattr(polarization, 'value') else str(polarization),
                        frequency_mhz=frequency_mhz,
                        azimuth_deg=azimuth_deg_native,
                        elevation_deg=elevation_deg_native,
                        gain_pattern_dbi=gain_pattern_native,
                        peak_gain_dbi=float(peak_gain),
                        peak_azimuth_deg=float(peak_azimuth),
                        peak_elevation_deg=float(peak_elevation),
                        hpbw_azimuth_deg=float(hpbw_azimuth) if hpbw_azimuth is not None else None,
                        hpbw_elevation_deg=float(hpbw_elevation) if hpbw_elevation is not None else None,
                        front_to_back_ratio_db=float(ftb_ratio) if ftb_ratio is not None else None,
                        reference_antenna=reference_antenna_id,
                        turntable=turntable_id,
                        measurement_distance_m=measurement_distance_m,
                        measured_at=datetime.utcnow(),
                        measured_by=calibrated_by,
                        valid_until=datetime.utcnow() + timedelta(days=PATTERN_VALIDITY_DAYS),
                        status=CalibrationStatus.VALID
                    )

                    db.add(calibration)
                    db.flush()
                    calibration_ids.append(str(calibration.id))

                except Exception as e:
                    logger.error(f"Pattern calibration failed for probe {probe_id}: {e}")
                    return CalibrationResult(
                        success=False,
                        message=f"Calibration failed: {str(e)}"
                    )

        db.commit()

        return CalibrationResult(
            success=True,
            message=f"Pattern calibration completed for {len(probe_ids)} probes, "
                    f"{len(polarizations)} polarizations",
            data={
                "calibration_ids": calibration_ids,
                "frequency_mhz": frequency_mhz,
                "num_azimuth_points": len(azimuth_deg),
                "num_elevation_points": len(elevation_deg)
            },
            warnings=warnings
        )

    def _mock_pattern_measurements(
        self,
        probe_id: int,
        polarization: PolarizationType,
        azimuth_deg: List[float],
        elevation_deg: List[float],
        frequency_mhz: float
    ) -> List[PatternMeasurement]:
        """生成 mock 方向图测量数据"""
        measurements = []

        # 探头间的变异
        probe_variation = (probe_id % 10 - 5) * 0.2  # ±1 dB

        # 基础增益 (典型探头增益约 5 dBi)
        base_gain = 5.0 + probe_variation

        # 方向图参数
        hpbw_target = 60.0  # 目标 HPBW 60°
        sigma_az = hpbw_target / (2 * np.sqrt(2 * np.log(2)))  # 方位面波束宽度
        sigma_el = hpbw_target / (2 * np.sqrt(2 * np.log(2)))  # 俯仰面波束宽度

        # 主瓣方向 (假设指向 azimuth=0, elevation=90)
        main_az = 0
        main_el = 90

        for elev in elevation_deg:
            for az in azimuth_deg:
                # 计算与主瓣的角度偏差
                az_diff = min(abs(az - main_az), 360 - abs(az - main_az))
                el_diff = abs(elev - main_el)

                # 高斯波束模型
                az_factor = np.exp(-(az_diff ** 2) / (2 * sigma_az ** 2))
                el_factor = np.exp(-(el_diff ** 2) / (2 * sigma_el ** 2))

                # 增益计算
                gain = base_gain + 10 * np.log10(az_factor * el_factor + 0.001)

                # 添加测量噪声
                gain += np.random.normal(0, 0.3)

                measurements.append(PatternMeasurement(
                    azimuth_deg=az,
                    elevation_deg=elev,
                    gain_dbi=gain,
                    uncertainty_db=0.3
                ))

        return measurements

    async def _real_pattern_measurements(
        self,
        probe_id: int,
        polarization: PolarizationType,
        azimuth_deg: List[float],
        elevation_deg: List[float],
        frequency_mhz: float,
        reference_antenna_id: Optional[str],
        turntable_id: Optional[str]
    ) -> List[PatternMeasurement]:
        """执行实际方向图测量"""
        if not self.instruments:
            raise RuntimeError("No instruments connected")
        raise NotImplementedError("Real pattern measurements not yet implemented")

    def get_latest_calibration(
        self,
        db: Session,
        probe_id: int,
        frequency_mhz: Optional[float] = None
    ) -> Optional[ProbePattern]:
        """获取最新方向图校准记录"""
        query = db.query(ProbePattern).filter(
            ProbePattern.probe_id == probe_id
        )
        if frequency_mhz is not None:
            query = query.filter(ProbePattern.frequency_mhz == frequency_mhz)
        return query.order_by(desc(ProbePattern.measured_at)).first()

    def get_calibrations_by_frequency(
        self,
        db: Session,
        probe_id: int,
        frequency_mhz: Optional[float] = None
    ) -> List[ProbePattern]:
        """获取指定频率的方向图校准记录"""
        query = db.query(ProbePattern).filter(
            ProbePattern.probe_id == probe_id
        )
        if frequency_mhz is not None:
            query = query.filter(ProbePattern.frequency_mhz == frequency_mhz)
        return query.order_by(desc(ProbePattern.measured_at)).all()

    def evaluate_pattern_quality(
        self,
        calibration: ProbePattern
    ) -> Dict[str, Any]:
        """
        评估方向图校准质量

        Args:
            calibration: 校准记录

        Returns:
            质量评估结果
        """
        issues = []
        quality = "good"

        # 检查峰值增益
        if calibration.peak_gain_dbi is not None:
            if calibration.peak_gain_dbi < 0:
                issues.append("Low peak gain (< 0 dBi)")
                quality = "poor"
            elif calibration.peak_gain_dbi < 3:
                issues.append("Marginal peak gain (< 3 dBi)")
                if quality != "poor":
                    quality = "marginal"

        # 检查 HPBW
        if calibration.hpbw_azimuth_deg is not None:
            if calibration.hpbw_azimuth_deg > 120:
                issues.append("Wide azimuth HPBW (> 120°)")
                if quality != "poor":
                    quality = "marginal"
            elif calibration.hpbw_azimuth_deg < 20:
                issues.append("Narrow azimuth HPBW (< 20°)")

        if calibration.hpbw_elevation_deg is not None:
            if calibration.hpbw_elevation_deg > 120:
                issues.append("Wide elevation HPBW (> 120°)")
                if quality != "poor":
                    quality = "marginal"

        # 检查前后比
        if calibration.front_to_back_ratio_db is not None:
            if calibration.front_to_back_ratio_db < 10:
                issues.append("Low front-to-back ratio (< 10 dB)")
                if quality != "poor":
                    quality = "marginal"

        return {
            "peak_gain_dbi": calibration.peak_gain_dbi,
            "hpbw_azimuth_deg": calibration.hpbw_azimuth_deg,
            "hpbw_elevation_deg": calibration.hpbw_elevation_deg,
            "front_to_back_ratio_db": calibration.front_to_back_ratio_db,
            "quality": quality,
            "issues": issues
        }


# ==================== 链路校准服务 (TASK-P08) ====================

# 链路校准常数
LINK_CALIBRATION_VALIDITY_DAYS = 7  # 链路校准有效期 (天)
DEFAULT_DEVIATION_THRESHOLD_DB = 1.0  # 默认偏差阈值 (dB)
EXCELLENT_DEVIATION_THRESHOLD_DB = 0.3  # 优秀偏差阈值 (dB)


def calculate_deviation(
    measured_gain_dbi: float,
    known_gain_dbi: float
) -> float:
    """
    计算测量增益与已知增益的偏差

    偏差 = 测量值 - 已知值 (dB)

    Args:
        measured_gain_dbi: 测量增益 (dBi)
        known_gain_dbi: 已知增益 (dBi)

    Returns:
        偏差 (dB)，正值表示测量偏高
    """
    return measured_gain_dbi - known_gain_dbi


def validate_link_calibration(
    deviation_db: float,
    threshold_db: float = DEFAULT_DEVIATION_THRESHOLD_DB
) -> Tuple[bool, str]:
    """
    验证链路校准是否合格

    Args:
        deviation_db: 偏差 (dB)
        threshold_db: 合格阈值 (dB)

    Returns:
        (is_pass, quality_rating)
    """
    abs_deviation = abs(deviation_db)

    if abs_deviation <= EXCELLENT_DEVIATION_THRESHOLD_DB:
        return True, "excellent"
    elif abs_deviation <= threshold_db:
        return True, "good"
    elif abs_deviation <= threshold_db * 1.5:
        return False, "marginal"
    else:
        return False, "poor"


class LinkMeasurement:
    """链路测量结果"""
    def __init__(
        self,
        probe_id: int,
        link_loss_db: float,
        phase_offset_deg: float,
        uncertainty_db: float = 0.0
    ):
        self.probe_id = probe_id
        self.link_loss_db = link_loss_db
        self.phase_offset_deg = phase_offset_deg
        self.uncertainty_db = uncertainty_db


class LinkCalibrationService:
    """
    链路校准服务

    负责 RF 链路端到端校准验证:
    1. 使用标准 DUT (如标准偶极子) 进行测量
    2. 比对已知增益与测量增益
    3. 计算偏差并判定合格性
    4. 可选: 探头级链路校准
    """

    def __init__(self, instruments=None):
        self.instruments = instruments

    async def execute_link_calibration(
        self,
        db: Session,
        calibration_type: str,
        standard_dut: Dict[str, Any],
        frequency_mhz: float,
        calibrated_by: str,
        probe_ids: Optional[List[int]] = None,
        threshold_db: float = DEFAULT_DEVIATION_THRESHOLD_DB,
        use_mock: bool = True
    ) -> CalibrationResult:
        """
        执行链路校准

        Args:
            db: 数据库会话
            calibration_type: 校准类型 (weekly_check, pre_test, post_maintenance)
            standard_dut: 标准 DUT 信息 {dut_type, model, serial, known_gain_dbi}
            frequency_mhz: 测试频率 (MHz)
            calibrated_by: 校准人员
            probe_ids: 要校准的探头 ID 列表，None 表示全部
            threshold_db: 合格阈值 (dB)
            use_mock: 是否使用 mock 数据

        Returns:
            CalibrationResult
        """
        logger.info(
            f"Starting link calibration, type={calibration_type}, "
            f"DUT={standard_dut.get('model')}, frequency={frequency_mhz} MHz"
        )

        known_gain_dbi = standard_dut.get('known_gain_dbi', 2.15)  # 默认偶极子增益

        try:
            if use_mock:
                measured_gain, probe_calibrations = self._mock_link_measurement(
                    known_gain_dbi, probe_ids, frequency_mhz
                )
            else:
                measured_gain, probe_calibrations = await self._real_link_measurement(
                    standard_dut, probe_ids, frequency_mhz
                )

            # 计算偏差
            deviation = calculate_deviation(measured_gain, known_gain_dbi)

            # 验证
            is_pass, quality = validate_link_calibration(deviation, threshold_db)

            # 创建校准记录
            calibration = LinkCalibration(
                calibration_type=calibration_type,
                standard_dut_type=standard_dut.get('dut_type'),
                standard_dut_model=standard_dut.get('model'),
                standard_dut_serial=standard_dut.get('serial'),
                known_gain_dbi=known_gain_dbi,
                frequency_mhz=frequency_mhz,
                measured_gain_dbi=measured_gain,
                deviation_db=deviation,
                probe_link_calibrations=probe_calibrations,
                validation_pass=is_pass,
                threshold_db=threshold_db,
                calibrated_at=datetime.utcnow(),
                calibrated_by=calibrated_by
            )

            db.add(calibration)
            db.commit()

            warnings = []
            if not is_pass:
                warnings.append(
                    f"Deviation {deviation:.2f} dB exceeds threshold {threshold_db} dB"
                )

            return CalibrationResult(
                success=True,
                message=f"Link calibration completed, result: {'PASS' if is_pass else 'FAIL'}",
                data={
                    "calibration_id": str(calibration.id),
                    "measured_gain_dbi": round(measured_gain, 2),
                    "known_gain_dbi": known_gain_dbi,
                    "deviation_db": round(deviation, 3),
                    "validation_pass": is_pass,
                    "quality": quality,
                    "num_probes": len(probe_calibrations) if probe_calibrations else 0
                },
                warnings=warnings
            )

        except Exception as e:
            logger.error(f"Link calibration failed: {e}")
            return CalibrationResult(
                success=False,
                message=f"Link calibration failed: {str(e)}"
            )

    def _mock_link_measurement(
        self,
        known_gain_dbi: float,
        probe_ids: Optional[List[int]],
        frequency_mhz: float
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """生成 mock 链路测量数据"""
        # 系统误差 (小的随机偏差)
        system_offset = np.random.normal(0, 0.3)  # ±0.3 dB 系统误差

        # 测量增益 = 已知增益 + 系统误差 + 随机噪声
        measured_gain = known_gain_dbi + system_offset + np.random.normal(0, 0.1)

        # 探头级校准数据
        probe_calibrations = []
        target_probes = probe_ids if probe_ids else list(range(PROBE_ID_MIN, PROBE_ID_MAX + 1))

        for probe_id in target_probes:
            # 探头间的变异
            probe_variation = (probe_id % 10 - 5) * 0.05  # ±0.25 dB

            probe_calibrations.append({
                "probe_id": probe_id,
                "link_loss_db": round(30.0 + probe_variation + np.random.normal(0, 0.2), 2),
                "phase_offset_deg": round(np.random.uniform(-180, 180), 1)
            })

        return float(measured_gain), probe_calibrations

    async def _real_link_measurement(
        self,
        standard_dut: Dict[str, Any],
        probe_ids: Optional[List[int]],
        frequency_mhz: float
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """执行实际链路测量"""
        if not self.instruments:
            raise RuntimeError("No instruments connected")
        raise NotImplementedError("Real link measurement not yet implemented")

    def get_latest_calibration(
        self,
        db: Session,
        calibration_type: Optional[str] = None
    ) -> Optional[LinkCalibration]:
        """获取最新链路校准记录"""
        query = db.query(LinkCalibration)
        if calibration_type:
            query = query.filter(LinkCalibration.calibration_type == calibration_type)
        return query.order_by(desc(LinkCalibration.calibrated_at)).first()

    def get_calibration_history(
        self,
        db: Session,
        calibration_type: Optional[str] = None,
        limit: int = 20
    ) -> List[LinkCalibration]:
        """获取链路校准历史"""
        query = db.query(LinkCalibration)
        if calibration_type:
            query = query.filter(LinkCalibration.calibration_type == calibration_type)
        return query.order_by(desc(LinkCalibration.calibrated_at)).limit(limit).all()

    def check_link_validity(
        self,
        db: Session
    ) -> Dict[str, Any]:
        """
        检查链路校准有效性

        Returns:
            有效性状态
        """
        latest = self.get_latest_calibration(db)

        if not latest:
            return {
                "status": "unknown",
                "message": "No link calibration found"
            }

        now = datetime.utcnow()
        valid_until = latest.calibrated_at + timedelta(days=LINK_CALIBRATION_VALIDITY_DAYS)

        if now > valid_until:
            days_overdue = (now - valid_until).days
            return {
                "status": "expired",
                "calibration_id": str(latest.id),
                "calibrated_at": latest.calibrated_at.isoformat(),
                "days_overdue": days_overdue,
                "message": f"Link calibration expired {days_overdue} days ago"
            }

        days_remaining = (valid_until - now).days

        if days_remaining <= 2:
            return {
                "status": "expiring_soon",
                "calibration_id": str(latest.id),
                "calibrated_at": latest.calibrated_at.isoformat(),
                "valid_until": valid_until.isoformat(),
                "days_remaining": days_remaining,
                "message": f"Link calibration expires in {days_remaining} days"
            }

        return {
            "status": "valid",
            "calibration_id": str(latest.id),
            "calibrated_at": latest.calibrated_at.isoformat(),
            "valid_until": valid_until.isoformat(),
            "days_remaining": days_remaining,
            "validation_pass": latest.validation_pass,
            "deviation_db": latest.deviation_db
        }

    def evaluate_calibration_quality(
        self,
        calibration: LinkCalibration
    ) -> Dict[str, Any]:
        """
        评估链路校准质量

        Args:
            calibration: 校准记录

        Returns:
            质量评估结果
        """
        deviation = calibration.deviation_db or 0
        threshold = calibration.threshold_db or DEFAULT_DEVIATION_THRESHOLD_DB

        is_pass, quality = validate_link_calibration(deviation, threshold)

        return {
            "deviation_db": deviation,
            "threshold_db": threshold,
            "validation_pass": is_pass,
            "quality": quality,
            "measured_gain_dbi": calibration.measured_gain_dbi,
            "known_gain_dbi": calibration.known_gain_dbi
        }


# ==================== 有效性管理服务 ====================

class CalibrationValidityService:
    """
    校准有效性管理服务

    负责跟踪校准状态、过期检查和有效性报告
    """

    def __init__(self, expiring_threshold_days: int = 7):
        """
        初始化服务

        Args:
            expiring_threshold_days: 即将过期的阈值天数
        """
        self.expiring_threshold_days = expiring_threshold_days

    def check_validity(
        self,
        db: Session,
        probe_id: int
    ) -> Dict[str, Any]:
        """
        检查探头的校准有效性

        Args:
            db: 数据库会话
            probe_id: 探头 ID

        Returns:
            各类校准的有效性状态
        """
        now = datetime.utcnow()
        expiring_threshold = now + timedelta(days=self.expiring_threshold_days)

        result = {
            "probe_id": probe_id,
            "amplitude": None,
            "phase": None,
            "polarization": None,
            "pattern": None,
            "link": None,
            "overall_status": "unknown"
        }

        # 检查幅度校准
        amplitude = db.query(ProbeAmplitudeCalibration).filter(
            ProbeAmplitudeCalibration.probe_id == probe_id,
            ProbeAmplitudeCalibration.status != CalibrationStatus.INVALIDATED.value
        ).order_by(desc(ProbeAmplitudeCalibration.calibrated_at)).first()

        if amplitude:
            result["amplitude"] = self._get_calibration_status(amplitude, now, expiring_threshold)

        # 检查相位校准
        phase = db.query(ProbePhaseCalibration).filter(
            ProbePhaseCalibration.probe_id == probe_id,
            ProbePhaseCalibration.status != CalibrationStatus.INVALIDATED.value
        ).order_by(desc(ProbePhaseCalibration.calibrated_at)).first()

        if phase:
            result["phase"] = self._get_calibration_status(phase, now, expiring_threshold)

        # 检查极化校准
        polarization = db.query(ProbePolarizationCalibration).filter(
            ProbePolarizationCalibration.probe_id == probe_id,
            ProbePolarizationCalibration.status != CalibrationStatus.INVALIDATED.value
        ).order_by(desc(ProbePolarizationCalibration.calibrated_at)).first()

        if polarization:
            result["polarization"] = self._get_calibration_status(polarization, now, expiring_threshold)

        # 检查方向图校准
        pattern = db.query(ProbePattern).filter(
            ProbePattern.probe_id == probe_id,
            ProbePattern.status != CalibrationStatus.INVALIDATED.value
        ).order_by(desc(ProbePattern.measured_at)).first()

        if pattern:
            result["pattern"] = self._get_calibration_status(pattern, now, expiring_threshold)

        # 检查链路校准 (链路校准是全局的，不是按探头分的)
        # 这里返回最新的链路校准状态
        link = db.query(LinkCalibration).order_by(
            desc(LinkCalibration.calibrated_at)
        ).first()

        if link:
            # 链路校准有效期 7 天
            link_valid_until = link.calibrated_at + timedelta(days=LINK_CALIBRATION_VALIDITY_DAYS)
            link_status = {
                "calibration_id": str(link.id),
                "valid_until": link_valid_until.isoformat(),
                "validation_pass": link.validation_pass
            }
            if link_valid_until < now:
                link_status["status"] = "expired"
                link_status["days_overdue"] = (now - link_valid_until).days
            elif link_valid_until < expiring_threshold:
                link_status["status"] = "expiring_soon"
                link_status["days_remaining"] = (link_valid_until - now).days
            else:
                link_status["status"] = "valid"
                link_status["days_remaining"] = (link_valid_until - now).days

            result["link"] = link_status

        # 计算总体状态
        calibration_statuses = []
        for cal_type in ["amplitude", "phase", "polarization", "pattern", "link"]:
            if result[cal_type] is not None:
                calibration_statuses.append(result[cal_type]["status"])

        if not calibration_statuses:
            result["overall_status"] = "unknown"
        elif "expired" in calibration_statuses:
            result["overall_status"] = "expired"
        elif "expiring_soon" in calibration_statuses:
            result["overall_status"] = "expiring_soon"
        elif all(s == "valid" for s in calibration_statuses):
            result["overall_status"] = "valid"
        else:
            result["overall_status"] = "partial"

        return result

    def _get_calibration_status(
        self,
        calibration,
        now: datetime,
        expiring_threshold: datetime
    ) -> Dict[str, Any]:
        """
        获取单个校准记录的状态

        Args:
            calibration: 校准记录
            now: 当前时间
            expiring_threshold: 即将过期阈值时间

        Returns:
            状态信息
        """
        status_info = {
            "calibration_id": str(calibration.id),
            "valid_until": calibration.valid_until.isoformat()
        }

        if calibration.valid_until < now:
            status_info["status"] = "expired"
            status_info["days_overdue"] = (now - calibration.valid_until).days
        elif calibration.valid_until < expiring_threshold:
            status_info["status"] = "expiring_soon"
            status_info["days_remaining"] = (calibration.valid_until - now).days
        else:
            status_info["status"] = "valid"
            status_info["days_remaining"] = (calibration.valid_until - now).days

        return status_info

    def generate_validity_report(
        self,
        db: Session,
        probe_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        生成校准有效性报告

        Args:
            db: 数据库会话
            probe_ids: 要检查的探头 ID 列表 (None 表示所有)

        Returns:
            有效性报告
        """
        if probe_ids is None:
            probe_ids = list(range(PROBE_ID_MIN, PROBE_ID_MAX + 1))

        total_probes = len(probe_ids)
        valid_probes = 0
        expired_probes = 0
        expiring_soon_probes = 0

        expired_calibrations = []
        expiring_soon_calibrations = []
        recommendations = []

        calibration_types = ["amplitude", "phase", "polarization", "pattern", "link"]
        priority_map = {
            "amplitude": "critical",
            "phase": "critical",
            "polarization": "high",
            "pattern": "medium",
            "link": "critical"
        }

        for probe_id in probe_ids:
            status = self.check_validity(db, probe_id)

            if status["overall_status"] == "valid":
                valid_probes += 1
            elif status["overall_status"] == "expired":
                expired_probes += 1
            elif status["overall_status"] == "expiring_soon":
                expiring_soon_probes += 1

            # 收集所有校准类型的状态
            for cal_type in calibration_types:
                cal_status = status.get(cal_type)
                if cal_status is None:
                    continue

                if cal_status["status"] == "expired":
                    expired_calibrations.append({
                        "probe_id": probe_id,
                        "calibration_type": cal_type,
                        "days_overdue": cal_status.get("days_overdue", 0),
                        "calibration_id": cal_status.get("calibration_id")
                    })
                    recommendations.append({
                        "probe_id": probe_id,
                        "calibration_type": cal_type,
                        "action": "recalibrate_now",
                        "priority": priority_map.get(cal_type, "medium"),
                        "reason": f"{cal_type} calibration expired {cal_status.get('days_overdue', 0)} days ago"
                    })
                elif cal_status["status"] == "expiring_soon":
                    expiring_soon_calibrations.append({
                        "probe_id": probe_id,
                        "calibration_type": cal_type,
                        "days_remaining": cal_status.get("days_remaining", 0),
                        "valid_until": cal_status.get("valid_until"),
                        "calibration_id": cal_status.get("calibration_id")
                    })
                    recommendations.append({
                        "probe_id": probe_id,
                        "calibration_type": cal_type,
                        "action": "schedule_recalibration",
                        "priority": "high" if cal_status.get("days_remaining", 0) <= 3 else "medium",
                        "reason": f"{cal_type} calibration expires in {cal_status.get('days_remaining', 0)} days"
                    })

        return {
            "total_probes": total_probes,
            "valid_probes": valid_probes,
            "expired_probes": expired_probes,
            "expiring_soon_probes": expiring_soon_probes,
            "expired_calibrations": expired_calibrations,
            "expiring_soon_calibrations": expiring_soon_calibrations,
            "recommendations": recommendations
        }

    def invalidate_calibration(
        self,
        db: Session,
        calibration_type: str,
        calibration_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        作废指定的校准记录

        Args:
            db: 数据库会话
            calibration_type: 校准类型 (amplitude, phase, polarization, pattern, link)
            calibration_id: 校准记录 ID
            reason: 作废原因

        Returns:
            作废结果
        """
        from uuid import UUID

        model_map = {
            "amplitude": ProbeAmplitudeCalibration,
            "phase": ProbePhaseCalibration,
            "polarization": ProbePolarizationCalibration,
            "pattern": ProbePattern,
            "link": LinkCalibration
        }

        if calibration_type not in model_map:
            return {
                "success": False,
                "message": f"Unknown calibration type: {calibration_type}"
            }

        model = model_map[calibration_type]

        try:
            cal_uuid = UUID(calibration_id)
        except ValueError:
            return {
                "success": False,
                "message": f"Invalid calibration ID format: {calibration_id}"
            }

        calibration = db.query(model).filter(model.id == cal_uuid).first()

        if not calibration:
            return {
                "success": False,
                "message": f"Calibration not found: {calibration_id}"
            }

        # 检查是否已经作废
        if hasattr(calibration, 'status') and calibration.status == CalibrationStatus.INVALIDATED.value:
            return {
                "success": False,
                "message": "Calibration is already invalidated"
            }

        # 更新状态为作废
        if hasattr(calibration, 'status'):
            calibration.status = CalibrationStatus.INVALIDATED.value

        db.commit()

        logger.info(f"Invalidated {calibration_type} calibration {calibration_id}: {reason}")

        return {
            "success": True,
            "message": f"Calibration {calibration_id} invalidated successfully",
            "calibration_type": calibration_type,
            "calibration_id": calibration_id,
            "reason": reason
        }

    def get_expiring_calibrations(
        self,
        db: Session,
        days_threshold: int = 7,
        calibration_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取即将过期的校准列表

        Args:
            db: 数据库会话
            days_threshold: 过期阈值天数
            calibration_type: 可选的校准类型筛选

        Returns:
            即将过期的校准列表
        """
        now = datetime.utcnow()
        expiring_threshold = now + timedelta(days=days_threshold)

        results = []

        calibration_configs = [
            ("amplitude", ProbeAmplitudeCalibration, "valid_until", "calibrated_at"),
            ("phase", ProbePhaseCalibration, "valid_until", "calibrated_at"),
            ("polarization", ProbePolarizationCalibration, "valid_until", "calibrated_at"),
            ("pattern", ProbePattern, "valid_until", "measured_at"),
        ]

        for cal_type, model, valid_until_field, date_field in calibration_configs:
            if calibration_type and calibration_type != cal_type:
                continue

            # 查询即将过期的校准 (在有效期内但即将过期)
            query = db.query(model).filter(
                getattr(model, valid_until_field) > now,
                getattr(model, valid_until_field) <= expiring_threshold,
                model.status != CalibrationStatus.INVALIDATED.value
            ).order_by(getattr(model, valid_until_field))

            for cal in query.all():
                valid_until = getattr(cal, valid_until_field)
                days_remaining = (valid_until - now).days

                results.append({
                    "calibration_type": cal_type,
                    "calibration_id": str(cal.id),
                    "probe_id": cal.probe_id,
                    "valid_until": valid_until.isoformat(),
                    "days_remaining": days_remaining,
                    "calibrated_at": getattr(cal, date_field).isoformat()
                })

        # 链路校准单独处理 (没有 valid_until 字段)
        if not calibration_type or calibration_type == "link":
            link_cals = db.query(LinkCalibration).all()
            for link in link_cals:
                link_valid_until = link.calibrated_at + timedelta(days=LINK_CALIBRATION_VALIDITY_DAYS)
                if now < link_valid_until <= expiring_threshold:
                    days_remaining = (link_valid_until - now).days
                    results.append({
                        "calibration_type": "link",
                        "calibration_id": str(link.id),
                        "probe_id": None,  # 链路校准是全局的
                        "valid_until": link_valid_until.isoformat(),
                        "days_remaining": days_remaining,
                        "calibrated_at": link.calibrated_at.isoformat()
                    })

        # 按剩余天数排序
        results.sort(key=lambda x: x["days_remaining"])

        return results

    def get_expired_calibrations(
        self,
        db: Session,
        calibration_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取已过期的校准列表

        Args:
            db: 数据库会话
            calibration_type: 可选的校准类型筛选

        Returns:
            已过期的校准列表
        """
        now = datetime.utcnow()
        results = []

        calibration_configs = [
            ("amplitude", ProbeAmplitudeCalibration, "valid_until", "calibrated_at"),
            ("phase", ProbePhaseCalibration, "valid_until", "calibrated_at"),
            ("polarization", ProbePolarizationCalibration, "valid_until", "calibrated_at"),
            ("pattern", ProbePattern, "valid_until", "measured_at"),
        ]

        for cal_type, model, valid_until_field, date_field in calibration_configs:
            if calibration_type and calibration_type != cal_type:
                continue

            # 查询已过期但未作废的校准
            query = db.query(model).filter(
                getattr(model, valid_until_field) < now,
                model.status != CalibrationStatus.INVALIDATED.value
            ).order_by(getattr(model, valid_until_field))

            for cal in query.all():
                valid_until = getattr(cal, valid_until_field)
                days_overdue = (now - valid_until).days

                results.append({
                    "calibration_type": cal_type,
                    "calibration_id": str(cal.id),
                    "probe_id": cal.probe_id,
                    "valid_until": valid_until.isoformat(),
                    "days_overdue": days_overdue,
                    "calibrated_at": getattr(cal, date_field).isoformat()
                })

        # 链路校准单独处理
        if not calibration_type or calibration_type == "link":
            link_cals = db.query(LinkCalibration).all()
            for link in link_cals:
                link_valid_until = link.calibrated_at + timedelta(days=LINK_CALIBRATION_VALIDITY_DAYS)
                if link_valid_until < now:
                    days_overdue = (now - link_valid_until).days
                    results.append({
                        "calibration_type": "link",
                        "calibration_id": str(link.id),
                        "probe_id": None,
                        "valid_until": link_valid_until.isoformat(),
                        "days_overdue": days_overdue,
                        "calibrated_at": link.calibrated_at.isoformat()
                    })

        # 按过期天数排序 (最久的在前)
        results.sort(key=lambda x: x["days_overdue"], reverse=True)

        return results
