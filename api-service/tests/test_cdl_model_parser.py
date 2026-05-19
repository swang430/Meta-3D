"""CDL model name parser unit tests — P1-7 (2026-05-19).

Pins:
1. Full coverage of accepted (scenario × cluster_model × condition) tuples,
   in the canonical TR-38.901 GUI ordering used everywhere in MIMO-First.
2. Token order is irrelevant — all 6 permutations of a 3-token name parse
   identically (parser classifies by enum-membership, not position).
3. Every existing GUI dropdown option (CDL_OPTIONS in MIMOOTAConfigForm.tsx)
   round-trips through the parser without raising — the regression Codex P1
   flagged on commit 937c5b5d93.
4. Scenario aliases: ``"UMi"`` → ``"UMi-StreetCanyon"``, ``"InH"`` → ``"InH-Office"``.
5. Bare cluster model (``"CDL-A"``) defaults scenario→UMa, condition→NLOS.
6. Defaults: 2-token without condition → NLOS; condition case-insensitive.
7. Friendly error messages for unknown tokens, missing cluster, role conflicts.
8. as_tuple convenience returns the right shape.
"""
from __future__ import annotations

import itertools

import pytest

from app.services.cdl_model_parser import (
    CLUSTER_MODEL_NAMES,
    CONDITION_NAMES,
    SCENARIO_ALIASES,
    SCENARIO_NAMES,
    ParsedCDLModelName,
    as_tuple,
    parse_cdl_model_name,
)


# ---------------------------------------------------------------------------
# Coverage matrix — 7 × 7 × 2 = 98 combinations
# ---------------------------------------------------------------------------

class TestCoverageMatrix:
    """Hit every accepted (scenario, cluster_model, condition) tuple.

    Why: any ChannelEgine-accepted value should round-trip through the parser
    without raising. If ChannelEgine widens the enum (e.g. adds a new
    scenario), this test surfaces the gap at the parser side before runtime.
    """

    @pytest.mark.parametrize(
        "scenario,cluster_model,condition",
        list(
            itertools.product(SCENARIO_NAMES, CLUSTER_MODEL_NAMES, CONDITION_NAMES)
        ),
    )
    def test_every_accepted_triple_parses_canonical_order(
        self, scenario: str, cluster_model: str, condition: str,
    ) -> None:
        """Canonical project ordering ``{Scenario} {Condition} {Cluster}``."""
        name = f"{scenario} {condition} {cluster_model}"
        p = parse_cdl_model_name(name)
        assert p.scenario_name == scenario
        assert p.cluster_model_name == cluster_model
        assert p.condition == condition
        assert p.is_los == (condition == "LOS")

    @pytest.mark.parametrize(
        "scenario,cluster_model,condition",
        list(
            itertools.product(SCENARIO_NAMES, CLUSTER_MODEL_NAMES, CONDITION_NAMES)
        ),
    )
    def test_every_accepted_triple_parses_alternate_order(
        self, scenario: str, cluster_model: str, condition: str,
    ) -> None:
        """Older docs ordering ``{Scenario} {Cluster} {Condition}`` also accepted."""
        name = f"{scenario} {cluster_model} {condition}"
        p = parse_cdl_model_name(name)
        assert p.scenario_name == scenario
        assert p.cluster_model_name == cluster_model
        assert p.condition == condition


# ---------------------------------------------------------------------------
# Token order is irrelevant — all 6 permutations of a 3-token name parse same
# ---------------------------------------------------------------------------

class TestTokenOrderInvariance:
    """The parser classifies by enum-membership, so any permutation of a
    3-token (scenario, cluster, condition) triple yields the same result.

    Why: the GUI selector emits ``{Scenario} {Condition} {Cluster}`` but
    older code (and this very parser's earlier version) wrote tests against
    ``{Scenario} {Cluster} {Condition}``. Lock down that BOTH work.
    """

    @pytest.mark.parametrize(
        "ordered_tokens",
        list(itertools.permutations(["UMa", "CDL-C", "NLOS"])),
    )
    def test_all_six_permutations_yield_same_result(
        self, ordered_tokens: tuple[str, str, str],
    ) -> None:
        p = parse_cdl_model_name(" ".join(ordered_tokens))
        assert p.scenario_name == "UMa"
        assert p.cluster_model_name == "CDL-C"
        assert p.condition == "NLOS"


# ---------------------------------------------------------------------------
# Codex P1 regression: every current GUI dropdown option must parse
# ---------------------------------------------------------------------------

class TestGUIDropdownOptions:
    """Pins all 10 ``CDL_OPTIONS`` entries from
    ``gui/.../MIMOOTAConfigForm.tsx`` against the parser. If the GUI option
    list changes, update this test in the same PR.

    Why this exists: PR #59 commit 937c5b5d93 assumed canonical
    ``{Scenario} {Cluster} {Condition}`` ordering and rejected every actual
    GUI value (Codex P1 review). This regression test makes the parser-vs-GUI
    contract explicit.
    """

    @pytest.mark.parametrize(
        "gui_value, expected_scenario, expected_cluster, expected_condition",
        [
            # 5 fully-qualified options
            ("UMi LOS CDL-D", "UMi-StreetCanyon", "CDL-D", "LOS"),
            ("UMi NLOS CDL-A", "UMi-StreetCanyon", "CDL-A", "NLOS"),
            ("UMa LOS CDL-D", "UMa", "CDL-D", "LOS"),
            ("UMa NLOS CDL-C", "UMa", "CDL-C", "NLOS"),
            ("InH CDL-B", "InH-Office", "CDL-B", "NLOS"),
            # 5 bare-cluster options
            ("CDL-A", "UMa", "CDL-A", "NLOS"),
            ("CDL-B", "UMa", "CDL-B", "NLOS"),
            ("CDL-C", "UMa", "CDL-C", "NLOS"),
            ("CDL-D", "UMa", "CDL-D", "NLOS"),
            ("CDL-E", "UMa", "CDL-E", "NLOS"),
        ],
    )
    def test_current_gui_option_parses(
        self,
        gui_value: str,
        expected_scenario: str,
        expected_cluster: str,
        expected_condition: str,
    ) -> None:
        p = parse_cdl_model_name(gui_value)
        assert p.scenario_name == expected_scenario
        assert p.cluster_model_name == expected_cluster
        assert p.condition == expected_condition


# ---------------------------------------------------------------------------
# Scenario aliases — operator-facing short names → canonical ChannelEgine
# ---------------------------------------------------------------------------

class TestScenarioAliases:
    """``"UMi"`` and ``"InH"`` are the only aliases. Both resolve to the
    canonical TR 38.901 sub-scenario most commonly meant in MIMO OTA work."""

    def test_umi_resolves_to_streetcanyon(self):
        p = parse_cdl_model_name("UMi CDL-C NLOS")
        assert p.scenario_name == "UMi-StreetCanyon"

    def test_inh_resolves_to_office(self):
        p = parse_cdl_model_name("InH CDL-B LOS")
        assert p.scenario_name == "InH-Office"

    def test_alias_set_matches_documented(self):
        """If someone adds a new alias they must update both the parser and
        this regression — the alias set is a stable interface."""
        assert SCENARIO_ALIASES == {
            "UMi": "UMi-StreetCanyon",
            "InH": "InH-Office",
        }

    def test_alias_targets_are_canonical(self):
        """Every alias target must itself be a canonical scenario."""
        for alias, target in SCENARIO_ALIASES.items():
            assert target in SCENARIO_NAMES, (
                f"alias {alias!r} → {target!r} but {target!r} not in SCENARIO_NAMES"
            )


# ---------------------------------------------------------------------------
# Defaults — bare cluster, missing condition
# ---------------------------------------------------------------------------

class TestDefaults:
    """Document the defaults the parser fills in."""

    def test_bare_cluster_defaults_uma_nlos(self):
        """Bare ``"CDL-A"`` → UMa scenario + NLOS condition (most common
        cellular bench-test combo)."""
        p = parse_cdl_model_name("CDL-A")
        assert p.scenario_name == "UMa"
        assert p.cluster_model_name == "CDL-A"
        assert p.condition == "NLOS"
        assert p.is_los is False

    def test_two_token_scenario_plus_cluster_defaults_nlos(self):
        p = parse_cdl_model_name("UMa CDL-C")
        assert p.scenario_name == "UMa"
        assert p.cluster_model_name == "CDL-C"
        assert p.condition == "NLOS"

    def test_two_token_cluster_plus_condition_defaults_uma(self):
        p = parse_cdl_model_name("CDL-D LOS")
        assert p.scenario_name == "UMa"
        assert p.cluster_model_name == "CDL-D"
        assert p.condition == "LOS"

    def test_condition_case_normalized(self):
        """LOWERCASE 'los' should be uppercased to LOS (operator REPL UX)."""
        p = parse_cdl_model_name("RMa CDL-A los")
        assert p.condition == "LOS"

    def test_condition_mixed_case_normalized(self):
        p = parse_cdl_model_name("CDL-B NlOs")
        assert p.condition == "NLOS"


# ---------------------------------------------------------------------------
# Invalid inputs — friendly error messages
# ---------------------------------------------------------------------------

class TestInvalidInputs:
    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match=r"empty"):
            parse_cdl_model_name("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match=r"empty"):
            parse_cdl_model_name("   \t  ")

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match=r"must be a string"):
            parse_cdl_model_name(123)  # type: ignore[arg-type]

    def test_bare_scenario_rejected_no_cluster(self):
        """``"UMa"`` alone has no cluster model — TR 38.901 dispatch needs one."""
        with pytest.raises(ValueError, match=r"no cluster_model"):
            parse_cdl_model_name("UMa")

    def test_bare_condition_rejected_no_cluster(self):
        with pytest.raises(ValueError, match=r"no cluster_model"):
            parse_cdl_model_name("NLOS")

    def test_scenario_plus_condition_rejected_no_cluster(self):
        with pytest.raises(ValueError, match=r"no cluster_model"):
            parse_cdl_model_name("UMa NLOS")

    def test_four_tokens_rejected(self):
        """Spec demands 1-3 space-separated tokens — extra trailing data
        means operator typo'd a value or appended noise."""
        with pytest.raises(ValueError, match=r"1-3"):
            parse_cdl_model_name("UMa CDL-C NLOS extra")

    def test_unknown_scenario_rejected_with_helpful_message(self):
        with pytest.raises(ValueError) as exc:
            parse_cdl_model_name("Mars CDL-C NLOS")
        msg = str(exc.value)
        assert "unknown token" in msg
        assert "Mars" in msg
        # Lists the accepted values so operator can self-correct
        assert "UMa" in msg

    def test_unknown_cluster_model_rejected_with_helpful_message(self):
        with pytest.raises(ValueError) as exc:
            parse_cdl_model_name("UMa BadCDL NLOS")
        msg = str(exc.value)
        assert "unknown token" in msg
        assert "BadCDL" in msg
        assert "CDL-A" in msg

    def test_unknown_condition_rejected(self):
        with pytest.raises(ValueError) as exc:
            parse_cdl_model_name("UMa CDL-C Sunny")
        msg = str(exc.value)
        assert "unknown token" in msg
        assert "Sunny" in msg

    def test_multiple_scenarios_rejected(self):
        """Two scenario tokens (e.g. ``"UMa UMi CDL-C"``) is ambiguous."""
        with pytest.raises(ValueError, match=r"multiple scenario"):
            parse_cdl_model_name("UMa UMi CDL-C")

    def test_multiple_clusters_rejected(self):
        with pytest.raises(ValueError, match=r"multiple cluster_model"):
            parse_cdl_model_name("CDL-A CDL-B NLOS")

    def test_multiple_conditions_rejected(self):
        with pytest.raises(ValueError, match=r"multiple condition"):
            parse_cdl_model_name("UMa LOS NLOS")

    def test_hyphenated_scenario_with_internal_space_rejected(self):
        """``"UMi-StreetCanyon"`` (correct) vs ``"UMi StreetCanyon"`` (typo).
        ``"UMi"`` resolves to alias, but ``"StreetCanyon"`` is unknown — the
        parser surfaces the unknown token rather than silently dropping it."""
        with pytest.raises(ValueError, match=r"unknown token"):
            parse_cdl_model_name("UMi StreetCanyon CDL-C")


# ---------------------------------------------------------------------------
# Hyphenated scenario names (UMi-StreetCanyon etc.) parse cleanly
# ---------------------------------------------------------------------------

class TestHyphenatedScenarios:
    """Make sure hyphens inside scenario names don't get split — pins the
    "space is sole separator" contract."""

    def test_umi_streetcanyon_parses(self):
        p = parse_cdl_model_name("UMi-StreetCanyon CDL-C NLOS")
        assert p.scenario_name == "UMi-StreetCanyon"
        assert p.cluster_model_name == "CDL-C"

    def test_umi_openarea_parses(self):
        p = parse_cdl_model_name("UMi-OpenArea Stochastic LOS")
        assert p.scenario_name == "UMi-OpenArea"

    def test_inh_office_canonical_still_parses(self):
        """``"InH-Office"`` (canonical) must keep working even though
        ``"InH"`` (alias) also resolves to it."""
        p = parse_cdl_model_name("InH-Office CDL-A LOS")
        assert p.scenario_name == "InH-Office"


# ---------------------------------------------------------------------------
# as_tuple convenience
# ---------------------------------------------------------------------------

class TestAsTuple:
    def test_returns_three_tuple_in_order(self):
        p = ParsedCDLModelName(
            scenario_name="UMa", cluster_model_name="CDL-C", condition="NLOS",
        )
        assert as_tuple(p) == ("UMa", "CDL-C", "NLOS")
