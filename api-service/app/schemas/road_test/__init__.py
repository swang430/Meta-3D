"""
Virtual Road Test Schemas

Pydantic models for request/response validation
"""

from .scenario import (
    # Enums
    NetworkType,
    ScenarioCategory,
    ScenarioSource,
    ChannelModel,
    RouteType,
    EnvironmentType,
    WeatherCondition,
    TrafficDensity,
    TrafficType,
    EventType,
    KPIType,
    # Data models
    NetworkConfig,
    BaseStationConfig,
    Waypoint,
    Route,
    Environment,
    TrafficConfig,
    ScenarioEvent,
    HandoverEvent,
    BeamSwitchEvent,
    RFImpairmentEvent,
    TrafficBurstEvent,
    KPIDefinition,
    # Step configuration models
    ChamberInitConfig,
    NetworkConfigStep,
    BaseStationSetupConfig,
    OTAMapperConfig,
    RouteExecutionConfig,
    KPIValidationConfig,
    ReportGenerationConfig,
    StepConfiguration,
    # Scenario models
    RoadTestScenario,
    ScenarioCreate,
    ScenarioUpdate,
    ScenarioSummary,
)

from .topology import (
    # Enums
    TopologyType,
    DeviceType,
    InterfaceType,
    CableType,
    # Data models
    DeviceConfig,
    BaseStationDevice,
    ChannelEmulatorDevice,
    DUTDevice,
    RFConnection,
    NetworkTopology,
    TopologyCreate,
    TopologyUpdate,
    TopologySummary,
    TopologyValidationRequest,
    TopologyValidationResult,
)

from .execution import (
    # Enums
    TestMode,
    ExecutionStatus,
    ControlAction,
    # Data models
    TestCapabilities,
    TestStatus,
    TestMetrics,
    KPIMetrics,
    TestExecution,
    ExecutionCreate,
    ExecutionControl,
    ExecutionSummary,
    # Report models
    PhaseResult,
    KPISummary,
    ScenarioInfo,
    NetworkInfo,
    EnvironmentInfo,
    RouteInfo,
    BaseStationInfo,
    StepConfigInfo,
    ExecutionReport,
    # Metrics submission models
    TimeSeriesPoint,
    ExecutionMetricsSubmit,
    # Detailed config models
    NetworkConfigDetail,
    BaseStationConfigDetail,
    DigitalTwinConfig,
    CustomConfigHighlight,
    TrajectoryPoint,
    # Streaming models
    MetricsStreamMessage,
    StreamSubscription,
)

__all__ = [
    # Scenario enums
    "NetworkType",
    "ScenarioCategory",
    "ScenarioSource",
    "ChannelModel",
    "RouteType",
    "EnvironmentType",
    "WeatherCondition",
    "TrafficDensity",
    "TrafficType",
    "EventType",
    "KPIType",
    # Scenario models
    "NetworkConfig",
    "BaseStationConfig",
    "Waypoint",
    "Route",
    "Environment",
    "TrafficConfig",
    "ScenarioEvent",
    "HandoverEvent",
    "BeamSwitchEvent",
    "RFImpairmentEvent",
    "TrafficBurstEvent",
    "KPIDefinition",
    # Step configuration models
    "ChamberInitConfig",
    "NetworkConfigStep",
    "BaseStationSetupConfig",
    "OTAMapperConfig",
    "RouteExecutionConfig",
    "KPIValidationConfig",
    "ReportGenerationConfig",
    "StepConfiguration",
    # Scenario models
    "RoadTestScenario",
    "ScenarioCreate",
    "ScenarioUpdate",
    "ScenarioSummary",
    # Topology enums
    "TopologyType",
    "DeviceType",
    "InterfaceType",
    "CableType",
    # Topology models
    "DeviceConfig",
    "BaseStationDevice",
    "ChannelEmulatorDevice",
    "DUTDevice",
    "RFConnection",
    "NetworkTopology",
    "TopologyCreate",
    "TopologyUpdate",
    "TopologySummary",
    "TopologyValidationRequest",
    "TopologyValidationResult",
    # Execution enums
    "TestMode",
    "ExecutionStatus",
    "ControlAction",
    # Execution models
    "TestCapabilities",
    "TestStatus",
    "TestMetrics",
    "KPIMetrics",
    "TestExecution",
    "ExecutionCreate",
    "ExecutionControl",
    "ExecutionSummary",
    # Report models
    "PhaseResult",
    "KPISummary",
    "ScenarioInfo",
    "NetworkInfo",
    "EnvironmentInfo",
    "RouteInfo",
    "BaseStationInfo",
    "StepConfigInfo",
    "ExecutionReport",
    # Metrics submission models
    "TimeSeriesPoint",
    "ExecutionMetricsSubmit",
    # Detailed config models
    "NetworkConfigDetail",
    "BaseStationConfigDetail",
    "DigitalTwinConfig",
    "CustomConfigHighlight",
    "TrajectoryPoint",
    # Streaming models
    "MetricsStreamMessage",
    "StreamSubscription",
]
