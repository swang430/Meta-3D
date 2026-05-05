"""LabProfile API — list + RF chain resolution.

P2: the calibration-startup UI needs to (1) let operators pick a LabProfile
and (2) preview the resolved RF chains for a given operating mode before
hitting Start. Both reads are tiny enough that they live here together
rather than in a dedicated CRUD module — there's no LabProfile create/edit
flow yet (labs are seeded by deployment scripts).
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.chamber import ChamberConfiguration
from app.models.lab_profile import LabProfile
from app.services.calibration.rf_chain_resolver import resolve_rf_chains

router = APIRouter(prefix="/lab-profiles", tags=["Lab Profiles"])


class LabProfileSummary(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    chamber_config_id: Optional[UUID] = None
    chamber_name: Optional[str] = Field(None, description="Resolved name for chamber_config_id")
    is_active: bool


class RFChainEntry(BaseModel):
    chain_id: str = Field(description="SwitchTopology connection id; stable lookup key")
    ce_port: str = Field(description="Source-side label, e.g. 'B1.1' for the channel emulator port")
    probe_id: int
    polarization: str
    cable_loss_db: float = Field(description="Per-connection cable loss from the topology")


class RFChainResolutionResponse(BaseModel):
    lab_profile_id: UUID
    lab_name: str
    chamber_id: Optional[UUID] = None
    chamber_name: Optional[str] = None
    topology_id: Optional[str] = None
    topology_name: Optional[str] = None
    operating_mode: str
    chains: List[RFChainEntry]
    warnings: List[str]
    success: bool


@router.get("", response_model=List[LabProfileSummary])
def list_lab_profiles(
    is_active: Optional[bool] = Query(True, description="Filter by active flag; default active-only"),
    db: Session = Depends(get_db),
):
    """List LabProfiles for selection in calibration / measurement UIs."""
    q = db.query(LabProfile)
    if is_active is not None:
        q = q.filter(LabProfile.is_active == is_active)
    rows = q.order_by(LabProfile.name).all()

    chamber_ids = {r.chamber_config_id for r in rows if r.chamber_config_id is not None}
    chambers_by_id = {}
    if chamber_ids:
        for c in db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id.in_(chamber_ids)
        ).all():
            chambers_by_id[c.id] = c.name

    return [
        LabProfileSummary(
            id=r.id,
            name=r.name,
            description=r.description,
            organization=r.organization,
            location=r.location,
            chamber_config_id=r.chamber_config_id,
            chamber_name=chambers_by_id.get(r.chamber_config_id) if r.chamber_config_id else None,
            is_active=r.is_active,
        )
        for r in rows
    ]


@router.get("/{lab_profile_id}/rf-chains", response_model=RFChainResolutionResponse)
def get_rf_chains(
    lab_profile_id: UUID,
    operating_mode: str = Query("mimo_ota", description="SwitchTopology operating mode id"),
    db: Session = Depends(get_db),
):
    """Resolve RF chains for a (lab_profile, operating_mode) pair.

    Returns the same data the path-loss calibrator iterates over, plus
    chamber/topology names so the UI can render `VNA→Switch→Cable→Probe`
    for human verification before kicking off a calibration.
    """
    try:
        resolution = resolve_rf_chains(db, lab_profile_id, operating_mode)
    except ValueError as e:
        # Lab missing / chamber unbound — actionable 422 instead of 500.
        raise HTTPException(status_code=422, detail=str(e))

    lab = db.query(LabProfile).filter(LabProfile.id == lab_profile_id).first()
    chamber_name: Optional[str] = None
    if resolution.chamber_id is not None:
        ch = db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == resolution.chamber_id
        ).first()
        chamber_name = ch.name if ch else None

    return RFChainResolutionResponse(
        lab_profile_id=resolution.lab_profile_id,
        lab_name=lab.name if lab else "(unknown)",
        chamber_id=resolution.chamber_id,
        chamber_name=chamber_name,
        topology_id=resolution.topology_id,
        topology_name=resolution.topology_name,
        operating_mode=resolution.operating_mode,
        chains=[
            RFChainEntry(
                chain_id=c.chain_id,
                ce_port=c.ce_port,
                probe_id=c.probe_id,
                polarization=c.polarization,
                cable_loss_db=c.cable_loss_db,
            )
            for c in resolution.chains
        ],
        warnings=resolution.warnings,
        success=resolution.success,
    )
