"""PROPSIM F64 channel-emulator health probe — diagnostic sequence form.

Mirrors what ``uxm_scpi_compatibility`` and ``vna_ena_health`` do for the
baseStation and VNA, but for the F64 — covering both the wide SCPI
surface (24 critical commands across identification, simulation engine,
channel filter, calibration, external units) AND the high-value
read-only driver APIs an operator uses before a real test.

Why two phases
--------------
F64's SCPI surface is much wider than UXM's: GCM-native + ASC-runtime
pipelines, optional licenses (Internal Interference Generator, User
Alignment), external units (SGH), runtime-emulation channel
configuration. A pure header-existence probe (Phase A) catches
firmware/license mismatches; the functional Phase B catches the
"header exists but the API path crashes for a different reason" case
(parser errors, retry-timeout, etc.).

Strategy — Phase A (SCPI surface, ~24 cmds, ~5 s)
-------------------------------------------------
For each curated SCPI header:

* QUERY form: send as-is.
* Append ``?`` when the driver only writes the header (e.g.
  ``DIAG:SIMU:MODEL:STATIC`` → ``DIAG:SIMU:MODEL:STATIC?``).
* Read ``SYST:ERR?`` after each probe and categorize the error code:

    *  0 ..................... SUPPORTED (command succeeded)
    * -200..-299 ............. SUPPORTED_BUT_STATE (header ok,
                               instrument state rejects query — fine
                               for a probe)
    * -113 / -114 ............ UNSUPPORTED (undefined header)
    * -100..-109 ............. UNSUPPORTED (F64 returns -100,"ATE
                               command not supported" for unknown
                               commands; Keysight reuses the SCPI
                               "command error" range to mean
                               "not in firmware")
    * anything else .......... UNKNOWN (surfaced raw)

The "critical" set tags the commands without which path-loss
calibration / channel loading / commissioning won't run. Any critical
UNSUPPORTED → success=False with a BLOCKER summary.

Strategy — Phase B (driver-API smoke, ~5 calls, ~2 s)
-----------------------------------------------------
Read-only driver methods that exercise multi-step SCPI sequences the
operator depends on:

* ``query_runtime_environment([1])`` — proves CH:MOD:CONT:ENV readback
* ``get_user_alignment_status()`` — proves user alignment query path
* ``list_external_units()`` — proves SGH discovery path
* ``get_output_calibration(1)`` — proves cal-readback + retry path
* ``get_metrics()`` — end-to-end driver snapshot

Each is wrapped in try/except. Returning ``None`` from a method that
documents that as "not available" is treated as a soft pass (license
not installed, no SGH connected, etc.); raising or hard-failing is
counted as a failure.

Safety
------
``safe_during_test=False`` — we don't mutate state, but we drain
``SYST:ERR?`` repeatedly which would eat errors a real test is
monitoring. Run between tests, not during.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    driver_not_loaded_summary,
    SequenceStepResult,
)
from app.services.diagnostic_context import DiagnosticContext


# IDN substrings used to verify the box behind that IP is actually a F64
# (not a different PROPSIM model or some other emulator). Match if ANY tag
# appears in IDN or SYST:INFO. Real F64 IDN observed at CAICT 2026-05-13 is
# ``Keysight Technologies,F8800A,...`` — no "PROPSIM" — so the Keysight SKU
# is the practical gate; SYST:INFO? typically carries "PROPSIM F64,...".
_IDN_MODEL_TAGS = ("PROPSIM", "F8800")


# ---------------------------------------------------------------------------
# Phase A — curated SCPI surface
#
# Tuple shape: (name, query_to_send, is_critical, description)
#   - name: short label that goes in step.label
#   - query_to_send: literal SCPI; must end in '?' (we append it for header
#     probes where the canonical form is write-only)
#   - is_critical: if UNSUPPORTED, blocks commissioning / path-loss cal
#   - description: human-readable detail for the step
#
# Index 1 is used for any channel-indexed query (CH 1, INP 1, OUTP 1) — every
# F64 has at least 1 channel, no risk of out-of-range error.
# ---------------------------------------------------------------------------
PROPSIM_SCPI: List[Tuple[str, str, bool, str]] = [
    # Identification & status — every F64 must answer these.
    ("IDN",                "*IDN?",                            True,  "identification"),
    ("OPT",                "*OPT?",                            True,  "installed licenses/options"),
    ("STB",                "*STB?",                            False, "status byte"),
    ("ESR",                "*ESR?",                            False, "event status register"),
    ("ERR",                "SYST:ERR?",                        True,  "error queue read"),
    ("SYS_INFO",           "SYST:INFO?",                       True,  "system info (channel count, band)"),
    ("SYS_VERS",           "SYST:VERS?",                       False, "SCPI version"),
    # Simulation engine — DIAG:SIMU namespace is F64-specific.
    ("SIMU_MODEL_STATIC",  "DIAG:SIMU:MODEL:STATIC?",          True,  "static bypass mode"),
    # Channel filter / routing — required for set_channel_model + frequency.
    ("CALC_FILT_CENT",     "CALC:FILT:CENT:CH? 1",             True,  "ch1 center frequency"),
    ("ROUT_PATH",          "ROUT:PATH:CONN? 1",                True,  "ch1 physical connector mapping"),
    # Runtime ASC pipeline (license-gated on some F64 builds).
    ("CH_MOD_ENV",         "CH:MOD:CONT:ENV? 1",               False, "runtime environment ch1"),
    # Input/output channel state.
    ("INP_LEV_AMP",        "INP:LEV:AMP:CH? 1",                False, "input level ch1"),
    ("OUTP_GAIN",          "OUTP:GAIN:CH? 1",                  False, "output gain ch1"),
    ("INP_PHASE",          "INP:PHA:DEG:CH? 1",                False, "input phase ch1"),
    ("OUTP_PHASE",         "OUTP:PHA:DEG:CH? 1",               False, "output phase ch1"),
    # Calibration measurement — required for path-loss readback.
    ("OUTP_CALIB",         "OUTP:CALIB:GET? 1",                True,  "ch1 calibration readback"),
    ("OUTP_MEAS",          "OUTP:MEAS:RES:GET? 1",             False, "ch1 output measurement"),
    ("INP_MEAS",           "INP:MEAS:RES:GET? 1",              False, "ch1 input measurement"),
    # User alignment (license-dependent — soft requirement).
    ("CAL_USER_GET",       "SYSTem:CALIBration:USER:GET?",     False, "active user calibration name"),
    ("CAL_USER_INFO",      "SYSTem:CALIBration:USER:INFO?",    False, "user calibration metadata"),
    # External units — SGH discovery, required for path-loss across SGH.
    ("EXT_UNIT_LIST",      "SYSTem:EXTernal:UNIT:LIST? 0",     False, "connected external units (SGH)"),
    # Mass-memory subsystem — required if we want to list available .smu
    # channel-model files on the F64's local disk (GUI dropdown of
    # operator-selectable models, instead of typing a path). FS16 already
    # supports these; F64 same firmware family is expected to as well,
    # but we've never verified on a real F64 — this probe row is the
    # verification step.
    ("MMEM_CDIR",          "MMEM:CDIR?",                       False, "current mass-memory working directory"),
    ("MMEM_CAT",           "MMEM:CAT?",                        False, "directory listing (used,free,\"name,type,size\",...)"),
    # Interference generator (license-dependent CW tone path).
    ("INT_LIST",           "OUTPut:INTERFerence:LIST?",        False, "active interference signals"),
    # RSRP measurement subsystem (queries existence, doesn't trigger one).
    ("RSRP_HEADER",        "INP:RSRP:MEAS:STAT?",              False, "RSRP measurement subsystem"),
]


# ---------------------------------------------------------------------------
# Helpers — pure functions, unit-testable
# ---------------------------------------------------------------------------

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
    # F64's ATE Server uses ``-100,"ATE command not supported"`` to report
    # "this command is not implemented" — same pattern as FS16. The
    # IEEE 488.2 spec defines -100..-109 as "command error" sub-codes
    # (header parses but something's off), but Keysight repurposed the
    # range to mean "command not in firmware", so anything in -100..-109
    # is functionally UNSUPPORTED, not SUPPORTED. -113/-114 ("undefined
    # header") are also UNSUPPORTED — we collapse both groups.
    """Same buckets as the UXM probe — kept identical so the GUI can
    treat the two probes uniformly for filtering."""
    if err_code is None:
        return "UNKNOWN"
    if err_code == 0:
        return "SUPPORTED"
    if err_code in (-113, -114):
        return "UNSUPPORTED"
    if -109 <= err_code <= -100:
        # F64 ATE Server says "ATE command not supported" in this range.
        return "UNSUPPORTED"
    if -299 <= err_code <= -200:
        return "SUPPORTED_BUT_STATE"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Sequence contract
# ---------------------------------------------------------------------------

metadata = SequenceMetadata(
    name="PROPSIM F64 health probe",
    description=(
        "Two-phase F64 readiness check: (A) probes ~24 critical SCPI "
        "headers and classifies each by SYST:ERR?; (B) exercises 5 "
        "read-only driver APIs (runtime env, user alignment, external "
        "units, output calibration, metrics). ~7 s end-to-end. Catches "
        "firmware/license mismatches before commissioning runs."
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
            "label": "Run Phase B (functional smoke tests)",
            "type": "boolean",
            "default": True,
        },
    ],
    safe_during_test=False,  # drains SYST:ERR? — would mask errors a live test is watching
)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def _drain_err(query_fn: Callable[[str], Any]) -> Tuple[Optional[int], str]:
    """Single SYST:ERR? read with await-handling."""
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
    # Clear the error queue once so the first probe sees a clean state.
    if callable(write_fn):
        try:
            await _maybe_await(write_fn("*CLS"))
        except Exception:  # noqa: BLE001
            pass

    steps: List[SequenceStepResult] = []
    counts = {"SUPPORTED": 0, "SUPPORTED_BUT_STATE": 0, "UNSUPPORTED": 0, "UNKNOWN": 0}
    critical_unsupported: List[str] = []
    # Fail-fast: 3 consecutive VISA timeouts during err-read => SCPI
    # channel is stuck. Continuing eats ~10 s per remaining command for
    # no useful signal. (Backported from the FS16 probe after the
    # 2026-05-13 on-site session hit a stuck channel via *TST?.)
    consecutive_timeouts = 0
    aborted_early = False

    log(f"  · Phase A: probing {len(PROPSIM_SCPI)} SCPI headers ...")

    for name, query, is_critical, desc in PROPSIM_SCPI:
        started = time.monotonic()
        # Send the probe; we don't care about the return — the error queue is
        # the source of truth. Some queries legitimately raise on this
        # firmware/state (e.g. "not ready" responses); swallow and inspect ERR.
        try:
            await _maybe_await(query_fn(query))
        except Exception:  # noqa: BLE001
            pass
        err_code, err_text = await _drain_err(query_fn)
        status = _categorize_status(err_code)
        counts[status] = counts.get(status, 0) + 1
        step_ok = status in ("SUPPORTED", "SUPPORTED_BUT_STATE")
        if not step_ok and is_critical:
            critical_unsupported.append(name)

        # Track consecutive VISA timeouts to short-circuit a stuck channel.
        if "VI_ERROR_TMO" in err_text:
            consecutive_timeouts += 1
        else:
            consecutive_timeouts = 0

        crit_part = " ★" if is_critical else ""
        err_part = (
            f" [{err_code}: {err_text}]" if err_code is not None
            else (f" [{err_text}]" if err_text else "")
        )
        detail = f"{status}{crit_part}{err_part} — {desc}"
        duration_ms = int((time.monotonic() - started) * 1000)

        # Suppress noisy SUPPORTED rows unless the operator opts in — keeps
        # the GUI step list focused on real findings. Always emit critical
        # rows so blockers are visible.
        emit_step = include_supported or not step_ok or is_critical
        if emit_step:
            steps.append(SequenceStepResult(
                label=f"{name} → {query}",
                success=step_ok,
                detail=detail,
                duration_ms=duration_ms,
            ))

        if consecutive_timeouts >= 3:
            log(
                f"  ✗ ABORTING Phase A — 3 consecutive VISA timeouts. "
                f"Last probed: {name}. SCPI channel is stuck; "
                f"reconnect the F64 driver (kill backend worker) and retry."
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

    log(
        f"  · Phase A done: "
        f"{counts.get('SUPPORTED', 0)} supported, "
        f"{counts.get('SUPPORTED_BUT_STATE', 0)} state, "
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
    none_means_unsupported: bool,
    log: Callable[[str], None],
) -> SequenceStepResult:
    """Exercise one driver API; classify success/soft-pass/fail.

    `fn_factory(ce)` is a deferred call so we can build the args at probe
    time (some methods take parameters like channel=1).
    """
    started = time.monotonic()
    try:
        result = await _maybe_await(fn_factory(ce))
    except AttributeError as e:
        log(f"  ✗ {name}: driver missing this method ({e})")
        return SequenceStepResult(
            label=name,
            success=False,
            detail=f"driver lacks method: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as e:  # noqa: BLE001
        log(f"  ✗ {name} raised: {e}")
        return SequenceStepResult(
            label=name,
            success=False,
            detail=f"{type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    if result is None and none_means_unsupported:
        # Method documents None as "not available" (no license / nothing
        # connected / not ready). Soft pass — surface but don't fail.
        log(f"  · {name}: None (not available / not configured)")
        return SequenceStepResult(
            label=name,
            success=True,
            detail="returned None (not available — license/feature/connection optional)",
            duration_ms=duration_ms,
        )

    # Truncate large responses for step detail.
    summary = repr(result)
    if len(summary) > 240:
        summary = summary[:237] + "..."
    log(f"  ✓ {name}: {summary[:80]}")
    return SequenceStepResult(
        label=name,
        success=True,
        detail=summary,
        duration_ms=duration_ms,
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
            summary=driver_not_loaded_summary("channelEmulator"),
        )

    query_fn = getattr(ce, "_query", None)
    if not callable(query_fn):
        return SequenceRunResult(
            success=False,
            summary=(
                f"channelEmulator driver {type(ce).__name__} doesn't expose _query; "
                "PROPSIM probe requires the raw SCPI primitive"
            ),
        )

    include_supported = bool(params.get("include_supported", False))
    do_functional = bool(params.get("functional_checks", True))

    # Pre-flight: verify IDN says PROPSIM before running 24 probes against
    # something that might be a different instrument behind the same IP.
    # Two-tier identity gate: IDN first, SYST:INFO? as fallback for the
    # firmware-rebranded case (backported from the FS16 probe — FS16's
    # IDN says "F8820A" but SYST:INFO carries "PROPSIM FS16"; future F64
    # firmware revs might do the same).
    try:
        idn_raw = await _maybe_await(query_fn("*IDN?"))
    except Exception as e:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"*IDN? raised: {type(e).__name__}: {e}",
        )
    idn_str = str(idn_raw or "").strip()
    idn_match = any(tag in idn_str.upper() for tag in _IDN_MODEL_TAGS)
    info_str = ""
    info_match = False
    if not idn_match:
        try:
            info_raw = await _maybe_await(query_fn("SYST:INFO?"))
            info_str = str(info_raw or "").strip()
            info_match = any(tag in info_str.upper() for tag in _IDN_MODEL_TAGS)
        except Exception as e:  # noqa: BLE001
            info_str = f"<err: {e}>"

    if not (idn_match or info_match):
        return SequenceRunResult(
            success=False,
            summary=(
                f"Identity check failed: IDN={idn_str!r}, "
                f"SYST:INFO={info_str!r}; expected any of "
                f"{_IDN_MODEL_TAGS} in either."
            ),
            steps=[SequenceStepResult(
                label="*IDN?",
                success=False,
                detail=f"{idn_str} — SYST:INFO?={info_str}",
            )],
            extra={"idn": idn_str, "sys_info": info_str},
        )
    log(f"  ✓ *IDN?: {idn_str}")

    # ----- Phase A: SCPI surface -----
    steps_a, counts, critical_unsupported, phase_a_aborted = await _run_scpi_surface(
        ce, include_supported=include_supported, log=log
    )

    # ----- Phase B: Functional smoke (driver APIs) -----
    # Skipped if Phase A aborted on a stuck channel — Phase B would reuse
    # the same channel and each call would eat 5+ s timing out.
    steps_b: List[SequenceStepResult] = []
    functional_failures = 0
    if do_functional and not phase_a_aborted:
        log("  · Phase B: functional smoke ...")
        functional_checks = [
            # (name, factory, none_means_unsupported)
            (
                "query_runtime_environment([1])",
                lambda d: d.query_runtime_environment([1]),
                False,
            ),
            (
                "get_user_alignment_status()",
                lambda d: d.get_user_alignment_status(),
                True,   # None = no active alignment, fine
            ),
            (
                "list_external_units()",
                lambda d: d.list_external_units(),
                False,  # [] is fine, None would be unusual
            ),
            (
                "get_output_calibration(1)",
                lambda d: d.get_output_calibration(1),
                True,   # None = not-ready / no cal, soft
            ),
            (
                "get_metrics()",
                lambda d: d.get_metrics(),
                False,
            ),
        ]
        for name, factory, soft in functional_checks:
            step = await _run_functional_check(
                name, factory, ce, none_means_unsupported=soft, log=log,
            )
            steps_b.append(step)
            if not step.success:
                functional_failures += 1

    # ----- Verdict -----
    success = (
        not critical_unsupported
        and functional_failures == 0
        and not phase_a_aborted
    )
    if phase_a_aborted:
        summary = (
            "ABORTED: SCPI channel got stuck (3 consecutive VISA "
            "timeouts) — reconnect the F64 driver and retry. Typical "
            "causes: stale TCP session after long idle, a previous "
            "command that triggered an in-instrument operation, or "
            "another client holding the SOCKET."
        )
    elif success:
        summary = (
            f"PROPSIM F64 health OK: IDN matched, "
            f"{counts.get('SUPPORTED', 0)} SCPI commands supported, "
            f"{counts.get('UNSUPPORTED', 0)} non-critical unsupported, "
            f"{counts.get('SUPPORTED_BUT_STATE', 0)} state-rejected (both OK)"
            + (
                f", {len(steps_b)} functional checks passed"
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
            "scpi_probed": len(PROPSIM_SCPI),
            "functional_failures": functional_failures,
            "phase_a_aborted": phase_a_aborted,
            "include_supported": include_supported,
            "functional_checks": do_functional,
        },
    )
