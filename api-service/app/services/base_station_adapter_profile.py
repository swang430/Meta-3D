"""Resolve and freeze the selected base-station adapter before hardware I/O."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.hal.base_station_adapter_profile import (
    BaseStationAdapterProfile,
    BaseStationAdapterProfileResolution,
)
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services.instrument_hal_service import get_real_driver_class, is_mock_driver


FREEZE_CONFIG_KEY = "base_station_adapter_profile_freeze"
CMW_FORMAL_CAPABILITY_KEY = "cmw500_lte_2x2_formal_capability"


def _loaded_base_station(hal):
    drivers = getattr(hal, "drivers", None)
    if not isinstance(drivers, dict):
        return None
    return drivers.get("baseStation")


def _driver_connection_identity(driver) -> dict[str, Any]:
    """Return the parsed transport identity already used by the loaded driver."""

    return {
        "host": getattr(driver, "_connection_host", None),
        "port": getattr(driver, "_connection_port", None),
        "resource": getattr(driver, "_connection_resource", None),
    }


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _single_base_station_binding(selected_lab_profile, category_id: str) -> dict[str, Any]:
    bindings = selected_lab_profile.instrument_bindings
    if not isinstance(bindings, list):
        raise ValueError("LabProfile instrument_bindings must be a list")
    matches = [
        binding
        for binding in bindings
        if isinstance(binding, dict)
        and str(binding.get("category_id")) == category_id
    ]
    if len(matches) != 1:
        raise ValueError("LabProfile must contain exactly one baseStation binding")
    return matches[0]


def validate_frozen_base_station_before_remote(hal, frozen: dict[str, Any]) -> str | None:
    """Pure lock-time check; never opens a session or reads the database."""

    driver = _loaded_base_station(hal)
    if driver is None:
        return "loaded driver is missing"

    resolution = frozen.get("resolution")
    if not isinstance(resolution, dict):
        return "frozen adapter resolution is missing"
    mode = resolution.get("execution_mode")
    if mode == "real":
        if is_mock_driver(driver):
            return "loaded driver changed from real to mock"
        expected_module = frozen.get("expected_driver_module")
        expected_name = frozen.get("expected_driver_name")
        if (
            type(driver).__module__ != expected_module
            or type(driver).__name__ != expected_name
        ):
            return "loaded driver does not match frozen registry class"
        if getattr(driver, "adapter_id", None) != resolution.get("adapter"):
            return "loaded driver adapter does not match frozen adapter"
        if _driver_connection_identity(driver) != frozen.get(
            "expected_driver_connection"
        ):
            return "loaded driver connection identity does not match frozen connection"
        return None
    if mode == "simulated":
        if not is_mock_driver(driver):
            return "loaded driver changed from mock to real"
        return None
    return "frozen execution mode is invalid"


def build_frozen_base_station_validator(frozen: dict[str, Any]):
    """Return a pure lock-time validator carrying its immutable freeze identity."""

    def _validate(hal):
        return validate_frozen_base_station_before_remote(hal, frozen)

    _validate.validation_identity = frozen.get("digest")
    return _validate


def freeze_base_station_adapter_profile(
    db,
    hal,
    execution,
    selected_lab_profile,
) -> dict[str, Any]:
    """Resolve once and persist an immutable execution-scoped adapter snapshot."""

    execution_config = execution.config if isinstance(execution.config, dict) else {}
    existing = execution_config.get(FREEZE_CONFIG_KEY)
    if isinstance(existing, dict):
        error = validate_frozen_base_station_before_remote(hal, existing)
        if error:
            raise ValueError(error)
        return existing

    category = (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.category_key == "baseStation")
        .with_for_update()
        .one_or_none()
    )
    if category is None:
        raise ValueError("baseStation category is not configured")

    binding = _single_base_station_binding(selected_lab_profile, str(category.id))
    binding_model_id = binding.get("instrument_model_id")
    selected_model_id = category.selected_model_id
    loaded_driver = _loaded_base_station(hal)
    if loaded_driver is None:
        raise ValueError("loaded driver is missing")
    simulated = is_mock_driver(loaded_driver)

    if (binding_model_id is None) != (selected_model_id is None):
        raise ValueError("baseStation binding and selected_model_id must both be configured")
    if binding_model_id is None and selected_model_id is None:
        if not simulated:
            raise ValueError("unbound baseStation diagnostics require the authoritative mock")
        resolution = BaseStationAdapterProfileResolution(
            schema_version=1,
            adapter=None,
            status="diagnostic_unbound",
            execution_mode="simulated",
            profile=None,
        )
        identity = {
            "schema_version": 1,
            "resolution": resolution.model_dump(mode="json"),
            "category_id": str(category.id),
            "instrument_model_id": None,
            "instrument_connection_id": None,
            "lab_profile_id": str(selected_lab_profile.id),
            "expected_driver_module": None,
            "expected_driver_name": None,
        }
        frozen = {**identity, "digest": _canonical_digest(identity)}
        execution.config = {**execution_config, FREEZE_CONFIG_KEY: frozen}
        flag_modified(execution, "config")
        db.flush()
        return frozen
    if str(binding_model_id) != str(selected_model_id):
        raise ValueError("baseStation binding does not match selected_model_id")

    model = (
        db.query(InstrumentModel)
        .filter(
            InstrumentModel.id == selected_model_id,
            InstrumentModel.category_id == category.id,
        )
        .one_or_none()
    )
    if model is None:
        raise ValueError("selected baseStation model is missing from the registry")
    connection = (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.category_id == category.id)
        .with_for_update()
        .one_or_none()
    )
    if connection is None:
        raise ValueError("selected baseStation connection is missing")
    binding_endpoint = binding.get("connection_endpoint")
    if (
        not isinstance(binding_endpoint, str)
        or binding_endpoint.strip() != (connection.endpoint or "").strip()
    ):
        raise ValueError(
            "LabProfile baseStation binding connection endpoint does not match "
            "selected connection"
        )

    expected_class = get_real_driver_class("baseStation", model.model)
    if expected_class is None:
        raise ValueError("selected baseStation model has no registered real driver")
    adapter = getattr(expected_class, "adapter_id", None)
    if adapter not in {"uxm", "cmw500"}:
        raise ValueError("selected baseStation registry class has no valid adapter identity")

    if not simulated and type(loaded_driver) is not expected_class:
        raise ValueError("loaded driver does not match selected registry class")

    if adapter == "cmw500":
        params = connection.connection_params
        if not isinstance(params, dict):
            raise ValueError("CMW500 connection_params are missing")
        raw_profile = params.get("base_station_adapter_profile")
        profile = BaseStationAdapterProfile.model_validate(raw_profile)
        resolution = BaseStationAdapterProfileResolution(
            schema_version=1,
            adapter="cmw500",
            status="configured",
            execution_mode="simulated" if simulated else "real",
            profile=profile,
        )
    else:
        resolution = BaseStationAdapterProfileResolution(
            schema_version=1,
            adapter="uxm",
            status="not_applicable",
            execution_mode="simulated" if simulated else "real",
            profile=None,
        )

    identity = {
        "schema_version": 1,
        "resolution": resolution.model_dump(mode="json"),
        "category_id": str(category.id),
        "instrument_model_id": str(model.id),
        "instrument_connection_id": str(connection.id),
        "lab_profile_id": str(selected_lab_profile.id),
        "expected_driver_module": expected_class.__module__,
        "expected_driver_name": expected_class.__name__,
        "expected_driver_connection": (
            None if simulated else _driver_connection_identity(loaded_driver)
        ),
    }
    if adapter == "cmw500":
        updated_at = connection.cmw500_lte_2x2_formal_updated_at
        identity[CMW_FORMAL_CAPABILITY_KEY] = {
            "schema_version": 1,
            "instrument_connection_id": str(connection.id),
            "enabled": connection.cmw500_lte_2x2_formal_enabled is True,
            "updated_at": updated_at.isoformat() if updated_at is not None else None,
        }
    frozen = {**identity, "digest": _canonical_digest(identity)}
    error = validate_frozen_base_station_before_remote(hal, frozen)
    if error:
        raise ValueError(error)

    execution.config = {**execution_config, FREEZE_CONFIG_KEY: frozen}
    flag_modified(execution, "config")
    db.flush()
    return frozen


def freeze_execution_base_station_adapter_profile(db, hal, execution, test_case):
    """Lock execution/lab and freeze before the first hardware operation.

    Old rows that already contain hardware progress cannot acquire provenance
    from today's catalog.  A pre-existing frozen snapshot remains readable and
    is only revalidated against the loaded driver.
    """

    locked_execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution.id)
        .with_for_update()
        .one_or_none()
    )
    if locked_execution is None:
        raise ValueError("TestExecution no longer exists")
    config = locked_execution.config if isinstance(locked_execution.config, dict) else {}
    if FREEZE_CONFIG_KEY not in config:
        has_progress = any(
            value not in (None, {}, [])
            for value in (
                locked_execution.measurements,
                locked_execution.test_results,
                locked_execution.phase_results,
                config.get("phase_progress"),
            )
        )
        if has_progress:
            raise ValueError(
                "execution already has hardware/phase progress; current adapter "
                "configuration cannot be backfilled"
            )

    lab_profile_id = getattr(test_case, "lab_profile_id", None)
    if lab_profile_id is None:
        raise ValueError("TestCase has no LabProfile for baseStation resolution")
    selected_lab = (
        db.query(LabProfile)
        .filter(LabProfile.id == lab_profile_id)
        .with_for_update()
        .one_or_none()
    )
    if selected_lab is None:
        raise ValueError("selected LabProfile no longer exists")
    return freeze_base_station_adapter_profile(
        db,
        hal,
        locked_execution,
        selected_lab,
    )
