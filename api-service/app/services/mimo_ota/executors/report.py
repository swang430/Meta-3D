"""Phase 5: Report archival.

Replaces commissioning_service.phase5_report. Pulls phase results out of
TestExecution.measurements (written by precheck/reference/measure/analysis),
creates a TestReport row, and triggers PDFGenerator with a content-data
override so the executor doesn't need to retrofit ReportDataCollector for
MIMO_OTA-specific shapes.

If PDF generation fails (template missing, disk error, etc.) the execution
is still marked completed — the warning surfaces in the result payload so
the operator sees what happened, but a missing PDF should not roll back a
finished measurement.
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional

from app.models.report import ReportFormat, ReportType
from app.models.test_plan import TestExecution
from app.hal.base_station import ThroughputMetrics
from app.services.mimo_ota.executors._helpers import write_phase_result
from app.services.mimo_ota.path_loss_application import (
    parse_path_loss_application,
    path_loss_application_is_formally_verified,
    path_loss_application_message,
)
from app.services.mimo_ota.rf_kpi_trust import (
    RF_KPI_TRUST_SCHEMA_VERSION,
    build_rf_kpi_trust,
    measurement_provenance_is_explicit_real,
    parse_rf_kpi_trust,
    rf_kpi_scope_is_verified,
)
from app.services.mimo_ota.quiet_zone_evidence import (
    QUIET_ZONE_EVIDENCE_SCHEMA_VERSION,
    build_quiet_zone_evidence,
    parse_quiet_zone_evidence,
    quiet_zone_evidence_is_formally_verified,
)
from app.services.mimo_ota.throughput_trust import (
    required_throughput_scope as _required_throughput_scope,
    throughput_scope_is_verified,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    BASE_STATION_EXECUTION_EVIDENCE_FIELD,
    base_station_expected_scope_from_evidence,
    base_station_metric_projection_required,
    project_base_station_metrics_by_position,
)
from app.services.report_service import (
    ReportService,
    THROUGHPUT_TRUST_SCHEMA_VERSION,
    build_base_station_metric_projection_attestation,
)
from app.services.test_execution import (
    IStepExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepExecutionStatus,
    register_executor,
)
from app.services.execution_evidence_outcome import (
    execution_evidence_blocks_formal_outputs,
    project_execution_evidence_outcome,
)
from app.schemas.mimo_ota.config import MIMOOTAStepType
from app.utils.human_time import format_human_local_timestamp

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportLifecycleProjection:
    """报告构造期间使用的只读最终生命周期。

    REPORT 仍在运行时，ORM 行必须保持原状态以保留取消裁决；PDF/content_data
    则需要描述本相位成功结束后的最终状态。投影只承载这三个同行事实，不写数据库。
    """

    status: str
    completed_at: Optional[datetime]
    duration_sec: Optional[float]


def _effective_lifecycle(
    execution: Any,
    projection: Optional[ReportLifecycleProjection],
) -> ReportLifecycleProjection:
    if projection is not None:
        return ReportLifecycleProjection(
            status=str(projection.status),
            completed_at=projection.completed_at,
            duration_sec=projection.duration_sec,
        )
    return ReportLifecycleProjection(
        status=str(getattr(execution, "status", "pending")),
        completed_at=getattr(execution, "completed_at", None),
        duration_sec=getattr(execution, "duration_sec", None),
    )


def _execution_summary(
    *,
    lifecycle: ReportLifecycleProjection,
    overall_pass: bool,
    verdict_unknown: bool,
    started_at: Optional[datetime],
    now: datetime,
) -> tuple[Dict[str, Any], str]:
    """把生命周期和正式判决收敛成唯一四态（加 pending 传输态）。"""

    status = lifecycle.status.lower()
    if status == "failed":
        outcome = "failed"
        pass_rate: Optional[float] = 0.0
    elif status == "completed":
        if overall_pass:
            outcome = "passed"
            pass_rate = 100.0
        elif verdict_unknown:
            outcome = "undetermined"
            pass_rate = None
        else:
            outcome = "failed"
            pass_rate = 0.0
    elif status == "pending":
        outcome = "pending"
        pass_rate = None
    else:
        # running/cancelled/skipped 以及未来新增但未明确定义的非终态都不得
        # 冒充已完成判决；统一保守显示为 incomplete。
        outcome = "incomplete"
        pass_rate = None

    duration_sec = (
        float(lifecycle.duration_sec)
        if lifecycle.duration_sec is not None
        else None
    )
    summary = {
        "total_executions": 1,
        "passed": 1 if outcome == "passed" else 0,
        "failed": 1 if outcome == "failed" else 0,
        "pending": 1 if outcome == "pending" else 0,
        "undetermined": 1 if outcome == "undetermined" else 0,
        "incomplete": 1 if outcome == "incomplete" else 0,
        "pass_rate": pass_rate,
        "total_duration_sec": duration_sec,
        "first_execution": started_at.isoformat() if started_at else None,
        "last_execution": (
            lifecycle.completed_at.isoformat()
            if lifecycle.completed_at is not None
            else None
        ),
    }
    return summary, outcome


def _settle_execution_lifecycle(
    db: Any,
    execution: Any,
    completed_projection: ReportLifecycleProjection,
) -> ReportLifecycleProjection:
    """以数据库条件更新裁决 REPORT 完成与外部终态谁先发生。

    `request_cancel()` 在独立会话中把 running 改为 cancelled。这里仅允许
    running -> completed；因此两边只能有一个赢家，不能再由 runner 会话
    的旧 ORM 快照把 cancelled 覆盖回 completed。
    """

    updated = (
        db.query(TestExecution)
        .filter(
            TestExecution.id == execution.id,
            TestExecution.status == "running",
        )
        .update(
            {
                TestExecution.status: completed_projection.status,
                TestExecution.completed_at: completed_projection.completed_at,
                TestExecution.duration_sec: completed_projection.duration_sec,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    db.expire(execution)
    db.refresh(execution)

    if updated == 1:
        return completed_projection

    observed = _effective_lifecycle(execution, None)
    if (
        observed.duration_sec is None
        and observed.completed_at is not None
        and getattr(execution, "started_at", None) is not None
    ):
        duration_end = observed.completed_at
        started_at = execution.started_at
        if duration_end.tzinfo is not None and started_at.tzinfo is None:
            duration_end = duration_end.replace(tzinfo=None)
        elif duration_end.tzinfo is None and started_at.tzinfo is not None:
            duration_end = duration_end.replace(tzinfo=started_at.tzinfo)
        derived_duration = (duration_end - started_at).total_seconds()
        # 取消方等外部终态 writer 可能只写 status/completed_at。报告不能
        # 私自持有第三份时长真值：仅在观察到的同一终态/完成时间仍成立时，
        # 用数据库条件更新补齐 duration，再从数据库重读。
        db.query(TestExecution).filter(
            TestExecution.id == execution.id,
            TestExecution.status == observed.status,
            TestExecution.completed_at == observed.completed_at,
            TestExecution.duration_sec.is_(None),
        ).update(
            {TestExecution.duration_sec: derived_duration},
            synchronize_session=False,
        )
        db.commit()
        db.expire(execution)
        db.refresh(execution)
        observed = _effective_lifecycle(execution, None)
    return observed


@register_executor(MIMOOTAStepType.REPORT.value)
class ReportExecutor(IStepExecutor):
    """Generate a PDF report from prior phases, mark execution completed."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        execution = context.test_execution
        now = datetime.now(timezone.utc)
        completed_at = now.replace(tzinfo=None)
        duration_sec: Optional[float] = getattr(execution, "duration_sec", None)
        if execution.started_at:
            delta_end = now if execution.started_at.tzinfo is not None else completed_at
            duration_sec = (delta_end - execution.started_at).total_seconds()
        lifecycle_projection = ReportLifecycleProjection(
            status="completed",
            completed_at=completed_at,
            duration_sec=duration_sec,
        )
        report_id_human = (
            f"MIMO_OTA-{str(execution.id)[:8]}-"
            + format_human_local_timestamp(now, fmt="%Y%m%d%H%M%S")
        )

        warnings: List[str] = []
        report_db_id: Optional[str] = None
        report_file_path: Optional[str] = None
        report = None
        svc: Optional[ReportService] = None
        content_data: Optional[Dict[str, Any]] = None
        settled_lifecycle: Optional[ReportLifecycleProjection] = None

        case_name = _lookup_case_name(context, execution)
        try:
            # 报告本身属于正式结论，必须先应用 SCPI AND 门再读取
            # validation_pass；否则 PDF 会比 runner 的最终判定早一步写出假 PASS。
            from app.services.test_case_runner import _finalize_scpi_acceptance

            _finalize_scpi_acceptance(execution)
            context.db.commit()
            content_data = _build_mimo_ota_content_data(
                execution,
                now,
                case_name,
                lifecycle_projection=lifecycle_projection,
            )
            svc = ReportService()
            report = svc.create_report(
                db=context.db,
                # ARCH-1 S2: MIMO_OTA 执行来自 TestCase 不挂 TestPlan, 标题
                # 用快照用例名 (执行时的名字), 不再写死 "Unknown Plan"
                title=f"MIMO OTA Test Report — {case_name}",
                report_type=ReportType.SINGLE_EXECUTION.value,
                format=ReportFormat.PDF.value,
                generated_by="mimo_ota.executors.report",
                test_plan_id=execution.test_plan_id,
                test_execution_ids=[execution.id],
                # 正式结论尚未裁决，pending 行不能先公开 completed 投影。
                content_data={},
            )
            report_db_id = str(report.id)
            def _resolve_lifecycle(
                projection: ReportLifecycleProjection,
            ) -> ReportLifecycleProjection:
                nonlocal settled_lifecycle
                settled_lifecycle = _settle_execution_lifecycle(
                    context.db,
                    execution,
                    projection,
                )
                return settled_lifecycle

            generated = svc.generate_report(
                db=context.db,
                report_id=report.id,
                content_data_override=content_data,
                execution_lifecycle_projection=lifecycle_projection,
                execution_lifecycle_resolver=_resolve_lifecycle,
            )
            if generated and generated.file_path:
                report_file_path = generated.file_path
                logger.info(
                    "[%s] Phase 5: PDF generated → %s (%d bytes)",
                    execution.id, generated.file_path, generated.file_size_bytes or 0,
                )
            else:
                warnings.append("PDF generation returned no file_path")
        except Exception as e:  # noqa: BLE001
            # Don't tank the execution — log + warn so operator can re-trigger
            # report from the GUI without re-running the test.
            warnings.append(f"PDF generation failed: {e}")
            logger.exception("[%s] Phase 5: PDF generation failed", execution.id)

        # 生成器异常时还没到内部裁决点；测量生命周期仍需独立收口。
        if settled_lifecycle is None:
            settled_lifecycle = _settle_execution_lifecycle(
                context.db,
                execution,
                lifecycle_projection,
            )

        result: Dict[str, Any] = {
            "report_id": report_id_human,
            "report_db_id": report_db_id,
            "report_file_path": report_file_path,
            "generated_at": now.isoformat(),
            "report_type": "single_execution",
            "format": "pdf" if report_file_path else "stub",
        }
        if warnings:
            result["warnings"] = warnings

        write_phase_result(execution, "report", result)

        # 生命周期已由上面的数据库条件更新裁决；这里只持久化 report 相位载荷。
        context.db.commit()

        logger.info("[%s] Phase 5: report_id=%s pdf=%s",
                    execution.id, report_id_human, bool(report_file_path))
        return StepExecutionResult(
            status=StepExecutionStatus.SUCCESS,
            measurements=result,
            warnings=warnings or None,
        )


def _lookup_case_name(context: StepExecutionContext, execution: Any) -> str:
    """快照 TestCase 名 (ARCH-1 S2)。

    模型上的 test_case relationship 是注释掉的 (models/test_plan.py), 不能
    走属性 — 显式按 test_case_id 查一行。查不到 (孤立执行 / 快照被删) 时
    兜底"未命名用例", 不再是 "Unknown Plan"。
    """
    try:
        if execution.test_case_id is not None:
            from app.models.test_plan import TestCase
            case = (
                context.db.query(TestCase)
                .filter(TestCase.id == execution.test_case_id)
                .first()
            )
            if case is not None and case.name:
                return case.name
    except Exception:  # noqa: BLE001 — 名字查询失败不该影响报告生成
        logger.warning("[%s] Phase 5: case name lookup failed", execution.id)
    return "未命名用例"


def _trp_source_label(src, verified) -> str:
    """把「来源」这一栏渲染成人能看懂、且不说假话的文字。

    ⚠️ **以验证状态为准，不单看 src**（外审）：
    - `verified is True` 才允许说「实测」；
    - `verified is False` → 按 src 区分是「模拟驱动」还是「无 SA 兜底」；
    - `verified is None` → 一律「未知」，**哪怕 src 写着 hal_signal_analyzer** ——
      那个标签在 `trp_verified` 引入之前对真 SA 和 mock SA 是同一个值，分不出来。
    """
    if verified is True:
        return "真实信号分析仪（实测）"
    if verified is False:
        if src == "mock":
            return "无信号分析仪，套用兜底默认值（非实测）"
        return "信号分析仪的模拟驱动（仿真值，非实测）"
    return "未知（历史数据未区分真实/模拟信号分析仪）"


def _build_mimo_ota_content_data(
    execution: Any,
    now: datetime,
    case_name: Optional[str] = None,
    *,
    lifecycle_projection: Optional[ReportLifecycleProjection] = None,
) -> Dict[str, Any]:
    """Pack the 4 prior phase results into the dict shape PDFGenerator expects.

    PDFGenerator._auto_generate_sections inspects keys (test_plan,
    execution_summary, statistics, table_data, step_results) and emits one
    PDF section per recognized key. We populate every key for which we have
    real data; unrecognized keys are ignored harmlessly.
    """
    measurements = execution.measurements or {}
    phases = measurements.get("phases", {})
    precheck = phases.get("precheck", {}) or {}
    reference = phases.get("reference", {}) or {}
    measure = phases.get("measure", {}) or {}
    analysis = phases.get("analysis", {}) or {}
    evidence_outcome = project_execution_evidence_outcome(execution)
    diagnostic_execution = execution_evidence_blocks_formal_outputs(execution)

    # ARCH-1 S2: MIMO_OTA 执行是 TestCase 制不挂 TestPlan, 报告首段的
    # "名字"就是快照用例名 (caller 经 _lookup_case_name 查好传入;
    # 旧二参调用 / 查不到时兜底"未命名用例", 不再是 "Unknown Plan")
    display_name = case_name or "未命名用例"
    lifecycle = _effective_lifecycle(execution, lifecycle_projection)
    plan_info = {
        "name": display_name,
        "description": "—",
        "status": lifecycle.status,
        "created_by": "system",
    }

    # P1-22: 通过谓词换 canonical 源 — analysis 执行器写的是
    # TestExecution.validation_pass 列 (= verdict in ("PASS","MARGINAL")),
    # 从不写 payload 的 "overall_pass" 键 (旧读法恒 False → 报告恒 failed/0.0%)。
    # 列缺失 (老执行 / analysis 未跑到 / 测试 stub) 时兜 payload 的 verdict
    # 三值字面量；两端都没有或 verdict 未知 → undetermined，不伪造 FAIL/0%。
    _validation_pass = getattr(execution, "validation_pass", None)
    _analysis_verdict = analysis.get("verdict")
    if _validation_pass is not None:
        overall_pass = bool(_validation_pass)
    else:
        overall_pass = _analysis_verdict in ("PASS", "MARGINAL")
    duration_sec = (
        float(lifecycle.duration_sec)
        if lifecycle.duration_sec is not None
        else None
    )

    # 只有显式的执行级布尔判决，或 ANALYSIS 写出的 PASS/MARGINAL/FAIL，
    # 才能把 completed 映射为正式通过/失败。手工跳过 ANALYSIS 直接跑
    # REPORT 时 verdict 缺失，语义是尚未判定，而不是 FAIL/0%。
    verdict_unknown = (
        _validation_pass is None
        and _analysis_verdict not in ("PASS", "MARGINAL", "FAIL")
    )
    if diagnostic_execution:
        overall_pass = False
        verdict_unknown = True

    # Aggregate per-azimuth stats into one stat-row per KPI
    raw_azimuth_results = measure.get("azimuth_results")
    azimuth_results: List[Dict[str, Any]] = (
        [row for row in raw_azimuth_results if isinstance(row, dict)]
        if isinstance(raw_azimuth_results, list)
        else []
    )
    raw_execution_config = getattr(execution, "config", None)
    execution_config = (
        raw_execution_config if isinstance(raw_execution_config, dict) else {}
    )
    base_station_evidence = execution_config.get(
        BASE_STATION_EXECUTION_EVIDENCE_FIELD
    )
    base_station_evidence_required = base_station_metric_projection_required(
        execution_config
    )
    expected_base_station_config, expected_positions = (
        base_station_expected_scope_from_evidence(base_station_evidence)
    )
    base_station_projection = (
        project_base_station_metrics_by_position(
            base_station_evidence,
            expected_config=expected_base_station_config,
            expected_positions=expected_positions,
            execution_config=execution_config,
        )
        if base_station_evidence_required
        and expected_base_station_config is not None
        else []
    )
    projection_by_azimuth = {
        row["position"]["azimuth_deg"]: row for row in base_station_projection
    }

    # P1-63: decide trust before touching historical metric values. Old or
    # malformed rows must reach the UNKNOWN/N/A path instead of raising while
    # min/max/sum or string formatting is still running.
    _rf_kpi_trust = parse_rf_kpi_trust(measure.get("rf_kpi_trust"))
    _rf_kpi_formally_verified = rf_kpi_scope_is_verified(measure)
    if not _rf_kpi_formally_verified:
        requested_azimuths = (
            _rf_kpi_trust["requested_azimuths"]
            if _rf_kpi_trust is not None
            else [
                float(row["azimuth_deg"])
                for row in azimuth_results
                if isinstance(row.get("azimuth_deg"), (int, float))
                and not isinstance(row.get("azimuth_deg"), bool)
                and math.isfinite(float(row["azimuth_deg"]))
            ]
        )
        _rf_kpi_trust = build_rf_kpi_trust(
            requested_azimuths=requested_azimuths,
            azimuth_results=[],
            source="unknown",
        )

    def _finite_report_number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    statistics = {}
    table_data = []
    if azimuth_results:
        for kpi_key, kpi_label, unit in [
            ("rsrp_dbm", "RSRP", "dBm"),
            ("sinr_db", "SINR", "dB"),
            ("throughput_mbps", "Throughput", "Mbps"),
            ("rank_indicator", "RankIndicator", ""),
        ]:
            if (
                kpi_key in {"rsrp_dbm", "sinr_db", "rank_indicator"}
                and not _rf_kpi_formally_verified
            ):
                values = []
            elif kpi_key == "throughput_mbps" and base_station_evidence_required:
                values = [
                    metric.formal_value
                    for row in base_station_projection
                    if (metric := row["dl_throughput_mbps"]).status == "trusted"
                ]
            else:
                values = [
                    number
                    for row in azimuth_results
                    if isinstance(row, dict)
                    and (number := _finite_report_number(row.get(kpi_key)))
                    is not None
                ]
            if values:
                vmin, vmax = min(values), max(values)
                vavg = sum(values) / len(values)
                vstd = _std(values)
                statistics[f"{kpi_label}_{unit}".strip("_")] = {
                    "metric_name": f"{kpi_label} ({unit})" if unit else kpi_label,
                    "mean": round(vavg, 3),
                    "median": round(median(values), 3),
                    "std": round(vstd, 3),
                    "min": round(vmin, 3),
                    "max": round(vmax, 3),
                    "count": len(values),
                }

        trusted_bler_values = [
            metric.formal_value
            for row in base_station_projection
            if (metric := row["dl_bler_percent"]).status == "trusted"
        ]
        if trusted_bler_values:
            statistics["BLER_%"] = {
                "metric_name": "BLER (%)",
                "mean": round(sum(trusted_bler_values) / len(trusted_bler_values), 3),
                "median": round(median(trusted_bler_values), 3),
                "std": round(_std(trusted_bler_values), 3),
                "min": round(min(trusted_bler_values), 3),
                "max": round(max(trusted_bler_values), 3),
                "count": len(trusted_bler_values),
            }

        for a in azimuth_results:
            def _format_metric(value: Any, digits: int, *, visible: bool = True) -> str:
                numeric = _finite_report_number(value) if visible else None
                return "N/A" if numeric is None else f"{numeric:.{digits}f}"

            base_station_row = projection_by_azimuth.get(
                _finite_report_number(a.get("azimuth_deg"))
            )
            throughput_value = a.get("throughput_mbps")
            bler_value = None
            if base_station_evidence_required:
                throughput_trust = (
                    base_station_row.get("dl_throughput_mbps")
                    if isinstance(base_station_row, dict)
                    else None
                )
                bler_trust = (
                    base_station_row.get("dl_bler_percent")
                    if isinstance(base_station_row, dict)
                    else None
                )
                throughput_value = (
                    throughput_trust.formal_value
                    if getattr(throughput_trust, "status", None) == "trusted"
                    else None
                )
                bler_value = (
                    bler_trust.formal_value
                    if getattr(bler_trust, "status", None) == "trusted"
                    else None
                )
            table_row = {
                "Azimuth (°)": _format_metric(a.get("azimuth_deg"), 1),
                "RSRP (dBm)": _format_metric(
                    a.get("rsrp_dbm"), 1, visible=_rf_kpi_formally_verified
                ),
                "SINR (dB)": _format_metric(
                    a.get("sinr_db"), 1, visible=_rf_kpi_formally_verified
                ),
                "Throughput (Mbps)": _format_metric(throughput_value, 1),
                "RI": _format_metric(
                    a.get("rank_indicator"), 2, visible=_rf_kpi_formally_verified
                ),
            }
            if base_station_evidence_required:
                table_row["BLER (%)"] = _format_metric(bler_value, 1)
            table_data.append(table_row)

    # P1-64: ProbePattern peak spread is a diagnostic proxy, not a multi-point
    # quiet-zone field scan. Historical booleans/source labels cannot promote
    # it; malformed or absent snapshots are rewritten to canonical unavailable.
    _qz_evidence = parse_quiet_zone_evidence(precheck.get("quiet_zone_evidence"))
    if _qz_evidence is None:
        _qz_evidence = build_quiet_zone_evidence(None)
    _qz_verified = quiet_zone_evidence_is_formally_verified(_qz_evidence)
    _trp_verified = reference.get("trp_verified")
    if _trp_verified is None:
        # "mock" = no SA → unverified; legacy "hal_signal_analyzer" didn't
        # distinguish real vs mock SA → unknown (None), rendered as not-verified.
        _src = reference.get("measurement_source")
        if _src == "mock":
            _trp_verified = False            # 压根没有 SA，套的兜底值
        elif _src == "hal_signal_analyzer_mock":
            _trp_verified = False            # SA 挂着但是 mock 驱动，功率是仿真的
        else:
            # ⚠️ 外审纠正：`hal_signal_analyzer` **不能当成已验证**。
            #    在 `trp_verified` 这个字段引入之前，写入端对真 SA 和 mock SA
            #    **写的是同一个值** —— 历史记录里这个标签既可能是真实测、
            #    也可能是仿真值，**分不出来**。当成 True 会把历史上那些 mock SA
            #    的记录判成实测、数值照印，那是我新引入的一个说谎方向。
            _trp_verified = None             # 来源不明 → 未知，按未确认处理
    _pl_verified_raw = measure.get("path_loss_verified")
    _pl_use_mock = measure.get("path_loss_calibration_use_mock")
    if _pl_verified_raw is True and _pl_use_mock is False:
        _pl_verified = True
    elif _pl_verified_raw is False or _pl_use_mock is True:
        _pl_verified = False
    else:
        # Before P1-27, even ``path_loss_verified=True`` did not distinguish a
        # real certificate from a mock one. Missing/NULL provenance therefore
        # stays UNKNOWN; neither a cert ID nor the legacy boolean can recover it.
        _pl_verified = None
    # P1-62: “是否应用”与“是否可信”是两个独立事实。报告只消费执行当时
    # 保存的应用快照；旧/畸形记录统一降级 unknown，绝不从证书 ID、补偿
    # 数值或当前数据库中的证书状态反推。
    _path_loss_application = parse_path_loss_application(
        measure.get("path_loss_application")
    )
    _path_loss_application_text = path_loss_application_message(
        _path_loss_application
    )
    _path_loss_formally_verified = (
        _pl_verified is True
        and path_loss_application_is_formally_verified(_path_loss_application)
    )
    _path_loss_value_visible = _path_loss_formally_verified

    # P1-54: 吞吐的数值与“这次是否真的读到”必须同行。历史执行没有该字段，
    # 也可能正是把缺测默认 0.0 当样本的旧数据，所以只能 fail-closed；不能从
    # 数值是否为 0、analysis 旧 verdict 或 measurement_verified 反推可信性。
    _throughput_verified = measure.get("throughput_verified")
    required_throughput_scope = _required_throughput_scope(measure)

    # P1-59: P1-54 的布尔值只能证明“读到了一个有限吞吐值”，不能证明
    # CA 执行读的是全部 NR cells 而非 PCell。正式报告必须同时核对载波数量、
    # measure 顶层范围和每个方位的同行范围；历史记录缺任一证据都 fail-closed。
    throughput_scope_verified = throughput_scope_is_verified(measure)
    if base_station_evidence_required:
        _throughput_verified = (
            len(base_station_projection) == len(expected_positions)
            and bool(expected_positions)
            and all(
                row["dl_throughput_mbps"].status == "trusted"
                for row in base_station_projection
            )
        )
    elif _throughput_verified is True and (
        not throughput_scope_verified
        or not measurement_provenance_is_explicit_real(measure)
    ):
        _throughput_verified = False

    if diagnostic_execution:
        # A diagnostic run remains downloadable as an audit artifact, so the
        # whole server trust envelope must be internally consistent as
        # non-formal—not merely hide cells while leaving promotable flags or
        # formal values in sibling fields.
        _path_loss_application = parse_path_loss_application(None)
        _path_loss_formally_verified = False
        _path_loss_value_visible = False
        _throughput_verified = False
        _rf_kpi_trust = build_rf_kpi_trust(
            requested_azimuths=[
                float(row["azimuth_deg"])
                for row in azimuth_results
                if _finite_report_number(row.get("azimuth_deg")) is not None
            ],
            azimuth_results=[],
            source="unknown",
        )
        _rf_kpi_formally_verified = False
        _qz_evidence = build_quiet_zone_evidence(None)
        _qz_verified = False

    # A formal KPI/report verdict requires explicit proof that the applied
    # path-loss certificate was real *and* every azimuth contributed a trusted
    # throughput sample. Historical, mock, bypass and missing-read executions
    # remain auditable, but their numerical KPI values cannot be re-published
    # as a formal PASS/FAIL after report regeneration.
    reported_verdict = "UNKNOWN" if verdict_unknown else _analysis_verdict
    if (
        diagnostic_execution
        or not _path_loss_formally_verified
        or _throughput_verified is not True
        or not _rf_kpi_formally_verified
        or not _qz_verified
    ):
        overall_pass = False
        verdict_unknown = True
        reported_verdict = "UNKNOWN"

        # 每个 KPI 族只由自己的证据门决定是否可见。RF KPI 不完整会阻止
        # 总体 PASS/FAIL，但不能顺带抹掉已经通过独立 P1-54/P1-59 门的真实
        # 吞吐量；反方向同理。路损不是 explicit-real 时，所有补偿后数值仍
        # 整体隐藏，避免把未经可信校准的读数重新发布为正式工程量。
        if diagnostic_execution:
            statistics = {}
            hidden_table_metrics = (
                "RSRP (dBm)",
                "SINR (dB)",
                "Throughput (Mbps)",
                "RI",
                "BLER (%)",
            )
        elif not _path_loss_formally_verified:
            statistics = {}
            hidden_table_metrics = (
                "RSRP (dBm)", "SINR (dB)", "Throughput (Mbps)", "RI"
            )
        else:
            hidden_table_metrics: tuple[str, ...] = ()
            if _throughput_verified is not True:
                statistics.pop("Throughput_Mbps", None)
                hidden_table_metrics += ("Throughput (Mbps)",)
            if not _rf_kpi_formally_verified:
                for metric_key in ("RSRP_dBm", "SINR_dB", "RankIndicator"):
                    statistics.pop(metric_key, None)
                hidden_table_metrics += ("RSRP (dBm)", "SINR (dB)", "RI")

        for row in table_data:
            for metric in hidden_table_metrics:
                row[metric] = "N/A"

    summary, report_outcome = _execution_summary(
        lifecycle=lifecycle,
        overall_pass=overall_pass,
        verdict_unknown=verdict_unknown,
        started_at=getattr(execution, "started_at", None),
        now=now,
    )

    def _verified_label(flag, verified_note: str, unverified_note: str) -> str:
        """P1-12 三值标志 → 报告可读标注。None (历史数据判不了) 也要显式说出来,
        不能沉默 —— 沉默正是 P2-21 要修的病。"""
        if flag is True:
            return f"已验证 ({verified_note})"
        if flag is False:
            return f"未验证 ({unverified_note})"
        return "未知 (历史数据未区分真实/兜底)"

    def _serialized_base_station_metric(metric: Any) -> Dict[str, Any]:
        if not diagnostic_execution:
            return metric.model_dump(mode="json")
        diagnostic_value = (
            metric.diagnostic_value
            if metric.diagnostic_value is not None
            else metric.formal_value
        )
        return metric.model_copy(
            update={
                "status": "diagnostic",
                "formal_value": None,
                "diagnostic_value": diagnostic_value,
                "reason": "execution_qualification_diagnostic",
            }
        ).model_dump(mode="json")

    def _cell(v):
        """parameters 单元格值卫生 (内审 F1/F3):
        - XML 转义统一由 PDFGenerator 的 Paragraph 入口负责；这里保留原始字符串，
          避免 MIMO 路径预转义后被共享渲染器二次转义成可见的 ``&lt;``。
        - None → "—" (中文报告里英文字面 "None" 含义模糊; .get 默认值只兜键
          缺失, 兜不住显式 null — 值形态三态)。
        - 列表逐条同处理 (messages; 渲染器 json.dumps 后统一转义)。"""
        if v is None:
            return "—"
        if isinstance(v, list):
            return [_cell(x) for x in v]
        return v

    def _path_loss_verification_label() -> str:
        if _path_loss_value_visible:
            return "已验证 (真实来源路损校准证书)"
        if _path_loss_application["status"] == "unknown":
            return f"未知 ({_path_loss_application_text})"
        return f"未验证 ({_path_loss_application_text})"

    _path_loss_provenance_labels = {
        "real": "真实来源",
        "simulated": "模拟来源",
        "unknown": "来源未知",
        "missing": "无匹配证书",
    }

    if _qz_verified:
        _precheck_result = (
            "PASS" if precheck.get("overall_pass") is True
            else "FAIL" if precheck.get("overall_pass") is False
            else "UNKNOWN"
        )
        _precheck_messages = precheck.get("messages") or []
    else:
        # 旧 overall_pass/quiet_zone_pass 与自由文本可能来自固定 0.7 或
        # ProbePattern 代理。只有当前写方同行保存的运行门失败可以继续发布
        # FAIL；静区结论与旧提示一律换成规范 UNKNOWN，避免同一份报告顶层
        # UNKNOWN、步骤内部却又出现 PASS/FAIL 与代理数值。
        _precheck_result = (
            "FAIL" if precheck.get("operational_ready") is False else "UNKNOWN"
        )
        def _is_legacy_quiet_zone_claim(message: Any) -> bool:
            if not isinstance(message, str):
                return False
            normalized = message.casefold()
            return any(marker in normalized for marker in (
                "quiet zone",
                "quiet-zone",
                "quiet_zone",
                "静区",
                "probe pattern",
                "probe_pattern",
                "fallback_default",
            ))

        _precheck_messages = [
            message
            for message in (precheck.get("messages") or [])
            if not _is_legacy_quiet_zone_claim(message)
        ] + [
            "静区结论未判定：无权威多点场扫描证据；"
            "历史提示未作为正式证据发布。"
        ]

    # P2-21: 渲染载荷整体放 parameters 下 (PDFGenerator 步骤区只渲染 name/
    # step_name 与 parameters 的键值表, 顶层键进不了 PDF) —— P1-12 的三个可信化
    # 标志因此从未生效过, 现场拿假干净报告做判断。同一修法 P1-22 已在 analysis
    # 站点验证 (verdict 进 parameters); 本次把 precheck/reference/measure 三站点
    # 收敛到同构, 顶层渲染键删干净 (step_results 唯一消费方是 PDFGenerator,
    # 留顶层就是死载荷双写)。
    step_results = [
        {"phase": "precheck", "name": "precheck (预检)",
         "parameters": {
             "结果": _precheck_result,
             # ⚠️ 旧执行可能保存固定 0.7 或 ProbePattern 代理；当前
             #    写方只保存 N/A 与独立 proxy。无权威多点场扫描时，
             #    新旧数字都不能印成正式静区波纹。
             "静区波纹 (±dB)": (
                 _cell(precheck.get("quiet_zone_ripple_db")) if _qz_verified is True
                 else "—（未实测，不印兜底值）"
             ),
             # P1-12: 非 True 时波纹是遗留默认值, 静区从未实测 —— 必须标注。
             "静区验证": _verified_label(
                 _qz_verified, "权威多点场扫描", "无权威多点场扫描证据"),
             # ⭐ 预检那两句「为什么算通过」的原话（P1-48）：库里早就存着
             #    （cal_pass_reason / dut_pass_reason），报告一直没取。
             #    其中一句会明说「这是 mock」—— 那正是读者最该看到的。
             "校准门理由": _cell(precheck.get("cal_pass_reason") or "未记录"),
             "DUT 门理由": _cell(precheck.get("dut_pass_reason") or "未记录"),
             "提示": _cell(_precheck_messages),
         }},
        {"phase": "reference", "name": "reference (参考测量)",
         "parameters": {
             # ⚠️ 只有确认是真实测的那一档才印数值（P1-48）：
             #   「假」= 仿真或兜底值；「空」= 历史记录来源不明，两者都可能是编的。
             #   光加一句「未验证」的标注不够 —— 数字印在那儿，读者会当成测量结果。
             "参考 TRP (dBm)": (
                 _cell(reference.get("measured_trp_dbm")) if _trp_verified is True
                 else "—（未确认来源，不印数值）"
             ),
             "补偿 (dB)": (
                 _cell(reference.get("compensation_factor_db")) if _trp_verified is True
                 else "—（未确认来源，不印数值）"
             ),
             # ⚠️ 标签由**验证状态**派生，不单独看 source（外审 P1-2）：
             #    存了 trp_verified=False 而 source 仍是 hal_signal_analyzer 的历史记录，
             #    单看 source 会渲染成「真实信号分析仪（实测）」，跟旁边的
             #    「验证：未验证」又打起来。两栏必须同源。
             "TRP 来源": _cell(_trp_source_label(
                 reference.get("measurement_source"), _trp_verified)),
             # P1-12: mock/兜底 TRP → 参考数据不是实测, 必须标注。
             "TRP 验证": _verified_label(
                 _trp_verified, "真实信号分析仪", "mock/兜底值"),
         }},
        {"phase": "measure", "name": "measure (吞吐测量)",
         "parameters": {
             "频率 (GHz)": _cell(measure.get("frequency_ghz")),
             "MIMO 配置": _cell(measure.get("mimo_config")),
             "CDL 模型": _cell(measure.get("cdl_model_name")),
             # ⚠️ 同上：没有路损证书时存的是兜底值 0.0，印出来会被当成「补偿过了」
             "路损补偿 (dB)": (
                 _cell(measure.get("path_loss_compensation_db"))
                 if _path_loss_value_visible
                 else "—（补偿数值不展示）"
             ),
             "路损应用": _path_loss_application_text,
             "路损证书 ID": _cell(_path_loss_application["certificate_id"]),
             "路损来源": _path_loss_provenance_labels[
                 _path_loss_application["provenance"]
             ],
             # P1-62: 标签与应用快照同源，不能再由单一 verified 布尔值把
             # “已应用但来源未知”叙述成“无证书/未补偿”。
             "路损验证": _path_loss_verification_label(),
             "测量验证": _verified_label(
                 measure.get("measurement_verified"),
                 "真实仪器链",
                 "Mock/缺失仪器, KPI 为 N/A",
             ),
             "吞吐验证": _verified_label(
                 _throughput_verified,
                 "各方位均有仪表有效读数",
                 "存在缺测/无效读数, 吞吐 KPI 为 N/A",
             ),
             "RF KPI 验证": _verified_label(
                 _rf_kpi_formally_verified,
                 "RSRP/SINR/RI 逐指标、逐方位真实读数完整",
                 "缺少完整真实读数, RSRP/SINR/RI 为 N/A",
             ),
             # ⭐ 逐台点名哪几台是模拟的（P1-48）：这份名单**早就存在库里**
             #    （measure 那格的 simulated_sources），只是报告一直没取。
             #    只说「未验证」读者不知道是哪个环节出的问题。
             "模拟来源": (
                 "、".join(measure.get("simulated_sources") or [])
                 or ("无（全链真实仪器）" if measure.get("simulated_sources") is not None
                     else "未知（历史数据未记录）")
             ),
             "已测方位数": len(azimuth_results),
         }},
        {"phase": "analysis",
         # P1-22: verdict 三值放渲染器可达位置; 旧 overall_pass /
         # pass_criteria_summary 是全仓无写方的死键, 删站点。
         "name": "analysis",
         "parameters": {"verdict": reported_verdict}},
    ]

    serialized_base_station_projection = [
        {
            "position": row["position"],
            "metrics": {
                key: _serialized_base_station_metric(metric)
                for key, metric in row["metrics"].items()
            },
            "dl_throughput_mbps": _serialized_base_station_metric(
                row["dl_throughput_mbps"]
            ),
            "dl_bler_percent": _serialized_base_station_metric(
                row["dl_bler_percent"]
            ),
        }
        for row in base_station_projection
    ]
    base_station_metric_projection_attestation = (
        build_base_station_metric_projection_attestation(
            base_station_evidence,
            serialized_base_station_projection,
        )
    )

    title_suffix = {
        "diagnostic": " — 诊断审计",
        "invalid": " — 证据无效",
    }.get(evidence_outcome.compatibility_classification, "")
    return {
        "title": f"MIMO OTA Test Report — {plan_info['name']}{title_suffix}",
        # P1-22 (Codex #256): 报告类型进 content_data — PDFGenerator 靠它分流
        # 计划口径/用例口径的字段标签 (名字有无判不了型: 本路径恒有名字)。
        "report_type": "single_execution",
        "report_family": "mimo_ota",
        "execution_classification": (
            evidence_outcome.qualification_classification
        ),
        "execution_evidence_outcome": evidence_outcome.model_dump(mode="json"),
        "calibration_trust_schema_version": 1,
        "formal_path_loss_verified": _path_loss_formally_verified,
        "path_loss_application": _path_loss_application,
        "throughput_trust_schema_version": THROUGHPUT_TRUST_SCHEMA_VERSION,
        "formal_throughput_verified": _throughput_verified is True,
        "base_station_metric_trust_schema_version": 1,
        "base_station_metric_projection": serialized_base_station_projection,
        "base_station_metric_projection_attestation": (
            base_station_metric_projection_attestation
        ),
        "throughput_scope": (
            required_throughput_scope
            if _throughput_verified is True
            else ThroughputMetrics.SCOPE_UNKNOWN
        ),
        "rf_kpi_trust_schema_version": RF_KPI_TRUST_SCHEMA_VERSION,
        "rf_kpi_trust": _rf_kpi_trust,
        "formal_rf_kpi_verified": _rf_kpi_formally_verified,
        "quiet_zone_evidence_schema_version": QUIET_ZONE_EVIDENCE_SCHEMA_VERSION,
        "quiet_zone_evidence": _qz_evidence,
        "formal_quiet_zone_verified": _qz_verified,
        "generated_by": "MIMO OTA System",
        "generated_at": now.isoformat(),
        "overall_result": report_outcome,
        # ReportViewer 仍消费顶层兼容镜像；它必须与同一次生命周期
        # 投影生成的 execution_summary 同源，避免延迟发布时丢失判决。
        "pass_rate": summary["pass_rate"],
        "duration_s": duration_sec,
        "test_plan": plan_info,
        "execution_summary": summary,
        "statistics": statistics,
        "table_data": table_data,
        "step_results": step_results,
        "scpi_evidence": _public_scpi_evidence(execution),
    }


def _public_scpi_evidence(execution: Any) -> Dict[str, Any]:
    from app.services.execution_scpi_evidence import public_execution_scpi_evidence

    evidence = public_execution_scpi_evidence(execution)
    if evidence is not None:
        return evidence
    return {
        "schema_version": 1,
        # 旧报告重建测试/迁移对象可能没有 id；缺失证据本就只能 UNKNOWN，
        # 用稳定占位而不是让历史内容重建直接异常。
        "execution_id": str(getattr(execution, "id", "legacy-unknown")),
        "environments": {},
        "required": [],
        "items": [],
        "missing_requirements": [],
        "formal_verdict": "unknown",
        "formal_acceptance": False,
        "reason": "execution_evidence_missing_or_invalid",
    }


def _std(values: List[float]) -> float:
    """Population stddev; returns 0 on <2 samples to avoid div-by-zero."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return var ** 0.5
