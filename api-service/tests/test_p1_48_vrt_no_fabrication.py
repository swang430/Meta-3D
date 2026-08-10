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
    assert _report_result([]) == "incomplete", "零 KPI 时应为未判定"
    assert _report_result([None, None, None]) == "incomplete", (
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
