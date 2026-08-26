"""P1-64: 静区代理量不能冒充正式多点场扫描证据。"""

import math
import json
from datetime import datetime, timezone
from pathlib import Path
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
        "base_station_metric_trust_schema_version": 1,
        "base_station_metric_projection": [],
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


def test_live_monitoring_does_not_derive_quiet_zone_from_path_loss():
    from app.services.instrument_hal_service import InstrumentHALService

    metrics = InstrumentHALService._build_monitoring_data(
        object(),
        {"path_loss_db": 80.0, "throughput_mbps": 350.0, "snr_db": 30.0},
        None,
        None,
        "2026-08-23T00:00:00Z",
    )

    assert "quiet_zone_uniformity" not in metrics


def test_monitoring_fallback_does_not_invent_quiet_zone_metric():
    from app.api.monitoring import _generate_fallback_data

    assert "quiet_zone_uniformity" not in _generate_fallback_data()


@pytest.mark.asyncio
async def test_legacy_quiet_zone_calibration_endpoint_fails_closed_without_real_scanner():
    from fastapi import HTTPException

    from app.api.calibration import execute_quiet_zone_calibration
    from app.schemas.calibration import QuietZoneCalibrationRequest

    request = QuietZoneCalibrationRequest(
        validation_type="field_uniformity",
        frequency_mhz=3500.0,
        tested_by="operator",
    )

    with pytest.raises(HTTPException) as exc_info:
        await execute_quiet_zone_calibration(request, db=object())

    assert exc_info.value.status_code == 503
    assert "真实多点场扫描" in str(exc_info.value.detail)


def test_channel_quiet_zone_random_writer_fails_before_db_write():
    from app.services.channel_calibration_service import ChannelCalibrationService

    class NoWriteDb:
        def add(self, _value):
            raise AssertionError("quiet-zone legacy row must not be persisted")

    service = ChannelCalibrationService(NoWriteDb())

    with pytest.raises(RuntimeError, match="真实多点场扫描"):
        service.run_quiet_zone_calibration(
            quiet_zone_shape="sphere",
            quiet_zone_diameter_m=1.0,
            fc_ghz=3.5,
        )


@pytest.mark.asyncio
async def test_orchestrator_mock_quiet_zone_fails_without_db_access():
    from app.services.quiet_zone_validation_service import QuietZoneValidationService

    result = await QuietZoneValidationService(object(), use_mock=True).run_field_uniformity_validation(
        chamber_id="00000000-0000-0000-0000-000000000001",
        frequency_mhz=3500.0,
        sgh_model="mock",
        sgh_gain_dbi=10.0,
    )

    assert result.success is False
    assert result.data == {}
    assert "真实多点场扫描" in result.message


def test_dashboard_quiet_zone_metric_is_unknown_without_evidence():
    from app.api.dashboard import _dashboard_live_metrics

    quiet_zone = next(
        metric for metric in _dashboard_live_metrics() if metric.label == "静区均匀性"
    )

    assert quiet_zone.value == "N/A"
    assert quiet_zone.trend == "unknown"


def _legacy_channel_qz_row():
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000064",
        session_id=None,
        quiet_zone_shape="sphere",
        quiet_zone_diameter_m=1.0,
        quiet_zone_height_m=None,
        field_probe_type="dipole",
        field_probe_size_mm=10.0,
        measurement_grid={"points": [{"amplitude_v_per_m": 1.23}]},
        num_points=100,
        amplitude_mean_db=0.1,
        amplitude_std_db=0.2,
        amplitude_range_db=[-0.2, 0.2],
        phase_mean_deg=1.0,
        phase_std_deg=2.0,
        phase_range_deg=[-2.0, 2.0],
        amplitude_uniformity_pass=True,
        phase_uniformity_pass=True,
        validation_pass=True,
        amplitude_threshold_db=1.0,
        phase_threshold_deg=30.0,
        fc_ghz=3.5,
        calibrated_at=datetime(2026, 8, 20),
        calibrated_by="legacy",
        valid_until=datetime(2027, 2, 20),
        status="valid",
    )


def test_legacy_channel_qz_detail_is_sanitized_to_unknown():
    from app.services.quiet_zone_calibration_truth import sanitize_channel_qz_detail

    detail = sanitize_channel_qz_detail(_legacy_channel_qz_row())

    assert detail["measurement_grid"] == {}
    assert detail["num_points"] == 0
    assert detail["validation_pass"] is None
    assert detail["amplitude_uniformity_pass"] is None
    assert detail["phase_uniformity_pass"] is None
    assert detail["amplitude_std_db"] is None
    assert detail["phase_std_deg"] is None
    assert detail["valid_until"] is None
    assert detail["status"] == "unknown"


def test_legacy_channel_qz_history_is_unknown_and_hides_values():
    from app.services.quiet_zone_calibration_truth import sanitize_channel_qz_history

    item = sanitize_channel_qz_history(_legacy_channel_qz_row())

    assert item["validation_pass"] is None
    assert item["status"] == "unknown"
    assert item["summary"] == {
        "shape": "sphere",
        "diameter_m": 1.0,
        "formal_status": "UNKNOWN",
        "amplitude_std_db": None,
    }


def test_channel_report_excludes_legacy_qz_from_formal_summary():
    from app.services.calibration_report_generator import CalibrationReportGenerator

    class Query:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, _value):
            return self

        def all(self):
            return [_legacy_channel_qz_row()]

    db = SimpleNamespace(query=lambda _model: Query())
    data = CalibrationReportGenerator(db)._collect_channel_data(
        calibration_type="quiet_zone"
    )

    assert data["execution_summary"] == {
        "total_executions": 0,
        "passed": 0,
        "failed": 0,
        "pending": 0,
        "pass_rate": None,
    }
    row = data["channel_calibration"]["quiet_zone"][0]
    assert row["validation_pass"] is None
    assert row["formal_status"] == "UNKNOWN"
    assert row["amplitude_uniformity_db"] is None
    assert row["phase_uniformity_deg"] is None


def test_comprehensive_summary_keeps_zero_formal_denominator_undetermined():
    from app.services.calibration_report_generator import CalibrationReportGenerator

    generator = CalibrationReportGenerator(SimpleNamespace())
    summary = generator._calculate_overall_summary({
        "probe_summary": {"total_executions": 0, "passed": 0, "failed": 0},
        "channel_summary": {
            "total_executions": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": None,
        },
    })

    assert summary["pass_rate"] is None
    assert summary["channel_pass_rate"] is None


@pytest.mark.asyncio
async def test_channel_status_cannot_be_valid_while_quiet_zone_is_unknown(monkeypatch):
    from app.api import channel_calibration as api

    temporal = SimpleNamespace(
        calibrated_at=datetime(2026, 8, 23),
        valid_until=datetime(2026, 10, 23),
    )
    service = SimpleNamespace(
        get_latest_temporal_calibration=lambda: temporal,
        list_calibrations=lambda **_kwargs: [],
    )
    monkeypatch.setattr(api, "ChannelCalibrationService", lambda _db: service)

    result = await api.get_channel_calibration_status(db=SimpleNamespace())

    assert result.temporal_status == "valid"
    assert result.quiet_zone_status == "unknown"
    assert result.overall_status == "unknown"


def test_empty_calibration_session_cannot_self_attest_pass():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.database import Base
    from app.services.channel_calibration_service import ChannelCalibrationService

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service = ChannelCalibrationService(db)
    session = service.create_session(name="no authoritative rows")

    completed = service.complete_session(
        session_id=session.id,
        overall_pass=True,
        total_calibrations=9,
        passed_calibrations=9,
        failed_calibrations=0,
    )

    assert completed.total_calibrations == 0
    assert completed.passed_calibrations == 0
    assert completed.failed_calibrations == 0
    assert completed.overall_pass is None


def test_requested_quiet_zone_without_a_trusted_row_keeps_session_undetermined():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.database import Base
    from app.models.channel_calibration import TemporalChannelCalibration
    from app.services.channel_calibration_service import ChannelCalibrationService

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service = ChannelCalibrationService(db)
    session = service.create_session(
        name="workflow requests quiet zone",
        workflow_id="workflow-1",
        configuration={
            "requested_calibration_types": ["temporal", "quiet_zone"],
        },
    )
    db.add(TemporalChannelCalibration(
        session_id=session.id,
        scenario_type="UMa",
        scenario_condition="LOS",
        fc_ghz=3.5,
        measured_pdp={},
        validation_pass=True,
    ))
    db.commit()

    completed = service.complete_session(
        session_id=session.id,
        overall_pass=False,
        total_calibrations=2,
        passed_calibrations=1,
        failed_calibrations=1,
    )

    assert completed.total_calibrations == 1
    assert completed.passed_calibrations == 1
    assert completed.failed_calibrations == 0
    assert completed.overall_pass is None


@pytest.mark.asyncio
async def test_direct_quiet_zone_start_registers_requested_scope_before_503():
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.api.channel_calibration import start_quiet_zone_calibration
    from app.db.database import Base
    from app.models.channel_calibration import TemporalChannelCalibration
    from app.schemas.channel_calibration import StartQuietZoneCalibrationRequest
    from app.services.channel_calibration_service import ChannelCalibrationService

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    service = ChannelCalibrationService(db)
    session = service.create_session(name="direct api session")
    db.add(TemporalChannelCalibration(
        session_id=session.id,
        scenario_type="UMa",
        scenario_condition="LOS",
        fc_ghz=3.5,
        measured_pdp={},
        validation_pass=True,
    ))
    db.commit()

    request = StartQuietZoneCalibrationRequest.model_validate({
        "quiet_zone": {"shape": "sphere", "diameter_m": 1.0},
        "fc_ghz": 3.5,
        "num_points": 25,
        "session_id": str(session.id),
        "calibrated_by": "operator",
    })
    with pytest.raises(HTTPException) as exc_info:
        await start_quiet_zone_calibration(request=request, db=db)
    assert exc_info.value.status_code == 503

    db.refresh(session)
    assert session.configuration["requested_calibration_types"] == ["quiet_zone"]
    completed = service.complete_session(
        session_id=session.id,
        overall_pass=True,
        total_calibrations=1,
        passed_calibrations=1,
        failed_calibrations=0,
    )
    assert completed.overall_pass is None

    from app.services.calibration_report_generator import CalibrationReportGenerator
    generator = CalibrationReportGenerator(db)
    channel_data = generator._collect_channel_data(session_id=session.id)
    assert channel_data["execution_summary"] == {
        "total_executions": 2,
        "passed": 1,
        "failed": 0,
        "pending": 0,
        "undetermined": 1,
        "pass_rate": None,
    }
    assert channel_data["channel_calibration"]["quiet_zone"] == [{
        "id": None,
        "session_id": str(session.id),
        "validation_pass": None,
        "formal_status": "UNKNOWN",
        "reason": "requested_without_explicit_real_evidence",
        "amplitude_uniformity_db": None,
        "phase_uniformity_deg": None,
    }]

    temporal_only = generator._collect_channel_data(
        session_id=session.id,
        calibration_type="temporal",
    )
    assert temporal_only["execution_summary"] == {
        "total_executions": 1,
        "passed": 1,
        "failed": 0,
        "pending": 0,
        "pass_rate": 100.0,
    }
    assert "quiet_zone" not in temporal_only["channel_calibration"]

    comprehensive = generator._collect_report_data(
        session_id=session.id,
        chamber_id=None,
        include_probe=False,
        include_channel=True,
    )
    assert comprehensive["execution_summary"]["pass_rate"] is None
    assert comprehensive["execution_summary"]["undetermined"] == 1


@pytest.mark.parametrize("malformed", ["null", "[]", '["schema_version", 2]', '"v2"', "3"])
def test_calibration_report_manifest_non_object_is_not_formal(tmp_path, malformed):
    """Gemini #375 R1 medium：manifest 文件是合法 JSON 但不是对象（null / list / 标量）时，
    可信门必须 fail-closed 返回 False，而不是在 `.get` 上抛 AttributeError 变 500。

    变异：去掉 `isinstance(manifest, dict)` 前置 → 本门以 AttributeError 红。
    """
    from app.api.calibration_report import _has_provenance_aware_calibration_manifest

    report_path = tmp_path / "channel_calibration_current.pdf"
    report_path.write_bytes(b"pdf")
    Path(f"{report_path}.provenance.json").write_text(malformed, encoding="utf-8")

    assert _has_provenance_aware_calibration_manifest(str(report_path)) is False


def test_calibration_report_manifest_requires_qz_sanitization(tmp_path):
    from app.api.calibration_report import _has_provenance_aware_calibration_manifest
    from app.services.calibration_report_generator import _write_report_provenance_manifest

    report_path = tmp_path / "channel_calibration_current.pdf"
    report_path.write_bytes(b"pdf")
    Path(f"{report_path}.provenance.json").write_text(
        json.dumps({
            "schema_version": 1,
            "path_loss_provenance_disclosed": True,
        }),
        encoding="utf-8",
    )
    assert _has_provenance_aware_calibration_manifest(str(report_path)) is False

    _write_report_provenance_manifest(
        str(report_path),
        {
            "probe_calibration": {},
            "channel_calibration": {"quiet_zone": [{"validation_pass": None}]},
        },
        path_loss_provenance_disclosed=True,
        quiet_zone_provenance_sanitized=True,
    )
    manifest = json.loads(
        Path(f"{report_path}.provenance.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 2
    assert manifest["quiet_zone_provenance_sanitized"] is True
    assert manifest["unverified_quiet_zone_records"] == 1
    assert _has_provenance_aware_calibration_manifest(str(report_path)) is True


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
