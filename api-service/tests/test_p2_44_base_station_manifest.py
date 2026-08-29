from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.hal.base_station import BaseStationDriver
from app.hal.base_station_manifest import (
    BaseStationAdapterManifest,
    BaseStationProfileFieldManifest,
    validate_base_station_adapter_registrations,
)
from app.hal.uxm_base_station import RealUxmDriver
from app.services.instrument_hal_service import (
    get_base_station_adapter_registration,
)


CMW_ROUTE_PATHS = {
    "lte_2x2_internal_route.pcc_bb_board",
    "lte_2x2_internal_route.rx_connector",
    "lte_2x2_internal_route.rx_converter",
    "lte_2x2_internal_route.tx1_connector",
    "lte_2x2_internal_route.tx1_converter",
    "lte_2x2_internal_route.tx2_connector",
    "lte_2x2_internal_route.tx2_converter",
}


def _field(path: str = "route.a") -> BaseStationProfileFieldManifest:
    return BaseStationProfileFieldManifest(
        path=path,
        label=path,
        required=True,
        placeholder="VALUE",
        description="configured adapter field",
    )


def _manifest(**overrides) -> BaseStationAdapterManifest:
    payload = {
        "schema_version": 1,
        "adapter_id": "adapter-a",
        "model_name": "Model A",
        "vendor": "Vendor",
        "rats": ["lte"],
        "capabilities": ["config", "measurement_window"],
        "profile_requirement": "required",
        "profile_fields": [_field()],
        "manual_sources": ["Instrument_API_Doc/vendor/manual.pdf"],
        "diagnostic_supported": True,
        "formal_gate": "site_certification",
    }
    payload.update(overrides)
    return BaseStationAdapterManifest.model_validate(payload)


def test_registered_base_station_manifests_match_registry_and_profile_contracts():
    uxm = get_base_station_adapter_registration("UXM 5G E7515B")
    cmw = get_base_station_adapter_registration("CMW500")

    assert uxm.driver_class.adapter_id == uxm.manifest.adapter_id == "uxm"
    assert uxm.manifest.model_name == "UXM 5G E7515B"
    assert uxm.manifest.profile_requirement == "not_applicable"
    assert uxm.manifest.profile_fields == ()
    assert uxm.profile_model is None
    assert uxm.manifest.rats == ("nr5g",)

    assert cmw.driver_class.adapter_id == cmw.manifest.adapter_id == "cmw500"
    assert cmw.manifest.model_name == "CMW500"
    assert cmw.manifest.profile_requirement == "required"
    assert {item.path for item in cmw.manifest.profile_fields} == CMW_ROUTE_PATHS
    assert cmw.profile_model is not None
    assert cmw.manifest.formal_gate == "site_certification"

    public = cmw.manifest.model_dump(mode="json")
    assert "profile_model" not in public
    assert all(isinstance(source, str) for source in public["manual_sources"])
    assert "SCPI" not in repr(public)


@pytest.mark.parametrize(
    "overrides",
    [
        {"profile_fields": [_field("route.a"), _field("route.a")]},
        {"profile_requirement": "required", "profile_fields": []},
        {
            "profile_requirement": "not_applicable",
            "profile_fields": [_field()],
        },
        {"rats": ["lte", "lte"]},
        {"capabilities": ["config", "config"]},
        {"manual_sources": []},
        {"formal_gate": "site_guess"},
    ],
)
def test_manifest_rejects_ambiguous_or_unverifiable_public_contract(overrides):
    with pytest.raises(ValidationError):
        _manifest(**overrides)


def test_registration_validation_rejects_missing_or_duplicate_adapter_identity():
    first_manifest = RealUxmDriver.adapter_manifest.model_copy(
        update={"adapter_id": "adapter-a", "model_name": "Model A"}
    )
    duplicate_manifest = RealUxmDriver.adapter_manifest.model_copy(
        update={"adapter_id": "adapter-a", "model_name": "Model B"}
    )
    first_driver = type(
        "FirstDriver",
        (BaseStationDriver,),
        {
            "adapter_id": "adapter-a",
            "adapter_manifest": first_manifest,
            "input_level_control_supported": True,
            "rrc_reconfiguration_supported": True,
            "mac_throughput_configuration_supported": True,
        },
    )
    duplicate_driver = type(
        "DuplicateDriver",
        (BaseStationDriver,),
        {
            "adapter_id": "adapter-a",
            "adapter_manifest": duplicate_manifest,
            "input_level_control_supported": True,
            "rrc_reconfiguration_supported": True,
            "mac_throughput_configuration_supported": True,
        },
    )
    first = SimpleNamespace(
        manifest=first_manifest,
        driver_class=first_driver,
        profile_model=None,
    )
    duplicate = SimpleNamespace(
        manifest=duplicate_manifest,
        driver_class=duplicate_driver,
        profile_model=None,
    )

    with pytest.raises(ValueError, match="duplicate base-station adapter_id"):
        validate_base_station_adapter_registrations(
            {"Model A": first, "Model B": duplicate}
        )

    missing = SimpleNamespace(
        manifest=None,
        driver_class=SimpleNamespace(adapter_id="adapter-c"),
        profile_model=None,
    )
    with pytest.raises(ValueError, match="manifest"):
        validate_base_station_adapter_registrations({"Model C": missing})
