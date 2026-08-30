"""Server-owned saved drafts for each registered BaseStation model."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm.attributes import flag_modified

from app.models.instrument import InstrumentConnection, InstrumentModel


class BaseStationModelPreset(BaseModel):
    """One saved model draft; never used directly as execution truth."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    model_id: UUID
    endpoint: str
    controller: str = ""
    notes: str = ""
    connection_params: dict[str, Any] = Field(default_factory=dict)
    base_station_adapter_profile: dict[str, Any] | None = None

    @field_validator("endpoint")
    @classmethod
    def _endpoint_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("BaseStation preset endpoint must be non-blank")
        return normalized

    @field_validator("controller", "notes")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _dedicated_profile_only(self):
        if "base_station_adapter_profile" in self.connection_params:
            raise ValueError(
                "BaseStation adapter profile must use the dedicated preset field"
            )
        return self


def parse_base_station_model_presets(raw: Any) -> dict[str, BaseStationModelPreset]:
    """Parse the complete server-owned map; malformed stored data fails loud."""

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("BaseStation model presets must be an object")
    parsed: dict[str, BaseStationModelPreset] = {}
    for key, value in raw.items():
        preset = BaseStationModelPreset.model_validate(value)
        canonical_key = str(preset.model_id)
        if key != canonical_key or canonical_key in parsed:
            raise ValueError("BaseStation model preset key must match unique model_id")
        parsed[canonical_key] = preset
    return parsed


def _validated_profile_for_model(
    model: InstrumentModel, raw_profile: dict[str, Any] | None
) -> dict[str, Any] | None:
    from app.services.instrument_hal_service import (
        get_base_station_adapter_registration,
    )

    try:
        registration = get_base_station_adapter_registration(model.model)
    except KeyError as exc:
        raise ValueError(
            "selected BaseStation model has no registered adapter manifest"
        ) from exc
    if registration.manifest.profile_requirement == "required":
        if raw_profile is None or registration.profile_model is None:
            raise ValueError("selected BaseStation model requires an adapter profile")
        return registration.profile_model.model_validate(raw_profile).model_dump(
            mode="json"
        )
    if raw_profile is not None:
        raise ValueError("selected BaseStation adapter does not accept a vendor profile")
    return None


def _snapshot_active_connection(
    model: InstrumentModel, connection: InstrumentConnection
) -> BaseStationModelPreset | None:
    endpoint = (connection.endpoint or "").strip()
    if not endpoint:
        return None
    params = dict(connection.connection_params or {})
    raw_profile = params.pop("base_station_adapter_profile", None)
    profile = _validated_profile_for_model(model, raw_profile)
    return BaseStationModelPreset(
        model_id=model.id,
        endpoint=endpoint,
        controller=connection.protocol or "",
        notes=connection.notes or "",
        connection_params=params,
        base_station_adapter_profile=profile,
    )


def save_base_station_model_preset(
    *,
    category: Any,
    current_model: InstrumentModel | None,
    target_model: InstrumentModel,
    connection: InstrumentConnection,
    endpoint: str,
    controller: str,
    notes: str,
    connection_params: dict[str, Any] | None,
    base_station_adapter_profile: dict[str, Any] | None,
    parsed_controller_ip: str | None,
    parsed_port: int | None,
) -> None:
    """Atomically stage old+target presets and project target as active truth."""

    presets = parse_base_station_model_presets(connection.base_station_model_presets)
    if (
        current_model is not None
        and current_model.id != target_model.id
        and str(current_model.id) not in presets
    ):
        old = _snapshot_active_connection(current_model, connection)
        if old is not None:
            presets[str(old.model_id)] = old

    generic_params = dict(connection_params or {})
    if "base_station_adapter_profile" in generic_params:
        raise ValueError(
            "base_station_adapter_profile must use the dedicated manifest-validated field"
        )
    profile = _validated_profile_for_model(
        target_model, base_station_adapter_profile
    )
    target = BaseStationModelPreset(
        model_id=target_model.id,
        endpoint=endpoint,
        controller=controller,
        notes=notes,
        connection_params=generic_params,
        base_station_adapter_profile=profile,
    )
    presets[str(target.model_id)] = target
    connection.base_station_model_presets = {
        key: value.model_dump(mode="json") for key, value in presets.items()
    }
    flag_modified(connection, "base_station_model_presets")

    active_params = dict(target.connection_params)
    if target.base_station_adapter_profile is not None:
        active_params["base_station_adapter_profile"] = (
            target.base_station_adapter_profile
        )
    connection.endpoint = target.endpoint
    connection.controller_ip = parsed_controller_ip
    connection.port = parsed_port
    connection.protocol = target.controller
    connection.notes = target.notes
    connection.connection_params = active_params
    flag_modified(connection, "connection_params")
    category.selected_model_id = target.model_id
