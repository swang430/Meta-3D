"""Execution-frozen channel-emulator lifecycle shared by every test entry."""

from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Annotated, Any, AsyncIterator, Callable, Literal, Mapping
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    NonNegativeInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.channel_emulator_execution_plan import (
    plan_from_frozen_payload,
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import channel_emulator_manifest_of
from app.services.channel_emulator_binding import (
    CHANNEL_EMULATOR_CATEGORY_KEY,
    FrozenChannelEmulatorTransport,
    validate_frozen_channel_emulator_before_remote,
)
from app.services.channel_emulator_execution_plan import (
    CHANNEL_ASSET_RESOLUTION_FREEZE_KEY,
    validate_frozen_channel_emulator_load_context,
    validate_frozen_channel_emulator_execution_plan,
    verify_frozen_channel_emulator_execution_plan,
)
from app.services.channel_emulator_operation_receipt import (
    ChannelEmulatorOperationRecorderOwner,
    channel_emulator_operation_receipt_chain_digest,
    empty_channel_emulator_operation_receipt_chain_digest,
    channel_emulator_operation_recorder_scope,
    current_channel_emulator_operation_recorder_owner,
    record_channel_emulator_operation,
)
from app.services.instrument_test_lease import (
    InstrumentTestLeaseError,
    InstrumentTestLeaseOutcome,
    await_completion_despite_cancellation,
    instrument_test_lease,
)

logger = logging.getLogger(__name__)

CE_TERMINAL_EVIDENCE_CONFIG_KEY = "channel_emulator_terminal_evidence"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


@dataclass
class _ChannelEmulatorSafeIdleState:
    """Task-local ownership of the one SAFE_IDLE attempt for this session."""

    driver: Any
    action: Literal["stop_emulation", "clear_passthrough_mode"] = "stop_emulation"
    attempted: bool = False
    confirmed: bool = False
    error: BaseException | None = None


_channel_emulator_safe_idle_owner: ContextVar[
    _ChannelEmulatorSafeIdleState | None
] = ContextVar(
    "channel_emulator_safe_idle_owner", default=None
)


def channel_emulator_safe_idle_is_scope_owned() -> bool:
    """Whether the current task is inside the single CE execution scope."""

    return _channel_emulator_safe_idle_owner.get() is not None


class ChannelEmulatorExecutionSessionError(InstrumentTestLeaseError):
    """The frozen CE session could not reach a confirmed safe terminal state."""


class FrozenChannelEmulatorTerminalEvidence(BaseModel):
    """Strict immutable terminal evidence; a matching digest alone is insufficient."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1, 2]
    session_id: NonEmptyString
    operation_scope: NonEmptyString | None = None
    execution_id: NonEmptyString
    measurement_attempt_id: NonEmptyString | None = None
    binding_digest: NonEmptyString
    binding_freeze_digest: NonEmptyString
    plan_digest: NonEmptyString
    execution_mode: Literal["real", "simulated"]
    adapter_id: NonEmptyString
    driver_module: NonEmptyString | None
    driver_name: NonEmptyString | None
    driver_connection: FrozenChannelEmulatorTransport | None
    lease_id: NonEmptyString | None
    instrument_id: NonEmptyString | None
    remote_acquired_confirmed: bool | None
    required_safe_idle_action: Literal["stop_emulation", "clear_passthrough_mode"]
    safe_idle_action: Literal["stop_emulation", "clear_passthrough_mode"]
    safe_idle_confirmed: bool
    transport_released_confirmed: bool | None
    operation_succeeded: bool | None
    terminal_state: Literal["completed", "failed", "cancelled"]
    error_type: NonEmptyString | None
    safe_idle_error_type: NonEmptyString | None
    operation_receipt_count: NonNegativeInt | None = None
    operation_receipts_digest: NonEmptyString | None = None
    operation_receipt_ids: tuple[NonEmptyString, ...] | None = None
    safe_idle_receipt_id: NonEmptyString | None = None
    transport_release_receipt_id: NonEmptyString | None = None
    digest: NonEmptyString

    @field_validator("operation_receipt_ids", mode="before")
    @classmethod
    def accept_persisted_receipt_id_array(cls, value: Any) -> Any:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "FrozenChannelEmulatorTerminalEvidence":
        receipt_values = (
            self.measurement_attempt_id,
            self.operation_receipt_count,
            self.operation_receipts_digest,
            self.operation_receipt_ids,
            self.safe_idle_receipt_id,
            self.transport_release_receipt_id,
        )
        if self.schema_version == 1:
            if any(value is not None for value in receipt_values):
                raise ValueError("v1 channelEmulator terminal cannot claim receipts")
        else:
            if (
                self.operation_receipt_count is None
                or self.operation_receipts_digest is None
                or self.operation_receipt_ids is None
                or self.operation_receipt_count != len(self.operation_receipt_ids)
                or len(set(self.operation_receipt_ids))
                != len(self.operation_receipt_ids)
            ):
                raise ValueError(
                    "v2 channelEmulator terminal receipt chain is incomplete"
                )
            if self.terminal_state == "completed" and (
                self.safe_idle_receipt_id not in self.operation_receipt_ids
                or self.transport_release_receipt_id
                not in self.operation_receipt_ids
            ):
                raise ValueError(
                    "completed v2 terminal misses safe-idle/release receipts"
                )
        if self.safe_idle_action != self.required_safe_idle_action:
            raise ValueError(
                "channelEmulator terminal safe idle action misses scope requirement"
            )
        if self.terminal_state == "completed":
            if (
                self.lease_id is None
                or self.instrument_id is None
                or self.operation_succeeded is not True
                or self.safe_idle_confirmed is not True
                or self.error_type is not None
                or self.safe_idle_error_type is not None
            ):
                raise ValueError("completed channelEmulator terminal is contradictory")
            if self.execution_mode == "real":
                if (
                    self.driver_module is None
                    or self.driver_name is None
                    or self.driver_connection is None
                    or self.remote_acquired_confirmed is not True
                    or self.transport_released_confirmed is not True
                ):
                    raise ValueError("completed real channelEmulator lifecycle is incomplete")
            elif (
                self.driver_connection is not None
                or self.remote_acquired_confirmed is not None
                or self.transport_released_confirmed is not None
            ):
                raise ValueError("completed simulated terminal claimed real transport evidence")
        elif self.error_type is None and self.safe_idle_error_type is None:
            raise ValueError("non-completed channelEmulator terminal has no failure identity")
        if self.terminal_state == "cancelled" and self.error_type != "CancelledError":
            raise ValueError("cancelled channelEmulator terminal has invalid error identity")
        return self


def validate_channel_emulator_terminal_evidence(
    evidence: Any,
) -> dict[str, Any]:
    """Parse the complete terminal schema, then verify its original canonical digest."""

    if not isinstance(evidence, dict):
        raise ValueError("channelEmulator terminal evidence is malformed")
    try:
        FrozenChannelEmulatorTerminalEvidence.model_validate(evidence)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(
            f"channelEmulator terminal evidence is malformed: {exc}"
        ) from exc
    payload = {key: value for key, value in evidence.items() if key != "digest"}
    if evidence.get("digest") != canonical_payload_digest(payload):
        raise ValueError("channelEmulator terminal evidence digest mismatch")
    return evidence


async def ensure_channel_emulator_safe_idle() -> bool:
    """Execute this scope's SAFE_IDLE exactly once and to a real terminal result."""

    state = _channel_emulator_safe_idle_owner.get()
    if state is None:
        raise ChannelEmulatorExecutionSessionError(
            "channelEmulator SAFE_IDLE has no execution-session owner"
        )
    if state.attempted:
        if state.error is not None:
            raise state.error
        return state.confirmed
    state.attempted = True
    # Driver capabilities were already resolved from the frozen manifest before
    # Remote acquire; direct interface access avoids inventing a second
    # ``hasattr/getattr`` capability truth here.
    if state.action == "stop_emulation":
        safe_idle = state.driver.stop_emulation
    else:
        safe_idle = state.driver.clear_passthrough_mode
    if not inspect.iscoroutinefunction(safe_idle):
        state.error = ChannelEmulatorExecutionSessionError(
            "channelEmulator safe idle contract requires async " f"{state.action}"
        )
        raise state.error
    stop_outcome = None

    async def invoke_safe_idle() -> bool:
        nonlocal stop_outcome
        stop_outcome = await await_completion_despite_cancellation(safe_idle())
        operation_error = stop_outcome.error
        if isinstance(operation_error, asyncio.CancelledError):
            inner_cancel = operation_error
            operation_error = ChannelEmulatorExecutionSessionError(
                "channelEmulator safe idle driver operation cancelled internally"
            )
            operation_error.__cause__ = inner_cancel
        if operation_error is not None:
            raise operation_error
        return stop_outcome.value is True

    try:
        recorder_owner = current_channel_emulator_operation_recorder_owner()
        if (
            recorder_owner is None
            or recorder_owner.automatic_lifecycle_receipts is not True
        ):
            confirmed = await invoke_safe_idle()
        else:
            confirmed = await record_channel_emulator_operation(
                phase="stop",
                operation=state.action,
                requested=(
                    {"state": "STOPPED"}
                    if state.action == "stop_emulation"
                    else {"mode": 0}
                ),
                invoke=invoke_safe_idle,
            )
    except BaseException as error:
        caller_cancellation = (
            stop_outcome.delayed_cancellation
            if stop_outcome is not None
            else None
        )
        state.error = error
        if caller_cancellation is not None:
            _attach_secondary_failure(
                caller_cancellation,
                attribute="channel_emulator_safe_idle_error",
                stage="SAFE_IDLE",
                secondary=error,
            )
            raise caller_cancellation
        raise

    caller_cancellation = (
        stop_outcome.delayed_cancellation if stop_outcome is not None else None
    )
    current_task = asyncio.current_task()
    if (
        caller_cancellation is None
        and current_task is not None
        and current_task.cancelling()
    ):
        caller_cancellation = asyncio.CancelledError(
            "channelEmulator execution task was cancelled during SAFE_IDLE"
        )
    error: BaseException | None = None
    if confirmed is not True:
        error = ChannelEmulatorExecutionSessionError(
            "channelEmulator safe idle was not confirmed"
        )
    if error is not None:
        state.error = error
        if caller_cancellation is not None:
            _attach_secondary_failure(
                caller_cancellation,
                attribute="channel_emulator_safe_idle_error",
                stage="SAFE_IDLE",
                secondary=error,
            )
            raise caller_cancellation
        raise error
    state.confirmed = True
    if caller_cancellation is not None:
        raise caller_cancellation
    return True


def require_channel_emulator_passthrough_clear() -> None:
    """Arm the post-STATIC terminal action after the pre-bypass stop succeeded."""

    state = _channel_emulator_safe_idle_owner.get()
    if state is None:
        raise ChannelEmulatorExecutionSessionError(
            "channelEmulator passthrough has no execution-session owner"
        )
    if state.action != "stop_emulation" or state.confirmed is not True:
        raise ChannelEmulatorExecutionSessionError(
            "channelEmulator passthrough requires confirmed pre-stop"
        )
    state.action = "clear_passthrough_mode"
    state.attempted = False
    state.confirmed = False
    state.error = None


def require_channel_emulator_stop_after_output_change() -> None:
    """Arm GOS before an operation that may resume channel output.

    This transition is intentionally made before the driver call: a rejected,
    interrupted, or partially applied start can still leave the instrument in
    GO, so the session must conservatively attempt ``stop_emulation`` on exit.
    """

    state = _channel_emulator_safe_idle_owner.get()
    if state is None:
        raise ChannelEmulatorExecutionSessionError(
            "channelEmulator output change has no execution-session owner"
        )
    if state.error is not None:
        raise state.error
    state.action = "stop_emulation"
    state.attempted = False
    state.confirmed = False


def _attach_secondary_failure(
    primary: BaseException,
    *,
    attribute: str,
    stage: str,
    secondary: BaseException,
) -> None:
    """Keep the primary control-flow signal while making safety failure explicit."""

    setattr(primary, attribute, secondary)
    primary.add_note(
        f"channelEmulator {stage} also failed: "
        f"{type(secondary).__name__}: {secondary}"
    )


@dataclass
class ChannelEmulatorExecutionScopeOutcome:
    """Lease truth plus an explicit business-result handshake."""

    lease_outcome: InstrumentTestLeaseOutcome
    recorder_owner: ChannelEmulatorOperationRecorderOwner | None = None
    operation_succeeded: bool | None = None

    def bind_measurement_attempt_id(self, attempt_id: str) -> None:
        """Bind the post-acquire MEASURE attempt to lease and CE receipts."""

        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise TypeError("channelEmulator measurement attempt id must be non-empty")
        existing = self.lease_outcome.measurement_attempt_id
        if existing is not None and existing != attempt_id:
            raise ChannelEmulatorExecutionSessionError(
                "channelEmulator measurement attempt identity cannot be rebound"
            )
        if self.recorder_owner is None:
            raise ChannelEmulatorExecutionSessionError(
                "channelEmulator measurement attempt has no receipt owner"
            )
        receipt_attempt = self.recorder_owner.measurement_attempt_id
        if receipt_attempt is not None and receipt_attempt != attempt_id:
            raise ChannelEmulatorExecutionSessionError(
                "channelEmulator receipt measurement attempt identity cannot be rebound"
            )
        self.lease_outcome.measurement_attempt_id = attempt_id
        self.recorder_owner.measurement_attempt_id = attempt_id

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

    try:
        validate_channel_emulator_terminal_evidence(evidence)
    except ValueError as exc:
        raise ChannelEmulatorExecutionSessionError(str(exc)) from exc
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
        try:
            validate_channel_emulator_terminal_evidence(item)
        except ValueError as exc:
            raise ChannelEmulatorExecutionSessionError(str(exc)) from exc
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
    execution_config: Any,
    authoritative_driver_source: str,
) -> str | None:
    binding_error = validate_frozen_channel_emulator_before_remote(hal, binding)
    if binding_error is not None:
        return binding_error
    try:
        validated_plan = validate_frozen_channel_emulator_execution_plan(plan)
        parsed_plan = plan_from_frozen_payload(validated_plan)
        load_request, _configuration = validate_frozen_channel_emulator_load_context(
            execution_config, validated_plan
        )
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
            driver_source=authoritative_driver_source,
            requested_load_mode=load_request["requested_load_mode"],
            binding_digest=parsed_plan.binding_digest,
        )
    except ValueError as exc:
        return str(exc)
    return verify_frozen_channel_emulator_execution_plan(validated_plan, live)


def _combined_validator(
    *,
    binding: Any,
    plan: Any,
    execution_config: Any,
    authoritative_driver_source: str,
    preflight_before_remote: Callable[[object], str | None] | None,
    validate_before_remote: Callable[[object], str | None] | None,
    prepare_locked_hal: Callable[[object], tuple[object, str | None]],
) -> Callable[[object], str | None]:
    def validate(hal: object) -> str | None:
        validation_hal, prepare_error = prepare_locked_hal(hal)
        if prepare_error is not None:
            return prepare_error
        if preflight_before_remote is not None:
            preflight_error = preflight_before_remote(hal)
            if preflight_error is not None:
                return preflight_error
        error = _validate_frozen_pair_and_live_driver(
            validation_hal,
            binding,
            plan,
            execution_config,
            authoritative_driver_source,
        )
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
    preflight_before_remote: Callable[[object], str | None] | None = None,
) -> AsyncIterator[ChannelEmulatorExecutionScopeOutcome]:
    """Validate, acquire, run, safe-idle and release one frozen CE session.

    A normal context exit is not evidence of business success.  The caller must
    explicitly call ``mark_operation_result`` on the yielded outcome.
    """

    session_id = uuid4().hex
    execution_pk = execution.id
    execution_id = str(execution_pk)
    binding_fields = binding if isinstance(binding, Mapping) else {}
    prepared_mock: MockChannelEmulator | None = None
    scope_error: BaseException | None = None
    lease_outcome: InstrumentTestLeaseOutcome | None = None
    scoped_outcome: ChannelEmulatorExecutionScopeOutcome | None = None
    recorder_owner: ChannelEmulatorOperationRecorderOwner | None = None
    receipt_persistence_enabled = db is not None and callable(
        getattr(db, "query", None)
    )
    safe_idle_state = _ChannelEmulatorSafeIdleState(driver=None)
    safe_idle_error_type: str | None = None
    drivers = getattr(hal, "drivers", None)
    if not isinstance(drivers, dict):
        raise ChannelEmulatorExecutionSessionError(
            "HAL channelEmulator registry is unavailable"
        )
    # The plan writer uses the process HAL that exists before any scoped mock
    # overlay: an already loaded CE is ``hal``; an absent CE is
    # ``fallback_mock``.  Derive that source from the same immutable scope
    # input, never from the plan's own claim or from binding status (a
    # diagnostic-unbound execution may still have a real Mock driver loaded).
    authoritative_driver_source = (
        "hal"
        if drivers.get(CHANNEL_EMULATOR_CATEGORY_KEY) is not None
        else "fallback_mock"
    )
    if binding_fields.get("execution_mode") == "simulated":
        prepared_mock = MockChannelEmulator(
            "execution-scoped-channel-emulator", {"model": "Mock Channel Emulator"}
        )

    def prepare_locked_hal(locked_hal: object) -> tuple[object, str | None]:
        return locked_hal, None

    validator = _combined_validator(
        binding=binding,
        plan=plan,
        execution_config=(
            execution.config if isinstance(execution.config, Mapping) else {}
        ),
        authoritative_driver_source=authoritative_driver_source,
        preflight_before_remote=preflight_before_remote,
        validate_before_remote=validate_before_remote,
        prepare_locked_hal=prepare_locked_hal,
    )
    operation_error: BaseException | None = None
    from app.services.instrument_hal_service import (
        get_hal_service,
        pinned_hal_service_view,
        scoped_hal_service_view,
    )

    try:
        try:
            overrides = (
                {CHANNEL_EMULATOR_CATEGORY_KEY: prepared_mock}
                if prepared_mock is not None
                else {}
            )
            # 只给当前 execution task（及它主动派生的子任务）暴露临时模拟驱动；
            # 进程级 hal.drivers 从不突变，并发 readiness/preview/freeze 请求仍看
            # 到真实的“未加载”状态。
            with scoped_hal_service_view(driver_overrides=overrides):
                async with instrument_test_lease(
                    purpose,
                    control_f64=True,
                    control_uxm=True,
                    enable_monitoring=False,
                    validate_before_remote=validator,
                ) as outcome:
                    lease_outcome = outcome
                    acquired_driver = (
                        outcome.channel_emulator_driver or prepared_mock
                    )
                    if acquired_driver is None:
                        raise ChannelEmulatorExecutionSessionError(
                            "channelEmulator lease did not retain its acquired driver"
                        )
                    # The outer provisional view intentionally follows reloads
                    # until the lease wins the lock.  From this point onward,
                    # pin the exact successfully acquired HAL/driver set so body
                    # code cannot splice a replacement into this execution.
                    leased_hal = get_hal_service()
                    with pinned_hal_service_view(
                        base_hal=leased_hal,
                        driver_overrides={
                            CHANNEL_EMULATOR_CATEGORY_KEY: acquired_driver
                        },
                    ):
                        safe_idle_state = _ChannelEmulatorSafeIdleState(acquired_driver)
                        parsed_plan = plan_from_frozen_payload(plan)
                        execution_config = (
                            execution.config
                            if isinstance(execution.config, Mapping)
                            else {}
                        )
                        base_station_freeze = execution_config.get(
                            "base_station_adapter_profile_freeze"
                        )
                        asset_freeze = (
                            base_station_freeze.get(
                                CHANNEL_ASSET_RESOLUTION_FREEZE_KEY
                            )
                            if isinstance(base_station_freeze, Mapping)
                            else None
                        )
                        instrument_id = (
                            outcome.channel_emulator_instrument_id
                            or getattr(acquired_driver, "instrument_id", None)
                        )
                        recorder_owner = ChannelEmulatorOperationRecorderOwner(
                            db=db,
                            execution_pk=execution_pk,
                            execution_id=execution_id,
                            session_id=session_id,
                            operation_scope=purpose,
                            measurement_attempt_id=outcome.measurement_attempt_id,
                            binding_digest=binding_fields.get("binding_digest"),
                            binding_freeze_digest=binding_fields.get("digest"),
                            plan_digest=parsed_plan.digest,
                            asset_digest=(
                                str(asset_freeze.get("digest"))
                                if isinstance(asset_freeze, Mapping)
                                and asset_freeze.get("digest")
                                else None
                            ),
                            lease_id=outcome.lease_id,
                            instrument_id=instrument_id,
                            adapter_id=parsed_plan.adapter_id,
                            execution_mode=binding_fields.get("execution_mode"),
                            plan=parsed_plan,
                            driver=acquired_driver,
                            automatic_lifecycle_receipts=(
                                receipt_persistence_enabled
                            ),
                        )
                        scoped_outcome = ChannelEmulatorExecutionScopeOutcome(
                            outcome,
                            recorder_owner=recorder_owner,
                        )

                        async def record_transport_release(
                            invoke: Callable[[], Any],
                        ) -> bool:
                            if recorder_owner is None:  # pragma: no cover
                                raise ChannelEmulatorExecutionSessionError(
                                    "channelEmulator release recorder owner is missing"
                                )
                            with channel_emulator_operation_recorder_scope(
                                recorder_owner
                            ):
                                return await record_channel_emulator_operation(
                                    phase="release",
                                    operation="transport_release",
                                    requested={"control_mode": "local"},
                                    invoke=invoke,
                                )

                        if receipt_persistence_enabled:
                            outcome.channel_emulator_release_recorder = (
                                record_transport_release
                            )
                        with channel_emulator_operation_recorder_scope(
                            recorder_owner
                        ):
                            ownership_token = _channel_emulator_safe_idle_owner.set(
                                safe_idle_state
                            )
                            try:
                                yield scoped_outcome
                            except BaseException as exc:
                                operation_error = exc
                                raise
                            finally:
                                try:
                                    parsed_plan = plan_from_frozen_payload(plan)
                                    if not parsed_plan.planned(safe_idle_state.action):
                                        raise ChannelEmulatorExecutionSessionError(
                                            parsed_plan.rejection(safe_idle_state.action)
                                        )
                                    if safe_idle_state.attempted:
                                        if safe_idle_state.error is not None:
                                            safe_idle_error_type = type(
                                                safe_idle_state.error
                                            ).__name__
                                            if operation_error is None:
                                                raise safe_idle_state.error
                                    else:
                                        await ensure_channel_emulator_safe_idle()
                                except asyncio.CancelledError:
                                    raise
                                except BaseException as safe_idle_error:
                                    safe_idle_error_type = type(safe_idle_error).__name__
                                    if operation_error is None:
                                        raise
                                    _attach_secondary_failure(
                                        operation_error,
                                        attribute="channel_emulator_safe_idle_error",
                                        stage="SAFE_IDLE",
                                        secondary=safe_idle_error,
                                    )
                                    logger.exception(
                                        "channelEmulator safe idle failed while preserving operation error"
                                    )
                                finally:
                                    _channel_emulator_safe_idle_owner.reset(ownership_token)
                if (
                    recorder_owner is not None
                    and receipt_persistence_enabled
                    and binding_fields.get("execution_mode") == "simulated"
                    and not any(
                        item.get("operation") == "transport_release"
                        for item in recorder_owner.recorded_receipts
                    )
                ):
                    async def simulated_release_not_applicable() -> bool:
                        return True

                    with channel_emulator_operation_recorder_scope(recorder_owner):
                        await record_channel_emulator_operation(
                            phase="release",
                            operation="transport_release",
                            requested={"control_mode": "local"},
                            invoke=simulated_release_not_applicable,
                        )
        except BaseException as exc:
            scope_error = exc
            raise
    finally:
        if db is not None:
            operation_receipts = (
                list(recorder_owner.recorded_receipts)
                if recorder_owner is not None
                else []
            )
            operation_receipt_ids = tuple(
                item["receipt_id"] for item in operation_receipts
            )
            operation_receipts_digest = (
                channel_emulator_operation_receipt_chain_digest(
                    operation_receipts
                )
                if operation_receipts
                else empty_channel_emulator_operation_receipt_chain_digest()
            )
            safe_idle_receipt_id = next(
                (
                    item["receipt_id"]
                    for item in reversed(operation_receipts)
                    if item.get("operation") == safe_idle_state.action
                ),
                None,
            )
            transport_release_receipt_id = next(
                (
                    item["receipt_id"]
                    for item in reversed(operation_receipts)
                    if item.get("operation") == "transport_release"
                ),
                None,
            )
            terminal_state = (
                "cancelled"
                if isinstance(scope_error, asyncio.CancelledError)
                else (
                    "completed"
                    if scope_error is None
                    and scoped_outcome is not None
                    and scoped_outcome.operation_succeeded is True
                    and safe_idle_state.confirmed
                    and (
                        binding_fields.get("execution_mode") == "simulated"
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
                "schema_version": 2 if receipt_persistence_enabled else 1,
                "session_id": session_id,
                "operation_scope": purpose,
                "execution_id": execution_id,
                "measurement_attempt_id": (
                    recorder_owner.measurement_attempt_id
                    if recorder_owner is not None
                    else None
                ),
                "binding_digest": binding_fields.get("binding_digest"),
                "binding_freeze_digest": binding_fields.get("digest"),
                "plan_digest": plan.get("digest") if isinstance(plan, Mapping) else None,
                "execution_mode": binding_fields.get("execution_mode"),
                "adapter_id": plan.get("adapter_id") if isinstance(plan, Mapping) else None,
                "driver_module": binding_fields.get("expected_driver_module"),
                "driver_name": binding_fields.get("expected_driver_name"),
                "driver_connection": binding_fields.get("expected_driver_connection"),
                "lease_id": lease_outcome.lease_id if lease_outcome is not None else None,
                "instrument_id": (
                    lease_outcome.channel_emulator_instrument_id
                    if lease_outcome is not None
                    and lease_outcome.channel_emulator_instrument_id is not None
                    else getattr(safe_idle_state.driver, "instrument_id", None)
                ),
                "remote_acquired_confirmed": (
                    None
                    if binding_fields.get("execution_mode") == "simulated"
                    else (
                        lease_outcome.channel_emulator_remote_acquired_confirmed
                        if lease_outcome is not None
                        else None
                    )
                ),
                "required_safe_idle_action": safe_idle_state.action,
                "safe_idle_action": safe_idle_state.action,
                "safe_idle_confirmed": safe_idle_state.confirmed,
                "transport_released_confirmed": (
                    None
                    if binding_fields.get("execution_mode") == "simulated"
                    else (
                        lease_outcome.channel_emulator_transport_released_confirmed
                        if lease_outcome is not None
                        else None
                    )
                ),
                "operation_succeeded": (
                    scoped_outcome.operation_succeeded
                    if scoped_outcome is not None
                    else None
                ),
                "terminal_state": terminal_state,
                "error_type": (
                    type(scope_error).__name__
                    if scope_error is not None
                    else (
                        None
                        if terminal_state == "completed"
                        else (
                            "OperationResultMissing"
                            if scoped_outcome is None
                            or scoped_outcome.operation_succeeded is None
                            else "OperationFailed"
                        )
                    )
                ),
                "safe_idle_error_type": (
                    safe_idle_error_type
                    or (
                        type(safe_idle_state.error).__name__
                        if safe_idle_state.error is not None
                        else None
                    )
                ),
                **(
                    {
                        "operation_receipt_count": len(operation_receipts),
                        "operation_receipts_digest": operation_receipts_digest,
                        "operation_receipt_ids": operation_receipt_ids,
                        "safe_idle_receipt_id": safe_idle_receipt_id,
                        "transport_release_receipt_id": (
                            transport_release_receipt_id
                        ),
                    }
                    if receipt_persistence_enabled
                    else {}
                ),
            }
            evidence = {**payload, "digest": canonical_payload_digest(payload)}
            try:
                if scope_error is not None:
                    rollback = getattr(db, "rollback", None)
                    if not callable(rollback):
                        raise ChannelEmulatorExecutionSessionError(
                            "database session cannot isolate failed CE terminal evidence"
                        )
                    rollback()
                persist_channel_emulator_terminal_evidence(db, execution_pk, evidence)
            except BaseException as persistence_error:
                if scope_error is None:
                    raise
                _attach_secondary_failure(
                    scope_error,
                    attribute="channel_emulator_terminal_persistence_error",
                    stage="terminal persistence",
                    secondary=persistence_error,
                )
                logger.exception(
                    "channelEmulator terminal evidence persistence failed while preserving error"
                )
