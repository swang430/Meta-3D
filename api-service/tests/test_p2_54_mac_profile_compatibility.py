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
    """守 profile **身份**（kind/version/rat/evidence/source）。

    P2-55 起 profile 还带 ``dimensions`` 取值域矩阵，那部分内容长且会随取证增长，
    由 ``test_p2_55_capability_matrix.py`` 逐值单独守 —— 但**这里仍然断言两个
    adapter 各自有没有维度**，否则「矩阵整个消失」或「挂到错误的 adapter 上」
    会从这道门底下漏过去。
    """
    assert [
        item.model_dump(mode="json", exclude={"dimensions"})
        for item in RealUxmDriver.adapter_manifest.mac_profiles
    ] == [
        {
            "kind": "nr_throughput",
            "profile_version": 1,
            "rat": "nr5g",
            "application_evidence": "command_error_queue",
            "source_reference": (
                "Instrument_API_Doc/Keysight UXM NR SCPI/"
                "5G_NR_Test_Application_SCPI_Reference.zip"
            ),
        }
    ]
    # UXM 侧本片不声明维度矩阵（P2-55 只做 CMW500 LTE FDD）
    assert all(
        item.dimensions == ()
        for item in RealUxmDriver.adapter_manifest.mac_profiles
    )

    assert [
        item.model_dump(mode="json", exclude={"dimensions"})
        for item in RealCmw500Driver.adapter_manifest.mac_profiles
    ] == [
        {
            "kind": "lte_rmc",
            "profile_version": 1,
            "rat": "lte",
            "application_evidence": "authoritative_readback",
            "source_reference": (
                "Instrument_API_Doc/R&S CMW500/"
                "CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
            ),
        }
    ]
    # CMW500 侧必须有矩阵，且维度名恰好是已取证的那些
    # （P2-55 取证 FDD 侧两个；P2-56 追加 LTE TDD 侧四个）
    assert [
        dimension.dimension
        for item in RealCmw500Driver.adapter_manifest.mac_profiles
        for dimension in item.dimensions
    ] == [
        "transmission_mode",
        "mimo_layers",
        "duplex",
        "uldl_configuration",
        "special_subframe",
        "rmc_version",
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
            application_evidence="command_error_queue",
        )
    with pytest.raises(ValidationError):
        BaseStationMacProfileCapability(
            kind="NR Throughput",
            profile_version=1,
            rat="nr5g",
            source_reference="manual",
            application_evidence="command_error_queue",
        )
    with pytest.raises(ValidationError):
        BaseStationMacProfileCapability(
            kind="nr_throughput",
            profile_version=1,
            rat="nr5g",
            source_reference=" ",
            application_evidence="command_error_queue",
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
