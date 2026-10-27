"""PC-01A：白名单配置盘点，无 HAL I/O、无持久化、无资格判定。"""
import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chamber import ChamberConfiguration
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.models.lab_profile import LabProfile
from app.models.probe import Probe
from app.models.switch_topology import SwitchTopology
from app.schemas.calibration_scope import (
    CalibrationScopePayload, CalibrationScopeSnapshot, CalibrationScopeComparison,
)
from app.services.calibration.rf_chain_resolver import resolve_rf_chains


def _json_numbers(value):
    """JSON number 无整数/浮点类型差异；兼容浏览器 4.0 → 4 的往返。"""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def _canonical(value):
    return json.dumps(_json_numbers(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _ordered(values):
    return sorted(values, key=_canonical)


def scope_digest(payload: CalibrationScopePayload) -> str:
    return hashlib.sha256(_canonical(payload.model_dump(mode='json')).encode()).hexdigest()


def _fields(value, names):
    return {name: getattr(value, name) for name in names}


def _scope_chain_for_route(topology, route):
    """身份不携带默认量值；只取同一实际所选路径的末边或显式owner。"""
    from app.services.calibration.rf_chain_resolver import RFChainSpec
    from app.services.topology_loss import effective_connection_loss, loss_source_for_terminal
    mode = next((item for item in topology.operating_modes or [] if item.get('id') == route.operating_mode), {})
    ids = set(mode.get('active_connections') or [edge['id'] for edge in topology.connections or []
                                               if route.operating_mode in edge.get('modes', [])])
    active = [edge for edge in topology.connections or [] if edge['id'] in ids]
    source = loss_source_for_terminal(topology.nodes or [], active, route.connection_ids)
    return RFChainSpec(route.chain_id, route.ce_port, route.probe_id, route.polarization,
                       cable_loss_db=effective_connection_loss(source))


def build_calibration_scope(db: Session, lab_id: UUID, mode: str = 'mimo_ota', *, topology_id: UUID | None = None) -> CalibrationScopeSnapshot:
    resolution = resolve_rf_chains(db, lab_id, mode)
    if topology_id is not None:
        # 普通显式topology仍使用完整正式集合；不借此绕过重复CE门。
        from app.services.calibration.route_calibration import list_route_selections
        from app.services.calibration.rf_chain_resolver import RFChainResolution
        selected_routes = list_route_selections(db, lab_id, topology_id, mode)
        selected_topology = db.get(SwitchTopology, topology_id)
        resolution = RFChainResolution(lab_profile_id=lab_id,chamber_id=selected_topology.chamber_id,
            topology_id=str(topology_id),topology_name=selected_topology.name,operating_mode=mode,
            chains=[_scope_chain_for_route(selected_topology,r) for r in selected_routes])
    return _build_scope_payload(db,lab_id,mode,resolution)


def build_selected_route_calibration_scope(db: Session,lab_id: UUID,mode: str,*,topology_id: UUID,chain_id: str) -> CalibrationScopeSnapshot:
    """批服务器指定单项的真实scope；不先经过正式全局集合唯一门。"""
    from app.services.calibration.route_calibration import resolve_explicit_route_selection
    from app.services.calibration.rf_chain_resolver import RFChainResolution
    from app.services.declared_rf_routes import resolve_saved_rf_path
    topology=db.get(SwitchTopology,topology_id)
    if topology is None:
        raise LookupError('拓扑不存在')
    selected_mode=next((m for m in topology.operating_modes or [] if m.get('id')==mode),{})
    ids=selected_mode.get('active_connections') or [c['id'] for c in topology.connections or [] if mode in c.get('modes',[])]
    active=[c for c in topology.connections or [] if c.get('id') in ids]
    _,edges=resolve_saved_rf_path(topology.nodes or [],active,chain_id)
    route=resolve_explicit_route_selection(db,lab_id,topology_id,mode,chain_id,[e['id'] for e in edges])
    resolution=RFChainResolution(lab_profile_id=lab_id,chamber_id=topology.chamber_id,
        topology_id=str(topology.id),topology_name=topology.name,operating_mode=mode,
        chains=[_scope_chain_for_route(topology,route)])
    return _build_scope_payload(db,lab_id,mode,resolution,selected_route=route)


def _build_scope_payload(db,lab_id,mode,resolution,*,selected_route=None):
    lab = db.query(LabProfile).filter(LabProfile.id == lab_id).one()
    chamber = db.query(ChamberConfiguration).filter(ChamberConfiguration.id == resolution.chamber_id).one_or_none()
    if chamber is None:
        raise ValueError('LabProfile 绑定暗室不存在')
    warnings = list(resolution.warnings)
    if not lab.is_active:
        warnings.append('LabProfile 已停用')
    # 只取保存声明；不将 UUID/端点伪装成实物序列号，不暴露凭据/自由参数。
    resources = []
    for binding in lab.instrument_bindings or []:
        if not isinstance(binding, dict):
            warnings.append('仪器绑定含畸形条目')
            continue
        raw_id = binding.get('category_id')
        try:
            category_id = UUID(str(raw_id))
        except (ValueError, TypeError):
            warnings.append('仪器绑定缺少合法 category_id')
            continue
        category = db.query(InstrumentCategory).filter(InstrumentCategory.id == category_id).one_or_none()
        connection = db.query(InstrumentConnection).filter(InstrumentConnection.category_id == category_id).one_or_none()
        row = {key: binding.get(key) for key in (
            'category_id', 'instrument_model_id', 'connection_endpoint', 'driver_mode', 'role')}
        row['saved'] = None if category is None else {
            'category_key': category.category_key, 'is_active': category.is_active,
            'selected_model_id': str(category.selected_model_id) if category.selected_model_id else None,
            'driver_mode': category.driver_mode,
            'endpoint': connection.endpoint if connection else None,
            'protocol': connection.protocol if connection else None,
            'connection_id': str(connection.id) if connection else None,
            'controller_ip': connection.controller_ip if connection else None,
            'port': connection.port if connection else None,
            'profiles': {k: (connection.connection_params or {}).get(k) for k in (
                'base_station_adapter_profile', 'channel_emulator_adapter_profile', 'topology_profile_id',
                'ip', 'controller_ip', 'ip_address', 'visa_resource', 'endpoint', 'port', 'protocol',
                'motion_truth_units_verified', 'motion_truth_user_units', 'motion_truth_coordinate_offset_deg',
                'motion_truth_coordinate_offset_verified', 'motion_truth_coordinate_offset_verification_source',
                'motion_truth_coordinate_offset_verified_at', 'motion_truth_min_deg', 'motion_truth_max_deg',
                'motion_truth_xf_speed', 'position_tolerance_deg', 'azimuth_axis')}
                if connection and isinstance(connection.connection_params, dict) else {},
        }
        resources.append(row)
        if selected_route is not None and connection is not None:
            from app.services.calibration.route_calibration import route_switch_steps
            selected_topology=db.get(SwitchTopology,selected_route.topology_id)
            steps=route_switch_steps(db,selected_topology,selected_route.nodes,selected_route.connections,lab)
            selected_maps={step['path_name']:step['mapping'] for step in steps
                if step['category_id']==str(category_id)}
            if selected_maps:
                row['saved']['selected_port_maps']=selected_maps
        if category is None:
            warnings.append(f'绑定仪器类别已不存在：{raw_id}')
        elif not category.is_active:
            warnings.append(f'绑定仪器已停用：{category.category_name}（{category.category_key}，{raw_id}）')
        elif (not connection or str(category.selected_model_id) != str(binding.get('instrument_model_id'))
              or connection.endpoint != binding.get('connection_endpoint')
              or category.driver_mode != binding.get('driver_mode')):
            warnings.append(f'保存资源与 LabProfile 绑定不一致：{category.category_key}')
    if not resources:
        warnings.append('尚无 LabProfile 仪器绑定')
    topology = db.query(SwitchTopology).filter(
        SwitchTopology.id == UUID(str(resolution.topology_id))).one_or_none() if resolution.topology_id else None
    graph = {'id': str(topology.id) if topology else None}
    if topology:
        if selected_route is not None:
            graph['scope_source']='selected_route'
            graph['selected_chain_id']=selected_route.chain_id
            graph['selected_route_digest']=selected_route.route_digest
        selected_mode = next((m for m in topology.operating_modes or [] if m.get('id') == mode), {})
        active = set(selected_mode.get('active_connections') or [])
        connections = [c for c in topology.connections or [] if c.get('id') in active]
        node_ids = {c.get(k) for c in connections for k in ('source', 'target')}
        graph['connections'] = _ordered([{k: c.get(k) for k in (
            'id', 'source', 'source_pin', 'target', 'target_pin', 'cable_type', 'cable_length_m',
            'cable_loss_db', 'pa_gain_db', 'switch_port', 'direction', 'calibrated_phase_deg',
            'calibrated_loss_db', 'ce_port')}
                                         for c in connections])
        # label 是 CE 端口解析输入，而非纯显示名称；因此保留。
        graph['nodes'] = _ordered([{
            **{k: n.get(k) for k in ('id', 'type', 'label')},
            'parameters': {k: v for k, v in (n.get('params') or {}).items() if k in (
                'model', 'vendor', 'hardware_id', 'inputs', 'outputs', 'ports', 'roles', 'slots',
                'function', 'num_ports', 'port_roles', 'physical_port_display', 'probe_id', 'polarization',
                'ce_port', 'switch_pin', 'switch_slot', 'ring', 'elevation_deg', 'gain_db', 'gain_dbi',
                'loss_db', 'attenuation_db', 'frequency_range_mhz', 'max_power_dbm')},
            'parameters_digest': hashlib.sha256(_canonical(n.get('params') or {}).encode()).hexdigest(),
        } for n in topology.nodes or [] if n.get('id') in node_ids])
        graph['active_connections'] = sorted(active)
        graph['required_instruments'] = sorted(selected_mode.get('required_instruments') or [])
        # 仅新增显式归属投影；不补null、不重建历史baseline，也不改变旧图摘要。
        if any('loss_owner_connection_id' in c for c in topology.connections or []):
            if selected_route is not None:
                selected_ids = set([*selected_route.connection_ids, *selected_route.calibration_connection_ids])
            else:
                from app.services.declared_rf_routes import resolve_saved_rf_path
                def effective_edges(mode_id):
                    saved_mode = next((m for m in topology.operating_modes or [] if m.get('id') == mode_id), None)
                    if saved_mode is None:
                        return []
                    ids = set(saved_mode.get('active_connections') or [c['id'] for c in topology.connections or []
                        if mode_id in c.get('modes', [])])
                    return [c for c in topology.connections or [] if c['id'] in ids]

                normal = effective_edges(mode)
                reference = effective_edges('calibration')
                selected_ids, probe_ids = set(), set()
                for chain in resolution.chains:
                    nodes, edges = resolve_saved_rf_path(topology.nodes or [], normal, chain.chain_id,
                        check_internal_paths=False)
                    selected_ids.update(c['id'] for c in edges)
                    probe_ids.add(nodes[-1]['id'])
                # 只盘点所选探头可达的保存参考边；不以内部贯通/采集资格门筛掉声明。
                frontier = list(probe_ids)
                seen = set(probe_ids)
                while frontier:
                    parent = frontier.pop()
                    for edge in reference:
                        if edge.get('source') != parent:
                            continue
                        selected_ids.add(edge['id'])
                        if edge['target'] not in seen:
                            seen.add(edge['target'])
                            frontier.append(edge['target'])
            declarations = [{ 'id': c['id'], 'loss_owner_connection_id': c['loss_owner_connection_id'] }
                for c in topology.connections or [] if c['id'] in selected_ids and 'loss_owner_connection_id' in c]
            if declarations:
                graph['loss_ownership'] = _ordered(declarations)
    probes = db.query(Probe).filter(Probe.chamber_config_id == chamber.id, Probe.is_active.is_(True)).all()
    chains = sorted([{
        'chain_id': c.chain_id, 'ce_port': c.ce_port, 'probe_id': c.probe_id,
        'polarization': c.polarization, 'cable_loss_db': c.cable_loss_db,
    } for c in resolution.chains], key=lambda c: c['chain_id'])
    if len({c['chain_id'] for c in chains}) != len(chains):
        warnings.append('解析链身份重复')
    if len({(c['probe_id'], c['polarization']) for c in chains}) != len(chains):
        warnings.append('探头/极化映射重复')
    payload = CalibrationScopePayload(
        lab_profile_id=lab.id, chamber_id=chamber.id, operating_mode=mode, lab_active=lab.is_active,
        chamber=_fields(chamber, (
            'chamber_radius_m', 'quiet_zone_diameter_m', 'num_probes', 'num_polarizations', 'num_rings',
            'probe_distribution', 'has_pa', 'pa_gain_db', 'has_lna', 'lna_gain_db', 'has_duplexer',
            'duplexer_insertion_loss_db', 'ce_num_ota_ports', 'probe_gain_dbi', 'typical_cable_loss_db',
            'cable_sgh_to_sa_loss_db', 'freq_min_mhz', 'freq_max_mhz', 'has_turntable', 'turntable_max_load_kg',
            'has_channel_emulator', 'ce_bidirectional', 'ce_min_input_dbm', 'pa_p1db_dbm',
            'lna_noise_figure_db', 'duplexer_isolation_db')),
        resources=_ordered(resources), topology=graph,
        probes=_ordered([_fields(p, ('probe_number', 'ring', 'polarization', 'position', 'hardware_id', 'channel_port',
                                    'frequency_range_mhz', 'max_power_dbm', 'gain_db'))
                         for p in probes]), chains=chains,
    )
    digest = scope_digest(payload)  # allow_nan=False，畸形数值不形成有效范围
    return CalibrationScopeSnapshot(payload=payload, digest=digest,
                                    configuration_complete=bool(chains) and not warnings, warnings=warnings)


def _topology_affected(before: dict, after: dict, chain_ids: set[str]) -> set[str]:
    """按已有有向连接定位下游链；全局声明或无法关联的差异保守复核全部链。"""
    local = {'nodes', 'connections', 'active_connections'}
    if any(before.get(k) != after.get(k) for k in (set(before) | set(after)) - local):
        return chain_ids

    def index(graph, key):
        rows = graph.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in rows):
            raise ValueError('保留快照拓扑结构无效')
        if key == 'connections' and any(r.get(k) is not None and not isinstance(r.get(k), str)
                                        for r in rows for k in ('source', 'target')):
            raise ValueError('保留快照连接身份无效')
        result = {r['id']: r for r in rows}
        if len(result) != len(rows):
            raise ValueError('保留快照拓扑身份重复')
        return result

    old_nodes, new_nodes = index(before, 'nodes'), index(after, 'nodes')
    old_edges, new_edges = index(before, 'connections'), index(after, 'connections')
    changed_nodes = {k for k in set(old_nodes) | set(new_nodes) if old_nodes.get(k) != new_nodes.get(k)}
    changed_edges = {k for k in set(old_edges) | set(new_edges) if old_edges.get(k) != new_edges.get(k)}
    # 活动列表若出现无法还原的边，不将缺失路径解释为无影响。
    active = []
    for graph in (before, after):
        rows = graph.get('active_connections', [])
        if not isinstance(rows, list) or any(not isinstance(k, str) for k in rows):
            raise ValueError('保留快照活动连接结构无效')
        active.extend(rows)
    if set(active) - (set(old_edges) | set(new_edges)):
        return chain_ids
    affected = changed_edges & chain_ids
    for edges in (old_edges, new_edges):
        downstream = set(changed_nodes)
        downstream.update(edges[k].get('target') for k in changed_edges if k in edges)
        while True:
            targets = {e.get('target') for e in edges.values() if e.get('source') in downstream}
            if targets <= downstream:
                break
            downstream.update(targets)
        affected.update(k for k, e in edges.items() if k in chain_ids
                        and (e.get('source') in downstream or e.get('target') in downstream))
    return affected or chain_ids


def compare_calibration_scope(current: CalibrationScopeSnapshot, baseline: CalibrationScopeSnapshot):
    if scope_digest(baseline.payload) != baseline.digest:
        raise ValueError('保留快照摘要不匹配，请重新保留快照')
    before, after = baseline.payload.model_dump(mode='json'), current.payload.model_dump(mode='json')
    changed = sorted(k for k in after if before[k] != after[k])
    old = {c.chain_id: c.model_dump() for c in baseline.payload.chains}
    new = {c.chain_id: c.model_dump() for c in current.payload.chains}
    all_chains = set(old) | set(new)
    affected = {key for key in all_chains if old.get(key) != new.get(key)}
    if set(changed) - {'chains', 'topology'}:
        affected = all_chains
    elif 'topology' in changed:
        affected.update(_topology_affected(before['topology'], after['topology'], all_chains))
    return CalibrationScopeComparison(current=current, changed_sections=changed, affected_chain_ids=sorted(affected),
                                      requires_review=bool(changed))
