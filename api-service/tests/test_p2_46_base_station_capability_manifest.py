from __future__ import annotations

from dataclasses import fields

import pytest
from pydantic import ValidationError

from app.hal.base_station import BaseStationRequestedConfig
from app.hal.base_station import BaseStationDriver, RadioTechnology
from app.hal.base_station_manifest import (
    BaseStationAdapterManifest,
    BaseStationAttachStageCapability,
    BaseStationConfigFieldCapability,
    BaseStationMeasurementCapability,
    BaseStationMetricCapability,
    BaseStationProfileFieldManifest,
    BaseStationRatCapability,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver


CONFIG_FIELD_NAMES = tuple(field.name for field in fields(BaseStationRequestedConfig))
ATTACH_STAGES = (
    "cell_ready",
    "ue_registered",
    "rrc_connected",
    "data_bearer_established",
)


def _config_field(name: str) -> BaseStationConfigFieldCapability:
    return BaseStationConfigFieldCapability(
        field=name,
        support="authoritative",
        readback="authoritative",
        reason="verified by the adapter readback",
        source_reference="Vendor Manual §1",
    )


def _attach_stage(name: str) -> BaseStationAttachStageCapability:
    return BaseStationAttachStageCapability(
        stage=name,
        evidence="authoritative",
        reason="verified state transition",
        source_reference="Vendor Manual §2",
    )


def _metric() -> BaseStationMetricCapability:
    return BaseStationMetricCapability(
        key="dl_throughput_mbps",
        direction="downlink",
        unit="mbps",
        scopes=("pcell",),
        evidence="authoritative",
        source_reference="Vendor Manual §3",
    )


def _payload(**overrides):
    payload = {
        "schema_version": 2,
        "adapter_id": "adapter-a",
        "model_name": "Model A",
        "vendor": "Vendor",
        "rat_capabilities": [
            {
                "rat": "lte",
                "source_reference": "Vendor Manual §1",
            }
        ],
        "operations": ["identity", "config", "cell_attach", "measurement_window"],
        "config_fields": [_config_field(name) for name in CONFIG_FIELD_NAMES],
        "attach_stages": [_attach_stage(name) for name in ATTACH_STAGES],
        "measurement": BaseStationMeasurementCapability(
            cardinality="requested",
            scopes=("pcell",),
            lifecycle="authoritative_closed",
            metrics=(_metric(),),
            source_reference="Vendor Manual §3",
        ),
        "profile_requirement": "required",
        "profile_schema_version": 1,
        "profile_fields": [
            BaseStationProfileFieldManifest(
                path="route.port",
                label="Route port",
                required=True,
                placeholder="PORT1",
                description="Configured route port",
            )
        ],
        "manual_sources": ["Instrument_API_Doc/vendor/manual.pdf"],
        "diagnostic_supported": True,
        "formal_gate": "site_certification",
    }
    payload.update(overrides)
    return payload


def test_structured_capabilities_derive_legacy_mirrors_and_cover_request_fields():
    manifest = BaseStationAdapterManifest.model_validate(_payload())

    assert manifest.schema_version == 2
    assert manifest.profile_schema_version == 1
    assert manifest.rats == ("lte",)
    assert manifest.capabilities == (
        "identity",
        "config",
        "cell_attach",
        "measurement_window",
    )
    assert {item.field for item in manifest.config_fields} == set(CONFIG_FIELD_NAMES)
    assert {item.stage for item in manifest.attach_stages} == set(ATTACH_STAGES)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"rats": ["nr5g"]}, "legacy rats mirror"),
        ({"capabilities": ["identity"]}, "legacy capabilities mirror"),
        ({"config_fields": [_config_field(CONFIG_FIELD_NAMES[0])]}, "config fields"),
        ({"attach_stages": [_attach_stage("cell_ready")]}, "attach stages"),
        (
            {
                "profile_requirement": "not_applicable",
                "profile_schema_version": 1,
                "profile_fields": [],
            },
            "profile_schema_version",
        ),
    ],
)
def test_manifest_rejects_split_or_incomplete_capability_truth(overrides, message):
    with pytest.raises(ValidationError, match=message):
        BaseStationAdapterManifest.model_validate(_payload(**overrides))


def test_authoritative_capabilities_require_auditable_source_reference():
    with pytest.raises(ValidationError, match="source_reference"):
        BaseStationRatCapability(rat="lte", source_reference=" ")

    with pytest.raises(ValidationError, match="source_reference"):
        BaseStationConfigFieldCapability(
            field="band",
            support="authoritative",
            readback="authoritative",
            reason="verified by the adapter readback",
            source_reference="",
        )


def test_not_applicable_profile_has_no_profile_version_or_fields():
    manifest = BaseStationAdapterManifest.model_validate(
        _payload(
            profile_requirement="not_applicable",
            profile_schema_version=None,
            profile_fields=[],
        )
    )
    assert manifest.profile_schema_version is None
    assert manifest.profile_fields == ()


def test_cmw500_manifest_v2_declares_lte_closed_window_and_profile_version():
    manifest = RealCmw500Driver.adapter_manifest

    assert manifest.schema_version == 2
    assert manifest.rats == ("lte",)
    assert manifest.profile_requirement == "required"
    assert manifest.profile_schema_version == 1
    assert manifest.measurement is not None
    assert manifest.measurement.cardinality == "single"
    assert manifest.measurement.scopes == ("pcell",)
    assert manifest.measurement.lifecycle == "authoritative_closed"
    assert {
        (metric.key, metric.direction, metric.unit, metric.evidence)
        for metric in manifest.measurement.metrics
    } == {
        ("dl_throughput_mbps", "downlink", "mbps", "authoritative"),
        ("dl_bler_percent", "downlink", "percent", "authoritative"),
    }


def test_uxm_manifest_v2_declares_nr_only_and_diagnostic_clear_read_window():
    manifest = RealUxmDriver.adapter_manifest

    assert manifest.schema_version == 2
    assert manifest.rats == ("nr5g",)
    assert manifest.profile_requirement == "not_applicable"
    assert manifest.profile_schema_version is None
    assert {
        "input_level_control",
        "rrc_reconfiguration",
        "mac_throughput_config",
    }.issubset(manifest.operations)
    assert manifest.measurement is not None
    assert manifest.measurement.cardinality == "requested"
    assert manifest.measurement.scopes == ("pcell", "all_cells")
    assert manifest.measurement.lifecycle == "clear_read_only"
    assert all(
        metric.evidence == "diagnostic_only"
        for metric in manifest.measurement.metrics
    )
    assert {metric.key for metric in manifest.measurement.metrics} == {
        "dl_throughput_mbps",
        "dl_throughput_current_mbps",
        "ul_throughput_mbps",
        "ul_throughput_current_mbps",
        "dl_bler_percent",
        "ul_bler_percent",
        "cqi",
        "rank_indicator",
        "rsrp_raw",
        "sinr_raw",
    }


def test_real_driver_rat_support_is_derived_from_the_manifest():
    assert RealCmw500Driver.get_supported_technologies is (
        BaseStationDriver.get_supported_technologies
    )
    assert RealUxmDriver.get_supported_technologies is (
        BaseStationDriver.get_supported_technologies
    )

    cmw = RealCmw500Driver.__new__(RealCmw500Driver)
    uxm = RealUxmDriver.__new__(RealUxmDriver)
    assert cmw.get_supported_technologies() == [RadioTechnology.LTE]
    assert uxm.get_supported_technologies() == [RadioTechnology.NR5G]
