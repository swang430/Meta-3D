"""拓扑逐通路清单契约；不接受客户端测量值或正式资格。"""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator
from app.schemas.fixed_route_acquisition import FixedRouteRequest,Text,Number
from app.schemas.route_calibration import RouteSelection
from app.schemas.calibration_scope import CalibrationScopeSnapshot


class BatchReference(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    chain_id: Text
    frequency_mhz: Number=Field(gt=0)
    reference_antenna: Text
    receive_cable_loss_db: Number
    receive_cable_source: Text


class BatchPlanRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    topology_id: UUID
    operating_mode: Literal['mimo_ota']='mimo_ota'
    chain_ids: tuple[Text,...]=Field(min_length=1)
    frequencies_mhz: tuple[Number,...]=Field(min_length=1)
    references: tuple[BatchReference,...]=Field(min_length=1)
    requested_power_dbm: Number=Field(ge=-100,le=0)
    sample_count: int=Field(default=5,ge=2,le=10,strict=True)
    fixed_route_confirmed: Literal[True]
    safety_confirmed: Literal[True]
    preview_digest: str | None=Field(default=None,pattern=r'^[a-f0-9]{64}$')

    @field_validator('fixed_route_confirmed','safety_confirmed',mode='before')
    @classmethod
    def explicit_confirmation(cls,value):
        if value is not True:
            raise ValueError('必须明确确认，不能用数字或文本代替')
        return value

    @model_validator(mode='after')
    def complete_explicit_matrix(self):
        if len(set(self.chain_ids))!=len(self.chain_ids) or len(set(self.frequencies_mhz))!=len(self.frequencies_mhz):
            raise ValueError('通路和频点不能重复')
        if any(f<=0 for f in self.frequencies_mhz):
            raise ValueError('频率必须为正')
        keys=[(r.chain_id,r.frequency_mhz) for r in self.references]
        if len(keys)!=len(set(keys)) or set(keys)!={(c,f) for c in self.chain_ids for f in self.frequencies_mhz}:
            raise ValueError('每条通路每个频点必须有唯一参考件与线缆来源')
        if self.fixed_route_confirmed is not True or self.safety_confirmed is not True:
            raise ValueError('必须明确确认固定接线和安全条件')
        return self


class BatchSwitchStep(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    node_id: str
    path_name: str
    category_id: UUID
    connection_id: UUID
    endpoint: str
    instrument_model_id: UUID
    driver_mode: str
    mapping: dict


class BatchPlanItem(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    item_id: str
    request: FixedRouteRequest
    route_selection: RouteSelection
    configuration_scope: CalibrationScopeSnapshot
    switch_steps: tuple[BatchSwitchStep,...]=()
    transition_kind: Literal['manual','fixed']='manual'
    transition_reasons: tuple[str,...]=()


class BatchPlan(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    version: Literal[1]=1
    lab_profile_id: UUID
    topology_id: UUID
    operating_mode: Literal['mimo_ota']='mimo_ota'
    items: tuple[BatchPlanItem,...]
    preview_digest: str=Field(pattern=r'^[a-f0-9]{64}$')
    formal_eligible: Literal[False]=False
