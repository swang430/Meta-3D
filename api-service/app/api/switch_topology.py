"""
Switch Topology API endpoints

CRUD operations for RF Switch Matrix hardware topology configurations,
and advanced endpoints for path resolution and calibration matrix.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
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

router = APIRouter(prefix="/switch-topologies", tags=["Switch Topologies"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topology template registry — loads dev-fixture template files at runtime.
#
# Templates live in ``api-service/scripts/dev-fixtures/topology-templates/`` so
# the *commercial* code path ships zero templates. New customers should build
# their topology in the GUI editor; developers who want a starter for a new
# site drop a ``<site>_<version>.py`` file in that directory exporting
# ``generate_topology_record() -> dict``.
#
# We resolve the directory via ``__file__`` (api-service is the repo subdir)
# and load each template via ``importlib.util.spec_from_file_location`` so
# the hyphenated ``dev-fixtures`` dir doesn't need to be an importable package.
# Production deployments that ship without ``scripts/dev-fixtures/`` will see
# an empty registry and the endpoint will 404 — which is exactly what we want
# (the workflow there is "build via GUI editor").
# ---------------------------------------------------------------------------

import importlib.util
from pathlib import Path
from typing import Callable

_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2]  # app/api/.. → app/.. → api-service/
    / "scripts" / "dev-fixtures" / "topology-templates"
)


def _list_template_ids() -> list[str]:
    """Return template_id values available on disk (filename without .py)."""
    if not _TEMPLATES_DIR.is_dir():
        return []
    return sorted(
        p.stem
        for p in _TEMPLATES_DIR.glob("*.py")
        if not p.name.startswith("_")
    )


def _load_template(template_id: str) -> Callable[[], dict]:
    """Load a template module by id and return its ``generate_topology_record``.

    Raises HTTPException(404) if the file doesn't exist or doesn't export
    the contract function.
    """
    if "/" in template_id or template_id.startswith(".") or not template_id.isidentifier():
        # Defensive: keep this constrained to bare module names — never let
        # an arbitrary path get joined with _TEMPLATES_DIR.
        raise HTTPException(status_code=400, detail=f"Invalid template_id: {template_id!r}")

    path = _TEMPLATES_DIR / f"{template_id}.py"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Topology template '{template_id}' not found. Available: "
                f"{_list_template_ids() or '(none — commercial deploy has no templates; build via GUI)'}"
            ),
        )

    spec = importlib.util.spec_from_file_location(f"topology_template_{template_id}", path)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail=f"Failed to load template module {template_id!r}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fn = getattr(module, "generate_topology_record", None)
    if not callable(fn):
        raise HTTPException(
            status_code=500,
            detail=(
                f"Template '{template_id}' does not export generate_topology_record(). "
                "Every template module must define a zero-arg function returning a "
                "SwitchTopology record dict."
            ),
        )
    return fn


@router.get("", response_model=SwitchTopologyListResponse)
def list_switch_topologies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    switch_category_id: Optional[UUID] = Query(None),
    chamber_id: Optional[UUID] = Query(
        None,
        description=(
            "Filter by chamber. Each (switch_category_id, chamber_id) pair has its "
            "own topology row — TopologyEditor uses this to pull the chamber-specific "
            "wiring without sweeping in other chambers' rows. Legacy rows with "
            "chamber_id=NULL are excluded when this filter is set."
        ),
    ),
    db: Session = Depends(get_db)
):
    """List all switch topologies"""
    query = db.query(SwitchTopology)

    if is_active is not None:
        query = query.filter(SwitchTopology.is_active == is_active)
    if switch_category_id:
        query = query.filter(SwitchTopology.switch_category_id == switch_category_id)
    if chamber_id:
        query = query.filter(SwitchTopology.chamber_id == chamber_id)

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


# ---------------------------------------------------------------------------
# Template endpoints are registered BEFORE the /{topology_id} parametric
# routes so FastAPI matches "templates" and "import/from-template" as literal
# path segments first. Otherwise GET /switch-topologies/templates would be
# routed to get_switch_topology with topology_id="templates" and fail UUID
# parsing with a 422.
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=List[str])
def list_topology_templates():
    """List topology template ids loadable via /import/from-template.

    On a commercial deploy without ``scripts/dev-fixtures/`` shipped, this
    returns ``[]`` — operators are expected to build via the GUI editor.
    """
    return _list_template_ids()


@router.post("/import/from-template", response_model=SwitchTopologyResponse)
def import_topology_from_template(
    switch_category_id: UUID,
    chamber_id: UUID,
    template_id: str = Query(
        ...,
        description=(
            "Filename (without .py) of a template under "
            "scripts/dev-fixtures/topology-templates/. The template must "
            "export ``generate_topology_record() -> dict``."
        ),
    ),
    db: Session = Depends(get_db),
):
    """Import a topology structure from a named template file.

    chamber_id is required: a topology models physical cabling inside a
    specific chamber, so importing one without binding it leaves a row that
    no consumer (calibration / measure / analysis) can resolve.

    Templates are loaded dynamically from
    ``api-service/scripts/dev-fixtures/topology-templates/<template_id>.py``
    by ``importlib`` — commercial deploys that don't ship dev-fixtures will
    see an empty registry and get 404.
    """
    from app.models.chamber import ChamberConfiguration
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()
    if chamber is None:
        raise HTTPException(
            status_code=422,
            detail=f"Chamber {chamber_id} not found — pick an existing chamber before importing topology",
        )

    generate = _load_template(template_id)
    topo_data = generate()

    db.query(SwitchTopology).filter(
        SwitchTopology.switch_category_id == switch_category_id,
        SwitchTopology.is_default == True
    ).update({"is_default": False})

    topology = SwitchTopology(
        switch_category_id=switch_category_id,
        chamber_id=chamber_id,
        **topo_data
    )
    topology.update_statistics()

    db.add(topology)
    db.commit()
    db.refresh(topology)
    logger.info(
        "Imported topology from template '%s' for switch category %s into chamber %s",
        template_id, switch_category_id, chamber_id,
    )
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

    # P1: enforce chamber_id on active topologies so calibration/measure/analysis
    # downstream consumers can always resolve a chamber. If the request is
    # explicitly setting chamber_id we validate it exists; if it leaves the
    # current value alone, only fail when both stored and requested are NULL
    # AND the topology will end up active.
    final_chamber_id = update_data.get("chamber_id", topology.chamber_id)
    final_is_active = update_data.get("is_active", topology.is_active)
    if final_is_active and final_chamber_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Active SwitchTopology requires chamber_id. Bind the topology "
                "to a chamber before saving, or mark it inactive."
            ),
        )
    if "chamber_id" in update_data and update_data["chamber_id"] is not None:
        from app.models.chamber import ChamberConfiguration
        if not db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == update_data["chamber_id"]
        ).first():
            raise HTTPException(
                status_code=422,
                detail=f"Chamber {update_data['chamber_id']} not found",
            )

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
