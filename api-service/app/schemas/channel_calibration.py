"""
Channel Calibration Pydantic Schemas

信道校准 API 的请求和响应模型。

参考设计: docs/features/calibration/channel-calibration.md
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from uuid import UUID
from enum import Enum


# ==================== Enums ====================

class ScenarioTypeEnum(str, Enum):
    """3GPP信道场景类型"""
    UMA = "UMa"       # Urban Macro
    UMI = "UMi"       # Urban Micro
    RMA = "RMa"       # Rural Macro
    INH = "InH"       # Indoor Hotspot


class ScenarioConditionEnum(str, Enum):
    """3GPP信道条件"""
    LOS = "LOS"       # Line of Sight
    NLOS = "NLOS"     # Non-Line of Sight
    O2I = "O2I"       # Outdoor to Indoor


class DistributionTypeEnum(str, Enum):
    """角度分布类型"""
    LAPLACIAN = "Laplacian"
    GAUSSIAN = "Gaussian"


class QuietZoneShapeEnum(str, Enum):
    """静区形状"""
    SPHERE = "sphere"
    CYLINDER = "cylinder"


class FieldProbeTypeEnum(str, Enum):
    """场探头类型"""
    DIPOLE = "dipole"
    LOOP = "loop"


class DUTTypeEnum(str, Enum):
    """被测设备类型"""
    SMARTPHONE = "smartphone"
    VEHICLE = "vehicle"
    MODULE = "module"


class ChannelCalibrationStatusEnum(str, Enum):
    """信道校准状态"""
    VALID = "valid"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    PENDING = "pending"


class ChannelCalibrationJobStatus(str, Enum):
    """校准任务状态"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionStatusEnum(str, Enum):
    """校准会话状态"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==================== Common Schemas ====================

class CalibrationJobResponse(BaseModel):
    """校准任务响应"""
    calibration_job_id: UUID
    status: ChannelCalibrationJobStatus
    estimated_duration_minutes: Optional[float] = None
    message: Optional[str] = None


class CalibrationProgress(BaseModel):
    """校准进度"""
    job_id: UUID
    status: ChannelCalibrationJobStatus
    progress_percent: float = Field(ge=0, le=100)
    current_step: Optional[str] = None
    error_message: Optional[str] = None


class MeasuredPDP(BaseModel):
    """测量的功率时延谱"""
    delay_bins_ns: List[float] = Field(..., description="时延点 (ns)")
    power_db: List[float] = Field(..., description="功率 (dB)")


class MeasuredSpectrum(BaseModel):
    """测量的频谱"""
    frequency_bins_hz: List[float] = Field(..., description="频率点 (Hz)")
    power_density_db: List[float] = Field(..., description="功率谱密度 (dB)")


class MeasuredAPS(BaseModel):
    """测量的角度功率谱"""
    azimuth_deg: List[float] = Field(..., description="方位角 (度)")
    power_db: List[float] = Field(..., description="功率 (dB)")


class MeasurementPoint(BaseModel):
    """测量点"""
    x_m: float = Field(..., description="X 坐标 (m)")
    y_m: float = Field(..., description="Y 坐标 (m)")
    z_m: float = Field(..., description="Z 坐标 (m)")
    amplitude_v_per_m: float = Field(..., description="场幅度 (V/m)")
    phase_deg: float = Field(..., description="相位 (度)")


class MeasurementGrid(BaseModel):
    """测量网格"""
    points: List[MeasurementPoint] = Field(..., description="测量点列表")


class EISMap(BaseModel):
    """EIS 分布图"""
    azimuth_deg: List[float] = Field(..., description="方位角数组")
    elevation_deg: List[float] = Field(..., description="俯仰角数组")
    eis_dbm: List[List[float]] = Field(..., description="EIS 值二维数组")


# ==================== Scenario Configuration ====================

class ScenarioConfig(BaseModel):
    """3GPP场景配置"""
    type: ScenarioTypeEnum = Field(..., description="场景类型")
    condition: ScenarioConditionEnum = Field(..., description="信道条件")
    fc_ghz: float = Field(..., ge=0.5, le=100, description="载波频率 (GHz)")
    distance_2d_m: Optional[float] = Field(None, ge=0, description="2D距离 (m)")


# ==================== Temporal Channel Calibration Schemas ====================

class StartTemporalCalibrationRequest(BaseModel):
    """启动时域校准请求"""
    scenario: ScenarioConfig = Field(..., description="场景配置")
    session_id: Optional[UUID] = Field(None, description="关联的校准会话ID")
    channel_emulator_id: Optional[str] = Field(None, description="信道仿真器设备ID")
    calibrated_by: str = Field(..., description="校准人员")


class TemporalCalibrationMeasuredParams(BaseModel):
    """时域校准测量参数"""
    rms_delay_spread_ns: float = Field(..., description="RMS时延扩展 (ns)")
    max_delay_ns: float = Field(..., description="最大时延 (ns)")
    num_clusters: int = Field(..., ge=0, description="簇数量")
    cluster_delays_ns: List[float] = Field(..., description="簇时延数组 (ns)")
    cluster_powers_db: List[float] = Field(..., description="簇功率数组 (dB)")


class TemporalCalibrationReferenceParams(BaseModel):
    """3GPP参考参数"""
    rms_delay_spread_ns: float = Field(..., description="参考RMS时延扩展 (ns)")
    rms_delay_spread_range_ns: List[float] = Field(
        ..., min_length=2, max_length=2,
        description="RMS时延扩展范围 [min, max]"
    )
    num_clusters: int = Field(..., description="参考簇数量")


class TemporalCalibrationValidation(BaseModel):
    """时域校准验证结果"""
    rms_error_percent: float = Field(..., description="RMS误差百分比")
    cluster_count_match: bool = Field(..., description="簇数量是否匹配")
    pass_: bool = Field(..., alias="pass", description="是否通过")
    threshold_percent: float = Field(default=10.0, description="阈值百分比")


class TemporalCalibrationResponse(BaseModel):
    """时域校准响应"""
    id: UUID
    session_id: Optional[UUID] = None
    scenario_type: str
    scenario_condition: str
    fc_ghz: float
    distance_2d_m: Optional[float] = None
    # 测量PDP
    measured_pdp: Dict[str, List[float]]
    # 测量参数
    measured_rms_delay_spread_ns: Optional[float] = None
    measured_max_delay_ns: Optional[float] = None
    measured_num_clusters: Optional[int] = None
    measured_cluster_delays_ns: Optional[List[float]] = None
    measured_cluster_powers_db: Optional[List[float]] = None
    # 参考参数
    reference_rms_delay_spread_ns: Optional[float] = None
    reference_rms_delay_spread_range_ns: Optional[List[float]] = None
    reference_num_clusters: Optional[int] = None
    # 验证结果
    rms_error_percent: Optional[float] = None
    cluster_count_match: Optional[bool] = None
    validation_pass: Optional[bool] = None
    threshold_percent: float = 10.0
    # 仪器
    channel_emulator: Optional[str] = None
    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True
        populate_by_name = True


# ==================== Doppler Calibration Schemas ====================

class StartDopplerCalibrationRequest(BaseModel):
    """启动多普勒校准请求"""
    velocity_kmh: float = Field(..., ge=0, le=500, description="移动速度 (km/h)")
    fc_ghz: float = Field(..., ge=0.5, le=100, description="载波频率 (GHz)")
    session_id: Optional[UUID] = Field(None, description="关联的校准会话ID")
    channel_emulator_id: Optional[str] = Field(None, description="信道仿真器设备ID")
    calibrated_by: str = Field(..., description="校准人员")


class DopplerCalibrationResponse(BaseModel):
    """多普勒校准响应"""
    id: UUID
    session_id: Optional[UUID] = None
    velocity_kmh: float
    fc_ghz: float
    expected_doppler_hz: float
    # 频谱
    measured_spectrum: Dict[str, List[float]]
    reference_spectrum: Dict[str, List[float]]
    # 验证结果
    spectral_correlation: Optional[float] = None
    doppler_spread_error_percent: Optional[float] = None
    validation_pass: Optional[bool] = None
    threshold_correlation: float = 0.9
    # 仪器
    channel_emulator: Optional[str] = None
    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


# ==================== Spatial Correlation Calibration Schemas ====================

class TestDUTConfig(BaseModel):
    """测试DUT配置"""
    antenna_spacing_wavelengths: float = Field(
        ..., ge=0.1, le=10,
        description="天线间距 (波长)"
    )
    antenna_spacing_m: Optional[float] = Field(None, description="天线间距 (m)")
    antenna_type: str = Field(default="dipole", description="天线类型")


class StartSpatialCorrelationCalibrationRequest(BaseModel):
    """启动空间相关性校准请求"""
    scenario: ScenarioConfig = Field(..., description="场景配置")
    test_dut: TestDUTConfig = Field(..., description="测试DUT配置")
    session_id: Optional[UUID] = Field(None, description="关联的校准会话ID")
    calibrated_by: str = Field(..., description="校准人员")


class MeasuredCorrelation(BaseModel):
    """测量相关性"""
    magnitude: float = Field(..., ge=0, le=1, description="幅度 (0-1)")
    phase_deg: float = Field(..., description="相位 (度)")
    samples: int = Field(..., ge=1, description="统计样本数")
    confidence_interval: List[float] = Field(
        ..., min_length=2, max_length=2,
        description="置信区间 [lower, upper]"
    )


class SpatialCorrelationCalibrationResponse(BaseModel):
    """空间相关性校准响应"""
    id: UUID
    session_id: Optional[UUID] = None
    # 场景
    scenario_type: str
    scenario_condition: str
    fc_ghz: float
    angular_spread_deg: Optional[float] = None
    # 测试DUT
    antenna_spacing_wavelengths: float
    antenna_spacing_m: Optional[float] = None
    antenna_type: Optional[str] = None
    # 测量结果
    measured_correlation_magnitude: Optional[float] = None
    measured_correlation_phase_deg: Optional[float] = None
    samples: Optional[int] = None
    confidence_interval: Optional[List[float]] = None
    # 参考值
    reference_correlation_magnitude: Optional[float] = None
    reference_correlation_phase_deg: Optional[float] = None
    calculation_method: str = "3GPP_TR_38_901_Laplacian"
    # 验证结果
    magnitude_error: Optional[float] = None
    phase_error_deg: Optional[float] = None
    validation_pass: Optional[bool] = None
    threshold_magnitude: float = 0.1
    threshold_phase_deg: float = 10.0
    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


# ==================== Angular Spread Calibration Schemas ====================

class StartAngularSpreadCalibrationRequest(BaseModel):
    """启动角度扩展校准请求"""
    scenario: ScenarioConfig = Field(..., description="场景配置")
    azimuth_step_deg: float = Field(default=5.0, ge=1, le=30, description="方位角步进 (度)")
    session_id: Optional[UUID] = Field(None, description="关联的校准会话ID")
    positioner_id: Optional[str] = Field(None, description="转台设备ID")
    calibrated_by: str = Field(..., description="校准人员")


class FittedParams(BaseModel):
    """拟合参数"""
    mean_azimuth_deg: float = Field(..., description="平均方位角 (度)")
    rms_angular_spread_deg: float = Field(..., description="RMS角度扩展 (度)")
    distribution_type: DistributionTypeEnum = Field(
        default=DistributionTypeEnum.LAPLACIAN,
        description="分布类型"
    )
    r_squared: float = Field(..., ge=0, le=1, description="拟合优度 R²")


class AngularSpreadCalibrationResponse(BaseModel):
    """角度扩展校准响应"""
    id: UUID
    session_id: Optional[UUID] = None
    # 场景
    scenario_type: str
    scenario_condition: str
    fc_ghz: float
    # 测量APS
    measured_aps: Dict[str, List[float]]
    # 拟合参数
    fitted_mean_azimuth_deg: Optional[float] = None
    fitted_rms_angular_spread_deg: Optional[float] = None
    fitted_distribution_type: str = "Laplacian"
    fitted_r_squared: Optional[float] = None
    # 参考值
    reference_rms_angular_spread_deg: Optional[float] = None
    reference_rms_angular_spread_range_deg: Optional[List[float]] = None
    # 验证结果
    rms_error_deg: Optional[float] = None
    validation_pass: Optional[bool] = None
    threshold_deg: float = 5.0
    # 设备
    positioner: Optional[str] = None
    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


# ==================== Quiet Zone Calibration Schemas ====================

class QuietZoneConfig(BaseModel):
    """静区配置"""
    shape: QuietZoneShapeEnum = Field(..., description="静区形状")
    diameter_m: float = Field(..., ge=0.1, le=5, description="直径 (m)")
    height_m: Optional[float] = Field(None, ge=0.1, le=5, description="高度 (m)，仅圆柱形")


class FieldProbeConfig(BaseModel):
    """场探头配置"""
    type: FieldProbeTypeEnum = Field(default=FieldProbeTypeEnum.DIPOLE, description="探头类型")
    size_mm: float = Field(default=10, ge=1, le=100, description="尺寸 (mm)")


class StartQuietZoneCalibrationRequest(BaseModel):
    """启动静区校准请求"""
    quiet_zone: QuietZoneConfig = Field(..., description="静区配置")
    field_probe: FieldProbeConfig = Field(
        default_factory=FieldProbeConfig,
        description="场探头配置"
    )
    fc_ghz: float = Field(..., ge=0.5, le=100, description="测试频率 (GHz)")
    num_points: int = Field(default=100, ge=10, le=1000, description="测量点数")
    session_id: Optional[UUID] = Field(None, description="关联的校准会话ID")
    calibrated_by: str = Field(..., description="校准人员")


class UniformityStats(BaseModel):
    """均匀性统计"""
    mean_db: float = Field(..., description="均值 (dB)")
    std_db: float = Field(..., description="标准差 (dB)")
    range_db: List[float] = Field(
        ..., min_length=2, max_length=2,
        description="范围 [min, max]"
    )


class QuietZoneCalibrationResponse(BaseModel):
    """静区校准响应"""
    id: UUID
    session_id: Optional[UUID] = None
    # 静区配置
    quiet_zone_shape: str
    quiet_zone_diameter_m: float
    quiet_zone_height_m: Optional[float] = None
    # 场探头
    field_probe_type: Optional[str] = None
    field_probe_size_mm: Optional[float] = None
    # 测量网格
    measurement_grid: Dict[str, Any]
    num_points: int
    # 幅度均匀性
    amplitude_mean_db: Optional[float] = None
    amplitude_std_db: Optional[float] = None
    amplitude_range_db: Optional[List[float]] = None
    # 相位均匀性
    phase_mean_deg: Optional[float] = None
    phase_std_deg: Optional[float] = None
    phase_range_deg: Optional[List[float]] = None
    # 验证结果
    amplitude_uniformity_pass: Optional[bool] = None
    phase_uniformity_pass: Optional[bool] = None
    validation_pass: Optional[bool] = None
    amplitude_threshold_db: float = 1.0
    phase_threshold_deg: float = 30.0
    # 测试频率
    fc_ghz: Optional[float] = None
    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


# ==================== EIS Validation Schemas ====================

class EISTestConfig(BaseModel):
    """EIS测试配置"""
    scenario: Optional[str] = Field(None, description="测试场景")
    fc_ghz: float = Field(..., ge=0.5, le=100, description="载波频率 (GHz)")
    bandwidth_mhz: Optional[float] = Field(None, ge=1, le=400, description="信号带宽 (MHz)")
    modulation: Optional[str] = Field(None, description="调制方式")
    target_throughput_percent: float = Field(default=95.0, ge=50, le=100, description="目标吞吐量百分比")


class EISDUTConfig(BaseModel):
    """EIS DUT配置"""
    type: DUTTypeEnum = Field(..., description="DUT类型")
    model: str = Field(..., description="型号")
    num_rx_antennas: Optional[int] = Field(None, ge=1, description="接收天线数")


class StartEISValidationRequest(BaseModel):
    """启动EIS验证请求"""
    test_config: EISTestConfig = Field(..., description="测试配置")
    dut: EISDUTConfig = Field(..., description="DUT配置")
    min_eis_dbm: Optional[float] = Field(None, description="最小EIS要求 (dBm)")
    session_id: Optional[UUID] = Field(None, description="关联的校准会话ID")
    measured_by: str = Field(..., description="测量人员")


class EISResults(BaseModel):
    """EIS测量结果"""
    peak_eis_dbm: float = Field(..., description="峰值EIS (dBm)")
    peak_direction: Dict[str, float] = Field(..., description="峰值方向 {azimuth_deg, elevation_deg}")
    median_eis_dbm: float = Field(..., description="中位EIS (dBm)")
    eis_spread_db: float = Field(..., description="EIS扩展 (dB)")


class EISValidationResponse(BaseModel):
    """EIS验证响应"""
    id: UUID
    session_id: Optional[UUID] = None
    # 测试配置
    scenario: Optional[str] = None
    fc_ghz: float
    bandwidth_mhz: Optional[float] = None
    modulation: Optional[str] = None
    target_throughput_percent: float = 95.0
    # DUT
    dut_type: Optional[str] = None
    dut_model: str
    num_rx_antennas: Optional[int] = None
    # EIS分布
    eis_map: Dict[str, Any]
    # 结果
    peak_eis_dbm: Optional[float] = None
    peak_azimuth_deg: Optional[float] = None
    peak_elevation_deg: Optional[float] = None
    median_eis_dbm: Optional[float] = None
    eis_spread_db: Optional[float] = None
    # 要求
    min_eis_dbm: Optional[float] = None
    validation_pass: Optional[bool] = None
    # 元数据
    measured_at: datetime
    measured_by: Optional[str] = None
    valid_until: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


# ==================== Calibration Session Schemas ====================

class StartCalibrationSessionRequest(BaseModel):
    """启动校准会话请求"""
    name: str = Field(..., min_length=1, max_length=255, description="会话名称")
    description: Optional[str] = Field(None, description="会话描述")
    workflow_id: Optional[str] = Field(None, description="工作流ID")
    configuration: Optional[Dict[str, Any]] = Field(None, description="会话配置")
    created_by: str = Field(..., description="创建人员")


class CalibrationSessionResponse(BaseModel):
    """校准会话响应"""
    id: UUID
    name: str
    description: Optional[str] = None
    workflow_id: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None
    # 时间
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_minutes: Optional[float] = None
    # 状态
    status: str
    progress_percent: int = 0
    current_stage: Optional[str] = None
    # 结果
    total_calibrations: int = 0
    passed_calibrations: int = 0
    failed_calibrations: int = 0
    overall_pass: Optional[bool] = None
    # 操作人员
    created_by: Optional[str] = None
    # 系统字段
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpdateSessionProgressRequest(BaseModel):
    """更新会话进度请求"""
    progress_percent: int = Field(..., ge=0, le=100, description="进度百分比")
    current_stage: Optional[str] = Field(None, description="当前阶段")
    status: Optional[SessionStatusEnum] = Field(None, description="状态")


class CompleteSessionRequest(BaseModel):
    """完成会话请求"""
    overall_pass: bool = Field(..., description="总体是否通过")
    total_calibrations: int = Field(..., ge=0, description="总校准数")
    passed_calibrations: int = Field(..., ge=0, description="通过数")
    failed_calibrations: int = Field(..., ge=0, description="失败数")


# ==================== Validity Management Schemas ====================

class ChannelCalibrationTypeStatus(BaseModel):
    """单种校准类型状态"""
    valid: bool = Field(..., description="是否有效")
    valid_until: Optional[datetime] = Field(None, description="有效期至")
    calibration_id: Optional[UUID] = Field(None, description="最新校准记录ID")
    days_remaining: Optional[int] = Field(None, description="剩余天数")


class ChannelCalibrationValidityResponse(BaseModel):
    """信道校准有效性响应"""
    id: int
    # 各类校准状态
    temporal: ChannelCalibrationTypeStatus
    doppler: ChannelCalibrationTypeStatus
    spatial_correlation: ChannelCalibrationTypeStatus
    angular_spread: ChannelCalibrationTypeStatus
    quiet_zone: ChannelCalibrationTypeStatus
    eis: ChannelCalibrationTypeStatus
    # 总体状态
    overall_status: str = Field(..., description="总体状态: valid, expiring_soon, expired, unknown")
    updated_at: datetime

    class Config:
        from_attributes = True


class ChannelCalibrationValidityReport(BaseModel):
    """信道校准有效性报告"""
    # 状态统计
    total_calibration_types: int = 6
    valid_count: int
    expired_count: int
    expiring_soon_count: int  # 7天内过期

    # 详细列表
    expired_calibrations: List[Dict[str, Any]] = Field(
        default=[],
        description="已过期的校准 [{calibration_type, expired_at, days_overdue}]"
    )
    expiring_soon_calibrations: List[Dict[str, Any]] = Field(
        default=[],
        description="即将过期的校准 [{calibration_type, valid_until, days_remaining}]"
    )

    # 建议
    recommendations: List[Dict[str, Any]] = Field(
        default=[],
        description="建议操作 [{calibration_type, action, priority, reason}]"
    )


class InvalidateCalibrationRequest(BaseModel):
    """作废校准请求"""
    reason: str = Field(..., min_length=5, max_length=500, description="作废原因")


class InvalidateCalibrationResponse(BaseModel):
    """作废校准响应"""
    calibration_id: UUID
    calibration_type: str
    invalidated_at: datetime
    reason: str
    previous_status: str


# ==================== Calibration History Schemas ====================

class ChannelCalibrationHistoryQuery(BaseModel):
    """信道校准历史查询参数"""
    calibration_type: Optional[str] = Field(
        None,
        description="temporal | doppler | spatial_correlation | angular_spread | quiet_zone | eis"
    )
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    validation_pass: Optional[bool] = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ChannelCalibrationHistoryItem(BaseModel):
    """信道校准历史记录"""
    calibration_id: UUID
    calibration_type: str
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    status: str
    validation_pass: Optional[bool] = None
    summary: Dict[str, Any] = Field(
        default={},
        description="关键参数摘要"
    )


class ChannelCalibrationHistoryResponse(BaseModel):
    """信道校准历史响应"""
    total: int
    items: List[ChannelCalibrationHistoryItem]


# ==================== Dashboard/Status Schemas ====================

class ChannelCalibrationStatusSummary(BaseModel):
    """信道校准状态摘要"""
    temporal_status: str
    temporal_last_calibrated: Optional[datetime] = None
    temporal_next_due: Optional[datetime] = None

    doppler_status: str
    doppler_last_calibrated: Optional[datetime] = None
    doppler_next_due: Optional[datetime] = None

    spatial_correlation_status: str
    spatial_correlation_last_calibrated: Optional[datetime] = None
    spatial_correlation_next_due: Optional[datetime] = None

    angular_spread_status: str
    angular_spread_last_calibrated: Optional[datetime] = None
    angular_spread_next_due: Optional[datetime] = None

    quiet_zone_status: str
    quiet_zone_last_calibrated: Optional[datetime] = None
    quiet_zone_next_due: Optional[datetime] = None

    eis_status: str
    eis_last_calibrated: Optional[datetime] = None
    eis_next_due: Optional[datetime] = None

    overall_status: str
    recent_calibrations: List[ChannelCalibrationHistoryItem] = []
