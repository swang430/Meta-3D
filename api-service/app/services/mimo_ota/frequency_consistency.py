"""P2-11 Phase 1: 多方频率一致性 fail-loud 校验.

架构原则 (docs/architecture/testcase-driven-instrument-config.md): TestCase 是频率
单一真值源; 各仪表 (UXM / F64 / SA) 配置后归一到 (中心 ARFCN, 带宽) 规范标识, 必须
跟 TestCase **精确一致** (ARFCN 整数相等 + 带宽相等, 无浮点容差 —— ARFCN 是 3GPP
标准整数)。不一致 = 静默错配 (e.g. GCM 模式 TestCase 3500 但 F64 用默认 .smu 3600,
或 UXM 标称 3500 但没传 arfcn 实际下发 band fallback 基线值), fail-loud 拦住。

这是 silent-failure 防护 (P1-8 cal / P1-9 DUT / P1-12 未验证标记 同族): 不管配置来自
TestCase 还是默认 fallback, 最后都校验多方同频, 保护测试结果可信度。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.hal.nr_arfcn import FrequencyIdentity


@dataclass(frozen=True)
class FrequencyMismatch:
    instrument: str
    expected: str  # TestCase identity describe (真值)
    actual: str    # 仪表 identity describe (实际)


@dataclass
class FrequencyConsistencyResult:
    consistent: bool
    testcase_identity: str
    per_instrument: Dict[str, str]  # name → describe / "未报告(跳过)"
    mismatches: List[FrequencyMismatch] = field(default_factory=list)

    def failure_reason(self) -> Optional[str]:
        if self.consistent:
            return None
        parts = [
            f"{m.instrument}=实际 {m.actual} (≠ TestCase {m.expected})"
            for m in self.mismatches
        ]
        return (
            "频率不一致 — 各仪表中心 ARFCN/带宽必须跟 TestCase 一致: "
            + "; ".join(parts)
        )

    def to_payload(self) -> Dict[str, object]:
        return {
            "consistent": self.consistent,
            "testcase_identity": self.testcase_identity,
            "per_instrument": self.per_instrument,
            "mismatches": [
                {"instrument": m.instrument, "expected": m.expected, "actual": m.actual}
                for m in self.mismatches
            ],
        }


def check_frequency_consistency(
    testcase: FrequencyIdentity,
    instruments: Dict[str, Optional[FrequencyIdentity]],
) -> FrequencyConsistencyResult:
    """校验各仪表频率规范标识跟 TestCase 精确一致。

    Args:
        testcase: TestCase 派生的频率规范标识 (真值源)。
        instruments: ``{仪表名: Optional[FrequencyIdentity]}``。``None`` = 该仪表无
            频率可报 → **跳过, 不算不一致** (e.g. ASC 路径 F64 频率由 channel-engine
            按 TestCase 同源生成, driver 状态里没有; 或仪表未配置)。

    Returns:
        FrequencyConsistencyResult: ``consistent`` + 每仪表 identity + mismatch 列表。
        比对是精确的 (FrequencyIdentity 相等 = ARFCN 整数 + 带宽都相等)。
    """
    per_instrument: Dict[str, str] = {}
    mismatches: List[FrequencyMismatch] = []
    for name, ident in instruments.items():
        if ident is None:
            per_instrument[name] = "未报告(跳过)"
            continue
        per_instrument[name] = ident.describe()
        if ident != testcase:
            mismatches.append(
                FrequencyMismatch(
                    instrument=name,
                    expected=testcase.describe(),
                    actual=ident.describe(),
                )
            )
    return FrequencyConsistencyResult(
        consistent=not mismatches,
        testcase_identity=testcase.describe(),
        per_instrument=per_instrument,
        mismatches=mismatches,
    )
