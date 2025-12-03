"""
Test Execution Schemas

Data models for virtual road test execution
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime
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


class TestMetrics(BaseModel):
    """Complete test metrics"""
    execution_id: str = Field(description="Execution ID")

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
    start_time: Optional[datetime] = Field(None, description="Start time")
    end_time: Optional[datetime] = Field(None, description="End time")
    duration_s: Optional[float] = Field(None, description="Duration in seconds")

    # Metadata
    created_by: Optional[str] = Field(None, description="Created by user")
    notes: Optional[str] = Field(None, description="Execution notes")


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
    execution_id: str
    mode: TestMode
    status: ExecutionStatus
    scenario_name: str
    start_time: Optional[datetime]
    duration_s: Optional[float]
    progress_percent: float
    created_by: Optional[str]


# ===== Real-time Streaming =====

class MetricsStreamMessage(BaseModel):
    """Real-time metrics stream message (WebSocket)"""
    execution_id: str = Field(description="Execution ID")
    timestamp: datetime = Field(description="Message timestamp")
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
