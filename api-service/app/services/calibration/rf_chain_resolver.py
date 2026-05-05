"""Resolve concrete RF chains from a LabProfile + operating mode.

Before this helper, calibration services were keyed only on chamber_id and
treated cable loss as a chamber-wide single value (`chamber.typical_cable_loss_db`).
That is wrong for any chamber where different probe ports take different
physical paths through the switch matrix — the per-connection
`cable_loss_db` / `calibrated_loss_db` already exist on SwitchTopology, but
nothing was wiring them through to the calibration math.

resolve_rf_chains(db, lab_profile_id, operating_mode) returns a flat list of
RFChainSpec — one per (probe_id, polarization) routed by the switch topology
in the requested mode. Path-loss / RF chain calibration iterate this list
instead of doing `for probe in range(num_probes)`. measure.py uses the same
list to look up per-azimuth compensation by (probe_id, polarization).

Today CAICT-Lab-1 has effectively-fixed cabling, so the resolver is a
declaration check + cable-loss source. When a second lab comes online with
a real switch matrix, the same resolver feeds the live SCPI orchestrator.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.lab_profile import LabProfile
from app.services.mimo_ota.switch_orchestrator import (
    ProbePortBinding,
    TopologyOrchestrationResult,
    orchestrate_switch_topology,
)

logger = logging.getLogger(__name__)


@dataclass
class RFChainSpec:
    """A single (probe, polarization) RF path declared by the topology.

    `chain_id` is the SwitchTopology connection id — stable and unique within
    a topology, so calibration certs can persist results keyed by it without
    having to recompute (probe_id, pol, ce_port) tuples on read.
    """

    chain_id: str
    ce_port: str
    probe_id: int
    polarization: str  # "V" / "H"
    cable_loss_db: float = 0.0  # from connection.calibrated_loss_db or .cable_loss_db


@dataclass
class RFChainResolution:
    lab_profile_id: UUID
    chamber_id: Optional[UUID]
    topology_id: Optional[str]
    topology_name: Optional[str]
    operating_mode: str
    chains: List[RFChainSpec] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.chains)

    def chain_for(self, probe_id: int, polarization: str = "V") -> Optional[RFChainSpec]:
        """Look up the chain for a (probe_id, polarization) pair.

        Returns None if no such chain is wired in the active mode — callers
        should fall back to chamber-wide values (legacy behavior).
        """
        pol_upper = polarization.upper()
        for c in self.chains:
            if c.probe_id == probe_id and c.polarization.upper() == pol_upper:
                return c
        return None

    def chain_id_index(self) -> Dict[str, RFChainSpec]:
        return {c.chain_id: c for c in self.chains}


def resolve_rf_chains(
    db: Session,
    lab_profile_id: UUID,
    operating_mode: str = "mimo_ota",
) -> RFChainResolution:
    """Resolve LabProfile → SwitchTopology → list of RFChainSpec.

    Raises ValueError if the LabProfile doesn't exist or has no chamber bound;
    those are configuration errors the caller can't recover from. Missing
    topology rows (chamber wired but topology not seeded) return success=False
    with a warning, consistent with switch_orchestrator's "loud warning, not
    hard failure" stance for early-stage labs.
    """
    lab = db.query(LabProfile).filter(LabProfile.id == lab_profile_id).first()
    if lab is None:
        raise ValueError(f"LabProfile {lab_profile_id} not found")
    if lab.chamber_config_id is None:
        raise ValueError(
            f"LabProfile {lab.name} has no chamber_config_id — cannot resolve "
            "RF chains without a chamber to look up SwitchTopology by"
        )

    topo: TopologyOrchestrationResult = orchestrate_switch_topology(
        db, lab.chamber_config_id, mode_id=operating_mode
    )

    chains: List[RFChainSpec] = []
    for binding in topo.probe_bindings:
        spec = _binding_to_spec(binding)
        if spec is not None:
            chains.append(spec)

    resolution = RFChainResolution(
        lab_profile_id=lab.id,
        chamber_id=lab.chamber_config_id,
        topology_id=topo.topology_id,
        topology_name=topo.topology_name,
        operating_mode=operating_mode,
        chains=chains,
        warnings=list(topo.warnings),
    )

    if not chains:
        # Topology missing or has no probe-routing connections in this mode.
        # Caller decides whether to fall back to chamber defaults or fail.
        logger.warning(
            "[rf_chain_resolver] No chains resolved for lab=%s mode=%s "
            "(topology_id=%s); calibration will degrade to chamber-wide values",
            lab.name, operating_mode, topo.topology_id,
        )

    return resolution


def _binding_to_spec(binding: ProbePortBinding) -> Optional[RFChainSpec]:
    """ProbePortBinding → RFChainSpec, dropping bindings missing required ids.

    A binding is only useful for calibration if we know *which probe* and
    *which polarization* it serves — without those, we can't look up the
    SGH path-loss measurement against it. Bindings that fail this check are
    dropped silently here; switch_orchestrator already warns on the topology.
    """
    if binding.probe_id is None or binding.polarization is None:
        return None
    if binding.connection_id is None:
        return None
    return RFChainSpec(
        chain_id=str(binding.connection_id),
        ce_port=binding.ce_port,
        probe_id=int(binding.probe_id),
        polarization=binding.polarization.upper(),
        cable_loss_db=float(binding.cable_loss_db or 0.0),
    )
