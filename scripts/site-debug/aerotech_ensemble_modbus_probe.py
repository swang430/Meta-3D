#!/usr/bin/env python3
"""Aerotech Ensemble Modbus/TCP capability probe.

Goal: with zero changes to the controller's parameters, find out what the
Aerotech Modbus interface on 192.168.0.16:502 actually exposes. We need to
decide whether a Modbus-based positioner driver is viable BEFORE investing a
half day writing one — and without going through Configuration Manager to
enable Socket2 first (the alternative path that requires unsticking the
chamber PC's outbound TCP filter).

Strategy
--------
1. Walk the 4 Modbus data spaces with FC 01/02/03/04 across address 0..511
   in step-16 buckets. For each bucket where the read SUCCEEDS, drop into a
   dense scan of 0..127 around it. (Aerotech docs suggest registers live in
   the low hundreds, so this covers the typical map.)
2. For each region of readable holding/input registers, attempt to decode
   plausible numeric content as int16, uint16, float32 (both word orders) —
   so we can spot 'this looks like 0.0000 deg' vs 'this looks like a bit
   pattern'.
3. Same for coils / discrete inputs — bit values reveal status / fault /
   inposition signals.

Strict read-only. Never sends FC 05/06/15/16 (write coil / write register /
write multiple). A turntable cannot be allowed to interpret a wild write
as 'move'.

Usage
-----
    python3 scripts/site-debug/aerotech_ensemble_modbus_probe.py \\
        --host 192.168.0.16 --port 502 --unit 1

    # Or hit the curated dense windows directly (skip the sweep):
    python3 scripts/site-debug/aerotech_ensemble_modbus_probe.py --dense-only
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


# Modbus exception codes we care about for triage.
_EXC: dict[int, str] = {
    0x01: "IllegalFunction",
    0x02: "IllegalDataAddress",
    0x03: "IllegalDataValue",
    0x04: "SlaveDeviceFailure",
    0x05: "Acknowledge",
    0x06: "SlaveDeviceBusy",
    0x08: "MemoryParityError",
    0x0A: "GatewayPathUnavailable",
    0x0B: "GatewayTargetFailedToRespond",
}


@dataclass
class ModbusResult:
    """One Modbus request outcome."""
    ok: bool
    fc: int  # function code echoed back (or |0x80 on error)
    payload: bytes  # raw data bytes (after byte-count or directly, depending on FC)
    exc_code: Optional[int]  # set when ok=False
    elapsed_ms: int

    @property
    def exc_name(self) -> str:
        if self.exc_code is None:
            return ""
        return _EXC.get(self.exc_code, f"UnknownExc(0x{self.exc_code:02X})")


class ModbusClient:
    """Minimal Modbus/TCP client. Read-only by design — write FCs not implemented."""

    def __init__(self, host: str, port: int, unit: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.unit = unit
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._txid = 0

    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.settimeout(self.timeout)

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _request(self, fc: int, pdu_data: bytes) -> ModbusResult:
        assert self._sock is not None, "not connected"
        self._txid = (self._txid + 1) & 0xFFFF
        pdu = bytes([fc]) + pdu_data
        # MBAP: txid(2) + proto(2)=0 + length(2)=unit+pdu + unit(1)
        mbap = struct.pack(">HHHB", self._txid, 0x0000, 1 + len(pdu), self.unit)
        t0 = time.monotonic()
        self._sock.sendall(mbap + pdu)
        # Read MBAP first to know how much PDU to expect.
        head = self._recv_exact(7)
        rx_txid, rx_proto, rx_len, rx_unit = struct.unpack(">HHHB", head)
        if rx_txid != self._txid:
            raise RuntimeError(f"txid mismatch (expected {self._txid}, got {rx_txid})")
        body_len = rx_len - 1  # already consumed unit byte
        body = self._recv_exact(body_len) if body_len > 0 else b""
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if not body:
            return ModbusResult(ok=False, fc=fc, payload=b"", exc_code=None, elapsed_ms=elapsed_ms)
        rx_fc = body[0]
        if rx_fc & 0x80:
            exc = body[1] if len(body) >= 2 else None
            return ModbusResult(ok=False, fc=rx_fc, payload=b"", exc_code=exc, elapsed_ms=elapsed_ms)
        return ModbusResult(ok=True, fc=rx_fc, payload=body[1:], exc_code=None, elapsed_ms=elapsed_ms)

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed mid-frame")
            buf.extend(chunk)
        return bytes(buf)

    # --- read FCs ---

    def read_holding(self, addr: int, qty: int) -> ModbusResult:
        return self._request(0x03, struct.pack(">HH", addr, qty))

    def read_input(self, addr: int, qty: int) -> ModbusResult:
        return self._request(0x04, struct.pack(">HH", addr, qty))

    def read_coils(self, addr: int, qty: int) -> ModbusResult:
        return self._request(0x01, struct.pack(">HH", addr, qty))

    def read_discrete(self, addr: int, qty: int) -> ModbusResult:
        return self._request(0x02, struct.pack(">HH", addr, qty))


def parse_register_payload(payload: bytes) -> List[int]:
    """FC 03/04 response payload: byte_count + N pairs of bytes (big-endian)."""
    if not payload:
        return []
    byte_count = payload[0]
    body = payload[1:1 + byte_count]
    if len(body) != byte_count or byte_count % 2 != 0:
        return []
    return [int.from_bytes(body[i:i + 2], "big") for i in range(0, byte_count, 2)]


def parse_bit_payload(payload: bytes, qty: int) -> List[int]:
    """FC 01/02 response: byte_count + packed bits (LSB first within each byte)."""
    if not payload:
        return []
    byte_count = payload[0]
    body = payload[1:1 + byte_count]
    bits: List[int] = []
    for byte_val in body:
        for bit in range(8):
            if len(bits) < qty:
                bits.append((byte_val >> bit) & 1)
    return bits[:qty]


def decode_float32_pairs(regs: List[int]) -> List[Tuple[float, float]]:
    """For every adjacent pair (regs[i], regs[i+1]), return (BE, LE-word-swap)
    interpretations. Aerotech historically uses BE byte order with the high
    word first — but some integrators run word-swapped maps, so we report
    both. Returns one tuple per pair; len = len(regs) // 2."""
    out: List[Tuple[float, float]] = []
    for i in range(0, len(regs) - 1, 2):
        hi, lo = regs[i], regs[i + 1]
        be = struct.unpack(">f", struct.pack(">HH", hi, lo))[0]
        le = struct.unpack(">f", struct.pack(">HH", lo, hi))[0]
        out.append((be, le))
    return out


# ---------------------------------------------------------------------------
# Probe phases
# ---------------------------------------------------------------------------

def quick_identity(c: ModbusClient) -> None:
    """One read at addr 0, qty 1, on each space — establishes that the unit
    is alive and which FCs it implements at all."""
    print("\n=== Phase 0: existence probe (1 register/coil at addr 0) ===")
    for label, fn in [
        ("FC03 Holding ", c.read_holding),
        ("FC04 Input   ", c.read_input),
        ("FC01 Coils   ", c.read_coils),
        ("FC02 Discrete", c.read_discrete),
    ]:
        r = fn(0, 1)
        if r.ok:
            print(f"  {label} @0  -> OK   ({r.elapsed_ms}ms) raw={r.payload.hex()}")
        else:
            print(f"  {label} @0  -> ERR  ({r.elapsed_ms}ms) {r.exc_name}")


def sweep(c: ModbusClient, *, fn_name: str, fn, max_addr: int, step: int, qty: int) -> List[int]:
    """Coarse address scan. Returns the list of base addresses that read OK."""
    hits: List[int] = []
    print(f"\n=== Phase 1: sweep {fn_name} addr 0..{max_addr - 1} step={step} qty={qty} ===")
    for addr in range(0, max_addr, step):
        r = fn(addr, qty)
        if r.ok:
            hits.append(addr)
            print(f"  {fn_name} @{addr:4d}+{qty} OK  ({r.elapsed_ms}ms)")
        # Suppress IllegalDataAddress noise; print only oddities.
        elif r.exc_code is not None and r.exc_code != 0x02:
            print(f"  {fn_name} @{addr:4d}+{qty} ERR ({r.elapsed_ms}ms) {r.exc_name}")
    return hits


def dense_scan_registers(c: ModbusClient, *, fn_name: str, fn, start: int, end: int) -> None:
    """For a hit region: read qty=2 walks and report decoded values."""
    print(f"\n=== Phase 2: dense scan {fn_name} addr {start}..{end - 1} qty=2 (paired) ===")
    print(f"  {'addr':>6}  {'hex':>9}  {'u32':>10}  {'int16[0]':>9}  {'f32 BE':>14}  {'f32 LE-WS':>14}")
    for addr in range(start, end, 2):
        r = fn(addr, 2)
        if not r.ok:
            continue
        regs = parse_register_payload(r.payload)
        if len(regs) != 2:
            continue
        raw_hex = f"{regs[0]:04X}{regs[1]:04X}"
        as_u32 = (regs[0] << 16) | regs[1]
        as_i16 = struct.unpack(">h", struct.pack(">H", regs[0]))[0]
        f_be = struct.unpack(">f", struct.pack(">HH", regs[0], regs[1]))[0]
        f_le = struct.unpack(">f", struct.pack(">HH", regs[1], regs[0]))[0]
        # Suppress all-zero rows to keep signal high.
        if as_u32 == 0:
            continue
        print(f"  {addr:>6}  {raw_hex:>9}  {as_u32:>10}  {as_i16:>9}  {f_be:>14.4g}  {f_le:>14.4g}")


def dense_scan_bits(c: ModbusClient, *, fn_name: str, fn, start: int, end: int) -> None:
    print(f"\n=== Phase 2: dense scan {fn_name} bits {start}..{end - 1} ===")
    r = fn(start, end - start)
    if not r.ok:
        print(f"  request failed: {r.exc_name}")
        return
    bits = parse_bit_payload(r.payload, end - start)
    # Print only set bits — saves output.
    set_bits = [start + i for i, b in enumerate(bits) if b]
    if set_bits:
        print(f"  bits set: {set_bits}")
    else:
        print(f"  all {len(bits)} bits in range = 0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.0.16")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--unit", type=int, default=1, help="Modbus slave/unit ID (default 1)")
    ap.add_argument("--max-addr", type=int, default=512,
                    help="Upper bound for the coarse sweep")
    ap.add_argument("--sweep-step", type=int, default=16)
    ap.add_argument("--dense-only", action="store_true",
                    help="Skip coarse sweep, dense-scan curated Aerotech windows (0..127)")
    ap.add_argument("--also-unit", type=int, nargs="*", default=[],
                    help="Retry on alternative unit IDs if unit 1 fails (e.g. --also-unit 0 247)")
    args = ap.parse_args()

    units_to_try = [args.unit] + [u for u in args.also_unit if u != args.unit]

    for unit in units_to_try:
        print(f"\n{'#' * 64}")
        print(f"#   Probing {args.host}:{args.port}, Modbus unit ID = {unit}")
        print(f"{'#' * 64}")
        c = ModbusClient(args.host, args.port, unit)
        try:
            c.connect()
            print(f"  TCP connect OK ({args.host}:{args.port})")
        except Exception as e:
            print(f"  TCP connect FAILED: {e}")
            return 1

        try:
            quick_identity(c)

            if not args.dense_only:
                holding_hits = sweep(c, fn_name="FC03 Holding ", fn=c.read_holding,
                                     max_addr=args.max_addr, step=args.sweep_step, qty=2)
                input_hits   = sweep(c, fn_name="FC04 Input   ", fn=c.read_input,
                                     max_addr=args.max_addr, step=args.sweep_step, qty=2)
                coil_hits    = sweep(c, fn_name="FC01 Coils   ", fn=c.read_coils,
                                     max_addr=args.max_addr, step=args.sweep_step, qty=16)
                disc_hits    = sweep(c, fn_name="FC02 Discrete", fn=c.read_discrete,
                                     max_addr=args.max_addr, step=args.sweep_step, qty=16)
            else:
                holding_hits = [0]
                input_hits = [0]
                coil_hits = [0]
                disc_hits = [0]

            # Dense scan around the first hit of each space (or 0..127 if dense-only)
            if holding_hits:
                base = holding_hits[0]
                dense_scan_registers(c, fn_name="FC03 Holding ", fn=c.read_holding,
                                     start=base, end=base + 128)
            if input_hits:
                base = input_hits[0]
                dense_scan_registers(c, fn_name="FC04 Input   ", fn=c.read_input,
                                     start=base, end=base + 128)
            if coil_hits:
                base = coil_hits[0]
                dense_scan_bits(c, fn_name="FC01 Coils   ", fn=c.read_coils,
                                start=base, end=base + 64)
            if disc_hits:
                base = disc_hits[0]
                dense_scan_bits(c, fn_name="FC02 Discrete", fn=c.read_discrete,
                                start=base, end=base + 64)

            if any([holding_hits, input_hits, coil_hits, disc_hits]):
                # If we got anything at all on this unit ID, stop trying others.
                return 0
            print(f"  No readable regions on unit {unit} — trying next unit ID if provided.")
        finally:
            c.close()

    print("\nNo Modbus capability found across the unit IDs tried.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
