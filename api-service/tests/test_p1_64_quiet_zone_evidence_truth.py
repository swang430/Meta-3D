"""P1-64: 静区代理量不能冒充正式多点场扫描证据。"""

import math

import pytest


def test_missing_quiet_zone_measurement_builds_unavailable_snapshot():
    from app.services.mimo_ota.quiet_zone_evidence import (
        build_quiet_zone_evidence,
        quiet_zone_evidence_is_formally_verified,
    )

    snapshot = build_quiet_zone_evidence(None)

    assert snapshot == {
        "schema_version": 1,
        "status": "unavailable",
        "source": "missing",
        "formal_verified": False,
        "measured_ripple_db": None,
        "proxy_ripple_db": None,
        "calibration_id": None,
    }
    assert quiet_zone_evidence_is_formally_verified(snapshot) is False


def test_probe_pattern_spread_is_only_a_diagnostic_proxy():
    from app.services.mimo_ota.quiet_zone_evidence import (
        build_quiet_zone_evidence,
        quiet_zone_evidence_is_formally_verified,
    )

    snapshot = build_quiet_zone_evidence(0.42)

    assert snapshot == {
        "schema_version": 1,
        "status": "diagnostic_proxy",
        "source": "probe_pattern_peak_spread",
        "formal_verified": False,
        "measured_ripple_db": None,
        "proxy_ripple_db": 0.42,
        "calibration_id": None,
    }
    assert quiet_zone_evidence_is_formally_verified(snapshot) is False


@pytest.mark.parametrize("bad_proxy", [math.nan, math.inf, -math.inf, True, "0.4"])
def test_non_finite_or_non_numeric_proxy_is_not_published(bad_proxy):
    from app.services.mimo_ota.quiet_zone_evidence import build_quiet_zone_evidence

    assert build_quiet_zone_evidence(bad_proxy)["status"] == "unavailable"
    assert build_quiet_zone_evidence(bad_proxy)["proxy_ripple_db"] is None


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: [value],
        lambda value: {**value, "extra": "client-claim"},
        lambda value: {**value, "schema_version": True},
        lambda value: {**value, "status": "measured", "formal_verified": True},
        lambda value: {**value, "source": "ce_sa"},
        lambda value: {**value, "measured_ripple_db": 0.5},
        lambda value: {**value, "proxy_ripple_db": math.nan},
    ],
)
def test_parser_rejects_noncanonical_or_impossible_snapshots(mutator):
    from app.services.mimo_ota.quiet_zone_evidence import (
        build_quiet_zone_evidence,
        parse_quiet_zone_evidence,
    )

    canonical = build_quiet_zone_evidence(0.42)
    assert parse_quiet_zone_evidence(mutator(canonical)) is None


def test_legacy_boolean_cannot_promote_diagnostic_snapshot():
    from app.services.mimo_ota.quiet_zone_evidence import (
        build_quiet_zone_evidence,
        quiet_zone_scope_is_formally_verified,
    )

    precheck = {
        "quiet_zone_verified": True,
        "quiet_zone_pass": True,
        "quiet_zone_ripple_source": "probe_pattern_peak_spread",
        "quiet_zone_evidence": build_quiet_zone_evidence(0.42),
    }

    assert quiet_zone_scope_is_formally_verified(precheck) is False
