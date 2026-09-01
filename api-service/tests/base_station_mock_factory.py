"""Test-only factory for a manifest-bound diagnostic BaseStation mock."""

from __future__ import annotations

from typing import Any

from app.hal.base_station import MockBaseStation
from app.services.instrument_hal_service import (
    get_base_station_adapter_registration,
)


def registered_mock_base_station(
    instrument_id: str,
    config: dict[str, Any] | None = None,
    *,
    model_name: str | None = None,
) -> MockBaseStation:
    """Build a test mock from one exact production adapter registration."""

    payload = dict(config or {})
    selected_model = model_name if model_name is not None else payload.get("model")
    if not isinstance(selected_model, str) or not selected_model.strip():
        raise ValueError("test BaseStation mock requires an explicit registered model")
    registration = get_base_station_adapter_registration(selected_model)
    payload["model"] = selected_model
    return MockBaseStation(
        instrument_id,
        payload,
        adapter_manifest=registration.manifest,
    )
