"""P1-73A Task 3：新执行证据只能使用 BaseStation 通用命名。"""

from __future__ import annotations

import inspect
from uuid import uuid4

from app.core.logging_config import current_execution_id
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    InstrumentEnvironment,
    InstrumentEvidenceItem,
    ScpiExchangeRef,
)
from app.models.test_plan import TestExecution
from app.services import execution_scpi_evidence as evidence_service
from app.services.mimo_ota.executors.measure import MeasureExecutor


def _legacy_payload(*, instrument: str = "uxm", model: str | None = "E7515B"):
    return {
        "schema_version": 1,
        "execution_id": "execution-1",
        "environments": {
            "baseStation": {
                "instrument_id": "baseStation",
                "instrument": instrument,
                "model": model,
                "firmware_version": "A.18.01",
                "captured_from_live_connection": True,
            }
        },
        "required": [{
            "requirement_id": "uxm.pcell.config_applied",
            "evidence_key": "uxm.config_apply",
            "requested": 636666,
            "required_evidence_level": "applied",
        }],
        "items": [{
            "requirement_id": "uxm.pcell.config_applied",
            "instrument": "uxm",
            "evidence_key": "uxm.config_apply",
            "requested": 636666,
            "command_sent": "BSE:CONF:NR5G:CELL0:ARFCN 636666",
            "readback": 636666,
            "exchange_ids": ["exchange-1"],
            "evidence_level": "applied",
            "source_reference": "UXM User Reference §20.4.3.14",
            "verdict": "passed",
            "reason": "configuration_readback_matched",
        }],
        "missing_requirements": [],
        "formal_verdict": "passed",
        "formal_acceptance": True,
        "reason": "all_mandatory_evidence_passed",
    }


def test_measure_new_writer_uses_only_base_station_evidence_hooks_and_keys():
    source = inspect.getsource(MeasureExecutor.execute)

    assert "record_base_station_config_capture(" in source
    assert "record_base_station_throughput_capture(" in source
    assert "record_uxm_config_capture(" not in source
    assert "record_uxm_throughput_capture(" not in source
    assert "base_station.pcell.config_applied" in source
    assert "base_station.config_apply" in source
    assert "base_station.throughput.azimuth." in source
    assert "base_station.dl_throughput" in source


def test_legacy_uxm_translation_requires_exact_live_uxm_identity():
    translator = getattr(
        evidence_service, "translate_legacy_uxm_execution_evidence", None
    )
    assert callable(translator)

    translated = translator(_legacy_payload(), execution_id="execution-1")
    assert translated is not None
    assert translated["required"][0]["requirement_id"] == (
        "base_station.pcell.config_applied"
    )
    assert translated["required"][0]["evidence_key"] == (
        "base_station.config_apply"
    )
    assert translated["items"][0]["evidence_key"] == (
        "base_station.config_apply"
    )

    assert translator(
        _legacy_payload(instrument="cmw500"), execution_id="execution-1"
    ) is None
    assert translator(
        _legacy_payload(model=None), execution_id="execution-1"
    ) is None
    assert translator(_legacy_payload(), execution_id="other-execution") is None


def test_legacy_uxm_translation_preserves_unrelated_instrument_evidence():
    payload = _legacy_payload()
    payload["required"].append({
        "requirement_id": "f64.model_loaded",
        "evidence_key": "f64.model_load",
        "requested": "runtime.smu",
        "required_evidence_level": "applied",
    })
    payload["items"].append({
        "requirement_id": "f64.model_loaded",
        "instrument": "propsim_f64",
        "evidence_key": "f64.model_load",
        "requested": "runtime.smu",
        "command_sent": "TASK:OPEN 'runtime.smu'",
        "readback": "runtime.smu",
        "exchange_ids": ["exchange-f64"],
        "evidence_level": "applied",
        "source_reference": "PROPSIM F64 ATE Manual §4.1",
        "verdict": "passed",
        "reason": "model_readback_matched",
    })

    translated = evidence_service.translate_legacy_uxm_execution_evidence(
        payload, execution_id="execution-1"
    )

    assert translated is not None
    assert translated["required"][0]["requirement_id"] == (
        "base_station.pcell.config_applied"
    )
    assert translated["required"][1] == payload["required"][1]
    assert translated["items"][1] == payload["items"][1]


def test_new_throughput_capture_records_common_key_and_identity_snapshot():
    recorder = getattr(
        evidence_service, "record_base_station_throughput_capture", None
    )
    assert callable(recorder)

    execution = TestExecution(
        id=uuid4(),
        status="running",
        executed_by="test_case_runner",
        config={},
    )
    current_execution_id.set(str(execution.id))
    evidence_service.register_required_scpi_evidence(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        evidence_key="base_station.dl_throughput",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        required_evidence_level=EvidenceLevel.OUTCOME,
    )
    exchange = ScpiExchangeRef(
        exchange_id="exchange-1",
        instrument_id="baseStation",
        operation="query",
        command="BSE:MEAS:NR5G:BTHR:DL:THR:OTA:CELL1?",
        execution_id=str(execution.id),
        capture_id="capture-1",
        sequence=0,
        result_type="response",
        response="100.0",
    )

    class Driver:
        adapter_id = "uxm"

        def capture_evidence_environment(self):
            return InstrumentEnvironment(
                instrument_id="baseStation",
                instrument="uxm",
                adapter_id="uxm",
                model="E7515B",
                firmware_version="A.18.01",
                options=("N7630",),
                captured_from_live_connection=True,
            )

        def build_p0_5_throughput_evidence(self, *, requested, throughput_exchange):
            assert throughput_exchange is exchange
            return InstrumentEvidenceItem(
                instrument="uxm",
                evidence_key="uxm.dl_throughput",
                requested=requested,
                command_sent=exchange.command,
                readback=100.0,
                exchange_ids=[exchange.exchange_id],
                evidence_level=EvidenceLevel.OUTCOME,
                source_reference="UXM User Reference §20.4.3.14",
                verdict=EvidenceVerdict.PASSED,
                reason="throughput_readback_captured",
            )

    recorder(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=Driver(),
        exchanges=[exchange],
    )

    stored = execution.config["scpi_evidence"]
    assert stored["items"][0]["evidence_key"] == "base_station.dl_throughput"
    assert stored["environments"]["baseStation"] | {
        "adapter_id": "uxm",
        "model": "E7515B",
        "firmware_version": "A.18.01",
        "options": ["N7630"],
    } == stored["environments"]["baseStation"]
