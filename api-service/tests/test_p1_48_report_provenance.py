"""P1-48 报告线：正式报告要说清哪几台是模拟的，别把编出来的数字当测量结果印。

治的毛病：
  ① 「TRP 来源」那栏在说假话 —— SA 挂着但是 mock 驱动时也写 hal_signal_analyzer，
     跟旁边的「TRP 验证：未验证」并排打架；
  ② 只加一句「未验证」不够 —— 数字照样印在那儿，读者会当成测量结果；
  ③ 库里早就逐台点了名（simulated_sources / cal_pass_reason / dut_pass_reason），
     报告一个都没取；
  ④ 用户手点「生成执行报告」那份走另一条路，三处标注一个都没有。
"""
from __future__ import annotations

from datetime import datetime

from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data


class _Exec:
    def __init__(self, measurements):
        self.id = "test-exec"
        self.measurements = measurements
        self.config = {}
        self.status = "completed"
        self.started_at = None
        self.completed_at = None
        self.error_message = None
        self.validation_pass = None
        self.duration_sec = None
        self.execution_number = 1
        self.test_case_id = None


def _content(reference=None, measure=None, precheck=None):
    ex = _Exec({"phases": {
        "precheck": precheck or {},
        "reference": reference or {},
        "measure": measure or {},
    }})
    return _build_mimo_ota_content_data(ex, datetime(2026, 8, 10), "case")


def _phase(content, name):
    for s in content.get("step_results") or []:
        if s.get("phase") == name:
            return s.get("parameters") or {}
    return {}


def test_mock_sa_is_not_labelled_as_a_real_instrument():
    """SA 是 mock 驱动时，「来源」那栏不许说成真实信号分析仪。"""
    p = _phase(_content(reference={"measurement_source": "hal_signal_analyzer_mock",
                                   "measured_trp_dbm": -12.3}), "reference")
    label = str(p.get("TRP 来源"))
    assert "模拟" in label or "仿真" in label, f"来源那栏写的是：{label}"
    assert "真实信号分析仪（实测）" != label


def test_real_sa_is_labelled_as_measured():
    p = _phase(_content(reference={"measurement_source": "hal_signal_analyzer",
                                   "measured_trp_dbm": -12.3}), "reference")
    assert "实测" in str(p.get("TRP 来源"))


def test_unconfirmed_trp_values_are_not_printed():
    """⭐ 只有确认是真实测的那一档才印数值。

    「假」（仿真/兜底）和「空」（历史记录来源不明）两档都可能是编的 ——
    光加一句「未验证」不够，数字印在那儿读者会当成测量结果。
    """
    for src in ("hal_signal_analyzer_mock", "mock", None, "某个没见过的值"):
        p = _phase(_content(reference={"measurement_source": src,
                                       "measured_trp_dbm": -12.3,
                                       "compensation_factor_db": 4.5}), "reference")
        assert "-12.3" not in str(p.get("参考 TRP (dBm)")), (
            f"来源={src!r} 时不该印数值，实际印了：{p.get('参考 TRP (dBm)')}"
        )
        assert "4.5" not in str(p.get("补偿 (dB)")), (
            f"来源={src!r} 时不该印补偿数值"
        )

    # 反向：确认真实测那一档必须印出来
    p = _phase(_content(reference={"measurement_source": "hal_signal_analyzer",
                                   "measured_trp_dbm": -12.3,
                                   "compensation_factor_db": 4.5}), "reference")
    assert "-12.3" in str(p.get("参考 TRP (dBm)")), "真实测的数值该印却没印"


def test_report_names_which_instruments_were_simulated():
    """⭐ 逐台点名 —— 这份名单早就在库里，报告一直没取。"""
    p = _phase(_content(measure={
        "simulated_sources": ["baseStation", "channelEmulator", "positioner"]}), "measure")
    shown = str(p.get("模拟来源"))
    for name in ("baseStation", "channelEmulator", "positioner"):
        assert name in shown, f"没点名 {name}，实际：{shown}"


def test_report_carries_the_precheck_reasons():
    """预检那两句「为什么算通过」的原话 —— 其中一句会明说这是 mock。"""
    p = _phase(_content(precheck={
        "cal_pass_reason": "mock 模式跳过校准门",
        "dut_pass_reason": "DUT 已在暗室内"}), "precheck")
    assert "mock" in str(p.get("校准门理由"))
    assert "暗室" in str(p.get("DUT 门理由"))


def test_manual_report_path_gets_the_same_annotations():
    """⭐ 用户手点「生成执行报告」那条路，标注不能丢。"""
    from app.services.report_data_collector import _fill_provenance_parameters

    ex = _Exec({"phases": {
        "reference": {"measurement_source": "mock", "measured_trp_dbm": -20.0},
        "measure": {"simulated_sources": ["baseStation"]},
    }})
    rows = [{"name": "reference", "parameters": {}},
            {"name": "measure", "parameters": {}}]
    _fill_provenance_parameters(ex, rows)

    ref_params = rows[0]["parameters"]
    assert ref_params, "手点那条路的相位参数还是空的 —— 三处标注全丢了"
    assert "TRP 验证" in ref_params
    assert "baseStation" in str(rows[1]["parameters"].get("模拟来源", ""))


def test_manual_report_path_leaves_other_executions_alone():
    """没有相位数据的执行链（调试台等）行为完全不变。"""
    from app.services.report_data_collector import _fill_provenance_parameters

    rows = [{"name": "x", "parameters": {}}]
    _fill_provenance_parameters(_Exec(None), rows)
    assert rows == [{"name": "x", "parameters": {}}]


def test_manual_report_path_call_site_is_wired():
    """⭐ 上一条测的是那个函数本身，改掉**调用点**它照样绿。

    跑真正的 `_get_phase_results`，确认标注真的出现在返回的结果里。

    让它报错的改法：把 `_get_phase_results` 里那句 `_fill_provenance_parameters(...)` 删掉。
    """
    from app.services.report_data_collector import ReportDataCollector

    ex = _Exec({"phases": {
        "reference": {"measurement_source": "mock", "measured_trp_dbm": -20.0},
    }})
    ex.config = {"phase_progress": [{"type": "reference", "status": "success"}]}

    rows = ReportDataCollector.__new__(ReportDataCollector)._get_phase_results([ex])

    assert rows, "没产出相位结果"
    assert rows[0].get("parameters"), (
        "相位参数是空的 —— 调用点没接上，三处标注全丢了"
    )
    assert "TRP 验证" in rows[0]["parameters"]
