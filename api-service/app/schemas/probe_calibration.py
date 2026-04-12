"""
Probe Calibration Pydantic Schemas

探头校准 API 的请求和响应模型。

参考设计: docs/features/calibration/probe-calibration.md
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from uuid import UUID
from enum import Enum


# ==================== Enums ====================

class PolarizationType(str, Enum):
    """极化类型"""
    V = "V"
    H = "H"
    LHCP = "LHCP"
    RHCP = "RHCP"


class ProbeTypeEnum(str, Enum):
    """探头类型"""
    DUAL_LINEAR = "dual_linear"
    DUAL_SLANT = "dual_slant"
    CIRCULAR = "circular"


class CalibrationStatusEnum(str, Enum):
    """校准状态"""
    VALID = "valid"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    PENDING = "pending"


class LinkCalibrationTypeEnum(str, Enum):
    """链路校准类型"""
    WEEKLY_CHECK = "weekly_check"
    PRE_TEST = "pre_test"
    POST_MAINTENANCE = "post_maintenance"


class CalibrationJobStatus(str, Enum):
    """校准任务状态"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ==================== Common Schemas ====================

class FrequencyRange(BaseModel):
    """频率范围配置"""
    start_mhz: float = Field(..., ge=100, le=100000, description="起始频率 (MHz)")
    stop_mhz: float = Field(..., ge=100, le=100000, description="终止频率 (MHz)")
    step_mhz: float = Field(..., ge=1, le=1000, description="频率步进 (MHz)")

    @field_validator('stop_mhz')
    @classmethod
    def stop_must_be_greater_than_start(cls, v, info):
        if 'start_mhz' in info.data and v <= info.data['start_mhz']:
            raise ValueError('stop_mhz must be greater than start_mhz')
        return v


class CalibrationJobResponse(BaseModel):
    """校准任务响应"""
    calibration_job_id: UUID
    status: CalibrationJobStatus
    estimated_duration_minutes: Optional[float] = None
    message: Optional[str] = None


class CalibrationProgress(BaseModel):
    """校准进度"""
    job_id: UUID
    status: CalibrationJobStatus
    progress_percent: float = Field(ge=0, le=100)
    current_step: Optional[str] = None
    current_probe: Optional[int] = None
    total_probes: Optional[int] = None
    current_frequency_mhz: Optional[float] = None
    total_frequencies: Optional[int] = None
    error_message: Optional[str] = None


# ==================== Amplitude Calibration Schemas ====================

class StartAmplitudeCalibrationRequest(BaseModel):
    """启动幅度校准请求"""
    probe_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=64,
        description="要校准的探头 ID 列表 (0-63)"
    )
    polarizations: List[PolarizationType] = Field(
        default=[PolarizationType.V, PolarizationType.H],
        description="要校准的极化类型"
    )
    frequency_range: FrequencyRange = Field(
        ...,
        description="频率范围配置"
    )
    reference_antenna_id: Optional[str] = Field(
        None,
        description="参考天线设备 ID"
    )
    power_meter_id: Optional[str] = Field(
        None,
        description="功率计设备 ID"
    )
    calibrated_by: str = Field(..., description="校准人员")

    @field_validator('probe_ids')
    @classmethod
    def validate_probe_ids(cls, v):
        for probe_id in v:
            if probe_id < 0 or probe_id > 63:
                raise ValueError(f'probe_id must be between 0 and 63, got {probe_id}')
        return v


class AmplitudeCalibrationData(BaseModel):
    """幅度校准数据"""
    probe_id: int
    polarization: str
    frequency_points_mhz: List[float]
    tx_gain_dbi: List[float]
    rx_gain_dbi: List[float]
    tx_gain_uncertainty_db: List[float]
    rx_gain_uncertainty_db: List[float]


class AmplitudeCalibrationResponse(BaseModel):
    """幅度校准响应"""
    id: UUID
    probe_id: int
    polarization: str
    frequency_points_mhz: List[float]
    tx_gain_dbi: List[float]
    rx_gain_dbi: List[float]
    tx_gain_uncertainty_db: List[float]
    rx_gain_uncertainty_db: List[float]
    reference_antenna: Optional[str] = None
    reference_power_meter: Optional[str] = None
    temperature_celsius: Optional[float] = None
    humidity_percent: Optional[float] = None
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: datetime
    status: str

    class Config:
        from_attributes = True


# ==================== Phase Calibration Schemas ====================

class StartPhaseCalibrationRequest(BaseModel):
    """启动相位校准请求"""
    probe_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=64,
        description="要校准的探头 ID 列表"
    )
    polarizations: List[PolarizationType] = Field(
        default=[PolarizationType.V, PolarizationType.H],
        description="要校准的极化类型"
    )
    reference_probe_id: int = Field(
        default=0,
        ge=0,
        le=63,
        description="参考探头 ID"
    )
    frequency_range: FrequencyRange = Field(..., description="频率范围配置")
    vna_id: Optional[str] = Field(None, description="VNA 设备 ID")
    calibrated_by: str = Field(..., description="校准人员")

    @field_validator('probe_ids')
    @classmethod
    def validate_probe_ids(cls, v):
        for probe_id in v:
            if probe_id < 0 or probe_id > 63:
                raise ValueError(f'probe_id must be between 0 and 63, got {probe_id}')
        return v


class PhaseCalibrationResponse(BaseModel):
    """相位校准响应"""
    id: UUID
    probe_id: int
    polarization: str
    reference_probe_id: int
    frequency_points_mhz: List[float]
    phase_offset_deg: List[float]
    group_delay_ns: List[float]
    phase_uncertainty_deg: List[float]
    vna_model: Optional[str] = None
    vna_serial: Optional[str] = None
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: datetime
    status: str

    class Config:
        from_attributes = True


# ==================== Polarization Calibration Schemas ====================

class StartPolarizationCalibrationRequest(BaseModel):
    """启动极化校准请求"""
    probe_ids: List[int] = Field(..., min_length=1, max_length=64)
    probe_type: ProbeTypeEnum = Field(..., description="探头类型")
    frequency_range: FrequencyRange = Field(..., description="频率范围配置")
    reference_antenna_id: Optional[str] = Field(None, description="参考天线设备 ID")
    positioner_id: Optional[str] = Field(None, description="转台设备 ID")
    calibrated_by: str = Field(..., description="校准人员")


class LinearPolarizationData(BaseModel):
    """线极化数据"""
    v_to_h_isolation_db: float = Field(..., description="V 极化端口对 H 极化的隔离度 (dB)")
    h_to_v_isolation_db: float = Field(..., description="H 极化端口对 V 极化的隔离度 (dB)")
    frequency_points_mhz: List[float]
    isolation_vs_frequency_db: List[float]


class CircularPolarizationData(BaseModel):
    """圆极化数据"""
    polarization_hand: Literal["LHCP", "RHCP"]
    axial_ratio_db: float = Field(..., description="轴比 (dB)")
    frequency_points_mhz: List[float]
    axial_ratio_vs_frequency_db: List[float]


class PolarizationCalibrationResponse(BaseModel):
    """极化校准响应"""
    id: UUID
    probe_id: int
    probe_type: str
    # 线极化数据
    v_to_h_isolation_db: Optional[float] = None
    h_to_v_isolation_db: Optional[float] = None
    # 圆极化数据
    polarization_hand: Optional[str] = None
    axial_ratio_db: Optional[float] = None
    # 频率相关数据
    frequency_points_mhz: Optional[List[float]] = None
    isolation_vs_frequency_db: Optional[List[float]] = None
    axial_ratio_vs_frequency_db: Optional[List[float]] = None
    # 参考设备
    reference_antenna: Optional[str] = None
    positioner: Optional[str] = None
    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: datetime
    status: str

    class Config:
        from_attributes = True


# ==================== Pattern Calibration Schemas ====================

class StartPatternCalibrationRequest(BaseModel):
    """启动方向图校准请求"""
    probe_ids: List[int] = Field(..., min_length=1, max_length=64)
    polarizations: List[PolarizationType] = Field(
        default=[PolarizationType.V, PolarizationType.H]
    )
    frequency_mhz: float = Field(..., description="测量频率 (MHz)")
    azimuth_step_deg: float = Field(default=5.0, ge=1, le=30, description="方位角步进 (度)")
    elevation_step_deg: float = Field(default=5.0, ge=1, le=30, description="俯仰角步进 (度)")
    measurement_distance_m: float = Field(
        default=3.0,
        ge=0.5,
        le=10.0,
        description="测量距离 (m)"
    )
    reference_antenna_id: Optional[str] = None
    turntable_id: Optional[str] = None
    calibrated_by: str = Field(..., description="校准人员")


class PatternCalibrationResponse(BaseModel):
    """方向图校准响应"""
    id: UUID
    probe_id: int
    polarization: str
    frequency_mhz: float
    # 角度网格
    azimuth_deg: List[float]
    elevation_deg: List[float]
    # 方向图数据
    gain_pattern_dbi: List[float]  # 扁平数组
    # 主要参数
    peak_gain_dbi: Optional[float] = None
    peak_azimuth_deg: Optional[float] = None
    peak_elevation_deg: Optional[float] = None
    hpbw_azimuth_deg: Optional[float] = None
    hpbw_elevation_deg: Optional[float] = None
    front_to_back_ratio_db: Optional[float] = None
    # 测量设置
    reference_antenna: Optional[str] = None
    turntable: Optional[str] = None
    measurement_distance_m: Optional[float] = None
    # 元数据
    measured_at: datetime
    measured_by: Optional[str] = None
    valid_until: datetime
    status: str

    class Config:
        from_attributes = True


# ==================== Link Calibration Schemas ====================

class StandardDUT(BaseModel):
    """标准 DUT 配置"""
    dut_type: Literal["dipole", "horn", "patch"] = Field(..., description="DUT 类型")
    model: str = Field(..., description="型号")
    serial: str = Field(..., description="序列号")
    known_gain_dbi: float = Field(..., description="已知增益 (dBi)")


class StartLinkCalibrationRequest(BaseModel):
    """启动链路校准请求"""
    calibration_type: LinkCalibrationTypeEnum = Field(..., description="校准类型")
    standard_dut: StandardDUT = Field(..., description="标准 DUT 配置")
    frequency_mhz: float = Field(..., description="测试频率 (MHz)")
    probe_ids: Optional[List[int]] = Field(
        None,
        description="要校准的探头 ID 列表，None 表示所有探头"
    )
    threshold_db: float = Field(default=1.0, ge=0.1, le=3.0, description="合格阈值 (dB)")
    calibrated_by: str = Field(..., description="校准人员")


class ProbeLinkCalibration(BaseModel):
    """单个探头的链路校准数据"""
    probe_id: int
    link_loss_db: float
    phase_offset_deg: float


class LinkCalibrationResponse(BaseModel):
    """链路校准响应"""
    id: UUID
    calibration_type: str
    # 标准 DUT
    standard_dut_type: Optional[str] = None
    standard_dut_model: Optional[str] = None
    standard_dut_serial: Optional[str] = None
    known_gain_dbi: Optional[float] = None
    frequency_mhz: Optional[float] = None
    # 测量结果
    measured_gain_dbi: Optional[float] = None
    deviation_db: Optional[float] = None
    # 探头链路校准
    probe_link_calibrations: Optional[List[Dict[str, Any]]] = None
    # 合格判定
    validation_pass: Optional[bool] = None
    threshold_db: float
    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Validity Management Schemas ====================

class ProbeCalibrationStatus(BaseModel):
    """单个探头的校准状态"""
    probe_id: int
    # 各类校准状态
    amplitude: Optional[Dict[str, Any]] = Field(
        None,
        description="{'status': 'valid', 'valid_until': datetime, 'calibration_id': uuid}"
    )
    phase: Optional[Dict[str, Any]] = None
    polarization: Optional[Dict[str, Any]] = None
    pattern: Optional[Dict[str, Any]] = None
    link: Optional[Dict[str, Any]] = None
    # 总体状态
    overall_status: str = Field(..., description="valid | expiring_soon | expired | unknown")


class CalibrationValidityReport(BaseModel):
    """校准有效性报告"""
    total_probes: int
    valid_probes: int
    expired_probes: int
    expiring_soon_probes: int  # 7 天内过期

    expired_calibrations: List[Dict[str, Any]] = Field(
        default=[],
        description="已过期的校准列表 [{probe_id, calibration_type, expired_at, days_overdue}]"
    )
    expiring_soon_calibrations: List[Dict[str, Any]] = Field(
        default=[],
        description="即将过期的校准列表 [{probe_id, calibration_type, valid_until, days_remaining}]"
    )

    recommendations: List[Dict[str, Any]] = Field(
        default=[],
        description="建议操作 [{probe_id, calibration_type, action, priority, reason}]"
    )


class ExpiringCalibration(BaseModel):
    """即将过期的校准"""
    probe_id: int
    calibration_type: str
    valid_until: datetime
    days_remaining: int


class InvalidateCalibrationRequest(BaseModel):
    """作废校准请求"""
    reason: str = Field(..., min_length=5, max_length=500, description="作废原因")


# ==================== Calibration History Schemas ====================

class CalibrationHistoryQuery(BaseModel):
    """校准历史查询参数"""
    probe_id: int
    calibration_type: Optional[str] = Field(
        None,
        description="amplitude | phase | polarization | pattern | link"
    )
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(default=20, ge=1, le=100)


class CalibrationHistoryItem(BaseModel):
    """校准历史记录"""
    calibration_id: UUID
    calibration_type: str
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    status: str
    summary: Dict[str, Any] = Field(
        default={},
        description="关键参数摘要"
    )


class CalibrationHistoryResponse(BaseModel):
    """校准历史响应"""
    probe_id: int
    history: List[CalibrationHistoryItem]
    # 趋势分析
    trends: Optional[Dict[str, Any]] = Field(
        None,
        description="趋势分析 {amplitude_drift_db_per_month, phase_drift_deg_per_month, stability_rating}"
    )


# ==================== Probe Calibration Data Query ====================

class ProbeCalibrationDataResponse(BaseModel):
    """探头校准数据综合响应"""
    probe_id: int
    amplitude_calibration: Optional[AmplitudeCalibrationResponse] = None
    phase_calibration: Optional[PhaseCalibrationResponse] = None
    polarization_calibration: Optional[PolarizationCalibrationResponse] = None
    pattern_calibrations: Optional[List[PatternCalibrationResponse]] = None  # 多频点
    link_calibration: Optional[LinkCalibrationResponse] = None
    validity_status: ProbeCalibrationStatus


# ==================== Probe Path Loss Calibration Schemas ====================

class ChainTypeEnum(str, Enum):
    """RF 链路类型"""
    UPLINK = "uplink"      # 上行链路 (DUT TX → CE RX)
    DOWNLINK = "downlink"  # 下行链路 (CE TX → DUT RX)


class ProbePathLossData(BaseModel):
    """单个探头的路损数据"""
    probe_id: int = Field(..., ge=0, le=63, description="探头 ID")
    path_loss_db: float = Field(..., description="路损 (dB)")
    uncertainty_db: float = Field(default=0.5, ge=0, le=5, description="不确定度 (dB)")
    pol_v_db: Optional[float] = Field(None, description="V 极化路损 (dB)")
    pol_h_db: Optional[float] = Field(None, description="H 极化路损 (dB)")


class StartProbePathLossCalibrationRequest(BaseModel):
    """启动探头路损校准请求"""
    chamber_id: UUID = Field(..., description="暗室配置 ID")
    frequency_mhz: float = Field(..., ge=100, le=100000, description="测量频率 (MHz)")

    # SGH 参考天线
    sgh_model: str = Field(..., description="SGH 型号")
    sgh_serial: Optional[str] = Field(None, description="SGH 序列号")
    sgh_gain_dbi: float = Field(..., description="SGH 标定增益 (dBi)")

    # 测量设置
    vna_id: Optional[str] = Field(None, description="VNA 设备 ID")
    cable_loss_db: float = Field(default=0.0, ge=0, le=20, description="测量电缆损耗 (dB)")

    # 选择性校准
    probe_ids: Optional[List[int]] = Field(
        None,
        description="要校准的探头 ID 列表，None 表示所有探头"
    )
    polarizations: List[PolarizationType] = Field(
        default=[PolarizationType.V, PolarizationType.H],
        description="要校准的极化类型"
    )

    calibrated_by: str = Field(..., description="校准人员")


class ProbePathLossCalibrationResponse(BaseModel):
    """探头路损校准响应"""
    id: UUID
    chamber_id: UUID
    frequency_mhz: float

    # 探头路损数据
    probe_path_losses: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="探头路损数据，格式: {probe_id: {path_loss_db, uncertainty_db, pol_v_db, pol_h_db}}"
    )

    # 参考天线
    sgh_model: str
    sgh_serial: Optional[str] = None
    sgh_gain_dbi: float
    sgh_certificate_date: Optional[datetime] = None

    # 测量设置
    vna_model: Optional[str] = None
    cable_loss_db: float = 0.0
    measurement_distance_m: Optional[float] = None

    # 环境条件
    temperature_celsius: Optional[float] = None
    humidity_percent: Optional[float] = None

    # 统计数据
    avg_path_loss_db: Optional[float] = None
    max_path_loss_db: Optional[float] = None
    min_path_loss_db: Optional[float] = None
    std_dev_db: Optional[float] = None

    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: datetime
    status: str

    class Config:
        from_attributes = True


# ==================== RF Chain Calibration Schemas ====================

class StartRFChainCalibrationRequest(BaseModel):
    """启动 RF 链路增益校准请求"""
    chamber_id: UUID = Field(..., description="暗室配置 ID")
    chain_type: ChainTypeEnum = Field(..., description="链路类型: uplink 或 downlink")
    frequency_mhz: float = Field(..., ge=100, le=100000, description="测量频率 (MHz)")

    # 测量设备
    vna_id: Optional[str] = Field(None, description="VNA 设备 ID")
    power_meter_id: Optional[str] = Field(None, description="功率计设备 ID")
    signal_generator_id: Optional[str] = Field(None, description="信号源设备 ID")

    # 选择性校准 (探头级精细校准)
    probe_ids: Optional[List[int]] = Field(
        None,
        description="要校准的探头 ID 列表，None 表示测量整体链路"
    )

    calibrated_by: str = Field(..., description="校准人员")


class RFChainCalibrationResponse(BaseModel):
    """RF 链路增益校准响应"""
    id: UUID
    chamber_id: UUID
    chain_type: str
    frequency_mhz: float

    # 上行链路参数 (LNA)
    has_lna: bool = False
    lna_model: Optional[str] = None
    lna_serial: Optional[str] = None
    lna_gain_measured_db: Optional[float] = None
    lna_noise_figure_db: Optional[float] = None
    lna_p1db_dbm: Optional[float] = None

    # 下行链路参数 (PA)
    has_pa: bool = False
    pa_model: Optional[str] = None
    pa_serial: Optional[str] = None
    pa_gain_measured_db: Optional[float] = None
    pa_p1db_measured_dbm: Optional[float] = None

    # 双工器参数
    has_duplexer: bool = False
    duplexer_model: Optional[str] = None
    duplexer_insertion_loss_db: Optional[float] = None
    duplexer_isolation_measured_db: Optional[float] = None

    # 电缆损耗
    cable_loss_to_ce_db: Optional[float] = None
    cable_loss_to_probe_db: Optional[float] = None

    # 链路总增益
    total_chain_gain_db: Optional[float] = None

    # 探头级链路数据
    probe_chain_data: Optional[Dict[str, Dict[str, Any]]] = None

    # 测量设备
    vna_model: Optional[str] = None
    power_meter_model: Optional[str] = None
    signal_generator_model: Optional[str] = None

    # 环境条件
    temperature_celsius: Optional[float] = None

    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: datetime
    status: str

    class Config:
        from_attributes = True


# ==================== Multi-Frequency Path Loss Schemas ====================

class StartMultiFrequencyPathLossRequest(BaseModel):
    """启动多频点路损校准请求"""
    chamber_id: UUID = Field(..., description="暗室配置 ID")
    probe_ids: List[int] = Field(..., min_length=1, max_length=64, description="探头 ID 列表")
    polarization: PolarizationType = Field(..., description="极化类型")

    # 频率范围
    freq_start_mhz: float = Field(..., ge=100, le=100000, description="起始频率 (MHz)")
    freq_stop_mhz: float = Field(..., ge=100, le=100000, description="终止频率 (MHz)")
    freq_step_mhz: float = Field(..., ge=1, le=1000, description="频率步进 (MHz)")

    # SGH 参考天线
    sgh_model: str = Field(..., description="SGH 型号")
    sgh_gain_dbi: float = Field(..., description="SGH 标定增益 (dBi)")

    # 测量设备
    vna_id: Optional[str] = Field(None, description="VNA 设备 ID")

    calibrated_by: str = Field(..., description="校准人员")

    @field_validator('freq_stop_mhz')
    @classmethod
    def validate_freq_range(cls, v, info):
        if 'freq_start_mhz' in info.data and v <= info.data['freq_start_mhz']:
            raise ValueError('freq_stop_mhz must be greater than freq_start_mhz')
        return v


class MultiFrequencyPathLossResponse(BaseModel):
    """多频点路损校准响应"""
    id: UUID
    chamber_id: UUID
    probe_id: int
    polarization: str

    # 频率范围
    freq_start_mhz: float
    freq_stop_mhz: float
    freq_step_mhz: float
    num_points: int

    # 扫频数据
    frequency_points_mhz: List[float]
    path_loss_db: List[float]
    uncertainty_db: Optional[List[float]] = None

    # 插值系数
    interpolation_coefficients: Optional[Dict[str, Any]] = None

    # 元数据
    calibrated_at: datetime
    calibrated_by: Optional[str] = None
    valid_until: datetime
    status: str

    class Config:
        from_attributes = True


# ==================== Calibration Summary Schemas ====================

class ChamberCalibrationSummary(BaseModel):
    """暗室校准汇总"""
    chamber_id: UUID
    chamber_name: str

    # 路损校准
    path_loss_calibration: Optional[Dict[str, Any]] = Field(
        None,
        description="{'status': 'valid', 'calibrated_at': datetime, 'avg_loss_db': float}"
    )

    # RF 链路校准
    uplink_calibration: Optional[Dict[str, Any]] = Field(
        None,
        description="上行链路校准状态 {'status': str, 'lna_gain_db': float, 'calibrated_at': datetime}"
    )
    downlink_calibration: Optional[Dict[str, Any]] = Field(
        None,
        description="下行链路校准状态 {'status': str, 'pa_gain_db': float, 'calibrated_at': datetime}"
    )

    # 多频点校准
    multi_frequency_coverage: Optional[Dict[str, Any]] = Field(
        None,
        description="多频点覆盖 {'freq_min_mhz': float, 'freq_max_mhz': float, 'num_points': int}"
    )

    # 总体状态
    overall_status: str = Field(
        ...,
        description="valid | partial | expired | not_calibrated"
    )
    next_calibration_due: Optional[datetime] = None

    # 建议
    recommendations: List[str] = []
