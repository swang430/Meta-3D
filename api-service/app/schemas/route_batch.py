"""拓扑逐通路清单契约；不接受客户端测量值或正式资格。"""
import copy
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime,BaseModel,ConfigDict,Field,JsonValue,model_validator,field_validator
from app.schemas.fixed_route_acquisition import FixedRouteRequest,ExplicitMockInput,Text,Number
from app.schemas.route_calibration import RouteSelection
from app.schemas.calibration_scope import CalibrationScopeSnapshot


class BatchReference(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    chain_id: Text
    frequency_mhz: Number=Field(gt=0)
    reference_antenna: Text
    receive_cable_loss_db: Number | None = None
    receive_cable_source: Text | None = None


class BatchMockInput(ExplicitMockInput):
    chain_id: Text
    frequency_mhz: Number=Field(gt=0)


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
    mock_inputs: tuple[BatchMockInput,...] | None=Field(default=None,min_length=1)

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
        if self.mock_inputs is None:
            if any(r.receive_cable_loss_db is None or not r.receive_cable_source for r in self.references):
                raise ValueError('普通批采集每个频点必须有线缆损耗与来源')
        else:
            mock_keys=[(r.chain_id,r.frequency_mhz) for r in self.mock_inputs]
            if (len(mock_keys)!=len(set(mock_keys)) or set(mock_keys)!=set(keys) or
                any(len(r.samples)!=self.sample_count for r in self.mock_inputs)):
                raise ValueError('显式模拟矩阵须完整唯一，且每组样本数必须一致')
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


class BatchContinueRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_id: Text
    transition_id: Text
    reference_antenna: Text
    manual_confirmed: Literal[True]
    skip_failed: bool=Field(default=False,strict=True)

    @field_validator('manual_confirmed',mode='before')
    @classmethod
    def explicit_confirmation(cls,value):
        if value is not True:
            raise ValueError('必须明确确认当前人工步骤')
        return value


class BatchJobItem(BaseModel):
    item_id: str
    request: FixedRouteRequest
    status: Literal['pending','waiting_manual','measuring','running','completed','simulated',
        'failed','cancelled','cleanup_unconfirmed','interrupted','incomplete']
    run_id: UUID | None=None
    error: str | None=None
    switch_receipts: list[dict[str,JsonValue]]=Field(default_factory=list)


class BatchJobRecord(BaseModel):
    """只序列化服务器审计；缺损父记录不制造计划、释放或最终化事实。"""
    job_id: UUID
    lab_id: UUID
    version: Literal[1] | None=None
    idempotency_key: UUID | None=None
    request: BatchPlanRequest | None=None
    plan: BatchPlan | None=None
    preview_digest: str | None=None
    status: Literal['running','waiting_manual','paused_failure','completed','cancelled','failed',
        'cleanup_unconfirmed','interrupted','incomplete']
    current_index: int | None=None
    transition_id: str | None=None
    cancel_requested: bool=False
    error: str | None=None
    manual_notice: str | None=None
    lease_id: str | None=None
    f64_control_released: bool | None=None
    finalization_id: str | None=None
    finalization_committed: bool
    persistence_failed: bool | None=None
    all_started_cleanup_confirmed: bool | None=None
    items: list[BatchJobItem]
