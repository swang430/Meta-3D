"""PROPSIM FS16 (Keysight F8820A) health probe — diagnostic sequence form.

Same operator-facing role as ``propsim_f64_health`` but built around
the *empirically verified* FS16 SCPI surface (different from F64).

Why a separate probe from the F64 one
-------------------------------------
F64 and FS16 share the PROPSIM brand but the SCPI dialect overlap is
small. Bench probing on a CAICT-2026-05-13 unit
(``Keysight Technologies,F8820A,MY62500170,10.2``) showed that F64
namespaces ``FAD:*``, ``CALC:FILT:FILE``, ``SENS:FREQ``, ``OUTP:STATe``,
``CH:MOD:STATe``, ``SYST:EXT:LIST`` all return
``-100,"ATE command not supported"`` on FS16; channel-indexed queries
fail with ``-200,"Channel not found"`` until a simulation is OPEN; and
``*OPT?`` itself is unsupported. Running the F64 probe against FS16
would report ~60% of "critical" commands as UNSUPPORTED and red-screen
the result, which is misleading — the FS16 commands that *do* exist
all work, they're just different names.

Strategy
--------
Two phases, same shape as the F64 / UXM probes:

* **Phase A** (~20 commands, ~3 s) — curated SCPI list of headers that
  empirically *do* respond on FS16. The list is hand-curated rather
  than auto-extracted from the driver because the FS16 driver is an
  MVP and doesn't exercise the full FS16 surface yet.
* **Phase B** (~4 calls, ~1 s) — read-only driver APIs we did
  implement: ``query_simulation_state()``,
  ``list_playback_directory()``, ``query_user_alignment_name()``,
  ``get_metrics()``.

Phase A categorises each response via ``SYST:ERR?`` with the same
SUPPORTED / SUPPORTED_BUT_STATE / UNSUPPORTED / UNKNOWN buckets the F64
and UXM probes use — keeps the GUI uniform.

Channel-indexed probes (``... :CH 1``) intentionally use the smallest
valid channel index. On FS16 these return ``-200,"Channel not found"``
when no simulation is OPEN — that's bucketed as ``SUPPORTED_BUT_STATE``
(header recognised, state rejects query) which is the correct verdict:
the SCPI header exists, we just don't have a simulation loaded.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
)
from app.services.diagnostic_context import DiagnosticContext


# Substrings that identify an FS16 / F8820 chassis. IDN says "F8820A",
# SYST:INFO says "PROPSIM FS16" — accept either as proof we're on the
# right instrument.
_IDN_OK_TAGS = ("F8820", "FS16")
_INFO_OK_TAGS = ("PROPSIM FS16", "PROPSIM FS")


# ---------------------------------------------------------------------------
# Phase A — curated SCPI surface (hand-verified on F8820A firmware 10.2)
#
# Tuple shape: (name, query, is_critical, description)
# ---------------------------------------------------------------------------
FS16_SCPI: List[Tuple[str, str, bool, str]] = [
    # Identification — must all succeed.
    ("IDN",                "*IDN?",                            True,  "identification"),
    ("OPC",                "*OPC?",                            True,  "operation complete"),
    ("STB",                "*STB?",                            False, "status byte"),
    ("ESR",                "*ESR?",                            False, "event status register"),
    # NOTE: *TST? deliberately excluded — IEEE 488.2 spec says it
    # *triggers* an actual self-test on the instrument, not a query of
    # cached results. F8820A self-test runs ~30 s during which the SCPI
    # channel does not respond to any other command, which would
    # poison every subsequent probe step. Re-add only if a future need
    # justifies a 30 s lockout.
    ("ERR",                "SYST:ERR?",                        True,  "error queue read"),
    ("SYS_INFO",           "SYST:INFO?",                       True,  "product family / channel count / band"),
    ("SYS_VERS",           "SYST:VERS?",                       False, "SCPI version (1999.0 on FS16)"),
    # Simulation engine state.
    ("SIMU_STATE",         "DIAG:SIMU:STATe?",                 True,  "simulation state (CLOSED/OPEN/RUNNING)"),
    # User alignment readback (no license needed for the query itself —
    # returns "0" when nothing is loaded).
    ("CAL_USER_GET",       "SYSTem:CALibration:USER:GET?",     False, "active user alignment ('0' = none)"),
    ("CAL_USER_INFO",      "SYSTem:CALibration:USER:INFO?",    False, "user alignment metadata"),
    # File system — MMEM is supported and tells us where playbacks live.
    ("MMEM_CDIR",          "MMEM:CDIR?",                       True,  "current playback directory"),
    ("MMEM_CAT",           "MMEM:CAT?",                        False, "directory listing"),
    # Channel-indexed reads — these are state-dependent: they exist as
    # SCPI headers but return -200 'not found' until a simulation is open.
    # We probe them anyway to verify the *headers* are recognised; the
    # state error is bucketed as SUPPORTED_BUT_STATE.
    ("CALC_FILT_CENT",     "CALC:FILT:CENT:CH? 1",             False, "ch1 center freq (needs OPEN simulation)"),
    ("INP_LEV_AMP",        "INP:LEV:AMP:CH? 1",                False, "ch1 input level (needs OPEN simulation)"),
    ("INP_PHASE",          "INP:PHA:DEG:CH? 1",                False, "ch1 input phase (needs OPEN simulation)"),
    ("OUTP_GAIN",          "OUTP:GAIN:CH? 1",                  False, "ch1 output gain (needs OPEN simulation)"),
    ("OUTP_PHASE",         "OUTP:PHA:DEG:CH? 1",               False, "ch1 output phase (needs OPEN simulation)"),
    ("OUTP_CALIB",         "OUTP:CALIB:GET? 1",                False, "ch1 output cal (needs RUNNING simulation)"),
    ("OUTP_MEAS",          "OUTP:MEAS:RES:GET? 1",             False, "ch1 output meas (needs RUNNING simulation)"),
    ("ROUT_PATH",          "ROUT:PATH:CONN? 1",                False, "ch1 path routing (needs OPEN simulation)"),
    ("DIAG_SIMU_MODEL",    "DIAG:SIMU:MODEL:STATIC?",          False, "bypass mode (needs OPEN simulation)"),
    # SCPI commands that are confirmed UNSUPPORTED — bucketed UNSUPPORTED
    # but flagged as expected so the operator isn't surprised. Listed
    # so the probe report is the single source of truth on what FS16
    # does NOT do (vs F64).
    ("OPT",                "*OPT?",                            False, "(expected UNSUPPORTED on FS16) license enumeration"),
]


# Names in FS16_SCPI we expect to come back UNSUPPORTED on this firmware.
# Showing them as failures would be noise — operator already knows.
_EXPECTED_UNSUPPORTED = frozenset({"OPT"})


def _parse_err(raw: str) -> Tuple[Optional[int], str]:
    """Parse 'SYST:ERR?' response. Returns (code, text)."""
    raw = (raw or "").strip()
    if not raw:
        return None, ""
    m = re.match(r"^([+-]?\d+)\s*,\s*(.*)$", raw)
    if not m:
        return None, raw
    return int(m.group(1)), m.group(2).strip(' "')


def _categorize_status(err_code: Optional[int]) -> str:
    """Same buckets as the F64 / UXM probes."""
    if err_code is None:
        return "UNKNOWN"
    if err_code == 0:
        return "SUPPORTED"
    if err_code in (-113, -114):
        return "UNSUPPORTED"
    if -109 <= err_code <= -100:
        return "UNSUPPORTED"  # FS16 says "-100 ATE command not supported"
    if -299 <= err_code <= -200:
        return "SUPPORTED_BUT_STATE"
    return "UNKNOWN"


metadata = SequenceMetadata(
    name="PROPSIM FS16 health probe",
    description=(
        "Two-phase FS16 readiness check. Phase A probes ~22 SCPI "
        "headers verified on F8820A firmware 10.2 and classifies each "
        "by SYST:ERR? (SUPPORTED / state-rejected / unsupported). "
        "Phase B exercises the driver's read-only APIs (simulation "
        "state, playback dir listing, user alignment, metrics). ~5 s "
        "end-to-end. Tells you the FS16 is alive, identifies itself, "
        "and isn't in a degraded state — before any real test."
    ),
    required_categories=["channelEmulator"],
    params_schema=[
        {
            "name": "include_supported",
            "label": "Detail SUPPORTED commands too (default: only flag failures)",
            "type": "boolean",
            "default": False,
        },
        {
            "name": "functional_checks",
            "label": "Run Phase B (driver API smoke tests)",
            "type": "boolean",
            "default": True,
        },
    ],
    safe_during_test=False,  # drains SYST:ERR? — would eat errors a live test is watching
)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def _drain_err(query_fn: Callable[[str], Any]) -> Tuple[Optional[int], str]:
    try:
        raw = await _maybe_await(query_fn("SYST:ERR?"))
    except Exception as e:  # noqa: BLE001
        return None, f"err-read raised: {e}"
    return _parse_err(raw if isinstance(raw, str) else str(raw))


async def _run_scpi_surface(
    ce: Any,
    *,
    include_supported: bool,
    log: Callable[[str], None],
) -> Tuple[List[SequenceStepResult], Dict[str, int], List[str], bool]:
    """Phase A. Returns (steps, counts, critical_unsupported_names, aborted_early)."""
    query_fn = ce._query  # noqa: SLF001
    write_fn = getattr(ce, "_write", None)
    if callable(write_fn):
        try:
            await _maybe_await(write_fn("*CLS"))
        except Exception:  # noqa: BLE001
            pass

    steps: List[SequenceStepResult] = []
    counts = {"SUPPORTED": 0, "SUPPORTED_BUT_STATE": 0, "UNSUPPORTED": 0, "UNKNOWN": 0}
    critical_unsupported: List[str] = []
    # Fail-fast: if we hit 3 consecutive VISA timeouts during err-read,
    # the SCPI channel is stuck (e.g. a previous command kicked off an
    # in-instrument operation that hasn't returned). Continuing would
    # eat ~10 s per remaining command for no useful signal — abort and
    # tell the operator.
    consecutive_timeouts = 0
    aborted_early = False
    log(f"  · Phase A: probing {len(FS16_SCPI)} SCPI headers ...")

    for name, query, is_critical, desc in FS16_SCPI:
        started = time.monotonic()
        try:
            await _maybe_await(query_fn(query))
        except Exception:  # noqa: BLE001
            pass
        err_code, err_text = await _drain_err(query_fn)
        status = _categorize_status(err_code)
        counts[status] = counts.get(status, 0) + 1

        # Track consecutive VISA timeouts to short-circuit a stuck channel.
        if "VI_ERROR_TMO" in err_text:
            consecutive_timeouts += 1
        else:
            consecutive_timeouts = 0
        if consecutive_timeouts >= 3:
            log(
                f"  ✗ ABORTING Phase A — 3 consecutive VISA timeouts. "
                f"Last probed: {name}. SCPI channel is stuck; "
                f"reconnect the FS16 driver (kill backend worker) and retry."
            )
            steps.append(SequenceStepResult(
                label="ABORTED",
                success=False,
                detail=(
                    "3 consecutive VISA timeouts on SYST:ERR? — SCPI "
                    "channel stuck. Skipped remaining probes to save time. "
                    "Reconnect the driver (kill backend worker → uvicorn "
                    "auto-reload reopens the SOCKET) and retry."
                ),
                duration_ms=0,
            ))
            aborted_early = True
            break

        # An UNSUPPORTED that we *expect* on FS16 is not a real failure.
        # Mark the step success accordingly so the GUI shows green for
        # "yep, FS16 doesn't have *OPT? — we know".
        is_expected_unsupported = (
            status == "UNSUPPORTED" and name in _EXPECTED_UNSUPPORTED
        )
        step_ok = (
            status in ("SUPPORTED", "SUPPORTED_BUT_STATE")
            or is_expected_unsupported
        )
        if not step_ok and is_critical:
            critical_unsupported.append(name)

        crit_part = " ★" if is_critical else ""
        expect_part = " (expected)" if is_expected_unsupported else ""
        err_part = (
            f" [{err_code}: {err_text}]" if err_code is not None
            else (f" [{err_text}]" if err_text else "")
        )
        detail = f"{status}{crit_part}{expect_part}{err_part} — {desc}"
        duration_ms = int((time.monotonic() - started) * 1000)

        # Always emit critical rows, state-rejected rows ("header
        # exists, no simulation open" — informative), unexpected
        # UNSUPPORTED (real findings), and expected UNSUPPORTED (proves
        # we did probe — operator can see we confirmed *OPT? absent
        # rather than just trust the docstring). Suppress plain
        # SUPPORTED unless operator opts in.
        emit_step = (
            include_supported
            or is_critical
            or status in ("SUPPORTED_BUT_STATE", "UNKNOWN", "UNSUPPORTED")
        )
        if emit_step:
            steps.append(SequenceStepResult(
                label=f"{name} → {query}",
                success=step_ok,
                detail=detail,
                duration_ms=duration_ms,
            ))

    log(
        f"  · Phase A done: "
        f"{counts.get('SUPPORTED', 0)} supported, "
        f"{counts.get('SUPPORTED_BUT_STATE', 0)} state-rejected, "
        f"{counts.get('UNSUPPORTED', 0)} unsupported, "
        f"{counts.get('UNKNOWN', 0)} unknown"
    )
    if critical_unsupported:
        log(f"  ✗ CRITICAL UNSUPPORTED: {sorted(critical_unsupported)}")
    return steps, counts, critical_unsupported, aborted_early


async def _run_functional_check(
    name: str,
    fn_factory: Callable[[Any], Any],
    ce: Any,
    *,
    none_is_soft: bool,
    log: Callable[[str], None],
) -> SequenceStepResult:
    """One driver-API smoke check. None return → soft pass; raise → fail."""
    started = time.monotonic()
    try:
        result = await _maybe_await(fn_factory(ce))
    except AttributeError as e:
        log(f"  ✗ {name}: driver missing method ({e})")
        return SequenceStepResult(
            label=name, success=False,
            detail=f"driver lacks method: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as e:  # noqa: BLE001
        log(f"  ✗ {name} raised: {e}")
        return SequenceStepResult(
            label=name, success=False,
            detail=f"{type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    if result is None and none_is_soft:
        log(f"  · {name}: None (not configured)")
        return SequenceStepResult(
            label=name, success=True,
            detail="returned None (no value / not configured — informational)",
            duration_ms=duration_ms,
        )
    summary = repr(result)
    if len(summary) > 240:
        summary = summary[:237] + "..."
    log(f"  ✓ {name}: {summary[:80]}")
    return SequenceStepResult(
        label=name, success=True, detail=summary, duration_ms=duration_ms,
    )


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    ce = drivers.get("channelEmulator")
    if ce is None:
        return SequenceRunResult(
            success=False,
            summary="No channelEmulator driver loaded — check HAL init logs",
        )

    query_fn = getattr(ce, "_query", None)
    if not callable(query_fn):
        return SequenceRunResult(
            success=False,
            summary=(
                f"channelEmulator driver {type(ce).__name__} doesn't expose "
                "_query; FS16 probe requires the raw SCPI primitive"
            ),
        )

    include_supported = bool(params.get("include_supported", False))
    do_functional = bool(params.get("functional_checks", True))

    # Pre-flight identity check — accept either IDN substring (F8820/FS16)
    # OR SYST:INFO? carrying the PROPSIM FS family tag. We try IDN first
    # because it's cheaper.
    try:
        idn_raw = await _maybe_await(query_fn("*IDN?"))
    except Exception as e:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"*IDN? raised: {type(e).__name__}: {e}",
        )
    idn_str = str(idn_raw or "").strip()
    idn_match = any(tag in idn_str.upper() for tag in (t.upper() for t in _IDN_OK_TAGS))
    info_str = ""
    info_match = False
    if not idn_match:
        try:
            info_raw = await _maybe_await(query_fn("SYST:INFO?"))
            info_str = str(info_raw or "").strip()
            info_match = any(tag in info_str.upper() for tag in (t.upper() for t in _INFO_OK_TAGS))
        except Exception as e:  # noqa: BLE001
            info_str = f"<err: {e}>"

    if not (idn_match or info_match):
        return SequenceRunResult(
            success=False,
            summary=(
                f"Identity check failed: IDN={idn_str!r}, "
                f"SYST:INFO={info_str!r}; expected IDN to contain one of "
                f"{_IDN_OK_TAGS} or SYST:INFO to contain one of {_INFO_OK_TAGS}"
            ),
            steps=[SequenceStepResult(
                label="*IDN?", success=False,
                detail=f"{idn_str} — SYST:INFO?={info_str}",
            )],
            extra={"idn": idn_str, "sys_info": info_str},
        )
    log(f"  ✓ *IDN?: {idn_str}")

    steps_a, counts, critical_unsupported, phase_a_aborted = await _run_scpi_surface(
        ce, include_supported=include_supported, log=log
    )

    steps_b: List[SequenceStepResult] = []
    functional_failures = 0
    # If Phase A aborted on a stuck SCPI channel, Phase B is pointless —
    # its driver methods reuse the same channel and would each eat 5+ s
    # before returning None. Skip it.
    if do_functional and not phase_a_aborted:
        log("  · Phase B: functional smoke ...")
        checks = [
            (
                "query_simulation_state()",
                lambda d: d.query_simulation_state(),
                True,
            ),
            (
                "list_playback_directory()",
                lambda d: d.list_playback_directory(),
                True,
            ),
            (
                "query_user_alignment_name()",
                lambda d: d.query_user_alignment_name(),
                True,
            ),
            (
                "get_metrics()",
                lambda d: d.get_metrics(),
                False,
            ),
        ]
        for name, factory, soft in checks:
            step = await _run_functional_check(
                name, factory, ce, none_is_soft=soft, log=log,
            )
            steps_b.append(step)
            if not step.success:
                functional_failures += 1

    success = (
        not critical_unsupported
        and functional_failures == 0
        and not phase_a_aborted
    )
    if phase_a_aborted:
        summary = (
            "ABORTED: SCPI channel got stuck (3 consecutive VISA "
            "timeouts) — reconnect the FS16 driver and retry. Typical "
            "causes: stale TCP session after long idle, a previous "
            "command that triggered an in-instrument operation, or "
            "another client holding the SOCKET."
        )
    elif success:
        summary = (
            f"PROPSIM FS16 health OK: identity matched, "
            f"{counts.get('SUPPORTED', 0)} SCPI commands supported, "
            f"{counts.get('SUPPORTED_BUT_STATE', 0)} state-rejected "
            f"(no simulation open is fine), "
            f"{counts.get('UNSUPPORTED', 0)} unsupported"
            + (
                f"; {len(steps_b)} functional checks passed"
                if do_functional else ""
            )
        )
    else:
        parts: List[str] = []
        if critical_unsupported:
            parts.append(
                f"{len(critical_unsupported)} critical SCPI unsupported: "
                f"{sorted(critical_unsupported)}"
            )
        if functional_failures:
            parts.append(f"{functional_failures} functional check(s) failed")
        summary = "BLOCKER: " + "; ".join(parts)

    return SequenceRunResult(
        success=success,
        summary=summary,
        steps=steps_a + steps_b,
        extra={
            "idn": idn_str,
            "sys_info": info_str if info_str else None,
            "counts": counts,
            "critical_unsupported": sorted(critical_unsupported),
            "scpi_probed": len(FS16_SCPI),
            "functional_failures": functional_failures,
            "phase_a_aborted": phase_a_aborted,
            "include_supported": include_supported,
            "functional_checks": do_functional,
        },
    )
