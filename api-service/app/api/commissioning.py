"""3GPP Static MIMO OTA Commissioning REST endpoints — TestCase-backed.

Public surface is unchanged from the legacy in-memory service so existing
GUI/clients keep working. Internally every session is now a TestCase row
(test_type='MIMO_OTA') + a TestExecution row, and each phase is dispatched
through the ExecutorRegistry. The `_sessions` in-memory dict is gone.

Phase name compatibility map (old string -> step.type):
  precheck   -> MIMO_OTA_PRECHECK
  reference  -> MIMO_OTA_REFERENCE
  mimo_test  -> MIMO_OTA_MEASURE
  analysis   -> MIMO_OTA_ANALYSIS
  report     -> MIMO_OTA_REPORT
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.calibration import CalibrationCertificate
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.schemas.mimo_ota.config import MIMO_OTA_TEST_TYPE, MIMOOTAStepType
from app.services.mimo_ota import build_mimo_ota_test_case
from app.services.test_execution import (
    StepDescriptor,
    StepExecutionContext,
    dispatch_step,
)

router = APIRouter(prefix="/commissioning", tags=["暗室首测"])
logger = logging.getLogger(__name__)


# Map old phase-name strings to canonical step.type values
_PHASE_NAME_TO_STEP_TYPE: Dict[str, str] = {
    "precheck": MIMOOTAStepType.PRECHECK.value,
    "reference": MIMOOTAStepType.REFERENCE.value,
    # legacy "wait for antenna" stage is not separately modeled in MIMO_OTA;
    # treat the wait endpoint as a no-op that just reports current status.
    "reference_wait": MIMOOTAStepType.REFERENCE.value,
    "mimo_test": MIMOOTAStepType.MEASURE.value,
    "analysis": MIMOOTAStepType.ANALYSIS.value,
    "report": MIMOOTAStepType.REPORT.value,
}

# Map step.type -> the key under measurements['phases'] each executor writes
_STEP_TYPE_TO_PHASES_KEY: Dict[str, str] = {
    MIMOOTAStepType.PRECHECK.value: "precheck",
    MIMOOTAStepType.REFERENCE.value: "reference",
    MIMOOTAStepType.MEASURE.value: "measure",
    MIMOOTAStepType.ANALYSIS.value: "analysis",
    MIMOOTAStepType.REPORT.value: "report",
}

# Old SessionResponse-side phase keys (kept for backward compat with old GUI)
_LEGACY_PHASE_ORDER = ["precheck", "reference", "mimo_test", "analysis", "report"]


# ==================== Pydantic models (unchanged shape) ====================


class CreateSessionRequest(BaseModel):
    cdl_model_name: str = "UMa CDL-C NLOS"
    frequency_hz: float = 3.5e9
    bandwidth_mhz: float = 100
    mimo_layers: int = 2
    azimuths_deg: List[float] = [0.0, 90.0, 180.0, 270.0]
    measurement_duration_s: float = 10.0
    engine_mode: str = "mimo_first_asc"
    min_throughput_ratio: float = 0.70
    max_rsrp_variance_db: float = 3.0
    # New optional field — pin a specific lab; falls back to the unique active one.
    lab_profile_id: Optional[UUID] = None


class SessionResponse(BaseModel):
    session_id: str
    phase: str
    phase_statuses: Dict[str, str]
    overall_progress: float
    config: Dict[str, Any]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    precheck: Optional[Dict[str, Any]] = None
    reference: Optional[Dict[str, Any]] = None
    mimo_test: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    report_id: Optional[str] = None


class PhaseResultResponse(BaseModel):
    phase: str
    status: str
    result: Dict[str, Any]


# ==================== Helpers ====================


def _request_overrides(req: CreateSessionRequest) -> Dict[str, Any]:
    """Translate CreateSessionRequest fields into MIMOOTAConfiguration overrides."""
    return {
        "cdl_model_name": req.cdl_model_name,
        "frequency_hz": req.frequency_hz,
        "bandwidth_mhz": req.bandwidth_mhz,
        "mimo_layers": req.mimo_layers,
        "azimuths_deg": req.azimuths_deg,
        "measurement_duration_s": req.measurement_duration_s,
        "engine_mode": req.engine_mode,
        "pass_criteria": {
            "min_throughput_ratio": req.min_throughput_ratio,
            "max_rsrp_variance_db": req.max_rsrp_variance_db,
        },
    }


def _phase_status_from_payload(payload: Dict[str, Any]) -> str:
    """Map a phase payload to old PhaseStatus string."""
    if not payload:
        return "pending"
    if payload.get("overall_pass") is False:
        return "failed"
    return "completed"


def _execution_to_session_response(
    execution: TestExecution, test_case: TestCase
) -> SessionResponse:
    """Reconstruct the legacy SessionResponse shape from TestExecution + TestCase."""
    measurements = execution.measurements or {}
    phases: Dict[str, Dict[str, Any]] = (measurements or {}).get("phases", {})

    # phase_statuses keyed by old phase strings
    phase_statuses: Dict[str, str] = {}
    completed_count = 0
    for legacy_name in _LEGACY_PHASE_ORDER:
        # legacy_name -> internal phases key (mimo_test -> measure, others same)
        internal_key = (
            "measure" if legacy_name == "mimo_test" else legacy_name
        )
        payload = phases.get(internal_key, {}) or {}
        status = _phase_status_from_payload(payload)
        phase_statuses[legacy_name] = status
        if status == "completed":
            completed_count += 1

    overall_progress = completed_count / len(_LEGACY_PHASE_ORDER) * 100.0

    # current "phase" — pick the latest one with data, else first pending
    current_phase = "precheck"
    for legacy_name in _LEGACY_PHASE_ORDER:
        if phase_statuses[legacy_name] == "completed":
            current_phase = legacy_name
        else:
            current_phase = legacy_name
            break

    cfg = test_case.configuration or {}
    config_view = {
        "cdl_model_name": cfg.get("cdl_model_name"),
        "frequency_ghz": (cfg.get("frequency_hz") or 0.0) / 1e9,
        "bandwidth_mhz": cfg.get("bandwidth_mhz"),
        "mimo_config": f"{cfg.get('mimo_layers', 2)}x{cfg.get('mimo_layers', 2)}",
        "azimuths_deg": cfg.get("azimuths_deg"),
        "measurement_duration_s": cfg.get("measurement_duration_s"),
        "total_estimated_time_s": (
            (cfg.get("measurement_duration_s", 0) + cfg.get("settling_time_s", 0))
            * len(cfg.get("azimuths_deg", []) or [])
        ),
        "engine_mode": cfg.get("engine_mode"),
    }

    report_payload = phases.get("report") or {}

    return SessionResponse(
        session_id=str(execution.id),
        phase=current_phase,
        phase_statuses=phase_statuses,
        overall_progress=overall_progress,
        config=config_view,
        started_at=(
            execution.started_at.isoformat() + "Z" if execution.started_at else None
        ),
        completed_at=(
            execution.completed_at.isoformat() + "Z" if execution.completed_at else None
        ),
        precheck=phases.get("precheck"),
        reference=phases.get("reference"),
        mimo_test=phases.get("measure"),
        analysis=phases.get("analysis"),
        report_id=report_payload.get("report_id"),
    )


def _resolve_execution(
    db: Session, session_id: str
) -> tuple[TestExecution, TestCase, list[StepDescriptor]]:
    """Look up TestExecution + TestCase by session_id (= execution UUID).

    Step descriptors are reconstructed from TestExecution.config JSON, which
    the create_session endpoint stores at session creation time.
    """
    try:
        exec_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid session_id: {session_id}")

    execution = db.query(TestExecution).filter(TestExecution.id == exec_uuid).first()
    if execution is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if execution.test_case_id is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session {session_id}: no test_case bound (corrupted state)",
        )
    test_case = (
        db.query(TestCase).filter(TestCase.id == execution.test_case_id).first()
    )
    if test_case is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session {session_id}: TestCase {execution.test_case_id} missing",
        )
    if test_case.test_type != MIMO_OTA_TEST_TYPE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Session {session_id}: TestCase test_type='{test_case.test_type}' is "
                f"not {MIMO_OTA_TEST_TYPE}"
            ),
        )

    raw_steps = (execution.config or {}).get("step_descriptors") or []
    descriptors = [
        StepDescriptor(
            id=s["id"], type=s["type"], parameters=s.get("parameters") or {}
        )
        for s in raw_steps
    ]
    return execution, test_case, descriptors


def _build_context(
    db: Session,
    execution: TestExecution,
    test_case: TestCase,
    step: StepDescriptor,
) -> StepExecutionContext:
    """Hydrate a StepExecutionContext: pull LabProfile + cert from FKs."""
    lab_profile = None
    if test_case.lab_profile_id is not None:
        lab_profile = (
            db.query(LabProfile)
            .filter(LabProfile.id == test_case.lab_profile_id)
            .first()
        )
    cert = None
    cert_id = test_case.calibration_certificate_id or (
        lab_profile.active_calibration_certificate_id if lab_profile else None
    )
    if cert_id is not None:
        cert = (
            db.query(CalibrationCertificate)
            .filter(CalibrationCertificate.id == cert_id)
            .first()
        )
    return StepExecutionContext(
        db=db,
        step=step,
        test_execution=execution,
        lab_profile=lab_profile,
        calibration_certificate=cert,
        parameters=dict(step.parameters or {}),
    )


# ==================== Endpoints ====================


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest, db: Session = Depends(get_db)):
    """Create a new MIMO_OTA session (TestCase + TestExecution + 5 step descriptors)."""
    overrides = _request_overrides(req)
    test_case, descriptors = build_mimo_ota_test_case(
        db,
        name=f"MIMO_OTA Session {datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
        description="Created by /commissioning/sessions REST endpoint",
        lab_profile_id=req.lab_profile_id,
        config_overrides=overrides,
        created_by="commissioning_api",
        tags=["mimo_ota_session", "commissioning"],
    )

    execution = TestExecution(
        test_case_id=test_case.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={
            "step_descriptors": [
                {"id": d.id, "type": d.type, "parameters": d.parameters}
                for d in descriptors
            ]
        },
        executed_by="commissioning_api",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    logger.info(
        "Created MIMO_OTA session: execution_id=%s test_case_id=%s",
        execution.id,
        test_case.id,
    )
    return _execution_to_session_response(execution, test_case)


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(db: Session = Depends(get_db)):
    """List all MIMO_OTA sessions (TestExecutions whose TestCase.test_type=MIMO_OTA)."""
    rows = (
        db.query(TestExecution, TestCase)
        .join(TestCase, TestExecution.test_case_id == TestCase.id)
        .filter(TestCase.test_type == MIMO_OTA_TEST_TYPE)
        .order_by(TestExecution.executed_at.desc())
        .limit(200)
        .all()
    )
    return [_execution_to_session_response(ex, tc) for ex, tc in rows]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: Session = Depends(get_db)):
    execution, test_case, _ = _resolve_execution(db, session_id)
    return _execution_to_session_response(execution, test_case)


@router.post(
    "/sessions/{session_id}/phase/{phase_name}",
    response_model=PhaseResultResponse,
)
async def run_phase(
    session_id: str, phase_name: str, db: Session = Depends(get_db)
):
    if phase_name not in _PHASE_NAME_TO_STEP_TYPE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown phase: {phase_name}. "
                f"Valid: {list(_PHASE_NAME_TO_STEP_TYPE.keys())}"
            ),
        )
    target_step_type = _PHASE_NAME_TO_STEP_TYPE[phase_name]
    execution, test_case, descriptors = _resolve_execution(db, session_id)

    # Find the descriptor for this step type
    step = next((d for d in descriptors if d.type == target_step_type), None)
    if step is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session {session_id} has no step descriptor for {target_step_type}",
        )

    ctx = _build_context(db, execution, test_case, step)
    result = await dispatch_step(ctx)

    db.refresh(execution)  # pick up measurements written by executor
    phases_key = _STEP_TYPE_TO_PHASES_KEY[target_step_type]
    phase_payload = (execution.measurements or {}).get("phases", {}).get(phases_key) or {}

    return PhaseResultResponse(
        phase=phase_name,
        status=result.status.value,
        result=phase_payload or {"_executor_status": result.status.value},
    )


@router.post("/sessions/{session_id}/run-all", response_model=SessionResponse)
async def run_all_phases(session_id: str, db: Session = Depends(get_db)):
    """Sequentially dispatch all 5 phases. Aborts early if a phase fails."""
    execution, test_case, descriptors = _resolve_execution(db, session_id)

    for step in descriptors:
        ctx = _build_context(db, execution, test_case, step)
        result = await dispatch_step(ctx)
        if result.status.value == "failed":
            logger.warning(
                "[%s] run-all aborted at %s: %s",
                session_id,
                step.type,
                result.error_message,
            )
            break

    db.refresh(execution)
    db.refresh(test_case)
    return _execution_to_session_response(execution, test_case)
