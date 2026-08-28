"""Vendor-neutral declarations for registered base-station adapters.

The public manifest describes application-owned integration boundaries only.
Instrument command semantics remain in each driver and its cited vendor manual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Mapping

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


class BaseStationAdapterManifest(BaseModel):
    """Immutable, JSON-safe contract declared by one base-station adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    adapter_id: str
    model_name: str
    vendor: str
    rats: tuple[str, ...]
    capabilities: tuple[str, ...]
    profile_requirement: Literal["required", "not_applicable"]
    profile_fields: tuple[BaseStationProfileFieldManifest, ...]
    manual_sources: tuple[str, ...]
    diagnostic_supported: bool
    formal_gate: Literal["site_certification"]

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

    @field_validator("rats", "capabilities")
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
