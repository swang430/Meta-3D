"""DUTProfile 声明 vs UXM 实测协商能力交叉核对 (阶段 4, attach 后)。

三层能力的最后一道关系网:
- 声明 (DUTProfile, 规划期, operator 填) —— `dut_capability_check` 拿 TestCase 请求跟它比。
- 协商 (query_ue_capability, attach 后, UXM 上报) —— 本 module 拿声明跟它**交叉核对**。
- 运行时 (CSI RI, 测量中)。

跟 `dut_capability_check` (请求 vs 声明, 单向 fail-loud) 不同, 这里是**声明 vs 实测协商**的
**双向**比对: 声明 ≠ 实测 (任一方向) = 有用发现 —— DUT 实际行为跟它的 spec 声明不符
(固件升级 / 换 SIM / 声明过时 / 声明笔误)。

⚠️ 设计原则 (用户 2026-06-04 明确): 不一致是**发现不是错误** —— audit-only surface,
**不 fail** (已 attach 投入), **不自动覆盖声明** (声明是规划期真值源, 自动覆盖会丢失
"spec vs actual 偏差"这个发现)。observed 单独记 measurements; operator 在 DUT 声明页**显式**
决定是否采纳实测值反写。

仅真实 UE (source==real_ue) 核对; mock / 未 attach (unavailable) → skipped, 不算不一致
(同 cell_config_consistency mock-skip, 避免拿假数据产生假阳)。调制阶数归一化复用
cell_config_consistency._modulation_order (单一真值)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.mimo_ota.cell_config_consistency import _modulation_order


@dataclass(frozen=True)
class DUTCapabilityMismatch:
    """一项 DUT 声明值 vs 实测协商值不一致。"""

    field: str
    declared: Any
    observed: Any

    def describe(self) -> str:
        return (
            f"{self.field}: DUT 声明 {self.declared} 但实测协商 {self.observed} "
            f"(spec 跟 actual 不符)"
        )


@dataclass
class DUTCapabilityMismatchResult:
    consistent: bool = True
    skipped: bool = False  # True = 无可比实测 (mock / 未 attach / 不支持), 跳过核对
    mismatches: List[DUTCapabilityMismatch] = field(default_factory=list)

    def failure_reason(self) -> Optional[str]:
        if self.consistent:
            return None
        return "; ".join(m.describe() for m in self.mismatches)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "consistent": self.consistent,
            "skipped": self.skipped,
            "mismatches": [
                {"field": m.field, "declared": m.declared, "observed": m.observed}
                for m in self.mismatches
            ],
        }


def _layers_mismatch(declared: Optional[int], observed: Optional[int]) -> bool:
    """层数: 两边都声明且不等 → 不一致。任一 None (未声明 / 未上报) → 跳过该项。"""
    return declared is not None and observed is not None and declared != observed


def _modulation_mismatch(declared: Optional[str], observed: Optional[str]) -> bool:
    """调制: 优先按阶数比 (容忍 256QAM/QAM256 格式差异); 阶数都识别不出时退化到
    归一化字符串相等比。任一 None → 跳过。"""
    if not declared or not observed:
        return False
    do = _modulation_order(declared)
    oo = _modulation_order(observed)
    if do is not None and oo is not None:
        return do != oo
    # 阶数识别不出 (非常规调制名) → 归一化大小写/空白后字符串比, 不轻易判等
    # (feedback_normalize_identifier_compare)。
    return str(declared).strip().upper() != str(observed).strip().upper()


def check_dut_capability_mismatch(
    *,
    declared_max_dl_layers: Optional[int],
    declared_max_ul_layers: Optional[int],
    declared_max_modulation_dl: Optional[str],
    declared_max_modulation_ul: Optional[str],
    observed_max_dl_layers: Optional[int],
    observed_max_ul_layers: Optional[int],
    observed_max_modulation_dl: Optional[str],
    observed_max_modulation_ul: Optional[str],
    observed_available: bool,
) -> DUTCapabilityMismatchResult:
    """声明 vs 实测协商, 逐字段双向比。

    `observed_available=False` (mock / 未 attach / source 非 real_ue) → skipped, 不核对。
    每个字段: 声明跟实测都有 + 不等 → mismatch; 任一缺失 → 跳过该字段 (不是所有 DUT
    都声明全, 也不是所有字段 UXM 都上报)。
    """
    if not observed_available:
        return DUTCapabilityMismatchResult(consistent=True, skipped=True)

    mismatches: List[DUTCapabilityMismatch] = []
    if _layers_mismatch(declared_max_dl_layers, observed_max_dl_layers):
        mismatches.append(
            DUTCapabilityMismatch("max_dl_layers", declared_max_dl_layers, observed_max_dl_layers)
        )
    if _layers_mismatch(declared_max_ul_layers, observed_max_ul_layers):
        mismatches.append(
            DUTCapabilityMismatch("max_ul_layers", declared_max_ul_layers, observed_max_ul_layers)
        )
    if _modulation_mismatch(declared_max_modulation_dl, observed_max_modulation_dl):
        mismatches.append(
            DUTCapabilityMismatch(
                "max_modulation_dl", declared_max_modulation_dl, observed_max_modulation_dl
            )
        )
    if _modulation_mismatch(declared_max_modulation_ul, observed_max_modulation_ul):
        mismatches.append(
            DUTCapabilityMismatch(
                "max_modulation_ul", declared_max_modulation_ul, observed_max_modulation_ul
            )
        )
    return DUTCapabilityMismatchResult(consistent=not mismatches, mismatches=mismatches)
