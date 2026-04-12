"""System calibration database models"""
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from datetime import datetime

from app.db.database import Base


class SystemTRPCalibration(Base):
    """TRP (Total Radiated Power) calibration records"""
    __tablename__ = "system_trp_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Standard DUT
    standard_dut_model = Column(String(255), nullable=False)
    standard_dut_serial = Column(String(255), nullable=False)
    reference_trp_dbm = Column(Float, nullable=False, comment="Known TRP from reference lab")
    reference_lab = Column(String(255), comment="Reference laboratory name")
    reference_cert_number = Column(String(255), comment="Reference certificate number")

    # Test configuration
    frequency_mhz = Column(Float, nullable=False)
    channel = Column(String(50))
    bandwidth_mhz = Column(Float)
    modulation = Column(String(100))
    tx_power_dbm = Column(Float)

    # Measurement results
    measured_trp_dbm = Column(Float, nullable=False)
    measurement_uncertainty_db = Column(Float)

    # Error analysis
    trp_error_db = Column(Float, nullable=False, comment="measured - reference")
    absolute_error_db = Column(Float, nullable=False, comment="abs(trp_error_db)")

    # Probe data
    num_probes_used = Column(Integer)
    probe_data = Column(JSON, comment="Array of {probe_id, theta, phi, measured_power_dbm}")

    # Integration
    integration_method = Column(String(100), default="spherical_integration")
    theta_step_deg = Column(Float, default=15.0)
    phi_step_deg = Column(Float, default=15.0)

    # Validation
    validation_pass = Column(Boolean, nullable=False)
    threshold_db = Column(Float, default=0.5, comment="Pass threshold ±0.5 dB")
    notes = Column(Text)

    # Metadata
    tested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tested_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SystemTISCalibration(Base):
    """TIS (Total Isotropic Sensitivity) calibration records"""
    __tablename__ = "system_tis_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Standard DUT
    standard_dut_model = Column(String(255), nullable=False)
    standard_dut_serial = Column(String(255), nullable=False)
    reference_tis_dbm = Column(Float, nullable=False)
    reference_lab = Column(String(255))
    reference_cert_number = Column(String(255))

    # Test configuration
    frequency_mhz = Column(Float, nullable=False)
    channel = Column(String(50))
    bandwidth_mhz = Column(Float)
    modulation = Column(String(100))
    target_throughput_mbps = Column(Float, comment="Target throughput for sensitivity")

    # Measurement results
    measured_tis_dbm = Column(Float, nullable=False)
    measurement_uncertainty_db = Column(Float)

    # Error analysis
    tis_error_db = Column(Float, nullable=False)
    absolute_error_db = Column(Float, nullable=False)

    # Probe data
    num_probes_used = Column(Integer)
    probe_data = Column(JSON, comment="Array of {probe_id, theta, phi, sensitivity_dbm}")

    # Integration
    integration_method = Column(String(100), default="harmonic_mean")
    theta_step_deg = Column(Float, default=15.0)
    phi_step_deg = Column(Float, default=15.0)

    # Validation
    validation_pass = Column(Boolean, nullable=False)
    threshold_db = Column(Float, default=1.0)
    notes = Column(Text)

    # Metadata
    tested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tested_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RepeatabilityTest(Base):
    """Repeatability test records"""
    __tablename__ = "repeatability_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    test_type = Column(String(50), nullable=False, comment="TRP, TIS, or EIS")

    # Standard DUT
    dut_model = Column(String(255))
    dut_serial = Column(String(255))

    # Measurement data
    measurements = Column(JSON, nullable=False, comment="[{run_number, value_dbm, timestamp}, ...]")

    # Statistics
    num_runs = Column(Integer, nullable=False)
    mean_dbm = Column(Float, nullable=False)
    std_dev_db = Column(Float, nullable=False, comment="Standard deviation")
    coefficient_of_variation = Column(Float, comment="std_dev / mean")
    min_dbm = Column(Float)
    max_dbm = Column(Float)
    range_db = Column(Float, comment="max - min")

    # Validation
    validation_pass = Column(Boolean, nullable=False)
    threshold_db = Column(Float, nullable=False, comment="Pass if std_dev < threshold")

    # Metadata
    tested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tested_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())


class ComparabilityTest(Base):
    """Comparability (inter-laboratory comparison) test records"""
    __tablename__ = "comparability_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    round_robin_id = Column(UUID(as_uuid=True), comment="Shared ID for round-robin test")

    # Laboratory information
    lab_name = Column(String(255), nullable=False)
    lab_id = Column(String(100))
    lab_accreditation = Column(String(255), comment="e.g., ISO/IEC 17025:2017")

    # Standard DUT
    dut_model = Column(String(255))
    dut_serial = Column(String(255))
    dut_stable = Column(Boolean, comment="DUT stability check passed")

    # Local measurements
    local_trp_dbm = Column(Float)
    local_tis_dbm = Column(Float)
    local_eis_dbm = Column(Float)
    local_measured_at = Column(DateTime)

    # Reference measurements
    reference_measurements = Column(JSON, comment="[{lab_name, trp_dbm, tis_dbm, eis_dbm, measured_at}, ...]")

    # Comparison analysis
    trp_bias_db = Column(JSON, comment="Bias vs. each reference lab")
    tis_bias_db = Column(JSON)
    eis_bias_db = Column(JSON)

    trp_mean_bias_db = Column(Float, comment="Average bias")
    tis_mean_bias_db = Column(Float)
    eis_mean_bias_db = Column(Float)

    # Validation
    validation_pass = Column(Boolean)
    threshold_db = Column(Float, default=1.0)
    notes = Column(Text)

    # Metadata
    tested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tested_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())


class CalibrationCertificate(Base):
    """Calibration certificates"""
    __tablename__ = "calibration_certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    certificate_number = Column(String(100), unique=True, nullable=False)

    # System information
    system_name = Column(String(255), comment="e.g., Meta-3D MPAC System")
    system_serial_number = Column(String(255))
    system_configuration = Column(JSON, comment="Configuration details")

    # Laboratory information
    lab_name = Column(String(255))
    lab_address = Column(Text)
    lab_accreditation = Column(String(255))
    lab_accreditation_body = Column(String(100), comment="e.g., CNAS, A2LA")

    # Dates
    calibration_date = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False, comment="calibration_date + validity_period")

    # Standards
    standards = Column(JSON, comment='["3GPP TS 34.114", "CTIA OTA Ver. 4.0"]')

    # Calibration results
    trp_error_db = Column(Float)
    trp_pass = Column(Boolean)

    tis_error_db = Column(Float)
    tis_pass = Column(Boolean)

    repeatability_std_dev_db = Column(Float)
    repeatability_pass = Column(Boolean)

    comparability_bias_db = Column(Float)
    comparability_pass = Column(Boolean)

    overall_pass = Column(Boolean, nullable=False)

    # Signatures
    calibrated_by = Column(String(100))
    calibrated_by_signature = Column(Text, comment="Base64 encoded signature image")

    reviewed_by = Column(String(100))
    reviewed_by_signature = Column(Text)

    digital_signature = Column(String(255), comment="SHA-256 hash for integrity")

    # Attachments
    attachments = Column(JSON, comment='[{type, file_path, description}, ...]')

    # PDF
    pdf_path = Column(String(500), comment="Path to generated PDF certificate")

    # Metadata
    issued_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class QuietZoneCalibration(Base):
    """
    Quiet Zone Quality Validation

    验证静区（Quiet Zone）的电磁场质量，这是 MIMO OTA 系统的核心指标。
    静区质量由软件算法和校准决定，而非暗室的物理尺寸。

    支持的验证类型：
    1. field_uniformity - 场均匀性测试 (使用 SGH 在静区内扫描)
    2. spatial_correlation - 空间相关性验证
    3. probe_coupling - 探头互耦测量
    4. phase_stability - 相位稳定性测试

    CAL-07: 关联暗室配置和 SGH 测量方法
    - field_uniformity 测量使用 SGH 在静区内多点扫描
    - 需要记录 SGH 参考天线信息和测量方法
    """
    __tablename__ = "quiet_zone_calibrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 暗室配置关联 (CAL-07)
    chamber_id = Column(
        UUID(as_uuid=True),
        index=True,
        comment="关联的暗室配置 ID，用于获取探头阵列和几何参数"
    )

    # Validation type
    validation_type = Column(
        String(50),
        nullable=False,
        comment="field_uniformity | spatial_correlation | probe_coupling | phase_stability"
    )

    # Test configuration
    frequency_mhz = Column(Float, nullable=False)
    channel = Column(String(50))
    bandwidth_mhz = Column(Float, default=20.0)

    # Quiet Zone geometry
    qz_center_x_cm = Column(Float, default=0.0, comment="QZ center X coordinate")
    qz_center_y_cm = Column(Float, default=0.0, comment="QZ center Y coordinate")
    qz_center_z_cm = Column(Float, default=150.0, comment="QZ center Z coordinate (height)")
    qz_diameter_cm = Column(Float, default=100.0, comment="QZ diameter")

    # Measurement grid
    grid_points = Column(Integer, default=25, comment="Number of measurement points (e.g., 5x5 grid)")
    grid_data = Column(JSON, comment="Array of {x, y, z, measured_value, ...}")

    # ===== SGH Reference Antenna (CAL-07) =====
    # 用于场均匀性测量的标准增益天线
    sgh_model = Column(String(255), comment="SGH 型号，如 'ETS-Lindgren 3164-06'")
    sgh_serial = Column(String(255), comment="SGH 序列号")
    sgh_gain_dbi = Column(Float, comment="SGH 标定增益 (dBi)")
    sgh_certificate_date = Column(DateTime, comment="SGH 校准证书日期")

    # Measurement method (CAL-07)
    measurement_method = Column(
        String(100),
        comment="测量方法: sgh_scan (SGH扫描), probe_synthesis (探头合成), reference_dut (参考DUT)"
    )
    scan_pattern = Column(
        String(50),
        comment="扫描模式: grid (网格), radial (径向), random (随机)"
    )
    scan_step_cm = Column(Float, comment="扫描步进 (cm)")

    # VNA measurement settings
    vna_model = Column(String(255), comment="VNA 型号")
    vna_if_bandwidth_hz = Column(Float, comment="VNA IF 带宽 (Hz)")

    # ===== Field Uniformity Results =====
    # 场均匀性：静区内不同位置的场强差异
    # 标准：±1 dB (3GPP TS 34.114)
    field_uniformity_db = Column(Float, comment="Max field variation in dB")
    field_uniformity_pass = Column(Boolean, comment="True if < ±1 dB")
    field_mean_dbm = Column(Float, comment="Mean field strength")
    field_std_dev_db = Column(Float, comment="Standard deviation")
    field_max_dbm = Column(Float, comment="Maximum field strength")
    field_min_dbm = Column(Float, comment="Minimum field strength")

    # ===== Spatial Correlation Results =====
    # 空间相关性：MIMO 信道的空间相关性矩阵
    # 对比目标信道模型（如 3GPP UMa, UMi）
    spatial_correlation_matrix = Column(JSON, comment="NxN correlation matrix")
    target_channel_model = Column(String(100), comment="e.g., 3GPP_UMa, 3GPP_UMi")
    correlation_error_rms = Column(Float, comment="RMS error vs target model")
    correlation_pass = Column(Boolean, comment="True if RMS error < threshold")

    # ===== Probe Coupling Results =====
    # 探头互耦：测量探头间的 S 参数矩阵
    # 用于互耦补偿算法
    num_probes_measured = Column(Integer, comment="Number of probes in coupling matrix")
    coupling_matrix = Column(JSON, comment="S-parameter matrix (complex values)")
    max_coupling_db = Column(Float, comment="Maximum coupling between any two probes")
    coupling_pass = Column(Boolean, comment="True if max coupling < -20 dB")

    # ===== Phase Stability Results =====
    # 相位稳定性：验证系统相位漂移
    # 对 MIMO 相位同步至关重要
    measurement_duration_sec = Column(Float, comment="Duration of stability test")
    phase_drift_deg = Column(Float, comment="Maximum phase drift in degrees")
    phase_stability_pass = Column(Boolean, comment="True if drift < 10°")
    phase_time_series = Column(JSON, comment="Array of {time_sec, phase_deg}")

    # ===== Overall Validation =====
    validation_pass = Column(Boolean, nullable=False, comment="Overall pass/fail")
    threshold_value = Column(Float, comment="Threshold used for pass/fail")

    # Probe selection
    probes_used = Column(JSON, comment="List of probe IDs used in test")

    # Environmental conditions
    temperature_celsius = Column(Float)
    humidity_percent = Column(Float)

    # Notes
    notes = Column(Text)

    # Metadata
    tested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    tested_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
