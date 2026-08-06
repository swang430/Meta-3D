"""Read-only P1-28 chamber truth-source and calibration reference audit."""
from __future__ import annotations

from typing import Any, Callable, Dict

from app.diagnostics.protocol import SequenceMetadata, SequenceRunResult, SequenceStepResult
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="暗室配置真值与校准引用审计",
    description=(
        "确认所选 LabProfile 的暗室绑定存在，并检查所有暗室作用域校准表是否引用了"
        "已删除的暗室。只读，不自动修复数据。"
    ),
    required_categories=[],
    params_schema=[],
    safe_during_test=True,
)


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    report = ctx.chamber_integrity
    if ctx.lab_profile_id is None or report is None:
        return SequenceRunResult(
            success=False,
            summary="必须选择 LabProfile 才能审计当前暗室配置。",
        )

    binding_detail = (
        f"LabProfile {ctx.lab_profile_name} → chamber {report.current_chamber_id}"
        if report.current_chamber_exists
        else "; ".join(report.errors) or "当前暗室绑定无效"
    )
    binding_step = SequenceStepResult(
        label="LabProfile 当前暗室绑定",
        success=report.current_chamber_exists and not report.errors,
        detail=binding_detail,
    )
    if report.orphan_references:
        orphan_detail = "; ".join(
            f"{table}: {', '.join(ids)}"
            for table, ids in sorted(report.orphan_references.items())
        )
    else:
        orphan_detail = "未发现引用不存在暗室的校准记录"
    orphan_step = SequenceStepResult(
        label="校准暗室引用完整性",
        success=report.orphan_count == 0,
        detail=orphan_detail,
    )
    for step in (binding_step, orphan_step):
        log(f"{'✓' if step.success else '✗'} {step.label}: {step.detail}")

    success = report.ok
    return SequenceRunResult(
        success=success,
        summary=(
            "暗室配置真值与校准引用完整性通过"
            if success
            else f"暗室配置完整性失败：{len(report.errors)} 个绑定错误，"
                 f"{report.orphan_count} 个孤儿暗室引用"
        ),
        steps=[binding_step, orphan_step],
        extra={
            "lab_profile_id": str(report.lab_profile_id),
            "current_chamber_id": (
                str(report.current_chamber_id) if report.current_chamber_id else None
            ),
            "orphan_references": report.orphan_references,
            "errors": report.errors,
        },
    )
