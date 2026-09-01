from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.hal.base_station_mac_profile import (
    FrozenMacTestProfile,
    LteRmcMacTestProfileV1,
    MacMetricRequirement,
    MacStatisticalWindow,
    NrMacTestProfileV1,
)
from app.schemas.mimo_ota.config import (
    MIMOOTAConfiguration,
    canonicalize_mimo_ota_configuration_payload,
)


def _nr_profile(**updates) -> NrMacTestProfileV1:
    payload = {
        "schema_version": 1,
        "kind": "nr_throughput",
        "profile_version": 1,
        "rat": "nr5g",
        "test_intent": "downlink_throughput",
        "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 5000},
        "metric_requirements": [
            {"key": "dl_throughput_mbps", "scope": "pcell"}
        ],
        "rb_allocation": "all",
        "scheduler_algorithm": "full_throughput",
        "mcs": 28,
        "enable_amc": False,
        "tdd_pattern": "DDDDDDDSUU",
        "tdd_period": "5MS",
        "harq_max_trans": 4,
        "harq_processes": 16,
        "subcarrier_spacing_khz": 30,
        "csi_rs_ports": 4,
        "source_reference": (
            "Instrument_API_Doc/Keysight UXM NR SCPI/"
            "5G_NR_Test_Application_SCPI_Reference.zip"
        ),
    }
    payload.update(updates)
    return NrMacTestProfileV1.model_validate(payload)


def _lte_profile(**updates) -> LteRmcMacTestProfileV1:
    payload = {
        "schema_version": 1,
        "kind": "lte_rmc",
        "profile_version": 1,
        "rat": "lte",
        "test_intent": "downlink_throughput",
        "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 5000},
        "metric_requirements": [
            {"key": "dl_throughput_mbps", "scope": "pcell"},
            {"key": "dl_bler_percent", "scope": "pcell"},
        ],
        "scheduling_mode": "rmc",
        "resource_allocation": "full",
        "enable_amc": False,
        "duplex": "fdd",
        "transmission_mode": "TM3",
        "source_reference": (
            "Instrument_API_Doc/R&S CMW500/"
            "CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
        ),
    }
    payload.update(updates)
    return LteRmcMacTestProfileV1.model_validate(payload)


def _lte_pcell() -> dict:
    return {
        "radio_technology": "lte",
        "frequency_hz": 1_815_000_000.0,
        "bandwidth_mhz": 20.0,
        "subcarrier_spacing_khz": None,
        "band": "B3",
        "duplex": "fdd",
        "lte_dl_earfcn": 1300,
        "lte_transmission_mode": "TM3",
        "role": "pcell",
    }


def test_profile_models_are_frozen_and_digest_covers_nested_truth():
    profile = _nr_profile()
    frozen = FrozenMacTestProfile.freeze(profile)

    assert frozen.profile.kind == "nr_throughput"
    assert frozen.profile_digest
    assert frozen == FrozenMacTestProfile.model_validate(frozen.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        frozen.profile.mcs = 10

    changed = FrozenMacTestProfile.freeze(
        profile.model_copy(
            update={
                "statistical_window": MacStatisticalWindow(
                    unit="subframes", count=6000
                )
            }
        )
    )
    assert changed.profile_digest != frozen.profile_digest


def test_metric_requirements_are_nonempty_unique_stable_keys():
    with pytest.raises(ValidationError):
        _nr_profile(metric_requirements=[])
    with pytest.raises(ValidationError):
        _nr_profile(
            metric_requirements=[
                MacMetricRequirement(key="dl_throughput_mbps", scope="pcell"),
                MacMetricRequirement(key="dl_throughput_mbps", scope="pcell"),
            ]
        )
    with pytest.raises(ValidationError):
        _nr_profile(
            metric_requirements=[
                {"key": "fabricated_metric", "scope": "pcell"}
            ]
        )
    with pytest.raises(ValidationError):
        _lte_profile(
            metric_requirements=[
                {"key": "dl_throughput_mbps", "scope": "pcell"}
            ]
        )


def test_nr_and_lte_profiles_reject_each_others_fields():
    with pytest.raises(ValidationError):
        _nr_profile(transmission_mode="TM3")
    with pytest.raises(ValidationError):
        _lte_profile(mcs=28)
    with pytest.raises(ValidationError):
        _lte_profile(tdd_pattern="DDDDDDDSUU")
    with pytest.raises(ValidationError):
        _lte_profile(harq_processes=16)
    with pytest.raises(ValidationError):
        _lte_profile(subcarrier_spacing_khz=30)
    with pytest.raises(ValidationError):
        _lte_profile(csi_rs_ports=4)


def test_lte_v1_is_the_existing_narrow_fdd_fixed_rmc_shape():
    assert _lte_profile().model_dump(mode="json") == {
        "schema_version": 1,
        "kind": "lte_rmc",
        "profile_version": 1,
        "rat": "lte",
        "test_intent": "downlink_throughput",
        "mimo_layers": 2,
        "statistical_window": {"unit": "subframes", "count": 5000},
        "metric_requirements": [
            {"key": "dl_throughput_mbps", "scope": "pcell"},
            {"key": "dl_bler_percent", "scope": "pcell"},
        ],
        "scheduling_mode": "rmc",
        "resource_allocation": "full",
        "enable_amc": False,
        "duplex": "fdd",
        "transmission_mode": "TM3",
        "source_reference": (
            "Instrument_API_Doc/R&S CMW500/"
            "CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
        ),
    }
    with pytest.raises(ValidationError):
        _lte_profile(enable_amc=True)
    with pytest.raises(ValidationError):
        _lte_profile(duplex="tdd")
    with pytest.raises(ValidationError):
        _lte_profile(mimo_layers=4)


def test_legacy_nr_flat_fields_migrate_to_one_canonical_profile():
    raw = {
        "mimo_layers": 4,
        "mcs": 19,
        "enable_amc": False,
        "tdd_pattern": "DDDDDDDSUU",
        "tdd_period": "5MS",
        "harq_max_trans": 3,
        "harq_processes": 8,
        "stat_count": 6000,
        "sched_algo": "FULLBUFFER",
        "csi_rs_ports": 8,
    }

    config = MIMOOTAConfiguration.model_validate(raw)

    assert config.mac_profile.profile.kind == "nr_throughput"
    assert config.mac_profile.profile.mimo_layers == 4
    assert config.mac_profile.profile.mcs == 19
    assert config.mac_profile.profile.harq_processes == 8
    assert config.mac_profile.profile.statistical_window.count == 6000
    assert config.mac_profile.profile.scheduler_algorithm == "full_throughput"
    assert config.mac_profile.profile.csi_rs_ports == 8

    canonical = canonicalize_mimo_ota_configuration_payload(raw)
    assert "mac_profile" in canonical
    for legacy in (
        "mcs",
        "enable_amc",
        "tdd_pattern",
        "tdd_period",
        "harq_max_trans",
        "harq_processes",
        "stat_count",
        "sched_algo",
        "csi_rs_ports",
    ):
        assert legacy not in canonical


def test_explicit_profile_rejects_conflicting_legacy_mac_value():
    canonical = canonicalize_mimo_ota_configuration_payload({"mcs": 28})
    canonical["mcs"] = 21

    with pytest.raises(ValidationError, match="mac_profile.*mcs"):
        MIMOOTAConfiguration.model_validate(canonical)


def test_explicit_lte_profile_rejects_nr_only_legacy_mac_value():
    canonical = canonicalize_mimo_ota_configuration_payload(
        {
            "component_carriers": [_lte_pcell()],
            "mimo_layers": 2,
        }
    )
    canonical["mcs"] = 28

    with pytest.raises(ValidationError, match="mac_profile.*mcs"):
        MIMOOTAConfiguration.model_validate(canonical)


def test_legacy_lte_migrates_without_nr_only_fields():
    raw = {
        "component_carriers": [_lte_pcell()],
        "mimo_layers": 2,
        "enable_amc": False,
        "stat_count": 10_000,
        # Historical universal fields may exist but are not LTE semantics.
        "mcs": 28,
        "tdd_pattern": "DDDDDDDSUU",
        "harq_processes": 16,
        "csi_rs_ports": 4,
    }

    profile = MIMOOTAConfiguration.model_validate(raw).mac_profile.profile

    assert profile.kind == "lte_rmc"
    assert profile.statistical_window.count == 10_000
    dumped = profile.model_dump(mode="json")
    for nr_only in (
        "mcs",
        "tdd_pattern",
        "harq_processes",
        "subcarrier_spacing_khz",
        "csi_rs_ports",
    ):
        assert nr_only not in dumped


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update({"rat": "lte"}),
        lambda p: p.update({"mimo_layers": 4}),
        lambda p: p.update({"subcarrier_spacing_khz": 15}),
    ],
)
def test_explicit_nr_profile_must_match_pcell_and_common_intent(mutate):
    profile = _nr_profile().model_dump(mode="json")
    mutate(profile)
    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate(
            {
                "mimo_layers": 2,
                "subcarrier_spacing_khz": 30,
                "mac_profile": FrozenMacTestProfile.freeze(
                    NrMacTestProfileV1.model_validate(profile)
                ).model_dump(mode="json"),
            }
        )


def test_explicit_lte_profile_must_match_pcell_tm_and_duplex():
    base = {
        "component_carriers": [_lte_pcell()],
        "mimo_layers": 2,
    }
    for update in (
        {"transmission_mode": "TM4"},
        {"duplex": "tdd"},
        {"mimo_layers": 1},
    ):
        with pytest.raises(ValidationError):
            profile = _lte_profile().model_copy(update=update)
            raw = deepcopy(base)
            raw["mac_profile"] = FrozenMacTestProfile.freeze(profile).model_dump(
                mode="json"
            )
            MIMOOTAConfiguration.model_validate(raw)


def test_explicit_profile_digest_tampering_is_rejected():
    frozen = FrozenMacTestProfile.freeze(_nr_profile()).model_dump(mode="json")
    frozen["profile_digest"] = "0" * 64

    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate({"mac_profile": frozen})
