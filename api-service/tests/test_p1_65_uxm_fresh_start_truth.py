"""P1-65 / P1-17: `uxm_fresh_start_truth` 的行为门。

故障：roadmap「Blocked on hardware」P1-17（UXM fresh-start / 状态导入机制真值）
没有任何 checked-in 载体；驱动 5G profile 的 `STATE_LOAD`（`SYSTem:CONFiguration:LOAD`）/
`STATE_LIST`（`MMEMory:CATalog?`）手册查无（设计稿 §5 Discovered 2）。

本序列的契约（设计稿 §1/§2/§3）：
- 只读：`SYSTem:APPLication:NAME?` / `SYSTem:LICense:AVAilable:ALL?` / `SYSTem:SCPI:FOLDer?`
  （查询形式为推断）/ `SYSTem:SCPI:IMPort:INCLude:PRESet?`（同推断）/
  `SYSTem:SCPI:IMPort:STATus?`（手册 Query only）/ 小区状态；
- 可选动作：`import_file` + `confirm_action=True` → `SYSTem:SCPI:IMPort "<file>"` →
  `IMPort:STATus?` → `SYSTem:ERRor?` → `APPLication:NAME?` 复核；
- **不发** `SYSTem:PRESet:*`、`SYSTem:CONFiguration:LOAD`、`MMEMory:CATalog?`；
- 只在 BSE 方言发；5G_NR_Test → 不发，UNDETERMINED；每步后读错误队列；四态 verdict。
"""
from __future__ import annotations

import asyncio
from typing import Dict, List
from unittest.mock import MagicMock

from app.diagnostics.sequences import uxm_fresh_start_truth as seq
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)

CELL = UxmLteNrIratProfile.PRIMARY_CELL
ERR = UxmLteNrIratProfile.ERR
STATUS_Q = UxmLteNrIratProfile.CELL_STATUS_QUERY.format(cell=CELL)
APP_Q = "SYSTem:APPLication:NAME?"
LIC_Q = "SYSTem:LICense:AVAilable:ALL?"
FOLDER_Q = "SYSTem:SCPI:FOLDer?"
INCL_PRESET_Q = "SYSTem:SCPI:IMPort:INCLude:PRESet?"
IMPORT_STATUS_Q = "SYSTem:SCPI:IMPort:STATus?"
IMPORT_HEADER = "SYSTem:SCPI:IMPort"
INJ = "CELL1?;:SYSTem:PRESet:FULL;:BSE:STATus:NR5G:CELL1"  # 内审 F5 的注入串

_READONLY_SET = {APP_Q, LIC_Q, FOLDER_Q, INCL_PRESET_Q, IMPORT_STATUS_Q, STATUS_Q, ERR}

# 任何路径都**不得**出现：破坏性复位 / 驱动里手册查无的状态命令
_NEVER = ("SYSTem:PRESet", "SYSTem:CONFiguration:LOAD", "MMEMory:CATalog?")


class _ScriptedBs:
    def __init__(self, profile=UxmLteNrIratProfile, *, responses=None,
                 err_after=None, import_status_after_import="1",
                 app_after_import=None, raise_on=None):
        self._cmds = profile
        self.ops: List[str] = []
        self.writes: List[str] = []
        self._responses: Dict[str, str] = {
            APP_Q: '"LTE_NR_IRAT"',
            LIC_Q: '"NR5G_R15,LTE_CA"',
            FOLDER_Q: '"D:\\User Files\\SCPI"',
            INCL_PRESET_Q: "0",
            IMPORT_STATUS_Q: "0",
            STATUS_Q: "OFF",
        }
        self._responses.update(responses or {})
        self._err_after = err_after or {}
        self._import_status_after_import = import_status_after_import
        self._app_after_import = app_after_import
        self._raise_on = raise_on
        self._last = None
        self._imported = False

    def _query(self, cmd):
        self.ops.append(cmd)
        if self._raise_on and cmd == self._raise_on:
            raise TimeoutError(f"timeout on {cmd}")
        if cmd == ERR:
            return self._err_after.get(self._last, '0,"No error"')
        self._last = cmd
        if self._imported and cmd == IMPORT_STATUS_Q:
            return self._import_status_after_import
        if self._imported and cmd == APP_Q and self._app_after_import is not None:
            return self._app_after_import
        return self._responses.get(cmd, "")

    def _write(self, cmd):
        self.ops.append(cmd)
        self.writes.append(cmd)
        self._last = cmd
        if cmd.startswith(IMPORT_HEADER + " "):
            self._imported = True


def _run(bs, params=None):
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}
    return asyncio.run(seq.run(
        MagicMock(), hal, params or {}, log=lambda *_: None,
    ))


def _assert_err_after_every_step(bs):
    ops = bs.ops
    assert ops
    for i, cmd in enumerate(ops):
        if cmd == ERR:
            continue
        assert i + 1 < len(ops) and ops[i + 1] == ERR, (i, cmd, ops[i + 1:i + 2])
    assert ops[-1] == ERR


def _assert_never_sent(bs):
    for tok in _NEVER:
        assert not any(tok in c for c in bs.ops), f"{tok} 不该出现在任何路径: {bs.ops}"


# ── 门 0 / 1 ───────────────────────────────────────────────────────────

def test_metadata():
    assert seq.metadata.required_categories == ["baseStation"]
    assert seq.metadata.safe_during_test is False
    names = {p["name"] for p in seq.metadata.params_schema}
    assert {"import_file", "confirm_action"} <= names


def test_refuses_mock_driver():
    class MockUxm:
        _cmds = UxmLteNrIratProfile

        def _query(self, _):
            raise AssertionError("mock 不该收到命令")

    result = _run(MockUxm())
    assert result.success is False and "mock" in result.summary


def test_refuses_when_driver_not_loaded():
    hal = MagicMock()
    hal.drivers = {}
    result = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
    assert result.success is False and "未加载 baseStation" in result.summary


# ── 门 2：方言门 ────────────────────────────────────────────────────────

def test_5gnr_dialect_sends_nothing_and_is_undetermined():
    bs = _ScriptedBs(Uxm5GNRTestAppProfile)
    result = _run(bs, {"import_file": "x.scpi", "confirm_action": True})
    assert bs.ops == []
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.success is False
    assert "5G_NR_Test" in result.summary and "未查证" in result.summary


# ── 门 3：只读路径 ──────────────────────────────────────────────────────

def test_readonly_collects_mechanism_truth_and_never_writes():
    bs = _ScriptedBs()
    result = _run(bs)
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.success is False
    assert bs.writes == []
    assert set(bs.ops) == _READONLY_SET
    _assert_err_after_every_step(bs)
    _assert_never_sent(bs)
    assert result.extra["readback"] == {
        "application_name": '"LTE_NR_IRAT"',
        "licenses_available_all": '"NR5G_R15,LTE_CA"',
        "scpi_folder": '"D:\\User Files\\SCPI"',
        "import_include_preset": "0",
        "import_status": "0",
        "cell_status": "OFF",
    }
    raws = {s.raw for s in result.steps if s.raw is not None}
    assert {'"LTE_NR_IRAT"', '"NR5G_R15,LTE_CA"', "OFF"} <= raws
    assert "未执行导入" in result.summary
    assert result.extra["import"]["attempted"] is False


def test_readonly_discloses_preset_commands_not_sent_and_driver_discrepancy():
    bs = _ScriptedBs()
    result = _run(bs)
    assert result.extra["preset_commands_available_not_sent"] == [
        "SYSTem:PRESet:API", "SYSTem:PRESet:FACTory", "SYSTem:PRESet:FULL",
    ]
    disc = result.extra["driver_state_load_discrepancy"]
    # 如实记录驱动 5G profile 现用而手册查无的两条（不发）
    assert disc["STATE_LOAD"] == Uxm5GNRTestAppProfile.STATE_LOAD
    assert disc["STATE_LIST"] == Uxm5GNRTestAppProfile.STATE_LIST
    assert disc["manual_hits"] == 0
    assert disc["sent"] is False
    _assert_never_sent(bs)


def test_readonly_query_rejected_is_recorded_not_hidden():
    """FOLDer? 是推断的查询形式：-113 要记录进 readback_errors，措辞不写「不支持」。"""
    bs = _ScriptedBs(err_after={FOLDER_Q: '-113,"Undefined header"'})
    result = _run(bs)
    assert result.extra["readback_errors"] == {FOLDER_Q: '-113,"Undefined header"'}
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "不支持" not in result.summary


# ── 门 4：导入路径 ──────────────────────────────────────────────────────

def test_import_without_confirm_does_not_import():
    bs = _ScriptedBs()
    result = _run(bs, {"import_file": "fresh.scpi"})
    assert bs.writes == []
    assert result.extra["import"]["attempted"] is False
    assert "confirm_action" in result.extra["import"]["reason"]
    assert result.extra["verdict"] == "UNDETERMINED"


def test_import_refused_when_ue_attached():
    for st in ("CONNected", "IDLE", "AGGRegated", "ACTivated"):
        bs = _ScriptedBs(responses={STATUS_Q: st})
        result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": True})
        assert bs.writes == [], st
        assert result.extra["import"]["attempted"] is False, st
        assert st in result.extra["import"]["reason"], st


def test_import_refuses_unsafe_filename_locally():
    for bad in ('a"b.scpi', "a\nb.scpi", "   "):
        bs = _ScriptedBs()
        result = _run(bs, {"import_file": bad, "confirm_action": True})
        assert bs.writes == [], repr(bad)
        assert result.extra["import"]["attempted"] is False, repr(bad)


def test_import_confirmed_status_ok_queue_clean_is_success():
    bs = _ScriptedBs()
    result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": True})
    assert bs.writes == ['SYSTem:SCPI:IMPort "fresh.scpi"']
    w = bs.ops.index('SYSTem:SCPI:IMPort "fresh.scpi"')
    # 导入 → ERR → STATus? → ERR → APPLication:NAME? → ERR
    assert bs.ops[w:w + 6] == [
        'SYSTem:SCPI:IMPort "fresh.scpi"', ERR, IMPORT_STATUS_Q, ERR, APP_Q, ERR,
    ]
    _assert_err_after_every_step(bs)
    _assert_never_sent(bs)
    assert result.extra["verdict"] == "SUCCESS"
    assert result.success is True
    imp = result.extra["import"]
    assert imp["attempted"] is True
    assert imp["file"] == "fresh.scpi"
    assert imp["status_after"] == "1"
    assert imp["application_after"] == '"LTE_NR_IRAT"'
    assert imp["error_after_import"] == '0,"No error"'


def test_import_status_failure_is_blocker():
    bs = _ScriptedBs(import_status_after_import="0")
    result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": True})
    assert result.extra["verdict"] == "BLOCKER"
    assert result.success is False
    assert "IMPort:STATus" in result.summary


def test_import_error_queue_dirty_is_blocker_even_if_status_ok():
    bs = _ScriptedBs(err_after={'SYSTem:SCPI:IMPort "fresh.scpi"': '-256,"File name not found"'})
    result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": True})
    assert result.extra["verdict"] == "BLOCKER"
    assert "-256" in result.summary


def test_import_include_preset_on_is_surfaced_in_summary():
    """INCLude:PRESet=1 意味着导入会先复位 —— 必须在结论里点名，不能静默。"""
    bs = _ScriptedBs(responses={INCL_PRESET_Q: "1"})
    result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": True})
    assert result.extra["readback"]["import_include_preset"] == "1"
    assert "PRESet" in result.summary


# ── 门 4b：同意门 fail-closed（内审 F2）────────────────────────────────

def test_confirm_action_string_false_forms_never_import():
    """`bool("false") == True` 会放行导入 —— 在 INCLude:PRESet 默认为 1 的机器上
    = 先复位再导入。变异：`_as_bool(...) is True` 换回 `bool(...)` → 红。"""
    for form in ("false", "0", "no", "False", None, "", "maybe", 0):
        bs = _ScriptedBs()
        result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": form})
        assert bs.writes == [], repr(form)
        assert result.extra["import"]["attempted"] is False, repr(form)
        assert result.extra["verdict"] == "UNDETERMINED", repr(form)


def test_confirm_action_string_true_forms_import():
    for form in ("true", "1", "yes", "True", True):
        bs = _ScriptedBs()
        result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": form})
        assert bs.writes == ['SYSTem:SCPI:IMPort "fresh.scpi"'], repr(form)
        assert result.extra["verdict"] == "SUCCESS", repr(form)


# ── 门 4c：cell 白名单（内审 F5）────────────────────────────────────────

def test_cell_injection_sends_nothing():
    """变异：去掉 `_validate_cell` 校验 → 红（注入串会拼进 BSE:STATus 查询）。"""
    for bad in (INJ, "CELL0", "CELL15", "CELL1;*RST", "SELected?"):
        bs = _ScriptedBs()
        result = _run(bs, {"cell": bad, "import_file": "fresh.scpi", "confirm_action": True})
        assert bs.ops == [], repr(bad)
        assert result.extra["verdict"] != "SUCCESS", repr(bad)
        assert "白名单" in result.summary, repr(bad)


# ── 门 5：异常 → ABORTED ────────────────────────────────────────────────

def test_transport_exception_is_aborted_and_no_import():
    bs = _ScriptedBs(raise_on=LIC_Q)
    result = _run(bs, {"import_file": "fresh.scpi", "confirm_action": True})
    assert result.extra["verdict"] == "ABORTED"
    assert bs.writes == []
    assert "TimeoutError" in result.summary
