"""Hardware Synchronization Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ==================== Enums ====================

class SyncState(str, Enum):
    """System sync state"""
    IDLE = "idle"
    CONFIGURING = "configuring"
    SYNCHRONIZED = "synchronized"
    RUNNING = "running"
    ERROR = "error"


class ClockSource(str, Enum):
    """Clock source type"""
    INTERNAL = "internal"
    EXTERNAL_10MHZ = "external_10mhz"
    EXTERNAL_100MHZ = "external_100mhz"
    PXI_BACKPLANE = "pxi_backplane"
    GPS = "gps"


class ClockSyncStatus(str, Enum):
    """Clock synchronization status"""
    UNLOCKED = "unlocked"
    LOCKING = "locking"
    LOCKED = "locked"
    HOLDOVER = "holdover"
    ERROR = "error"


class TriggerSource(str, Enum):
    """Trigger source"""
    IMMEDIATE = "immediate"
    EXTERNAL = "external"
    SOFTWARE = "software"
    TIMER = "timer"
    BUS = "bus"


class TriggerEdge(str, Enum):
    """Trigger edge"""
    RISING = "rising"
    FALLING = "falling"
    EITHER = "either"


class TriggerMode(str, Enum):
    """Trigger mode"""
    SINGLE = "single"
    CONTINUOUS = "continuous"
    GATED = "gated"


# ==================== Clock Schemas ====================

class ClockConfig(BaseModel):
    """Clock configuration request"""
    source: ClockSource = Field(ClockSource.EXTERNAL_10MHZ, description="Clock source")
    reference_frequency_hz: float = Field(10_000_000, description="Reference frequency in Hz")
    output_enabled: bool = Field(True, description="Enable clock output")


class ClockStatusResponse(BaseModel):
    """Clock status response"""
    sync_status: ClockSyncStatus
    source: ClockSource
    frequency_offset_ppb: float = Field(0.0, description="Frequency offset in ppb")
    phase_offset_ps: float = Field(0.0, description="Phase offset in ps")
    lock_time_seconds: float = Field(0.0, description="Time since lock acquired")
    is_locked: bool = Field(False, description="Whether clock is locked")


class InstrumentClockStatus(BaseModel):
    """Individual instrument clock status"""
    instrument_id: str
    instrument_name: str
    status: ClockStatusResponse
    last_updated: datetime


# ==================== Trigger Schemas ====================

class TriggerConfig(BaseModel):
    """Trigger configuration"""
    source: TriggerSource = Field(TriggerSource.BUS, description="Trigger source")
    edge: TriggerEdge = Field(TriggerEdge.RISING, description="Trigger edge")
    mode: TriggerMode = Field(TriggerMode.SINGLE, description="Trigger mode")
    delay_ns: float = Field(0.0, description="Trigger delay in nanoseconds")
    level_v: float = Field(1.5, description="Trigger level in volts")
    holdoff_ns: float = Field(0.0, description="Trigger holdoff in nanoseconds")


class TriggerSequenceStep(BaseModel):
    """Single step in trigger sequence"""
    order: int = Field(..., ge=0, description="Step order")
    action: str = Field(..., description="Action: arm | trigger | wait | configure")
    instrument_id: str = Field(..., description="Target instrument")
    delay_after_us: float = Field(0.0, ge=0, description="Delay after step in microseconds")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Action-specific parameters")


class TriggerSequenceCreate(BaseModel):
    """Create trigger sequence request"""
    name: str = Field(..., description="Sequence name")
    description: Optional[str] = None
    steps: List[TriggerSequenceStep] = Field(..., min_length=1)
    repeat_count: int = Field(1, ge=1, description="Number of times to repeat sequence")


class TriggerSequenceResponse(BaseModel):
    """Trigger sequence response"""
    id: str
    name: str
    description: Optional[str]
    steps: List[TriggerSequenceStep]
    repeat_count: int
    status: str = Field("idle", description="Sequence status: idle | armed | running | completed")
    created_at: datetime


# ==================== System Sync Schemas ====================

class SyncMetrics(BaseModel):
    """Synchronization performance metrics"""
    latency_avg_ms: float = Field(0.0, description="Average latency in ms")
    latency_p50_ms: float = Field(0.0, description="P50 latency in ms")
    latency_p95_ms: float = Field(0.0, description="P95 latency in ms")
    latency_p99_ms: float = Field(0.0, description="P99 latency in ms")
    latency_max_ms: float = Field(0.0, description="Max latency in ms")
    jitter_ms: float = Field(0.0, description="Jitter in ms")
    messages_per_second: float = Field(0.0, description="Message throughput")
    dropped_count: int = Field(0, description="Number of dropped messages")
    error_count: int = Field(0, description="Number of errors")


class InstrumentSyncState(BaseModel):
    """Individual instrument sync state"""
    instrument_id: str
    instrument_name: str
    clock_locked: bool
    trigger_armed: bool
    last_trigger_time: Optional[datetime]
    status: str


class SystemSyncStatus(BaseModel):
    """Complete system synchronization status"""
    state: SyncState
    is_synchronized: bool = Field(False, description="Whether system is fully synchronized")

    # L0 Clock status
    clock_locked: bool = Field(False, description="All clocks locked to reference")
    clock_source: ClockSource = Field(ClockSource.INTERNAL)
    clock_coherence_verified: bool = Field(False, description="Clock coherence verified")

    # L1 Trigger status
    trigger_armed: bool = Field(False, description="Trigger system armed")
    active_sequence: Optional[str] = Field(None, description="Active trigger sequence name")

    # L2 Parameter status
    parameter_sync_active: bool = Field(False, description="Parameter synchronization active")
    metrics: SyncMetrics = Field(default_factory=SyncMetrics)

    # Instrument states
    instruments: List[InstrumentSyncState] = Field(default_factory=list)

    # Timestamps
    last_sync_check: Optional[datetime] = None
    uptime_seconds: float = Field(0.0)


class SyncInitRequest(BaseModel):
    """Initialize synchronization request"""
    clock_source: ClockSource = Field(ClockSource.EXTERNAL_10MHZ)
    auto_configure_triggers: bool = Field(True, description="Auto-configure default triggers")
    verify_coherence: bool = Field(True, description="Verify clock coherence after init")
    timeout_seconds: float = Field(30.0, description="Initialization timeout")


class SyncInitResponse(BaseModel):
    """Synchronization initialization response"""
    success: bool
    state: SyncState
    message: str
    clock_locked: bool
    instruments_configured: int
    elapsed_seconds: float
