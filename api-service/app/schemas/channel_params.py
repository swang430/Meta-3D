"""Channel Parameter Schemas for L2 Synchronization

Defines data structures for real-time channel parameters
exchanged between ray tracing engine and channel emulator.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum
import numpy as np


class ChannelModel(str, Enum):
    """Supported channel models"""
    CDL_A = "CDL-A"
    CDL_B = "CDL-B"
    CDL_C = "CDL-C"
    CDL_D = "CDL-D"
    CDL_E = "CDL-E"
    TDL_A = "TDL-A"
    TDL_B = "TDL-B"
    TDL_C = "TDL-C"
    TDL_D = "TDL-D"
    TDL_E = "TDL-E"
    SCME_UMA = "SCME-UMa"
    SCME_UMI = "SCME-UMi"
    CUSTOM = "custom"


class SyncTimestamp(BaseModel):
    """High-precision timestamp for synchronization"""
    sequence_id: int = Field(..., description="Monotonic sequence number")
    timestamp_ns: int = Field(..., description="Nanosecond timestamp")
    source: str = Field("api", description="Timestamp source")


class LargeScaleParams(BaseModel):
    """
    Large-scale channel parameters (L2 sync - small data)

    Updated at ~100Hz for dynamic scenarios.
    """
    timestamp: SyncTimestamp

    # Scene identification
    scenario_id: Optional[UUID] = None
    position_index: int = Field(0, description="Position index in trajectory")

    # Propagation parameters
    n_paths: int = Field(1, ge=1, description="Number of multipath components")
    path_loss_db: List[float] = Field(default_factory=list, description="Path loss per path (dB)")

    # Angle information
    aod_azimuth: List[float] = Field(default_factory=list, description="AoD azimuth per path (degrees)")
    aod_elevation: List[float] = Field(default_factory=list, description="AoD elevation per path (degrees)")
    aoa_azimuth: List[float] = Field(default_factory=list, description="AoA azimuth per path (degrees)")
    aoa_elevation: List[float] = Field(default_factory=list, description="AoA elevation per path (degrees)")

    # Delay and Doppler
    delay_ns: List[float] = Field(default_factory=list, description="Delay per path (ns)")
    doppler_hz: List[float] = Field(default_factory=list, description="Doppler shift per path (Hz)")

    # Polarization
    xpr_db: List[float] = Field(default_factory=list, description="Cross-polarization ratio per path (dB)")

    # Cluster information (optional)
    cluster_powers: Optional[List[float]] = None
    cluster_delays: Optional[List[float]] = None


class ChannelMatrixMetadata(BaseModel):
    """Metadata for channel matrix (actual matrix in SharedMemory)"""
    timestamp: SyncTimestamp
    n_rx: int = Field(..., ge=1, description="Number of RX antennas")
    n_tx: int = Field(..., ge=1, description="Number of TX antennas")
    n_subcarriers: int = Field(..., ge=1, description="Number of subcarriers")
    n_ofdm_symbols: int = Field(..., ge=1, description="Number of OFDM symbols")
    subcarrier_spacing_khz: float = Field(15.0, description="Subcarrier spacing (kHz)")
    shm_name: str = Field(..., description="Shared memory segment name")
    shm_offset: int = Field(0, description="Offset in shared memory")
    shm_size: int = Field(..., description="Size in bytes")
    dtype: str = Field("complex64", description="NumPy dtype string")


class ParameterSyncConfig(BaseModel):
    """Configuration for parameter synchronization"""
    enabled: bool = Field(True, description="Enable parameter sync")
    update_rate_hz: float = Field(100.0, ge=1, le=1000, description="Target update rate")
    channel_model: ChannelModel = Field(ChannelModel.CDL_C)
    use_shared_memory: bool = Field(True, description="Use shared memory for large data")
    zmq_endpoint: str = Field("ipc:///tmp/mimo_large_scale_params", description="ZeroMQ endpoint")
    buffer_size: int = Field(100, ge=10, le=1000, description="Ring buffer size")


class ParameterSyncStatus(BaseModel):
    """Status of parameter synchronization subsystem"""
    is_running: bool = Field(False)
    is_connected: bool = Field(False)
    last_update_time: Optional[datetime] = None
    update_count: int = Field(0)
    error_count: int = Field(0)
    dropped_count: int = Field(0)

    # Performance metrics
    latency_avg_ms: float = Field(0.0)
    latency_max_ms: float = Field(0.0)
    update_rate_actual_hz: float = Field(0.0)
    buffer_fill_percent: float = Field(0.0)

    # Current parameters summary
    current_n_paths: int = Field(0)
    current_sequence_id: int = Field(0)


class ParameterPublishRequest(BaseModel):
    """Request to publish channel parameters"""
    params: LargeScaleParams
    priority: int = Field(5, ge=1, le=10, description="Publishing priority")


class ParameterHistoryRequest(BaseModel):
    """Request for parameter history"""
    start_sequence_id: Optional[int] = None
    end_sequence_id: Optional[int] = None
    count: int = Field(10, ge=1, le=100, description="Number of records")


class ParameterHistoryResponse(BaseModel):
    """Response with parameter history"""
    items: List[LargeScaleParams]
    total_available: int
    oldest_sequence_id: int
    newest_sequence_id: int
