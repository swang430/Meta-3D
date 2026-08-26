"""P1-63：正式 RF KPI 必须有逐指标、逐方位真实来源证据。"""

from __future__ import annotations

import inspect
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.hal.base_station import ThroughputMetrics
from app.api.test_execution import _formal_validation_pass
from app.services.mimo_ota.executors.analysis import AnalysisExecutor
from app.services.mimo_ota.executors.measure import MeasureExecutor
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.report_service import (
    _strip_untrusted_report_attestation,
    report_has_provenance_trust,
)
from app.services.test_execution import StepExecutionStatus
from app.services.mimo_ota.rf_kpi_trust import rf_kpi_scope_is_verified
from app.services.mimo_ota.quiet_zone_evidence import build_quiet_zone_evidence


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
            "rsrp_dbm": -80.0,
            "rsrp_valid": True,
            "sinr_db": 30.0,
            "sinr_valid": True,
            "rank_indicator": 2.0,
            "rank_indicator_valid": True,
        }],
        source="explicit_real",
    )


def _formal_measure(*, rf_trust: object = None) -> dict[str, object]:
    measure: dict[str, object] = {
        "measurement_verified": True,
        "measurement_source": "instrument",
        "simulated_sources": [],
        "frequency_consistency": {"fully_verified": True},
        "path_loss_application": _verified_path_loss_application(),
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [{
            "azimuth_deg": 0.0,
            "measurement_source": "instrument",
            "measurement_verified": True,
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
            "measurement_source": "instrument",
            "measurement_verified": True,
            "rsrp_dbm": -80.0,
            "rsrp_valid": True,
            "sinr_db": 30.0,
            "sinr_valid": True,
            "rank_indicator": 2.0,
            "rank_indicator_valid": True,
        },
        {
            "azimuth_deg": 90.0,
            "measurement_source": "instrument",
            "measurement_verified": True,
            "rsrp_dbm": -81.0,
            "rsrp_valid": True,
            "sinr_db": 29.0,
            "sinr_valid": True,
            "rank_indicator": 2.0,
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
        {
            "rf_kpi_trust": complete,
            "formal_rf_kpi_verified": True,
            "measurement_source": "instrument",
            "measurement_verified": True,
            "simulated_sources": [],
            "azimuth_results": complete_rows,
        }
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
            "rsrp_dbm": -80.0,
            "rsrp_valid": True,
            "sinr_db": 30.0,
            "sinr_valid": True,
            "rank_indicator": 2.0,
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("rsrp_dbm", float("nan")),
        ("rsrp_dbm", float("inf")),
        ("rsrp_dbm", True),
        ("rsrp_dbm", None),
        ("azimuth_deg", 90.0),
    ],
)
def test_rf_kpi_scope_rejects_invalid_or_snapshot_mismatched_rows(
    field: str,
    value: object,
):
    measure = _formal_measure(rf_trust=_complete_rf_trust())
    row = measure["azimuth_results"][0]
    if value is None:
        row.pop(field)
    else:
        row[field] = value

    assert rf_kpi_scope_is_verified(measure) is False


def test_rf_kpi_scope_rejects_unrequested_extra_rows():
    measure = _formal_measure(rf_trust=_complete_rf_trust())
    measure["azimuth_results"].append({
        "azimuth_deg": 90.0,
        "measurement_source": "instrument",
        "measurement_verified": True,
        "throughput_mbps": 999.0,
        "throughput_valid": True,
        "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
        "rsrp_dbm": 999.0,
        "rsrp_valid": True,
        "sinr_db": 999.0,
        "sinr_valid": True,
        "rank_indicator": 99.0,
        "rank_indicator_valid": True,
    })

    assert rf_kpi_scope_is_verified(measure) is False


def test_rf_kpi_scope_rejects_current_simulated_provenance():
    measure = _formal_measure(rf_trust=_complete_rf_trust())
    measure["measurement_source"] = "simulated"
    measure["measurement_verified"] = False
    measure["simulated_sources"] = ["baseStation"]
    measure["azimuth_results"][0]["measurement_source"] = "simulated"
    measure["azimuth_results"][0]["measurement_verified"] = False

    execution = SimpleNamespace(
        measurements={"phases": {"measure": measure}},
        validation_pass=True,
        config={},
    )

    assert rf_kpi_scope_is_verified(measure) is False
    assert _formal_validation_pass(execution, "MIMO_OTA") is None


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

    assert result.measurements["verdict"] == "UNKNOWN"
    assert execution.validation_pass is None


def test_execution_history_requires_complete_rf_kpi_trust(monkeypatch):
    # Isolate the RF contract under test from P1-64's independent QZ gate.
    monkeypatch.setattr(
        "app.api.test_execution.quiet_zone_scope_is_formally_verified",
        lambda _precheck: True,
    )
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


def _report_execution(*, include_rf_trust: bool) -> SimpleNamespace:
    measure = _formal_measure(
        rf_trust=_complete_rf_trust() if include_rf_trust else None
    )
    return SimpleNamespace(
        id="p1-63-report",
        measurements={
            "phases": {
                "measure": measure,
                "analysis": {"verdict": "PASS"},
            }
        },
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 8, 23),
        completed_at=datetime(2026, 8, 23),
        validation_pass=True,
    )


def _pre_p1_63_report_envelope() -> dict[str, object]:
    return {
        "calibration_trust_schema_version": 1,
        "throughput_trust_schema_version": 2,
        "path_loss_application": _verified_path_loss_application(),
        "formal_path_loss_verified": True,
    }


def test_report_masks_rf_kpis_without_complete_trust_snapshot():
    content = _build_mimo_ota_content_data(
        _report_execution(include_rf_trust=False),
        datetime(2026, 8, 23),
    )

    assert content["formal_rf_kpi_verified"] is False
    assert content["overall_result"] == "undetermined"
    assert content["pass_rate"] is None
    assert content["statistics"]["Throughput_Mbps"]["mean"] == 350.0
    assert content["table_data"][0]["RSRP (dBm)"] == "N/A"
    assert content["table_data"][0]["SINR (dB)"] == "N/A"
    assert content["table_data"][0]["Throughput (Mbps)"] == "350.0"
    assert content["table_data"][0]["RI"] == "N/A"


def test_report_safely_masks_malformed_legacy_rf_values_before_statistics():
    execution = _report_execution(include_rf_trust=False)
    execution.measurements["phases"]["measure"]["azimuth_results"][0][
        "rsrp_dbm"
    ] = "bad"

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 23),
    )

    assert content["overall_result"] == "undetermined"
    assert content["pass_rate"] is None
    assert content["statistics"]["Throughput_Mbps"]["mean"] == 350.0
    assert content["table_data"][0]["RSRP (dBm)"] == "N/A"


def test_report_safely_omits_non_object_legacy_rows():
    execution = _report_execution(include_rf_trust=False)
    execution.measurements["phases"]["measure"]["azimuth_results"] = ["bad-row"]

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 23),
    )

    assert content["overall_result"] == "undetermined"
    assert content["pass_rate"] is None
    assert content["statistics"] == {}
    assert content["table_data"] == []


def test_report_rewrites_mismatched_rf_snapshot_to_safe_unknown_envelope():
    execution = _report_execution(include_rf_trust=True)
    execution.measurements["phases"]["measure"]["azimuth_results"][0][
        "azimuth_deg"
    ] = 90.0

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 23),
    )

    assert content["formal_rf_kpi_verified"] is False
    assert content["rf_kpi_trust"]["source"] == "unknown"
    assert content["rf_kpi_trust"]["verified_azimuths"] == []
    assert content["overall_result"] == "undetermined"
    assert report_has_provenance_trust(content) is True


def test_report_hides_throughput_when_current_measurement_is_simulated():
    execution = _report_execution(include_rf_trust=True)
    measure = execution.measurements["phases"]["measure"]
    measure["measurement_source"] = "simulated"
    measure["measurement_verified"] = False
    measure["simulated_sources"] = ["baseStation"]
    measure["azimuth_results"][0]["measurement_source"] = "simulated"
    measure["azimuth_results"][0]["measurement_verified"] = False

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 23),
    )

    assert content["formal_rf_kpi_verified"] is False
    assert content["formal_throughput_verified"] is False
    assert "Throughput_Mbps" not in content["statistics"]
    assert content["table_data"][0]["Throughput (Mbps)"] == "N/A"
    assert content["overall_result"] == "undetermined"


def test_report_keeps_rf_kpis_with_complete_trust_snapshot():
    content = _build_mimo_ota_content_data(
        _report_execution(include_rf_trust=True),
        datetime(2026, 8, 23),
    )

    assert content["rf_kpi_trust_schema_version"] == 1
    assert content["rf_kpi_trust"] == _complete_rf_trust()
    assert content["formal_rf_kpi_verified"] is True
    assert content["overall_result"] == "undetermined"
    assert content["table_data"][0]["RSRP (dBm)"] == "-80.0"


def test_pre_p1_63_report_cannot_bypass_new_trust_envelope():
    old_envelope = _pre_p1_63_report_envelope()
    new_envelope = {
        **old_envelope,
        "rf_kpi_trust_schema_version": 1,
        "rf_kpi_trust": _complete_rf_trust(),
        "formal_rf_kpi_verified": True,
        "quiet_zone_evidence_schema_version": 1,
        "quiet_zone_evidence": build_quiet_zone_evidence(None),
        "formal_quiet_zone_verified": False,
        "base_station_metric_trust_schema_version": 1,
        "base_station_metric_projection": [],
    }

    assert report_has_provenance_trust(old_envelope) is False
    assert report_has_provenance_trust(new_envelope) is True


def test_client_cannot_self_attest_rf_kpi_trust():
    forged = {
        "title": "client payload",
        "rf_kpi_trust_schema_version": 1,
        "rf_kpi_trust": _complete_rf_trust(),
        "formal_rf_kpi_verified": True,
    }

    sanitized = _strip_untrusted_report_attestation(forged)

    assert sanitized == {"title": "client payload"}
