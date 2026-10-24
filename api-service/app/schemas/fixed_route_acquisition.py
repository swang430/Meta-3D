"""PC-04A自动采集契约；客户端不能提交两端实测值或校准资格。"""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Number = Annotated[float, Field(allow_inf_nan=False)]


class FixedRouteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chain_id: Text
    configuration_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    frequency_mhz: Number = Field(gt=0)
    # 应用首批安全边界，不是厂商承诺的整个功率域；操作员仍须核对放大器/接收端安全。
    requested_power_dbm: Number = Field(ge=-100, le=0)
    reference_antenna: Text = Field(description='参考天线身份、极化及位置，由操作员确认')
    receive_cable_loss_db: Number | None = None
    receive_cable_source: Text | None = None
    fixed_route_confirmed: Literal[True]
    safety_confirmed: Literal[True] = Field(description='操作员已确认专用校准仿真、固定接线、无其它混入信号及允许功率')
    sample_count: int = Field(default=5, ge=2, le=10, strict=True)


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
    version: Literal[1] = 1
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


class FixedRouteRecord(BaseModel):
    run_id: UUID
    lab_profile_id: UUID
    run_at: datetime
    status: str
    result: FixedRouteResult | None = None
    formal_eligible: Literal[False] = False
