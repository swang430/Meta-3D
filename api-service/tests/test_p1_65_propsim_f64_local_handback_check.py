"""P1-65 NEW-2：F64 面板 Local 交还的两段式人工确认序列的行为门。

手册事实（Propsim User Reference Rev 10.2 §20.1 原文）："To return to local mode,
click the Local Mode button in the top right corner of the GUI." —— 没有任何 SCPI
能切回或查询 Local（NotebookLM 2026-08-23 核对：§20.4 指令集无 LOCAL/MODE? 类命令，
此为手册无记载而非推断出的"支持"）。所以本序列**不能用 SCPI 判定**这件事，只能做
证据记录器：release 段给指令、confirm 段把操作员的面板观察记回来。
"""
import asyncio
from unittest.mock import MagicMock

from app.diagnostics.sequences import propsim_f64_local_handback_check as seq

IDN = "Keysight Technologies,F8800A,FI1234567,8.0"


class _ScriptedCe:
    def __init__(self, replies=None, *, err_queue=None):
        self._replies = dict(replies or {"*IDN?": IDN})
        self._err_queue = list(err_queue or [])
        self.queries = []
        self.release_calls = 0

    def _query(self, cmd):
        self.queries.append(cmd)
        if cmd == "SYSTem:ERRor?":
            return self._err_queue.pop(0) if self._err_queue else '0,"No error"'
        if cmd not in self._replies:
            raise AssertionError(f"序列发了脚本外的命令: {cmd!r}")
        return self._replies[cmd]

    async def release_to_local_control(self):  # 序列绝不该调它（租约 runner 的事）
        self.release_calls += 1
        return True


class MockChannelEmulator:
    def _query(self, cmd):  # pragma: no cover
        raise AssertionError("mock 驱动不该被查询")


def _run(ce, params=None):
    hal = MagicMock()
    hal.drivers = {"channelEmulator": ce}
    return asyncio.run(seq.run(MagicMock(), hal, params or {}, log=lambda *_: None))


# ── 前置拒绝 ─────────────────────────────────────────────────────────────────

def test_driver_not_loaded_is_refused():
    hal = MagicMock()
    hal.drivers = {}
    result = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
    assert result.success is False
    assert "未加载 channelEmulator" in result.summary


def test_mock_driver_is_refused_in_both_phases():
    for phase in ("release", "confirm"):
        result = _run(MockChannelEmulator(), {"phase": phase})
        assert result.success is False
        assert "mock" in result.summary


def test_metadata_params():
    assert seq.metadata.required_categories == ["channelEmulator"]
    names = {p["name"] for p in seq.metadata.params_schema}
    assert names == {"phase", "operator_observation", "operator_confirmed_local"}
    phase = next(p for p in seq.metadata.params_schema if p["name"] == "phase")
    assert phase["default"] == "release"


# ── release 段 ───────────────────────────────────────────────────────────────

def test_release_phase_identity_only_instructions_and_undetermined():
    ce = _ScriptedCe()
    result = _run(ce)  # 默认 phase=release
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["phase"] == "release"
    # 只读：*IDN? + 结尾错误队列，没有别的命令
    assert set(ce.queries) == {"*IDN?", "SYSTem:ERRor?"}
    assert ce.queries[-1] == "SYSTem:ERRor?"
    # 不自己释放租约
    assert ce.release_calls == 0
    # 给操作员的明确指令
    assert "Local Mode" in result.summary
    assert "Remote mode" in result.summary
    assert "phase=confirm" in result.summary
    assert "人工确认" in result.summary
    idn_step = next(s for s in result.steps if s.label.startswith("*IDN?"))
    assert idn_step.raw == IDN


def test_release_phase_identity_mismatch_is_aborted():
    ce = _ScriptedCe({"*IDN?": "Other,Box,1,2", "SYSTem:INFO?": "nothing"})
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"


def test_release_phase_error_queue_residue_is_archived():
    ce = _ScriptedCe(err_queue=['-100,"ATE command not supported"'])
    result = _run(ce)
    assert ce.queries.count("SYSTem:ERRor?") == 2
    assert result.extra["residue_clean"] is False
    assert result.extra["verdict"] == "UNDETERMINED"


# ── confirm 段 ───────────────────────────────────────────────────────────────

def test_confirm_phase_sends_zero_scpi():
    ce = _ScriptedCe()
    result = _run(ce, {
        "phase": "confirm",
        "operator_observation": "背景 Remote mode 水印消失，Local Mode 按钮不再亮蓝",
        "operator_confirmed_local": True,
    })
    assert ce.queries == []
    assert ce.release_calls == 0
    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"


def test_confirm_phase_records_observation_as_onsite_evidence():
    obs = "背景 Remote mode 水印消失，Local Mode 按钮不再亮蓝"
    ce = _ScriptedCe()
    result = _run(ce, {
        "phase": "confirm", "operator_observation": obs, "operator_confirmed_local": True,
    })
    assert result.extra["evidence_kind"] == "onsite-observed"
    assert result.extra["operator_observation"] == obs
    assert result.extra["operator_confirmed_local"] is True
    assert "人工面板观察" in result.summary
    assert "非 SCPI 证据" in result.summary


def test_confirm_phase_false_is_blocker():
    ce = _ScriptedCe()
    result = _run(ce, {
        "phase": "confirm",
        "operator_observation": "Local Mode 按钮仍是蓝色，背景仍显示 Remote mode",
        "operator_confirmed_local": False,
    })
    assert ce.queries == []
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    assert result.extra["operator_confirmed_local"] is False
    assert "人工面板观察" in result.summary


def test_confirm_phase_missing_observation_is_undetermined_naming_the_gap():
    ce = _ScriptedCe()
    result = _run(ce, {"phase": "confirm", "operator_confirmed_local": True})
    assert ce.queries == []
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "operator_observation" in result.summary
    assert result.extra["missing"] == ["operator_observation"]


def test_confirm_phase_missing_boolean_is_undetermined():
    ce = _ScriptedCe()
    result = _run(ce, {"phase": "confirm", "operator_observation": "看了面板"})
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["missing"] == ["operator_confirmed_local"]
    assert "operator_confirmed_local" in result.summary


def test_confirm_phase_accepts_string_booleans_from_api_callers():
    ce = _ScriptedCe()
    result = _run(ce, {
        "phase": "confirm", "operator_observation": "看了面板", "operator_confirmed_local": "true",
    })
    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["operator_confirmed_local"] is True


def test_unknown_phase_is_aborted_without_scpi():
    ce = _ScriptedCe()
    result = _run(ce, {"phase": "whatever"})
    assert ce.queries == []
    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"
    assert "release" in result.summary and "confirm" in result.summary


# ── F4：判据文本必须与手册 §20.1 同向 ──────────────────────────────────────

def test_operator_facing_texts_follow_manual_button_semantics():
    """§20.1 原文：Remote 态下 "the Local Mode button … is activated (turns blue)" ——
    按钮亮 / 可点是 **Remote** 的标志。给操作员看的 label 与指令不得写"按钮可点 = 已回 Local"，
    判据只留手册有据的"水印消失 / 按钮不再亮蓝"。"""
    texts = [p["label"] for p in seq.metadata.params_schema] + [
        seq._RELEASE_INSTRUCTIONS, seq.metadata.description,
    ]
    for t in texts:
        assert "按钮可点" not in t, t
        assert "可点" not in t, t
    confirm_label = next(p for p in seq.metadata.params_schema
                         if p["name"] == "operator_confirmed_local")["label"]
    assert "水印" in confirm_label and "亮蓝" in confirm_label
    assert "水印" in seq._RELEASE_INSTRUCTIONS and "亮蓝" in seq._RELEASE_INSTRUCTIONS
    # release 段 summary 就是这段指令，运行态也要同向
    result = _run(_ScriptedCe())
    assert "可点" not in result.summary
    assert "水印" in result.summary
