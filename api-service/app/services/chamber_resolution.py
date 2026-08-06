"""LabProfile-bound current chamber resolution and read-only integrity audit.

``ChamberConfiguration.is_active`` is a retained legacy column.  It is not a
current-chamber selector: the selected LabProfile's ``chamber_config_id`` is
the only operational truth source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.chamber import ChamberConfiguration
from app.models.lab_profile import LabProfile
from app.services.lab_resolution import resolve_lab_profile


_CALIBRATION_CHAMBER_TABLES = (
    "quiet_zone_calibrations",
    "probe_amplitude_calibrations",
    "probe_phase_calibrations",
    "probe_polarization_calibrations",
    "probe_patterns",
    "probe_path_loss_calibrations",
    "rf_chain_calibrations",
    "multi_frequency_path_losses",
    "probe_calibration_validity",
    "channel_phase_calibrations",
    "calibration_baselines",
    "rf_switch_calibrations",
    "e2e_compensation_matrices",
)


@dataclass(frozen=True)
class ChamberIntegrityReport:
    lab_profile_id: UUID
    current_chamber_id: Optional[UUID]
    current_chamber_exists: bool
    orphan_references: Dict[str, List[str]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def orphan_count(self) -> int:
        return sum(len(ids) for ids in self.orphan_references.values())

    @property
    def ok(self) -> bool:
        return self.current_chamber_exists and not self.errors and self.orphan_count == 0


def _coerce_uuid(value: Optional[UUID | str]) -> Optional[UUID]:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid lab_profile_id: {value}") from exc


def resolve_current_chamber(
    db: Session, lab_profile_id: Optional[UUID | str] = None
) -> ChamberConfiguration:
    """Return the chamber bound to the explicit or uniquely-active lab."""
    lab = resolve_lab_profile(db, _coerce_uuid(lab_profile_id))
    if lab.chamber_config_id is None:
        raise ValueError(
            f"LabProfile {lab.name} ({lab.id}) has no chamber_config_id; "
            "bind a chamber before running chamber-dependent flows."
        )
    chamber = db.get(ChamberConfiguration, lab.chamber_config_id)
    if chamber is None:
        raise ValueError(
            f"LabProfile {lab.name} ({lab.id}) references missing chamber "
            f"{lab.chamber_config_id}."
        )
    return chamber


def bind_current_chamber(
    db: Session,
    chamber_id: UUID,
    lab_profile_id: Optional[UUID | str] = None,
) -> tuple[LabProfile, ChamberConfiguration]:
    """Rebind the resolved LabProfile; caller owns commit/rollback."""
    lab = resolve_lab_profile(db, _coerce_uuid(lab_profile_id))
    chamber = db.get(ChamberConfiguration, chamber_id)
    if chamber is None:
        raise LookupError(f"Chamber configuration {chamber_id} not found")
    lab.chamber_config_id = chamber.id
    return lab, chamber


def calibration_chamber_reference_counts(
    db: Session, chamber_id: UUID,
) -> Dict[str, int]:
    """Return non-zero calibration-history references for one chamber.

    Calibration history is evidence and must never be cascaded away with a
    chamber configuration.  DELETE preflight and the integrity audit share
    this catalog so newly chamber-scoped tables cannot silently diverge.
    """
    references: Dict[str, int] = {}
    for table_name in _CALIBRATION_CHAMBER_TABLES:
        table = Base.metadata.tables.get(table_name)
        if table is None or "chamber_id" not in table.c:
            continue
        count = db.scalar(
            select(func.count()).select_from(table).where(table.c.chamber_id == chamber_id)
        )
        if count:
            references[table_name] = int(count)
    return references


def audit_chamber_integrity(
    db: Session, lab_profile_id: Optional[UUID | str] = None
) -> ChamberIntegrityReport:
    """Audit binding existence and orphaned calibration chamber references.

    This function never mutates or repairs data.  The legacy chamber
    ``is_active`` value is intentionally absent: once retired as a selector,
    agreement with it is no longer an operational invariant.
    """
    lab = resolve_lab_profile(db, _coerce_uuid(lab_profile_id))
    errors: List[str] = []
    current_exists = False
    if lab.chamber_config_id is None:
        errors.append(f"LabProfile {lab.name} has no chamber_config_id")
    else:
        current_exists = db.get(ChamberConfiguration, lab.chamber_config_id) is not None
        if not current_exists:
            errors.append(
                f"LabProfile {lab.name} references missing chamber {lab.chamber_config_id}"
            )

    known_chamber_ids = set(db.scalars(select(ChamberConfiguration.id)).all())
    orphan_references: Dict[str, List[str]] = {}
    for table_name in _CALIBRATION_CHAMBER_TABLES:
        table = Base.metadata.tables.get(table_name)
        if table is None or "chamber_id" not in table.c:
            errors.append(f"Calibration integrity audit table missing: {table_name}")
            continue
        referenced = set(
            db.scalars(
                select(table.c.chamber_id)
                .where(table.c.chamber_id.is_not(None))
                .distinct()
            ).all()
        )
        orphan_ids = sorted(str(value) for value in referenced - known_chamber_ids)
        if orphan_ids:
            orphan_references[table_name] = orphan_ids

    return ChamberIntegrityReport(
        lab_profile_id=lab.id,
        current_chamber_id=lab.chamber_config_id,
        current_chamber_exists=current_exists,
        orphan_references=orphan_references,
        errors=errors,
    )
