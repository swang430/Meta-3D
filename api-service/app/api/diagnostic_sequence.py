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
from contextlib import asynccontextmanager, nullcontext
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.diagnostics import loader
from app.models.diagnostic_run import DiagnosticKind
from app.schemas.diagnostic_evidence import (
    SequenceEvidence,
    SequenceRunResponse,
    SequenceStepEvidence,
)
from app.services.diagnostic_context import (
    build_diagnostic_context,
    DiagnosticContext,
)
from app.services.instrument_hal_service import get_hal_service
from app.services.instrument_test_lease import instrument_test_lease
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
    is_cmw_probe = key == "cmw500_fdd_matrix_probe"
    lease_outcome = None
    captured = []
    resolved_binding = None
    locked_hal = None
    validator = None
    if is_cmw_probe:
        from app.diagnostics.sequences.cmw500_fdd_matrix_probe import (
            ProbeCancelled, ProbePreflightRejected, validate_params,
        )
        from app.hal.cmw500_base_station import RealCmw500Driver
        from app.hal.scpi_evidence import capture_scpi_exchanges
        from app.models.lab_profile import LabProfile
        from app.services.base_station_binding import resolve_base_station_binding
        from app.services.instrument_hal_service import is_mock_driver
        from app.services.instrument_test_lease import hal_mutation_guard

        extra = {"formal_eligible": False, "classification": "diagnostic_only"}

        def validator(hal):
            nonlocal resolved_binding, locked_hal
            # Same HAL mutation lock as Remote acquisition; no client snapshot.
            try:
                validate_params(request.params)
                lab = db.get(LabProfile, ctx.lab_profile_id)
                if lab is None:
                    return "CMW 抽样缺少所选 LabProfile"
                resolved_binding = resolve_base_station_binding(db, hal, lab, lock=True)
                driver = hal.drivers.get("baseStation")
                if is_mock_driver(driver) or type(driver) is not RealCmw500Driver:
                    return "CMW 抽样只接受真实 CMW500；模拟结果不能作为现场证据"
                locked_hal = hal
                extra["binding"] = resolved_binding.model_dump(mode="json")
            except ValueError as exc:
                return str(exc)
            finally:
                # Resolver is read-only; don't retain row locks across awaited I/O.
                db.rollback()
            return None

    @asynccontextmanager
    async def sequence_lease(lease_categories):
        # Only this probe needs a non-mutating RF preflight before the common
        # lease (CMW release always enforces SAFE_IDLE). Reuse the same HAL lock
        # across preflight/connect/acquire; never weaken release to preserve ON.
        if is_cmw_probe:
            async with hal_mutation_guard():
                error = validator(get_hal_service())
                if error:
                    raise ValueError(error)
                driver = locked_hal.drivers["baseStation"]
                if driver._visa_session is None and not await driver.connect():
                    raise ValueError("CMW 只读前置连接失败")
                preflight = await sequence.run(
                    ctx, locked_hal, request.params, log=_log,
                    resolved_binding=resolved_binding, preflight_only=True,
                )
                if not preflight.success:
                    # On refusal keep the HAL-owned transport; closing through
                    # release_remote_session would shut down an out-of-scope cell.
                    raise ProbePreflightRejected(preflight)
                async with instrument_test_lease(
                    f"diagnostic-sequence:{key}", control_f64=False, control_uxm=True,
                    validate_before_remote=validator, enable_monitoring=False,
                ) as outcome:
                    yield outcome
        else:
            async with instrument_test_lease(
                f"diagnostic-sequence:{key}",
                control_f64="channelEmulator" in lease_categories,
                control_uxm="baseStation" in lease_categories,
            ) as outcome:
                yield outcome

    try:
        try:
            # 租约要覆盖序列**会碰到**的驱动，不只是它**跑不了就得有**的那些。
            # 只取 required 时，声明为可选依赖的驱动会停在 park 后的 Local 态，
            # 序列一调它就返 False（内审 F3：`baseStation_attach_check` 声明
            # 只有 baseStation，序列体却实打实调 channelEmulator 的
            # stop_emulation / set_passthrough_mode）。G17 门守着两者不脱钩。
            # ⚠ optional 那半必须再过一遍**本 lab 到底绑没绑**（内审 F2）——
            #   判据要跟序列体同源。`baseStation_attach_check:145` 用的是
            #   `ctx.find_binding_by_category_key("channelEmulator")`，而
            #   HAL drivers 是**全局**的：线缆直连 lab（无 CE binding）撞上别的
            #   setup 残留的 F64 驱动时，只按声明取租约会
            #     ① 把**不属于本 lab** 的 F64 拽进 Remote —— 手册原文
            #        （PROPSIM User Reference §20.1）：发第一条 ATE 命令即进
            #        remote，**回 local 要操作员在 GUI 右上角点按钮**，我们
            #        没法替它回去；
            #     ② 那台 F64 不可达时 acquire 失败 → InstrumentTestLeaseError
            #        → 整条 attach 序列 aborted，「可选依赖」变成硬前置，
            #        正好抵消 optional_categories 想解决的问题。
            #   required 保持无条件取：跑不了就得有，那是真前置。
            lease_categories = set(sequence.metadata.required_categories) | {
                c for c in sequence.metadata.optional_categories
                if ctx.find_binding_by_category_key(c) is not None
            }
            if key == "instrument_idn_sweep":
                lease_categories.update(
                    binding.category_key
                    for binding in (ctx.instrument_bindings or [])
                    if binding.category_key
                )
            with (capture_scpi_exchanges() if is_cmw_probe else nullcontext([])) as captured:
                async with sequence_lease(lease_categories) as lease_outcome:
                    # CMW uses the exact HAL resolved by the lock-time validator.
                    hal = locked_hal if is_cmw_probe else get_hal_service()
                    try:
                        result = await sequence.run(
                            ctx, hal, request.params, log=_log,
                            **({"resolved_binding": resolved_binding} if is_cmw_probe else {}),
                        )
                    except asyncio.CancelledError as exc:
                        if is_cmw_probe and isinstance(exc, ProbeCancelled):
                            step_results = [asdict(s) for s in exc.result.steps]
                            extra = exc.result.extra
                        raise
                    # Keep the completed/partial result even if transport release fails.
                    success = bool(result.success)
                    summary = result.summary
                    step_results = [asdict(s) for s in result.steps]
                    extra = result.extra
        except asyncio.CancelledError as exc:
            if is_cmw_probe and isinstance(exc, ProbeCancelled):
                step_results = [asdict(s) for s in exc.result.steps]
                extra = exc.result.extra
            # 请求取消也必须留下审计记录。CMW probe 显式携带部分结果；其他
            # 序列若尚未返回则不能声称拿到内部证据。完成安全收尾与 DB commit 后重抛。
            success = False
            summary = "Sequence cancelled"
            error_msg = summary
            extra.update(cancelled=True, partial_result_available=(
                is_cmw_probe and bool(step_results)))
            cancelled_exc = exc
        except Exception as e:  # noqa: BLE001
            if is_cmw_probe and isinstance(e, ProbePreflightRejected):
                step_results = [asdict(s) for s in e.result.steps]
                extra = e.result.extra
            # Sequence raised — record as failure, surface error to UI.
            success = False
            summary = f"Sequence aborted: {e}"
            error_msg = str(e)
            logger.exception("Sequence %s aborted with exception", key)
    finally:
        if is_cmw_probe:
            extra["formal_eligible"] = False
            extra["exchanges"] = [item.model_dump(mode="json") for item in captured]
            extra["release"] = (
                asdict(lease_outcome.base_station_release)
                if lease_outcome is not None and lease_outcome.base_station_release is not None
                else None
            )
        # asyncio.CancelledError 属于 BaseException，不会被上面的普通异常分支吞掉；
        # 但它仍必须释放破坏性诊断占位，避免进程永久 409。
        if unsafe_token is not None:
            release_unsafe_diagnostic(unsafe_token)

    duration_ms = int((time.monotonic() - started) * 1000)
    evidence = SequenceEvidence(
        summary=summary,
        duration_ms=duration_ms,
        log=log_buffer,
        steps=[SequenceStepEvidence(**step) for step in step_results],
        extra=extra,
    )

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
        sequence_evidence=evidence.model_dump(mode="json"),
        error_message=error_msg,
        duration_ms=duration_ms,
        run_by=request.run_by,
    )

    if cancelled_exc is not None:
        raise cancelled_exc

    return SequenceRunResponse(
        diagnostic_run_id=run.id,
        success=success,
        **evidence.model_dump(),
    )
