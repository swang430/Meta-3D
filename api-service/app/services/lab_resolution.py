"""Shared LabProfile resolver — used by every flow that takes an
optional ``lab_profile_id`` and needs to fall back to the active lab.

# Why this exists

Pre-this-refactor each factory (mimo_ota, trp) had a copy of the
same `_resolve_lab_profile` function that raised plain ``ValueError``
for both "no active lab" and "multiple active labs". The API layer
then let those ValueErrors propagate uncaught → FastAPI returned
**500 Internal Server Error**, surfaced in the GUI as a useless
"初始化失败 错误代码500".

The "multiple active labs" case is **not** a server bug — it's a
legitimate configuration ambiguity. Real production will have many
labs (per-chamber, per-line). The right HTTP status is 422 with
enough detail for the GUI to render an actionable picker.

This module gives both factories one source of truth + a typed
``LabResolutionError`` carrying the list of candidate labs, so the
API layer can construct an actionable 422 response.

# Backwards-compat decision

When exactly one LabProfile is active and the caller didn't specify
``lab_profile_id``, we return it — same as the legacy behavior. This
preserves the dev/test convenience case (one lab → no friction) and
all existing scripts. Tightening to "explicit always" would be a
breaking change touching `scripts/`, `tests/`, `docs/quickstart.md`
etc. — out of scope for the targeted fix.

The bug we ARE fixing is the foot-gun: 2+ active labs returning 500.
Operator now sees a 422 with the active-lab list and can pick the
right one explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.lab_profile import LabProfile


@dataclass(frozen=True)
class LabSummary:
    """Minimal LabProfile shape returned in resolution errors so the
    GUI can build a picker without an extra round-trip."""
    id: UUID
    name: str


class LabResolutionError(Exception):
    """Raised when the active-lab fallback can't pick a single lab.

    Carries the list of candidate active labs so API handlers can
    construct an actionable 422 response (and the GUI can render a
    picker pre-populated with the candidates).

    Attributes:
        kind:      "none" (no active labs) or "ambiguous" (≥2)
        active_labs: candidate labs the caller can pass explicitly
    """
    def __init__(self, kind: str, active_labs: List[LabSummary]):
        self.kind = kind
        self.active_labs = active_labs
        if kind == "none":
            msg = (
                "No active LabProfile in DB. Create one via the GUI's "
                "first-launch wizard (POST /api/v1/lab-profiles) before "
                "starting a session."
            )
        elif kind == "ambiguous":
            names = ", ".join(f"{lab.name} ({lab.id})" for lab in active_labs)
            msg = (
                f"Multiple active LabProfiles ({len(active_labs)}). "
                f"Pass an explicit lab_profile_id from: {names}."
            )
        else:
            msg = f"LabResolutionError(kind={kind})"
        super().__init__(msg)


def resolve_lab_profile(
    db: Session, lab_profile_id: Optional[UUID]
) -> LabProfile:
    """Look up the requested LabProfile, or the unique active one as
    fallback.

    Returns the resolved LabProfile.

    Raises:
        ValueError: caller passed ``lab_profile_id`` but the row is
            missing or inactive. This stays as ValueError (not a typed
            error) because it's a caller bug — the lab profile id came
            from somewhere upstream that should know its IDs are valid.
        LabResolutionError: caller didn't pass ``lab_profile_id`` AND
            the active-lab fallback couldn't pick a single lab
            (kind="none" or kind="ambiguous"). API handlers catch this
            and translate to 422 with structured detail.
    """
    if lab_profile_id is not None:
        profile = db.query(LabProfile).filter(LabProfile.id == lab_profile_id).first()
        if not profile:
            raise ValueError(f"LabProfile {lab_profile_id} not found")
        if not profile.is_active:
            raise ValueError(f"LabProfile {lab_profile_id} is inactive")
        return profile

    active = (
        db.query(LabProfile)
        .filter(LabProfile.is_active.is_(True))
        .order_by(LabProfile.name)
        .all()
    )
    if not active:
        raise LabResolutionError(kind="none", active_labs=[])
    if len(active) > 1:
        raise LabResolutionError(
            kind="ambiguous",
            active_labs=[LabSummary(id=p.id, name=p.name) for p in active],
        )
    return active[0]
