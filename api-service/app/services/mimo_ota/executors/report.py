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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.report import ReportFormat, ReportType
from app.services.mimo_ota.executors._helpers import write_phase_result
from app.services.report_service import ReportService
from app.services.test_execution import (
    IStepExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepExecutionStatus,
    register_executor,
)
from app.schemas.mimo_ota.config import MIMOOTAStepType

logger = logging.getLogger(__name__)


@register_executor(MIMOOTAStepType.REPORT.value)
class ReportExecutor(IStepExecutor):
    """Generate a PDF report from prior phases, mark execution completed."""

    async def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        execution = context.test_execution
        now = datetime.now(timezone.utc)
        report_id_human = (
            f"MIMO_OTA-{str(execution.id)[:8]}-{now.strftime('%Y%m%d%H%M%S')}"
        )

        warnings: List[str] = []
        report_db_id: Optional[str] = None
        report_file_path: Optional[str] = None

        case_name = _lookup_case_name(context, execution)
        try:
            content_data = _build_mimo_ota_content_data(execution, now, case_name)
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
                content_data=content_data,
            )
            report_db_id = str(report.id)
            generated = svc.generate_report(
                db=context.db,
                report_id=report.id,
                content_data_override=content_data,
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

        # Mark execution lifecycle complete regardless of PDF outcome
        execution.status = "completed"
        execution.completed_at = now.replace(tzinfo=None)
        if execution.started_at:
            delta = (now.replace(tzinfo=None) - execution.started_at).total_seconds()
            execution.duration_sec = delta
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


def _build_mimo_ota_content_data(
    execution: Any, now: datetime, case_name: Optional[str] = None
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

    # ARCH-1 S2: MIMO_OTA 执行是 TestCase 制不挂 TestPlan, 报告首段的
    # "名字"就是快照用例名 (caller 经 _lookup_case_name 查好传入;
    # 旧二参调用 / 查不到时兜底"未命名用例", 不再是 "Unknown Plan")
    display_name = case_name or "未命名用例"
    plan_info = {
        "name": display_name,
        "description": "—",
        "status": execution.status,
        "created_by": "system",
    }

    # P1-22: 通过谓词换 canonical 源 — analysis 执行器写的是
    # TestExecution.validation_pass 列 (= verdict in ("PASS","MARGINAL")),
    # 从不写 payload 的 "overall_pass" 键 (旧读法恒 False → 报告恒 failed/0.0%)。
    # 列缺失 (老执行 / analysis 未跑到 / 测试 stub) 时兜 payload 的 verdict
    # 三值字面量; 都没有 → 保守 False (与旧行为同向, 绝不把未知判成通过)。
    _validation_pass = getattr(execution, "validation_pass", None)
    if _validation_pass is not None:
        overall_pass = bool(_validation_pass)
    else:
        overall_pass = analysis.get("verdict") in ("PASS", "MARGINAL")
    duration_sec = float(execution.duration_sec or 0.0)

    summary = {
        "total_executions": 1,
        "passed": 1 if overall_pass else 0,
        "failed": 0 if overall_pass else 1,
        "pending": 0,
        "pass_rate": 100.0 if overall_pass else 0.0,
        "total_duration_sec": duration_sec,
        "first_execution": execution.started_at.isoformat() if execution.started_at else None,
        "last_execution": execution.completed_at.isoformat() if execution.completed_at else now.isoformat(),
    }

    # Aggregate per-azimuth stats into one stat-row per KPI
    azimuth_results: List[Dict[str, Any]] = measure.get("azimuth_results") or []
    statistics = {}
    table_data = []
    if azimuth_results:
        for kpi_key, kpi_label, unit in [
            ("rsrp_dbm", "RSRP", "dBm"),
            ("sinr_db", "SINR", "dB"),
            ("throughput_mbps", "Throughput", "Mbps"),
            ("rank_indicator", "RankIndicator", ""),
        ]:
            values = [a.get(kpi_key) for a in azimuth_results if a.get(kpi_key) is not None]
            if values:
                vmin, vmax = min(values), max(values)
                vavg = sum(values) / len(values)
                vstd = _std(values)
                statistics[f"{kpi_label}_{unit}".strip("_")] = {
                    "metric_name": f"{kpi_label} ({unit})" if unit else kpi_label,
                    "mean": round(vavg, 3),
                    "median": round(sorted(values)[len(values) // 2], 3),
                    "std": round(vstd, 3),
                    "min": round(vmin, 3),
                    "max": round(vmax, 3),
                    "count": len(values),
                }

        for a in azimuth_results:
            table_data.append({
                "Azimuth (°)": f"{a.get('azimuth_deg', 0):.1f}",
                "RSRP (dBm)": f"{a.get('rsrp_dbm', 0):.1f}",
                "SINR (dB)": f"{a.get('sinr_db', 0):.1f}",
                "Throughput (Mbps)": f"{a.get('throughput_mbps', 0):.1f}",
                "RI": f"{a.get('rank_indicator', 0):.2f}",
            })

    # Backward-compat for historical/migrated executions that predate the
    # explicit verified flags (Codex on PR #80): NEVER default an absent flag to
    # "verified" — an old fallback run would then be silently presented as a
    # real measurement. Derive from provenance instead.
    _qz_verified = precheck.get("quiet_zone_verified")
    if _qz_verified is None:
        # quiet_zone_ripple_source unambiguously recovers it: only the real
        # probe-pattern source counts as verified; fallback_default / missing
        # source → not verified.
        _qz_verified = precheck.get("quiet_zone_ripple_source") == "probe_pattern_peak_spread"
    _trp_verified = reference.get("trp_verified")
    if _trp_verified is None:
        # "mock" = no SA → unverified; legacy "hal_signal_analyzer" didn't
        # distinguish real vs mock SA → unknown (None), rendered as not-verified.
        _trp_verified = False if reference.get("measurement_source") == "mock" else None
    _pl_verified = measure.get("path_loss_verified")
    if _pl_verified is None:
        # Historical measure records carry path_loss_certificate_id — a non-null
        # cert is the provenance that recovers "verified" without the flag.
        _pl_verified = measure.get("path_loss_certificate_id") is not None

    def _verified_label(flag, verified_note: str, unverified_note: str) -> str:
        """P1-12 三值标志 → 报告可读标注。None (历史数据判不了) 也要显式说出来,
        不能沉默 —— 沉默正是 P2-21 要修的病。"""
        if flag is True:
            return f"已验证 ({verified_note})"
        if flag is False:
            return f"未验证 ({unverified_note})"
        return "未知 (历史数据未区分真实/兜底)"

    def _cell(v):
        """parameters 单元格值卫生 (内审 F1/F3):
        - 字符串过 XML 转义 — 渲染器把值喂 Paragraph(paraparser), `<字母` 形态
          的自由文本 (操作员命名 "TDL-A <30ns" / DUT 名) 会被当未闭合 tag,
          **整份报告 PDF 生成失败**; 完整 `<tag>` 形态更阴险 — 内容被静默吞掉。
          旧顶层键时代这些值从不进 Paragraph, 本次接入渲染管道必须带转义。
        - None → "—" (中文报告里英文字面 "None" 含义模糊; .get 默认值只兜键
          缺失, 兜不住显式 null — 值形态三态)。
        - 列表逐条同处理 (messages; 渲染器 json.dumps 保留原字符)。"""
        from xml.sax.saxutils import escape
        if v is None:
            return "—"
        if isinstance(v, str):
            return escape(v)
        if isinstance(v, list):
            return [_cell(x) for x in v]
        return v

    # P2-21: 渲染载荷整体放 parameters 下 (PDFGenerator 步骤区只渲染 name/
    # step_name 与 parameters 的键值表, 顶层键进不了 PDF) —— P1-12 的三个可信化
    # 标志因此从未生效过, 现场拿假干净报告做判断。同一修法 P1-22 已在 analysis
    # 站点验证 (verdict 进 parameters); 本次把 precheck/reference/measure 三站点
    # 收敛到同构, 顶层渲染键删干净 (step_results 唯一消费方是 PDFGenerator,
    # 留顶层就是死载荷双写)。
    step_results = [
        {"phase": "precheck", "name": "precheck (预检)",
         "parameters": {
             "结果": "PASS" if precheck.get("overall_pass") else "FAIL",
             "静区波纹 (±dB)": _cell(precheck.get("quiet_zone_ripple_db")),
             # P1-12: 非 True 时波纹是遗留默认值, 静区从未实测 —— 必须标注。
             "静区验证": _verified_label(
                 _qz_verified, "探头方向图实测", "兜底默认值, 非实测静区"),
             "提示": _cell(precheck.get("messages") or []),
         }},
        {"phase": "reference", "name": "reference (参考测量)",
         "parameters": {
             "参考 TRP (dBm)": _cell(reference.get("measured_trp_dbm")),
             "补偿 (dB)": _cell(reference.get("compensation_factor_db")),
             "TRP 来源": _cell(reference.get("measurement_source")),
             # P1-12: mock/兜底 TRP → 参考数据不是实测, 必须标注。
             "TRP 验证": _verified_label(
                 _trp_verified, "真实信号分析仪", "mock/兜底值"),
         }},
        {"phase": "measure", "name": "measure (吞吐测量)",
         "parameters": {
             "频率 (GHz)": _cell(measure.get("frequency_ghz")),
             "MIMO 配置": _cell(measure.get("mimo_config")),
             "CDL 模型": _cell(measure.get("cdl_model_name")),
             "路损补偿 (dB)": _cell(measure.get("path_loss_compensation_db")),
             # P1-12: 无路损证书 → RSRP 未补偿 → 结果未校准, 必须标注。
             "路损验证": _verified_label(
                 _pl_verified, "路损校准证书", "无路损校准, RSRP 未补偿"),
             "已测方位数": len(azimuth_results),
         }},
        {"phase": "analysis",
         # P1-22: verdict 三值放渲染器可达位置; 旧 overall_pass /
         # pass_criteria_summary 是全仓无写方的死键, 删站点。
         "name": "analysis",
         "parameters": {"verdict": analysis.get("verdict")}},
    ]

    return {
        "title": f"MIMO OTA Test Report — {plan_info['name']}",
        # P1-22 (Codex #256): 报告类型进 content_data — PDFGenerator 靠它分流
        # 计划口径/用例口径的字段标签 (名字有无判不了型: 本路径恒有名字)。
        "report_type": "single_execution",
        "generated_by": "MIMO OTA System",
        "generated_at": now.isoformat(),
        "overall_result": "passed" if overall_pass else "failed",
        "duration_s": duration_sec,
        "test_plan": plan_info,
        "execution_summary": summary,
        "statistics": statistics,
        "table_data": table_data,
        "step_results": step_results,
    }


def _std(values: List[float]) -> float:
    """Population stddev; returns 0 on <2 samples to avoid div-by-zero."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return var ** 0.5
