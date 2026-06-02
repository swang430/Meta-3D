"""RealPropsimF64Driver.list_channel_models() — operator-curated model list.

CAICT 2026-05-13 verified that the F64's ATE Server doesn't expose MMEM
SCPI (``MMEM:CDIR?`` / ``MMEM:CAT?`` return ``-100,"ATE command not
supported"``) AND the FTP service is closed on the chamber's F64. We
can't dynamically discover .smu / .rtc files on the F64's local disk
right now. Stage 1: operator-curated list in
``InstrumentConnection.connection_params['available_channel_models']``.

These tests pin the normalisation behaviour of
``list_channel_models()`` — string vs dict entries, malformed entries,
empty config — so the GUI dropdown gets predictable data shapes
regardless of how the operator typed the JSON.
"""
from __future__ import annotations

import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver


# ---------------------------------------------------------------------------
# Driver factory — list_channel_models doesn't need a real VISA session.
# ---------------------------------------------------------------------------

def _driver(available=None) -> RealPropsimF64Driver:
    """Build a driver with an arbitrary ``available_channel_models`` config.
    No TCP / VISA setup — we only exercise the pure-Python normalisation
    path."""
    config = {"ip": "192.168.0.132", "port": 5025}
    if available is not None:
        config["available_channel_models"] = available
    return RealPropsimF64Driver("f64-test", config)


# ---------------------------------------------------------------------------
# Empty / missing config
# ---------------------------------------------------------------------------

class TestEmptyConfig:
    @pytest.mark.asyncio
    async def test_no_config_returns_empty_list(self):
        # Config silent on this key — most realistic for a fresh DB row.
        d = _driver()
        assert await d.list_channel_models() == []

    @pytest.mark.asyncio
    async def test_explicit_empty_list_returns_empty(self):
        d = _driver(available=[])
        assert await d.list_channel_models() == []

    @pytest.mark.asyncio
    async def test_explicit_none_returns_empty(self):
        # Config value ``None`` shouldn't crash on a `for entry in None` —
        # the constructor coerces falsy to [].
        d = _driver(available=None)
        # available_channel_models key absent path — same as TestEmpty above
        # but routed explicitly through the None branch.
        assert await d.list_channel_models() == []


# ---------------------------------------------------------------------------
# String-shape and dict-shape normalisation
# ---------------------------------------------------------------------------

class TestEntryNormalisation:
    @pytest.mark.asyncio
    async def test_bare_string_expands_to_full_dict(self):
        d = _driver(available=["CDL-A_UMi_2x2.smu"])
        items = await d.list_channel_models()
        assert items == [{
            "filename": "CDL-A_UMi_2x2.smu",
            "label": "CDL-A_UMi_2x2.smu",  # defaults to filename
            "description": None,
            "type": "smu",
            # 无频率 token (2x2 / UMi 不匹配) → None (P2-10 Step 1)
            "center_frequency_mhz": None,
            "nr_arfcn": None,
        }]

    @pytest.mark.asyncio
    async def test_full_dict_preserves_all_fields(self):
        d = _driver(available=[{
            "filename": "CDL-C_UMa_4x4.smu",
            "label": "5G NR UMa 4×4",
            "description": "3GPP TR 38.901 CDL-C profile",
        }])
        items = await d.list_channel_models()
        assert items == [{
            "filename": "CDL-C_UMa_4x4.smu",
            "label": "5G NR UMa 4×4",
            "description": "3GPP TR 38.901 CDL-C profile",
            "type": "smu",
            "center_frequency_mhz": None,  # 无频率 token
            "nr_arfcn": None,
        }]

    @pytest.mark.asyncio
    async def test_dict_without_label_falls_back_to_filename(self):
        d = _driver(available=[{"filename": "TDL-A.smu", "description": "tdl-a"}])
        items = await d.list_channel_models()
        assert items[0]["label"] == "TDL-A.smu"
        assert items[0]["description"] == "tdl-a"

    @pytest.mark.asyncio
    async def test_type_derived_from_extension(self):
        d = _driver(available=[
            "model.smu",
            "model.rtc",
            "model.asc",
            "no_extension_model",
            "weird.WeIrDCASE",
        ])
        items = await d.list_channel_models()
        types = [it["type"] for it in items]
        assert types == ["smu", "rtc", "asc", "unknown", "weirdcase"]


# ---------------------------------------------------------------------------
# Malformed entries — silent drop, not crash
# ---------------------------------------------------------------------------

class TestMalformedEntriesAreSilentlyDropped:
    """If an operator typos a config row, the GUI should still load —
    we filter bad rows out instead of 500-ing the endpoint."""

    @pytest.mark.asyncio
    async def test_dict_without_filename_dropped(self):
        d = _driver(available=[
            "good.smu",
            {"label": "no filename here"},
            {"filename": "also-good.smu"},
        ])
        items = await d.list_channel_models()
        names = [it["filename"] for it in items]
        assert names == ["good.smu", "also-good.smu"]

    @pytest.mark.asyncio
    async def test_non_string_filename_dropped(self):
        d = _driver(available=[
            {"filename": 42},
            {"filename": None},
            {"filename": "real.smu"},
        ])
        items = await d.list_channel_models()
        assert len(items) == 1
        assert items[0]["filename"] == "real.smu"

    @pytest.mark.asyncio
    async def test_non_dict_non_str_entries_dropped(self):
        d = _driver(available=[
            42,
            ["nested", "list"],
            None,
            "real.smu",
        ])
        items = await d.list_channel_models()
        assert len(items) == 1
        assert items[0]["filename"] == "real.smu"

    @pytest.mark.asyncio
    async def test_empty_string_filename_dropped(self):
        d = _driver(available=["", "real.smu"])
        items = await d.list_channel_models()
        assert [it["filename"] for it in items] == ["real.smu"]


# ---------------------------------------------------------------------------
# Mixed real-world payload — same shape the API endpoint serialises
# ---------------------------------------------------------------------------

class TestMixedRealisticPayload:
    @pytest.mark.asyncio
    async def test_six_seeded_entries_yield_three_valid(self):
        """Mirrors the seed payload used in API live-fire verification:
        3 valid + 3 malformed → 3 items out, in order."""
        d = _driver(available=[
            "CDL-A_UMi_2x2.smu",
            {
                "filename": "CDL-C_UMa_4x4.smu",
                "label": "5G NR Urban Macro 4x4 (CDL-C)",
                "description": "3GPP TR 38.901 CDL-C profile, 4×4 MIMO, UMa scenario",
            },
            {"filename": "TDL-A_Indoor_2x2.smu", "label": "5G NR Indoor 2x2 (TDL-A)"},
            {"label": "no filename, should be dropped"},
            "",
            42,
        ])
        items = await d.list_channel_models()
        assert [it["filename"] for it in items] == [
            "CDL-A_UMi_2x2.smu",
            "CDL-C_UMa_4x4.smu",
            "TDL-A_Indoor_2x2.smu",
        ]
        # Spot-check the rich middle entry.
        assert items[1]["label"] == "5G NR Urban Macro 4x4 (CDL-C)"
        assert items[1]["description"].startswith("3GPP TR 38.901")


# ---------------------------------------------------------------------------
# P2-10 Step 1 — 资产盘点频率元数据 (center_frequency_mhz + nr_arfcn)
# ---------------------------------------------------------------------------

class TestFrequencyMetadata:
    @pytest.mark.asyncio
    async def test_freq_token_parsed_from_filename(self):
        # ".._3600M.smu" → 3600 MHz → ARFCN 640000 (服务 emulation_file 频率匹配)
        d = _driver(available=["3GPP_FR1_OTA_CDLC_UMa_3600M.smu"])
        item = (await d.list_channel_models())[0]
        assert item["center_frequency_mhz"] == 3600.0
        assert item["nr_arfcn"] == 640000

    @pytest.mark.asyncio
    async def test_no_freq_token_is_none(self):
        d = _driver(available=["CDL-A_UMi_2x2.smu"])  # 无 _<数字>M token
        item = (await d.list_channel_models())[0]
        assert item["center_frequency_mhz"] is None
        assert item["nr_arfcn"] is None

    @pytest.mark.asyncio
    async def test_explicit_config_center_overrides_filename(self):
        # operator 在 config 显式给 center_frequency_mhz → 优先于文件名解析
        d = _driver(available=[{
            "filename": "reusable_3600M.smu",  # 文件名说 3600
            "center_frequency_mhz": 3500,       # 但 operator 声明实际跑 3500
        }])
        item = (await d.list_channel_models())[0]
        assert item["center_frequency_mhz"] == 3500.0
        assert item["nr_arfcn"] == 633333  # 3500 MHz 的 ARFCN, 非 3600 的


# ---------------------------------------------------------------------------
# Base class contract — non-F64 channel emulators get empty list
# (regression guard: don't accidentally break MockChannelEmulator)
# ---------------------------------------------------------------------------

class TestBaseClassDefault:
    @pytest.mark.asyncio
    async def test_mock_channel_emulator_returns_empty_list(self):
        """MockChannelEmulator inherits ChannelEmulatorDriver.list_channel_models
        which is the no-op default — empty list, no crash. This keeps the
        GUI dropdown predictable when the lab is on mock HAL."""
        from app.hal.channel_emulator import MockChannelEmulator
        mock = MockChannelEmulator("mock-ce", {})
        assert await mock.list_channel_models() == []
