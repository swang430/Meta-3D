"""PC-03A 仪器当时的只读记录，不构成校准有效性结论。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from uuid import UUID
from app.schemas.diagnostic_evidence import SequenceStepEvidence


class F64StateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    group_id: int = Field(strict=True, gt=0)
    input_port: int = Field(strict=True, gt=0)
    output_port: int = Field(strict=True, gt=0)


class F64StateField(BaseModel):
    key: str
    label: str
    status: Literal['confirmed', 'unknown', 'simulated'] = 'unknown'
    value: JsonValue = None
    raw: str | None = None
    source_reference: str
    detail: str = '尚未读取'


class F64CalibrationState(BaseModel):
    requested: F64StateRequest
    captured_at: datetime
    binding_digest: str
    instrument_id: str
    acquisition_status: Literal['recorded', 'simulated']
    fields: list[F64StateField]
    diagnostic_only: Literal[True] = True
    formal_eligible: Literal[False] = False
    warnings: list[str] = Field(default_factory=list)
    query_evidence: dict[str, JsonValue] = Field(default_factory=dict)
    steps: list[SequenceStepEvidence] = Field(default_factory=list)


class F64StateRecord(BaseModel):
    diagnostic_run_id: UUID
    lab_profile_id: UUID
    run_at: datetime
    success: bool
    error_message: str | None = None
    record_status: Literal['complete', 'incomplete']
    state: F64CalibrationState | None = None
    formal_eligible: Literal[False] = False
