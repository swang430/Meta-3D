"""P1-63：正式 RF KPI 必须有逐指标、逐方位真实来源证据。"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.hal.base_station import ThroughputMetrics
from app.api.test_execution import _formal_validation_pass
from app.services.mimo_ota.executors.analysis import AnalysisExecutor
from app.services.mimo_ota.executors.measure import MeasureExecutor
from app.services.test_execution import StepExecutionStatus


def _verified_path_loss_application() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "applied",
        "provenance": "real",
        "reason": "selected",
        "gate_mode": "strict",
        "certificate_id": "p1-63-real-cert",
        "value_disclosure": "verified",
    }


def _complete_rf_trust() -> dict[str, object]:
    from app.services.mimo_ota.rf_kpi_trust import build_rf_kpi_trust

    return build_rf_kpi_trust(
        requested_azimuths=[0.0],
        azimuth_results=[{
            "azimuth_deg": 0.0,
            "rsrp_valid": True,
            "sinr_valid": True,
            "rank_indicator_valid": True,
        }],
        source="explicit_real",
    )


def _formal_measure(*, rf_trust: object = None) -> dict[str, object]:
    measure: dict[str, object] = {
        "measurement_verified": True,
        "frequency_consistency": {"fully_verified": True},
        "path_loss_application": _verified_path_loss_application(),
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [{
            "azimuth_deg": 0.0,
            "throughput_mbps": 350.0,
            "throughput_valid": True,
            "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
            "rsrp_dbm": -80.0,
            "rsrp_valid": True,
            "sinr_db": 30.0,
            "sinr_valid": True,
            "rank_indicator": 2.0,
            "rank_indicator_valid": True,
        }],
    }
    if rf_trust is not None:
        measure["rf_kpi_trust"] = rf_trust
        measure["formal_rf_kpi_verified"] = True
    return measure


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


@pytest.mark.asyncio
async def test_analysis_stays_unknown_without_complete_rf_kpi_trust(monkeypatch):
    from app.services.mimo_ota.executors import analysis as analysis_module

    measure = _formal_measure()
    config = SimpleNamespace(
        theoretical_peak_throughput_mbps=450.0,
        pass_criteria=SimpleNamespace(
            min_throughput_ratio=0.5,
            min_throughput_mbps=300.0,
            max_rsrp_variance_db=8.0,
            min_sinr_db=10.0,
            min_avg_rank_indicator=1.5,
        ),
    )
    execution = SimpleNamespace(
        validation_pass=True,
        validation_details=None,
        id="p1-63-analysis",
    )
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )
    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _e: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _e, phase: measure if phase == "measure" else {"quiet_zone_pass": True},
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_args: None)

    result = await AnalysisExecutor().execute(context)

    assert result.status == StepExecutionStatus.SUCCESS
    assert result.measurements["verdict"] == "UNKNOWN"
    assert result.measurements["rsrp_variance_db"] is None
    assert result.measurements["avg_sinr_db"] is None
    assert result.measurements["avg_rank_indicator"] is None
    assert execution.validation_pass is None
    assert "RF KPI" in " ".join(result.warnings)


@pytest.mark.asyncio
async def test_analysis_keeps_verdict_with_complete_rf_kpi_trust(monkeypatch):
    from app.services.mimo_ota.executors import analysis as analysis_module

    measure = _formal_measure(rf_trust=_complete_rf_trust())
    config = SimpleNamespace(
        theoretical_peak_throughput_mbps=450.0,
        pass_criteria=SimpleNamespace(
            min_throughput_ratio=0.5,
            min_throughput_mbps=300.0,
            max_rsrp_variance_db=8.0,
            min_sinr_db=10.0,
            min_avg_rank_indicator=1.5,
        ),
    )
    execution = SimpleNamespace(
        validation_pass=None,
        validation_details=None,
        id="p1-63-analysis-real",
    )
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )
    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _e: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _e, phase: measure if phase == "measure" else {"quiet_zone_pass": True},
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_args: None)

    result = await AnalysisExecutor().execute(context)

    assert result.measurements["verdict"] == "PASS"
    assert execution.validation_pass is True


def test_execution_history_requires_complete_rf_kpi_trust():
    without_trust = SimpleNamespace(
        measurements={"phases": {"measure": _formal_measure()}},
        validation_pass=True,
        config={},
    )
    with_trust = SimpleNamespace(
        measurements={
            "phases": {
                "measure": _formal_measure(rf_trust=_complete_rf_trust()),
            }
        },
        validation_pass=True,
        config={},
    )

    assert _formal_validation_pass(without_trust, "MIMO_OTA") is None
    assert _formal_validation_pass(with_trust, "MIMO_OTA") is True
