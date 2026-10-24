"""PC04A2完整路径查询；不改变正常执行解析器，不访问仪器。"""
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
    for probe in nodes.values():
        if probe.get('type') != 'probe' or probe['id'] not in incoming:
            continue
        route_nodes, route_edges, visited = [probe], [], {probe['id']}
        current = probe
        while current.get('type') not in ('ce_port', 'channel_emulator'):
            predecessors = incoming.get(current['id'], [])
            if len(predecessors) != 1:
                raise ValueError('通路存在多个可达分支或缺少唯一F64源端')
            edge = predecessors[0]
            parent = nodes[edge['source']]
            if parent['id'] in visited:
                raise ValueError('通路存在回路，不能确定采集路径')
            if parent.get('type') != 'channel_emulator' and len(outgoing.get(parent['id'], [])) != 1:
                raise ValueError('通路存在多个输出分支，不能确定固定接线')
            visited.add(parent['id'])
            route_nodes.insert(0,parent)
            route_edges.insert(0,edge)
            current = parent
        # F64源端存在回接也不是合法固定路径。
        if incoming.get(current['id']):
            raise ValueError('F64输出源端存在回接或回路')
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
            k:v for k,v in n.get('params', {}).items() if k not in ('visible_modes','description','notes')
        }} for n in [*route_nodes,*refs]]
        port_rows = [dict(connection_id=e['id'],source=e['source'],source_pin=e.get('source_pin','out'),
                         target=e['target'],target_pin=e.get('target_pin','in')) for e in route_edges]
        identity = dict(lab_profile_id=str(lab.id),topology_id=str(topology.id),mode=operating_mode,
            ce_port=ce_port,nodes=identity_nodes,ports=port_rows,calibration_connections=ref_edges)
        digest = hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        antennas = [n for n in refs if n.get('type') == 'reference_antenna']
        analyzers = [n for n in refs if n.get('type') == 'signal_analyzer']
        if len(antennas) > 1 or len(analyzers) > 1:
            raise ValueError('所选通路的参考天线或分析仪不唯一')
        selections.append(RouteSelection(lab_profile_id=lab.id,chamber_id=lab.chamber_config_id,
            topology_id=topology.id,operating_mode=operating_mode,chain_id=route_edges[-1]['id'],ce_port=ce_port,
            probe_id=probe_id,polarization=pol,node_ids=[n['id'] for n in route_nodes],
            connection_ids=[e['id'] for e in route_edges],ports=port_rows,nodes=snapshot(route_nodes),
            connections=snapshot(route_edges),calibration_node_ids=[n['id'] for n in refs],
            calibration_connection_ids=[e['id'] for e in ref_edges],calibration_nodes=snapshot(refs),
            calibration_connections=snapshot(ref_edges),reference_antenna_id=antennas[0]['id'] if antennas else None,
            analyzer_category_id=analyzers[0].get('params',{}).get('instrument_category_id') if analyzers else None,
            route_digest=digest))
    if len({(r.probe_id,r.polarization) for r in selections}) != len(selections):
        raise ValueError('探头编号及极化存在重复通路')
    from app.hal.propsim_f64 import RealPropsimF64Driver
    physical_outputs = [RealPropsimF64Driver._ce_port_to_output_num(r.ce_port) for r in selections]
    if len(physical_outputs) != len(set(physical_outputs)):
        raise ValueError('同一F64输出口存在多个可达通路，不能确定单条固定接线')
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
    record=jobs.record(row)
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
                current=list_route_selections(db,lab_id,selection.topology_id,selection.operating_mode)
                matching=[route for route in current if route.chain_id==selection.chain_id]
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
        result=jobs.record(row).result
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
