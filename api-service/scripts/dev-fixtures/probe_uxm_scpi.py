"""On-site UXM 5G NR SCPI compatibility probe.

Why this exists
---------------
We can't get CAICT (or any new site) to pre-verify 76 SCPI command strings
against their UXM firmware before a debug trip. Instead, we run this probe
the moment UXM is reachable on the network — it spends ~30 seconds walking
every command our driver depends on, and returns a categorized go/no-go.

What it does NOT do
-------------------
- Does not change UXM state (no ``*RST``, no ``CELL_STATE ON``).
- Does not start measurements (no ``MEAS:*:STARt``).
- Does not require the cell to be active or a DUT attached.

Strategy
--------
For each ``UxmScpiCommands`` constant:

* **QUERY** (ends with ``?``): send as-is, then read ``SYSTem:ERRor?``.
* **WRITE** (set commands, has placeholders or no ``?``): strip trailing
  arguments down to the bare header, append ``?``, send the resulting
  query, read ``SYSTem:ERRor?``. Firmware that doesn't recognize the
  base command will queue ``-113 "Undefined header"`` (or ``-114``).
  Firmware that recognizes it but rejects the ``?`` form will queue a
  syntax error (``-100..-109``) — still proves the header exists.
* **ACTION** (pure triggers like ``:STARt`` / ``*CLS`` / ``:APPLy``):
  skipped. They have no query form; their existence is inferred from a
  paired query in the same subsystem (e.g. ``:START`` exists if
  ``:JSON?`` works). Reported as ``INFERRED`` with the paired query.

Categorization of the response error code:

* ``0`` (no error) ............... 🟢 SUPPORTED — header recognized, ok.
* ``-100..-109`` (command/syntax) . 🟢 SUPPORTED — header recognized but the
                                     bare ``?`` form was rejected. Fine —
                                     the underlying SET command still works.
* ``-200..-299`` (execution) ..... 🟡 SUPPORTED_BUT_STATE — header
                                     recognized, current UXM state doesn't
                                     allow the query (e.g. measurement not
                                     running). Fine for probe purposes.
* ``-113`` or ``-114`` ........... 🔴 UNSUPPORTED — undefined header. The
                                     driver needs a vendor alias for this
                                     command on this firmware.
* anything else .................. ⚪ UNKNOWN — log raw, surface to operator.

Usage
-----
::

    cd api-service
    .venv/bin/python scripts/dev-fixtures/probe_uxm_scpi.py --ip 192.168.X.Y

    # JSON output for the GUI or a follow-up script:
    .venv/bin/python scripts/dev-fixtures/probe_uxm_scpi.py --ip ... --json /tmp/scpi.json

Exit codes
----------

* 0 .. all critical commands SUPPORTED
* 1 .. some critical commands UNSUPPORTED (look at the report)
* 2 .. could not connect to UXM at the given IP
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

# Make ``app.*`` importable when run directly from scripts/dev-fixtures/.
_API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_API_ROOT))

from app.hal.uxm_base_station import UxmScpiCommands  # noqa: E402

# Placeholder substitutions used when formatting a template into a concrete
# command. Chosen to be syntactically valid on E7515B firmware — these values
# never get committed because we only query, never set.
_PLACEHOLDERS = {
    "cell":     "CELL0",
    "bwp":      "BWP0",
    "ant":      "1",
    "idx":      "1",
    "layers":   "2",
    "mod":      "QPSK",
    "freq_mhz": "3500",
    "bw_mhz":   "100",
    "scs_khz":  "30",
    "band":     "N78",
    "filepath": "D:\\probe_test.state",
}

# Action-only commands that have no useful query form and trigger side
# effects we don't want during a probe. The probe skips these and infers
# their existence from a neighbor query in the same subsystem.
_ACTION_NEIGHBOR_QUERY: dict[str, Optional[str]] = {
    "*CLS":  "IDN",                          # IEEE 488.2 — *IDN? proves it
    "*RST":  "IDN",
    "MEAS_BTHROUGHPUT_DL_START": "MEAS_BTHROUGHPUT_DL_JSON",
    "MEAS_BTHROUGHPUT_DL_STOP":  "MEAS_BTHROUGHPUT_DL_JSON",
    "MEAS_CSI_START":            "MEAS_CSI_CQI",
    "MEAS_CSI_STOP":             "MEAS_CSI_CQI",
    "MEAS_EVM_START":            "MEAS_BTHROUGHPUT_DL_JSON",  # same MEAS subsystem
    "RRC_RECONFIG_APPLY":        "RRC_RECONFIG_LAYERS",        # same RRC subsystem
    "SCELL_ADD":                 "SCELL_LIST_QUERY",
    "SCELL_REMOVE_ALL":          "SCELL_LIST_QUERY",
}

# Critical commands — if any of these come back UNSUPPORTED, the trip fails.
# This is the *minimum viable* MIMO_OTA test surface.
_CRITICAL_NAMES = {
    "IDN", "ERR", "APP_SELECT",
    "CELL_BAND", "CELL_DL_BW", "CELL_SCS", "CELL_DUPLEX", "CELL_ACTIVE",
    "DL_POWER", "SSB_POWER",
    "MIMO_DL_LAYERS", "MIMO_TX_ANT_PORT", "MIMO_RX_ANT_PORT",
    "PDSCH_MCS", "PDSCH_SCHED_ALGO", "PDSCH_AMC_ENABLE",
    "TDD_PATTERN", "TDD_PERIOD",
    "HARQ_MAX_TRANS", "HARQ_PROCESSES",
    "MEAS_BTHROUGHPUT_DL_JSON", "MEAS_BTHROUGHPUT_DL_BLER",
}


@dataclass
class ProbeResult:
    name: str
    sent: str
    category: str            # QUERY / WRITE / ACTION
    status: str              # SUPPORTED / SUPPORTED_BUT_STATE / UNSUPPORTED / INFERRED / SKIPPED / UNKNOWN
    err_code: Optional[int]  # the int from SYSTem:ERRor? or None
    err_text: str            # raw err string
    inferred_from: Optional[str] = None  # neighbor query name (for ACTION)
    is_critical: bool = False


def _classify(value: str) -> str:
    """Return 'QUERY' | 'WRITE' | (caller checks ACTION via name)."""
    head = value.split(None, 1)[0]
    return "QUERY" if head.endswith("?") else "WRITE"


def _to_probe_command(value: str) -> str:
    """Format placeholders + reduce a WRITE command to its query form.

    Examples:
      'CONFig:NR5G:{cell}:BAND'             → 'CONFig:NR5G:CELL0:BAND?'
      'CONFig:NR5G:{cell}:ACTive:STATe ON'  → 'CONFig:NR5G:CELL0:ACTive:STATe?'
      'MEASure:NR5G:{cell}:CSI:CQI:STATistics?' → unchanged after format
    """
    # 1. Substitute placeholders.
    formatted = value
    for k, v in _PLACEHOLDERS.items():
        formatted = formatted.replace("{" + k + "}", v)
    # 2. Drop trailing arguments — keep only the header.
    head = formatted.split(None, 1)[0]
    # 3. Ensure it ends with '?' for safe probing.
    if not head.endswith("?"):
        head = head + "?"
    return head


def _parse_err(raw: str) -> tuple[Optional[int], str]:
    """Parse 'SYSTem:ERRor?' response. Returns (code, text)."""
    raw = raw.strip()
    if not raw:
        return None, ""
    # Typical: '0,"No error"' or '-113,"Undefined header"' or '+0,"No error"'
    m = re.match(r"^([+-]?\d+)\s*,\s*(.*)$", raw)
    if not m:
        return None, raw
    return int(m.group(1)), m.group(2).strip(' "')


def _categorize_status(err_code: Optional[int]) -> str:
    if err_code is None:
        return "UNKNOWN"
    if err_code == 0:
        return "SUPPORTED"
    if err_code in (-113, -114):
        return "UNSUPPORTED"
    # -100..-109 syntax/command errors — header was recognized (would be
    # -113 otherwise) but the bare ? form was rejected. SET still works.
    if -109 <= err_code <= -100:
        return "SUPPORTED"
    # -200..-299 execution errors — header recognized, wrong state.
    if -299 <= err_code <= -200:
        return "SUPPORTED_BUT_STATE"
    return "UNKNOWN"


def _probe_one(session, name: str, value: str, is_critical: bool) -> ProbeResult:
    sent = _to_probe_command(value)
    category = _classify(value)
    try:
        # Fire the query — discard response, what matters is the error queue.
        try:
            session.query(sent)
        except Exception:
            # Query may time out on commands that don't return data; that's
            # fine — the error queue still records what happened.
            pass
        # Now read the error queue.
        raw_err = session.query(UxmScpiCommands.ERR)
    except Exception as exc:
        return ProbeResult(
            name=name, sent=sent, category=category,
            status="UNKNOWN", err_code=None, err_text=f"probe exception: {exc}",
            is_critical=is_critical,
        )

    err_code, err_text = _parse_err(raw_err)
    return ProbeResult(
        name=name, sent=sent, category=category,
        status=_categorize_status(err_code),
        err_code=err_code, err_text=err_text,
        is_critical=is_critical,
    )


def _all_commands() -> list[tuple[str, str]]:
    """Enumerate (name, value) for every string constant on UxmScpiCommands."""
    pairs = []
    for name, value in inspect.getmembers(UxmScpiCommands):
        if name.startswith("_") or not isinstance(value, str):
            continue
        pairs.append((name, value))
    pairs.sort(key=lambda p: p[0])
    return pairs


def run_probe(ip: str, protocol: str = "TCPIP", port: int = 5025) -> list[ProbeResult]:
    """Open VISA, drain the error queue, probe every command, close."""
    import pyvisa
    rm = pyvisa.ResourceManager()

    if protocol.upper() == "HISLIP":
        resource = f"TCPIP::{ip}::hislip0::INSTR"
    else:
        resource = f"TCPIP::{ip}::{port}::SOCKET"

    sys.stderr.write(f"[probe] Connecting to {resource} ...\n")
    session = rm.open_resource(resource, timeout=5000)
    if "SOCKET" in resource:
        session.read_termination = "\n"
        session.write_termination = "\n"

    try:
        idn = session.query("*IDN?").strip()
        sys.stderr.write(f"[probe] Connected: {idn}\n")
        # Clean the error queue once so the first probe sees a fresh state.
        session.write("*CLS")
        time.sleep(0.05)

        results: list[ProbeResult] = []
        action_pending: list[tuple[str, str]] = []
        results_by_name: dict[str, ProbeResult] = {}

        for name, value in _all_commands():
            is_critical = name in _CRITICAL_NAMES

            if name in _ACTION_NEIGHBOR_QUERY:
                action_pending.append((name, value))
                continue

            res = _probe_one(session, name, value, is_critical)
            results.append(res)
            results_by_name[name] = res

        # After regular commands are probed, infer ACTION status from neighbors.
        for name, value in action_pending:
            neighbor = _ACTION_NEIGHBOR_QUERY[name]
            neighbor_res = results_by_name.get(neighbor) if neighbor else None
            if neighbor_res is None or neighbor_res.status == "UNKNOWN":
                inferred = "UNKNOWN"
            elif neighbor_res.status in ("SUPPORTED", "SUPPORTED_BUT_STATE"):
                inferred = "INFERRED"
            else:
                inferred = "UNSUPPORTED"
            results.append(ProbeResult(
                name=name, sent=value, category="ACTION",
                status=inferred,
                err_code=neighbor_res.err_code if neighbor_res else None,
                err_text=f"inferred from neighbor {neighbor}" if neighbor else "no neighbor",
                inferred_from=neighbor,
                is_critical=name in _CRITICAL_NAMES,
            ))

        return results
    finally:
        try:
            session.close()
        finally:
            rm.close()


def render_report(results: list[ProbeResult]) -> str:
    by_status: dict[str, list[ProbeResult]] = {}
    for r in results:
        by_status.setdefault(r.status, []).append(r)

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("UXM SCPI compatibility probe — report")
    lines.append("=" * 78)
    lines.append("")

    icon = {
        "SUPPORTED":           "🟢",
        "SUPPORTED_BUT_STATE": "🟡",
        "INFERRED":            "🟢 (inferred)",
        "UNSUPPORTED":         "🔴",
        "UNKNOWN":             "⚪",
        "SKIPPED":             "  ",
    }

    # Summary
    total = len(results)
    crit_total = sum(1 for r in results if r.is_critical)
    crit_unsupported = sum(
        1 for r in results
        if r.is_critical and r.status == "UNSUPPORTED"
    )
    lines.append(f"Total commands probed: {total}")
    lines.append(f"Critical (MIMO OTA minimum surface): {crit_total}")
    lines.append(f"Critical UNSUPPORTED: {crit_unsupported}")
    for status, group in sorted(by_status.items()):
        lines.append(f"  {icon.get(status, '?'):<14} {status:<22} {len(group):>3}")
    lines.append("")

    # Per-status detail (UNSUPPORTED first so it doesn't get lost)
    for status in ("UNSUPPORTED", "UNKNOWN", "SUPPORTED_BUT_STATE", "INFERRED", "SUPPORTED"):
        group = by_status.get(status) or []
        if not group:
            continue
        lines.append(f"--- {icon.get(status, '?')} {status} ({len(group)}) ---")
        for r in sorted(group, key=lambda x: (not x.is_critical, x.name)):
            crit_marker = "★" if r.is_critical else " "
            err = f" [{r.err_code}: {r.err_text}]" if r.err_code is not None else ""
            inferred = f" ← {r.inferred_from}" if r.inferred_from else ""
            lines.append(f"  {crit_marker} {r.name:<32} {r.sent}{err}{inferred}")
        lines.append("")

    # Bottom line
    if crit_unsupported > 0:
        lines.append("🔴 BLOCKER: critical commands missing — driver needs vendor aliases")
        lines.append("   before commissioning can run. Save the report and escalate.")
    elif by_status.get("UNSUPPORTED"):
        lines.append("🟡 Some non-critical commands missing. Cell config + MIMO OTA")
        lines.append("   throughput will run; some optional measurements (CSI/EVM/UE)")
        lines.append("   may degrade. Operator can proceed but flag in phase reports.")
    else:
        lines.append("🟢 All commands supported. Proceed with commissioning.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ip", required=True, help="UXM IP address")
    parser.add_argument("--protocol", default="TCPIP", choices=["TCPIP", "HISLIP"])
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--json", dest="json_out", help="Also write structured JSON to this path")
    args = parser.parse_args()

    try:
        results = run_probe(args.ip, args.protocol, args.port)
    except Exception as exc:
        sys.stderr.write(f"[probe] Failed to connect / probe: {exc}\n")
        return 2

    report = render_report(results)
    print(report)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(
                {"results": [asdict(r) for r in results]},
                f, indent=2, ensure_ascii=False,
            )
        sys.stderr.write(f"[probe] JSON report → {args.json_out}\n")

    critical_unsupported = any(
        r.is_critical and r.status == "UNSUPPORTED" for r in results
    )
    return 1 if critical_unsupported else 0


if __name__ == "__main__":
    raise SystemExit(main())
