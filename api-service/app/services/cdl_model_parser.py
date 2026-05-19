"""CDL model name parser — 拆 operator-facing 字符串成 ChannelEgine
`Standard3GPPBuilder` 接受的 (scenario, cluster_model, condition) 三元组。

设计原则 (P1-7, 2026-05-19):
- 本模块**不持有** 3GPP 数据 (簇延迟 / 角度 / 功率统计参数等)。这些数据全在
  ChannelEgine 内部的 `channel_model_38901` package, 由 `Standard3GPPBuilder`
  调用。本模块只做字符串规约。
- 接受的枚举值跟 ChannelEgine `app.py:164-165` / `gui.py:138-139` 的 dropdown
  选项严格对齐, 避免传错值让 ChannelEgine 内部 raise generic error.

Naming convention (跟 [`gui/.../MIMOOTAConfigForm.tsx`] CDL_OPTIONS,
[`api-service/.../legacy_migration.py`] _CHANNEL_MODEL_TO_CDL 对齐):

- **Token order is irrelevant** — operator-facing strings come from multiple
  sources with different conventions:
    - GUI selector: ``"UMa NLOS CDL-C"``, ``"UMi LOS CDL-D"`` (Scenario Condition Cluster)
    - Legacy migration: same as GUI
    - Older docs / tests:  ``"UMa CDL-C NLOS"`` (Scenario Cluster Condition)
  Since :data:`SCENARIO_NAMES`, :data:`CLUSTER_MODEL_NAMES`, and
  :data:`CONDITION_NAMES` are disjoint sets, the parser classifies each token
  by membership rather than by position. Both orderings round-trip identically.

- **Aliases** for scenarios that the GUI / legacy seeds shorten:
    - ``"UMi"`` → ``"UMi-StreetCanyon"`` (canonical 3GPP TR 38.901 §7.2 default
      for "Urban Microcell"; ``UMi-OpenArea`` is the explicit minority)
    - ``"InH"`` → ``"InH-Office"`` (only InH sub-scenario in TR 38.901)

- **Defaults** when a token is omitted:
    - scenario absent  → ``"UMa"`` (most common cellular bench-test scenario)
    - condition absent → ``"NLOS"``  (TR 38.901 §7.2 majority case)
    - cluster absent   → **rejected** — cluster model is the load-bearing piece,
      bare ``"UMa NLOS"`` doesn't specify which delay/angle profile to use.

- **Bare cluster model** (e.g. ``"CDL-A"`` alone) is accepted — defaults to
  ``"UMa"`` scenario + ``"NLOS"`` condition. Matches the GUI selector's bare
  ``CDL-A``…``CDL-E`` entries.

- Ray-Tracing snapshots like ``"{Scenario} CDL Snapshot-{N}"`` are **not
  handled** here — operator picks RT scenarios through a separate workflow
  that bypasses 3GPP dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

# ChannelEgine accepted scenario values — must stay in lockstep with
# `channel-engine-service/app/models/hardware_pipeline_models.py:ScenarioName`
# and ChannelEgine's `mimo_ota_simulator/channel_builders.py`.
SCENARIO_NAMES = frozenset({
    "UMa",
    "UMi-StreetCanyon",
    "UMi-OpenArea",
    "RMa",
    "InH-Office",
    "SMa",
    "InF",
})

# Operator-facing aliases that don't appear in ChannelEgine's strict enum
# but are produced by the existing GUI selector / legacy seed data.
# Each alias maps to a single canonical SCENARIO_NAMES value.
SCENARIO_ALIASES = {
    "UMi": "UMi-StreetCanyon",
    "InH": "InH-Office",
}

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

DEFAULT_SCENARIO = "UMa"
DEFAULT_CONDITION: "ConditionLiteral" = "NLOS"

ConditionLiteral = Literal["LOS", "NLOS"]


@dataclass(frozen=True)
class ParsedCDLModelName:
    """A 3GPP standard CDL model identifier split for ChannelEgine dispatch.

    ``scenario_name`` is always a canonical :data:`SCENARIO_NAMES` value
    (aliases like ``"UMi"`` are resolved to ``"UMi-StreetCanyon"``).
    """

    scenario_name: str       # one of SCENARIO_NAMES (post-alias resolution)
    cluster_model_name: str  # one of CLUSTER_MODEL_NAMES
    condition: ConditionLiteral  # LOS / NLOS

    @property
    def is_los(self) -> bool:
        return self.condition == "LOS"


def _classify_token(tok: str) -> Tuple[str, str]:
    """Classify a single token into one of four buckets.

    Returns ``(kind, normalized_value)`` where ``kind`` is one of
    ``"scenario"`` / ``"cluster"`` / ``"condition"`` / ``"unknown"`` and
    ``normalized_value`` is the canonical form
    (scenario alias resolved, condition uppercased) or the original token
    if ``kind == "unknown"``.
    """
    # Condition match is case-insensitive — operators sometimes type "los"
    upper = tok.upper()
    if upper in CONDITION_NAMES:
        return "condition", upper
    if tok in SCENARIO_NAMES:
        return "scenario", tok
    if tok in SCENARIO_ALIASES:
        return "scenario", SCENARIO_ALIASES[tok]
    if tok in CLUSTER_MODEL_NAMES:
        return "cluster", tok
    return "unknown", tok


def parse_cdl_model_name(name: str) -> ParsedCDLModelName:
    """Parse an operator-facing CDL model name into a ChannelEgine-dispatch tuple.

    Token order is irrelevant — each token is classified by which enum set it
    belongs to. The cluster model token is required; scenario defaults to
    ``"UMa"`` and condition defaults to ``"NLOS"`` when absent.

    Accepted forms (non-exhaustive):

        - ``"UMa NLOS CDL-C"``         → ("UMa", "CDL-C", "NLOS")    # GUI / legacy
        - ``"UMa CDL-C NLOS"``         → ("UMa", "CDL-C", "NLOS")    # older docs
        - ``"UMi LOS CDL-D"``          → ("UMi-StreetCanyon", "CDL-D", "LOS")
        - ``"InH CDL-B"``              → ("InH-Office", "CDL-B", "NLOS")
        - ``"CDL-A"``                  → ("UMa", "CDL-A", "NLOS")
        - ``"UMi-StreetCanyon Stochastic LOS"`` → ("UMi-StreetCanyon", "Stochastic", "LOS")
        - ``"RMa CDL-A los"``          → ("RMa", "CDL-A", "LOS")     # condition case-insensitive

    Raises:
        ValueError: when input isn't a non-empty string of 1-3 space-separated
            tokens, when any token is unknown, when the same role appears
            twice (e.g. two scenarios), or when the cluster model is missing.
    """
    if not isinstance(name, str):
        raise ValueError(
            f"cdl_model_name must be a string, got {type(name).__name__}"
        )
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("cdl_model_name is empty or whitespace-only")

    tokens = cleaned.split()
    if not 1 <= len(tokens) <= 3:
        raise ValueError(
            f"cdl_model_name {name!r} has {len(tokens)} space-separated tokens; "
            f"expected 1-3 (any of: scenario / cluster_model / condition, in any order). "
            f"Examples: 'UMa NLOS CDL-C', 'InH CDL-B', 'CDL-A'."
        )

    scenario: str | None = None
    cluster_model: str | None = None
    condition: ConditionLiteral | None = None
    unknown: list[str] = []

    for tok in tokens:
        kind, value = _classify_token(tok)
        if kind == "scenario":
            if scenario is not None:
                raise ValueError(
                    f"cdl_model_name {name!r} has multiple scenario tokens "
                    f"({scenario!r} and {value!r}); only one allowed."
                )
            scenario = value
        elif kind == "cluster":
            if cluster_model is not None:
                raise ValueError(
                    f"cdl_model_name {name!r} has multiple cluster_model tokens "
                    f"({cluster_model!r} and {value!r}); only one allowed."
                )
            cluster_model = value
        elif kind == "condition":
            if condition is not None:
                raise ValueError(
                    f"cdl_model_name {name!r} has multiple condition tokens "
                    f"({condition!r} and {value!r}); only one allowed."
                )
            condition = value  # type: ignore[assignment]
        else:
            unknown.append(tok)

    if unknown:
        raise ValueError(
            f"cdl_model_name {name!r} contains unknown token(s) {unknown}. "
            f"Accepted scenarios: {sorted(SCENARIO_NAMES)} "
            f"(aliases: {sorted(SCENARIO_ALIASES)}); "
            f"accepted cluster_model: {sorted(CLUSTER_MODEL_NAMES)}; "
            f"accepted condition: {sorted(CONDITION_NAMES)} (case-insensitive)."
        )

    if cluster_model is None:
        raise ValueError(
            f"cdl_model_name {name!r} has no cluster_model token; "
            f"one of {sorted(CLUSTER_MODEL_NAMES)} is required "
            f"(bare scenario/condition is not enough to dispatch 3GPP synthesis)."
        )

    if scenario is None:
        scenario = DEFAULT_SCENARIO
    if condition is None:
        condition = DEFAULT_CONDITION

    return ParsedCDLModelName(
        scenario_name=scenario,
        cluster_model_name=cluster_model,
        condition=condition,
    )


def as_tuple(parsed: ParsedCDLModelName) -> Tuple[str, str, str]:
    """Convenience for places that prefer the bare tuple — e.g. logging."""
    return (parsed.scenario_name, parsed.cluster_model_name, parsed.condition)
