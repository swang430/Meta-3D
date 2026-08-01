"""P1-22 报告可信化 — 行为锁定。

设计稿 docs/design/p1-22-report-trustworthy-fix.md:
  ① 通过谓词换 canonical 源: TestExecution.validation_pass 列优先,
    缺列兜 payload 的 verdict 三值字面量, 都没有 → 保守 False。
    红线: 禁 status=='completed' 判通过 / 禁 bool(verdict)。
  ② step_results 的 analysis 项: verdict 放渲染器可达位置 (parameters 下),
    overall_pass / pass_criteria_summary 死键站点删除。
  ③ CJK 字体三族收敛到 CJK_FONT 常量; 生成的 PDF 字节含 CID 字体引用。
  ④ 封面 Test Plan 行按报告类型分流: execution 类显示「来源」。

变异自验对应表 (⓪-④):
- 谓词改回 analysis.get("overall_pass") → test_pass_predicate_* 的
  PASS/MARGINAL 形态红 (报告恒 failed 的原病灶)
- 谓词改 status=='completed' → test_kpi_fail_not_reported_as_pass 红
  (KPI FAIL 的 completed 行谎报通过)
- 字体遍历收敛删除 → test_all_styles_use_cjk_font 红
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.pdf_generator import CJK_FONT, PDFGenerator


def _exec(phases, validation_pass=None, status="completed"):
    return SimpleNamespace(
        measurements={"phases": phases},
        status=status,
        duration_sec=1.0,
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1),
        validation_pass=validation_pass,
    )


def _content(phases, **kw):
    return _build_mimo_ota_content_data(_exec(phases, **kw), datetime(2026, 1, 1))


# ─────────────────────────────────────────────────────────────────────
# ① 通过谓词
# ─────────────────────────────────────────────────────────────────────

class TestPassPredicate:
    def test_pass_predicate_validation_pass_column_wins(self):
        """canonical 列优先 — 判别形态: 列与 verdict **反向** (列 True /
        verdict FAIL), 列必须赢 (内审 F1: 同向用例区分不出列读取整个失效
        恒走 fallback 的形态, 属性名拼错也全绿)。"""
        c = _content({"analysis": {"verdict": "FAIL"}}, validation_pass=True)
        assert c["overall_result"] == "passed"
        assert c["execution_summary"]["pass_rate"] == 100.0
        assert c["execution_summary"]["passed"] == 1

    def test_pass_predicate_column_false_is_failed(self):
        c = _content({"analysis": {"verdict": "FAIL"}}, validation_pass=False)
        assert c["overall_result"] == "failed"
        assert c["execution_summary"]["pass_rate"] == 0.0

    def test_pass_predicate_falls_back_to_verdict_literal(self):
        """列缺失 (老执行) → 按 verdict 三值字面量判。"""
        assert _content({"analysis": {"verdict": "PASS"}})["overall_result"] == "passed"
        assert _content({"analysis": {"verdict": "MARGINAL"}})["overall_result"] == "passed"
        assert _content({"analysis": {"verdict": "FAIL"}})["overall_result"] == "failed"

    def test_pass_predicate_unknown_stays_failed(self):
        """列与 verdict 都缺 → 保守 failed (绝不把未知判成通过)。"""
        assert _content({"analysis": {}})["overall_result"] == "failed"
        assert _content({})["overall_result"] == "failed"

    def test_kpi_fail_not_reported_as_pass(self):
        """红线: completed 状态 + KPI FAIL → 必须 failed。
        (analysis 相位机械成功与 KPI 通过是两层 — 谓词若退化成
        status=='completed' 会在这里谎报通过。)"""
        c = _content(
            {"analysis": {"verdict": "FAIL"}},
            validation_pass=False, status="completed",
        )
        assert c["overall_result"] == "failed"


# ─────────────────────────────────────────────────────────────────────
# ② analysis step 项 — verdict 可达 + 死键站点已删
# ─────────────────────────────────────────────────────────────────────

class TestAnalysisStepShape:
    def test_verdict_in_renderer_reachable_position(self):
        """渲染器只读 name/step_name 与 parameters 下的键。"""
        c = _content({"analysis": {"verdict": "MARGINAL"}}, validation_pass=True)
        step = next(s for s in c["step_results"] if s["phase"] == "analysis")
        assert step["parameters"]["verdict"] == "MARGINAL"
        assert step["name"] == "analysis"

    def test_dead_keys_removed_from_analysis_step(self):
        c = _content({"analysis": {"verdict": "PASS"}}, validation_pass=True)
        step = next(s for s in c["step_results"] if s["phase"] == "analysis")
        assert "overall_pass" not in step
        assert "pass_criteria_summary" not in step


# ─────────────────────────────────────────────────────────────────────
# ③ CJK 字体三族收敛
# ─────────────────────────────────────────────────────────────────────

class TestCJKFont:
    def test_all_styles_use_cjk_font(self):
        """不变量: stylesheet 全部样式 (默认族 + 自定义族) fontName 均为
        CJK_FONT — 删掉收敛遍历或漏改任一族即红。"""
        gen = PDFGenerator()
        wrong = {
            name: style.fontName
            for name, style in gen.styles.byName.items()
            if hasattr(style, "fontName") and style.fontName != CJK_FONT
        }
        assert wrong == {}, f"未收敛到 {CJK_FONT} 的样式: {wrong}"

    def test_no_helvetica_left_in_module(self):
        """存在性粗筛: 源码里不许再出现 Helvetica 字面量 (Table FONTNAME 族
        由此兜住 — 该族不进 stylesheet, 上一条不变量够不到)。"""
        import inspect
        import app.services.pdf_generator as m
        assert "Helvetica" not in inspect.getsource(m)

    def test_generated_pdf_embeds_cid_font_and_chinese_title(self, tmp_path):
        """行为门: 真生成一份中文标题+中文表格值的 PDF, 字节里必须有
        CID 字体引用 (STSong)。"""
        gen = PDFGenerator()
        out = str(tmp_path / "p1_22_cjk.pdf")
        data = {
            "title": "P1-22 中文报告验证",
            "report_type": "single_execution",
            "generated_at": "2026-08-01T00:00:00",
            "execution_summary": {
                "total_executions": 1, "passed": 1, "failed": 0,
                "pending": 0, "pass_rate": 100.0, "total_duration_sec": 1.0,
            },
            "step_results": [
                {"phase": "analysis", "name": "analysis",
                 "parameters": {"verdict": "PASS", "备注": "中文单元格"}},
            ],
        }
        gen.generate_report(data, template=None, output_path=out)
        pdf = open(out, "rb").read()
        assert b"STSong" in pdf


# ─────────────────────────────────────────────────────────────────────
# ④ 封面 Test Plan 行分流
# ─────────────────────────────────────────────────────────────────────

class TestCoverPlanRow:
    @staticmethod
    def _cover_rows(data):
        gen = PDFGenerator()
        elements = gen._generate_cover_page(data, {})
        rows = []
        for el in elements:
            cells = getattr(el, "_cellvalues", None)
            if cells:
                rows.extend([tuple(r) for r in cells])
        return rows

    def test_execution_report_without_plan_shows_source(self):
        """手动路径 (collector 无 test_plan) → 用例口径兜底文案。"""
        rows = self._cover_rows({"title": "t", "report_type": "single_execution"})
        assert ("测试用例:", "用例执行") in rows
        assert not any(r[0] == "Test Plan:" for r in rows)

    def test_execution_report_with_case_name_not_mislabeled(self):
        """Codex #256 P1: MIMO_OTA 自动路径恒带 test_plan dict (装的是用例名) —
        判据必须按 report_type 分型, 名字有无判不了 (恒真会把用例错标成
        Test Plan)。"""
        rows = self._cover_rows({
            "title": "t", "report_type": "single_execution",
            "test_plan": {"name": "S6-验收-五步闭环"},
        })
        assert ("测试用例:", "S6-验收-五步闭环") in rows
        assert not any(r[0] == "Test Plan:" for r in rows)

    def test_plan_report_keeps_test_plan_row(self):
        """Codex #255 R2 scope: 计划类标准报告仍显示真实计划名。"""
        rows = self._cover_rows({
            "title": "t", "report_type": "Standard",
            "test_plan": {"name": "真实计划名"},
        })
        assert ("Test Plan:", "真实计划名") in rows
