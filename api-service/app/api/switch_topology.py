"""
Switch Topology API endpoints

CRUD operations for RF Switch Matrix hardware topology configurations,
and advanced endpoints for path resolution and calibration matrix.
"""
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query, Request
from copy import deepcopy
from datetime import datetime
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy import cast, Text
import sqlite3
from typing import Optional, List
from uuid import UUID
import logging

from app.db.database import get_db
from app.models.switch_topology import SwitchTopology
from app.schemas.switch_topology import (
    SwitchTopologyCreate,
    SwitchTopologyCopy,
    SwitchTopologyUpdate,
    SwitchTopologyResponse,
    SwitchTopologyListResponse,
    SignalPathResponse,
    CalibrationMatrixResponse,
    TopologyConnection,
    TopologyRestoreRequest, TopologyRevisionDetail,
    TopologyRevisionList, TopologyRestorePreview,
)
from app.services.topology_service import TopologyService
from app.schemas.topology_nominal import (
    MISSING, CONNECTION_NUMERIC_FIELDS, same_json, validate_nominal_write,
    preserve_graph_rows, normalize_nominal_metadata, validate_number,
)
from app.services.declared_rf_routes import resolve_saved_rf_path
from app.schemas.topology_ports import validate_port_write
from app.schemas.topology_internal_paths import validate_internal_path_write
from app.schemas.topology_loss_ownership import validate_loss_owner_write
from app.services.chamber_resolution import resolve_current_chamber
from app.services.calibration.route_calibration import assert_route_topologies_deletable, RouteApplicationConflict
from app.schemas.topology_conversion import TopologyConversionRequest, TopologyConversionPreview
from app.services.topology_conversion import (
    GRAPH_FIELDS, build_conversion, conversion_source_digest, conversion_differences, conversion_warnings,
)
from app.services import execution_exclusion_guard
from app.services.topology_revisions import (
    lock_chamber, cas_revision, add_revision, assert_revision_deletable,
    demote_default_peers, topology_write,
    RESTORABLE, raw_snapshot, restore_candidate, field_differences,
)
from app.models.switch_topology_revision import SwitchTopologyRevision

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
            if key == 'cable_loss_db' and (key in declared or not (equal_raw or equal_display)):
                try:
                    validate_number(value, key=key, nonnegative=True)
                except ValueError as exc:
                    raise HTTPException(422, detail=str(exc)) from exc
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


def _validate_loss_owners(nodes, connections, modes, **kwargs):
    try:
        validate_loss_owner_write(nodes, connections, modes, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


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
    topology = db.query(SwitchTopology).populate_existing().filter(SwitchTopology.id == topology_id).first()
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
@topology_write
def create_switch_topology(
    request: SwitchTopologyCreate,
    raw_body: dict = Depends(_raw_topology_body),
    db: Session = Depends(get_db)
):
    """Create a new switch topology in the current lab's chamber"""
    chamber = _resolve_scope(db, request.lab_profile_id)
    lock_chamber(db, chamber.id)
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
    _validate_loss_owners(nodes_data, connections_data, modes_data)

    topology = SwitchTopology(
        revision=1,
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
    db.flush()
    SwitchTopologyResponse.model_validate(topology).model_dump(mode='json')
    peers = demote_default_peers(db, topology) if request.is_default is True else []
    add_revision(db, topology, 'create')
    db.flush()
    for written in [topology, *peers]:
        SwitchTopologyResponse.model_validate(written).model_dump(mode='json')
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
@topology_write
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
            "已有同一 (switch_category_id, 派生暗室) 的行时拒绝覆盖（409）。"
            "导入只追加inactive、非default草稿，不清旧默认位，不自动用于正式执行。"
        ),
    ),
    db: Session = Depends(get_db),
):
    """Import a topology structure from a named template file.

    导入目标暗室 = lab_profile_id 派生（不再收裸 chamber_id 当真值）。
    解析顺序是硬约束：lab → chamber → 模板全部成功之后核对已有行。
    只追加inactive、非default草稿；replace遇已有行409，不删除原图或历史。

    Templates are loaded dynamically from
    ``api-service/scripts/dev-fixtures/topology-templates/<template_id>.py``
    by ``importlib`` — commercial deploys that don't ship dev-fixtures will
    see an empty registry and get 404.
    """
    chamber = _resolve_scope(db, lab_profile_id)
    lock_chamber(db, chamber.id)
    _assert_chamber_consistent(chamber_id, chamber.id)

    generate = _load_template(template_id)
    topo_data = generate()
    # 模板沿4a保留typed旧数值字符串；新增非法量值必须早于替换旧行/默认位写入。
    try:
        for edge in topo_data.get('connections', []):
            if 'cable_loss_db' in edge:
                value = edge['cable_loss_db']
                validate_number(float(value) if isinstance(value, str) else value,
                                key='cable_loss_db', nonnegative=True)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
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

    _validate_loss_owners(topo_data.get('nodes', []), topo_data.get('connections', []),
                          topo_data.get('operating_modes', []))
    if replace_existing:
        existing = db.query(SwitchTopology.id).filter(
            SwitchTopology.switch_category_id == switch_category_id,
            SwitchTopology.chamber_id == chamber.id,
        )
        if existing.first() is not None:
            raise HTTPException(409, detail='已有拓扑不能覆盖导入；请复制已保存版本，原图和历史保持不变')

    topo_data['is_active'] = False
    topo_data['is_default'] = False
    try:
        topology = SwitchTopology(
            revision=1,
            switch_category_id=switch_category_id,
            chamber_id=chamber.id,
            **topo_data
        )
        topology.update_statistics()

        db.add(topology)
        db.flush()
        SwitchTopologyResponse.model_validate(topology).model_dump(mode='json')
        add_revision(db, topology, 'import')
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(topology)
    logger.info(
        "Imported topology from template '%s' for switch category %s into chamber %s (replace=%s)",
        template_id, switch_category_id, chamber.id, replace_existing,
    )
    return topology


@router.post('/{topology_id}/copy', response_model=SwitchTopologyResponse, status_code=201)
@topology_write
def copy_switch_topology(topology_id: UUID, request: SwitchTopologyCopy,
                         lab_profile_id: UUID = Query(...), db: Session = Depends(get_db)):
    """复制已保存的原始图为inactive、非default新UUID；不复制采用记录/证书。

    仅副本连线已有calibrated_loss_db/calibrated_phase_deg置null，缺键保留；
    原图不改，不改变正式执行选择。未来显式激活仍受既有旧证书兼容政策约束。
    """
    chamber = _resolve_scope(db, lab_profile_id)
    lock_chamber(db, chamber.id)
    source = _load_scoped_topology(db, topology_id, chamber.id)
    graph = {key: deepcopy(getattr(source, key)) for key in GRAPH_FIELDS}
    # 旧JSON形态损坏也须422；先拒绝，避免遍历/统计先于响应校验抛500。
    if any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
           for rows in graph.values()):
        raise HTTPException(422, detail='源拓扑的器件、连线、模式必须为对象列表')
    for edge in graph['connections']:
        for key in ('calibrated_loss_db', 'calibrated_phase_deg'):
            if key in edge:
                edge[key] = None
    copied = SwitchTopology(switch_category_id=source.switch_category_id, chamber_id=source.chamber_id,
        name=request.name, description=source.description, version=source.version,
        site_name=source.site_name, system_model=source.system_model,
        installed_date=source.installed_date, installed_by=source.installed_by,
        revision=1, is_active=False, is_default=False, **graph)
    try:
        db.add(copied)
        db.flush()
        # 先校验必填图字段，再计算依赖节点id的统计；失败仍在提交前回滚。
        SwitchTopologyResponse.model_validate(copied).model_dump(mode='json')
        copied.update_statistics()
        db.flush()
        add_revision(db, copied, 'copy')
        db.flush()
        SwitchTopologyResponse.model_validate(copied).model_dump(mode='json')
        db.commit()
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(422, detail='源拓扑无法序列化，请先核对已保存图') from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(copied)
    return copied


@router.get("/{topology_id}", response_model=SwitchTopologyResponse)
def get_switch_topology(
    topology_id: UUID,
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """Get a specific switch topology by ID (scoped to the current lab's chamber)"""
    chamber = _resolve_scope(db, lab_profile_id)
    return _load_scoped_topology(db, topology_id, chamber.id)


def _history_revision(db, topology_id, revision):
    row = db.query(SwitchTopologyRevision).filter(
        SwitchTopologyRevision.topology_id == topology_id,
        SwitchTopologyRevision.revision == revision).first()
    if row is None:
        raise HTTPException(404, detail='未找到该拓扑修订')
    return row


@router.get('/{topology_id}/revisions', response_model=TopologyRevisionList)
def list_topology_revisions(topology_id: UUID, lab_profile_id: UUID = Query(...),
                            skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                            db: Session = Depends(get_db)):
    chamber = _resolve_scope(db, lab_profile_id)
    _load_scoped_topology(db, topology_id, chamber.id)
    query = db.query(SwitchTopologyRevision).filter(SwitchTopologyRevision.topology_id == topology_id)
    return {'total': query.count(), 'items': query.order_by(
        SwitchTopologyRevision.revision.desc()).offset(skip).limit(limit).all()}


@router.get('/{topology_id}/revisions/{revision}', response_model=TopologyRevisionDetail,
            response_model_exclude_unset=True)
def get_topology_revision(topology_id: UUID, revision: int = PathParam(..., ge=0),
                          lab_profile_id: UUID = Query(...), db: Session = Depends(get_db)):
    chamber = _resolve_scope(db, lab_profile_id)
    _load_scoped_topology(db, topology_id, chamber.id)
    return _history_revision(db, topology_id, revision)


def _restore_selection(db, topology_id, chamber_id, request):
    current = _load_scoped_topology(db, topology_id, chamber_id)
    if current.revision != request.expected_revision:
        raise HTTPException(409, detail='服务器拓扑已变化，请刷新核对；草稿未覆盖')
    history = _history_revision(db, topology_id, request.revision)
    candidate = restore_candidate(history.snapshot)
    nodes, edges, modes = (candidate[key] for key in ('nodes', 'connections', 'operating_modes'))
    # 验证模型形态但丢弃typed结果；不将默认图或日期格式灌回raw快照。
    try:
        SwitchTopologyUpdate.model_validate(dict(expected_revision=request.expected_revision, **candidate))
        if candidate['installed_date'] is not None:
            if not isinstance(candidate['installed_date'], str):
                raise ValueError('历史日期必须为ISO字符串')
            datetime.fromisoformat(candidate['installed_date'])
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, detail='历史名称、安装信息或图字段形态无效') from exc
    _validate_structure(nodes, edges, modes)
    _validate_nominal(nodes, edges, previous_nodes=current.nodes, previous_connections=current.connections)
    old_edges = {edge['id']: edge for edge in current.connections}
    for edge in edges:
        previous = old_edges.get(edge['id'], {})
        if 'cable_loss_db' in edge and ('cable_loss_db' not in previous or
                not same_json(edge['cable_loss_db'], previous['cable_loss_db'])):
            try:
                validate_number(edge['cable_loss_db'], key='cable_loss_db', nonnegative=True)
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
    _validate_ports(nodes, edges, previous_nodes=current.nodes, previous_connections=current.connections)
    _validate_internal_paths(nodes, edges, modes, previous_nodes=current.nodes,
        previous_connections=current.connections, previous_modes=current.operating_modes)
    _validate_loss_owners(nodes, edges, modes, previous_connections=current.connections)
    statistics = SwitchTopology(nodes=nodes, connections=edges, operating_modes=modes)
    statistics.update_statistics()
    # 与写入口同样验证最终响应可序列化，但绝不以该typed结果替代raw。
    response = {column.name: getattr(current, column.name) for column in SwitchTopology.__table__.columns}
    response.update(candidate)
    response.update({key: getattr(statistics, key) for key in
                    ('total_nodes', 'total_connections', 'total_probes', 'total_channels')})
    SwitchTopologyResponse.model_validate(response).model_dump(mode='json')
    return current, history, candidate, statistics


@router.post('/{topology_id}/restore-preview', response_model=TopologyRestorePreview,
             response_model_exclude_unset=True)
def preview_topology_restore(topology_id: UUID, request: TopologyRestoreRequest,
                            lab_profile_id: UUID = Query(...), db: Session = Depends(get_db)):
    chamber = _resolve_scope(db, lab_profile_id)
    current, history, candidate, _ = _restore_selection(db, topology_id, chamber.id, request)
    return TopologyRestorePreview.model_validate(dict(current_revision=current.revision,
        target_revision=request.revision, snapshot=history.snapshot, candidate=candidate,
        differences=field_differences(raw_snapshot(current), candidate), warnings=[
            '仅恢复接线声明；已存在的内嵌校准值清空，不恢复采用、证书、运行或confirmed资格。',
            '当前暗室、分类、激活、默认及创建信息保持不变；历史原件只读。']))


@router.post('/{topology_id}/restore', response_model=SwitchTopologyResponse)
@topology_write
def restore_topology(topology_id: UUID, request: TopologyRestoreRequest,
                     lab_profile_id: UUID = Query(...), db: Session = Depends(get_db)):
    chamber = _resolve_scope(db, lab_profile_id)
    lock_chamber(db, chamber.id)
    current, _, candidate, statistics = _restore_selection(db, topology_id, chamber.id, request)
    values = deepcopy(candidate)
    if values['installed_date'] is not None:
        values['installed_date'] = datetime.fromisoformat(values['installed_date'])
    values.update({key: getattr(statistics, key) for key in
                  ('total_nodes', 'total_connections', 'total_probes', 'total_channels')})
    cas_revision(db, current, request.expected_revision, values, operation='restore',
                 restored_from_revision=request.revision, force_revision=True)
    db.flush()
    SwitchTopologyResponse.model_validate(current).model_dump(mode='json')
    db.commit()
    db.refresh(current)
    return current


def _conversion_snapshot(db, topology_id, chamber_id):
    # 同一次SELECT取新源与数据库原始JSON文本；不使用identity-map里的旧对象。
    row=db.query(SwitchTopology.id,SwitchTopology.chamber_id,SwitchTopology.switch_category_id,
        SwitchTopology.nodes,SwitchTopology.connections,SwitchTopology.operating_modes,
        cast(SwitchTopology.nodes,Text),cast(SwitchTopology.connections,Text),
        cast(SwitchTopology.operating_modes,Text),SwitchTopology.revision).filter(
            SwitchTopology.id==topology_id,SwitchTopology.chamber_id==chamber_id).one_or_none()
    if row is None:
        raise HTTPException(404,detail='Switch topology not found in current Lab')
    source=dict(zip(('id','chamber_id','switch_category_id'),map(str,row[:3])))
    source.update(dict(zip(GRAPH_FIELDS,deepcopy(row[3:6]))))
    return source,row[6:9],row[9]


def _conversion_candidate(source, changes):
    try:
        candidate=build_conversion(source,changes)
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    nodes,edges,modes=(candidate[key] for key in GRAPH_FIELDS)
    declared_nodes={edit.node_id for edit in changes.nodes if edit.model_fields_set & {
        'target_type','ports','port_directions','port_roles','internal_paths'}}
    repinned={edit.connection_id for edit in changes.connections
              if edit.model_fields_set & {'source_pin','target_pin'}}
    for edge in edges:
        if edge['id'] in repinned or edge['source'] in declared_nodes or edge['target'] in declared_nodes:
            if any(not isinstance(edge.get(key),str) or not edge[key].strip()
                   for key in ('source_pin','target_pin')):
                raise HTTPException(422,detail=f'连线 {edge["id"]} 转换须显式保存两端pin，不推定默认端口')
    # builder只动声明白名单，未动键直接深复制原JSON；不默认化历史opaque或数值。
    _validate_nominal(nodes,edges,previous_nodes=source['nodes'],previous_connections=source['connections'])
    _validate_structure(nodes,edges,modes)
    _validate_ports(nodes,edges,previous_nodes=source['nodes'],previous_connections=source['connections'])
    _validate_internal_paths(nodes,edges,modes,previous_nodes=source['nodes'],
        previous_connections=source['connections'],previous_modes=source['operating_modes'])
    _validate_loss_owners(nodes,edges,modes,previous_connections=source['connections'])
    return candidate


@router.post('/{topology_id}/conversion-preview',response_model=TopologyConversionPreview,
             response_model_exclude_unset=True)
def preview_topology_conversion(topology_id: UUID, request: TopologyConversionRequest,
        lab_profile_id: UUID = Query(...), db: Session = Depends(get_db)):
    """只读预览原保存声明；不改图、默认位、历史或HAL。"""
    chamber=_resolve_scope(db,lab_profile_id)
    source,_,revision=_conversion_snapshot(db,topology_id,chamber.id)
    candidate=_conversion_candidate(source,request)
    return dict(revision=revision,source_digest=conversion_source_digest(source),changes=request.model_dump(exclude_unset=True),
                candidate=candidate,differences=conversion_differences(source,candidate),
                warnings=conversion_warnings(source,candidate))


def _commit_conversion(db,topology_id,chamber,conversion,expected_revision):
    if execution_exclusion_guard.active_unsafe_diagnostic():
        raise HTTPException(409,detail='仪器工作正在进行，暂不能确认转换')
    source,raw,revision=_conversion_snapshot(db,topology_id,chamber.id)
    topology=_load_scoped_topology(db,topology_id,chamber.id)
    if revision != expected_revision:
        raise HTTPException(409,detail='服务器拓扑已变化，请刷新核对；草稿未覆盖')
    if conversion_source_digest(source)!=conversion.source_digest:
        db.rollback()
        raise HTTPException(409,detail='原图已变化，请重新预览')
    candidate=_conversion_candidate(source,conversion.changes)
    # 只用未挂载Session的临时对象复用原统计函数；禁止旧ORM对象dirty绕过CAS。
    statistics=SwitchTopology(**candidate)
    statistics.update_statistics()
    conditions=(
        cast(SwitchTopology.nodes,Text)==raw[0],cast(SwitchTopology.connections,Text)==raw[1],
        cast(SwitchTopology.operating_modes,Text)==raw[2],
    )
    try:
        cas_revision(db,topology,expected_revision,dict(candidate,**{key:getattr(statistics,key) for key in
            ('total_nodes','total_connections','total_probes','total_channels')}),
            operation='conversion',raw_conditions=conditions)
        db.flush()
        SwitchTopologyResponse.model_validate(topology).model_dump(mode='json')
        db.commit()
    except OperationalError as exc:
        db.rollback()
        code=getattr(exc.orig,'sqlite_errorcode',None)
        if isinstance(code,int) and code & 0xff in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):
            raise HTTPException(409,detail='原图正在被其他会话修改，请重新预览') from exc
        raise
    db.expire_all()
    return _load_scoped_topology(db,topology_id,chamber.id)


@router.patch("/{topology_id}", response_model=SwitchTopologyResponse)
@topology_write
def update_switch_topology(
    topology_id: UUID,
    request: SwitchTopologyUpdate,
    lab_profile_id: UUID = Query(...),
    raw_body: dict = Depends(_raw_topology_body),
    db: Session = Depends(get_db)
):
    """Update an existing switch topology (scoped to the current lab's chamber)"""
    chamber = _resolve_scope(db, lab_profile_id)
    lock_chamber(db, chamber.id)
    if 'conversion' in raw_body:
        if set(raw_body)!={'conversion','expected_revision'} or request.conversion is None:
            raise HTTPException(422,detail='conversion不能与其他更新字段同时提交，也不能置空')
        return _commit_conversion(db,topology_id,chamber,request.conversion,request.expected_revision)
    topology = _load_scoped_topology(db, topology_id, chamber.id)
    if topology.revision != request.expected_revision:
        raise HTTPException(409,detail='服务器拓扑已变化，请刷新核对；草稿未覆盖')

    update_data = request.model_dump(exclude_unset=True)
    update_data.pop('expected_revision')
    update_data.pop('conversion', None)
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
    _validate_loss_owners(nodes_data, connections_data,
        update_data.get('operating_modes', topology.operating_modes), previous_connections=topology.connections)

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

    update_data.pop('chamber_id', None)
    name_only = set(update_data) == {'name'}
    if any(k in update_data for k in ["nodes", "connections"]):
        statistics = SwitchTopology(nodes=nodes_data, connections=connections_data,
            operating_modes=update_data.get('operating_modes', topology.operating_modes))
        statistics.update_statistics()
        update_data.update({key:getattr(statistics,key) for key in
            ('total_nodes','total_connections','total_probes','total_channels')})
    peers = demote_default_peers(db, topology) if (
        'is_default' in request.model_fields_set and request.is_default is True and not topology.is_default) else []
    cas_revision(db, topology, request.expected_revision, update_data, preserve_updated_at=name_only)
    db.flush()
    for written in [topology, *peers]:
        SwitchTopologyResponse.model_validate(written).model_dump(mode='json')
    db.commit()
    db.refresh(topology)
    logger.info(f"Updated switch topology: {topology_id}")
    return topology


@router.delete("/{topology_id}", status_code=204)
@topology_write
def delete_switch_topology(
    topology_id: UUID,
    lab_profile_id: UUID = Query(...),
    db: Session = Depends(get_db)
):
    """删除本lab暗室内拓扑；已有采用或修订历史时409，保留追溯。"""
    chamber = _resolve_scope(db, lab_profile_id)
    lock_chamber(db, chamber.id)
    topology = _load_scoped_topology(db, topology_id, chamber.id)

    topology_ids=[topology.id]
    _assert_deletable(db,topology_ids)
    assert_revision_deletable(db,topology_ids)
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
