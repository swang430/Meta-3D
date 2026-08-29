from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.hal.base_station import BaseStationRequestedConfig
from app.hal.base_station import BaseStationDriver, RadioTechnology
from app.hal.base_station_manifest import (
    BaseStationAdapterManifest,
    BaseStationAdapterRegistration,
    BaseStationAttachStageCapability,
    BaseStationConfigFieldCapability,
    BaseStationMeasurementCapability,
    BaseStationMetricCapability,
    BaseStationProfileFieldManifest,
    BaseStationRatCapability,
    validate_base_station_adapter_registrations,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.instrument_hal_service import _validate_base_station_adapter_ids


CONFIG_FIELD_NAMES = tuple(field.name for field in fields(BaseStationRequestedConfig))
REPO_ROOT = Path(__file__).resolve().parents[2]
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


def test_adapter_without_measurement_operation_declares_explicit_null_capability():
    manifest = BaseStationAdapterManifest.model_validate(
        _payload(
            operations=["identity", "config", "cell_attach"],
            measurement=None,
            profile_requirement="not_applicable",
            profile_schema_version=None,
            profile_fields=[],
        )
    )
    registration = _third_adapter_registration(manifest=manifest)

    assert manifest.measurement is None
    validate_base_station_adapter_registrations({"Model A": registration})


@pytest.mark.parametrize(
    "operations, measurement",
    [
        (["identity", "config", "cell_attach", "measurement_window"], None),
        (["identity", "config", "cell_attach"], _payload()["measurement"]),
    ],
)
def test_measurement_operation_and_capability_must_be_declared_together(
    operations, measurement
):
    with pytest.raises(ValidationError, match="measurement_window"):
        BaseStationAdapterManifest.model_validate(
            _payload(operations=operations, measurement=measurement)
        )


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


def test_uxm_manifest_v2_declares_only_capabilities_common_to_all_profiles():
    manifest = RealUxmDriver.adapter_manifest

    assert manifest.schema_version == 2
    assert manifest.rats == ("nr5g",)
    assert manifest.profile_requirement == "not_applicable"
    assert manifest.profile_schema_version is None
    assert "input_level_control" in manifest.operations
    assert "measurement_window" in manifest.operations
    assert "rrc_reconfiguration" not in manifest.operations
    assert "mac_throughput_config" not in manifest.operations
    assert manifest.measurement is not None
    assert manifest.measurement.cardinality == "requested"
    assert manifest.measurement.scopes == ("pcell", "all_cells")
    # P2-52：clear 边界双证据（CLEar 手册原文 + IRAT 现场实测）→ clear_read_only；
    # closed 无出处（IRAT 适用性未说明 + [:STATe]? 查询形无原文）→ 不升
    # authoritative_closed。metrics = 两个可选 profile registry 的保守交集
    # （逐字段一致性由 test_p2_52 的不变量门守着）。
    assert manifest.measurement.lifecycle == "clear_read_only"
    assert manifest.measurement.source_reference is not None
    assert {metric.key for metric in manifest.measurement.metrics} == {
        "cqi_index",
        "ri_index",
    }
    assert not any(
        field.readback == "authoritative"
        for field in manifest.config_fields
    )
    assert not any(
        field.support == "authoritative"
        for field in manifest.config_fields
    )


def test_uxm_authoritative_capability_sources_resolve_to_tracked_archive_anchors():
    manifest = RealUxmDriver.adapter_manifest
    assert manifest.measurement is not None
    authoritative_sources = [
        *(item.source_reference for item in manifest.rat_capabilities),
        *(
            item.source_reference
            for item in manifest.config_fields
            if item.support == "authoritative" or item.readback == "authoritative"
        ),
        # P2-52：测量窗口的 clear 边界出处 + 交集 metrics 的 authoritative
        # 出处也必须解析到 tracked archive 锚点，不许编。
        manifest.measurement.source_reference,
        *(
            metric.source_reference
            for metric in manifest.measurement.metrics
            if metric.evidence == "authoritative"
        ),
    ]

    assert all(source is not None for source in authoritative_sources)
    for source in authoritative_sources:
        archive_path, member_anchor = source.split("!", 1)
        member_name, anchor = member_anchor.split("#", 1)
        archive = REPO_ROOT / archive_path
        assert archive.is_file()
        with ZipFile(archive) as manual:
            assert member_name in manual.namelist()
            html = manual.read(member_name)
        assert f'id="{anchor}"'.encode() in html


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


def _third_adapter_registration(
    *,
    manifest: BaseStationAdapterManifest | None = None,
    driver_attributes: dict | None = None,
    profile_model: type[BaseModel] | None = None,
) -> BaseStationAdapterRegistration:
    manifest = manifest or BaseStationAdapterManifest.model_validate(
        _payload(
            adapter_id="third_adapter",
            model_name="Third Adapter",
            profile_requirement="not_applicable",
            profile_schema_version=None,
            profile_fields=[],
        )
    )
    async def _measure_base_station_window(self, window_s, **kwargs):
        raise RuntimeError("test-only concrete measurement implementation")

    attributes = {
        "adapter_id": manifest.adapter_id,
        "adapter_manifest": manifest,
        "adapter_profile_model": profile_model,
        "measure_base_station_window": _measure_base_station_window,
        **(driver_attributes or {}),
    }
    driver_class = type("ThirdAdapterDriver", (BaseStationDriver,), attributes)
    return BaseStationAdapterRegistration(
        manifest=manifest,
        driver_class=driver_class,
        profile_model=profile_model,
    )


def test_registration_accepts_a_new_adapter_without_registry_code_changes():
    registration = _third_adapter_registration()

    validate_base_station_adapter_registrations(
        {"Third Adapter": registration}
    )


def test_production_registration_uses_driver_declared_profile_model_for_third_adapter():
    class ThirdAdapterProfile(BaseModel):
        model_config = ConfigDict(extra="forbid")

        schema_version: Literal[1] = 1
        adapter: Literal["third_adapter"] = "third_adapter"
        route: dict

    manifest = BaseStationAdapterManifest.model_validate(
        _payload(adapter_id="third_adapter", model_name="Third Adapter")
    )
    registration = _third_adapter_registration(
        manifest=manifest,
        profile_model=ThirdAdapterProfile,
        driver_attributes={"adapter_profile_model": ThirdAdapterProfile},
    )

    _validate_base_station_adapter_ids(
        {"Third Adapter": registration.driver_class}
    )


def test_registration_rejects_inherited_unimplemented_measurement_operation():
    registration = _third_adapter_registration(
        driver_attributes={
            "measure_base_station_window": BaseStationDriver.measure_base_station_window,
        }
    )

    with pytest.raises(ValueError, match="measure_base_station_window"):
        validate_base_station_adapter_registrations(
            {"Third Adapter": registration}
        )


@pytest.mark.parametrize(
    "driver_attributes, message",
    [
        ({"input_level_control_supported": True}, "input_level_control"),
        ({"rrc_reconfiguration_supported": True}, "rrc_reconfiguration"),
        ({"mac_throughput_configuration_supported": True}, "mac_throughput_config"),
        ({"measurement_window_cardinality": "single"}, "cardinality"),
    ],
)
def test_registration_rejects_driver_class_capability_drift(
    driver_attributes, message
):
    registration = _third_adapter_registration(
        driver_attributes=driver_attributes
    )

    with pytest.raises(ValueError, match=message):
        validate_base_station_adapter_registrations(
            {"Third Adapter": registration}
        )


@pytest.mark.parametrize(
    "operation, message",
    [
        ("input_level_control", "input_level_control"),
        ("rrc_reconfiguration", "rrc_reconfiguration"),
        ("mac_throughput_config", "mac_throughput_config"),
    ],
)
def test_registration_rejects_manifest_operation_without_class_support(
    operation, message
):
    manifest = BaseStationAdapterManifest.model_validate(
        _payload(
            adapter_id="third_adapter",
            model_name="Third Adapter",
            operations=[
                "identity",
                "config",
                "cell_attach",
                "measurement_window",
                operation,
            ],
            profile_requirement="not_applicable",
            profile_schema_version=None,
            profile_fields=[],
        )
    )
    registration = _third_adapter_registration(manifest=manifest)

    with pytest.raises(ValueError, match=message):
        validate_base_station_adapter_registrations(
            {"Third Adapter": registration}
        )


def test_registration_rejects_legacy_mirror_or_class_manifest_drift():
    registration = _third_adapter_registration()
    split_manifest = registration.manifest.model_copy(
        update={"rats": ("nr5g",)}
    )
    split_registration = BaseStationAdapterRegistration(
        manifest=split_manifest,
        driver_class=registration.driver_class,
        profile_model=None,
    )

    with pytest.raises(ValueError, match="rats"):
        validate_base_station_adapter_registrations(
            {"Third Adapter": split_registration}
        )


def test_registration_rejects_profile_schema_version_drift():
    class ProfileV2(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        schema_version: Literal[2]

    manifest = BaseStationAdapterManifest.model_validate(
        _payload(adapter_id="third_adapter", model_name="Third Adapter")
    )
    registration = _third_adapter_registration(
        manifest=manifest,
        profile_model=ProfileV2,
    )

    with pytest.raises(ValueError, match="profile_schema_version"):
        validate_base_station_adapter_registrations(
            {"Third Adapter": registration}
        )


def test_registration_rejects_rat_accessor_override():
    registration = _third_adapter_registration(
        driver_attributes={
            "get_supported_technologies": lambda self: [RadioTechnology.NR5G]
        }
    )

    with pytest.raises(ValueError, match="get_supported_technologies"):
        validate_base_station_adapter_registrations(
            {"Third Adapter": registration}
        )
