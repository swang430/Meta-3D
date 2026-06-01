"""P2-11 Phase 6: UXM 下发后 cell config 一致性校验 (吞吐链版的频率一致性)。

Phase 1 给**频率**做了"下发后回读 (get_frequency_identity) + 跟 TestCase 精确比对"。
Phase 6 把这张一致性网扩到决定吞吐的 cell config —— 当前是 **DL MIMO layers**: UE 能力
撑不住请求层数时 UXM 会把请求的 4 层静默 clamp 到 2 而不报错, 吞吐其实是 2 层却当 4 层
测。measure 在 set_cell_config + RRC reconfig 后, 拿 **UE 协商能力** (max_dl_layers) 跟
TestCase 请求比 —— 请求 > UE 上限 → fail-loud (precheck_strict_cell_config), 跟
P1-8/9/12 + Phase 1/2/3 同族的 silent-failure 防护。

⚠️ Codex on PR #114: 校验源是 **UE 协商能力**, 不是 `CONF:...:LAY?` 配置旋钮 —— 后者是
set_cell_config 写入的同一个值, 回读只会原样返回配置的 4, 抓不到 UE 侧的 clamp。

不可核对 (mock / UE 未 attach / firmware 不支持 UEINFO) → skipped, 不算不一致 (同
Phase 1 mock-skip)。
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
        return (
            f"{self.field}: TestCase 请求 {self.requested} 但 UXM/UE 实际上限 "
            f"{self.applied} (超出 → 会被静默 clamp)"
        )


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

    - applied=None (mock / UE 未 attach / firmware 不支持): skipped=True, consistent=True。
    - applied.ue_max_dl_layers=None (该项不可核对): 跳过该项, 不算不一致。
    - requested_mimo_layers > applied.ue_max_dl_layers: 不一致 (UE 能力撑不住请求层数 →
      UXM 会静默 clamp, 吞吐其实更少却当请求层数测)。Codex on PR #114: 读 UE 协商能力,
      不读 set_cell_config 写入的配置旋钮 (那个回读只会原样返回配置值)。
    """
    if applied is None:
        return CellConfigConsistencyResult(consistent=True, skipped=True)

    mismatches: List[CellConfigMismatch] = []
    if (
        applied.ue_max_dl_layers is not None
        and requested_mimo_layers > applied.ue_max_dl_layers
    ):
        mismatches.append(
            CellConfigMismatch(
                field="mimo_layers",
                requested=requested_mimo_layers,
                applied=applied.ue_max_dl_layers,
            )
        )

    return CellConfigConsistencyResult(
        consistent=not mismatches,
        skipped=False,
        mismatches=mismatches,
    )
