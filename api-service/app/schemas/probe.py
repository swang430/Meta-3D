"""Probe Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# ==================== Position ====================

class ProbePosition(BaseModel):
    """Probe 3D position"""
    azimuth: float = Field(..., ge=0, le=360, description="方位角（度）0-360")
    elevation: float = Field(..., ge=-90, le=90, description="仰角（度）-90-90")
    radius: float = Field(..., gt=0, description="半径（米）")


# ==================== Request Schemas ====================

class ProbeCreateRequest(BaseModel):
    """Request to create a new probe"""
    probe_number: int = Field(..., ge=1, le=32, description="探头编号 1-32")
    name: Optional[str] = Field(None, max_length=100)
    ring: int = Field(..., ge=1, le=5, description="环编号 1-5 (基于仰角: 1=顶层>60°, 2=上层30-60°, 3=中层±30°, 4=下层-60~-30°, 5=底层<-60°)")
    polarization: str = Field(..., pattern="^[VH]$", description="极化: V | H")
    position: ProbePosition
    is_active: bool = Field(True, description="是否启用")
    hardware_id: Optional[str] = Field(None, max_length=100)
    channel_port: Optional[int] = None
    frequency_range_mhz: Optional[Dict[str, float]] = Field(
        None,
        description="频率范围 {min, max}"
    )
    max_power_dbm: Optional[float] = None
    gain_db: Optional[float] = None
    notes: Optional[str] = None
    created_by: Optional[str] = Field(None, max_length=100)


class ProbeUpdateRequest(BaseModel):
    """Request to update a probe"""
    name: Optional[str] = Field(None, max_length=100)
    ring: Optional[int] = Field(None, ge=1, le=5, description="环编号 1-5 (基于仰角自动计算)")
    polarization: Optional[str] = Field(None, pattern="^[VH]$")
    position: Optional[ProbePosition] = None
    is_active: Optional[bool] = None
    is_connected: Optional[bool] = None
    status: Optional[str] = Field(
        None,
        pattern="^(idle|active|error|calibrating)$"
    )
    hardware_id: Optional[str] = Field(None, max_length=100)
    channel_port: Optional[int] = None
    last_calibration_date: Optional[datetime] = None
    calibration_status: Optional[str] = Field(
        None,
        pattern="^(valid|expired|invalid|unknown)$"
    )
    calibration_data: Optional[Dict[str, Any]] = None
    frequency_range_mhz: Optional[Dict[str, float]] = None
    max_power_dbm: Optional[float] = None
    gain_db: Optional[float] = None
    notes: Optional[str] = None


class BulkProbeRequest(BaseModel):
    """Request to replace all probes in bulk"""
    probes: List[ProbeCreateRequest] = Field(..., max_length=32)


# ==================== Response Schemas ====================

class ProbeResponse(BaseModel):
    """Probe response"""
    id: UUID
    probe_number: int
    name: Optional[str]
    ring: int
    polarization: str
    position: ProbePosition
    is_active: bool
    is_connected: bool
    status: str
    hardware_id: Optional[str]
    channel_port: Optional[int]
    last_calibration_date: Optional[datetime]
    calibration_status: str
    calibration_data: Optional[Dict[str, Any]]
    frequency_range_mhz: Optional[Dict[str, float]]
    max_power_dbm: Optional[float]
    gain_db: Optional[float]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: Optional[str]

    class Config:
        from_attributes = True


class ProbesListResponse(BaseModel):
    """List of probes response"""
    total: int
    probes: List[ProbeResponse]


class BulkProbeResponse(BaseModel):
    """Bulk probe operation response"""
    total: int
    created: int
    updated: int
    deleted: int
    probes: List[ProbeResponse]


# ==================== Configuration Schemas ====================

class ProbeConfigurationCreate(BaseModel):
    """Request to create a probe configuration"""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    version: str = Field("1.0", max_length=50)
    probe_data: List[ProbeResponse]
    created_by: str = Field(..., max_length=100)
    imported_from: Optional[str] = Field(None, max_length=255)


class ProbeConfigurationUpdate(BaseModel):
    """Request to update a probe configuration"""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=50)
    probe_data: Optional[List[ProbeResponse]] = None
    is_active: Optional[bool] = None


class ProbeConfigurationResponse(BaseModel):
    """Probe configuration response"""
    id: UUID
    name: str
    description: Optional[str]
    version: str
    probe_data: List[ProbeResponse]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: str
    imported_from: Optional[str]
    exported_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProbeConfigurationListResponse(BaseModel):
    """List of probe configurations response"""
    total: int
    configurations: List[ProbeConfigurationResponse]


# ==================== Statistics ====================

class ProbeStatistics(BaseModel):
    """Probe system statistics"""
    total_probes: int
    active_probes: int
    connected_probes: int
    calibrated_probes: int
    by_ring: Dict[int, int]  # {ring_number: count}
    by_polarization: Dict[str, int]  # {"V": count, "H": count}
    by_status: Dict[str, int]  # {"idle": count, "active": count, ...}
