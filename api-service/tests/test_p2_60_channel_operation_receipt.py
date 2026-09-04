"""P2-60：vendor-neutral Channel Operation Receipt。"""

from __future__ import annotations

from copy import deepcopy
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml

from app.hal.base_station_compatibility import canonical_payload_digest


API_SERVICE = Path(__file__).resolve().parents[1]


class _Plan:
    def __init__(self, *, planned: bool = True) -> None:
        self.load_mode_planned = planned
        self._planned = planned

    def planned(self, _operation: str) -> bool:
        return self._planned

    def rejection(self, operation: str) -> str:
        return f"operation {operation} is unavailable"


class _ProjectingDriver:
    def __init__(self, *, simulated: bool = False) -> None:
        self.simulated = simulated
        self.calls = 0

    def project_channel_operation_evidence(self, **kwargs):
        requested = kwargs["requested"]
        exchanges = kwargs["exchanges"]
        return {
            "fields": [
                {
                    "field": key,
                    "requested": value,
                    "applied": None,
                    "applied_present": False,
                    "status": "unknown",
                    "provenance": "simulated" if self.simulated else "command_error_queue",
                    "exchange_ids": [],
                    "source_reference": None,
                }
                for key, value in requested.items()
            ],
            "exchange_ids": [item.exchange_id for item in exchanges],
            "error_queue_exchange_ids": [],
        }


def _recorder_owner(
    row,
    db,
    *,
    driver=None,
    plan=None,
    execution_mode: str = "real",
):
    from app.services.channel_emulator_operation_receipt import (
        ChannelEmulatorOperationRecorderOwner,
    )

    return ChannelEmulatorOperationRecorderOwner(
        db=db,
        execution_pk=row.id,
        execution_id=str(row.id),
        session_id="session-runtime",
        operation_scope=f"formal-case:{row.id}",
        measurement_attempt_id="attempt-runtime",
        binding_digest="b" * 64,
        binding_freeze_digest="f" * 64,
        plan_digest="p" * 64,
        asset_digest="a" * 64,
        lease_id="lease-runtime",
        instrument_id="ce-runtime",
        adapter_id="propsim_f64" if execution_mode == "real" else "mock_channel_emulator",
        execution_mode=execution_mode,
        plan=plan or _Plan(),
        driver=driver or _ProjectingDriver(simulated=execution_mode == "simulated"),
    )


@pytest.mark.asyncio
async def test_measure_session_binds_attempt_to_channel_receipt_owner_before_operation(
    monkeypatch,
):
    """MEASURE creates its attempt after CE acquire, so both owners must be rebound."""

    from app.services import base_station_execution_session as module

    recorder = SimpleNamespace(measurement_attempt_id=None)
    lease_outcome = SimpleNamespace(
        measurement_attempt_id=None,
        base_station_release=None,
    )
    marked: list[bool] = []

    class _ScopeOutcome:
        def __init__(self):
            self.lease_outcome = lease_outcome

        def bind_measurement_attempt_id(self, attempt_id: str) -> None:
            lease_outcome.measurement_attempt_id = attempt_id
            recorder.measurement_attempt_id = attempt_id

        def mark_operation_result(self, succeeded: bool) -> None:
            marked.append(succeeded)

    @asynccontextmanager
    async def _scope(*_args, **_kwargs):
        yield _ScopeOutcome()
        lease_outcome.base_station_release = object()

    monkeypatch.setattr(module, "channel_emulator_execution_scope", _scope)
    monkeypatch.setattr(
        module,
        "begin_execution_base_station_measurement",
        lambda *_args, **_kwargs: "attempt-1",
    )
    monkeypatch.setattr(
        module,
        "persist_execution_base_station_release",
        lambda *_args, **_kwargs: "completed",
    )
    monkeypatch.setattr(module, "_get_hal_service", lambda: SimpleNamespace())
    monkeypatch.setattr(module, "_get_base_station_driver", lambda: object())

    execution = SimpleNamespace(
        id="execution-1",
        config={
            "channel_emulator_binding_freeze": {},
            "channel_emulator_execution_plan_freeze": {},
        },
    )

    async def _operation():
        assert lease_outcome.measurement_attempt_id == "attempt-1"
        assert recorder.measurement_attempt_id == "attempt-1"
        return module.BaseStationSessionOperationResult(value="ok", succeeded=True)

    assert await module.run_base_station_execution_session(
        SimpleNamespace(),
        execution,
        SimpleNamespace(),
        purpose="formal-case:execution-1",
        step_type="MIMO_OTA_MEASURE",
        validate_before_remote=lambda _hal: None,
        operation=_operation,
    ) == "ok"
    assert marked == [True]


def test_scope_outcome_binds_attempt_to_both_lease_and_receipt_owner():
    from app.services.channel_emulator_execution_session import (
        ChannelEmulatorExecutionScopeOutcome,
        ChannelEmulatorExecutionSessionError,
    )

    lease = SimpleNamespace(measurement_attempt_id=None)
    recorder = SimpleNamespace(measurement_attempt_id=None)
    outcome = ChannelEmulatorExecutionScopeOutcome(
        lease,
        recorder_owner=recorder,
    )

    outcome.bind_measurement_attempt_id("attempt-1")

    assert lease.measurement_attempt_id == "attempt-1"
    assert recorder.measurement_attempt_id == "attempt-1"
    with pytest.raises(ChannelEmulatorExecutionSessionError, match="rebound"):
        outcome.bind_measurement_attempt_id("attempt-2")


def _field(
    *,
    status: str = "confirmed",
    provenance: str = "authoritative_readback",
    simulated: bool = False,
) -> dict:
    return {
        "field": "loaded_file",
        "requested": "scenario.smu",
        "applied": "scenario.smu" if status in {"applied", "confirmed"} else None,
        "applied_present": status in {"applied", "confirmed"},
        "status": status,
        "provenance": "simulated" if simulated else provenance,
        "exchange_ids": ["exchange-1"] if status != "unavailable" else [],
        "source_reference": (
            None
            if simulated or status == "unavailable"
            else "notebooklm:982222b7-4953-46cd-9949-00fa97882353:Propsim User Reference#20.4.3"
        ),
    }


def _receipt(
    *,
    receipt_id: str = "receipt-1",
    sequence: int = 0,
    execution_mode: str = "real",
    terminal_state: str = "completed",
    operation_succeeded: bool | None = True,
    fields: list[dict] | None = None,
    execution_id: str = "execution-1",
) -> dict:
    simulated = execution_mode == "simulated"
    payload = {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "session_id": "session-1",
        "operation_scope": "formal-case:execution-1",
        "execution_id": execution_id,
        "measurement_attempt_id": "attempt-1",
        "binding_digest": "b" * 64,
        "binding_freeze_digest": "f" * 64,
        "plan_digest": "p" * 64,
        "asset_digest": "a" * 64,
        "lease_id": "lease-1",
        "instrument_id": "ce-runtime",
        "adapter_id": "propsim_f64",
        "execution_mode": execution_mode,
        "sequence": sequence,
        "phase": "load",
        "operation": "load_channel",
        "invocation_id": f"invocation-{sequence}",
        "terminal_state": terminal_state,
        "operation_succeeded": operation_succeeded,
        "simulated": simulated,
        "fields": fields if fields is not None else [_field(simulated=simulated)],
        "exchange_ids": ["exchange-1", "exchange-error"],
        "error_queue_exchange_ids": ["exchange-error"],
        "error_type": None,
    }
    if terminal_state == "failed":
        payload["error_type"] = "RuntimeError"
    elif terminal_state == "cancelled":
        payload["error_type"] = "CancelledError"
    return {**payload, "digest": canonical_payload_digest(payload)}


def test_receipt_schema_is_strict_and_digest_covers_original_payload():
    from app.services.channel_emulator_operation_receipt import (
        validate_channel_emulator_operation_receipt,
    )

    receipt = _receipt()
    assert validate_channel_emulator_operation_receipt(receipt) == receipt

    extra = {**receipt, "server_guess": True}
    with pytest.raises(ValueError, match="malformed"):
        validate_channel_emulator_operation_receipt(extra)

    tampered = {**receipt, "instrument_id": "another-instrument"}
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_channel_emulator_operation_receipt(tampered)


@pytest.mark.parametrize(
    ("receipt", "message"),
    [
        (
            _receipt(
                execution_mode="simulated",
                fields=[_field(status="confirmed")],
            ),
            "simulated.*confirmed",
        ),
        (
            _receipt(
                terminal_state="failed",
                operation_succeeded=True,
            ),
            "failed.*successful",
        ),
        (
            _receipt(
                fields=[
                    _field(status="unavailable", provenance="unavailable")
                ],
            ),
            "unavailable.*exchange",
        ),
    ],
)
def test_receipt_rejects_contradictory_success_claims(receipt, message):
    from app.services.channel_emulator_operation_receipt import (
        validate_channel_emulator_operation_receipt,
    )

    receipt["digest"] = canonical_payload_digest(
        {key: value for key, value in receipt.items() if key != "digest"}
    )
    with pytest.raises(ValueError, match=message):
        validate_channel_emulator_operation_receipt(receipt)


def test_receipt_chain_digest_requires_canonical_contiguous_order():
    from app.services.channel_emulator_operation_receipt import (
        channel_emulator_operation_receipt_chain_digest,
    )

    first = _receipt(receipt_id="receipt-1", sequence=0)
    second = _receipt(receipt_id="receipt-2", sequence=1)
    digest = channel_emulator_operation_receipt_chain_digest([first, second])

    assert digest == canonical_payload_digest(
        {
            "schema_version": 1,
            "receipt_digests": [first["digest"], second["digest"]],
        }
    )
    with pytest.raises(ValueError, match="sequence"):
        channel_emulator_operation_receipt_chain_digest([second, first])
    with pytest.raises(ValueError, match="session"):
        foreign = deepcopy(second)
        foreign["session_id"] = "session-2"
        foreign["digest"] = canonical_payload_digest(
            {key: value for key, value in foreign.items() if key != "digest"}
        )
        channel_emulator_operation_receipt_chain_digest([first, foreign])

    with pytest.raises(ValueError, match="identity"):
        foreign = deepcopy(second)
        foreign["lease_id"] = "lease-2"
        foreign["digest"] = canonical_payload_digest(
            {key: value for key, value in foreign.items() if key != "digest"}
        )
        channel_emulator_operation_receipt_chain_digest([first, foreign])


def test_unavailable_receipt_cannot_claim_a_successful_operation():
    from app.services.channel_emulator_operation_receipt import (
        validate_channel_emulator_operation_receipt,
    )

    receipt = _receipt(
        fields=[_field(status="unavailable", provenance="unavailable")]
    )
    receipt["exchange_ids"] = []
    receipt["error_queue_exchange_ids"] = []
    receipt["digest"] = canonical_payload_digest(
        {key: value for key, value in receipt.items() if key != "digest"}
    )

    with pytest.raises(ValueError, match="unavailable.*successful"):
        validate_channel_emulator_operation_receipt(receipt)


class _LockedQuery:
    def __init__(self, row) -> None:
        self.row = row

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def one_or_none(self):
        return self.row


class _Db:
    def __init__(self, row) -> None:
        self.row = row
        self.commits = 0

    def query(self, _model):
        return _LockedQuery(self.row)

    def commit(self) -> None:
        self.commits += 1


def test_persist_receipt_is_append_only_idempotent_and_conflict_safe():
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        ChannelEmulatorOperationReceiptError,
        persist_channel_emulator_operation_receipt,
    )

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    receipt = _receipt(execution_id=str(row.id))

    persist_channel_emulator_operation_receipt(db, row.id, receipt)
    assert row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY] == [receipt]
    assert db.commits == 1

    persist_channel_emulator_operation_receipt(db, row.id, receipt)
    assert row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY] == [receipt]
    assert db.commits == 1

    conflicting = deepcopy(receipt)
    conflicting["operation_scope"] = "adhoc:execution-1"
    conflicting["digest"] = canonical_payload_digest(
        {key: value for key, value in conflicting.items() if key != "digest"}
    )
    with pytest.raises(ChannelEmulatorOperationReceiptError, match="already has different"):
        persist_channel_emulator_operation_receipt(db, row.id, conflicting)


def test_persist_receipt_rejects_wrong_execution_and_malformed_existing_chain():
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        ChannelEmulatorOperationReceiptError,
        persist_channel_emulator_operation_receipt,
    )

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    wrong_execution = _receipt(execution_id="execution-2")
    wrong_execution["execution_id"] = "execution-2"
    wrong_execution["digest"] = canonical_payload_digest(
        {key: value for key, value in wrong_execution.items() if key != "digest"}
    )
    with pytest.raises(ChannelEmulatorOperationReceiptError, match="execution identity"):
        persist_channel_emulator_operation_receipt(db, row.id, wrong_execution)

    row.config = {CE_OPERATION_RECEIPTS_CONFIG_KEY: {"not": "a list"}}
    with pytest.raises(ChannelEmulatorOperationReceiptError, match="chain is malformed"):
        persist_channel_emulator_operation_receipt(
            db,
            row.id,
            _receipt(execution_id=str(row.id)),
        )


@pytest.mark.asyncio
async def test_recorder_rejects_calls_outside_the_execution_owned_scope():
    from app.services.channel_emulator_operation_receipt import (
        ChannelEmulatorOperationReceiptError,
        record_channel_emulator_operation,
    )

    invoked = False

    async def invoke():
        nonlocal invoked
        invoked = True
        return True

    with pytest.raises(ChannelEmulatorOperationReceiptError, match="no execution-session owner"):
        await record_channel_emulator_operation(
            phase="configure",
            operation="set_path_loss",
            requested={"path_loss_db": 12.0},
            invoke=invoke,
        )
    assert invoked is False


@pytest.mark.asyncio
async def test_unplanned_operation_persists_unavailable_without_io():
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        ChannelEmulatorOperationReceiptError,
        channel_emulator_operation_recorder_scope,
        record_channel_emulator_operation,
    )

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    driver = _ProjectingDriver()
    owner = _recorder_owner(row, db, driver=driver, plan=_Plan(planned=False))

    async def invoke():
        driver.calls += 1
        return True

    with channel_emulator_operation_recorder_scope(owner):
        with pytest.raises(ChannelEmulatorOperationReceiptError, match="unavailable"):
            await record_channel_emulator_operation(
                phase="configure",
                operation="set_path_loss",
                requested={"path_loss_db": 12.0},
                invoke=invoke,
            )

    assert driver.calls == 0
    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][0]
    assert receipt["terminal_state"] == "rejected"
    assert receipt["operation_succeeded"] is False
    assert receipt["fields"][0]["status"] == "unavailable"
    assert receipt["exchange_ids"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "error", "terminal_state", "operation_succeeded", "error_type"),
    [
        (True, None, "completed", True, None),
        (False, None, "rejected", False, None),
        (None, TimeoutError("late"), "failed", None, "TimeoutError"),
        (None, RuntimeError("broken"), "failed", None, "RuntimeError"),
        (None, asyncio.CancelledError(), "cancelled", None, "CancelledError"),
    ],
)
async def test_recorder_classifies_boolean_error_timeout_and_cancellation(
    result,
    error,
    terminal_state,
    operation_succeeded,
    error_type,
):
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        channel_emulator_operation_recorder_scope,
        record_channel_emulator_operation,
    )

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    owner = _recorder_owner(row, db)

    async def invoke():
        if error is not None:
            raise error
        return result

    with channel_emulator_operation_recorder_scope(owner):
        if error is None:
            assert await record_channel_emulator_operation(
                phase="configure",
                operation="set_path_loss",
                requested={"path_loss_db": 12.0},
                invoke=invoke,
            ) is result
        else:
            with pytest.raises(type(error)):
                await record_channel_emulator_operation(
                    phase="configure",
                    operation="set_path_loss",
                    requested={"path_loss_db": 12.0},
                    invoke=invoke,
                )

    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][0]
    assert receipt["terminal_state"] == terminal_state
    assert receipt["operation_succeeded"] is operation_succeeded
    assert receipt["error_type"] == error_type
    assert receipt["session_id"] == owner.session_id
    assert receipt["execution_id"] == owner.execution_id
    assert receipt["measurement_attempt_id"] == owner.measurement_attempt_id
    assert receipt["lease_id"] == owner.lease_id
    assert receipt["instrument_id"] == owner.instrument_id
    assert receipt["binding_digest"] == owner.binding_digest
    assert receipt["plan_digest"] == owner.plan_digest


@pytest.mark.asyncio
async def test_recorder_rejects_foreign_capture_execution_or_instrument():
    from app.core.logging_config import current_execution_id
    from app.hal.scpi_evidence import record_exchange_intent, record_exchange_terminal
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        ChannelEmulatorOperationReceiptError,
        channel_emulator_operation_recorder_scope,
        record_channel_emulator_operation,
    )

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    owner = _recorder_owner(row, db)
    token = current_execution_id.set("foreign-execution")

    async def invoke():
        record_exchange_intent(
            exchange_id="exchange-foreign",
            instrument_id="another-instrument",
            operation="write",
            command="REDACTED",
        )
        record_exchange_terminal(
            exchange_id="exchange-foreign",
            result_type="ok",
        )
        return True

    try:
        with channel_emulator_operation_recorder_scope(owner):
            with pytest.raises(ChannelEmulatorOperationReceiptError, match="identity"):
                await record_channel_emulator_operation(
                    phase="configure",
                    operation="set_path_loss",
                    requested={"path_loss_db": 12.0},
                    invoke=invoke,
                )
    finally:
        current_execution_id.reset(token)

    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][0]
    assert receipt["terminal_state"] == "failed"
    assert receipt["operation_succeeded"] is None
    assert receipt["error_type"] == "ExchangeIdentityMismatch"
    assert receipt["exchange_ids"] == []


@pytest.mark.asyncio
async def test_mock_receipt_is_simulated_unknown_and_never_confirmed():
    from app.hal.channel_emulator import MockChannelEmulator
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        channel_emulator_operation_recorder_scope,
        record_channel_emulator_operation,
    )

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    driver = MockChannelEmulator("ce-runtime", {"model": "Mock Channel Emulator"})
    owner = _recorder_owner(
        row,
        db,
        driver=driver,
        execution_mode="simulated",
    )

    async def invoke():
        return True

    with channel_emulator_operation_recorder_scope(owner):
        assert await record_channel_emulator_operation(
            phase="configure",
            operation="set_path_loss",
            requested={"path_loss_db": 12.0},
            invoke=invoke,
        ) is True

    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][0]
    assert receipt["simulated"] is True
    assert {field["status"] for field in receipt["fields"]} == {"unknown"}
    assert {field["provenance"] for field in receipt["fields"]} == {"simulated"}


@pytest.mark.asyncio
async def test_transport_release_receipt_uses_actual_release_result_without_exchange():
    from app.models.test_plan import TestExecution
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        channel_emulator_operation_recorder_scope,
        record_channel_emulator_operation,
    )

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    owner = _recorder_owner(row, db)
    release_calls = 0

    async def release_to_local_control():
        nonlocal release_calls
        release_calls += 1
        return True

    with channel_emulator_operation_recorder_scope(owner):
        assert await record_channel_emulator_operation(
            phase="release",
            operation="transport_release",
            requested={"control_mode": "local"},
            invoke=release_to_local_control,
        ) is True

    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][0]
    assert release_calls == 1
    assert receipt["exchange_ids"] == []
    assert receipt["fields"] == [
        {
            "field": "control_mode",
            "requested": "local",
            "applied": "local",
            "applied_present": True,
            "status": "confirmed",
            "provenance": "transport_release",
            "exchange_ids": [],
            "source_reference": "instrument_test_lease.release_to_local_control",
        }
    ]


@pytest.mark.asyncio
async def test_success_cannot_swallow_receipt_persistence_failure():
    from app.models.test_plan import TestExecution
    from app.services import channel_emulator_operation_receipt as module

    row = TestExecution(id=uuid4(), config={})
    db = _Db(row)
    owner = _recorder_owner(row, db)

    async def invoke():
        return True

    original = module.persist_channel_emulator_operation_receipt
    module.persist_channel_emulator_operation_receipt = lambda *_args: (_ for _ in ()).throw(
        OSError("database unavailable")
    )
    try:
        with module.channel_emulator_operation_recorder_scope(owner):
            with pytest.raises(OSError, match="database unavailable"):
                await module.record_channel_emulator_operation(
                    phase="configure",
                    operation="set_path_loss",
                    requested={"path_loss_db": 12.0},
                    invoke=invoke,
                )
    finally:
        module.persist_channel_emulator_operation_receipt = original


def test_execution_bound_effectful_calls_use_the_common_recorder():
    sources = {
        "app/services/channel_generation/asc_strategy.py": (
            "await self.emulator.load_channel(",
        ),
        "app/services/channel_generation/external_asc_strategy.py": (
            "await self.emulator.load_channel(",
        ),
        "app/services/channel_generation/gcm_strategy.py": (
            "await self.emulator.load_channel(",
        ),
        "app/services/mimo_ota/executors/measure.py": (
            "await emulator.ensure_topology(",
            "await emulator.measure_input(",
            "await emulator.set_output_level_dbm(",
            "await emulator.set_passthrough_mode(",
            "await emulator.start_emulation(",
            "await emulator.set_output_gain(",
            "await emulator.set_baseband_power(",
            "await emulator.set_crest_factor(",
        ),
        "app/services/input_level_controller.py": (
            "await self._ce.measure_input(",
            "await self._ce.get_input_level_limits(",
            "await self._ce.get_group_clipping(",
            "await self._ce.get_system_status(",
            "await self._ce.autoset_inputs(",
            "await self._ce.set_input_measurement_mode(",
            "await self._ce.set_burst_trigger_level(",
        ),
    }
    for relative_path, forbidden_calls in sources.items():
        source = (API_SERVICE / relative_path).read_text()
        recorder_token = (
            "record_channel_emulator_operation"
            if relative_path.endswith("measure.py")
            else "_invoke_channel_operation"
        )
        assert recorder_token in source, relative_path
        for forbidden in forbidden_calls:
            assert forbidden not in source, f"{relative_path}: {forbidden}"

    measure_source = (
        API_SERVICE / "app/services/mimo_ota/executors/measure.py"
    ).read_text()
    assert measure_source.count(
        "operation_recorder=record_channel_emulator_operation"
    ) >= 3


def test_f64_receipt_strengthens_only_same_invocation_authoritative_state():
    from app.core.logging_config import current_execution_id
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.scpi_evidence import InstrumentEnvironment, ScpiExchangeRef

    driver = RealPropsimF64Driver("ce-live", {})
    driver.capture_evidence_environment = lambda: InstrumentEnvironment(
        instrument_id="ce-live",
        instrument="f64",
        model="PROPSIM F64",
        firmware_version="v1.0",
        captured_from_live_connection=True,
    )

    def exchange(
        exchange_id: str,
        sequence: int,
        command: str,
        *,
        operation: str,
        result_type: str,
        response: str | None = None,
    ) -> ScpiExchangeRef:
        return ScpiExchangeRef(
            exchange_id=exchange_id,
            instrument_id="ce-live",
            operation=operation,
            command=command,
            execution_id="execution-1",
            capture_id="capture-1",
            sequence=sequence,
            result_type=result_type,
            response=response,
        )

    exchanges = (
        exchange(
            "preclear", 0, "SYST:ERR?", operation="query",
            result_type="response", response='0,"No error"',
        ),
        exchange(
            "go", 1, "DIAG:SIMU:GO", operation="command", result_type="ok",
        ),
        exchange(
            "opc", 2, "*OPC?", operation="query",
            result_type="response", response="1",
        ),
        exchange(
            "error", 3, "SYST:ERR?", operation="query",
            result_type="response", response='0,"No error"',
        ),
        exchange(
            "state", 4, "DIAG:SIMU:STATE?", operation="query",
            result_type="response", response="RUNNING",
        ),
    )
    token = current_execution_id.set("execution-1")
    try:
        confirmed = driver.project_channel_operation_evidence(
            operation="start_emulation",
            requested={"state": "RUNNING"},
            operation_succeeded=True,
            exchanges=exchanges,
            execution_mode="real",
        )
        missing_readback = driver.project_channel_operation_evidence(
            operation="start_emulation",
            requested={"state": "RUNNING"},
            operation_succeeded=True,
            exchanges=exchanges[:-1],
            execution_mode="real",
        )
    finally:
        current_execution_id.reset(token)
    assert confirmed["fields"][0]["status"] == "confirmed"
    assert confirmed["fields"][0]["provenance"] == "authoritative_readback"
    assert confirmed["fields"][0]["applied"] == "RUNNING"
    assert confirmed["fields"][0]["exchange_ids"] == [
        "preclear", "go", "opc", "error", "state"
    ]
    assert confirmed["error_queue_exchange_ids"] == ["preclear", "error"]

    assert missing_readback["fields"][0]["status"] == "unknown"
    assert missing_readback["fields"][0]["applied"] is None


@pytest.mark.parametrize(
    ("operation", "requested", "command", "readback_query", "readback"),
    [
        (
            "load_channel",
            {
                "load_mode": "external_waveform",
                "model_name": "external-asc-bundle",
                "waveform_dir": "/tmp/asc-source",
            },
            "CALCulate:FILTer:FILE D:\\User Emulations\\runtime_emulation.smu",
            "DIAGnostic:SIMUlation:MODel:STATE?",
            "READY",
        ),
        (
            "load_channel",
            {"load_mode": "native_model", "emulation_file": "D:\\Models\\case.smu"},
            "CALCulate:FILTer:FILE D:\\Models\\case.smu",
            "DIAGnostic:SIMUlation:MODel:STATE?",
            "READY",
        ),
        (
            "set_output_gain",
            {"output_port": 1, "gain_db": -3.0},
            "OUTPut:GAIN:CHannel 1,-3.0",
            "OUTPut:GAIN:CHannel? 1",
            "-3.0",
        ),
        (
            "set_baseband_power",
            {"reference_dbm": -12.0},
            "INPut:LEVel:AMPLitude:CHannel 1,-12.0",
            "INPut:LEVel:AMPLitude:CHannel? 1",
            "-12.0",
        ),
        (
            "set_crest_factor",
            {"input_port": 1, "crest_db": 8.0},
            "INPut:CRESt:SET 1,8.0",
            "INPut:CRESt:GET? 1",
            "8.0",
        ),
    ],
)
def test_f64_receipt_projects_existing_authoritative_parameter_readback(
    operation, requested, command, readback_query, readback
):
    from app.core.logging_config import current_execution_id
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.scpi_evidence import InstrumentEnvironment, ScpiExchangeRef

    driver = RealPropsimF64Driver("ce-live", {})
    driver.capture_evidence_environment = lambda: InstrumentEnvironment(
        instrument_id="ce-live",
        instrument="f64",
        model="PROPSIM F64",
        firmware_version="v1.0",
        captured_from_live_connection=True,
    )

    def exchange(exchange_id, sequence, text, *, kind, result_type, response=None):
        return ScpiExchangeRef(
            exchange_id=exchange_id,
            instrument_id="ce-live",
            operation=kind,
            command=text,
            execution_id="execution-1",
            capture_id="capture-1",
            sequence=sequence,
            result_type=result_type,
            response=response,
        )

    exchanges = (
        exchange(
            "preclear", 0, "SYST:ERR?", kind="query",
            result_type="response", response='0,"No error"',
        ),
        exchange("write", 1, command, kind="command", result_type="ok"),
        *(
            (
                exchange(
                    "opc", 2, "*OPC?", kind="query",
                    result_type="response", response="1",
                ),
            )
            if operation == "load_channel"
            else ()
        ),
        exchange(
            "error", 3 if operation == "load_channel" else 2,
            "SYST:ERR?", kind="query",
            result_type="response", response='0,"No error"',
        ),
        exchange(
            "readback", 4 if operation == "load_channel" else 3,
            readback_query, kind="query",
            result_type="response", response=readback,
        ),
        *(
            (
                exchange(
                    "state", 5, "DIAGnostic:SIMUlation:STATE?", kind="query",
                    result_type="response", response="STOPPED",
                ),
            )
            if operation == "load_channel"
            else ()
        ),
    )
    token = current_execution_id.set("execution-1")
    try:
        projected = driver.project_channel_operation_evidence(
            operation=operation,
            requested=requested,
            operation_succeeded=True,
            exchanges=exchanges,
            execution_mode="real",
        )
    finally:
        current_execution_id.reset(token)

    confirmed = [field for field in projected["fields"] if field["status"] == "confirmed"]
    assert confirmed
    assert confirmed[0]["field"] == {
        "load_channel": "emulation_file",
        "set_output_gain": "gain_db",
        "set_baseband_power": "reference_dbm",
        "set_crest_factor": "crest_db",
    }[operation]
    if operation == "load_channel":
        assert confirmed[0]["applied"] == command.split(maxsplit=1)[1]
    assert confirmed[0]["provenance"] == "authoritative_readback"
    assert confirmed[0]["exchange_ids"] == (
        ["preclear", "write", "opc", "error", "readback", "state"]
        if operation == "load_channel"
        else ["preclear", "write", "error", "readback"]
    )
    assert projected["error_queue_exchange_ids"] == ["preclear", "error"]


@pytest.mark.parametrize(
    ("operation", "requested", "query", "response", "expected_applied"),
    [
        (
            "measure_input",
            {"measurement": {"input_port": 2, "measurement_time_s": 1.0}},
            "INP:LEV:MEAS? 2,1.0",
            "-21.4,7.5",
            {
                "input_port": 2,
                "measurement_time_s": 1.0,
                "avg_dbm": -21.4,
                "crest_db": 7.5,
            },
        ),
        (
            "get_input_level_limits",
            {"limits": {"input_port": 2}},
            "INP:LEV:AMP:LIM? 2",
            "-23,0",
            {"input_port": 2, "lower_dbm": -23.0, "upper_dbm": 0.0},
        ),
        (
            "get_group_clipping",
            {"clipping": {"group_num": 1, "reset": True}},
            "GROup:CLIpping:GET? 1,1",
            "0",
            {"group_num": 1, "reset": True, "per_mille": 0.0},
        ),
        (
            "get_system_status",
            {"system_status": "channel_emulator"},
            "SYST:STAT?",
            "0,Input cut-off",
            {"healthy": False, "warnings": ["Input cut-off"]},
        ),
    ],
)
def test_f64_receipt_projects_same_invocation_authoritative_observation(
    operation, requested, query, response, expected_applied
):
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.scpi_evidence import InstrumentEnvironment, ScpiExchangeRef

    driver = RealPropsimF64Driver("ce-live", {})
    driver.capture_evidence_environment = lambda: InstrumentEnvironment(
        instrument_id="ce-live",
        instrument="f64",
        model="PROPSIM F64",
        firmware_version="v1.0",
        captured_from_live_connection=True,
    )
    exchange = ScpiExchangeRef(
        exchange_id="observation",
        instrument_id="ce-live",
        operation="query",
        command=query,
        execution_id="execution-1",
        capture_id="capture-1",
        sequence=0,
        result_type="response",
        response=response,
    )

    projected = driver.project_channel_operation_evidence(
        operation=operation,
        requested=requested,
        operation_succeeded=True,
        exchanges=(exchange,),
        execution_mode="real",
    )

    assert projected["fields"] == [
        {
            "field": next(iter(requested)),
            "requested": next(iter(requested.values())),
            "applied": expected_applied,
            "applied_present": True,
            "status": "confirmed",
            "provenance": "authoritative_readback",
            "exchange_ids": ["observation"],
            "source_reference": projected["fields"][0]["source_reference"],
        }
    ]
    assert "Propsim User Reference" in projected["fields"][0]["source_reference"]

    wrong_query = exchange.model_copy(update={"command": query + " 99"})
    rejected = driver.project_channel_operation_evidence(
        operation=operation,
        requested=requested,
        operation_succeeded=True,
        exchanges=(wrong_query,),
        execution_mode="real",
    )
    assert rejected["fields"][0]["status"] == "unknown"


def test_f64_measurement_without_crest_readback_stays_unknown():
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.scpi_evidence import InstrumentEnvironment, ScpiExchangeRef

    driver = RealPropsimF64Driver("ce-live", {})
    driver.capture_evidence_environment = lambda: InstrumentEnvironment(
        instrument_id="ce-live",
        instrument="f64",
        model="PROPSIM F64",
        firmware_version="v1.0",
        captured_from_live_connection=True,
    )
    exchange = ScpiExchangeRef(
        exchange_id="observation",
        instrument_id="ce-live",
        operation="query",
        command="INP:LEV:MEAS? 2,1.0",
        execution_id="execution-1",
        capture_id="capture-1",
        sequence=0,
        result_type="response",
        response="-21.4",
    )

    projected = driver.project_channel_operation_evidence(
        operation="measure_input",
        requested={
            "measurement": {"input_port": 2, "measurement_time_s": 1.0}
        },
        operation_succeeded=True,
        exchanges=(exchange,),
        execution_mode="real",
    )

    assert projected["fields"][0]["field"] == "measurement"
    assert projected["fields"][0]["status"] == "unknown"
    assert projected["fields"][0]["applied_present"] is False

def test_f64_receipt_confirms_only_complete_cross_checked_topology_readback():
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.scpi_evidence import InstrumentEnvironment, ScpiExchangeRef

    driver = RealPropsimF64Driver("ce-live", {})
    driver.capture_evidence_environment = lambda: InstrumentEnvironment(
        instrument_id="ce-live",
        instrument="f64",
        model="PROPSIM F64",
        firmware_version="v1.0",
        captured_from_live_connection=True,
    )

    def exchange(sequence, query, response):
        return ScpiExchangeRef(
            exchange_id=f"topology-{sequence}",
            instrument_id="ce-live",
            operation="query",
            command=query,
            execution_id="execution-1",
            capture_id="capture-1",
            sequence=sequence,
            result_type="response",
            response=response,
        )

    exchanges = (
        exchange(0, "DIAG:SIMU:STATE?", "STOPPED"),
        exchange(1, "DIAG:SIMU:MODEL:INFO?", "2,4,2"),
        exchange(2, "GROUP:GET?", "1"),
        exchange(3, "GROUP:CHANNELS:GET? 1", "1,2,3,4"),
        exchange(4, "GROUP:INPUTS:GET? 1", "1,2"),
        exchange(5, "GROUP:OUTPUTS:GET? 1", "1,2"),
    )

    confirmed = driver.project_channel_operation_evidence(
        operation="ensure_topology",
        requested={"topology": "active_ports"},
        operation_succeeded=True,
        exchanges=exchanges,
        execution_mode="real",
    )
    assert confirmed["fields"][0]["status"] == "confirmed"
    assert confirmed["fields"][0]["applied"] == {
        "inputs": [1, 2],
        "outputs": [1, 2],
        "channels": [1, 2, 3, 4],
    }
    assert confirmed["fields"][0]["exchange_ids"] == [
        f"topology-{index}" for index in range(6)
    ]

    incomplete = driver.project_channel_operation_evidence(
        operation="ensure_topology",
        requested={"topology": "active_ports"},
        operation_succeeded=True,
        exchanges=exchanges[:-1],
        execution_mode="real",
    )
    assert incomplete["fields"][0]["status"] == "unknown"


def _v2_terminal_projection_fixture(*, execution_mode: str = "real"):
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        channel_emulator_operation_receipt_chain_digest,
    )
    from app.hal.channel_emulator import MockChannelEmulator
    from tests.test_p2_59_3_channel_emulator_session import (
        _RealCe,
        _execution_with_ce_evidence,
        _frozen_binding_for_driver,
        _frozen_plan,
    )

    driver = (
        MockChannelEmulator("ce-runtime", {"model": "Mock Channel Emulator"})
        if execution_mode == "simulated"
        else _RealCe()
    )
    binding = _frozen_binding_for_driver(driver, execution_mode=execution_mode)
    plan = _frozen_plan(driver)
    session_id = "session-v2"
    lease_id = "lease-v2"
    instrument_id = "ce-runtime"
    simulated = execution_mode == "simulated"

    def operation_receipt(
        *,
        receipt_id: str,
        sequence: int,
        phase: str,
        operation: str,
        field: str,
        requested,
        applied,
        provenance: str,
        exchange_ids: list[str],
        source_reference: str,
    ) -> dict:
        payload = {
            "schema_version": 1,
            "receipt_id": receipt_id,
            "session_id": session_id,
            "operation_scope": "formal-case:execution-1",
            "execution_id": "execution-1",
            "measurement_attempt_id": "attempt-v2",
            "binding_digest": binding["binding_digest"],
            "binding_freeze_digest": binding["digest"],
            "plan_digest": plan["digest"],
            "asset_digest": None,
            "lease_id": lease_id,
            "instrument_id": instrument_id,
            "adapter_id": plan["adapter_id"],
            "execution_mode": execution_mode,
            "sequence": sequence,
            "phase": phase,
            "operation": operation,
            "invocation_id": f"invocation-{sequence}",
            "terminal_state": "completed",
            "operation_succeeded": True,
            "simulated": simulated,
            "fields": [
                {
                    "field": field,
                    "requested": requested,
                    "applied": None if simulated else applied,
                    "applied_present": not simulated,
                    "status": "unknown" if simulated else "confirmed",
                    "provenance": "simulated" if simulated else provenance,
                    "exchange_ids": [] if simulated else exchange_ids,
                    "source_reference": None if simulated else source_reference,
                }
            ],
            "exchange_ids": [] if simulated else exchange_ids,
            "error_queue_exchange_ids": [],
            "error_type": None,
        }
        return {**payload, "digest": canonical_payload_digest(payload)}

    safe = operation_receipt(
        receipt_id="receipt-safe",
        sequence=0,
        phase="stop",
        operation="stop_emulation",
        field="state",
        requested="STOPPED",
        applied="STOPPED",
        provenance="runtime_state",
        exchange_ids=["exchange-safe"],
        source_reference="f64.simulation_state",
    )
    release = operation_receipt(
        receipt_id="receipt-release",
        sequence=1,
        phase="release",
        operation="transport_release",
        field="control_mode",
        requested="local",
        applied="local",
        provenance="transport_release",
        exchange_ids=[],
        source_reference="instrument_test_lease.release_to_local_control",
    )
    receipts = [safe, release]
    terminal_payload = {
        "schema_version": 2,
        "session_id": session_id,
        "operation_scope": "formal-case:execution-1",
        "execution_id": "execution-1",
        "measurement_attempt_id": "attempt-v2",
        "binding_digest": binding["binding_digest"],
        "binding_freeze_digest": binding["digest"],
        "plan_digest": plan["digest"],
        "execution_mode": execution_mode,
        "adapter_id": plan["adapter_id"],
        "driver_module": binding["expected_driver_module"],
        "driver_name": binding["expected_driver_name"],
        "driver_connection": binding["expected_driver_connection"],
        "lease_id": lease_id,
        "instrument_id": instrument_id,
        "remote_acquired_confirmed": None if simulated else True,
        "required_safe_idle_action": "stop_emulation",
        "safe_idle_action": "stop_emulation",
        "safe_idle_confirmed": True,
        "transport_released_confirmed": None if simulated else True,
        "operation_succeeded": True,
        "terminal_state": "completed",
        "error_type": None,
        "safe_idle_error_type": None,
        "operation_receipt_count": len(receipts),
        "operation_receipts_digest": (
            channel_emulator_operation_receipt_chain_digest(receipts)
        ),
        "operation_receipt_ids": tuple(item["receipt_id"] for item in receipts),
        "safe_idle_receipt_id": safe["receipt_id"],
        "transport_release_receipt_id": release["receipt_id"],
    }
    terminal = {
        **terminal_payload,
        "digest": canonical_payload_digest(terminal_payload),
    }
    execution = _execution_with_ce_evidence(binding, plan, terminal)
    execution.config[CE_OPERATION_RECEIPTS_CONFIG_KEY] = receipts
    execution.config[CE_TERMINAL_EVIDENCE_CONFIG_KEY] = [terminal]
    return execution, terminal, receipts


def _redigest(value: dict) -> None:
    value["digest"] = canonical_payload_digest(
        {key: item for key, item in value.items() if key != "digest"}
    )


def test_p2_66_accepts_only_a_complete_real_v2_receipt_chain():
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    execution, _terminal, _receipts = _v2_terminal_projection_fixture()

    assert _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    ) == (None, None)


def test_p2_66_allows_empty_failed_v2_retry_to_be_superseded():
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    execution, terminal, _receipts = _v2_terminal_projection_fixture()
    failed = deepcopy(terminal)
    failed.update(
        session_id="session-failed-before-acquire",
        operation_succeeded=False,
        terminal_state="failed",
        error_type="InstrumentTestLeaseError",
        safe_idle_confirmed=False,
        transport_released_confirmed=False,
        operation_receipt_count=0,
        operation_receipts_digest=canonical_payload_digest(
            {"schema_version": 1, "receipt_digests": []}
        ),
        operation_receipt_ids=(),
        safe_idle_receipt_id=None,
        transport_release_receipt_id=None,
    )
    _redigest(failed)
    execution.config[CE_TERMINAL_EVIDENCE_CONFIG_KEY] = [failed, terminal]

    assert _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    ) == (None, None)


@pytest.mark.parametrize(
    ("operation", "requested", "field", "formal_error"),
    [
        (
            "set_input_measurement_mode",
            "BURST",
            "mode",
            True,
        ),
        (
            "set_burst_trigger_level",
            -35.0,
            "trigger_dbm",
            True,
        ),
        (
            "autoset_inputs",
            [1, 2],
            "input_ports",
            True,
        ),
        (
            "ensure_topology",
            "active_ports",
            "topology",
            True,
        ),
        (
            "measure_input",
            {"input_port": 1, "measurement_time_s": 1.0},
            "measurement",
            True,
        ),
        (
            "get_input_level_limits",
            {"input_port": 1},
            "limits",
            True,
        ),
        (
            "get_group_clipping",
            {"group_num": 1, "reset": True},
            "clipping",
            True,
        ),
        (
            "get_system_status",
            "channel_emulator",
            "system_status",
            True,
        ),
        (
            "set_output_gain",
            -3.0,
            "gain_db",
            True,
        ),
        (
            "set_output_level_dbm",
            -52.0,
            "level_dbm",
            True,
        ),
        (
            "load_channel",
            "D:\\Models\\case.smu",
            "emulation_file",
            True,
        ),
    ],
)
def test_p2_66_requires_confirmation_for_every_formal_effect_field(
    operation, requested, field, formal_error
):
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        channel_emulator_operation_receipt_chain_digest,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    execution, terminal, receipts = _v2_terminal_projection_fixture()
    configure = deepcopy(receipts[0])
    configure.update(
        receipt_id="receipt-configure",
        sequence=0,
        phase="configure",
        operation=operation,
        invocation_id="invocation-configure",
        fields=[
            {
                "field": field,
                "requested": requested,
                "applied": None,
                "applied_present": False,
                "status": "unknown",
                "provenance": "command_error_queue",
                "exchange_ids": [],
                "source_reference": None,
            }
        ],
        exchange_ids=["exchange-configure-error"],
        error_queue_exchange_ids=["exchange-configure-error"],
    )
    _redigest(configure)
    receipts[0]["sequence"] = 1
    _redigest(receipts[0])
    receipts[1]["sequence"] = 2
    _redigest(receipts[1])
    receipts[:] = [configure, *receipts]
    terminal["operation_receipt_count"] = len(receipts)
    terminal["operation_receipt_ids"] = tuple(
        receipt["receipt_id"] for receipt in receipts
    )
    terminal["operation_receipts_digest"] = (
        channel_emulator_operation_receipt_chain_digest(receipts)
    )
    _redigest(terminal)
    execution.config[CE_OPERATION_RECEIPTS_CONFIG_KEY] = receipts

    classification, reason = _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )
    if formal_error:
        assert classification == "invalid"
        assert reason and "unconfirmed" in reason
    else:
        assert (classification, reason) == (None, None)


@pytest.mark.parametrize("mutation", ["receipt_attempt", "current_attempt"])
def test_p2_66_rejects_v2_receipts_outside_current_measurement_attempt(mutation):
    from app.services.channel_emulator_operation_receipt import (
        channel_emulator_operation_receipt_chain_digest,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    execution, terminal, receipts = _v2_terminal_projection_fixture()
    execution.config["base_station_execution_evidence"] = {
        "current_measurement_attempt_id": "attempt-v2",
        "current_measurement_attempt_state": "completed",
    }
    if mutation == "receipt_attempt":
        for receipt in receipts:
            receipt["measurement_attempt_id"] = "attempt-foreign"
            _redigest(receipt)
        terminal["operation_receipts_digest"] = (
            channel_emulator_operation_receipt_chain_digest(receipts)
        )
        _redigest(terminal)
    else:
        execution.config["base_station_execution_evidence"][
            "current_measurement_attempt_id"
        ] = "attempt-foreign"

    classification, reason = _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )

    assert classification == "invalid"
    assert reason and "attempt" in reason


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_receipt",
        "receipt_chain_digest",
        "foreign_session",
        "foreign_lease",
        "foreign_instrument",
        "foreign_asset",
        "unknown_field",
        "fake_release_field",
        "transport_provenance_on_safe",
    ],
)
def test_p2_66_rejects_incomplete_or_foreign_v2_receipt_chain(mutation):
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
        channel_emulator_operation_receipt_chain_digest,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    execution, terminal, receipts = _v2_terminal_projection_fixture()
    if mutation == "missing_receipt":
        execution.config[CE_OPERATION_RECEIPTS_CONFIG_KEY] = receipts[:-1]
    elif mutation == "receipt_chain_digest":
        terminal["operation_receipts_digest"] = "0" * 64
        _redigest(terminal)
    else:
        receipt = receipts[0]
        if mutation == "foreign_session":
            receipt["session_id"] = "foreign-session"
        elif mutation == "foreign_lease":
            receipt["lease_id"] = "foreign-lease"
        elif mutation == "foreign_instrument":
            receipt["instrument_id"] = "foreign-instrument"
        elif mutation == "foreign_asset":
            for item in receipts:
                item["asset_digest"] = "foreign-asset"
                _redigest(item)
        elif mutation == "fake_release_field":
            receipt = receipts[1]
            receipt["fields"][0].update(
                field="unrelated",
                requested="local",
                applied="local",
            )
        elif mutation == "transport_provenance_on_safe":
            receipt["fields"][0].update(
                provenance="transport_release",
                exchange_ids=[],
                source_reference="instrument_test_lease.release_to_local_control",
            )
            receipt["exchange_ids"] = []
        else:
            receipt["fields"][0].update(
                applied=None,
                applied_present=False,
                status="unknown",
                provenance="command_error_queue",
                exchange_ids=[],
                source_reference=None,
            )
            receipt["exchange_ids"] = []
        if mutation != "foreign_asset":
            _redigest(receipt)
        try:
            terminal["operation_receipts_digest"] = (
                channel_emulator_operation_receipt_chain_digest(receipts)
            )
        except ValueError:
            pass
        else:
            _redigest(terminal)

    classification, reason = _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )
    assert classification == "invalid"
    assert reason


def test_p2_66_keeps_simulated_v2_receipts_diagnostic():
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    execution, _terminal, _receipts = _v2_terminal_projection_fixture(
        execution_mode="simulated"
    )

    classification, reason = _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )
    assert classification == "diagnostic"
    assert "simulated" in reason


def test_p2_66_requires_v2_terminal_when_measurement_attempt_already_completed():
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    execution, _terminal, _receipts = _v2_terminal_projection_fixture()
    execution.status = "running"
    execution.config.pop(CE_TERMINAL_EVIDENCE_CONFIG_KEY)
    execution.config["base_station_execution_evidence"] = {
        "current_measurement_attempt_state": "completed"
    }

    classification, reason = _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )
    assert classification == "invalid"
    assert "terminal evidence" in reason


def test_public_projection_is_server_owned_redacted_and_shared_by_outcome():
    from app.services.execution_evidence_outcome import (
        project_execution_evidence_outcome,
    )

    execution, terminal, receipts = _v2_terminal_projection_fixture()
    projection = project_execution_evidence_outcome(
        execution
    ).channel_emulator_operation_evidence

    assert projection.status == "verified"
    assert projection.reasons == ()
    assert len(projection.sessions) == 1
    session = projection.sessions[0]
    assert session.session_id == terminal["session_id"]
    assert session.receipt_count == 2
    assert session.receipt_chain_digest == terminal["operation_receipts_digest"]
    assert [item.sequence for item in session.receipts] == [0, 1]
    assert [item.operation for item in session.receipts] == [
        "stop_emulation",
        "transport_release",
    ]
    assert session.receipts[0].fields[0].provenance == "runtime_state"
    assert session.receipts[0].fields[0].exchange_ids == ("exchange-safe",)
    serialized = projection.model_dump(mode="json")
    assert "requested" not in json.dumps(serialized)
    assert "applied" not in json.dumps(serialized)
    assert receipts[0]["fields"][0]["requested"] == "STOPPED"


def test_public_projection_marks_invalid_and_simulated_without_green_receipts():
    from app.services.channel_emulator_operation_receipt import (
        CE_OPERATION_RECEIPTS_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import (
        project_execution_evidence_outcome,
    )

    invalid, _terminal, receipts = _v2_terminal_projection_fixture()
    invalid.config[CE_OPERATION_RECEIPTS_CONFIG_KEY] = receipts[:-1]
    invalid_projection = project_execution_evidence_outcome(
        invalid
    ).channel_emulator_operation_evidence
    assert invalid_projection.status == "invalid"
    assert invalid_projection.sessions == ()
    assert invalid_projection.reasons

    simulated, _terminal, _receipts = _v2_terminal_projection_fixture(
        execution_mode="simulated"
    )
    simulated_projection = project_execution_evidence_outcome(
        simulated
    ).channel_emulator_operation_evidence
    assert simulated_projection.status == "diagnostic"
    assert all(
        item.status != "verified"
        for session in simulated_projection.sessions
        for item in session.receipts
    )


def test_execution_log_metadata_uses_the_same_channel_operation_projection():
    from app.api.system_logs import _load_execution_export_metadata
    from app.services.execution_evidence_outcome import (
        project_execution_evidence_outcome,
    )

    execution, _terminal, _receipts = _v2_terminal_projection_fixture()
    execution.id = uuid4()

    class _Query:
        def filter(self, *_args):
            return self

        def one_or_none(self):
            return execution

    class _Db:
        def query(self, *_args):
            return _Query()

    metadata = _load_execution_export_metadata(str(execution.id), _Db())
    expected = project_execution_evidence_outcome(
        execution
    ).channel_emulator_operation_evidence.model_dump(mode="json")
    assert metadata["execution_evidence_outcome"][
        "channel_emulator_operation_evidence"
    ] == expected


def test_pre_p2_60_stored_report_outcome_accepts_missing_public_projection():
    from app.api.report import _report_execution_outcome_state
    from app.services.execution_evidence_outcome import (
        project_execution_evidence_outcome,
    )

    execution, _terminal, _receipts = _v2_terminal_projection_fixture()
    report_source_id = uuid4()
    stored = project_execution_evidence_outcome(execution).model_dump(mode="json")
    stored.pop("channel_emulator_operation_evidence")
    report = SimpleNamespace(
        status="completed",
        report_type="single_execution",
        test_execution_ids=[report_source_id],
        road_test_execution_id=None,
        content_data={"execution_evidence_outcome": stored},
    )

    class _Db:
        def get(self, _model, execution_id):
            return execution if execution_id == report_source_id else None

    outcome, matches = _report_execution_outcome_state(_Db(), report)
    assert matches is True
    assert outcome is not None
    assert outcome.channel_emulator_operation_evidence.status == "verified"


def test_report_aggregate_digest_is_stable_across_public_projection_addition():
    from app.api.report import _aggregate_report_execution_outcomes
    from app.services.execution_evidence_outcome import (
        project_execution_evidence_outcome,
    )

    execution, _terminal, _receipts = _v2_terminal_projection_fixture()
    source_id = uuid4()
    projected = project_execution_evidence_outcome(execution)
    expected_digest = canonical_payload_digest(
        [
            {
                "execution_id": str(source_id),
                "outcome": projected.model_dump(
                    mode="json",
                    exclude={"channel_emulator_operation_evidence"},
                ),
            }
        ]
    )

    aggregate = _aggregate_report_execution_outcomes(
        [source_id],
        [execution],
    )
    assert aggregate.compatibility_digest == expected_digest
    assert aggregate.channel_emulator_operation_evidence.status == "verified"


def test_live_checked_and_generated_contracts_publish_channel_operation_projection():
    from app.main import app

    repo_root = API_SERVICE.parent
    live = app.openapi()["components"]["schemas"]
    checked = yaml.safe_load(
        (repo_root / "api/openapi.yaml").read_text(encoding="utf-8")
    )["components"]["schemas"]
    for schemas in (live, checked):
        assert "ChannelEmulatorOperationEvidenceProjection" in schemas
        outcome = schemas["ExecutionEvidenceOutcome"]
        assert "channel_emulator_operation_evidence" in outcome["properties"]
        assert "channel_emulator_operation_evidence" in outcome["required"]

    generated = (
        repo_root / "gui/src/types/api.generated.ts"
    ).read_text(encoding="utf-8")
    assert "ChannelEmulatorOperationEvidenceProjection:" in generated
    assert "channel_emulator_operation_evidence:" in generated
