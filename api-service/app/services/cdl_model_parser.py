"""CDL model name parser — 拆 "UMa CDL-C NLOS" 这种字符串成 ChannelEgine
`Standard3GPPBuilder` 接受的 (scenario, cluster_model, condition) 三元组。

设计原则 (P1-7, 2026-05-19):
- 本模块**不持有** 3GPP 数据 (簇延迟 / 角度 / 功率统计参数等)。这些数据全在
  ChannelEgine 内部的 `channel_model_38901` package, 由 `Standard3GPPBuilder`
  调用。本模块只做字符串规约。
- 枚举值跟 ChannelEgine `app.py:164-165` / `gui.py:138-139` 的 dropdown 选项
  严格对齐, 避免传错值让 ChannelEgine 内部 raise generic error.

Naming convention (跟 [`docs/api/data-model.md`] 命名规范 + 历史 cdl_model_name
惯例对齐):
- 3GPP 标准模型: `"{ScenarioName} {ClusterModelName} {Condition}"`,
  e.g. `"UMa CDL-C NLOS"`, `"UMi-StreetCanyon Stochastic LOS"`
- Ray-Tracing snapshots: `"{ScenarioName} CDL Snapshot-{N}"` — **不被本解析器
  处理** (operator selects RT scenario via separate workflow, bypasses 3GPP)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

# ChannelEgine accepted values — 跟 mimo_ota_simulator/channel_builders.py 同步
# 任何更新需要同时 verify 跟 ChannelEgine /app.py:164-165 一致.
SCENARIO_NAMES = frozenset({
    "UMa",
    "UMi-StreetCanyon",
    "UMi-OpenArea",
    "RMa",
    "InH-Office",
    "SMa",
    "InF",
})

CLUSTER_MODEL_NAMES = frozenset({
    "Stochastic",
    "CDL-A",
    "CDL-B",
    "CDL-C",
    "CDL-D",
    "CDL-E",
    "SCME",
})

CONDITION_NAMES = frozenset({"LOS", "NLOS"})

# Conditions on `is_los` default mapping (when condition is parsed)
ConditionLiteral = Literal["LOS", "NLOS"]


@dataclass(frozen=True)
class ParsedCDLModelName:
    """A 3GPP standard CDL model identifier split for ChannelEgine dispatch.

    `condition` defaults to "NLOS" when the operator-supplied string omits it
    (consistent with TR 38.901 §7.2 default for most scenarios; LOS is the
    explicit minority case).
    """

    scenario_name: str       # one of SCENARIO_NAMES
    cluster_model_name: str  # one of CLUSTER_MODEL_NAMES
    condition: ConditionLiteral  # LOS / NLOS

    @property
    def is_los(self) -> bool:
        return self.condition == "LOS"


def parse_cdl_model_name(name: str) -> ParsedCDLModelName:
    """Parse a 3GPP-style CDL model name into ChannelEgine-dispatch tuple.

    Accepts the canonical format::

        "{ScenarioName} {ClusterModelName} {Condition}"

    Examples:
        - "UMa CDL-C NLOS" → ("UMa", "CDL-C", "NLOS")
        - "UMi-StreetCanyon Stochastic LOS" → ("UMi-StreetCanyon", "Stochastic", "LOS")
        - "RMa CDL-A" → ("RMa", "CDL-A", "NLOS")  # condition default
        - "UMa CDL-C" → ("UMa", "CDL-C", "NLOS")

    Multi-word scenario names (e.g. "UMi-StreetCanyon") use hyphens — the
    parser does *not* split on hyphens. Space is the only separator.

    Raises:
        ValueError: when the name doesn't match the format, when any token
            is not in the ChannelEgine-accepted enums, or when the input is
            empty/whitespace-only.
    """
    if not isinstance(name, str):
        raise ValueError(
            f"cdl_model_name must be a string, got {type(name).__name__}"
        )
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("cdl_model_name is empty or whitespace-only")

    tokens = cleaned.split()
    if len(tokens) not in (2, 3):
        raise ValueError(
            f"cdl_model_name {name!r} doesn't match "
            f"'{{Scenario}} {{ClusterModel}} [{{Condition}}]' shape "
            f"(got {len(tokens)} space-separated tokens, need 2 or 3). "
            f"Valid examples: 'UMa CDL-C NLOS', 'RMa Stochastic LOS', 'UMa CDL-C'."
        )

    scenario, cluster_model = tokens[0], tokens[1]
    condition: ConditionLiteral = (
        tokens[2].upper() if len(tokens) == 3 else "NLOS"  # type: ignore[assignment]
    )

    if scenario not in SCENARIO_NAMES:
        raise ValueError(
            f"scenario_name {scenario!r} not in ChannelEgine-accepted "
            f"values {sorted(SCENARIO_NAMES)}. Source: cdl_model_name={name!r}"
        )
    if cluster_model not in CLUSTER_MODEL_NAMES:
        raise ValueError(
            f"cluster_model_name {cluster_model!r} not in ChannelEgine-accepted "
            f"values {sorted(CLUSTER_MODEL_NAMES)}. Source: cdl_model_name={name!r}"
        )
    if condition not in CONDITION_NAMES:
        raise ValueError(
            f"condition {condition!r} not in {sorted(CONDITION_NAMES)}. "
            f"Source: cdl_model_name={name!r}"
        )

    return ParsedCDLModelName(
        scenario_name=scenario,
        cluster_model_name=cluster_model,
        condition=condition,  # type: ignore[arg-type]
    )


def as_tuple(parsed: ParsedCDLModelName) -> Tuple[str, str, str]:
    """Convenience for places that prefer the bare tuple — e.g. logging."""
    return (parsed.scenario_name, parsed.cluster_model_name, parsed.condition)
