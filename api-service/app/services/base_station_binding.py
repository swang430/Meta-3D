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


class BaseStationBindingPreview(BaseModel):
    """Structured read-only projection used by API sync/readiness surfaces."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[
        "configured", "not_applicable", "diagnostic_unbound", "invalid"
    ]
    binding_digest: str | None
    execution_mode: Literal["real", "simulated"] | None
    adapter_id: str | None
    model_name: str | None
    category_id: str | None
    instrument_model_id: str | None
    instrument_connection_id: str | None
    lab_profile_id: str
    resolved_binding: dict[str, Any] | None
    runtime_driver: dict[str, Any] | None
    detail: str

    @classmethod
    def from_resolved(
        cls,
        resolved: ResolvedBaseStationBinding,
    ) -> "BaseStationBindingPreview":
        return cls(
            status=resolved.status,
            binding_digest=resolved.binding_digest,
            execution_mode=resolved.execution_mode,
            adapter_id=(
                resolved.manifest.adapter_id if resolved.manifest is not None else None
            ),
            model_name=(
                resolved.manifest.model_name if resolved.manifest is not None else None
            ),
            category_id=resolved.category_id,
            instrument_model_id=resolved.instrument_model_id,
            instrument_connection_id=resolved.instrument_connection_id,
            lab_profile_id=resolved.lab_profile_id,
            resolved_binding=resolved.stable_projection(),
            runtime_driver=resolved.runtime_driver.model_dump(mode="json"),
            detail="BaseStation binding resolved from current server truth",
        )


def build_base_station_binding_preview(
    db,
    hal,
    selected_lab_profile: LabProfile,
) -> BaseStationBindingPreview:
    """Resolve a preview; invalid truth stays explicit and never looks ready."""

    try:
        resolved = resolve_base_station_binding(db, hal, selected_lab_profile)
    except ValueError as exc:
        return BaseStationBindingPreview(
            status="invalid",
            binding_digest=None,
            execution_mode=None,
            adapter_id=None,
            model_name=None,
            category_id=None,
            instrument_model_id=None,
            instrument_connection_id=None,
            lab_profile_id=str(selected_lab_profile.id),
            resolved_binding=None,
            runtime_driver=None,
            detail=str(exc),
        )
    return BaseStationBindingPreview.from_resolved(resolved)


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


def validate_loaded_base_station_driver_binding(
    model: InstrumentModel,
    connection: InstrumentConnection,
    driver,
) -> str | None:
    """Validate a loaded real driver against saved model and transport truth."""

    if driver is None:
        return "loaded driver is missing"
    if is_mock_driver(driver):
        return "loaded driver is simulated"
    try:
        registration = get_base_station_adapter_registration(model.model)
    except KeyError:
        return "selected baseStation model has no registered real driver"
    if type(driver) is not registration.driver_class:
        return "loaded driver does not match selected registry class"
    if getattr(driver, "adapter_id", None) != registration.manifest.adapter_id:
        return "loaded driver adapter does not match selected adapter"
    try:
        expected_transport = _expected_transport(connection)
    except ValueError as exc:
        return str(exc)
    if _driver_transport(driver) != expected_transport:
        return (
            "loaded driver connection identity/transport does not match "
            "selected connection"
        )
    return None


def build_saved_base_station_driver_validator(
    model: InstrumentModel,
    connection: InstrumentConnection,
):
    """Freeze saved driver identity for a lease-time pre-I/O validation."""

    try:
        registration = get_base_station_adapter_registration(model.model)
    except KeyError as exc:
        raise ValueError(
            "selected baseStation model has no registered real driver"
        ) from exc
    expected_class = registration.driver_class
    expected_adapter = registration.manifest.adapter_id
    expected_transport = _expected_transport(connection)
    identity = _canonical_digest(
        {
            "driver_module": expected_class.__module__,
            "driver_name": expected_class.__name__,
            "adapter_id": expected_adapter,
            "transport": expected_transport,
        }
    )

    def _validate(hal):
        driver = _loaded_base_station(hal)
        if driver is None:
            detail = "loaded driver is missing"
        elif is_mock_driver(driver):
            detail = "loaded driver is simulated"
        elif type(driver) is not expected_class:
            detail = "loaded driver does not match selected registry class"
        elif getattr(driver, "adapter_id", None) != expected_adapter:
            detail = "loaded driver adapter does not match selected adapter"
        elif _driver_transport(driver) != expected_transport:
            detail = (
                "loaded driver connection identity/transport does not match "
                "selected connection"
            )
        else:
            return None
        return f"baseStation driver binding mismatch: {detail}"

    _validate.validation_identity = identity
    return _validate


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
        category_query = category_query.execution_options(
            populate_existing=True
        ).with_for_update()
    category = category_query.one_or_none()
    if category is None:
        raise ValueError("baseStation category is not configured")

    lab = selected_lab_profile
    if lock:
        lab = (
            db.query(LabProfile)
            .filter(LabProfile.id == selected_lab_profile.id)
            .execution_options(populate_existing=True)
            .with_for_update()
            .one_or_none()
        )
        if lab is None:
            raise ValueError("selected LabProfile no longer exists")
    binding = _single_binding(lab, str(category.id))
    category_driver_mode = category.driver_mode or "auto"
    binding_driver_mode = binding.get("driver_mode")
    if category_driver_mode not in {"auto", "mock", "real"}:
        raise ValueError("baseStation category driver mode is invalid")
    if binding_driver_mode not in {"auto", "mock", "real"}:
        raise ValueError("LabProfile baseStation binding driver mode is invalid")
    if binding_driver_mode != category_driver_mode:
        raise ValueError(
            "LabProfile baseStation binding driver mode does not match "
            "the current category driver mode"
        )
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
        if category_driver_mode == "real":
            raise ValueError(
                "loaded driver mode does not match the explicit real category driver mode"
            )
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
                "driver_mode": binding_driver_mode,
                "role": binding.get("role"),
            },
            "category_driver_mode": category_driver_mode,
        }
        return ResolvedBaseStationBinding(
            **{key: value for key, value in persistent.items() if key not in {"binding", "category_driver_mode"}},
            execution_mode="simulated",
            binding_digest=_canonical_digest(persistent),
            runtime_driver=_runtime_driver_identity(driver, True),
        )

    if category_driver_mode == "real" and simulated:
        raise ValueError(
            "loaded driver mode does not match the explicit real category driver mode"
        )
    if category_driver_mode == "mock" and not simulated:
        raise ValueError(
            "loaded driver mode does not match the explicit mock category driver mode"
        )

    if str(binding_model_id) != str(selected_model_id):
        raise ValueError("baseStation binding does not match selected_model_id")
    model_query = db.query(InstrumentModel).filter(
        InstrumentModel.id == selected_model_id,
        InstrumentModel.category_id == category.id,
    )
    if lock:
        # InstrumentModel rows are registry metadata and are not mutated in this
        # workflow, but a preloaded identity-map value must not become binding
        # truth after the surrounding persistent rows have been locked.
        model_query = model_query.execution_options(populate_existing=True)
    model = model_query.one_or_none()
    if model is None:
        raise ValueError("selected baseStation model is missing from the registry")

    connection_query = db.query(InstrumentConnection).filter(
        InstrumentConnection.category_id == category.id
    )
    if lock:
        connection_query = connection_query.execution_options(
            populate_existing=True
        ).with_for_update()
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
    if (
        simulated
        and getattr(driver, "adapter_id", None)
        != registration.manifest.adapter_id
    ):
        raise ValueError(
            "loaded mock driver adapter does not match selected adapter; "
            "reload HAL after BaseStation model change"
        )
    expected_transport = _expected_transport(connection)
    expected_class = registration.driver_class
    if not simulated:
        driver_binding_error = validate_loaded_base_station_driver_binding(
            model,
            connection,
            driver,
        )
        if driver_binding_error is not None:
            raise ValueError(driver_binding_error)

    params = connection.connection_params if isinstance(connection.connection_params, dict) else {}
    raw_profile = params.get("base_station_adapter_profile")
    if registration.manifest.profile_requirement == "required":
        if raw_profile is None:
            required_fields = ", ".join(
                field.label
                for field in registration.manifest.profile_fields
                if field.required
            )
            raise ValueError(
                f"{registration.manifest.model_name} required adapter profile "
                f"is missing; configure and save required fields: {required_fields}"
            )
        assert registration.profile_model is not None
        profile = registration.profile_model.model_validate(raw_profile).model_dump(mode="json")
        status = "configured"
    else:
        if raw_profile is not None:
            raise ValueError("selected baseStation adapter profile is not applicable")
        profile = None
        status = "not_applicable"

    # P2-45: retain the historical CMW approval projection for old readers,
    # but it is no longer a formal gate and must not influence binding_digest.
    formal_capability = None
    if registration.manifest.adapter_id == "cmw500":
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
            "driver_mode": binding_driver_mode,
            "role": binding.get("role"),
        },
        "category_driver_mode": category_driver_mode,
    }
    digest_payload = {**persistent, "formal_capability": None}
    return ResolvedBaseStationBinding(
        **{
            key: value
            for key, value in persistent.items()
            if key not in {"binding", "category_driver_mode", "manifest"}
        },
        execution_mode="simulated" if simulated else "real",
        manifest=registration.manifest,
        binding_digest=_canonical_digest(digest_payload),
        runtime_driver=_runtime_driver_identity(driver, simulated),
    )
