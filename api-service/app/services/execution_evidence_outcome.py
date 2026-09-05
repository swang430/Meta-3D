"""Execution-scoped evidence compatibility and completion semantics.

The projection in this module is deliberately pure: it reads immutable
evidence snapshots plus the execution row's authoritative lifecycle status.
It never consults the current adapter registry, LabProfile, connection, or
site certification.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError

from app.hal.base_station_adapter_profile import BaseStationAdapterProfileResolution
from app.hal.base_station_compatibility import (
    BaseStationCompatibilityVerdict,
    BaseStationExecutionRequirements,
    canonical_payload_digest,
    evaluate_base_station_compatibility,
    manifest_compatibility_digest,
    build_measure_execution_requirements_from_configuration,
)
from app.hal.base_station_manifest import BaseStationAdapterManifest
from app.hal.base_station_mac_profile import (
    CMW500_LTE_PROFILE_SOURCE,
    UXM_NR_PROFILE_SOURCE,
)
from app.hal.channel_emulator_execution_plan import (
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import ChannelEmulatorManifest
from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    ExecutionQualification,
    validate_frozen_execution_qualification,
)
from app.services.base_station_adapter_profile import (
    MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    frozen_mac_profile_from_adapter_freeze,
)
from app.services.channel_emulator_binding import (
    CE_FREEZE_CONFIG_KEY,
    validate_frozen_channel_emulator_binding,
)
from app.services.channel_emulator_certification import (
    CE_EXECUTION_QUALIFICATION_CONFIG_KEY,
    ChannelEmulatorExecutionQualification,
    _has_certifiable_channel_emulator_frequency_evidence,
    validate_frozen_channel_emulator_execution_qualification,
)
from app.services.channel_emulator_execution_plan import (
    CHANNEL_ASSET_RESOLUTION_FREEZE_KEY,
    CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
    CE_PLAN_FREEZE_CONFIG_KEY,
    validate_frozen_channel_emulator_load_context,
    validate_frozen_channel_emulator_execution_plan,
    verify_frozen_channel_emulator_execution_plan,
)
from app.services.channel_emulator_execution_session import (
    CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    validate_channel_emulator_terminal_evidence,
)
from app.services.channel_emulator_operation_receipt import (
    CE_OPERATION_RECEIPTS_CONFIG_KEY,
    ChannelEmulatorOperationEvidenceProjection,
    ChannelOperationFieldEvidenceProjection,
    ChannelOperationReceiptEvidenceProjection,
    ChannelOperationSessionEvidenceProjection,
    channel_emulator_operation_receipt_chain_digest,
    empty_channel_emulator_operation_receipt_chain_digest,
    empty_channel_emulator_operation_evidence,
    validate_channel_emulator_operation_receipt,
)


CompatibilityClassification = Literal[
    "compatible", "diagnostic", "legacy", "invalid"
]
CompletionSemantic = Literal[
    "valid_test_completed",
    "diagnostic_completed",
    "pipeline_completed",
    "not_completed",
]
QualificationClassification = Literal["formal", "diagnostic", "legacy"]


_PRE_P2_54_MANIFESTS = {
    "uxm": {
        "digest": "f0c48a1a28ddfc17995b84a20bd826e429a4f46de5dcdc7928bdaa459c6656fa",
        "profile": {
            "kind": "nr_throughput",
            "profile_version": 1,
            "rat": "nr5g",
            "application_evidence": "command_error_queue",
            "source_reference": UXM_NR_PROFILE_SOURCE,
        },
    },
    "cmw500": {
        "digest": "e64a9ef3959911a3a6a54d0ac47cccf22b9c6af43b19034b8c1996559d35c62f",
        "profile": {
            "kind": "lte_rmc",
            "profile_version": 1,
            "rat": "lte",
            "application_evidence": "authoritative_readback",
            "source_reference": CMW500_LTE_PROFILE_SOURCE,
        },
    },
}


class ExecutionEvidenceOutcome(BaseModel):
    """Single server-owned projection for history, reports, and formal gates."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_serialization_defaults_required=True,
    )

    schema_version: Literal[1] = 1
    compatibility_classification: CompatibilityClassification
    completion_semantic: CompletionSemantic
    formal_eligible: bool
    compatibility_digest: str | None
    qualification_classification: QualificationClassification
    reasons: tuple[str, ...]
    pipeline_status: str
    channel_emulator_operation_evidence: (
        ChannelEmulatorOperationEvidenceProjection
    ) = empty_channel_emulator_operation_evidence()


def _channel_emulator_v2_receipt_chain_error(
    config: Mapping[str, Any],
    terminal: Mapping[str, Any],
    *,
    simulated: bool,
) -> str | None:
    required_confirmed_fields = {
        "load_channel": frozenset({"emulation_file"}),
        "set_output_gain": frozenset({"gain_db"}),
        "set_output_level_dbm": frozenset({"level_dbm"}),
        "set_baseband_power": frozenset({"reference_dbm"}),
        "set_crest_factor": frozenset({"crest_db"}),
        "autoset_inputs": frozenset({"input_ports"}),
        "set_input_measurement_mode": frozenset({"mode"}),
        "set_burst_trigger_level": frozenset({"trigger_dbm"}),
        "ensure_topology": frozenset({"topology"}),
        "measure_input": frozenset({"measurement"}),
        "get_input_level_limits": frozenset({"limits"}),
        "get_group_clipping": frozenset({"clipping"}),
        "get_system_status": frozenset({"system_status"}),
        "start_emulation": frozenset({"state"}),
        "stop_emulation": frozenset({"state"}),
        "set_passthrough_mode": frozenset({"mode"}),
        "clear_passthrough_mode": frozenset({"mode"}),
        "transport_release": frozenset({"control_mode"}),
    }
    raw_receipts = config.get(CE_OPERATION_RECEIPTS_CONFIG_KEY)
    if not isinstance(raw_receipts, list):
        return "channelEmulator v2 operation receipt chain is missing"

    validated_receipts: list[Mapping[str, Any]] = []
    receipt_by_id: dict[str, Mapping[str, Any]] = {}
    for raw_receipt in raw_receipts:
        if not isinstance(raw_receipt, Mapping):
            return "channelEmulator operation receipt is malformed"
        try:
            receipt = validate_channel_emulator_operation_receipt(
                dict(raw_receipt)
            )
        except ValueError as exc:
            return str(exc)
        receipt_id = receipt["receipt_id"]
        if receipt_id in receipt_by_id:
            return "channelEmulator operation receipt id is duplicated"
        receipt_by_id[receipt_id] = receipt
        validated_receipts.append(receipt)

    receipt_ids = terminal.get("operation_receipt_ids")
    if not isinstance(receipt_ids, (list, tuple)):
        return "channelEmulator v2 terminal receipt ids are malformed"
    selected: list[Mapping[str, Any]] = []
    for receipt_id in receipt_ids:
        receipt = receipt_by_id.get(receipt_id)
        if receipt is None:
            return "channelEmulator v2 terminal references a missing receipt"
        selected.append(receipt)
    if terminal.get("operation_receipt_count") != len(selected):
        return "channelEmulator v2 terminal receipt count does not match chain"
    if selected:
        try:
            selected_digest = channel_emulator_operation_receipt_chain_digest(
                selected
            )
        except ValueError as exc:
            return str(exc)
    elif terminal.get("terminal_state") == "completed":
        return "completed channelEmulator v2 receipt chain is incomplete"
    else:
        selected_digest = empty_channel_emulator_operation_receipt_chain_digest()
    if terminal.get("operation_receipts_digest") != selected_digest:
        return "channelEmulator v2 terminal receipt chain digest mismatch"

    session_id = terminal.get("session_id")
    complete_session_ids = [
        receipt["receipt_id"]
        for receipt in validated_receipts
        if receipt.get("session_id") == session_id
    ]
    if list(receipt_ids) != complete_session_ids:
        return "channelEmulator v2 terminal omits or reorders a session receipt"

    expected_identity = {
        "session_id": session_id,
        "operation_scope": terminal.get("operation_scope"),
        "execution_id": terminal.get("execution_id"),
        "measurement_attempt_id": terminal.get("measurement_attempt_id"),
        "binding_digest": terminal.get("binding_digest"),
        "binding_freeze_digest": terminal.get("binding_freeze_digest"),
        "plan_digest": terminal.get("plan_digest"),
        "lease_id": terminal.get("lease_id"),
        "instrument_id": terminal.get("instrument_id"),
        "adapter_id": terminal.get("adapter_id"),
        "execution_mode": terminal.get("execution_mode"),
    }
    base_station_freeze = config.get(FREEZE_CONFIG_KEY)
    asset_freeze = (
        base_station_freeze.get(CHANNEL_ASSET_RESOLUTION_FREEZE_KEY)
        if isinstance(base_station_freeze, Mapping)
        else None
    )
    expected_identity["asset_digest"] = (
        asset_freeze.get("digest") if isinstance(asset_freeze, Mapping) else None
    )
    if any(
        receipt.get("measurement_attempt_id")
        != expected_identity["measurement_attempt_id"]
        for receipt in selected
    ):
        return "channelEmulator v2 receipt measurement attempt identity drift"
    if any(
        receipt.get(key) != value
        for receipt in selected
        for key, value in expected_identity.items()
        if key != "measurement_attempt_id"
    ):
        return "channelEmulator v2 receipt identity drift"

    if terminal.get("terminal_state") != "completed":
        return None
    safe_receipt_id = terminal.get("safe_idle_receipt_id")
    release_receipt_id = terminal.get("transport_release_receipt_id")
    if len(selected) < 2:
        return "completed channelEmulator v2 receipt chain is incomplete"
    safe_receipt = receipt_by_id.get(safe_receipt_id)
    release_receipt = receipt_by_id.get(release_receipt_id)
    if (
        safe_receipt is not selected[-2]
        or safe_receipt.get("operation")
        != terminal.get("required_safe_idle_action")
    ):
        return "channelEmulator v2 terminal safe-idle receipt is not final"
    if (
        release_receipt is not selected[-1]
        or release_receipt.get("operation") != "transport_release"
    ):
        return "channelEmulator v2 terminal release receipt is not final"
    safe_fields = safe_receipt.get("fields")
    expected_safe_field = (
        ("state", "STOPPED")
        if safe_receipt.get("operation") == "stop_emulation"
        else ("mode", 0)
    )
    if (
        not isinstance(safe_fields, (list, tuple))
        or len(safe_fields) != 1
        or not isinstance(safe_fields[0], Mapping)
        or safe_fields[0].get("field") != expected_safe_field[0]
        or safe_fields[0].get("requested") != expected_safe_field[1]
        or (
            not simulated
            and safe_fields[0].get("applied") != expected_safe_field[1]
        )
        or safe_fields[0].get("provenance") == "transport_release"
    ):
        return "channelEmulator v2 terminal safe-idle receipt fields are invalid"
    release_fields = release_receipt.get("fields")
    if (
        not isinstance(release_fields, (list, tuple))
        or len(release_fields) != 1
        or not isinstance(release_fields[0], Mapping)
        or release_fields[0].get("field") != "control_mode"
        or release_fields[0].get("requested") != "local"
        or (
            not simulated
            and (
                release_fields[0].get("applied") != "local"
                or release_fields[0].get("provenance") != "transport_release"
            )
        )
    ):
        return "channelEmulator v2 terminal release receipt fields are invalid"
    if any(
        field.get("provenance") == "transport_release"
        for receipt in selected[:-1]
        for field in receipt.get("fields", ())
        if isinstance(field, Mapping)
    ):
        return "channelEmulator transport release provenance is on another operation"
    for receipt in selected:
        if (
            receipt.get("terminal_state") != "completed"
            or receipt.get("operation_succeeded") is not True
        ):
            return "channelEmulator v2 operation receipt lifecycle is incomplete"
        fields = receipt.get("fields")
        if not isinstance(fields, (list, tuple)) or not fields:
            return "channelEmulator v2 operation receipt fields are missing"
        if simulated:
            if receipt.get("simulated") is not True or any(
                field.get("status") in {"applied", "confirmed"}
                for field in fields
                if isinstance(field, Mapping)
            ):
                return "simulated channelEmulator v2 receipt claimed formal evidence"
        elif receipt.get("simulated") is not False:
            return "real channelEmulator v2 receipt claimed simulated evidence"
        else:
            fields_by_name = {
                field.get("field"): field
                for field in fields
                if isinstance(field, Mapping)
            }
            required = required_confirmed_fields.get(
                receipt.get("operation"), frozenset()
            )
            if any(
                fields_by_name.get(name, {}).get("status") != "confirmed"
                for name in required
            ):
                return "real channelEmulator v2 receipt has unconfirmed formal fields"
            if not required:
                return "real channelEmulator v2 receipt operation has no formal evidence policy"
    return None


def _channel_emulator_terminal_projection(
    config: Mapping[str, Any],
    *,
    execution_id: object,
    pipeline_status: str,
) -> tuple[Literal["diagnostic", "invalid"] | None, str | None]:
    """Validate the immutable CE binding/plan/session chain without current state."""

    binding = config.get(CE_FREEZE_CONFIG_KEY)
    plan = config.get(CE_PLAN_FREEZE_CONFIG_KEY)
    load_request = config.get(CE_LOAD_REQUEST_FREEZE_CONFIG_KEY)
    evidence = config.get(CE_TERMINAL_EVIDENCE_CONFIG_KEY)
    if binding is None and plan is None and load_request is None and evidence is None:
        return None, None
    if binding is None or plan is None or load_request is None:
        return "invalid", "channelEmulator binding / execution plan freeze is incomplete"
    try:
        validated_binding = validate_frozen_channel_emulator_binding(binding)
        validated_plan = validate_frozen_channel_emulator_execution_plan(plan)
        validated_load_request, _mimo_configuration = (
            validate_frozen_channel_emulator_load_context(config, plan)
        )
    except ValueError as exc:
        return "invalid", str(exc)
    if validated_plan.get("binding_digest") != validated_binding.get("binding_digest"):
        return "invalid", "channelEmulator plan and binding digest do not match"
    try:
        resolved_binding = validated_binding["resolved_binding"]
        binding_status = resolved_binding["status"]
        execution_mode = validated_binding["execution_mode"]
        if binding_status == "diagnostic_unbound":
            if execution_mode != "simulated":
                return "invalid", "channelEmulator diagnostic binding is not simulated"
            from app.hal.channel_emulator import MockChannelEmulator

            manifest = MockChannelEmulator.adapter_manifest
        elif binding_status == "configured":
            if execution_mode == "simulated":
                # A configured mock run still executes the one authoritative CE
                # mock implementation; the binding manifest describes the
                # selected real model and must not be mistaken for live mock
                # execution capability.
                from app.hal.channel_emulator import MockChannelEmulator

                manifest = MockChannelEmulator.adapter_manifest
            else:
                manifest = ChannelEmulatorManifest.model_validate(
                    resolved_binding["manifest"]
                )
        else:
            return "invalid", "channelEmulator binding status cannot derive a plan"

        authoritative_load_mode = validated_load_request["requested_load_mode"]
        authoritative_plan = resolve_channel_emulator_execution_plan(
            manifest=manifest,
            # Real execution can only use the loaded HAL.  Simulated execution
            # is always diagnostic/non-formal and may have frozen either a
            # loaded Mock (``hal``) or the execution-scoped fallback after the
            # binding was frozen.  Preserve that diagnostic provenance while
            # still deriving the adapter and load mode from independent truth.
            driver_source=(
                validated_plan["driver_source"]
                if execution_mode == "simulated"
                else "hal"
            ),
            requested_load_mode=authoritative_load_mode,
            binding_digest=validated_binding["binding_digest"],
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        return "invalid", f"channelEmulator binding manifest cannot derive plan: {exc}"
    plan_error = verify_frozen_channel_emulator_execution_plan(
        validated_plan,
        authoritative_plan,
        allow_legacy=True,
    )
    if plan_error is not None:
        return (
            "invalid",
            "channelEmulator plan does not match binding manifest: " + plan_error,
        )
    attempt_evidence = config.get("base_station_execution_evidence")
    terminal_required = pipeline_status == "completed" or (
        isinstance(attempt_evidence, Mapping)
        and attempt_evidence.get("current_measurement_attempt_state")
        == "completed"
    )
    if evidence is None and not terminal_required:
        return None, None
    if not isinstance(evidence, list) or not evidence:
        return "invalid", "completed execution has no channelEmulator terminal evidence"

    simulated = validated_binding.get("execution_mode") == "simulated"
    validated_evidence: list[Mapping[str, Any]] = []
    for item in evidence:
        if not isinstance(item, Mapping):
            return "invalid", "channelEmulator terminal evidence is malformed"
        try:
            item = validate_channel_emulator_terminal_evidence(dict(item))
        except ValueError as exc:
            return "invalid", str(exc)
        expected = {
            "execution_id": str(execution_id),
            "binding_digest": validated_binding.get("binding_digest"),
            "binding_freeze_digest": validated_binding.get("digest"),
            "plan_digest": validated_plan.get("digest"),
            "execution_mode": validated_binding.get("execution_mode"),
            "adapter_id": validated_plan.get("adapter_id"),
            "driver_module": validated_binding.get("expected_driver_module"),
            "driver_name": validated_binding.get("expected_driver_name"),
            "driver_connection": validated_binding.get("expected_driver_connection"),
        }
        if any(item.get(key) != value for key, value in expected.items()):
            return "invalid", "channelEmulator terminal evidence identity drift"
        if item.get("safe_idle_action") != item.get("required_safe_idle_action"):
            return "invalid", "channelEmulator terminal safe idle action misses scope requirement"
        if item.get("schema_version") in {2, 3}:
            receipt_error = _channel_emulator_v2_receipt_chain_error(
                config,
                item,
                simulated=simulated,
            )
            if receipt_error is not None:
                return "invalid", receipt_error
        validated_evidence.append(item)

    # Commissioning single-phase runs are deliberately retryable.  Persistence
    # is append-only, so the last terminal record for the same immutable
    # operation scope is the accepted attempt; an earlier failed attempt from
    # that scope must not poison a later successful retry.  Pre-P2-59 records
    # have no scope and therefore remain independently fail-closed.
    effective_evidence: list[Mapping[str, Any]] = []
    latest_by_scope: dict[str, Mapping[str, Any]] = {}
    for item in validated_evidence:
        operation_scope = item.get("operation_scope")
        if isinstance(operation_scope, str):
            latest_by_scope[operation_scope] = item
        else:
            effective_evidence.append(item)
    effective_evidence.extend(latest_by_scope.values())

    attempt_evidence = config.get("base_station_execution_evidence")
    current_attempt_id = (
        attempt_evidence.get("current_measurement_attempt_id")
        if isinstance(attempt_evidence, Mapping)
        and attempt_evidence.get("current_measurement_attempt_state") == "completed"
        else None
    )
    receipt_terminals = [
        item for item in effective_evidence if item.get("schema_version") in {2, 3}
    ]
    if current_attempt_id is not None and receipt_terminals and not any(
        item.get("measurement_attempt_id") == current_attempt_id
        for item in receipt_terminals
    ):
        return (
            "invalid",
            "channelEmulator receipt terminal does not match the current measurement attempt",
        )

    for item in effective_evidence:
        if (
            item.get("terminal_state") != "completed"
            or item.get("operation_succeeded") is not True
            or item.get("safe_idle_confirmed") is not True
        ):
            return "invalid", "channelEmulator execution lifecycle is incomplete"
        if simulated:
            if (
                item.get("remote_acquired_confirmed") is not None
                or item.get("transport_released_confirmed") is not None
            ):
                return "invalid", "simulated channelEmulator claimed real transport evidence"
        elif (
            item.get("remote_acquired_confirmed") is not True
            or item.get("transport_released_confirmed") is not True
            or not isinstance(item.get("instrument_id"), str)
            or not item.get("instrument_id")
        ):
            return "invalid", "real channelEmulator control lifecycle is incomplete"
    if simulated:
        return "diagnostic", "simulated channelEmulator is excluded from formal KPI"
    return None, None


def _public_channel_emulator_operation_evidence(
    config: Mapping[str, Any],
    *,
    pipeline_status: str,
    classification: Literal["diagnostic", "invalid"] | None,
    reason: str | None,
) -> ChannelEmulatorOperationEvidenceProjection:
    """Redact the already-validated CE receipt chain for every API consumer."""

    reasons = (reason,) if reason is not None else ()
    if classification == "invalid":
        return empty_channel_emulator_operation_evidence(
            status="invalid",
            reasons=reasons,
        )

    raw_terminals = config.get(CE_TERMINAL_EVIDENCE_CONFIG_KEY)
    if raw_terminals is None:
        has_frozen_ce = any(
            config.get(key) is not None
            for key in (
                CE_FREEZE_CONFIG_KEY,
                CE_PLAN_FREEZE_CONFIG_KEY,
                CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
            )
        )
        return empty_channel_emulator_operation_evidence(
            status=(
                "pending"
                if has_frozen_ce and pipeline_status != "completed"
                else "not_available"
            ),
            reasons=reasons,
        )
    if not isinstance(raw_terminals, list):
        return empty_channel_emulator_operation_evidence(
            status="invalid",
            reasons=("channelEmulator terminal evidence is malformed",),
        )

    validated_terminals: list[Mapping[str, Any]] = []
    for raw_terminal in raw_terminals:
        try:
            validated_terminals.append(
                validate_channel_emulator_terminal_evidence(dict(raw_terminal))
            )
        except (TypeError, ValueError):
            return empty_channel_emulator_operation_evidence(
                status="invalid",
                reasons=("channelEmulator terminal evidence is malformed",),
            )

    effective: list[Mapping[str, Any]] = []
    latest_by_scope: dict[str, Mapping[str, Any]] = {}
    for terminal in validated_terminals:
        operation_scope = terminal.get("operation_scope")
        if isinstance(operation_scope, str):
            latest_by_scope[operation_scope] = terminal
        else:
            effective.append(terminal)
    effective.extend(latest_by_scope.values())

    raw_receipts = config.get(CE_OPERATION_RECEIPTS_CONFIG_KEY)
    receipts_by_id: dict[str, Mapping[str, Any]] = {}
    if isinstance(raw_receipts, list):
        try:
            receipts_by_id = {
                receipt["receipt_id"]: receipt
                for receipt in (
                    validate_channel_emulator_operation_receipt(dict(item))
                    for item in raw_receipts
                )
            }
        except (KeyError, TypeError, ValueError):
            return empty_channel_emulator_operation_evidence(
                status="invalid",
                reasons=("channelEmulator operation receipt is malformed",),
            )

    sessions: list[ChannelOperationSessionEvidenceProjection] = []
    has_legacy = False
    for terminal in effective:
        if terminal.get("schema_version") == 1:
            has_legacy = True
            sessions.append(
                ChannelOperationSessionEvidenceProjection(
                    session_id=terminal["session_id"],
                    operation_scope=terminal.get("operation_scope"),
                    status="legacy",
                    receipt_count=None,
                    receipt_chain_digest=None,
                )
            )
            continue
        selected = [
            receipts_by_id[receipt_id]
            for receipt_id in terminal.get("operation_receipt_ids", ())
        ]
        receipt_projections: list[ChannelOperationReceiptEvidenceProjection] = []
        for receipt in selected:
            terminal_state = receipt["terminal_state"]
            public_status = (
                "diagnostic"
                if receipt["simulated"]
                else "verified" if terminal_state == "completed" else terminal_state
            )
            receipt_projections.append(
                ChannelOperationReceiptEvidenceProjection(
                    sequence=receipt["sequence"],
                    phase=receipt["phase"],
                    operation=receipt["operation"],
                    terminal_state=terminal_state,
                    operation_succeeded=receipt["operation_succeeded"],
                    simulated=receipt["simulated"],
                    status=public_status,
                    fields=tuple(
                        ChannelOperationFieldEvidenceProjection(
                            field=field["field"],
                            status=field["status"],
                            provenance=field["provenance"],
                            exchange_ids=tuple(field.get("exchange_ids", ())),
                            source_reference=field.get("source_reference"),
                        )
                        for field in receipt["fields"]
                    ),
                    exchange_ids=tuple(receipt.get("exchange_ids", ())),
                    error_queue_exchange_ids=tuple(
                        receipt.get("error_queue_exchange_ids", ())
                    ),
                )
            )
        sessions.append(
            ChannelOperationSessionEvidenceProjection(
                session_id=terminal["session_id"],
                operation_scope=terminal.get("operation_scope"),
                status=(
                    "diagnostic"
                    if classification == "diagnostic"
                    else "verified"
                ),
                receipt_count=terminal["operation_receipt_count"],
                receipt_chain_digest=terminal["operation_receipts_digest"],
                receipts=tuple(receipt_projections),
            )
        )

    status = (
        "diagnostic"
        if classification == "diagnostic"
        else "legacy" if has_legacy else "verified"
    )
    return ChannelEmulatorOperationEvidenceProjection(
        status=status,
        reasons=reasons,
        sessions=tuple(sessions),
    )


def _outer_freeze_digest_error(frozen: Mapping[str, Any]) -> str | None:
    digest = frozen.get("digest")
    if not isinstance(digest, str):
        return "frozen baseStation adapter profile digest is missing"
    payload = {key: value for key, value in frozen.items() if key != "digest"}
    if digest != canonical_payload_digest(payload):
        return "frozen baseStation adapter profile digest mismatch"
    return None


def _historical_manifest_compatibility_error(
    raw_manifest: Any,
    *,
    requirements: BaseStationExecutionRequirements,
    verdict: BaseStationCompatibilityVerdict,
    adapter: str,
) -> str | None:
    """Validate an exact pre-P2-54 manifest without rewriting its digest."""

    if not isinstance(raw_manifest, Mapping) or "mac_profiles" in raw_manifest:
        return "frozen resolved binding manifest does not parse"
    historical_payload = dict(raw_manifest)
    historical_contract = _PRE_P2_54_MANIFESTS.get(adapter)
    historical_digest = canonical_payload_digest(historical_payload)
    if (
        historical_contract is None
        or historical_digest != historical_contract["digest"]
    ):
        return "frozen manifest is not an exact supported historical manifest"
    validation_payload = {
        **historical_payload,
        "mac_profiles": (historical_contract["profile"],),
    }
    if "mac_throughput_config" not in validation_payload.get("operations", ()):
        operations = (
            *validation_payload.get("operations", ()),
            "mac_throughput_config",
        )
        validation_payload["operations"] = operations
        validation_payload["capabilities"] = operations
    try:
        manifest = BaseStationAdapterManifest.model_validate(validation_payload)
    except (ValidationError, ValueError, TypeError):
        return "frozen resolved binding manifest does not parse"
    if manifest.adapter_id != adapter:
        return "frozen resolved binding manifest does not match adapter resolution"
    if historical_digest != verdict.manifest_digest:
        return "frozen compatibility manifest does not match resolved binding"
    authoritative_verdict = evaluate_base_station_compatibility(
        requirements,
        manifest,
    ).model_copy(update={"manifest_digest": verdict.manifest_digest})
    if verdict != authoritative_verdict:
        return (
            "frozen compatibility verdict does not match authoritative "
            "re-evaluation"
        )
    return None


def _compatibility_snapshot_error(frozen: Mapping[str, Any]) -> str | None:
    compatibility = frozen.get("compatibility")
    if not isinstance(compatibility, Mapping):
        return "frozen compatibility payload is malformed"
    try:
        requirements = BaseStationExecutionRequirements.model_validate(
            compatibility.get("requirements")
        )
        verdict = BaseStationCompatibilityVerdict.model_validate(
            compatibility.get("verdict")
        )
    except (ValidationError, ValueError, TypeError):
        return "frozen compatibility payload does not parse"
    if requirements.digest != verdict.requirements_digest:
        return "frozen compatibility requirements digest drifted"
    if MIMO_OTA_CONFIGURATION_FREEZE_KEY in frozen:
        configuration = frozen[MIMO_OTA_CONFIGURATION_FREEZE_KEY]
        if not isinstance(configuration, Mapping):
            return "frozen MIMO OTA configuration is malformed"
        try:
            derived_requirements = (
                build_measure_execution_requirements_from_configuration(
                    dict(configuration)
                )
            )
        except (ValidationError, ValueError, TypeError):
            return "frozen MIMO OTA configuration does not parse"
        if derived_requirements != requirements:
            return "frozen MIMO OTA configuration does not match requirements"
    elif requirements.mac_profile is not None:
        return "frozen MIMO OTA configuration is missing"
    if verdict.status == "incompatible" or verdict.compatible is not True:
        return "frozen compatibility verdict is incompatible"

    resolution = frozen.get("resolution")
    if not isinstance(resolution, Mapping):
        return "frozen adapter resolution is missing"
    try:
        BaseStationAdapterProfileResolution.model_validate(resolution)
    except (ValidationError, ValueError, TypeError):
        if verdict.status == "no_adapter":
            return "frozen no_adapter verdict has invalid adapter resolution"
        return "frozen compatible verdict has invalid adapter resolution"
    if verdict.status == "no_adapter":
        if (
            resolution.get("status") != "diagnostic_unbound"
            or resolution.get("execution_mode") != "simulated"
            or resolution.get("adapter") is not None
        ):
            return (
                "frozen no_adapter verdict does not match simulated "
                "diagnostic_unbound resolution"
            )
    elif verdict.status != "compatible":
        return "frozen compatibility verdict status is invalid"
    adapter = resolution.get("adapter")
    if verdict.status == "compatible" and (
        not isinstance(adapter, str) or not adapter.strip()
    ):
        return "frozen compatible verdict is missing adapter identity"
    if resolution.get("execution_mode") not in {"real", "simulated"}:
        return "frozen compatible verdict has invalid execution mode"

    resolved_binding = frozen.get("resolved_binding")
    if not isinstance(resolved_binding, Mapping):
        return "frozen resolved binding is missing"
    if resolved_binding.get("binding_digest") != frozen.get("binding_digest"):
        return "frozen resolved binding digest does not match adapter freeze"
    if resolved_binding.get("status") != resolution.get("status"):
        return "frozen resolved binding status does not match adapter resolution"
    raw_manifest = resolved_binding.get("manifest")
    if verdict.status == "no_adapter":
        if raw_manifest is not None:
            return "frozen no_adapter verdict unexpectedly includes a manifest"
        return None
    if requirements.mac_profile is None and isinstance(raw_manifest, Mapping):
        if "mac_profiles" not in raw_manifest:
            return _historical_manifest_compatibility_error(
                raw_manifest,
                requirements=requirements,
                verdict=verdict,
                adapter=adapter,
            )
    try:
        manifest = BaseStationAdapterManifest.model_validate(raw_manifest)
    except (ValidationError, ValueError, TypeError):
        return "frozen resolved binding manifest does not parse"
    if manifest.adapter_id != adapter:
        return "frozen resolved binding manifest does not match adapter resolution"
    if manifest_compatibility_digest(manifest) != verdict.manifest_digest:
        return "frozen compatibility manifest does not match resolved binding"
    authoritative_verdict = evaluate_base_station_compatibility(
        requirements,
        manifest,
    )
    if verdict != authoritative_verdict:
        return (
            "frozen compatibility verdict does not match authoritative "
            "re-evaluation"
        )
    return None


def validate_frozen_compatibility_snapshot(frozen: Any) -> str | None:
    """Validate an explicit P1-75 freeze without consulting mutable state.

    ``None`` and snapshots created before the compatibility field existed are
    legacy and intentionally accepted here.  Once ``compatibility`` exists,
    malformed or tampered evidence fails closed.
    """

    if frozen is None:
        return None
    if not isinstance(frozen, Mapping):
        return "frozen baseStation adapter profile is malformed"
    digest_error = _outer_freeze_digest_error(frozen)
    if digest_error is not None:
        return digest_error
    if "compatibility" not in frozen:
        return None
    return _compatibility_snapshot_error(frozen)


def _qualification_projection(
    config: Mapping[str, Any],
) -> tuple[
    QualificationClassification,
    tuple[str, ...],
    ExecutionQualification | None,
]:
    if EXECUTION_QUALIFICATION_KEY not in config:
        return "legacy", (), None
    raw = config.get(EXECUTION_QUALIFICATION_KEY)
    error = validate_frozen_execution_qualification(raw)
    if error is not None:
        return "diagnostic", (error,), None
    qualification = ExecutionQualification.model_validate(raw)
    return qualification.classification, tuple(qualification.reasons), qualification


def _qualification_freeze_alignment_error(
    frozen: Mapping[str, Any],
    qualification: ExecutionQualification | None,
) -> str | None:
    if qualification is None:
        return None
    resolution = frozen.get("resolution")
    if not isinstance(resolution, Mapping):
        return "frozen qualification has no adapter resolution"
    expected = (
        frozen.get("binding_digest"),
        resolution.get("status"),
        resolution.get("execution_mode"),
        resolution.get("adapter"),
    )
    actual = (
        qualification.binding_digest,
        qualification.binding_status,
        qualification.execution_mode,
        qualification.adapter_id,
    )
    if actual != expected:
        return "frozen qualification does not match adapter binding"
    if qualification.classification == "formal":
        if (
            qualification.policy_mode != "formal"
            or qualification.execution_mode != "real"
            or qualification.binding_status not in {"configured", "not_applicable"}
            or qualification.adapter_id is None
        ):
            return "formal qualification does not describe a real authoritative adapter"
        certification = qualification.site_certification
        if certification is None or certification.status != "active":
            return "formal qualification has no active site certification"
        certification_scope = (
            certification.lab_profile_id,
            certification.instrument_connection_id,
            certification.binding_digest,
            certification.adapter_id,
        )
        frozen_scope = (
            frozen.get("lab_profile_id"),
            frozen.get("instrument_connection_id"),
            frozen.get("binding_digest"),
            resolution.get("adapter"),
        )
        if certification_scope != frozen_scope:
            return "formal qualification site certification scope mismatch"
    return None


def _channel_emulator_qualification_projection(
    config: Mapping[str, Any],
) -> tuple[
    Literal["formal", "diagnostic", "legacy", "invalid"],
    tuple[str, ...],
    ChannelEmulatorExecutionQualification | None,
]:
    if CE_EXECUTION_QUALIFICATION_CONFIG_KEY not in config:
        raw_terminals = config.get(CE_TERMINAL_EVIDENCE_CONFIG_KEY)
        if isinstance(raw_terminals, list) and any(
            isinstance(item, Mapping) and item.get("schema_version") == 3
            for item in raw_terminals
        ):
            return (
                "invalid",
                ("channelEmulator terminal v3 has no frozen execution qualification",),
                None,
            )
        return "legacy", (), None
    raw = config.get(CE_EXECUTION_QUALIFICATION_CONFIG_KEY)
    error = validate_frozen_channel_emulator_execution_qualification(raw)
    if error is not None:
        return "invalid", (error,), None
    qualification = ChannelEmulatorExecutionQualification.model_validate(raw)
    return qualification.classification, tuple(qualification.reasons), qualification


def _channel_emulator_qualification_alignment_error(
    config: Mapping[str, Any],
    qualification: ChannelEmulatorExecutionQualification | None,
) -> str | None:
    if qualification is None:
        return None
    raw_base_station_qualification = config.get(EXECUTION_QUALIFICATION_KEY)
    if (
        validate_frozen_execution_qualification(raw_base_station_qualification)
        is not None
    ):
        return "frozen channelEmulator qualification has no valid baseStation qualification"
    base_station_qualification = ExecutionQualification.model_validate(
        raw_base_station_qualification
    )
    expected_diagnostic_actor = (
        base_station_qualification.policy.updated_by
        if base_station_qualification.policy is not None
        and base_station_qualification.policy_mode == "diagnostic"
        else None
    )
    if (
        qualification.base_station_qualification_digest
        != base_station_qualification.qualification_digest
        or qualification.policy_mode != base_station_qualification.policy_mode
        or qualification.diagnostic_actor != expected_diagnostic_actor
        or qualification.diagnostic_reasons
        != tuple(base_station_qualification.reasons)
    ):
        return "frozen channelEmulator qualification does not match baseStation qualification"
    try:
        binding = validate_frozen_channel_emulator_binding(
            config[CE_FREEZE_CONFIG_KEY]
        )
        plan = validate_frozen_channel_emulator_execution_plan(
            config[CE_PLAN_FREEZE_CONFIG_KEY]
        )
        load_request, _configuration = validate_frozen_channel_emulator_load_context(
            config,
            plan,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return f"frozen channelEmulator qualification scope is invalid: {exc}"
    base_freeze = config.get(FREEZE_CONFIG_KEY)
    asset = (
        base_freeze.get(CHANNEL_ASSET_RESOLUTION_FREEZE_KEY)
        if isinstance(base_freeze, Mapping)
        else None
    )
    asset_digest = (
        asset.get("digest")
        if isinstance(asset, Mapping) and isinstance(asset.get("digest"), str)
        else load_request.get("digest")
    )
    expected = (
        binding.get("lab_profile_id"),
        binding.get("instrument_connection_id"),
        binding.get("instrument_model_id"),
        binding.get("binding_digest"),
        plan.get("digest"),
        asset_digest,
        plan.get("adapter_id"),
        plan.get("requested_load_mode"),
    )
    actual = (
        qualification.lab_profile_id,
        qualification.instrument_connection_id,
        qualification.instrument_model_id,
        qualification.binding_digest,
        qualification.plan_digest,
        qualification.asset_digest,
        qualification.adapter_id,
        qualification.load_mode,
    )
    if actual != expected:
        return "frozen channelEmulator qualification does not match binding/plan/asset"
    if qualification.classification != "formal":
        return None
    certification = qualification.site_certification
    if certification is None or certification.status != "active":
        return "formal channelEmulator qualification has no active site certification"
    certification_scope = (
        certification.lab_profile_id,
        certification.instrument_connection_id,
        certification.instrument_model_id,
        certification.binding_digest,
        certification.plan_digest,
        certification.asset_digest,
        certification.adapter_id,
        certification.load_mode,
    )
    if certification_scope != expected:
        return "formal channelEmulator certification scope mismatch"
    raw_terminals = config.get(CE_TERMINAL_EVIDENCE_CONFIG_KEY)
    if not isinstance(raw_terminals, list):
        return None
    latest_by_scope: dict[str, Mapping[str, Any]] = {}
    unscoped: list[Mapping[str, Any]] = []
    for raw in raw_terminals:
        if not isinstance(raw, Mapping):
            continue
        scope = raw.get("operation_scope")
        if isinstance(scope, str):
            latest_by_scope[scope] = raw
        else:
            unscoped.append(raw)
    effective = [*unscoped, *latest_by_scope.values()]
    for raw in effective:
        if raw.get("schema_version") != 3:
            return "formal channelEmulator qualification requires terminal v3"
        identity = raw.get("hardware_identity")
        if not isinstance(identity, Mapping):
            return "formal channelEmulator terminal hardware identity is missing"
        frozen_identity = (
            identity.get("model"),
            identity.get("firmware_version"),
            identity.get("serial_number"),
            tuple(identity.get("options") or ()),
            identity.get("digest"),
        )
        certified_identity = (
            certification.model,
            certification.firmware_version,
            certification.serial_number,
            certification.options,
            certification.identity_digest,
        )
        if frozen_identity != certified_identity:
            return "formal channelEmulator terminal identity/options mismatch certification"
    return None


def _channel_emulator_frequency_evidence_error(
    execution: Any,
    config: Mapping[str, Any],
    qualification: ChannelEmulatorExecutionQualification | None,
    *,
    require_formal_confirmation: bool,
) -> str | None:
    """Validate current CE frequency proof without consulting mutable state."""

    if (
        qualification is None
        or qualification.schema_version == 1
        or qualification.classification != "formal"
        or not require_formal_confirmation
    ):
        return None
    attempt_evidence = config.get("base_station_execution_evidence")
    attempt_id = (
        attempt_evidence.get("current_measurement_attempt_id")
        if isinstance(attempt_evidence, Mapping)
        and attempt_evidence.get("current_measurement_attempt_state") == "completed"
        else None
    )
    if not isinstance(attempt_id, str) or not attempt_id:
        return "formal channelEmulator frequency evidence has no completed attempt"
    raw_terminals = config.get(CE_TERMINAL_EVIDENCE_CONFIG_KEY)
    if not isinstance(raw_terminals, list):
        return "formal channelEmulator frequency evidence has no terminal identity"
    instrument_ids = {
        item.get("instrument_id")
        for item in raw_terminals
        if isinstance(item, Mapping)
        and item.get("measurement_attempt_id") == attempt_id
        and isinstance(item.get("instrument_id"), str)
        and item.get("instrument_id")
    }
    if len(instrument_ids) != 1:
        return "formal channelEmulator frequency evidence terminal identity is ambiguous"
    measurements = getattr(execution, "measurements", None)
    phases = measurements.get("phases") if isinstance(measurements, Mapping) else None
    measure = phases.get("measure") if isinstance(phases, Mapping) else None
    frequency = (
        measure.get("frequency_consistency")
        if isinstance(measure, Mapping)
        else None
    )
    if not _has_certifiable_channel_emulator_frequency_evidence(
        frequency,
        current_adapter_id=qualification.adapter_id,
        instrument_id=next(iter(instrument_ids)),
    ):
        return "formal channelEmulator frequency evidence is incomplete"
    return None


def validate_frozen_mac_profile_evidence(
    config: Mapping[str, Any],
    frozen: Mapping[str, Any],
    *,
    require_formal_confirmation: bool,
) -> str | None:
    """Validate P2-54 profile/receipt alignment from immutable evidence only."""

    # Local import avoids package initialization cycling through executors,
    # which themselves consume this outcome projector.
    from app.services.mimo_ota.base_station_execution_evidence import (
        BASE_STATION_EXECUTION_EVIDENCE_FIELD,
        BaseStationExecutionEvidence,
        _attempt_lifecycle_envelope,
        parse_base_station_execution_evidence,
    )

    try:
        profile = frozen_mac_profile_from_adapter_freeze(dict(frozen))
    except ValueError as exc:
        return str(exc)
    raw = config.get(BASE_STATION_EXECUTION_EVIDENCE_FIELD)
    if raw is None:
        if profile is not None and require_formal_confirmation:
            return "formal execution is missing baseStation execution evidence"
        return None
    if not isinstance(raw, dict):
        return "baseStation execution evidence is malformed"
    normalized = parse_base_station_execution_evidence(raw)
    if normalized is None:
        return "baseStation execution evidence is malformed"
    evidence = BaseStationExecutionEvidence.model_validate(normalized)
    resolution = frozen.get("resolution")
    frozen_adapter = (
        resolution.get("adapter") if isinstance(resolution, Mapping) else None
    )
    if (
        profile is not None
        and frozen_adapter is not None
        and evidence.adapter != frozen_adapter
    ):
        return "MAC evidence adapter does not match frozen adapter"
    if profile is None:
        if evidence.mac_profile_contract_version is not None:
            return "legacy compatibility carries unexpected MAC profile evidence"
        return None
    if (
        evidence.mac_profile_contract_version != 1
        or evidence.mac_profile_digest != profile.profile_digest
        or evidence.mac_profile_receipts is None
    ):
        return "frozen MAC profile evidence digest mismatch"
    if not require_formal_confirmation:
        return None
    resolved_binding = frozen.get("resolved_binding")
    raw_manifest = (
        resolved_binding.get("manifest")
        if isinstance(resolved_binding, Mapping)
        else None
    )
    try:
        manifest = BaseStationAdapterManifest.model_validate(raw_manifest)
    except (ValidationError, ValueError, TypeError):
        return "formal MAC evidence has no frozen adapter manifest"
    profile_identity = (
        profile.profile.kind,
        profile.profile.profile_version,
        profile.profile.rat,
        profile.profile.source_reference,
    )
    matching_capabilities = [
        item
        for item in manifest.mac_profiles
        if (
            item.kind,
            item.profile_version,
            item.rat,
            item.source_reference,
        )
        == profile_identity
    ]
    if len(matching_capabilities) != 1:
        return "formal MAC evidence does not match frozen adapter capability"
    attempt_id = evidence.current_measurement_attempt_id
    matching = [
        row
        for row in evidence.mac_profile_receipts
        if row.measurement_attempt_id == attempt_id
    ]
    if len(matching) != 1:
        return "formal execution has no current-attempt MAC receipt"
    receipt = matching[0]
    evidence_mode = matching_capabilities[0].application_evidence
    if evidence_mode == "authoritative_readback":
        if receipt.confirmed is not True:
            return "formal execution has no confirmed current-attempt MAC receipt"
    elif (
        receipt.operation_succeeded is not True
        or receipt.simulated is not False
        or receipt.application_evidence is None
        or receipt.application_evidence.execution_id != evidence.execution_id
        or receipt.application_evidence.mode != evidence_mode
        or any(
            field.status == "not_applicable" or not field.exchange_ids
            for field in receipt.fields
        )
    ):
        return (
            "formal execution has no complete current-attempt MAC "
            "command/error-queue evidence"
        )
    if evidence.current_measurement_attempt_state != "completed":
        return "formal MAC receipt measurement attempt is not completed"
    accepted, _, windows = _attempt_lifecycle_envelope(evidence, attempt_id)
    if not accepted:
        return "formal MAC receipt has no confirmed current-attempt lifecycle"
    if not set(receipt.exchange_ids).issubset(evidence.exchange_ids):
        return "formal MAC receipt exchanges are outside execution evidence"
    if not any(
        window.lease_id == receipt.lease_id
        and window.session_token == receipt.session_token
        for window in windows
    ):
        return "formal MAC receipt lease/session does not match measurement window"
    return None


def project_execution_evidence_outcome(
    execution: Any,
    *,
    lifecycle_status: str | None = None,
) -> ExecutionEvidenceOutcome:
    """Project frozen evidence plus one authoritative lifecycle into semantics.

    ``lifecycle_status`` is reserved for the REPORT executor's immutable final
    lifecycle projection.  Every other caller continues to consume the stored
    execution status.
    """

    config = getattr(execution, "config", None)
    config = config if isinstance(config, Mapping) else {}
    pipeline_status = str(
        lifecycle_status
        if lifecycle_status is not None
        else getattr(execution, "status", "unknown")
    )
    frozen = config.get(FREEZE_CONFIG_KEY)
    (
        qualification,
        qualification_reasons,
        qualification_snapshot,
    ) = _qualification_projection(config)

    reasons: list[str] = list(qualification_reasons)
    compatibility_digest: str | None = None
    if frozen is None:
        classification: CompatibilityClassification = (
            "diagnostic" if qualification == "diagnostic" else "legacy"
        )
        reasons.append("execution has no frozen compatibility snapshot")
    else:
        error = validate_frozen_compatibility_snapshot(frozen)
        if error is not None:
            classification = "invalid"
            reasons.append(error)
        elif isinstance(frozen, Mapping) and "compatibility" not in frozen:
            classification = (
                "diagnostic" if qualification == "diagnostic" else "legacy"
            )
            reasons.append("execution has no frozen compatibility snapshot")
        else:
            assert isinstance(frozen, Mapping)
            compatibility = frozen["compatibility"]
            assert isinstance(compatibility, Mapping)
            compatibility_digest = canonical_payload_digest(compatibility)
            requirements = BaseStationExecutionRequirements.model_validate(
                compatibility.get("requirements")
            )
            verdict = BaseStationCompatibilityVerdict.model_validate(
                compatibility.get("verdict")
            )
            alignment_error = _qualification_freeze_alignment_error(
                frozen,
                qualification_snapshot,
            )
            mac_evidence_error = validate_frozen_mac_profile_evidence(
                config,
                frozen,
                require_formal_confirmation=(
                    qualification == "formal"
                    and (
                        pipeline_status == "completed"
                        or (
                            isinstance(
                                config.get("base_station_execution_evidence"),
                                Mapping,
                            )
                            and config["base_station_execution_evidence"].get(
                                "current_measurement_attempt_state"
                            )
                            == "completed"
                        )
                    )
                ),
            )
            if alignment_error is not None:
                classification = "invalid"
                reasons.append(alignment_error)
            elif mac_evidence_error is not None:
                classification = "invalid"
                reasons.append(mac_evidence_error)
            elif requirements.mac_profile is None:
                classification = (
                    "diagnostic" if qualification == "diagnostic" else "legacy"
                )
                reasons.append(
                    "pre-P2-54 compatibility snapshot has no frozen MAC profile"
                )
            elif verdict.status == "no_adapter" or qualification == "diagnostic":
                classification = "diagnostic"
            else:
                classification = "compatible"

    ce_classification, ce_reason = _channel_emulator_terminal_projection(
        config,
        execution_id=getattr(execution, "id", ""),
        pipeline_status=pipeline_status,
    )
    (
        ce_qualification,
        ce_qualification_reasons,
        ce_qualification_snapshot,
    ) = _channel_emulator_qualification_projection(config)
    reasons.extend(ce_qualification_reasons)
    ce_qualification_error = _channel_emulator_qualification_alignment_error(
        config,
        ce_qualification_snapshot,
    )
    ce_frequency_error = _channel_emulator_frequency_evidence_error(
        execution,
        config,
        ce_qualification_snapshot,
        require_formal_confirmation=(
            pipeline_status == "completed"
            or (
                isinstance(
                    config.get("base_station_execution_evidence"),
                    Mapping,
                )
                and config["base_station_execution_evidence"].get(
                    "current_measurement_attempt_state"
                )
                == "completed"
            )
        ),
    )
    if ce_qualification_error is not None:
        reasons.append(ce_qualification_error)
    if ce_frequency_error is not None:
        reasons.append(ce_frequency_error)
    if ce_reason is not None:
        reasons.append(ce_reason)
    if (
        ce_classification == "invalid"
        or ce_qualification == "invalid"
        or ce_qualification_error is not None
        or ce_frequency_error is not None
    ):
        classification = "invalid"
    elif (
        ce_classification == "diagnostic"
        or ce_qualification == "diagnostic"
    ) and classification != "invalid":
        classification = "diagnostic"

    formal_eligible = (
        pipeline_status == "completed"
        and classification == "compatible"
        and qualification == "formal"
        and ce_qualification in {"formal", "legacy"}
    )
    if pipeline_status != "completed":
        completion: CompletionSemantic = "not_completed"
    elif formal_eligible:
        completion = "valid_test_completed"
    elif classification == "diagnostic":
        completion = "diagnostic_completed"
    else:
        completion = "pipeline_completed"

    channel_emulator_operation_evidence = (
        _public_channel_emulator_operation_evidence(
            config,
            pipeline_status=pipeline_status,
            classification=ce_classification,
            reason=ce_reason,
        )
    )

    return ExecutionEvidenceOutcome(
        compatibility_classification=classification,
        completion_semantic=completion,
        formal_eligible=formal_eligible,
        compatibility_digest=compatibility_digest,
        qualification_classification=qualification,
        reasons=tuple(dict.fromkeys(reasons)),
        pipeline_status=pipeline_status,
        channel_emulator_operation_evidence=(
            channel_emulator_operation_evidence
        ),
    )


def execution_evidence_blocks_formal_outputs(
    execution: Any,
    *,
    lifecycle_status: str | None = None,
) -> bool:
    """Return whether this execution must be excluded from every formal output.

    Legacy rows intentionally retain the pre-P1-75 provenance rules.  Explicit
    diagnostic or invalid evidence is fail-closed everywhere.
    """

    return project_execution_evidence_outcome(
        execution,
        lifecycle_status=lifecycle_status,
    ).compatibility_classification in {"diagnostic", "invalid"}
