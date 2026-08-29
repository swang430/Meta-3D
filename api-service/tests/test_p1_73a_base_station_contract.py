"""P1-73A Task 1：厂商无关 BaseStation 应用契约。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import inspect

import pytest

from app.hal import base_station
from app.hal import uxm_base_station
from app.services import instrument_hal_service
from app.services.mimo_ota import cell_config_consistency


_EXPECTED_FIELDS = {
    "BaseStationIdentity": ("adapter_id", "model", "firmware_version", "options"),
    "AppliedCellConfig": ("ue_max_dl_layers", "ue_max_modulation_dl"),
    "BaseStationConfigResult": ("requested", "applied", "confirmed", "reason"),
    "BaseStationCleanupResult": (
        "stop_signaling_confirmed",
        "safe_idle_confirmed",
        "warnings",
    ),
    "BaseStationRemoteSessionResult": (
        "adapter_id",
        "session_token",
        "acquired_confirmed",
        "warnings",
    ),
    "BaseStationControlReleaseResult": (
        "measurement_attempt_id",
        "lease_id",
        "adapter_id",
        "session_token",
        "remote_session_acquired_confirmed",
        "transport_session_released_confirmed",
        "front_panel_local_confirmed",
        "warnings",
    ),
}


def _shared_type(name: str):
    value = getattr(base_station, name, None)
    assert value is not None, f"通用 HAL 缺少 {name}"
    return value


@pytest.mark.parametrize("name, expected_fields", _EXPECTED_FIELDS.items())
def test_shared_contract_types_are_frozen_dataclasses(name, expected_fields):
    contract_type = _shared_type(name)
    assert is_dataclass(contract_type)
    assert contract_type.__dataclass_params__.frozen is True
    assert tuple(field.name for field in fields(contract_type)) == expected_fields


def test_shared_contract_instances_reject_mutation():
    identity_type = _shared_type("BaseStationIdentity")
    identity = identity_type(
        adapter_id="uxm",
        model="UXM 5G E7515B",
        firmware_version="A.01",
        options=("N7630",),
    )

    with pytest.raises(FrozenInstanceError):
        identity.model = "CMW500"


def test_applied_cell_config_has_one_common_runtime_type():
    shared_type = _shared_type("AppliedCellConfig")
    assert uxm_base_station.AppliedCellConfig is shared_type
    assert cell_config_consistency.AppliedCellConfig is shared_type

    result = cell_config_consistency.check_cell_config_consistency(
        requested_mimo_layers=4,
        applied=shared_type(ue_max_dl_layers=2),
    )
    assert result.consistent is False


def test_shared_service_does_not_import_the_uxm_driver_module():
    source = inspect.getsource(cell_config_consistency)
    assert "app.hal.uxm_base_station" not in source
    assert "from app.hal.base_station import AppliedCellConfig" in source


def test_common_hal_no_longer_defines_vendor_command_builder():
    source = inspect.getsource(base_station)
    assert "def build_uxm_downlink_power_command" not in source


def test_uxm_power_builder_keeps_existing_command_shape_after_relocation():
    command = uxm_base_station.build_uxm_downlink_power_command(
        {"detected_test_app": "LTE_NR_IRAT"},
        -46.0,
    )
    assert command == "BSE:CONFig:NR5G:CELL0:DL:POWer -46.0"


def test_registered_base_station_adapters_have_unique_fixed_identities():
    registry = instrument_hal_service._real_driver_registry()
    registered = registry["baseStation"]

    adapter_ids = {
        model_name: driver_class.adapter_id
        for model_name, driver_class in registered.items()
    }

    assert adapter_ids == {
        "UXM 5G E7515B": "uxm",
        "CMW500": "cmw500",
    }
    assert len(set(adapter_ids.values())) == len(adapter_ids)


def test_registry_validation_rejects_duplicate_base_station_adapter_ids():
    first_manifest = uxm_base_station.RealUxmDriver.adapter_manifest.model_copy(
        update={"adapter_id": "uxm", "model_name": "first"}
    )
    duplicate_manifest = uxm_base_station.RealUxmDriver.adapter_manifest.model_copy(
        update={"adapter_id": "uxm", "model_name": "duplicate"}
    )

    class FirstDriver(base_station.BaseStationDriver):
        adapter_id = "uxm"
        adapter_manifest = first_manifest
        input_level_control_supported = True
        rrc_reconfiguration_supported = False
        mac_throughput_configuration_supported = False

    class DuplicateDriver(base_station.BaseStationDriver):
        adapter_id = "uxm"
        adapter_manifest = duplicate_manifest
        input_level_control_supported = True
        rrc_reconfiguration_supported = False
        mac_throughput_configuration_supported = False

    with pytest.raises(ValueError, match="duplicate base-station adapter_id"):
        instrument_hal_service._validate_base_station_adapter_ids(
            {"first": FirstDriver, "duplicate": DuplicateDriver}
        )
