"""P3-5 — HAL readiness report aggregation.

Single source of truth for "what state is the chamber in right now".
Bundles three previously-scattered signals so the operator (and Slack
paste-ables, and the future GUI panel) get a coherent answer in one
place:

1. **Driver readiness** — per-loaded-driver row (category, model, endpoint,
   ok/fail/skipped, detail) plus a free-form ``extras`` dict for
   driver-specific metadata the driver wants to surface in the readiness
   table without the report having to know about every driver class.
   F64 uses this to expose parsed ``SYST:INFO?`` fields (firmware_version,
   band_label, product_family) added in P3-4 (PR #33), which were stored
   on the driver instance but never reachable from outside the process.
2. **Lab-profile section** — which ``LabProfile`` row is the system
   pointing at, is it active, what's its name. Today the only way to
   know "did the operator finish the wizard?" is to grep server logs;
   surfacing it here lets the GUI HAL panel show a single green/yellow
   chip.
3. **Calibration section** — the active lab's
   ``active_calibration_certificate``, its ``valid_until`` validity, days
   remaining. Operators can see "calibration expires in 3 days" before
   the cert dies mid-run.

**DUT-attach is deliberately a placeholder.** P3-5's roadmap line
mentions DUT-attach state, but the codebase has no runtime model for
"DUT is currently in the chamber" — no probe-sensing, chamber-RFID,
session table, nothing. Reporting fake-ok would be a lie, reporting
nothing leaves a future P3-x worker without a slot to fill. So we
return ``status="not_implemented"`` with a clear ``detail`` — the shape
is forward-compatible, the operator sees the truth, and the next worker
just swaps the implementation when sensing exists.

This module is intentionally pure / SQL-only (no HAL imports) so tests
can build a synthetic DB and exercise the lab + cal helpers without
spinning up the full driver factory.
"""
from __future__ import annotations

import ipaddress
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.calibration import CalibrationCertificate
from app.models.lab_profile import LabProfile


@dataclass(frozen=True)
class DriverReadinessRow:
    """One driver's readiness state as it appears in the HAL report.

    The five core fields (``category`` … ``detail``) match what the
    pre-P3-5 ``_log_readiness_report`` already rendered — the only new
    field is ``extras``. Keeping the core unchanged means the formatted
    log table stays diff-able with old captures.
    """

    category: str
    model: str
    endpoint: str
    status: str  # "ok" | "fail" | "skipped"
    detail: str
    extras: Dict[str, Any] = field(default_factory=dict)
    # P1-11: when ``status == "fail"``, why did it fail?
    #   "network" — TCP/preflight couldn't reach the host (most likely the
    #               control PC isn't on the instrument's /24 subnet)
    #   "scpi"    — TCP reached the host but driver.connect() / *IDN? failed
    #               (instrument/session problem, not a routing problem)
    # ``None`` whenever ``status != "fail"``. Surfaced so readiness can tell
    # the operator "fix your subnet" (network) vs "check the instrument"
    # (scpi) instead of a single opaque ``fail``.
    fail_kind: Optional[str] = None  # "network" | "scpi" | None
    # P1-13: explicit network-probe outcome, independent of status/fail_kind:
    #   True  — TCP preflight ran and the host was alive (connect or refused)
    #   False — TCP preflight ran and the host was dead (timeout / no route)
    #   None  — preflight did NOT run (mock driver, or no parseable host:port).
    # Needed because "no network-fail" ≠ "reachable": a row that was never
    # probed (preflight skipped) must NOT make its subnet look reachable.
    network_reachable: Optional[bool] = None


@dataclass(frozen=True)
class SubnetReachability:
    """P1-11: per-/24-subnet reachability rollup of the driver rows.

    CAICT's instruments live across two /24 subnets (F64 on
    ``192.168.0.x``, UXM + SA on ``192.168.1.x``) and the single-NIC
    control Mac can only sit on one subnet at a time. When a whole
    subnet is unreachable the operator was getting one opaque VISA
    error per instrument; this rollup says "this entire subnet is
    unreachable, here's what to do" once per subnet.

    P1-13 tri-state via (``probed``, ``reachable``):
    - ``probed=False``                 — NO instrument on this subnet was
      actually network-probed (all mock / no parseable host:port). The subnet
      is **未探测/unknown** — we must NOT claim it reachable. (e.g. mock-HAL
      mode never probes the network, so every subnet is unknown.)
    - ``probed=True, reachable=False``  — ≥1 instrument's preflight timed out
      (``network_reachable is False``): the network layer can't route here.
    - ``probed=True, reachable=True``   — instruments were probed and none
      failed at the network layer.

    The pre-P1-13 bug: a subnet whose instruments were never preflighted
    (e.g. bindings with the IP only in the VISA endpoint string, so the
    controller_ip/port-gated preflight was skipped) had no ``network`` fail and
    was therefore mislabelled **reachable** — even with no route to it.

    ``hint`` is a runbook-pointing actionable string for unreachable subnets,
    ``None`` otherwise.
    """

    cidr: str
    reachable: bool
    instrument_count: int
    unreachable_count: int
    hint: Optional[str]
    # P1-13: was any instrument on this subnet actually network-probed?
    # False → 未探测/unknown (don't render as reachable).
    probed: bool = False


@dataclass(frozen=True)
class LabProfileReadiness:
    """Aggregated state of the active ``LabProfile`` row.

    ``status`` semantics:
    - ``"ok"`` — exactly one ``is_active=True`` row found, has a name.
    - ``"inactive"`` — rows exist but none is active. Operator created
      profiles then turned them all off; HAL has nothing to bind to.
    - ``"missing"`` — no ``LabProfile`` rows at all. Fresh install — the
      P0-2 init wizard hasn't been run yet.
    - ``"ambiguous"`` — two or more ``is_active=True`` rows. Schema
      doesn't enforce singleton (intentional — historical executions
      may pin a "previously active" profile), but at runtime the
      ambiguity is a bug to flag.
    """

    profile_id: Optional[str]
    profile_name: Optional[str]
    is_active: bool
    status: str  # "ok" | "inactive" | "missing" | "ambiguous"
    detail: str


@dataclass(frozen=True)
class CalibrationReadiness:
    """Validity state of the active lab's bound calibration certificate.

    ``status`` semantics:
    - ``"valid"`` — cert exists, ``valid_until > now``.
    - ``"expired"`` — cert exists, ``valid_until <= now``. Tests that
      consume path-loss tables will run with stale calibration.
    - ``"missing"`` — lab is set but ``active_calibration_certificate_id``
      is NULL. P0-3 hasn't been run yet, or the operator manually
      detached a cert and didn't re-bind one.
    - ``"no_lab"`` — no active lab to even look at a cert through.
      Distinguished from ``"missing"`` so the GUI can show "set up a
      lab first" vs "run calibration" — different next-steps for the
      operator.
    """

    certificate_number: Optional[str]
    valid_until_iso: Optional[str]
    status: str  # "valid" | "expired" | "missing" | "no_lab"
    days_remaining: Optional[int]
    detail: str


@dataclass(frozen=True)
class DutAttachReadiness:
    """Placeholder for DUT-attach sensing.

    See module docstring. Always returns ``status="not_implemented"``
    in this build — the shape is the contract; the implementation is
    a future P3-x item that wires up probe-sensing or chamber-RFID.
    Surfacing the field now so the readiness payload doesn't change
    shape later (no GUI / openapi contract break when sensing lands).
    """

    status: str = "not_implemented"
    detail: str = (
        "DUT attach sensing not implemented in this build "
        "(no probe-sensing / RFID / session table yet — future P3 item)"
    )


@dataclass(frozen=True)
class ReadinessReport:
    """Composite snapshot returned by ``GET /instruments/hal/readiness``."""

    drivers: List[DriverReadinessRow]
    lab_profile: LabProfileReadiness
    calibration: CalibrationReadiness
    dut_attach: DutAttachReadiness
    generated_at_iso: str
    # P1-11: per-/24-subnet reachability rollup derived from ``drivers``.
    subnets: List[SubnetReachability] = field(default_factory=list)


def build_lab_profile_readiness(db: Session) -> LabProfileReadiness:
    """Inspect ``lab_profiles`` and classify the system's lab state.

    Pure SQL — no HAL coupling so tests can call this with a fixture DB.
    """
    profiles = db.query(LabProfile).all()
    if not profiles:
        return LabProfileReadiness(
            profile_id=None,
            profile_name=None,
            is_active=False,
            status="missing",
            detail="no LabProfile rows — run the init wizard (P0-2)",
        )

    active = [p for p in profiles if p.is_active]
    if not active:
        return LabProfileReadiness(
            profile_id=None,
            profile_name=None,
            is_active=False,
            status="inactive",
            detail=(
                f"{len(profiles)} profile(s) exist but none is active — "
                "set is_active=True on one or create a new active profile"
            ),
        )

    if len(active) > 1:
        # Multiple active rows: pick the first deterministically (by name)
        # so the report is stable across calls, but flag the ambiguity.
        chosen = sorted(active, key=lambda p: p.name or "")[0]
        return LabProfileReadiness(
            profile_id=str(chosen.id),
            profile_name=chosen.name,
            is_active=True,
            status="ambiguous",
            detail=(
                f"{len(active)} active LabProfiles found "
                f"({', '.join(sorted(p.name for p in active if p.name))}); "
                f"reporting {chosen.name!r}. Schema allows multiple but "
                "runtime expects one — disable the extras."
            ),
        )

    chosen = active[0]
    return LabProfileReadiness(
        profile_id=str(chosen.id),
        profile_name=chosen.name,
        is_active=True,
        status="ok",
        detail=f"active LabProfile {chosen.name!r}",
    )


def build_calibration_readiness(
    db: Session, lab_section: LabProfileReadiness, now: Optional[datetime] = None
) -> CalibrationReadiness:
    """Inspect the active lab's bound cert and classify validity.

    Takes the already-built ``lab_section`` so it doesn't re-query
    LabProfile — the caller has it and the two sections share the
    "what lab are we pointing at" decision.

    ``now`` is injectable so expiry tests can pin a deterministic clock.
    """
    if now is None:
        now = datetime.utcnow()

    if not lab_section.is_active or lab_section.profile_id is None:
        return CalibrationReadiness(
            certificate_number=None,
            valid_until_iso=None,
            status="no_lab",
            days_remaining=None,
            detail="no active lab to bind a calibration certificate to",
        )

    # ``profile_id`` was stringified for the wire-shape; convert back
    # to UUID for the typed column comparison so SQLite + Postgres
    # both bind correctly (SQLite's UUID adapter chokes on str).
    try:
        profile_uuid = uuid.UUID(lab_section.profile_id)
    except (TypeError, ValueError):
        return CalibrationReadiness(
            certificate_number=None,
            valid_until_iso=None,
            status="no_lab",
            days_remaining=None,
            detail=f"invalid profile_id {lab_section.profile_id!r}",
        )
    lab = (
        db.query(LabProfile)
        .filter(LabProfile.id == profile_uuid)
        .first()
    )
    if lab is None or lab.active_calibration_certificate_id is None:
        return CalibrationReadiness(
            certificate_number=None,
            valid_until_iso=None,
            status="missing",
            days_remaining=None,
            detail=(
                f"lab {lab_section.profile_name!r} has no active calibration "
                "certificate bound — run path-loss calibration (P0-3)"
            ),
        )

    cert = (
        db.query(CalibrationCertificate)
        .filter(CalibrationCertificate.id == lab.active_calibration_certificate_id)
        .first()
    )
    if cert is None:
        # FK points at a deleted row. Schema has ON DELETE SET NULL on
        # this FK so this state should be unreachable, but the DB could
        # also be hand-edited or restored from a stale dump — be defensive.
        return CalibrationReadiness(
            certificate_number=None,
            valid_until_iso=None,
            status="missing",
            days_remaining=None,
            detail=(
                f"lab {lab_section.profile_name!r} references certificate "
                f"{lab.active_calibration_certificate_id} but the row is "
                "missing (DB inconsistency — rebind a cert)"
            ),
        )

    days_remaining = (cert.valid_until - now).days
    if cert.valid_until <= now:
        status = "expired"
        detail = (
            f"certificate {cert.certificate_number} expired "
            f"{abs(days_remaining)} day(s) ago — re-run calibration"
        )
    else:
        status = "valid"
        detail = (
            f"certificate {cert.certificate_number} valid for "
            f"{days_remaining} more day(s) "
            f"(until {cert.valid_until.isoformat()})"
        )

    return CalibrationReadiness(
        certificate_number=cert.certificate_number,
        valid_until_iso=cert.valid_until.isoformat(),
        status=status,
        days_remaining=days_remaining,
        detail=detail,
    )


def build_dut_attach_readiness() -> DutAttachReadiness:
    """Placeholder — always returns ``not_implemented``. See module docstring."""
    return DutAttachReadiness()


# P1-11: pull a bare IPv4 host out of an endpoint string. The driver
# rows carry endpoints in two production shapes (see
# instrument_hal_service._initialize_from_db):
#   - "192.168.0.132:5025"                       (controller_ip:port)
#   - "TCPIP0::192.168.0.132::inst0::INSTR"      (VISA resource string)
# Either way we want the host. We deliberately do NOT resolve hostnames
# — instruments are configured by IP in this system, and a DNS lookup in
# a readiness path would reintroduce the slow-blocking problem P1-#15's
# preflight removed.
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def parse_subnet_cidr(endpoint: str) -> Optional[str]:
    """Return the ``/24`` CIDR for the first IPv4 host in ``endpoint``.

    ``192.168.0.132:5025`` → ``"192.168.0.0/24"``;
    ``TCPIP0::192.168.0.132::inst0::INSTR`` → ``"192.168.0.0/24"``.
    Returns ``None`` when no parseable IPv4 host is present (hostname-only
    endpoints, empty strings) — the caller buckets those as "unknown"
    rather than crashing.
    """
    if not endpoint:
        return None
    m = _IPV4_RE.search(endpoint)
    if not m:
        return None
    try:
        net = ipaddress.ip_network(f"{m.group(0)}/24", strict=False)
    except ValueError:
        return None
    return str(net)


def build_subnet_reachability(
    rows: List[DriverReadinessRow],
) -> List[SubnetReachability]:
    """Group driver rows by their /24 subnet and roll up reachability.

    P1-13 tri-state, driven by each row's ``network_reachable`` probe outcome
    (NOT by "absence of a network-fail", which the pre-P1-13 version used and
    which mislabelled never-probed subnets as reachable):
    - ``network_reachable is False`` on any row → subnet ``reachable=False``
      (probed, route dead).
    - else if ``network_reachable is True`` on any row → ``reachable=True,
      probed=True`` (probed, route alive).
    - else (every row ``None`` — none probed: mock / no host:port) →
      ``probed=False`` → 未探测/unknown; ``reachable`` is meaningless, left
      False, GUI renders neutral.

    Rows whose endpoint has no parseable IPv4 host are grouped under the
    sentinel CIDR ``"unknown"``.

    Output is sorted by CIDR, ``"unknown"`` last.
    """
    # cidr -> [rows]
    groups: Dict[str, List[DriverReadinessRow]] = {}
    for r in rows:
        cidr = parse_subnet_cidr(r.endpoint) or "unknown"
        groups.setdefault(cidr, []).append(r)

    result: List[SubnetReachability] = []
    for cidr, group_rows in groups.items():
        dead = [r for r in group_rows if r.network_reachable is False]
        alive = [r for r in group_rows if r.network_reachable is True]
        probed = bool(dead or alive)
        # reachable only when probed AND nothing on it failed the network probe.
        reachable = probed and not dead
        if probed and dead:
            hint = (
                f"子网 {cidr} 不可达：参见 "
                "docs/guides/multi-subnet-instrument-network.md 方案 A"
                "（单网卡加 IP 别名），或确认交换机连线"
            )
        elif not probed:
            hint = (
                f"子网 {cidr} 未探测：本子网无仪表做 TCP preflight "
                "（mock 模式不探网络，或 binding 缺 host:port）——可达性未知"
            )
        else:
            hint = None
        result.append(
            SubnetReachability(
                cidr=cidr,
                reachable=reachable,
                instrument_count=len(group_rows),
                unreachable_count=len(dead),
                hint=hint,
                probed=probed,
            )
        )

    # Stable order; keep the "unknown" bucket at the end.
    result.sort(key=lambda s: (s.cidr == "unknown", s.cidr))
    return result
