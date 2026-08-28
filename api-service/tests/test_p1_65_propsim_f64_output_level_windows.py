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
    ports = tuple(ports)
    replies = {
        "*IDN?": IDN,
        "SYSTem:INFO?": SYS_INFO,
        "DIAG:SIMU:STATE?": state,
        "DIAG:SIMU:MODEL:INFO?": f"2,{2 * len(ports)},{len(ports)}",
        "GROUP:GET?": "1",
        "GROUP:OUTPUTS:GET? 1": ",".join(str(port) for port in ports),
    }
    for n in ports:
        replies[f"OUTPut:LEVel:AMPlitude:LIMits? {n}"] = "-68.8401,-23.8401"
        replies[f"OUTPut:LEVel:AMPlitude:CH? {n}"] = "-40"
    return replies


def _with_live_topology(replies, *, ports=(1, 2), model_outputs=None):
    """加入当前仿真的手册拓扑回读；不借驱动缓存声明活动口。"""
    out = dict(replies)
    live_ports = list(ports)
    output_count = len(live_ports) if model_outputs is None else model_outputs
    out["DIAG:SIMU:MODEL:INFO?"] = f"2,{2 * output_count},{output_count}"
    out["GROUP:GET?"] = "1"
    out["GROUP:OUTPUTS:GET? 1"] = ",".join(str(port) for port in live_ports)
    return out


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


def test_metadata_declares_channel_emulator_without_manual_output_override():
    assert seq.metadata.required_categories == ["channelEmulator"]
    assert seq.metadata.params_schema == []
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
    assert result.extra["port_source"] == "live_group_output_union"
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

def test_cold_cache_uses_live_group_output_union_not_system_channel_count():
    """现场故障：缓存为空时不得把 SYSTem:INFO? 的 32 个衰落通道当 32 个输出口。"""
    replies = _with_live_topology(_base_replies(ports=(1, 2)), ports=(1, 2))
    replies["SYSTem:INFO?"] = "PROPSIM F64,32,RF,v1.0,16,Band: 450MHz - 3000MHz"
    ce = _ScriptedCe(replies)  # 冷缓存：无 _active_output_ports

    result = _run(ce)

    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["port_source"] == "live_group_output_union"
    assert sorted(int(key) for key in result.extra["ports"]) == [1, 2]
    assert "OUTPut:LEVel:AMPlitude:LIMits? 3" not in ce.queries


def test_stale_driver_cache_cannot_override_live_group_output_union():
    """前面板换场景后旧 32 口缓存不得覆盖本次实时读到的 2 个活动口。"""
    replies = _with_live_topology(_base_replies(ports=(2, 4)), ports=(2, 4))
    ce = _ScriptedCe(replies, active_outputs=list(range(1, 33)))

    result = _run(ce)

    assert result.extra["verdict"] == "SUCCESS"
    assert sorted(int(key) for key in result.extra["ports"]) == [2, 4]
    assert not [
        query for query in ce.queries
        if query.startswith("OUTPut:LEVel") and query.endswith(" 1")
    ]


def test_explicit_outputs_param_cannot_narrow_live_activity_truth():
    """人工口集不能跳过真实活动口后给出 SUCCESS。"""
    replies = _with_live_topology(_base_replies(ports=(1, 2)), ports=(1, 2))
    ce = _ScriptedCe(replies, active_outputs=[1, 2])

    result = _run(ce, {"outputs": "1"})

    assert result.extra["verdict"] == "ABORTED"
    assert not [query for query in ce.queries if query.startswith("OUTPut:LEVel")]


def test_missing_live_topology_does_not_fallback_to_system_channel_count():
    """实时拓扑缺失时不得退到 SYSTem:INFO? 的整机衰落通道数。"""
    replies = _base_replies(ports=(1, 2, 3))
    replies["SYSTem:INFO?"] = "PROPSIM F64,3,RF,v1.0,16,Band: 450MHz - 3000MHz,Main license"
    replies.pop("DIAG:SIMU:MODEL:INFO?")
    replies.pop("GROUP:GET?")
    replies.pop("GROUP:OUTPUTS:GET? 1")
    ce = _ScriptedCe(replies)
    result = _run(ce)
    assert result.extra["port_source"] is None
    assert result.extra["ports"] == {}
    assert result.extra["verdict"] == "UNDETERMINED"
    assert not [query for query in ce.queries if query.startswith("OUTPut:LEVel")]


def test_model_output_count_mismatch_is_visible_and_sends_no_level_queries():
    """MODEL 数量与 group 并集打架时，必须有显式失败 step，不能只在摘要里悄悄降级。"""
    replies = _with_live_topology(
        _base_replies(ports=(2, 4)),
        ports=(2, 4),
        model_outputs=3,
    )
    ce = _ScriptedCe(replies)

    result = _run(ce)

    assert result.extra["verdict"] == "UNDETERMINED"
    assert not [query for query in ce.queries if query.startswith("OUTPut:LEVel")]
    cross_checks = [step for step in result.steps if step.label == "活动输出集合交叉核对"]
    assert len(cross_checks) == 1
    assert cross_checks[0].success is False
    assert "outputs=3" in cross_checks[0].detail


def test_success_discloses_that_non_active_hardware_ports_were_not_probed():
    replies = _with_live_topology(_base_replies(ports=(2, 4)), ports=(2, 4))
    ce = _ScriptedCe(replies, active_outputs=list(range(1, 33)))

    result = _run(ce)

    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["active_output_ports"] == [2, 4]
    assert "未进入活动集合的硬件口未探测、不影响本次判定" in result.summary


def test_non_contiguous_live_output_numbers_are_queried_exactly():
    replies = _with_live_topology(_base_replies(ports=(2, 7)), ports=(2, 7))
    ce = _ScriptedCe(replies)

    result = _run(ce)

    assert result.extra["verdict"] == "SUCCESS"
    queried = {
        int(query.rsplit(" ", 1)[1])
        for query in ce.queries
        if query.startswith("OUTPut:LEVel")
    }
    assert queried == {2, 7}


def test_legacy_outputs_param_is_aborted_without_scpi_to_ports():
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


# ── F7：边界值与状态读不到 ─────────────────────────────────────────────────

def test_boundary_values_are_inside_window():
    """手册 §20.4.5.5 "Level cannot be set outside the limits"：恰好等于下限 / 上限算窗内。
    判定改成严格 < 会把边界值误报 BLOCKER。"""
    replies = _base_replies(ports=(1, 2))
    replies["OUTPut:LEVel:AMPlitude:CH? 1"] = "-68.8401"   # == lower
    replies["OUTPut:LEVel:AMPlitude:CH? 2"] = "-23.8401"   # == higher
    ce = _ScriptedCe(replies, active_outputs=[1, 2])
    result = _run(ce)
    assert result.extra["ports"]["1"]["in_window"] is True
    assert result.extra["ports"]["2"]["in_window"] is True
    assert result.extra["verdict"] == "SUCCESS"


def test_just_outside_boundary_is_blocker():
    replies = _base_replies(ports=(1,))
    replies["OUTPut:LEVel:AMPlitude:CH? 1"] = "-23.84"   # 高于上限 -23.8401 一点
    ce = _ScriptedCe(replies, active_outputs=[1])
    result = _run(ce)
    assert result.extra["verdict"] == "BLOCKER"
    assert result.extra["out_of_window"] == [1]


def test_state_none_sends_no_per_port_query_and_is_undetermined():
    """STATE? 读不到（驱动回 None）：先查状态再决定发不发 —— 读不到就不盲发逐口查询。"""
    replies = _base_replies()
    replies["DIAG:SIMU:STATE?"] = None
    ce = _ScriptedCe(replies, active_outputs=[1, 2])
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["state"] is None
    assert not [q for q in ce.queries if q.startswith("OUTPut:LEVel")]
    assert "读不到" in result.summary
    _assert_read_only(ce)


def test_state_outside_whitelist_sends_no_per_port_query():
    """会话错位的迟到应答（如 0,"No error"）不是状态 → 同样不发。"""
    replies = _base_replies(state='0,"No error"')
    ce = _ScriptedCe(replies, active_outputs=[1, 2])
    result = _run(ce)
    assert result.extra["verdict"] == "UNDETERMINED"
    assert not [q for q in ce.queries if q.startswith("OUTPut:LEVel")]
