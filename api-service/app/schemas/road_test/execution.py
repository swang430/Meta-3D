"""
Test Execution Schemas

Data models for virtual road test execution
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Any
from .._datetime import UTCDateTime
from enum import Enum


class TestMode(str, Enum):
    """Test execution mode"""
    DIGITAL_TWIN = "digital_twin"
    CONDUCTED = "conducted"
    OTA = "ota"


class ExecutionStatus(str, Enum):
    """Execution status"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    CONFIGURED = "configured"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ControlAction(str, Enum):
    """Execution control action"""
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    COMPLETE = "complete"


# ===== Test Capabilities =====

class TestCapabilities(BaseModel):
    """Test executor capabilities"""
    mode: TestMode = Field(description="Test mode")
    max_bandwidth_mhz: float = Field(description="Maximum bandwidth")
    max_mimo_order: str = Field(description="Maximum MIMO order (e.g., '8x8')")
    supports_fading: bool = Field(description="Supports fading channel")
    supports_3gpp_models: bool = Field(description="Supports 3GPP channel models")
    supports_real_time: bool = Field(description="Supports real-time execution")
    acceleration_factor: Optional[float] = Field(None, description="Time acceleration factor (digital twin)")
    supported_scenarios: List[str] = Field(description="Supported scenario categories")


# ===== Test Status =====

class TestStatus(BaseModel):
    """Test execution status"""
    execution_id: str = Field(description="Execution ID")
    status: ExecutionStatus = Field(description="Current status")
    progress_percent: float = Field(description="Progress percentage (0-100)")

    # Timing
    elapsed_time_s: float = Field(description="Elapsed time in seconds")
    remaining_time_s: Optional[float] = Field(None, description="Estimated remaining time")

    # Resource status
    cpu_usage_percent: Optional[float] = Field(None, description="CPU usage")
    memory_usage_mb: Optional[float] = Field(None, description="Memory usage in MB")
    gpu_usage_percent: Optional[float] = Field(None, description="GPU usage (digital twin)")

    # Current state
    current_waypoint_index: Optional[int] = Field(None, description="Current waypoint index")
    current_time_s: Optional[float] = Field(None, description="Current simulation/test time")
    current_position: Optional[Dict[str, float]] = Field(None, description="Current vehicle position")

    conducted_stop_pending: bool = Field(description="原传导执行仍有设备端口待复核停止")

    # Hardware status (conducted/OTA)
    instruments_connected: Optional[bool] = Field(None, description="Instruments connected")
    instrument_status: Optional[Dict[str, str]] = Field(None, description="Instrument status")

    # Error information
    last_error: Optional[str] = Field(None, description="Last error message")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")


# ===== Test Metrics =====

class KPIMetrics(BaseModel):
    """KPI metrics at a specific time"""
    time_s: float = Field(description="Time in seconds")

    # RF metrics
    rsrp_dbm: Optional[float] = Field(None, description="RSRP in dBm")
    rsrq_db: Optional[float] = Field(None, description="RSRQ in dB")
    sinr_db: Optional[float] = Field(None, description="SINR in dB")
    rssi_dbm: Optional[float] = Field(None, description="RSSI in dBm")

    # Performance metrics
    dl_throughput_mbps: Optional[float] = Field(None, description="DL throughput in Mbps")
    ul_throughput_mbps: Optional[float] = Field(None, description="UL throughput in Mbps")
    latency_ms: Optional[float] = Field(None, description="Latency in ms")
    bler_percent: Optional[float] = Field(None, description="BLER percentage")

    # PHY layer metrics
    cqi: Optional[int] = Field(None, description="Channel Quality Indicator")
    ri: Optional[int] = Field(None, description="Rank Indicator")
    pmi: Optional[int] = Field(None, description="Precoding Matrix Indicator")
    mcs: Optional[int] = Field(None, description="Modulation and Coding Scheme")

    # Position
    position: Optional[Dict[str, float]] = Field(None, description="Vehicle position")
    velocity_kmh: Optional[float] = Field(None, description="Vehicle velocity")

    # Events
    event_occurred: Optional[str] = Field(None, description="Event occurred (handover, etc.)")


class RunnerObservation(BaseModel):
    """单次回读。三种时间各自记录，缺项保持空。"""
    metric: Literal["connection_state", "dl_throughput_mbps", "ul_throughput_mbps", "playback_position_s"]
    value: str | float | bool | None
    unit: str
    source: str
    throughput_scope: Optional[Literal["pcell"]] = Field(None, description="仅在指定小区吞吐量回读有效时记录。")
    provenance: Literal["server_measured", "simulated", "unverified"]
    sampled_at: UTCDateTime
    time_s: float = Field(ge=0, allow_inf_nan=False)
    source_frame_time_s: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    device_playback_time_s: Optional[float] = Field(None, ge=0, allow_inf_nan=False)


class TestMetrics(BaseModel):
    """Complete test metrics"""
    execution_id: str = Field(description="Execution ID")

    observations: List[RunnerObservation] = Field(default_factory=list)

    # Time series data
    kpi_samples: List[KPIMetrics] = Field(description="KPI samples over time")

    # Summary statistics
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics (mean, min, max, std, percentiles)"
    )

    # Event log
    events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Event log (handovers, beam switches, etc.)"
    )

    # KPI targets achievement
    kpi_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="KPI target achievement results"
    )

    provenance: Optional[str] = Field(None, description="kpi_samples 的来源。运行器逐项回读另见 observations。")


# ===== Test Execution =====

class TestExecution(BaseModel):
    """Test execution instance"""
    execution_id: str = Field(description="Unique execution ID")
    mode: TestMode = Field(description="Test mode")
    status: ExecutionStatus = Field(description="Current status")

    # Configuration
    scenario_id: str = Field(description="Scenario ID")
    topology_id: Optional[str] = Field(None, description="Topology ID (conducted mode)")

    # Executor configuration
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Executor-specific configuration"
    )

    # Results
    start_time: Optional[UTCDateTime] = Field(None, description="Start time")
    end_time: Optional[UTCDateTime] = Field(None, description="End time")
    duration_s: Optional[float] = Field(None, description="Duration in seconds")

    # Metadata
    created_by: Optional[str] = Field(None, description="Created by user")
    notes: Optional[str] = Field(None, description="Execution notes")
    # NEW: Execution logs
    logs: List[Dict[str, Any]] = Field(default_factory=list, description="Execution logs")


class ExecutionCreate(BaseModel):
    """Create execution request"""
    mode: TestMode = Field(description="Test mode")
    scenario_id: str = Field(description="Scenario ID")
    topology_id: Optional[str] = Field(None, description="Topology ID (conducted mode only)")

    # Mode-specific configuration
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mode-specific configuration"
    )

    notes: Optional[str] = Field(None, description="Execution notes")


class ExecutionControl(BaseModel):
    """Execution control request"""
    action: ControlAction = Field(description="Control action")
    parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="Action-specific parameters"
    )


class ExecutionSummary(BaseModel):
    """Execution summary for list view"""
    conducted: Optional[Dict[str, Any]] = None
    ota: Optional[Dict[str, Any]] = None
    execution_id: str
    mode: TestMode
    status: ExecutionStatus
    scenario_name: str
    start_time: Optional[UTCDateTime]
    duration_s: Optional[float]
    progress_percent: float
    created_by: Optional[str]


# ===== Execution Report =====

class PhaseResult(BaseModel):
    """Result for a single test phase"""
    name: str = Field(description="Phase name")
    status: str = Field(description="completed | failed | skipped")
    duration_s: float = Field(description="Phase duration in seconds")
    start_time: UTCDateTime = Field(description="Phase start time")
    end_time: UTCDateTime = Field(description="Phase end time")
    notes: Optional[str] = Field(None, description="Phase notes")


class KPISummary(BaseModel):
    """Summary statistics for a KPI"""
    name: str = Field(description="KPI name")
    unit: str = Field(description="Unit of measurement")
    mean: float = Field(description="Mean value")
    min: float = Field(description="Minimum value")
    max: float = Field(description="Maximum value")
    std: Optional[float] = Field(None, description="Standard deviation")
    target: Optional[float] = Field(None, description="Target value")
    passed: Optional[bool] = Field(None, description="Whether target was met")


class ScenarioInfo(BaseModel):
    """Scenario information for report"""
    id: str = Field(description="Scenario ID")
    name: str = Field(description="Scenario name")
    category: str = Field(description="Scenario category")
    description: Optional[str] = Field(None, description="Scenario description")
    tags: List[str] = Field(default_factory=list, description="Scenario tags")


class NetworkInfo(BaseModel):
    """Network configuration info for report"""
    type: str = Field(description="Network type (5G NR, LTE, etc.)")
    band: str = Field(description="Frequency band")
    bandwidth_mhz: float = Field(description="Bandwidth in MHz")
    duplex_mode: str = Field(description="TDD or FDD")
    scs_khz: Optional[int] = Field(None, description="Subcarrier spacing")


class EnvironmentInfo(BaseModel):
    """Environment info for report"""
    type: str = Field(description="Environment type")
    channel_model: str = Field(description="Channel model")
    weather: str = Field(description="Weather condition")
    traffic_density: str = Field(description="Traffic density")


class RouteInfo(BaseModel):
    """Route info for report"""
    duration_s: float = Field(description="Route duration in seconds")
    distance_m: float = Field(description="Total distance in meters")
    waypoint_count: int = Field(description="Number of waypoints")
    avg_speed_kmh: Optional[float] = Field(None, description="Average speed")


class BaseStationInfo(BaseModel):
    """Base station info for report"""
    bs_id: str = Field(description="Base station ID")
    name: str = Field(description="Base station name")
    tx_power_dbm: float = Field(description="TX power in dBm")
    antenna_config: str = Field(description="Antenna configuration")
    antenna_height_m: float = Field(description="Antenna height")


class StepConfigInfo(BaseModel):
    """Step configuration info for report"""
    step_name: str = Field(description="Step name")
    enabled: bool = Field(True, description="Whether step is enabled")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Step parameters")


# ===== Metrics Submission =====

class TimeSeriesPoint(BaseModel):
    """Single data point in time series (for frontend submission)"""
    time_s: float = Field(description="Time in seconds")
    position: Optional[Dict[str, float]] = Field(None, description="Position {lat, lon, alt}")

    # RF metrics
    rsrp_dbm: Optional[float] = Field(None, description="RSRP in dBm")
    rsrq_db: Optional[float] = Field(None, description="RSRQ in dB")
    sinr_db: Optional[float] = Field(None, description="SINR in dB")

    # Performance metrics
    dl_throughput_mbps: Optional[float] = Field(None, description="DL throughput in Mbps")
    ul_throughput_mbps: Optional[float] = Field(None, description="UL throughput in Mbps")
    latency_ms: Optional[float] = Field(None, description="Latency in ms")

    # Event marker
    event: Optional[str] = Field(None, description="Event type if occurred")


class ExecutionMetricsSubmit(BaseModel):
    """Request to submit execution metrics"""
    execution_id: str = Field(description="Execution ID")
    time_series: List[TimeSeriesPoint] = Field(description="Time series data points")
    phases: List[PhaseResult] = Field(description="Phase execution results")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Event log")
    kpi_summary: List[KPISummary] = Field(description="KPI summary statistics")


# ===== Detailed Configuration for Report =====

class NetworkConfigDetail(BaseModel):
    """Detailed network configuration for report"""
    authentication: Optional[Dict[str, Any]] = Field(None, description="Auth config")
    qos: Optional[Dict[str, Any]] = Field(None, description="QoS config")
    pdu_session: Optional[Dict[str, Any]] = Field(None, description="PDU session config")
    applications: Optional[List[str]] = Field(None, description="Application test types")


class BaseStationConfigDetail(BaseModel):
    """Detailed base station configuration for report"""
    rf: Optional[Dict[str, Any]] = Field(None, description="RF parameters")
    antenna: Optional[Dict[str, Any]] = Field(None, description="Antenna config")
    beamforming: Optional[Dict[str, Any]] = Field(None, description="Beamforming config")
    handover: Optional[Dict[str, Any]] = Field(None, description="Handover config")


class DigitalTwinConfig(BaseModel):
    """Digital twin environment configuration for report"""
    channel_model: Optional[Dict[str, Any]] = Field(None, description="Channel model config")
    ray_tracing: Optional[Dict[str, Any]] = Field(None, description="Ray tracing config")
    weather: Optional[Dict[str, Any]] = Field(None, description="Weather effects")
    interference: Optional[Dict[str, Any]] = Field(None, description="Interference config")


class CustomConfigHighlight(BaseModel):
    """Highlight for custom/special configuration"""
    category: str = Field(description="Config category")
    label: str = Field(description="Display label")
    value: Any = Field(description="Config value")
    description: Optional[str] = Field(None, description="Description")


class TrajectoryPoint(BaseModel):
    """Single point in trajectory"""
    lat: float = Field(description="Latitude")
    lon: float = Field(description="Longitude")
    alt: Optional[float] = Field(None, description="Altitude")
    time_s: Optional[float] = Field(None, description="Time in seconds")


class TwinPoint(BaseModel):
    source_frame_time_s: float
    dl_throughput_mbps: float
    provenance: Literal["simulated"]


class TwinTimeline(BaseModel):
    points: List[TwinPoint]
    provenance: Literal["simulated"]
    formal_kpi: Literal[False]


class TwinDifference(BaseModel):
    source_frame_time_s: float
    delta_dl_throughput_mbps: float


class TwinComparison(BaseModel):
    comparable: bool
    reason: str
    differences: List[TwinDifference]
    formal_kpi: Literal[False]


class ExecutionReport(BaseModel):
    """Complete execution report"""
    simulation_input: Optional[dict] = None
    simulation_timeline: Optional[TwinTimeline] = None
    conducted_setup: Optional[Dict[str, Any]] = None
    ota_setup: Optional[Dict[str, Any]] = None
    observations: List[RunnerObservation] = Field(default_factory=list)
    execution_id: str = Field(description="Execution ID")
    scenario_name: str = Field(description="Scenario name")
    mode: TestMode = Field(description="Test mode")
    status: ExecutionStatus = Field(description="Final status")

    # Scenario details
    scenario: Optional[ScenarioInfo] = Field(None, description="Scenario information")
    network: Optional[NetworkInfo] = Field(None, description="Network configuration")
    environment: Optional[EnvironmentInfo] = Field(None, description="Environment info")
    route: Optional[RouteInfo] = Field(None, description="Route info")
    base_stations: List[BaseStationInfo] = Field(default_factory=list, description="Base stations")

    # Step configuration
    step_configs: List[StepConfigInfo] = Field(default_factory=list, description="Step configurations")

    # Timing
    start_time: Optional[UTCDateTime] = Field(None, description="Start time")
    end_time: Optional[UTCDateTime] = Field(None, description="End time")
    duration_s: Optional[float] = Field(None, description="Total duration")

    # Phase results
    phases: List[PhaseResult] = Field(default_factory=list, description="Phase results")

    # KPI summary
    kpi_summary: List[KPISummary] = Field(default_factory=list, description="KPI summary")

    # Overall result
    overall_result: str = Field(
        description="passed | failed | incomplete | undetermined —— "
                    "incomplete=执行没跑完（还在跑/被停止）；"
                    "undetermined=跑完了但一条 KPI 都没有可信判决",
    )
    pass_rate: Optional[float] = Field(
        default=None,
        description="合格率；一条 KPI 都没有可信判决时为 None（不是 0）—— "
                    "0 会被读成「一条都没过」，而实际是「一条都没判」",
    )

    # Events
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Notable events")

    # NEW: Time series data for charts
    time_series: List[TimeSeriesPoint] = Field(default_factory=list, description="Time series data")

    # NEW: Trajectory for map
    trajectory: List[TrajectoryPoint] = Field(default_factory=list, description="Vehicle trajectory")

    # NEW: Detailed configurations
    network_config_detail: Optional[NetworkConfigDetail] = Field(None, description="Detailed network config")
    base_station_config_detail: Optional[BaseStationConfigDetail] = Field(None, description="Detailed BS config")
    digital_twin_config: Optional[DigitalTwinConfig] = Field(None, description="Digital twin config")

    # NEW: Custom config highlights
    custom_config_highlights: List[CustomConfigHighlight] = Field(
        default_factory=list, description="Custom/special configuration highlights"
    )

    # Metadata
    generated_at: UTCDateTime = Field(description="Report generation time")
    notes: Optional[str] = Field(None, description="Execution notes")
    # NEW: Logs
    logs: List[Dict[str, Any]] = Field(default_factory=list, description="Execution process logs")


# ===== Real-time Streaming =====

class MetricsStreamMessage(BaseModel):
    """Real-time metrics stream message (WebSocket)"""
    execution_id: str = Field(description="Execution ID")
    timestamp: UTCDateTime = Field(description="Message timestamp")
    message_type: Literal["metrics", "event", "status", "alert"] = Field(
        description="Message type"
    )
    data: Dict[str, Any] = Field(description="Message payload")


class StreamSubscription(BaseModel):
    """Stream subscription request"""
    channels: List[str] = Field(
        default=["metrics", "events", "logs"],
        description="Channels to subscribe"
    )
    sample_rate_hz: Optional[float] = Field(
        None,
        description="Desired sample rate (will be limited by executor)"
    )


class ModeAvailability(BaseModel):
    available: bool
    max_bandwidth_mhz: Optional[float]
    max_mimo_order: str


class DigitalTwinAvailability(ModeAvailability):
    acceleration_factor: float


class ConductedAvailability(ModeAvailability):
    simulated_available: bool
    real_available: bool = Field(description="当前驱动组合支持真机分支；具体场景须通过准备和启动复核。")
    requires_preparation: bool
    requires_topology: bool


class OtaAvailability(ModeAvailability):
    simulated_available: bool
    real_available: bool
    requires_preparation: bool
    requires_mpac: bool


class RoadTestAvailability(BaseModel):
    digital_twin: DigitalTwinAvailability
    conducted: ConductedAvailability
    ota: OtaAvailability



class ExecutionControlReceipt(BaseModel):
    status: Literal["success"]
    execution_id: str
    action: str


class ExecutionArchiveReceipt(BaseModel):
    id: str
    title: str
    status: str
