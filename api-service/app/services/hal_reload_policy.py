"""P2-5 — refuse / force policy for HAL Reload mid-test.

Pre-P2-5 ``POST /api/v1/instruments/hal/reload`` would tear down every
driver and reinitialise unconditionally. Concurrent reloads could race
the global service assignment (see ``reload_hal_service_atomic`` for
the mutex fix), AND a reload mid-test would silently abort the test —
the test plan's ``status='running'`` row stayed in the DB, the in-flight
sequence's HTTP request hung until ~30s VISA timeout, then surfaced a
cryptic ``visa.Error`` instead of a user-comprehensible "you reloaded
the HAL while a test was running".

This module supplies the *refuse* arm of the A+D policy chosen for
P2-5: block reload when there's a ``TestPlan`` in ``running`` or
``paused`` state. The endpoint returns HTTP 409 with a structured
payload listing the blocker(s) so the GUI can render a precise message
("3 test plans are running: …") instead of a generic "busy".

The operator override is a ``force=true`` query param — they take
responsibility for the abort. We don't try to refuse harder than that
because in actual on-site debugging, the operator sometimes KNOWS
the test is hung on a bad driver and reload is the right escape hatch.

**What this module does NOT detect**:

- In-flight diagnostic sequences (``app/api/diagnostic_sequence.py``)
  run synchronously on the FastAPI request thread; no DB row exists
  until the run completes, so there's nothing to query.
- Live SCPI commands via ``/instruments/{cat}/scpi-command``: same —
  request-thread bound, no in-flight registry.
- Background metrics broadcaster: continuously polling; not a "user
  initiated" operation worth refusing for.

A future P3 item could add an in-process active-operations registry
on the HAL service for the diagnostic / SCPI paths to opt-in to. For
P2-5 the TestPlan check covers the most consequential case (a multi-
minute formal test) and the warning log on shutdown (with the active
driver list) gives post-mortem context for the unguarded cases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from app.models.test_plan import TestPlan, TestPlanStatus


@dataclass(frozen=True)
class ReloadBlocker:
    """One reason a HAL reload should be refused (without ``force=true``).

    ``kind`` lets future blocker types coexist — today only ``"test_plan"``
    is emitted, but the registry / GUI rendering can branch on this when
    additional check sources (in-flight diagnostics, calibration session,
    etc.) get wired in later.
    """

    kind: str  # "test_plan" today; future: "diagnostic_run", "calibration"
    id: str
    name: str
    status: str
    detail: str


# TestPlan statuses that mean "a test session is actively bound to the
# drivers — tearing the HAL down will corrupt it". 'paused' is included
# because a paused test plan typically still holds driver state (a
# resume is expected); reload between pause + resume would surface the
# corruption on resume rather than failing visibly during the reload.
BLOCKING_TEST_PLAN_STATUSES = (
    TestPlanStatus.RUNNING.value,
    TestPlanStatus.PAUSED.value,
)


def find_test_plan_blockers(db: Session) -> List[ReloadBlocker]:
    """Return one ``ReloadBlocker`` per ``TestPlan`` row whose status
    would be invalidated by a HAL teardown.

    Pure SQL — no HAL coupling. The reload endpoint composes this with
    future check helpers when they're added.
    """
    plans = (
        db.query(TestPlan)
        .filter(TestPlan.status.in_(BLOCKING_TEST_PLAN_STATUSES))
        .order_by(TestPlan.started_at.desc().nullslast())
        .all()
    )
    return [
        ReloadBlocker(
            kind="test_plan",
            id=str(plan.id),
            name=plan.name or "(unnamed)",
            status=plan.status,
            detail=(
                f"test plan {plan.name!r} is {plan.status} — "
                "tearing down HAL will abort its in-flight driver work"
            ),
        )
        for plan in plans
    ]


def find_reload_blockers(db: Session) -> List[ReloadBlocker]:
    """Composite of every blocker source. Today only TestPlan; future
    extensions land here so callers don't grow per-source if-trees."""
    return find_test_plan_blockers(db)
