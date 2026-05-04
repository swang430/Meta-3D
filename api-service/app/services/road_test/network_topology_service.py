"""VRT network topology service — backed by the `topologies` table.

Phase 2.3 of the VRT-into-TestCase consolidation. The existing `Topology` ORM
model already has the columns needed (id, name, description, topology_type,
devices JSON, etc.). This service maps the legacy `NetworkTopology` Pydantic
shape (used by the /road-test/topologies endpoints) to/from rows in that
table so the conducted-mode topology metadata persists across restarts.

The ORM `Topology.topology_type` column tracks the *test mode* (ota /
conducted / hybrid) and is fixed to "conducted" for VRT network topologies.
The MIMO order (SISO / MIMO_2x2 / ...) from the road_test schema lives inside
the `devices` JSON blob alongside the device definitions.

This service is independent from `app/services/topology_service.py`, which
covers SwitchTopology (RF switch matrix layout) — a different domain entity.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.topology import Topology as TopologyORM, TopologyType as ORMTopologyType
from app.schemas.road_test import (
    BaseStationDevice,
    ChannelEmulatorDevice,
    DUTDevice,
    NetworkTopology,
    RFConnection,
    TopologyCreate,
    TopologyUpdate,
    TopologyType,
)

logger = logging.getLogger(__name__)


def _devices_blob(
    *,
    mimo_type: TopologyType,
    base_station: BaseStationDevice,
    channel_emulator: ChannelEmulatorDevice,
    dut: DUTDevice,
    connections: List[RFConnection],
    is_validated: bool = False,
    validation_errors: Optional[List[str]] = None,
    author: Optional[str] = None,
) -> str:
    """Serialize all VRT-specific topology data into the `devices` JSON column."""
    payload = {
        "mimo_type": mimo_type.value if hasattr(mimo_type, "value") else str(mimo_type),
        "base_station": base_station.model_dump(mode="json"),
        "channel_emulator": channel_emulator.model_dump(mode="json"),
        "dut": dut.model_dump(mode="json"),
        "connections": [c.model_dump(mode="json") for c in connections],
        "is_validated": is_validated,
        "validation_errors": validation_errors or [],
        "author": author,
    }
    return json.dumps(payload)


def _orm_to_network_topology(orm: TopologyORM) -> NetworkTopology:
    """Read a Topology ORM row and project it onto the NetworkTopology shape."""
    raw = json.loads(orm.devices) if orm.devices else {}
    return NetworkTopology(
        id=str(orm.id),
        name=orm.name,
        topology_type=TopologyType(raw.get("mimo_type", TopologyType.SISO.value)),
        description=orm.description,
        base_station=BaseStationDevice.model_validate(raw["base_station"]),
        channel_emulator=ChannelEmulatorDevice.model_validate(raw["channel_emulator"]),
        dut=DUTDevice.model_validate(raw["dut"]),
        connections=[RFConnection.model_validate(c) for c in raw.get("connections", [])],
        is_validated=raw.get("is_validated", False),
        validation_errors=raw.get("validation_errors", []),
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        author=raw.get("author") or orm.created_by,
    )


def _resolve_uuid(topology_id: str) -> Optional[UUID]:
    try:
        return UUID(topology_id)
    except (ValueError, AttributeError):
        return None


class NetworkTopologyService:
    """CRUD over the `topologies` table for VRT network topologies."""

    def list(self, db: Session) -> List[NetworkTopology]:
        rows = (
            db.query(TopologyORM)
            .filter(TopologyORM.topology_type == ORMTopologyType.CONDUCTED.value)
            .order_by(TopologyORM.created_at.desc())
            .all()
        )
        return [_orm_to_network_topology(r) for r in rows]

    def get(self, db: Session, topology_id: str) -> Optional[NetworkTopology]:
        uid = _resolve_uuid(topology_id)
        if uid is None:
            return None
        row = db.query(TopologyORM).filter(TopologyORM.id == uid).first()
        if row is None:
            return None
        return _orm_to_network_topology(row)

    def exists(self, db: Session, topology_id: str) -> bool:
        uid = _resolve_uuid(topology_id)
        if uid is None:
            return False
        return db.query(TopologyORM.id).filter(TopologyORM.id == uid).first() is not None

    def create(
        self,
        db: Session,
        payload: TopologyCreate,
        author: Optional[str] = None,
    ) -> NetworkTopology:
        row = TopologyORM(
            name=payload.name,
            description=payload.description,
            topology_type=ORMTopologyType.CONDUCTED.value,
            devices=_devices_blob(
                mimo_type=payload.topology_type,
                base_station=payload.base_station,
                channel_emulator=payload.channel_emulator,
                dut=payload.dut,
                connections=payload.connections,
                author=author,
            ),
            is_active=True,
            is_default=False,
            created_by=author,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info("Created network topology %s — %s", row.id, payload.name)
        return _orm_to_network_topology(row)

    def update(
        self,
        db: Session,
        topology_id: str,
        payload: TopologyUpdate,
    ) -> Optional[NetworkTopology]:
        uid = _resolve_uuid(topology_id)
        if uid is None:
            return None
        row = db.query(TopologyORM).filter(TopologyORM.id == uid).first()
        if row is None:
            return None

        # Read current state from JSON, apply patch, re-serialize
        existing = _orm_to_network_topology(row)
        update_data = payload.model_dump(exclude_unset=True)
        merged = existing.model_dump()
        for field, value in update_data.items():
            if value is not None:
                merged[field] = value
        merged_topology = NetworkTopology.model_validate(merged)

        if payload.name is not None:
            row.name = merged_topology.name
        if payload.description is not None:
            row.description = merged_topology.description

        row.devices = _devices_blob(
            mimo_type=merged_topology.topology_type,
            base_station=merged_topology.base_station,
            channel_emulator=merged_topology.channel_emulator,
            dut=merged_topology.dut,
            connections=merged_topology.connections,
            is_validated=merged_topology.is_validated,
            validation_errors=merged_topology.validation_errors,
            author=merged_topology.author or row.created_by,
        )

        db.commit()
        db.refresh(row)
        return _orm_to_network_topology(row)

    def set_validation_result(
        self,
        db: Session,
        topology_id: str,
        is_validated: bool,
        errors: List[str],
    ) -> Optional[NetworkTopology]:
        """Persist the outcome of /topologies/{id}/validate back into devices JSON."""
        uid = _resolve_uuid(topology_id)
        if uid is None:
            return None
        row = db.query(TopologyORM).filter(TopologyORM.id == uid).first()
        if row is None:
            return None
        existing = _orm_to_network_topology(row)
        row.devices = _devices_blob(
            mimo_type=existing.topology_type,
            base_station=existing.base_station,
            channel_emulator=existing.channel_emulator,
            dut=existing.dut,
            connections=existing.connections,
            is_validated=is_validated,
            validation_errors=errors,
            author=existing.author,
        )
        db.commit()
        db.refresh(row)
        return _orm_to_network_topology(row)

    def delete(self, db: Session, topology_id: str) -> bool:
        uid = _resolve_uuid(topology_id)
        if uid is None:
            return False
        row = db.query(TopologyORM).filter(TopologyORM.id == uid).first()
        if row is None:
            return False
        db.delete(row)
        db.commit()
        logger.info("Deleted network topology %s", topology_id)
        return True


network_topology_service = NetworkTopologyService()
