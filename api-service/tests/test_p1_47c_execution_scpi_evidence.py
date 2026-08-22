"""P1-47C：SCPI 证据必须进入同一 TestExecution 的生效链。"""
from __future__ import annotations

from datetime import datetime
import inspect
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.logging_config import current_execution_id
from app.db.database import Base, get_db
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    InstrumentEnvironment,
    InstrumentEvidenceItem,
    ScpiExchangeRef,
)
from app.main import app
from app.models.report import TestReport
from app.models.test_plan import TestExecution
from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.execution_scpi_evidence import (
    finalize_execution_scpi_evidence,
    public_execution_scpi_evidence,
    record_execution_scpi_evidence,
    record_f64_command_capture,
    record_positioner_capture,
    register_required_scpi_evidence,
)
from app.services.report_data_collector import ReportDataCollector


engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _db_schema():
    Base.metadata.create_all(bind=engine)
    previous = app.dependency_overrides.get(get_db)

    def _override():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    yield
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _execution(db) -> TestExecution:
    execution = TestExecution(
        status="running",
        started_at=datetime.utcnow(),
        executed_by="test_case_runner",
        config={"phase_progress": []},
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    current_execution_id.set(str(execution.id))
    return execution


def _item(
    *,
    verdict=EvidenceVerdict.PASSED,
    level=EvidenceLevel.APPLIED,
    requested=636666,
):
    return InstrumentEvidenceItem(
        instrument="uxm",
        evidence_key="uxm.config_readback",
        requested=requested,
        command_sent="CONF:AUTH:TOKEN secret-value",
        readback={"value": 636666, "password": "secret-value"},
        exchange_ids=["exchange-1", "exchange-2"],
        evidence_level=level,
        source_reference="notebooklm:source:manual#section",
        verdict=verdict,
        reason="configuration_readback_matched",
    )


def _environment():
    return InstrumentEnvironment(
        instrument_id="baseStation",
        instrument="uxm",
        model="E7515B",
        firmware_version="A.18.01",
        test_application="5G_NR_Test",
        serial_number="MY1234",
        captured_from_live_connection=True,
    )


def _exchanges(execution, *, capture_id="capture-1"):
    return [
        ScpiExchangeRef(
            exchange_id="exchange-1",
            instrument_id="baseStation",
            operation="command",
            command="CONF:ARFCN 636666",
            execution_id=str(execution.id),
            capture_id=capture_id,
            sequence=0,
            result_type="ok",
        ),
        ScpiExchangeRef(
            exchange_id="exchange-2",
            instrument_id="baseStation",
            operation="query",
            command="CONF:ARFCN?",
            execution_id=str(execution.id),
            capture_id=capture_id,
            sequence=1,
            result_type="response",
            response="636666",
        ),
    ]


def test_azimuth_evidence_workload_is_bounded_and_canonical():
    with pytest.raises(ValueError, match="at most 361"):
        MIMOOTAConfiguration(azimuths_deg=[float(index) for index in range(362)])
    with pytest.raises(ValueError, match="equivalent duplicates"):
        MIMOOTAConfiguration(azimuths_deg=[0.0, 360.0])
    with pytest.raises(ValueError, match="finite angles"):
        MIMOOTAConfiguration(azimuths_deg=[float("inf")])


def test_fixed_summary_is_sanitized_and_persisted_on_same_execution(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        item=_item(),
        environment=_environment(),
        exchanges=_exchanges(execution),
    )
    summary = finalize_execution_scpi_evidence(execution)
    db.commit()

    db.expire_all()
    stored = db.query(TestExecution).filter(TestExecution.id == execution.id).one()
    evidence = stored.config["scpi_evidence"]
    assert evidence["execution_id"] == str(execution.id)
    assert evidence["formal_verdict"] == "passed"
    assert evidence["formal_acceptance"] is True
    assert evidence["missing_requirements"] == []
    assert evidence["items"][0]["exchange_ids"] == ["exchange-1", "exchange-2"]
    assert set(evidence["items"][0]) >= {
        "requested", "command_sent", "readback", "exchange_ids",
        "evidence_level", "source_reference", "verdict", "reason",
    }
    serialized = str(evidence)
    assert "secret-value" not in serialized
    assert "[REDACTED]" in serialized
    assert summary.formal_acceptance is True
    assert public_execution_scpi_evidence(stored)["items"][0]["evidence_key"] == (
        "uxm.config_readback"
    )


def test_unverified_frequency_identity_blocks_formal_acceptance(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        item=_item(),
        environment=_environment(),
        exchanges=_exchanges(execution),
    )
    execution.measurements = {
        "phases": {
            "measure": {
                "frequency_consistency": {
                    "fully_verified": False,
                    "warnings": ["F64 bandwidth lacks a supported readback"],
                }
            }
        }
    }

    summary = finalize_execution_scpi_evidence(execution)

    assert summary.formal_acceptance is False
    assert summary.formal_verdict is EvidenceVerdict.UNKNOWN
    assert summary.reason == "frequency_identity_not_fully_verified"


def test_simulated_exchanges_cannot_be_persisted_as_formal_evidence(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    simulated = [
        exchange.model_copy(update={"simulated": True})
        for exchange in _exchanges(execution)
    ]

    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        item=_item(),
        environment=_environment(),
        exchanges=simulated,
    )
    summary = finalize_execution_scpi_evidence(execution)

    assert summary.formal_acceptance is False
    assert summary.formal_verdict is EvidenceVerdict.UNKNOWN
    assert "simulated_exchange_not_authoritative" in summary.items[0].reason


@pytest.mark.parametrize("verdict", [EvidenceVerdict.UNKNOWN, EvidenceVerdict.REJECTED])
def test_unknown_or_rejected_mandatory_evidence_blocks_formal_pass(db, verdict):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        item=_item(verdict=verdict),
        environment=_environment(),
        exchanges=_exchanges(execution),
    )
    summary = finalize_execution_scpi_evidence(execution)
    assert summary.formal_acceptance is False
    assert summary.formal_verdict.value == verdict.value


def test_missing_mandatory_evidence_blocks_formal_pass(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="positioner.azimuth.000",
        evidence_key="positioner.angle",
        requested=0.0,
    )
    summary = finalize_execution_scpi_evidence(execution)
    assert summary.formal_acceptance is False
    assert summary.formal_verdict is EvidenceVerdict.UNKNOWN
    assert summary.missing_requirements == ["positioner.azimuth.000"]


def test_case_runner_gate_cannot_leave_business_validation_green(db):
    from app.services.test_case_runner import _finalize_scpi_acceptance

    execution = _execution(db)
    execution.validation_pass = True
    execution.measurements = {
        "phases": {"measure": {
            "path_loss_verified": True,
            "path_loss_calibration_use_mock": False,
        }}
    }
    register_required_scpi_evidence(
        execution,
        requirement_id="positioner.azimuth.000",
        evidence_key="positioner.angle",
        requested=0.0,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    summary = _finalize_scpi_acceptance(execution)
    assert summary.formal_acceptance is False
    assert execution.validation_pass is False


def test_passed_item_below_required_level_still_blocks_formal_pass(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.config_applied",
        evidence_key="uxm.config_readback",
        requested=636666,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.config_applied",
        item=_item(level=EvidenceLevel.ACCEPTED),
        environment=_environment(),
        exchanges=_exchanges(execution),
    )
    summary = finalize_execution_scpi_evidence(execution)
    assert summary.formal_acceptance is False
    assert summary.formal_verdict is EvidenceVerdict.UNKNOWN
    assert summary.reason == (
        "mandatory_evidence_level_insufficient:uxm.pcell.config_applied"
    )


def test_passed_item_for_different_requested_value_cannot_close_requirement(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.config_applied",
        evidence_key="uxm.config_readback",
        requested=640000,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.config_applied",
        item=_item(level=EvidenceLevel.APPLIED),
        environment=_environment(),
        exchanges=_exchanges(execution),
    )
    summary = finalize_execution_scpi_evidence(execution)
    assert summary.formal_acceptance is False
    assert summary.formal_verdict is EvidenceVerdict.UNKNOWN
    assert summary.reason == (
        "mandatory_requested_mismatch:uxm.pcell.config_applied"
    )


def test_record_rejects_cross_execution_context(db):
    execution = _execution(db)
    current_execution_id.set(str(uuid4()))
    with pytest.raises(ValueError, match="execution context mismatch"):
        record_execution_scpi_evidence(
            execution,
            requirement_id="uxm.pcell.arfcn",
            item=_item(),
            environment=_environment(),
            exchanges=_exchanges(execution),
        )


def test_item_captured_by_another_execution_cannot_be_rebound(db):
    source_execution = _execution(db)
    stale_exchanges = _exchanges(source_execution, capture_id="capture-a")
    target_execution = _execution(db)
    register_required_scpi_evidence(
        target_execution,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    record_execution_scpi_evidence(
        target_execution,
        requirement_id="uxm.pcell.arfcn",
        item=_item(),
        environment=_environment(),
        exchanges=stale_exchanges,
    )
    summary = finalize_execution_scpi_evidence(target_execution)
    assert summary.formal_acceptance is False
    assert summary.formal_verdict is EvidenceVerdict.UNKNOWN
    assert "provenance" in summary.reason or "unconfirmed" in summary.reason


def test_environment_hot_swap_cannot_lend_identity_to_old_item(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        item=_item(),
        environment=_environment(),
        exchanges=_exchanges(execution),
    )
    assert finalize_execution_scpi_evidence(execution).formal_acceptance is True

    execution.config["scpi_evidence"]["environments"]["baseStation"][
        "serial_number"
    ] = "HOT-SWAPPED-SERIAL"
    summary = finalize_execution_scpi_evidence(execution)
    assert summary.formal_acceptance is False
    assert summary.reason == (
        "mandatory_evidence_provenance_invalid:uxm.pcell.arfcn"
    )


def test_dual_axis_position_capture_binds_azimuth_feedback_not_last_elevation(db):
    execution = _execution(db)
    requirement_id = "positioner.azimuth.000"
    register_required_scpi_evidence(
        execution,
        requirement_id=requirement_id,
        evidence_key="positioner.angle",
        requested={"angle_deg": 45.0},
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    captured = {}

    class _Positioner:
        az_axis = "X"

        def capture_evidence_environment(self):
            return InstrumentEnvironment(
                instrument_id="positioner",
                instrument="positioner",
                model="A3200",
                firmware_version="1.0",
                captured_from_live_connection=True,
            )

        def build_p0_5_position_evidence(self, **kwargs):
            captured.update(kwargs)
            move = kwargs["move_exchange"]
            feedback = kwargs["feedback_exchange"]
            return InstrumentEvidenceItem(
                instrument="positioner",
                evidence_key="positioner.angle",
                requested={"angle_deg": kwargs["requested_angle_deg"]},
                command_sent=move.command,
                readback={"raw_feedback_angle_deg": 45.1},
                exchange_ids=[move.exchange_id, feedback.exchange_id],
                evidence_level=EvidenceLevel.APPLIED,
                source_reference="notebooklm:source:aerobasic#pfbk",
                verdict=EvidenceVerdict.PASSED,
                reason="calibrated_feedback_within_tolerance",
            )

    exchanges = [
        ScpiExchangeRef(
            exchange_id="move", instrument_id="positioner", operation="command",
            command="MOVEABS X 45.0000 Y 10.0000", execution_id=str(execution.id),
            capture_id="position-capture", sequence=0, result_type="ok",
        ),
        ScpiExchangeRef(
            exchange_id="status-x", instrument_id="positioner", operation="query",
            command="AXISSTATUS(X)", execution_id=str(execution.id),
            capture_id="position-capture", sequence=1, result_type="response", response="4",
        ),
        ScpiExchangeRef(
            exchange_id="feedback-x", instrument_id="positioner", operation="query",
            command="PFBK(X)", execution_id=str(execution.id),
            capture_id="position-capture", sequence=2, result_type="response", response="45.1",
        ),
        ScpiExchangeRef(
            exchange_id="feedback-y", instrument_id="positioner", operation="query",
            command="PFBK(Y)", execution_id=str(execution.id),
            capture_id="position-capture", sequence=3, result_type="response", response="10.0",
        ),
    ]
    record_positioner_capture(
        execution,
        requirement_id=requirement_id,
        requested_angle_deg=45.0,
        driver=_Positioner(),
        exchanges=exchanges,
    )
    assert captured["feedback_exchange"].exchange_id == "feedback-x"
    assert finalize_execution_scpi_evidence(execution).formal_acceptance is True


def test_f64_bypass_capture_selects_final_command_and_static_readback(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="f64.output_state",
        evidence_key="f64.bypass_mode",
        requested=2,
        required_evidence_level=EvidenceLevel.APPLIED,
    )

    class _BypassDriver:
        selected = None

        def capture_evidence_environment(self):
            return InstrumentEnvironment(
                instrument_id="channelEmulator",
                instrument="f64",
                model="PROPSIM F64",
                firmware_version="1.0",
                captured_from_live_connection=True,
            )

        def build_p0_5_command_evidence(self, **kwargs):
            self.selected = kwargs
            selected = [
                *kwargs["preclear_exchanges"],
                kwargs["command_exchange"],
                kwargs["opc_exchange"],
                kwargs["error_exchange"],
                kwargs["readback_exchange"],
                kwargs["state_exchange"],
            ]
            return InstrumentEvidenceItem(
                instrument="f64",
                evidence_key="f64.bypass_mode",
                requested=2,
                command_sent=kwargs["command_exchange"].command,
                readback={"value": 2},
                exchange_ids=[item.exchange_id for item in selected],
                evidence_level=EvidenceLevel.APPLIED,
                source_reference="notebooklm:f64#20.4.6.25-26",
                verdict=EvidenceVerdict.PASSED,
                reason="accepted_and_bypass_readback_matched",
            )

    commands = [
        ("pre", "SYST:ERR?", "query", "response", '0,"No error"'),
        ("old-set", "DIAG:SIMU:MODEL:STATIC 2", "command", "ok", None),
        ("old-opc", "*OPC?", "query", "response", "1"),
        ("old-err", "SYST:ERR?", "query", "response", '-200,"retry"'),
        ("reset", "DIAG:SIMU:MODEL:STATIC 0", "command", "ok", None),
        ("retry-pre", "SYST:ERR?", "query", "response", '0,"No error"'),
        ("final-set", "DIAG:SIMU:MODEL:STATIC 2", "command", "ok", None),
        ("final-opc", "*OPC?", "query", "response", "1"),
        ("final-err", "SYST:ERR?", "query", "response", '0,"No error"'),
        ("static-read", "DIAG:SIMU:MODEL:STATIC?", "query", "response", "2"),
        ("state", "DIAG:SIMU:STATE?", "query", "response", "STOPPED"),
    ]
    exchanges = [
        ScpiExchangeRef(
            exchange_id=exchange_id,
            instrument_id="channelEmulator",
            operation=operation,
            command=command,
            execution_id=str(execution.id),
            capture_id="bypass-capture",
            sequence=index,
            result_type=result_type,
            response=response,
        )
        for index, (exchange_id, command, operation, result_type, response)
        in enumerate(commands)
    ]
    driver = _BypassDriver()
    record_f64_command_capture(
        execution,
        requirement_id="f64.output_state",
        evidence_key="f64.bypass_mode",
        requested=2,
        driver=driver,
        exchanges=exchanges,
    )
    assert driver.selected["command_exchange"].exchange_id == "final-set"
    assert driver.selected["readback_exchange"].exchange_id == "static-read"
    assert finalize_execution_scpi_evidence(execution).formal_acceptance is True


def test_status_api_and_report_collector_return_sanitized_evidence(db):
    execution = _execution(db)
    register_required_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    record_execution_scpi_evidence(
        execution,
        requirement_id="uxm.pcell.arfcn",
        item=_item(),
        environment=_environment(),
        exchanges=_exchanges(execution),
    )
    finalize_execution_scpi_evidence(execution)
    execution.status = "completed"
    execution.completed_at = datetime.utcnow()
    db.commit()

    body = TestClient(app).get(
        f"/api/v1/test-plans/cases/executions/{execution.id}"
    ).json()
    assert body["scpi_evidence"]["formal_verdict"] == "passed"
    assert body["scpi_evidence"]["items"][0]["evidence_level"] == "E3"
    assert "secret-value" not in str(body)

    report = TestReport(
        title="P1-47C evidence report",
        report_type="single_execution",
        format="pdf",
        generated_by="test",
        test_execution_ids=[str(execution.id)],
    )
    db.add(report)
    db.commit()
    data = ReportDataCollector().collect(db, report)
    assert data.scpi_evidence["formal_verdict"] == "passed"
    assert data.scpi_evidence["items"][0]["exchange_ids"] == [
        "exchange-1", "exchange-2"
    ]


def test_multi_execution_report_cannot_filter_missing_evidence_into_pass(db):
    confirmed = _execution(db)
    register_required_scpi_evidence(
        confirmed,
        requirement_id="uxm.pcell.arfcn",
        evidence_key="uxm.config_readback",
        requested=636666,
    )
    record_execution_scpi_evidence(
        confirmed,
        requirement_id="uxm.pcell.arfcn",
        item=_item(),
        environment=_environment(),
        exchanges=_exchanges(confirmed),
    )
    finalize_execution_scpi_evidence(confirmed)
    confirmed.status = "completed"
    confirmed.completed_at = datetime.utcnow()
    db.commit()

    missing = _execution(db)
    missing.status = "completed"
    missing.completed_at = datetime.utcnow()
    db.commit()

    report = TestReport(
        title="multi execution evidence",
        report_type="comparison",
        format="pdf",
        generated_by="test",
        test_execution_ids=[str(confirmed.id), str(missing.id)],
    )
    db.add(report)
    db.commit()
    evidence = ReportDataCollector().collect(db, report).scpi_evidence
    assert evidence["formal_acceptance"] is False
    assert evidence["formal_verdict"] == "unknown"
    assert len(evidence["executions"]) == 2
    assert any(
        bundle["reason"] == "execution_evidence_missing_or_invalid"
        for bundle in evidence["executions"]
    )


@pytest.mark.parametrize("include_existing", [False, True])
def test_report_collector_rejects_missing_requested_execution_ids(
    db, include_existing
):
    requested_ids = [str(uuid4())]
    if include_existing:
        requested_ids.insert(0, str(_execution(db).id))
    report = TestReport(
        title="missing execution must fail closed",
        report_type="comparison",
        format="pdf",
        generated_by="test",
        test_execution_ids=requested_ids,
    )
    db.add(report)
    db.commit()

    with pytest.raises(ValueError, match="TestExecution rows not found"):
        ReportDataCollector().collect(db, report, strict_execution_ids=True)


def test_report_summary_never_counts_business_pass_without_formal_evidence(db):
    execution = _execution(db)
    execution.validation_pass = True
    execution.status = "completed"
    report = TestReport(
        title="strict summary",
        report_type="single_execution",
        format="pdf",
        generated_by="test",
        test_execution_ids=[str(execution.id)],
    )
    db.add(report)
    db.commit()
    summary = ReportDataCollector().collect(db, report).execution_summary
    assert summary is not None
    assert summary.passed == 0
    assert summary.failed == 1
    assert summary.pass_rate == 0.0


def test_report_service_overwrites_client_pass_in_pdf_and_persisted_content(
    db, tmp_path, monkeypatch
):
    from pathlib import Path

    from app.services.report_service import ReportService

    execution = _execution(db)
    execution.validation_pass = True
    execution.status = "completed"
    report = TestReport(
        title="malicious override",
        report_type="single_execution",
        format="pdf",
        generated_by="test",
        test_execution_ids=[str(execution.id)],
        content_data={"overall_result": "passed", "pass_rate": 100.0},
    )
    db.add(report)
    db.commit()
    captured = {}

    def _fake_generate(self, report_data, template, output_path):
        captured.update(report_data)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n")
        return str(path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.services.report_service.PDFGenerator.generate_report", _fake_generate
    )
    generated = ReportService().generate_report(
        db,
        report.id,
        content_data_override={"overall_result": "passed", "pass_rate": 100.0},
    )
    assert captured["overall_result"] == "failed"
    assert captured["execution_summary"]["passed"] == 0
    assert captured["scpi_evidence"]["formal_acceptance"] is False
    assert generated.content_data["overall_result"] == "failed"
    assert generated.content_data["scpi_evidence"]["formal_acceptance"] is False


def test_report_service_rebuilds_legacy_mimo_content_from_execution(
    db, tmp_path, monkeypatch,
):
    from pathlib import Path

    from app.services.report_service import ReportService

    execution = _execution(db)
    execution.status = "completed"
    execution.validation_pass = True
    execution.config = {
        "step_descriptors": [{"type": "MIMO_OTA_MEASURE"}],
    }
    execution.measurements = {
        "phases": {
            "precheck": {"overall_pass": True},
            "reference": {},
            "measure": {
                "path_loss_verified": True,
                # Legacy record: no path_loss_calibration_use_mock.
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
    }
    report = TestReport(
        title="MIMO OTA Test Report — legacy",
        report_type="single_execution",
        format="pdf",
        generated_by="user",
        test_execution_ids=[str(execution.id)],
        content_data={
            "overall_result": "passed",
            "statistics": {"throughput_mbps": {"mean": 500.0}},
            "table_data": [{"Throughput (Mbps)": "500.0"}],
        },
    )
    db.add(report)
    db.commit()
    captured = {}

    def _fake_generate(self, report_data, template, output_path):
        captured.update(report_data)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n")
        return str(path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.services.report_service.PDFGenerator.generate_report", _fake_generate,
    )

    generated = ReportService().generate_report(db, report.id)

    assert captured["calibration_trust_schema_version"] == 1
    assert captured["overall_result"] == "undetermined"
    assert captured["statistics"] == {}
    assert captured["table_data"][0]["Throughput (Mbps)"] == "N/A"
    assert generated.content_data == captured


def test_internal_mimo_generation_preserves_final_lifecycle_projection(
    db, tmp_path, monkeypatch,
):
    """最终投影的 verdict、summary 与顶层通过率必须同行发布。"""
    from pathlib import Path

    from app.services.mimo_ota.executors.report import ReportLifecycleProjection
    from app.services.report_service import ReportService

    execution = _execution(db)
    execution.config = {
        "step_descriptors": [{"type": "MIMO_OTA_MEASURE"}],
    }
    execution.validation_pass = True
    execution.measurements = {
        "phases": {
            "measure": {
                "path_loss_verified": True,
                "path_loss_calibration_use_mock": False,
                "throughput_verified": True,
                "throughput_scope": "pcell",
                "carrier_aggregation": {"num_component_carriers": 1},
                "azimuth_results": [
                    {
                        "azimuth_deg": 0.0,
                        "throughput_mbps": 123.0,
                        "throughput_valid": True,
                        "throughput_scope": "pcell",
                    }
                ],
            },
            "analysis": {"verdict": "PASS"},
        }
    }
    report = TestReport(
        title="MIMO OTA Test Report — projected",
        report_type="single_execution",
        format="pdf",
        generated_by="mimo_ota.executors.report",
        test_execution_ids=[str(execution.id)],
        content_data={},
    )
    db.add(report)
    db.commit()
    captured = {}

    def _fake_generate(self, report_data, template, output_path):
        captured.update(report_data)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n")
        return str(path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "app.services.report_service.PDFGenerator.generate_report", _fake_generate,
    )
    monkeypatch.setattr(
        "app.services.test_case_runner._finalize_scpi_acceptance",
        lambda _execution: None,
    )
    completed_at = datetime(2026, 8, 22, 1, 1, 29)
    projection = ReportLifecycleProjection(
        status="completed",
        completed_at=completed_at,
        duration_sec=89.195194,
    )

    def _settle_lifecycle(candidate):
        assert candidate == projection
        execution.status = candidate.status
        execution.completed_at = candidate.completed_at
        execution.duration_sec = candidate.duration_sec
        db.commit()
        db.refresh(execution)
        return candidate

    generated = ReportService().generate_report(
        db,
        report.id,
        execution_lifecycle_projection=projection,
        execution_lifecycle_resolver=_settle_lifecycle,
    )

    assert execution.status == "completed"
    assert execution.completed_at == completed_at
    assert execution.duration_sec == pytest.approx(89.195194)
    assert captured["test_plan"]["status"] == "completed"
    assert captured["overall_result"] == "passed"
    assert captured["pass_rate"] == 100.0
    assert captured["execution_summary"]["pending"] == 0
    assert captured["execution_summary"]["passed"] == 1
    assert captured["execution_summary"]["pass_rate"] == 100.0
    assert captured["execution_summary"]["total_duration_sec"] == pytest.approx(
        89.195194
    )
    assert generated.content_data == captured


def test_legacy_user_mimo_report_detail_is_blocked_by_execution_truth(db):
    from app.api import report as report_api

    execution = _execution(db)
    execution.config = {
        "step_descriptors": [{"type": "MIMO_OTA_MEASURE"}],
    }
    legacy = TestReport(
        title="手工生成的执行报告",
        report_type="single_execution",
        format="pdf",
        generated_by="user",
        status="completed",
        test_execution_ids=[str(execution.id)],
        content_data={"overall_result": "passed"},
    )
    db.add(legacy)
    db.commit()

    with pytest.raises(Exception) as exc_info:
        report_api.get_report(legacy.id, db=db)

    assert getattr(exc_info.value, "status_code", None) == 409


def test_multi_execution_mimo_regeneration_fails_closed(db):
    from app.services.report_service import ReportService

    executions = [_execution(db), _execution(db)]
    for execution in executions:
        execution.config = {
            "step_descriptors": [{"type": "MIMO_OTA_MEASURE"}],
        }
    legacy = TestReport(
        title="legacy multi MIMO",
        report_type="single_execution",
        format="pdf",
        generated_by="user",
        status="completed",
        test_execution_ids=[str(execution.id) for execution in executions],
        content_data={
            "overall_result": "passed",
            "table_data": [{"Throughput (Mbps)": "500.0"}],
        },
    )
    db.add(legacy)
    db.commit()

    with pytest.raises(ValueError, match="cannot be safely regenerated"):
        ReportService().generate_report(db, legacy.id)

    db.refresh(legacy)
    # Unsafe recovery shapes are rejected before status/content/file mutation.
    assert legacy.status == "completed"
    assert legacy.file_path is None


def test_pdf_active_chain_contains_layered_evidence_section(tmp_path):
    from app.services.pdf_generator import PDFGenerator

    generator = PDFGenerator()
    data = {
        "title": "P1-47C",
        "generated_by": "test",
        "scpi_evidence": {
            "formal_verdict": "unknown",
            "formal_acceptance": False,
            "reason": "mandatory_evidence_unconfirmed:positioner.azimuth.000",
            "items": [{
                "requirement_id": "positioner.azimuth.000",
                "instrument": "positioner",
                "evidence_level": "E3",
                "verdict": "unknown",
                "exchange_ids": ["ex-move", "ex-feedback"],
            }],
        },
    }
    sections = generator._auto_generate_sections(data)
    assert any(section["type"] == "scpi_evidence" for section in sections)
    output = tmp_path / "evidence.pdf"
    generator.generate_report(data, None, str(output))
    assert output.stat().st_size > 0


def test_custom_pdf_template_cannot_omit_scpi_evidence(tmp_path, monkeypatch):
    from app.services.pdf_generator import PDFGenerator

    generator = PDFGenerator()
    rendered = []

    def _capture(section, data, template):
        rendered.append(section["type"])
        return []

    monkeypatch.setattr(generator, "_generate_section", _capture)
    output = tmp_path / "custom-evidence.pdf"
    generator.generate_report(
        {
            "title": "strict template",
            "scpi_evidence": {
                "formal_verdict": "unknown",
                "formal_acceptance": False,
                "reason": "mandatory_evidence_missing:x",
            },
        },
        {"sections": [{"type": "cover", "order": 1}]},
        str(output),
    )
    assert rendered == ["cover", "scpi_evidence"]


def test_pdf_multi_execution_evidence_keeps_each_execution_items():
    from app.services.pdf_generator import PDFGenerator

    generator = PDFGenerator()
    data = {
        "scpi_evidence": {
            "formal_verdict": "unknown",
            "formal_acceptance": False,
            "reason": "one_or_more_executions_unconfirmed",
            "executions": [
                {
                    "execution_id": "aaaaaaaa-0000-0000-0000-000000000000",
                    "items": [{
                        "requirement_id": "uxm.pcell.config_applied",
                        "instrument": "uxm",
                        "evidence_level": "E3",
                        "verdict": "passed",
                        "exchange_ids": ["ex-uxm"],
                    }],
                },
                {
                    "execution_id": "bbbbbbbb-0000-0000-0000-000000000000",
                    "items": [{
                        "requirement_id": "positioner.azimuth.000",
                        "instrument": "positioner",
                        "evidence_level": "E2",
                        "verdict": "unknown",
                        "exchange_ids": ["ex-position"],
                    }],
                },
            ],
        }
    }
    elements = generator._generate_scpi_evidence_section(data)
    table = next(element for element in elements if hasattr(element, "_cellvalues"))
    rendered = str(table._cellvalues)
    assert "aaaaaaaa" in rendered and "ex-uxm" in rendered
    assert "bbbbbbbb" in rendered and "ex-position" in rendered


def test_mimo_report_applies_evidence_gate_before_building_content(db):
    from app.services.mimo_ota.executors.report import (
        ReportExecutor,
        _build_mimo_ota_content_data,
    )
    from app.services.test_case_runner import _finalize_scpi_acceptance

    execution = _execution(db)
    execution.validation_pass = True
    register_required_scpi_evidence(
        execution,
        requirement_id="positioner.azimuth.000",
        evidence_key="positioner.angle",
        requested=0.0,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    _finalize_scpi_acceptance(execution)
    measurements = dict(execution.measurements or {})
    phases = dict(measurements.get("phases") or {})
    measure = dict(phases.get("measure") or {})
    measure.update({
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        # P1-54 的独立吞吐可信门不是本用例的被测对象；显式打开后，
        # overall_result 仍只由 SCPI formal acceptance 决定。
        "throughput_verified": True,
        # P1-59 的独立 scope 门同样不是本用例对象；固定完整单载波证据。
        "throughput_scope": "pcell",
        "carrier_aggregation": {"num_component_carriers": 1},
        "azimuth_results": [{
            "azimuth_deg": 0.0,
            "throughput_mbps": 1.0,
            "throughput_valid": True,
            "throughput_scope": "pcell",
        }],
    })
    phases["measure"] = measure
    measurements["phases"] = phases
    execution.measurements = measurements
    content = _build_mimo_ota_content_data(
        execution, datetime.utcnow(), "evidence-gated"
    )
    # 证据门失败只决定“不能发布 PASS”；执行仍在 running 时，生命周期真值
    # 必须优先显示 incomplete，不能提前伪造一个已完成的 failed 终态。
    assert content["overall_result"] == "incomplete"
    assert content["scpi_evidence"]["formal_acceptance"] is False

    source = inspect.getsource(ReportExecutor.execute)
    assert source.index("_finalize_scpi_acceptance(execution)") < source.index(
        "_build_mimo_ota_content_data("
    )


def test_measure_executor_keeps_all_p0_5_evidence_capture_hooks():
    """变异门：正式执行器若断开任一证据钩子，本测试必须变红。"""
    from app.services.mimo_ota.executors.measure import MeasureExecutor

    source = inspect.getsource(MeasureExecutor.execute)
    required_hooks = {
        "record_uxm_config_capture": 1,
        "record_f64_command_capture": 3,
        "record_positioner_capture": 1,
        "record_uxm_throughput_capture": 1,
    }
    for hook, minimum_call_sites in required_hooks.items():
        assert source.count(f"{hook}(") >= minimum_call_sites, hook

    for requirement_prefix in (
        "uxm.pcell.config_applied",
        "f64.model_loaded",
        "f64.output_state",
        "positioner.azimuth.",
        "uxm.throughput.azimuth.",
    ):
        assert requirement_prefix in source

    # 驱动用 False（而非异常）报告转台失败；调用方不得在旧角度继续采样。
    assert "moved = await positioner.move_to" in source
    assert "if not moved:" in source
    # Attach 失败同样是 bool 契约，不能继续读取上一轮缓存 KPI。
    assert "signaling_started = await base_station.start_signaling()" in source
    assert "if not signaling_started:" in source
