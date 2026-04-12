"""Database models"""
from app.models.calibration import (
    SystemTRPCalibration,
    SystemTISCalibration,
    RepeatabilityTest,
    ComparabilityTest,
    CalibrationCertificate,
    QuietZoneCalibration,
)
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    ProbePhaseCalibration,
    ProbePolarizationCalibration,
    ProbePattern,
    LinkCalibration,
    ProbeCalibrationValidity,
    CalibrationStatus,
    Polarization,
    ProbeType,
    LinkCalibrationType,
    # New path loss and RF chain calibration models (CAL-01)
    ProbePathLossCalibration,
    RFChainCalibration,
    MultiFrequencyPathLoss,
)
from app.models.chamber import (
    ChamberConfiguration,
    ChamberType,
    CHAMBER_PRESETS,
    create_chamber_from_preset,
)
from app.models.test_plan import (
    TestPlan,
    TestCase,
    TestExecution,
    TestSequence,
    TestQueue,
    TestStep,
    TestPlanStatus,
    TestCaseType,
)
from app.models.report import (
    TestReport,
    ReportTemplate,
    ReportComparison,
    ReportSchedule,
    ReportFormat,
    ReportType,
    ReportStatus,
    TemplateType,
)
from app.models.alert import (
    Alert,
    AlertSeverity,
    AlertStatus,
)
from app.models.topology import (
    Topology,
    TopologyType,
)
from app.models.probe import (
    Probe,
    ProbePolarization,
)
from app.models.channel_calibration import (
    # Enums
    ScenarioType,
    ScenarioCondition,
    DistributionType,
    QuietZoneShape,
    FieldProbeType,
    DUTType,
    ChannelCalibrationStatus,
    # Models
    ChannelCalibrationSession,
    TemporalChannelCalibration,
    DopplerCalibration,
    SpatialCorrelationCalibration,
    AngularSpreadCalibration,
    ChannelQuietZoneCalibration,
    EISValidation,
    ChannelCalibrationValidity,
)

__all__ = [
    # System Calibration
    "SystemTRPCalibration",
    "SystemTISCalibration",
    "RepeatabilityTest",
    "ComparabilityTest",
    "CalibrationCertificate",
    "QuietZoneCalibration",
    # Probe Calibration
    "ProbeAmplitudeCalibration",
    "ProbePhaseCalibration",
    "ProbePolarizationCalibration",
    "ProbePattern",
    "LinkCalibration",
    "ProbeCalibrationValidity",
    "CalibrationStatus",
    "Polarization",
    "ProbeType",
    "LinkCalibrationType",
    # Path Loss and RF Chain Calibration (CAL-01)
    "ProbePathLossCalibration",
    "RFChainCalibration",
    "MultiFrequencyPathLoss",
    # Chamber Configuration (CAL-00)
    "ChamberConfiguration",
    "ChamberType",
    "CHAMBER_PRESETS",
    "create_chamber_from_preset",
    # Test Plan
    "TestPlan",
    "TestCase",
    "TestExecution",
    "TestSequence",
    "TestQueue",
    "TestStep",
    "TestPlanStatus",
    "TestCaseType",
    # Report
    "TestReport",
    "ReportTemplate",
    "ReportComparison",
    "ReportSchedule",
    "ReportFormat",
    "ReportType",
    "ReportStatus",
    "TemplateType",
    # Alert
    "Alert",
    "AlertSeverity",
    "AlertStatus",
    # Topology
    "Topology",
    "TopologyType",
    # Channel Calibration Enums
    "ScenarioType",
    "ScenarioCondition",
    "DistributionType",
    "QuietZoneShape",
    "FieldProbeType",
    "DUTType",
    "ChannelCalibrationStatus",
    # Channel Calibration Models
    "ChannelCalibrationSession",
    "TemporalChannelCalibration",
    "DopplerCalibration",
    "SpatialCorrelationCalibration",
    "AngularSpreadCalibration",
    "ChannelQuietZoneCalibration",
    "EISValidation",
    "ChannelCalibrationValidity",
]
