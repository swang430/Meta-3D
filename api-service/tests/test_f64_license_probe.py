"""F64 license probe — feature-probe replacement for ``*OPT?``.

Confirmed CAICT 2026-05-13 (memory ``project_f64_ate_server_capabilities``):
F64's ATE Server answers ``-100,"ATE command not supported"`` to
``*OPT?``. The base class default therefore got no options and the
``has_interference_generator`` flag silently stayed False even on units
where the K01 license was actually installed.

The fix replaces ``*OPT?`` with two complementary probes:
  (a) SYST:INFO? keyword scan — SYST:INFO? is known to work on F64.
  (b) Soft feature probes — one read-only SCPI per option. If the
      controller answers, the gating license is installed; if it NAKs,
      treated as absent.

These tests pin the dispatch contract without needing a real F64.
``_query`` is monkey-patched to return canned responses per command.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.hal.propsim_f64 import (
    INTERFERENCE_GEN_OPTION_TOKENS,
    RealPropsimF64Driver,
    _is_unsupported_error_payload,
)


def _make_driver_with_query_table(query_table: Dict[str, Any]) -> RealPropsimF64Driver:
    """Build an F64 driver and hijack ``_query`` to return canned answers.

    ``query_table`` maps command strings to either:
      - a response string (returned as-is)
      - an exception instance (raised)
      - None (raises a generic Exception — used to simulate NAK)
    Commands not in the table raise (so the test fails noisily on
    unexpected SCPI traffic — better than silently passing).
    """
    d = RealPropsimF64Driver(
        instrument_id="f64-license-test",
        config={"ip": "192.168.0.100", "port": 5025},
    )

    async def fake_query(cmd: str, **_kwargs) -> str:
        if cmd not in query_table:
            raise AssertionError(f"unexpected SCPI: {cmd!r}")
        spec = query_table[cmd]
        if isinstance(spec, BaseException):
            raise spec
        if spec is None:
            raise RuntimeError(f"simulated NAK for {cmd}")
        return spec

    d._query = fake_query  # type: ignore[assignment]
    return d


# ---------------------------------------------------------------------------
# SYST:INFO? scan
# ---------------------------------------------------------------------------

class TestSystInfoKeywordScan:
    @pytest.mark.asyncio
    async def test_interference_keyword_promotes_int_gen(self):
        """Realistic SYST:INFO? format with an 'interference' substring
        is recognised — even without a successful soft probe."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,Interference Generator,Calibration User Alignment",
            # Soft probes both NAK — must NOT remove tokens already
            # found by the keyword scan.
            "OUTPut:INTERFerence:LIST?": None,
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        assert "INT-GEN" in opts
        assert "USER-ALIGN" in opts

    @pytest.mark.asyncio
    async def test_no_keywords_means_no_tokens_from_scan_alone(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz",
            "OUTPut:INTERFerence:LIST?": None,
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        assert opts == []

    @pytest.mark.asyncio
    async def test_syst_info_failure_does_not_block_probes(self):
        """If SYST:INFO? itself fails, the soft probes still run —
        startup must not depend on any one source."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": RuntimeError("simulated SYST:INFO? failure"),
            "OUTPut:INTERFerence:LIST?": "",  # ACK with empty payload
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        # Probe succeeded → INT-GEN detected even with SYST:INFO? failure.
        assert "INT-GEN" in opts
        # User align probe NAKed → absent.
        assert "USER-ALIGN" not in opts


# ---------------------------------------------------------------------------
# Soft feature probes
# ---------------------------------------------------------------------------

class TestSoftFeatureProbes:
    @pytest.mark.asyncio
    async def test_probe_ack_promotes_option(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,v1.0,16",
            # Both probes ACK → both options installed.
            "OUTPut:INTERFerence:LIST?": "ce_sa_cal_tone,interferer_2",
            "SYSTem:CALibration:USER:LIST?": "lab_alignment_v1",
        })
        opts = await d._probe_installed_options()
        assert set(opts) == {"INT-GEN", "USER-ALIGN"}

    @pytest.mark.asyncio
    async def test_empty_ack_still_counts_as_license_present(self):
        """ACK with empty payload ≠ 'command not supported'. Probe must
        recognise '' as success (license present, list just happens to
        be empty)."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": "",
            "SYSTem:CALibration:USER:LIST?": "",
        })
        opts = await d._probe_installed_options()
        assert set(opts) == {"INT-GEN", "USER-ALIGN"}

    @pytest.mark.asyncio
    async def test_probe_nak_keeps_option_out(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": RuntimeError("simulated -100"),
            "SYSTem:CALibration:USER:LIST?": RuntimeError("simulated -100"),
        })
        opts = await d._probe_installed_options()
        assert opts == []

    @pytest.mark.asyncio
    async def test_mixed_result_reports_only_the_working_one(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": "",         # K01 installed
            "SYSTem:CALibration:USER:LIST?": None,    # user-align missing
        })
        opts = await d._probe_installed_options()
        assert opts == ["INT-GEN"]


# ---------------------------------------------------------------------------
# Idempotence — keyword + probe agreeing doesn't double-list
# ---------------------------------------------------------------------------

class TestNoDuplicates:
    @pytest.mark.asyncio
    async def test_keyword_and_probe_both_find_same_token_emits_once(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,Interference Generator",
            "OUTPut:INTERFerence:LIST?": "",  # ALSO acks
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        assert opts.count("INT-GEN") == 1


# ---------------------------------------------------------------------------
# Integration with _apply_discovered_capabilities — the whole reason this
# matters in production
# ---------------------------------------------------------------------------

class TestAppliesToHasFlag:
    @pytest.mark.asyncio
    async def test_int_gen_token_flips_has_interference_generator_true(self):
        """End-to-end intent of the probe: ``has_interference_generator``
        ends up True on a unit with the K01 license, without operator
        having to manually set ``config['has_interference_generator']``."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": "ce_sa_cal_tone",
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        await d._apply_discovered_capabilities(opts)
        assert d.has_interference_generator is True

    @pytest.mark.asyncio
    async def test_no_int_gen_token_keeps_has_flag_false(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": None,
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        await d._apply_discovered_capabilities(opts)
        assert d.has_interference_generator is False

    @pytest.mark.asyncio
    async def test_explicit_config_overrides_probe(self):
        """When the operator explicitly sets has_interference_generator
        in config, the probe result is informational only — explicit
        wins over discovered. Pre-existing contract, pinned here so
        the new probe path doesn't accidentally clobber it."""
        d = RealPropsimF64Driver(
            instrument_id="f64-explicit",
            config={
                "ip": "192.168.0.100",
                "port": 5025,
                # Operator says "yes K01 is here" — even if probe NAKs.
                "has_interference_generator": True,
            },
        )

        async def all_nak(cmd: str, **_kwargs) -> str:
            raise RuntimeError("simulated NAK")

        d._query = all_nak  # type: ignore[assignment]
        opts = await d._probe_installed_options()
        await d._apply_discovered_capabilities(opts)
        # Explicit config wins.
        assert d.has_interference_generator is True


# ---------------------------------------------------------------------------
# Token canonicalisation — probe uses the same set the apply hook checks
# ---------------------------------------------------------------------------

class TestTokenSetAlignment:
    def test_probe_int_gen_token_is_in_apply_set(self):
        """Probe emits "INT-GEN"; ``_apply_discovered_capabilities``
        checks against ``INTERFERENCE_GEN_OPTION_TOKENS``. The probe
        token must be a member, otherwise a perfectly-detected option
        silently fails to flip the has_* flag."""
        # The apply hook upper-cases options before set intersection,
        # so the probe's canonical token must round-trip through .upper()
        # to a member of INTERFERENCE_GEN_OPTION_TOKENS.
        assert "INT-GEN".upper() in INTERFERENCE_GEN_OPTION_TOKENS


# ---------------------------------------------------------------------------
# Error-payload guard (Codex P1 on PR #15)
# ---------------------------------------------------------------------------

class TestUnsupportedErrorPayloadDetector:
    """``_is_unsupported_error_payload`` recognises IEEE 488.2 error
    tuples the F64 sometimes returns as the **query response** itself
    (not raised) when a SCPI command isn't supported.

    Without this guard the soft-probe ``if response is not None`` would
    credit ``-100,"ATE command not supported"`` as proof the license is
    installed — exactly the false-positive Codex flagged.
    """

    def test_canonical_minus_100_payload_is_rejected(self):
        # The exact payload F64 returns for unsupported commands.
        assert _is_unsupported_error_payload(
            '-100,"ATE command not supported"'
        ) is True

    def test_other_unsupported_codes_rejected(self):
        # The whole -100..-109 / -113 / -114 range is treated as
        # unsupported, matching propsim_f64_health._categorize_status.
        for code in (-100, -103, -109, -113, -114):
            payload = f'{code},"description"'
            assert _is_unsupported_error_payload(payload) is True, (
                f"code={code} should map to unsupported, got accept"
            )

    def test_no_error_sentinel_not_treated_as_unsupported(self):
        # SYST:ERR? "all clear" sentinel — looks SCPI-shaped but means
        # "everything is fine", must NOT be confused with unsupported.
        assert _is_unsupported_error_payload('0,"No error"') is False
        assert _is_unsupported_error_payload('+0,"No error"') is False

    def test_state_error_codes_not_treated_as_unsupported(self):
        # -200..-299 is "execution error" (controller knows the command,
        # just refused this state). Distinct bucket — don't lump in.
        for code in (-200, -222, -250, -299):
            payload = f'{code},"execution error"'
            assert _is_unsupported_error_payload(payload) is False, (
                f"code={code} is execution-error, not unsupported"
            )

    def test_real_response_not_treated_as_unsupported(self):
        # Normal-looking responses must pass through.
        assert _is_unsupported_error_payload("ce_sa_cal_tone,interferer_2") is False
        assert _is_unsupported_error_payload("12.345") is False
        assert _is_unsupported_error_payload("PROPSIM,F64,SN12345") is False

    def test_empty_string_not_treated_as_unsupported(self):
        # Empty ACK = "command ran, list is empty" = license present.
        # Must not be confused with an error payload.
        assert _is_unsupported_error_payload("") is False

    def test_whitespace_around_payload_tolerated(self):
        # F64 has been seen to add stray whitespace; the regex is
        # anchored with optional surrounding whitespace so leading /
        # trailing newlines don't fool the guard.
        assert _is_unsupported_error_payload(
            '  -100,"ATE command not supported"  '
        ) is True

    def test_non_string_response_safe(self):
        # Defence-in-depth — None / non-string never crashes the guard.
        assert _is_unsupported_error_payload(None) is False  # type: ignore[arg-type]


class TestProbeRejectsInlineErrorPayload:
    """End-to-end: the F64 license probe must NOT credit an option when
    the soft probe ``response`` is itself a SCPI error payload."""

    @pytest.mark.asyncio
    async def test_inline_minus_100_payload_keeps_option_absent(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            # F64 returns the error TEXT as the query response — does
            # NOT raise. Probe must detect and reject.
            "OUTPut:INTERFerence:LIST?": '-100,"ATE command not supported"',
            "SYSTem:CALibration:USER:LIST?": '-100,"ATE command not supported"',
        })
        opts = await d._probe_installed_options()
        assert opts == []

    @pytest.mark.asyncio
    async def test_no_error_sentinel_does_credit_option(self):
        """Negative control — ``0,"No error"`` (SCPI-shaped but not an
        error) must NOT be misclassified as unsupported. The probe
        should treat it as proof the command ran."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": '0,"No error"',
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        assert "INT-GEN" in opts

    @pytest.mark.asyncio
    async def test_mixed_inline_error_and_real_response(self):
        """One probe returns inline -100, the other returns real data
        — only the latter's option ends up in the list."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": '-100,"ATE command not supported"',
            "SYSTem:CALibration:USER:LIST?": "lab_alignment_v1",
        })
        opts = await d._probe_installed_options()
        assert opts == ["USER-ALIGN"]

    @pytest.mark.asyncio
    async def test_inline_error_payload_with_apply_keeps_has_flag_false(self):
        """End-to-end: an unlicensed unit emitting inline ``-100,...``
        as the probe response must NOT end up with
        ``has_interference_generator = True`` (the Codex P1 concern)."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
            "OUTPut:INTERFerence:LIST?": '-100,"ATE command not supported"',
            "SYSTem:CALibration:USER:LIST?": None,
        })
        opts = await d._probe_installed_options()
        await d._apply_discovered_capabilities(opts)
        assert d.has_interference_generator is False
