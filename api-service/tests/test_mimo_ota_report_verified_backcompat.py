"""Codex on PR #80: report must NOT default an absent verified flag to True —
historical/migrated executions carry provenance (measurement_source /
quiet_zone_ripple_source) but no quiet_zone_verified / trp_verified key, and
defaulting True would silently present an old fallback run as a real measurement.
Pins that the report derives verification from provenance instead.

P2-21 迁移: 三标志的生效端从 step 顶层键挪到 parameters 下的可读标注
("已验证 (…)"/"未验证 (…)"/"未知 (…)") —— 本文件钉的是**推导逻辑**不变,
断言跟着打在新生效端 (标注前缀), 渲染可达性另由 test_p2_21_* 行为门钉。
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.report_service import ReportService


@pytest.fixture
def report_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


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


def _path_loss_report_phases(application, *, verified=False):
    return {
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
            "path_loss_application": application,
            "path_loss_verified": verified,
            "path_loss_calibration_use_mock": False if verified else None,
            "path_loss_compensation_db": 56.77,
            "throughput_verified": True,
            "throughput_scope": "pcell",
            "carrier_aggregation": {"num_component_carriers": 1},
            "azimuth_results": [{
                "azimuth_deg": 0.0,
                "rsrp_dbm": -70.0,
                "sinr_db": 20.0,
                "throughput_mbps": 500.0,
                "throughput_valid": True,
                "throughput_scope": "pcell",
                "rank_indicator": 4.0,
            }],
        },
        "analysis": {"verdict": "PASS"},
    }


def _path_loss_application(
    *,
    status="applied",
    provenance="unknown",
    reason="selected",
    certificate_id="cert-legacy",
    value_disclosure="hidden_unverified",
):
    return {
        "schema_version": 1,
        "status": status,
        "provenance": provenance,
        "reason": reason,
        "gate_mode": "mock_not_applicable",
        "certificate_id": certificate_id,
        "value_disclosure": value_disclosure,
    }


def test_report_renders_applied_unknown_certificate_without_false_uncompensated_claim():
    application = _path_loss_application()

    content = _build_mimo_ota_content_data(
        _exec(_path_loss_report_phases(application)), datetime(2026, 1, 1),
    )
    parameters = _step(content, "measure")["parameters"]

    assert content["path_loss_application"] == application
    assert content["formal_path_loss_verified"] is False
    assert content["overall_result"] != "passed"
    assert "已应用路损补偿" in parameters["路损应用"]
    assert "来源未知" in parameters["路损应用"]
    assert parameters["路损证书 ID"] == "cert-legacy"
    assert "未补偿" not in parameters["路损应用"]
    assert parameters["路损补偿 (dB)"] == "—（补偿数值不展示）"
    assert "56.77" not in str(content)


def test_report_renders_applied_real_certificate_and_verified_value():
    application = _path_loss_application(
        provenance="real",
        certificate_id="cert-real",
        value_disclosure="verified",
    )

    content = _build_mimo_ota_content_data(
        _exec(_path_loss_report_phases(application, verified=True)),
        datetime(2026, 1, 1),
    )
    parameters = _step(content, "measure")["parameters"]

    assert content["formal_path_loss_verified"] is True
    assert content["overall_result"] == "passed"
    assert parameters["路损补偿 (dB)"] == 56.77
    assert parameters["路损证书 ID"] == "cert-real"
    assert "已应用经验证" in parameters["路损应用"]


@pytest.mark.parametrize(
    "application, expected_text",
    [
        (
            _path_loss_application(provenance="simulated"),
            "流程演练",
        ),
        (
            _path_loss_application(
                status="not_applied",
                reason="rejected_untrusted",
                value_disclosure="none",
            ),
            "因来源未验证未应用",
        ),
        (
            _path_loss_application(
                status="not_applied",
                provenance="missing",
                reason="missing",
                certificate_id=None,
                value_disclosure="none",
            ),
            "未找到匹配",
        ),
        (
            _path_loss_application(
                status="not_applied",
                provenance="missing",
                reason="expired",
                certificate_id=None,
                value_disclosure="none",
            ),
            "已过期",
        ),
        (
            _path_loss_application(
                status="not_applied",
                provenance="missing",
                reason="frequency_mismatch",
                certificate_id=None,
                value_disclosure="none",
            ),
            "频率不匹配",
        ),
        (
            _path_loss_application(
                status="not_applied",
                provenance="missing",
                reason="operating_mode_mismatch",
                certificate_id=None,
                value_disclosure="none",
            ),
            "operating mode 不匹配",
        ),
        (None, "历史记录无法证明"),
        ({"schema_version": 1, "status": "invented"}, "历史记录无法证明"),
    ],
    ids=[
        "simulated",
        "rejected-untrusted",
        "missing",
        "expired",
        "frequency-mismatch",
        "mode-mismatch",
        "absent-history",
        "malformed-history",
    ],
)
def test_report_path_loss_state_matrix_hides_unverified_values(
    application,
    expected_text,
):
    content = _build_mimo_ota_content_data(
        _exec(_path_loss_report_phases(application)), datetime(2026, 1, 1),
    )
    parameters = _step(content, "measure")["parameters"]

    assert expected_text in parameters["路损应用"]
    assert parameters["路损补偿 (dB)"] == "—（补偿数值不展示）"
    assert content["formal_path_loss_verified"] is False
    assert content["overall_result"] != "passed"
    assert "56.77" not in str(content)


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
    assert content["overall_result"] == "undetermined"
    assert content["execution_summary"]["pending"] == 0
    assert content["execution_summary"]["undetermined"] == 1
    assert content["execution_summary"]["pass_rate"] is None
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

    assert content["overall_result"] == "undetermined"
    assert content["execution_summary"]["undetermined"] == 1
    assert content["execution_summary"]["pass_rate"] is None
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
            "throughput_verified": True,
            "throughput_scope": "pcell",
            "carrier_aggregation": {"num_component_carriers": 1},
            "azimuth_results": [{
                "azimuth_deg": 0.0,
                "rsrp_dbm": -70.0,
                "sinr_db": 20.0,
                "throughput_mbps": 500.0,
                "throughput_valid": True,
                "throughput_scope": "pcell",
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
            "throughput_trust_schema_version": 2,
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


def test_historical_client_vrt_report_is_hidden_until_server_rebuild(
    monkeypatch,
    tmp_path,
):
    from app.api import report as report_api

    report_file = tmp_path / "client-vrt.pdf"
    report_file.write_bytes(b"client-owned")
    historical = SimpleNamespace(
        id=uuid4(),
        status="completed",
        progress_percent=100,
        file_size_bytes=len(b"client-owned"),
        file_path=str(report_file),
        format="pdf",
        report_type="single_execution",
        title="historical client VRT",
        generated_by="operator",
        generated_at=datetime(2026, 1, 1),
        test_execution_ids=[],
        road_test_execution_id="vrt-old-gui-row",
        content_data={"overall_result": "passed"},
    )
    monkeypatch.setattr(
        report_api.report_service,
        "get_report",
        lambda db, report_id: historical,
    )

    summary = report_api._report_summary(object(), historical)
    assert summary.vrt_archive_trusted is False
    with pytest.raises(HTTPException) as get_error:
        report_api.get_report(historical.id, db=object())
    assert get_error.value.status_code == 409
    with pytest.raises(HTTPException) as download_error:
        report_api.download_report(historical.id, db=object())
    assert download_error.value.status_code == 409


def test_manual_generation_cannot_publish_untrusted_historical_vrt(report_db):
    from app.models.report import TestReport
    from app.services.report_service import LegacyVrtArchiveRejected

    report = TestReport(
        title="historical client VRT",
        report_type="single_execution",
        format="pdf",
        generated_by="operator",
        status="completed",
        road_test_execution_id="vrt-old-manual-generate",
        content_data={"overall_result": "passed"},
    )
    report_db.add(report)
    report_db.commit()

    with pytest.raises(LegacyVrtArchiveRejected, match="not server-owned"):
        ReportService().generate_report(report_db, report.id)

    report_db.refresh(report)
    assert report.status == "completed"
    assert report.content_data == {"overall_result": "passed"}


def test_report_list_regeneration_state_comes_from_mimo_trust_and_execution_truth(
    monkeypatch,
):
    from app.api import report as report_api

    recoverable_execution_id = uuid4()
    missing_execution_id = uuid4()

    def _report(*, content_data, execution_ids, generated_by="mimo_ota.executors.report"):
        return SimpleNamespace(
            id=uuid4(),
            title="Historical report",
            report_type="single_execution",
            format="pdf",
            status="completed",
            progress_percent=100,
            file_size_bytes=123,
            generated_by=generated_by,
            generated_at=datetime(2026, 1, 1),
            test_execution_ids=execution_ids,
            road_test_execution_id=None,
            content_data=content_data,
        )

    reports = [
        _report(
            content_data={"report_family": "mimo_ota"},
            execution_ids=[recoverable_execution_id],
        ),
        _report(
            content_data={
                "report_family": "mimo_ota",
                "calibration_trust_schema_version": 1,
                "throughput_trust_schema_version": 2,
            },
            execution_ids=[recoverable_execution_id],
        ),
        _report(
            content_data={"report_family": "mimo_ota"},
            execution_ids=[missing_execution_id],
        ),
        _report(
            content_data={"report_family": "mimo_ota"},
            execution_ids=[uuid4(), uuid4()],
        ),
        _report(content_data={}, execution_ids=[], generated_by="manual"),
    ]

    class _DB:
        def get(self, model, value):
            if value != recoverable_execution_id:
                return None
            return SimpleNamespace(
                config={"step_descriptors": [{"type": "MIMO_OTA_MEASURE"}]},
                test_case_id=None,
                status="completed",
            )

    monkeypatch.setattr(report_api.report_service, "list_reports", lambda **kwargs: reports)
    monkeypatch.setattr(report_api.report_service, "count_reports", lambda **kwargs: len(reports))

    response = report_api.list_reports(
        skip=0,
        limit=20,
        status=None,
        report_type=None,
        format=None,
        generated_by=None,
        db=_DB(),
    )
    recoverable, sanitized, missing, multiple, ordinary = response.reports

    assert recoverable.requires_regeneration is True
    assert recoverable.regeneration_available is True
    assert "UNKNOWN/N/A" in recoverable.regeneration_reason

    assert sanitized.requires_regeneration is False
    assert sanitized.regeneration_available is False
    assert sanitized.regeneration_reason is None

    assert missing.requires_regeneration is True
    assert missing.regeneration_available is False
    assert "unavailable" in missing.regeneration_reason.lower()

    assert multiple.requires_regeneration is True
    assert multiple.regeneration_available is False
    assert "single" in multiple.regeneration_reason.lower()

    assert ordinary.requires_regeneration is False
    assert ordinary.regeneration_available is False
    assert ordinary.regeneration_reason is None


def test_report_list_malformed_historical_json_does_not_poison_page(monkeypatch):
    from app.api import report as report_api

    malformed_execution_id = uuid4()
    healthy_execution_id = uuid4()
    malformed_descriptors_execution_id = uuid4()

    def _report(**overrides):
        values = {
            "id": uuid4(),
            "title": "Historical report",
            "report_type": "single_execution",
            "format": "pdf",
            "status": "completed",
            "progress_percent": 100,
            "file_size_bytes": 123,
            "generated_by": "manual",
            "generated_at": datetime(2026, 1, 1),
            "test_execution_ids": [],
            "road_test_execution_id": None,
            "content_data": {},
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    reports = [
        _report(content_data=["legacy", "non-object"]),
        _report(
            generated_by="mimo_ota.executors.report",
            content_data={"report_family": "mimo_ota"},
            test_execution_ids=[malformed_execution_id],
        ),
        _report(
            generated_by="mimo_ota.executors.report",
            content_data={"report_family": "mimo_ota"},
            test_execution_ids=[healthy_execution_id],
        ),
        _report(
            generated_by="mimo_ota.executors.report",
            content_data={"report_family": "mimo_ota"},
            test_execution_ids=[malformed_descriptors_execution_id],
        ),
        _report(
            generated_by="mimo_ota.executors.report",
            content_data={"report_family": "mimo_ota"},
            test_execution_ids=42,
        ),
        _report(
            test_execution_ids=[healthy_execution_id, "not-a-uuid"],
        ),
        _report(
            generated_by="mimo_ota.executors.report",
            content_data={
                "report_family": "mimo_ota",
                "calibration_trust_schema_version": True,
                "throughput_trust_schema_version": 2,
            },
            test_execution_ids=[healthy_execution_id],
        ),
        _report(
            generated_by="mimo_ota.executors.report",
            content_data={
                "report_family": "mimo_ota",
                "calibration_trust_schema_version": 1.0,
                "throughput_trust_schema_version": 2,
            },
            test_execution_ids=[healthy_execution_id],
        ),
        _report(
            generated_by="mimo_ota.executors.report",
            content_data={
                "report_family": "mimo_ota",
                "calibration_trust_schema_version": 1,
                "throughput_trust_schema_version": 2,
            },
            test_execution_ids=[healthy_execution_id],
        ),
    ]

    class _DB:
        def get(self, model, value):
            if value == malformed_execution_id:
                return SimpleNamespace(config=["legacy"], test_case_id=None)
            if value == healthy_execution_id:
                return SimpleNamespace(
                    config={"step_descriptors": [{"type": "MIMO_OTA_MEASURE"}]},
                    test_case_id=None,
                    status="completed",
                )
            if value == malformed_descriptors_execution_id:
                return SimpleNamespace(
                    config={"step_descriptors": 42},
                    test_case_id=None,
                )
            return None

    monkeypatch.setattr(report_api.report_service, "list_reports", lambda **kwargs: reports)
    monkeypatch.setattr(report_api.report_service, "count_reports", lambda **kwargs: len(reports))

    response = report_api.list_reports(
        skip=0,
        limit=20,
        status=None,
        report_type=None,
        format=None,
        generated_by=None,
        db=_DB(),
    )
    (
        malformed_content,
        malformed_execution,
        healthy,
        malformed_descriptors,
        malformed_execution_ids,
        malformed_execution_id_items,
        boolean_schema,
        float_schema,
        integer_schema,
    ) = response.reports

    assert malformed_content.requires_regeneration is False
    assert malformed_execution.requires_regeneration is True
    assert malformed_execution.regeneration_available is False
    assert "authoritative" in malformed_execution.regeneration_reason.lower()
    assert healthy.requires_regeneration is True
    assert healthy.regeneration_available is True
    assert malformed_descriptors.requires_regeneration is True
    assert malformed_descriptors.regeneration_available is False
    assert malformed_execution_ids.test_execution_ids == []
    assert malformed_execution_ids.requires_regeneration is True
    assert malformed_execution_ids.regeneration_available is False
    assert malformed_execution_id_items.test_execution_ids == []
    assert malformed_execution_id_items.requires_regeneration is True
    assert malformed_execution_id_items.regeneration_available is False
    assert boolean_schema.requires_regeneration is True
    assert float_schema.requires_regeneration is True
    assert integer_schema.requires_regeneration is False


def test_report_list_recovery_rejects_non_pdf_wrong_shape_and_in_progress(
    monkeypatch,
):
    from app.api import report as report_api

    execution_id = uuid4()

    def _report(**overrides):
        values = {
            "id": uuid4(),
            "title": "Historical report",
            "report_type": "single_execution",
            "format": "pdf",
            "status": "completed",
            "progress_percent": 100,
            "file_size_bytes": 123,
            "generated_by": "mimo_ota.executors.report",
            "generated_at": datetime(2026, 1, 1),
            "test_execution_ids": [execution_id],
            "road_test_execution_id": None,
            "content_data": {"report_family": "mimo_ota"},
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    reports = [
        _report(format="html"),
        _report(report_type="comparison"),
        _report(road_test_execution_id="vrt-1"),
        _report(status="generating"),
    ]

    class _DB:
        def get(self, model, value):
            return object() if value == execution_id else None

    monkeypatch.setattr(report_api.report_service, "list_reports", lambda **kwargs: reports)
    monkeypatch.setattr(report_api.report_service, "count_reports", lambda **kwargs: len(reports))

    response = report_api.list_reports(
        skip=0,
        limit=20,
        status=None,
        report_type=None,
        format=None,
        generated_by=None,
        db=_DB(),
    )

    html, comparison, road_test, generating = response.reports
    assert html.regeneration_available is False
    assert "PDF" in html.regeneration_reason
    assert comparison.regeneration_available is False
    assert "single-execution" in comparison.regeneration_reason
    assert road_test.regeneration_available is False
    assert "road-test" in road_test.regeneration_reason.lower()
    assert generating.regeneration_available is False
    assert "progress" in generating.regeneration_reason.lower()


def test_non_pdf_legacy_mimo_regeneration_fails_before_mutating_report(report_db):
    from app.models.report import TestReport
    from app.models.test_plan import TestExecution

    execution = TestExecution(
        id=uuid4(),
        status="completed",
        config={"step_descriptors": [{"type": "MIMO_OTA_MEASURE"}]},
    )
    report = TestReport(
        title="legacy HTML",
        report_type="single_execution",
        format="html",
        generated_by="mimo_ota.executors.report",
        status="completed",
        test_execution_ids=[str(execution.id)],
        file_path="legacy.html",
        content_data={"report_family": "mimo_ota", "overall_result": "passed"},
    )
    report_db.add_all([execution, report])
    report_db.commit()

    with pytest.raises(ValueError, match="PDF"):
        ReportService().generate_report(report_db, report.id)

    report_db.refresh(report)
    assert report.status == "completed"
    assert report.file_path == "legacy.html"
    assert report.content_data == {
        "report_family": "mimo_ota",
        "overall_result": "passed",
    }


def test_malformed_execution_ids_cannot_republish_ordinary_report_content(
    report_db,
    monkeypatch,
):
    from app.models.report import TestReport
    from app.models.test_plan import TestExecution

    execution = TestExecution(
        id=uuid4(),
        status="completed",
        config={"step_descriptors": [{"type": "WAIT"}]},
    )
    report = TestReport(
        title="ordinary report with damaged links",
        report_type="single_execution",
        format="pdf",
        generated_by="manual",
        status="completed",
        test_execution_ids=[str(execution.id), "not-a-uuid"],
        file_path="old.pdf",
        content_data={"overall_result": "passed", "pass_rate": 100.0},
    )
    report_db.add_all([execution, report])
    report_db.commit()

    monkeypatch.setattr(
        "app.services.pdf_generator.PDFGenerator.generate_report",
        lambda *args, **kwargs: pytest.fail(
            "malformed linked sources must be rejected before PDF generation"
        ),
    )

    with pytest.raises(ValueError, match="identifiers are malformed"):
        ReportService().generate_report(report_db, report.id)

    report_db.refresh(report)
    assert report.status == "completed"
    assert report.file_path == "old.pdf"
    assert report.content_data == {
        "overall_result": "passed",
        "pass_rate": 100.0,
    }


def test_declared_mimo_report_cannot_regenerate_from_non_mimo_execution(report_db):
    from app.models.report import TestReport
    from app.models.test_plan import TestExecution
    from app.services.report_service import LegacyMimoRegenerationRejected

    execution = TestExecution(
        id=uuid4(),
        status="completed",
        config={"step_descriptors": [{"type": "WAIT"}]},
    )
    report = TestReport(
        title="spoofed MIMO source",
        report_type="single_execution",
        format="pdf",
        generated_by="mimo_ota.executors.report",
        status="completed",
        test_execution_ids=[str(execution.id)],
        file_path="legacy.pdf",
        content_data={"report_family": "mimo_ota", "overall_result": "passed"},
    )
    report_db.add_all([execution, report])
    report_db.commit()

    with pytest.raises(LegacyMimoRegenerationRejected, match="MIMO OTA"):
        ReportService().generate_report(report_db, report.id)

    report_db.refresh(report)
    assert report.status == "completed"
    assert report.file_path == "legacy.pdf"
    assert report.content_data == {
        "report_family": "mimo_ota",
        "overall_result": "passed",
    }


def test_sanitized_mimo_report_still_rejects_non_mimo_execution_after_claim(
    report_db,
    monkeypatch,
):
    from app.models.report import TestReport
    from app.models.test_plan import TestExecution

    execution = TestExecution(
        id=uuid4(),
        status="completed",
        config={"step_descriptors": [{"type": "WAIT"}]},
    )
    report = TestReport(
        title="sanitized marker with non-MIMO source",
        report_type="single_execution",
        format="pdf",
        generated_by="mimo_ota.executors.report",
        status="completed",
        test_execution_ids=[str(execution.id)],
        content_data={
            "report_family": "mimo_ota",
            "calibration_trust_schema_version": 1,
            "throughput_trust_schema_version": 2,
        },
    )
    report_db.add_all([execution, report])
    report_db.commit()

    monkeypatch.setattr(
        "app.services.mimo_ota.executors.report._build_mimo_ota_content_data",
        lambda *args, **kwargs: pytest.fail(
            "non-MIMO execution must never reach the MIMO report builder"
        ),
    )

    with pytest.raises(ValueError, match="not authoritatively MIMO OTA"):
        ReportService().generate_report(report_db, report.id)

    report_db.refresh(report)
    assert report.status == "failed"
    assert "not authoritatively MIMO OTA" in report.error_message


def _vrt_archive_payload():
    return SimpleNamespace(
        model_dump=lambda mode: {
            "logs": [],
            "time_series": [],
            "step_configs": [],
            "kpi_summary": [],
        },
        scenario_name="claim race",
        mode=SimpleNamespace(value="ota"),
        overall_result="passed",
        notes=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_marker", [None, True, 1.0])
async def test_vrt_archive_rebuilds_existing_row_without_strict_server_trust(
    report_db,
    monkeypatch,
    legacy_marker,
):
    from app.api import road_test
    from app.models.report import TestReport

    legacy_content = {
        "overall_result": "passed",
        "kpi_summary": [{"name": "client-owned", "mean": 999}],
    }
    if legacy_marker is not None:
        legacy_content["vrt_archive_trust_schema_version"] = legacy_marker
    legacy = TestReport(
        title="legacy client-created VRT report",
        report_type="single_execution",
        format="pdf",
        generated_by="operator",
        status="completed",
        road_test_execution_id="vrt-legacy-client-row",
        content_data=legacy_content,
        file_path="legacy-client.pdf",
    )
    report_db.add(legacy)
    report_db.commit()

    async def _authoritative_execution_report(execution_id, db):
        return _vrt_archive_payload()

    generation_calls = []

    def _capture_authoritative_rebuild(
        self,
        db,
        report_id,
        content_data_override=None,
        **kwargs,
    ):
        generation_calls.append((report_id, content_data_override))
        report = db.get(TestReport, report_id)
        report.status = "completed"
        report.content_data = content_data_override
        report.file_path = "server-rebuilt.pdf"
        db.commit()
        return report

    monkeypatch.setattr(
        road_test,
        "_generate_execution_report",
        _authoritative_execution_report,
    )
    monkeypatch.setattr(
        "app.services.report_service.ReportService.generate_report",
        _capture_authoritative_rebuild,
    )
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    await road_test._archive_execution_report("vrt-legacy-client-row", report_db)

    report_db.expire_all()
    rebuilt = report_db.query(TestReport).filter(
        TestReport.road_test_execution_id == "vrt-legacy-client-row"
    ).one()
    assert rebuilt.id == legacy.id
    assert rebuilt.file_path == "server-rebuilt.pdf"
    assert rebuilt.content_data["vrt_archive_trust_schema_version"] == 1
    assert type(rebuilt.content_data["vrt_archive_trust_schema_version"]) is int
    assert "client-owned" not in str(rebuilt.content_data)
    assert generation_calls == [(legacy.id, rebuilt.content_data)]


@pytest.mark.asyncio
async def test_vrt_legacy_rebuild_normalizes_server_owned_pdf_envelope(
    report_db,
    monkeypatch,
):
    from app.api import road_test
    from app.models.report import TestReport

    legacy = TestReport(
        title="client HTML title",
        description="client description",
        report_type="single_execution",
        format="html",
        generated_by="operator",
        status="completed",
        road_test_execution_id="vrt-legacy-envelope",
        content_data={"overall_result": "passed", "client_kpi": 999},
        file_path="client-owned.html",
        file_size_bytes=12345,
        template_id=uuid4(),
    )
    report_db.add(legacy)
    report_db.commit()

    async def _authoritative_execution_report(execution_id, db):
        return _vrt_archive_payload()

    generated = []

    def _generate_pdf(self, report_data, template, output_path):
        generated.append((report_data, template, output_path))

    monkeypatch.setattr(
        road_test,
        "_generate_execution_report",
        _authoritative_execution_report,
    )
    monkeypatch.setattr(
        "app.services.report_service.PDFGenerator.generate_report",
        _generate_pdf,
    )
    monkeypatch.setattr("app.services.report_service.os.path.getsize", lambda path: 456)
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    await road_test._archive_execution_report("vrt-legacy-envelope", report_db)

    report_db.expire_all()
    rebuilt = report_db.get(TestReport, legacy.id)
    assert rebuilt.status == "completed"
    assert rebuilt.report_type == "single_execution"
    assert rebuilt.format == "pdf"
    assert rebuilt.title == "虚拟路测报告: claim race"
    assert rebuilt.generated_by == "System (Auto-Archive)"
    assert rebuilt.template_id is None
    assert rebuilt.file_path != "client-owned.html"
    assert rebuilt.file_path.endswith(f"report_{legacy.id}.pdf")
    assert rebuilt.file_size_bytes == 456
    assert rebuilt.content_data["vrt_archive_trust_schema_version"] == 1
    assert "client_kpi" not in rebuilt.content_data
    assert len(generated) == 1
    assert generated[0][1] is None


@pytest.mark.asyncio
async def test_vrt_legacy_rebuild_claims_old_snapshot_only_once(
    report_db,
    monkeypatch,
):
    from sqlalchemy.orm import sessionmaker

    from app.api import road_test
    from app.models.report import TestReport

    legacy = TestReport(
        title="legacy race",
        report_type="single_execution",
        format="pdf",
        generated_by="operator",
        status="completed",
        road_test_execution_id="vrt-legacy-rebuild-race",
        content_data={"snapshot": "client"},
        file_path="client.pdf",
    )
    report_db.add(legacy)
    report_db.commit()

    both_read_legacy = asyncio.Event()
    release_builders = asyncio.Event()
    builder_count = 0

    async def _coordinated_execution_report(execution_id, db):
        nonlocal builder_count
        builder_count += 1
        if builder_count == 2:
            both_read_legacy.set()
        await release_builders.wait()
        return _vrt_archive_payload()

    generated_paths = []

    def _generate_pdf(self, report_data, template, output_path):
        generated_paths.append(output_path)

    monkeypatch.setattr(
        road_test,
        "_generate_execution_report",
        _coordinated_execution_report,
    )
    monkeypatch.setattr(
        "app.services.report_service.PDFGenerator.generate_report",
        _generate_pdf,
    )
    monkeypatch.setattr("app.services.report_service.os.path.getsize", lambda path: 10)
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    SessionLocal = sessionmaker(bind=report_db.get_bind())
    first_db = SessionLocal()
    second_db = SessionLocal()
    first = asyncio.create_task(
        road_test._archive_execution_report("vrt-legacy-rebuild-race", first_db)
    )
    second = asyncio.create_task(
        road_test._archive_execution_report("vrt-legacy-rebuild-race", second_db)
    )
    await both_read_legacy.wait()
    release_builders.set()
    await asyncio.gather(first, second)
    first_db.close()
    second_db.close()

    report_db.expire_all()
    rebuilt = report_db.get(TestReport, legacy.id)
    assert rebuilt.status == "completed"
    assert rebuilt.content_data["vrt_archive_trust_schema_version"] == 1
    assert len(generated_paths) == 1


@pytest.mark.asyncio
async def test_vrt_archive_preserves_an_existing_generation_claim(
    report_db,
    monkeypatch,
):
    from app.api import road_test
    from app.models.report import TestReport

    report = TestReport(
        title="active writer",
        report_type="single_execution",
        format="pdf",
        generated_by="System (Auto-Archive)",
        status="generating",
        road_test_execution_id="vrt-active-writer",
        content_data={
            "owner": "report-generator",
            "vrt_archive_trust_schema_version": 1,
        },
    )
    report_db.add(report)
    report_db.commit()

    async def _unexpected_execution_report(execution_id, db):
        pytest.fail("an existing VRT archive must not be regenerated")

    monkeypatch.setattr(
        road_test,
        "_generate_execution_report",
        _unexpected_execution_report,
    )
    monkeypatch.setattr(
        "app.services.report_service.ReportService.generate_report",
        lambda *args, **kwargs: pytest.fail(
            "an existing VRT archive must not reopen the writer claim"
        ),
    )
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    await road_test._archive_execution_report("vrt-active-writer", report_db)

    report_db.expire_all()
    preserved = report_db.get(TestReport, report.id)
    assert preserved.status == "generating"
    assert preserved.content_data == {
        "owner": "report-generator",
        "vrt_archive_trust_schema_version": 1,
    }


@pytest.mark.asyncio
async def test_vrt_archive_does_not_rewrite_existing_completed_snapshot(
    report_db,
    monkeypatch,
):
    from app.api import road_test
    from app.models.report import TestReport

    report = TestReport(
        title="authoritative final snapshot",
        report_type="single_execution",
        format="pdf",
        generated_by="System (Auto-Archive)",
        status="completed",
        road_test_execution_id="vrt-preclaim-window",
        content_data={
            "snapshot": "final",
            "vrt_archive_trust_schema_version": 1,
        },
    )
    report_db.add(report)
    report_db.commit()

    async def _unexpected_execution_report(execution_id, db):
        pytest.fail("an existing completed VRT archive must be immutable")

    monkeypatch.setattr(
        road_test,
        "_generate_execution_report",
        _unexpected_execution_report,
    )
    monkeypatch.setattr(
        "app.services.report_service.ReportService.generate_report",
        lambda *args, **kwargs: pytest.fail(
            "an existing completed VRT archive must not be regenerated"
        ),
    )
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    await road_test._archive_execution_report("vrt-preclaim-window", report_db)

    report_db.expire_all()
    preserved = report_db.get(TestReport, report.id)
    assert preserved.status == "completed"
    assert preserved.content_data == {
        "snapshot": "final",
        "vrt_archive_trust_schema_version": 1,
    }


@pytest.mark.asyncio
async def test_vrt_archive_conflict_handler_does_not_release_winner_claim(
    report_db,
    monkeypatch,
):
    from app.api import road_test
    from app.models.report import ReportStatus, TestReport
    from app.services.report_service import ReportGenerationConflict

    async def _fake_execution_report(execution_id, db):
        return _vrt_archive_payload()

    def _lose_claim(self, db, report_id, content_data_override=None, **kwargs):
        preclaim = db.get(TestReport, report_id)
        assert preclaim.status == ReportStatus.PENDING.value
        assert preclaim.generation_completed_at is None
        db.query(TestReport).filter(TestReport.id == report_id).update(
            {TestReport.status: ReportStatus.GENERATING.value},
            synchronize_session=False,
        )
        db.commit()
        raise ReportGenerationConflict("Report generation is already in progress")

    monkeypatch.setattr(road_test, "_generate_execution_report", _fake_execution_report)
    monkeypatch.setattr(
        "app.services.report_service.ReportService.generate_report",
        _lose_claim,
    )
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    await road_test._archive_execution_report("vrt-lost-claim", report_db)

    report_db.expire_all()
    preserved = report_db.query(TestReport).filter(
        TestReport.road_test_execution_id == "vrt-lost-claim"
    ).one()
    assert preserved.status == "generating"


@pytest.mark.asyncio
async def test_vrt_archive_conflict_loser_does_not_downgrade_completed_winner(
    report_db,
    monkeypatch,
):
    from app.api import road_test
    from app.models.report import ReportStatus, TestReport
    from app.services.report_service import ReportGenerationConflict

    async def _fake_execution_report(execution_id, db):
        return _vrt_archive_payload()

    def _winner_completes_before_conflict_is_handled(
        self,
        db,
        report_id,
        content_data_override=None,
        **kwargs,
    ):
        db.query(TestReport).filter(TestReport.id == report_id).update(
            {
                TestReport.status: ReportStatus.COMPLETED.value,
                TestReport.content_data: {"version": "winner"},
                TestReport.file_path: "winner.pdf",
            },
            synchronize_session=False,
        )
        db.commit()
        raise ReportGenerationConflict("another archive completed generation")

    monkeypatch.setattr(road_test, "_generate_execution_report", _fake_execution_report)
    monkeypatch.setattr(
        "app.services.report_service.ReportService.generate_report",
        _winner_completes_before_conflict_is_handled,
    )
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    await road_test._archive_execution_report("vrt-winner-completed", report_db)

    report_db.expire_all()
    preserved = report_db.query(TestReport).filter(
        TestReport.road_test_execution_id == "vrt-winner-completed"
    ).one()
    assert preserved.status == "completed"
    assert preserved.content_data == {"version": "winner"}
    assert preserved.file_path == "winner.pdf"


def test_vrt_execution_id_has_one_report_database_invariant(report_db):
    from sqlalchemy.exc import IntegrityError

    from app.models.report import TestReport

    report_db.add_all(
        [
            TestReport(
                title="first",
                report_type="single_execution",
                format="pdf",
                generated_by="System (Auto-Archive)",
                status="completed",
                road_test_execution_id="vrt-one-report",
            ),
            TestReport(
                title="second",
                report_type="single_execution",
                format="pdf",
                generated_by="System (Auto-Archive)",
                status="completed",
                road_test_execution_id="vrt-one-report",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        report_db.commit()
    report_db.rollback()


def test_generic_report_creation_cannot_claim_vrt_archive_slot(report_db, monkeypatch):
    from app.api import report as report_api
    from app.schemas.report import ReportCreate

    monkeypatch.setattr(
        report_api.report_service,
        "create_report",
        lambda *args, **kwargs: pytest.fail(
            "generic report creation must not write a VRT archive row"
        ),
    )

    request = ReportCreate(
        title="manual archive",
        report_type="single_execution",
        format="pdf",
        generated_by="operator",
        road_test_execution_id="vrt-preclaim",
    )
    with pytest.raises(HTTPException) as exc_info:
        report_api.create_report(request, report_db)

    assert exc_info.value.status_code == 409
    assert "terminal archive" in str(exc_info.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("archive_status", ["pending", "generating"])
async def test_manual_vrt_archive_does_not_report_pending_row_as_generated(
    report_db,
    monkeypatch,
    archive_status,
):
    from app.api import road_test
    from app.models.report import TestReport
    from app.models.test_plan import TestExecution

    execution = TestExecution(
        status="completed",
        scenario_id="pending-archive",
        mode="ota",
    )
    report_db.add(execution)
    report_db.flush()
    report_db.add(
        TestReport(
            title="recoverable pending archive",
            report_type="single_execution",
            format="pdf",
            generated_by="System (Auto-Archive)",
            status=archive_status,
            road_test_execution_id=str(execution.id),
        )
    )
    report_db.commit()
    async def _existing_pending_archive(*args, **kwargs):
        return None

    monkeypatch.setattr(
        road_test,
        "_archive_execution_report",
        _existing_pending_archive,
    )

    with pytest.raises(HTTPException) as exc_info:
        await road_test.archive_execution_report(str(execution.id), report_db)

    assert exc_info.value.status_code == 409
    detail = str(exc_info.value.detail).lower()
    assert archive_status in detail
    if archive_status == "generating":
        assert "inspect" in detail
        assert "/generate" not in detail
    else:
        assert "/generate" in detail


def test_vrt_terminal_transition_allows_only_one_archive_owner(report_db):
    from app.models.test_plan import TestExecution
    from app.schemas.road_test import ExecutionStatus
    from app.services.road_test.vrt_execution_service import VrtExecutionService

    execution = TestExecution(
        status=ExecutionStatus.RUNNING.value,
        scenario_id="terminal-cas",
        mode="ota",
        vrt_runtime_status={"progress_percent": 50.0},
    )
    report_db.add(execution)
    report_db.commit()

    service = VrtExecutionService()
    first = service.stop(
        report_db,
        str(execution.id),
        expected_status=ExecutionStatus.RUNNING,
    )
    second = service.complete(
        report_db,
        str(execution.id),
        expected_status=ExecutionStatus.RUNNING,
    )

    assert first is not None
    assert first.status == ExecutionStatus.STOPPED.value
    assert second is None
    report_db.expire_all()
    assert report_db.get(TestExecution, execution.id).status == ExecutionStatus.STOPPED.value


def test_stale_nonterminal_transition_cannot_overwrite_terminal_state(report_db):
    from app.models.test_plan import TestExecution
    from app.schemas.road_test import ExecutionStatus
    from app.services.road_test.vrt_execution_service import VrtExecutionService

    execution = TestExecution(
        status=ExecutionStatus.PAUSED.value,
        scenario_id="terminal-cas-vs-resume",
        mode="ota",
    )
    report_db.add(execution)
    report_db.commit()

    service = VrtExecutionService()
    terminal = service.stop(
        report_db,
        str(execution.id),
        expected_status=ExecutionStatus.PAUSED,
    )
    stale_resume = service.resume(
        report_db,
        str(execution.id),
        expected_status=ExecutionStatus.PAUSED,
    )

    assert terminal is not None
    assert stale_resume is None
    report_db.expire_all()
    assert report_db.get(TestExecution, execution.id).status == ExecutionStatus.STOPPED.value


@pytest.mark.asyncio
async def test_vrt_first_archive_loser_exits_after_unique_insert_conflict(
    report_db,
    monkeypatch,
):
    from sqlalchemy.exc import IntegrityError

    from app.api import road_test
    from app.models.report import TestReport

    async def _fake_execution_report(execution_id, db):
        return _vrt_archive_payload()

    original_commit = report_db.commit
    first_commit = True
    winner = TestReport(
        title="concurrent winner",
        report_type="single_execution",
        format="pdf",
        generated_by="System (Auto-Archive)",
        status="completed",
        road_test_execution_id="vrt-first-race",
        content_data={"owner": "winner"},
    )

    def _race_commit():
        nonlocal first_commit
        if not first_commit:
            return original_commit()
        first_commit = False
        report_db.rollback()
        report_db.add(winner)
        original_commit()
        raise IntegrityError("INSERT test_reports", {}, Exception("unique conflict"))

    generated_report_ids = []

    def _generate_winner(self, db, report_id, content_data_override=None):
        generated_report_ids.append(report_id)

    monkeypatch.setattr(road_test, "_generate_execution_report", _fake_execution_report)
    monkeypatch.setattr(report_db, "commit", _race_commit)
    monkeypatch.setattr(
        "app.services.report_service.ReportService.generate_report",
        _generate_winner,
    )
    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disabled in test")),
    )

    await road_test._archive_execution_report("vrt-first-race", report_db)

    reports = report_db.query(TestReport).filter(
        TestReport.road_test_execution_id == "vrt-first-race"
    ).all()
    assert [report.id for report in reports] == [winner.id]
    assert generated_report_ids == []


def test_report_generation_rejects_an_already_claimed_report(report_db):
    from app.models.report import TestReport

    report = TestReport(
        title="already generating",
        report_type="single_execution",
        format="pdf",
        generated_by="manual",
        status="generating",
        content_data={},
    )
    report_db.add(report)
    report_db.commit()

    with pytest.raises(ValueError, match="already in progress"):
        ReportService().generate_report(report_db, report.id)

    report_db.refresh(report)
    assert report.status == "generating"


def test_atomic_generation_claim_rejects_the_losing_session():
    from app.services.report_service import (
        ReportGenerationConflict,
        claim_report_generation,
    )

    class _LostClaimQuery:
        predicates = ()

        def filter(self, *args):
            self.predicates = args
            return self

        def update(self, values, synchronize_session):
            return 0

    query = _LostClaimQuery()

    class _DB:
        rolled_back = False

        def query(self, model):
            return query

        def rollback(self):
            self.rolled_back = True

        def commit(self):
            raise AssertionError("a losing claim must not commit")

    db = _DB()
    with pytest.raises(ReportGenerationConflict, match="already in progress"):
        claim_report_generation(db, uuid4())
    assert db.rolled_back is True
    assert any(
        "test_reports.status" in str(predicate)
        and "!=" in str(predicate)
        and "generating" in str(predicate.compile(compile_kwargs={"literal_binds": True}))
        for predicate in query.predicates
    )


def test_non_mimo_generation_claim_conflict_is_http_409(monkeypatch):
    from app.api import report as report_api
    from app.services.report_service import ReportGenerationConflict

    ordinary = SimpleNamespace(
        content_data={},
        generated_by="manual",
        test_execution_ids=[],
    )
    monkeypatch.setattr(
        report_api.report_service,
        "get_report",
        lambda db, report_id: ordinary,
    )
    monkeypatch.setattr(
        report_api.report_service,
        "generate_report",
        lambda db, report_id: (_ for _ in ()).throw(
            ReportGenerationConflict("Report generation is already in progress")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        report_api.generate_report(uuid4(), db=object())

    assert exc_info.value.status_code == 409
    assert "already in progress" in str(exc_info.value.detail)


def test_legacy_mimo_regeneration_rejection_is_http_409(monkeypatch):
    from app.api import report as report_api
    from app.services.report_service import LegacyMimoRegenerationRejected

    monkeypatch.setattr(
        report_api.report_service,
        "generate_report",
        lambda db, report_id: (_ for _ in ()).throw(
            LegacyMimoRegenerationRejected("Only PDF reports can be regenerated")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        report_api.generate_report(uuid4(), db=object())

    assert exc_info.value.status_code == 409
    assert "Only PDF reports" in str(exc_info.value.detail)


def test_mimo_generation_value_error_after_claim_is_not_misreported_as_conflict(
    monkeypatch,
):
    from app.api import report as report_api

    sanitized_mimo = SimpleNamespace(
        content_data={
            "report_family": "mimo_ota",
            "calibration_trust_schema_version": 1,
            "throughput_trust_schema_version": 2,
        },
        generated_by="mimo_ota.executors.report",
        test_execution_ids=[],
    )
    monkeypatch.setattr(
        report_api.report_service,
        "get_report",
        lambda db, report_id: sanitized_mimo,
    )
    monkeypatch.setattr(
        report_api.report_service,
        "generate_report",
        lambda db, report_id: (_ for _ in ()).throw(
            ValueError("template rendering failed")
        ),
    )

    with pytest.raises(ValueError, match="template rendering failed"):
        report_api.generate_report(uuid4(), db=object())


def test_report_create_drops_client_supplied_trust_attestation():
    class _FakeDB:
        def add(self, value):
            self.value = value

        def commit(self):
            return None

        def refresh(self, value):
            return None

    forged = {
        "report_family": "mimo_ota",
        "calibration_trust_schema_version": 1,
        "throughput_trust_schema_version": 1,
        "formal_path_loss_verified": True,
        "path_loss_application": {
            "schema_version": 1,
            "status": "applied",
            "provenance": "real",
            "reason": "selected",
            "gate_mode": "strict",
            "certificate_id": "forged-cert",
            "value_disclosure": "verified",
        },
        "formal_throughput_verified": True,
        "overall_result": "passed",
        "statistics": {"avg_throughput_mbps": 9999.0},
    }

    report = ReportService().create_report(
        _FakeDB(),
        title="forged legacy KPI",
        report_type="single_execution",
        format="pdf",
        generated_by="client",
        content_data=forged,
    )

    assert "report_family" not in report.content_data
    assert "calibration_trust_schema_version" not in report.content_data
    assert "throughput_trust_schema_version" not in report.content_data
    assert "formal_path_loss_verified" not in report.content_data
    assert "path_loss_application" not in report.content_data
    assert "formal_throughput_verified" not in report.content_data
    assert report.content_data["overall_result"] == "passed"
    assert report.content_data["statistics"]["avg_throughput_mbps"] == 9999.0


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
