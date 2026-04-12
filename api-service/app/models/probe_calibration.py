"""
Probe Calibration Database Models

探头校准数据模型，支持 5 种校准类型：
1. 幅度校准 (Amplitude Calibration) - TX/RX 增益
2. 相位校准 (Phase Calibration) - 相位偏差和群时延
3. 极化校准 (Polarization Calibration) - XPD 和轴比
4. 方向图校准 (Pattern Calibration) - 3D 辐射方向图
5. 链路校准 (Link Calibration) - 端到端验证

参考设计: docs/features/calibration/probe-calibration.md
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON, Text, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from datetime import datetime
import enum

from app.db.database import Base


class CalibrationStatus(str, enum.Enum):
    """校准状态"""
    VALID = "valid"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    PENDING = "pending"


class Polarization(str, enum.Enum):
    """极化类型"""
    V = "V"           # 垂直极化
    H = "H"           # 水平极化
    LHCP = "LHCP"     # 左旋圆极化
    RHCP = "RHCP"     # 右旋圆极化


class ProbeType(str, enum.Enum):
    """探头类型"""
    DUAL_LINEAR = "dual_linear"   # 双线极化
    DUAL_SLANT = "dual_slant"     # 双斜极化
    CIRCULAR = "circular"         # 圆极化


class LinkCalibrationType(str, enum.Enum):
    """链路校准类型"""
    WEEKLY_CHECK = "weekly_check"
    PRE_TEST = "pre_test"
    POST_MAINTENANCE = "post_maintenance"


class ProbeAmplitudeCalibration(Base):
    """
    探头幅度校准记录

    测量每个探头的 TX/RX 增益，确保幅度一致性。
    校准方法：使用已校准的功率计和信号源测量链路增益。

    有效期：3 个月
    精度要求：±0.5 dB
    """
    __tablename__ = "probe_amplitude_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    probe_id = Column(Integer, nullable=False, index=True, comment="探头 ID (0-63)")
    polarization = Column(String(10), nullable=False, comment="极化类型: V, H, LHCP, RHCP")

    # 频率-增益数据 (JSONB 数组)
    frequency_points_mhz = Column(
        JSON, nullable=False,
        comment="频率点数组 [3300, 3400, ..., 3800]"
    )
    tx_gain_dbi = Column(
        JSON, nullable=False,
        comment="TX 增益数组 (dBi)"
    )
    rx_gain_dbi = Column(
        JSON, nullable=False,
        comment="RX 增益数组 (dBi)"
    )
    tx_gain_uncertainty_db = Column(
        JSON, nullable=False,
        comment="TX 增益不确定度数组 (dB)"
    )
    rx_gain_uncertainty_db = Column(
        JSON, nullable=False,
        comment="RX 增益不确定度数组 (dB)"
    )

    # 参考仪器
    reference_antenna = Column(
        String(255),
        comment="参考天线型号和序列号，如 'Schwarzbeck BBHA 9120 D SN:12345'"
    )
    reference_power_meter = Column(
        String(255),
        comment="参考功率计型号和序列号，如 'Keysight N1913A SN:67890'"
    )

    # 环境条件
    temperature_celsius = Column(Float, comment="环境温度 (°C)")
    humidity_percent = Column(Float, comment="相对湿度 (%)")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    calibrated_by = Column(String(100), comment="校准人员")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="校准有效期至")
    status = Column(
        String(50), default=CalibrationStatus.VALID.value,
        index=True, comment="状态: valid, expired, invalidated"
    )

    # 原始数据文件
    raw_data_file_path = Column(Text, comment="原始测量数据文件路径")

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ProbePhaseCalibration(Base):
    """
    探头相位校准记录

    测量每个探头相对于参考探头（通常是 Probe 0）的相位偏差。
    校准方法：使用 VNA 测量 S21 相位，提取相位偏差和群时延。

    有效期：3 个月
    精度要求：±1°
    """
    __tablename__ = "probe_phase_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    probe_id = Column(Integer, nullable=False, index=True, comment="探头 ID (0-63)")
    polarization = Column(String(10), nullable=False, comment="极化类型")
    reference_probe_id = Column(
        Integer, nullable=False, default=0,
        comment="参考探头 ID，通常为 0"
    )

    # 频率-相位数据
    frequency_points_mhz = Column(
        JSON, nullable=False,
        comment="频率点数组"
    )
    phase_offset_deg = Column(
        JSON, nullable=False,
        comment="相位偏差数组 (度)，相对于参考探头"
    )
    group_delay_ns = Column(
        JSON, nullable=False,
        comment="群时延数组 (ns)"
    )
    phase_uncertainty_deg = Column(
        JSON, nullable=False,
        comment="相位不确定度数组 (度)"
    )

    # 参考仪器
    vna_model = Column(String(255), comment="VNA 型号")
    vna_serial = Column(String(255), comment="VNA 序列号")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    calibrated_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime, nullable=False)
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 原始数据文件 (Touchstone .s2p)
    raw_data_file_path = Column(Text, comment="Touchstone .s2p 文件路径")

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ProbePolarizationCalibration(Base):
    """
    探头极化校准记录

    测量双极化探头的极化纯度：
    - 线极化探头：交叉极化隔离度 (XPD)
    - 圆极化探头：轴比 (AR)

    有效期：6 个月
    要求：XPD > 20 dB, AR < 3 dB
    """
    __tablename__ = "probe_polarization_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    probe_id = Column(Integer, nullable=False, index=True)
    probe_type = Column(
        String(50), nullable=False,
        comment="探头类型: dual_linear, dual_slant, circular"
    )

    # 线极化数据
    v_to_h_isolation_db = Column(Float, comment="V 极化端口对 H 极化的隔离度 (dB)")
    h_to_v_isolation_db = Column(Float, comment="H 极化端口对 V 极化的隔离度 (dB)")

    # 圆极化数据
    polarization_hand = Column(String(10), comment="圆极化旋向: LHCP, RHCP")
    axial_ratio_db = Column(Float, comment="轴比 (dB)")

    # 频率相关数据
    frequency_points_mhz = Column(JSON, comment="频率点数组")
    isolation_vs_frequency_db = Column(JSON, comment="隔离度随频率变化 (dB)")
    axial_ratio_vs_frequency_db = Column(JSON, comment="轴比随频率变化 (dB)")

    # 参考设备
    reference_antenna = Column(String(255), comment="参考天线型号")
    positioner = Column(String(255), comment="转台型号，如 'Orbit FR 5060 Turntable'")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    calibrated_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime, nullable=False)
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ProbePattern(Base):
    """
    探头方向图数据

    存储探头的 3D 辐射方向图，用于场重构算法。
    测量方法：远场测量法，转台扫描方位角和俯仰角。

    有效期：12 个月
    数据量：典型 72×36 = 2592 个测量点
    """
    __tablename__ = "probe_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    probe_id = Column(Integer, nullable=False, index=True)
    polarization = Column(String(10), nullable=False)
    frequency_mhz = Column(Float, nullable=False, index=True, comment="测量频率 (MHz)")

    # 角度网格
    azimuth_deg = Column(
        JSON, nullable=False,
        comment="方位角数组 [0, 5, 10, ..., 355]"
    )
    elevation_deg = Column(
        JSON, nullable=False,
        comment="俯仰角数组 [0, 5, 10, ..., 180]"
    )

    # 方向图数据 (存储为扁平数组，前端重构为 2D)
    gain_pattern_dbi = Column(
        JSON, nullable=False,
        comment="增益方向图数据 (dBi)，行优先存储"
    )

    # 主要参数
    peak_gain_dbi = Column(Float, comment="峰值增益 (dBi)")
    peak_azimuth_deg = Column(Float, comment="峰值方向 - 方位角 (度)")
    peak_elevation_deg = Column(Float, comment="峰值方向 - 俯仰角 (度)")
    hpbw_azimuth_deg = Column(Float, comment="方位面半功率波束宽度 (度)")
    hpbw_elevation_deg = Column(Float, comment="俯仰面半功率波束宽度 (度)")
    front_to_back_ratio_db = Column(Float, comment="前后比 (dB)")

    # 测量设置
    reference_antenna = Column(String(255), comment="参考天线")
    turntable = Column(String(255), comment="转台型号")
    measurement_distance_m = Column(Float, comment="测量距离 (m)")

    # 元数据
    measured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    measured_by = Column(String(100))

    # 有效性
    valid_until = Column(DateTime, nullable=False)
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 原始数据
    raw_data_file_path = Column(Text, comment="原始数据文件路径")

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LinkCalibration(Base):
    """
    链路校准记录

    快速校准 RF 链路的端到端传输特性。
    方法：使用已知 DUT（标准偶极子）进行快速验证。

    有效期：7 天
    频率：每周或每次测试前
    """
    __tablename__ = "link_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calibration_type = Column(
        String(50), nullable=False,
        comment="校准类型: weekly_check, pre_test, post_maintenance"
    )

    # 标准 DUT
    standard_dut_type = Column(String(50), comment="标准 DUT 类型: dipole, horn, patch")
    standard_dut_model = Column(String(255), comment="标准 DUT 型号")
    standard_dut_serial = Column(String(255), comment="标准 DUT 序列号")
    known_gain_dbi = Column(Float, comment="已知增益 (dBi)")
    frequency_mhz = Column(Float, comment="测试频率 (MHz)")

    # 测量结果
    measured_gain_dbi = Column(Float, comment="测量增益 (dBi)")
    deviation_db = Column(Float, comment="偏差 = 测量 - 已知 (dB)")

    # 探头链路校准数据 (JSONB)
    probe_link_calibrations = Column(
        JSON,
        comment="探头级链路校准 [{probe_id, link_loss_db, phase_offset_deg}, ...]"
    )

    # 合格判定
    validation_pass = Column(Boolean, comment="是否合格")
    threshold_db = Column(Float, default=1.0, comment="合格阈值 (dB)")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100))

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ProbePathLossCalibration(Base):
    """
    探头路损校准记录

    测量静区中心（SGH 位置）到每个探头的空间路径损耗。
    使用标准增益天线 (SGH) 作为参考发射源。

    校准方法：
    1. 将 SGH 置于静区中心
    2. 使用 VNA 测量 SGH 到每个探头的 S21
    3. 计算路损: PathLoss = P_tx - P_rx + G_sgh + G_probe - Cable_loss

    有效期：6 个月
    精度要求：±0.5 dB

    关联：暗室配置 (chamber_id)
    """
    __tablename__ = "probe_path_loss_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chamber_id = Column(UUID(as_uuid=True), nullable=False, index=True, comment="关联的暗室配置 ID")

    # 测试频率
    frequency_mhz = Column(Float, nullable=False, index=True, comment="测量频率 (MHz)")

    # 探头路损数据 (按探头 ID 索引)
    # 格式: {probe_id: {path_loss_db, uncertainty_db, polarization: {V: loss, H: loss}}}
    probe_path_losses = Column(
        JSON, nullable=False,
        comment="探头路损数据，格式: {probe_id: {path_loss_db, uncertainty_db, pol_v_db, pol_h_db}}"
    )

    # 参考天线 (SGH)
    sgh_model = Column(String(255), nullable=False, comment="SGH 型号，如 'ETS-Lindgren 3164-06'")
    sgh_serial = Column(String(255), comment="SGH 序列号")
    sgh_gain_dbi = Column(Float, nullable=False, comment="SGH 标定增益 (dBi)")
    sgh_certificate_date = Column(DateTime, comment="SGH 校准证书日期")

    # 测量设置
    vna_model = Column(String(255), comment="VNA 型号")
    vna_if_bandwidth_hz = Column(Float, comment="VNA IF 带宽 (Hz)")
    cable_loss_db = Column(Float, default=0.0, comment="测量电缆损耗 (dB)")
    measurement_distance_m = Column(Float, comment="SGH 到静区中心距离 (m)")

    # 环境条件
    temperature_celsius = Column(Float, comment="环境温度 (°C)")
    humidity_percent = Column(Float, comment="相对湿度 (%)")

    # 统计数据
    avg_path_loss_db = Column(Float, comment="平均路损 (dB)")
    max_path_loss_db = Column(Float, comment="最大路损 (dB)")
    min_path_loss_db = Column(Float, comment="最小路损 (dB)")
    std_dev_db = Column(Float, comment="路损标准差 (dB)")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100), comment="校准人员")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="校准有效期至")
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 原始数据文件
    raw_data_file_path = Column(Text, comment="原始测量数据文件路径")

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RFChainCalibration(Base):
    """
    RF 链路增益校准记录

    校准暗室中的有源器件（LNA、PA）增益。
    分为上行链路（含 LNA）和下行链路（含 PA）两类。

    上行链路: 探头 → LNA → 电缆 → 信道仿真器
    下行链路: 信道仿真器 → 电缆 → PA → 探头

    有效期：3 个月
    精度要求：±0.3 dB

    关联：暗室配置 (chamber_id)
    """
    __tablename__ = "rf_chain_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chamber_id = Column(UUID(as_uuid=True), nullable=False, index=True, comment="关联的暗室配置 ID")

    # 校准类型
    chain_type = Column(
        String(20), nullable=False,
        comment="链路类型: uplink (含LNA), downlink (含PA)"
    )

    # 测试频率
    frequency_mhz = Column(Float, nullable=False, index=True, comment="测量频率 (MHz)")

    # === 上行链路参数 (LNA) ===
    has_lna = Column(Boolean, default=False, comment="是否包含 LNA")
    lna_model = Column(String(255), comment="LNA 型号")
    lna_serial = Column(String(255), comment="LNA 序列号")
    lna_gain_measured_db = Column(Float, comment="测量的 LNA 增益 (dB)")
    lna_noise_figure_db = Column(Float, comment="测量的 LNA 噪声系数 (dB)")
    lna_p1db_dbm = Column(Float, comment="LNA 1dB 压缩点 (dBm)")

    # === 下行链路参数 (PA) ===
    has_pa = Column(Boolean, default=False, comment="是否包含 PA")
    pa_model = Column(String(255), comment="PA 型号")
    pa_serial = Column(String(255), comment="PA 序列号")
    pa_gain_measured_db = Column(Float, comment="测量的 PA 增益 (dB)")
    pa_p1db_measured_dbm = Column(Float, comment="测量的 PA 1dB 压缩点 (dBm)")

    # === 双工器参数 ===
    has_duplexer = Column(Boolean, default=False, comment="是否包含双工器")
    duplexer_model = Column(String(255), comment="双工器型号")
    duplexer_insertion_loss_db = Column(Float, comment="双工器插损 (dB)")
    duplexer_isolation_measured_db = Column(Float, comment="测量的双工器隔离度 (dB)")

    # === 电缆损耗 ===
    cable_loss_to_ce_db = Column(Float, comment="到信道仿真器的电缆损耗 (dB)")
    cable_loss_to_probe_db = Column(Float, comment="到探头的电缆损耗 (dB)")

    # === 链路总增益/损耗 ===
    total_chain_gain_db = Column(Float, comment="链路总增益 (dB)，正为增益，负为损耗")

    # 各探头的链路校准数据 (可选，用于探头级精细校准)
    probe_chain_data = Column(
        JSON,
        comment="探头级链路数据 {probe_id: {gain_db, phase_deg}}"
    )

    # 测量设置
    vna_model = Column(String(255), comment="VNA 型号")
    power_meter_model = Column(String(255), comment="功率计型号")
    signal_generator_model = Column(String(255), comment="信号源型号")

    # 环境条件
    temperature_celsius = Column(Float, comment="环境温度 (°C)")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100), comment="校准人员")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="校准有效期至")
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 原始数据文件
    raw_data_file_path = Column(Text, comment="原始测量数据文件路径")

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MultiFrequencyPathLoss(Base):
    """
    多频点路损校准数据

    存储扫频校准的路损数据，支持频率插值。
    用于宽带测试场景。

    关联：ProbePathLossCalibration (单频点校准)
    """
    __tablename__ = "multi_frequency_path_losses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chamber_id = Column(UUID(as_uuid=True), nullable=False, index=True, comment="暗室配置 ID")
    probe_id = Column(Integer, nullable=False, index=True, comment="探头 ID")
    polarization = Column(String(10), nullable=False, comment="极化类型: V, H")

    # 频率范围
    freq_start_mhz = Column(Float, nullable=False, comment="起始频率 (MHz)")
    freq_stop_mhz = Column(Float, nullable=False, comment="终止频率 (MHz)")
    freq_step_mhz = Column(Float, nullable=False, comment="频率步进 (MHz)")
    num_points = Column(Integer, nullable=False, comment="频率点数")

    # 扫频数据 (数组)
    frequency_points_mhz = Column(JSON, nullable=False, comment="频率点数组")
    path_loss_db = Column(JSON, nullable=False, comment="路损数组 (dB)")
    uncertainty_db = Column(JSON, comment="不确定度数组 (dB)")

    # 插值系数 (可选，用于快速查询)
    interpolation_coefficients = Column(
        JSON,
        comment="多项式插值系数，用于频率插值"
    )

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    calibrated_by = Column(String(100))
    valid_until = Column(DateTime, nullable=False)
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ProbeCalibrationValidity(Base):
    """
    探头校准有效性状态汇总

    跟踪每个探头所有校准类型的有效性状态。
    用于快速查询哪些探头需要重新校准。
    """
    __tablename__ = "probe_calibration_validity"

    probe_id = Column(Integer, primary_key=True, comment="探头 ID")

    # 幅度校准
    amplitude_valid = Column(Boolean, default=False)
    amplitude_valid_until = Column(DateTime)
    amplitude_calibration_id = Column(UUID(as_uuid=True), comment="最新幅度校准记录 ID")

    # 相位校准
    phase_valid = Column(Boolean, default=False)
    phase_valid_until = Column(DateTime)
    phase_calibration_id = Column(UUID(as_uuid=True), comment="最新相位校准记录 ID")

    # 极化校准
    polarization_valid = Column(Boolean, default=False)
    polarization_valid_until = Column(DateTime)
    polarization_calibration_id = Column(UUID(as_uuid=True))

    # 方向图校准
    pattern_valid = Column(Boolean, default=False)
    pattern_valid_until = Column(DateTime)
    pattern_calibration_id = Column(UUID(as_uuid=True))

    # 链路校准
    link_valid = Column(Boolean, default=False)
    link_valid_until = Column(DateTime)
    link_calibration_id = Column(UUID(as_uuid=True))

    # 总体状态
    overall_status = Column(
        String(50), default="unknown",
        comment="总体状态: valid, expiring_soon, expired, unknown"
    )

    # 系统字段
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ==================== CAL-04/06: 新增校准模型 ====================

class ChannelPhaseCalibration(Base):
    """
    通道相位校准记录 (CAL-04)

    测量暗室所有通道间的相位一致性。
    用于 MIMO OTA 空间保真度校准。

    有效期：90 天
    精度要求：±5°
    """
    __tablename__ = "channel_phase_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chamber_id = Column(UUID(as_uuid=True), nullable=False, index=True, comment="暗室配置 ID")
    frequency_mhz = Column(Float, nullable=False, index=True, comment="校准频率 (MHz)")

    # 参考通道
    reference_channel_id = Column(Integer, default=0, comment="参考通道 ID")

    # 通道相位数据 (JSON 数组)
    channel_phases = Column(
        JSON, nullable=False,
        comment="通道相位数据: [{channel_id, phase_deg, amplitude_db}]"
    )

    # 相位一致性指标
    coherence_score = Column(Float, comment="相位一致性得分 (0-1)")
    max_phase_deviation_deg = Column(Float, comment="最大相位偏差 (°)")
    mean_phase_deviation_deg = Column(Float, comment="平均相位偏差 (°)")
    std_phase_deviation_deg = Column(Float, comment="相位偏差标准差 (°)")

    # 补偿数据
    phase_compensation = Column(
        JSON,
        comment="相位补偿值: [{channel_id, compensation_deg}]"
    )
    compensation_applied = Column(Boolean, default=False, comment="补偿是否已应用")

    # 测量设备
    vna_model = Column(String(255), comment="VNA 型号")
    measurement_method = Column(String(50), comment="测量方法: vna, signal_generator")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100), comment="校准人员")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="校准有效期至")
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CEInternalCalibration(Base):
    """
    信道仿真器内部校准记录 (CAL-06)

    记录 CE 厂商校准程序的执行结果。

    有效期：90 天
    """
    __tablename__ = "ce_internal_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ce_id = Column(String(100), nullable=False, index=True, comment="CE 标识符")
    vendor = Column(String(50), nullable=False, comment="厂商: spirent, keysight, anite")
    calibration_type = Column(String(50), nullable=False, comment="校准类型: full, power, phase, delay")

    # 频率范围
    frequency_start_mhz = Column(Float, comment="起始频率 (MHz)")
    frequency_stop_mhz = Column(Float, comment="终止频率 (MHz)")

    # 通道校准数据
    channel_count = Column(Integer, comment="通道数量")
    channels_data = Column(
        JSON, nullable=False,
        comment="通道数据: [{channel_id, power_offset_db, phase_offset_deg, delay_offset_ns}]"
    )

    # 偏差指标
    max_power_deviation_db = Column(Float, comment="最大功率偏差 (dB)")
    max_phase_deviation_deg = Column(Float, comment="最大相位偏差 (°)")
    max_delay_deviation_ns = Column(Float, comment="最大时延偏差 (ns)")

    # 合格判定
    pass_criteria = Column(Boolean, comment="是否通过校准")
    power_tolerance_db = Column(Float, default=0.5, comment="功率容限 (dB)")
    phase_tolerance_deg = Column(Float, default=5.0, comment="相位容限 (°)")
    delay_tolerance_ns = Column(Float, default=1.0, comment="时延容限 (ns)")

    # 固件信息
    firmware_version = Column(String(100), comment="CE 固件版本")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100), comment="校准人员")
    notes = Column(Text, comment="备注")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="校准有效期至")
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CalibrationBaseline(Base):
    """
    相对校准基线记录

    存储各通道相对于参考通道的 Delta 偏移量。
    用于快速校准模式：仅测量参考通道即可推导其他通道数值。

    有效期：90 天（可配置）
    """
    __tablename__ = "calibration_baselines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chamber_id = Column(UUID(as_uuid=True), nullable=False, index=True, comment="暗室配置 ID")
    calibration_type = Column(
        String(50), nullable=False, index=True,
        comment="校准类型: amplitude, phase, path_loss"
    )
    frequency_mhz = Column(Float, nullable=False, index=True, comment="校准频率 (MHz)")

    # 参考通道
    reference_channel_id = Column(Integer, nullable=False, default=0, comment="参考通道 ID")
    reference_value_db = Column(Float, comment="基线时的参考通道值 (dB)")
    reference_value_deg = Column(Float, comment="基线时的参考通道相位 (°)")

    # Delta 矩阵: {channel_id: {delta_db, delta_deg, uncertainty_db}}
    delta_matrix = Column(
        JSON, nullable=False,
        comment="Delta 偏移矩阵: {channel_id: {delta_db, delta_deg, uncertainty}}"
    )

    # 总通道数
    total_channels = Column(Integer, comment="总通道数")

    # 漂移阈值
    drift_threshold_db = Column(Float, default=0.3, comment="幅度漂移阈值 (dB)")
    drift_threshold_deg = Column(Float, default=2.0, comment="相位漂移阈值 (°)")

    # 最近漂移检测结果
    last_drift_check_at = Column(DateTime, comment="上次漂移检测时间")
    last_drift_db = Column(Float, comment="上次检测的最大幅度漂移 (dB)")
    last_drift_deg = Column(Float, comment="上次检测的最大相位漂移 (°)")
    drift_within_threshold = Column(Boolean, default=True, comment="漂移是否在阈值内")

    # 元数据
    baseline_date = Column(DateTime, default=datetime.utcnow, nullable=False, comment="基线建立日期")
    calibrated_by = Column(String(100), comment="校准人员")
    notes = Column(Text, comment="备注")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="基线有效期至")
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RFSwitchCalibration(Base):
    """
    RF 开关矩阵校准记录 (CAL-02)

    存储 RF Switch Matrix 的插入损耗、隔离度和切换一致性校准数据。

    有效期：6 个月
    精度要求：插损 < 2 dB, 隔离度 > 60 dB
    """
    __tablename__ = "rf_switch_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chamber_id = Column(UUID(as_uuid=True), nullable=False, index=True, comment="暗室配置 ID")
    frequency_mhz = Column(Float, nullable=False, index=True, comment="校准频率 (MHz)")

    # 矩阵规模
    num_input_ports = Column(Integer, nullable=False, comment="输入端口数")
    num_output_ports = Column(Integer, nullable=False, comment="输出端口数")

    # 端口测量数据
    port_measurements = Column(
        JSON, nullable=False,
        comment="端口测量: {port_key: {insertion_loss_db, phase_deg, uncertainty_db}}"
    )

    # 隔离度测量数据
    isolation_measurements = Column(
        JSON,
        comment="隔离度: [{port_pair, isolation_db}]"
    )

    # 统计数据
    avg_insertion_loss_db = Column(Float, comment="平均插入损耗 (dB)")
    max_insertion_loss_db = Column(Float, comment="最大插入损耗 (dB)")
    min_insertion_loss_db = Column(Float, comment="最小插入损耗 (dB)")
    std_dev_db = Column(Float, comment="插损标准差 (dB)")
    avg_isolation_db = Column(Float, comment="平均隔离度 (dB)")
    worst_isolation_db = Column(Float, comment="最差隔离度 (dB)")

    # 测量设备
    vna_model = Column(String(255), comment="VNA 型号")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100), comment="校准人员")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="校准有效期至")
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class E2ECompensationMatrix(Base):
    """
    端到端补偿矩阵记录 (E2E)

    存储整合路损 + RF Switch + 链路增益后的综合补偿矩阵。
    每次执行 E2E 校准后生成一条记录。

    有效期：30 天
    """
    __tablename__ = "e2e_compensation_matrices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chamber_id = Column(UUID(as_uuid=True), nullable=False, index=True, comment="暗室配置 ID")
    frequency_mhz = Column(Float, nullable=False, index=True, comment="目标频率 (MHz)")
    num_probes = Column(Integer, nullable=False, comment="探头数量")

    # 补偿矩阵数据
    # {probe_key: {path_loss_db, cable_loss_db, switch_loss_db, pa_gain_db, lna_gain_db, dl_comp, ul_comp}}
    probe_compensations = Column(
        JSON, nullable=False,
        comment="探头补偿数据矩阵"
    )

    # 统计摘要
    dl_avg_compensation_db = Column(Float, comment="下行平均补偿 (dB)")
    dl_max_compensation_db = Column(Float, comment="下行最大补偿 (dB)")
    dl_std_compensation_db = Column(Float, comment="下行补偿标准差 (dB)")
    ul_avg_compensation_db = Column(Float, comment="上行平均补偿 (dB)")
    ul_max_compensation_db = Column(Float, comment="上行最大补偿 (dB)")
    ul_std_compensation_db = Column(Float, comment="上行补偿标准差 (dB)")

    # 一致性验证
    consistency_check_pass = Column(Boolean, comment="一致性检查是否通过")
    max_variation_db = Column(Float, comment="最大变化量 (dB)")

    # 数据来源校准 ID (追溯)
    path_loss_calibration_id = Column(UUID(as_uuid=True), comment="路损校准来源 ID")
    rf_chain_calibration_id = Column(UUID(as_uuid=True), comment="链路校准来源 ID")
    switch_calibration_id = Column(UUID(as_uuid=True), comment="开关校准来源 ID")

    # 警告信息
    warnings = Column(JSON, comment="校准警告列表")

    # 元数据
    calibrated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    calibrated_by = Column(String(100), comment="校准人员")

    # 有效性
    valid_until = Column(DateTime, nullable=False, comment="有效期至")
    status = Column(String(50), default=CalibrationStatus.VALID.value, index=True)

    # 系统字段
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
