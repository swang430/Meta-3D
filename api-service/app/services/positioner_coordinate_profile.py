"""Freeze one execution-owned Aerotech program/feedback coordinate contract."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy.orm.attributes import flag_modified

from app.hal.base import resolve_configured_tcpip_connection
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services.instrument_hal_service import get_real_driver_class, is_mock_driver


FREEZE_CONFIG_KEY = "positioner_coordinate_profile_freeze"


class PositionerCoordinateProfile(BaseModel):
    """Strict site-entered values whose attestation is frozen per execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    user_units: Literal["degree"]
    units_verified: Literal[True]
    coordinate_offset_deg: float
    coordinate_offset_verified: Literal[True]
    coordinate_offset_verification_source: str
    coordinate_offset_verified_at: datetime
    minimum_deg: float
    maximum_deg: float
    xf_speed: float
    position_tolerance_deg: float
    azimuth_axis: str

    @field_validator(
        "coordinate_offset_deg",
        "minimum_deg",
        "maximum_deg",
        "xf_speed",
        "position_tolerance_deg",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if isinstance(value, bool):
            raise ValueError("must be finite numeric")
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("must be finite numeric")
        return parsed

    @field_validator("azimuth_axis")
    @classmethod
    def _axis(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if normalized != "X":
            raise ValueError("azimuth_axis must be X")
        return normalized

    @field_validator("coordinate_offset_verification_source")
    @classmethod
    def _verification_source(cls, value: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("coordinate_offset_verification_source is required")
        return normalized

    @field_validator("coordinate_offset_verified_at")
    @classmethod
    def _verified_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("coordinate_offset_verified_at must include timezone")
        return value

    @model_validator(mode="after")
    def _ranges(self):
        if self.minimum_deg >= self.maximum_deg:
            raise ValueError("motion range must have minimum_deg < maximum_deg")
        if self.xf_speed <= 0:
            raise ValueError("xf_speed must be positive")
        if not 0 < self.position_tolerance_deg <= 1.0:
            raise ValueError("position_tolerance_deg must be in (0, 1]")
        return self


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _loaded_positioner(hal):
    drivers = getattr(hal, "drivers", None)
    return drivers.get("positioner") if isinstance(drivers, dict) else None


def _single_positioner_binding(lab: LabProfile, category_id: str) -> dict[str, Any]:
    bindings = lab.instrument_bindings
    if not isinstance(bindings, list):
        raise ValueError("LabProfile instrument_bindings must be a list")
    matches = [
        binding
        for binding in bindings
        if isinstance(binding, dict)
        and str(binding.get("category_id")) == category_id
    ]
    if len(matches) != 1:
        raise ValueError("LabProfile must contain exactly one positioner binding")
    return matches[0]


def _connection_config(connection: InstrumentConnection) -> dict[str, Any]:
    config: dict[str, Any] = {
        "endpoint": connection.endpoint,
        "controller_ip": connection.controller_ip,
        "port": connection.port,
        "protocol": connection.protocol,
    }
    if isinstance(connection.connection_params, dict):
        config.update(connection.connection_params)
    return config


def _connection_identity(config: dict[str, Any]) -> dict[str, Any]:
    host, port, resource, error = resolve_configured_tcpip_connection(config)
    if error:
        raise ValueError(f"selected positioner connection is invalid: {error}")
    if not host:
        raise ValueError("selected positioner connection has no transport host")
    return {"host": host, "port": port or 8000, "resource": resource}


def _driver_connection_identity(driver) -> dict[str, Any]:
    return {
        "host": getattr(driver, "_connection_host", None),
        "port": getattr(driver, "port", None),
        "resource": getattr(driver, "_connection_resource", None),
    }


def _profile_from_config(config: dict[str, Any]) -> PositionerCoordinateProfile:
    if config.get("motion_truth_units_verified") is not True:
        raise ValueError("motion_truth_units_verified must be explicitly true")
    if config.get("motion_truth_coordinate_offset_verified") is not True:
        raise ValueError(
            "motion_truth_coordinate_offset_verified must be explicitly true"
        )
    try:
        return PositionerCoordinateProfile.model_validate({
            "schema_version": 1,
            "user_units": str(config.get("motion_truth_user_units", ""))
            .strip()
            .lower(),
            "units_verified": config.get("motion_truth_units_verified"),
            "coordinate_offset_deg": config.get(
                "motion_truth_coordinate_offset_deg"
            ),
            "coordinate_offset_verified": config.get(
                "motion_truth_coordinate_offset_verified"
            ),
            "coordinate_offset_verification_source": config.get(
                "motion_truth_coordinate_offset_verification_source"
            ),
            "coordinate_offset_verified_at": config.get(
                "motion_truth_coordinate_offset_verified_at"
            ),
            "minimum_deg": config.get("motion_truth_min_deg"),
            "maximum_deg": config.get("motion_truth_max_deg"),
            "xf_speed": config.get("motion_truth_xf_speed"),
            "position_tolerance_deg": config.get("position_tolerance_deg", 0.5),
            "azimuth_axis": config.get("azimuth_axis", "X"),
        })
    except Exception as exc:
        raise ValueError(f"positioner coordinate profile is invalid: {exc}") from exc


def validate_frozen_positioner_before_motion(
    hal, frozen: dict[str, Any]
) -> str | None:
    """Pure pre-I/O validation against the loaded driver; never reads the DB."""

    resolution = frozen.get("resolution")
    unbound_simulated_diagnostic = (
        isinstance(resolution, dict)
        and resolution.get("execution_mode") == "simulated"
        and resolution.get("status") == "diagnostic_unbound"
        and frozen.get("profile") is None
        and "digest" not in frozen
    )
    digest = frozen.get("digest")
    identity = {key: value for key, value in frozen.items() if key != "digest"}
    if (
        not unbound_simulated_diagnostic
        and (not isinstance(digest, str) or digest != _canonical_digest(identity))
    ):
        return "frozen positioner digest is missing or does not match its payload"
    driver = _loaded_positioner(hal)
    if driver is None:
        return "loaded positioner driver is missing"
    if not isinstance(resolution, dict):
        return "frozen positioner resolution is missing"
    mode = resolution.get("execution_mode")
    if mode == "simulated":
        return None if is_mock_driver(driver) else "loaded positioner changed from mock"
    if mode != "real":
        return "frozen positioner execution mode is invalid"
    if is_mock_driver(driver):
        return "loaded positioner changed from real to mock"
    if (
        type(driver).__module__ != frozen.get("expected_driver_module")
        or type(driver).__name__ != frozen.get("expected_driver_name")
    ):
        return "loaded positioner driver does not match frozen registry class"
    if _driver_connection_identity(driver) != frozen.get("expected_driver_connection"):
        return "loaded positioner connection identity does not match frozen connection"
    if resolution.get("status") == "not_applicable":
        return None
    if resolution.get("status") != "verified":
        return "frozen positioner resolution is not verified real hardware"
    raw_profile = frozen.get("profile")
    if not isinstance(raw_profile, dict):
        return "frozen positioner coordinate profile is missing"
    try:
        live_profile = _profile_from_config(getattr(driver, "config", {}) or {})
    except ValueError as exc:
        return f"loaded driver coordinate profile is invalid: {exc}"
    if live_profile.model_dump(mode="json") != raw_profile:
        return "loaded driver coordinate profile does not match frozen coordinates"
    return None


def build_frozen_positioner_validator(frozen: dict[str, Any]):
    """Return a pure lock-time validator carrying its immutable identity."""

    def _validate(hal):
        return validate_frozen_positioner_before_motion(hal, frozen)

    _validate.validation_identity = frozen.get("digest")
    return _validate


def freeze_positioner_coordinate_profile(
    db,
    hal,
    execution,
    selected_lab_profile,
) -> dict[str, Any]:
    """Persist one immutable positioner coordinate snapshot before hardware I/O."""

    execution_config = execution.config if isinstance(execution.config, dict) else {}
    existing = execution_config.get(FREEZE_CONFIG_KEY)
    if isinstance(existing, dict):
        error = validate_frozen_positioner_before_motion(hal, existing)
        if error:
            raise ValueError(error)
        return existing

    category = (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.category_key == "positioner")
        .with_for_update()
        .one_or_none()
    )
    if category is None:
        loaded_driver = _loaded_positioner(hal)
        if loaded_driver is not None and not is_mock_driver(loaded_driver):
            raise ValueError("positioner category is not configured")
        simulated = is_mock_driver(loaded_driver)
        identity = {
            "schema_version": 1,
            "resolution": {
                "schema_version": 1,
                "adapter": None,
                "status": "diagnostic_unbound" if simulated else "unavailable",
                "execution_mode": "simulated" if simulated else "unavailable",
            },
            "category_id": None,
            "instrument_model_id": None,
            "instrument_connection_id": None,
            "lab_profile_id": str(selected_lab_profile.id),
            "expected_driver_module": None,
            "expected_driver_name": None,
            "expected_driver_connection": None,
            "profile": None,
            "source_reference": None,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        }
        frozen = {**identity, "digest": _canonical_digest(identity)}
        execution.config = {**execution_config, FREEZE_CONFIG_KEY: frozen}
        flag_modified(execution, "config")
        db.flush()
        return frozen
    binding = _single_positioner_binding(selected_lab_profile, str(category.id))
    if str(binding.get("instrument_model_id")) != str(category.selected_model_id):
        raise ValueError("positioner binding does not match selected_model_id")
    model = (
        db.query(InstrumentModel)
        .filter(
            InstrumentModel.id == category.selected_model_id,
            InstrumentModel.category_id == category.id,
        )
        .one_or_none()
    )
    if model is None:
        raise ValueError("selected positioner model is missing from the registry")
    connection = (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.category_id == category.id)
        .with_for_update()
        .one_or_none()
    )
    if connection is None:
        raise ValueError("selected positioner connection is missing")
    if (
        not isinstance(binding.get("connection_endpoint"), str)
        or binding["connection_endpoint"].strip()
        != (connection.endpoint or "").strip()
    ):
        raise ValueError(
            "LabProfile positioner binding connection endpoint does not match "
            "selected connection"
        )
    expected_class = get_real_driver_class("positioner", model.model)
    if expected_class is None:
        raise ValueError("selected positioner model has no registered real driver")
    loaded_driver = _loaded_positioner(hal)
    if loaded_driver is None:
        raise ValueError("loaded positioner driver is missing")
    simulated = is_mock_driver(loaded_driver)
    connection_config = _connection_config(connection)

    if simulated:
        resolution = {
            "schema_version": 1,
            "adapter": "aerotech" if model.model == "A3200" else None,
            "status": "diagnostic",
            "execution_mode": "simulated",
        }
        profile = None
        expected_connection = None
    else:
        if type(loaded_driver) is not expected_class:
            raise ValueError("loaded positioner driver does not match selected model")
        if model.model != "A3200":
            resolution = {
                "schema_version": 1,
                "adapter": None,
                "status": "not_applicable",
                "execution_mode": "real",
            }
            profile = None
            expected_connection = _connection_identity(connection_config)
        else:
            resolution = {
                "schema_version": 1,
                "adapter": "aerotech",
                "status": "verified",
                "execution_mode": "real",
            }
            profile_model = _profile_from_config(connection_config)
            loaded_profile = _profile_from_config(
                getattr(loaded_driver, "config", {}) or {}
            )
            if loaded_profile != profile_model:
                raise ValueError(
                    "loaded driver coordinate profile does not match persisted coordinates"
                )
            profile = profile_model.model_dump(mode="json")
            expected_connection = _connection_identity(connection_config)
            if _driver_connection_identity(loaded_driver) != expected_connection:
                raise ValueError(
                    "loaded positioner connection identity does not match selected connection"
                )

    frozen_at = datetime.now(timezone.utc).isoformat()
    identity = {
        "schema_version": 1,
        "resolution": resolution,
        "category_id": str(category.id),
        "instrument_model_id": str(model.id),
        "instrument_connection_id": str(connection.id),
        "lab_profile_id": str(selected_lab_profile.id),
        "expected_driver_module": expected_class.__module__,
        "expected_driver_name": expected_class.__name__,
        "expected_driver_connection": expected_connection,
        "profile": profile,
        "source_reference": (
            profile["coordinate_offset_verification_source"]
            if isinstance(profile, dict)
            else None
        ),
        "frozen_at": frozen_at,
    }
    frozen = {**identity, "digest": _canonical_digest(identity)}
    error = validate_frozen_positioner_before_motion(hal, frozen)
    if error:
        raise ValueError(error)
    execution.config = {**execution_config, FREEZE_CONFIG_KEY: frozen}
    flag_modified(execution, "config")
    db.flush()
    return frozen


def freeze_execution_positioner_coordinate_profile(
    db,
    hal,
    execution,
    test_case,
) -> dict[str, Any]:
    """Lock execution/lab and refuse provenance backfill after progress exists."""

    locked_execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution.id)
        .with_for_update()
        .one_or_none()
    )
    if locked_execution is None:
        raise ValueError("TestExecution no longer exists")
    config = (
        locked_execution.config if isinstance(locked_execution.config, dict) else {}
    )
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
                "execution already has hardware/phase progress; current positioner "
                "coordinate profile cannot be backfilled"
            )
    lab_profile_id = getattr(test_case, "lab_profile_id", None)
    if lab_profile_id is None:
        raise ValueError("TestCase has no LabProfile for positioner resolution")
    selected_lab = (
        db.query(LabProfile)
        .filter(LabProfile.id == lab_profile_id)
        .with_for_update()
        .one_or_none()
    )
    if selected_lab is None:
        raise ValueError("selected LabProfile no longer exists")
    return freeze_positioner_coordinate_profile(
        db,
        hal,
        locked_execution,
        selected_lab,
    )
