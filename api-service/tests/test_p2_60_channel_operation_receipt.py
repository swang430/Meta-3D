"""P2-60：vendor-neutral Channel Operation Receipt。"""

from __future__ import annotations

from copy import deepcopy
import asyncio
from uuid import uuid4

import pytest

from app.hal.base_station_compatibility import canonical_payload_digest


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
