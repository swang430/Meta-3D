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
from app.services.chamber_resolution import resolve_current_chamber

router = APIRouter(prefix="/switch-topologies", tags=["Switch Topologies"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P1-57：除 /templates 外，所有端点的暗室真值 = lab_profile_id →
# resolve_current_chamber()。后端不再相信客户端自由提交的 chamber_id ——
# 那正是「拓扑编辑器能把拓扑写进另一个暗室」的口子。
# ---------------------------------------------------------------------------

def _resolve_scope(db: Session, lab_profile_id: UUID):
    """lab_profile_id → 绑定的暗室；解析失败一律 422（fail-closed，不回退）。"""
    try:
        return resolve_current_chamber(db, lab_profile_id)
    except ValueError as exc:
        # missing / inactive lab、无 chamber 绑定、绑定指向缺失暗室 —— 都是
        # 调用方上下文坏了，不是服务器错误。
        raise HTTPException(status_code=422, detail=str(exc))


def _assert_chamber_consistent(requested: Optional[UUID], resolved_id: UUID) -> None:
    """兼容期仍收 chamber_id 时只做一致性断言 —— 不一致必须在任何写入前失败。"""
    if requested is not None and requested != resolved_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"chamber_id {requested} 与当前 LabProfile 绑定的暗室 "
                f"{resolved_id} 不一致 —— 暗室由 LabProfile 派生，请先切换到"
                "绑定目标暗室的 LabProfile。"
            ),
        )


def _load_scoped_topology(db: Session, topology_id: UUID, chamber_id: UUID) -> SwitchTopology:
    """按 id 取行并校验属于当前 lab 的暗室；别的暗室的行一律 409。"""
    topology = db.query(SwitchTopology).filter(SwitchTopology.id == topology_id).first()
    if not topology:
        raise HTTPException(status_code=404, detail="Switch topology not found")
    if topology.chamber_id != chamber_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Topology {topology_id} 属于另一个暗室（{topology.chamber_id}），"
                "当前 LabProfile 无权操作 —— 请先切换到绑定该暗室的 LabProfile。"
            ),
        )
    return topology


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
    lab_profile_id: UUID = Query(
        ...,
        description="当前 LabProfile —— 暗室由它派生（P1-57），列表只含该暗室的行。",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    switch_category_id: Optional[UUID] = Query(None),
    chamber_id: Optional[UUID] = Query(
        None,
        description="兼容参数：如提供必须等于 LabProfile 派生的暗室，否则 422。",
    ),
    db: Session = Depends(get_db)
):
    """List switch topologies in the current lab's chamber"""
    chamber = _resolve_scope(db, lab_profile_id)
    _assert_chamber_consistent(chamber_id, chamber.id)

    query = db.query(SwitchTopology).filter(SwitchTopology.chamber_id == chamber.id)

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
    """Create a new switch topology in the current lab's chamber"""
    chamber = _resolve_scope(db, request.lab_profile_id)
    _assert_chamber_consistent(request.chamber_id, chamber.id)

    # Define default if this is marked as default —— 只在本暗室范围内让位，
    # 不许从 lab A 顺手改掉 chamber B 的默认行（P1-57 跨暗室写点）。
    if request.is_default:
        db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == request.switch_category_id,
            SwitchTopology.chamber_id == chamber.id,
            SwitchTopology.is_default == True
        ).update({"is_default": False})

    # Dump nested Pydantic models to dicts
    nodes_data = [d.model_dump() for d in request.nodes]
    connections_data = [d.model_dump() for d in request.connections]
    modes_data = [d.model_dump() for d in request.operating_modes]

    topology = SwitchTopology(
        switch_category_id=request.switch_category_id,
        chamber_id=chamber.id,
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
    lab_profile_id: UUID = Query(
        ...,
        description="当前 LabProfile —— 导入目标暗室由它派生（P1-57）。",
    ),
    template_id: str = Query(
        ...,
        description=(
            "Filename (without .py) of a template under "
            "scripts/dev-fixtures/topology-templates/. The template must "
            "export ``generate_topology_record() -> dict``."
        ),
    ),
    chamber_id: Optional[UUID] = Query(
        None,
        description="兼容参数：如提供必须等于 LabProfile 派生的暗室，否则 422。",
    ),
    replace_existing: bool = Query(
        False,
        description=(
            "重导入：先删除同一 (switch_category_id, 派生暗室) 的既有行再导入。"
            "P1-57 之前这个删除在 GUI 客户端做（先删后验 —— lab/模板解析失败时"
            "行已经没了）；收进服务端后保证完整解析成功才动行。"
        ),
    ),
    db: Session = Depends(get_db),
):
    """Import a topology structure from a named template file.

    导入目标暗室 = lab_profile_id 派生（不再收裸 chamber_id 当真值）。
    解析顺序是硬约束：lab → chamber → 模板全部成功之后才碰任何既有行。

    Templates are loaded dynamically from
    ``api-service/scripts/dev-fixtures/topology-templates/<template_id>.py``
    by ``importlib`` — commercial deploys that don't ship dev-fixtures will
    see an empty registry and get 404.
    """
    chamber = _resolve_scope(db, lab_profile_id)
    _assert_chamber_consistent(chamber_id, chamber.id)

    generate = _load_template(template_id)
    topo_data = generate()

    if replace_existing:
        # 只删本 (switch, 派生暗室) 的行 —— 别的暗室的行一根手指都不碰
        db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == switch_category_id,
            SwitchTopology.chamber_id == chamber.id,
        ).delete()

    db.query(SwitchTopology).filter(
        SwitchTopology.switch_category_id == switch_category_id,
        SwitchTopology.chamber_id == chamber.id,
        SwitchTopology.is_default == True
    ).update({"is_default": False})

    topology = SwitchTopology(
        switch_category_id=switch_category_id,
        chamber_id=chamber.id,
        **topo_data
    )
    topology.update_statistics()

    db.add(topology)
    db.commit()
    db.refresh(topology)
    logger.info(
        "Imported topology from template '%s' for switch category %s into chamber %s (replace=%s)",
        template_id, switch_category_id, chamber.id, replace_existing,
    )
    return topology


@router.get("/{topology_id}", response_model=SwitchTopologyResponse)
def get_switch_topology(
    topology_id: UUID,
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """Get a specific switch topology by ID (scoped to the current lab's chamber)"""
    chamber = _resolve_scope(db, lab_profile_id)
    return _load_scoped_topology(db, topology_id, chamber.id)


@router.patch("/{topology_id}", response_model=SwitchTopologyResponse)
def update_switch_topology(
    topology_id: UUID,
    request: SwitchTopologyUpdate,
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """Update an existing switch topology (scoped to the current lab's chamber)"""
    chamber = _resolve_scope(db, lab_profile_id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

    if request.is_default and not topology.is_default:
        # 默认位让位只在本暗室内 —— 不从 lab A 顺手改 chamber B 的行
        db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == topology.switch_category_id,
            SwitchTopology.chamber_id == chamber.id,
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

    # P1-57：chamber 由 LabProfile 派生 —— PATCH 不接受改绑（含置 NULL）。
    # 之前的规则只查「chamber 存在」，现在收窄成「必须等于派生暗室」；
    # 想把拓扑放进另一个暗室 = 先切到绑定那个暗室的 LabProfile 再建/导。
    if "chamber_id" in update_data and update_data["chamber_id"] != chamber.id:
        raise HTTPException(
            status_code=422,
            detail=(
                "chamber_id 由当前 LabProfile 派生，不接受改绑。"
                f"当前暗室：{chamber.id}，请求值：{update_data['chamber_id']}。"
            ),
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
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """Delete a switch topology (scoped to the current lab's chamber)"""
    chamber = _resolve_scope(db, lab_profile_id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

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
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """Resolve all active signal paths for a specific operating mode"""
    chamber = _resolve_scope(db, lab_profile_id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

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
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """Generate the calibration compensation matrix for a specific operating mode"""
    chamber = _resolve_scope(db, lab_profile_id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

    svc = TopologyService(topology.__dict__)
    
    if mode not in [m["id"] for m in topology.operating_modes]:
        raise HTTPException(status_code=400, detail=f"Mode '{mode}' not found in topology")
        
    matrix = svc.get_calibration_matrix(mode)
    return CalibrationMatrixResponse(mode_id=mode, matrix=matrix)


@router.get("/{topology_id}/validate")
def validate_topology(
    topology_id: UUID,
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """Validate a topology for broken links and issues"""
    chamber = _resolve_scope(db, lab_profile_id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

    svc = TopologyService(topology.__dict__)
    issues = svc.validate()
    
    return {
        "is_valid": len([i for i in issues if i.severity == "error"]) == 0,
        "issues": [i.__dict__ for i in issues]
    }
