"""P2-44 production entry points must stay on the single binding resolver."""

import inspect

from app.api.instrument import get_hal_readiness
from app.api.lab_profile import sync_current_instrument_binding
from app.services.base_station_adapter_profile import (
    freeze_base_station_adapter_profile,
)
from app.services.base_station_binding import build_base_station_binding_preview


def test_binding_entry_points_delegate_to_the_common_resolver_chain():
    inventory = (
        (freeze_base_station_adapter_profile, "resolve_base_station_binding"),
        (build_base_station_binding_preview, "resolve_base_station_binding"),
        (sync_current_instrument_binding, "resolve_base_station_binding"),
        (get_hal_readiness, "build_base_station_binding_preview"),
    )
    for entrypoint, common_call in inventory:
        source = inspect.getsource(entrypoint)
        assert source.count(f"{common_call}(") == 1, (
            f"{entrypoint.__module__}.{entrypoint.__name__} must delegate exactly "
            f"once to {common_call}"
        )


def test_execution_freeze_does_not_requery_model_connection_or_vendor_profile():
    source = inspect.getsource(freeze_base_station_adapter_profile)
    for forbidden in (
        "InstrumentCategory",
        "InstrumentModel",
        "InstrumentConnection",
        "BaseStationAdapterProfile.model_validate",
    ):
        assert forbidden not in source

