"""Vendor-neutral declarations for registered base-station adapters.

The public manifest describes application-owned integration boundaries only.
Instrument command semantics remain in each driver and its cited vendor manual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_FIELD_PATH_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


class BaseStationProfileFieldManifest(BaseModel):
    """One persisted vendor-profile field rendered by generic consumers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    label: str
    required: bool
    placeholder: str
    description: str

    @field_validator("path")
    @classmethod
    def _valid_path(cls, value: str) -> str:
        normalized = value.strip()
        if not _FIELD_PATH_RE.fullmatch(normalized):
            raise ValueError("profile field path must be a dotted identifier")
        return normalized

    @field_validator("label", "placeholder", "description")
    @classmethod
    def _non_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("profile field text must be non-blank")
        return normalized


class BaseStationRatCapability(BaseModel):
    """One RAT implemented by the application adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rat: Literal["lte", "nr5g"]
    source_reference: str

    @field_validator("source_reference")
    @classmethod
    def _auditable_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_reference must be non-blank")
        return normalized


class BaseStationConfigFieldCapability(BaseModel):
    """Static support/readback boundary for one common config field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    support: Literal["authoritative", "diagnostic_only", "not_applicable"]
    readback: Literal["authoritative", "unavailable", "not_applicable"]
    reason: str
    source_reference: str | None = None

    @field_validator("field")
    @classmethod
    def _valid_field(cls, value: str) -> str:
        normalized = value.strip()
        if not _TOKEN_RE.fullmatch(normalized):
            raise ValueError("config field must be a lowercase identifier")
        return normalized

    @field_validator("reason")
    @classmethod
    def _reason_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("config field reason must be non-blank")
        return normalized

    @field_validator("source_reference")
    @classmethod
    def _normalize_optional_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_reference must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _support_matches_readback(self):
        if (
            self.support == "authoritative" or self.readback == "authoritative"
        ) and self.source_reference is None:
            raise ValueError("authoritative config capability requires source_reference")
        if self.support == "not_applicable" and self.readback != "not_applicable":
            raise ValueError("not_applicable config support requires not_applicable readback")
        if self.support != "not_applicable" and self.readback == "not_applicable":
            raise ValueError("applicable config support cannot use not_applicable readback")
        return self


class BaseStationAttachStageCapability(BaseModel):
    """Static evidence strength available for one attach milestone."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal[
        "cell_ready",
        "ue_registered",
        "rrc_connected",
        "data_bearer_established",
    ]
    evidence: Literal[
        "authoritative",
        "diagnostic_only",
        "unavailable",
        "not_applicable",
    ]
    reason: str
    source_reference: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("attach stage reason must be non-blank")
        return normalized

    @field_validator("source_reference")
    @classmethod
    def _normalize_optional_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_reference must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _authoritative_stage_has_source(self):
        if self.evidence == "authoritative" and self.source_reference is None:
            raise ValueError("authoritative attach stage requires source_reference")
        return self


class BaseStationMetricCapability(BaseModel):
    """One stable metric key exposed by an adapter measurement window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    direction: Literal["downlink", "uplink", "link", "not_applicable"]
    unit: Literal["mbps", "percent", "index", "raw", "not_applicable"]
    scopes: tuple[Literal["pcell", "all_cells"], ...]
    evidence: Literal["authoritative", "diagnostic_only", "unavailable"]
    source_reference: str | None = None

    @field_validator("key")
    @classmethod
    def _valid_key(cls, value: str) -> str:
        normalized = value.strip()
        if not _TOKEN_RE.fullmatch(normalized):
            raise ValueError("metric key must be a lowercase identifier")
        return normalized

    @field_validator("scopes")
    @classmethod
    def _unique_scopes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or len(set(values)) != len(values):
            raise ValueError("metric scopes must be non-empty and unique")
        return values

    @field_validator("source_reference")
    @classmethod
    def _normalize_optional_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_reference must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _authoritative_metric_has_source(self):
        if self.evidence == "authoritative" and self.source_reference is None:
            raise ValueError("authoritative metric requires source_reference")
        return self


class BaseStationMeasurementCapability(BaseModel):
    """Static measurement-window shape and currently supported metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cardinality: Literal["requested", "single"]
    scopes: tuple[Literal["pcell", "all_cells"], ...]
    lifecycle: Literal["authoritative_closed", "clear_read_only", "unavailable"]
    metrics: tuple[BaseStationMetricCapability, ...]
    source_reference: str | None = None

    @field_validator("scopes")
    @classmethod
    def _unique_scopes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or len(set(values)) != len(values):
            raise ValueError("measurement scopes must be non-empty and unique")
        return values

    @field_validator("source_reference")
    @classmethod
    def _normalize_optional_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("source_reference must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _valid_measurement_shape(self):
        keys = [metric.key for metric in self.metrics]
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("measurement metric keys must be non-empty and unique")
        if self.lifecycle == "authoritative_closed" and self.source_reference is None:
            raise ValueError("authoritative closed lifecycle requires source_reference")
        if any(not set(metric.scopes).issubset(self.scopes) for metric in self.metrics):
            raise ValueError("metric scopes must be declared by the measurement window")
        return self


class BaseStationAdapterManifest(BaseModel):
    """Immutable, JSON-safe contract declared by one base-station adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Schema 1 remains readable only while registered adapters migrate in
    # P2-46.  Registry validation will require schema 2 before this slice ends.
    schema_version: Literal[1, 2]
    adapter_id: str
    model_name: str
    vendor: str
    rats: tuple[str, ...]
    capabilities: tuple[str, ...]
    rat_capabilities: tuple[BaseStationRatCapability, ...] = ()
    operations: tuple[str, ...] = ()
    config_fields: tuple[BaseStationConfigFieldCapability, ...] = ()
    attach_stages: tuple[BaseStationAttachStageCapability, ...] = ()
    measurement: BaseStationMeasurementCapability | None = None
    profile_requirement: Literal["required", "not_applicable"]
    profile_schema_version: int | None = None
    profile_fields: tuple[BaseStationProfileFieldManifest, ...]
    manual_sources: tuple[str, ...]
    diagnostic_supported: bool
    formal_gate: Literal["site_certification"]

    @model_validator(mode="before")
    @classmethod
    def _derive_legacy_mirrors(cls, value: Any) -> Any:
        if not isinstance(value, Mapping) or value.get("schema_version") != 2:
            return value
        payload = dict(value)
        rat_items = payload.get("rat_capabilities") or ()
        operation_items = payload.get("operations") or ()

        def _read(item: Any, key: str) -> Any:
            if isinstance(item, Mapping):
                return item.get(key)
            return getattr(item, key, None)

        derived_rats = tuple(_read(item, "rat") for item in rat_items)
        derived_operations = tuple(operation_items)
        payload.setdefault("rats", derived_rats)
        payload.setdefault("capabilities", derived_operations)
        return payload

    @field_validator("adapter_id")
    @classmethod
    def _valid_adapter_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _TOKEN_RE.fullmatch(normalized):
            raise ValueError("adapter_id must be a lowercase identifier")
        return normalized

    @field_validator("model_name", "vendor")
    @classmethod
    def _non_blank_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("manifest identity must be non-blank")
        return normalized

    @field_validator("rats", "capabilities", "operations")
    @classmethod
    def _unique_tokens(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not _TOKEN_RE.fullmatch(value) for value in normalized):
            raise ValueError("manifest tokens must be non-empty lowercase identifiers")
        if len(set(normalized)) != len(normalized):
            raise ValueError("manifest tokens must be unique")
        return normalized

    @field_validator("manual_sources")
    @classmethod
    def _auditable_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ValueError("manual_sources must contain auditable non-blank paths")
        if len(set(normalized)) != len(normalized):
            raise ValueError("manual_sources must be unique")
        return normalized

    @model_validator(mode="after")
    def _profile_shape_matches_requirement(self):
        paths = [field.path for field in self.profile_fields]
        if len(set(paths)) != len(paths):
            raise ValueError("profile field paths must be unique")
        if self.profile_requirement == "required" and not self.profile_fields:
            raise ValueError("required profile must declare profile_fields")
        if self.profile_requirement == "not_applicable" and self.profile_fields:
            raise ValueError("not_applicable profile cannot declare profile_fields")
        if self.schema_version == 1:
            return self
        if self.profile_requirement == "required":
            if type(self.profile_schema_version) is not int or self.profile_schema_version < 1:
                raise ValueError("required profile needs a positive profile_schema_version")
        elif self.profile_schema_version is not None:
            raise ValueError("not_applicable profile requires profile_schema_version null")

        derived_rats = tuple(item.rat for item in self.rat_capabilities)
        if self.rats != derived_rats:
            raise ValueError("legacy rats mirror must match rat_capabilities")
        if self.capabilities != self.operations:
            raise ValueError("legacy capabilities mirror must match operations")

        from app.hal.base_station import BaseStationRequestedConfig
        from dataclasses import fields

        expected_config_fields = {
            field.name for field in fields(BaseStationRequestedConfig)
        }
        actual_config_fields = [field.field for field in self.config_fields]
        if (
            set(actual_config_fields) != expected_config_fields
            or len(actual_config_fields) != len(expected_config_fields)
        ):
            raise ValueError("config fields must cover BaseStationRequestedConfig exactly")
        expected_attach_stages = {
            "cell_ready",
            "ue_registered",
            "rrc_connected",
            "data_bearer_established",
        }
        actual_attach_stages = [stage.stage for stage in self.attach_stages]
        if (
            set(actual_attach_stages) != expected_attach_stages
            or len(actual_attach_stages) != len(expected_attach_stages)
        ):
            raise ValueError("attach stages must cover the common milestone set exactly")
        if not self.rat_capabilities:
            raise ValueError("rat_capabilities must be non-empty")
        if not self.operations:
            raise ValueError("operations must be non-empty")
        if self.measurement is None:
            raise ValueError("measurement capability is required")
        return self


@dataclass(frozen=True)
class BaseStationAdapterRegistration:
    """Internal registration; Python implementation types never enter the API."""

    manifest: BaseStationAdapterManifest
    driver_class: type
    profile_model: type[BaseModel] | None


def validate_base_station_adapter_registrations(
    registrations: Mapping[str, object],
) -> None:
    """Fail loudly when registry identity and declared manifest diverge."""

    seen: dict[str, str] = {}
    for model_name, registration in registrations.items():
        manifest = getattr(registration, "manifest", None)
        if not isinstance(manifest, BaseStationAdapterManifest):
            raise ValueError(f"base-station manifest missing for {model_name!r}")
        driver_class = getattr(registration, "driver_class", None)
        driver_adapter_id = getattr(driver_class, "adapter_id", None)
        if manifest.model_name != model_name:
            raise ValueError(
                f"base-station manifest model mismatch: {model_name!r} != "
                f"{manifest.model_name!r}"
            )
        if driver_adapter_id != manifest.adapter_id:
            raise ValueError(
                f"base-station adapter_id mismatch for {model_name}: "
                f"{driver_adapter_id!r} != {manifest.adapter_id!r}"
            )
        previous_model = seen.get(manifest.adapter_id)
        if previous_model is not None:
            raise ValueError(
                "duplicate base-station adapter_id "
                f"{manifest.adapter_id!r}: {previous_model!r} and {model_name!r}"
            )
        seen[manifest.adapter_id] = model_name

        profile_model = getattr(registration, "profile_model", None)
        if manifest.profile_requirement == "required" and profile_model is None:
            raise ValueError(f"required profile model missing for {model_name!r}")
        if manifest.profile_requirement == "not_applicable" and profile_model is not None:
            raise ValueError(f"unexpected profile model for {model_name!r}")
