"""Seed the 7 canonical UXM topology profiles for P2-1 Phase 2.1.

Source of truth is ``app.hal.uxm_test_profiles._PROFILE_REGISTRY`` —
the in-code dataclass registry that pre-dates DB persistence. Keeping
the seeder a thin reflection of the registry means edits to a built-in
template happen in one place (the dataclass), then a bumped seeder
version re-syncs DB rows on next bootstrap.

Idempotency rule: identifies the system-preset row by
``(profile_id, is_system_preset=True)``. If a row matching that pair
already exists, the seeder leaves it alone; user-customized rows
(``is_system_preset=False``) are never touched, even if they share a
profile_id with a preset (this shouldn't happen — the API rejects
operator-created IDs that collide with built-ins — but the seeder is
defensive).

Bump the version when adding/removing a built-in template or changing
a field default on an existing built-in. Operator-customized rows are
never modified by bootstrap; mutations only apply to system-preset rows.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.hal.uxm_test_profiles import (
    _PROFILE_REGISTRY, _register_builtin_profiles,
)
from app.models.instrument_topology_profile import InstrumentTopologyProfile
from app.services.bootstrap import SeedResult, Seeder

logger = logging.getLogger(__name__)


def _seed(db: Session) -> SeedResult:
    if not _PROFILE_REGISTRY:
        _register_builtin_profiles()

    inserted = 0
    skipped = 0

    for profile_id, dc_profile in _PROFILE_REGISTRY.items():
        existing = (
            db.query(InstrumentTopologyProfile)
            .filter(
                InstrumentTopologyProfile.profile_id == profile_id,
                InstrumentTopologyProfile.is_system_preset.is_(True),
            )
            .first()
        )
        if existing is not None:
            skipped += 1
            continue

        # asdict() gives us a {field_name: value} that mirrors the DB
        # column names (the model + dataclass were designed in lockstep
        # for this round-trip).
        data = asdict(dc_profile)
        # ``profile_id`` is the natural key; copy it through explicitly
        # so the DB column gets the operator-visible ID rather than
        # the dataclass field clashing with the UUID PK.
        row = InstrumentTopologyProfile(
            profile_id=data.pop("profile_id"),
            name=data.pop("name"),
            description=data.pop("description", None),
            category=data.pop("category", "general"),
            band=data.pop("band"),
            frequency_mhz=data.pop("frequency_mhz"),
            bandwidth_mhz=data.pop("bandwidth_mhz"),
            scs_khz=data.pop("scs_khz"),
            duplex=data.pop("duplex"),
            arfcn=data.pop("arfcn"),
            mimo_layers=data.pop("mimo_layers"),
            mimo_port_preset=data.pop("mimo_port_preset"),
            dl_power_dbm=data.pop("dl_power_dbm"),
            ssb_power_dbm=data.pop("ssb_power_dbm"),
            modulation=data.pop("modulation"),
            target_mcs=data.pop("target_mcs"),
            sched_algo=data.pop("sched_algo"),
            enable_amc=data.pop("enable_amc"),
            tdd_pattern=data.pop("tdd_pattern"),
            tdd_period=data.pop("tdd_period"),
            harq_max_trans=data.pop("harq_max_trans"),
            harq_processes=data.pop("harq_processes"),
            csi_rs_ports=data.pop("csi_rs_ports"),
            stat_count=data.pop("stat_count"),
            cell_id=data.pop("cell_id"),
            state_file=data.pop("state_file"),
            compatible_test_apps=list(data.pop("compatible_test_apps", [])),
            notes=data.pop("notes", ""),
            is_system_preset=True,
            created_by="system",
        )
        db.add(row)
        inserted += 1
        logger.info(
            "[topology_profiles] seeding default '%s' (%s)",
            row.name, row.profile_id,
        )

    db.flush()
    return SeedResult(inserted=inserted, skipped=skipped)


topology_profiles_seeder = Seeder(
    name="topology_profiles",
    version=1,
    description="7 canonical UXM topology profiles (SISO/MIMO/calibration) "
                "marked is_system_preset=true",
    run=_seed,
)
