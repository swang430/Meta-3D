"""Single read-only resolver for the selected BaseStation binding."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.hal.base import resolve_configured_tcpip_connection
from app.hal.base_station_adapter_profile import BaseStationAdapterProfile
from app.hal.base_station_manifest import BaseStationAdapterManifest
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.services.instrument_hal_service import (
    get_base_station_adapter_registration,
    is_mock_driver,
)


class BaseStationTransportIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str
    port: int | None
    resource: str | None


class BaseStationFormalCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    instrument_connection_id: str
    enabled: bool
    updated_at: str | None


class BaseStationRuntimeDriverIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str
    name: str
    instrument_id: str
    adapter_id: str | None
    simulated: bool
    transport: BaseStationTransportIdentity | None


class ResolvedBaseStationBinding(BaseModel):
    """Immutable resolution; runtime identity is deliberately outside its digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    status: Literal["configured", "not_applicable", "diagnostic_unbound"]
    execution_mode: Literal["real", "simulated"]
    category_id: str
    instrument_model_id: str | None
    instrument_connection_id: str | None
    lab_profile_id: str
    manifest: BaseStationAdapterManifest | None
    profile: BaseStationAdapterProfile | None
    expected_driver_module: str | None
    expected_driver_name: str | None
    expected_transport: BaseStationTransportIdentity | None
    formal_capability: BaseStationFormalCapability | None
    binding_digest: str
    runtime_driver: BaseStationRuntimeDriverIdentity

    def stable_projection(self) -> dict[str, Any]:
        """JSON-safe binding truth shared by preview/readiness/freeze consumers."""

        projection = self.model_dump(
            mode="json",
            exclude={"execution_mode", "runtime_driver"},
        )
        return projection


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _loaded_base_station(hal):
    drivers = getattr(hal, "drivers", None)
    if not isinstance(drivers, dict):
        return None
    return drivers.get("baseStation")


def _driver_transport(driver) -> dict[str, Any]:
    return {
        "host": getattr(driver, "_connection_host", None),
        "port": getattr(driver, "_connection_port", None),
        "resource": getattr(driver, "_connection_resource", None),
    }


def _expected_transport(connection: InstrumentConnection) -> dict[str, Any]:
    config = {
        "endpoint": connection.endpoint,
        "ip": connection.controller_ip,
        "port": connection.port,
        "protocol": connection.protocol,
    }
    if isinstance(connection.connection_params, dict):
        config.update(connection.connection_params)
    host, port, resource, error = resolve_configured_tcpip_connection(config)
    if error:
        raise ValueError(f"selected baseStation connection is invalid: {error}")
    if not host:
        raise ValueError("selected baseStation connection has no transport host")
    return {"host": host, "port": port, "resource": resource}


def _single_binding(lab: LabProfile, category_id: str) -> dict[str, Any]:
    bindings = lab.instrument_bindings
    if not isinstance(bindings, list):
        raise ValueError("LabProfile instrument_bindings must be a list")
    matches = [
        item
        for item in bindings
        if isinstance(item, dict) and str(item.get("category_id")) == category_id
    ]
    if len(matches) != 1:
        raise ValueError("LabProfile must contain exactly one baseStation binding")
    return matches[0]


def _runtime_driver_identity(driver, simulated: bool) -> dict[str, Any]:
    return {
        "module": type(driver).__module__,
        "name": type(driver).__name__,
        "instrument_id": str(getattr(driver, "instrument_id", "")),
        "adapter_id": getattr(driver, "adapter_id", None),
        "simulated": simulated,
        "transport": None if simulated else _driver_transport(driver),
    }


def resolve_base_station_binding(
    db,
    hal,
    selected_lab_profile: LabProfile,
    *,
    lock: bool = False,
) -> ResolvedBaseStationBinding:
    """Resolve persistent binding truth and loaded runtime identity without I/O."""

    category_query = db.query(InstrumentCategory).filter(
        InstrumentCategory.category_key == "baseStation"
    )
    if lock:
        category_query = category_query.with_for_update()
    category = category_query.one_or_none()
    if category is None:
        raise ValueError("baseStation category is not configured")

    lab = selected_lab_profile
    if lock:
        lab = (
            db.query(LabProfile)
            .filter(LabProfile.id == selected_lab_profile.id)
            .with_for_update()
            .one_or_none()
        )
        if lab is None:
            raise ValueError("selected LabProfile no longer exists")
    binding = _single_binding(lab, str(category.id))
    binding_model_id = binding.get("instrument_model_id")
    selected_model_id = category.selected_model_id
    driver = _loaded_base_station(hal)
    if driver is None:
        raise ValueError("loaded driver is missing")
    simulated = is_mock_driver(driver)

    if (binding_model_id is None) != (selected_model_id is None):
        raise ValueError("baseStation binding and selected_model_id must both be configured")
    if binding_model_id is None:
        if not simulated:
            raise ValueError("unbound baseStation diagnostics require the authoritative mock")
        persistent = {
            "schema_version": 1,
            "status": "diagnostic_unbound",
            "category_id": str(category.id),
            "instrument_model_id": None,
            "instrument_connection_id": None,
            "lab_profile_id": str(lab.id),
            "manifest": None,
            "profile": None,
            "expected_driver_module": None,
            "expected_driver_name": None,
            "expected_transport": None,
            "formal_capability": None,
            "binding": {
                "driver_mode": binding.get("driver_mode"),
                "role": binding.get("role"),
            },
            "category_driver_mode": category.driver_mode,
        }
        return ResolvedBaseStationBinding(
            **{key: value for key, value in persistent.items() if key not in {"binding", "category_driver_mode"}},
            execution_mode="simulated",
            binding_digest=_canonical_digest(persistent),
            runtime_driver=_runtime_driver_identity(driver, True),
        )

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

    connection_query = db.query(InstrumentConnection).filter(
        InstrumentConnection.category_id == category.id
    )
    if lock:
        connection_query = connection_query.with_for_update()
    connection = connection_query.one_or_none()
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

    try:
        registration = get_base_station_adapter_registration(model.model)
    except KeyError as exc:
        raise ValueError("selected baseStation model has no registered real driver") from exc
    expected_class = registration.driver_class
    if not simulated and type(driver) is not expected_class:
        raise ValueError("loaded driver does not match selected registry class")

    expected_transport = _expected_transport(connection)
    if not simulated and _driver_transport(driver) != expected_transport:
        raise ValueError(
            "loaded driver connection identity/transport does not match selected connection"
        )

    params = connection.connection_params if isinstance(connection.connection_params, dict) else {}
    raw_profile = params.get("base_station_adapter_profile")
    if registration.manifest.profile_requirement == "required":
        if raw_profile is None:
            raise ValueError(
                "CMW500 内部 Route 未配置：请在仪器资源配置中完整填写并保存七个字段"
            )
        assert registration.profile_model is not None
        profile = registration.profile_model.model_validate(raw_profile).model_dump(mode="json")
        status = "configured"
    else:
        if raw_profile is not None:
            raise ValueError("selected baseStation adapter profile is not applicable")
        profile = None
        status = "not_applicable"

    formal_capability = None
    if registration.manifest.formal_gate == "connection_approval":
        updated_at = connection.cmw500_lte_2x2_formal_updated_at
        formal_capability = {
            "schema_version": 1,
            "instrument_connection_id": str(connection.id),
            "enabled": connection.cmw500_lte_2x2_formal_enabled is True,
            "updated_at": updated_at.isoformat() if updated_at is not None else None,
        }

    persistent = {
        "schema_version": 1,
        "status": status,
        "category_id": str(category.id),
        "instrument_model_id": str(model.id),
        "instrument_connection_id": str(connection.id),
        "lab_profile_id": str(lab.id),
        "manifest": registration.manifest.model_dump(mode="json"),
        "profile": profile,
        "expected_driver_module": expected_class.__module__,
        "expected_driver_name": expected_class.__name__,
        "expected_transport": expected_transport,
        "formal_capability": formal_capability,
        "binding": {
            "connection_endpoint": binding_endpoint.strip(),
            "driver_mode": binding.get("driver_mode"),
            "role": binding.get("role"),
        },
        "category_driver_mode": category.driver_mode,
    }
    return ResolvedBaseStationBinding(
        **{
            key: value
            for key, value in persistent.items()
            if key not in {"binding", "category_driver_mode", "manifest"}
        },
        execution_mode="simulated" if simulated else "real",
        manifest=registration.manifest,
        binding_digest=_canonical_digest(persistent),
        runtime_driver=_runtime_driver_identity(driver, simulated),
    )
