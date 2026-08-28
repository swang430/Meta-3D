"""Public API schemas for the resolved BaseStation binding."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class BaseStationBindingPreviewResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_serialization_defaults_required=True,
    )

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
