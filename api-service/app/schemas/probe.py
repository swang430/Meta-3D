"""Probe Pydantic schemas"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from ._datetime import UTCDateTime
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
    probe_number: int = Field(..., ge=1, le=128, description="探头编号")
    name: Optional[str] = Field(None, max_length=100)
    ring: int = Field(..., ge=1, le=5, description="环编号 1-5 (基于仰角: 1=顶层>60°, 2=上层30-60°, 3=中层±30°, 4=下层-60~-30°, 5=底层<-60°)")
    polarization: str = Field(..., pattern="^(V|H|V/H|RHCP|LHCP)$", description="极化: V | H | V/H | RHCP | LHCP")
    position: ProbePosition
    is_active: bool = Field(True, description="是否启用")
    chamber_config_id: Optional[UUID] = Field(None, description="所属暗室配置 ID")
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
    polarization: Optional[str] = Field(None, pattern="^(V|H|V/H|RHCP|LHCP)$")
    position: Optional[ProbePosition] = None
    is_active: Optional[bool] = None
    is_connected: Optional[bool] = None
    status: Optional[str] = Field(
        None,
        pattern="^(idle|active|error|calibrating)$"
    )
    hardware_id: Optional[str] = Field(None, max_length=100)
    channel_port: Optional[int] = None
    chamber_config_id: Optional[UUID] = Field(None, description="所属暗室配置 ID")
    last_calibration_date: Optional[UTCDateTime] = None
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
    """Request to replace probes for a SINGLE chamber (scoped)."""
    probes: List[ProbeCreateRequest] = Field(..., max_length=128)
    # **必填**: 批量替换只作用于单个暗室, 拒绝全局替换 (防一次清空所有暗室的探头)。
    # 字段设为 required → OpenAPI/生成客户端都标必填, 缺失时 422 (而非到 handler 才 400)。
    chamber_config_id: UUID = Field(..., description="目标暗室配置 ID (必填; 批量替换按此暗室作用域)")


# ==================== Response Schemas ====================

class ProbeResponse(BaseModel):
    """Probe response"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_serialization_defaults_required=True,
    )

    id: UUID
    probe_number: int
    name: Optional[str]
    ring: int
    polarization: str
    position: ProbePosition
    is_active: bool
    is_connected: bool
    status: str
    chamber_config_id: Optional[UUID] = None
    hardware_id: Optional[str]
    channel_port: Optional[int]
    last_calibration_date: Optional[UTCDateTime]
    calibration_status: str
    calibration_data: Optional[Dict[str, Any]]
    frequency_range_mhz: Optional[Dict[str, float]]
    max_power_dbm: Optional[float]
    gain_db: Optional[float]
    notes: Optional[str]
    created_at: UTCDateTime
    updated_at: Optional[UTCDateTime]
    created_by: Optional[str]

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


# ⚠ P2-41（2026-08-24）已删除 ProbeConfigurationCreate/Update/Response/ListResponse
# 四个 schema 类 —— 全仓零引用的死类型，随 `probe_configurations` 表一并清理
# （Schema Review R3，docs/plans/2026-08-24-system-schema-review.md）。


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
