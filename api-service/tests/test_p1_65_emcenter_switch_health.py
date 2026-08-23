"""P1-65 A 组：`emcenter_switch_health` —— P2-9 EMCenter 开关的首个只读载体。

故障（roadmap「Blocked on hardware」2026-08-23 矩阵）：P2-9 现场半（端口 / 卡型号 /
继电器位 / 互锁）没有任何 checked-in 载体，到了现场只能临时敲命令 —— 正是
P1-45 立的规矩禁止的形态。

本文件守的门（全部打在序列的**可观察后果**上，不看实现细节）：
- mock 驱动拒绝 / 驱动未加载拒绝 / 驱动无 `_send_command` 原语拒绝；
- **只读不变量**：假驱动收到的命令集合里没有任何写命令，且序列源码里不出现
  写命令 token（复位 / 清错 / 重启 / 置位）；
- 四态判定各一条行为门：全部正常 → SUCCESS；互锁=1 / 超时无响应 / 回读值不在
  合法值域 → BLOCKER；无槽位配置 / relay_type 未配置 → UNDETERMINED；
- `raw` 原样进步骤；`extra` 结构化携带 chassis_idn / version / slots / interlock / verdict。

手册出处（`Instrument_API_Doc/ETS-L EMCenter/EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf`，
pdftotext 行号）：`*IDN?` :136-185、`VERSION_SW?` :287-298、SPDT `INT_RELAY_<R>?` → NO|NC :305-330、
SP6T `INT_RELAY_<R>?` → 0-6 :508-532、`INTLK? SAFETYRELAY` → 0/1 :492-500。
"""
from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import MagicMock

import pytest

from app.diagnostics.protocol import driver_not_loaded_summary
from app.diagnostics.sequences import emcenter_switch_health as seq
from app.hal.rf_switch import MockRfSwitch


# ── 回放式假驱动（照 test_p1_58 的 _ScriptedBs 形态，记录收到的每条命令）──

class _ScriptedEmcenter:
    """只实现序列会碰的 `_send_command(cmd)`；未脚本化的命令返回 None
    （= 驱动在超时 / 异常时的真实返回值，见 rf_switch.py `_send_command`）。"""

    def __init__(self, responses: Dict[str, Optional[str]], mappings=None):
        self.received = []
        self._responses = dict(responses)
        self._mappings = dict(mappings or {})

    async def _send_command(self, cmd: str) -> Optional[str]:
        self.received.append(cmd)
        return self._responses.get(cmd)


_MAPPINGS_TWO_CARDS = {
    # Slot4 = SPDT 卡（A/B 两个继电器），Slot5 = SP6T 卡（A 一个继电器）。
    # 同一继电器被两条路径引用（rf1 / rf3 都走 4:INT_RELAY_A），序列必须去重。
    "rf1": {"switch_id": "4:INT_RELAY_A", "output_port": "NO", "relay_type": "spdt"},
    "rf3": {"switch_id": "4:INT_RELAY_A", "output_port": "NC", "relay_type": "spdt"},
    "nr_tis": {"relay": "4:INT_RELAY_B", "position": "NC", "relay_type": "SPDT"},
    "theta": {"switch_id": "5:INT_RELAY_A", "output_port": 3, "relay_type": "sp6t"},
}

_HEALTHY_RESPONSES = {
    "*IDN?": "ETS-Lindgren EMCenter version 4.3.4",
    "VERSION_SW?": "4.3.4",
    "4:*IDN?": "ETS-Lindgren, EMSwitch 7001-002, 4.3.3",
    "5:*IDN?": "ETS-Lindgren, EMSwitch 7001-003, 4.3.3",
    "4:INT_RELAY_A?": "NC",
    "4:INT_RELAY_B?": "NO",
    "5:INT_RELAY_A?": "0",
    "INTLK? SAFETYRELAY": "0",
}

_WRITE_FORM = re.compile(
    r"INT_RELAY_[A-D]_|EXT_RELAY_[A-B]_|RESET|CLEAR|REBOOT|LOCAL|EXT_VOLTAGE_"
)


def _run(drv, params=None):
    hal = MagicMock()
    hal.drivers = {"rfSwitch": drv} if drv is not None else {}
    return asyncio.run(seq.run(
        MagicMock(), hal, params or {}, log=lambda *_: None,
    ))


# ── 元数据 ──────────────────────────────────────────────────────────

def test_metadata_declares_rf_switch_only_and_not_safe_during_test():
    assert seq.metadata.required_categories == ["rfSwitch"]
    assert seq.metadata.safe_during_test is False
    assert inspect.iscoroutinefunction(seq.run)


# ── 拒绝门 ──────────────────────────────────────────────────────────

def test_refuses_mock_driver():
    result = _run(MockRfSwitch("sw", {}))
    assert result.success is False
    assert "mock" in result.summary.lower()
    assert "MockRfSwitch" in result.summary


def test_refuses_when_driver_not_loaded():
    result = _run(None)
    assert result.success is False
    assert result.summary == driver_not_loaded_summary("rfSwitch")


def test_refuses_driver_without_send_command_primitive():
    class _NoPrimitive:
        _mappings = {}

    result = _run(_NoPrimitive())
    assert result.success is False
    assert "_send_command" in result.summary


# ── 只读不变量 ──────────────────────────────────────────────────────

def test_read_only_invariant_no_write_command_reaches_driver():
    """假驱动收到的每条命令都必须是查询（含 `?`），且不匹配任何写命令形态。"""
    drv = _ScriptedEmcenter(_HEALTHY_RESPONSES, _MAPPINGS_TWO_CARDS)
    _run(drv)
    assert drv.received, "序列一条命令都没发"
    for cmd in drv.received:
        assert "?" in cmd, f"发出了非查询命令: {cmd!r}"
        assert not _WRITE_FORM.search(cmd), f"发出了写命令形态: {cmd!r}"


def test_read_only_invariant_source_has_no_write_tokens():
    """源码级存在性粗筛（旁边配上面的行为门）：写命令 token 一律不出现在序列源码里。"""
    src = Path(seq.__file__).read_text(encoding="utf-8")
    for token in ("RESET", "CLEAR", "REBOOT"):
        assert token not in src, f"序列源码里出现了写命令 token {token!r}"
    assert not re.search(r"INT_RELAY_<?[A-DR]>?_", src), "序列源码里出现了继电器置位形态"


# ── SUCCESS ─────────────────────────────────────────────────────────

def test_healthy_two_card_chassis_is_success_with_exact_command_walk():
    drv = _ScriptedEmcenter(_HEALTHY_RESPONSES, _MAPPINGS_TWO_CARDS)
    result = _run(drv)

    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"
    # 命令序列是从配置派生的恒等关系：机箱 → 版本 → 每槽 IDN → 每槽每继电器 → 互锁
    assert drv.received == [
        "*IDN?", "VERSION_SW?",
        "4:*IDN?", "4:INT_RELAY_A?", "4:INT_RELAY_B?",
        "5:*IDN?", "5:INT_RELAY_A?",
        "INTLK? SAFETYRELAY",
    ]
    assert result.extra["chassis_idn"] == "ETS-Lindgren EMCenter version 4.3.4"
    assert result.extra["version"] == "4.3.4"
    assert result.extra["interlock"] == "0"
    assert result.extra["slots"] == [
        {"slot": "4", "idn": "ETS-Lindgren, EMSwitch 7001-002, 4.3.3",
         "relays": {"A": "NC", "B": "NO"}},
        {"slot": "5", "idn": "ETS-Lindgren, EMSwitch 7001-003, 4.3.3",
         "relays": {"A": "0"}},
    ]
    # raw 原样进步骤：每个有回复的步骤 raw == 仪器回复
    raw_by_label = {s.label: s.raw for s in result.steps}
    assert raw_by_label["4:INT_RELAY_A?"] == "NC"
    assert raw_by_label["5:INT_RELAY_A?"] == "0"
    assert raw_by_label["INTLK? SAFETYRELAY"] == "0"
    assert all(s.success for s in result.steps)


def test_sp6t_position_six_and_spdt_no_are_in_domain():
    responses = dict(_HEALTHY_RESPONSES, **{"5:INT_RELAY_A?": "6", "4:INT_RELAY_A?": "NO"})
    result = _run(_ScriptedEmcenter(responses, _MAPPINGS_TWO_CARDS))
    assert result.extra["verdict"] == "SUCCESS"


# ── BLOCKER ─────────────────────────────────────────────────────────

def test_interlock_active_is_blocker_naming_relay_a_hardware_lock():
    responses = dict(_HEALTHY_RESPONSES, **{"INTLK? SAFETYRELAY": "1"})
    result = _run(_ScriptedEmcenter(responses, _MAPPINGS_TWO_CARDS))
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    assert result.extra["interlock"] == "1"
    assert "Relay A 被硬件锁" in result.summary
    intlk_step = next(s for s in result.steps if s.label == "INTLK? SAFETYRELAY")
    assert intlk_step.success is False
    assert intlk_step.raw == "1"


def test_relay_readback_timeout_is_blocker_and_walk_continues():
    responses = dict(_HEALTHY_RESPONSES)
    del responses["4:INT_RELAY_B?"]  # 驱动超时 → None
    drv = _ScriptedEmcenter(responses, _MAPPINGS_TWO_CARDS)
    result = _run(drv)
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    step = next(s for s in result.steps if s.label == "4:INT_RELAY_B?")
    assert step.success is False
    assert step.raw is None  # None = 没有仪器回复，不填 ""
    assert "无响应" in step.detail or "超时" in step.detail
    # 单点超时不中断余下只读步骤（slot5 与互锁仍要读）
    assert "5:INT_RELAY_A?" in drv.received
    assert "INTLK? SAFETYRELAY" in drv.received


def test_three_consecutive_timeouts_stop_the_walk():
    """行为门（内审 F7-M7）：半死会话上每条超时 5 s，连续 3 次无响应后序列必须停，
    steps 不再增长、互锁也不再问。变异：上限放到 10**6 → 红。"""
    mappings = {
        f"p{slot}": {"switch_id": f"{slot}:INT_RELAY_A", "relay_type": "spdt"}
        for slot in (4, 5, 6, 7)
    }
    responses = {"*IDN?": "ETS-Lindgren EMCenter version 4.3.4", "VERSION_SW?": "4.3.4"}
    drv = _ScriptedEmcenter(responses, mappings)  # 槽位级全部无响应
    result = _run(drv)

    assert drv.received == [
        "*IDN?", "VERSION_SW?",
        "4:*IDN?", "4:INT_RELAY_A?", "5:*IDN?",  # 第 3 次连续无响应 → 停
    ]
    assert "INTLK? SAFETYRELAY" not in drv.received
    assert len(result.steps) == 5
    assert result.extra["walk_aborted"] is True
    assert result.extra["verdict"] == "BLOCKER"
    assert "连续无响应" in result.summary


def test_chassis_idn_timeout_aborts_walk_as_blocker():
    responses = dict(_HEALTHY_RESPONSES)
    del responses["*IDN?"]
    drv = _ScriptedEmcenter(responses, _MAPPINGS_TWO_CARDS)
    result = _run(drv)
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    assert drv.received == ["*IDN?"], "机箱都不应答就不该继续往下敲"
    assert result.extra["chassis_idn"] is None


@pytest.mark.parametrize(
    "cmd,bad",
    [
        ("4:INT_RELAY_A?", "3"),     # SPDT 只能 NC|NO
        ("4:INT_RELAY_A?", ""),      # 空串不在值域
        ("5:INT_RELAY_A?", "NC"),    # SP6T 只能 0-6
        ("5:INT_RELAY_A?", "7"),
        ("INTLK? SAFETYRELAY", "2"), # 互锁只能 0/1
    ],
)
def test_readback_outside_legal_domain_is_blocker(cmd, bad):
    responses = dict(_HEALTHY_RESPONSES, **{cmd: bad})
    result = _run(_ScriptedEmcenter(responses, _MAPPINGS_TWO_CARDS))
    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    step = next(s for s in result.steps if s.label == cmd)
    assert step.success is False
    assert step.raw == bad, "值域外的回读也必须原样留档"


# ── UNDETERMINED ────────────────────────────────────────────────────

def test_no_port_maps_only_chassis_level_and_undetermined():
    drv = _ScriptedEmcenter(_HEALTHY_RESPONSES, mappings={})
    result = _run(drv)
    assert drv.received == ["*IDN?", "VERSION_SW?", "INTLK? SAFETYRELAY"]
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["slots"] == []
    assert "未配置槽位" in result.summary


def test_missing_relay_type_records_value_but_cannot_judge_domain():
    mappings = {"p": {"switch_id": "4:INT_RELAY_A"}}  # 没标 relay_type
    responses = dict(_HEALTHY_RESPONSES, **{"4:INT_RELAY_A?": "NC"})
    result = _run(_ScriptedEmcenter(responses, mappings))
    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["slots"][0]["relays"] == {"A": "NC"}
    assert "relay_type" in result.summary


def test_ext_relay_mapping_is_skipped_not_probed():
    """设计稿 §2 没列 EXT_RELAY 的只读形式 —— 不盲试，如实登记为未探测。"""
    mappings = dict(_MAPPINGS_TWO_CARDS, ext={"switch_id": "EXT_RELAY_A", "output_port": 0})
    drv = _ScriptedEmcenter(_HEALTHY_RESPONSES, mappings)
    result = _run(drv)
    assert not any("EXT_RELAY" in c for c in drv.received)
    assert "EXT_RELAY_A" in result.extra["skipped_mappings"]
    assert result.extra["verdict"] == "SUCCESS"
