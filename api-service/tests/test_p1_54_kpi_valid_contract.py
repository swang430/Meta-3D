"""P1-54：吞吐 KPI 有效性必须随正式数据契约传播。"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.hal.base_station import ThroughputMetrics
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.mimo_ota.executors.analysis import AnalysisExecutor
from app.services.mimo_ota.executors.measure import MeasureExecutor
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.mimo_ota.rf_kpi_trust import build_rf_kpi_trust
from app.services.mimo_ota.quiet_zone_evidence import build_quiet_zone_evidence
from app.services.report_service import report_has_provenance_trust
from app.services.test_execution import StepExecutionStatus


def _stub_uxm(driver: RealUxmDriver, responses: dict[str, str]) -> None:
    def _query(command: str, **_kwargs):
        return next(
            (response for fragment, response in responses.items() if fragment in command),
            "",
        )

    driver._do_query = _query  # type: ignore[method-assign]
    driver._do_write = lambda *_args, **_kwargs: None  # type: ignore[method-assign]


def _stub_cmw(driver: RealCmw500Driver, responses: dict[str, str]) -> None:
    driver._query = lambda command: next(  # type: ignore[method-assign]
        (response for fragment, response in responses.items() if fragment in command),
        "",
    )


def _verified_path_loss_application() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "applied",
        "provenance": "real",
        "reason": "selected",
        "gate_mode": "strict",
        "certificate_id": "p1-54-real-cert",
        "value_disclosure": "verified",
    }


def test_throughput_contract_distinguishes_missing_from_real_zero():
    missing = ThroughputMetrics()
    missing_payload = missing.to_dict()

    assert missing.dl_throughput_mbps is None
    assert missing.dl_throughput_current_mbps is None
    assert missing.dl_bler is None
    assert missing_payload["dl_throughput_mbps"] is None
    assert missing_payload["kpi_valid"]["dl_throughput"] is False
    assert missing_payload["kpi_valid"]["dl_throughput_current"] is False
    assert missing_payload["kpi_valid"]["dl_bler"] is False

    measured_zero = ThroughputMetrics(
        dl_throughput_mbps=0.0,
        dl_throughput_current_mbps=0.0,
    )
    measured_payload = measured_zero.to_dict()

    assert measured_payload["dl_throughput_mbps"] == 0.0
    assert measured_payload["kpi_valid"]["dl_throughput"] is True
    assert measured_payload["kpi_valid"]["dl_throughput_current"] is True


def test_uxm_nan_is_missing_but_real_zero_is_valid():
    driver = RealUxmDriver("uxm-p1-54", {"ip": "10.0.0.2", "uxm_profile": "irat"})
    _stub_uxm(
        driver,
        {
            "DL:THRoughput:OTA": "0,9.91E+37,9.91E+37,9.91E+37,9.91E+37,0",
            "UL:THRoughput:OTA": "0,0,0,0,0,0",
        },
    )

    metrics = asyncio.run(driver.get_throughput_metrics())
    payload = metrics.to_dict()

    assert metrics.dl_throughput_mbps is None
    assert metrics.dl_throughput_current_mbps is None
    assert payload["kpi_valid"]["dl_throughput"] is False
    assert payload["kpi_valid"]["dl_throughput_current"] is False
    assert metrics.ul_throughput_mbps == 0.0
    assert payload["kpi_valid"]["ul_throughput"] is True
    assert payload["kpi_valid"]["ul_throughput_current"] is True


@pytest.mark.parametrize(
    "response",
    [
        "",
        "CURRENT,BAD,MAX",
        "CURRENT,nan,MAX",
        "CURRENT,inf,MAX",
        "CURRENT,0,MAX",
        "CURRENT,125000,MAX",
    ],
)
def test_cmw500_throughput_stays_unverified_without_a_sourced_response_contract(
    response: str,
):
    driver = RealCmw500Driver("cmw-p1-54", {"ip": "10.0.0.3"})
    _stub_cmw(
        driver,
        {
            "ETHRoughput:DL:PCC?": response,
            "ETHRoughput:UL:PCC?": response,
        },
    )

    metrics = asyncio.run(driver.get_throughput_metrics())
    payload = metrics.to_dict()

    assert metrics.dl_throughput_mbps is None
    assert metrics.dl_throughput_current_mbps is None
    assert metrics.ul_throughput_mbps is None
    assert metrics.ul_throughput_current_mbps is None
    assert payload["kpi_valid"]["dl_throughput"] is False
    assert payload["kpi_valid"]["dl_throughput_current"] is False
    assert payload["kpi_valid"]["ul_throughput"] is False
    assert payload["kpi_valid"]["ul_throughput_current"] is False


def test_measure_sample_gate_accepts_real_zero_and_rejects_invalid_default():
    invalid_zero = ThroughputMetrics(
        dl_throughput_mbps=0.0,
        kpi_valid={"dl_throughput": False},
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
    )
    real_zero = ThroughputMetrics(
        dl_throughput_mbps=0.0,
        kpi_valid={"dl_throughput": True},
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
    )
    non_finite = ThroughputMetrics(
        dl_throughput_mbps=float("nan"),
        kpi_valid={"dl_throughput": True},
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
    )

    assert MeasureExecutor._trusted_throughput_value(invalid_zero) is None
    assert MeasureExecutor._trusted_throughput_value(real_zero) == 0.0
    assert MeasureExecutor._trusted_throughput_value(non_finite) is None


def test_measure_executor_routes_samples_through_trust_gate():
    """生产采样与 phase 判据都必须经过各自的可信门。"""
    source = inspect.getsource(MeasureExecutor.execute)

    assert "self._trusted_throughput_value(" in source
    assert "required_scope=throughput_scope" in source
    assert "samples_tput.append(metrics.dl_throughput_mbps)" not in source
    assert "self._all_requested_throughput_is_valid(" in source
    assert "config.azimuths_deg" in source


def test_measure_phase_requires_every_requested_azimuth_to_have_trusted_throughput():
    completed = [{"azimuth_deg": 0.0, "throughput_valid": True}]

    assert MeasureExecutor._all_requested_throughput_is_valid(
        [0.0, 90.0, 180.0, 270.0],
        completed,
    ) is False
    assert MeasureExecutor._all_requested_throughput_is_valid(
        [0.0],
        completed,
    ) is True
    assert MeasureExecutor._all_requested_throughput_is_valid([], []) is False


@pytest.mark.parametrize("throughput_verified", [False, None])
@pytest.mark.asyncio
async def test_analysis_stays_unknown_without_explicit_trusted_throughput(
    monkeypatch,
    throughput_verified: bool | None,
):
    from app.services.mimo_ota.executors import analysis as analysis_module

    measure = {
        "measurement_verified": True,
        "measurement_source": "instrument",
        "simulated_sources": [],
        "frequency_consistency": {"fully_verified": True},
        "path_loss_application": _verified_path_loss_application(),
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "azimuth_results": [
            {
                "azimuth_deg": 0.0,
                "measurement_source": "instrument",
                "measurement_verified": True,
                "throughput_mbps": 0.0,
                "rsrp_dbm": -80.0,
                "sinr_db": 30.0,
                "rank_indicator": 2.0,
            }
        ],
    }
    measure["rf_kpi_trust"] = build_rf_kpi_trust(
        requested_azimuths=[0.0],
        azimuth_results=[{
            "azimuth_deg": 0.0,
            "rsrp_valid": True,
            "sinr_valid": True,
            "rank_indicator_valid": True,
        }],
        source="explicit_real",
    )
    measure["formal_rf_kpi_verified"] = True
    if throughput_verified is not None:
        measure["throughput_verified"] = throughput_verified

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
    written: dict[str, object] = {}
    execution = SimpleNamespace(validation_pass=True, validation_details=None, id="p1-54")
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )

    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _execution: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _execution, phase: measure if phase == "measure" else {"quiet_zone_pass": True},
    )
    monkeypatch.setattr(
        analysis_module,
        "write_phase_result",
        lambda _execution, phase, result: written.update({phase: result}),
    )

    result = await AnalysisExecutor().execute(context)

    assert result.status == StepExecutionStatus.SUCCESS
    assert result.measurements["verdict"] == "UNKNOWN"
    assert result.measurements["avg_throughput_mbps"] is None
    assert result.measurements["throughput_pass"] is None
    assert execution.validation_pass is None
    assert "吞吐" in " ".join(result.warnings)


@pytest.mark.parametrize(
    "path_loss_application,expected_verdict",
    [
        (_verified_path_loss_application(), "UNKNOWN"),
        (
            {
                **_verified_path_loss_application(),
                "provenance": "simulated",
                "certificate_id": "impossible-strict-simulated",
            },
            "UNKNOWN",
        ),
    ],
    ids=["verified-application", "malformed-application"],
)
@pytest.mark.asyncio
async def test_analysis_keeps_normal_verdict_with_explicit_trusted_throughput(
    monkeypatch,
    path_loss_application: dict[str, object],
    expected_verdict: str,
):
    from app.services.mimo_ota.executors import analysis as analysis_module

    measure = {
        "measurement_verified": True,
        "measurement_source": "instrument",
        "simulated_sources": [],
        "frequency_consistency": {"fully_verified": True},
        "path_loss_application": path_loss_application,
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [
            {
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
            }
        ],
    }
    measure["rf_kpi_trust"] = build_rf_kpi_trust(
        requested_azimuths=[0.0],
        azimuth_results=measure["azimuth_results"],
        source="explicit_real",
    )
    measure["formal_rf_kpi_verified"] = True
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
    execution = SimpleNamespace(validation_pass=None, validation_details=None, id="p1-54")
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )

    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _execution: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _execution, phase: measure if phase == "measure" else {"quiet_zone_pass": True},
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_args: None)

    result = await AnalysisExecutor().execute(context)

    assert result.measurements["verdict"] == expected_verdict
    if expected_verdict == "PASS":
        assert result.measurements["avg_throughput_mbps"] == 350.0
        assert result.measurements["throughput_pass"] is True
        assert execution.validation_pass is True
    else:
        assert result.measurements["avg_throughput_mbps"] is None
        assert result.measurements["throughput_pass"] is None
        assert execution.validation_pass is None
        warning_text = " ".join(result.warnings)
        if path_loss_application.get("provenance") == "real":
            assert "静区" in warning_text
        else:
            assert "路损" in warning_text


def _report_execution(throughput_verified: bool | None) -> SimpleNamespace:
    measure = {
        "measurement_verified": True,
        "measurement_source": "instrument",
        "simulated_sources": [],
        "path_loss_application": _verified_path_loss_application(),
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [
            {
                "azimuth_deg": 0.0,
                "measurement_source": "instrument",
                "measurement_verified": True,
                "throughput_mbps": 0.0,
                "throughput_valid": True,
                "throughput_scope": ThroughputMetrics.SCOPE_PCELL,
                "rsrp_dbm": -80.0,
                "rsrp_valid": True,
                "sinr_db": 30.0,
                "sinr_valid": True,
                "rank_indicator": 2.0,
                "rank_indicator_valid": True,
            }
        ],
    }
    if throughput_verified is not None:
        measure["throughput_verified"] = throughput_verified
    measure["rf_kpi_trust"] = build_rf_kpi_trust(
        requested_azimuths=[0.0],
        azimuth_results=measure["azimuth_results"],
        source="explicit_real",
    )
    measure["formal_rf_kpi_verified"] = True
    return SimpleNamespace(
        id="p1-54-report",
        measurements={
            "phases": {
                "measure": measure,
                "analysis": {"verdict": "PASS"},
            }
        },
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 8, 16),
        completed_at=datetime(2026, 8, 16),
        validation_pass=True,
    )


@pytest.mark.parametrize("throughput_verified", [False, None])
def test_report_hides_untrusted_or_historical_throughput(
    throughput_verified: bool | None,
):
    content = _build_mimo_ota_content_data(
        _report_execution(throughput_verified),
        datetime(2026, 8, 16),
    )

    assert content["formal_throughput_verified"] is False
    assert content["overall_result"] == "undetermined"
    assert content["execution_summary"]["pending"] == 0
    assert content["execution_summary"]["undetermined"] == 1
    assert content["execution_summary"]["pass_rate"] is None
    assert "Throughput_Mbps" not in content["statistics"]
    assert content["statistics"]["RSRP_dBm"]["mean"] == -80.0
    assert content["table_data"][0]["Throughput (Mbps)"] == "N/A"
    assert content["table_data"][0]["RSRP (dBm)"] == "-80.0"
    measure_step = next(
        step for step in content["step_results"] if step["phase"] == "measure"
    )
    expected_label = "未验证" if throughput_verified is False else "未知"
    assert expected_label in measure_step["parameters"]["吞吐验证"]


def test_report_keeps_explicitly_trusted_throughput():
    content = _build_mimo_ota_content_data(
        _report_execution(True),
        datetime(2026, 8, 16),
    )

    assert content["formal_throughput_verified"] is True
    assert content["throughput_trust_schema_version"] == 2
    assert content["overall_result"] == "undetermined"
    assert content["table_data"][0]["Throughput (Mbps)"] == "0.0"


def test_existing_path_loss_only_report_is_not_trusted_for_throughput():
    path_loss_only = {"calibration_trust_schema_version": 1}
    fully_sanitized = {
        "calibration_trust_schema_version": 1,
        "throughput_trust_schema_version": 2,
        "path_loss_application": {
            "schema_version": 1,
            "status": "unknown",
            "provenance": "unknown",
            "reason": "legacy_unclassified",
            "gate_mode": "strict",
            "certificate_id": None,
            "value_disclosure": "none",
        },
        "formal_path_loss_verified": False,
        "rf_kpi_trust_schema_version": 1,
        "rf_kpi_trust": build_rf_kpi_trust(
            requested_azimuths=[],
            azimuth_results=[],
            source="unknown",
        ),
        "formal_rf_kpi_verified": False,
        "quiet_zone_evidence_schema_version": 1,
        "quiet_zone_evidence": build_quiet_zone_evidence(None),
        "formal_quiet_zone_verified": False,
    }
    inconsistent_path_loss_attestation = {
        **fully_sanitized,
        "formal_path_loss_verified": True,
    }
    old_throughput_scope = {
        "calibration_trust_schema_version": 1,
        "throughput_trust_schema_version": 1,
    }

    assert report_has_provenance_trust(path_loss_only) is False
    assert report_has_provenance_trust(old_throughput_scope) is False
    assert report_has_provenance_trust(inconsistent_path_loss_attestation) is False
    assert report_has_provenance_trust(fully_sanitized) is True
