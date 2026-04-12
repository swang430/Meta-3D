"""
Channel Calibration Database Models

信道校准数据模型，包含以下校准类型：
1. 时域信道校准 (Temporal Channel Calibration) - PDP、时延扩展
2. 多普勒校准 (Doppler Calibration) - 多普勒频谱
3. 空间相关性校准 (Spatial Correlation Calibration) - MIMO天线相关性
4. 角度扩展校准 (Angular Spread Calibration) - AoA/AoD扩展
5. 静区均匀性校准 (Quiet Zone Calibration) - 场均匀性
6. EIS验证 (EIS Validation) - 端到端性能验证
7. 校准会话 (Calibration Session) - 关联校准记录

参考设计: docs/features/calibration/channel-calibration.md
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from datetime import datetime
import enum

from app.db.database import Base


# ============================================================================
# Enums
# ============================================================================

class ScenarioType(str, enum.Enum):
    """3GPP信道场景类型"""
    UMA = "UMa"       # Urban Macro
    UMI = "UMi"       # Urban Micro
    RMA = "RMa"       # Rural Macro
    INH = "InH"       # Indoor Hotspot


class ScenarioCondition(str, enum.Enum):
    """3GPP信道条件"""
    LOS = "LOS"       # Line of Sight
    NLOS = "NLOS"     # Non-Line of Sight
    O2I = "O2I"       # Outdoor to Indoor


class DistributionType(str, enum.Enum):
    """角度分布类型"""
    LAPLACIAN = "Laplacian"
    GAUSSIAN = "Gaussian"


class QuietZoneShape(str, enum.Enum):
    """静区形状"""
    SPHERE = "sphere"
    CYLINDER = "cylinder"


class FieldProbeType(str, enum.Enum):
    """场探头类型"""
    DIPOLE = "dipole"
    LOOP = "loop"


class DUTType(str, enum.Enum):
    """被测设备类型"""
    SMARTPHONE = "smartphone"
    VEHICLE = "vehicle"
    MODULE = "module"


class ChannelCalibrationStatus(str, enum.Enum):
    """信道校准状态"""
    VALID = "valid"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    PENDING = "pending"


# ============================================================================
# Calibration Session
# ============================================================================

class ChannelCalibrationSession(Base):
    """
    信道校准会话

    用于关联一次完整校准流程中的所有校准记录。
    一个会话可以包含多个不同类型的校准（时域、空间、EIS等）。
    """
    __tablename__ = "channel_calibration_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, comment="会话名称")
    description = Column(Text, comment="会话描述")

    # 会话配置
    workflow_id = Column(String(100), comment="执行的工作流ID")
    configuration = Column(JSON, comment="会话配置参数")

    # 时间信息
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, comment="完成时间")
    duration_minutes = Column(Float, comment="持续时间（分钟）")

    # 状态
    status = Column(
        String(50), default="running",
        comment="状态: running, completed, failed, cancelled"
    )
    progress_percent = Column(Integer, default=0, comment="进度百分比")
    current_stage = Column(String(100), comment="当前阶段")

    # 结果汇总
    total_calibrations = Column(Integer, default=0, comment="总校准数")
    passed_calibrations = Column(Integer, default=0, comment="通过数")
    failed_calibrations = Column(Integer, default=0, comment="失败数")
    overall_pass = Column(Boolean, comment="总体是否通过")

    # 操作人员
    created_by = Column(String(100), comment="创建人员")

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# Temporal Channel Calibration (时域信道校准)
# ============================================================================

class TemporalChannelCalibration(Base):
    """
    时域信道校准记录

    验证信道仿真器能否正确生成3GPP定义的功率时延谱(PDP)。
    提取RMS时延扩展、最大时延、簇参数等，与3GPP理论值对比。

    有效期：1个月
    合格标准：RMS时延扩展误差 < 10%
    """
    __tablename__ = "temporal_channel_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), index=True, comment="关联的校准会话ID")

    # 场景配置
    scenario_type = Column(
        String(50), nullable=False, index=True,
        comment="场景类型: UMa, UMi, RMa, InH"
    )
    scenario_condition = Column(
        String(50), nullable=False,
        comment="信道条件: LOS, NLOS, O2I"
    )
    fc_ghz = Column(Float, nullable=False, comment="载波频率 (GHz)")
    distance_2d_m = Column(Float, comment="2D距离 (m)")

    # 测量PDP数据 (JSONB)
    measured_pdp = Column(
        JSON, nullable=False,
        comment="测量PDP: {delay_bins_ns: [], power_db: []}"
    )

    # 提取的测量参数
    measured_rms_delay_spread_ns = Column(Float, comment="测量的RMS时延扩展 (ns)")
    measured_max_delay_ns = Column(Float, comment="测量的最大时延 (ns)")
    measured_num_clusters = Column(Integer, comment="检测到的簇数量")
    measured_cluster_delays_ns = Column(JSON, comment="簇时延数组 (ns)")
    measured_cluster_powers_db = Column(JSON, comment="簇功率数组 (dB)")

    # 3GPP参考参数
    reference_rms_delay_spread_ns = Column(Float, comment="3GPP参考RMS时延扩展 (ns)")
    reference_rms_delay_spread_range_ns = Column(
        JSON, comment="3GPP RMS时延扩展范围 [min, max]"
    )
    reference_num_clusters = Column(Integer, comment="3GPP参考簇数量")

    # 验证结果
    rms_error_percent = Column(Float, comment="RMS时延扩展误差 (%)")
    cluster_count_match = Column(Boolean, comment="簇数量是否匹配")
    validation_pass = Column(Boolean, index=True, comment="验证是否通过")
    threshold_percent = Column(Float, default=10.0, comment="误差阈值 (%)")

    # 仪器信息
    channel_emulator = Column(String(255), comment="信道仿真器型号和序列号")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100), comment="校准人员")

    # 有效性
    valid_until = Column(DateTime, comment="校准有效期至")
    status = Column(
        String(50), default=ChannelCalibrationStatus.VALID.value,
        index=True, comment="状态: valid, expired, invalidated"
    )

    # 原始数据
    raw_data_file_path = Column(Text, comment="原始测量数据文件路径")

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# Doppler Calibration (多普勒校准)
# ============================================================================

class DopplerCalibration(Base):
    """
    多普勒频谱校准记录

    验证信道仿真器能否正确生成多普勒频谱（经典多普勒谱）。
    测量方法：发射CW信号，FFT分析接收信号，提取多普勒频谱。

    有效期：1个月
    合格标准：频谱相关性 > 0.9
    """
    __tablename__ = "doppler_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), index=True, comment="关联的校准会话ID")

    # 配置
    velocity_kmh = Column(Float, nullable=False, comment="移动速度 (km/h)")
    fc_ghz = Column(Float, nullable=False, comment="载波频率 (GHz)")
    expected_doppler_hz = Column(Float, nullable=False, comment="预期最大多普勒频移 (Hz)")

    # 测量频谱
    measured_spectrum = Column(
        JSON, nullable=False,
        comment="测量频谱: {frequency_bins_hz: [], power_density_db: []}"
    )

    # 理论参考频谱
    reference_spectrum = Column(
        JSON, nullable=False,
        comment="参考频谱: {frequency_bins_hz: [], power_density_db: []}"
    )

    # 验证结果
    spectral_correlation = Column(Float, comment="频谱相关性 (0-1)")
    doppler_spread_error_percent = Column(Float, comment="多普勒扩展误差 (%)")
    validation_pass = Column(Boolean, index=True, comment="验证是否通过")
    threshold_correlation = Column(Float, default=0.9, comment="相关性阈值")

    # 仪器信息
    channel_emulator = Column(String(255), comment="信道仿真器型号")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime)
    status = Column(String(50), default=ChannelCalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# Spatial Correlation Calibration (空间相关性校准)
# ============================================================================

class SpatialCorrelationCalibration(Base):
    """
    空间相关性校准记录

    验证MPAC系统能否正确重现MIMO天线间的空间相关性。
    测量方法：使用双天线DUT，测量两天线信道系数的相关性。

    有效期：3个月
    合格标准：相关系数幅度误差 < 0.1
    """
    __tablename__ = "spatial_correlation_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), index=True, comment="关联的校准会话ID")

    # 场景配置
    scenario_type = Column(
        String(50), nullable=False, index=True,
        comment="场景类型: UMa, UMi, RMa, InH"
    )
    scenario_condition = Column(String(50), nullable=False, comment="信道条件: LOS, NLOS")
    fc_ghz = Column(Float, nullable=False, comment="载波频率 (GHz)")
    angular_spread_deg = Column(Float, comment="RMS角度扩展 (度)")

    # 测试DUT配置
    antenna_spacing_wavelengths = Column(Float, nullable=False, comment="天线间距 (波长)")
    antenna_spacing_m = Column(Float, comment="天线间距 (m)")
    antenna_type = Column(String(100), comment="天线类型")

    # 测量结果
    measured_correlation_magnitude = Column(Float, comment="测量相关系数幅度 (0-1)")
    measured_correlation_phase_deg = Column(Float, comment="测量相关系数相位 (度)")
    samples = Column(Integer, comment="统计样本数")
    confidence_interval = Column(JSON, comment="置信区间 [lower, upper]")

    # 理论参考值
    reference_correlation_magnitude = Column(Float, comment="理论相关系数幅度")
    reference_correlation_phase_deg = Column(Float, comment="理论相关系数相位 (度)")
    calculation_method = Column(
        String(100), default="3GPP_TR_38_901_Laplacian",
        comment="计算方法"
    )

    # 验证结果
    magnitude_error = Column(Float, comment="幅度误差")
    phase_error_deg = Column(Float, comment="相位误差 (度)")
    validation_pass = Column(Boolean, index=True, comment="验证是否通过")
    threshold_magnitude = Column(Float, default=0.1, comment="幅度误差阈值")
    threshold_phase_deg = Column(Float, default=10.0, comment="相位误差阈值 (度)")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime)
    status = Column(String(50), default=ChannelCalibrationStatus.VALID.value, index=True)

    # 原始数据
    raw_data_file_path = Column(Text)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# Angular Spread Calibration (角度扩展校准)
# ============================================================================

class AngularSpreadCalibration(Base):
    """
    角度扩展校准记录

    验证MPAC系统的角度功率谱(APS)与3GPP模型一致。
    测量方法：旋转DUT，扫描方位角，测量接收功率，拟合角度分布。

    有效期：3个月
    合格标准：RMS角度扩展误差 < 5°
    """
    __tablename__ = "angular_spread_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), index=True, comment="关联的校准会话ID")

    # 场景配置
    scenario_type = Column(String(50), nullable=False, index=True, comment="场景类型")
    scenario_condition = Column(String(50), nullable=False, comment="信道条件")
    fc_ghz = Column(Float, nullable=False, comment="载波频率 (GHz)")

    # 测量角度功率谱
    measured_aps = Column(
        JSON, nullable=False,
        comment="测量APS: {azimuth_deg: [], power_db: []}"
    )

    # 拟合参数
    fitted_mean_azimuth_deg = Column(Float, comment="拟合的平均方位角 (度)")
    fitted_rms_angular_spread_deg = Column(Float, comment="拟合的RMS角度扩展 (度)")
    fitted_distribution_type = Column(
        String(50), default=DistributionType.LAPLACIAN.value,
        comment="拟合分布类型: Laplacian, Gaussian"
    )
    fitted_r_squared = Column(Float, comment="拟合优度 R²")

    # 3GPP参考值
    reference_rms_angular_spread_deg = Column(Float, comment="3GPP参考RMS角度扩展 (度)")
    reference_rms_angular_spread_range_deg = Column(
        JSON, comment="3GPP RMS角度扩展范围 [min, max]"
    )

    # 验证结果
    rms_error_deg = Column(Float, comment="RMS角度扩展误差 (度)")
    validation_pass = Column(Boolean, index=True, comment="验证是否通过")
    threshold_deg = Column(Float, default=5.0, comment="误差阈值 (度)")

    # 测量设备
    positioner = Column(String(255), comment="转台型号")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime)
    status = Column(String(50), default=ChannelCalibrationStatus.VALID.value, index=True)

    # 原始数据
    raw_data_file_path = Column(Text)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# Quiet Zone Calibration (静区均匀性校准)
# ============================================================================

class ChannelQuietZoneCalibration(Base):
    """
    信道校准-静区均匀性校准记录

    验证静区(Quiet Zone)内的电磁场幅度和相位均匀性。
    测量方法：使用场探头在静区内多点扫描，计算均匀性。

    有效期：6个月
    合格标准：幅度均匀性 ±1 dB，相位均匀性 ±30°

    注意：与 models/calibration.py 中的 QuietZoneCalibration (系统级) 不同，
    此表专用于信道校准流程中的场均匀性验证。
    """
    __tablename__ = "channel_quiet_zone_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), index=True, comment="关联的校准会话ID")

    # 静区配置
    quiet_zone_shape = Column(
        String(50), nullable=False,
        comment="静区形状: sphere, cylinder"
    )
    quiet_zone_diameter_m = Column(Float, nullable=False, comment="静区直径 (m)")
    quiet_zone_height_m = Column(Float, comment="静区高度 (m)，仅圆柱形")

    # 场探头配置
    field_probe_type = Column(String(50), comment="场探头类型: dipole, loop")
    field_probe_size_mm = Column(Float, comment="场探头尺寸 (mm)")

    # 测量网格数据
    measurement_grid = Column(
        JSON, nullable=False,
        comment="测量网格: {points: [{x_m, y_m, z_m, amplitude_v_per_m, phase_deg}, ...]}"
    )
    num_points = Column(Integer, nullable=False, comment="测量点数")

    # 幅度均匀性统计
    amplitude_mean_db = Column(Float, comment="幅度均值 (dB)")
    amplitude_std_db = Column(Float, comment="幅度标准差 (dB)")
    amplitude_range_db = Column(JSON, comment="幅度范围 [min, max]")

    # 相位均匀性统计
    phase_mean_deg = Column(Float, comment="相位均值 (度)")
    phase_std_deg = Column(Float, comment="相位标准差 (度)")
    phase_range_deg = Column(JSON, comment="相位范围 [min, max]")

    # 验证结果
    amplitude_uniformity_pass = Column(Boolean, comment="幅度均匀性是否通过")
    phase_uniformity_pass = Column(Boolean, comment="相位均匀性是否通过")
    validation_pass = Column(Boolean, index=True, comment="总体验证是否通过")
    amplitude_threshold_db = Column(Float, default=1.0, comment="幅度均匀性阈值 (dB)")
    phase_threshold_deg = Column(Float, default=30.0, comment="相位均匀性阈值 (度)")

    # 测试频率
    fc_ghz = Column(Float, comment="测试频率 (GHz)")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime)
    status = Column(String(50), default=ChannelCalibrationStatus.VALID.value, index=True)

    # 原始数据
    raw_data_file_path = Column(Text)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# EIS Validation (EIS验证)
# ============================================================================

class EISValidation(Base):
    """
    EIS(等效全向灵敏度)验证记录

    端到端性能验证，确保系统能正确测量DUT的EIS。
    测量方法：使用参考DUT，在3D空间扫描测量灵敏度。

    有效期：系统重大变更后需重新验证
    """
    __tablename__ = "eis_validations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), index=True, comment="关联的校准会话ID")

    # 测试配置
    scenario = Column(String(100), comment="测试场景")
    fc_ghz = Column(Float, nullable=False, comment="载波频率 (GHz)")
    bandwidth_mhz = Column(Float, comment="信号带宽 (MHz)")
    modulation = Column(String(50), comment="调制方式，如 64QAM")
    target_throughput_percent = Column(Float, default=95.0, comment="目标吞吐量百分比")

    # DUT信息
    dut_type = Column(String(50), comment="DUT类型: smartphone, vehicle, module")
    dut_model = Column(String(255), nullable=False, index=True, comment="DUT型号")
    num_rx_antennas = Column(Integer, comment="接收天线数")

    # EIS测量数据（3D分布）
    eis_map = Column(
        JSON, nullable=False,
        comment="EIS分布: {azimuth_deg: [], elevation_deg: [], eis_dbm: [[]]}"
    )

    # 结果
    peak_eis_dbm = Column(Float, comment="峰值EIS (dBm)")
    peak_azimuth_deg = Column(Float, comment="峰值方向-方位角 (度)")
    peak_elevation_deg = Column(Float, comment="峰值方向-俯仰角 (度)")
    median_eis_dbm = Column(Float, comment="中位EIS (dBm)")
    eis_spread_db = Column(Float, comment="EIS扩展 (峰值-第5百分位)")

    # 3GPP要求
    min_eis_dbm = Column(Float, comment="最小EIS要求 (dBm)")
    validation_pass = Column(Boolean, index=True, comment="验证是否通过")

    # 元数据
    measured_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    measured_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime)
    status = Column(String(50), default=ChannelCalibrationStatus.VALID.value, index=True)

    # 原始数据
    raw_data_file_path = Column(Text)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ============================================================================
# Channel Calibration Validity Summary (信道校准有效性汇总)
# ============================================================================

class ChannelCalibrationValidity(Base):
    """
    信道校准有效性状态汇总

    跟踪整个系统的信道校准有效性状态。
    用于快速查询系统是否需要重新校准。
    """
    __tablename__ = "channel_calibration_validity"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 时域校准状态
    temporal_valid = Column(Boolean, default=False)
    temporal_valid_until = Column(DateTime)
    temporal_calibration_id = Column(UUID(as_uuid=True), comment="最新时域校准记录ID")

    # 多普勒校准状态
    doppler_valid = Column(Boolean, default=False)
    doppler_valid_until = Column(DateTime)
    doppler_calibration_id = Column(UUID(as_uuid=True))

    # 空间相关性校准状态
    spatial_correlation_valid = Column(Boolean, default=False)
    spatial_correlation_valid_until = Column(DateTime)
    spatial_correlation_calibration_id = Column(UUID(as_uuid=True))

    # 角度扩展校准状态
    angular_spread_valid = Column(Boolean, default=False)
    angular_spread_valid_until = Column(DateTime)
    angular_spread_calibration_id = Column(UUID(as_uuid=True))

    # 静区校准状态
    quiet_zone_valid = Column(Boolean, default=False)
    quiet_zone_valid_until = Column(DateTime)
    quiet_zone_calibration_id = Column(UUID(as_uuid=True))

    # EIS验证状态
    eis_valid = Column(Boolean, default=False)
    eis_valid_until = Column(DateTime)
    eis_validation_id = Column(UUID(as_uuid=True))

    # 总体状态
    overall_status = Column(
        String(50), default="unknown",
        comment="总体状态: valid, expiring_soon, expired, unknown"
    )

    # 最后更新
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
