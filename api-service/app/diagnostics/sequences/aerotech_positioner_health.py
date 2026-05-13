"""Aerotech positioner health probe — diagnostic sequence form.

Operator-facing role parallels ``propsim_f64_health`` /
``propsim_fs16_health`` / ``uxm_scpi_compatibility`` — a fast read-only
check before a real test that the turntable is alive, identifies its
axes, isn't in a fault state, and the driver-level APIs we use during
calibration/test all return.

Why this looks different from the SCPI probes
---------------------------------------------
Aerotech Ensemble / A3200 controllers don't speak SCPI. They speak
**AeroBasic ASCII** over a TCP Socket (default Ensemble Socket2 → port
8000). The wire protocol has three response framings instead of
SCPI's ``SYST:ERR?`` query:

* ``%<data>``  ACK — command succeeded; ``<data>`` is the optional
  return value for query commands.
* ``!<...>``   NAK — invalid syntax / unsupported command / parameter
  error. ``RealAerotechDriver._send`` already translates this to
  ``AerotechError``.
* ``#<...>``   FAULT — command was accepted *but* executing it
  triggered a controller-level axis fault. The driver does NOT raise
  on ``#`` (see ``aerotech_positioner.py:172`` — only ``!`` raises),
  so this probe inspects the raw response itself.

Mapping AeroBasic → the same bucket system the SCPI probes use keeps
the GUI uniform:

  ACK / parses to number ......... SUPPORTED
  ``#`` prefix returned .......... SUPPORTED_BUT_FAULT (header
                                   recognised, controller in fault)
  AerotechError raised ........... UNSUPPORTED (NAK — bad command)
  timeout / unexpected ........... UNKNOWN

Why this is read-only
---------------------
**No ``ENABLE`` / ``HOME`` / ``MOVEABS`` / ``FAULTACK`` / ``DISABLE``
ever leaves this probe.** A chamber turntable rotating during what the
operator thinks is a "health check" risks pulling cabling, RF cables,
or hitting a probe arm. The probe stays on pure feedback queries:
``PFBK`` (position), ``VFBK`` (velocity), ``AXISSTATUS`` (status
bitmask), ``AXISFAULT`` (fault bitmask).

The probe **does not call** ``driver.connect()`` either — the driver's
``connect`` issues ``ACKNOWLEDGEALL`` + ``ENABLE`` on its way in, both
of which mutate axis state. The probe assumes the HAL session already
came up at startup; if it didn't, it reports "driver not connected"
and bails so the operator can fix the IP / firewall / Socket2 toggle
and reload HAL.
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


# ---------------------------------------------------------------------------
# AeroBasic AXISSTATUS bitmask — only the bits we surface in the probe
# report. Definitions match ``aerotech_positioner.py:67-75`` (AxisStatusBit).
# ---------------------------------------------------------------------------
_STATUS_BITS: List[Tuple[int, str]] = [
    (0,  "Enabled"),
    (1,  "Homed"),
    (2,  "InPosition"),
    (3,  "MoveActive"),
    (10, "Fault"),
]


# ---------------------------------------------------------------------------
# Read-only AeroBasic command set. {az} / {el} are substituted with the
# axis names the driver was configured with (``azimuth_axis`` /
# ``elevation_axis``; defaults X / Y).
#
# Tuple: (name, command_template, is_critical, description)
#
# *Critical* commands are those without which we couldn't run a probe-loss
# or commissioning sweep: PFBK gives us position-feedback proof, AXISSTATUS
# is needed for the WAIT-INPOS loop, AXISFAULT tells us "is the controller
# safe to drive". Y-axis variants stay non-critical because some chambers
# only have azimuth.
# ---------------------------------------------------------------------------
AEROBASIC_READONLY: List[Tuple[str, str, bool, str]] = [
    ("PFBK_AZ",      "PFBK({az})",        True,  "azimuth position feedback (deg)"),
    ("PFBK_EL",      "PFBK({el})",        False, "elevation position feedback (deg, skipped if single-axis)"),
    ("AXISSTAT_AZ",  "AXISSTATUS({az})",  True,  "azimuth status bitmask"),
    ("AXISSTAT_EL",  "AXISSTATUS({el})",  False, "elevation status bitmask"),
    ("AXISFAULT_AZ", "AXISFAULT({az})",   True,  "azimuth fault bitmask (0 = healthy)"),
    ("AXISFAULT_EL", "AXISFAULT({el})",   False, "elevation fault bitmask"),
    ("VFBK_AZ",      "VFBK({az})",        False, "azimuth velocity feedback (≈0 at rest)"),
    ("VFBK_EL",      "VFBK({el})",        False, "elevation velocity feedback"),
]


# Names in AEROBASIC_READONLY whose UNSUPPORTED outcome is acceptable.
# Today's controllers handle PFBK/VFBK/AXISSTATUS/AXISFAULT uniformly so
# this set is empty; kept here as a hook for future controller variants.
_EXPECTED_UNSUPPORTED: frozenset[str] = frozenset()


def _decode_status_bits(value: int) -> str:
    """Human-readable bit summary, e.g. '0x90480005 (Enabled, InPosition)'.

    AeroBasic returns the bitmask as a large ASCII float (Ensemble's 32-bit
    status word has the sign bit set for axes in normal operation —
    "ServoEnabled" lives in the high half). Python's ``int(float(...))``
    of that float carries the sign through, so we mask back to 32-bit
    unsigned before printing — otherwise hex renders as ``0x-6FB7FFFB``
    which the operator can't visually intersect with a bit table.
    """
    u32 = value & 0xFFFFFFFF
    flags = [name for bit, name in _STATUS_BITS if u32 & (1 << bit)]
    return f"0x{u32:08X}" + (f" ({', '.join(flags)})" if flags else "")


def _categorize(response: Optional[str], exception: Optional[BaseException]) -> str:
    """Map (response, raised exception) → status bucket."""
    if exception is not None:
        # Driver translates NAK (! prefix) → AerotechError. Timeout →
        # asyncio.TimeoutError. Connection drop → AerotechError("Not
        # connected") or AerotechError("Connection lost ... reconnect
        # failed").
        if isinstance(exception, asyncio.TimeoutError):
            return "UNKNOWN"
        msg = str(exception)
        if "Not connected" in msg or "reconnect failed" in msg.lower():
            return "UNKNOWN"
        # AerotechError on ! prefix = controller rejected the command.
        return "UNSUPPORTED"
    if response is None:
        return "UNKNOWN"
    # Empty string means the driver got EOF on readline (controller-side
    # half-close, common on idle TCP) but didn't raise — the pre-#14 idle-
    # close behaviour. Without this guard, the categorizer treats it as
    # SUPPORTED and the probe summary says "8/8 supported" on a dead
    # session. With #14 in place ``_send`` synthesises ConnectionResetError
    # on EOF, so this branch is defence-in-depth: still triggered if a
    # driver _send returns "" for any future reason (e.g. controller
    # ACK with no payload — which we don't issue here, but).
    if response == "":
        return "UNKNOWN"
    # _send strips the leading '%' already, so a fault response that the
    # driver doesn't translate comes back starting with '#'.
    if response.startswith("#"):
        return "SUPPORTED_BUT_FAULT"
    return "SUPPORTED"


_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _parse_number(raw: str) -> Optional[float]:
    """Pull the first numeric token out of an AeroBasic reply.
    Returns None when the reply is non-numeric (e.g. empty ACK)."""
    m = _FLOAT_RE.search(raw or "")
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Sequence metadata
# ---------------------------------------------------------------------------
metadata = SequenceMetadata(
    name="Aerotech positioner health probe",
    description=(
        "Two-phase Aerotech (A3200 / Ensemble) readiness check over the "
        "existing AeroBasic ASCII TCP session. Phase A probes 8 read-only "
        "commands (PFBK / VFBK / AXISSTATUS / AXISFAULT × {az,el}) and "
        "categorises each as SUPPORTED / FAULT / UNSUPPORTED / UNKNOWN. "
        "Phase B exercises the driver's read-only APIs (get_position, "
        "get_metrics, get_capabilities). ~2 s end-to-end. "
        "Tells you the turntable is alive, on the right IP/port, the "
        "configured axis names match the controller, and no axis is "
        "stuck in fault — before any real movement is commanded. "
        "Strictly read-only: NEVER sends ENABLE / HOME / MOVEABS / "
        "FAULTACK; safe to run in a chamber with cabling attached."
    ),
    required_categories=["positioner"],
    params_schema=[
        {
            "name": "include_supported",
            "label": "Detail every SUPPORTED command too (default: only flag failures and faults)",
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
    # Position/velocity reads are non-mutating, but we explicitly stay
    # OFF during a real test in case the testbench is mid-WAIT-INPOS —
    # our PFBK polling could race the test's own readback. (And there's
    # no reason a chamber test sweep needs a parallel health check.)
    safe_during_test=False,
)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def _probe_one(
    driver: Any,
    *,
    name: str,
    command: str,
    is_critical: bool,
    description: str,
) -> Tuple[SequenceStepResult, str, Optional[str]]:
    """Send one AeroBasic command and classify the outcome.
    Returns (step_result, status_bucket, raw_response)."""
    started = time.monotonic()
    response: Optional[str] = None
    exc: Optional[BaseException] = None
    try:
        response = await _maybe_await(driver._send(command))  # noqa: SLF001
    except asyncio.TimeoutError as e:
        exc = e
    except Exception as e:  # noqa: BLE001  — AerotechError + anything else
        exc = e

    status = _categorize(response, exc)
    duration_ms = int((time.monotonic() - started) * 1000)

    # Build a useful detail string. For status-/fault-bitmask commands
    # we decode the bits so a glance tells the operator what's on.
    detail_parts: List[str] = [status]
    if is_critical:
        detail_parts[0] += " ★"
    if status == "SUPPORTED" and response is not None:
        num = _parse_number(response)
        if num is not None and ("AXISSTATUS" in command or "AXISFAULT" in command):
            detail_parts.append(_decode_status_bits(int(num)))
        elif num is not None:
            detail_parts.append(f"= {num:.4f}")
        else:
            detail_parts.append(f"raw={response!r}")
    elif status == "SUPPORTED_BUT_FAULT":
        detail_parts.append(f"controller fault: {response!r}")
    elif status == "UNSUPPORTED":
        detail_parts.append(f"NAK / unsupported: {exc}")
    elif status == "UNKNOWN":
        detail_parts.append(f"{type(exc).__name__ if exc else 'no-response'}: {exc}")
    detail_parts.append(f"— {description}")

    success = status == "SUPPORTED" or (
        status == "UNSUPPORTED" and name in _EXPECTED_UNSUPPORTED
    )
    return (
        SequenceStepResult(
            label=f"{name} → {command}",
            success=success,
            detail=" ".join(detail_parts),
            duration_ms=duration_ms,
        ),
        status,
        response,
    )


async def _run_aerobasic_surface(
    driver: Any,
    *,
    include_supported: bool,
    log: Callable[[str], None],
) -> Tuple[List[SequenceStepResult], Dict[str, int], List[str], Dict[str, Any]]:
    """Phase A. Returns (steps, status_counts, critical_failures, extras)."""
    az = getattr(driver, "az_axis", "X")
    el = getattr(driver, "el_axis", "Y")
    # ``RealAerotechDriver.is_single_axis`` is populated in connect(); honour
    # it so chamber azimuth-only turntables don't drown the probe report in
    # 4 expected-NAK lines for the absent Y axis.
    single_axis = bool(getattr(driver, "is_single_axis", False))
    steps: List[SequenceStepResult] = []
    counts = {"SUPPORTED": 0, "SUPPORTED_BUT_FAULT": 0, "UNSUPPORTED": 0, "UNKNOWN": 0}
    critical_failures: List[str] = []
    extras: Dict[str, Any] = {
        "az_axis": az,
        "el_axis": el,
        "single_axis": single_axis,
        "axes_present": list(getattr(driver, "_axes_present", []) or []),
    }

    # Filter Y-axis probes out when the controller is single-axis: emitting
    # 4 UNSUPPORTED rows for axes that legitimately don't exist would noise
    # up the GUI and make a real Y failure on a 2-axis box indistinguishable.
    commands = [
        c for c in AEROBASIC_READONLY
        if not (single_axis and c[0].endswith("_EL"))
    ]

    log(
        f"  · Phase A: probing {len(commands)} read-only commands"
        + (f" (single-axis mode: {len(AEROBASIC_READONLY) - len(commands)} Y-axis probes skipped)"
           if single_axis else "")
        + " ..."
    )

    # Fail-fast on consecutive UNKNOWN (timeout / not-connected): if the
    # session is dead, every remaining probe will eat its full timeout
    # (~10 s by default) for the same diagnostic. Three is enough signal.
    consecutive_unknown = 0
    aborted_early = False

    for name, template, is_critical, desc in commands:
        command = template.format(az=az, el=el)
        step, status, response = await _probe_one(
            driver,
            name=name,
            command=command,
            is_critical=is_critical,
            description=desc,
        )
        counts[status] = counts.get(status, 0) + 1

        if not step.success and is_critical:
            critical_failures.append(name)

        if status == "UNKNOWN":
            consecutive_unknown += 1
        else:
            consecutive_unknown = 0

        # Capture the live position + status bitmasks for the extras
        # payload (downstream summaries like "/aerotech: az=180° at rest"
        # can use this without re-querying).
        if status == "SUPPORTED" and response is not None:
            num = _parse_number(response)
            if num is not None:
                if name == "PFBK_AZ":
                    extras["azimuth_deg"] = num
                elif name == "PFBK_EL":
                    extras["elevation_deg"] = num
                elif name == "AXISSTAT_AZ":
                    extras["axis_status_az"] = int(num)
                elif name == "AXISSTAT_EL":
                    extras["axis_status_el"] = int(num)
                elif name == "AXISFAULT_AZ":
                    extras["axis_fault_az"] = int(num)
                elif name == "AXISFAULT_EL":
                    extras["axis_fault_el"] = int(num)
                elif name == "VFBK_AZ":
                    extras["velocity_az_deg_s"] = num
                elif name == "VFBK_EL":
                    extras["velocity_el_deg_s"] = num

        emit = (
            include_supported
            or is_critical
            or status in ("SUPPORTED_BUT_FAULT", "UNSUPPORTED", "UNKNOWN")
        )
        if emit:
            steps.append(step)

        if consecutive_unknown >= 3:
            log(
                f"  ✗ ABORTING Phase A — 3 consecutive timeouts / no-response. "
                f"Last probed: {name}. Driver session likely dropped; "
                f"reload HAL (POST /api/v1/instruments/hal/reload) and retry."
            )
            steps.append(SequenceStepResult(
                label="ABORTED",
                success=False,
                detail=(
                    "3 consecutive UNKNOWN responses — Aerotech TCP "
                    "session is dead. Reload HAL and retry."
                ),
                duration_ms=0,
            ))
            aborted_early = True
            break

    extras["phase_a_aborted"] = aborted_early
    log(
        f"  · Phase A done: "
        f"{counts['SUPPORTED']} supported, "
        f"{counts['SUPPORTED_BUT_FAULT']} fault, "
        f"{counts['UNSUPPORTED']} unsupported, "
        f"{counts['UNKNOWN']} unknown"
    )
    if critical_failures:
        log(f"  ✗ CRITICAL FAILURES: {sorted(critical_failures)}")
    # If any axis fault bit is set the operator MUST see it before
    # commanding motion — log it loudly even when the status is
    # technically SUPPORTED (header recognised, just the controller is
    # reporting a fault state).
    for axis_key, raw_key in (("az_axis", "axis_fault_az"), ("el_axis", "axis_fault_el")):
        fault = extras.get(raw_key)
        if isinstance(fault, int) and fault != 0:
            log(
                f"  ⚠ {extras[axis_key]} axis AXISFAULT = 0x{fault:04X} "
                f"(non-zero) — controller in fault state; FAULTACK required "
                f"before motion."
            )

    return steps, counts, critical_failures, extras


async def _run_functional_check(
    name: str,
    fn_factory: Callable[[Any], Any],
    driver: Any,
    *,
    log: Callable[[str], None],
) -> SequenceStepResult:
    """One driver-API smoke check. Raise → fail; None tolerated as
    informational (some drivers return None when their cache is fresh)."""
    started = time.monotonic()
    try:
        result = await _maybe_await(fn_factory(driver))
    except AttributeError as e:
        log(f"  ✗ {name}: driver lacks method ({e})")
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
    pos = drivers.get("positioner")
    if pos is None:
        return SequenceRunResult(
            success=False,
            summary=(
                "No positioner driver loaded. Bind an Aerotech instrument "
                "to category 'positioner' with a valid IP (default port 8000 "
                "= Ensemble Socket2), then reload HAL "
                "(POST /api/v1/instruments/hal/reload)."
            ),
        )

    # Refuse mock drivers — the probe would silently pass against a
    # MockPositioner and tell the operator nothing about the real
    # turntable. (Same gate the SCPI Console uses against MockBaseStation.)
    cls_name = type(pos).__name__
    if cls_name.startswith("Mock"):
        return SequenceRunResult(
            success=False,
            summary=(
                f"positioner driver is {cls_name} (mock). The probe needs "
                "a real Aerotech driver to be meaningful. Check the "
                "instrument's connection config: IP must be set + reachable, "
                "or driver_class must be 'RealAerotechDriver'."
            ),
        )

    if not hasattr(pos, "_send"):
        return SequenceRunResult(
            success=False,
            summary=(
                f"positioner driver {cls_name} doesn't expose _send; "
                "this probe targets the AeroBasic ASCII protocol."
            ),
        )

    # Driver must have an open TCP session. We don't call connect()
    # ourselves — it issues ACKNOWLEDGEALL + ENABLE, mutating axis state.
    if getattr(pos, "_writer", None) is None:
        return SequenceRunResult(
            success=False,
            summary=(
                f"positioner driver {cls_name} is not connected "
                "(_writer is None). HAL startup didn't bring it up — "
                "check the IP, that Ensemble Socket2 is enabled "
                "(ASCIICommandSetup.Enable Ethernet Socket 2 = True), "
                "and that the controller PC's firewall allows port 8000. "
                "Then reload HAL."
            ),
        )

    include_supported = bool(params.get("include_supported", False))
    do_functional = bool(params.get("functional_checks", True))

    az = getattr(pos, "az_axis", "X")
    el = getattr(pos, "el_axis", "Y")
    ip = getattr(pos, "ip_address", "?")
    port = getattr(pos, "port", "?")
    log(f"  ✓ Driver bound: {cls_name} @ {ip}:{port}, axes az={az!r} el={el!r}")

    steps_a, counts, critical_failures, extras = await _run_aerobasic_surface(
        pos, include_supported=include_supported, log=log,
    )

    steps_b: List[SequenceStepResult] = []
    functional_failures = 0
    if do_functional and not extras.get("phase_a_aborted"):
        log("  · Phase B: driver API smoke ...")
        checks = [
            ("get_position()",     lambda d: d.get_position()),
            ("get_metrics()",      lambda d: d.get_metrics()),
            ("get_capabilities()", lambda d: d.get_capabilities()),
        ]
        for name, factory in checks:
            step = await _run_functional_check(name, factory, pos, log=log)
            steps_b.append(step)
            if not step.success:
                functional_failures += 1

    # An axis reporting a non-zero fault bitmask is not a "command
    # failed" but it IS a blocker for any subsequent motion — surface it
    # as a failure so the operator can't just glance at a green probe
    # and command MOVEABS.
    axis_in_fault = bool(
        extras.get("axis_fault_az") or extras.get("axis_fault_el")
    )

    success = (
        not critical_failures
        and functional_failures == 0
        and not extras.get("phase_a_aborted")
        and not axis_in_fault
    )

    if extras.get("phase_a_aborted"):
        summary = (
            "ABORTED: Aerotech TCP session looks dead (3 consecutive "
            "UNKNOWN responses). Reload HAL and retry; if it persists, "
            "check the Ensemble PC is up, Socket2 is enabled, and port "
            "8000 is open in the host firewall."
        )
    elif success:
        az_pos = extras.get("azimuth_deg")
        el_pos = extras.get("elevation_deg")
        pos_str = (
            f"position: az={az_pos:.2f}°" + (f" el={el_pos:.2f}°" if el_pos is not None else "")
            if az_pos is not None else "position not read"
        )
        total_probed = sum(counts.values())
        summary = (
            f"Aerotech health OK — {pos_str}, no axis fault, "
            f"{counts['SUPPORTED']}/{total_probed} commands supported"
            + (" (single-axis turntable)" if extras.get("single_axis") else "")
            + (
                f"; {len(steps_b)} driver-API checks passed"
                if do_functional else ""
            )
        )
    else:
        parts: List[str] = []
        if critical_failures:
            parts.append(
                f"{len(critical_failures)} critical AeroBasic failed: "
                f"{sorted(critical_failures)}"
            )
        if axis_in_fault:
            faults = []
            if extras.get("axis_fault_az"):
                faults.append(f"{az}=0x{extras['axis_fault_az']:04X}")
            if extras.get("axis_fault_el"):
                faults.append(f"{el}=0x{extras['axis_fault_el']:04X}")
            parts.append(f"axis fault active: {', '.join(faults)}")
        if functional_failures:
            parts.append(f"{functional_failures} driver-API check(s) failed")
        summary = "BLOCKER: " + "; ".join(parts)

    return SequenceRunResult(
        success=success,
        summary=summary,
        steps=steps_a + steps_b,
        extra={
            **extras,
            "driver_class": cls_name,
            "ip": ip,
            "port": port,
            "counts": counts,
            "critical_failures": sorted(critical_failures),
            "commands_probed": sum(counts.values()),
            "functional_failures": functional_failures,
            "include_supported": include_supported,
            "functional_checks": do_functional,
            "axis_in_fault": axis_in_fault,
        },
    )
