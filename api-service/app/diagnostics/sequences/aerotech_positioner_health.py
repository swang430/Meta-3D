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
  error. ``RealAerotechDriver._send`` translates this to the dedicated
  ``AerotechCommandRejected`` exception.
* ``#<...>``   FAULT — command was accepted *but* executing it
  triggered a controller-level task fault. The real driver raises a
  dedicated task-fault exception so writes cannot mistake it for success.

Mapping AeroBasic → the same bucket system the SCPI probes use keeps
the GUI uniform:

  ACK / parses to number ......... SUPPORTED
  ``#`` prefix returned .......... SUPPORTED_BUT_FAULT (header
                                   recognised, controller in fault)
  AerotechCommandRejected raised . UNSUPPORTED (NAK — bad command)
  timeout / unexpected ........... UNKNOWN

Why this is read-only
---------------------
**No ``ENABLE`` / ``HOME`` / ``MOVEABS`` / ``FAULTACK`` / ``DISABLE``
ever leaves this probe.** A chamber turntable rotating during what the
operator thinks is a "health check" risks pulling cabling, RF cables,
or hitting a probe arm. The probe stays on pure feedback/parameter
queries: ``PFBK`` (position), ``VFBK`` (velocity), ``AXISSTATUS``
(status bitmask), ``AXISFAULT`` (fault bitmask), and ``GETPARM`` reads
for configured user units, software limits, and speed parameters.

The probe **does not call** ``driver.connect()`` either. It assumes the HAL session already
came up at startup; if it didn't, it reports "driver not connected"
and bails so the operator can fix the IP / firewall / Socket2 toggle
and reload HAL.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    driver_not_loaded_summary,
    SequenceStepResult,
)
from app.hal.aerotech_positioner import (
    AerotechCommandRejected,
    AerotechTaskFault,
)
from app.services.diagnostic_context import DiagnosticContext
from app.services.instrument_hal_service import is_mock_driver


# ---------------------------------------------------------------------------
# Read-only AeroBasic command set. {az} / {el} are substituted with the
# axis names the driver was configured with (``azimuth_axis`` /
# ``elevation_axis``; defaults X / Y).
#
# Tuple: (name, command_template, is_critical, description)
#
# *Critical* commands are those used by the supported local truth chain:
# PFBK gives position feedback, VFBK proves zero velocity, and AXISFAULT is
# retained as a raw diagnostic value. AXISSTATUS remains raw evidence: the
# Ensemble 3.04 header defines the bits, but input polarity/configuration must
# still be interpreted against the live controller setup.
#
# GETPARM sources in the local Ensemble 3.04 vendor package:
# * Ensemble/Samples/Cpp/ASCII/OperatorInterface/Lin/Program.cpp:436 gives
#   Socket2 ASCII syntax ``GETPARM <axis>, <numeric-parameter-id>``.
# * Ensemble/CLibrary/Include/ParameterId.h gives the exact IDs below.
# All reads target only the configured azimuth axis and never mutate
# controller parameters.
# ---------------------------------------------------------------------------
AEROBASIC_READONLY: List[Tuple[str, str, bool, str]] = [
    ("PFBK_AZ",      "PFBK({az})",        True,  "azimuth position feedback (controller user units)"),
    ("PFBK_EL",      "PFBK({el})",        False, "elevation position feedback (controller user units, skipped if single-axis)"),
    ("AXISSTAT_AZ",  "AXISSTATUS({az})",  False, "azimuth raw status bitmask (bit meanings unverified)"),
    ("AXISSTAT_EL",  "AXISSTATUS({el})",  False, "elevation raw status bitmask (bit meanings unverified)"),
    ("AXISFAULT_AZ", "AXISFAULT({az})",   True,  "azimuth fault bitmask (0 = healthy)"),
    ("AXISFAULT_EL", "AXISFAULT({el})",   False, "elevation fault bitmask"),
    ("VFBK_AZ",      "VFBK({az})",        True,  "azimuth velocity feedback (controller user units/s; exact 0 proves stopped)"),
    ("VFBK_EL",      "VFBK({el})",        False, "elevation velocity feedback"),
    ("UNITS_NAME_AZ", "GETPARM {az}, 129", False, "configured azimuth user-unit name (observed, not automatically attested)"),
    ("COUNTS_PER_UNIT_AZ", "GETPARM {az}, 2", False, "encoder counts per configured azimuth user unit"),
    ("SOFTWARE_LIMIT_SETUP_AZ", "GETPARM {az}, 210", False, "raw software-limit enable/setup value"),
    ("SOFTWARE_LIMIT_LOW_AZ", "GETPARM {az}, 37", False, "configured azimuth software low limit (controller user units)"),
    ("SOFTWARE_LIMIT_HIGH_AZ", "GETPARM {az}, 38", False, "configured azimuth software high limit (controller user units)"),
    ("DEFAULT_SPEED_AZ", "GETPARM {az}, 71", False, "configured default speed (controller user units/s; not site approval)"),
    ("MAX_JOG_SPEED_AZ", "GETPARM {az}, 123", False, "configured maximum jog speed (controller user units/s; not site approval)"),
]

_MOTION_PARAMETER_PROBES: frozenset[str] = frozenset({
    "UNITS_NAME_AZ",
    "COUNTS_PER_UNIT_AZ",
    "SOFTWARE_LIMIT_SETUP_AZ",
    "SOFTWARE_LIMIT_LOW_AZ",
    "SOFTWARE_LIMIT_HIGH_AZ",
    "DEFAULT_SPEED_AZ",
    "MAX_JOG_SPEED_AZ",
})
_TEXT_RESPONSE_PROBES: frozenset[str] = frozenset({"UNITS_NAME_AZ"})


# Names in AEROBASIC_READONLY whose UNSUPPORTED outcome is acceptable.
# Today's controllers handle PFBK/VFBK/AXISSTATUS/AXISFAULT uniformly so
# this set is empty; kept here as a hook for future controller variants.
_EXPECTED_UNSUPPORTED: frozenset[str] = frozenset()


def _decode_status_bits(value: int) -> str:
    """Render the raw unsigned word without inventing undocumented labels.

    Historical controllers can return the raw word in signed decimal form.
    Python's ``int(float(...))`` carries that sign through, so mask to the
    existing 32-bit display width before printing.  This is presentation only:
    no bit is assigned a semantic label without a checked-in vendor table.
    """
    u32 = value & 0xFFFFFFFF
    return f"0x{u32:08X} (raw; bit meanings unverified)"


def _categorize(response: Optional[str], exception: Optional[BaseException]) -> str:
    """Map (response, raised exception) → status bucket."""
    if exception is not None:
        if isinstance(exception, AerotechTaskFault):
            return "SUPPORTED_BUT_FAULT"
        if isinstance(exception, AerotechCommandRejected):
            return "UNSUPPORTED"
        # Timeout, transport loss, and any unexpected driver error do not
        # prove that the command header is unsupported.
        return "UNKNOWN"
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


def _parse_number(raw: str) -> Optional[float]:
    """Accept only one complete finite numeric controller response."""
    try:
        value = float(raw.strip())
    except (AttributeError, TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _parse_bitmask(raw: str) -> Optional[int]:
    """Accept one 32-bit integer, including signed-decimal wire form."""
    try:
        value = float(raw.strip())
    except (AttributeError, TypeError, ValueError):
        return None
    if not math.isfinite(value) or not value.is_integer():
        return None
    integer = int(value)
    if integer < -(1 << 31) or integer > 0xFFFFFFFF:
        return None
    return integer & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Sequence metadata
# ---------------------------------------------------------------------------
metadata = SequenceMetadata(
    name="Aerotech positioner health probe",
    description=(
        "Two-phase Aerotech (A3200 / Ensemble) readiness check over the "
        "existing AeroBasic ASCII TCP session. Phase A probes read-only "
        "PFBK / VFBK / AXISSTATUS / AXISFAULT axis state plus seven "
        "azimuth GETPARM unit/limit/speed values, and "
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
        if name in _TEXT_RESPONSE_PROBES:
            text = response.strip()
            if not text:
                status = "UNKNOWN"
                detail_parts[0] = "UNKNOWN" + (" ★" if is_critical else "")
                detail_parts.append(f"invalid text raw={response!r}")
            else:
                detail_parts.append(f"= {text!r}")
        elif "AXISSTATUS" in command or "AXISFAULT" in command:
            bitmask = _parse_bitmask(response)
            if bitmask is None:
                status = "UNKNOWN"
                detail_parts[0] = "UNKNOWN" + (" ★" if is_critical else "")
                detail_parts.append(f"invalid bitmask raw={response!r}")
            else:
                detail_parts.append(_decode_status_bits(bitmask))
        elif num is not None:
            detail_parts.append(f"= {num:.4f}")
        else:
            status = "UNKNOWN"
            detail_parts[0] = "UNKNOWN" + (" ★" if is_critical else "")
            detail_parts.append(f"invalid numeric raw={response!r}")
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
        "degree_units_verified": (
            (getattr(driver, "config", {}) or {}).get("motion_truth_units_verified")
            is True
            and str(
                (getattr(driver, "config", {}) or {}).get(
                    "motion_truth_user_units", ""
                )
            ).strip().lower() == "degree"
        ),
    }

    # Filter Y-axis probes out when the controller is single-axis: emitting
    # 4 UNSUPPORTED rows for axes that legitimately don't exist would noise
    # up the GUI and make a real Y failure on a 2-axis box indistinguishable.
    commands = [
        c for c in AEROBASIC_READONLY
        if not (single_axis and c[0].endswith("_EL"))
    ]
    elevation_truth_names = {"PFBK_EL", "VFBK_EL", "AXISFAULT_EL"}
    elevation_present = el in set(extras["axes_present"])

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
        effective_critical = is_critical or (
            elevation_present and name in elevation_truth_names
        )
        command = template.format(az=az, el=el)
        step, status, response = await _probe_one(
            driver,
            name=name,
            command=command,
            is_critical=effective_critical,
            description=desc,
        )
        counts[status] = counts.get(status, 0) + 1

        if not step.success and effective_critical:
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
            if name == "UNITS_NAME_AZ":
                extras["units_name_az"] = response.strip().strip('"\'')
            elif num is not None:
                if name == "PFBK_AZ":
                    extras["position_az_controller_units"] = num
                    if extras["degree_units_verified"]:
                        extras["azimuth_deg"] = num
                elif name == "PFBK_EL":
                    extras["position_el_controller_units"] = num
                    if extras["degree_units_verified"]:
                        extras["elevation_deg"] = num
                elif name == "AXISSTAT_AZ":
                    extras["axis_status_az"] = _parse_bitmask(response)
                elif name == "AXISSTAT_EL":
                    extras["axis_status_el"] = _parse_bitmask(response)
                elif name == "AXISFAULT_AZ":
                    extras["axis_fault_az"] = _parse_bitmask(response)
                elif name == "AXISFAULT_EL":
                    extras["axis_fault_el"] = _parse_bitmask(response)
                elif name == "VFBK_AZ":
                    extras["velocity_az_controller_units_s"] = num
                    if extras["degree_units_verified"]:
                        extras["velocity_az_deg_s"] = num
                elif name == "VFBK_EL":
                    extras["velocity_el_controller_units_s"] = num
                    if extras["degree_units_verified"]:
                        extras["velocity_el_deg_s"] = num
                elif name == "COUNTS_PER_UNIT_AZ":
                    extras["counts_per_unit_az"] = num
                elif name == "SOFTWARE_LIMIT_SETUP_AZ":
                    extras["software_limit_setup_az"] = (
                        int(num) if num.is_integer() else num
                    )
                elif name == "SOFTWARE_LIMIT_LOW_AZ":
                    extras["software_limit_low_az"] = num
                elif name == "SOFTWARE_LIMIT_HIGH_AZ":
                    extras["software_limit_high_az"] = num
                elif name == "DEFAULT_SPEED_AZ":
                    extras["default_speed_az"] = num
                elif name == "MAX_JOG_SPEED_AZ":
                    extras["max_jog_speed_az"] = num

        emit = (
            include_supported
            or effective_critical
            or name in _MOTION_PARAMETER_PROBES
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
                driver_not_loaded_summary("positioner")
                + "（Aerotech 默认端口 8000 = Ensemble Socket2；连上后 POST "
                "/api/v1/instruments/hal/reload 重载 HAL）"
            ),
        )

    # Refuse mock drivers — the probe would silently pass against a
    # MockPositioner and tell the operator nothing about the real
    # turntable. (Same gate the SCPI Console uses against MockBaseStation.)
    cls_name = type(pos).__name__
    if is_mock_driver(pos):
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

    # Driver must have an open TCP session. We don't call connect() ourselves:
    # lifecycle ownership belongs to HAL reload, while this sequence is only a
    # read-only observer of the already-open transport.
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
        and counts.get("SUPPORTED_BUT_FAULT", 0) == 0
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
        if extras.get("degree_units_verified"):
            pos_str = (
                f"position: az={az_pos:.2f}°"
                + (f" el={el_pos:.2f}°" if el_pos is not None else "")
                if az_pos is not None else "position not read"
            )
        else:
            raw_az = extras.get("position_az_controller_units")
            pos_str = (
                f"position raw={raw_az:.4f} controller-user-units (unit unverified)"
                if raw_az is not None else "position not read"
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
