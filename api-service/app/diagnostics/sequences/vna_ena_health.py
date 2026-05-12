"""Keysight E5071C ENA health probe — diagnostic sequence form.

Runs the four checks an operator wants before kicking off a path-loss
calibration: driver loaded, IDN matches an E5071-family box, a short
S21 sweep completes, and the returned trace is well-formed (N points,
no NaN).

Same architectural rationale as ``uxm_scpi_compatibility``: reuse the
live HAL session (one VXI-11 client per E5071C is the safe assumption),
get a ``diagnostic_runs`` audit row, and surface in the "调试序列"
panel — no standalone CLI.

Outcome is intentionally narrow:

* PASS = the measurement pipeline returned data of the expected shape.
* FAIL = driver missing, IDN doesn't say E5071, setup_sweep / measure /
  trace fetch threw or returned the wrong shape.

An all-zero trace is *not* a failure — that's the expected reading when
the operator deliberately leaves a port open (common during cal
familiarization). We surface it as a step note so the operator notices,
but it doesn't block the run.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Callable, Dict, List, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
)
from app.services.diagnostic_context import DiagnosticContext


# IDN substrings we accept as "this is an E5071-family ENA". Keysight
# rebranded from Agilent ~2014; both prefixes still show up in the wild.
_IDN_MODEL_TAG = "E5071"


metadata = SequenceMetadata(
    name="VNA E5071C health probe",
    description=(
        "Four-step sanity check for the Keysight E5071C ENA before path-loss "
        "calibration: driver loaded, IDN reports E5071-family, short S21 "
        "sweep completes, trace data has the expected shape. ~5 s end-to-end."
    ),
    required_categories=["vna"],
    params_schema=[
        {
            "name": "center_freq_mhz",
            "label": "Sweep center frequency (MHz)",
            "type": "number",
            "default": 2450,
        },
        {
            "name": "span_mhz",
            "label": "Sweep span (MHz)",
            "type": "number",
            "default": 100,
        },
        {
            "name": "points",
            "label": "Sweep points",
            "type": "number",
            "default": 101,
        },
    ],
    safe_during_test=False,  # mutates ENA sweep config; don't interleave with a live cal
)


async def _maybe_await(value: Any) -> Any:
    """Drivers may run sync (pyvisa is sync) or async — uniformise."""
    if asyncio.iscoroutine(value):
        return await value
    return value


async def _query_idn(driver: Any) -> Optional[str]:
    """Try a few well-known ways drivers expose *IDN?."""
    for name in ("get_identity", "query_idn"):
        method = getattr(driver, name, None)
        if callable(method):
            try:
                return await _maybe_await(method())
            except Exception:  # noqa: BLE001
                continue
    # Fall back to the raw _query primitive used elsewhere in HAL drivers.
    raw_query = getattr(driver, "_query", None)
    if callable(raw_query):
        try:
            return await _maybe_await(raw_query("*IDN?"))
        except Exception:  # noqa: BLE001
            return None
    return None


def _trace_stats(trace: List[complex]) -> Dict[str, Any]:
    """Summarise trace shape without importing numpy (this runs hot)."""
    if not trace:
        return {"len": 0, "nan_count": 0, "all_zero": True, "first": None, "last": None}
    nan_count = 0
    all_zero = True
    for c in trace:
        if isinstance(c, complex):
            re_v, im_v = c.real, c.imag
        else:
            re_v, im_v = float(c), 0.0
        if math.isnan(re_v) or math.isnan(im_v):
            nan_count += 1
        if re_v != 0.0 or im_v != 0.0:
            all_zero = False
    return {
        "len": len(trace),
        "nan_count": nan_count,
        "all_zero": all_zero,
        "first": str(trace[0]),
        "last": str(trace[-1]),
    }


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    vna = drivers.get("vna")
    if vna is None:
        return SequenceRunResult(
            success=False,
            summary="No vna driver loaded — check HAL init logs",
        )

    center_mhz = float(params.get("center_freq_mhz", 2450))
    span_mhz = float(params.get("span_mhz", 100))
    points = int(params.get("points", 101))
    start_hz = (center_mhz - span_mhz / 2) * 1e6
    stop_hz = (center_mhz + span_mhz / 2) * 1e6

    steps: List[SequenceStepResult] = []
    extra: Dict[str, Any] = {
        "center_freq_mhz": center_mhz,
        "span_mhz": span_mhz,
        "points": points,
    }

    # Step 1: IDN — confirm the box behind that IP is actually an E5071.
    started = time.monotonic()
    idn = await _query_idn(vna)
    duration_ms = int((time.monotonic() - started) * 1000)
    if idn is None:
        steps.append(SequenceStepResult(
            label="*IDN?",
            success=False,
            detail="Driver exposes none of get_identity/query_idn/_query, or all raised",
            duration_ms=duration_ms,
        ))
        log("  ✗ *IDN? — no usable query method on the driver")
        return SequenceRunResult(
            success=False,
            summary="VNA driver can't be queried for IDN",
            steps=steps,
            extra=extra,
        )
    idn_str = str(idn).strip()
    extra["idn"] = idn_str
    idn_ok = _IDN_MODEL_TAG in idn_str.upper()
    steps.append(SequenceStepResult(
        label="*IDN?",
        success=idn_ok,
        detail=idn_str if idn_ok else (
            f"{idn_str} — expected substring '{_IDN_MODEL_TAG}'"
        ),
        duration_ms=duration_ms,
    ))
    log(f"  {'✓' if idn_ok else '✗'} *IDN?: {idn_str}")
    if not idn_ok:
        return SequenceRunResult(
            success=False,
            summary=(
                f"IDN reports '{idn_str}' — not an E5071-family ENA. "
                "Check the IP / VISA endpoint points at the right instrument."
            ),
            steps=steps,
            extra=extra,
        )

    # Step 2: setup_sweep — exercises freq config + *OPC? sync.
    started = time.monotonic()
    try:
        setup_ok = await _maybe_await(vna.setup_sweep(start_hz, stop_hz, points))
    except Exception as e:  # noqa: BLE001
        setup_ok = False
        setup_err = f"{type(e).__name__}: {e}"
    else:
        setup_err = None
    duration_ms = int((time.monotonic() - started) * 1000)
    steps.append(SequenceStepResult(
        label=f"setup_sweep({start_hz/1e6:.1f}–{stop_hz/1e6:.1f} MHz, {points} pts)",
        success=bool(setup_ok),
        detail=setup_err or ("OK" if setup_ok else "driver returned False"),
        duration_ms=duration_ms,
    ))
    log(f"  {'✓' if setup_ok else '✗'} setup_sweep")
    if not setup_ok:
        return SequenceRunResult(
            success=False,
            summary=f"setup_sweep failed: {setup_err or 'driver returned False'}",
            steps=steps,
            extra=extra,
        )

    # Step 3: measure_s_param S21 — exercises CALC + INIT + OPC.
    started = time.monotonic()
    try:
        meas_ok = await _maybe_await(vna.measure_s_param("S21"))
    except Exception as e:  # noqa: BLE001
        meas_ok = False
        meas_err = f"{type(e).__name__}: {e}"
    else:
        meas_err = None
    duration_ms = int((time.monotonic() - started) * 1000)
    steps.append(SequenceStepResult(
        label="measure_s_param('S21')",
        success=bool(meas_ok),
        detail=meas_err or ("OK" if meas_ok else "driver returned False"),
        duration_ms=duration_ms,
    ))
    log(f"  {'✓' if meas_ok else '✗'} measure_s_param S21")
    if not meas_ok:
        return SequenceRunResult(
            success=False,
            summary=f"measure_s_param('S21') failed: {meas_err or 'driver returned False'}",
            steps=steps,
            extra=extra,
        )

    # Step 4: get_trace_data — exercises CALC:DATA? + ASCII parse.
    started = time.monotonic()
    try:
        trace = await _maybe_await(vna.get_trace_data())
    except Exception as e:  # noqa: BLE001
        steps.append(SequenceStepResult(
            label="get_trace_data()",
            success=False,
            detail=f"{type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
        log(f"  ✗ get_trace_data raised: {e}")
        return SequenceRunResult(
            success=False,
            summary=f"get_trace_data raised: {e}",
            steps=steps,
            extra=extra,
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    stats = _trace_stats(list(trace or []))
    extra["trace_stats"] = stats

    trace_ok = (
        stats["len"] == points
        and stats["nan_count"] == 0
    )
    note_parts: List[str] = [f"{stats['len']} points"]
    if stats["nan_count"]:
        note_parts.append(f"{stats['nan_count']} NaN")
    if stats["all_zero"]:
        note_parts.append("ALL-ZERO (open port? cable disconnected?)")
    elif stats["first"]:
        note_parts.append(f"first={stats['first']}")
    detail = ", ".join(note_parts)
    if not trace_ok:
        if stats["len"] != points:
            detail = f"expected {points} points, got {stats['len']} — {detail}"
    steps.append(SequenceStepResult(
        label="get_trace_data()",
        success=trace_ok,
        detail=detail,
        duration_ms=duration_ms,
    ))
    log(f"  {'✓' if trace_ok else '✗'} get_trace_data: {detail}")

    if not trace_ok:
        return SequenceRunResult(
            success=False,
            summary=(
                f"Trace data malformed: {detail}. Check ENA FORM:DATA setting "
                "and that the active measurement has data."
            ),
            steps=steps,
            extra=extra,
        )

    summary_note = " (trace all-zero — open port / cable off, not a fault)" if stats["all_zero"] else ""
    return SequenceRunResult(
        success=True,
        summary=(
            f"E5071C health OK: IDN matched, S21 sweep "
            f"{start_hz/1e6:.0f}–{stop_hz/1e6:.0f} MHz × {points} pts returned"
            + summary_note
        ),
        steps=steps,
        extra=extra,
    )
