"""Seed CAICT-Lab-1 SwitchTopology — fixed-cabling MIMO OTA configuration.

CAICT-Lab-1 has a static RF cabling: F64 channel emulator outputs are
hard-wired through ETS-Lindgren switch racks to the 32 dual-polarized
probes. This script declares that topology so any MIMO_OTA test in this
chamber can verify "yes the F64 ports are connected to probes 0-31 V/H
in canonical order."

Convention (CAICT v1):
  - F64 has 64 outputs (B1..B16 each with 4 channels = 64 ports)
  - Probes numbered 0..31, each with V and H polarization → 64 channels
  - Mapping: F64 port (k+1) → probe ⌊k/2⌋, polarization V if k even, H if odd
    (i.e. port 1 → probe 0 V, port 2 → probe 0 H, port 3 → probe 1 V, ...)
  - Cable loss typical 0.5 dB per channel (uncalibrated baseline)

Idempotent: re-running updates the existing CAICT topology in place.

Usage:
    cd api-service
    .venv/bin/python scripts/dev-fixtures/seed_caict_switch_topology.py

Note: This script seeds a *simplified* 32-port direct topology. For the full
CAICT V4.0 layout (horizontal ring + vertical ring + calibration paths), use
the GUI: TopologyEditor → 「重导入」 (calls /import/from-template?template_id=caict_v4
which loads scripts/dev-fixtures/topology-templates/caict_v4.py).
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal
from app.models.chamber import ChamberConfiguration
from app.models.lab_profile import LabProfile
from app.models.instrument import InstrumentCategory
from app.models.switch_topology import SwitchTopology
from app.services.chamber_resolution import resolve_current_chamber

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_caict_topology")

TOPOLOGY_NAME = "CAICT Beijing AMS8947 v1.0"
TOPOLOGY_VERSION = "1.0"
SITE = "CAICT Beijing BDA"
SYSTEM_MODEL = "ETS-Lindgren AMS8947"
NUM_PROBES = 32
DEFAULT_CABLE_LOSS_DB = 0.5


def _resolve_chamber(db) -> ChamberConfiguration:
    lab = db.query(LabProfile).filter(LabProfile.name == "CAICT-Lab-1").one_or_none()
    if lab is None:
        raise RuntimeError("CAICT-Lab-1 not found; seed the LabProfile first.")
    return resolve_current_chamber(db, lab.id)


def _resolve_switch_category(db) -> InstrumentCategory | None:
    """rfSwitch category may not exist if the lab hasn't registered the
    switch matrix as an instrument yet. Return None and let the topology
    point to a placeholder — operator can backfill switch_category_id later.
    """
    return (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.category_key == "rfSwitch")
        .first()
    )


def _build_nodes() -> list[dict]:
    """64 CE ports + 32 probes × 2 pol = 128 nodes total (CE + probes only;
    intermediate switch slots are abstracted because CAICT cabling is fixed
    and we don't need per-relay control).
    """
    nodes: list[dict] = []
    # CE output ports (F64 with 16 baseband modules × 4 channels = 64)
    for i in range(64):
        module = (i // 4) + 1
        ch = (i % 4) + 1
        nodes.append({
            "id": f"ce_b{module}_{ch}",
            "type": "ce_port",
            "label": f"F64 B{module}.CH{ch}",
            "position": {"x": 50, "y": 30 + i * 20},
            "params": {"port_index": i + 1},
        })
    # Probes — 32 nodes, each with V and H pins (we model V/H as separate
    # nodes for cleaner connection mapping; alt would be one probe node with
    # multiple pins, but separate nodes match the topology convention better)
    for probe in range(NUM_PROBES):
        for pol in ("V", "H"):
            nodes.append({
                "id": f"probe_{probe}_{pol.lower()}",
                "type": "probe",
                "label": f"Probe {probe} {pol}",
                "position": {"x": 600, "y": 30 + (probe * 2 + (1 if pol == "H" else 0)) * 20},
                "params": {"probe_id": probe, "polarization": pol},
            })
    return nodes


def _build_connections() -> list[dict]:
    """64 connections, one per CE-port-to-probe-pol pairing."""
    conns: list[dict] = []
    for i in range(64):
        probe = i // 2
        pol = "v" if i % 2 == 0 else "h"
        module = (i // 4) + 1
        ch = (i % 4) + 1
        conns.append({
            "id": f"conn_ce_b{module}_{ch}_to_probe_{probe}_{pol}",
            "source": f"ce_b{module}_{ch}",
            "source_pin": "out",
            "target": f"probe_{probe}_{pol}",
            "target_pin": pol.upper(),
            "cable_type": "Phase-matched N-N",
            "cable_loss_db": DEFAULT_CABLE_LOSS_DB,
            "cable_length_m": 5.0,
            "calibrated_loss_db": None,
            "calibrated_phase_deg": None,
            "modes": ["mimo_ota"],
        })
    return conns


def _build_modes(connections: list[dict]) -> list[dict]:
    return [
        {
            "id": "mimo_ota",
            "name": "MIMO OTA (5G NR)",
            "description": "All 64 channels active; CE ports → 32 probes × V/H",
            "active_connections": [c["id"] for c in connections],
            "required_instruments": ["channelEmulator", "baseStation"],
            "color": "#4CAF50",
        }
    ]


def main() -> None:
    db = SessionLocal()
    try:
        chamber = _resolve_chamber(db)
        switch_cat = _resolve_switch_category(db)

        nodes = _build_nodes()
        connections = _build_connections()
        modes = _build_modes(connections)

        existing = (
            db.query(SwitchTopology)
            .filter(SwitchTopology.name == TOPOLOGY_NAME)
            .first()
        )

        if existing is None:
            if switch_cat is None:
                raise RuntimeError(
                    "rfSwitch InstrumentCategory not found; create it first via "
                    "seed_instruments.py or register the switch in the GUI."
                )
            topology = SwitchTopology(
                switch_category_id=switch_cat.id,
                chamber_id=chamber.id,
                name=TOPOLOGY_NAME,
                description=(
                    "Fixed-cabling MIMO OTA topology for CAICT Beijing "
                    "ETS-Lindgren AMS8947. F64 64 ports → 32 probes × V/H."
                ),
                version=TOPOLOGY_VERSION,
                site_name=SITE,
                system_model=SYSTEM_MODEL,
                installed_date=datetime.utcnow(),
                installed_by="seed_caict_switch_topology.py",
                nodes=nodes,
                connections=connections,
                operating_modes=modes,
                is_active=True,
                is_default=True,
            )
            topology.update_statistics()
            db.add(topology)
            logger.info("Creating new topology '%s'", TOPOLOGY_NAME)
        else:
            existing.chamber_id = chamber.id
            existing.nodes = nodes
            existing.connections = connections
            existing.operating_modes = modes
            existing.is_active = True
            existing.update_statistics()
            logger.info("Updating existing topology '%s'", TOPOLOGY_NAME)

        db.commit()
        topology = existing or topology
        logger.info(
            "Done. id=%s probes=%d connections=%d modes=%d",
            topology.id,
            topology.total_probes,
            topology.total_connections,
            len(modes),
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
