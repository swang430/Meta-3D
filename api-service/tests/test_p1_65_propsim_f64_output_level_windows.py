"""P1-65 NEW-1：F64 各口输出电平窗口核对序列的行为门。

故障形态（2026-08-07 实测）：口 1 的 `OUTPut:LEVel:AMPlitude:LIMits? 1` 返回
`-166.60,-51.61`，而我们下发的是 `-50.00` —— 落在窗外，仪器静默钳位，现场无载体
能在测试前把这件事亮出来。本序列只读：`DIAG:SIMU:STATE?` 前置 → 逐口
`LIMits?` + `CH?` → 结尾 `SYSTem:ERRor?` 零残留。

手册依据（Propsim User Reference Rev 10.2）：§20.4 开篇「Most PROPSIM ATE commands
are only available when emulation has been opened」；§20.4.5.4 `CH?` 返回单个 dBm 数；
§20.4.5.5 `LIMits?` 返回 `<lower>,<higher>`。
"""
import asyncio
from unittest.mock import MagicMock

from app.diagnostics.sequences import propsim_f64_output_level_windows as seq

IDN = "Keysight Technologies,F8800A,FI1234567,8.0"
SYS_INFO = "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,Main license,Shadowing"

_READ_ONLY_TAILS = ("?",)


class _ScriptedCe:
    """回放式假驱动：按命令返回脚本化回复，记录全部命令。

    `SYSTem:ERRor?` 按 FIFO 弹 `err_queue`，弹空后恒回 `0,"No error"`。
    `raise_for` 里的命令抛 TimeoutError（模拟 VISA 超时，驱动 `_query` 的真实形态是抛）。
    """

    def __init__(self, replies, *, err_queue=None, raise_for=(), active_outputs=None):
        self._replies = dict(replies)
        self._err_queue = list(err_queue or [])
        self._raise_for = set(raise_for)
        self.queries = []
        if active_outputs is not None:
            self._active_output_ports = list(active_outputs)

    def _query(self, cmd):
        self.queries.append(cmd)
        if cmd in self._raise_for:
            raise TimeoutError(f"VI_ERROR_TMO on {cmd}")
        if cmd == "SYSTem:ERRor?":
            return self._err_queue.pop(0) if self._err_queue else '0,"No error"'
        if cmd not in self._replies:
            raise AssertionError(f"序列发了脚本外的命令: {cmd!r}")
        return self._replies[cmd]


class MockChannelEmulator:
    def _query(self, cmd):  # pragma: no cover - 不该被调到
        raise AssertionError("mock 驱动不该被查询")


def _base_replies(state="STOPPED", ports=(1, 2)):
    replies = {
        "*IDN?": IDN,
        "SYSTem:INFO?": SYS_INFO,
        "DIAG:SIMU:STATE?": state,
    }
    for n in ports:
        replies[f"OUTPut:LEVel:AMPlitude:LIMits? {n}"] = "-68.8401,-23.8401"
        replies[f"OUTPut:LEVel:AMPlitude:CH? {n}"] = "-40"
    return replies


def _run(ce, params=None):
    hal = MagicMock()
    hal.drivers = {"channelEmulator": ce}
    return asyncio.run(seq.run(MagicMock(), hal, params or {}, log=lambda *_: None))


def _assert_read_only(ce):
    """只读不变量：所有命令都是查询（以 ? 结尾，允许带参数），且绝不含手册查无的两条。"""
    for cmd in ce.queries:
        head = cmd.split(" ", 1)[0]
        assert head.endswith(_READ_ONLY_TAILS), f"发了写命令: {cmd!r}"
    forbidden = {"SYSTem:CALibration:USER:LIST?", "OUTPut:INTERFerence:LIST?"}
    assert not (set(ce.queries) & forbidden), "发了手册查无的探针命令"


# ── 门：前置拒绝 ────────────────────────────────────────────────────────────

def test_driver_not_loaded_is_refused():
    hal = MagicMock()
    hal.drivers = {}
    result = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
    assert result.success is False
    assert "未加载 channelEmulator" in result.summary


def test_mock_driver_is_refused():
    result = _run(MockChannelEmulator())
    assert result.success is False
    assert "mock" in result.summary


def test_metadata_declares_channel_emulator_and_outputs_param():
    assert seq.metadata.required_categories == ["channelEmulator"]
    names = {p["name"] for p in seq.metadata.params_schema}
    assert "outputs" in names
    assert seq.metadata.safe_during_test is False


# ── 门：四态各一条行为门 ────────────────────────────────────────────────────

def test_all_ports_in_window_is_success_and_read_only():
    ce = _ScriptedCe(_base_replies(), active_outputs=[1, 2])
    result = _run(ce)
    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["ports"]["1"]["in_window"] is True
    assert result.extra["ports"]["1"] == {
        "lower": -68.8401, "higher": -23.8401, "current": -40.0, "in_window": True,
    }
    assert result.extra["port_source"] == "driver_active_output_ports"
    _assert_read_only(ce)
    # 逐口两条查询都发了，且拼法是手册 §20.4.5.4/5 的（CH 后直接 ?，不带 GET）
    assert "OUTPut:LEVel:AMPlitude:LIMits? 1" in ce.queries
    assert "OUTPut:LEVel:AMPlitude:CH? 1" in ce.queries
    assert "OUTPut:LEVel:AMPlitude:CH? 2" in ce.queries
    # raw 原样进 step
    raws = {s.raw for s in result.steps if s.raw is not None}
    assert "-68.8401,-23.8401" in raws and "-40" in raws


def test_port_out_of_window_is_blocker_naming_port_and_window():
    """08-07 故障形态：口 1 窗口 -166.60,-51.61 而当前 -50.00 → BLOCKER 点名口号与窗口。"""
    replies = _base_replies(ports=(1, 2))
    replies["OUTPut:LEVel:AMPlitude:LIMits? 1"] = "-166.60,-51.61"
    replies["OUTPut:LEVel:AMPlitude:CH? 1"] = "-50.00"
    ce = _ScriptedCe(replies, active_outputs=[1, 2])
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    assert result.extra["out_of_window"] == [1]
    assert result.extra["ports"]["1"]["in_window"] is False
    assert result.extra["ports"]["2"]["in_window"] is True
    assert "口 1" in result.summary
    assert "-166.6" in result.summary and "-51.61" in result.summary
    assert "-50.0" in result.summary
    _assert_read_only(ce)


def test_unparseable_reply_is_unknown_port_and_undetermined():
    replies = _base_replies(ports=(1, 2))
    replies["OUTPut:LEVel:AMPlitude:CH? 2"] = ""  # 空回复 / 非数值
    ce = _ScriptedCe(replies, active_outputs=[1, 2])
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["unknown_ports"] == [2]
    assert result.extra["ports"]["2"]["in_window"] is None
    assert result.extra["ports"]["2"]["current"] is None
    assert result.extra["out_of_window"] == []


def test_closed_state_sends_no_per_port_query_and_is_undetermined():
    """§20.4 开篇：多数 ATE 命令仅在仿真打开后可用 → CLOSED 时先查状态、不盲发。"""
    ce = _ScriptedCe(_base_replies(state="CLOSED"), active_outputs=[1, 2])
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["state"] == "CLOSED"
    assert not [q for q in ce.queries if q.startswith("OUTPut:LEVel")]
    assert "未发" in result.summary
    _assert_read_only(ce)


def test_identity_mismatch_is_aborted_without_port_queries():
    replies = _base_replies()
    replies["*IDN?"] = "Rohde&Schwarz,SMW200A,1,2"
    replies["SYSTem:INFO?"] = "something else"
    ce = _ScriptedCe(replies, active_outputs=[1])
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"
    assert not [q for q in ce.queries if q.startswith("OUTPut:LEVel")]


def test_query_timeout_is_unknown_then_three_in_a_row_aborts():
    replies = _base_replies(ports=(1, 2, 3, 4))
    ce = _ScriptedCe(
        replies, active_outputs=[1, 2, 3, 4],
        raise_for={
            "OUTPut:LEVel:AMPlitude:LIMits? 2",
            "OUTPut:LEVel:AMPlitude:CH? 2",
            "OUTPut:LEVel:AMPlitude:LIMits? 3",
        },
    )
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"
    # 三连超时即停：口 3 的 CH? 与口 4 两条都不再发；通道已卡死也不再读错误队列
    assert "OUTPut:LEVel:AMPlitude:CH? 3" not in ce.queries
    assert not [q for q in ce.queries if q.endswith(" 4")]
    assert ce.queries[-1] == "OUTPut:LEVel:AMPlitude:LIMits? 3"
    assert result.extra["residue_clean"] is None
    assert "超时" in result.summary
    # 口 2 的记录保留 UNKNOWN，不被丢掉
    assert result.extra["ports"]["2"]["in_window"] is None


# ── 门：口集来源 ─────────────────────────────────────────────────────────────

def test_explicit_outputs_param_overrides_driver_ports():
    replies = _base_replies(ports=(3, 7))
    ce = _ScriptedCe(replies, active_outputs=[1, 2])
    result = _run(ce, {"outputs": "3, 7"})
    assert result.extra["port_source"] == "param"
    assert sorted(int(k) for k in result.extra["ports"]) == [3, 7]
    assert "OUTPut:LEVel:AMPlitude:LIMits? 1" not in ce.queries


def test_fallback_to_syst_info_channel_count_is_labelled():
    """驱动没有回读口集时退到 SYSTem:INFO? 第 2 字段，且 extra 如实标注来源
    （那是整机衰落通道数，不是输出口数 —— 驱动注释明说两者单位不同）。"""
    replies = _base_replies(ports=(1, 2, 3))
    replies["SYSTem:INFO?"] = "PROPSIM F64,3,RF,v1.0,16,Band: 450MHz - 3000MHz,Main license"
    ce = _ScriptedCe(replies)  # 无 _active_output_ports
    result = _run(ce)
    assert result.extra["port_source"] == "syst_info_channel_count"
    assert sorted(int(k) for k in result.extra["ports"]) == [1, 2, 3]
    assert result.extra["verdict"] == "SUCCESS"


def test_invalid_outputs_param_is_aborted_without_scpi_to_ports():
    ce = _ScriptedCe(_base_replies(), active_outputs=[1])
    result = _run(ce, {"outputs": "1,abc"})
    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"
    assert not [q for q in ce.queries if q.startswith("OUTPut:LEVel")]


# ── 门：错误队列结尾读取 ─────────────────────────────────────────────────────

def test_error_queue_is_read_at_end_until_no_error():
    ce = _ScriptedCe(_base_replies(), active_outputs=[1, 2],
                     err_queue=['-222,"Data out of range"'])
    result = _run(ce)
    # 最后一条命令必是 SYSTem:ERRor?，且读到 0 为止（残留 1 条 + 终止 1 条）
    assert ce.queries[-1] == "SYSTem:ERRor?"
    assert ce.queries.count("SYSTem:ERRor?") == 2
    assert result.extra["residue_clean"] is False
    # 残留不让它报绿
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.success is False


def test_clean_error_queue_is_read_once_and_marked_clean():
    ce = _ScriptedCe(_base_replies(), active_outputs=[1, 2])
    result = _run(ce)
    assert ce.queries[-1] == "SYSTem:ERRor?"
    assert ce.queries.count("SYSTem:ERRor?") == 1
    assert result.extra["residue_clean"] is True
