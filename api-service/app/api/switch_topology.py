"""
Switch Topology API endpoints

CRUD operations for RF Switch Matrix hardware topology configurations,
and advanced endpoints for path resolution and calibration matrix.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from uuid import UUID
import logging

from app.db.database import get_db
from app.models.switch_topology import SwitchTopology
from app.schemas.switch_topology import (
    SwitchTopologyCreate,
    SwitchTopologyUpdate,
    SwitchTopologyResponse,
    SwitchTopologyListResponse,
    SignalPathResponse,
    CalibrationMatrixResponse,
)
from app.services.topology_service import TopologyService
from app.hal.port_maps.caict_default import generate_caict_topology_record

router = APIRouter(prefix="/switch-topologies", tags=["Switch Topologies"])
logger = logging.getLogger(__name__)


@router.get("", response_model=SwitchTopologyListResponse)
def list_switch_topologies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    switch_category_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db)
):
    """List all switch topologies"""
    query = db.query(SwitchTopology)

    if is_active is not None:
        query = query.filter(SwitchTopology.is_active == is_active)
    if switch_category_id:
        query = query.filter(SwitchTopology.switch_category_id == switch_category_id)

    total = query.count()
    topologies = query.order_by(SwitchTopology.created_at.desc()).offset(skip).limit(limit).all()

    return SwitchTopologyListResponse(
        total=total,
        items=topologies
    )


@router.post("", response_model=SwitchTopologyResponse, status_code=201)
def create_switch_topology(
    request: SwitchTopologyCreate,
    db: Session = Depends(get_db)
):
    """Create a new switch topology"""
    # Define default if this is marked as default
    if request.is_default:
        db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == request.switch_category_id,
            SwitchTopology.is_default == True
        ).update({"is_default": False})

    # Dump nested Pydantic models to dicts
    nodes_data = [d.model_dump() for d in request.nodes]
    connections_data = [d.model_dump() for d in request.connections]
    modes_data = [d.model_dump() for d in request.operating_modes]

    topology = SwitchTopology(
        switch_category_id=request.switch_category_id,
        chamber_id=request.chamber_id,
        name=request.name,
        description=request.description,
        version=request.version,
        site_name=request.site_name,
        system_model=request.system_model,
        installed_date=request.installed_date,
        installed_by=request.installed_by,
        is_active=request.is_active,
        is_default=request.is_default,
        nodes=nodes_data,
        connections=connections_data,
        operating_modes=modes_data,
    )
    topology.update_statistics()

    db.add(topology)
    db.commit()
    db.refresh(topology)
    logger.info(f"Created switch topology: {topology.id} - {topology.name}")
    return topology


@router.get("/{topology_id}", response_model=SwitchTopologyResponse)
def get_switch_topology(
    topology_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific switch topology by ID"""
    topology = db.query(SwitchTopology).filter(SwitchTopology.id == topology_id).first()
    if not topology:
        raise HTTPException(status_code=404, detail="Switch topology not found")
    return topology


@router.patch("/{topology_id}", response_model=SwitchTopologyResponse)
def update_switch_topology(
    topology_id: UUID,
    request: SwitchTopologyUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing switch topology"""
    topology = db.query(SwitchTopology).filter(SwitchTopology.id == topology_id).first()
    if not topology:
        raise HTTPException(status_code=404, detail="Switch topology not found")

    if request.is_default and not topology.is_default:
        db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == topology.switch_category_id,
            SwitchTopology.is_default == True
        ).update({"is_default": False})

    update_data = request.model_dump(exclude_unset=True)
    
    # Process Pydantic models if they are in the update
    if "nodes" in update_data:
        update_data["nodes"] = [d.model_dump() if hasattr(d, 'model_dump') else d for d in update_data["nodes"]]
    if "connections" in update_data:
        update_data["connections"] = [d.model_dump() if hasattr(d, 'model_dump') else d for d in update_data["connections"]]
    if "operating_modes" in update_data:
        update_data["operating_modes"] = [d.model_dump() if hasattr(d, 'model_dump') else d for d in update_data["operating_modes"]]

    for key, value in update_data.items():
        setattr(topology, key, value)

    if any(k in update_data for k in ["nodes", "connections"]):
        topology.update_statistics()

    db.commit()
    db.refresh(topology)
    logger.info(f"Updated switch topology: {topology_id}")
    return topology


@router.delete("/{topology_id}", status_code=204)
def delete_switch_topology(
    topology_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a switch topology"""
    topology = db.query(SwitchTopology).filter(SwitchTopology.id == topology_id).first()
    if not topology:
        raise HTTPException(status_code=404, detail="Switch topology not found")

    db.delete(topology)
    db.commit()
    return None


@router.post("/import/caict-default", response_model=SwitchTopologyResponse)
def import_caict_default_topology(
    switch_category_id: UUID,
    db: Session = Depends(get_db)
):
    """Import the default CAICT AMS8947 topology structure"""
    topo_data = generate_caict_topology_record()
    
    # Reset existing defaults for this category
    db.query(SwitchTopology).filter(
        SwitchTopology.switch_category_id == switch_category_id,
        SwitchTopology.is_default == True
    ).update({"is_default": False})

    topology = SwitchTopology(
        switch_category_id=switch_category_id,
        **topo_data
    )
    topology.update_statistics()

    db.add(topology)
    db.commit()
    db.refresh(topology)
    logger.info(f"Imported default CAICT topology for switch category: {switch_category_id}")
    return topology


# ==========================================
# TopologyService Operations
# ==========================================

@router.get("/{topology_id}/paths/{mode}", response_model=List[SignalPathResponse])
def resolve_topology_paths(
    topology_id: UUID,
    mode: str,
    db: Session = Depends(get_db)
):
    """Resolve all active signal paths for a specific operating mode"""
    topology = db.query(SwitchTopology).filter(SwitchTopology.id == topology_id).first()
    if not topology:
        raise HTTPException(status_code=404, detail="Switch topology not found")

    svc = TopologyService(topology.__dict__)
    
    # Check if mode exists
    if mode not in [m["id"] for m in topology.operating_modes]:
        raise HTTPException(status_code=400, detail=f"Mode '{mode}' not found in topology")
        
    paths = svc.resolve_paths(mode)
    
    response = []
    for path in paths:
        response.append({
            "path_id": path.path_id,
            "source_node": path.source_node.__dict__,
            "target_node": path.target_node.__dict__,
            "total_loss_db": path.total_loss_db,
            "total_phase_deg": path.total_phase_deg,
            "calibration_status": path.calibration_status,
            "hop_count": len(path.hops)
        })
        
    return response


@router.get("/{topology_id}/calibration-matrix/{mode}", response_model=CalibrationMatrixResponse)
def get_topology_calibration_matrix(
    topology_id: UUID,
    mode: str,
    db: Session = Depends(get_db)
):
    """Generate the calibration compensation matrix for a specific operating mode"""
    topology = db.query(SwitchTopology).filter(SwitchTopology.id == topology_id).first()
    if not topology:
        raise HTTPException(status_code=404, detail="Switch topology not found")

    svc = TopologyService(topology.__dict__)
    
    if mode not in [m["id"] for m in topology.operating_modes]:
        raise HTTPException(status_code=400, detail=f"Mode '{mode}' not found in topology")
        
    matrix = svc.get_calibration_matrix(mode)
    return CalibrationMatrixResponse(mode_id=mode, matrix=matrix)


@router.get("/{topology_id}/validate")
def validate_topology(
    topology_id: UUID,
    db: Session = Depends(get_db)
):
    """Validate a topology for broken links and issues"""
    topology = db.query(SwitchTopology).filter(SwitchTopology.id == topology_id).first()
    if not topology:
        raise HTTPException(status_code=404, detail="Switch topology not found")

    svc = TopologyService(topology.__dict__)
    issues = svc.validate()
    
    return {
        "is_valid": len([i for i in issues if i.severity == "error"]) == 0,
        "issues": [i.__dict__ for i in issues]
    }
