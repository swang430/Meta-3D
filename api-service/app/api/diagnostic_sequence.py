"""GET /diagnostic-sequences (list) + POST .../{key}/run (execute).

Sequences themselves live as Python files under app/diagnostics/sequences/.
This module bridges the GUI: list metadata for a picker, run the chosen
one with operator-supplied params and a LabProfile context, persist the
result via the diagnostic_run audit table.

Failure modes the API should distinguish:
- 404: sequence key not found (typo / not yet imported)
- 422: required category not bound on the lab / invalid lab id
- 200 with success=False: sequence ran but reported a failure (DUT didn't
  attach, instrument refused command, etc.) — operator-actionable, not an
  HTTP error.
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.diagnostics import loader
from app.models.diagnostic_run import DiagnosticKind
from app.services.diagnostic_context import (
    build_diagnostic_context,
    DiagnosticContext,
)
from app.services.instrument_hal_service import get_hal_service

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/diagnostic-sequences", tags=["Diagnostics"])


class SequenceParamSpec(BaseModel):
    name: str
    label: str
    type: str
    default: Optional[Any] = None
    options: Optional[List[str]] = None


class SequenceMetadataResponse(BaseModel):
    key: str
    name: str
    description: str
    required_categories: List[str]
    params_schema: List[SequenceParamSpec]
    safe_during_test: bool


class RunSequenceRequest(BaseModel):
    lab_profile_id: Optional[UUID] = Field(
        None,
        description="Required when the sequence touches the lab; None for parameter-less probes",
    )
    operating_mode: str = Field("mimo_ota", description="For RF chain resolution if the sequence wants it")
    params: Dict[str, Any] = Field(default_factory=dict)
    run_by: Optional[str] = Field(None, description="Operator name / id for audit row")


class SequenceStepResponse(BaseModel):
    label: str
    success: bool
    detail: str = ""
    duration_ms: Optional[int] = None


class SequenceRunResponse(BaseModel):
    diagnostic_run_id: UUID
    success: bool
    summary: str
    duration_ms: int
    log: List[str]
    steps: List[SequenceStepResponse]
    extra: Dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=List[SequenceMetadataResponse])
def list_diagnostic_sequences():
    """List sequences discovered under app/diagnostics/sequences/."""
    return [SequenceMetadataResponse(**entry) for entry in loader.list_sequences()]


@router.post("/{key}/run", response_model=SequenceRunResponse)
async def run_diagnostic_sequence(
    key: str,
    request: RunSequenceRequest,
    db: Session = Depends(get_db),
):
    """Execute a sequence, persist a diagnostic_run row, return the result.

    The sequence's own success flag controls whether `success=True` lands in
    the DB row. HTTP stays 200 for operator-actionable failures (DUT didn't
    attach etc.); only 404/422 surface as HTTP errors because they're caller
    bugs (typo / lab missing).
    """
    try:
        sequence = loader.get_sequence(key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Build context — workshop tools accept lab_profile_id=None for
    # category-less probes, but most sequences will need a lab.
    try:
        ctx = build_diagnostic_context(
            db,
            lab_profile_id=request.lab_profile_id,
            operating_mode=request.operating_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Pre-flight: required_categories must all be bound on the lab. Missing
    # binding → 422 with the offending category, not "sequence ran and
    # silently skipped that step".
    missing = [
        cat for cat in sequence.metadata.required_categories
        if ctx.find_binding_by_category_key(cat) is None
        and ctx.find_binding_by_role(cat) is None
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Sequence '{key}' requires {missing} but the lab "
                f"'{ctx.lab_profile_name or '(none)'}' has no binding for them. "
                "Wire them in LabProfile.instrument_bindings first."
            ),
        )

    log_buffer: List[str] = []

    def _log(msg: str) -> None:
        log_buffer.append(msg)
        logger.info("[diagnostic %s] %s", key, msg)

    started = time.monotonic()
    error_msg: Optional[str] = None
    step_results: List[Any] = []
    extra: Dict[str, Any] = {}
    success = False
    summary = ""

    try:
        hal = get_hal_service()
        result = await sequence.run(ctx, hal, request.params, log=_log)
        success = bool(result.success)
        summary = result.summary
        step_results = [asdict(s) for s in result.steps]
        extra = result.extra
    except Exception as e:  # noqa: BLE001
        # Sequence raised — record as failure, surface error to UI.
        success = False
        summary = f"Sequence aborted: {e}"
        error_msg = str(e)
        logger.exception("Sequence %s aborted with exception", key)

    duration_ms = int((time.monotonic() - started) * 1000)

    # Persist the audit row. output_excerpt = the human log lines + summary
    # so the list view recap shows what actually happened.
    output_text = io.StringIO()
    output_text.write(f"summary: {summary}\n")
    if log_buffer:
        output_text.write("log:\n")
        for line in log_buffer:
            output_text.write(line + "\n")
    if step_results:
        output_text.write("steps:\n")
        for s in step_results:
            ok = "✓" if s["success"] else "✗"
            output_text.write(f"  {ok} {s['label']}: {s.get('detail') or ''}\n")

    run = ctx.record_run(
        db,
        kind=DiagnosticKind.SCPI_SEQUENCE,
        target_name=key,
        success=success,
        params={"sequence_key": key, **request.params},
        output=output_text.getvalue(),
        error_message=error_msg,
        duration_ms=duration_ms,
        run_by=request.run_by,
    )

    return SequenceRunResponse(
        diagnostic_run_id=run.id,
        success=success,
        summary=summary,
        duration_ms=duration_ms,
        log=log_buffer,
        steps=[SequenceStepResponse(**s) for s in step_results],
        extra=extra,
    )
