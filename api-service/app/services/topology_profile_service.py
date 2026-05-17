"""P2-1 Phase 2.1 — CRUD + lookup for persisted UXM topology profiles.

Sits between the API layer (``app/api/instrument.py``) and the
``InstrumentTopologyProfile`` ORM model. Key responsibilities:

- ``get_dataclass(db, profile_id)`` — fetch a row and return the
  runtime ``UxmTestProfile`` dataclass the HAL driver consumes. Drivers
  must NOT touch ``Session`` directly; this seam keeps HAL layer clean.
- ``list_dataclass_profiles(db)`` — same as above but for the GET
  endpoint's list view.
- ``create / update / delete`` — operator-driven CRUD; rejects mutation
  of ``is_system_preset=True`` rows (clone-to-edit pattern, mirrors
  chamber_service).
- ``duplicate`` — clone a row (typically a system preset) into a new
  editable copy.

Exception types let the API layer translate cleanly to HTTP status:
- ``TopologyProfileNotFound`` → 404
- ``TopologyProfileDuplicate`` → 409 (collision on profile_id)
- ``TopologyProfileImmutable`` → 409 (PUT/DELETE on system preset)
"""
from __future__ import annotations

import logging
import re
from dataclasses import fields as dc_fields
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.hal.uxm_test_profiles import UxmTestProfile
from app.models.instrument_topology_profile import InstrumentTopologyProfile

logger = logging.getLogger(__name__)


class TopologyProfileNotFound(LookupError):
    """profile_id has no row in instrument_topology_profiles."""


class TopologyProfileDuplicate(ValueError):
    """A row with this profile_id already exists."""


class TopologyProfileImmutable(PermissionError):
    """Attempted PUT/DELETE on an is_system_preset=True row.

    Operator should clone via ``duplicate()`` and edit the copy.
    """


# ============================================================
# Row ↔ dataclass conversion
# ============================================================

# Fields the dataclass has but that are operator-meta / DB-managed rather
# than knobs the driver consumes. Used by ``to_dataclass()`` to defend
# against schema drift between the row and the dataclass.
_DATACLASS_FIELD_NAMES = {f.name for f in dc_fields(UxmTestProfile)}


def to_dataclass(row: InstrumentTopologyProfile) -> UxmTestProfile:
    """Convert a DB row into the runtime ``UxmTestProfile`` dataclass.

    The driver consumes the dataclass — it knows nothing about
    ``InstrumentTopologyProfile`` or ``Session``. Keeps the HAL layer
    free of DB dependencies.
    """
    # Pull every dataclass field by name from the row; this stays stable
    # even if the column order in the model changes. ``compatible_test_apps``
    # is JSON in DB → list in dataclass; deepcopy via ``list(...)`` so
    # mutation of the returned dataclass doesn't bleed into the row.
    kwargs: Dict[str, Any] = {}
    for name in _DATACLASS_FIELD_NAMES:
        if not hasattr(row, name):
            continue
        value = getattr(row, name)
        if name == "compatible_test_apps":
            value = list(value or [])
        kwargs[name] = value
    return UxmTestProfile(**kwargs)


# ============================================================
# Read paths
# ============================================================

def get_row(db: Session, profile_id: str) -> InstrumentTopologyProfile:
    """Fetch by stable string ``profile_id`` (not UUID PK).

    Raises ``TopologyProfileNotFound`` if absent — callers in the API
    layer map that to HTTP 404.
    """
    row = (
        db.query(InstrumentTopologyProfile)
        .filter(InstrumentTopologyProfile.profile_id == profile_id)
        .first()
    )
    if row is None:
        raise TopologyProfileNotFound(profile_id)
    return row


def get_dataclass(db: Session, profile_id: str) -> UxmTestProfile:
    """Convenience: fetch row + convert to runtime dataclass."""
    return to_dataclass(get_row(db, profile_id))


def list_rows(db: Session) -> List[InstrumentTopologyProfile]:
    """All rows, system presets first (stable display order in GUI)."""
    return (
        db.query(InstrumentTopologyProfile)
        .order_by(
            InstrumentTopologyProfile.is_system_preset.desc(),
            InstrumentTopologyProfile.category,
            InstrumentTopologyProfile.profile_id,
        )
        .all()
    )


# ============================================================
# Mutation paths
# ============================================================

# Operator-supplied input fields — strict allowlist matching the
# dataclass surface. ``id``, ``profile_id``, ``is_system_preset``,
# ``created_at/by``, ``updated_at`` are NOT operator-mutable via
# update(); see ``_SYSTEM_OR_KEY_FIELDS``.
_MUTABLE_FIELDS = {
    "name", "description", "category",
    "band", "frequency_mhz", "bandwidth_mhz", "scs_khz", "duplex", "arfcn",
    "mimo_layers", "mimo_port_preset",
    "dl_power_dbm", "ssb_power_dbm",
    "modulation", "target_mcs",
    "sched_algo", "enable_amc", "tdd_pattern", "tdd_period",
    "harq_max_trans", "harq_processes", "csi_rs_ports", "stat_count",
    "cell_id", "state_file",
    "compatible_test_apps", "notes",
}

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _slugify(text: str) -> str:
    """Generate a safe ``profile_id`` fragment from a name.

    Lowercases, collapses non-[a-zA-Z0-9_] into single underscores,
    strips leading/trailing underscores. Pure helper, doesn't
    namespace — caller prefixes with ``custom_``.
    """
    slug = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    return slug or "profile"


def _allocate_custom_profile_id(db: Session, base: str) -> str:
    """Find an unused ``custom_<base>[_<n>]`` profile_id.

    Operator-created profiles always get the ``custom_`` prefix to keep
    them in their own namespace — built-in IDs (``caict_n78_2x2`` etc.)
    are never collisible from the create endpoint.
    """
    base_slug = _slugify(base)
    candidate = f"custom_{base_slug}"
    suffix = 2
    while (
        db.query(InstrumentTopologyProfile)
        .filter(InstrumentTopologyProfile.profile_id == candidate)
        .first()
        is not None
    ):
        candidate = f"custom_{base_slug}_{suffix}"
        suffix += 1
    return candidate


def create(
    db: Session,
    *,
    name: str,
    fields: Dict[str, Any],
    created_by: Optional[str] = None,
) -> InstrumentTopologyProfile:
    """Create a new operator-owned topology profile.

    The DB-side ``profile_id`` is auto-generated from the name with a
    ``custom_`` prefix; operators don't pick raw IDs (prevents both
    namespace collisions with built-ins and DB-style slug formatting
    surprises in the GUI).

    ``fields`` is the allowlisted set of mutable knobs. Unknown keys
    raise ``ValueError`` so frontend drift is loud — silent ignore would
    let a renamed field disappear without anyone noticing.
    """
    if not name or not name.strip():
        raise ValueError("name must be a non-empty string")

    unknown = set(fields.keys()) - _MUTABLE_FIELDS
    if unknown:
        raise ValueError(
            f"Unknown topology profile fields: {sorted(unknown)}. "
            f"Allowed: {sorted(_MUTABLE_FIELDS)}"
        )

    profile_id = _allocate_custom_profile_id(db, name)
    row = InstrumentTopologyProfile(
        profile_id=profile_id,
        name=name.strip(),
        is_system_preset=False,
        created_by=created_by,
        # Sensible defaults will come from the column server_defaults;
        # apply operator-supplied values on top.
    )
    # Apply operator fields. ``compatible_test_apps`` JSON column gets
    # a list copy so caller-side mutation doesn't bleed in.
    for key, value in fields.items():
        if key == "compatible_test_apps" and value is not None:
            value = list(value)
        setattr(row, key, value)
    db.add(row)
    db.flush()
    logger.info(
        "[topology_profile_service] created '%s' (profile_id=%s)",
        row.name, row.profile_id,
    )
    return row


def update(
    db: Session,
    profile_id: str,
    fields: Dict[str, Any],
) -> InstrumentTopologyProfile:
    """Partial-update an existing topology profile.

    Refuses ``is_system_preset=True`` rows with
    ``TopologyProfileImmutable`` — operator must duplicate first.
    """
    row = get_row(db, profile_id)
    if row.is_system_preset:
        raise TopologyProfileImmutable(
            f"Topology profile {profile_id!r} is a system preset and "
            f"cannot be modified. Duplicate it first to create an "
            f"editable copy."
        )

    unknown = set(fields.keys()) - _MUTABLE_FIELDS
    if unknown:
        raise ValueError(
            f"Unknown topology profile fields: {sorted(unknown)}. "
            f"Allowed: {sorted(_MUTABLE_FIELDS)}"
        )

    for key, value in fields.items():
        if key == "compatible_test_apps" and value is not None:
            value = list(value)
        setattr(row, key, value)
    db.flush()
    logger.info(
        "[topology_profile_service] updated %s: keys=%s",
        profile_id, sorted(fields.keys()),
    )
    return row


def delete(db: Session, profile_id: str) -> None:
    """Delete an operator-owned profile.

    Refuses system presets with ``TopologyProfileImmutable``. Does NOT
    cascade — if the row is referenced by any
    ``InstrumentConnection.connection_params['topology_profile_id']``,
    the FK isn't materialised (it's just a JSON value), so the
    selection silently becomes stale on next HAL reload (driver will
    log a warning and skip auto-apply). The API layer should warn the
    operator at PUT time if the row they're about to delete is bound.
    """
    row = get_row(db, profile_id)
    if row.is_system_preset:
        raise TopologyProfileImmutable(
            f"Topology profile {profile_id!r} is a system preset and "
            f"cannot be deleted."
        )
    db.delete(row)
    db.flush()
    logger.info("[topology_profile_service] deleted '%s'", profile_id)


def duplicate(
    db: Session,
    profile_id: str,
    *,
    created_by: Optional[str] = None,
) -> InstrumentTopologyProfile:
    """Clone any row (system preset or not) into a new operator copy.

    The new copy gets:
    - ``profile_id`` = ``custom_<slug>`` allocated from the source name
    - ``name`` = ``<source name> (副本)`` so it's visually distinct
    - ``is_system_preset=False`` (always — operator owns the copy)
    """
    source = get_row(db, profile_id)
    new_name = f"{source.name} (副本)"
    new_profile_id = _allocate_custom_profile_id(db, new_name)

    # Shallow copy of every operator-mutable + meta field except
    # is_system_preset / audit / PK.
    row = InstrumentTopologyProfile(
        profile_id=new_profile_id,
        name=new_name,
        is_system_preset=False,
        created_by=created_by,
    )
    for key in _MUTABLE_FIELDS:
        if key == "name":
            continue  # already set above with the (副本) suffix
        value = getattr(source, key, None)
        if key == "compatible_test_apps" and value is not None:
            value = list(value)
        setattr(row, key, value)
    db.add(row)
    db.flush()
    logger.info(
        "[topology_profile_service] duplicated '%s' → '%s'",
        profile_id, new_profile_id,
    )
    return row
