"""UXM 5G NR SCPI compatibility probe — diagnostic sequence form.

Why this exists
---------------
We can't realistically get a site engineer (CAICT etc.) to verify all 76
SCPI commands against their firmware before a debug trip. Instead, this
sequence walks every command the UXM driver depends on the moment we
arrive — picks them up from the live HAL driver's session, classifies
each by the resulting ``SYSTem:ERRor?`` code, and reports which need
vendor aliases before commissioning can run.

Why a sequence and not a CLI script
-----------------------------------
Earlier iteration of this lived in ``scripts/dev-fixtures/`` as a
pyvisa CLI. That had three problems:

1. It opened a second VISA session, conflicting with the running HAL
   driver (one TCP connection per UXM is typical).
2. It bypassed audit logging — no ``diagnostic_runs`` row, no GUI
   history, operator had to ssh to read the output.
3. It reinvented machinery the diagnostic-sequence framework already
   provides (LabProfile resolution, audit, GUI surface).

This module reuses the same probe logic but runs through the live
driver and the existing ``/api/v1/diagnostic-sequences/{key}/run``
endpoint, so the operator sees it in the same panel as IDN sweep + the
commissioning ad-hoc tools.

Strategy
--------
For each ``UxmScpiCommands`` constant:

* **QUERY** (ends with ``?``): send as-is.
* **WRITE / SET** (has placeholders, hardcoded value, or no ``?``):
  strip trailing arguments down to the bare header, append ``?``, send
  the resulting query. Firmware that doesn't know the header queues
  ``-113 "Undefined header"``; firmware that knows the header but
  rejects ``?`` form queues a syntax error (-100..-109) — still proves
  the header exists.
* **ACTION-only** (``:STARt`` / ``:STOP`` / ``:APPLy`` / ``*RST`` /
  ``*CLS`` / ``SCEL:ADD`` etc.): SKIPPED to avoid side-effects;
  existence inferred from a paired query in the same subsystem.

After each probed command, ``SYSTem:ERRor?`` is queried and the error
code categorized:

* ``0`` / ``-100..-109`` ........ SUPPORTED (header recognized)
* ``-200..-299`` ................ SUPPORTED_BUT_STATE (header
                                  recognized, current state doesn't
                                  allow query — fine for probe)
* ``-113`` / ``-114`` ........... UNSUPPORTED (driver needs alias)
* anything else ................. UNKNOWN (surfaced raw)

The 22 "critical" commands (cell config + MIMO + throughput) are
tagged so the operator sees immediately whether to proceed or escalate.

Safety
------
``safe_during_test=False`` — even though the probe doesn't mutate state,
it floods the error queue and we don't want it interleaved with a real
measurement reading from the same queue.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
    SequenceStepResult,
)
from app.hal.uxm_base_station import UxmScpiCommands
from app.hal.uxm_command_profiles import (
    UxmTestApp,
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)
from app.services.diagnostic_context import DiagnosticContext


# Fail-fast threshold — abort the SCPI walk after this many consecutive
# VISA timeouts. Mirrors the pattern proven on PROPSIM FS16 / F64 probes
# 2026-05-13: when a session goes half-closed mid-walk, every subsequent
# command costs 5 s (VISA default timeout), and the probe drags on for
# minutes before reporting useless data. 3 strikes = bail, tell operator
# to reload HAL.
_MAX_CONSECUTIVE_TIMEOUTS = 3


# Placeholder substitutions used when formatting a template into a concrete
# command. Chosen to be syntactically valid on E7515B firmware — these values
# never get committed because we only query, never set.
_PLACEHOLDERS: Dict[str, str] = {
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
# effects we don't want during a probe. Existence inferred from a paired
# query in the same subsystem; None means "assume present" (IEEE 488.2).
_ACTION_NEIGHBOR_QUERY: Dict[str, Optional[str]] = {
    "CLS":  "IDN",                                # IEEE 488.2 — *IDN? proves it
    "RST":  "IDN",
    "MEAS_BTHROUGHPUT_DL_START": "MEAS_BTHROUGHPUT_DL_JSON",
    "MEAS_BTHROUGHPUT_DL_STOP":  "MEAS_BTHROUGHPUT_DL_JSON",
    # ⚠ 手册标 "Immediate Action / No query: True" —— 不列在这里的话
    #   _to_probe_command 会给它补 `?` 发出 `...:CLEar?`, 必然 undefined
    #   header + 烧一次 VISA 超时 + 记成假 UNSUPPORTED（禁盲试违例）。
    "MEAS_BTHROUGHPUT_CLEAR":     "MEAS_TPUT_DL_OTA",
    "MEAS_BTHROUGHPUT_STATE":     "MEAS_TPUT_DL_OTA",
    "MEAS_UE_REPORT_STATE":       "MEAS_UE_REPORT_JSON",
    "MEAS_CSI_START":            "MEAS_CSI_CQI",
    "MEAS_CSI_STOP":             "MEAS_CSI_CQI",
    "MEAS_EVM_START":            "MEAS_BTHROUGHPUT_DL_JSON",
    "RRC_RECONFIG_APPLY":        "RRC_RECONFIG_LAYERS",
    "SCELL_ADD":                 "SCELL_LIST_QUERY",
    "SCELL_REMOVE_ALL":          "SCELL_LIST_QUERY",
}

# Critical commands — if any of these come back UNSUPPORTED, commissioning
# can't run. This is the minimum viable MIMO_OTA test surface.
_CRITICAL_NAMES = frozenset({
    "IDN", "ERR", "APP_SELECT",
    "CELL_BAND", "CELL_DL_BW", "CELL_SCS", "CELL_DUPLEX", "CELL_ACTIVE",
    "DL_POWER", "SSB_POWER",
    "MIMO_DL_LAYERS", "MIMO_TX_ANT_PORT", "MIMO_RX_ANT_PORT",
    "PDSCH_MCS", "PDSCH_SCHED_ALGO", "PDSCH_AMC_ENABLE",
    "TDD_PATTERN", "TDD_PERIOD",
    "HARQ_MAX_TRANS", "HARQ_PROCESSES",
    "MEAS_BTHROUGHPUT_DL_JSON",
    # 2026-08-03: KPI 回读整批换命令后, critical 清单同步。
    # ⚠ 移除 MEAS_BTHROUGHPUT_DL_BLER —— 它在 IRAT profile 上已置 None
    #   (那条是 Early Pass/Fail 状态机不是 BLER), 留在清单里会被
    #   _collect_commands 的 isinstance(value, str) 静默过滤掉,
    #   而总结仍按 len(_CRITICAL_NAMES) 报 "All N critical commands
    #   supported" —— 报一个**从没探测过**的命令为已支持。
    # 新增下面这批 = 吞吐量/BLER/CSI/UE 报告的真值源, 现场必须逐条对账。
    "MEAS_TPUT_DL_OTA", "MEAS_TPUT_UL_OTA",
    "MEAS_BLER_DL", "MEAS_BLER_UL",
    "MEAS_CSI_CQI", "MEAS_CSI_RI",
    "MEAS_UE_REPORT_JSON",
})


# ---------------------------------------------------------------------------
# Helpers — pure functions, unit-testable without a driver/UXM.
# ---------------------------------------------------------------------------

def _to_probe_command(value: str, profile: Optional[Union[type, UxmTestApp]] = None) -> str:
    """Format placeholders + reduce a WRITE command to its query form.

    If ``profile`` is given, its ``PRIMARY_CELL`` overrides the default
    ``CELL0`` (so e.g. LTE_NR_IRAT correctly probes ``CELL1`` since that
    app doesn't expose ``CELL0``).
    """
    formatted = value
    placeholders = dict(_PLACEHOLDERS)
    if profile is not None and getattr(profile, "PRIMARY_CELL", None):
        placeholders["cell"] = profile.PRIMARY_CELL
    if profile is not None and getattr(profile, "PRIMARY_BWP", None):
        placeholders["bwp"] = profile.PRIMARY_BWP
    for k, v in placeholders.items():
        formatted = formatted.replace("{" + k + "}", v)
    head = formatted.split(None, 1)[0]
    if not head.endswith("?"):
        head = head + "?"
    return head


def _parse_err(raw: str) -> Tuple[Optional[int], str]:
    """Parse 'SYSTem:ERRor?' response. Returns (code, text)."""
    raw = (raw or "").strip()
    if not raw:
        return None, ""
    m = re.match(r"^([+-]?\d+)\s*,\s*(.*)$", raw)
    if not m:
        return None, raw
    return int(m.group(1)), m.group(2).strip(' "')


def _categorize_status(err_code: Optional[int]) -> str:
    """Map IEEE 488.2 error codes to probe outcome.

    -113 / -114 = "Undefined header" / "Header suffix out of range" — the
    only codes that mean the SCPI mnemonic genuinely doesn't exist.

    -100 .. -112 = "Command header error" family. These mean the parser
    recognized the header (it's in the SCPI tree) but the form was
    wrong (write-only command probed as a query, missing parameter,
    bad separator, etc.). For a *compatibility* probe, that's SUPPORTED
    — the driver can use the header, just with the right form.

    -200 .. -299 = execution error family. Header is recognized AND
    valid syntax; instrument state is what's preventing the command
    from running right now. Also OK for the probe.
    """
    if err_code is None:
        return "UNKNOWN"
    if err_code == 0:
        return "SUPPORTED"
    if err_code in (-113, -114):
        return "UNSUPPORTED"
    if -112 <= err_code <= -100:
        return "SUPPORTED"
    if -299 <= err_code <= -200:
        return "SUPPORTED_BUT_STATE"
    return "UNKNOWN"


def _all_commands(profile: Union[type, UxmTestApp]) -> List[Tuple[str, str]]:
    """Enumerate (name, value) for every string-valued SCPI command attribute
    on ``profile``.

    Skips:
      - dunders / private attrs (``_``)
      - non-string attributes (PROFILE_NAME etc are str so they leak in;
        we drop them by exclusion list below — they're not real SCPI)
      - attributes set to ``None`` in the profile (means "this Test App
        doesn't expose this command", per profile design contract)
    """
    skip = {
        "PROFILE_NAME",
        # APP_NAME_MATCH is a tuple, naturally filtered by isinstance str
    }
    pairs: List[Tuple[str, str]] = []
    for name, value in inspect.getmembers(profile):
        if name.startswith("_") or name in skip or not isinstance(value, str):
            continue
        # Profile-design contract: cell/bwp constants like PRIMARY_CELL also
        # appear as str — exclude them because they aren't SCPI commands.
        if name in {"PRIMARY_CELL", "PRIMARY_BWP"}:
            continue
        pairs.append((name, value))
    pairs.sort(key=lambda p: p[0])
    return pairs


def _profile_for_driver(bs: Any) -> Union[type, UxmTestApp]:
    """Return the live driver's command profile (instance OR class).

    ``RealUxmDriver._cmds`` is an *instance* of a ``UxmTestApp`` subclass
    since PR #44 (class-vs-instance mutability fix). Older test fixtures
    that build a MagicMock baseStation and set ``_cmds`` to the class
    directly still work because downstream ``_all_commands`` /
    ``_to_probe_command`` use ``inspect.getmembers`` + ``getattr`` —
    both class and instance expose the SCPI command attrs identically.

    Codex P2 (PR #44 review): previously gated on
    ``isinstance(profile, type)`` so the live instance fell through to
    the 5G fallback, causing the IRAT diagnostic to probe the wrong
    SCPI tree + CELL0 defaults and false-flag commands as unsupported.

    MagicMock / missing ``_cmds`` still fall back to the 5G class
    (the pre-2026-05-13 default).
    """
    profile = getattr(bs, "_cmds", None)
    if isinstance(profile, UxmTestApp):
        return profile  # live RealUxmDriver instance (current)
    if isinstance(profile, type) and issubclass(profile, UxmTestApp):
        return profile  # class ref (legacy test fixtures)
    return Uxm5GNRTestAppProfile


# ---------------------------------------------------------------------------
# Sequence contract
# ---------------------------------------------------------------------------

metadata = SequenceMetadata(
    name="UXM SCPI compatibility probe",
    description=(
        "Walks every SCPI command the UXM driver depends on (~76 commands), "
        "categorizes each as SUPPORTED / UNSUPPORTED / state-error / inferred "
        "based on SYSTem:ERRor?. ~30 s end-to-end. Replaces asking a site "
        "engineer to pre-verify firmware compatibility."
    ),
    required_categories=["baseStation"],
    params_schema=[
        {
            "name": "include_supported",
            "label": "Detail SUPPORTED commands too (default: only flag failures)",
            "type": "boolean",
            "default": False,
        },
    ],
    safe_during_test=False,  # floods the error queue
)


def _categorize_action(
    name: str,
    results_by_name: Dict[str, "SequenceStepResult"],
) -> Tuple[str, Optional[int], str]:
    """Infer ACTION command status from its neighbor query.

    Returns (status, err_code, detail_message).
    """
    neighbor = _ACTION_NEIGHBOR_QUERY[name]
    if neighbor is None:
        return "SUPPORTED", None, "IEEE 488.2 standard — assumed present"
    neighbor_res = results_by_name.get(neighbor)
    if neighbor_res is None:
        return "UNKNOWN", None, f"neighbor {neighbor} not probed"
    # Re-derive status from the step's detail since SequenceStepResult
    # doesn't carry it as a field. We tagged it into detail at probe time.
    neighbor_status = neighbor_res.detail.split(" ", 1)[0] if neighbor_res.detail else ""
    if neighbor_status in ("SUPPORTED", "SUPPORTED_BUT_STATE"):
        return "SUPPORTED", None, f"inferred from neighbor {neighbor}"
    if neighbor_status == "UNSUPPORTED":
        return "UNSUPPORTED", None, (
            f"inferred from neighbor {neighbor} = UNSUPPORTED — driver "
            "likely needs an alias for the whole subsystem"
        )
    return "UNKNOWN", None, f"neighbor {neighbor} = {neighbor_status or 'unparseable'}"


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(
            success=False,
            summary=driver_not_loaded_summary("baseStation"),
        )

    # P1-14: hardware probe is meaningless against a mock driver —
    # refuse with an actionable summary instead of running the
    # identity/SCPI checks against canned/empty mock values.
    refusal = mock_driver_refusal_summary("baseStation", bs)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)

    # The probe needs the driver's raw SCPI primitives. `_query` is the
    # template method that also writes to the SCPI log — exactly what we
    # want (every probed command shows up in measurement.log alongside
    # phases). If the driver doesn't expose `_query` we bail loudly.
    query_fn = getattr(bs, "_query", None)
    if not callable(query_fn):
        return SequenceRunResult(
            success=False,
            summary=(
                f"baseStation driver {type(bs).__name__} doesn't expose _query; "
                "the SCPI probe needs a raw query primitive"
            ),
        )

    include_supported = bool(params.get("include_supported", False))

    # The driver may run sync (UXM does — pyvisa is sync) or async. Wrap
    # uniformly so we don't block the event loop for 30 s.
    async def _q(cmd: str) -> str:
        result = query_fn(cmd)
        if asyncio.iscoroutine(result):
            return await result
        return await asyncio.get_event_loop().run_in_executor(None, lambda: result)

    # Clean the error queue once so the first probe sees a fresh state.
    write_fn = getattr(bs, "_write", None)
    if callable(write_fn):
        try:
            res = write_fn("*CLS")
            if asyncio.iscoroutine(res):
                await res
        except Exception:  # noqa: BLE001
            pass

    profile = _profile_for_driver(bs)
    all_cmds = _all_commands(profile)
    log(
        f"  · probing {len(all_cmds)} commands from profile "
        f"{profile.PROFILE_NAME} (driver={type(bs).__name__}) ..."
    )

    steps: List[SequenceStepResult] = []
    results_by_name: Dict[str, SequenceStepResult] = {}
    counts = {"SUPPORTED": 0, "SUPPORTED_BUT_STATE": 0, "UNSUPPORTED": 0, "UNKNOWN": 0}
    critical_unsupported: List[str] = []
    action_pending: List[Tuple[str, str]] = []
    consecutive_timeouts = 0
    aborted_early = False
    last_probed = ""

    err_query = profile.ERR or UxmScpiCommands.ERR

    for name, value in all_cmds:
        # Skip ACTIONs in the first pass; infer from neighbors later.
        if name in _ACTION_NEIGHBOR_QUERY:
            action_pending.append((name, value))
            continue

        probe_cmd = _to_probe_command(value, profile)
        last_probed = probe_cmd
        started = time.monotonic()
        err_code: Optional[int] = None
        err_text = ""
        try:
            try:
                await _q(probe_cmd)
            except Exception:
                # Query may timeout on commands that don't return data;
                # what matters is the error queue, not this response.
                pass
            raw_err = await _q(err_query)
            err_code, err_text = _parse_err(raw_err)
            # The real failure signal is "SYST:ERR? itself stops responding"
            # — that means the SCPI channel is genuinely stuck. An unsupported
            # command will normally make the probe_cmd time out (UXM silently
            # logs -113 to the queue without sending a response) but SYST:ERR?
            # still returns the queued -113. That's not a stuck channel,
            # just a missing command — must NOT trip fail-fast.
            channel_alive = err_code is not None
            consecutive_timeouts = 0 if channel_alive else consecutive_timeouts + 1
        except Exception as e:  # noqa: BLE001
            err_text = f"probe exception: {e}"
            # SYST:ERR? itself threw — real channel-stuck signal.
            if "VI_ERROR_TMO" in str(e) or "timeout" in str(e).lower():
                consecutive_timeouts += 1

        if consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
            log(
                f"  ✗ ABORTING — {_MAX_CONSECUTIVE_TIMEOUTS} consecutive VISA "
                f"timeouts. Last probed: {last_probed}. SCPI channel is stuck; "
                f"reload HAL (POST /api/v1/instruments/hal/reload) and retry."
            )
            aborted_early = True
            break

        status = _categorize_status(err_code)
        counts[status] = counts.get(status, 0) + 1
        is_critical = name in _CRITICAL_NAMES

        # Step success is meaningful only for UNSUPPORTED-on-critical:
        # the GUI's red/green per step should highlight just the real
        # blockers; SUPPORTED_BUT_STATE/SUPPORTED both render green.
        step_ok = status in ("SUPPORTED", "SUPPORTED_BUT_STATE")
        if not step_ok and is_critical:
            critical_unsupported.append(name)

        # The status string leads `detail` because the action-neighbor
        # lookup later parses detail.split()[0] to infer ACTION status.
        err_part = f" [{err_code}: {err_text}]" if err_code is not None else (
            f" [{err_text}]" if err_text else ""
        )
        crit_part = " ★" if is_critical else ""
        detail = f"{status}{crit_part}{err_part}"

        # Suppress noisy SUPPORTED steps unless operator opts in — keeps
        # the GUI step list focused on real findings (typically 0-5 rows
        # instead of all 76). The summary text + extra.critical_unsupported
        # already surface the critical-command verdict; the step list is
        # for "show me what specifically broke".
        emit_step = include_supported or not step_ok

        if emit_step:
            label = f"{name} → {probe_cmd}"
            step = SequenceStepResult(
                label=label,
                success=step_ok,
                detail=detail,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            steps.append(step)
        # Always record into results_by_name so action inference can find us.
        results_by_name[name] = SequenceStepResult(
            label=name, success=step_ok, detail=detail,
        )

    # Action commands: infer from neighbors.
    for name, value in action_pending:
        status, _ec, detail_msg = _categorize_action(name, results_by_name)
        counts[status] = counts.get(status, 0) + 1
        is_critical = name in _CRITICAL_NAMES
        step_ok = status == "SUPPORTED"
        if not step_ok and is_critical:
            critical_unsupported.append(name)
        if include_supported or not step_ok or is_critical:
            steps.append(SequenceStepResult(
                label=f"{name} (ACTION) → {value}",
                success=step_ok,
                detail=f"{status} ★ ← {detail_msg}" if is_critical else f"{status} ← {detail_msg}",
                duration_ms=0,
            ))

    log(
        f"  · done: "
        f"{counts.get('SUPPORTED', 0)} supported, "
        f"{counts.get('SUPPORTED_BUT_STATE', 0)} state, "
        f"{counts.get('UNSUPPORTED', 0)} unsupported, "
        f"{counts.get('UNKNOWN', 0)} unknown"
        + (" — ABORTED EARLY (SCPI channel stuck)" if aborted_early else "")
    )
    if critical_unsupported:
        log(f"  ✗ CRITICAL UNSUPPORTED: {sorted(critical_unsupported)}")

    success = (not critical_unsupported) and (not aborted_early)
    if aborted_early:
        summary = (
            f"ABORTED: {_MAX_CONSECUTIVE_TIMEOUTS} consecutive VISA timeouts on "
            f"profile {profile.PROFILE_NAME}. Last probed: {last_probed}. "
            f"SCPI session is stuck — POST /api/v1/instruments/hal/reload and retry."
        )
    elif not critical_unsupported:
        summary = (
            f"All {len(_CRITICAL_NAMES)} critical SCPI commands supported on "
            f"profile {profile.PROFILE_NAME} "
            f"({counts.get('UNSUPPORTED', 0)} non-critical unsupported, "
            f"{counts.get('SUPPORTED_BUT_STATE', 0)} state errors — both OK)"
        )
    else:
        summary = (
            f"BLOCKER: {len(critical_unsupported)} critical SCPI command(s) "
            f"unsupported on profile {profile.PROFILE_NAME}. Driver needs vendor "
            f"aliases for: {sorted(critical_unsupported)}"
        )

    return SequenceRunResult(
        success=success,
        summary=summary,
        steps=steps,
        extra={
            "profile": profile.PROFILE_NAME,
            "counts": counts,
            "critical_unsupported": sorted(critical_unsupported),
            "total_probed": len(all_cmds),
            "include_supported": include_supported,
            "aborted_early": aborted_early,
        },
    )
