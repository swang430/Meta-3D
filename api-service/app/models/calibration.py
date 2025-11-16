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
