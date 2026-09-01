"""Public API schemas for the resolved BaseStation binding."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.hal.base_station_compatibility import (
    BaseStationCompatibilityVerdict,
    BaseStationExecutionRequirements,
)


class BaseStationCompatibilityPreviewResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_serialization_defaults_required=True,
    )

    schema_version: Literal[1] = 1
    status: Literal[
        "compatible",
        "incompatible",
        "no_adapter",
        "not_evaluated",
        "invalid",
    ]
    compatible: bool | None
    test_case_id: str | None
    lab_profile_id: str | None
    binding_digest: str | None
    execution_mode: Literal["real", "simulated"] | None
    requirements: BaseStationExecutionRequirements | None
    verdict: BaseStationCompatibilityVerdict | None
    reasons: tuple[str, ...]
    detail: str


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
    testcase_compatibility: BaseStationCompatibilityPreviewResponse | None = None
