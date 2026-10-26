from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer
from uuid import UUID
from ._datetime import UTCDateTime


# ==========================================
# Schema Definitions corresponding to JSONB
# ==========================================

class TopologyNode(BaseModel):
    id: str
    type: str = Field(description="ce_port|switch_slot|probe|amplifier|combiner|pad|antenna|bse_port|sa_port|termination")
    label: str
    position: Dict[str, float] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict, description=(
        '开放JSON，保留扩展与缺键，不自动补声明。ports为非空、唯一、无首尾空白的字符串ID清单；'
        '新节点必须显式声明，旧图仅无关编辑可保留缺失。port_directions可选非null对象，'
        '键只能为ports内ID，值严格为input/output/bidirectional/unknown，允许部分map或空对象；'
        'unknown不是双向能力。communication_tester/bse_port的port_roles仅dl/ul且键属于ports，'
        'dl→output、ul→input为权威，通用方向unknown不覆盖它，同向可保存，反向或bidirectional冲突拒绝。'
        '新增/重接边或端口声明变化校验全部关联边：source不得input，target不得output；'
        '模板导入仅容旧缺声明，显式错误仍拒绝；端口声明不授予硬件、实测、校准采用或执行资格。'))


class TopologyConnection(BaseModel):
    id: str
    source: str
    source_pin: str = "out"
    target: str
    target_pin: str = "in"
    cable_type: str = ""
    cable_loss_db: float = 0.0
    pa_gain_db: JsonValue = Field(default=None, description=(
        '标称PA增益(dB)，非实测。新增/变更只接受有限number或null；'
        'PATCH仅兼容同Lab同ID同键、JSON类型和值均未改变的历史原值。'))
    nominal_metadata: JsonValue = Field(default=None, description=(
        '标称说明原始JSON：仅pa_gain_db/cable_loss_db键，值含unit(dB)、'
        'source_note(string/null)、frequency_range_mhz(两个有限正数且递增或null)。'
        '写入时严格验证，不授予实测或采用资格。'))
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
    installed_date: Optional[UTCDateTime] = None
    installed_by: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    nodes: List[TopologyNode] = Field(default_factory=list)
    connections: List[TopologyConnection] = Field(default_factory=list)
    operating_modes: List[OperatingMode] = Field(default_factory=list)


class SwitchTopologyCreate(SwitchTopologyBase):
    switch_category_id: UUID
    chamber_id: Optional[UUID] = None
    # P1-57：请求真值。暗室由它派生；chamber_id 只是兼容期一致性断言输入。
    lab_profile_id: UUID


class SwitchTopologyUpdate(BaseModel):
    connection_numeric_declarations: Dict[str, List[Literal[
        'cable_loss_db', 'cable_length_m', 'calibrated_loss_db', 'calibrated_phase_deg'
    ]]] = Field(default_factory=dict, description='仅本次PATCH显式重申数值的连线ID和字段；不持久化、不返回。')
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    site_name: Optional[str] = None
    system_model: Optional[str] = None
    installed_date: Optional[UTCDateTime] = None
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
    created_at: UTCDateTime
    updated_at: Optional[UTCDateTime] = None
    created_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('connections', when_used='json')
    def serialized_connections(self, connections):
        return [connection.model_dump(mode='json', exclude_unset=True) for connection in connections]


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
