"""Pydantic schemas for API request/response models"""
from app.schemas.report import (
    # Report
    ReportCreate,
    ReportUpdate,
    ReportResponse,
    ReportSummary,
    ReportDownloadResponse,
    ReportListResponse,
    # Template
    ReportTemplateCreate,
    ReportTemplateUpdate,
    ReportTemplateResponse,
    ReportTemplateSummary,
    TemplateListResponse,
    # Comparison
    ReportComparisonCreate,
    ReportComparisonResponse,
    ComparisonListResponse,
    # Schedule
    ReportScheduleCreate,
    ReportScheduleUpdate,
    ReportScheduleResponse,
    ScheduleListResponse,
)
from app.schemas.probe_calibration import (
    # Enums
    PolarizationType,
    ProbeTypeEnum,
    CalibrationStatusEnum,
    LinkCalibrationTypeEnum,
    CalibrationJobStatus,
    # Common
    FrequencyRange,
    CalibrationJobResponse,
    CalibrationProgress,
    # Amplitude
    StartAmplitudeCalibrationRequest,
    AmplitudeCalibrationResponse,
    # Phase
    StartPhaseCalibrationRequest,
    PhaseCalibrationResponse,
    # Polarization
    StartPolarizationCalibrationRequest,
    PolarizationCalibrationResponse,
    # Pattern
    StartPatternCalibrationRequest,
    PatternCalibrationResponse,
    # Link
    StartLinkCalibrationRequest,
    LinkCalibrationResponse,
    StandardDUT,
    ProbeLinkCalibration,
    # Validity
    ProbeCalibrationStatus,
    CalibrationValidityReport,
    ExpiringCalibration,
    InvalidateCalibrationRequest,
    # History
    CalibrationHistoryQuery,
    CalibrationHistoryResponse,
    # Data Query
    ProbeCalibrationDataResponse,
)
from app.schemas.channel_calibration import (
    # Enums
    ScenarioTypeEnum,
    ScenarioConditionEnum,
    DistributionTypeEnum,
    QuietZoneShapeEnum,
    FieldProbeTypeEnum,
    DUTTypeEnum,
    ChannelCalibrationStatusEnum,
    ChannelCalibrationJobStatus,
    SessionStatusEnum,
    # Common
    CalibrationJobResponse as ChannelCalibrationJobResponse,
    CalibrationProgress as ChannelCalibrationProgress,
    ScenarioConfig,
    # Temporal
    StartTemporalCalibrationRequest,
    TemporalCalibrationResponse,
    # Doppler
    StartDopplerCalibrationRequest,
    DopplerCalibrationResponse,
    # Spatial Correlation
    StartSpatialCorrelationCalibrationRequest,
    SpatialCorrelationCalibrationResponse,
    TestDUTConfig,
    # Angular Spread
    StartAngularSpreadCalibrationRequest,
    AngularSpreadCalibrationResponse,
    # Quiet Zone
    StartQuietZoneCalibrationRequest,
    QuietZoneCalibrationResponse,
    QuietZoneConfig,
    FieldProbeConfig,
    # EIS
    StartEISValidationRequest,
    EISValidationResponse,
    EISTestConfig,
    EISDUTConfig,
    # Session
    StartCalibrationSessionRequest,
    CalibrationSessionResponse,
    UpdateSessionProgressRequest,
    CompleteSessionRequest,
    # Validity
    ChannelCalibrationValidityResponse,
    ChannelCalibrationValidityReport,
    InvalidateCalibrationRequest as ChannelInvalidateCalibrationRequest,
    InvalidateCalibrationResponse,
    # History
    ChannelCalibrationHistoryQuery,
    ChannelCalibrationHistoryResponse,
    ChannelCalibrationHistoryItem,
    # Status
    ChannelCalibrationStatusSummary,
)

__all__ = [
    # Report
    "ReportCreate",
    "ReportUpdate",
    "ReportResponse",
    "ReportSummary",
    "ReportDownloadResponse",
    "ReportListResponse",
    # Template
    "ReportTemplateCreate",
    "ReportTemplateUpdate",
    "ReportTemplateResponse",
    "ReportTemplateSummary",
    "TemplateListResponse",
    # Comparison
    "ReportComparisonCreate",
    "ReportComparisonResponse",
    "ComparisonListResponse",
    # Schedule
    "ReportScheduleCreate",
    "ReportScheduleUpdate",
    "ReportScheduleResponse",
    "ScheduleListResponse",
    # Probe Calibration - Enums
    "PolarizationType",
    "ProbeTypeEnum",
    "CalibrationStatusEnum",
    "LinkCalibrationTypeEnum",
    "CalibrationJobStatus",
    # Probe Calibration - Common
    "FrequencyRange",
    "CalibrationJobResponse",
    "CalibrationProgress",
    # Probe Calibration - Amplitude
    "StartAmplitudeCalibrationRequest",
    "AmplitudeCalibrationResponse",
    # Probe Calibration - Phase
    "StartPhaseCalibrationRequest",
    "PhaseCalibrationResponse",
    # Probe Calibration - Polarization
    "StartPolarizationCalibrationRequest",
    "PolarizationCalibrationResponse",
    # Probe Calibration - Pattern
    "StartPatternCalibrationRequest",
    "PatternCalibrationResponse",
    # Probe Calibration - Link
    "StartLinkCalibrationRequest",
    "LinkCalibrationResponse",
    "StandardDUT",
    "ProbeLinkCalibration",
    # Probe Calibration - Validity
    "ProbeCalibrationStatus",
    "CalibrationValidityReport",
    "ExpiringCalibration",
    "InvalidateCalibrationRequest",
    # Probe Calibration - History
    "CalibrationHistoryQuery",
    "CalibrationHistoryResponse",
    # Probe Calibration - Data Query
    "ProbeCalibrationDataResponse",
    # Channel Calibration - Enums
    "ScenarioTypeEnum",
    "ScenarioConditionEnum",
    "DistributionTypeEnum",
    "QuietZoneShapeEnum",
    "FieldProbeTypeEnum",
    "DUTTypeEnum",
    "ChannelCalibrationStatusEnum",
    "ChannelCalibrationJobStatus",
    "SessionStatusEnum",
    # Channel Calibration - Common
    "ChannelCalibrationJobResponse",
    "ChannelCalibrationProgress",
    "ScenarioConfig",
    # Channel Calibration - Temporal
    "StartTemporalCalibrationRequest",
    "TemporalCalibrationResponse",
    # Channel Calibration - Doppler
    "StartDopplerCalibrationRequest",
    "DopplerCalibrationResponse",
    # Channel Calibration - Spatial Correlation
    "StartSpatialCorrelationCalibrationRequest",
    "SpatialCorrelationCalibrationResponse",
    "TestDUTConfig",
    # Channel Calibration - Angular Spread
    "StartAngularSpreadCalibrationRequest",
    "AngularSpreadCalibrationResponse",
    # Channel Calibration - Quiet Zone
    "StartQuietZoneCalibrationRequest",
    "QuietZoneCalibrationResponse",
    "QuietZoneConfig",
    "FieldProbeConfig",
    # Channel Calibration - EIS
    "StartEISValidationRequest",
    "EISValidationResponse",
    "EISTestConfig",
    "EISDUTConfig",
    # Channel Calibration - Session
    "StartCalibrationSessionRequest",
    "CalibrationSessionResponse",
    "UpdateSessionProgressRequest",
    "CompleteSessionRequest",
    # Channel Calibration - Validity
    "ChannelCalibrationValidityResponse",
    "ChannelCalibrationValidityReport",
    "ChannelInvalidateCalibrationRequest",
    "InvalidateCalibrationResponse",
    # Channel Calibration - History
    "ChannelCalibrationHistoryQuery",
    "ChannelCalibrationHistoryResponse",
    "ChannelCalibrationHistoryItem",
    # Channel Calibration - Status
    "ChannelCalibrationStatusSummary",
]
