"""Formal RSRP/SINR/RI provenance shared by every MIMO verdict consumer."""

from __future__ import annotations

import math
from typing import Any


RF_KPI_TRUST_SCHEMA_VERSION = 1
RF_KPI_TRUST_FIELD = "rf_kpi_trust"
RF_KPI_METRICS = (
    ("rsrp_dbm", "rsrp_valid"),
    ("sinr_db", "sinr_valid"),
    ("rank_indicator", "rank_indicator_valid"),
)
RF_KPI_SOURCES = frozenset({"explicit_real", "simulated", "unknown"})


def _finite_azimuths(value: Any) -> list[float] | None:
    if not isinstance(value, list):
        return None
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        number = float(item)
        if not math.isfinite(number) or number in result:
            return None
        result.append(number)
    return result


def _row_has_finite_metric(row: dict[str, Any], metric: str) -> bool:
    value = row.get(metric)
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def build_rf_kpi_trust(
    *,
    requested_azimuths: list[float],
    azimuth_results: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    """Build the server-owned per-metric coverage snapshot."""
    requested = _finite_azimuths(list(requested_azimuths)) or []
    safe_source = source if source in RF_KPI_SOURCES else "unknown"
    rows_by_azimuth: dict[float, dict[str, Any]] = {}
    duplicate_azimuths: set[float] = set()
    for row in azimuth_results if isinstance(azimuth_results, list) else []:
        if not isinstance(row, dict):
            continue
        raw_azimuth = row.get("azimuth_deg")
        if (
            isinstance(raw_azimuth, bool)
            or not isinstance(raw_azimuth, (int, float))
            or not math.isfinite(float(raw_azimuth))
        ):
            continue
        azimuth = float(raw_azimuth)
        if azimuth in rows_by_azimuth:
            duplicate_azimuths.add(azimuth)
        rows_by_azimuth[azimuth] = row

    metric_payload: dict[str, dict[str, Any]] = {}
    for metric, validity_field in RF_KPI_METRICS:
        verified_azimuths = (
            [
                azimuth
                for azimuth in requested
                if azimuth not in duplicate_azimuths
                and isinstance(rows_by_azimuth.get(azimuth), dict)
                and rows_by_azimuth[azimuth].get(validity_field) is True
                and _row_has_finite_metric(rows_by_azimuth[azimuth], metric)
            ]
            if safe_source == "explicit_real"
            else []
        )
        metric_payload[metric] = {
            "verified": bool(requested) and verified_azimuths == requested,
            "verified_azimuths": verified_azimuths,
        }

    verified_azimuths = [
        azimuth
        for azimuth in requested
        if all(
            azimuth in metric_payload[metric]["verified_azimuths"]
            for metric, _ in RF_KPI_METRICS
        )
    ]
    return {
        "schema_version": RF_KPI_TRUST_SCHEMA_VERSION,
        "source": safe_source,
        "requested_azimuths": requested,
        "verified_azimuths": verified_azimuths,
        "metrics": metric_payload,
    }


def parse_rf_kpi_trust(value: Any) -> dict[str, Any] | None:
    """Return a normalized exact-schema snapshot, otherwise ``None``."""
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "source",
        "requested_azimuths",
        "verified_azimuths",
        "metrics",
    }:
        return None
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != RF_KPI_TRUST_SCHEMA_VERSION
        or value.get("source") not in RF_KPI_SOURCES
    ):
        return None
    requested = _finite_azimuths(value.get("requested_azimuths"))
    verified = _finite_azimuths(value.get("verified_azimuths"))
    if requested is None:
        return None
    if verified is None and value.get("verified_azimuths") != []:
        return None
    verified = verified or []
    if any(azimuth not in requested for azimuth in verified):
        return None

    metrics = value.get("metrics")
    metric_names = {metric for metric, _ in RF_KPI_METRICS}
    if not isinstance(metrics, dict) or set(metrics) != metric_names:
        return None
    normalized_metrics: dict[str, dict[str, Any]] = {}
    for metric, _ in RF_KPI_METRICS:
        payload = metrics.get(metric)
        if not isinstance(payload, dict) or set(payload) != {
            "verified",
            "verified_azimuths",
        }:
            return None
        if type(payload.get("verified")) is not bool:
            return None
        metric_azimuths = _finite_azimuths(payload.get("verified_azimuths"))
        if metric_azimuths is None and payload.get("verified_azimuths") != []:
            return None
        metric_azimuths = metric_azimuths or []
        if any(azimuth not in requested for azimuth in metric_azimuths):
            return None
        expected_verified = bool(requested) and metric_azimuths == requested
        if payload["verified"] is not expected_verified:
            return None
        normalized_metrics[metric] = {
            "verified": expected_verified,
            "verified_azimuths": metric_azimuths,
        }

    expected_intersection = [
        azimuth
        for azimuth in requested
        if all(
            azimuth in normalized_metrics[metric]["verified_azimuths"]
            for metric, _ in RF_KPI_METRICS
        )
    ]
    if verified != expected_intersection:
        return None
    if value["source"] != "explicit_real" and (
        verified
        or any(
            payload["verified_azimuths"]
            for payload in normalized_metrics.values()
        )
    ):
        return None
    return {
        "schema_version": RF_KPI_TRUST_SCHEMA_VERSION,
        "source": value["source"],
        "requested_azimuths": requested,
        "verified_azimuths": verified,
        "metrics": normalized_metrics,
    }


def rf_kpi_trust_is_formally_verified(value: Any) -> bool:
    parsed = parse_rf_kpi_trust(value)
    return bool(
        parsed
        and parsed["source"] == "explicit_real"
        and parsed["verified_azimuths"] == parsed["requested_azimuths"]
        and all(
            parsed["metrics"][metric]["verified"] is True
            for metric, _ in RF_KPI_METRICS
        )
    )


def rf_kpi_scope_is_verified(measure: Any) -> bool:
    """Require the snapshot, server boolean and current rows to agree."""
    if not isinstance(measure, dict):
        return False
    raw_trust = measure.get(RF_KPI_TRUST_FIELD)
    parsed = parse_rf_kpi_trust(raw_trust)
    formal = measure.get("formal_rf_kpi_verified")
    expected = rf_kpi_trust_is_formally_verified(raw_trust)
    rows = measure.get("azimuth_results")
    current_azimuths = (
        _finite_azimuths([row.get("azimuth_deg") for row in rows])
        if isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
        else None
    )
    rows_match_requested = bool(
        parsed is not None
        and current_azimuths is not None
        and len(current_azimuths) == len(parsed["requested_azimuths"])
        and set(current_azimuths) == set(parsed["requested_azimuths"])
    )
    current_source = (
        "explicit_real"
        if (
            measure.get("measurement_source") == "instrument"
            and measure.get("measurement_verified") is True
            and measure.get("simulated_sources") == []
            and isinstance(rows, list)
            and all(
                isinstance(row, dict)
                and row.get("measurement_source") == "instrument"
                and row.get("measurement_verified") is True
                for row in rows
            )
        )
        else "unknown"
    )
    rebuilt = (
        build_rf_kpi_trust(
            requested_azimuths=parsed["requested_azimuths"],
            azimuth_results=rows,
            source=current_source,
        )
        if parsed is not None and isinstance(rows, list)
        else None
    )
    return bool(
        parsed is not None
        and parsed == raw_trust
        and rows_match_requested
        and rebuilt == parsed
        and type(formal) is bool
        and formal is expected
        and expected
    )
