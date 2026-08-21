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
from app.hal.base_station import ThroughputMetrics
from app.services.mimo_ota.executors._helpers import write_phase_result
from app.services.mimo_ota.throughput_trust import (
    required_throughput_scope as _required_throughput_scope,
    throughput_scope_is_verified,
)
from app.services.report_service import (
    ReportService,
    THROUGHPUT_TRUST_SCHEMA_VERSION,
)
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
            # 报告本身属于正式结论，必须先应用 SCPI AND 门再读取
            # validation_pass；否则 PDF 会比 runner 的最终判定早一步写出假 PASS。
            from app.services.test_case_runner import _finalize_scpi_acceptance

            _finalize_scpi_acceptance(execution)
            context.db.commit()
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

    verdict_unknown = analysis.get("verdict") == "UNKNOWN"
    summary = {
        "total_executions": 1,
        "passed": 1 if overall_pass else 0,
        "failed": 0 if overall_pass or verdict_unknown else 1,
        "pending": 1 if verdict_unknown else 0,
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
            def _format_metric(value, digits: int) -> str:
                return "N/A" if value is None else f"{value:.{digits}f}"

            table_data.append({
                "Azimuth (°)": f"{a.get('azimuth_deg', 0):.1f}",
                "RSRP (dBm)": _format_metric(a.get("rsrp_dbm"), 1),
                "SINR (dB)": _format_metric(a.get("sinr_db"), 1),
                "Throughput (Mbps)": _format_metric(a.get("throughput_mbps"), 1),
                "RI": _format_metric(a.get("rank_indicator"), 2),
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

    # P1-54: 吞吐的数值与“这次是否真的读到”必须同行。历史执行没有该字段，
    # 也可能正是把缺测默认 0.0 当样本的旧数据，所以只能 fail-closed；不能从
    # 数值是否为 0、analysis 旧 verdict 或 measurement_verified 反推可信性。
    _throughput_verified = measure.get("throughput_verified")
    required_throughput_scope = _required_throughput_scope(measure)

    # P1-59: P1-54 的布尔值只能证明“读到了一个有限吞吐值”，不能证明
    # CA 执行读的是全部 NR cells 而非 PCell。正式报告必须同时核对载波数量、
    # measure 顶层范围和每个方位的同行范围；历史记录缺任一证据都 fail-closed。
    throughput_scope_verified = throughput_scope_is_verified(measure)
    if _throughput_verified is True and not throughput_scope_verified:
        _throughput_verified = False

    # A formal KPI/report verdict requires explicit proof that the applied
    # path-loss certificate was real *and* every azimuth contributed a trusted
    # throughput sample. Historical, mock, bypass and missing-read executions
    # remain auditable, but their numerical KPI values cannot be re-published
    # as a formal PASS/FAIL after report regeneration.
    reported_verdict = analysis.get("verdict")
    if _pl_verified is not True or _throughput_verified is not True:
        overall_pass = False
        verdict_unknown = True
        reported_verdict = "UNKNOWN"
        summary.update({
            "passed": 0,
            "failed": 0,
            "pending": 1,
            "pass_rate": 0.0,
        })
        statistics = {}
        for row in table_data:
            for metric in ("RSRP (dBm)", "SINR (dB)", "Throughput (Mbps)", "RI"):
                row[metric] = "N/A"

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
             # ⚠️ 未验证时不印数值（外审 P1）：没有探头方向图时，写入端存的是
             #    兜底值 0.7，验证标志为假 —— 光标一句「未验证」不够，
             #    数字印在那儿读者会当成实测的静区波纹。
             "静区波纹 (±dB)": (
                 _cell(precheck.get("quiet_zone_ripple_db")) if _qz_verified is True
                 else "—（未实测，不印兜底值）"
             ),
             # P1-12: 非 True 时波纹是遗留默认值, 静区从未实测 —— 必须标注。
             "静区验证": _verified_label(
                 _qz_verified, "探头方向图实测", "兜底默认值, 非实测静区"),
             # ⭐ 预检那两句「为什么算通过」的原话（P1-48）：库里早就存着
             #    （cal_pass_reason / dut_pass_reason），报告一直没取。
             #    其中一句会明说「这是 mock」—— 那正是读者最该看到的。
             "校准门理由": _cell(precheck.get("cal_pass_reason") or "未记录"),
             "DUT 门理由": _cell(precheck.get("dut_pass_reason") or "未记录"),
             "提示": _cell(precheck.get("messages") or []),
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
                 _cell(measure.get("path_loss_compensation_db")) if _pl_verified is True
                 else "—（无路损校准，未补偿）"
             ),
             # P1-12: 无路损证书 → RSRP 未补偿 → 结果未校准, 必须标注。
             "路损验证": _verified_label(
                 _pl_verified, "路损校准证书", "无路损校准, RSRP 未补偿"),
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

    return {
        "title": f"MIMO OTA Test Report — {plan_info['name']}",
        # P1-22 (Codex #256): 报告类型进 content_data — PDFGenerator 靠它分流
        # 计划口径/用例口径的字段标签 (名字有无判不了型: 本路径恒有名字)。
        "report_type": "single_execution",
        "report_family": "mimo_ota",
        "calibration_trust_schema_version": 1,
        "formal_path_loss_verified": _pl_verified is True,
        "throughput_trust_schema_version": THROUGHPUT_TRUST_SCHEMA_VERSION,
        "formal_throughput_verified": _throughput_verified is True,
        "throughput_scope": (
            required_throughput_scope
            if _throughput_verified is True
            else ThroughputMetrics.SCOPE_UNKNOWN
        ),
        "generated_by": "MIMO OTA System",
        "generated_at": now.isoformat(),
        "overall_result": (
            "passed" if overall_pass else "unknown" if verdict_unknown else "failed"
        ),
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
