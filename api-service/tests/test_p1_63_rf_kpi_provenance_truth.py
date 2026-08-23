"""P1-63：正式 RF KPI 必须有逐指标、逐方位真实来源证据。"""

from __future__ import annotations

import inspect

import pytest

from app.hal.base_station import ThroughputMetrics
from app.services.mimo_ota.executors.measure import MeasureExecutor


def test_measure_no_longer_synthesizes_formal_rsrp_or_sinr():
    source = inspect.getsource(MeasureExecutor.execute)

    assert "random.gauss" not in source
    assert "self._trusted_rf_kpi_value(" in source
    assert "metrics.rank_indicator" not in source


@pytest.mark.parametrize(
    "key,attribute,value,valid,expected",
    [
        ("rsrp_dbm", "rsrp_dbm", -82.5, True, -82.5),
        ("sinr_db", "sinr_db", 0.0, True, 0.0),
        ("rank_indicator", "rank_indicator", 2, True, 2.0),
        ("rsrp_dbm", "rsrp_dbm", -82.5, False, None),
        ("sinr_db", "sinr_db", float("nan"), True, None),
        ("rank_indicator", "rank_indicator", float("inf"), True, None),
    ],
)
def test_rf_sample_gate_requires_explicit_valid_finite_value(
    key: str,
    attribute: str,
    value: float,
    valid: bool,
    expected: float | None,
):
    metrics = ThroughputMetrics(kpi_valid={key: valid})
    setattr(metrics, attribute, value)

    assert MeasureExecutor._trusted_rf_kpi_value(  # type: ignore[attr-defined]
        metrics,
        key=key,
        attribute=attribute,
    ) == expected


def test_rf_kpi_trust_requires_every_metric_at_every_requested_azimuth():
    from app.services.mimo_ota.rf_kpi_trust import (
        build_rf_kpi_trust,
        rf_kpi_scope_is_verified,
    )

    complete_rows = [
        {
            "azimuth_deg": 0.0,
            "rsrp_valid": True,
            "sinr_valid": True,
            "rank_indicator_valid": True,
        },
        {
            "azimuth_deg": 90.0,
            "rsrp_valid": True,
            "sinr_valid": True,
            "rank_indicator_valid": True,
        },
    ]
    complete = build_rf_kpi_trust(
        requested_azimuths=[0.0, 90.0],
        azimuth_results=complete_rows,
        source="explicit_real",
    )
    partial = build_rf_kpi_trust(
        requested_azimuths=[0.0, 90.0],
        azimuth_results=[complete_rows[0]],
        source="explicit_real",
    )
    simulated = build_rf_kpi_trust(
        requested_azimuths=[0.0, 90.0],
        azimuth_results=complete_rows,
        source="simulated",
    )

    assert rf_kpi_scope_is_verified(
        {"rf_kpi_trust": complete, "formal_rf_kpi_verified": True}
    ) is True
    assert rf_kpi_scope_is_verified(
        {"rf_kpi_trust": partial, "formal_rf_kpi_verified": False}
    ) is False
    assert rf_kpi_scope_is_verified(
        {"rf_kpi_trust": simulated, "formal_rf_kpi_verified": False}
    ) is False


def test_rf_kpi_trust_rejects_malformed_or_self_inconsistent_payloads():
    from app.services.mimo_ota.rf_kpi_trust import (
        build_rf_kpi_trust,
        parse_rf_kpi_trust,
        rf_kpi_scope_is_verified,
    )

    trust = build_rf_kpi_trust(
        requested_azimuths=[0.0],
        azimuth_results=[{
            "azimuth_deg": 0.0,
            "rsrp_valid": True,
            "sinr_valid": True,
            "rank_indicator_valid": True,
        }],
        source="explicit_real",
    )

    assert parse_rf_kpi_trust(trust) == trust
    assert parse_rf_kpi_trust({**trust, "extra": "forged"}) is None
    assert rf_kpi_scope_is_verified(
        {"rf_kpi_trust": trust, "formal_rf_kpi_verified": False}
    ) is False
    assert rf_kpi_scope_is_verified({"formal_rf_kpi_verified": True}) is False
