from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.hal.base_station_compatibility import (
    BaseStationExecutionRequirements,
    build_compatibility_payload,
    build_measure_execution_requirements,
    build_measure_execution_requirements_from_configuration,
    evaluate_base_station_compatibility,
)
from app.hal.base_station_manifest import BaseStationMacProfileCapability
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver


def _lte_configuration() -> dict:
    return {
        "component_carriers": [
            {
                "radio_technology": "lte",
                "frequency_hz": 1_842_500_000.0,
                "bandwidth_mhz": 20.0,
                "subcarrier_spacing_khz": None,
                "band": "B3",
                "duplex": "fdd",
                "lte_dl_earfcn": 1575,
                "lte_transmission_mode": "TM3",
                "role": "pcell",
            }
        ],
        "mimo_layers": 2,
        "theoretical_peak_throughput_mbps": None,
    }


def test_registered_manifests_declare_one_exact_mac_profile_acceptance():
    assert [
        item.model_dump(mode="json")
        for item in RealUxmDriver.adapter_manifest.mac_profiles
    ] == [
        {
            "kind": "nr_throughput",
            "profile_version": 1,
            "rat": "nr5g",
            "source_reference": (
                "Instrument_API_Doc/Keysight UXM NR SCPI/"
                "5G_NR_Test_Application_SCPI_Reference.zip"
            ),
        }
    ]
    assert [
        item.model_dump(mode="json")
        for item in RealCmw500Driver.adapter_manifest.mac_profiles
    ] == [
        {
            "kind": "lte_rmc",
            "profile_version": 1,
            "rat": "lte",
            "source_reference": (
                "Instrument_API_Doc/R&S CMW500/"
                "CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
            ),
        }
    ]


def test_saved_configuration_freezes_profile_into_requirements_digest():
    nr = build_measure_execution_requirements_from_configuration({})
    lte = build_measure_execution_requirements_from_configuration(
        _lte_configuration()
    )

    assert nr.mac_profile is not None
    assert nr.mac_profile.profile.kind == "nr_throughput"
    assert lte.mac_profile is not None
    assert lte.mac_profile.profile.kind == "lte_rmc"
    assert nr.digest != build_measure_execution_requirements("nr5g").digest


@pytest.mark.parametrize(
    ("configuration", "accepted", "rejected"),
    [
        ({}, RealUxmDriver.adapter_manifest, RealCmw500Driver.adapter_manifest),
        (
            _lte_configuration(),
            RealCmw500Driver.adapter_manifest,
            RealUxmDriver.adapter_manifest,
        ),
    ],
)
def test_evaluator_accepts_only_manifest_declared_profile(
    configuration, accepted, rejected
):
    requirements = build_measure_execution_requirements_from_configuration(
        configuration
    )

    assert evaluate_base_station_compatibility(requirements, accepted).compatible
    verdict = evaluate_base_station_compatibility(requirements, rejected)
    assert verdict.compatible is False
    assert any("MAC profile" in reason for reason in verdict.reasons)


def test_evaluator_rejects_missing_or_drifted_manifest_profile_declaration():
    requirements = build_measure_execution_requirements_from_configuration({})
    manifest = RealUxmDriver.adapter_manifest

    missing = manifest.model_copy(update={"mac_profiles": ()})
    drifted = manifest.model_copy(
        update={
            "mac_profiles": (
                manifest.mac_profiles[0].model_copy(
                    update={"source_reference": "wrong-source"}
                ),
            )
        }
    )

    for candidate in (missing, drifted):
        verdict = evaluate_base_station_compatibility(requirements, candidate)
        assert verdict.compatible is False
        assert any("MAC profile" in reason for reason in verdict.reasons)


def test_manifest_profile_declaration_is_structured_and_consistent():
    with pytest.raises(ValidationError):
        BaseStationMacProfileCapability(
            kind="nr_throughput",
            profile_version=0,
            rat="nr5g",
            source_reference="manual",
        )
    with pytest.raises(ValidationError):
        BaseStationMacProfileCapability(
            kind="NR Throughput",
            profile_version=1,
            rat="nr5g",
            source_reference="manual",
        )
    with pytest.raises(ValidationError):
        BaseStationMacProfileCapability(
            kind="nr_throughput",
            profile_version=1,
            rat="nr5g",
            source_reference=" ",
        )


def test_no_adapter_stays_explicit_diagnostic_without_expanding_acceptance():
    requirements = build_measure_execution_requirements_from_configuration({})

    payload = build_compatibility_payload(requirements, None)

    assert payload["verdict"]["status"] == "no_adapter"
    assert payload["verdict"]["compatible"] is True
    assert (
        payload["requirements"]["mac_profile"]["profile"]["kind"]
        == "nr_throughput"
    )


def test_pre_p2_54_requirements_none_keeps_the_historical_digest():
    old_payload = {
        "schema_version": 1,
        "requested_rat": "nr5g",
        "required_operations": [
            "identity",
            "config",
            "cell_attach",
            "measurement_window",
            "safe_idle_release",
        ],
    }
    without_key = BaseStationExecutionRequirements.model_validate(old_payload)
    with_null = BaseStationExecutionRequirements.model_validate(
        {**old_payload, "mac_profile": None}
    )

    assert without_key.digest == with_null.digest
    assert "mac_profile" not in without_key.model_dump(
        mode="json", exclude_none=True
    )
