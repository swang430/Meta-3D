"""
Road Test Scenario Schemas

Data models for virtual road test scenarios
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Literal, Union
from datetime import datetime
from enum import Enum


# ===== Enums =====

class NetworkType(str, Enum):
    """Network type"""
    NR_5G = "5G_NR"
    LTE = "LTE"
    C_V2X = "C-V2X"


class ScenarioCategory(str, Enum):
    """Scenario category"""
    STANDARD = "standard"  # 3GPP, CTIA, 5GAA
    FUNCTIONAL = "functional"  # Handover, Beam Switching
    PERFORMANCE = "performance"  # Max throughput, Low latency
    ENVIRONMENT = "environment"  # Urban, Highway, Tunnel
    EXTREME = "extreme"  # Cell edge, High interference
    CUSTOM = "custom"  # User-defined


class ScenarioSource(str, Enum):
    """Scenario source"""
    STANDARD = "standard"
    CUSTOM = "custom"


class ChannelModel(str, Enum):
    """3GPP channel model"""
    UMA = "UMa"  # Urban Macro
    UMI = "UMi"  # Urban Micro
    RMA = "RMa"  # Rural Macro
    INH = "InH"  # Indoor Hotspot
    CDL_A = "CDL-A"
    CDL_B = "CDL-B"
    CDL_C = "CDL-C"
    CDL_D = "CDL-D"
    CDL_E = "CDL-E"
    TDL_A = "TDL-A"
    TDL_B = "TDL-B"
    TDL_C = "TDL-C"


class RouteType(str, Enum):
    """Route generation type"""
    PREDEFINED = "predefined"  # Pre-recorded GPS trace
    RECORDED = "recorded"  # Real-world recording
    GENERATED = "generated"  # Algorithmically generated


class EnvironmentType(str, Enum):
    """Environment type"""
    URBAN_CANYON = "urban_canyon"
    URBAN_STREET = "urban_street"
    HIGHWAY = "highway"
    TUNNEL = "tunnel"
    PARKING_LOT = "parking_lot"
    RURAL = "rural"


class WeatherCondition(str, Enum):
    """Weather condition"""
    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    SNOW = "snow"


class TrafficDensity(str, Enum):
    """Traffic density"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TrafficType(str, Enum):
    """Traffic type"""
    FTP = "ftp"
    VIDEO = "video"
    VOIP = "voip"
    WEB = "web"
    GAMING = "gaming"


class EventType(str, Enum):
    """Scenario event type"""
    HANDOVER = "handover"
    BEAM_SWITCH = "beam_switch"
    RF_IMPAIRMENT = "rf_impairment"
    TRAFFIC_BURST = "traffic_burst"


class KPIType(str, Enum):
    """KPI metric type"""
    THROUGHPUT = "throughput"
    LATENCY = "latency"
    BLER = "bler"
    RSRP = "rsrp"
    SINR = "sinr"
    HANDOVER_SUCCESS_RATE = "handover_success_rate"


# ===== Data Models =====

class NetworkConfig(BaseModel):
    """Network configuration"""
    type: NetworkType = Field(description="Network type (5G NR/LTE/C-V2X)")
    band: str = Field(description="Frequency band (e.g., 'n78', 'B7')")
    bandwidth_mhz: float = Field(description="Channel bandwidth in MHz")
    duplex_mode: Literal["TDD", "FDD"] = Field(description="Duplex mode")
    scs_khz: Optional[float] = Field(None, description="Subcarrier spacing in kHz (5G NR)")


class BaseStationConfig(BaseModel):
    """Base station configuration"""
    bs_id: str = Field(description="Base station ID")
    name: str = Field(description="Base station name")
    position: Dict[str, float] = Field(description="Position {lat, lon, alt}")
    tx_power_dbm: float = Field(description="Transmit power in dBm")
    antenna_height_m: float = Field(default=30.0, description="Antenna height in meters")
    antenna_config: str = Field(default="4T4R", description="Antenna configuration")
    azimuth_deg: float = Field(default=0.0, description="Antenna azimuth in degrees")
    tilt_deg: float = Field(default=0.0, description="Antenna tilt in degrees")


class Waypoint(BaseModel):
    """Route waypoint"""
    time_s: float = Field(description="Time in seconds from start")
    position: Dict[str, float] = Field(description="Position {lat, lon, alt}")
    velocity: Dict[str, float] = Field(description="Velocity {speed_kmh, heading_deg}")


class Route(BaseModel):
    """Vehicle route"""
    type: RouteType = Field(description="Route type")
    waypoints: List[Waypoint] = Field(description="List of waypoints")
    duration_s: float = Field(description="Total duration in seconds")
    total_distance_m: float = Field(description="Total distance in meters")
    description: Optional[str] = Field(None, description="Route description")


class ChannelSnapshot(BaseModel):
    """Channel environment snapshot at specific time for Digital Twins"""
    timestamp_s: float = Field(description="Snapshot trigger time relative to start (s)")
    duration_s: float = Field(description="Duration this channel state is maintained (s)")
    channel_type: Literal["3GPP", "Custom"] = Field(description="Channel data type source")
    standard_model: Optional[ChannelModel] = Field(None, description="Standard 3GPP channel model (e.g., CDL-C)")
    custom_matrix_config: Optional[Dict] = Field(None, description="Custom multi-path rays matrix or definitions")


class Environment(BaseModel):
    """Environment configuration"""
    type: EnvironmentType = Field(description="Environment type")
    channel_snapshots: List[ChannelSnapshot] = Field(default_factory=list, description="Sequence of channel snapshots over time")
    weather: WeatherCondition = Field(default=WeatherCondition.CLEAR)
    traffic_density: TrafficDensity = Field(default=TrafficDensity.MEDIUM)
    obstructions: Optional[List[Dict]] = Field(None, description="Buildings, trees, etc.")


class TrafficConfig(BaseModel):
    """Traffic configuration"""
    type: TrafficType = Field(description="Traffic type")
    direction: Literal["DL", "UL", "BOTH"] = Field(description="Traffic direction")
    data_rate_mbps: Optional[float] = Field(None, description="Target data rate in Mbps")
    packet_size_bytes: Optional[int] = Field(None, description="Packet size in bytes")
    inter_arrival_ms: Optional[float] = Field(None, description="Inter-arrival time in ms")


class ScenarioEvent(BaseModel):
    """Base scenario event"""
    event_type: EventType = Field(description="Event type")
    trigger_time_s: float = Field(description="Trigger time in seconds")
    description: Optional[str] = Field(None, description="Event description")


class HandoverEvent(ScenarioEvent):
    """Handover event"""
    event_type: EventType = Field(default=EventType.HANDOVER)
    source_cell_id: str = Field(description="Source cell ID")
    target_cell_id: str = Field(description="Target cell ID")
    handover_type: Literal["intra-freq", "inter-freq", "inter-rat"] = Field(
        description="Handover type"
    )


class BeamSwitchEvent(ScenarioEvent):
    """Beam switch event"""
    event_type: EventType = Field(default=EventType.BEAM_SWITCH)
    source_beam_id: int = Field(description="Source beam ID")
    target_beam_id: int = Field(description="Target beam ID")
    reason: str = Field(description="Switch reason (RSRP low, load balancing, etc.)")


class RFImpairmentEvent(ScenarioEvent):
    """RF impairment event"""
    event_type: EventType = Field(default=EventType.RF_IMPAIRMENT)
    impairment_type: Literal["signal_loss", "interference", "fading"] = Field(
        description="Impairment type"
    )
    duration_s: float = Field(description="Duration in seconds")
    severity_db: float = Field(description="Severity in dB (e.g., -10 to -30)")


class TrafficBurstEvent(ScenarioEvent):
    """Traffic burst event"""
    event_type: EventType = Field(default=EventType.TRAFFIC_BURST)
    traffic_type: TrafficType = Field(description="Traffic type")
    data_volume_mb: float = Field(description="Data volume in MB")
    duration_s: float = Field(description="Duration in seconds")


class KPIDefinition(BaseModel):
    """KPI definition with target"""
    kpi_type: KPIType = Field(description="KPI type")
    target_value: float = Field(description="Target value")
    unit: str = Field(description="Unit (Mbps, ms, %, dBm)")
    percentile: Optional[float] = Field(None, description="Percentile (50, 95, etc.)")
    threshold_min: Optional[float] = Field(None, description="Minimum threshold")
    threshold_max: Optional[float] = Field(None, description="Maximum threshold")


# ===== Step Configuration Models =====

class ChamberInitConfig(BaseModel):
    """Chamber initialization step configuration"""
    chamber_id: Optional[str] = Field(None, description="Chamber ID")
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds")
    verify_connections: Optional[bool] = Field(None, description="Verify connections")
    calibrate_position_table: Optional[bool] = Field(None, description="Calibrate position table")


class NetworkConfigStep(BaseModel):
    """Network configuration step"""
    frequency_mhz: Optional[float] = Field(None, description="Frequency in MHz")
    bandwidth_mhz: Optional[float] = Field(None, description="Bandwidth in MHz")
    technology: Optional[str] = Field(None, description="Technology (5G NR, LTE, etc.)")
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds")
    verify_signal: Optional[bool] = Field(None, description="Verify signal")


class BaseStationSetupConfig(BaseModel):
    """Base station setup step configuration"""
    channel_model: Optional[str] = Field(None, description="Channel model")
    num_base_stations: Optional[int] = Field(None, description="Number of base stations")
    bs_positions: Optional[List[Dict]] = Field(None, description="Base station positions")
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds")
    verify_coverage: Optional[bool] = Field(None, description="Verify coverage")


class OTAMapperConfig(BaseModel):
    """OTA mapper step configuration"""
    route_file: Optional[str] = Field(None, description="Route file path")
    route_type: Optional[str] = Field(None, description="Route type")
    update_rate_hz: Optional[float] = Field(None, description="Update rate in Hz")
    enable_handover: Optional[bool] = Field(None, description="Enable handover")
    position_tolerance_m: Optional[float] = Field(None, description="Position tolerance in meters")
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds")


class RouteExecutionConfig(BaseModel):
    """Route execution step configuration"""
    route_duration_s: Optional[float] = Field(None, description="Route duration in seconds")
    total_distance_m: Optional[float] = Field(None, description="Total distance in meters")
    environment_type: Optional[str] = Field(None, description="Environment type")
    monitor_kpis: Optional[bool] = Field(None, description="Monitor KPIs")
    log_interval_s: Optional[float] = Field(None, description="Log interval in seconds")
    auto_screenshot: Optional[bool] = Field(None, description="Auto screenshot")
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds")


class KPIValidationConfig(BaseModel):
    """KPI validation step configuration"""

    class KPIThresholds(BaseModel):
        """KPI threshold values"""
        min_throughput_mbps: Optional[float] = Field(None, description="Minimum throughput in Mbps")
        max_latency_ms: Optional[float] = Field(None, description="Maximum latency in ms")
        min_rsrp_dbm: Optional[float] = Field(None, description="Minimum RSRP in dBm")
        max_packet_loss_percent: Optional[float] = Field(None, description="Maximum packet loss percentage")

    kpi_thresholds: Optional[KPIThresholds] = Field(None, description="KPI threshold values")
    generate_plots: Optional[bool] = Field(None, description="Generate plots")
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds")


class ReportGenerationConfig(BaseModel):
    """Report generation step configuration"""
    report_format: Optional[str] = Field(None, description="Report format (PDF, HTML, etc.)")
    include_raw_data: Optional[bool] = Field(None, description="Include raw data")
    include_screenshots: Optional[bool] = Field(None, description="Include screenshots")
    include_recommendations: Optional[bool] = Field(None, description="Include recommendations")
    timeout_seconds: Optional[int] = Field(None, description="Timeout in seconds")


class StepConfiguration(BaseModel):
    """Test step configuration for scenario"""
    chamber_init: Optional[ChamberInitConfig] = Field(None, description="Chamber initialization config")
    network_config: Optional[NetworkConfigStep] = Field(None, description="Network configuration")
    base_station_setup: Optional[BaseStationSetupConfig] = Field(None, description="Base station setup")
    ota_mapper: Optional[OTAMapperConfig] = Field(None, description="OTA mapper configuration")
    route_execution: Optional[RouteExecutionConfig] = Field(None, description="Route execution")
    kpi_validation: Optional[KPIValidationConfig] = Field(None, description="KPI validation")
    report_generation: Optional[ReportGenerationConfig] = Field(None, description="Report generation")


# ===== Main Scenario Model =====

class RoadTestScenario(BaseModel):
    """Complete road test scenario"""
    id: str = Field(description="Scenario ID")
    name: str = Field(description="Scenario name")
    category: ScenarioCategory = Field(description="Scenario category")
    source: ScenarioSource = Field(description="Scenario source")
    tags: List[str] = Field(default_factory=list, description="Search tags")
    description: Optional[str] = Field(None, description="Detailed description")

    # Configuration
    network: NetworkConfig = Field(description="Network configuration")
    base_stations: List[BaseStationConfig] = Field(description="Base station configurations")
    route: Route = Field(description="Vehicle route")
    environment: Environment = Field(description="Environment configuration")
    traffic: TrafficConfig = Field(description="Traffic configuration")
    events: List[Union[HandoverEvent, BeamSwitchEvent, RFImpairmentEvent, TrafficBurstEvent]] = Field(
        default_factory=list, description="Scenario events"
    )
    kpi_definitions: List[KPIDefinition] = Field(description="KPI definitions")

    # Step configuration (optional pre-configured test steps)
    step_configuration: Optional[StepConfiguration] = Field(None, description="Pre-configured test step parameters")

    # Metadata
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    author: Optional[str] = Field(None, description="Author")
    version: str = Field(default="1.0", description="Scenario version")


class ScenarioCreate(BaseModel):
    """Create scenario request"""
    name: str = Field(description="Scenario name")
    category: ScenarioCategory = Field(description="Scenario category")
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None

    network: NetworkConfig
    base_stations: List[BaseStationConfig]
    route: Route
    environment: Environment
    traffic: TrafficConfig
    events: List[Union[HandoverEvent, BeamSwitchEvent, RFImpairmentEvent, TrafficBurstEvent]] = Field(
        default_factory=list
    )
    kpi_definitions: List[KPIDefinition]
    step_configuration: Optional[StepConfiguration] = None


class ScenarioUpdate(BaseModel):
    """Update scenario request"""
    name: Optional[str] = None
    category: Optional[ScenarioCategory] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None

    network: Optional[NetworkConfig] = None
    base_stations: Optional[List[BaseStationConfig]] = None
    route: Optional[Route] = None
    environment: Optional[Environment] = None
    traffic: Optional[TrafficConfig] = None
    events: Optional[List[Union[HandoverEvent, BeamSwitchEvent, RFImpairmentEvent, TrafficBurstEvent]]] = None
    kpi_definitions: Optional[List[KPIDefinition]] = None
    step_configuration: Optional[StepConfiguration] = None


class ScenarioSummary(BaseModel):
    """Scenario summary for list view"""
    id: str
    name: str
    category: ScenarioCategory
    source: ScenarioSource
    tags: List[str]
    description: Optional[str]
    duration_s: float
    distance_m: float
    created_at: Optional[datetime]
    author: Optional[str]
    step_configuration: Optional[StepConfiguration] = None
    # Extended fields for editing
    network_type: Optional[str] = None
    band: Optional[str] = None
    bandwidth_mhz: Optional[float] = None
    channel_model: Optional[str] = None
    avg_speed_kmh: Optional[float] = None
