"""CDL model name parser unit tests — P1-7 (2026-05-19).

Pins:
1. Full coverage of accepted (scenario × cluster_model × condition) tuples
2. Default condition (NLOS) when caller omits it
3. Friendly error messages for unknown tokens / bad shape / empty input
4. as_tuple convenience returns the right shape
"""
from __future__ import annotations

import itertools

import pytest

from app.services.cdl_model_parser import (
    CLUSTER_MODEL_NAMES,
    CONDITION_NAMES,
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
    def test_every_accepted_triple_parses(
        self, scenario: str, cluster_model: str, condition: str,
    ) -> None:
        name = f"{scenario} {cluster_model} {condition}"
        p = parse_cdl_model_name(name)
        assert p.scenario_name == scenario
        assert p.cluster_model_name == cluster_model
        assert p.condition == condition
        # is_los derived consistently
        assert p.is_los == (condition == "LOS")


# ---------------------------------------------------------------------------
# Default condition behavior
# ---------------------------------------------------------------------------

class TestDefaultCondition:
    """2-token input (scenario + cluster_model) defaults to NLOS — TR 38.901
    §7.2 majority case, LOS is explicit minority."""

    def test_two_token_input_defaults_nlos(self):
        p = parse_cdl_model_name("UMa CDL-C")
        assert p.scenario_name == "UMa"
        assert p.cluster_model_name == "CDL-C"
        assert p.condition == "NLOS"
        assert p.is_los is False

    def test_condition_case_normalized(self):
        """LOWERCASE 'los' should be uppercased to LOS (operator UX)."""
        p = parse_cdl_model_name("RMa CDL-A los")
        assert p.condition == "LOS"


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

    def test_single_token_rejected(self):
        with pytest.raises(ValueError, match=r"doesn't match"):
            parse_cdl_model_name("UMa")

    def test_four_tokens_rejected(self):
        """Spec demands 2 or 3 space-separated tokens — extra trailing data
        means operator typo'd a value or appended noise."""
        with pytest.raises(ValueError, match=r"doesn't match"):
            parse_cdl_model_name("UMa CDL-C NLOS extra")

    def test_unknown_scenario_rejected_with_helpful_message(self):
        with pytest.raises(ValueError) as exc:
            parse_cdl_model_name("Mars CDL-C NLOS")
        msg = str(exc.value)
        assert "scenario_name" in msg
        assert "Mars" in msg
        # Lists the accepted values so operator can self-correct
        assert "UMa" in msg

    def test_unknown_cluster_model_rejected_with_helpful_message(self):
        with pytest.raises(ValueError) as exc:
            parse_cdl_model_name("UMa BadCDL NLOS")
        msg = str(exc.value)
        assert "cluster_model_name" in msg
        assert "BadCDL" in msg
        assert "CDL-A" in msg

    def test_unknown_condition_rejected(self):
        with pytest.raises(ValueError) as exc:
            parse_cdl_model_name("UMa CDL-C Sunny")
        assert "condition" in str(exc.value)

    def test_hyphenated_scenario_with_internal_space_rejected(self):
        """UMi-StreetCanyon (correct) vs 'UMi StreetCanyon' (typo).
        Space is the only token separator — internal spaces in a scenario
        name mean operator forgot the hyphen."""
        with pytest.raises(ValueError):
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

    def test_inh_office_parses(self):
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
