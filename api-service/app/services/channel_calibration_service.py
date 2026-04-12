"""
Channel Calibration Services

信道校准业务逻辑实现。

包含以下校准算法:
1. 时域校准: PDP分析、RMS时延扩展计算、簇检测、3GPP对比
2. 多普勒校准: 频谱分析、相关性计算
3. 空间相关性校准: 相关系数计算、Laplacian拟合
4. 角度扩展校准: APS拟合
5. 静区校准: 均匀性分析
6. EIS验证: 3D扫描分析

参考: docs/features/calibration/channel-calibration.md
"""
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging
from scipy import signal
from scipy.optimize import curve_fit

from app.models.channel_calibration import (
    ChannelCalibrationSession,
    TemporalChannelCalibration,
    DopplerCalibration,
    SpatialCorrelationCalibration,
    AngularSpreadCalibration,
    ChannelQuietZoneCalibration,
    EISValidation,
    ChannelCalibrationValidity,
    ChannelCalibrationStatus,
)

logger = logging.getLogger(__name__)


# ==================== 3GPP 参考参数 (TR 38.901) ====================

# RMS 时延扩展参考值 (ns) - 根据场景和条件
# 格式: {(scenario_type, scenario_condition): (median, min, max)}
RMS_DELAY_SPREAD_REFERENCE = {
    ("UMa", "LOS"): (93, 50, 200),
    ("UMa", "NLOS"): (363, 200, 600),
    ("UMi", "LOS"): (65, 30, 150),
    ("UMi", "NLOS"): (129, 80, 250),
    ("RMa", "LOS"): (37, 20, 80),
    ("RMa", "NLOS"): (153, 100, 300),
    ("InH", "LOS"): (18, 10, 40),
    ("InH", "NLOS"): (43, 25, 80),
}

# 簇数量参考值 - 根据场景和条件
CLUSTER_COUNT_REFERENCE = {
    ("UMa", "LOS"): 12,
    ("UMa", "NLOS"): 20,
    ("UMi", "LOS"): 12,
    ("UMi", "NLOS"): 19,
    ("RMa", "LOS"): 11,
    ("RMa", "NLOS"): 10,
    ("InH", "LOS"): 15,
    ("InH", "NLOS"): 19,
}

# 角度扩展参考值 (度) - AoA RMS
ANGULAR_SPREAD_REFERENCE = {
    ("UMa", "LOS"): (15, 8, 25),
    ("UMa", "NLOS"): (22, 12, 35),
    ("UMi", "LOS"): (17, 10, 28),
    ("UMi", "NLOS"): (19, 11, 30),
    ("RMa", "LOS"): (12, 5, 20),
    ("RMa", "NLOS"): (16, 8, 25),
    ("InH", "LOS"): (25, 15, 40),
    ("InH", "NLOS"): (35, 20, 50),
}


# ==================== 校准常数 ====================

# 时域校准有效期 (天)
TEMPORAL_VALIDITY_DAYS = 30

# 多普勒校准有效期 (天)
DOPPLER_VALIDITY_DAYS = 30

# 空间相关性校准有效期 (天)
SPATIAL_CORRELATION_VALIDITY_DAYS = 90

# 角度扩展校准有效期 (天)
ANGULAR_SPREAD_VALIDITY_DAYS = 90

# 静区校准有效期 (天)
QUIET_ZONE_VALIDITY_DAYS = 180

# EIS 验证有效期 (天)
EIS_VALIDITY_DAYS = 365

# 光速 (m/s)
SPEED_OF_LIGHT = 299792458


# ==================== 时域校准算法 ====================

def calculate_rms_delay_spread(
    delay_bins_ns: np.ndarray,
    power_db: np.ndarray,
    threshold_db: float = -25.0
) -> Tuple[float, float]:
    """
    计算 RMS 时延扩展

    公式:
        τ_rms = sqrt(E[τ²] - E[τ]²)
        其中:
        E[τ] = Σ P_n · τ_n / Σ P_n
        E[τ²] = Σ P_n · τ_n² / Σ P_n

    Args:
        delay_bins_ns: 时延点数组 (ns)
        power_db: 功率数组 (dB)
        threshold_db: 功率门限 (相对于最大值)

    Returns:
        (rms_delay_spread_ns, max_delay_ns)
    """
    # 转换为线性功率
    power_linear = 10 ** (power_db / 10.0)

    # 应用门限
    max_power = np.max(power_linear)
    threshold_linear = max_power * (10 ** (threshold_db / 10.0))
    mask = power_linear >= threshold_linear

    if np.sum(mask) < 2:
        return 0.0, 0.0

    delays = delay_bins_ns[mask]
    powers = power_linear[mask]

    # 归一化功率
    total_power = np.sum(powers)
    if total_power == 0:
        return 0.0, 0.0

    weights = powers / total_power

    # 计算均值和方差
    mean_delay = np.sum(weights * delays)
    mean_delay_sq = np.sum(weights * delays ** 2)
    rms_delay = np.sqrt(mean_delay_sq - mean_delay ** 2)

    # 最大时延
    max_delay = np.max(delays)

    return float(rms_delay), float(max_delay)


def detect_clusters(
    delay_bins_ns: np.ndarray,
    power_db: np.ndarray,
    threshold_db: float = -25.0,
    min_cluster_separation_ns: float = 20.0
) -> Tuple[List[float], List[float]]:
    """
    检测 PDP 中的簇

    使用局部最大值检测方法识别簇。

    Args:
        delay_bins_ns: 时延点数组 (ns)
        power_db: 功率数组 (dB)
        threshold_db: 功率门限 (相对于最大值)
        min_cluster_separation_ns: 最小簇间隔 (ns)

    Returns:
        (cluster_delays_ns, cluster_powers_db)
    """
    # 应用门限
    max_power = np.max(power_db)
    threshold = max_power + threshold_db
    mask = power_db >= threshold

    if np.sum(mask) < 1:
        return [], []

    # 找到局部最大值
    # 使用 scipy 的 find_peaks
    peaks, properties = signal.find_peaks(
        power_db,
        height=threshold,
        distance=int(min_cluster_separation_ns / (delay_bins_ns[1] - delay_bins_ns[0]))
        if len(delay_bins_ns) > 1 else 1
    )

    if len(peaks) == 0:
        # 如果没有找到峰值，返回最大值点
        max_idx = np.argmax(power_db)
        return [float(delay_bins_ns[max_idx])], [float(power_db[max_idx])]

    cluster_delays = delay_bins_ns[peaks].tolist()
    cluster_powers = power_db[peaks].tolist()

    return cluster_delays, cluster_powers


def compare_with_3gpp_reference(
    scenario_type: str,
    scenario_condition: str,
    measured_rms_delay_ns: float,
    measured_num_clusters: int,
    threshold_percent: float = 10.0
) -> Dict[str, Any]:
    """
    与 3GPP 参考值对比

    Args:
        scenario_type: 场景类型 (UMa, UMi, RMa, InH)
        scenario_condition: 信道条件 (LOS, NLOS)
        measured_rms_delay_ns: 测量的 RMS 时延扩展 (ns)
        measured_num_clusters: 测量的簇数量
        threshold_percent: 误差阈值百分比

    Returns:
        对比结果字典
    """
    key = (scenario_type, scenario_condition)

    # 获取参考值
    ref_delay = RMS_DELAY_SPREAD_REFERENCE.get(key, (100, 50, 200))
    ref_clusters = CLUSTER_COUNT_REFERENCE.get(key, 15)

    ref_rms_delay_ns = ref_delay[0]  # 中位数
    ref_range_ns = [ref_delay[1], ref_delay[2]]  # 范围

    # 计算误差
    rms_error_percent = abs(measured_rms_delay_ns - ref_rms_delay_ns) / ref_rms_delay_ns * 100

    # 簇数量匹配 (允许 ±3)
    cluster_count_match = abs(measured_num_clusters - ref_clusters) <= 3

    # 判断是否通过
    validation_pass = rms_error_percent < threshold_percent

    return {
        "reference_rms_delay_spread_ns": ref_rms_delay_ns,
        "reference_rms_delay_spread_range_ns": ref_range_ns,
        "reference_num_clusters": ref_clusters,
        "rms_error_percent": rms_error_percent,
        "cluster_count_match": cluster_count_match,
        "validation_pass": validation_pass,
    }


def generate_mock_pdp(
    scenario_type: str,
    scenario_condition: str,
    fc_ghz: float,
    max_delay_ns: float = 10000,
    resolution_ns: float = 10
) -> Tuple[np.ndarray, np.ndarray]:
    """
    生成模拟 PDP 数据 (用于测试)

    基于 3GPP TR 38.901 簇状模型生成。

    Args:
        scenario_type: 场景类型
        scenario_condition: 信道条件
        fc_ghz: 载波频率 (GHz)
        max_delay_ns: 最大时延 (ns)
        resolution_ns: 时延分辨率 (ns)

    Returns:
        (delay_bins_ns, power_db)
    """
    key = (scenario_type, scenario_condition)
    ref_delay = RMS_DELAY_SPREAD_REFERENCE.get(key, (100, 50, 200))
    ref_clusters = CLUSTER_COUNT_REFERENCE.get(key, 15)

    # 生成时延轴
    delay_bins = np.arange(0, max_delay_ns, resolution_ns)
    power_linear = np.zeros_like(delay_bins, dtype=float)

    # 生成簇
    num_clusters = ref_clusters
    rms_delay = ref_delay[0]

    # 簇时延遵循指数分布
    cluster_delays = np.sort(np.random.exponential(rms_delay, num_clusters))

    # 簇功率遵循指数衰减
    cluster_powers = np.exp(-cluster_delays / (rms_delay * 2))

    # 为每个簇添加到 PDP
    for i, (delay, power) in enumerate(zip(cluster_delays, cluster_powers)):
        # 找到最近的时延 bin
        idx = np.argmin(np.abs(delay_bins - delay))
        if idx < len(power_linear):
            power_linear[idx] += power

            # 添加一些时延扩展 (簇内扩展)
            intra_cluster_spread = 10  # ns
            for j in range(-3, 4):
                spread_idx = idx + j
                if 0 <= spread_idx < len(power_linear):
                    spread_power = power * np.exp(-(j * resolution_ns / intra_cluster_spread) ** 2)
                    power_linear[spread_idx] += spread_power * 0.3

    # 添加噪底
    noise_floor = np.max(power_linear) * 1e-5
    power_linear += noise_floor

    # 转换为 dB
    power_db = 10 * np.log10(power_linear / np.max(power_linear))

    return delay_bins, power_db


# ==================== 多普勒校准算法 ====================

def calculate_doppler_shift(
    velocity_kmh: float,
    fc_ghz: float
) -> float:
    """
    计算最大多普勒频移

    公式: f_d = v * fc / c

    Args:
        velocity_kmh: 移动速度 (km/h)
        fc_ghz: 载波频率 (GHz)

    Returns:
        最大多普勒频移 (Hz)
    """
    velocity_ms = velocity_kmh / 3.6  # km/h -> m/s
    fc_hz = fc_ghz * 1e9  # GHz -> Hz
    fd = velocity_ms * fc_hz / SPEED_OF_LIGHT
    return fd


def generate_classical_doppler_spectrum(
    fd_hz: float,
    num_bins: int = 512
) -> Tuple[np.ndarray, np.ndarray]:
    """
    生成经典多普勒频谱 (Jake's spectrum)

    公式: S(f) = 1 / (π * fd * sqrt(1 - (f/fd)²))

    Args:
        fd_hz: 最大多普勒频移 (Hz)
        num_bins: 频率 bin 数量

    Returns:
        (frequency_bins_hz, power_density_db)
    """
    # 生成频率轴
    freq_bins = np.linspace(-fd_hz * 1.1, fd_hz * 1.1, num_bins)

    # 计算功率谱密度
    power_density = np.zeros_like(freq_bins)

    for i, f in enumerate(freq_bins):
        if abs(f) < fd_hz:
            # 经典 Jakes 频谱
            denominator = np.pi * fd_hz * np.sqrt(1 - (f / fd_hz) ** 2)
            if denominator > 1e-10:
                power_density[i] = 1 / denominator
            else:
                # 接近边界时的处理
                power_density[i] = power_density[i - 1] if i > 0 else 0

    # 归一化
    if np.max(power_density) > 0:
        power_density = power_density / np.max(power_density)

    # 转换为 dB
    power_density_db = 10 * np.log10(power_density + 1e-10)

    return freq_bins, power_density_db


def calculate_spectral_correlation(
    measured_spectrum: np.ndarray,
    reference_spectrum: np.ndarray
) -> float:
    """
    计算频谱相关性

    使用 Pearson 相关系数。

    Args:
        measured_spectrum: 测量频谱 (线性或 dB)
        reference_spectrum: 参考频谱 (线性或 dB)

    Returns:
        相关系数 (0-1)
    """
    if len(measured_spectrum) != len(reference_spectrum):
        # 插值到相同长度
        from scipy.interpolate import interp1d
        x_meas = np.linspace(0, 1, len(measured_spectrum))
        x_ref = np.linspace(0, 1, len(reference_spectrum))
        f = interp1d(x_ref, reference_spectrum, kind='linear')
        reference_spectrum = f(x_meas)

    # 计算 Pearson 相关系数
    correlation = np.corrcoef(measured_spectrum, reference_spectrum)[0, 1]

    # 取绝对值并限制在 [0, 1]
    correlation = min(max(abs(correlation), 0), 1)

    return float(correlation)


# ==================== 空间相关性校准算法 ====================

def calculate_theoretical_correlation_laplacian(
    antenna_spacing_wavelengths: float,
    angular_spread_deg: float
) -> complex:
    """
    计算理论空间相关性 (Laplacian 角度分布)

    3GPP TR 38.901 定义的 Laplacian 分布:
    P(θ) = exp(-√2 * |θ - θ_mean| / σ_θ) / (√2 * σ_θ)

    相关系数:
    ρ = ∫ P(θ) * e^(j * k * d * sin(θ)) dθ

    对于 Laplacian 分布，简化公式:
    |ρ| ≈ (1 + (2π * d / λ * σ_θ)²)^(-1)

    Args:
        antenna_spacing_wavelengths: 天线间距 (波长)
        angular_spread_deg: RMS 角度扩展 (度)

    Returns:
        复数相关系数
    """
    angular_spread_rad = np.deg2rad(angular_spread_deg)
    d = antenna_spacing_wavelengths  # 以波长为单位

    # 简化计算 (适用于小角度扩展)
    denominator = 1 + (2 * np.pi * d * angular_spread_rad) ** 2
    magnitude = 1 / np.sqrt(denominator)

    # 相位为 0 (对称分布)
    phase = 0

    return magnitude * np.exp(1j * phase)


def calculate_measured_correlation(
    h1: np.ndarray,
    h2: np.ndarray
) -> Tuple[float, float, float]:
    """
    计算测量的空间相关性

    公式: ρ = E[h1 · h2*] / sqrt(E[|h1|²] · E[|h2|²])

    Args:
        h1: 第一个天线的复数信道系数数组
        h2: 第二个天线的复数信道系数数组

    Returns:
        (magnitude, phase_deg, confidence_interval_width)
    """
    # 确保长度相同
    min_len = min(len(h1), len(h2))
    h1 = h1[:min_len]
    h2 = h2[:min_len]

    # 计算相关系数
    numerator = np.mean(h1 * np.conj(h2))
    denominator = np.sqrt(np.mean(np.abs(h1) ** 2) * np.mean(np.abs(h2) ** 2))

    if denominator < 1e-10:
        return 0.0, 0.0, 1.0

    rho = numerator / denominator

    magnitude = np.abs(rho)
    phase_deg = np.rad2deg(np.angle(rho))

    # 计算置信区间 (基于 Fisher 变换)
    z = np.arctanh(magnitude)
    se = 1 / np.sqrt(len(h1) - 3) if len(h1) > 3 else 0.5
    ci_width = 1.96 * se  # 95% 置信区间

    return float(magnitude), float(phase_deg), float(ci_width)


# ==================== 角度扩展校准算法 ====================

def laplacian_distribution(theta: np.ndarray, mean: float, sigma: float, amplitude: float = 1.0) -> np.ndarray:
    """Laplacian 角度分布函数"""
    return amplitude * np.exp(-np.sqrt(2) * np.abs(theta - mean) / sigma) / (np.sqrt(2) * sigma)


def gaussian_distribution(theta: np.ndarray, mean: float, sigma: float, amplitude: float = 1.0) -> np.ndarray:
    """Gaussian 角度分布函数"""
    return amplitude * np.exp(-((theta - mean) ** 2) / (2 * sigma ** 2)) / (sigma * np.sqrt(2 * np.pi))


def fit_angular_power_spectrum(
    azimuth_deg: np.ndarray,
    power_db: np.ndarray,
    distribution_type: str = "Laplacian"
) -> Tuple[float, float, float, str]:
    """
    拟合角度功率谱

    Args:
        azimuth_deg: 方位角数组 (度)
        power_db: 功率数组 (dB)
        distribution_type: 分布类型 ("Laplacian" 或 "Gaussian")

    Returns:
        (mean_azimuth_deg, rms_angular_spread_deg, r_squared, distribution_type)
    """
    # 转换为线性功率
    power_linear = 10 ** (power_db / 10)
    power_normalized = power_linear / np.max(power_linear)

    # 初始估计
    # 均值: 最大功率位置
    mean_init = azimuth_deg[np.argmax(power_linear)]

    # 方差: 基于二阶矩
    weights = power_normalized / np.sum(power_normalized)
    sigma_init = np.sqrt(np.sum(weights * (azimuth_deg - mean_init) ** 2))
    sigma_init = max(sigma_init, 5)  # 最小 5 度

    try:
        if distribution_type == "Laplacian":
            popt, _ = curve_fit(
                laplacian_distribution,
                azimuth_deg,
                power_normalized,
                p0=[mean_init, sigma_init, 1.0],
                bounds=([-180, 1, 0.1], [180, 90, 10]),
                maxfev=5000
            )
        else:  # Gaussian
            popt, _ = curve_fit(
                gaussian_distribution,
                azimuth_deg,
                power_normalized,
                p0=[mean_init, sigma_init, 1.0],
                bounds=([-180, 1, 0.1], [180, 90, 10]),
                maxfev=5000
            )

        mean_deg = popt[0]
        sigma_deg = popt[1]

        # 计算 R²
        if distribution_type == "Laplacian":
            fitted = laplacian_distribution(azimuth_deg, *popt)
        else:
            fitted = gaussian_distribution(azimuth_deg, *popt)

        ss_res = np.sum((power_normalized - fitted) ** 2)
        ss_tot = np.sum((power_normalized - np.mean(power_normalized)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    except Exception as e:
        logger.warning(f"Fitting failed: {e}, using initial estimates")
        mean_deg = mean_init
        sigma_deg = sigma_init
        r_squared = 0.0

    return float(mean_deg), float(sigma_deg), float(r_squared), distribution_type


# ==================== 静区校准算法 ====================

def calculate_uniformity_stats(
    values: np.ndarray
) -> Tuple[float, float, Tuple[float, float]]:
    """
    计算均匀性统计

    Args:
        values: 值数组

    Returns:
        (mean, std, (min, max))
    """
    mean_val = np.mean(values)
    std_val = np.std(values)
    range_val = (float(np.min(values)), float(np.max(values)))

    return float(mean_val), float(std_val), range_val


def validate_quiet_zone_uniformity(
    amplitude_std_db: float,
    phase_std_deg: float,
    amplitude_threshold_db: float = 1.0,
    phase_threshold_deg: float = 30.0
) -> Tuple[bool, bool, bool]:
    """
    验证静区均匀性

    Args:
        amplitude_std_db: 幅度标准差 (dB)
        phase_std_deg: 相位标准差 (度)
        amplitude_threshold_db: 幅度阈值 (dB)
        phase_threshold_deg: 相位阈值 (度)

    Returns:
        (amplitude_pass, phase_pass, overall_pass)
    """
    amplitude_pass = amplitude_std_db <= amplitude_threshold_db
    phase_pass = phase_std_deg <= phase_threshold_deg
    overall_pass = amplitude_pass and phase_pass

    return amplitude_pass, phase_pass, overall_pass


# ==================== 服务层函数 ====================

class ChannelCalibrationService:
    """信道校准服务"""

    def __init__(self, db: Session):
        self.db = db

    # ========== 会话管理 ==========

    def create_session(
        self,
        name: str,
        description: Optional[str] = None,
        workflow_id: Optional[str] = None,
        configuration: Optional[Dict] = None,
        created_by: Optional[str] = None
    ) -> ChannelCalibrationSession:
        """创建校准会话"""
        session = ChannelCalibrationSession(
            name=name,
            description=description,
            workflow_id=workflow_id,
            configuration=configuration,
            created_by=created_by,
            status="running",
            progress_percent=0,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_session_progress(
        self,
        session_id: UUID,
        progress_percent: int,
        current_stage: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[ChannelCalibrationSession]:
        """更新会话进度"""
        session = self.db.query(ChannelCalibrationSession).filter(
            ChannelCalibrationSession.id == session_id
        ).first()

        if not session:
            return None

        session.progress_percent = progress_percent
        if current_stage:
            session.current_stage = current_stage
        if status:
            session.status = status

        self.db.commit()
        self.db.refresh(session)
        return session

    def complete_session(
        self,
        session_id: UUID,
        overall_pass: bool,
        total_calibrations: int,
        passed_calibrations: int,
        failed_calibrations: int
    ) -> Optional[ChannelCalibrationSession]:
        """完成校准会话"""
        session = self.db.query(ChannelCalibrationSession).filter(
            ChannelCalibrationSession.id == session_id
        ).first()

        if not session:
            return None

        session.status = "completed"
        session.progress_percent = 100
        session.completed_at = datetime.utcnow()
        session.duration_minutes = (
            (session.completed_at - session.started_at).total_seconds() / 60
        )
        session.overall_pass = overall_pass
        session.total_calibrations = total_calibrations
        session.passed_calibrations = passed_calibrations
        session.failed_calibrations = failed_calibrations

        self.db.commit()
        self.db.refresh(session)
        return session

    # ========== 时域校准 ==========

    def run_temporal_calibration(
        self,
        scenario_type: str,
        scenario_condition: str,
        fc_ghz: float,
        distance_2d_m: Optional[float] = None,
        session_id: Optional[UUID] = None,
        channel_emulator: Optional[str] = None,
        calibrated_by: Optional[str] = None
    ) -> TemporalChannelCalibration:
        """
        执行时域信道校准

        1. 生成/获取 PDP 数据
        2. 计算 RMS 时延扩展
        3. 检测簇
        4. 与 3GPP 参考对比
        5. 保存结果
        """
        # 生成模拟 PDP (实际实现应从仪器获取)
        delay_bins, power_db = generate_mock_pdp(
            scenario_type, scenario_condition, fc_ghz
        )

        # 计算 RMS 时延扩展
        rms_delay_ns, max_delay_ns = calculate_rms_delay_spread(delay_bins, power_db)

        # 检测簇
        cluster_delays, cluster_powers = detect_clusters(delay_bins, power_db)

        # 与 3GPP 对比
        comparison = compare_with_3gpp_reference(
            scenario_type,
            scenario_condition,
            rms_delay_ns,
            len(cluster_delays)
        )

        # 创建校准记录
        calibration = TemporalChannelCalibration(
            session_id=session_id,
            scenario_type=scenario_type,
            scenario_condition=scenario_condition,
            fc_ghz=fc_ghz,
            distance_2d_m=distance_2d_m,
            # PDP 数据
            measured_pdp={
                "delay_bins_ns": delay_bins.tolist(),
                "power_db": power_db.tolist()
            },
            # 测量参数
            measured_rms_delay_spread_ns=rms_delay_ns,
            measured_max_delay_ns=max_delay_ns,
            measured_num_clusters=len(cluster_delays),
            measured_cluster_delays_ns=cluster_delays,
            measured_cluster_powers_db=cluster_powers,
            # 参考参数
            reference_rms_delay_spread_ns=comparison["reference_rms_delay_spread_ns"],
            reference_rms_delay_spread_range_ns=comparison["reference_rms_delay_spread_range_ns"],
            reference_num_clusters=comparison["reference_num_clusters"],
            # 验证结果
            rms_error_percent=comparison["rms_error_percent"],
            cluster_count_match=comparison["cluster_count_match"],
            validation_pass=comparison["validation_pass"],
            threshold_percent=10.0,
            # 元数据
            channel_emulator=channel_emulator,
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=TEMPORAL_VALIDITY_DAYS),
            status=ChannelCalibrationStatus.VALID.value,
        )

        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return calibration

    # ========== 多普勒校准 ==========

    def run_doppler_calibration(
        self,
        velocity_kmh: float,
        fc_ghz: float,
        session_id: Optional[UUID] = None,
        channel_emulator: Optional[str] = None,
        calibrated_by: Optional[str] = None
    ) -> DopplerCalibration:
        """
        执行多普勒校准

        1. 计算预期多普勒频移
        2. 生成参考频谱
        3. 获取/模拟测量频谱
        4. 计算频谱相关性
        5. 保存结果
        """
        # 计算预期多普勒频移
        expected_doppler = calculate_doppler_shift(velocity_kmh, fc_ghz)

        # 生成参考频谱
        ref_freq, ref_power = generate_classical_doppler_spectrum(expected_doppler)

        # 模拟测量频谱 (添加一些噪声)
        meas_power = ref_power + np.random.normal(0, 0.5, len(ref_power))

        # 计算相关性
        correlation = calculate_spectral_correlation(meas_power, ref_power)

        # 计算多普勒扩展误差
        doppler_spread_error = abs(1 - correlation) * 100  # 简化计算

        # 验证
        threshold_correlation = 0.9
        validation_pass = correlation >= threshold_correlation

        # 创建校准记录
        calibration = DopplerCalibration(
            session_id=session_id,
            velocity_kmh=velocity_kmh,
            fc_ghz=fc_ghz,
            expected_doppler_hz=expected_doppler,
            measured_spectrum={
                "frequency_bins_hz": ref_freq.tolist(),
                "power_density_db": meas_power.tolist()
            },
            reference_spectrum={
                "frequency_bins_hz": ref_freq.tolist(),
                "power_density_db": ref_power.tolist()
            },
            spectral_correlation=correlation,
            doppler_spread_error_percent=doppler_spread_error,
            validation_pass=validation_pass,
            threshold_correlation=threshold_correlation,
            channel_emulator=channel_emulator,
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=DOPPLER_VALIDITY_DAYS),
            status=ChannelCalibrationStatus.VALID.value,
        )

        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return calibration

    # ========== 空间相关性校准 ==========

    def run_spatial_correlation_calibration(
        self,
        scenario_type: str,
        scenario_condition: str,
        fc_ghz: float,
        antenna_spacing_wavelengths: float,
        antenna_spacing_m: Optional[float] = None,
        antenna_type: str = "dipole",
        session_id: Optional[UUID] = None,
        calibrated_by: Optional[str] = None
    ) -> SpatialCorrelationCalibration:
        """
        执行空间相关性校准
        """
        # 获取参考角度扩展
        key = (scenario_type, scenario_condition)
        ref_angular = ANGULAR_SPREAD_REFERENCE.get(key, (15, 8, 25))
        angular_spread_deg = ref_angular[0]

        # 计算理论相关性
        theoretical_correlation = calculate_theoretical_correlation_laplacian(
            antenna_spacing_wavelengths,
            angular_spread_deg
        )

        # 模拟测量 (生成随机信道系数)
        num_samples = 10000
        h1 = np.random.randn(num_samples) + 1j * np.random.randn(num_samples)
        h2 = theoretical_correlation * h1 + (
            np.sqrt(1 - abs(theoretical_correlation) ** 2) *
            (np.random.randn(num_samples) + 1j * np.random.randn(num_samples))
        )

        # 计算测量相关性
        meas_mag, meas_phase, ci_width = calculate_measured_correlation(h1, h2)

        # 验证
        ref_magnitude = abs(theoretical_correlation)
        ref_phase = np.rad2deg(np.angle(theoretical_correlation))
        magnitude_error = abs(meas_mag - ref_magnitude)
        phase_error = abs(meas_phase - ref_phase)

        threshold_magnitude = 0.1
        threshold_phase = 10.0
        validation_pass = magnitude_error < threshold_magnitude and phase_error < threshold_phase

        # 创建校准记录
        calibration = SpatialCorrelationCalibration(
            session_id=session_id,
            scenario_type=scenario_type,
            scenario_condition=scenario_condition,
            fc_ghz=fc_ghz,
            angular_spread_deg=angular_spread_deg,
            antenna_spacing_wavelengths=antenna_spacing_wavelengths,
            antenna_spacing_m=antenna_spacing_m,
            antenna_type=antenna_type,
            measured_correlation_magnitude=meas_mag,
            measured_correlation_phase_deg=meas_phase,
            samples=num_samples,
            confidence_interval=[meas_mag - ci_width, meas_mag + ci_width],
            reference_correlation_magnitude=ref_magnitude,
            reference_correlation_phase_deg=ref_phase,
            calculation_method="3GPP_TR_38_901_Laplacian",
            magnitude_error=magnitude_error,
            phase_error_deg=phase_error,
            validation_pass=validation_pass,
            threshold_magnitude=threshold_magnitude,
            threshold_phase_deg=threshold_phase,
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=SPATIAL_CORRELATION_VALIDITY_DAYS),
            status=ChannelCalibrationStatus.VALID.value,
        )

        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return calibration

    # ========== 角度扩展校准 ==========

    def run_angular_spread_calibration(
        self,
        scenario_type: str,
        scenario_condition: str,
        fc_ghz: float,
        azimuth_step_deg: float = 5.0,
        session_id: Optional[UUID] = None,
        positioner: Optional[str] = None,
        calibrated_by: Optional[str] = None
    ) -> AngularSpreadCalibration:
        """
        执行角度扩展校准

        1. 生成/获取角度功率谱 (APS)
        2. 拟合 Laplacian 分布
        3. 提取 RMS 角度扩展
        4. 与 3GPP 参考对比
        5. 保存结果
        """
        # 获取参考值
        key = (scenario_type, scenario_condition)
        ref_angular = ANGULAR_SPREAD_REFERENCE.get(key, (15, 8, 25))
        ref_rms = ref_angular[0]
        ref_range = [ref_angular[1], ref_angular[2]]

        # 生成模拟 APS 数据 (实际实现应从转台测量获取)
        azimuth_deg = np.arange(-180, 180, azimuth_step_deg)

        # 使用 Laplacian 分布生成模拟数据 (添加噪声)
        sigma = ref_rms * (0.9 + 0.2 * np.random.random())  # 参考值 ±10%
        power_linear = np.exp(-np.sqrt(2) * np.abs(azimuth_deg) / sigma)
        power_linear += 0.01 * np.random.random(len(azimuth_deg))  # 噪底
        power_db = 10 * np.log10(power_linear / np.max(power_linear))

        # 拟合
        mean_deg, rms_deg, r_squared, dist_type = fit_angular_power_spectrum(
            azimuth_deg, power_db, "Laplacian"
        )

        # 计算误差
        rms_error_deg = abs(rms_deg - ref_rms)
        threshold_deg = 5.0
        validation_pass = rms_error_deg < threshold_deg

        # 创建校准记录
        calibration = AngularSpreadCalibration(
            session_id=session_id,
            scenario_type=scenario_type,
            scenario_condition=scenario_condition,
            fc_ghz=fc_ghz,
            measured_aps={
                "azimuth_deg": azimuth_deg.tolist(),
                "power_db": power_db.tolist()
            },
            fitted_mean_azimuth_deg=mean_deg,
            fitted_rms_angular_spread_deg=rms_deg,
            fitted_distribution_type=dist_type,
            fitted_r_squared=r_squared,
            reference_rms_angular_spread_deg=ref_rms,
            reference_rms_angular_spread_range_deg=ref_range,
            rms_error_deg=rms_error_deg,
            validation_pass=validation_pass,
            threshold_deg=threshold_deg,
            positioner=positioner,
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=ANGULAR_SPREAD_VALIDITY_DAYS),
            status=ChannelCalibrationStatus.VALID.value,
        )

        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return calibration

    # ========== 静区校准 ==========

    def run_quiet_zone_calibration(
        self,
        quiet_zone_shape: str,
        quiet_zone_diameter_m: float,
        fc_ghz: float,
        num_points: int = 100,
        quiet_zone_height_m: Optional[float] = None,
        field_probe_type: str = "dipole",
        field_probe_size_mm: float = 10.0,
        session_id: Optional[UUID] = None,
        calibrated_by: Optional[str] = None
    ) -> ChannelQuietZoneCalibration:
        """
        执行静区均匀性校准

        1. 生成测量网格
        2. 获取/模拟场幅度和相位数据
        3. 计算均匀性统计
        4. 验证是否满足要求
        5. 保存结果
        """
        # 生成测量网格
        if quiet_zone_shape == "sphere":
            # 球形静区: 生成 3D 网格点
            points = []
            radius = quiet_zone_diameter_m / 2
            n_per_axis = int(np.ceil(num_points ** (1/3)))

            for i in range(n_per_axis):
                for j in range(n_per_axis):
                    for k in range(n_per_axis):
                        x = (i / (n_per_axis - 1) - 0.5) * quiet_zone_diameter_m
                        y = (j / (n_per_axis - 1) - 0.5) * quiet_zone_diameter_m
                        z = (k / (n_per_axis - 1) - 0.5) * quiet_zone_diameter_m

                        # 只保留球内的点
                        if np.sqrt(x**2 + y**2 + z**2) <= radius:
                            # 模拟测量数据
                            amplitude = 1.0 + np.random.normal(0, 0.1)
                            phase = np.random.normal(0, 10)
                            points.append({
                                "x_m": x, "y_m": y, "z_m": z,
                                "amplitude_v_per_m": amplitude,
                                "phase_deg": phase
                            })
                            if len(points) >= num_points:
                                break
                    if len(points) >= num_points:
                        break
                if len(points) >= num_points:
                    break
        else:
            # 圆柱形静区
            points = []
            radius = quiet_zone_diameter_m / 2
            height = quiet_zone_height_m or quiet_zone_diameter_m

            for _ in range(num_points):
                r = radius * np.sqrt(np.random.random())
                theta = 2 * np.pi * np.random.random()
                x = r * np.cos(theta)
                y = r * np.sin(theta)
                z = (np.random.random() - 0.5) * height

                amplitude = 1.0 + np.random.normal(0, 0.1)
                phase = np.random.normal(0, 10)
                points.append({
                    "x_m": x, "y_m": y, "z_m": z,
                    "amplitude_v_per_m": amplitude,
                    "phase_deg": phase
                })

        # 计算统计
        amplitudes_db = 20 * np.log10([p["amplitude_v_per_m"] for p in points])
        phases_deg = np.array([p["phase_deg"] for p in points])

        amp_mean, amp_std, amp_range = calculate_uniformity_stats(amplitudes_db)
        phase_mean, phase_std, phase_range = calculate_uniformity_stats(phases_deg)

        # 验证
        amplitude_threshold_db = 1.0
        phase_threshold_deg = 30.0
        amp_pass, phase_pass, overall_pass = validate_quiet_zone_uniformity(
            amp_std, phase_std, amplitude_threshold_db, phase_threshold_deg
        )

        # 创建校准记录
        calibration = ChannelQuietZoneCalibration(
            session_id=session_id,
            quiet_zone_shape=quiet_zone_shape,
            quiet_zone_diameter_m=quiet_zone_diameter_m,
            quiet_zone_height_m=quiet_zone_height_m,
            field_probe_type=field_probe_type,
            field_probe_size_mm=field_probe_size_mm,
            measurement_grid={"points": points},
            num_points=len(points),
            amplitude_mean_db=amp_mean,
            amplitude_std_db=amp_std,
            amplitude_range_db=list(amp_range),
            phase_mean_deg=phase_mean,
            phase_std_deg=phase_std,
            phase_range_deg=list(phase_range),
            amplitude_uniformity_pass=amp_pass,
            phase_uniformity_pass=phase_pass,
            validation_pass=overall_pass,
            amplitude_threshold_db=amplitude_threshold_db,
            phase_threshold_deg=phase_threshold_deg,
            fc_ghz=fc_ghz,
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=QUIET_ZONE_VALIDITY_DAYS),
            status=ChannelCalibrationStatus.VALID.value,
        )

        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return calibration

    # ========== EIS 验证 ==========

    def run_eis_validation(
        self,
        fc_ghz: float,
        dut_model: str,
        dut_type: str = "vehicle",
        scenario: Optional[str] = None,
        bandwidth_mhz: Optional[float] = None,
        modulation: Optional[str] = None,
        target_throughput_percent: float = 95.0,
        num_rx_antennas: Optional[int] = None,
        min_eis_dbm: Optional[float] = None,
        session_id: Optional[UUID] = None,
        measured_by: Optional[str] = None
    ) -> EISValidation:
        """
        执行 EIS 验证

        1. 配置 3D 扫描网格
        2. 获取/模拟 EIS 测量数据
        3. 计算峰值、中位数等统计
        4. 验证是否满足要求
        5. 保存结果
        """
        # 生成 3D 扫描网格
        azimuth_deg = np.arange(0, 360, 15).tolist()
        elevation_deg = np.arange(-90, 91, 15).tolist()

        # 模拟 EIS 测量数据 (实际应从 DUT 测量获取)
        # EIS 通常在 -100 到 -80 dBm 范围内
        base_eis = -90.0
        eis_map = []
        for el in elevation_deg:
            row = []
            for az in azimuth_deg:
                # 添加一些空间变化
                pattern_factor = np.cos(np.deg2rad(el)) * 0.5 + 0.5
                noise = np.random.normal(0, 2)
                eis = base_eis + 10 * pattern_factor + noise
                row.append(eis)
            eis_map.append(row)

        eis_array = np.array(eis_map)

        # 计算统计
        peak_eis = float(np.max(eis_array))
        peak_idx = np.unravel_index(np.argmax(eis_array), eis_array.shape)
        peak_elevation = elevation_deg[peak_idx[0]]
        peak_azimuth = azimuth_deg[peak_idx[1]]

        median_eis = float(np.median(eis_array))
        percentile_5 = float(np.percentile(eis_array, 5))
        eis_spread = peak_eis - percentile_5

        # 验证
        if min_eis_dbm is None:
            min_eis_dbm = -96.0  # FR1 默认要求
        validation_pass = peak_eis >= min_eis_dbm

        # 创建验证记录
        validation = EISValidation(
            session_id=session_id,
            scenario=scenario,
            fc_ghz=fc_ghz,
            bandwidth_mhz=bandwidth_mhz,
            modulation=modulation,
            target_throughput_percent=target_throughput_percent,
            dut_type=dut_type,
            dut_model=dut_model,
            num_rx_antennas=num_rx_antennas,
            eis_map={
                "azimuth_deg": azimuth_deg,
                "elevation_deg": elevation_deg,
                "eis_dbm": eis_map
            },
            peak_eis_dbm=peak_eis,
            peak_azimuth_deg=peak_azimuth,
            peak_elevation_deg=peak_elevation,
            median_eis_dbm=median_eis,
            eis_spread_db=eis_spread,
            min_eis_dbm=min_eis_dbm,
            validation_pass=validation_pass,
            measured_at=datetime.utcnow(),
            measured_by=measured_by,
            valid_until=datetime.utcnow() + timedelta(days=EIS_VALIDITY_DAYS),
            status=ChannelCalibrationStatus.VALID.value,
        )

        self.db.add(validation)
        self.db.commit()
        self.db.refresh(validation)

        return validation

    # ========== 查询方法 ==========

    def get_temporal_calibration(self, calibration_id: UUID) -> Optional[TemporalChannelCalibration]:
        """获取时域校准记录"""
        return self.db.query(TemporalChannelCalibration).filter(
            TemporalChannelCalibration.id == calibration_id
        ).first()

    def get_latest_temporal_calibration(
        self,
        scenario_type: Optional[str] = None,
        scenario_condition: Optional[str] = None
    ) -> Optional[TemporalChannelCalibration]:
        """获取最新的时域校准记录"""
        query = self.db.query(TemporalChannelCalibration)
        if scenario_type:
            query = query.filter(TemporalChannelCalibration.scenario_type == scenario_type)
        if scenario_condition:
            query = query.filter(TemporalChannelCalibration.scenario_condition == scenario_condition)
        return query.order_by(desc(TemporalChannelCalibration.calibrated_at)).first()

    def get_doppler_calibration(self, calibration_id: UUID) -> Optional[DopplerCalibration]:
        """获取多普勒校准记录"""
        return self.db.query(DopplerCalibration).filter(
            DopplerCalibration.id == calibration_id
        ).first()

    def get_spatial_correlation_calibration(
        self,
        calibration_id: UUID
    ) -> Optional[SpatialCorrelationCalibration]:
        """获取空间相关性校准记录"""
        return self.db.query(SpatialCorrelationCalibration).filter(
            SpatialCorrelationCalibration.id == calibration_id
        ).first()

    def get_angular_spread_calibration(
        self,
        calibration_id: UUID
    ) -> Optional[AngularSpreadCalibration]:
        """获取角度扩展校准记录"""
        return self.db.query(AngularSpreadCalibration).filter(
            AngularSpreadCalibration.id == calibration_id
        ).first()

    def get_quiet_zone_calibration(
        self,
        calibration_id: UUID
    ) -> Optional[ChannelQuietZoneCalibration]:
        """获取静区校准记录"""
        return self.db.query(ChannelQuietZoneCalibration).filter(
            ChannelQuietZoneCalibration.id == calibration_id
        ).first()

    def get_eis_validation(
        self,
        calibration_id: UUID
    ) -> Optional[EISValidation]:
        """获取 EIS 验证记录"""
        return self.db.query(EISValidation).filter(
            EISValidation.id == calibration_id
        ).first()

    def get_session(self, session_id: UUID) -> Optional[ChannelCalibrationSession]:
        """获取校准会话"""
        return self.db.query(ChannelCalibrationSession).filter(
            ChannelCalibrationSession.id == session_id
        ).first()

    def list_calibrations(
        self,
        calibration_type: Optional[str] = None,
        validation_pass: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict]:
        """列出校准记录"""
        results = []

        # 时域校准
        if calibration_type in (None, "temporal"):
            query = self.db.query(TemporalChannelCalibration)
            if validation_pass is not None:
                query = query.filter(TemporalChannelCalibration.validation_pass == validation_pass)
            for cal in query.order_by(desc(TemporalChannelCalibration.calibrated_at)).limit(limit).offset(offset):
                results.append({
                    "calibration_id": cal.id,
                    "calibration_type": "temporal",
                    "calibrated_at": cal.calibrated_at,
                    "calibrated_by": cal.calibrated_by,
                    "status": cal.status,
                    "validation_pass": cal.validation_pass,
                    "summary": {
                        "scenario": f"{cal.scenario_type} {cal.scenario_condition}",
                        "rms_error_percent": cal.rms_error_percent,
                    }
                })

        # 多普勒校准
        if calibration_type in (None, "doppler"):
            query = self.db.query(DopplerCalibration)
            if validation_pass is not None:
                query = query.filter(DopplerCalibration.validation_pass == validation_pass)
            for cal in query.order_by(desc(DopplerCalibration.calibrated_at)).limit(limit).offset(offset):
                results.append({
                    "calibration_id": cal.id,
                    "calibration_type": "doppler",
                    "calibrated_at": cal.calibrated_at,
                    "calibrated_by": cal.calibrated_by,
                    "status": cal.status,
                    "validation_pass": cal.validation_pass,
                    "summary": {
                        "velocity_kmh": cal.velocity_kmh,
                        "spectral_correlation": cal.spectral_correlation,
                    }
                })

        # 空间相关性校准
        if calibration_type in (None, "spatial_correlation"):
            query = self.db.query(SpatialCorrelationCalibration)
            if validation_pass is not None:
                query = query.filter(SpatialCorrelationCalibration.validation_pass == validation_pass)
            for cal in query.order_by(desc(SpatialCorrelationCalibration.calibrated_at)).limit(limit).offset(offset):
                results.append({
                    "calibration_id": cal.id,
                    "calibration_type": "spatial_correlation",
                    "calibrated_at": cal.calibrated_at,
                    "calibrated_by": cal.calibrated_by,
                    "status": cal.status,
                    "validation_pass": cal.validation_pass,
                    "summary": {
                        "scenario": f"{cal.scenario_type} {cal.scenario_condition}",
                        "magnitude_error": cal.magnitude_error,
                    }
                })

        # 角度扩展校准
        if calibration_type in (None, "angular_spread"):
            query = self.db.query(AngularSpreadCalibration)
            if validation_pass is not None:
                query = query.filter(AngularSpreadCalibration.validation_pass == validation_pass)
            for cal in query.order_by(desc(AngularSpreadCalibration.calibrated_at)).limit(limit).offset(offset):
                results.append({
                    "calibration_id": cal.id,
                    "calibration_type": "angular_spread",
                    "calibrated_at": cal.calibrated_at,
                    "calibrated_by": cal.calibrated_by,
                    "status": cal.status,
                    "validation_pass": cal.validation_pass,
                    "summary": {
                        "scenario": f"{cal.scenario_type} {cal.scenario_condition}",
                        "rms_angular_spread_deg": cal.fitted_rms_angular_spread_deg,
                    }
                })

        # 静区校准
        if calibration_type in (None, "quiet_zone"):
            query = self.db.query(ChannelQuietZoneCalibration)
            if validation_pass is not None:
                query = query.filter(ChannelQuietZoneCalibration.validation_pass == validation_pass)
            for cal in query.order_by(desc(ChannelQuietZoneCalibration.calibrated_at)).limit(limit).offset(offset):
                results.append({
                    "calibration_id": cal.id,
                    "calibration_type": "quiet_zone",
                    "calibrated_at": cal.calibrated_at,
                    "calibrated_by": cal.calibrated_by,
                    "status": cal.status,
                    "validation_pass": cal.validation_pass,
                    "summary": {
                        "shape": cal.quiet_zone_shape,
                        "diameter_m": cal.quiet_zone_diameter_m,
                        "amplitude_std_db": cal.amplitude_std_db,
                    }
                })

        # EIS 验证
        if calibration_type in (None, "eis"):
            query = self.db.query(EISValidation)
            if validation_pass is not None:
                query = query.filter(EISValidation.validation_pass == validation_pass)
            for cal in query.order_by(desc(EISValidation.measured_at)).limit(limit).offset(offset):
                results.append({
                    "calibration_id": cal.id,
                    "calibration_type": "eis",
                    "calibrated_at": cal.measured_at,
                    "calibrated_by": cal.measured_by,
                    "status": cal.status,
                    "validation_pass": cal.validation_pass,
                    "summary": {
                        "dut_model": cal.dut_model,
                        "peak_eis_dbm": cal.peak_eis_dbm,
                    }
                })

        # 按时间排序
        results.sort(key=lambda x: x["calibrated_at"], reverse=True)

        return results[:limit]
