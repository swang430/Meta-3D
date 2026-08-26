"""P2-11 Phase 6: UXM 下发后 cell config 一致性校验 (吞吐链版的频率一致性)。

Phase 1 给**频率**做了"下发后回读 (get_frequency_identity) + 跟 TestCase 精确比对"。
Phase 6 把这张一致性网扩到决定吞吐的 cell config —— **DL MIMO layers** (首条线 #114) +
**DL 调制阶数** (本次延伸): UE 能力撑不住请求时 UXM 会静默 clamp (4 层 clamp 到 2 /
256QAM clamp 到 64QAM) 而不报错, 吞吐其实更低却当请求值测。measure 在 set_cell_config +
RRC reconfig 后, 拿 **UE 协商能力** (max_dl_layers / max_modulation_dl) 跟 TestCase 请求
比 —— 请求 > UE 上限 → fail-loud (precheck_strict_cell_config), 跟 P1-8/9/12 + Phase
1/2/3 同族的 silent-failure 防护。

⚠️ Codex on PR #114: 校验源是 **UE 协商能力**, 不是 `CONF:...:LAY?` 配置旋钮 —— 后者是
set_cell_config 写入的同一个值, 回读只会原样返回配置的 4, 抓不到 UE 侧的 clamp。

不可核对 (mock / UE 未 attach / firmware 不支持 UEINFO) → skipped, 不算不一致 (同
Phase 1 mock-skip)。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.hal.base_station import AppliedCellConfig


# 调制方式 → 阶数 (bits/symbol)。比较"请求调制阶数 vs UE 能力上限"用 —— 阶数越高 =
# 每符号 bit 越多 = 吞吐越高, UE 撑不住会 clamp 到它支持的最高阶。
_MODULATION_BITS = {4: 2, 16: 4, 64: 6, 256: 8, 1024: 10}


def _modulation_order(modulation: Optional[str]) -> Optional[int]:
    """归一化调制方式到阶数 (bits/symbol)。无法识别 → None (该项跳过校验)。

    容忍多种格式: '256QAM' / 'QAM256' / '256-QAM' / 'qam256' / 'QPSK'。TestCase 用
    '256QAM', 但真 UXM SCPI (UEINFO:CAPability:MODulation:DL?) 返回格式不保证 —— 按数字
    (QAM 点数) 或 QPSK 特例提取阶数, 避免纯字符串相等比较因格式差异误判
    (feedback_normalize_identifier_compare)。
    """
    if not modulation:
        return None
    s = re.sub(r"[\s_\-]", "", str(modulation).upper())
    if "QPSK" in s:
        return 2
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    return _MODULATION_BITS.get(int(m.group(1)))


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
    requested_modulation: Optional[str] = None,
) -> CellConfigConsistencyResult:
    """比对 TestCase 请求的 cell config vs UXM/UE 实际能力 (读 UE 协商能力)。

    - applied=None (mock / UE 未 attach / firmware 不支持): skipped=True, consistent=True。
    - 各字段 None (该项不可核对): 跳过该项, 不算不一致。
    - requested_mimo_layers > applied.ue_max_dl_layers: 不一致 (UE 撑不住请求层数 → UXM
      静默 clamp, 吞吐其实更少却当请求层数测)。
    - requested_modulation 阶数 > applied.ue_max_modulation_dl 阶数: 不一致 (UE 调制能力
      撑不住 → clamp 到更低调制, 同等危害)。阶数归一化容忍格式差异; 任一侧无法识别 → 跳过。

    Codex on PR #114: 全部读 UE **协商能力**, 不读 set_cell_config 写入的配置旋钮 (那个
    回读只会原样返回配置值, 抓不到 UE 侧 clamp)。
    """
    if applied is None:
        return CellConfigConsistencyResult(consistent=True, skipped=True)

    mismatches: List[CellConfigMismatch] = []

    # --- 第一条线 (#114): DL MIMO layers ---
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

    # --- 第二条线 (Phase 6 延伸): DL 调制阶数 ---
    req_mod_ord = _modulation_order(requested_modulation)
    ue_mod_ord = _modulation_order(applied.ue_max_modulation_dl)
    if req_mod_ord is not None and ue_mod_ord is not None and req_mod_ord > ue_mod_ord:
        mismatches.append(
            CellConfigMismatch(
                field="modulation",
                requested=requested_modulation,
                applied=applied.ue_max_modulation_dl,
            )
        )

    return CellConfigConsistencyResult(
        consistent=not mismatches,
        skipped=False,
        mismatches=mismatches,
    )


# ===========================================================================
# Phase 6 第三条线: DL MCS index (实际生效回读, 区别于上面的 UE 协商能力核对)
# ===========================================================================


@dataclass
class McsConsistencyResult:
    """AMC off 时请求 MCS vs throughput 实测生效 mcs_dl 的一致性。"""

    consistent: bool = True
    skipped: bool = False  # AMC on (mcs 浮动) / 无样本 → 不可核对
    requested_mcs: Optional[int] = None
    effective_mcs: Optional[int] = None  # 实测 mcs_dl 众数
    reason: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "consistent": self.consistent,
            "skipped": self.skipped,
            "requested_mcs": self.requested_mcs,
            "effective_mcs": self.effective_mcs,
            "reason": self.reason,
        }


def check_mcs_consistency(
    *,
    requested_mcs: int,
    enable_amc: bool,
    measured_mcs_samples: List[Optional[int]],
    bs_is_real: bool = True,
) -> McsConsistencyResult:
    """Phase 6 第三条线: AMC off 时固定 MCS 下发后, throughput 实测生效 mcs_dl 应 ==
    请求 mcs。UE 撑不住请求 MCS → 静默 clamp 到更低 (吞吐反映 clamp 后 MCS 却当请求
    MCS 测, 跟 layers/modulation clamp 同等危害)。

    跟 layers/modulation **不同**: 那两条读 attach 后 UE 协商能力 (capability); MCS 是跑
    流量后的**实际生效回读** (throughput metrics.mcs_dl), 只有 AMC off 固定 MCS 才有意义。

    - bs_is_real=False (mock BS): skipped —— mock mcs_dl 是合成随机值 (base_station
      mock 返回 randint), 不反映真实 clamp, 校验无意义 (mock-aware, 同 cell_config /
      emulation_file 门; 否则 mock measure 会因 mock mcs<请求 全部误 FAIL)。
    - enable_amc=True: AMC 动态调 MCS, mcs_dl 浮动是设计行为 → skipped (不校验)。
    - 无有效样本 (没跑流量): skipped。
    - 实测众数 effective < requested: 不一致 (被 clamp)。effective >= requested: 一致
      (AMC off 下正常应相等; > 不该发生但不算错)。
    """
    if not bs_is_real:
        return McsConsistencyResult(
            consistent=True,
            skipped=True,
            requested_mcs=requested_mcs,
            reason="mock baseStation: mcs_dl 合成值不反映真实 clamp, 不校验",
        )
    if enable_amc:
        return McsConsistencyResult(
            consistent=True,
            skipped=True,
            requested_mcs=requested_mcs,
            reason="enable_amc=True: AMC 动态调 MCS, mcs_dl 浮动为设计行为, 不校验",
        )
    # mcs_dl 默认 0 = "UXM 未报 DL_MCS" 哨兵 (Codex P1 #126): 过滤 None 和 <=0, 不当
    # 真实样本 (否则真 UXM 缺 DL_MCS 时 0 被当 clamp 误 FAIL)。MCS 0 (QPSK 最低) 吞吐
    # 测试不会用, 跟"未报"无法区分 → 一并 skip 取保守。
    samples = [int(s) for s in measured_mcs_samples if s is not None and int(s) > 0]
    if not samples:
        return McsConsistencyResult(
            consistent=True,
            skipped=True,
            requested_mcs=requested_mcs,
            reason="无 mcs_dl 样本 (mock / 未跑流量)",
        )
    effective = Counter(samples).most_common(1)[0][0]  # 众数 (AMC off 应稳定)
    if effective < requested_mcs:
        return McsConsistencyResult(
            consistent=False,
            skipped=False,
            requested_mcs=requested_mcs,
            effective_mcs=effective,
            reason=(
                f"AMC off 固定 MCS={requested_mcs} 但实测生效 mcs_dl 众数={effective} "
                f"(< 请求 → UE 静默 clamp; 吞吐反映 MCS {effective} 却当 {requested_mcs} 测)"
            ),
        )
    return McsConsistencyResult(
        consistent=True,
        skipped=False,
        requested_mcs=requested_mcs,
        effective_mcs=effective,
    )
