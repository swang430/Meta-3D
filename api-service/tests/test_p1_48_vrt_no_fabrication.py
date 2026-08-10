"""P1-48 第 5 片：虚拟路测不再编数、不再替人下结论。

治的毛病（生产库里有实物）：一份 PDF 上 5 行 KPI 全 ✓ PASS、通过率 100%，
而那次执行**零仪器参与** —— 数值是 `random.uniform` 现编的，合格判定是**浏览器**算的，
后端原样存、原样印。
"""
from __future__ import annotations

import pathlib

import pytest

_SRC = pathlib.Path(__file__).resolve().parents[1] / "app/api/road_test.py"


def test_no_random_fabrication_left_in_road_test():
    """那段用随机数编 KPI/相位/事件的代码不许回来。

    让它报错的改法：把 `import random` 和那段 fallback 加回去。
    """
    text = _SRC.read_text(encoding="utf-8")
    lines = [
        l for l in text.split("\n")
        if ("random." in l or l.strip() == "import random")
        and not l.strip().startswith("#")
    ]
    assert not lines, (
        "road_test.py 里又出现了随机数：\n  " + "\n  ".join(lines)
        + "\n虚拟路测没有真数据源，编出来的数会进正式 PDF。"
    )


def test_browser_verdict_is_not_persisted():
    """浏览器算的合格判定不许落库。

    让它报错的改法：把落库处的 `"passed": None` 改回 `kpi.passed`。
    """
    text = _SRC.read_text(encoding="utf-8")
    assert '"passed": kpi.passed' not in text, (
        "又在把浏览器算的 passed 存进库 —— 那是客户端的判决，不是系统的结论"
    )


def _report_result(kpi_passed_values, status_completed=True):
    """调**生产代码里那个**结论算法（不复刻逻辑 —— 复刻出来的门测的是我自己写的副本）。"""
    from app.api.road_test import ExecutionStatus, compute_overall_result

    class _KPI:
        def __init__(self, passed):
            self.passed = passed

    status = ExecutionStatus.COMPLETED if status_completed else ExecutionStatus.FAILED
    _rate, result = compute_overall_result([_KPI(v) for v in kpi_passed_values], status)
    return result


def test_no_real_verdict_means_undetermined_not_failed():
    """⭐ 一条 KPI 都没有真判决时，结论恒为「未判定」。

    不能掉进 failed —— 那等于把「编造的通过」换成「编造的不通过」，
    半径没收敛，只是换了个方向说谎。

    让它报错的改法：把 `compute_overall_result` 里的 `if not judged:` 分支去掉。
    """
    # 跑完了但没判决 → undetermined（不是 failed，也不是 incomplete）
    assert _report_result([]) == "undetermined", "零 KPI 时应为未判定"
    assert _report_result([None, None, None]) == "undetermined", (
        "KPI 都没有真判决时应为未判定，不能算 failed"
    )


def test_real_verdicts_still_decide_normally():
    """反向：有真判决时，原来的合格率逻辑照常работа。

    只测「没判决→未判定」的话，把结论写死成 incomplete 也能绿。
    """
    assert _report_result([True, True, True, True, True]) == "passed"
    assert _report_result([False, False, False]) == "failed"


def test_empty_sample_path_produces_nothing():
    """没有样本时，相位/KPI/事件三样都为空 —— 不再现编一份「全部通过」。

    让它报错的改法：把那段 fallback 里的 `phases = []` 改回生成 7 个假相位。
    """
    text = _SRC.read_text(encoding="utf-8")
    # 那三个变量在无样本分支里必须被置空
    for marker in ("phases = []", "kpi_summary = []", "events = []"):
        assert marker in text, f"无样本分支里没有把 {marker.split(' =')[0]} 置空"
    # 而且不许再出现当年那批假相位名
    assert "启动基站" not in text or "原先" in text, (
        "又出现了硬编的假相位名"
    )


def test_client_submitted_values_are_marked_and_excluded():
    """⭐ 外审抓出：上一版只丢掉 passed，而 mean/min/max/std 照样落库照样印。

    那些数值本身就是浏览器 `Math.random()` 造的 —— 判决不采信了、数值还是编的，
    等于只挡了一半。

    让它报错的改法：把落库处的 `"provenance": "client_simulated"` 删掉，
    或把读回处那句 `continue` 去掉。
    """
    text = _SRC.read_text(encoding="utf-8")
    assert '"provenance": "client_simulated"' in text, (
        "落库时没给客户端提交的数据打来源标记 —— 报告分不出这批是编的"
    )
    assert 'stats.get("provenance") == "client_simulated"' in text, (
        "读回时没按来源排除 —— 浏览器造的 mean/min/max/std 会进正式 KPI"
    )


def test_undetermined_is_not_rendered_as_failed_in_ui():
    """⭐ 外审抓出：`passed=null` 在界面上会掉进 false 分支、显示成 ✗ 不合格。

    那是**新造的假信息** —— 把「未判定」说成「不合格」。

    （前端没有测试框架，这里从源码上确认那个判断已经排除 null。
      如实申报：这一格只能这么验，真实渲染要靠人眼。）
    """
    import pathlib

    viewer = (pathlib.Path(__file__).resolve().parents[2]
              / "gui/src/components/Report/ReportViewer.tsx")
    if not viewer.exists():
        import pytest as _pt
        _pt.skip("找不到 ReportViewer.tsx")
    text = viewer.read_text(encoding="utf-8")
    assert "kpi.passed !== undefined && kpi.passed !== null" in text, (
        "界面判 passed 时没排除 null —— null 会掉进 false 分支、显示成红色 ✗，"
        "把「未判定」说成「不合格」"
    )


def test_client_samples_do_not_reach_the_recompute_path():
    """⭐ 外审抓出：上一版的 continue 只挡了摘要，**原始样本还在**。

    `has_real_metrics` 只看 `len(kpi_samples) > 0`，而 kpi_summary 被排空之后
    下游会 `_compute_kpi_summary_from_samples()` **从原始样本重算** ——
    那些样本正是浏览器 `Math.random()` 造的，编的数又算回来了。

    让它报错的改法：把 `has_real_metrics` 改回只判 `len(...) > 0`。
    """
    text = _SRC.read_text(encoding="utf-8")
    # 2026-08-10 外审后改成白名单：只有显式标着真实的才算真数据
    assert "_explicitly_real" in text, (
        "has_real_metrics 没有要求显式的真实标记 —— 重算路径会把编的数算回来"
    )


def test_unjudged_pass_rate_is_none_not_zero():
    """⭐ 外审抓出：`pass_rate=0.0` 会被显示成「通过率 0%」。

    读者以为一条都没过，实际是**一条都没判**。

    让它报错的改法：把 `return None, "incomplete"` 改回 `return 0.0, ...`。
    """
    from app.api.road_test import ExecutionStatus, compute_overall_result

    rate, result = compute_overall_result([], ExecutionStatus.COMPLETED)
    assert rate is None, f"没有可信判决时合格率应为 None，实际 {rate!r}"
    # 跑完了但没判决 → undetermined（跟「没跑完」的 incomplete 分开，见外审 P2）
    assert result == "undetermined"

    class _KPI:
        passed = True

    rate2, result2 = compute_overall_result([_KPI()], ExecutionStatus.COMPLETED)
    assert rate2 == 100.0 and result2 == "passed", "有真判决时照常算"


def test_real_data_requires_an_explicit_marker():
    """⭐ 外审抓出：上一版用黑名单（有 client_simulated 标记才排除）。

    历史执行的样本**没有这个标记** → 被当成真数据放行；
    带样本但 summary 为空的提交同理。而虚拟路测今天没有服务端真实数据源。

    让它报错的改法：把 `_explicitly_real` 那段改回黑名单判法。
    """
    text = _SRC.read_text(encoding="utf-8")
    assert "_explicitly_real" in text and 'provenance") == "server_measured"' in text, (
        "没有改成白名单 —— 历史样本会被当成真数据"
    )
    assert "and _explicitly_real" in text, "has_real_metrics 没有要求显式的真实标记"


def test_unfinished_and_unjudged_are_different_labels():
    """⭐ 外审抓出：incomplete 原本表示「执行没跑完」。

    拿它兼表「跑完但没判决」，会让真正没跑完的执行也显示成「未判定」。

    让它报错的改法：把 undetermined 那个分支改回统一返回 incomplete。
    """
    from app.api.road_test import ExecutionStatus, compute_overall_result

    # 跑完了但没有可信判决 → undetermined
    _rate, r1 = compute_overall_result([], ExecutionStatus.COMPLETED)
    assert r1 == "undetermined", f"跑完但没判决应为 undetermined，实际 {r1}"

    # 真的没跑完 → 仍是 incomplete
    _rate, r2 = compute_overall_result([], ExecutionStatus.RUNNING)
    assert r2 == "incomplete", f"没跑完应为 incomplete，实际 {r2}"


def test_pdf_does_not_crash_on_unknown_pass_rate():
    """⭐ 外审抓出：`f"{None:.1f}%"` 会 TypeError 把整份 PDF 弄崩。

    让它报错的改法：把 pdf_generator 里那两处的 None 判断去掉。
    """
    import pathlib

    text = (pathlib.Path(__file__).resolve().parents[1]
            / "app/services/pdf_generator.py").read_text(encoding="utf-8")
    bad = [l for l in text.split("\n")
           if 'f"{pass_rate:.1f}%"' in l and "None" not in l]
    assert not bad, (
        "PDF 里还有没做 None 判断的合格率格式化，会崩：\n  " + "\n  ".join(bad)
    )


def test_every_pass_rate_consumer_handles_none():
    """⭐ 外审两轮都抓到「改了返回值没查全下游」。

    第一轮漏了 `road_test.py` 自己里的 `round(pass_rate, 1)`（会 TypeError）；
    还有一处 f-string 会印出 "Pass Rate: None%"。

    这条把**所有**用到 pass_rate 的地方一次性钉住。

    让它报错的改法：任一处去掉 None 判断。
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in root.rglob("*.py"):
        for i, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            if "pass_rate" not in line or line.strip().startswith("#"):
                continue
            # 会崩或会印出 None 的用法：round(...)、:.1f 格式化、裸插值
            risky = (re.search(r"round\(\s*pass_rate", line)
                     or re.search(r"\{pass_rate[:!]", line)
                     or re.search(r"\{pass_rate\}", line))
            if risky and "None" not in line:
                offenders.append(f"{f.relative_to(root)}:{i}: {line.strip()[:70]}")
    assert not offenders, (
        "这些地方用了 pass_rate 但没处理 None（会崩或印出 None%）：\n  "
        + "\n  ".join(offenders)
    )


def test_failed_execution_keeps_its_failed_result():
    """⭐ 外审抓出：执行本身失败时，早退分支把它盖成了「未完成」。

    让它报错的改法：把 `if execution_status == ExecutionStatus.FAILED: return None, "failed"`
    这个分支删掉。
    """
    from app.api.road_test import ExecutionStatus, compute_overall_result

    _rate, r = compute_overall_result([], ExecutionStatus.FAILED)
    assert r == "failed", f"执行失败且无判决时应保留 failed，实际 {r}"


def test_pdf_overall_result_line_is_not_truncated():
    """⭐ 外审抓出：我上一轮的三元表达式跨相邻 f-string 写，把前半句吃掉了。

    Python 先把相邻字符串拼起来再套三元 → false 分支只剩 "(Pass Rate: 100.0%)"，
    整句 "Overall Result: ..." 被静默丢掉。

    让它报错的改法：把 `_rate_txt` 那个变量去掉、改回三元跨行写。
    """
    import pathlib

    text = (pathlib.Path(__file__).resolve().parents[1]
            / "app/services/pdf_generator.py").read_text(encoding="utf-8")
    bad = [
        l for l in text.split("\n")
        if "Pass Rate:" in l and " if " in l and " else " in l
        and not l.strip().startswith("#")
    ]
    assert not bad, (
        "三元又跨相邻 f-string 写了，会把前半句吃掉：\n  " + "\n  ".join(bad)
    )


def test_archived_pre_provenance_reports_are_flagged():
    """⭐ 外审抓出：白名单只在生成报告时生效，**已归档的旧报告照样能原样取出**。

    生产库里有实物（5 行 KPI 全 ✓ PASS、通过率 100%、零仪器参与）。
    不改历史数据（那是伪造），读取时挂显式警示。

    让它报错的改法：把 `_flag_pre_provenance_report(report)` 那句删掉。
    """
    from app.api.report import _flag_pre_provenance_report

    class _R:
        content_data = {"overall_result": "passed", "pass_rate": 100.0,
                        "kpi_summary": [{"name": "下行吞吐量", "passed": True}]}

    old = _R()
    _flag_pre_provenance_report(old)
    assert "provenance_warning" in old.content_data, "老报告没挂警示"
    assert "未经验证" in old.content_data["provenance_warning"]

    # 新报告（带真假标注痕迹）不该被挂警示
    class _New:
        content_data = {"overall_result": "undetermined", "pass_rate": None}

    new = _New()
    _flag_pre_provenance_report(new)
    assert "provenance_warning" not in new.content_data, "新报告被误挂了警示"
