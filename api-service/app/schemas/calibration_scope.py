"""校准前配置盘点契约；不构成校准适用性或硬件证据。"""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ScopeChain(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chain_id: str
    ce_port: str
    probe_id: int
    polarization: str
    cable_loss_db: float | None = Field(allow_inf_nan=False, description='既有拓扑声明，null为未知，不是本片实测')


class CalibrationScopePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = 1
    lab_profile_id: UUID
    chamber_id: UUID
    operating_mode: str
    lab_active: bool
    chamber: dict[str, JsonValue]
    resources: list[dict[str, JsonValue]]
    topology: dict[str, JsonValue]
    probes: list[dict[str, JsonValue]]
    chains: list[ScopeChain]


class CalibrationScopeSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payload: CalibrationScopePayload
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    physical_identity: Literal['unverified'] = 'unverified'
    formal_eligible: Literal[False] = False
    configuration_complete: bool
    warnings: list[str]


class CalibrationScopeCompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    baseline: CalibrationScopeSnapshot


class CalibrationScopeComparison(BaseModel):
    current: CalibrationScopeSnapshot
    changed_sections: list[str]
    affected_chain_ids: list[str]
    requires_review: bool
    formal_eligible: Literal[False] = False
