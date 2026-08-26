"""P2-12 slice 1: 标准信道文件命名契约 测试.

钉死: 我们拥有的 config↔标准名 双向 (round-trip 精确) + Step 1 解析器降为 cross-check
(标准名精确反解优先, 厂商名松解析退回, 文件名说谎 → 不一致 fail-loud)。
"""
from __future__ import annotations

import pytest

from app.services.mimo_ota.channel_naming import (
    ChannelNameFreqCheck,
    StandardChannelName,
    check_channel_filename_freq,
    format_standard_channel_filename,
    parse_standard_channel_filename,
)


def _scn(**over) -> StandardChannelName:
    base = dict(
        band="N78", arfcn=640000, bandwidth_mhz=100, model="CDLC",
        scenario="UMa", mimo="4x4", polarization="DP", version=3,
    )
    base.update(over)
    return StandardChannelName(**base)


def _lte_scn(**over) -> StandardChannelName:
    base = dict(
        radio_technology="lte", channel_kind="lte_dl_earfcn",
        band="B3", arfcn=None, lte_dl_earfcn=1575,
        bandwidth_mhz=20, model="TDLA", scenario="Urban",
        mimo="2x2", polarization="DP", version=1,
    )
    base.update(over)
    return StandardChannelName(**base)


class TestFormat:
    def test_basic(self):
        assert (
            format_standard_channel_filename(_scn())
            == "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu"
        )

    def test_pol_and_version_in_name(self):
        n = format_standard_channel_filename(_scn(polarization="V", version=12))
        assert "_V_v12.smu" in n

    def test_field_with_underscore_rejected(self):
        # 下划线是分隔符, 字段含它会让反解错位 → 早失败
        with pytest.raises(ValueError):
            format_standard_channel_filename(_scn(model="CDL_C"))

    def test_field_with_hyphen_rejected(self):
        with pytest.raises(ValueError):
            format_standard_channel_filename(_scn(model="CDL-C"))

    def test_non_positive_int_rejected(self):
        with pytest.raises(ValueError):
            format_standard_channel_filename(_scn(version=0))

    def test_lte_name_has_explicit_rat_and_channel_kind(self):
        assert format_standard_channel_filename(_lte_scn()) == (
            "MF_LTE_B3_EARFCN1575_BW20_TDLA_Urban_2x2_DP_v1.smu"
        )

    def test_lte_number_cannot_use_nr_arfcn_slot(self):
        with pytest.raises(ValueError, match="arfcn"):
            format_standard_channel_filename(_lte_scn(arfcn=1575))


class TestRoundTrip:
    def test_format_parse_format_exact(self):
        scn = _scn(band="N41", arfcn=518000, bandwidth_mhz=40,
                   model="TDLA", scenario="UMi", mimo="2x2",
                   polarization="V", version=1)
        name = format_standard_channel_filename(scn)
        back = parse_standard_channel_filename(name)
        assert back == scn  # 两个方向都我们拥有 → 反解必然精确

    def test_lte_format_parse_format_exact(self):
        scn = _lte_scn()
        name = format_standard_channel_filename(scn)
        assert parse_standard_channel_filename(name) == scn


class TestParse:
    def test_standard_name_parsed(self):
        scn = parse_standard_channel_filename("MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu")
        assert scn is not None
        assert scn.arfcn == 640000 and scn.polarization == "DP" and scn.version == 3

    def test_strips_path(self):
        p = r"D:\Std Channels\MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu"
        assert parse_standard_channel_filename(p).arfcn == 640000

    def test_vendor_name_is_none(self):
        # 厂商原始 / 非本标准格式 → None (不强行反解)
        assert parse_standard_channel_filename("3GPP_FR1_OTA_CDLC_UMa_3600M.smu") is None

    def test_none_empty(self):
        assert parse_standard_channel_filename(None) is None
        assert parse_standard_channel_filename("") is None


class TestCrossCheck:
    def test_standard_name_match(self):
        # 标准名精确反解 ARFCN == 声明 → 一致
        r = check_channel_filename_freq(
            "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu", declared_arfcn=640000
        )
        assert r.consistent and r.source == "standard"

    def test_standard_name_mismatch_fails(self):
        # 标准名说 633333 (3500) 但 SCD 声明 640000 (3600) → 不一致 (文件名说谎)
        r = check_channel_filename_freq(
            "MF_N78_633333_BW100_CDLC_UMa_4x4_DP_v1.smu", declared_arfcn=640000
        )
        assert not r.consistent and r.actual_arfcn == 633333
        assert "≠" in (r.failure_reason() or "")

    def test_vendor_name_loose_match(self):
        # 厂商名走 Step 1 松解析: 3600M → 640000 == 声明 → 一致 (source=loose)
        r = check_channel_filename_freq(
            "3GPP_FR1_OTA_CDLC_UMa_3600M.smu", declared_arfcn=640000
        )
        assert r.consistent and r.source == "loose" and r.actual_arfcn == 640000

    def test_vendor_name_loose_mismatch(self):
        # 厂商 3600M 但 SCD 声明 3500 (633333) → 不一致 (关联错文件)
        r = check_channel_filename_freq(
            "3GPP_FR1_OTA_CDLC_UMa_3600M.smu", declared_arfcn=633333
        )
        assert not r.consistent and r.source == "loose"

    def test_unparseable_skips(self):
        # 文件名无频率 token → 无从核对 → skip (consistent=True, source=unparseable)
        r = check_channel_filename_freq("CDL-A_UMi_2x2.smu", declared_arfcn=640000)
        assert r.consistent and r.source == "unparseable" and r.actual_arfcn is None
