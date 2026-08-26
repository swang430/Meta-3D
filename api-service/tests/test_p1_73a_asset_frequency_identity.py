"""P1-73A: NR/LTE 频率身份不得共享无类型的 ARFCN 槽。"""

from __future__ import annotations

from app.hal.nr_arfcn import FrequencyIdentity
from app.services.mimo_ota.frequency_consistency import (
    CenterFrequencyObservation,
    ChannelFrequencyIdentity,
    check_frequency_consistency,
)


def test_lte_identity_keeps_rat_kind_band_and_earfcn() -> None:
    identity = ChannelFrequencyIdentity.from_lte_earfcn(
        band="B3",
        dl_earfcn=1575,
        bandwidth_mhz=20,
    )

    assert identity.radio_technology == "lte"
    assert identity.channel_kind == "lte_dl_earfcn"
    assert identity.band == "B3"
    assert identity.channel_number == 1575
    assert identity.center_freq_mhz == 1842.5
    assert "EARFCN 1575" in identity.describe()


def test_same_integer_channel_number_across_rat_is_not_equal() -> None:
    nr = ChannelFrequencyIdentity.from_nr_arfcn(
        nr_arfcn=1575,
        bandwidth_mhz=20,
    )
    lte = ChannelFrequencyIdentity.from_lte_earfcn(
        band="B3",
        dl_earfcn=1575,
        bandwidth_mhz=20,
    )

    assert nr != lte
    result = check_frequency_consistency(lte, {"SCD": nr})
    assert result.consistent is False
    assert result.mismatches[0].instrument == "SCD"


def test_legacy_frequency_identity_is_narrowly_translated_as_nr() -> None:
    legacy = FrequencyIdentity.from_center_freq_mhz(3500.0, 100.0)
    expected = ChannelFrequencyIdentity.from_nr_arfcn(
        nr_arfcn=legacy.center_arfcn,
        bandwidth_mhz=100.0,
    )

    result = check_frequency_consistency(expected, {"legacy UXM": legacy})
    assert result.consistent is True


def test_center_only_observation_compares_to_lte_center_without_inventing_rat() -> None:
    expected = ChannelFrequencyIdentity.from_lte_earfcn(
        band="B40",
        dl_earfcn=39150,
        bandwidth_mhz=20,
    )
    observed = CenterFrequencyObservation.from_center_freq_mhz(
        2350.0,
        source="F64 CALC:FILT:CENT:CH?",
    )

    result = check_frequency_consistency(expected, {"F64": observed})
    assert result.consistent is True
    assert result.fully_verified is False
    assert result.unverified == ["F64"]


def test_missing_base_station_identity_keeps_frequency_gate_unverified() -> None:
    expected = ChannelFrequencyIdentity.from_lte_earfcn(
        band="B3",
        dl_earfcn=1575,
        bandwidth_mhz=20,
    )

    result = check_frequency_consistency(
        expected,
        {"BaseStation": None, "F64": expected},
    )

    assert result.consistent is True
    assert result.fully_verified is False
    assert result.unverified == ["BaseStation"]
