"""P2-11 Phase 3: RF 开关拓扑 operating mode TestCase-驱动门 + schema 字段 测试.

钉死:
1. evaluate_switch_mode_gate 4 路决策 (无 topology 放行 / mode 已解析放行 / 有 topology
   但 mode 未解析 strict FAIL / opt-out warn)。
2. MIMOOTAConfiguration 新字段 switch_mode_id / precheck_strict_switch_mode 默认与覆盖。
   switch_mode_id 默认 "mimo_ota" = 历史硬编码值 (backward-compat)。
"""
from __future__ import annotations

from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.mimo_ota.switch_mode_gate import (
    GATE_FAIL,
    GATE_PROCEED,
    GATE_WARN_FALLBACK,
    evaluate_switch_mode_gate,
)


class TestSwitchModeGate:
    def test_no_topology_proceeds(self):
        # 无 active topology row (固定布线手工接线) → 放行 (orchestrator 已 warn),
        # 即使 strict —— 不强迫每个固定布线 lab 都建拓扑行
        d = evaluate_switch_mode_gate(
            topology_present=False,
            mode_resolved=False,
            requested_mode_id="mimo_ota",
            strict=True,
        )
        assert d.action == GATE_PROCEED
        assert not d.should_fail and not d.should_warn

    def test_mode_resolved_proceeds(self):
        # 有 topology + 请求 mode 已解析 (topology+mode 找到 + ≥1 active conn) → 放行
        d = evaluate_switch_mode_gate(
            topology_present=True,
            mode_resolved=True,
            requested_mode_id="mimo_ota",
            strict=True,
        )
        assert d.action == GATE_PROCEED

    def test_topology_present_mode_missing_strict_fails(self):
        # 有 active topology 但请求的 mode 未解析 + strict → FAIL (显式请求 RF 通路
        # 链路不提供 = 真错配)
        d = evaluate_switch_mode_gate(
            topology_present=True,
            mode_resolved=False,
            requested_mode_id="cal_power_sweep",
            strict=True,
        )
        assert d.action == GATE_FAIL
        assert d.should_fail
        assert d.message and "cal_power_sweep" in d.message

    def test_topology_present_mode_missing_optout_warns(self):
        # 同上但 opt-out → 降级 warning, 继续
        d = evaluate_switch_mode_gate(
            topology_present=True,
            mode_resolved=False,
            requested_mode_id="cal_power_sweep",
            strict=False,
        )
        assert d.action == GATE_WARN_FALLBACK
        assert d.should_warn
        assert d.message and "cal_power_sweep" in d.message


class TestSwitchModeSchemaFields:
    def test_defaults(self):
        cfg = MIMOOTAConfiguration()
        # 默认 mode = 历史硬编码 "mimo_ota" (backward-compat) + 严格门开
        assert cfg.switch_mode_id == "mimo_ota"
        assert cfg.precheck_strict_switch_mode is True

    def test_override(self):
        cfg = MIMOOTAConfiguration(
            switch_mode_id="cal_power_sweep",
            precheck_strict_switch_mode=False,
        )
        assert cfg.switch_mode_id == "cal_power_sweep"
        assert cfg.precheck_strict_switch_mode is False
