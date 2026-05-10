"""Seed the four canonical chamber presets (Type A/B/C/D).

Source of truth is ``app.models.chamber.CHAMBER_PRESETS`` — keeping the
seeder a thin wrapper means edits to a preset only happen in one place.

Idempotency rule: identifies the system-preset row by
``(chamber_type, is_system_preset=True)``. If a row matching that pair
already exists, the seeder leaves it alone; user-customized rows
(``is_system_preset=False``) are never touched, even if they share a
chamber_type with a preset.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.chamber import CHAMBER_PRESETS, ChamberConfiguration
from app.services.bootstrap import SeedResult, Seeder

logger = logging.getLogger(__name__)


def _seed(db: Session) -> SeedResult:
    inserted = 0
    skipped = 0

    for preset_type, preset in CHAMBER_PRESETS.items():
        existing = (
            db.query(ChamberConfiguration)
            .filter(
                ChamberConfiguration.chamber_type == preset_type,
                ChamberConfiguration.is_system_preset.is_(True),
            )
            .first()
        )
        if existing is not None:
            skipped += 1
            continue

        # Build with a "默认 - " name prefix so users can immediately tell
        # canonical presets from their own variants. The user's clones
        # get a "(副本)" suffix from the duplicate endpoint.
        chamber = ChamberConfiguration(
            **preset,
            is_system_preset=True,
            is_active=False,  # Don't auto-activate; user picks per-deploy
            created_by="system",
        )
        # Override the name to make it scannable as a default
        chamber.name = f"默认 - {preset['name']}"
        db.add(chamber)
        inserted += 1
        logger.info("[chamber_presets] seeding default '%s'", chamber.name)

    db.flush()
    return SeedResult(inserted=inserted, skipped=skipped)


chamber_presets_seeder = Seeder(
    name="chamber_presets",
    version=1,
    description="4 canonical chamber presets (Type A/B/C/D) marked is_system_preset=true",
    run=_seed,
)
