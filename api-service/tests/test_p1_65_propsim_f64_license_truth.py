"""P1-65 / P1-2：F64 许可与校准真值序列的行为门。

故障：驱动连接时靠两条**手册查无**的软探针（`SYSTem:CALibration:USER:LIST?` /
`OUTPut:INTERFerence:LIST?`）猜许可，每次连接各留一条 -100 在错误队列
（08-07 实测 269 次连接 = 269 条），而现场没有载体能用手册有的命令把许可/校准
真值读出来跟驱动自称对账。

手册依据（Propsim User Reference Rev 10.2）：§20.4.2.4 `SYSTem:INFO?` 尾部
`<License#1>,…`（原文 "Query returns the basic system info and licenses"）；
§20.4.2.11/12/13 `CALIBration:GET?/LIST?/VALid?`；§20.4.2.19/21 `USER:GET?/INFO?`；
§20.4.9.5 `OUTPut:INTERFerence:GET?`（"List all the interferers in emulation"，
无干扰源返回 0）—— §20.4 开篇「多数 ATE 命令仅在仿真打开后可用」→ 先 STATE? 再决定发不发。
"""
import asyncio
from unittest.mock import MagicMock

from app.diagnostics.sequences import propsim_f64_license_truth as seq

IDN = "Keysight Technologies,F8800A,FI1234567,8.0"
SYS_INFO = (
    "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,"
    "Main license,Interference Generator,Shadowing"
)

FORBIDDEN = {"SYSTem:CALibration:USER:LIST?", "OUTPut:INTERFerence:LIST?"}


class _ScriptedCe:
    def __init__(self, replies, *, err_queue=None, raise_for=(), installed_options=None):
        self._replies = dict(replies)
        self._err_queue = list(err_queue or [])
        self._raise_for = set(raise_for)
        self.queries = []
        if installed_options is not None:
            self._installed_options = list(installed_options)
            # 与生产驱动同形：关键字 → canonical token（序列从驱动实例上取，不另抄）
            self._F64_SYSTINFO_KEYWORDS = {
                "interference": "INT-GEN",
                "user alignment": "USER-ALIGN",
            }

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
    def _query(self, cmd):  # pragma: no cover
        raise AssertionError("mock 驱动不该被查询")


def _replies(state="STOPPED", **over):
    base = {
        "*IDN?": IDN,
        "SYSTem:INFO?": SYS_INFO,
        "SYSTem:CALIBration:LIST?": "LTETestSetup,WCDMATestSetup",
        "SYSTem:CALIBration:VALid?": "1,1",
        "SYSTem:CALIBration:GET?": "LTETestSetup",
        "SYSTem:CALIBration:USER:GET?": "",
        "SYSTem:CALIBration:USER:INFO?": "",
        "DIAG:SIMU:STATE?": state,
        "OUTPut:INTERFerence:GET?": "0",
    }
    base.update(over)
    return base


def _run(ce, params=None):
    hal = MagicMock()
    hal.drivers = {"channelEmulator": ce}
    return asyncio.run(seq.run(MagicMock(), hal, params or {}, log=lambda *_: None))


def _assert_read_only(ce):
    for cmd in ce.queries:
        assert cmd.split(" ", 1)[0].endswith("?"), f"发了写命令: {cmd!r}"
    assert not (set(ce.queries) & FORBIDDEN), "发了手册查无的驱动探针命令"


# ── 前置拒绝 ─────────────────────────────────────────────────────────────────

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


def test_metadata():
    assert seq.metadata.required_categories == ["channelEmulator"]
    assert seq.metadata.safe_during_test is False


# ── 主路径：全部有回复 → SUCCESS，且只读、不发编造命令 ──────────────────────

def test_all_replies_is_success_read_only_and_raw_archived():
    ce = _ScriptedCe(_replies(), installed_options=["INT-GEN"])
    result = _run(ce)
    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"
    _assert_read_only(ce)
    for cmd in (
        "SYSTem:INFO?", "SYSTem:CALIBration:LIST?", "SYSTem:CALIBration:VALid?",
        "SYSTem:CALIBration:GET?", "SYSTem:CALIBration:USER:GET?",
        "SYSTem:CALIBration:USER:INFO?", "DIAG:SIMU:STATE?", "OUTPut:INTERFerence:GET?",
    ):
        assert cmd in ce.queries, cmd
    raws = {s.raw for s in result.steps if s.raw is not None}
    assert SYS_INFO in raws and "1,1" in raws and "0" in raws
    # 许可列表从 SYSTem:INFO? 尾部解析（不是探针）
    assert result.extra["licenses"] == ["Main license", "Interference Generator", "Shadowing"]
    assert result.extra["calibration"]["in_use"] is True
    assert result.extra["calibration"]["valid"] is True
    assert result.extra["calibration"]["current"] == "LTETestSetup"
    assert result.extra["user_alignment"]["enabled"] is False
    assert result.extra["interference"]["sent"] is True
    assert result.extra["interference"]["sources"] == []


def test_closed_state_does_not_send_interference_get():
    ce = _ScriptedCe(_replies(state="CLOSED"), installed_options=[])
    result = _run(ce)
    assert "OUTPut:INTERFerence:GET?" not in ce.queries
    assert result.extra["interference"]["sent"] is False
    assert "无已加载仿真" in result.extra["interference"]["reason"]
    # 未发不算失败
    assert result.extra["verdict"] == "SUCCESS"
    _assert_read_only(ce)


def test_unreadable_state_does_not_send_interference_get():
    ce = _ScriptedCe(_replies(state='0,"No error"'), installed_options=[])
    result = _run(ce)
    assert "OUTPut:INTERFerence:GET?" not in ce.queries
    assert result.extra["interference"]["sent"] is False
    assert result.extra["verdict"] == "SUCCESS"


def test_interference_sources_are_parsed_in_triples():
    ce = _ScriptedCe(
        _replies(**{"OUTPut:INTERFerence:GET?": "1, TX1_AWGN, 1, 2, TX2_CW, 2"}),
        installed_options=["INT-GEN"],
    )
    result = _run(ce)
    assert result.extra["interference"]["sources"] == [
        {"output": 1, "id": "TX1_AWGN", "type": 1},
        {"output": 2, "id": "TX2_CW", "type": 2},
    ]


# ── 超时 → BLOCKER ───────────────────────────────────────────────────────────

def test_any_query_timeout_is_blocker():
    ce = _ScriptedCe(_replies(), raise_for={"SYSTem:CALIBration:VALid?"}, installed_options=[])
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    assert "SYSTem:CALIBration:VALid?" in result.summary
    assert result.extra["failed_queries"] == ["SYSTem:CALIBration:VALid?"]


def test_none_reply_is_blocker_but_empty_string_is_not():
    """None = 驱动没拿到回复（如 socket 已释放），"" = 仪器回了空串（USER:GET? 未启用的合法回复）。"""
    ce = _ScriptedCe(_replies(**{"SYSTem:CALIBration:GET?": None}), installed_options=[])
    result = _run(ce)
    assert result.extra["verdict"] == "BLOCKER"
    assert result.extra["failed_queries"] == ["SYSTem:CALIBration:GET?"]


# ── 对账：驱动自称 vs 手册列表；探针命令手册查无的措辞 ───────────────────────

def test_driver_token_reconciliation_both_directions():
    """驱动自称 USER-ALIGN 但 SYSTem:INFO? 没有对应许可字样；手册列表里有
    Interference 字样但驱动没记 INT-GEN → 两向差异都要列出，措辞恒为
    「驱动探针命令手册查无」，不说「仪器不支持」。"""
    ce = _ScriptedCe(_replies(), installed_options=["USER-ALIGN"])
    result = _run(ce)
    d = result.extra["driver_probe_discrepancy"]
    assert d["driver_tokens"] == ["USER-ALIGN"]
    assert d["driver_claims_without_manual_hit"] == ["USER-ALIGN"]
    assert d["manual_hits_without_driver_token"] == ["INT-GEN"]
    assert d["keyword_hits"]["INT-GEN"] == ["Interference Generator"]
    assert sorted(d["driver_probe_commands_not_in_manual"]) == sorted(FORBIDDEN)
    assert "手册查无" in d["note"]
    assert "不支持" not in d["note"]
    assert "不支持" not in result.summary
    # 对账差异只进 extra 与 summary 后缀，不算失败
    assert result.success is True
    assert "对账" in result.summary


def test_reconciliation_consistent_is_reported_empty():
    ce = _ScriptedCe(_replies(), installed_options=["INT-GEN"])
    result = _run(ce)
    d = result.extra["driver_probe_discrepancy"]
    assert d["driver_claims_without_manual_hit"] == []
    assert d["manual_hits_without_driver_token"] == []


def test_driver_without_options_attribute_still_reports():
    ce = _ScriptedCe(_replies())  # 无 _installed_options / 关键字表
    result = _run(ce)
    d = result.extra["driver_probe_discrepancy"]
    assert d["driver_tokens"] == []
    assert d["keyword_map_available"] is False
    assert result.extra["verdict"] == "SUCCESS"


# ── 错误队列结尾读取 ─────────────────────────────────────────────────────────

def test_error_queue_read_at_end_until_clean_and_residue_blocks_green():
    ce = _ScriptedCe(_replies(), err_queue=['-100,"ATE command not supported"'],
                     installed_options=[])
    result = _run(ce)
    assert ce.queries[-1] == "SYSTem:ERRor?"
    assert ce.queries.count("SYSTem:ERRor?") == 2
    assert result.extra["residue_clean"] is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.success is False


def test_identity_mismatch_aborts_before_license_queries():
    ce = _ScriptedCe(_replies(**{"*IDN?": "Other,Box,1,2", "SYSTem:INFO?": "nothing"}))
    result = _run(ce)
    assert result.success is False
    assert result.extra["verdict"] == "ABORTED"
    assert "SYSTem:CALIBration:LIST?" not in ce.queries
