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
capabilities exposed by the lab's HAL-loaded drivers, and returns a
typed `PreflightResult` with gaps + unknown-token warnings. The
operator-facing surface (POST /api/v1/test-plans/{id}/preflight)
returns the same shape; the GUI's "预检" button (PR B) renders it.

# Design choices

- **Iterate all HAL drivers, don't pre-map token prefix → category**.
  Simplest semantic: "no driver in the lab exposes this token" is the
  gap. The token namespace (`ce.*` / `pos.*` / …) is informational only.
  Avoids maintaining a prefix-to-category-key lookup table that would
  drift out of sync with `KNOWN_CAPABILITIES`.

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
from typing import List, Optional, Sequence
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
    """Sorted union of all tokens exposed by HAL-loaded drivers — included
    in the response so the GUI can show "what the lab DOES have"
    alongside the gaps."""

    @property
    def ready(self) -> bool:
        """True iff the plan can be run as-is against this lab.
        Gaps block; unknown tokens warn but don't block (a future
        token registration would unblock without re-validating)."""
        return not self.gaps


def validate_plan(
    plan: TestPlan,
    lab: LabProfile,
    db: Session,
    hal_drivers: dict,
) -> PreflightResult:
    """Iterate ``plan``'s steps in execution order and produce a
    ``PreflightResult``.

    ``hal_drivers`` is the live ``InstrumentHALService.drivers`` dict
    (``{category_key: driver_instance}``). Each driver exposes
    ``driver.capabilities: Set[str]`` from P2-2.

    Pure-function: no side effects, no DB writes. Callers persist /
    log / return the result themselves.
    """
    # Union of all tokens any loaded driver exposes. The pre-flight
    # gap check is "is the token present in ANY driver" — not
    # "in the driver of the right category" — because the namespace
    # prefix (ce / bs / pos / …) is informational and a future driver
    # might legitimately expose a token outside its namespace
    # (e.g. a combined CE-plus-BS host). Keeping this as a flat union
    # avoids prefix-routing logic that would drift.
    all_capabilities: set[str] = set()
    for driver in hal_drivers.values():
        all_capabilities |= getattr(driver, "capabilities", set())

    loaded_categories: Sequence[str] = sorted(hal_drivers.keys())

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
                # Compose a reason the operator can act on: name the
                # missing token, list the categories that ARE loaded,
                # nudge toward license / hardware checks.
                gaps.append(Gap(
                    step_id=step.id,
                    step_name=step.name or f"step #{step.order}",
                    step_order=step.order,
                    missing_token=token,
                    reason=(
                        f"No HAL driver in this lab exposes "
                        f"{token!r}. Loaded categories: "
                        f"{list(loaded_categories) or '(none)'}. "
                        f"Check that the required hardware / license "
                        f"is connected and the driver came up cleanly."
                    ),
                ))

    return PreflightResult(
        plan_id=plan.id,
        lab_profile_id=lab.id,
        gaps=gaps,
        unknown_tokens=sorted(unknown_seen),
        lab_capabilities=sorted(all_capabilities),
    )
