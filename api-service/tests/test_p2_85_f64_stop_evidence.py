"""P2-85：停止目标可以确认，拒绝的 GOS 不能洗成应用/rewind。"""

from uuid import uuid4
from pathlib import Path

import pytest
import yaml

from app.core.logging_config import current_execution_id
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.scpi_evidence import (
    InstrumentEnvironment, ScpiExchangeRef, EvidenceVerdict,
    build_f64_evidence, scope_for_evidence, select_f64_command_capture,
)


CLEAN = '0,"No error"'
REJECTED = '-200,"Execution error;Wrong device state for command"'


def test_manual_stop_goal_response_contract_mirrors():
    from app.main import app
    root = Path(__file__).resolve().parents[2]
    live = app.openapi()
    checked = yaml.safe_load((root / "api/openapi.yaml").read_text())
    route = "/api/v1/instruments/{category_key}/emulation-control"
    assert checked["paths"][route] == live["paths"][route]
    assert checked["components"]["schemas"]["EmulationControlResponse"] == live["components"]["schemas"]["EmulationControlResponse"]
    generated = (root / "gui/src/types/api.generated.ts").read_text()
    handwritten = (root / "gui/src/types/api.ts").read_text()
    assert route in generated and "EmulationControlResponse" in generated
    assert "export interface EmulationControlResponse" in handwritten
    assert "detail: string" in handwritten


def _driver():
    driver = RealPropsimF64Driver("ce-runtime", {})
    driver.capture_evidence_environment = lambda: InstrumentEnvironment(
        instrument_id="ce-runtime", instrument="f64", model="PROPSIM F64",
        firmware_version="8.0", captured_from_live_connection=True,
    )
    return driver


def _capture(states=("STOPPED", "STOPPED"), tail=CLEAN, error=REJECTED):
    rows = [
        ("SYST:ERR?", CLEAN), ("DIAG:SIMU:GOS", None),
        ("*OPC?", "1"), ("SYST:ERR?", error),
        *(("DIAG:SIMU:STATE?", state) for state in states),
    ]
    if tail is not None:
        rows.append(("SYST:ERR?", tail))
    return tuple(ScpiExchangeRef(
        exchange_id=f"x-{i}", instrument_id="ce-runtime",
        execution_id="execution-85", capture_id="capture-85", sequence=i,
        command=command, operation="command" if response is None else "query",
        result_type="ok" if response is None else "response", response=response,
    ) for i, (command, response) in enumerate(rows))


def _project(driver, exchanges, **kwargs):
    token = current_execution_id.set("execution-85")
    try:
        return driver.project_channel_operation_evidence(
            operation="stop_emulation", requested={"state": "STOPPED"},
            operation_succeeded=kwargs.get("succeeded", True),
            execution_mode=kwargs.get("mode", "real"), exchanges=exchanges,
        )["fields"][0]
    finally:
        current_execution_id.reset(token)


@pytest.mark.parametrize("state", ["STOPPED", "CLOSED"])
def test_rejected_gos_confirms_only_observed_idle_not_command_application(state):
    driver = _driver()
    exchanges = _capture((state, state))
    field = _project(driver, exchanges)
    assert field["status"] == "confirmed"
    assert field["applied"] == state
    assert field["provenance"] == "runtime_state"
    assert field["source_reference"].endswith("#20.4.3.14")
    assert {"x-4", "x-5", "x-6"}.issubset(field["exchange_ids"])
    # 同一 capture 的 GOS 应用判据仍拒绝，不把停止状态说成 rewind。
    token = current_execution_id.set("execution-85")
    try:
        command_proof = build_f64_evidence(
            evidence_key="f64.simulation_stop_state", requested="STOPPED",
            scope=scope_for_evidence("f64.simulation_stop_state", driver.capture_evidence_environment()),
            **select_f64_command_capture(exchanges, "f64.simulation_stop_state"),
        )
    finally:
        current_execution_id.reset(token)
    assert command_proof.verdict is EvidenceVerdict.REJECTED


@pytest.mark.parametrize("states,tail", [
    (("RUNNING", "RUNNING"), CLEAN), (("STOPPING", "STOPPING"), CLEAN),
    (("STOPPED", "RUNNING"), CLEAN), (("RUNNING", "STOPPED"), CLEAN),
    (("STOPPED", "CLOSED"), CLEAN), (("STOPPED", ""), CLEAN),
    (("STOPPED",), CLEAN), (("STOPPED", "STOPPED"), None),
    (("STOPPED", "STOPPED"), '-100,"bad query"'),
])
def test_idle_proof_rejects_unstable_missing_or_query_error_evidence(states, tail):
    field = _project(_driver(), _capture(states, tail))
    assert field["status"] == "unknown"
    assert field["applied"] is None


@pytest.mark.parametrize("key,value", [
    ("instrument_id", "other-device"), ("execution_id", "old-execution"),
    ("capture_id", "old-capture"), ("simulated", True),
    ("result_type", "empty_response"), ("sequence", 0),
])
def test_idle_proof_rejects_foreign_or_nonterminal_exchange(key, value):
    exchanges = list(_capture())
    exchanges[5] = exchanges[5].model_copy(update={key: value})
    assert _project(_driver(), tuple(exchanges))["status"] == "unknown"


@pytest.mark.asyncio
async def test_stop_boolean_rejects_conflicting_live_reads_and_no_rewind_claim(caplog):
    from tests.test_f64_state_truth_source_f64r1 import _drv
    driver, _ = _drv(state=["RUNNING", "STOPPED"], err_on={"DIAG:SIMU:GOS": REJECTED})
    assert await driver.stop_emulation() is False
    driver, _ = _drv(state="STOPPED", err_on={"DIAG:SIMU:GOS": REJECTED})
    assert await driver.stop_emulation() is True
    assert "Emulation stopped and rewound" not in caplog.text


@pytest.mark.asyncio
async def test_real_stop_recorder_preserves_error_and_separates_two_executions():
    from app.hal.scpi_evidence import record_exchange_intent, record_exchange_terminal
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        channel_emulator_operation_recorder_scope, record_channel_emulator_operation,
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
    )
    from tests.test_p2_60_channel_operation_receipt import _Db, _recorder_owner

    driver = _driver()
    driver._visa_resource = object()
    pending_errors = []

    async def write(command, **_kwargs):
        exchange_id = uuid4().hex
        record_exchange_intent(exchange_id=exchange_id, instrument_id=driver.instrument_id,
                               operation="command", command=command)
        pending_errors.append(REJECTED)
        record_exchange_terminal(exchange_id=exchange_id, result_type="ok")

    async def query(command, **_kwargs):
        exchange_id = uuid4().hex
        record_exchange_intent(exchange_id=exchange_id, instrument_id=driver.instrument_id,
                               operation="query", command=command)
        response = (pending_errors.pop(0) if pending_errors else CLEAN) if command == "SYST:ERR?" else (
            "STOPPED" if command == "DIAG:SIMU:STATE?" else "1")
        record_exchange_terminal(exchange_id=exchange_id, result_type="response", response=response)
        return response

    driver._write, driver._query = write, query
    receipt_ids = []
    for _ in range(2):
        row = TestExecution(id=uuid4(), config={})
        owner = _recorder_owner(row, _Db(row), driver=driver)
        token = current_execution_id.set(str(row.id))
        try:
            with channel_emulator_operation_recorder_scope(owner):
                assert await record_channel_emulator_operation(
                    phase="stop", operation="stop_emulation", requested={"state": "STOPPED"},
                    invoke=driver.stop_emulation,
                ) is True
        finally:
            current_execution_id.reset(token)
        receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][0]
        assert receipt["execution_id"] == str(row.id)
        assert receipt["fields"][0]["status"] == "confirmed"
        assert receipt["fields"][0]["provenance"] == "runtime_state"
        assert len(receipt["error_queue_exchange_ids"]) >= 3
        receipt_ids.append(receipt["receipt_id"])
    assert receipt_ids[0] != receipt_ids[1]


@pytest.mark.parametrize("state,expected_status", [("STOPPED", None), ("CLOSED", "invalid")])
def test_actual_f64_idle_projection_reaches_formal_terminal_without_upgrading_closed(state, expected_status):
    from tests.test_p2_60_channel_operation_receipt import _v2_terminal_projection_fixture, _redigest
    from app.services.channel_emulator_operation_receipt import channel_emulator_operation_receipt_chain_digest
    from app.services.execution_evidence_outcome import _channel_emulator_terminal_projection
    driver = _driver()
    execution, terminal, receipts = _v2_terminal_projection_fixture(driver_override=driver)
    exchanges = tuple(item.model_copy(update={"execution_id": "execution-1"})
                      for item in _capture((state, state)))
    token = current_execution_id.set("execution-1")
    try:
        projection = driver.project_channel_operation_evidence(
            operation="stop_emulation", requested={"state": "STOPPED"},
            operation_succeeded=True, exchanges=exchanges, execution_mode="real",
        )
    finally:
        current_execution_id.reset(token)
    receipts[0].update(projection)
    _redigest(receipts[0])
    terminal["operation_receipts_digest"] = channel_emulator_operation_receipt_chain_digest(receipts)
    _redigest(terminal)
    status, reason = _channel_emulator_terminal_projection(
        execution.config, execution_id=execution.id, pipeline_status=execution.status,
    )
    assert status == expected_status
    if state == "CLOSED":
        assert "safe-idle receipt fields are invalid" in reason
    else:
        assert reason is None
