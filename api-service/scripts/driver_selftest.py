"""Driver self-test CLI (P3-2) — dump per-driver runtime + declared
capabilities for on-site debugging.

# Why this exists

Operator on-site needs to answer questions like:
  - "Did HAL come up with the right drivers?"
  - "Is the F64 K01 license actually showing as live, or is it just
    declared in the model?"
  - "Why is plan pre-flight saying capability X is missing?"

The GUI's "HAL Readiness" table shows a one-line summary per driver,
but it doesn't surface the canonical capability tokens (P2-2 live
``capabilities`` + P2-3 declared ``model_capabilities``). For
slack-paste debugging or offline review, a CLI that dumps the full
picture beats clicking through the GUI.

# Usage

  cd api-service
  python -m scripts.driver_selftest                  # text table to stdout
  python -m scripts.driver_selftest --format json    # JSON (pipe to jq)
  python -m scripts.driver_selftest --format md      # Markdown (paste in slack)
  python -m scripts.driver_selftest --mode real      # use REAL drivers
                                                       (default: mock, matches
                                                        FastAPI lifespan default)
  python -m scripts.driver_selftest --category channelEmulator  # filter

# Exit codes

  0  HAL initialised successfully; one or more drivers loaded
  1  HAL init raised an exception (returned report includes the error)
  2  HAL initialised but 0 drivers loaded (catalog likely empty)

The tool always tears down HAL after dumping so it can be run repeatedly
without leaking sessions to the real hardware.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ----------------------------------------------------------------------------
# Report dataclasses — kept separate from the driver classes so the dump
# stays a stable, JSON-serialisable contract independent of any driver-
# internal refactor.
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class DriverReport:
    """Per-loaded-driver snapshot. Mirrors the questions an operator
    asks at a console: what's bound, what's it talking to, is it up,
    what does it claim, what does it expose."""
    category: str
    driver_class: str  # e.g. "RealPropsimF64Driver" or "MockChannelEmulator"
    is_mock: bool
    endpoint_display: Optional[str]  # operator-friendly ip:port or VISA string
    status: str  # InstrumentStatus enum value as string
    last_error: Optional[str]
    live_capabilities: List[str]  # sorted, P2-2 driver.capabilities
    model_capabilities: List[str]  # sorted, P2-3 DriverClass.model_capabilities
    declared_but_not_live: List[str]  # set diff: declared ∖ live
    live_but_not_declared: List[str]  # set diff: live ∖ declared — invariant violation


@dataclass(frozen=True)
class SelftestReport:
    timestamp: str  # ISO8601 UTC
    hal_mode: str  # "mock" | "real"
    drivers_loaded: int
    drivers: List[DriverReport] = field(default_factory=list)
    init_error: Optional[str] = None  # set when HAL init itself raised


# ----------------------------------------------------------------------------
# Report builder — pure given a HAL service (testable without the CLI)
# ----------------------------------------------------------------------------

def _endpoint_display_for(driver: Any) -> Optional[str]:
    """Best-effort operator-readable endpoint string. Prefer parsed
    ip:port (what the wizard speaks) over the raw VISA resource string
    so a slack-paste shows ``192.168.0.132:5025`` not
    ``TCPIP0::192.168.0.132::5025::INSTR``."""
    cfg = getattr(driver, "config", None) or {}
    ip = cfg.get("ip")
    port = cfg.get("port")
    if ip and port:
        return f"{ip}:{port}"
    if cfg.get("endpoint"):
        return str(cfg["endpoint"])
    if ip:
        return str(ip)
    return None


def _build_driver_report(category: str, driver: Any) -> DriverReport:
    cls = type(driver)
    cls_name = cls.__name__
    is_mock = cls_name.startswith("Mock")
    live = set(getattr(driver, "capabilities", set()) or set())
    declared = set(getattr(cls, "model_capabilities", frozenset()) or frozenset())
    status_obj = getattr(driver, "status", None)
    status_str = (
        status_obj.value if hasattr(status_obj, "value") else str(status_obj)
        if status_obj is not None else "unknown"
    )
    return DriverReport(
        category=category,
        driver_class=cls_name,
        is_mock=is_mock,
        endpoint_display=_endpoint_display_for(driver),
        status=status_str,
        last_error=getattr(driver, "last_error", None),
        live_capabilities=sorted(live),
        model_capabilities=sorted(declared),
        declared_but_not_live=sorted(declared - live),
        live_but_not_declared=sorted(live - declared),
    )


def build_report(hal_service: Any, mode_label: str) -> SelftestReport:
    """Build a SelftestReport from a live HAL service. Pure function —
    no I/O, no async. Tests construct a HAL service (or a stand-in)
    and call this directly to pin the report shape.

    ``mode_label`` is what to put in the report's ``hal_mode`` field —
    the HAL service's internal mode enum may already be exposed, but
    keeping this parameterised lets tests assert against an explicit
    label without depending on enum string format."""
    drivers_dict = getattr(hal_service, "drivers", {}) or {}
    reports = [
        _build_driver_report(category, driver)
        for category, driver in sorted(drivers_dict.items())
    ]
    return SelftestReport(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        hal_mode=mode_label,
        drivers_loaded=len(reports),
        drivers=reports,
    )


# ----------------------------------------------------------------------------
# Renderers — text / json / md
# ----------------------------------------------------------------------------

def render_json(report: SelftestReport) -> str:
    """Stable JSON for piping (``| jq``) or attaching to an issue."""
    return json.dumps(asdict(report), indent=2, ensure_ascii=False)


def render_text(report: SelftestReport) -> str:
    """Compact text table for terminal use. Each driver gets a 5-7 line
    block — kept short so a 7-category HAL fits in one screen."""
    lines: List[str] = []
    lines.append(f"Driver self-test — {report.timestamp}")
    lines.append(f"HAL mode: {report.hal_mode}    Drivers loaded: {report.drivers_loaded}")
    if report.init_error:
        lines.append(f"⚠️  HAL init error: {report.init_error}")
    lines.append("=" * 72)
    if not report.drivers:
        lines.append("(no drivers loaded)")
        return "\n".join(lines)
    for d in report.drivers:
        mock_tag = " [MOCK]" if d.is_mock else ""
        lines.append(f"▸ {d.category:24} {d.driver_class}{mock_tag}")
        if d.endpoint_display:
            lines.append(f"    endpoint:  {d.endpoint_display}")
        lines.append(f"    status:    {d.status}")
        if d.last_error:
            lines.append(f"    error:     {d.last_error}")
        # Capability surfaces — pair live + declared so the operator
        # sees the diff at a glance.
        lines.append(
            f"    live caps:     {', '.join(d.live_capabilities) or '(none)'}"
        )
        lines.append(
            f"    declared caps: {', '.join(d.model_capabilities) or '(none)'}"
        )
        if d.declared_but_not_live:
            lines.append(
                f"    ⚠ declared but not live: {', '.join(d.declared_but_not_live)} "
                f"(license absent? alignment not loaded? probe failed?)"
            )
        if d.live_but_not_declared:
            # Should be empty by the P2-3 invariant; surface loudly if not.
            lines.append(
                f"    ✗ INVARIANT BREACH live ⊄ declared: "
                f"{', '.join(d.live_but_not_declared)} — add to "
                f"DriverClass.model_capabilities or fix the spurious _add_capability"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(report: SelftestReport) -> str:
    """Slack / GitHub-issue friendly markdown. Tables for the driver
    list (one row per loaded driver) — operator can paste straight in."""
    lines: List[str] = []
    lines.append(f"# Driver self-test — {report.timestamp}")
    lines.append("")
    lines.append(f"- HAL mode: `{report.hal_mode}`")
    lines.append(f"- Drivers loaded: **{report.drivers_loaded}**")
    if report.init_error:
        lines.append(f"- ⚠️ **HAL init error**: `{report.init_error}`")
    lines.append("")
    if not report.drivers:
        lines.append("_(no drivers loaded)_")
        return "\n".join(lines) + "\n"
    lines.append("| Category | Driver class | Endpoint | Status | Live caps | Declared caps |")
    lines.append("|---|---|---|---|---|---|")
    for d in report.drivers:
        mock_tag = " ⚙️" if d.is_mock else ""
        lines.append(
            f"| `{d.category}` | `{d.driver_class}`{mock_tag} "
            f"| `{d.endpoint_display or '(none)'}` | {d.status} "
            f"| {', '.join(f'`{c}`' for c in d.live_capabilities) or '_(none)_'} "
            f"| {', '.join(f'`{c}`' for c in d.model_capabilities) or '_(none)_'} |"
        )
    # Per-driver issue callouts below the table so the row stays compact.
    callouts = [d for d in report.drivers if d.declared_but_not_live or d.live_but_not_declared or d.last_error]
    if callouts:
        lines.append("")
        lines.append("## Issues")
        lines.append("")
        for d in callouts:
            lines.append(f"### `{d.category}`")
            if d.last_error:
                lines.append(f"- ⚠ last error: `{d.last_error}`")
            if d.declared_but_not_live:
                lines.append(
                    f"- ⚠ declared but not live: "
                    f"{', '.join(f'`{c}`' for c in d.declared_but_not_live)} "
                    f"— license absent? alignment not loaded? probe failed?"
                )
            if d.live_but_not_declared:
                lines.append(
                    f"- ✗ **INVARIANT BREACH** live ⊄ declared: "
                    f"{', '.join(f'`{c}`' for c in d.live_but_not_declared)} "
                    f"— add to `DriverClass.model_capabilities` or fix the "
                    f"spurious `_add_capability` call"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_RENDERERS = {
    "text": render_text,
    "json": render_json,
    "md": render_markdown,
}


# ----------------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------------

async def _run(mode: str, category_filter: Optional[str]) -> SelftestReport:
    """Initialise HAL in ``mode``, build a report, then tear HAL down.

    Tear-down matters even in mock mode because the singleton survives
    across multiple CLI invocations in the same Python process (tests
    do this); without shutdown the second invocation reuses stale
    driver state."""
    from app.services.instrument_hal_service import (
        DriverMode,
        get_hal_service,
        initialize_hal_service,
        shutdown_hal_service,
    )

    target_mode = DriverMode.REAL if mode == "real" else DriverMode.MOCK
    try:
        await initialize_hal_service(mode=target_mode)
    except Exception as exc:  # noqa: BLE001
        return SelftestReport(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            hal_mode=mode,
            drivers_loaded=0,
            init_error=f"{type(exc).__name__}: {exc}",
        )

    try:
        hal = get_hal_service()
        report = build_report(hal, mode_label=mode)
    finally:
        await shutdown_hal_service()

    if category_filter:
        filtered = [d for d in report.drivers if d.category == category_filter]
        # Rebuild rather than mutate — SelftestReport is frozen.
        report = SelftestReport(
            timestamp=report.timestamp,
            hal_mode=report.hal_mode,
            drivers_loaded=len(filtered),
            drivers=filtered,
            init_error=report.init_error,
        )
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dump per-driver runtime + declared capabilities "
                    "(P3-2). Reads the same HAL bootstrap path the "
                    "FastAPI lifespan uses, then exits clean."
    )
    parser.add_argument(
        "--format", choices=sorted(_RENDERERS), default="text",
        help="Output format (default: text). 'md' is slack/issue-paste-ready.",
    )
    parser.add_argument(
        "--mode", choices=["mock", "real"], default="mock",
        help="HAL driver mode (default: mock). 'real' will try to connect "
             "to whatever the catalog says — only do this when you actually "
             "want hardware traffic.",
    )
    parser.add_argument(
        "--category", default=None, metavar="CATEGORY_KEY",
        help="Filter to one category (e.g. 'channelEmulator'). Useful "
             "when only one driver matters for the debug at hand.",
    )
    args = parser.parse_args(argv)

    report = asyncio.run(_run(args.mode, args.category))
    rendered = _RENDERERS[args.format](report)
    print(rendered, end="" if rendered.endswith("\n") else "\n")

    if report.init_error:
        return 1
    if report.drivers_loaded == 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
