"""SwitchTopology orchestration for MIMO_OTA tests.

Purpose: between Phase 1 (precheck) and Phase 3 (measure), verify the chamber
has an active SwitchTopology that defines the requested operating mode and
extract the CE-port → probe mapping so the channel generator and downstream
analysis know exactly which physical probe receives which F64 port.

For sites like CAICT-Lab-1 where the cabling is fixed (no live switching
between modes), this function is a *declaration check*: the lab installer
seeds the topology once, and every test confirms "yes, the active topology
defines mimo_ota mode and routes F64 ports 1-64 to probes 0-31 V/H." A
missing or stale topology is a loud warning, not a hard failure — labs that
haven't seeded yet still get usable mock-data results.

The structure leaves room for future Path B (driving an rfSwitch driver to
*actually* set physical paths) by surfacing connections in the result; today
nothing actually flips a relay because CAICT-Lab-1 doesn't need it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.switch_topology import SwitchTopology
from app.services.base_station_port_mapping import BaseStationPortMapping

logger = logging.getLogger(__name__)


@dataclass
class ProbePortBinding:
    """One CE-port → probe-port channel as declared in the topology."""

    ce_port: str  # e.g. "B1.1" or "1"
    probe_id: Optional[int] = None  # probe number 0..N-1 if parseable
    polarization: Optional[str] = None  # "V" / "H" / None
    connection_id: Optional[str] = None
    cable_loss_db: Optional[float] = None


@dataclass
class TopologyOrchestrationResult:
    """Result returned to the caller for embedding into the phase result_payload."""

    topology_id: Optional[str] = None
    topology_name: Optional[str] = None
    topology_version: Optional[str] = None
    mode_id: Optional[str] = None
    mode_name: Optional[str] = None
    active_connection_count: int = 0
    probe_bindings: List[ProbePortBinding] = field(default_factory=list)
    base_station_ports: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    success: bool = False  # True only if topology+mode found AND has ≥1 active conn

    def to_payload(self) -> Dict[str, Any]:
        return {
            "topology_id": self.topology_id,
            "topology_name": self.topology_name,
            "topology_version": self.topology_version,
            "mode_id": self.mode_id,
            "mode_name": self.mode_name,
            "active_connection_count": self.active_connection_count,
            "probe_binding_count": len(self.probe_bindings),
            "base_station_ports": self.base_station_ports,
            "warnings": self.warnings,
            "success": self.success,
        }


def orchestrate_switch_topology(
    db: Session,
    chamber_id: UUID,
    mode_id: str = "mimo_ota",
    base_station_port_mapping: Optional[BaseStationPortMapping] = None,
) -> TopologyOrchestrationResult:
    """Look up the active topology for `chamber_id` and resolve `mode_id`.

    Returns a result with probe bindings even if the rfSwitch HAL driver
    isn't connected — the bindings are downstream-useful for channel gen.
    """
    result = TopologyOrchestrationResult(mode_id=mode_id)

    topology = (
        db.query(SwitchTopology)
        .filter(
            SwitchTopology.chamber_id == chamber_id,
            SwitchTopology.is_active == True,  # noqa: E712
        )
        .order_by(SwitchTopology.updated_at.desc())
        .first()
    )

    if topology is None:
        result.warnings.append(
            f"No active SwitchTopology for chamber {chamber_id}. "
            "RF paths are assumed pre-configured manually; cross-lab "
            "portability requires a topology row to declare CE→probe mapping."
        )
        return result

    result.topology_id = str(topology.id)
    result.topology_name = topology.name
    result.topology_version = topology.version

    modes = topology.operating_modes or []
    mode = next((m for m in modes if m.get("id") == mode_id), None)
    if mode is None:
        available = [m.get("id") for m in modes]
        result.warnings.append(
            f"Topology '{topology.name}' has no operating mode '{mode_id}'. "
            f"Available modes: {available}"
        )
        return result

    result.mode_name = mode.get("name") or mode_id
    active_conn_ids = set(mode.get("active_connections") or [])
    connections = topology.connections or []
    active_conns = [c for c in connections if c.get("id") in active_conn_ids]
    if mode_id == "mimo_ota" and base_station_port_mapping is not None:
        active_ports = base_station_port_mapping.active_logical_ports

        def _uses_inactive_base_station_port(connection: Dict[str, Any]) -> bool:
            if connection.get("source") == "baseStation":
                return connection.get("source_pin") not in active_ports
            if connection.get("target") == "baseStation":
                return connection.get("target_pin") not in active_ports
            return False

        active_conns = [
            connection
            for connection in active_conns
            if not _uses_inactive_base_station_port(connection)
        ]
        result.base_station_ports = [
            port.to_payload() for port in base_station_port_mapping.ports
        ]
        result.warnings.extend(base_station_port_mapping.warnings)
    result.active_connection_count = len(active_conns)

    if not active_conns:
        result.warnings.append(
            f"Mode '{mode_id}' is defined but has no active_connections. "
            "Topology must list connection ids in mode.active_connections."
        )
        return result

    nodes = topology.nodes or []
    nodes_by_id = {n.get("id"): n for n in nodes}

    for conn in active_conns:
        binding = _build_probe_binding(conn, nodes_by_id)
        if binding is not None:
            result.probe_bindings.append(binding)

    if not result.probe_bindings:
        result.warnings.append(
            "Topology has active connections but none route to probe nodes. "
            "Check node.type='probe' and connection.target points at a probe id."
        )

    result.success = bool(result.probe_bindings)
    return result


def _build_probe_binding(
    connection: Dict[str, Any],
    nodes_by_id: Dict[str, Dict[str, Any]],
) -> Optional[ProbePortBinding]:
    """Extract CE-port → probe info from a connection if its target is a probe.

    Topology convention: connections from `ce_port` (or `bse_port` / `switch_slot`)
    to `probe` node type carry the routing info we need. Connections between
    intermediates (combiners, pads) are skipped here — they're physical-layer
    detail, not channel-mapping info.
    """
    target_id = connection.get("target")
    target = nodes_by_id.get(target_id) if target_id else None
    if target is None or target.get("type") != "probe":
        return None

    source_id = connection.get("source")
    source = nodes_by_id.get(source_id) if source_id else None
    ce_port_label = (
        (source.get("label") if source else None)
        or connection.get("source_pin")
        or source_id
        or "?"
    )

    # Probe binding params (id, polarization) — convention is they live on the
    # probe node's params dict; fall back to parsing the label.
    target_params = target.get("params") or {}
    probe_id = target_params.get("probe_id")
    if probe_id is None:
        # Try parsing target id like "probe_5" or label like "Probe 5 V"
        for token in (target_id or "", target.get("label") or ""):
            for piece in token.replace("_", " ").split():
                if piece.isdigit():
                    probe_id = int(piece)
                    break
            if probe_id is not None:
                break

    polarization = target_params.get("polarization")
    if polarization is None:
        # Pull V/H from the connection target_pin or label
        for token in (connection.get("target_pin") or "", target.get("label") or ""):
            up = token.upper()
            if " V" in f" {up}" or up.endswith("V") or "VERTICAL" in up:
                polarization = "V"
                break
            if " H" in f" {up}" or up.endswith("H") or "HORIZONTAL" in up:
                polarization = "H"
                break

    return ProbePortBinding(
        ce_port=str(ce_port_label),
        probe_id=int(probe_id) if probe_id is not None else None,
        polarization=polarization,
        connection_id=connection.get("id"),
        cable_loss_db=connection.get("calibrated_loss_db") or connection.get("cable_loss_db"),
    )
