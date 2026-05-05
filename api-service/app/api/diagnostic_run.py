"""Read-only audit API for the workshop-tier diagnostic_runs.

Writes happen inside SCPI / Commissioning handlers via DiagnosticContext;
this module only exposes list + detail so the GUI can render history.

Filters worth supporting on day one:
  - kind (limit list to SCPI commands / sequences / commissioning runs)
  - lab_profile_id (operator scoped to one lab)
  - success (find recent failures fast — that's the most common debug entry)
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.diagnostic_run import DiagnosticKind, DiagnosticRun


router = APIRouter(prefix="/diagnostic-runs", tags=["Diagnostics"])


class DiagnosticRunSummary(BaseModel):
    id: UUID
    kind: str
    lab_profile_id: Optional[UUID] = None
    target_name: str
    success: bool
    duration_ms: Optional[int] = None
    run_at: datetime
    run_by: Optional[str] = None
    error_message: Optional[str] = None


class DiagnosticRunDetail(DiagnosticRunSummary):
    params: Optional[dict] = None
    output_excerpt: Optional[str] = None
    hal_trace_log_path: Optional[str] = None


class DiagnosticRunListResponse(BaseModel):
    items: List[DiagnosticRunSummary]
    total: int


@router.get("", response_model=DiagnosticRunListResponse)
def list_diagnostic_runs(
    kind: Optional[str] = Query(None, description="Filter by kind enum value"),
    lab_profile_id: Optional[UUID] = Query(None),
    success: Optional[bool] = Query(None, description="True/false to filter; omit for all"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List recent runs ordered by run_at desc. Lightweight summary only."""
    if kind is not None:
        # Validate against the enum so a typo doesn't silently return zero rows.
        try:
            DiagnosticKind(kind)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown kind '{kind}'. Valid: {[k.value for k in DiagnosticKind]}",
            ) from e

    q = db.query(DiagnosticRun)
    if kind is not None:
        q = q.filter(DiagnosticRun.kind == kind)
    if lab_profile_id is not None:
        q = q.filter(DiagnosticRun.lab_profile_id == lab_profile_id)
    if success is not None:
        q = q.filter(DiagnosticRun.success.is_(success))

    total = q.count()
    rows = (
        q.order_by(desc(DiagnosticRun.run_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return DiagnosticRunListResponse(
        items=[
            DiagnosticRunSummary(
                id=r.id,
                kind=r.kind,
                lab_profile_id=r.lab_profile_id,
                target_name=r.target_name,
                success=r.success,
                duration_ms=r.duration_ms,
                run_at=r.run_at,
                run_by=r.run_by,
                error_message=r.error_message,
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/{run_id}", response_model=DiagnosticRunDetail)
def get_diagnostic_run(run_id: UUID, db: Session = Depends(get_db)):
    row = db.query(DiagnosticRun).filter(DiagnosticRun.id == run_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"DiagnosticRun {run_id} not found")
    return DiagnosticRunDetail(
        id=row.id,
        kind=row.kind,
        lab_profile_id=row.lab_profile_id,
        target_name=row.target_name,
        success=row.success,
        duration_ms=row.duration_ms,
        run_at=row.run_at,
        run_by=row.run_by,
        error_message=row.error_message,
        params=row.params,
        output_excerpt=row.output_excerpt,
        hal_trace_log_path=row.hal_trace_log_path,
    )
