"""P2-11 Phase 3: RF 开关拓扑 operating mode TestCase-驱动门 (fail-loud)。

正式测试 (路径 B) 由 TestCase 的 `switch_mode_id` 选 chamber active SwitchTopology
的 operating mode。本门处理"chamber 有 active topology 但其中没有请求的 mode (或该
mode 无 active_connections)"—— TestCase 显式请求的 RF 通路链路声明不提供 = 真错配,
strict FAIL; opt-out 降级 warning。

关键边界 (CAICT 固定布线既有语义): chamber **没有** active topology row 时, 假设
RF 通路是手工接线, orchestrator 自身已出 warning, 本门**放行** (不受 strict 影响) ——
所以门只对"声明了拓扑却不含请求 mode"开火, 不强迫每个固定布线 lab 都建拓扑行。

跟 P1-8/9 (cal/dut) + Phase 1 (频率) + Phase 2 (.smu) 同族的 silent-failure 防护。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# action 取值 (measure 据此决定放行 / FAIL / 降级 warning)
GATE_PROCEED = "proceed"               # 放行: 无 active topology (固定布线), 或 mode 已解析
GATE_FAIL = "fail"                     # strict FAIL: 有 topology 但请求 mode 未解析
GATE_WARN_FALLBACK = "warn_fallback"   # opt-out: 同上但降级 warning, 继续


@dataclass(frozen=True)
class SwitchModeGateDecision:
    """switch mode 门决策。action ∈ {proceed, fail, warn_fallback}; message 供 FAIL/warn。"""

    action: str
    message: Optional[str] = None

    @property
    def should_fail(self) -> bool:
        return self.action == GATE_FAIL

    @property
    def should_warn(self) -> bool:
        return self.action == GATE_WARN_FALLBACK


def evaluate_switch_mode_gate(
    *,
    topology_present: bool,
    mode_resolved: bool,
    requested_mode_id: str,
    strict: bool,
) -> SwitchModeGateDecision:
    """决定 measure 是否因 switch mode 未解析而 fail-loud。

    决策表 (按优先级):
    1. 无 active topology row (topology_present=False) → PROCEED (固定布线, orchestrator
       已 warn; 不强迫建拓扑行)。
    2. 请求的 mode 已解析 (mode_resolved=True, 即 topology+mode 找到且 ≥1 active conn)
       → PROCEED。
    3. 有 topology 但 mode 未解析 + strict → FAIL (显式请求的 RF 通路链路不提供)。
    4. 有 topology 但 mode 未解析 + opt-out → WARN_FALLBACK (继续, 下游退 chamber 几何)。
    """
    if not topology_present:
        return SwitchModeGateDecision(GATE_PROCEED)
    if mode_resolved:
        return SwitchModeGateDecision(GATE_PROCEED)
    if strict:
        return SwitchModeGateDecision(
            GATE_FAIL,
            message=(
                f"P2-11 Phase 3: chamber 的 active SwitchTopology 不提供 TestCase 请求的 "
                f"switch_mode_id='{requested_mode_id}' (mode 缺失或无 active_connections) "
                f"→ RF 通路链路声明跟 TestCase 错配。请在拓扑里补该 operating mode, 或设 "
                f"precheck_strict_switch_mode=False 降级继续 (probe 绑定可能空)。"
            ),
        )
    return SwitchModeGateDecision(
        GATE_WARN_FALLBACK,
        message=(
            f"P2-11: switch_mode_id='{requested_mode_id}' 在 active 拓扑里未解析 "
            f"(precheck_strict_switch_mode=False, 继续; probe 绑定可能空, 下游退 chamber 几何)"
        ),
    )
