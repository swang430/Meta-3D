"""Pydantic schemas for system calibration"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID


# ==================== TRP Calibration Schemas ====================

class TRPCalibrationRequest(BaseModel):
    """Request to execute TRP calibration"""
    standard_dut_model: str = Field(..., description="Model of standard DUT")
    standard_dut_serial: str = Field(..., description="Serial number of standard DUT")
    reference_trp_dbm: float = Field(..., description="Known TRP from reference lab (dBm)")
    frequency_mhz: float = Field(..., description="Test frequency (MHz)")
    tx_power_dbm: float = Field(..., description="Transmit power (dBm)")
    tested_by: str = Field(..., description="Name of test engineer")
    reference_lab: Optional[str] = Field(None, description="Reference laboratory name")
    reference_cert_number: Optional[str] = Field(None, description="Reference certificate number")


class TRPCalibrationResponse(BaseModel):
    """Response from TRP calibration"""
    id: UUID
    measured_trp_dbm: float
    trp_error_db: float
    absolute_error_db: float
    validation_pass: bool
    threshold_db: float
    num_probes_used: int
    tested_at: datetime

    class Config:
        from_attributes = True


# ==================== TIS Calibration Schemas ====================

class TISCalibrationRequest(BaseModel):
    """Request to execute TIS calibration"""
    standard_dut_model: str
    standard_dut_serial: str
    reference_tis_dbm: float = Field(..., description="Known TIS from reference lab (dBm)")
    frequency_mhz: float
    tested_by: str
    reference_lab: Optional[str] = None
    reference_cert_number: Optional[str] = None


class TISCalibrationResponse(BaseModel):
    """Response from TIS calibration"""
    id: UUID
    measured_tis_dbm: float
    tis_error_db: float
    absolute_error_db: float
    validation_pass: bool
    threshold_db: float
    num_probes_used: int
    tested_at: datetime

    class Config:
        from_attributes = True


# ==================== Repeatability Test Schemas ====================

class RepeatabilityTestRequest(BaseModel):
    """Request to execute repeatability test"""
    test_type: str = Field(..., description="Type: TRP, TIS, or EIS")
    dut_model: str
    dut_serial: str
    num_runs: int = Field(..., ge=3, le=20, description="Number of repeated measurements")
    frequency_mhz: float
    tested_by: str


class RepeatabilityTestResponse(BaseModel):
    """Response from repeatability test"""
    id: UUID
    test_type: str
    num_runs: int
    mean_dbm: float
    std_dev_db: float
    coefficient_of_variation: float
    min_dbm: float
    max_dbm: float
    range_db: float
    validation_pass: bool
    threshold_db: float
    measurements: List[Dict[str, Any]]
    tested_at: datetime

    class Config:
        from_attributes = True


# ==================== Certificate Schemas ====================

class GenerateCertificateRequest(BaseModel):
    """Request to generate calibration certificate"""
    trp_calibration_id: UUID
    tis_calibration_id: UUID
    repeatability_test_id: UUID
    lab_name: str = Field(..., description="Laboratory name")
    lab_address: str = Field(..., description="Laboratory address")
    lab_accreditation: str = Field(default="ISO/IEC 17025:2017", description="Accreditation standard")
    calibrated_by: str = Field(..., description="Calibration engineer name")
    reviewed_by: str = Field(..., description="Technical reviewer name")
    validity_months: int = Field(default=12, ge=1, le=24, description="Certificate validity (months)")


class CertificateResponse(BaseModel):
    """Response from certificate generation"""
    id: UUID
    certificate_number: str
    overall_pass: bool
    trp_pass: bool
    tis_pass: bool
    repeatability_pass: bool
    calibration_date: datetime
    valid_until: datetime
    issued_at: datetime

    class Config:
        from_attributes = True


class CertificateDetail(BaseModel):
    """Detailed certificate information"""
    id: UUID
    certificate_number: str
    system_name: str
    system_serial_number: Optional[str]
    system_configuration: Optional[Dict[str, Any]]
    lab_name: Optional[str]
    lab_address: Optional[str]
    lab_accreditation: Optional[str]
    calibration_date: datetime
    valid_until: datetime
    standards: Optional[List[str]]
    trp_error_db: Optional[float]
    trp_pass: Optional[bool]
    tis_error_db: Optional[float]
    tis_pass: Optional[bool]
    repeatability_std_dev_db: Optional[float]
    repeatability_pass: Optional[bool]
    overall_pass: bool
    calibrated_by: Optional[str]
    reviewed_by: Optional[str]
    digital_signature: Optional[str]
    issued_at: datetime

    class Config:
        from_attributes = True


# ==================== Comparability Test Schemas ====================

class ComparabilityTestRequest(BaseModel):
    """Request to execute comparability test"""
    round_robin_id: Optional[UUID] = Field(None, description="Round-robin test ID (shared across labs)")
    lab_name: str = Field(..., description="This laboratory's name")
    lab_id: str = Field(..., description="This laboratory's ID")
    lab_accreditation: str = Field(default="ISO/IEC 17025:2017", description="Accreditation standard")
    dut_model: str
    dut_serial: str
    local_trp_dbm: float = Field(..., description="TRP measured by this lab")
    local_tis_dbm: float = Field(..., description="TIS measured by this lab")
    local_eis_dbm: Optional[float] = Field(None, description="EIS measured by this lab")
    reference_measurements: List[Dict[str, Any]] = Field(..., description="Measurements from other labs")
    tested_by: str


class ComparabilityTestResponse(BaseModel):
    """Response from comparability test"""
    id: UUID
    round_robin_id: Optional[UUID]
    lab_name: str
    trp_mean_bias_db: float
    tis_mean_bias_db: float
    eis_mean_bias_db: Optional[float]
    validation_pass: Optional[bool]
    threshold_db: float
    tested_at: datetime

    class Config:
        from_attributes = True


class RoundRobinSummary(BaseModel):
    """Summary of round-robin test"""
    round_robin_id: str
    num_labs: int
    labs: List[Dict[str, Any]]
    trp: Optional[Dict[str, Optional[float]]]
    tis: Optional[Dict[str, Optional[float]]]


# ==================== List/Query Schemas ====================

class CalibrationListResponse(BaseModel):
    """List of calibration records"""
    total: int
    items: List[TRPCalibrationResponse] | List[TISCalibrationResponse] | List[RepeatabilityTestResponse]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    database_connected: bool
    mock_instruments: bool


# ==================== Quiet Zone Calibration Schemas ====================

class QuietZoneCalibrationRequest(BaseModel):
    """Request to execute quiet zone validation"""
    validation_type: str = Field(..., description="field_uniformity | spatial_correlation | probe_coupling | phase_stability")
    frequency_mhz: float
    tested_by: str
    grid_points: Optional[int] = 25  # 5x5 grid
    probes_used: Optional[List[int]] = None  # Specific probe IDs


class QuietZoneCalibrationResponse(BaseModel):
    """Response from quiet zone calibration"""
    id: UUID
    validation_type: str
    frequency_mhz: float
    validation_pass: bool
    threshold_value: float
    # 场均匀性结果
    field_uniformity_db: Optional[float] = None
    field_mean_dbm: Optional[float] = None
    # 空间相关性结果
    correlation_error_rms: Optional[float] = None
    # 探头互耦结果
    max_coupling_db: Optional[float] = None
    # 相位稳定性结果
    phase_drift_deg: Optional[float] = None
    tested_at: datetime
    tested_by: str

    class Config:
        from_attributes = True
