"""Controlled recovery of one saved CMW500 preset from frozen real evidence."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.instrument import InstrumentConnection, InstrumentModel
from app.models.test_plan import TestExecution
from app.services.base_station_model_preset import (
    BaseStationModelPreset,
    _validated_profile_for_model,
    parse_base_station_model_presets,
)


@dataclass(frozen=True)
class BaseStationPresetRecoveryResult:
    changed: bool
    applied: bool
    source_execution_id: UUID
    preset: BaseStationModelPreset


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"recovery source is missing {label}")
    return value


def recover_cmw500_model_preset(
    db: Session,
    *,
    connection_id: UUID,
    model_id: UUID,
    source_execution_id: UUID,
    apply: bool,
) -> BaseStationPresetRecoveryResult:
    """Recover a saved preset without changing the active model/connection.

    The source must be a real execution whose frozen CMW500 profile and
    independently confirmed applied route agree exactly. This restores a
    reusable saved draft only; it does not grant formal qualification.
    """

    connection = db.get(InstrumentConnection, connection_id)
    model = db.get(InstrumentModel, model_id)
    execution = db.get(TestExecution, source_execution_id)
    if connection is None or model is None or execution is None:
        raise ValueError("recovery target connection, model, or execution is missing")
    if model.category_id != connection.category_id or model.model != "CMW500":
        raise ValueError("recovery target must be the CMW500 model on this connection")

    config = _mapping(execution.config, "execution config")
    freeze = _mapping(
        config.get("base_station_adapter_profile_freeze"),
        "base_station_adapter_profile_freeze",
    )
    resolution = _mapping(freeze.get("resolution"), "frozen resolution")
    evidence = _mapping(
        config.get("base_station_execution_evidence"),
        "base_station_execution_evidence",
    )
    identity = _mapping(evidence.get("identity"), "execution identity")
    expected_connection = _mapping(
        freeze.get("expected_driver_connection"),
        "expected_driver_connection",
    )

    if freeze.get("instrument_model_id") != str(model.id):
        raise ValueError("frozen instrument_model_id does not match recovery target")
    if freeze.get("instrument_connection_id") != str(connection.id):
        raise ValueError("frozen instrument_connection_id does not match recovery target")
    if identity.get("instrument_connection_id") != str(connection.id):
        raise ValueError("execution identity does not match recovery target connection")
    if (
        resolution.get("status") != "configured"
        or resolution.get("adapter") != "cmw500"
        or resolution.get("execution_mode") != "real"
        or evidence.get("adapter") != "cmw500"
        or evidence.get("execution_mode") != "real"
    ):
        raise ValueError("recovery requires configured real CMW500 evidence")
    if evidence.get("route_confirmed") is not True:
        raise ValueError("recovery requires an independently confirmed route")

    profile = _validated_profile_for_model(
        model,
        _mapping(resolution.get("profile"), "frozen CMW500 profile"),
    )
    if profile is None:
        raise ValueError("recovery source has no CMW500 profile")
    applied_route = _mapping(evidence.get("applied_route"), "applied route")
    if applied_route.get("payload") != profile.get("lte_2x2_internal_route"):
        raise ValueError("confirmed applied route does not match frozen profile")

    resource = str(expected_connection.get("resource") or "").strip()
    if not resource:
        raise ValueError("frozen CMW500 evidence has no transport resource")
    preset = BaseStationModelPreset(
        model_id=model.id,
        endpoint=resource,
        controller="",
        notes="",
        connection_params={},
        base_station_adapter_profile=profile,
    )

    presets = parse_base_station_model_presets(
        connection.base_station_model_presets
    )
    existing = presets.get(str(model.id))
    if existing is not None and existing != preset:
        raise ValueError(
            "a different CMW500 saved preset already exists; refusing to overwrite it"
        )
    changed = existing is None
    if apply and changed:
        presets[str(model.id)] = preset
        connection.base_station_model_presets = {
            key: value.model_dump(mode="json") for key, value in presets.items()
        }
        flag_modified(connection, "base_station_model_presets")
        db.flush()

    return BaseStationPresetRecoveryResult(
        changed=changed,
        applied=apply,
        source_execution_id=execution.id,
        preset=preset,
    )
