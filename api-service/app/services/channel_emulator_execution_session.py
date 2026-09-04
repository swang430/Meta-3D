"""Execution-frozen channel-emulator lifecycle shared by every test entry."""

from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Mapping
from uuid import uuid4

from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.channel_emulator_execution_plan import (
    plan_from_frozen_payload,
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import channel_emulator_manifest_of
from app.services.channel_emulator_binding import (
    CHANNEL_EMULATOR_CATEGORY_KEY,
    validate_frozen_channel_emulator_before_remote,
)
from app.services.channel_emulator_execution_plan import (
    validate_frozen_channel_emulator_execution_plan,
    verify_frozen_channel_emulator_execution_plan,
)
from app.services.instrument_test_lease import (
    InstrumentTestLeaseError,
    InstrumentTestLeaseOutcome,
    instrument_test_lease,
)

logger = logging.getLogger(__name__)

CE_TERMINAL_EVIDENCE_CONFIG_KEY = "channel_emulator_terminal_evidence"


class ChannelEmulatorExecutionSessionError(InstrumentTestLeaseError):
    """The frozen CE session could not reach a confirmed safe terminal state."""


@dataclass
class ChannelEmulatorExecutionScopeOutcome:
    """Lease truth plus an explicit business-result handshake."""

    lease_outcome: InstrumentTestLeaseOutcome
    operation_succeeded: bool | None = None

    def mark_operation_result(self, succeeded: bool) -> None:
        if type(succeeded) is not bool:
            raise TypeError("channelEmulator operation result must be bool")
        self.operation_succeeded = succeeded

    def __getattr__(self, name: str) -> Any:
        return getattr(self.lease_outcome, name)


def persist_channel_emulator_terminal_evidence(
    db: Any,
    execution_id: Any,
    evidence: dict[str, Any],
) -> None:
    """Append one immutable session terminal after safe-idle and lease release."""

    from sqlalchemy.orm.attributes import flag_modified

    from app.models.test_plan import TestExecution

    payload = {key: value for key, value in evidence.items() if key != "digest"}
    if evidence.get("digest") != canonical_payload_digest(payload):
        raise ChannelEmulatorExecutionSessionError(
            "channelEmulator terminal evidence digest mismatch"
        )
    locked = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution_id)
        .with_for_update()
        .one_or_none()
    )
    if locked is None:
        raise ChannelEmulatorExecutionSessionError("TestExecution no longer exists")
    config = locked.config if isinstance(locked.config, dict) else {}
    existing = config.get(CE_TERMINAL_EVIDENCE_CONFIG_KEY, [])
    if not isinstance(existing, list):
        raise ChannelEmulatorExecutionSessionError(
            "channelEmulator terminal evidence chain is malformed"
        )
    session_id = evidence.get("session_id")
    for item in existing:
        if not isinstance(item, Mapping):
            raise ChannelEmulatorExecutionSessionError(
                "channelEmulator terminal evidence chain is malformed"
            )
        item_payload = {key: value for key, value in item.items() if key != "digest"}
        if item.get("digest") != canonical_payload_digest(item_payload):
            raise ChannelEmulatorExecutionSessionError(
                "channelEmulator terminal evidence chain digest mismatch"
            )
        if item.get("session_id") == session_id:
            if dict(item) == evidence:
                return
            raise ChannelEmulatorExecutionSessionError(
                "channelEmulator terminal session id already has different evidence"
            )
    locked.config = {
        **config,
        CE_TERMINAL_EVIDENCE_CONFIG_KEY: [*existing, evidence],
    }
    flag_modified(locked, "config")
    db.commit()


def _driver_from_hal(hal: Any) -> Any:
    drivers = getattr(hal, "drivers", None)
    return (
        drivers.get(CHANNEL_EMULATOR_CATEGORY_KEY)
        if isinstance(drivers, Mapping)
        else None
    )


def _validate_frozen_pair_and_live_driver(
    hal: Any,
    binding: Any,
    plan: Any,
) -> str | None:
    binding_error = validate_frozen_channel_emulator_before_remote(hal, binding)
    if binding_error is not None:
        return binding_error
    try:
        validated_plan = validate_frozen_channel_emulator_execution_plan(plan)
        parsed_plan = plan_from_frozen_payload(validated_plan)
    except ValueError as exc:
        return str(exc)
    if not isinstance(binding, Mapping):
        return "frozen channelEmulator binding is malformed"
    if parsed_plan.binding_digest != binding.get("binding_digest"):
        return "frozen channelEmulator plan and binding digest do not match"
    driver = _driver_from_hal(hal)
    manifest = channel_emulator_manifest_of(driver)
    if manifest is None:
        return "loaded channelEmulator driver has no manifest"
    try:
        live = resolve_channel_emulator_execution_plan(
            manifest=manifest,
            driver_source=parsed_plan.driver_source,
            requested_load_mode=parsed_plan.requested_load_mode,
            binding_digest=parsed_plan.binding_digest,
        )
    except ValueError as exc:
        return str(exc)
    return verify_frozen_channel_emulator_execution_plan(validated_plan, live)


def _combined_validator(
    *,
    binding: Any,
    plan: Any,
    validate_before_remote: Callable[[object], str | None] | None,
) -> Callable[[object], str | None]:
    def validate(hal: object) -> str | None:
        error = _validate_frozen_pair_and_live_driver(hal, binding, plan)
        if error is not None:
            return error
        return validate_before_remote(hal) if validate_before_remote is not None else None

    if validate_before_remote is not None:
        for attribute in ("validation_identity", "lease_audit_context"):
            if hasattr(validate_before_remote, attribute):
                setattr(validate, attribute, getattr(validate_before_remote, attribute))
    return validate


@asynccontextmanager
async def channel_emulator_execution_scope(
    db: Any,
    execution: Any,
    *,
    purpose: str,
    binding: Any,
    plan: Any,
    hal: Any,
    validate_before_remote: Callable[[object], str | None] | None,
) -> AsyncIterator[ChannelEmulatorExecutionScopeOutcome]:
    """Validate, acquire, run, safe-idle and release one frozen CE session.

    A normal context exit is not evidence of business success.  The caller must
    explicitly call ``mark_operation_result`` on the yielded outcome.
    """

    session_id = uuid4().hex
    installed_mock = False
    safe_idle_confirmed = False
    scope_error: BaseException | None = None
    lease_outcome: InstrumentTestLeaseOutcome | None = None
    scoped_outcome: ChannelEmulatorExecutionScopeOutcome | None = None
    drivers = getattr(hal, "drivers", None)
    if not isinstance(drivers, dict):
        raise ChannelEmulatorExecutionSessionError(
            "HAL channelEmulator registry is unavailable"
        )
    if drivers.get(CHANNEL_EMULATOR_CATEGORY_KEY) is None:
        mode = binding.get("execution_mode") if isinstance(binding, Mapping) else None
        if mode == "simulated":
            drivers[CHANNEL_EMULATOR_CATEGORY_KEY] = MockChannelEmulator(
                "execution-scoped-channel-emulator",
                {"model": "Mock Channel Emulator"},
            )
            installed_mock = True

    validator = _combined_validator(
        binding=binding,
        plan=plan,
        validate_before_remote=validate_before_remote,
    )
    operation_error: BaseException | None = None
    try:
        try:
            async with instrument_test_lease(
                purpose,
                control_f64=True,
                control_uxm=True,
                enable_monitoring=False,
                validate_before_remote=validator,
            ) as outcome:
                lease_outcome = outcome
                scoped_outcome = ChannelEmulatorExecutionScopeOutcome(outcome)
                try:
                    yield scoped_outcome
                except BaseException as exc:
                    operation_error = exc
                    raise
                finally:
                    driver = _driver_from_hal(hal)
                    try:
                        parsed_plan = plan_from_frozen_payload(plan)
                        if not parsed_plan.planned("stop_emulation"):
                            raise ChannelEmulatorExecutionSessionError(
                                parsed_plan.rejection("stop_emulation")
                            )
                        stop = getattr(driver, "stop_emulation", None)
                        if not inspect.iscoroutinefunction(stop):
                            raise ChannelEmulatorExecutionSessionError(
                                "channelEmulator safe idle contract requires async stop_emulation"
                            )
                        if await stop() is not True:
                            raise ChannelEmulatorExecutionSessionError(
                                "channelEmulator safe idle was not confirmed"
                            )
                        safe_idle_confirmed = True
                    except BaseException:
                        if operation_error is None:
                            raise
                        logger.exception(
                            "channelEmulator safe idle failed while preserving operation error"
                        )
        except BaseException as exc:
            scope_error = exc
            raise
    finally:
        if installed_mock:
            drivers.pop(CHANNEL_EMULATOR_CATEGORY_KEY, None)
        if db is not None:
            terminal_state = (
                "cancelled"
                if isinstance(scope_error, asyncio.CancelledError)
                else (
                    "completed"
                    if scope_error is None
                    and scoped_outcome is not None
                    and scoped_outcome.operation_succeeded is True
                    and safe_idle_confirmed
                    and (
                        binding.get("execution_mode") == "simulated"
                        or (
                            lease_outcome is not None
                            and lease_outcome.channel_emulator_remote_acquired_confirmed
                            is True
                            and lease_outcome.channel_emulator_transport_released_confirmed
                            is True
                        )
                    )
                    else "failed"
                )
            )
            payload = {
                "schema_version": 1,
                "session_id": session_id,
                "execution_id": str(execution.id),
                "binding_digest": binding.get("binding_digest"),
                "binding_freeze_digest": binding.get("digest"),
                "plan_digest": plan.get("digest") if isinstance(plan, Mapping) else None,
                "execution_mode": binding.get("execution_mode"),
                "adapter_id": plan.get("adapter_id") if isinstance(plan, Mapping) else None,
                "driver_module": binding.get("expected_driver_module"),
                "driver_name": binding.get("expected_driver_name"),
                "driver_connection": binding.get("expected_driver_connection"),
                "lease_id": lease_outcome.lease_id if lease_outcome is not None else None,
                "instrument_id": (
                    lease_outcome.channel_emulator_instrument_id
                    if lease_outcome is not None
                    else None
                ),
                "remote_acquired_confirmed": (
                    lease_outcome.channel_emulator_remote_acquired_confirmed
                    if lease_outcome is not None
                    else None
                ),
                "safe_idle_confirmed": safe_idle_confirmed,
                "transport_released_confirmed": (
                    lease_outcome.channel_emulator_transport_released_confirmed
                    if lease_outcome is not None
                    else None
                ),
                "operation_succeeded": (
                    scoped_outcome.operation_succeeded
                    if scoped_outcome is not None
                    else None
                ),
                "terminal_state": terminal_state,
                "error_type": type(scope_error).__name__ if scope_error is not None else None,
            }
            evidence = {**payload, "digest": canonical_payload_digest(payload)}
            try:
                persist_channel_emulator_terminal_evidence(db, execution.id, evidence)
            except BaseException:
                if scope_error is None:
                    raise
                logger.exception(
                    "channelEmulator terminal evidence persistence failed while preserving error"
                )
