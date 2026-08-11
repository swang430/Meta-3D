"""Codex on PR #80: report must NOT default an absent verified flag to True —
historical/migrated executions carry provenance (measurement_source /
quiet_zone_ripple_source) but no quiet_zone_verified / trp_verified key, and
defaulting True would silently present an old fallback run as a real measurement.
Pins that the report derives verification from provenance instead.

P2-21 迁移: 三标志的生效端从 step 顶层键挪到 parameters 下的可读标注
("已验证 (…)"/"未验证 (…)"/"未知 (…)") —— 本文件钉的是**推导逻辑**不变,
断言跟着打在新生效端 (标注前缀), 渲染可达性另由 test_p2_21_* 行为门钉。
"""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data


def _exec(phases):
    return SimpleNamespace(
        measurements={"phases": phases},
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1),
        # no `test_plan` attribute → getattr(..., None) inside the builder
    )


def _step(content, phase):
    return next(s for s in content["step_results"] if s["phase"] == phase)


def test_historical_fallback_not_marked_verified():
    """Legacy payloads: provenance present, verified flag ABSENT → must NOT
    be reported as verified."""
    phases = {
        "precheck": {
            "overall_pass": True,
            "quiet_zone_ripple_db": 0.7,
            "quiet_zone_ripple_source": "fallback_default",  # no quiet_zone_verified key
        },
        "reference": {
            "measured_trp_dbm": 23.5,
            "compensation_factor_db": 8.0,
            "measurement_source": "mock",  # no trp_verified key
        },
        "measure": {},
        "analysis": {"overall_pass": True},
    }
    content = _build_mimo_ota_content_data(_exec(phases), datetime(2026, 1, 1))
    assert not _step(content, "precheck")["parameters"]["静区验证"].startswith("已验证")
    assert not _step(content, "reference")["parameters"]["TRP 验证"].startswith("已验证")


def test_historical_cert_id_cannot_recover_path_loss_verification_or_kpis():
    """Legacy cert IDs do not carry provenance; a present ID must stay UNKNOWN
    and must not preserve a formal PASS or publish historical KPI values."""
    base = {
        "precheck": {"overall_pass": True, "quiet_zone_ripple_source": "probe_pattern_peak_spread"},
        "reference": {"measured_trp_dbm": 23.0, "compensation_factor_db": 8.0, "trp_verified": True},
        "analysis": {"verdict": "PASS"},
    }
    historical = dict(base, measure={
        "path_loss_certificate_id": "cert-123",
        "path_loss_compensation_db": 123.45,
        "azimuth_results": [{
            "azimuth_deg": 0.0,
            "rsrp_dbm": -70.0,
            "sinr_db": 20.0,
            "throughput_mbps": 500.0,
            "rank_indicator": 4.0,
        }],
    })
    content = _build_mimo_ota_content_data(
        _exec(historical), datetime(2026, 1, 1),
    )

    assert _step(content, "measure")["parameters"]["路损验证"].startswith("未知")
    assert content["overall_result"] == "unknown"
    assert content["execution_summary"]["pending"] == 1
    assert content["execution_summary"]["passed"] == 0
    assert content["execution_summary"]["failed"] == 0
    assert content["statistics"] == {}
    assert content["table_data"][0]["RSRP (dBm)"] == "N/A"
    assert content["table_data"][0]["Throughput (Mbps)"] == "N/A"
    assert _step(content, "analysis")["parameters"]["verdict"] == "UNKNOWN"


def test_historical_verified_flag_without_explicit_real_provenance_stays_unknown():
    """Pre-P1-27 ``path_loss_verified=True`` did not distinguish mock certs."""
    phases = {
        "precheck": {
            "overall_pass": True,
            "quiet_zone_ripple_source": "probe_pattern_peak_spread",
        },
        "reference": {
            "measured_trp_dbm": 23.0,
            "compensation_factor_db": 8.0,
            "trp_verified": True,
        },
        "measure": {
            "path_loss_verified": True,
            "path_loss_certificate_id": "legacy-cert",
            "azimuth_results": [{
                "azimuth_deg": 0.0,
                "rsrp_dbm": -70.0,
                "sinr_db": 20.0,
                "throughput_mbps": 500.0,
                "rank_indicator": 4.0,
            }],
        },
        "analysis": {"verdict": "PASS"},
    }

    content = _build_mimo_ota_content_data(
        _exec(phases), datetime(2026, 1, 1),
    )

    assert content["overall_result"] == "unknown"
    assert content["formal_path_loss_verified"] is False
    assert content["calibration_trust_schema_version"] == 1
    assert content["table_data"][0]["Throughput (Mbps)"] == "N/A"


def test_fresh_explicit_real_path_loss_can_publish_formal_kpis():
    phases = {
        "precheck": {
            "overall_pass": True,
            "quiet_zone_ripple_source": "probe_pattern_peak_spread",
        },
        "reference": {
            "measured_trp_dbm": 23.0,
            "compensation_factor_db": 8.0,
            "trp_verified": True,
        },
        "measure": {
            "path_loss_verified": True,
            "path_loss_calibration_use_mock": False,
            "azimuth_results": [{
                "azimuth_deg": 0.0,
                "rsrp_dbm": -70.0,
                "sinr_db": 20.0,
                "throughput_mbps": 500.0,
                "rank_indicator": 4.0,
            }],
        },
        "analysis": {"verdict": "PASS"},
    }

    content = _build_mimo_ota_content_data(
        _exec(phases), datetime(2026, 1, 1),
    )

    assert content["overall_result"] == "passed"
    assert content["formal_path_loss_verified"] is True
    assert content["table_data"][0]["Throughput (Mbps)"] == "500.0"


def test_legacy_mimo_pdf_without_explicit_path_loss_provenance_is_not_downloadable(
    monkeypatch, tmp_path,
):
    from app.api import report as report_api

    report_file = tmp_path / "legacy-mimo.pdf"
    report_file.write_bytes(b"legacy")
    legacy_report = SimpleNamespace(
        status="completed",
        file_path=str(report_file),
        format="pdf",
        title="MIMO OTA Test Report — legacy",
        content_data={
            "title": "MIMO OTA Test Report — legacy",
            "report_family": "mimo_ota",
        },
        generated_by="mimo_ota.executors.report",
    )
    monkeypatch.setattr(
        report_api.report_service,
        "get_report",
        lambda db, report_id: legacy_report,
    )

    with pytest.raises(HTTPException) as exc_info:
        report_api.download_report(uuid4(), db=object())

    assert exc_info.value.status_code == 409
    assert "regenerate" in str(exc_info.value.detail).lower()

    with pytest.raises(HTTPException) as get_exc_info:
        report_api.get_report(uuid4(), db=object())

    assert get_exc_info.value.status_code == 409


def test_non_mimo_report_with_mimo_like_title_is_still_downloadable(
    monkeypatch, tmp_path,
):
    from app.api import report as report_api

    report_file = tmp_path / "ordinary.pdf"
    report_file.write_bytes(b"ordinary")
    ordinary_report = SimpleNamespace(
        status="completed",
        file_path=str(report_file),
        format="pdf",
        title="MIMO OTA Test Report — user supplied title",
        content_data={"title": "MIMO OTA Test Report — user supplied title"},
        generated_by="manual",
    )
    monkeypatch.setattr(
        report_api.report_service,
        "get_report",
        lambda db, report_id: ordinary_report,
    )

    response = report_api.download_report(uuid4(), db=object())

    assert response.path == str(report_file)


def test_sanitized_unknown_mimo_audit_report_is_viewable_and_downloadable(
    monkeypatch, tmp_path,
):
    from app.api import report as report_api

    report_file = tmp_path / "unknown-audit.pdf"
    report_file.write_bytes(b"unknown audit")
    audit_report = SimpleNamespace(
        status="completed",
        file_path=str(report_file),
        format="pdf",
        title="MIMO OTA Test Report — legacy regenerated",
        generated_by="mimo_ota.executors.report",
        content_data={
            "report_family": "mimo_ota",
            "calibration_trust_schema_version": 1,
            "formal_path_loss_verified": False,
            "overall_result": "unknown",
        },
    )
    monkeypatch.setattr(
        report_api.report_service,
        "get_report",
        lambda db, report_id: audit_report,
    )

    assert report_api.get_report(uuid4(), db=object()) is audit_report
    assert report_api.download_report(uuid4(), db=object()).path == str(report_file)


def test_historical_real_provenance_derives_verified():
    """Legacy real-source payload (no flag) → derived verified=True for QZ
    (source unambiguously recovers it)."""
    phases = {
        "precheck": {
            "overall_pass": True,
            "quiet_zone_ripple_db": 0.5,
            "quiet_zone_ripple_source": "probe_pattern_peak_spread",
        },
        "reference": {"measured_trp_dbm": 23.0, "compensation_factor_db": 8.0,
                      "measurement_source": "hal_signal_analyzer", "trp_verified": True},
        "measure": {},
        "analysis": {"overall_pass": True},
    }
    content = _build_mimo_ota_content_data(_exec(phases), datetime(2026, 1, 1))
    assert _step(content, "precheck")["parameters"]["静区验证"].startswith("已验证")
    assert _step(content, "reference")["parameters"]["TRP 验证"].startswith("已验证")


def test_fresh_explicit_flags_passthrough():
    """Fresh executions set the flags explicitly — used verbatim."""
    phases = {
        "precheck": {"overall_pass": True, "quiet_zone_ripple_db": 0.7,
                     "quiet_zone_ripple_source": "fallback_default",
                     "quiet_zone_verified": False},
        "reference": {"measured_trp_dbm": 23.5, "compensation_factor_db": 8.0,
                      "measurement_source": "mock", "trp_verified": False},
        "measure": {},
        "analysis": {"overall_pass": True},
    }
    content = _build_mimo_ota_content_data(_exec(phases), datetime(2026, 1, 1))
    assert _step(content, "precheck")["parameters"]["静区验证"].startswith("未验证")
    assert _step(content, "reference")["parameters"]["TRP 验证"].startswith("未验证")
