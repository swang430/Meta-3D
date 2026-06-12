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

import asyncio
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
from app.services.execution_exclusion_guard import (
    active_unsafe_diagnostic,
    release_unsafe_diagnostic,
    try_acquire_unsafe_diagnostic,
)
from app.services.test_case_runner import (
    has_active_case_run,
    has_running_case_run_row,
)

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
    raw: Optional[str] = None
    """仪器原始回复 (见 SequenceStepResult.raw)。None = 该步无仪器回复。"""


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
            audit_chamber_integrity_too=(key == "chamber_configuration_integrity"),
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

    # 破坏性诊断与正式 TestCase 执行共用同一套 HAL，不能交错下发。先用正式
    # runner 的进程任务表 + DB running 行双判据拒绝，再无等待地占进程内 token。
    # 三步之间都没有 await，在当前单进程/单事件循环部署契约下不会被另一请求插入。
    # safe_during_test=True 的只读序列不占位，也不受该门影响。
    unsafe_token: Optional[str] = None
    if not sequence.metadata.safe_during_test:
        active_case = has_active_case_run()
        if active_case is not None:
            raise HTTPException(
                status_code=409,
                detail=(f"正式用例执行 {active_case} 正在运行；"
                        f"破坏性诊断 '{key}' 未发送任何仪器指令。"),
            )
        running_row = has_running_case_run_row(db)
        if running_row is not None:
            raise HTTPException(
                status_code=409,
                detail=(f"DB 中正式用例执行 {running_row} 仍为 running；"
                        f"破坏性诊断 '{key}' 未发送任何仪器指令。"),
            )
        unsafe_token = try_acquire_unsafe_diagnostic(key)
        if unsafe_token is None:
            active_diagnostic = active_unsafe_diagnostic() or "(unknown)"
            raise HTTPException(
                status_code=409,
                detail=(f"破坏性诊断 '{active_diagnostic}' 正在运行；"
                        f"'{key}' 未发送任何仪器指令。"),
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
    cancelled_exc: Optional[asyncio.CancelledError] = None

    try:
        try:
            hal = get_hal_service()
            result = await sequence.run(ctx, hal, request.params, log=_log)
            success = bool(result.success)
            summary = result.summary
            step_results = [asdict(s) for s in result.steps]
            extra = result.extra
        except asyncio.CancelledError as exc:
            # 请求取消也必须留下“这次诊断发生过”的审计记录。序列尚未返回
            # SequenceRunResult，不能声称拿到了内部 partial steps/extra；明确记录
            # 该边界，待同步 I/O/序列取消收尾和下方同步 DB commit 完成后再重抛。
            success = False
            summary = "Sequence cancelled"
            error_msg = summary
            extra = {
                "cancelled": True,
                "partial_result_available": False,
            }
            cancelled_exc = exc
        except Exception as e:  # noqa: BLE001
            # Sequence raised — record as failure, surface error to UI.
            success = False
            summary = f"Sequence aborted: {e}"
            error_msg = str(e)
            logger.exception("Sequence %s aborted with exception", key)
    finally:
        # asyncio.CancelledError 属于 BaseException，不会被上面的普通异常分支吞掉；
        # 但它仍必须释放破坏性诊断占位，避免进程永久 409。
        if unsafe_token is not None:
            release_unsafe_diagnostic(unsafe_token)

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
            # 仪器原始回复必须进归档 —— 归档就是下次现场用来跟本次对照的东西,
            # 只存人读的 detail 等于把"它返回什么字面值"这类结论丢了 (本字段的
            # 存在理由)。`is not None` 而非真值判断: 空串回复本身就是一条结论。
            raw = s.get("raw")
            if raw is not None:
                output_text.write(f"      raw: {raw!r}\n")

    run = ctx.record_run(
        db,
        kind=DiagnosticKind.SCPI_SEQUENCE,
        target_name=key,
        success=success,
        params={"sequence_key": key, **request.params},
        output=output_text.getvalue(),
        result_extra=extra,
        error_message=error_msg,
        duration_ms=duration_ms,
        run_by=request.run_by,
    )

    if cancelled_exc is not None:
        raise cancelled_exc

    return SequenceRunResponse(
        diagnostic_run_id=run.id,
        success=success,
        summary=summary,
        duration_ms=duration_ms,
        log=log_buffer,
        steps=[SequenceStepResponse(**s) for s in step_results],
        extra=extra,
    )
