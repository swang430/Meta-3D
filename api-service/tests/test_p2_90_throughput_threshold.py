import pytest
from pydantic import ValidationError

from app.schemas.mimo_ota.config import MIMOOTAConfiguration, MIMOOTAPassCriteria
from app.services.mimo_ota.legacy_migration import legacy_to_mimo_ota_config


def test_default_has_no_implicit_absolute_threshold_or_theoretical_peak():
    cfg = MIMOOTAConfiguration(theoretical_peak_throughput_mbps=None)
    assert cfg.pass_criteria.min_throughput_mbps is None
    assert MIMOOTAConfiguration().theoretical_peak_throughput_mbps is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "300", "invalid"])
def test_threshold_rejects_nonfinite_or_non_numeric_operator_input(value):
    with pytest.raises(ValidationError):
        MIMOOTAPassCriteria(min_throughput_mbps=value)


@pytest.mark.parametrize("value", [None, 0, -1, 96.5, 1000000, 300])
def test_finite_explicit_threshold_is_preserved_without_reasonableness_check(value):
    assert MIMOOTAPassCriteria(min_throughput_mbps=value).min_throughput_mbps == value


def test_legacy_migration_does_not_invent_pass_threshold_from_target():
    payload = legacy_to_mimo_ota_config({"configuration": {"target_throughput_mbps": 450}})
    assert payload["pass_criteria"]["min_throughput_mbps"] is None


def test_legacy_explicit_threshold_remains_configuration_truth():
    payload = legacy_to_mimo_ota_config({"pass_criteria": {"min_throughput_mbps": 300}})
    assert payload["pass_criteria"]["min_throughput_mbps"] == 300


def test_commissioning_request_preserves_explicit_threshold_and_missing_is_none():
    from app.api.commissioning import CreateSessionRequest, _request_overrides

    assert _request_overrides(CreateSessionRequest(min_throughput_mbps=96.5))["pass_criteria"]["min_throughput_mbps"] == 96.5
    assert _request_overrides(CreateSessionRequest())["pass_criteria"]["min_throughput_mbps"] is None


def test_commissioning_openapi_mirrors_absolute_threshold_and_deprecated_theory():
    from pathlib import Path
    import yaml
    from app.main import app

    checked = yaml.safe_load((Path(__file__).resolve().parents[2] / "api/openapi.yaml").read_text())
    for contract in (app.openapi(), checked):
        props = contract["components"]["schemas"]["CreateSessionRequest"]["properties"]
        assert "min_throughput_mbps" in props
        assert props["min_throughput_mbps"].get("default") is None
        assert props["theoretical_peak_throughput_mbps"]["deprecated"] is True
        assert props["min_throughput_ratio"]["deprecated"] is True


def test_report_explains_frozen_absolute_threshold_and_inactive_legacy_fields():
    from app.services.mimo_ota.report_traceability import report_traceability_parameters

    rows = report_traceability_parameters({
        "reason": "冻结请求", "execution_mode": "real", "case_name": "用户名称",
        "duration_s": 10, "recorded_window_count": 1, "status": "frozen_request",
        "parameters": {p: {"requested": v, "source": "saved_configuration"} for p, v in {
            "pass_criteria.min_throughput_mbps": 96.5,
            "pass_criteria.min_throughput_ratio": 0.7,
            "theoretical_peak_throughput_mbps": 450,
        }.items()},
    })
    assert "操作员" in rows["pass_criteria.min_throughput_mbps"]["生效说明"]
    for p in ("pass_criteria.min_throughput_ratio", "theoretical_peak_throughput_mbps"):
        assert "当前" in rows[p]["生效说明"]
        assert "历史判据以原落库判决为准" in rows[p]["生效说明"]
