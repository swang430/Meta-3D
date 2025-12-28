"""Topology Pydantic schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class TopologyType(str, Enum):
    """Topology type"""
    OTA = "ota"
    CONDUCTED = "conducted"
    HYBRID = "hybrid"


class DeviceConfig(BaseModel):
    """Device configuration within a topology"""
    device_type: str = Field(..., description="Device type: base_station | channel_emulator | signal_analyzer | etc")
    name: str = Field(..., description="Device name")
    connection_type: str = Field("visa", description="Connection type: visa | lan | usb | pxi")
    address: Optional[str] = Field(None, description="Device address (VISA resource string, IP, etc)")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Device-specific parameters")


class TopologyCreate(BaseModel):
    """Request to create a topology"""
    name: str = Field(..., max_length=255, description="Topology name")
    description: Optional[str] = Field(None, description="Topology description")
    topology_type: TopologyType = Field(TopologyType.OTA, description="Topology type")
    devices: List[DeviceConfig] = Field(default_factory=list, description="Device configurations")
    is_default: bool = Field(False, description="Set as default topology")
    created_by: Optional[str] = Field(None, description="Creator")


class TopologyUpdate(BaseModel):
    """Request to update a topology"""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    topology_type: Optional[TopologyType] = None
    devices: Optional[List[DeviceConfig]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class TopologyResponse(BaseModel):
    """Topology response"""
    id: UUID
    name: str
    description: Optional[str]
    topology_type: str
    devices: List[DeviceConfig]
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


class TopologyListResponse(BaseModel):
    """List of topologies"""
    total: int
    items: List[TopologyResponse]


class TopologySummary(BaseModel):
    """Brief topology info for lists"""
    id: UUID
    name: str
    topology_type: str
    device_count: int
    is_active: bool
    is_default: bool
