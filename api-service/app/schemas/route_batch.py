"""拓扑逐通路清单契约；不接受客户端测量值或正式资格。"""
import copy
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime,BaseModel,ConfigDict,Field,model_validator,field_validator
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


class BatchSwitchWiringConfirmation(BaseModel):
    """人工接线声明，不是SCPI验证或RF验收；operator是自述，不能冒称认证身份。"""
    model_config=ConfigDict(extra='forbid',frozen=True)
    operator: Text
    confirmed_at: AwareDatetime
    note: Text
    switch_scope_digest: str=Field(pattern=r'^[a-f0-9]{64}$')


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
    switch_wiring_confirmation: BatchSwitchWiringConfirmation | None=None

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
    """mapping读取为独立工作副本，不能原地改写已冻结的步骤。"""
    model_config=ConfigDict(extra='forbid',frozen=True)
    node_id: str
    path_name: str
    category_id: UUID
    connection_id: UUID
    endpoint: str
    instrument_model_id: UUID
    driver_mode: str
    mapping: dict
    connection_config: dict=Field(default_factory=dict)

    @field_validator('mapping','connection_config')
    @classmethod
    def detach_mapping(cls,value):
        return copy.deepcopy(value)

    def __getattribute__(self,name):
        value=super().__getattribute__(name)
        return copy.deepcopy(value) if name in ('mapping','connection_config') else value


class BatchPlanItem(BaseModel):
    """公共可变schema仅作读取副本；构造和读取均隔离，JSON线形不变。

    Task2/3取得request/route_selection/configuration_scope后可持有工作副本，
    但修改副本不回写计划；需要新配置时必须重新构造并校验计划摘要。
    """
    model_config=ConfigDict(extra='forbid',frozen=True)
    item_id: str
    request: FixedRouteRequest
    route_selection: RouteSelection
    configuration_scope: CalibrationScopeSnapshot
    switch_steps: tuple[BatchSwitchStep,...]=()
    transition_kind: Literal['manual','fixed']='manual'
    transition_reasons: tuple[str,...]=()

    @field_validator('request','route_selection','configuration_scope')
    @classmethod
    def detach_snapshots(cls,value):
        return value.model_copy(deep=True)

    def __getattribute__(self,name):
        value=super().__getattribute__(name)
        if name in ('request','route_selection','configuration_scope'):
            return value.model_copy(deep=True)
        return value


class BatchPlan(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    version: Literal[1]=1
    lab_profile_id: UUID
    topology_id: UUID
    operating_mode: Literal['mimo_ota']='mimo_ota'
    items: tuple[BatchPlanItem,...]
    switch_scope_digest: str | None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    switch_wiring_confirmation: BatchSwitchWiringConfirmation | None=None
    preview_digest: str=Field(pattern=r'^[a-f0-9]{64}$')
    formal_eligible: Literal[False]=False
