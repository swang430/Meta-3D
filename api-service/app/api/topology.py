"""Topology API endpoints

CRUD operations for hardware topology configurations.
A topology defines the physical setup of instruments and devices for testing.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from datetime import datetime
import json
import logging

from app.db.database import get_db
from app.models.topology import Topology, TopologyType as ModelTopologyType
from app.schemas.topology import (
    TopologyCreate,
    TopologyUpdate,
    TopologyResponse,
    TopologyListResponse,
    TopologySummary,
    DeviceConfig,
    TopologyType,
)

router = APIRouter(prefix="/topologies", tags=["Topologies"])
logger = logging.getLogger(__name__)


def _topology_to_response(topology: Topology) -> TopologyResponse:
    """Convert DB model to response schema"""
    devices = []
    if topology.devices:
        try:
            devices_data = json.loads(topology.devices)
            devices = [DeviceConfig(**d) for d in devices_data]
        except (json.JSONDecodeError, TypeError):
            pass

    return TopologyResponse(
        id=topology.id,
        name=topology.name,
        description=topology.description,
        topology_type=topology.topology_type,
        devices=devices,
        is_active=topology.is_active,
        is_default=topology.is_default,
        created_at=topology.created_at,
        updated_at=topology.updated_at,
        created_by=topology.created_by,
    )


@router.get("", response_model=TopologyListResponse)
def list_topologies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    topology_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    List all topologies

    Returns paginated list of topology configurations.
    """
    query = db.query(Topology)

    if is_active is not None:
        query = query.filter(Topology.is_active == is_active)

    if topology_type:
        query = query.filter(Topology.topology_type == topology_type)

    total = query.count()
    topologies = query.order_by(Topology.created_at.desc()).offset(skip).limit(limit).all()

    return TopologyListResponse(
        total=total,
        items=[_topology_to_response(t) for t in topologies]
    )


@router.post("", response_model=TopologyResponse, status_code=201)
def create_topology(
    request: TopologyCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new topology

    Defines a hardware configuration for testing.
    """
    # If setting as default, unset other defaults
    if request.is_default:
        db.query(Topology).filter(Topology.is_default == True).update({"is_default": False})

    # Convert devices to JSON
    devices_json = json.dumps([d.model_dump() for d in request.devices])

    topology = Topology(
        name=request.name,
        description=request.description,
        topology_type=request.topology_type.value,
        devices=devices_json,
        is_default=request.is_default,
        created_by=request.created_by,
    )

    db.add(topology)
    db.commit()
    db.refresh(topology)

    logger.info(f"Created topology: {topology.id} - {topology.name}")

    return _topology_to_response(topology)


@router.get("/{topology_id}", response_model=TopologyResponse)
def get_topology(
    topology_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific topology by ID"""
    topology = db.query(Topology).filter(Topology.id == topology_id).first()

    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found")

    return _topology_to_response(topology)


@router.patch("/{topology_id}", response_model=TopologyResponse)
def update_topology(
    topology_id: UUID,
    request: TopologyUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing topology"""
    topology = db.query(Topology).filter(Topology.id == topology_id).first()

    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found")

    # If setting as default, unset other defaults
    if request.is_default:
        db.query(Topology).filter(
            Topology.is_default == True,
            Topology.id != topology_id
        ).update({"is_default": False})

    # Update fields
    if request.name is not None:
        topology.name = request.name
    if request.description is not None:
        topology.description = request.description
    if request.topology_type is not None:
        topology.topology_type = request.topology_type.value
    if request.devices is not None:
        topology.devices = json.dumps([d.model_dump() for d in request.devices])
    if request.is_active is not None:
        topology.is_active = request.is_active
    if request.is_default is not None:
        topology.is_default = request.is_default

    db.commit()
    db.refresh(topology)

    logger.info(f"Updated topology: {topology_id}")

    return _topology_to_response(topology)


@router.delete("/{topology_id}", status_code=204)
def delete_topology(
    topology_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a topology"""
    topology = db.query(Topology).filter(Topology.id == topology_id).first()

    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found")

    db.delete(topology)
    db.commit()

    logger.info(f"Deleted topology: {topology_id}")

    return None


@router.get("/default", response_model=TopologyResponse)
def get_default_topology(db: Session = Depends(get_db)):
    """Get the default topology"""
    topology = db.query(Topology).filter(Topology.is_default == True).first()

    if not topology:
        raise HTTPException(status_code=404, detail="No default topology configured")

    return _topology_to_response(topology)


@router.post("/{topology_id}/set-default", response_model=TopologyResponse)
def set_default_topology(
    topology_id: UUID,
    db: Session = Depends(get_db)
):
    """Set a topology as the default"""
    topology = db.query(Topology).filter(Topology.id == topology_id).first()

    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found")

    # Unset other defaults
    db.query(Topology).filter(
        Topology.is_default == True,
        Topology.id != topology_id
    ).update({"is_default": False})

    topology.is_default = True
    db.commit()
    db.refresh(topology)

    logger.info(f"Set default topology: {topology_id}")

    return _topology_to_response(topology)
