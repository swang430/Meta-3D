"""Execution-bound channel-emulator operation receipts.

The receipt stores immutable, redacted evidence indexes.  A successful driver
return is intentionally separate from a confirmed applied value: only an
existing authoritative readback or runtime-state source may confirm a field.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Annotated, Any, Awaitable, Callable, Iterator, Literal, Mapping
from uuid import uuid4

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
from app.hal.scpi_evidence import ScpiExchangeRef, capture_scpi_exchanges


logger = logging.getLogger(__name__)


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
ChannelOperationEvidenceStatus = Literal[
    "not_available",
    "pending",
    "legacy",
    "verified",
    "diagnostic",
    "invalid",
]

_RECEIPT_OPERATIONS = frozenset(
    (*CHANNEL_EMULATOR_OPERATIONS, "load_channel", "transport_release")
)
_CONFIRMING_PROVENANCE = frozenset(
    {"authoritative_readback", "runtime_state", "transport_release"}
)


class ChannelEmulatorOperationReceiptError(RuntimeError):
    """A receipt cannot be trusted or appended to its execution."""


@dataclass
class ChannelEmulatorOperationRecorderOwner:
    """Task-local immutable execution identity plus append serialization."""

    db: Any
    execution_pk: Any
    execution_id: str
    session_id: str
    operation_scope: str
    measurement_attempt_id: str | None
    binding_digest: str
    binding_freeze_digest: str
    plan_digest: str
    asset_digest: str | None
    lease_id: str
    instrument_id: str
    adapter_id: str
    execution_mode: Literal["real", "simulated"]
    plan: Any
    driver: Any
    automatic_lifecycle_receipts: bool = True
    next_sequence: int = 0
    recorded_receipts: list[dict[str, Any]] = field(default_factory=list, repr=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self) -> None:
        for name in (
            "execution_id",
            "session_id",
            "operation_scope",
            "binding_digest",
            "binding_freeze_digest",
            "plan_digest",
            "lease_id",
            "instrument_id",
            "adapter_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ChannelEmulatorOperationReceiptError(
                    f"channelEmulator recorder {name} must be non-empty"
                )
        if self.execution_mode not in {"real", "simulated"}:
            raise ChannelEmulatorOperationReceiptError(
                "channelEmulator recorder execution mode is invalid"
            )


_channel_emulator_operation_recorder_owner: ContextVar[
    ChannelEmulatorOperationRecorderOwner | None
] = ContextVar("channel_emulator_operation_recorder_owner", default=None)


def current_channel_emulator_operation_recorder_owner(
) -> ChannelEmulatorOperationRecorderOwner | None:
    """Return the immutable owner only while the execution scope is active."""

    return _channel_emulator_operation_recorder_owner.get()


@contextmanager
def channel_emulator_operation_recorder_scope(
    owner: ChannelEmulatorOperationRecorderOwner,
) -> Iterator[ChannelEmulatorOperationRecorderOwner]:
    """Expose one execution-owned recorder only to this task and its children."""

    if not isinstance(owner, ChannelEmulatorOperationRecorderOwner):
        raise TypeError("channelEmulator recorder owner has invalid type")
    if _channel_emulator_operation_recorder_owner.get() is not None:
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator recorder scope cannot be nested"
        )
    token = _channel_emulator_operation_recorder_owner.set(owner)
    try:
        yield owner
    finally:
        _channel_emulator_operation_recorder_owner.reset(token)


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
            if (
                self.provenance != "transport_release"
                and not self.exchange_ids
            ) or self.source_reference is None:
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


class ChannelOperationFieldEvidenceProjection(BaseModel):
    """Redacted public field evidence; requested/applied values stay private."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: NonEmptyString
    status: ChannelOperationFieldStatus
    provenance: ChannelOperationProvenance
    exchange_ids: tuple[NonEmptyString, ...] = ()
    source_reference: NonEmptyString | None = None


class ChannelOperationReceiptEvidenceProjection(BaseModel):
    """One immutable receipt's public sequence and evidence classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: NonNegativeInt
    phase: ChannelOperationPhase
    operation: NonEmptyString
    terminal_state: ChannelOperationTerminalState
    operation_succeeded: bool | None
    simulated: bool
    status: Literal["verified", "diagnostic", "rejected", "failed", "cancelled"]
    fields: tuple[ChannelOperationFieldEvidenceProjection, ...]
    exchange_ids: tuple[NonEmptyString, ...] = ()
    error_queue_exchange_ids: tuple[NonEmptyString, ...] = ()


class ChannelOperationSessionEvidenceProjection(BaseModel):
    """Public ordered receipt chain for one effective execution session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: NonEmptyString
    operation_scope: NonEmptyString | None
    status: Literal["legacy", "verified", "diagnostic"]
    receipt_count: NonNegativeInt | None
    receipt_chain_digest: NonEmptyString | None
    receipts: tuple[ChannelOperationReceiptEvidenceProjection, ...] = ()


class ChannelEmulatorOperationEvidenceProjection(BaseModel):
    """Server-owned CE audit projection shared by every formal consumer."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_serialization_defaults_required=True,
    )

    schema_version: Literal[1] = 1
    status: ChannelOperationEvidenceStatus
    reasons: tuple[str, ...] = ()
    sessions: tuple[ChannelOperationSessionEvidenceProjection, ...] = ()


def empty_channel_emulator_operation_evidence(
    *,
    status: ChannelOperationEvidenceStatus = "not_available",
    reasons: tuple[str, ...] = (),
) -> ChannelEmulatorOperationEvidenceProjection:
    """Build the conservative default used for historical/non-CE outcomes."""

    return ChannelEmulatorOperationEvidenceProjection(
        status=status,
        reasons=reasons,
    )


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


def _requested_fields(
    requested: Mapping[str, Any],
    *,
    status: ChannelOperationFieldStatus,
    provenance: ChannelOperationProvenance,
) -> list[dict[str, Any]]:
    if not requested:
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator operation requested fields must be non-empty"
        )
    return [
        {
            "field": str(name),
            "requested": value,
            "applied": None,
            "applied_present": False,
            "status": status,
            "provenance": provenance,
            "exchange_ids": [],
            "source_reference": None,
        }
        for name, value in requested.items()
    ]


def _operation_is_planned(owner: ChannelEmulatorOperationRecorderOwner, operation: str) -> bool:
    if operation == "load_channel":
        planned = getattr(owner.plan, "load_mode_planned", None)
    elif operation == "transport_release":
        planned = True
    else:
        planned_method = getattr(owner.plan, "planned", None)
        if not callable(planned_method):
            raise ChannelEmulatorOperationReceiptError(
                "channelEmulator recorder plan has no planned-operation contract"
            )
        planned = planned_method(operation)
    if type(planned) is not bool:
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator recorder plan returned a non-boolean decision"
        )
    return planned


def _operation_rejection(owner: ChannelEmulatorOperationRecorderOwner, operation: str) -> str:
    if operation == "load_channel":
        reason = getattr(owner.plan, "load_mode_reason", None)
        if isinstance(reason, str) and reason.strip():
            return reason
        return "requested channel load mode is unavailable"
    rejection = getattr(owner.plan, "rejection", None)
    if callable(rejection):
        reason = rejection(operation)
        if isinstance(reason, str) and reason.strip():
            return reason
    return f"channelEmulator operation {operation} is unavailable"


def _validate_exchange_identity(
    owner: ChannelEmulatorOperationRecorderOwner,
    exchanges: list[ScpiExchangeRef],
) -> None:
    if not exchanges:
        return
    capture_ids = {item.capture_id for item in exchanges}
    execution_ids = {item.execution_id for item in exchanges}
    instrument_ids = {item.instrument_id for item in exchanges}
    if (
        len(capture_ids) != 1
        or execution_ids != {owner.execution_id}
        or instrument_ids != {owner.instrument_id}
    ):
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator operation exchange identity does not match the frozen execution"
        )


def _project_operation_evidence(
    owner: ChannelEmulatorOperationRecorderOwner,
    *,
    operation: str,
    requested: Mapping[str, Any],
    operation_succeeded: bool | None,
    exchanges: list[ScpiExchangeRef],
) -> dict[str, Any]:
    if operation == "transport_release":
        if owner.execution_mode == "simulated":
            return {
                "fields": [
                    {
                        "field": "control_mode",
                        "requested": requested.get("control_mode"),
                        "applied": None,
                        "applied_present": False,
                        "status": "not_applicable",
                        "provenance": "simulated",
                        "exchange_ids": [],
                        "source_reference": None,
                    }
                ],
                "exchange_ids": [],
                "error_queue_exchange_ids": [],
            }
        released = operation_succeeded is True
        return {
            "fields": [
                {
                    "field": "control_mode",
                    "requested": requested.get("control_mode"),
                    "applied": "local" if released else None,
                    "applied_present": released,
                    "status": "confirmed" if released else "unknown",
                    "provenance": "transport_release",
                    "exchange_ids": [],
                    "source_reference": (
                        "instrument_test_lease.release_to_local_control"
                        if released
                        else None
                    ),
                }
            ],
            "exchange_ids": [],
            "error_queue_exchange_ids": [],
        }
    projector = getattr(owner.driver, "project_channel_operation_evidence", None)
    if not callable(projector) or inspect.iscoroutinefunction(projector):
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator driver has no synchronous evidence projection contract"
        )
    projected = projector(
        operation=operation,
        requested=dict(requested),
        operation_succeeded=operation_succeeded,
        exchanges=tuple(exchanges),
        execution_mode=owner.execution_mode,
    )
    if not isinstance(projected, Mapping):
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator driver evidence projection is malformed"
        )
    fields = projected.get("fields")
    exchange_ids = projected.get("exchange_ids", [])
    error_queue_exchange_ids = projected.get("error_queue_exchange_ids", [])
    if not isinstance(fields, (list, tuple)) or not fields:
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator driver evidence projection has no fields"
        )
    if not isinstance(exchange_ids, (list, tuple)) or not isinstance(
        error_queue_exchange_ids, (list, tuple)
    ):
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator driver evidence projection exchange indexes are malformed"
        )
    captured_ids = {item.exchange_id for item in exchanges}
    if not set(exchange_ids).issubset(captured_ids) or not set(
        error_queue_exchange_ids
    ).issubset(captured_ids):
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator driver evidence projection references a foreign exchange"
        )
    return {
        "fields": [dict(item) for item in fields],
        "exchange_ids": list(exchange_ids),
        "error_queue_exchange_ids": list(error_queue_exchange_ids),
    }


def _receipt_payload(
    owner: ChannelEmulatorOperationRecorderOwner,
    *,
    sequence: int,
    phase: ChannelOperationPhase,
    operation: str,
    invocation_id: str,
    terminal_state: ChannelOperationTerminalState,
    operation_succeeded: bool | None,
    evidence: Mapping[str, Any],
    error_type: str | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "receipt_id": uuid4().hex,
        "session_id": owner.session_id,
        "operation_scope": owner.operation_scope,
        "execution_id": owner.execution_id,
        "measurement_attempt_id": owner.measurement_attempt_id,
        "binding_digest": owner.binding_digest,
        "binding_freeze_digest": owner.binding_freeze_digest,
        "plan_digest": owner.plan_digest,
        "asset_digest": owner.asset_digest,
        "lease_id": owner.lease_id,
        "instrument_id": owner.instrument_id,
        "adapter_id": owner.adapter_id,
        "execution_mode": owner.execution_mode,
        "sequence": sequence,
        "phase": phase,
        "operation": operation,
        "invocation_id": invocation_id,
        "terminal_state": terminal_state,
        "operation_succeeded": operation_succeeded,
        "simulated": owner.execution_mode == "simulated",
        "fields": list(evidence["fields"]),
        "exchange_ids": list(evidence.get("exchange_ids", [])),
        "error_queue_exchange_ids": list(
            evidence.get("error_queue_exchange_ids", [])
        ),
        "error_type": error_type,
    }
    return {**payload, "digest": canonical_payload_digest(payload)}


def _persist_recorded_receipt(
    owner: ChannelEmulatorOperationRecorderOwner,
    receipt: dict[str, Any],
    *,
    primary_error: BaseException | None,
) -> None:
    if primary_error is not None:
        rollback = getattr(owner.db, "rollback", None)
        if callable(rollback):
            rollback()
    try:
        persist_channel_emulator_operation_receipt(
            owner.db, owner.execution_pk, receipt
        )
    except BaseException as persistence_error:
        if primary_error is None:
            raise
        setattr(
            primary_error,
            "channel_emulator_receipt_persistence_error",
            persistence_error,
        )
        primary_error.add_note(
            "channelEmulator operation receipt persistence also failed: "
            f"{type(persistence_error).__name__}: {persistence_error}"
        )
        logger.exception(
            "channelEmulator operation receipt persistence failed while preserving operation error"
        )
        return
    owner.recorded_receipts.append(receipt)


async def record_channel_emulator_operation(
    *,
    phase: ChannelOperationPhase,
    operation: str,
    requested: Mapping[str, Any],
    invoke: Callable[[], Awaitable[bool]],
) -> bool:
    """Invoke one planned CE operation and append its immutable evidence receipt."""

    owner = _channel_emulator_operation_recorder_owner.get()
    if owner is None:
        raise ChannelEmulatorOperationReceiptError(
            "channelEmulator operation has no execution-session owner"
        )
    if operation not in _RECEIPT_OPERATIONS:
        raise ChannelEmulatorOperationReceiptError(
            f"unknown channelEmulator receipt operation: {operation}"
        )
    if not isinstance(requested, Mapping):
        raise TypeError("channelEmulator operation requested values must be a mapping")
    if not callable(invoke):
        raise TypeError("channelEmulator operation invoke must be callable")

    async with owner.lock:
        sequence = owner.next_sequence
        invocation_id = uuid4().hex
        if not _operation_is_planned(owner, operation):
            reason = _operation_rejection(owner, operation)
            evidence = {
                "fields": _requested_fields(
                    requested, status="unavailable", provenance="unavailable"
                ),
                "exchange_ids": [],
                "error_queue_exchange_ids": [],
            }
            receipt = _receipt_payload(
                owner,
                sequence=sequence,
                phase=phase,
                operation=operation,
                invocation_id=invocation_id,
                terminal_state="rejected",
                operation_succeeded=False,
                evidence=evidence,
                error_type=None,
            )
            _persist_recorded_receipt(owner, receipt, primary_error=None)
            owner.next_sequence += 1
            raise ChannelEmulatorOperationReceiptError(reason)

        operation_error: BaseException | None = None
        result: bool | None = None
        with capture_scpi_exchanges() as exchanges:
            try:
                result = await invoke()
                if type(result) is not bool:
                    raise TypeError(
                        "channelEmulator operation must return a boolean result"
                    )
            except BaseException as exc:
                operation_error = exc

        identity_error: ChannelEmulatorOperationReceiptError | None = None
        try:
            _validate_exchange_identity(owner, exchanges)
        except ChannelEmulatorOperationReceiptError as exc:
            identity_error = exc
            if operation_error is None:
                operation_error = exc

        evidence_error: ChannelEmulatorOperationReceiptError | None = None
        if identity_error is not None:
            evidence = {
                "fields": _requested_fields(
                    requested,
                    status="unknown",
                    provenance=(
                        "simulated"
                        if owner.execution_mode == "simulated"
                        else "command_error_queue"
                    ),
                ),
                "exchange_ids": [],
                "error_queue_exchange_ids": [],
            }
        else:
            try:
                evidence = _project_operation_evidence(
                    owner,
                    operation=operation,
                    requested=requested,
                    operation_succeeded=(
                        result if operation_error is None else None
                    ),
                    exchanges=exchanges,
                )
            except ChannelEmulatorOperationReceiptError as exc:
                evidence_error = exc
                if operation_error is None:
                    operation_error = exc
                evidence = {
                    "fields": _requested_fields(
                        requested,
                        status="unknown",
                        provenance=(
                            "simulated"
                            if owner.execution_mode == "simulated"
                            else "command_error_queue"
                        ),
                    ),
                    "exchange_ids": [],
                    "error_queue_exchange_ids": [],
                }

        if isinstance(operation_error, asyncio.CancelledError):
            terminal_state: ChannelOperationTerminalState = "cancelled"
            operation_succeeded = None
            error_type = "CancelledError"
        elif operation_error is not None:
            terminal_state = "failed"
            operation_succeeded = None
            error_type = (
                "ExchangeIdentityMismatch"
                if identity_error is not None
                else (
                    "EvidenceProjectionError"
                    if evidence_error is not None
                    else type(operation_error).__name__
                )
            )
        elif result is True:
            terminal_state = "completed"
            operation_succeeded = True
            error_type = None
        else:
            terminal_state = "rejected"
            operation_succeeded = False
            error_type = None

        receipt = _receipt_payload(
            owner,
            sequence=sequence,
            phase=phase,
            operation=operation,
            invocation_id=invocation_id,
            terminal_state=terminal_state,
            operation_succeeded=operation_succeeded,
            evidence=evidence,
            error_type=error_type,
        )
        _persist_recorded_receipt(
            owner, receipt, primary_error=operation_error
        )
        owner.next_sequence += 1
        if operation_error is not None:
            raise operation_error
        return bool(result)
