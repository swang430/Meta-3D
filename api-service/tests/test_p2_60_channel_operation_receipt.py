"""P2-60：vendor-neutral Channel Operation Receipt。"""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest

from app.hal.base_station_compatibility import canonical_payload_digest


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
