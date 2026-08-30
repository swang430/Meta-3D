"""Server-owned saved drafts for each registered BaseStation model."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
