#!/usr/bin/env python3
"""Aerotech Ensemble ASCII (Socket2) read-only probe.

Bare-socket equivalent of ``app/diagnostics/sequences/aerotech_positioner_health.py``
— skips HAL/GUI so we can verify a freshly-enabled Socket2 in 2 seconds
without first wiring the IP into the DB and reloading the driver.

Strict read-only: sends only PFBK / VFBK / AXISSTATUS / AXISFAULT. NEVER
ENABLE / HOME / MOVEABS / FAULTACK / ABORT. A chamber turntable cannot
be allowed to interpret a wild write as motion.

Usage:
    python3 scripts/site-debug/aerotech_ensemble_ascii_probe.py \\
        --host 192.168.0.16 --port 8000 [--axes X Y]
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from typing import Optional


READ_ONLY_COMMANDS = [
    ("PFBK",       "position feedback (deg)"),
    ("AXISSTATUS", "axis status bitmask"),
    ("AXISFAULT",  "fault bitmask (0 = healthy)"),
    ("VFBK",       "velocity feedback (deg/s)"),
]


# AXISSTATUS bits we surface — keep in sync with
# aerotech_positioner.py:AxisStatusBit.
STATUS_BITS = [
    (0,  "Enabled"),
    (1,  "Homed"),
    (2,  "InPosition"),
    (3,  "MoveActive"),
    (10, "Fault"),
]


def decode_status(value: int) -> str:
    # AeroBasic returns the bitmask as a possibly-large ASCII float
    # (e.g. "2415919104.000000" for 0x90000000). Python's int() of that
    # gives a >32-bit value with the sign bit interpreted, so mask back
    # to 32-bit unsigned before pretty-printing.
    u32 = value & 0xFFFFFFFF
    flags = [name for bit, name in STATUS_BITS if u32 & (1 << bit)]
    return f"0x{u32:08X}" + (f" ({', '.join(flags)})" if flags else "")


def send_one(sock: socket.socket, cmd: str, *, timeout: float = 3.0) -> tuple[str, Optional[str], int]:
    """Send `cmd\\n`, read one line, classify.
    Returns (status, decoded_value, elapsed_ms) where status is one of
    SUPPORTED / SUPPORTED_BUT_FAULT / UNSUPPORTED / UNKNOWN."""
    sock.settimeout(timeout)
    t0 = time.monotonic()
    try:
        sock.sendall((cmd + "\n").encode("ascii"))
        # AeroBasic responses are short; read up to 256 bytes then split on first newline.
        data = sock.recv(256).decode("ascii", errors="replace").strip()
    except socket.timeout:
        return ("UNKNOWN", "timeout", int((time.monotonic() - t0) * 1000))
    except Exception as e:
        return ("UNKNOWN", f"{type(e).__name__}: {e}", int((time.monotonic() - t0) * 1000))
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if not data:
        return ("UNKNOWN", "empty response", elapsed_ms)
    head, body = data[0], data[1:].strip()
    if head == "%":
        return ("SUPPORTED", body if body else "(ACK, no data)", elapsed_ms)
    if head == "!":
        return ("UNSUPPORTED", f"NAK: {body}", elapsed_ms)
    if head == "#":
        return ("SUPPORTED_BUT_FAULT", f"FAULT: {body}", elapsed_ms)
    return ("UNKNOWN", f"unexpected leading char {head!r}: {data!r}", elapsed_ms)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.16")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--axes", nargs="+", default=["X", "Y"])
    ap.add_argument("--connect-timeout", type=float, default=3.0)
    args = ap.parse_args()

    print(f"Connecting to Aerotech ASCII socket at {args.host}:{args.port} ...")
    try:
        s = socket.create_connection((args.host, args.port), timeout=args.connect_timeout)
    except ConnectionRefusedError:
        print(f"  ✗ CLOSED (RST) — Socket2 service not listening.")
        print(f"    Did you Save Parameters to Controller AND Reset Controller?")
        return 2
    except socket.timeout:
        print(f"  ✗ FILTERED — SYN dropped. Check firewall on host side.")
        return 2
    except OSError as e:
        print(f"  ✗ connect failed: {e}")
        return 2
    print(f"  ✓ TCP connected.")

    summary: dict[str, dict[str, str]] = {}
    try:
        for axis in args.axes:
            print(f"\n--- axis {axis!r} ---")
            summary[axis] = {}
            for cmd_base, desc in READ_ONLY_COMMANDS:
                # Status/fault have function-call syntax; PFBK/VFBK same.
                cmd = f"{cmd_base}({axis})"
                status, payload, elapsed = send_one(s, cmd)
                # Decode bitmasks for AXISSTATUS / AXISFAULT.
                pretty = payload or ""
                if status == "SUPPORTED" and cmd_base in ("AXISSTATUS", "AXISFAULT"):
                    try:
                        val = int(float(payload or "0"))
                        pretty = decode_status(val)
                    except (TypeError, ValueError):
                        pass
                tag = {
                    "SUPPORTED": "✓",
                    "SUPPORTED_BUT_FAULT": "⚠",
                    "UNSUPPORTED": "✗",
                    "UNKNOWN": "?",
                }[status]
                print(f"  {tag} {cmd:18s} → [{status}] {pretty}   ({elapsed}ms)  // {desc}")
                summary[axis][cmd_base] = status

        # Verdict.
        print("\n=== verdict ===")
        any_axis_alive = False
        any_axis_fault = False
        for axis, results in summary.items():
            status_set = set(results.values())
            if results.get("PFBK") == "SUPPORTED" and results.get("AXISSTATUS") == "SUPPORTED":
                any_axis_alive = True
                print(f"  ✓ axis {axis!r}: communication OK, position+status readable")
            else:
                print(f"  ✗ axis {axis!r}: at least one critical read failed — {results}")
            if results.get("AXISFAULT") == "SUPPORTED_BUT_FAULT":
                any_axis_fault = True
                print(f"  ⚠ axis {axis!r}: AXISFAULT returned FAULT — clear faults before motion")

        if any_axis_alive and not any_axis_fault:
            print("\nReady to wire RealAerotechDriver into HAL.")
            return 0
        if any_axis_fault:
            print("\nComms OK, but a fault is active. Operator must FAULTACK from "
                  "Composer/Console (NOT from this probe) before any motion.")
            return 0
        return 1
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())
