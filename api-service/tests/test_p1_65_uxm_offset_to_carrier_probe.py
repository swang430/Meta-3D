"""P1-65 / NEW-3: `uxm_offset_to_carrier_probe` 的行为门。

故障：roadmap「Blocked on hardware」NEW-3（UXM OffsetToCarrier 是否需下发 102）
没有任何 checked-in 载体，到现场只能临时敲命令（P1-45 禁止）。

本序列的契约（设计稿 docs/plans/2026-08-23-p1-65-blocker-carrier-sequences-design.md §1/§3）：
- 默认**只读**：PointA / OTCarrier / ARFCN / 小区状态，把基线建议值放进 extra，不下发；
- 写只在 `offset_to_carrier` + `confirm_write=True` **且小区 OFF** 时发；写后回读 + 错误队列；
  **不发 APPLY**；
- 只在 BSE 方言（LTE_NR_IRAT）发新命令；5G_NR_Test 方言下命令形式未经手册证实 → 不发，
  UNDETERMINED；
- 每步后读 `SYSTem:ERRor?`；四态 `extra["verdict"]`。

回放式假驱动照 `tests/test_p1_58_irat_compat_sequence.py` 的 `_ScriptedBs`。
"""
from __future__ import annotations

import asyncio
from typing import Dict, List
from unittest.mock import MagicMock

from app.diagnostics.sequences import uxm_offset_to_carrier_probe as seq
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)

CELL = UxmLteNrIratProfile.PRIMARY_CELL
ERR = UxmLteNrIratProfile.ERR
SWITCH_Q = UxmLteNrIratProfile.CELL_STATE_QUERY.format(cell=CELL)
STATUS_Q = UxmLteNrIratProfile.CELL_STATUS_QUERY.format(cell=CELL)
ARFCN_Q = UxmLteNrIratProfile.CELL_DL_ARFCN.format(cell=CELL) + "?"
POINTA_Q = f"BSE:CONFig:NR5G:{CELL}:DL:POINta?"
OTC_Q = f"BSE:CONFig:NR5G:{CELL}:DL:OTCarrier?"
OTC_HEADER = f"BSE:CONFig:NR5G:{CELL}:DL:OTCarrier"

# 只读路径**不得**出现的东西：任何写命令 / APPLY / 驱动里手册查无的状态命令
_FORBIDDEN_IN_READONLY = (
    "APPLY", "SYSTem:CONFiguration:LOAD", "MMEMory:CATalog?", "SYSTem:PRESet",
)


class _ScriptedBs:
    """回放式假驱动：按命令回脚本化回复；记录全部 query / write。

    `err_after` 把「上一条非 ERR 命令」映射到 SYSTem:ERRor? 的回复，默认全干净。
    `otc_after_write` 模拟写后回读值（默认 = 写入值，即仪器接受了）。
    """

    def __init__(self, profile=UxmLteNrIratProfile, *, responses=None,
                 err_after=None, otc_after_write=None, raise_on=None):
        self._cmds = profile
        self.queries: List[str] = []
        self.writes: List[str] = []
        self.ops: List[str] = []   # 按实际发出顺序（query 与 write 混排）
        self._responses: Dict[str, str] = {
            SWITCH_Q: "0",
            STATUS_Q: "OFF",
            ARFCN_Q: "636666",
            POINTA_Q: "632946",
            OTC_Q: "0",
        }
        self._responses.update(responses or {})
        self._err_after = err_after or {}
        self._otc_after_write = otc_after_write
        self._raise_on = raise_on
        self._last = None
        self._written_otc = None

    def _query(self, cmd):
        self.queries.append(cmd)
        self.ops.append(cmd)
        if self._raise_on and cmd == self._raise_on:
            raise TimeoutError(f"timeout on {cmd}")
        if cmd == ERR:
            last = self._last
            return self._err_after.get(last, '0,"No error"')
        self._last = cmd
        if cmd == OTC_Q and self._written_otc is not None:
            return (self._otc_after_write
                    if self._otc_after_write is not None else self._written_otc)
        return self._responses.get(cmd, "")

    def _write(self, cmd):
        self.writes.append(cmd)
        self.ops.append(cmd)
        self._last = cmd
        if cmd.startswith(OTC_HEADER + " "):
            self._written_otc = cmd.split(" ", 1)[1].strip()


def _run(bs, params=None, hal=None):
    hal = hal or MagicMock()
    hal.drivers = {"baseStation": bs}
    return asyncio.run(seq.run(
        MagicMock(), hal, params or {}, log=lambda *_: None,
    ))


def _all_commands(bs) -> List[str]:
    return list(bs.ops)


def _assert_err_after_every_step(bs):
    """不变量：每条非 ERR 命令之后**紧跟**一次 SYSTem:ERRor?（按实际发出顺序）。"""
    ops = bs.ops
    assert ops, "没发任何命令"
    for i, cmd in enumerate(ops):
        if cmd == ERR:
            continue
        assert i + 1 < len(ops) and ops[i + 1] == ERR, (
            f"第 {i} 条 {cmd!r} 之后没有紧跟错误队列读取: {ops[i + 1:i + 2]}"
        )
    assert ops[-1] == ERR, "最后一条必须是错误队列读取"


# ── 门 0：元数据 / 品类声明 ────────────────────────────────────────────

def test_metadata_declares_base_station_and_is_not_safe_during_test():
    assert seq.metadata.required_categories == ["baseStation"]
    assert seq.metadata.safe_during_test is False
    names = {p["name"] for p in seq.metadata.params_schema}
    assert {"cell", "offset_to_carrier", "confirm_write"} <= names


# ── 门 1：拒绝 mock / 未加载 ──────────────────────────────────────────

def test_refuses_mock_driver_without_scpi():
    class MockUxm:  # 名字以 Mock 开头 = HAL mock 模式
        _cmds = UxmLteNrIratProfile

        def _query(self, _):
            raise AssertionError("mock 驱动不该收到任何命令")

    bs = MockUxm()
    result = _run(bs)
    assert result.success is False
    assert "mock" in result.summary
    assert result.steps == []


def test_refuses_when_driver_not_loaded():
    hal = MagicMock()
    hal.drivers = {}
    result = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
    assert result.success is False
    assert "未加载 baseStation" in result.summary


# ── 门 2：方言门 —— 5G_NR_Test 下不发新命令 ───────────────────────────

def test_5gnr_dialect_sends_nothing_and_is_undetermined():
    bs = _ScriptedBs(Uxm5GNRTestAppProfile)
    result = _run(bs, {"offset_to_carrier": "102", "confirm_write": True})
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert _all_commands(bs) == [], "5G_NR_Test 方言下一条命令都不该发"
    assert "未查证" in result.summary
    assert "5G_NR_Test" in result.summary


# ── 门 3：只读路径 ─────────────────────────────────────────────────────

def test_readonly_collects_all_four_and_never_writes():
    bs = _ScriptedBs()
    result = _run(bs)

    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.success is False
    # 四项都采到了
    assert result.extra["readback"] == {
        "cell_switch": "0", "cell_status": "OFF",
        "dl_arfcn": "636666", "dl_point_a": "632946", "dl_offset_to_carrier": "0",
    }
    # 不变量：只读路径零写命令
    assert bs.writes == []
    for tok in _FORBIDDEN_IN_READONLY:
        assert not any(tok in c for c in _all_commands(bs)), tok
    # 发出去的就是手册那几条，没有别的
    assert set(bs.queries) == {SWITCH_Q, STATUS_Q, ARFCN_Q, POINTA_Q, OTC_Q, ERR}
    _assert_err_after_every_step(bs)
    # 采集到的都落进 raw（归档可比对）
    raws = {s.raw for s in result.steps if s.raw is not None}
    assert {"0", "OFF", "636666", "632946"} <= raws
    assert "不下发" in result.summary or "未下发" in result.summary


def test_readonly_baseline_is_suggested_from_arfcn_match_not_sent():
    """基线：ARFCN 636666 匹配 N78 → 建议 offset_to_carrier=102 进 extra；不发任何写。"""
    bs = _ScriptedBs()
    result = _run(bs)
    baseline = result.extra["baseline"]
    assert baseline["band"] == "N78"
    assert baseline["offset_to_carrier"] == 102
    assert baseline["point_a_arfcn"] == 632946
    assert baseline["source"] == "arfcn_match"
    assert result.extra["baseline_comparison"] == {
        "offset_to_carrier_matches_baseline": False,   # 仪器 0 vs 基线 102
        "point_a_matches_baseline": True,
    }
    assert bs.writes == []
    assert "102" in result.summary


def test_readonly_baseline_unknown_arfcn_is_disclosed():
    bs = _ScriptedBs(responses={ARFCN_Q: "123456"})
    result = _run(bs)
    assert result.extra["baseline"] is None
    assert result.extra["baseline_comparison"] is None
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "基线" in result.summary


def test_readonly_band_param_overrides_arfcn_match():
    bs = _ScriptedBs(responses={ARFCN_Q: "123456"})
    result = _run(bs, {"band": "n41"})
    assert result.extra["baseline"]["band"] == "N41"
    assert result.extra["baseline"]["source"] == "param"


def test_readonly_query_rejected_is_recorded_not_hidden():
    """OTCarrier? 查询形式是推断：固件回 -113 时要如实记录，仍是 UNDETERMINED，
    措辞不得写成「不支持」。"""
    bs = _ScriptedBs(err_after={OTC_Q: '-113,"Undefined header"'})
    result = _run(bs)
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["readback_errors"] == {OTC_Q: '-113,"Undefined header"'}
    otc_err_steps = [s for s in result.steps if s.label.startswith("OTCarrier") and "ERRor" in s.label]
    assert otc_err_steps and otc_err_steps[0].success is False
    assert "不支持" not in result.summary


# ── 门 4：写路径 —— 不确认不写 / 小区 ON 不写 ────────────────────────

def test_write_without_confirm_does_not_write():
    bs = _ScriptedBs()
    result = _run(bs, {"offset_to_carrier": "102"})
    assert bs.writes == []
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["write"]["attempted"] is False
    assert "confirm_write" in result.extra["write"]["reason"]


def test_write_refused_when_cell_on():
    bs = _ScriptedBs(responses={SWITCH_Q: "1", STATUS_Q: "ON"})
    result = _run(bs, {"offset_to_carrier": "102", "confirm_write": True})
    assert bs.writes == []
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["write"]["attempted"] is False
    assert "ON" in result.extra["write"]["reason"]
    assert "APPLY" in result.summary  # 说明了 ON 态要 APPLY 而本序列不发


def test_write_refused_when_switch_and_status_disagree():
    """开关回声 0 但协议栈状态非 OFF（或反之）→ 状态不明，不写。"""
    bs = _ScriptedBs(responses={SWITCH_Q: "0", STATUS_Q: "IDLE"})
    result = _run(bs, {"offset_to_carrier": "102", "confirm_write": True})
    assert bs.writes == []
    assert result.extra["write"]["attempted"] is False


def test_write_refused_out_of_manual_range_before_sending():
    """手册 Range 0..2199：越界值在本地拒绝，一条都不发到仪器。"""
    for bad in ("2200", "-1", "abc", "1.5"):
        bs = _ScriptedBs()
        result = _run(bs, {"offset_to_carrier": bad, "confirm_write": True})
        assert bs.writes == [], bad
        assert result.extra["write"]["attempted"] is False, bad
        assert result.extra["verdict"] == "UNDETERMINED", bad


def test_write_confirmed_cell_off_readback_matches_is_success():
    bs = _ScriptedBs()
    result = _run(bs, {"offset_to_carrier": "102", "confirm_write": True})
    assert bs.writes == [f"{OTC_HEADER} 102"]
    assert not any("APPLY" in c for c in _all_commands(bs)), "本序列不发 APPLY"
    assert result.extra["verdict"] == "SUCCESS"
    assert result.success is True
    assert result.extra["write"] == {
        "attempted": True, "value": 102, "readback": "102",
        "readback_matches": True, "error_after_write": '0,"No error"',
        "error_after_readback": '0,"No error"', "reason": None,
    }
    # 写后立即回读：写命令 → ERR → OTCarrier? → ERR，中间不插别的
    w = bs.ops.index(f"{OTC_HEADER} 102")
    assert bs.ops[w:w + 4] == [f"{OTC_HEADER} 102", ERR, OTC_Q, ERR]
    _assert_err_after_every_step(bs)


def test_write_readback_mismatch_is_blocker():
    bs = _ScriptedBs(otc_after_write="0")
    result = _run(bs, {"offset_to_carrier": "102", "confirm_write": True})
    assert result.extra["verdict"] == "BLOCKER"
    assert result.success is False
    assert result.extra["write"]["readback_matches"] is False
    assert "102" in result.summary and "0" in result.summary


def test_write_error_queue_dirty_is_blocker_even_if_readback_matches():
    bs = _ScriptedBs(err_after={f"{OTC_HEADER} 102": '-222,"Data out of range"'})
    result = _run(bs, {"offset_to_carrier": "102", "confirm_write": True})
    assert result.extra["verdict"] == "BLOCKER"
    assert result.extra["write"]["readback_matches"] is True
    assert "-222" in result.summary


def test_accepts_int_param_form():
    """值的形态：int 102 与 str "102" 等价。"""
    bs = _ScriptedBs()
    result = _run(bs, {"offset_to_carrier": 102, "confirm_write": True})
    assert bs.writes == [f"{OTC_HEADER} 102"]
    assert result.extra["verdict"] == "SUCCESS"


# ── 门 5：异常 → ABORTED，且不写 ──────────────────────────────────────

def test_transport_exception_is_aborted_and_no_write():
    bs = _ScriptedBs(raise_on=POINTA_Q)
    result = _run(bs, {"offset_to_carrier": "102", "confirm_write": True})
    assert result.extra["verdict"] == "ABORTED"
    assert result.success is False
    assert bs.writes == []
    assert "TimeoutError" in result.summary
