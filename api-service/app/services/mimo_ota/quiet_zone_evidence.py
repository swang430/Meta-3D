"""Fail-closed quiet-zone evidence contract for MIMO OTA consumers."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


QUIET_ZONE_EVIDENCE_SCHEMA_VERSION = 1

_KEYS = {
    "schema_version",
    "status",
    "source",
    "formal_verified",
    "measured_ripple_db",
    "proxy_ripple_db",
    "calibration_id",
}


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def build_quiet_zone_evidence(proxy_ripple_db: Any) -> Dict[str, Any]:
    """Build the only two states currently supported by an authoritative writer.

    ProbePattern peak spread is useful diagnostics, but it is not a multi-point
    quiet-zone field measurement.  The real grid acquisition path remains
    fail-closed until a sourced centimetre-unit linear-stage contract exists.
    """
    proxy = _finite_number(proxy_ripple_db)
    return {
        "schema_version": QUIET_ZONE_EVIDENCE_SCHEMA_VERSION,
        "status": "diagnostic_proxy" if proxy is not None else "unavailable",
        "source": "probe_pattern_peak_spread" if proxy is not None else "missing",
        "formal_verified": False,
        "measured_ripple_db": None,
        "proxy_ripple_db": proxy,
        "calibration_id": None,
    }


def parse_quiet_zone_evidence(value: Any) -> Optional[Dict[str, Any]]:
    """Return a normalized snapshot only for an exact writer-supported state."""
    if not isinstance(value, dict) or set(value) != _KEYS:
        return None
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != QUIET_ZONE_EVIDENCE_SCHEMA_VERSION
    ):
        return None
    if value.get("formal_verified") is not False:
        return None
    if value.get("measured_ripple_db") is not None:
        return None
    if value.get("calibration_id") is not None:
        return None

    status = value.get("status")
    source = value.get("source")
    if status == "unavailable" and source == "missing":
        if value.get("proxy_ripple_db") is not None:
            return None
        return build_quiet_zone_evidence(None)
    if status == "diagnostic_proxy" and source == "probe_pattern_peak_spread":
        proxy = _finite_number(value.get("proxy_ripple_db"))
        if proxy is None:
            return None
        return build_quiet_zone_evidence(proxy)
    return None


def quiet_zone_evidence_is_formally_verified(value: Any) -> bool:
    """Current supported states are explicitly non-formal."""
    parsed = parse_quiet_zone_evidence(value)
    return parsed is not None and parsed["formal_verified"] is True


def quiet_zone_scope_is_formally_verified(precheck: Any) -> bool:
    """Legacy flags and source strings cannot promote an untrusted snapshot."""
    if not isinstance(precheck, dict):
        return False
    return quiet_zone_evidence_is_formally_verified(
        precheck.get("quiet_zone_evidence")
    )
