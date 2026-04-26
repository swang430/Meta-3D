from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime


# ==========================================
# Schema Definitions corresponding to JSONB
# ==========================================

class TopologyNode(BaseModel):
    id: str
    type: str = Field(description="ce_port|switch_slot|probe|amplifier|combiner|pad|antenna|bse_port|sa_port|termination")
    label: str
    position: Dict[str, float] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)


class TopologyConnection(BaseModel):
    id: str
    source: str
    source_pin: str = "out"
    target: str
    target_pin: str = "in"
    cable_type: str = ""
    cable_loss_db: float = 0.0
    pa_gain_db: Optional[float] = None
    ce_port: Optional[str] = None
    switch_port: Optional[str] = None
    cable_length_m: float = 0.0
    calibrated_loss_db: Optional[float] = None
    calibrated_phase_deg: Optional[float] = None
    direction: str = Field(default="DL", description="DL, UL, or Bi-Di")
    modes: List[str] = Field(default_factory=list)


class OperatingMode(BaseModel):
    id: str
    name: str
    description: str = ""
    active_connections: List[str] = Field(default_factory=list)
    required_instruments: List[str] = Field(default_factory=list)
    color: str = "#CCCCCC"


# ==========================================
# API Request / Response Models
# ==========================================

class SwitchTopologyBase(BaseModel):
    name: str
    description: Optional[str] = None
    version: str = "1.0"
    site_name: Optional[str] = None
    system_model: Optional[str] = None
    installed_date: Optional[datetime] = None
    installed_by: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    nodes: List[TopologyNode] = Field(default_factory=list)
    connections: List[TopologyConnection] = Field(default_factory=list)
    operating_modes: List[OperatingMode] = Field(default_factory=list)


class SwitchTopologyCreate(SwitchTopologyBase):
    switch_category_id: UUID
    chamber_id: Optional[UUID] = None


class SwitchTopologyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    site_name: Optional[str] = None
    system_model: Optional[str] = None
    installed_date: Optional[datetime] = None
    installed_by: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    nodes: Optional[List[TopologyNode]] = None
    connections: Optional[List[TopologyConnection]] = None
    operating_modes: Optional[List[OperatingMode]] = None
    chamber_id: Optional[UUID] = None


class SwitchTopologyResponse(SwitchTopologyBase):
    id: UUID
    switch_category_id: UUID
    chamber_id: Optional[UUID] = None
    total_nodes: int
    total_connections: int
    total_probes: int
    total_channels: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SwitchTopologyListResponse(BaseModel):
    total: int
    items: List[SwitchTopologyResponse]


# ==========================================
# TopologyService Computation Models
# ==========================================

class SignalPathResponse(BaseModel):
    path_id: str
    source_node: TopologyNode
    target_node: TopologyNode
    total_loss_db: float
    total_phase_deg: float
    calibration_status: str
    hop_count: int


class CalibrationMatrixResponse(BaseModel):
    mode_id: str
    matrix: Dict[str, Dict[str, Any]]
