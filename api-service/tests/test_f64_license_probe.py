"""F64 license discovery — SYSTem:INFO? replacement for ``*OPT?``.

Confirmed CAICT 2026-05-13 (memory ``project_f64_ate_server_capabilities``):
F64's ATE Server answers ``-100,"ATE command not supported"`` to
``*OPT?``. The base class default therefore got no options and the
``has_interference_generator`` flag silently stayed False even on units
where the K01 license was actually installed.

License discovery reads the ``SYSTem:INFO?`` reply — the manual says it
carries the license list (User Reference Rev 10.2 §20.4.2.4, "Query
returns the basic system info and licenses") — and scans it for known
keywords.

P1-66: the former "soft feature probes"
(``SYSTem:CALibration:USER:LIST?`` / ``OUTPut:INTERFerence:LIST?``) were
removed — both commands are absent from the manual, each connect left a
-100 in the error queue, and crediting "any response" as an ACK turned
the returned -100 payload into a license false-positive. The fake driver
here raises on any unexpected SCPI, so these tests double as a unit-level
gate that no fabricated probe command is ever sent.

Connect-level behavior gates live in ``test_p1_66_f64_probe_truth.py``.
"""
from __future__ import annotations

from typing import Any, Dict

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
    unexpected SCPI traffic — better than silently passing). Every sent
    command is recorded on ``driver._sent_commands``.
    """
    d = RealPropsimF64Driver(
        instrument_id="f64-license-test",
        config={"ip": "192.168.0.100", "port": 5025},
    )
    d._sent_commands = []  # type: ignore[attr-defined]

    async def fake_query(cmd: str, **_kwargs) -> str:
        d._sent_commands.append(cmd)  # type: ignore[attr-defined]
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
# SYST:INFO? scan — the single license source
# ---------------------------------------------------------------------------

class TestSystInfoKeywordScan:
    @pytest.mark.asyncio
    async def test_interference_keyword_promotes_int_gen(self):
        """Realistic SYST:INFO? format with license names in the tail
        (manual §20.4.2.4) — both tokens recognised from the scan."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,Interference Generator,Calibration User Alignment",
        })
        opts = await d._probe_installed_options()
        assert "INT-GEN" in opts
        assert "USER-ALIGN" in opts

    @pytest.mark.asyncio
    async def test_awgn_interferences_field_form_is_recognised(self):
        """现场 2026-08 实测形态: SYST:INFO? 含 "AWGN interferences:32"。"""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,Main license,AWGN interferences:32,Shadowing",
        })
        opts = await d._probe_installed_options()
        assert "INT-GEN" in opts

    @pytest.mark.asyncio
    async def test_no_keywords_means_no_tokens(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz",
        })
        opts = await d._probe_installed_options()
        assert opts == []
        assert d._certification_options_observed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "reply",
        (
            "",
            "   ",
            '-100,"ATE command not supported"',
            '0,"No error"',
        ),
    )
    async def test_invalid_syst_info_reply_keeps_certification_options_unobserved(
        self,
        reply,
    ):
        d = _make_driver_with_query_table({"SYST:INFO?": reply})

        opts = await d._probe_installed_options()

        assert opts == []
        assert d._certification_options_observed is False

    @pytest.mark.asyncio
    async def test_syst_info_failure_yields_empty_and_does_not_raise(self):
        """SYST:INFO? failing must not break connect — discovery just
        yields no tokens (fail-closed; explicit config can override)."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": RuntimeError("simulated SYST:INFO? failure"),
        })
        opts = await d._probe_installed_options()
        assert opts == []


# ---------------------------------------------------------------------------
# No fabricated probe commands (P1-66)
# ---------------------------------------------------------------------------

class TestNoFabricatedProbeCommands:
    @pytest.mark.asyncio
    async def test_discovery_sends_only_syst_info(self):
        """The two manual-absent probe commands
        (``SYSTem:CALibration:USER:LIST?`` / ``OUTPut:INTERFerence:LIST?``)
        must never be sent — with or without keyword hits."""
        for info in (
            "PROPSIM F64,64,RF,v1.0,16",  # no keywords → no fallback probing
            "PROPSIM F64,64,RF,Interference Generator",
        ):
            d = _make_driver_with_query_table({"SYST:INFO?": info})
            await d._probe_installed_options()
            assert d._sent_commands == ["SYST:INFO?"]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Idempotence — multiple keywords mapping to one token don't double-list
# ---------------------------------------------------------------------------

class TestNoDuplicates:
    @pytest.mark.asyncio
    async def test_two_keywords_for_same_token_emit_once(self):
        # "interference" and "int-gen" both map to INT-GEN.
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,Interference Generator,INT-GEN option",
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
        """End-to-end intent: ``has_interference_generator`` ends up True
        on a unit whose SYST:INFO? names the license, without operator
        having to manually set ``config['has_interference_generator']``."""
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF,Interference Generator",
        })
        opts = await d._probe_installed_options()
        await d._apply_discovered_capabilities(opts)
        assert d.has_interference_generator is True

    @pytest.mark.asyncio
    async def test_no_int_gen_token_keeps_has_flag_false(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": "PROPSIM F64,64,RF",
        })
        opts = await d._probe_installed_options()
        await d._apply_discovered_capabilities(opts)
        assert d.has_interference_generator is False

    @pytest.mark.asyncio
    async def test_explicit_config_overrides_discovery(self):
        """When the operator explicitly sets has_interference_generator
        in config, the discovery result is informational only — explicit
        wins over discovered. Pre-existing contract, pinned here so
        the discovery path doesn't accidentally clobber it."""
        d = RealPropsimF64Driver(
            instrument_id="f64-explicit",
            config={
                "ip": "192.168.0.100",
                "port": 5025,
                # Operator says "yes K01 is here" — even if SYST:INFO? NAKs.
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
# Token canonicalisation — scan uses the same set the apply hook checks
# ---------------------------------------------------------------------------

class TestTokenSetAlignment:
    def test_scan_int_gen_token_is_in_apply_set(self):
        """The scan emits "INT-GEN"; ``_apply_discovered_capabilities``
        checks against ``INTERFERENCE_GEN_OPTION_TOKENS``. The canonical
        token must be a member, otherwise a perfectly-detected option
        silently fails to flip the has_* flag."""
        # The apply hook upper-cases options before set intersection,
        # so the canonical token must round-trip through .upper()
        # to a member of INTERFERENCE_GEN_OPTION_TOKENS.
        assert "INT-GEN".upper() in INTERFERENCE_GEN_OPTION_TOKENS


# ---------------------------------------------------------------------------
# Error-payload guard (Codex P1 on PR #15; consumed post-P1-66 by
# get_user_alignment_status and the health categorizer alignment)
# ---------------------------------------------------------------------------

class TestUnsupportedErrorPayloadDetector:
    """``_is_unsupported_error_payload`` recognises IEEE 488.2 error
    tuples the F64 sometimes returns as the **query response** itself
    (not raised) when a SCPI command isn't supported.

    Without this guard, code that checks "did we get a non-empty
    string?" would credit ``-100,"ATE command not supported"`` as a
    real value — e.g. as an active user-alignment name.
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
        # Empty reply = 合法回复形态 (e.g. USER:GET? 未启用, §20.4.2.19)。
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


class TestScanRejectsInlineErrorPayload:
    """SYST:INFO? itself replying with a SCPI error payload must yield
    no license tokens (the error text carries no keywords — fail-closed
    by construction, pinned here so a keyword addition can't break it)."""

    @pytest.mark.asyncio
    async def test_inline_minus_100_payload_yields_no_tokens(self):
        d = _make_driver_with_query_table({
            "SYST:INFO?": '-100,"ATE command not supported"',
        })
        opts = await d._probe_installed_options()
        assert opts == []
        assert d._certification_options_observed is False
