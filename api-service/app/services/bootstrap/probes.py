"""Seed the canonical 32-probe layout for the default Type-C chamber.

Layout (MPAC 3-ring configuration, matches legacy ``init_probes.py``):

- Ring 1 (Upper, El=+45°): 4 positions (0, 90, 180, 270)
- Ring 2 (Middle, El=0°):  8 positions (0, 45, ..., 315)
- Ring 3 (Lower, El=-45°): 4 positions (0, 90, 180, 270)

Each position carries V + H polarizations → 16 positions × 2 = 32 probes.

Idempotency rule: probes are linked to a specific chamber via
``chamber_config_id``. This seeder attaches the 32 probes to the
canonical Type-C system preset (created by ``chamber_presets`` seeder).
If that preset has any probes already, the seeder skips — it never
re-creates rows or touches user-modified probes.

Dependency: must run after ``chamber_presets``.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.chamber import ChamberConfiguration
from app.models.probe import Probe
from app.services.bootstrap import SeedResult, Seeder

logger = logging.getLogger(__name__)


_RING_LAYOUT_32 = [
    {"ring_id": 1, "elevation": 45,  "count": 4},
    {"ring_id": 2, "elevation": 0,   "count": 8},
    {"ring_id": 3, "elevation": -45, "count": 4},
]


def _seed(db: Session) -> SeedResult:
    chamber = (
        db.query(ChamberConfiguration)
        .filter(
            ChamberConfiguration.chamber_type == "type_c",
            ChamberConfiguration.is_system_preset.is_(True),
        )
        .first()
    )
    if chamber is None:
        logger.warning(
            "[probes] Type-C system preset not found — has chamber_presets "
            "seeder run? Skipping probe seed."
        )
        return SeedResult(inserted=0, skipped=0)

    existing = db.query(Probe).filter(Probe.chamber_config_id == chamber.id).count()
    if existing > 0:
        logger.info(
            "[probes] chamber %s already has %d probes — skip",
            chamber.name, existing,
        )
        return SeedResult(inserted=0, skipped=existing)

    probe_number = 1
    inserted = 0
    radius = chamber.chamber_radius_m
    for ring in _RING_LAYOUT_32:
        step_deg = 360.0 / ring["count"]
        for i in range(ring["count"]):
            azimuth = i * step_deg
            for pol in ("V", "H"):
                db.add(Probe(
                    probe_number=probe_number,
                    name=f"Probe {probe_number}-{pol}",
                    ring=ring["ring_id"],
                    polarization=pol,
                    position={
                        "azimuth": azimuth,
                        "elevation": ring["elevation"],
                        "radius": radius,
                    },
                    is_active=True,
                    is_connected=False,
                    status="idle",
                    calibration_status="unknown",
                    chamber_config_id=chamber.id,
                ))
                probe_number += 1
                inserted += 1

    db.flush()
    logger.info(
        "[probes] seeded %d probes on chamber '%s'",
        inserted, chamber.name,
    )
    return SeedResult(inserted=inserted, skipped=0)


probes_seeder = Seeder(
    name="probes",
    version=1,
    description="32-probe MPAC layout attached to the default Type-C chamber preset",
    run=_seed,
)
