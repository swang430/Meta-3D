"""Formal throughput provenance checks shared by every verdict consumer."""

from __future__ import annotations

from typing import Any

from app.hal.base_station import ThroughputMetrics


def required_throughput_scope(measure: Any) -> str | None:
    """Return the only formal scope allowed by the recorded carrier count."""
    if not isinstance(measure, dict):
        return None
    carrier_aggregation = measure.get("carrier_aggregation")
    carrier_count = (
        carrier_aggregation.get("num_component_carriers")
        if isinstance(carrier_aggregation, dict)
        else None
    )
    if type(carrier_count) is int and carrier_count == 1:
        return ThroughputMetrics.SCOPE_PCELL
    if type(carrier_count) is int and carrier_count > 1:
        return ThroughputMetrics.SCOPE_NR_ALL_CELLS
    return None


def throughput_scope_is_verified(measure: Any) -> bool:
    """Require carrier-count, phase-level and per-azimuth scope evidence."""
    if not isinstance(measure, dict):
        return False
    required_scope = required_throughput_scope(measure)
    azimuth_results = measure.get("azimuth_results")
    return bool(
        required_scope is not None
        and measure.get("throughput_scope") == required_scope
        and isinstance(azimuth_results, list)
        and azimuth_results
        and all(
            isinstance(row, dict)
            and row.get("throughput_valid") is True
            and row.get("throughput_scope") == required_scope
            for row in azimuth_results
        )
    )
