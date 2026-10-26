"""
Switch Topology API endpoints

CRUD operations for RF Switch Matrix hardware topology configurations,
and advanced endpoints for path resolution and calibration matrix.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from copy import deepcopy
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.exc import IntegrityError
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
    TopologyConnection,
)
from app.services.topology_service import TopologyService
from app.schemas.topology_nominal import (
    MISSING, CONNECTION_NUMERIC_FIELDS, same_json, validate_nominal_write,
    preserve_graph_rows, normalize_nominal_metadata,
)
from app.services.declared_rf_routes import resolve_saved_rf_path
from app.schemas.topology_ports import validate_port_write
from app.schemas.topology_internal_paths import validate_internal_path_write
from app.services.chamber_resolution import resolve_current_chamber
from app.services.calibration.route_calibration import assert_route_topologies_deletable, RouteApplicationConflict

router = APIRouter(prefix="/switch-topologies", tags=["Switch Topologies"])
logger = logging.getLogger(__name__)


async def _raw_topology_body(request: Request) -> dict:
    """保留请求的JSON类型与缺键；同步写端点仍沿用原会话模型。"""
    return await request.json()


def preserve_connection_rows(raw_rows, normalized_rows, previous_rows, declarations):
    old_by_id = {row['id']: row for row in previous_rows or []}
    saved = []
    for raw, normalized in zip(raw_rows, normalized_rows):
        old = old_by_id.get(raw['id'], {})
        old_normalized = TopologyConnection.model_validate(old).model_dump(exclude_unset=True) if old else {}
        # 既有键沿存储顺序保留，已知键的显式删除仍生效；opaque只由服务端恢复。
        result = {key: deepcopy(value) for key, value in old.items()
                  if key not in TopologyConnection.model_fields or key in raw}
        declared = set(declarations.get(raw['id'], []))
        for key, value in raw.items():
            if key not in normalized:
                continue
            prior = old.get(key, MISSING)
            equal_raw = same_json(value, prior)
            equal_display = (key in CONNECTION_NUMERIC_FIELDS and key in old
                             and same_json(value, old_normalized[key]))
            if key not in declared and (equal_raw or equal_display):
                result[key] = deepcopy(prior)
            elif key == 'nominal_metadata':
                result[key] = normalize_nominal_metadata(value, prior)
            else:
                result[key] = deepcopy(normalized[key])
        saved.append(result)
    return saved


def _validate_nominal(nodes, connections, *, previous_nodes=None, previous_connections=None):
    try:
        validate_nominal_write(nodes, connections, previous_nodes=previous_nodes,
                               previous_connections=previous_connections)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


def _validate_ports(nodes, connections, **kwargs):
    try:
        validate_port_write(nodes, connections, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


def _validate_internal_paths(nodes, connections, modes, **kwargs):
    try:
        validate_internal_path_write(nodes, connections, modes, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


def _validate_numeric_declarations(declarations, raw_connections):
    by_id = {row['id']: row for row in raw_connections or []}
    for ident, keys in declarations.items():
        if (ident not in by_id or len(keys) != len(set(keys)) or
                any(key not in CONNECTION_NUMERIC_FIELDS or key not in by_id[ident] for key in keys)):
            raise HTTPException(422, detail='数值声明必须引用本次提交的连线与数值字段，且不得重复')


def _validate_structure(nodes, connections, modes) -> None:
    """只校验操作员声明的接线结构，不代表硬件能力、接通或校准资格。"""
    def index(items, name):
        if not isinstance(items, list):
            raise HTTPException(422, detail=f"{name} 必须是列表，不能置空")
        result = {}
        for item in items:
            ident = item.get("id") if isinstance(item, dict) else None
            if not isinstance(ident, str) or not ident.strip() or ident in result:
                raise HTTPException(422, detail=f"{name} 编号为空或重复：{ident}")
            result[ident] = item
        return result

    node_index = index(nodes, "器件")
    conn_index = index(connections, "连线")
    mode_index = index(modes, "模式")
    for node in nodes:
        ports = node.get("params", {}).get("ports")
        if ports is not None and (not isinstance(ports, list) or not ports or
                                  any(not isinstance(p, str) or not p.strip() for p in ports) or
                                  len(ports) != len(set(ports))):
            raise HTTPException(422, detail=f"器件 {node['id']} 的声明端口必须非空且不重复")
    for conn in connections:
        for end in ("source", "target"):
            node = node_index.get(conn.get(end))
            if node is None:
                raise HTTPException(422, detail=f"连线 {conn['id']} 引用了不存在的器件")
            ports = node.get("params", {}).get("ports")
            pin = conn.get(f"{end}_pin", TopologyConnection.model_fields[f"{end}_pin"].default)
            if ports is not None and pin not in ports:
                raise HTTPException(422, detail=f"连线 {conn['id']} 的 {end} 器件 {node['id']} 引用了未声明的端口 {pin}")
    for node in nodes:
        params = node.get('params') or {}
        if node.get('type') != 'probe' or params.get('rf_path_selection') is None:
            continue
        declaration = params['rf_path_selection']
        try:
            ids = declaration.get('connection_ids') if isinstance(declaration, dict) else None
            if not isinstance(ids, list) or not ids or any(
                    not isinstance(ident, str) or ident not in conn_index for ident in ids):
                raise ValueError('显式路径连接缺失或不存在')
            mappings = declaration.get('switch_mappings')
            if not isinstance(mappings, list) or any(not isinstance(item, dict) or
                    not isinstance(item.get('node_id'), str) or
                    not isinstance(item.get('path_name'), str) for item in mappings):
                raise ValueError('显式路径开关映射结构无效')
            selected = [conn_index[ident] for ident in ids]
            if selected[-1].get('target') != node['id']:
                raise ValueError('显式路径终端不属于此探头')
            # 只解释本声明选中的子图；其他模式分支不影响保存结构校验。
            resolve_saved_rf_path(nodes, selected, ids[-1], check_internal_paths=False)
        except ValueError as exc:
            raise HTTPException(422, detail=f"探头 {node['id']} 的显式路径无效：{exc}") from exc
    for mode in mode_index.values():
        # 与 TopologyService.resolve_paths 的实际消费一致：空活动列表会回退到连线自身的模式声明。
        effective_ids = mode.get("active_connections", []) or [
            conn['id'] for conn in connections if mode['id'] in conn.get('modes', [])
        ]
        for ident in effective_ids:
            conn = conn_index.get(ident)
            if conn is None:
                raise HTTPException(422, detail=f"模式 {mode['id']} 引用了不存在的连线")
            if mode['id'] != 'calibration' and any(
                node_index[conn[end]].get('params', {}).get('connection_scope') == 'calibration'
                for end in ('source', 'target')
            ):
                raise HTTPException(422, detail="校准器件不能加入正常测试模式")


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


def _assert_deletable(db: Session, topology_ids) -> None:
    try:
        assert_route_topologies_deletable(db,topology_ids)
    except RouteApplicationConflict as exc:
        raise HTTPException(409,detail=str(exc)) from exc


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
    raw_body: dict = Depends(_raw_topology_body),
    db: Session = Depends(get_db)
):
    """Create a new switch topology in the current lab's chamber"""
    chamber = _resolve_scope(db, request.lab_profile_id)
    _assert_chamber_consistent(request.chamber_id, chamber.id)

    _validate_nominal(raw_body.get('nodes', []), raw_body.get('connections', []))

    typed = request.model_dump(exclude_unset=True)
    nodes_data = preserve_graph_rows(raw_body.get('nodes', []), typed.get('nodes', []))
    connections_data = preserve_connection_rows(raw_body.get('connections', []), typed.get('connections', []), [], {})
    modes_data = preserve_graph_rows(raw_body.get('operating_modes', []), typed.get('operating_modes', []))
    # 校验最终待存图，不用显示默认端口替代显式路径必须保存的端口声明。
    _validate_structure(nodes_data, connections_data, modes_data)
    _validate_ports(nodes_data, connections_data)
    _validate_internal_paths(nodes_data, connections_data, modes_data)

    # Define default if this is marked as default —— 只在本暗室范围内让位，
    # 不许从 lab A 顺手改掉 chamber B 的默认行（P1-57 跨暗室写点）。
    if request.is_default:
        db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == request.switch_category_id,
            SwitchTopology.chamber_id == chamber.id,
            SwitchTopology.is_default == True
        ).update({"is_default": False})

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
            "已有校准采用历史的拓扑拒绝替换（409），保留原图和历史。"
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
    _validate_structure(topo_data.get('nodes', []), topo_data.get('connections', []),
                        topo_data.get('operating_modes', []))
    _validate_nominal(topo_data.get('nodes', []), topo_data.get('connections', []))
    # 模板不补默认；只规范化此次新说明的空白来源。
    topo_data = deepcopy(topo_data)
    topo_data['nodes'] = preserve_graph_rows(topo_data.get('nodes', []), topo_data.get('nodes', []))
    for edge in topo_data.get('connections', []):
        if 'nominal_metadata' in edge:
            edge['nominal_metadata'] = normalize_nominal_metadata(edge['nominal_metadata'])
    _validate_structure(topo_data.get('nodes', []), topo_data.get('connections', []),
                        topo_data.get('operating_modes', []))
    _validate_ports(topo_data.get('nodes', []), topo_data.get('connections', []),
                    allow_legacy_missing=True)
    _validate_internal_paths(topo_data.get('nodes', []), topo_data.get('connections', []),
                             topo_data.get('operating_modes', []), allow_legacy_missing=True)

    replaced_ids=[]
    if replace_existing:
        # 只删本 (switch, 派生暗室) 的行 —— 别的暗室的行一根手指都不碰
        existing=db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == switch_category_id,
            SwitchTopology.chamber_id == chamber.id,
        )
        replaced_ids=[row.id for row in existing.all()]
        _assert_deletable(db,replaced_ids)

    try:
        if replace_existing:
            existing.delete()
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
    except IntegrityError:
        db.rollback()
        # 预检后可能有另一会话确认采用；只据已提交的相关依赖转409。
        if replace_existing:
            _assert_deletable(db,replaced_ids)
        raise
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
    raw_body: dict = Depends(_raw_topology_body),
    db: Session = Depends(get_db)
):
    """Update an existing switch topology (scoped to the current lab's chamber)"""
    chamber = _resolve_scope(db, lab_profile_id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

    update_data = request.model_dump(exclude_unset=True)
    if any(key in update_data and update_data[key] is None
           for key in ('nodes', 'connections', 'operating_modes')):
        raise HTTPException(422, detail='器件、连线、模式必须是列表，不能置空')
    _validate_nominal(raw_body.get('nodes', topology.nodes), raw_body.get('connections', topology.connections),
                      previous_nodes=topology.nodes, previous_connections=topology.connections)
    declarations = update_data.pop('connection_numeric_declarations', {})
    _validate_numeric_declarations(declarations, raw_body.get('connections', []))

    for key in ('nodes', 'operating_modes'):
        if key in update_data:
            update_data[key] = preserve_graph_rows(raw_body[key], update_data[key], getattr(topology, key))
    if 'connections' in update_data:
        update_data['connections'] = preserve_connection_rows(raw_body['connections'], update_data['connections'],
                                                              topology.connections, declarations)

    # 保形后再校验最终候选；所有校验均早于默认位让位和 ORM 赋值。
    nodes_data = update_data.get('nodes', topology.nodes)
    connections_data = update_data.get('connections', topology.connections)
    _validate_structure(nodes_data, connections_data,
                        update_data.get('operating_modes', topology.operating_modes))
    _validate_ports(nodes_data, connections_data, previous_nodes=topology.nodes,
                    previous_connections=topology.connections)
    _validate_internal_paths(nodes_data, connections_data,
        update_data.get('operating_modes', topology.operating_modes), previous_nodes=topology.nodes,
        previous_connections=topology.connections, previous_modes=topology.operating_modes)

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

    if request.is_default and not topology.is_default:
        # 默认位让位只在本暗室内 —— 不从 lab A 顺手改 chamber B 的行
        db.query(SwitchTopology).filter(
            SwitchTopology.switch_category_id == topology.switch_category_id,
            SwitchTopology.chamber_id == chamber.id,
            SwitchTopology.is_default == True
        ).update({"is_default": False})

    for key, value in update_data.items():
        setattr(topology, key, value)
        if key in ('nodes', 'connections', 'operating_modes'):
            # ORM的Python相等会把 true→1 当成未变化；JSON写入必须保留类型修正。
            flag_modified(topology, key)

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
    """删除本lab暗室内拓扑；已有校准采用历史时409，保留测量追溯。"""
    chamber = _resolve_scope(db, lab_profile_id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

    topology_ids=[topology.id]
    _assert_deletable(db,topology_ids)
    try:
        db.delete(topology)
        db.commit()
    except IntegrityError:
        db.rollback()
        _assert_deletable(db,topology_ids)
        raise
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
        
    try:
        paths = svc.resolve_paths(mode)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    
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
        
    try:
        matrix = svc.get_calibration_matrix(mode)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
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
