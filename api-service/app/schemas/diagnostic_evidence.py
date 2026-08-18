"""Versioned structured evidence persisted for diagnostic sequence runs."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SequenceStepEvidence(BaseModel):
    label: str
    success: bool
    detail: str = ""
    duration_ms: Optional[int] = None
    raw: Optional[str] = None
    """Instrument reply verbatim; None means no reply while "" is observed."""


class SequenceEvidence(BaseModel):
    schema_version: Literal[1] = 1
    summary: str
    duration_ms: int
    log: List[str]
    steps: List[SequenceStepEvidence]
    extra: Dict[str, Any] = Field(default_factory=dict)


class SequenceRunResponse(SequenceEvidence):
    diagnostic_run_id: UUID
    success: bool
