"""PC04A2完整路径查询；不改变正常执行解析器，不访问仪器。"""
import copy
import hashlib
import json
from uuid import UUID

from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.schemas.route_calibration import RouteSelection
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
            for edge in calibration:
                if edge['source'] != parent_id:
                    continue
                target = nodes[edge['target']]
                if target['id'] in visited:
                    continue
                if not (target.get('params', {}).get('connection_scope') == 'calibration' or
                        target.get('type') in ('reference_antenna','receive_cable','signal_analyzer','air_path')):
                    continue
                if edge['id'] not in {e['id'] for e in ref_edges}:
                    ref_edges.append(edge)
                if target['id'] not in seen:
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
