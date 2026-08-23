"""P1-64: 静区代理量不能冒充正式多点场扫描证据。"""

import math
from datetime import datetime, timezone
from types import SimpleNamespace

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


def _trusted_measure_for_analysis() -> dict[str, object]:
    from app.hal.base_station import ThroughputMetrics
    from app.services.mimo_ota.rf_kpi_trust import build_rf_kpi_trust

    rows = [{
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
    }]
    return {
        "measurement_verified": True,
        "measurement_source": "instrument",
        "simulated_sources": [],
        "frequency_consistency": {"fully_verified": True},
        "path_loss_application": {
            "schema_version": 1,
            "status": "applied",
            "provenance": "real",
            "reason": "selected",
            "gate_mode": "strict",
            "certificate_id": "p1-64-real-cert",
            "value_disclosure": "verified",
        },
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": rows,
        "rf_kpi_trust": build_rf_kpi_trust(
            requested_azimuths=[0.0],
            azimuth_results=rows,
            source="explicit_real",
        ),
        "formal_rf_kpi_verified": True,
    }


@pytest.mark.asyncio
async def test_analysis_rejects_legacy_quiet_zone_pass(monkeypatch):
    from app.services.mimo_ota.executors import analysis as analysis_module
    from app.services.mimo_ota.executors.analysis import AnalysisExecutor
    from app.services.test_execution import StepExecutionStatus

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
        id="p1-64-analysis",
    )
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )
    legacy_precheck = {
        "quiet_zone_pass": True,
        "quiet_zone_verified": True,
        "quiet_zone_ripple_source": "probe_pattern_peak_spread",
    }
    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _e: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _e, phase: (
            _trusted_measure_for_analysis() if phase == "measure" else legacy_precheck
        ),
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_args: None)

    result = await AnalysisExecutor().execute(context)

    assert result.status == StepExecutionStatus.SUCCESS
    assert result.measurements["verdict"] == "UNKNOWN"
    assert result.measurements["qz_pass"] is None
    assert execution.validation_pass is None


def _trusted_report_envelope() -> dict[str, object]:
    measure = _trusted_measure_for_analysis()
    return {
        "calibration_trust_schema_version": 1,
        "throughput_trust_schema_version": 2,
        "path_loss_application": measure["path_loss_application"],
        "formal_path_loss_verified": True,
        "rf_kpi_trust_schema_version": 1,
        "rf_kpi_trust": measure["rf_kpi_trust"],
        "formal_rf_kpi_verified": True,
    }


def test_report_trust_requires_canonical_quiet_zone_attestation():
    from app.services.mimo_ota.quiet_zone_evidence import build_quiet_zone_evidence
    from app.services.report_service import report_has_provenance_trust

    old_envelope = _trusted_report_envelope()
    new_envelope = {
        **old_envelope,
        "quiet_zone_evidence_schema_version": 1,
        "quiet_zone_evidence": build_quiet_zone_evidence(None),
        "formal_quiet_zone_verified": False,
    }

    assert report_has_provenance_trust(old_envelope) is False
    assert report_has_provenance_trust(new_envelope) is True


def test_client_cannot_self_attest_quiet_zone_trust():
    from app.services.mimo_ota.quiet_zone_evidence import build_quiet_zone_evidence
    from app.services.report_service import _strip_untrusted_report_attestation

    forged = {
        "title": "client payload",
        "quiet_zone_evidence_schema_version": 1,
        "quiet_zone_evidence": build_quiet_zone_evidence(None),
        "formal_quiet_zone_verified": False,
    }

    assert _strip_untrusted_report_attestation(forged) == {"title": "client payload"}


def test_execution_history_rejects_legacy_quiet_zone_pass():
    from app.api.test_execution import _formal_validation_pass

    execution = SimpleNamespace(
        measurements={
            "phases": {
                "precheck": {
                    "overall_pass": True,
                    "quiet_zone_pass": True,
                    "quiet_zone_verified": True,
                    "quiet_zone_ripple_db": 0.7,
                    "quiet_zone_ripple_source": "probe_pattern_peak_spread",
                },
                "measure": _trusted_measure_for_analysis(),
            }
        },
        validation_pass=True,
        config={},
    )

    assert _formal_validation_pass(execution, "MIMO_OTA") is None


def test_commissioning_precheck_status_rejects_legacy_quiet_zone_failure():
    from app.api.commissioning import _phase_status_from_payload

    legacy_precheck = {
        "overall_pass": False,
        "quiet_zone_pass": False,
        "quiet_zone_ripple_db": 1.2,
    }

    assert _phase_status_from_payload(
        legacy_precheck,
        require_operational_truth=True,
    ) == "completed"


def test_commissioning_precheck_status_preserves_current_operational_failure():
    from app.api.commissioning import _phase_status_from_payload

    current_failure = {
        "overall_pass": False,
        "operational_ready": False,
        "error_message": "DUT 门未通过",
    }

    assert _phase_status_from_payload(
        current_failure,
        require_operational_truth=True,
    ) == "failed"


def test_report_rebuild_does_not_repeat_legacy_quiet_zone_pass_claims():
    from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data

    execution = SimpleNamespace(
        measurements={
            "phases": {
                "precheck": {
                    "overall_pass": True,
                    "quiet_zone_pass": True,
                    "quiet_zone_verified": True,
                    "quiet_zone_ripple_db": 0.7,
                    "quiet_zone_ripple_source": "probe_pattern_peak_spread",
                    "messages": [
                        "Quiet zone ripple: 0.70 dB (PASS) "
                        "[probe_pattern_peak_spread]"
                    ],
                },
                "measure": _trusted_measure_for_analysis(),
                "analysis": {"verdict": "PASS"},
            }
        },
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        validation_pass=True,
    )

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 8, 23, tzinfo=timezone.utc),
    )
    precheck = next(
        step for step in content["step_results"] if step["phase"] == "precheck"
    )["parameters"]

    assert precheck["结果"] == "UNKNOWN"
    assert all("0.70" not in message for message in precheck["提示"])
    assert all("(PASS)" not in message for message in precheck["提示"])
