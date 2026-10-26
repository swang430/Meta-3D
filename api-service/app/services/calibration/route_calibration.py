"""保存完整路径查询及采用重核；与正式声明解析同源，不访问仪器。"""
import copy
import hashlib
import json
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.schemas.route_calibration import (RouteSelection, RouteEligibility, RouteApplicationPreview,
    ConfirmRouteApplication, RouteApplicationRecord)
from app.models.route_calibration import RouteCalibrationApplication, RouteCalibrationSelection
from app.services.calibration.rf_chain_resolver import resolve_declared_calibration_ce_port


class RouteScopeConflict(ValueError):
    """保存图不属于当前实验室暗室。"""


def list_route_selections(db, lab_id: UUID, topology_id: UUID, operating_mode: str) -> list[RouteSelection]:
    return _route_selections(db,lab_id,topology_id,operating_mode)


def list_individual_route_selections(db,lab_id: UUID,topology_id: UUID,operating_mode: str) -> list[RouteSelection]:
    """逐条保存候选，不声明同时兼容；同CE互斥批仍由build_batch_plan核验。"""
    return _route_selections(db,lab_id,topology_id,operating_mode,individual=True)


def resolve_explicit_route_selection(db,lab_id,topology_id,mode,terminal_connection_id,connection_ids):
    """仅解析指定保存终端；允许批串行复用CE，不放宽正式集合门。"""
    routes=_route_selections(db,lab_id,topology_id,mode,terminal_connection_id=terminal_connection_id)
    if len(routes)!=1 or routes[0].connection_ids!=list(connection_ids):
        raise ValueError('所选连接与当前保存路径声明不一致')
    return routes[0]


def route_switch_steps(db,topology,path_nodes,path_edges,lab=None):
    """从保存仪器连接读取映射，返回零I/O快照，不授予自动切换资格。"""
    from app.models.instrument import InstrumentCategory,InstrumentConnection
    from app.services.declared_rf_routes import selected_switch_mappings
    declared=(path_nodes[-1].get('params') or {}).get('rf_path_selection')
    switches = [node for node in path_nodes[1:-1] if node.get('type') == 'switch_slot']
    if switches and (not declared or not declared['switch_mappings']):
        raise ValueError('开关路径必须保存原开关映射声明')
    if not switches:
        return []
    category=db.get(InstrumentCategory,topology.switch_category_id)
    connection=db.query(InstrumentConnection).filter_by(category_id=topology.switch_category_id).one_or_none()
    if (category is None or not category.is_active or category.category_key!='rfSwitch'
            or category.selected_model_id is None or connection is None):
        raise ValueError('保存路径缺少活动开关绑定连接')
    if lab is not None:
        bindings=[b for b in lab.instrument_bindings or [] if str(b.get('category_id'))==str(category.id)]
        if (len(bindings)!=1 or str(bindings[0].get('instrument_model_id'))!=str(category.selected_model_id)
                or bindings[0].get('connection_endpoint')!=connection.endpoint
                or bindings[0].get('driver_mode')!=category.driver_mode):
            raise ValueError('开关当前资源与实验室绑定不一致')
    steps=selected_switch_mappings(path_nodes,path_edges,(connection.connection_params or {}).get('port_maps'),
        category_id=category.id)
    return [dict(**step,connection_id=str(connection.id),endpoint=connection.endpoint,
        driver_mode=category.driver_mode,instrument_model_id=str(category.selected_model_id)) for step in steps]


def _route_selections(db, lab_id: UUID, topology_id: UUID, operating_mode: str, *, terminal_connection_id=None,individual=False) -> list[RouteSelection]:
    lab = db.get(LabProfile, lab_id)
    topology = db.get(SwitchTopology, topology_id)
    if lab is None or topology is None:
        raise LookupError('实验室或拓扑不存在')
    if topology.chamber_id != lab.chamber_config_id:
        raise RouteScopeConflict('拓扑不属于当前实验室绑定的暗室')
    if not lab.is_active or not topology.is_active:
        raise ValueError('实验室或拓扑已停用')

    def index(items, label):
        result = {}
        for item in items or []:
            ident = item.get('id')
            if not isinstance(ident, str) or not ident.strip() or ident in result:
                raise ValueError(f'{label}编号为空或重复')
            result[ident] = item
        return result

    nodes = index(topology.nodes, '器件')
    connections = index(topology.connections, '连接')
    modes = index(topology.operating_modes, '模式')
    if operating_mode not in modes or operating_mode == 'calibration':
        raise ValueError('请选择已保存的正常测试模式')

    def effective(mode):
        config = modes.get(mode)
        if config is None:
            return []
        ids = config.get('active_connections') or [c['id'] for c in connections.values() if mode in c.get('modes', [])]
        if len(ids) != len(set(ids)) or any(ident not in connections for ident in ids):
            raise ValueError('模式的连接引用为空、重复或不存在')
        selected = [connections[ident] for ident in ids]
        if any(c.get(end) not in nodes for c in selected for end in ('source','target')):
            raise ValueError('模式连接引用了不存在的器件')
        return selected

    active = effective(operating_mode)
    calibration = effective('calibration')
    incoming, outgoing = {}, {}
    for c in active:
        for end in ('source', 'target'):
            n = nodes[c[end]]
            if (n.get('params', {}).get('connection_scope') == 'calibration' or
                n.get('type') in ('reference_antenna','receive_cable','signal_analyzer','air_path')):
                raise ValueError('校准参考接线不能作为正常测试通路')
        incoming.setdefault(c['target'], []).append(c)
        outgoing.setdefault(c['source'], []).append(c)

    selections = []
    selected_steps=[]
    for probe in nodes.values():
        if probe.get('type') != 'probe' or probe['id'] not in incoming:
            continue
        terminals=incoming[probe['id']]
        if terminal_connection_id is not None:
            terminals=[e for e in terminals if e['id']==terminal_connection_id]
            if not terminals:
                continue
        declaration=(probe.get('params') or {}).get('rf_path_selection')
        if declaration is not None:
            ids=declaration.get('connection_ids') if isinstance(declaration,dict) else None
            if not isinstance(ids,list) or not ids:
                raise ValueError('保存显式路径缺少连接')
            terminals=[e for e in terminals if e['id']==ids[-1]]
        if len(terminals)!=1:
            raise ValueError('探头终端未保存唯一显式路径')
        from app.services.declared_rf_routes import resolve_saved_rf_path
        route_nodes,route_edges=resolve_saved_rf_path(nodes,active,terminals[0]['id'])
        switch_steps=route_switch_steps(db,topology,route_nodes,route_edges,lab)
        from app.services.declared_rf_routes import validate_simultaneous_switch_mappings
        validate_simultaneous_switch_mappings(switch_steps)
        selected_steps.extend(switch_steps)
        visited={n['id'] for n in route_nodes}
        ce_port = resolve_declared_calibration_ce_port(route_nodes, route_edges)
        params = probe.get('params', {})
        probe_id, pol = params.get('probe_id'), params.get('polarization')
        if type(probe_id) is not int or probe_id < 0 or pol not in ('V','H'):
            raise ValueError('探头必须明确声明编号与V/H极化')

        # 只随所选探头冻结校准模式中可达的参考接线，不吸入其它正常测试器件。
        refs, ref_edges, frontier = [], [], [probe['id']]
        seen = {probe['id']}
        while frontier:
            parent_id = frontier.pop(0)
            next_edges = [edge for edge in calibration if edge['source'] == parent_id]
            if len(next_edges) > 1:
                raise ValueError('参考测量段存在多个可达分支，不能确定唯一固定接线')
            for edge in next_edges:
                if parent_id != probe['id']:
                    parent = nodes[parent_id]
                    previous = next(e for e in ref_edges if e['target'] == parent_id)
                    # 无字段的唯一虚拟参考模型是原模型边界，不扩张物理双端白名单。
                    params = parent.get('params') or {}
                    virtual_legacy = (parent.get('type') in ('air_path', 'reference_antenna') and
                        'internal_paths' not in params and
                        ('ports' not in params or isinstance(params['ports'], list) and len(params['ports']) <= 2) and
                        sum(e['target'] == parent_id for e in calibration) == 1)
                    if not virtual_legacy:
                        from app.schemas.topology_internal_paths import validate_internal_traversals
                        validate_internal_traversals([probe, parent, nodes[edge['target']]],
                            [previous, edge], active_connections=calibration)
                    if parent.get('type') == 'switch_slot':
                        raise ValueError('参考段开关缺少原探头路径映射，不能推定选通')
                target = nodes[edge['target']]
                if target['id'] in visited or target['id'] in seen:
                    raise ValueError('参考测量段存在回路或回接正常测试通路')
                if not (target.get('params', {}).get('connection_scope') == 'calibration' or
                        target.get('type') in ('reference_antenna','receive_cable','signal_analyzer','air_path')):
                    raise ValueError('参考测量段接入了未声明为校准接线的器件')
                ref_edges.append(edge)
                seen.add(target['id']); refs.append(target); frontier.append(target['id'])

        def snapshot(values):
            return copy.deepcopy(values)

        identity_nodes = [{k:n[k] for k in ('id','type')} | {'params':{
            k:v for k,v in n.get('params', {}).items() if k not in ('visible_modes','description','notes','nominal_metadata')
        }} for n in [*route_nodes,*refs]]
        port_rows = [dict(connection_id=e['id'],source=e['source'],source_pin=e.get('source_pin','out'),
                         target=e['target'],target_pin=e.get('target_pin','in')) for e in route_edges]
        identity = dict(lab_profile_id=str(lab.id),topology_id=str(topology.id),mode=operating_mode,
            ce_port=ce_port,nodes=identity_nodes,ports=port_rows,
            calibration_connections=[{k:v for k,v in edge.items() if k not in ('nominal_metadata','loss_owner_connection_id')} for edge in ref_edges])
        if switch_steps:
            identity['switch_steps']=switch_steps
        digest = hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        antennas = [n for n in refs if n.get('type') == 'reference_antenna']
        analyzers = [n for n in refs if n.get('type') == 'signal_analyzer']
        if len(antennas) > 1 or len(analyzers) > 1:
            raise ValueError('所选通路的参考天线或分析仪不唯一')
        from app.services.declared_rf_routes import switch_execution_identity
        selections.append(RouteSelection(lab_profile_id=lab.id,chamber_id=lab.chamber_config_id,
            topology_id=topology.id,operating_mode=operating_mode,chain_id=route_edges[-1]['id'],ce_port=ce_port,
            probe_id=probe_id,polarization=pol,node_ids=[n['id'] for n in route_nodes],
            connection_ids=[e['id'] for e in route_edges],ports=port_rows,nodes=snapshot(route_nodes),
            connections=snapshot(route_edges),calibration_node_ids=[n['id'] for n in refs],
            calibration_connection_ids=[e['id'] for e in ref_edges],calibration_nodes=snapshot(refs),
            calibration_connections=snapshot(ref_edges),reference_antenna_id=antennas[0]['id'] if antennas else None,
            analyzer_category_id=analyzers[0].get('params',{}).get('instrument_category_id') if analyzers else None,
            route_digest=digest,switch_execution_identity=switch_execution_identity(switch_steps)))
    if len({(r.probe_id,r.polarization) for r in selections}) != len(selections):
        raise ValueError('探头编号及极化存在重复通路')
    from app.hal.propsim_f64 import RealPropsimF64Driver
    physical_outputs = [RealPropsimF64Driver._ce_port_to_output_num(r.ce_port) for r in selections]
    if terminal_connection_id is None and not individual and len(physical_outputs) != len(set(physical_outputs)):
        raise ValueError('同一F64输出口存在多个可达通路，不能确定单条固定接线')
    if terminal_connection_id is None and not individual:
        from app.services.declared_rf_routes import validate_simultaneous_switch_mappings
        validate_simultaneous_switch_mappings(selected_steps)
    return sorted(selections,key=lambda r:r.chain_id)


def evaluate_route_application(db, lab_id: UUID, run_id: UUID) -> RouteApplicationPreview:
    """只读采用准备状态；不签认证、不创建应用记录、不补历史或制造截止状态。"""
    from app.models.diagnostic_run import DiagnosticRun
    from app.services.calibration import fixed_route_jobs as jobs
    from app.services.calibration.fixed_route_evidence import check_fixed_route_evidence

    row=db.query(DiagnosticRun).filter_by(id=run_id,lab_profile_id=lab_id,
        target_name=jobs.TARGET,kind='scpi_sequence').one_or_none()
    if row is None:
        raise LookupError('本实验室中没有这条采集记录')
    from app.services.calibration.route_batch_jobs import batch_child_context
    record=jobs.record(row,batch_context=batch_child_context(db,row))
    result=record.result
    selection=None
    warnings=['选用截止时间由确认操作明确填写并校验，不是证书期限']
    blockers=[]
    provenance='unknown'
    measured_value=None
    if result is None:
        blockers.append('incomplete_capture_record')
    else:
        warnings.extend(result.missing_items)
        provenance,blockers=check_fixed_route_evidence(result)
        if result.version==2:
            selection=RouteSelection.model_validate(result.configuration['route_selection'])
        if provenance=='real' and not blockers:
            measured_value=result.net_loss_db
        if selection is not None:
            try:
                current=resolve_explicit_route_selection(db,lab_id,selection.topology_id,selection.operating_mode,
                    selection.chain_id,selection.connection_ids)
                matching=[current]
                if len(matching)!=1 or matching[0].route_digest!=selection.route_digest:
                    blockers.append('route_mismatch')
                elif matching[0].nodes!=selection.nodes or matching[0].calibration_nodes!=selection.calibration_nodes:
                    warnings.append('保存图的显示或其他声明有变化，请复核；未据此要求重新校准')
            except (LookupError,ValueError):
                blockers.append('route_unavailable')
    eligibility=RouteEligibility(eligible_for_adoption=not blockers,blockers=blockers,warnings=warnings,
        acquisition_run_id=run_id,route_digest=selection.route_digest if selection else None,
        method=result.method if result else None,frequency_mhz=result.request.frequency_mhz if result else None,
        measurement_provenance=provenance)
    current=None
    old_value=None
    if selection is not None:
        scope,_=_application_scope(result,selection)
        pointer=db.query(RouteCalibrationSelection).filter_by(**scope).one_or_none()
        if pointer is not None:
            current=pointer.application_id
            saved=db.get(RouteCalibrationApplication,current)
            if saved is not None:
                previous=RouteApplicationRecord.model_validate(saved.record)
                if datetime.fromisoformat(previous.coverage_snapshot['adoption_valid_until'].replace('Z','+00:00'))>datetime.now(timezone.utc):
                    old_value=previous.net_loss_db
                else:
                    warnings.append('当前选择的操作员选用窗口已过期，不作为有效旧量值')
    return RouteApplicationPreview(selection=selection,acquisition_run_id=run_id,
        expected_current_application_id=current,old_value_db=old_value,new_net_loss_db=measured_value,
        delta_db=measured_value-old_value if measured_value is not None and old_value is not None else None,
        eligibility=eligibility)


class RouteApplicationConflict(ValueError):
    """当前选择已改变或幂等键载荷矛盾；不得写入部分确认。"""


def _application_scope(result,selection):
    """身份来自冻结原文，不把拓扑UUID冒充实物序列号，不猜证书期限。"""
    reference=dict(reference_antenna_id=selection.reference_antenna_id,
        identity_description=result.request.reference_antenna,
        position_description=result.request.reference_antenna,polarization=selection.polarization,
        # 保存声明原文，不从自由文本猜序列号，更不把画布节点号当实物身份。
        receive_cable_identity=result.request.receive_cable_source,
        receive_cable_loss_db=result.request.receive_cable_loss_db,
        receive_cable_source=result.request.receive_cable_source,
        analyzer_binding_snapshot=copy.deepcopy(result.configuration.get('analyzer_binding',{})))
    # 数值变化不是参考件换身份，避免通过换线损数值绕过同一选择的CAS。
    identity={key:value for key,value in reference.items() if key!='receive_cable_loss_db'}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    scope=dict(lab_profile_id=selection.lab_profile_id,topology_id=selection.topology_id,
        operating_mode=selection.operating_mode,chain_id=selection.chain_id,
        frequency_mhz=result.request.frequency_mhz,reference_identity_digest=digest)
    return scope,reference


def _replay(db,lab_id,request):
    existing=db.query(RouteCalibrationApplication).filter_by(lab_profile_id=lab_id,
        idempotency_key=request.idempotency_key).one_or_none()
    if existing is None:
        return None
    if existing.request_payload!=request.model_dump(mode='json'):
        raise RouteApplicationConflict('幂等键已用于不同确认载荷')
    return RouteApplicationRecord.model_validate(existing.record)


def confirm_route_application(db,lab_id: UUID,request: ConfirmRouteApplication,actor: str | None):
    """事务内复核后追加记录，以唯一约束和条件UPDATE推进选择；返回(record,created)。"""
    from app.models.diagnostic_run import DiagnosticRun
    from app.services.calibration import fixed_route_jobs as jobs
    try:
        db.expire_all()  # 不使用同Session先前预览的身份映射缓存作为确认真值。
        existing=_replay(db,lab_id,request)
        if existing is not None:
            return existing,False
        row=db.query(DiagnosticRun).filter_by(id=request.acquisition_run_id,lab_profile_id=lab_id,
            target_name=jobs.TARGET,kind='scpi_sequence').with_for_update().one_or_none()
        if row is None:
            raise LookupError('本实验室中没有这条采集记录')
        candidate=evaluate_route_application(db,lab_id,request.acquisition_run_id)
        now=datetime.now(timezone.utc)
        if request.adoption_valid_until<=now:
            raise ValueError('操作员选用截止必须晚于本次确认时间')
        if (not candidate.eligibility.eligible_for_adoption or candidate.selection is None or
            candidate.new_net_loss_db is None or request.route_digest!=candidate.selection.route_digest):
            raise ValueError('采集证据或当前通路不适用于本次采用')
        from app.services.calibration.route_batch_jobs import batch_child_context
        result=jobs.record(row,batch_context=batch_child_context(db,row)).result
        selection=candidate.selection
        scope,reference=_application_scope(result,selection)
        pointer=db.query(RouteCalibrationSelection).filter_by(**scope).one_or_none()
        previous_id=pointer.application_id if pointer else None
        if previous_id!=request.expected_current_application_id:
            raise RouteApplicationConflict('当前选择已变化，请重新预览')
        ident=uuid4()
        record=RouteApplicationRecord(id=ident,predecessor_id=previous_id,acquisition_run_id=row.id,
            selection_snapshot=selection,method=result.method,frequency_mhz=result.request.frequency_mhz,
            coverage_snapshot=dict(frequency_mhz=result.request.frequency_mhz,polarization=selection.polarization,
                reference_identity_digest=scope['reference_identity_digest'],adopted_at=now.isoformat(),
                adoption_valid_until=request.adoption_valid_until.isoformat(),
                validity_source='operator_declared_adoption_window'),reference_snapshot=reference,
            net_loss_db=candidate.new_net_loss_db,adoption_evidence_snapshot=dict(acquisition_run_id=str(row.id),
                checked_exchange_indices=list(range(len(result.exchanges))),
                checked_state_keys=['f64_identity','output_loss_db','f64_control_released'],
                evaluated_at=now.isoformat(),method=result.method,blockers=[],
                warnings=candidate.eligibility.warnings,measurement_provenance='real',certification_status='unknown'),
            operator_confirmed=True,confirmed_at=now,confirmed_by=actor)
        db.add(RouteCalibrationApplication(id=ident,lab_profile_id=lab_id,acquisition_run_id=row.id,
            topology_id=selection.topology_id,chain_id=selection.chain_id,idempotency_key=request.idempotency_key,
            request_payload=request.model_dump(mode='json'),record=record.model_dump(mode='json')))
        db.flush()
        if pointer is None:
            db.add(RouteCalibrationSelection(**scope,application_id=ident,version=1))
            db.flush()  # 并发首选由scope唯一约束裁决。
        else:
            changed=db.execute(update(RouteCalibrationSelection).where(
                RouteCalibrationSelection.id==pointer.id,RouteCalibrationSelection.version==pointer.version,
                RouteCalibrationSelection.application_id==previous_id).values(
                application_id=ident,version=pointer.version+1).execution_options(synchronize_session=False))
            if changed.rowcount!=1:
                raise RouteApplicationConflict('当前选择已被另一确认推进')
        db.commit()  # 提交失败不能向HTTP返回已应用。
        return record,True
    except RouteApplicationConflict:
        db.rollback()
        # 另一会话可能已完成同一操作；先读已提交同键同载荷真值，而非把成功误报为CAS失败。
        existing=_replay(db,lab_id,request)
        if existing is not None:
            return existing,False
        raise
    except (IntegrityError,OperationalError) as exc:
        db.rollback()
        if isinstance(exc,OperationalError) and not (
            db.get_bind().dialect.name=='sqlite' and 'locked' in str(exc).lower()):
            raise
        existing=_replay(db,lab_id,request)
        if existing is not None:
            return existing,False
        raise RouteApplicationConflict('当前选择发生并发冲突，请重新预览') from exc
    except Exception:
        db.rollback()
        raise


def list_route_applications(db,lab_id: UUID,topology_id: UUID,chain_id: str):
    if db.get(LabProfile,lab_id) is None:
        raise LookupError('实验室不存在')
    rows=db.query(RouteCalibrationApplication).filter_by(lab_profile_id=lab_id,
        topology_id=topology_id,chain_id=chain_id).all()
    # 只反序列化不可变记录；不以当前图、run或当前期限重算历史。
    return sorted((RouteApplicationRecord.model_validate(row.record) for row in rows),
        key=lambda record:record.confirmed_at,reverse=True)


def assert_route_topologies_deletable(db,topology_ids):
    """采用历史不能随配置硬删除；不解除外键、不级联、不重写旧记录。"""
    for model in (RouteCalibrationApplication,RouteCalibrationSelection):
        if db.query(model.id).filter(model.topology_id.in_(topology_ids)).first() is not None:
            raise RouteApplicationConflict('拓扑已有校准采用记录；为保留测量追溯历史，不允许删除或替换该拓扑')


def resolve_effective_route_compensation(db,lab_id,mode,frequency_mhz):
    """统一查询接口；执行创建时冻结返回值，执行消费不得再次调用当前解析。"""
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation as resolve
    return resolve(db,lab_id,mode,frequency_mhz)
