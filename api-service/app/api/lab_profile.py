"""LabProfile API — list + create + RF chain resolution.

P2 historic note: the first version of this module was read-only because
labs were expected to be seeded by deployment scripts. P0-2 (first-call
roadmap) added the wizard-driven self-serve create flow so operators can
spin up a lab on a fresh install without filing a deploy ticket.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
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


# ---------------------------------------------------------------------------
# Create-LabProfile request — used by the P0-2 wizard
# ---------------------------------------------------------------------------
#
# Schema mirrors the `LabProfile` model's columns but only exposes fields
# the wizard collects. `chamber_config_id` is required (acceptance: "wizard
# completes → LabProfile with a Chamber") and `instrument_bindings` must
# have at least one entry (acceptance: "≥1 Instrument bound"). Everything
# else is optional and editable post-wizard via the lab settings UI.

class InstrumentBinding(BaseModel):
    """One row in the LabProfile.instrument_bindings JSONB array.

    Mirrors the schema documented in the model column comment. Kept loose
    (instrument_model_id optional) because the wizard step that wires up
    each category may legitimately leave a model unselected if the operator
    only knows the IP at install time — but the binding row itself must
    exist so the calibration UI can show that category as 'configured'.

    ``category_id`` is the DB UUID for InstrumentCategory.id. We tighten
    this rather than accept arbitrary strings because the diagnostic
    context resolver (`services/diagnostic_context._parse_instrument_bindings`)
    joins on UUID to populate `category_key`; non-UUID values would
    silently degrade the *IDN? sweep into "no HAL driver" for every
    bound instrument. Wizard reads the UUID from
    `GET /instruments/catalog` → `categoryId` field, which is exposed
    precisely for this purpose. (Codex P1 review on PR #18.)
    """
    category_id: UUID = Field(
        description='InstrumentCategory.id (DB UUID, available on /instruments/catalog as categoryId)',
    )
    instrument_model_id: Optional[UUID] = Field(
        None,
        description="Chosen InstrumentModel.id, or null if model TBD",
    )
    connection_endpoint: str = Field(
        description='Transport address, e.g. "192.168.1.10:5025" or "TCPIP0::host::INSTR"',
        min_length=1,
    )
    driver_mode: str = Field(
        "auto",
        description="auto | mock | real (matches DriverMode enum the HAL uses)",
    )
    role: Optional[str] = Field(
        None,
        description="Human-readable role for this binding, e.g. 'primary_channel_emulator'",
    )


class LabProfileCreateRequest(BaseModel):
    """Wizard payload for POST /lab-profiles."""
    name: str = Field(
        min_length=1, max_length=255,
        description='Unique lab identifier, e.g. "CAICT-Lab-1"',
    )
    chamber_config_id: UUID = Field(
        description="FK to chamber_configurations.id — the chamber this lab uses",
    )
    instrument_bindings: List[InstrumentBinding] = Field(
        min_length=1,
        description="At least one instrument category must be bound for first-call to work",
    )
    description: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    is_active: bool = Field(
        True,
        description="Wizard-created labs default to active so calibration can begin immediately",
    )
    created_by: Optional[str] = Field(
        None,
        description="Operator login or display name; null when no auth context",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank after trimming")
        return v


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


def _to_summary(row: LabProfile, chamber_name: Optional[str]) -> LabProfileSummary:
    return LabProfileSummary(
        id=row.id,
        name=row.name,
        description=row.description,
        organization=row.organization,
        location=row.location,
        chamber_config_id=row.chamber_config_id,
        chamber_name=chamber_name,
        is_active=row.is_active,
    )


@router.post(
    "",
    response_model=LabProfileSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_lab_profile(
    payload: LabProfileCreateRequest,
    db: Session = Depends(get_db),
):
    """Create a LabProfile from the init wizard (P0-2).

    Errors:
      - 409 if ``name`` already exists (unique constraint).
      - 422 if ``chamber_config_id`` does not resolve to a row.

    On success returns the same shape as ``GET /lab-profiles`` so the
    wizard can stash the response directly into the TanStack Query
    cache without a second round-trip.
    """
    chamber = (
        db.query(ChamberConfiguration)
        .filter(ChamberConfiguration.id == payload.chamber_config_id)
        .first()
    )
    if chamber is None:
        raise HTTPException(
            status_code=422,
            detail=f"chamber_config_id {payload.chamber_config_id} not found",
        )

    profile = LabProfile(
        name=payload.name,
        description=payload.description,
        organization=payload.organization,
        location=payload.location,
        chamber_config_id=payload.chamber_config_id,
        instrument_bindings=[b.model_dump(mode="json") for b in payload.instrument_bindings],
        is_active=payload.is_active,
        created_by=payload.created_by,
    )
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Most likely: unique constraint on `name`. Inspecting the inner
        # SQLSTATE would let us split this further, but for the wizard
        # the actionable surface is just "pick a different name".
        raise HTTPException(
            status_code=409,
            detail=f"LabProfile with this name already exists: {exc.orig}",
        ) from exc

    db.refresh(profile)
    return _to_summary(profile, chamber.name)


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
