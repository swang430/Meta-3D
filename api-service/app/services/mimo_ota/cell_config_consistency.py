"""P2-11 Phase 6: UXM 下发后 cell config 一致性校验 (吞吐链版的频率一致性)。

Phase 1 给**频率**做了"下发后回读 (get_frequency_identity) + 跟 TestCase 精确比对"。
Phase 6 把这张一致性网扩到决定吞吐的 cell config —— 当前是 **DL MIMO layers**: UXM 会
在 UE 能力 / 端口路由不支持时把请求的 4 层静默 clamp 到 2 而不报错, 吞吐其实是 2 层却
当 4 层测。measure 在 set_cell_config + RRC reconfig 后回读实际生效值跟 TestCase 比,
不一致 fail-loud (precheck_strict_cell_config), 跟 P1-8/9/12 + Phase 1/2/3 同族的
silent-failure 防护。

回读不到 (mock / 未连接 / 命令不支持) → skipped, 不算不一致 (同 Phase 1 mock-skip)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.hal.uxm_base_station import AppliedCellConfig


@dataclass(frozen=True)
class CellConfigMismatch:
    """一项 cell config 请求值 vs UXM 实际生效值不一致。"""

    field: str
    requested: Any
    applied: Any

    def describe(self) -> str:
        return f"{self.field}: 请求 {self.requested} 但 UXM 实际生效 {self.applied}"


@dataclass
class CellConfigConsistencyResult:
    consistent: bool = True
    skipped: bool = False  # True = 回读不到 (mock/未连接/不支持), 跳过校验
    mismatches: List[CellConfigMismatch] = field(default_factory=list)

    def failure_reason(self) -> Optional[str]:
        if self.consistent:
            return None
        return "; ".join(m.describe() for m in self.mismatches)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "consistent": self.consistent,
            "skipped": self.skipped,
            "mismatches": [
                {"field": m.field, "requested": m.requested, "applied": m.applied}
                for m in self.mismatches
            ],
        }


def check_cell_config_consistency(
    *,
    requested_mimo_layers: int,
    applied: Optional[AppliedCellConfig],
) -> CellConfigConsistencyResult:
    """比对 TestCase 请求的 cell config vs UXM 实际生效 (回读)。

    - applied=None (mock / 未连接 / 不支持回读): skipped=True, consistent=True (跳过)。
    - applied.mimo_layers=None (该项没回读到): 跳过该项, 不算不一致。
    - applied.mimo_layers != requested: 不一致 (UXM clamp/reject)。
    """
    if applied is None:
        return CellConfigConsistencyResult(consistent=True, skipped=True)

    mismatches: List[CellConfigMismatch] = []
    if (
        applied.mimo_layers is not None
        and applied.mimo_layers != requested_mimo_layers
    ):
        mismatches.append(
            CellConfigMismatch(
                field="mimo_layers",
                requested=requested_mimo_layers,
                applied=applied.mimo_layers,
            )
        )

    return CellConfigConsistencyResult(
        consistent=not mismatches,
        skipped=False,
        mismatches=mismatches,
    )
