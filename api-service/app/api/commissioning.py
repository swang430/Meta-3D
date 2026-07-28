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
from app.services.lab_resolution import LabResolutionError
from app.services.mimo_ota import build_mimo_ota_test_case
from app.services.test_execution import (
    StepDescriptor,
    StepExecutionContext,
    dispatch_step,
)


def _lab_resolution_to_422(err: LabResolutionError) -> HTTPException:
    """Translate a ``LabResolutionError`` into an actionable 422 the
    GUI can render directly.

    Detail shape (so the GUI can build a picker without re-fetching):
        {
          "kind": "none" | "ambiguous",
          "message": "<human-readable>",
          "active_labs": [{"id": str, "name": str}, ...],
        }

    Pre-this-fix the underlying ValueError propagated uncaught and
    FastAPI returned 500 — surfaced in the GUI's commissioning
    sandbox as "初始化失败 错误代码500" with no recovery path.
    """
    return HTTPException(
        status_code=422,
        detail={
            "kind": err.kind,
            "message": str(err),
            "active_labs": [
                {"id": str(lab.id), "name": lab.name}
                for lab in err.active_labs
            ],
        },
    )
from app.models.diagnostic_run import DiagnosticKind
from app.services.diagnostic_context import build_diagnostic_context

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
    # 2026-05-18 P0-7: engine_mode='external_asc' 时必填 (本机绝对路径,
    # 操作员手工产 .asc 的目录). 其他 engine_mode 该字段被忽略.
    asc_source_path: Optional[str] = None
    min_throughput_ratio: float = 0.70
    max_rsrp_variance_db: float = 3.0
    # New optional field — pin a specific lab; falls back to the unique active one.
    lab_profile_id: Optional[UUID] = None
    # Lab-smoke opt-outs for the strict precheck gates (P1-8 cal / P1-9 DUT).
    # Default None = don't override → config schema default (True, strict) applies,
    # so on-site real first-call keeps the fail-loud protection. The GUI's
    # "Lab smoke" toggle sends False to rehearse locally without a real DUT /
    # calibration (same path the e2e/smoke tests use). Optional[bool] not bool:
    # a literal False must override, but None must leave the default untouched
    # (passing None into the config would falsy-bypass the gate for everyone).
    precheck_strict_dut: Optional[bool] = None
    precheck_strict_cal: Optional[bool] = None
    # P2-11: 暗室首测 (路径 A) 的 "强制跳过严格门" 还要覆盖 Phase 1/2/3 新加的门, 否则
    # 真仪表空跑会撞上它们而无法绕过 (cal/dut 之外的捷径缺口)。同 Optional[bool] 语义:
    # 显式 False = real-mode operator override; None = 留 schema 默认 (strict)。
    precheck_strict_frequency: Optional[bool] = None
    precheck_strict_emulation_file: Optional[bool] = None
    precheck_strict_switch_mode: Optional[bool] = None
    # P2-11 Phase 6 (#114/#124/#126): DL layers/调制/MCS 一致性门也是暗室首测 (路径 A) 要跳的 ——
    # 此前漏接 → 真硬件 bring-up 撞 cell_config 门 (DUT 协商能力 < 默认请求 / MCS clamp) 挡住快速
    # first-call (feedback_strict_gate_extend_bypass_toggle 母题又踩)。同 Optional[bool] 语义。
    precheck_strict_cell_config: Optional[bool] = None
    # DUTProfile 声明能力门 (规划期, attach 前): 暗室首测 bring-up 也要可跳 (快速跑不关心 DUT
    # 声明)。新 strict 门同步 bypass (feedback_strict_gate_extend_bypass_toggle, 这次提前补)。
    precheck_strict_dut_capability: Optional[bool] = None
    # P2-13 Phase 2: SIM 身份核对门 (防插错卡)。bring-up 也要可跳 (快速跑可能不绑 SIMProfile /
    # 用临时卡)。新 strict 门同步 bypass (feedback_strict_gate_extend_bypass_toggle)。
    precheck_strict_sim_identity: Optional[bool] = None


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
    overrides: Dict[str, Any] = {
        "cdl_model_name": req.cdl_model_name,
        "frequency_hz": req.frequency_hz,
        "bandwidth_mhz": req.bandwidth_mhz,
        "mimo_layers": req.mimo_layers,
        "azimuths_deg": req.azimuths_deg,
        "measurement_duration_s": req.measurement_duration_s,
        "engine_mode": req.engine_mode,
        "asc_source_path": req.asc_source_path,
        "pass_criteria": {
            "min_throughput_ratio": req.min_throughput_ratio,
            "max_rsrp_variance_db": req.max_rsrp_variance_db,
        },
    }
    # Only emit the strict-gate flags when the caller set them explicitly.
    # Omitting them keeps the config schema default (True / strict). The
    # mock/real auto-skip is NOT applied here — it's evaluated live at precheck
    # time (precheck.py sections 5 / 5b: `strict = config_flag AND hardware_real`)
    # so a session created in mock but run on real hardware still gets the gate
    # (Codex on PR #75). An explicit False here is the real-mode operator
    # override (Lab-smoke toggle); None leaks nothing.
    if req.precheck_strict_dut is not None:
        overrides["precheck_strict_dut"] = req.precheck_strict_dut
    if req.precheck_strict_cal is not None:
        overrides["precheck_strict_cal"] = req.precheck_strict_cal
    # P2-11: Phase 1/2/3 新门同样的 explicit-False-override / None-leaves-default 语义。
    if req.precheck_strict_frequency is not None:
        overrides["precheck_strict_frequency"] = req.precheck_strict_frequency
    if req.precheck_strict_emulation_file is not None:
        overrides["precheck_strict_emulation_file"] = req.precheck_strict_emulation_file
    if req.precheck_strict_switch_mode is not None:
        overrides["precheck_strict_switch_mode"] = req.precheck_strict_switch_mode
    if req.precheck_strict_cell_config is not None:
        overrides["precheck_strict_cell_config"] = req.precheck_strict_cell_config
    if req.precheck_strict_dut_capability is not None:
        overrides["precheck_strict_dut_capability"] = req.precheck_strict_dut_capability
    if req.precheck_strict_sim_identity is not None:
        overrides["precheck_strict_sim_identity"] = req.precheck_strict_sim_identity
    return overrides


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
    """开关 3: 提升到 services/test_execution/hydrate.py 与计划 runner 共用。"""
    from app.services.test_execution.hydrate import build_step_context

    return build_step_context(db, execution, test_case, step)


# ==================== Endpoints ====================


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest, db: Session = Depends(get_db)):
    """Create a new MIMO_OTA session (TestCase + TestExecution + 5 step descriptors)."""
    overrides = _request_overrides(req)
    try:
        test_case, descriptors = build_mimo_ota_test_case(
            db,
            name=f"MIMO_OTA Session {datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            description="Created by /commissioning/sessions REST endpoint",
            lab_profile_id=req.lab_profile_id,
            config_overrides=overrides,
            created_by="commissioning_api",
            tags=["mimo_ota_session", "commissioning"],
        )
    except LabResolutionError as err:
        raise _lab_resolution_to_422(err) from err
    except ValueError as err:
        # explicit lab_profile_id that's missing/inactive — caller bug,
        # but a clean 422 is more useful than a 500 traceback
        raise HTTPException(status_code=422, detail=str(err)) from err

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
async def list_sessions(
    include_ad_hoc: bool = False,
    db: Session = Depends(get_db),
):
    """List MIMO_OTA sessions (TestExecutions whose TestCase.test_type=MIMO_OTA).

    Phase 3 introduced 'diagnostic_ad_hoc' single-phase runs that *must* live
    in test_executions (executors need a row to write measurements into) but
    aren't actual commissioning sessions. Default behaviour hides them so
    the regular list view stays clean; pass include_ad_hoc=true to see them.
    """
    rows = (
        db.query(TestExecution, TestCase)
        .join(TestCase, TestExecution.test_case_id == TestCase.id)
        .filter(TestCase.test_type == MIMO_OTA_TEST_TYPE)
        .order_by(TestExecution.executed_at.desc())
        .limit(200)
        .all()
    )
    if not include_ad_hoc:
        # 门审 #217 F9: 计划 runner 的步骤执行 (config 带 test_step_id) 与
        # diagnostic_ad_hoc 同理隐藏 — 反复调试计划会每步一行, 淹没 bring-up
        # 会话列表; 计划执行明细走测试管理页/历史 Tab, 不占会话视图。
        rows = [
            (ex, tc) for ex, tc in rows
            if not (ex.config or {}).get("diagnostic_ad_hoc")
            and not (ex.config or {}).get("test_step_id")
        ]
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


# ==================== P3 Phase 3: ad-hoc single-phase (workshop tier) ====================


class AdhocPhaseRequest(BaseModel):
    """One-shot run of a single MIMO_OTA executor against a synthetic session.

    Differs from /sessions + /sessions/{id}/phase/{name} in that:
      - The created TestCase + TestExecution are tagged 'diagnostic_ad_hoc'
        so the regular commissioning list view can hide them.
      - A diagnostic_run audit row is written (kind=COMMISSIONING_PHASE) so
        ops history is searchable across SCPI sequences + ad-hoc phases.
      - phase_overrides override the descriptor.parameters dict for this
        phase (e.g. skip a precheck assertion that's known broken-but-
        irrelevant for the current debug goal).
      - config_overrides override MIMOOTAConfiguration before descriptor build,
        same shape as CreateSessionRequest fields.
    """

    lab_profile_id: Optional[UUID] = None
    phase_name: str  # one of _PHASE_NAME_TO_STEP_TYPE keys
    config_overrides: Optional[Dict[str, Any]] = None
    phase_overrides: Optional[Dict[str, Any]] = None
    run_by: Optional[str] = None


class AdhocPhaseResponse(BaseModel):
    diagnostic_run_id: UUID
    test_execution_id: UUID
    phase: str
    status: str
    duration_ms: int
    result: Dict[str, Any]
    error_message: Optional[str] = None


@router.post("/diagnostic/run-phase", response_model=AdhocPhaseResponse)
async def run_adhoc_phase(req: AdhocPhaseRequest, db: Session = Depends(get_db)):
    """Run ONE MIMO_OTA executor as a debug probe.

    Creates a tagged TestCase + TestExecution (the executors need a row to
    write measurements into), runs the requested phase, persists a
    diagnostic_run audit row, returns the executor's payload + status.
    """
    import time

    if req.phase_name not in _PHASE_NAME_TO_STEP_TYPE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown phase: {req.phase_name}. "
                f"Valid: {list(_PHASE_NAME_TO_STEP_TYPE.keys())}"
            ),
        )
    target_step_type = _PHASE_NAME_TO_STEP_TYPE[req.phase_name]

    # Build a regular MIMO_OTA TestCase but tag it so the commissioning list
    # view can filter these out.
    overrides = req.config_overrides or {}
    try:
        test_case, descriptors = build_mimo_ota_test_case(
            db,
            name=f"ADHOC {req.phase_name} {datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            description=f"Ad-hoc workshop run of phase '{req.phase_name}'",
            lab_profile_id=req.lab_profile_id,
            config_overrides=overrides,
            created_by="commissioning_adhoc",
            tags=["diagnostic_ad_hoc", f"phase:{req.phase_name}"],
        )
    except LabResolutionError as err:
        raise _lab_resolution_to_422(err) from err
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    step = next((d for d in descriptors if d.type == target_step_type), None)
    if step is None:
        raise HTTPException(
            status_code=500,
            detail=f"No step descriptor for {target_step_type} (factory bug)",
        )

    # Apply per-phase parameter overrides on the in-memory descriptor only.
    if req.phase_overrides:
        step.parameters = {**(step.parameters or {}), **req.phase_overrides}

    execution = TestExecution(
        test_case_id=test_case.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={
            "step_descriptors": [
                {"id": step.id, "type": step.type, "parameters": step.parameters},
            ],
            "diagnostic_ad_hoc": True,
            "phase_overrides": req.phase_overrides or {},
        },
        executed_by="commissioning_adhoc",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    started = time.monotonic()
    error_message: Optional[str] = None
    status_value = "failed"
    try:
        ctx = _build_context(db, execution, test_case, step)
        result = await dispatch_step(ctx)
        status_value = result.status.value
        error_message = result.error_message
    except Exception as e:  # noqa: BLE001
        logger.exception("[adhoc] phase=%s aborted", req.phase_name)
        error_message = str(e)
    duration_ms = int((time.monotonic() - started) * 1000)

    db.refresh(execution)

    # Codex #238 迟到 C-2: 单相位诊断行也要收尾 — 建行时是 pending,
    # 不回写的话执行历史/仪表盘里它永远显示"待执行" (实际早跑完了)。
    # REPORT executor 会把成功链置 completed, 但 adhoc 多数相位不含
    # REPORT, 这里统一按实际结果落终态。
    # 相位状态有四种 (StepExecutionStatus: success/failed/skipped/running),
    # 二分成 completed/failed 会把"跳过"记成"失败" — skipped 是
    # TestExecution.status 的合法值, 原样保留 (自查发现, 见提交说明)。
    _PHASE_TO_ROW_STATUS = {"success": "completed", "skipped": "skipped"}
    execution.status = _PHASE_TO_ROW_STATUS.get(status_value, "failed")
    execution.completed_at = datetime.utcnow()
    execution.duration_sec = duration_ms / 1000.0
    if error_message:
        execution.error_message = error_message
    db.commit()

    phases_key = _STEP_TYPE_TO_PHASES_KEY[target_step_type]
    phase_payload = (execution.measurements or {}).get("phases", {}).get(phases_key) or {}

    # Workshop audit row — keyed by phase_name so list views can filter.
    ctx_for_audit = build_diagnostic_context(
        db,
        lab_profile_id=req.lab_profile_id,
        resolve_rf_chains_too=False,  # speed: this is debug, not measurement
    )
    summary_text = (
        f"phase={req.phase_name} status={status_value} "
        f"test_execution_id={execution.id} "
        f"phase_overrides={req.phase_overrides or {}}"
    )
    if error_message:
        summary_text += f"\nerror: {error_message}"
    audit_row = ctx_for_audit.record_run(
        db,
        kind=DiagnosticKind.COMMISSIONING_PHASE,
        target_name=req.phase_name,
        success=status_value == "success",
        params={
            "phase_name": req.phase_name,
            "config_overrides": overrides,
            "phase_overrides": req.phase_overrides or {},
            "test_execution_id": str(execution.id),
        },
        output=summary_text,
        error_message=error_message,
        duration_ms=duration_ms,
        run_by=req.run_by,
    )

    return AdhocPhaseResponse(
        diagnostic_run_id=audit_row.id,
        test_execution_id=execution.id,
        phase=req.phase_name,
        status=status_value,
        duration_ms=duration_ms,
        result=phase_payload or {"_executor_status": status_value},
        error_message=error_message,
    )


# ==================== HAL trace tail (workshop tier) ====================


class HALTraceTailResponse(BaseModel):
    """Last N lines from the HAL/SCPI log file."""

    log_path: str
    lines: List[str]
    total_lines_returned: int


@router.get("/diagnostic/hal-trace-tail", response_model=HALTraceTailResponse)
async def hal_trace_tail(lines: int = 200):
    """Return the tail of the SCPI / HAL log so the GUI can render a live console.

    Workshop tier debugging hinges on "what did the box send back". Right
    now operators have to ssh and tail; this surfaces the same lines next
    to the ad-hoc result so debug stays in one window.
    """
    from pathlib import Path

    # The logging config writes SCPI traffic to ./logs/calibration.log
    # (for calibration paths) and ./logs/app.log catches general HAL events.
    # Workshop tools mostly want the SCPI/measurement stream — start with
    # measurement.log, fall back to app.log.
    candidates = [
        Path("logs/measurement.log"),
        Path("logs/calibration.log"),
        Path("logs/app.log"),
    ]
    chosen = next((p for p in candidates if p.exists()), None)
    if chosen is None:
        raise HTTPException(
            status_code=404,
            detail=f"No log file found in {candidates}; check logging config",
        )

    n = max(1, min(2000, lines))  # cap so a malformed query doesn't OOM
    # Cheap-and-correct tail for typical log sizes (< 100MB). The "right"
    # answer is seek-from-end + read-back, but log files here are small.
    with chosen.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    tail = [line.rstrip("\n") for line in all_lines[-n:]]

    return HALTraceTailResponse(
        log_path=str(chosen),
        lines=tail,
        total_lines_returned=len(tail),
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


# ============================================================
# 暗室首测前逐设备快速自检 (借鉴转台 #132 / EMCenter standalone 验证理念)
#
# 暗室首测目的是快速 first-call 验整体思路, 不在细节调试上耗。但首测中途撞设备问题 (某仪表
# 没连上 / 不响应) 会打断这个目的。本端点在跑首测前对每个 HAL driver 主动探测 "连接 + 响应"
# (get_metrics 轻量查询), 让操作员先确认各设备单独通再开始首测 —— 把 "首测中途撞设备细节"
# 前移成 "首测前先单独验设备"。深度单设备控制验证去调试维护页 (转台控制 Tab / 调试序列)。
# ============================================================

class DeviceSelfcheckItem(BaseModel):
    category: str
    connected: bool
    responsive: bool  # get_metrics 不抛 = driver 能响应
    detail: Optional[str] = None


class DeviceSelfcheckResult(BaseModel):
    all_ready: bool
    devices: List[DeviceSelfcheckItem]
    message: str


@router.post("/device-selfcheck", response_model=DeviceSelfcheckResult)
async def device_selfcheck() -> DeviceSelfcheckResult:
    """暗室首测前逐设备快速自检 (连接 + 响应性主动探测)。"""
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
    except Exception:  # noqa: BLE001
        return DeviceSelfcheckResult(all_ready=False, devices=[], message="HAL 服务不可用")
    drivers = (hal.drivers or {}) if hal else {}
    if not drivers:
        return DeviceSelfcheckResult(
            all_ready=False, devices=[],
            message="无 HAL 驱动加载 — 检查仪器已选 + 连接 IP 已填, 或重载 HAL 驱动",
        )
    items: List[DeviceSelfcheckItem] = []
    for category, driver in sorted(drivers.items()):
        status = getattr(driver, "status", None)
        status_str = str(getattr(status, "value", status) or "").lower()
        connected = status_str in ("connected", "ready", "busy")
        responsive = False
        detail: Optional[str] = None
        try:
            await driver.get_metrics()  # 主动轻量探测 driver 是否响应
            responsive = True
        except Exception as e:  # noqa: BLE001
            detail = str(e)
        items.append(DeviceSelfcheckItem(
            category=category, connected=connected, responsive=responsive, detail=detail,
        ))
    all_ready = all(d.connected and d.responsive for d in items)
    return DeviceSelfcheckResult(
        all_ready=all_ready,
        devices=items,
        message=("各设备已连接且响应, 可开始暗室首测" if all_ready
                 else "部分设备未就绪 — 去调试维护页单独验证 (转台控制 / 调试序列) 后重试"),
    )
