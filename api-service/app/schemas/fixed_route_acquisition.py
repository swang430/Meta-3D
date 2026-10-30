"""PC-04A自动采集契约；客户端不能提交两端实测值或校准资格。"""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator, model_validator
from app.schemas.route_calibration import RouteSelection

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class MockPowerSample(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    source_before_dbm: Number
    received_dbm: Number
    source_after_dbm: Number


class ExplicitMockInput(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    samples: tuple[MockPowerSample, ...] = Field(min_length=2, max_length=10)
    expected_loss_db: Number | None = None


class FixedRouteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chain_id: Text
    configuration_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    topology_id: UUID | None = None
    operating_mode: Text = 'mimo_ota'
    route_digest: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    frequency_mhz: Number = Field(gt=0)
    # 应用首批安全边界，不是厂商承诺的整个功率域；操作员仍须核对放大器/接收端安全。
    requested_power_dbm: Number = Field(ge=-100, le=0)
    reference_antenna: Text = Field(description='参考天线身份、极化及位置，由操作员确认')
    receive_cable_loss_db: Number | None = None
    receive_cable_source: Text | None = None
    fixed_route_confirmed: Literal[True]
    safety_confirmed: Literal[True] = Field(description='操作员已确认专用校准仿真、固定接线、无其它混入信号及允许功率')
    sample_count: int = Field(default=5, ge=2, le=10, strict=True)
    mock_input: ExplicitMockInput | None = None

    @model_validator(mode='after')
    def explicit_sample_count(self):
        if self.mock_input is not None and len(self.mock_input.samples) != self.sample_count:
            raise ValueError('模拟样本数必须等于本次sample_count')
        return self

    @field_validator('fixed_route_confirmed', 'safety_confirmed', mode='before')
    @classmethod
    def require_explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('必须由操作员明确确认，不能以数字或文本代替')
        return value


class PowerExchange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    instrument_id: str
    command: str
    response: str | None = None
    error: str | None = None
    simulated: bool = False
    host_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FixedRouteSample(BaseModel):
    source_before_dbm: Number
    received_dbm: Number
    source_after_dbm: Number
    host_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FixedRouteResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1, 2] = 1
    run_id: UUID
    lab_profile_id: UUID
    request: FixedRouteRequest
    configuration: dict[str, JsonValue]
    status: Literal['running', 'completed', 'simulated', 'failed', 'cancelled', 'cleanup_unconfirmed', 'interrupted', 'incomplete'] = 'running'
    samples: list[FixedRouteSample] = Field(default_factory=list)
    exchanges: list[PowerExchange] = Field(default_factory=list)
    states: dict[str, JsonValue] = Field(default_factory=dict)
    net_loss_db: Number | None = None
    sample_std_db: Number | None = None
    cleanup_confirmed: bool | None = None
    error: str | None = None
    missing_items: list[str] = Field(default_factory=lambda: ['仪器绝对准确度、参考件证书及完整不确定度预算仍需现场核验；本记录不签发校准资格'])
    method: Literal['fixed_route_port_to_reference_v1'] = 'fixed_route_port_to_reference_v1'
    formal_eligible: Literal[False] = False
    simulation_input_source: Literal['operator_supplied_synthetic'] | None = None

    @model_validator(mode='after')
    def require_version2_route_snapshot(self):
        if self.version == 2:
            route = RouteSelection.model_validate(self.configuration.get('route_selection'))
            if (route.lab_profile_id != self.lab_profile_id or route.chain_id != self.request.chain_id or
                route.operating_mode != self.request.operating_mode or
                (self.request.topology_id is not None and route.topology_id != self.request.topology_id) or
                (self.request.route_digest is not None and route.route_digest != self.request.route_digest)):
                raise ValueError('新版采集记录的完整路径与请求身份不一致')
        return self


class FixedRouteBatchContext(BaseModel):
    active: bool
    finalized: bool
    job_id: UUID | None=None
    lease_id: str | None=None
    finalization_id: str | None=None


class FixedRouteRecord(BaseModel):
    run_id: UUID
    lab_profile_id: UUID
    run_at: datetime
    status: str
    result: FixedRouteResult | None = None
    batch_context: FixedRouteBatchContext | None = None
    formal_eligible: Literal[False] = False
