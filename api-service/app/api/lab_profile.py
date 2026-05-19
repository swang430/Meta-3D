"""LabProfile API — list/create + RF chain resolution.

P2: the calibration-startup UI needs to (1) let operators pick a LabProfile
and (2) preview the resolved RF chains for a given operating mode before
hitting Start. The create endpoint is intentionally small: it creates the
operator-facing lab bundle from an existing chamber and current instrument
catalog, without introducing a separate CRUD surface yet.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.chamber import ChamberConfiguration
from app.models.instrument import InstrumentCategory, InstrumentConnection
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


class CreateLabProfileRequest(BaseModel):
    name: str
    description: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    chamber_config_id: Optional[UUID] = None
    is_active: bool = True
    created_by: Optional[str] = None


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


def _build_instrument_bindings(db: Session) -> List[dict]:
    bindings: List[dict] = []
    categories = (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.is_active == True)  # noqa: E712
        .all()
    )
    for category in categories:
        connection = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.category_id == category.id)
            .first()
        )
        bindings.append(
            {
                "category_id": str(category.id),
                "category_key": category.category_key,
                "instrument_model_id": None,
                "connection_endpoint": connection.endpoint if connection else None,
                "driver_mode": "auto",
                "role": f"primary_{category.category_key}",
            }
        )
    return bindings


def _to_summary(db: Session, profile: LabProfile) -> LabProfileSummary:
    chamber_name: Optional[str] = None
    if profile.chamber_config_id is not None:
        chamber = (
            db.query(ChamberConfiguration)
            .filter(ChamberConfiguration.id == profile.chamber_config_id)
            .first()
        )
        chamber_name = chamber.name if chamber else None

    return LabProfileSummary(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        organization=profile.organization,
        location=profile.location,
        chamber_config_id=profile.chamber_config_id,
        chamber_name=chamber_name,
        is_active=profile.is_active,
    )


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


@router.post("", response_model=LabProfileSummary, status_code=201)
def create_lab_profile(
    request: CreateLabProfileRequest,
    db: Session = Depends(get_db),
):
    """Create a LabProfile from an existing chamber and current instruments."""
    existing = db.query(LabProfile).filter(LabProfile.name == request.name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"LabProfile name already exists: {request.name}",
        )

    chamber_id = request.chamber_config_id
    if chamber_id is None:
        active_chamber = (
            db.query(ChamberConfiguration)
            .filter(ChamberConfiguration.is_active == True)  # noqa: E712
            .first()
        )
        if not active_chamber:
            raise HTTPException(
                status_code=422,
                detail="No active chamber configuration found",
            )
        chamber_id = active_chamber.id
    else:
        chamber = (
            db.query(ChamberConfiguration)
            .filter(ChamberConfiguration.id == chamber_id)
            .first()
        )
        if not chamber:
            raise HTTPException(
                status_code=422,
                detail=f"Chamber configuration not found: {chamber_id}",
            )

    profile = LabProfile(
        name=request.name,
        description=request.description,
        organization=request.organization,
        location=request.location,
        chamber_config_id=chamber_id,
        instrument_bindings=_build_instrument_bindings(db),
        is_active=request.is_active,
        created_by=request.created_by,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _to_summary(db, profile)


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
