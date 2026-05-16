"""Plan-level pre-flight validator (P1-1, first-call roadmap).

# Why this exists

Before P1-1, the failure mode was: compose a plan in the GUI → click Run →
phase 4 of 5 fails because the F64 doesn't have the K01 interference-
generator license → debug for 30 min on-site → discover the driver
already knows the license is missing (capability set) but nothing was
asked at plan-edit time. P2-2 (PR #21) gave drivers a canonical
`driver.capabilities: Set[str]` so a single validation pass can answer
"does this lab have everything this plan asks for?" without per-driver
attribute peeks.

This module is the validation pass. It takes a `TestPlan` + a
`LabProfile`, iterates the plan's `TestStep` rows in execution order,
checks each step's `needs: List[str]` declaration against the
capabilities of drivers **scoped per-binding (category + endpoint
match) to this lab's `instrument_bindings`**, and returns a typed
`PreflightResult` with gaps, unknown-token warnings, bound-but-not-
loaded categories, and driver mismatches. The operator-facing surface
(POST /api/v1/test-plans/{id}/preflight) returns the same shape; the
GUI's "预检" button (PR B) renders it.

# Design choices

- **Scope per binding, not per category.** Pre-#24-fix this matched by
  `category_key in bound_keys`, which the second Codex P1 caught: if two
  labs both bind a `channelEmulator` but to different physical units
  (different endpoints / different license sets), the lab-A driver
  loaded in HAL would still satisfy lab-B's needs. Fix: compare each
  binding's `connection_endpoint` against the loaded driver's
  `config["endpoint"]` (or assembled `ip:port`). Mismatches surface in
  `mismatched_drivers` separate from `not_loaded_categories` because
  the operator hint is subtly different (mismatch → reload HAL bound
  to *this* lab or fix the binding; not-loaded → reload HAL period).
  When the binding row has no endpoint (older data), the scoping
  loosens to category-only with a warning — see _binding_endpoint.

- **Iterate all in-scope drivers, don't pre-map token prefix → category.**
  Simplest semantic: "no in-scope driver exposes this token" is the
  gap. The token namespace (`ce.*` / `pos.*` / …) is informational only.
  Avoids maintaining a prefix-to-category-key lookup table that would
  drift out of sync with `KNOWN_CAPABILITIES`.

- **Three distinct readiness signals**: gaps (license/hardware), not-
  loaded categories (HAL didn't bring up the driver at all), mismatched
  drivers (HAL brought up a driver but for the wrong unit). Conflating
  these would force the GUI to re-derive the remediation hint.

- **Unknown tokens warn, don't gap**. A typo in `needs` shouldn't kill
  the plan — the gap path already prevents running a plan that's
  missing real capabilities. Surfacing unknown tokens separately gives
  the operator + the next dev a chance to fix the typo without losing
  the green light on the rest of the plan.

- **Default empty `needs` == permissive**. Existing seeded steps stay
  green; we add `needs` only where the step has a real hardware
  contract that can be checked (e.g. F64 calibration-tone step needs
  `ce.interference_generator`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.hal.capabilities import KNOWN_CAPABILITIES
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestPlan, TestStep


@dataclass(frozen=True)
class Gap:
    """One unmet capability requirement on a specific plan step."""
    step_id: UUID
    step_name: str
    step_order: int
    missing_token: str
    reason: str  # human-readable, surfaced into the GUI gap modal


@dataclass(frozen=True)
class DriverMismatch:
    """A bound category has a HAL driver loaded, but for a different
    physical instrument (different endpoint) than this lab declares.

    Different remediation from ``not_loaded_categories``: there the
    driver isn't loaded at all (reload HAL); here the driver is up but
    bound to someone else's lab (reload HAL with this lab's config, or
    fix this lab's binding to match what's loaded). The GUI surfaces
    both lists separately so the operator sees the right hint."""
    category: str
    expected_endpoint: str  # from lab.instrument_bindings[*].connection_endpoint
    loaded_endpoint: str  # from driver.config endpoint/ip:port


@dataclass(frozen=True)
class PreflightResult:
    plan_id: UUID
    lab_profile_id: UUID
    gaps: List[Gap] = field(default_factory=list)
    unknown_tokens: List[str] = field(default_factory=list)
    lab_capabilities: List[str] = field(default_factory=list)
    """Sorted union of tokens exposed by drivers scoped per-binding
    (category + endpoint match) to this lab. Does NOT include
    capabilities from drivers HAL loaded for other labs even if the
    category key matches."""
    not_loaded_categories: List[str] = field(default_factory=list)
    """Sorted list of category keys the lab binds but HAL has not
    loaded any driver for. Distinguishes "operator forgot to reload
    HAL after swapping LabProfile" from gaps."""
    mismatched_drivers: List[DriverMismatch] = field(default_factory=list)
    """Categories where HAL has a driver loaded, but for a different
    instrument (endpoint) than this lab binds. Separate from
    not_loaded_categories because the operator hint is different."""

    @property
    def ready(self) -> bool:
        """True iff the plan can be run as-is against this lab.
        Gaps block; unknown tokens / not-loaded / mismatched are
        informational. An empty-needs plan against a half-misconfigured
        lab is still "ready" — nothing to block on."""
        return not self.gaps


def _normalize_endpoint(raw: Any) -> str:
    """Strip whitespace and lowercase. Used both for display and as
    input to ``_parse_endpoint``."""
    if raw is None:
        return ""
    return str(raw).strip().lower()


def _parse_endpoint(raw: Any) -> Tuple[str, str]:
    """Normalize an endpoint string into a ``(host, port)`` tuple
    so VISA-style and plain forms for the same physical unit
    compare equal.

    Codex P2 on PR #24 caught the gap: when InstrumentHALService
    builds ``driver.config``, it copies ``InstrumentConnection.endpoint``
    verbatim — which for VISA-managed drivers is the resource string
    (``TCPIP0::192.168.0.132::5025::INSTR``). The lab wizard saves
    bindings as the documented plain form (``192.168.0.132:5025``).
    String compare reports false-positive mismatch.

    Recognized forms (return value in parentheses):
    - ``TCPIP[N]::host::port::INSTR/SOCKET/RAW`` → ``(host, port)``
    - ``TCPIP[N]::host::named::INSTR`` (HiSLIP / VXI-11 named
      resource like ``hislip0`` / ``hislip2`` / ``inst0``) →
      ``(host, name)`` — name is **preserved verbatim**, NOT
      collapsed to ``(host, "")``. Different named resources on
      the same host address different SCPI subsystems and must
      not compare equal. UXM 5G (E7515B) is the canonical example:
      on the same IP, ``hislip0`` is the platform endpoint
      (system-level SCPI) and ``hislip2`` is the test-application
      framework (different command tree — see
      ``app/hal/uxm_command_profiles.py``). Codex P1 on PR #25
      caught the earlier conservative-but-wrong collapse.
    - ``host:port`` → ``(host, port)``
    - ``host`` (bare) → ``(host, "")``
    - non-TCPIP VISA (``USB::``, ``GPIB::``, ``ASRL::``) → the whole
      normalized string as ``(s, "")`` — we don't try to parse
      vendor/serial-shaped tokens, but identical strings still match
    - empty / None → ``("", "")``

    Strict interpretation: ``(host, "5025")`` ≠ ``(host, "hislip0")``
    ≠ ``(host, "")``. Operators who bind one form against a HAL
    loaded on another get a legitimate ``mismatched_drivers`` entry —
    same host but different SCPI endpoint is a real divergence.
    """
    s = _normalize_endpoint(raw)
    if not s:
        return ("", "")
    if "::" in s:
        parts = s.split("::")
        # VISA TCPIP family: "tcpip", "tcpip0", "tcpip1" etc.
        if len(parts) >= 3 and parts[0].startswith("tcpip"):
            host = parts[1]
            port_or_name = parts[2]
            # Keep the third token verbatim — numeric port OR named
            # resource (hislip0/hislip2/inst0). Collapsing names to
            # the host alone would let a UXM driver loaded on
            # hislip0 (platform) satisfy a binding declared on
            # hislip2 (test-app framework) — different SCPI
            # subsystems on the same instrument.
            return (host, port_or_name)
        # Non-TCPIP VISA — return the full normalized string as-is.
        # Identical USB::0x2A8D::... strings on both sides still match.
        return (s, "")
    if ":" in s:
        host, _, port = s.rpartition(":")
        return (host, port)
    return (s, "")


def _driver_endpoint_candidates(driver: Any) -> Set[Tuple[str, str]]:
    """Collect ALL plausible ``(host, port)`` tuples for a driver.

    When ``InstrumentHALService._initialize_from_db`` builds the
    config it may set BOTH ``endpoint`` (raw connection string,
    often VISA-shaped) AND ``ip`` + ``port`` (parsed alias fields
    from the same DB row). Pre-fix the validator returned the first
    non-empty form, so a binding using one form against a driver
    serving the other was falsely flagged. Now we yield every form
    we can parse out of the config — the binding-side parse just
    needs to match ANY of them."""
    cfg = getattr(driver, "config", None) or {}
    out: Set[Tuple[str, str]] = set()
    ep = cfg.get("endpoint")
    if ep:
        parsed = _parse_endpoint(ep)
        if parsed != ("", ""):
            out.add(parsed)
    ip = cfg.get("ip")
    port = cfg.get("port")
    if ip and port:
        out.add(_parse_endpoint(f"{ip}:{port}"))
    elif ip:
        out.add(_parse_endpoint(ip))
    return out


def _driver_endpoint_for_display(driver: Any) -> str:
    """Pick the most operator-friendly endpoint form for surfacing
    in a ``DriverMismatch`` — prefer the parsed ``ip:port`` since
    it's what the wizard speaks, fall back to the raw VISA string
    only when nothing else is set."""
    cfg = getattr(driver, "config", None) or {}
    ip = cfg.get("ip")
    port = cfg.get("port")
    if ip and port:
        return f"{ip}:{port}"
    ep = cfg.get("endpoint")
    if ep:
        return str(ep)
    if ip:
        return str(ip)
    return ""


def _binding_endpoint(entry: Dict[str, Any]) -> str:
    """Extract the expected endpoint from one lab binding row.

    Empty string means the binding row didn't declare an endpoint —
    older data, or a binding the wizard saved with just category+model.
    The validator treats this as a weakly-scoped binding: category
    match is accepted (preserves backwards compat) but the operator
    won't get the stricter "wrong unit" protection until they re-save
    the lab profile via the wizard."""
    return _normalize_endpoint(entry.get("connection_endpoint"))


def _bound_endpoints_by_key(
    lab: LabProfile, db: Session,
) -> Dict[str, str]:
    """Map `category_key → expected_endpoint` for each binding row.

    The HAL `drivers` dict is keyed by `category_key` (string), but
    LabProfile bindings reference `category_id` (UUID). One join here
    flips the keys so the validator can do its per-category lookup
    without re-resolving on every step.

    If two binding rows target the same category (unusual but legal
    today since the JSON column doesn't enforce uniqueness), the last
    one wins — this matches the HAL's "one driver per category" reality.
    """
    bindings = lab.instrument_bindings or []
    id_to_endpoint: Dict[UUID, str] = {}
    for entry in bindings:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("category_id")
        if raw is None:
            continue
        try:
            cid = UUID(str(raw))
        except (ValueError, TypeError):
            # Malformed binding row — skip rather than 500 the
            # whole pre-flight; the operator will see the
            # corresponding category as unbound and can fix it.
            continue
        id_to_endpoint[cid] = _binding_endpoint(entry)
    if not id_to_endpoint:
        return {}

    from app.models.instrument import InstrumentCategory  # avoid cycle
    rows = (
        db.query(InstrumentCategory.id, InstrumentCategory.category_key)
        .filter(InstrumentCategory.id.in_(id_to_endpoint.keys()))
        .all()
    )
    out: Dict[str, str] = {}
    for cid, key in rows:
        if key:
            out[key] = id_to_endpoint.get(cid, "")
    return out


def validate_plan(
    plan: TestPlan,
    lab: LabProfile,
    db: Session,
    hal_drivers: dict,
) -> PreflightResult:
    """Iterate ``plan``'s steps in execution order and produce a
    ``PreflightResult`` scoped per-binding to ``lab``.

    ``hal_drivers`` is the live ``InstrumentHALService.drivers`` dict
    (``{category_key: driver_instance}``). For each lab binding, the
    validator checks both that a driver of the right category is
    loaded AND that the driver's endpoint matches the binding's
    expected endpoint. Mismatches go into ``mismatched_drivers``;
    only fully-matched drivers contribute capabilities.

    Pure-function: no side effects, no DB writes. Callers persist /
    log / return the result themselves.
    """
    bound_endpoints = _bound_endpoints_by_key(lab, db)

    scoped_drivers: Dict[str, Any] = {}
    not_loaded: List[str] = []
    mismatches: List[DriverMismatch] = []

    for cat_key, expected_ep in bound_endpoints.items():
        driver = hal_drivers.get(cat_key)
        if driver is None:
            not_loaded.append(cat_key)
            continue
        if not expected_ep:
            # Weak binding: no endpoint declared, fall back to
            # category-only match. Preserves behavior for older lab
            # profiles that the wizard saved without endpoints.
            scoped_drivers[cat_key] = driver
            continue
        # Compare on parsed (host, port) tuples so VISA-style
        # endpoints and plain ip:port for the same physical unit
        # both match (Codex P2 follow-up on #24). Driver may have
        # multiple parseable forms in its config (raw VISA endpoint
        # AND parsed ip/port aliases) — accept a match against any.
        binding_tuple = _parse_endpoint(expected_ep)
        driver_tuples = _driver_endpoint_candidates(driver)
        if binding_tuple in driver_tuples:
            scoped_drivers[cat_key] = driver
        else:
            # Driver up but for a different unit — record mismatch
            # and DON'T pull its capabilities into scope. The lab's
            # needs in this category will gap. Display the cleanest
            # representation (parsed ip:port preferred over verbose
            # VISA resource string) so the operator can compare
            # against the binding without parsing TCPIP::host::...
            mismatches.append(DriverMismatch(
                category=cat_key,
                expected_endpoint=expected_ep,
                loaded_endpoint=_driver_endpoint_for_display(driver) or
                                "(unknown — driver did not expose endpoint in config)",
            ))

    loaded_in_scope: Sequence[str] = sorted(scoped_drivers.keys())
    not_loaded.sort()
    mismatches.sort(key=lambda m: m.category)
    mismatched_keys: List[str] = [m.category for m in mismatches]

    all_capabilities: set[str] = set()
    for driver in scoped_drivers.values():
        all_capabilities |= getattr(driver, "capabilities", set())

    steps: Sequence[TestStep] = (
        db.query(TestStep)
        .filter(TestStep.test_plan_id == plan.id)
        .order_by(TestStep.order)
        .all()
    )

    gaps: List[Gap] = []
    unknown_seen: set[str] = set()

    for step in steps:
        needs = step.needs or []
        for token in needs:
            if token not in KNOWN_CAPABILITIES:
                unknown_seen.add(token)
                continue  # typo guard — don't block the plan, just warn

            if token not in all_capabilities:
                # Three remediation hints we can surface (one or more
                # may apply per gap):
                #  - not_loaded: HAL never brought up this category
                #  - mismatched: HAL has the category up, but for the
                #    wrong physical unit (this lab's endpoint differs)
                #  - neither:    driver is up + correct, license/hardware
                #    just doesn't expose the needed token
                bound_display = (
                    list(sorted(bound_endpoints.keys()))
                    if bound_endpoints
                    else "(none — lab has no instrument_bindings)"
                )
                bits = [
                    f"No driver in this lab's bindings exposes {token!r}.",
                    f"Bound categories: {bound_display}.",
                    f"Loaded in scope: {list(loaded_in_scope) or '(none)'}.",
                ]
                if not_loaded:
                    bits.append(
                        f"Bound but not loaded: {not_loaded} — "
                        f"reload HAL or check the connection."
                    )
                if mismatched_keys:
                    bits.append(
                        f"Loaded but bound to a different unit: "
                        f"{mismatched_keys} — reload HAL with this "
                        f"lab's config, or fix the lab binding's endpoint."
                    )
                if not not_loaded and not mismatched_keys:
                    bits.append(
                        "Check that the required hardware / license is "
                        "connected and the bound driver came up cleanly."
                    )
                gaps.append(Gap(
                    step_id=step.id,
                    step_name=step.name or f"step #{step.order}",
                    step_order=step.order,
                    missing_token=token,
                    reason=" ".join(bits),
                ))

    return PreflightResult(
        plan_id=plan.id,
        lab_profile_id=lab.id,
        gaps=gaps,
        unknown_tokens=sorted(unknown_seen),
        lab_capabilities=sorted(all_capabilities),
        not_loaded_categories=list(not_loaded),
        mismatched_drivers=list(mismatches),
    )
