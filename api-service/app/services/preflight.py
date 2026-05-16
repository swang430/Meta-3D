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
checks each step's `needs: List[str]` declaration against the union of
capabilities exposed by drivers **scoped to this lab's
`instrument_bindings`** (not the global HAL singleton), and returns a
typed `PreflightResult` with gaps, unknown-token warnings, and a list
of bound-but-not-loaded categories. The operator-facing surface
(POST /api/v1/test-plans/{id}/preflight) returns the same shape; the
GUI's "预检" button (PR B) renders it.

# Design choices

- **Scope drivers by `lab.instrument_bindings`, NOT by global HAL state.**
  The endpoint takes a `lab_profile_id` query — the answer must reflect
  *that specific lab's* hardware contract. Pre-#22-fix this used
  `hal.drivers.values()` globally, so a deployment where HAL had been
  initialized from a different lab's instruments could return
  ready: true for a capability the selected lab cannot actually
  provide. Codex P1 on PR #22 caught this; fix landed in PR #23.

- **Iterate all in-scope drivers, don't pre-map token prefix → category.**
  Simplest semantic: "no in-scope driver exposes this token" is the
  gap. The token namespace (`ce.*` / `pos.*` / …) is informational only.
  Avoids maintaining a prefix-to-category-key lookup table that would
  drift out of sync with `KNOWN_CAPABILITIES`.

- **Surface bound-but-not-loaded categories separately.** The most common
  field regression is "operator swapped LabProfile without reloading
  HAL" — without distinguishing this from "license actually missing",
  every gap looks like a hardware procurement issue. The
  `not_loaded_categories` field lets the GUI direct the operator to
  the right corrective action.

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
from typing import List, Sequence
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
class PreflightResult:
    plan_id: UUID
    lab_profile_id: UUID
    gaps: List[Gap] = field(default_factory=list)
    unknown_tokens: List[str] = field(default_factory=list)
    lab_capabilities: List[str] = field(default_factory=list)
    """Sorted union of tokens exposed by HAL drivers WHOSE category this
    lab binds. Scoped — does NOT include capabilities from drivers HAL
    loaded for other labs / a different global config."""
    not_loaded_categories: List[str] = field(default_factory=list)
    """Sorted list of category keys the lab binds but HAL has not loaded
    a driver for. Distinguishes "operator forgot to reload HAL after
    swapping LabProfile" from "license actually missing" — they need
    different corrective actions."""

    @property
    def ready(self) -> bool:
        """True iff the plan can be run as-is against this lab.
        Gaps block; unknown tokens warn but don't block (a future
        token registration would unblock without re-validating).
        ``not_loaded_categories`` is informational — it'll typically
        show up alongside gaps from the same category, but an empty
        plan against a lab with not-loaded bindings is still ready
        (nothing to block on)."""
        return not self.gaps


def _bound_category_keys(lab: LabProfile, db: Session) -> set[str]:
    """Resolve ``lab.instrument_bindings[*].category_id`` (UUID) into
    the corresponding ``InstrumentCategory.category_key`` strings that
    HAL uses as its `drivers` dict keys.

    Lazy import of ``InstrumentCategory`` to avoid a circular dependency
    on module load (this module is imported from `app.api.test_plan`,
    which is mounted early in app/main.py).
    """
    bindings = lab.instrument_bindings or []
    bound_ids: set[UUID] = set()
    for entry in bindings:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("category_id")
        if raw is None:
            continue
        try:
            bound_ids.add(UUID(str(raw)))
        except (ValueError, TypeError):
            # Malformed binding row — skip rather than 500 the
            # whole pre-flight; the operator will see the
            # corresponding category as not-bound and can fix it.
            continue
    if not bound_ids:
        return set()

    from app.models.instrument import InstrumentCategory  # avoid cycle
    rows = (
        db.query(InstrumentCategory.category_key)
        .filter(InstrumentCategory.id.in_(bound_ids))
        .all()
    )
    return {r[0] for r in rows if r[0]}


def validate_plan(
    plan: TestPlan,
    lab: LabProfile,
    db: Session,
    hal_drivers: dict,
) -> PreflightResult:
    """Iterate ``plan``'s steps in execution order and produce a
    ``PreflightResult`` scoped to ``lab``'s ``instrument_bindings``.

    ``hal_drivers`` is the live ``InstrumentHALService.drivers`` dict
    (``{category_key: driver_instance}``). The validator filters this
    dict down to only the keys the lab actually binds, then unions
    those drivers' ``driver.capabilities`` sets (from P2-2).

    Pure-function: no side effects, no DB writes. Callers persist /
    log / return the result themselves.
    """
    bound_keys = _bound_category_keys(lab, db)

    scoped_drivers = {
        key: drv for key, drv in hal_drivers.items() if key in bound_keys
    }
    loaded_in_scope: Sequence[str] = sorted(scoped_drivers.keys())
    not_loaded: Sequence[str] = sorted(bound_keys - set(scoped_drivers))

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
                # Two distinct failure modes for the operator:
                #  (a) lab binds the relevant category but HAL hasn't
                #      loaded its driver  → reload HAL / fix connection
                #  (b) lab binds + HAL loaded, but the driver doesn't
                #      expose this token  → wrong license / wrong model
                # We don't prefix-route to pick (a) vs (b), but we
                # surface both lists in the reason so the operator
                # can correlate without reading code.
                bound_display = (
                    list(sorted(bound_keys))
                    if bound_keys else "(none — lab has no instrument_bindings)"
                )
                bits = [
                    f"No driver in this lab's bindings exposes {token!r}.",
                    f"Bound categories: {bound_display}.",
                    f"Loaded in scope: {list(loaded_in_scope) or '(none)'}.",
                ]
                if not_loaded:
                    bits.append(
                        f"Bound but not loaded: {list(not_loaded)} — "
                        f"reload HAL or check the connection."
                    )
                else:
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
    )
