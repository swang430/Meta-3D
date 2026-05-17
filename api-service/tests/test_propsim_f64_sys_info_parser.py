"""P3-4 — structured parse of PROPSIM F64 ``SYST:INFO?`` response.

Pre-P3-4 the F64 driver's ``connect()`` only extracted ``parts[1]``
(channel_count) from the comma-separated response and threw the rest
away. The fixture strings in ``test_f64_license_probe.py`` show the
real shape carries firmware version, band coverage, and license
keywords — useful for the readiness log + on-site triage.

These tests pin:
- positional field extraction (product_family, channel_count,
  signal_type, firmware_version, secondary_count)
- labeled field extraction (``Band: ...``)
- "tail" tokens collected into ``extra_tokens`` for forward-compat
- defensive shapes: degraded inputs, missing fields, malformed
  numerics, empty/None inputs — none must raise
"""
from __future__ import annotations

import pytest

from app.hal.propsim_f64 import F64SysInfo, parse_f64_sys_info


# Canonical full-shape response from the inline driver comment +
# test_f64_license_probe.py fixtures. Locked here so any future format
# change has to update this constant first.
FULL_SAMPLE = (
    "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,"
    "Interference Generator,Calibration User Alignment"
)


class TestPositionalExtraction:
    """Positions [0..4] are positional and unlabeled — pin them
    individually so a future firmware drift on any one position
    surfaces a specific failing assert (vs a single fixture compare
    that's hard to diff)."""

    def test_product_family(self):
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.product_family == "PROPSIM F64"

    def test_channel_count(self):
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.channel_count == 64

    def test_signal_type(self):
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.signal_type == "RF"

    def test_firmware_version(self):
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.firmware_version == "v1.0"

    def test_secondary_count(self):
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.secondary_count == 16


class TestLabeledExtraction:
    """Position 5+ has labeled fields like ``Band: ...`` interleaved
    with bare license keywords. Pin that the label is stripped + the
    payload extracted."""

    def test_band_label_extracted(self):
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.band_label == "450MHz - 3000MHz"

    def test_band_label_case_insensitive(self):
        # Older firmware uses lower-case "band:"; the comment block in
        # propsim_f64.py mentions "capitalisation has drifted". Pin
        # that both pass.
        info = parse_f64_sys_info(
            "PROPSIM F64,64,RF,v1.0,16,band: 450MHz - 3000MHz"
        )
        assert info.band_label == "450MHz - 3000MHz"

    def test_band_label_missing(self):
        info = parse_f64_sys_info("PROPSIM F64,64,RF,v1.0,16")
        assert info.band_label is None

    def test_tail_tokens_go_to_extra(self):
        """Non-labeled trailing tokens (license keywords from older
        firmware before *OPT? worked) get bucketed for forward-compat —
        readiness report can render them as-is."""
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.extra_tokens == [
            "Interference Generator",
            "Calibration User Alignment",
        ]


class TestDefensiveShapes:
    """Defensive against firmware revs that drop trailing fields or
    return weird payloads. Parser must never raise — F64 connect()
    falls back to a default channel_count but the rest of the
    bring-up must continue."""

    def test_empty_string_returns_empty_dataclass(self):
        info = parse_f64_sys_info("")
        assert info == F64SysInfo(raw="")
        # All fields default-None / empty list. Nothing raises.

    def test_none_input_returns_empty_dataclass(self):
        info = parse_f64_sys_info(None)
        assert info.raw == ""
        assert info.product_family is None
        assert info.channel_count is None

    def test_whitespace_only_returns_empty(self):
        info = parse_f64_sys_info("   ,  ,   ")
        # Stripped + filtered to nothing.
        assert info.product_family is None
        assert info.channel_count is None

    def test_skinny_response_three_fields_only(self):
        """Shortest fixture seen in test_f64_license_probe.py — older
        firmware truncates. Must extract what's present, default the rest."""
        info = parse_f64_sys_info("PROPSIM F64,64,RF")
        assert info.product_family == "PROPSIM F64"
        assert info.channel_count == 64
        assert info.signal_type == "RF"
        assert info.firmware_version is None
        assert info.secondary_count is None
        assert info.band_label is None
        assert info.extra_tokens == []

    def test_nonint_channel_count_falls_back_to_none(self):
        """If position [1] is unexpectedly non-numeric (firmware bug,
        truncated response, etc.), channel_count stays None — driver
        connect() falls back to its 64 default rather than raising."""
        info = parse_f64_sys_info("PROPSIM F64,NULL,RF,v1.0,16")
        assert info.channel_count is None
        # Other fields still parse positionally — partial recovery.
        assert info.signal_type == "RF"
        assert info.firmware_version == "v1.0"

    def test_nonint_secondary_count_falls_back_to_none(self):
        info = parse_f64_sys_info("PROPSIM F64,64,RF,v1.0,XXXX")
        assert info.secondary_count is None
        # Channel count up to position [1] unaffected.
        assert info.channel_count == 64

    def test_extra_whitespace_around_commas_normalized(self):
        # Some VISA layers pad with spaces; strip + filter handles it.
        info = parse_f64_sys_info("  PROPSIM F64 , 64 , RF , v1.0 ")
        assert info.product_family == "PROPSIM F64"
        assert info.channel_count == 64
        assert info.signal_type == "RF"
        assert info.firmware_version == "v1.0"

    def test_raw_preserved_for_audit(self):
        """Raw response stays in the dataclass so the readiness log
        and audit trail keep the unparsed source for diagnosis even
        when the parser silently drops a field."""
        info = parse_f64_sys_info(FULL_SAMPLE)
        assert info.raw == FULL_SAMPLE


class TestRoundTripFixtures:
    """Pin all the fixture strings the F64 license-probe tests use so
    a future format change forces a coordinated update across both
    test suites (rather than one drifting silently)."""

    @pytest.mark.parametrize(
        "raw,expected_channels,expected_fw",
        [
            (
                "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,Interference Generator,Calibration User Alignment",
                64, "v1.0",
            ),
            (
                "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz",
                64, "v1.0",
            ),
            ("PROPSIM F64,64,RF,v1.0,16", 64, "v1.0"),
            ("PROPSIM F64,64,RF", 64, None),
        ],
    )
    def test_known_fixture_parses(self, raw, expected_channels, expected_fw):
        info = parse_f64_sys_info(raw)
        assert info.channel_count == expected_channels
        assert info.firmware_version == expected_fw
        assert info.product_family == "PROPSIM F64"
