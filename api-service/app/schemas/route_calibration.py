"""保存拓扑的完整固定通路声明；不是实物接通或正式校准资格。"""
from uuid import UUID
from typing import Literal
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator, field_validator
from app.schemas._datetime import UTCDateTime


class RoutePort(BaseModel):
    model_config = ConfigDict(extra='forbid')
    connection_id: str
    source: str
    source_pin: str
    target: str
    target_pin: str


class RouteSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lab_profile_id: UUID
    chamber_id: UUID
    topology_id: UUID
    operating_mode: str
    chain_id: str
    ce_port: str
    probe_id: int
    polarization: str
    node_ids: list[str] = Field(min_length=2)
    connection_ids: list[str] = Field(min_length=1)
    ports: list[RoutePort] = Field(min_length=1)
    nodes: list[dict[str, JsonValue]] = Field(min_length=2)
    connections: list[dict[str, JsonValue]] = Field(min_length=1)
    calibration_node_ids: list[str]
    calibration_connection_ids: list[str]
    calibration_nodes: list[dict[str, JsonValue]]
    calibration_connections: list[dict[str, JsonValue]]
    reference_antenna_id: str | None = None
    analyzer_category_id: str | None = None
    route_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    configuration_digest: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def require_consistent_path_sequence(self):
        def check_sequence(node_ids, nodes, edge_ids, edges):
            if (any(not ident.strip() for ident in [*node_ids,*edge_ids]) or
                len(node_ids) != len(set(node_ids)) or len(edge_ids) != len(set(edge_ids)) or
                [n.get('id') for n in nodes] != node_ids or [e.get('id') for e in edges] != edge_ids or
                len(edge_ids) != len(node_ids)-1):
                raise ValueError('路径的节点和连接序列缺损或不一致')
            for index, edge in enumerate(edges):
                if edge.get('source') != node_ids[index] or edge.get('target') != node_ids[index+1]:
                    raise ValueError('路径连接端点与节点顺序不一致')

        check_sequence(self.node_ids,self.nodes,self.connection_ids,self.connections)
        if self.chain_id != self.connection_ids[-1] or len(self.ports) != len(self.connections):
            raise ValueError('路径终端编号或端口序列缺损')
        for port, edge in zip(self.ports,self.connections):
            if (port.connection_id != edge['id'] or port.source != edge['source'] or port.target != edge['target'] or
                port.source_pin != edge.get('source_pin','out') or port.target_pin != edge.get('target_pin','in')):
                raise ValueError('路径端口与连接声明不一致')
        if self.nodes[0].get('type') not in ('ce_port','channel_emulator') or self.nodes[-1].get('type') != 'probe':
            raise ValueError('路径缺少CE源端或探头终点')
        params = self.nodes[-1].get('params') or {}
        if not isinstance(params,dict) or params.get('probe_id') != self.probe_id or params.get('polarization') != self.polarization:
            raise ValueError('路径探头身份与快照不一致')
        if set(self.node_ids) & set(self.calibration_node_ids):
            raise ValueError('校准参考接线与正常路径节点混合')
        check_sequence([self.node_ids[-1],*self.calibration_node_ids],
            [self.nodes[-1],*self.calibration_nodes],self.calibration_connection_ids,self.calibration_connections)
        return self


class RouteEligibility(BaseModel):
    model_config = ConfigDict(extra='forbid')
    eligible_for_adoption: bool
    blockers: list[str]
    warnings: list[str]
    acquisition_run_id: UUID
    route_digest: str | None = None
    method: str | None = None
    frequency_mhz: float | None = Field(default=None,allow_inf_nan=False)
    measurement_provenance: Literal['real','simulated','unknown']
    certification_status: Literal['unknown'] = 'unknown'


class RouteApplicationPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selection: RouteSelection | None
    acquisition_run_id: UUID
    expected_current_application_id: UUID | None = None
    old_value_db: float | None = Field(default=None,allow_inf_nan=False)
    new_net_loss_db: float | None = Field(default=None,allow_inf_nan=False)
    delta_db: float | None = Field(default=None,allow_inf_nan=False)
    eligibility: RouteEligibility


class ConfirmRouteApplication(BaseModel):
    model_config=ConfigDict(extra='forbid')
    acquisition_run_id: UUID
    route_digest: str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_current_application_id: UUID | None
    idempotency_key: UUID
    confirmed: Literal[True]
    adoption_valid_until: UTCDateTime

    @field_validator('confirmed',mode='before')
    @classmethod
    def explicit_confirmation(cls,value):
        if value is not True:
            raise ValueError('必须明确确认采用')
        return value

    @field_validator('adoption_valid_until')
    @classmethod
    def aware_deadline(cls,value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('选用截止必须包含时区')
        return value.astimezone(timezone.utc)


class RouteApplicationRecord(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: UUID
    predecessor_id: UUID | None
    acquisition_run_id: UUID
    selection_snapshot: RouteSelection
    method: str
    frequency_mhz: float=Field(allow_inf_nan=False)
    coverage_snapshot: dict[str,JsonValue]
    reference_snapshot: dict[str,JsonValue]
    net_loss_db: float=Field(allow_inf_nan=False)
    adoption_evidence_snapshot: dict[str,JsonValue]
    operator_confirmed: Literal[True]
    certification_status: Literal['unknown']='unknown'
    confirmed_at: UTCDateTime
    confirmed_by: str | None
