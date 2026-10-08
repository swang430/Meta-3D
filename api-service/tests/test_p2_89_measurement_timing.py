import pytest
from types import SimpleNamespace
from uuid import uuid4
from pydantic import ValidationError

from app.schemas.mimo_ota.config import (
    MIMOOTAConfiguration,
    dump_canonical_mimo_ota_configuration,
)


def test_new_window_default_is_explicit_three_not_hidden_hundred():
    cfg = MIMOOTAConfiguration()
    assert cfg.num_samples_per_azimuth == 3
    assert dump_canonical_mimo_ota_configuration(cfg)["num_samples_per_azimuth"] == 3


@pytest.mark.parametrize("count", [0, -1, 10001, 1.5, True])
def test_invalid_window_count_is_rejected_before_freeze(count):
    with pytest.raises(ValidationError):
        MIMOOTAConfiguration(num_samples_per_azimuth=count)


def test_historical_explicit_hundred_is_not_silently_rewritten():
    cfg = MIMOOTAConfiguration(num_samples_per_azimuth=100)
    assert dump_canonical_mimo_ota_configuration(cfg)["num_samples_per_azimuth"] == 100


@pytest.mark.parametrize("delay", [-1, float("inf"), float("nan")])
def test_settling_is_finite_nonnegative_independent_operator_delay(delay):
    with pytest.raises(ValidationError):
        MIMOOTAConfiguration(settling_time_s=delay)


def test_factory_does_not_estimate_elapsed_from_ignored_duration(monkeypatch):
    from app.services.mimo_ota import factory

    monkeypatch.setattr(factory, "resolve_lab_profile", lambda *_: SimpleNamespace(
        id=uuid4(), active_calibration_certificate_id=None))
    db = SimpleNamespace(add=lambda _: None, commit=lambda: None, refresh=lambda _: None)
    case, _ = factory.build_mimo_ota_test_case(
        db, name="timing", config_overrides={"measurement_duration_s": 999})
    assert case.test_duration_sec is None


def test_report_marks_compatibility_duration_and_interval_not_effective():
    from tests.test_p2_88_report_traceability import _execution
    from tests.test_p2_66_execution_evidence_outcome import _freeze
    from app.services.mimo_ota.report_traceability import report_traceability_parameters, report_traceability
    from app.hal.base_station_compatibility import canonical_payload_digest

    frozen = _freeze()
    frozen["mimo_ota_configuration"].update(measurement_duration_s=999, sample_interval_ms=999)
    frozen["digest"] = canonical_payload_digest({k: v for k, v in frozen.items() if k != "digest"})
    parameters = report_traceability_parameters(report_traceability(_execution(frozen), 12))
    for key in ("measurement_duration_s", "sample_interval_ms"):
        assert parameters[key]["生效说明"] == "历史兼容字段，不控制本次测量"


def test_live_and_checked_commissioning_contract_marks_ignored_duration():
    from pathlib import Path
    import yaml
    from app.main import app

    checked = yaml.safe_load((Path(__file__).resolve().parents[2] / "api/openapi.yaml").read_text())
    for contract in (app.openapi(), checked):
        field = contract["components"]["schemas"]["CreateSessionRequest"]["properties"]["measurement_duration_s"]
        assert field["deprecated"] is True
        assert "不控制测量时长" in field["description"]
