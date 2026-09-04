"""Execution-bound channel-emulator operation receipts.

The receipt stores immutable, redacted evidence indexes.  A successful driver
return is intentionally separate from a confirmed applied value: only an
existing authoritative readback or runtime-state source may confirm a field.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    NonNegativeInt,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.channel_emulator_manifest import CHANNEL_EMULATOR_OPERATIONS


CE_OPERATION_RECEIPTS_CONFIG_KEY = "channel_emulator_operation_receipts"

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

ChannelOperationFieldStatus = Literal[
    "requested",
    "applied",
    "confirmed",
    "unknown",
    "not_applicable",
    "unavailable",
]
ChannelOperationProvenance = Literal[
    "authoritative_readback",
    "command_error_queue",
    "runtime_state",
    "transport_release",
    "simulated",
    "unavailable",
]
ChannelOperationPhase = Literal[
    "load",
    "configure",
    "start",
    "adjust",
    "stop",
    "cleanup",
    "release",
]
ChannelOperationTerminalState = Literal[
    "completed",
    "rejected",
    "failed",
    "cancelled",
]

_RECEIPT_OPERATIONS = frozenset(
    (*CHANNEL_EMULATOR_OPERATIONS, "load_channel", "transport_release")
)
_CONFIRMING_PROVENANCE = frozenset(
    {"authoritative_readback", "runtime_state", "transport_release"}
)


class ChannelEmulatorOperationReceiptError(RuntimeError):
    """A receipt cannot be trusted or appended to its execution."""


class FrozenChannelOperationField(BaseModel):
    """One requested field and the strongest evidence actually available."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: NonEmptyString
    requested: JsonValue
    applied: JsonValue | None = None
    applied_present: bool
    status: ChannelOperationFieldStatus
    provenance: ChannelOperationProvenance
    exchange_ids: tuple[NonEmptyString, ...] = ()
    source_reference: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_evidence_claim(self) -> "FrozenChannelOperationField":
        if len(set(self.exchange_ids)) != len(self.exchange_ids):
            raise ValueError("field exchange ids must be unique")
        if self.status in {"applied", "confirmed"}:
            if self.applied_present is not True:
                raise ValueError(f"{self.status} field has no applied value")
        elif self.applied_present is not False:
            raise ValueError(f"{self.status} field cannot carry an applied value")
        if self.status == "confirmed":
            if self.provenance not in _CONFIRMING_PROVENANCE:
                raise ValueError("confirmed field has no authoritative provenance")
            if not self.exchange_ids or self.source_reference is None:
                raise ValueError("confirmed field has no authoritative exchange/source")
        if self.status == "applied" and self.provenance not in _CONFIRMING_PROVENANCE:
            raise ValueError("applied field has no authoritative provenance")
        if self.status in {"not_applicable", "unavailable"}:
            if self.exchange_ids:
                raise ValueError(f"{self.status} field cannot carry an exchange")
            if self.applied_present:
                raise ValueError(f"{self.status} field cannot carry an applied value")
        if self.status == "unavailable" and self.provenance != "unavailable":
            raise ValueError("unavailable field must use unavailable provenance")
        if self.provenance == "simulated" and self.status in {
            "applied",
            "confirmed",
        }:
            raise ValueError("simulated field cannot be applied or confirmed")
        return self


class FrozenChannelOperationReceipt(BaseModel):
    """Strict immutable identity and evidence for one CE invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    receipt_id: NonEmptyString
    session_id: NonEmptyString
    operation_scope: NonEmptyString
    execution_id: NonEmptyString
    measurement_attempt_id: NonEmptyString | None = None
    binding_digest: NonEmptyString
    binding_freeze_digest: NonEmptyString
    plan_digest: NonEmptyString
    asset_digest: NonEmptyString | None = None
    lease_id: NonEmptyString
    instrument_id: NonEmptyString
    adapter_id: NonEmptyString
    execution_mode: Literal["real", "simulated"]
    sequence: NonNegativeInt
    phase: ChannelOperationPhase
    operation: NonEmptyString
    invocation_id: NonEmptyString
    terminal_state: ChannelOperationTerminalState
    operation_succeeded: bool | None
    simulated: bool
    fields: tuple[FrozenChannelOperationField, ...]
    exchange_ids: tuple[NonEmptyString, ...] = ()
    error_queue_exchange_ids: tuple[NonEmptyString, ...] = ()
    error_type: NonEmptyString | None = None
    digest: NonEmptyString

    @model_validator(mode="after")
    def validate_receipt_claim(self) -> "FrozenChannelOperationReceipt":
        if self.operation not in _RECEIPT_OPERATIONS:
            raise ValueError(f"unknown channelEmulator receipt operation: {self.operation}")
        if not self.fields:
            raise ValueError("channelEmulator receipt fields must be non-empty")
        if len({field.field for field in self.fields}) != len(self.fields):
            raise ValueError("channelEmulator receipt field names must be unique")
        if len(set(self.exchange_ids)) != len(self.exchange_ids):
            raise ValueError("channelEmulator receipt exchange ids must be unique")
        if len(set(self.error_queue_exchange_ids)) != len(
            self.error_queue_exchange_ids
        ):
            raise ValueError("channelEmulator error queue exchange ids must be unique")
        receipt_exchange_ids = set(self.exchange_ids)
        if not set(self.error_queue_exchange_ids).issubset(receipt_exchange_ids):
            raise ValueError("error queue exchange ids are outside the receipt")
        if any(
            not set(field.exchange_ids).issubset(receipt_exchange_ids)
            for field in self.fields
        ):
            raise ValueError("field exchange ids are outside the receipt")
        if self.simulated != (self.execution_mode == "simulated"):
            raise ValueError("receipt simulated flag does not match execution mode")
        if self.simulated and any(
            field.status in {"applied", "confirmed"} for field in self.fields
        ):
            raise ValueError("simulated receipt cannot carry a confirmed field")
        if self.terminal_state == "completed":
            if self.operation_succeeded is not True or self.error_type is not None:
                raise ValueError("completed receipt is contradictory")
        elif self.terminal_state == "rejected":
            if self.operation_succeeded is not False or self.error_type is not None:
                raise ValueError("rejected receipt is contradictory")
        elif self.terminal_state == "failed":
            if self.operation_succeeded is True:
                raise ValueError("failed receipt cannot claim successful operation")
            if self.error_type is None:
                raise ValueError("failed receipt has no error identity")
        else:
            if self.operation_succeeded is True:
                raise ValueError("cancelled receipt cannot claim successful operation")
            if self.error_type != "CancelledError":
                raise ValueError("cancelled receipt has invalid error identity")
        unavailable_fields = [
            field for field in self.fields if field.status == "unavailable"
        ]
        if unavailable_fields and self.exchange_ids:
            raise ValueError("unavailable receipt cannot carry an exchange")
        if unavailable_fields and (
            self.terminal_state != "rejected"
            or self.operation_succeeded is not False
        ):
            raise ValueError("unavailable receipt cannot claim successful operation")
        return self


def validate_channel_emulator_operation_receipt(value: Any) -> dict[str, Any]:
    """Parse the complete schema, then verify the original canonical digest."""

    if not isinstance(value, dict):
        raise ValueError("channelEmulator operation receipt is malformed")
    try:
        FrozenChannelOperationReceipt.model_validate(value)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(
            f"channelEmulator operation receipt is malformed: {exc}"
        ) from exc
    payload = {key: item for key, item in value.items() if key != "digest"}
    if value.get("digest") != canonical_payload_digest(payload):
        raise ValueError("channelEmulator operation receipt digest mismatch")
    return value


def channel_emulator_operation_receipt_chain_digest(
    receipts: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> str:
    """Validate one session's canonical order and return its immutable digest."""

    if not isinstance(receipts, (list, tuple)) or not receipts:
        raise ValueError("channelEmulator operation receipt chain is empty")
    validated: list[dict[str, Any]] = []
    for receipt in receipts:
        validated.append(
            validate_channel_emulator_operation_receipt(dict(receipt))
        )
    session_id = validated[0]["session_id"]
    execution_id = validated[0]["execution_id"]
    expected_sequences = list(range(len(validated)))
    actual_sequences = [item["sequence"] for item in validated]
    if actual_sequences != expected_sequences:
        raise ValueError(
            "channelEmulator operation receipt sequence is not canonical"
        )
    if any(item["session_id"] != session_id for item in validated):
        raise ValueError("channelEmulator operation receipt chain crosses session")
    if any(item["execution_id"] != execution_id for item in validated):
        raise ValueError("channelEmulator operation receipt chain crosses execution")
    identity_keys = (
        "operation_scope",
        "binding_digest",
        "binding_freeze_digest",
        "plan_digest",
        "asset_digest",
        "lease_id",
        "instrument_id",
        "adapter_id",
        "execution_mode",
    )
    identity = {key: validated[0].get(key) for key in identity_keys}
    if any(
        any(item.get(key) != expected for key, expected in identity.items())
        for item in validated[1:]
    ):
        raise ValueError("channelEmulator operation receipt chain identity drift")
    return canonical_payload_digest(
        {
            "schema_version": 1,
            "receipt_digests": [item["digest"] for item in validated],
        }
    )


def persist_channel_emulator_operation_receipt(
    db: Any,
    execution_id: Any,
    receipt: dict[str, Any],
) -> None:
    """Append one immutable receipt under the execution row lock."""

    from sqlalchemy.orm.attributes import flag_modified

    from app.models.test_plan import TestExecution

    try:
        validate_channel_emulator_operation_receipt(receipt)
    except ValueError as exc:
        raise ChannelEmulatorOperationReceiptError(str(exc)) from exc
    if receipt.get("execution_id") != str(execution_id):
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator receipt execution identity does not match target"
        )
    locked = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution_id)
        .with_for_update()
        .one_or_none()
    )
    if locked is None:
        raise ChannelEmulatorOperationReceiptError("TestExecution no longer exists")
    config = locked.config if isinstance(locked.config, dict) else {}
    existing = config.get(CE_OPERATION_RECEIPTS_CONFIG_KEY, [])
    if not isinstance(existing, list):
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator operation receipt chain is malformed"
        )
    for item in existing:
        try:
            validate_channel_emulator_operation_receipt(item)
        except ValueError as exc:
            raise ChannelEmulatorOperationReceiptError(str(exc)) from exc
        if item.get("receipt_id") == receipt.get("receipt_id"):
            if item == receipt:
                return
            raise ChannelEmulatorOperationReceiptError(
                "channelEmulator receipt id already has different evidence"
            )
    locked.config = {
        **config,
        CE_OPERATION_RECEIPTS_CONFIG_KEY: [*existing, receipt],
    }
    flag_modified(locked, "config")
    db.commit()
