"""保存的正常射频路径纯解释；不访问数据库、HAL 或当前继电器位置。"""
import copy
import re


def _index(rows, label):
    result = {}
    for row in rows:
        ident = row.get('id')
        if not isinstance(ident, str) or not ident.strip() or ident in result:
            raise ValueError(f'{label}身份缺失或重复')
        result[ident] = row
    return result


def resolve_saved_rf_path(nodes, active_connections, terminal_connection_id, *, check_internal_paths=True):
    """返回保存的有序(nodes, edges)；无声明时只接受旧式唯一链。"""
    nodes = _index(list(nodes.values()) if isinstance(nodes, dict) else nodes, '节点')
    edges = _index(active_connections, '连接')
    terminal = edges.get(terminal_connection_id)
    if terminal is None or terminal.get('target') not in nodes:
        raise ValueError('终端连接不属于当前保存模式')
    probe = nodes[terminal['target']]
    if probe.get('type') != 'probe':
        raise ValueError('路径必须以探头终止')
    incoming, outgoing = {}, {}
    for edge in edges.values():
        if any(edge.get(k) not in nodes for k in ('source','target')):
            raise ValueError('连接引用未知节点')
        incoming.setdefault(edge['target'], []).append(edge)
        outgoing.setdefault(edge['source'], []).append(edge)
    declared = (probe.get('params') or {}).get('rf_path_selection')
    if declared is None:
        path_nodes, path_edges, seen = [probe], [], {probe['id']}
        current = probe
        while current.get('type') not in ('ce_port','channel_emulator'):
            previous = incoming.get(current['id'], [])
            if len(previous) != 1:
                raise ValueError('通路缺少唯一完整CE源端，须保存显式路径')
            edge = previous[0]
            parent = nodes[edge['source']]
            if parent['id'] in seen:
                raise ValueError('正常通路存在回路')
            if parent.get('type') != 'channel_emulator' and len(outgoing.get(parent['id'], [])) != 1:
                raise ValueError('通路存在多个输出分支，须保存显式路径')
            seen.add(parent['id']); path_nodes.insert(0,parent); path_edges.insert(0,edge); current=parent
        if path_edges[-1]['id'] != terminal_connection_id:
            raise ValueError('保存路径终端不一致')
    else:
        if not isinstance(declared,dict) or set(declared) != {'connection_ids','switch_mappings'}:
            raise ValueError('显式路径声明结构无效')
        ids=declared['connection_ids']
        if (not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in edges for i in ids)
                or len(ids)!=len(set(ids)) or ids[-1]!=terminal_connection_id):
            raise ValueError('显式路径连接缺失、重复或终端不匹配')
        path_edges=[edges[i] for i in ids]
        path_nodes=[nodes[path_edges[0]['source']]]
        for edge in path_edges:
            if edge['source']!=path_nodes[-1]['id']:
                raise ValueError('显式路径不连续')
            path_nodes.append(nodes[edge['target']])
        if len({n['id'] for n in path_nodes})!=len(path_nodes):
            raise ValueError('显式路径存在回路')
        if path_nodes[0].get('type') not in ('ce_port','channel_emulator'):
            raise ValueError('显式路径必须从CE源端开始')
        mappings=declared['switch_mappings']
        switches={n['id'] for n in path_nodes if n.get('type')=='switch_slot'}
        if (not isinstance(mappings,list) or any(not isinstance(m,dict) or set(m)!={'node_id','path_name'}
                or not isinstance(m['path_name'],str) or not m['path_name'].strip() for m in mappings)
                or len({m['node_id'] for m in mappings})!=len(mappings)
                or {m['node_id'] for m in mappings}!=switches):
            raise ValueError('显式路径必须逐开关声明唯一映射名')
        for node in path_nodes[1:-1]:
            if node.get('type') in ('ce_port','channel_emulator','probe'):
                raise ValueError('显式路径存在额外CE源端或探头中转')
            if node.get('type') != 'switch_slot' and 'internal_paths' not in (node.get('params') or {}) and (
                    len(incoming.get(node['id'],[]))!=1 or len(outgoing.get(node['id'],[]))!=1):
                raise ValueError('非开关中间器件存在分叉')
        for edge in path_edges:
            if any(not isinstance(edge.get(k),str) or not edge[k].strip() for k in ('source_pin','target_pin')):
                raise ValueError('显式路径必须保存完整端口')
    if incoming.get(path_nodes[0]['id']):
        raise ValueError('CE源端存在回接')
    if any(node.get('type') in ('probe', 'antenna') for node in path_nodes[1:-1]):
        raise ValueError('正常路径的探头/天线只能作为终点，不能中转')
    for node in path_nodes:
        if (node.get('params') or {}).get('connection_scope')=='calibration' or node.get('type') in (
                'reference_antenna','receive_cable','signal_analyzer','air_path'):
            raise ValueError('正常路径不能包含校准参考接线')
    params=probe.get('params') or {}
    if declared is not None and (type(params.get('probe_id')) is not int or params['probe_id']<0 or params.get('polarization') not in ('V','H')):
        raise ValueError('显式路径探头必须明确编号及V/H极化')
    if check_internal_paths:
        from app.schemas.topology_internal_paths import validate_internal_traversals
        validate_internal_traversals(path_nodes, path_edges, active_connections=active_connections)
    return copy.deepcopy(path_nodes),copy.deepcopy(path_edges)


def selected_switch_mappings(path_nodes, path_edges, port_maps, *, category_id):
    """校验保存节点/连线与绑定port_maps的精确配对，不解释端口标签。"""
    declared=(path_nodes[-1].get('params') or {}).get('rf_path_selection')
    if declared is None:
        if any(node.get('type') == 'switch_slot' for node in path_nodes[1:-1]):
            raise ValueError('开关路径必须保存原开关映射声明')
        return []
    selected=[]
    for ref in declared['switch_mappings']:
        node=next(n for n in path_nodes if n['id']==ref['node_id'])
        params=node.get('params') or {}
        mapping=port_maps.get(ref['path_name']) if isinstance(port_maps,dict) else None
        if not isinstance(mapping,dict):
            raise ValueError('保存开关映射不存在')
        relay=mapping.get('switch_id',mapping.get('relay'))
        output=mapping.get('output_port',mapping.get('position'))
        kind=mapping.get('relay_type')
        # 只校验已核验的配置域：Rev A #1801188 p9 SPDT、p12 SP6T。
        relay_id=re.fullmatch(r'([1-9][0-9]*):INT_RELAY_([A-D])',relay) if isinstance(relay,str) else None
        if (relay_id is None or kind not in ('spdt','sp6t') or
                (kind=='spdt' and output not in ('NC','NO')) or
                (kind=='sp6t' and (type(output) is not int or not 1<=output<=6)) or
                type(mapping.get('input_port')) is not int or mapping['input_port']<0):
            raise ValueError('开关映射必须明确继电器类型、输入与合法输出')
        if str(params.get('instrument_category_id'))!=str(category_id):
            raise ValueError('开关节点与绑定类别不一致')
        index=path_nodes.index(node)
        # 图pin和命令位置属于不同命名域，只有操作员明确保存的配对可关联。
        if (mapping.get('topology_input_pin')!=path_edges[index-1]['target_pin'] or
                mapping.get('topology_output_pin')!=path_edges[index]['source_pin']):
            raise ValueError('保存路径端口与开关映射配对不一致')
        selected.append(dict(node_id=node['id'],path_name=ref['path_name'],category_id=str(category_id),
            mapping=copy.deepcopy(mapping)))
    return selected


def validate_simultaneous_switch_mappings(steps):
    """正式集合不能要求同一继电器同时处于不同位置。"""
    positions={}
    for step in steps:
        mapping=step['mapping']
        key=(str(step['category_id']),mapping.get('switch_id',mapping.get('relay')))
        position=(mapping['input_port'],mapping.get('output_port',mapping.get('position')))
        if key in positions and positions[key]!=position:
            raise ValueError('正式通路要求同一继电器同时处于冲突位置')
        positions[key]=position


def switch_execution_identity(steps):
    """只保留物理执行身份；路径别名、参考段和映射备注不纳入。"""
    result=[]
    for step in steps:
        mapping=step['mapping']
        result.append({key:step[key] for key in ('node_id','category_id','connection_id','endpoint',
            'instrument_model_id','driver_mode')} | {'mapping':{
                'switch_id':mapping.get('switch_id',mapping.get('relay')),
                'relay_type':mapping['relay_type'],'input_port':mapping['input_port'],
                'output_port':mapping.get('output_port',mapping.get('position')),
                'topology_input_pin':mapping['topology_input_pin'],'topology_output_pin':mapping['topology_output_pin']}})
    return result


def rf_execution_identity(nodes,edges,switch_identity=()):
    """冻结/当前图/独立actual-target共用正常路径身份的纯投影。"""
    identity=dict(nodes=[{'id':n['id'],'type':n['type']} for n in nodes],
        ports=[dict(connection_id=e['id'],source=e['source'],source_pin=e.get('source_pin','out'),
            target=e['target'],target_pin=e.get('target_pin','in')) for e in edges])
    if switch_identity:
        identity['switch_mappings']=copy.deepcopy(list(switch_identity))
    # 只投影各自保存快照的所选穿越，不运行当前严验、不访问当前图。
    internal = [dict(node_id=node['id'], from_port=edges[index-1].get('target_pin'),
                     to_port=edges[index].get('source_pin'))
        for index,node in enumerate(nodes[1:-1], 1)
        if 'internal_paths' in (node.get('params') or {})]
    if internal:
        identity['internal_paths'] = internal
    return identity
