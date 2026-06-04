"""DUTProfile 声明能力校验 (规划期, attach 前)。

跟 cell_config_consistency 平行, 但时机/数据源不同:
- cell_config_consistency: attach **后** vs UXM 协商能力 (actual/negotiated, query_ue_capability)。
- 本 module: attach **前** vs DUTProfile 声明能力 (spec, operator 填的 DUTProfile)。

价值: 规划期就拿 TestCase 请求跟 DUT 声明比, 请求 > 声明 (e.g. 请求 4 层但 DUT 声明 max 2) →
提前 fail, 不浪费一次真跑 (attach + 跑流量才发现 UE clamp)。调制阶数归一化复用
cell_config_consistency._modulation_order (单一真值, 不重复 QAM 解析)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.services.mimo_ota.cell_config_consistency import _modulation_order


@dataclass
class DUTCapabilityResult:
    consistent: bool
    violations: List[str] = field(default_factory=list)


def check_dut_capability(
    *,
    requested_layers: int,
    requested_modulation: Optional[str],
    declared_max_dl_layers: Optional[int],
    declared_max_modulation_dl: Optional[str],
) -> DUTCapabilityResult:
    """请求 vs DUT 声明。声明项 None = 未声明 (不是所有 DUT 都填全), 跳过该项。

    只校验 DL 方向 (layers + 调制); UL / 频段 / UE category 等后续按需扩展。
    """
    violations: List[str] = []
    if declared_max_dl_layers is not None and requested_layers > declared_max_dl_layers:
        violations.append(
            f"请求 DL {requested_layers} 层 > DUT 声明 max {declared_max_dl_layers} 层"
        )
    if declared_max_modulation_dl is not None and requested_modulation:
        req = _modulation_order(requested_modulation)
        dut = _modulation_order(declared_max_modulation_dl)
        if req is not None and dut is not None and req > dut:
            violations.append(
                f"请求 DL 调制 {requested_modulation} > DUT 声明 max {declared_max_modulation_dl}"
            )
    return DUTCapabilityResult(consistent=not violations, violations=violations)
