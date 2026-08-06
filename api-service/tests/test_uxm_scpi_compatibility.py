"""P1-46: UXM SCPI 普查的判定集必须跟生产 MAC 配置同源。"""
import asyncio
from unittest.mock import MagicMock

from app.diagnostics.sequences import uxm_scpi_compatibility as seq
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import UxmLteNrIratProfile


def test_mac_critical_names_are_derived_from_driver_mandatory_contract():
    """变异：在诊断侧静态复制/漏掉任一 mandatory 名称会红。"""
    assert seq._MAC_CRITICAL_NAMES == frozenset(RealUxmDriver.MAC_CFG_MANDATORY)
    assert seq._MAC_CRITICAL_NAMES <= seq._CRITICAL_NAMES
    assert "CELL_BAND" in seq._CRITICAL_NAMES
    assert "MEAS_TPUT_DL_OTA" in seq._CRITICAL_NAMES


def test_no_equivalent_commands_are_explicitly_excluded_from_decision_set():
    """手册确认没有对应命令的项不能被伪装成“待兼容性探测”。"""
    no_equivalent = frozenset(RealUxmDriver.MAC_CFG_NO_EQUIVALENT)
    assert no_equivalent
    assert seq._MAC_CRITICAL_NAMES.isdisjoint(no_equivalent)
    assert seq._CRITICAL_NAMES.isdisjoint(no_equivalent)


def test_legacy_tdd_pattern_none_does_not_make_irat_profile_always_fail():
    """IRAT 用六个数描述 TDD；不存在的旧字符串 TDD_PATTERN 不能进 critical。"""
    assert "TDD_PATTERN" not in seq._CRITICAL_NAMES
    assert "TDD_PATTERN_STATE" in seq._CRITICAL_NAMES
    assert "TDD_PERIOD" in seq._CRITICAL_NAMES


def test_immediate_apply_actions_are_inferred_and_never_queried():
    """Imm Action / No query 不能被 `_to_probe_command` 伪造成 APPLY?。"""
    assert seq._ACTION_NEIGHBOR_QUERY["QCONFIG_APPLY_ALL"] == "PDSCH_SCHED_ALGO"
    assert seq._ACTION_NEIGHBOR_QUERY["CONFIG_APPLY"] == "CELL_STATUS_QUERY"

    class _RecordingBs:
        _cmds = UxmLteNrIratProfile

        def __init__(self):
            self.queries = []

        def _query(self, cmd):
            self.queries.append(cmd)
            return '0,"No error"' if cmd == self._cmds.ERR else ""

        def _write(self, _cmd):
            return None

    bs = _RecordingBs()
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}
    result = asyncio.run(seq.run(
        MagicMock(), hal, {"include_supported": True}, log=lambda *_: None,
    ))

    for name in ("QCONFIG_APPLY_ALL", "CONFIG_APPLY"):
        action = getattr(UxmLteNrIratProfile, name)
        assert action + "?" not in bs.queries
        action_steps = [
            step for step in result.steps
            if step.label.startswith(name + " (ACTION)")
        ]
        assert len(action_steps) == 1
        assert action_steps[0].success is False
        assert action_steps[0].detail.startswith("INFERRED_ONLY")

    assert result.success is False
    assert result.extra["critical_unverified_actions"] == [
        "CONFIG_APPLY", "QCONFIG_APPLY_ALL",
    ]
    assert not ({"CONFIG_APPLY", "QCONFIG_APPLY_ALL"}
                & set(result.extra["critical_unsupported"]))
    assert "未直接验证" in result.summary
