"""Probe API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import logging

from app.db.database import get_db
from app.models.probe import Probe
from app.schemas.probe import (
    ProbeCreateRequest,
    ProbeUpdateRequest,
    ProbeResponse,
    ProbesListResponse,
    BulkProbeRequest,
    BulkProbeResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/probes", response_model=ProbesListResponse)
def get_probes(db: Session = Depends(get_db)):
    """Get all probes"""
    try:
        probes = db.query(Probe).order_by(Probe.probe_number).all()
        return ProbesListResponse(total=len(probes), probes=probes)
    except Exception as e:
        logger.error(f"Error fetching probes: {e}")
        return ProbesListResponse(total=0, probes=[])


@router.post("/probes", response_model=ProbeResponse, status_code=201)
def create_probe(request: ProbeCreateRequest, db: Session = Depends(get_db)):
    """Create a new probe"""
    # Check duplicate probe_number
    existing = db.query(Probe).filter(
        Probe.probe_number == request.probe_number
    ).first()
    if existing:
        raise HTTPException(400, f"Probe number {request.probe_number} already exists")

    probe = Probe(
        **request.dict(exclude={'position'}),
        position=request.position.dict()
    )
    db.add(probe)
    db.commit()
    db.refresh(probe)
    return probe


@router.put("/probes/{probe_id}", response_model=ProbeResponse)
def update_probe(
    probe_id: UUID,
    request: ProbeUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update a probe"""
    probe = db.query(Probe).filter(Probe.id == probe_id).first()
    if not probe:
        raise HTTPException(404, "Probe not found")

    for key, value in request.dict(exclude_unset=True).items():
        if key == 'position' and value:
            setattr(probe, key, value.dict())
        elif value is not None:
            setattr(probe, key, value)

    db.commit()
    db.refresh(probe)
    return probe


@router.delete("/probes/{probe_id}", status_code=204)
def delete_probe(probe_id: UUID, db: Session = Depends(get_db)):
    """Delete a probe"""
    probe = db.query(Probe).filter(Probe.id == probe_id).first()
    if not probe:
        raise HTTPException(404, "Probe not found")

    db.delete(probe)
    db.commit()


@router.put("/probes/bulk", response_model=BulkProbeResponse)
def replace_probes(request: BulkProbeRequest, db: Session = Depends(get_db)):
    """Replace all probes in bulk"""
    # Count existing probes
    deleted_count = db.query(Probe).count()

    # Delete all existing probes
    db.query(Probe).delete()

    # Create new probes
    created_probes = []
    for probe_data in request.probes:
        probe = Probe(
            **probe_data.dict(exclude={'position'}),
            position=probe_data.position.dict()
        )
        db.add(probe)
        created_probes.append(probe)

    db.commit()
    for probe in created_probes:
        db.refresh(probe)

    return BulkProbeResponse(
        total=len(created_probes),
        created=len(created_probes),
        updated=0,
        deleted=deleted_count,
        probes=created_probes
    )
