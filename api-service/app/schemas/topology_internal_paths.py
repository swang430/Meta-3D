"""内部端口对白名单的纯判据；不访问仪器，不推断物理导通或授予资格。"""
from .topology_nominal import MISSING, same_json
from .topology_ports import BSE_TYPES, resolve_port_direction


_TWO_PORT_TYPES = {'amplifier', 'pad', 'cable', 'receive_cable'}
_NO_FORWARDING_TYPES = {'termination', 'ce_port', 'channel_emulator', 'bse_port',
    'communication_tester', 'sa_port', 'signal_analyzer', 'vna', 'emcenter'}


def _validate_declaration(node):
    params = node.get('params') or {}
    if 'internal_paths' not in params:
        return
    ident, paths, ports = node['id'], params['internal_paths'], params.get('ports')
    if not isinstance(paths, list):
        raise ValueError(f'器件 {ident} 的 internal_paths 必须是非 null 列表')
    if paths and node.get('type') in _NO_FORWARDING_TYPES:
        raise ValueError(f'器件 {ident} 类型不允许非空内部通路')
    if paths and (not isinstance(ports, list) or not ports or
            any(not isinstance(p, str) or not p or p.strip() != p for p in ports) or
            len(ports) != len(set(ports))):
        raise ValueError(f'器件 {ident} 的内部通路必须引用显式 ports')
    if paths and node.get('type') in _TWO_PORT_TYPES and len(ports) != 2:
        raise ValueError(f'器件 {ident} 的内部通路只允许两个显式端口')
    if node.get('type') == 'amplifier' and len(paths) > 1:
        raise ValueError(f'器件 {ident} 放大器只允许一条单向内部通路')
    seen = set()
    for pair in paths:
        if not isinstance(pair, dict) or set(pair) != {'from_port', 'to_port'}:
            raise ValueError(f'器件 {ident} 的内部通路每行只能含 from_port/to_port')
        source, target = pair['from_port'], pair['to_port']
        if any(not isinstance(p, str) or not p or p.strip() != p or p not in ports
               for p in (source, target)) or source == target:
            raise ValueError(f'器件 {ident} 内部通路 {source}→{target} 引用无效端口或自环')
        if (source, target) in seen:
            raise ValueError(f'器件 {ident} 内部通路 {source}→{target} 重复')
        seen.add((source, target))
        _check_known_direction(node, source, target)


def _check_known_direction(node, source, target):
    if (resolve_port_direction(node, source)[0] == 'output' or
            resolve_port_direction(node, target)[0] == 'input'):
        raise ValueError(f"器件 {node['id']} 内部通路 {source}→{target} 与已声明方向冲突")


def internal_transition(node: dict, from_port: str, to_port: str, *,
                        incoming_count: int, outgoing_count: int) -> str:
    """返回 declared/legacy；缺证据或禁止穿越抛 ValueError，不修改原 JSON。"""
    _validate_declaration(node)
    ident, kind, params = node['id'], node.get('type'), node.get('params') or {}
    if kind == 'termination':
        raise ValueError(f'器件 {ident} 为负载，不能作为中转')
    if 'internal_paths' in params:
        if {'from_port': from_port, 'to_port': to_port} not in params['internal_paths']:
            raise ValueError(f'器件 {ident} 未声明内部通路 {from_port}→{to_port}')
        if (resolve_port_direction(node, from_port)[0] not in {'input', 'bidirectional'} or
                resolve_port_direction(node, to_port)[0] not in {'output', 'bidirectional'}):
            raise ValueError(f'器件 {ident} 内部通路方向未声明或冲突')
        return 'declared'
    ports = params.get('ports')
    if (kind not in _TWO_PORT_TYPES or not isinstance(ports, list) or len(ports) != 2 or
            any(not isinstance(p, str) or not p or p.strip() != p for p in ports) or
            not isinstance(from_port, str) or not isinstance(to_port, str) or
            from_port == to_port or {from_port, to_port} != set(ports) or
            incoming_count != 1 or outgoing_count != 1):
        raise ValueError(f'器件 {ident} 内部通路未声明，不能推定多端口贯通')
    _check_known_direction(node, from_port, to_port)
    return 'legacy'


def _saved_pins(node, incoming, outgoing):
    pins = incoming.get('target_pin'), outgoing.get('source_pin')
    if any(not isinstance(pin, str) or not pin or pin.strip() != pin for pin in pins):
        raise ValueError(f"器件 {node['id']} 相邻连线 {incoming['id']}/{outgoing['id']} 必须保存完整端口")
    return pins


def validate_internal_traversals(path_nodes: list[dict], path_edges: list[dict], *,
                                 active_connections: list[dict]) -> list[dict]:
    """只返回所选 declared 身份；边必须来自保存 JSON，不接受模型补默认值。

    缺字段开关仅延后到调用者原映射门核验，不代表本函数证明了开关可用。
    参考虚拟模型的无字段例外由参考解析调用边界处理，不扩充双端白名单。
    """
    result = []
    for index, node in enumerate(path_nodes[1:-1], 1):
        source, target = _saved_pins(node, path_edges[index - 1], path_edges[index])
        if node.get('type') == 'switch_slot' and 'internal_paths' not in (node.get('params') or {}):
            continue
        provenance = internal_transition(node, source, target,
            incoming_count=sum(edge.get('target') == node['id'] for edge in active_connections),
            outgoing_count=sum(edge.get('source') == node['id'] for edge in active_connections))
        if provenance == 'declared':
            result.append(dict(node_id=node['id'], from_port=source, to_port=target))
    return result


def _node_contract(node):
    params = node.get('params') or {}
    keys = ['ports', 'port_directions', 'internal_paths', 'rf_path_selection']
    if node.get('type') in BSE_TYPES:
        keys.append('port_roles')
    return [node.get('type'), *[params.get(key, MISSING) for key in keys]]


def _edge_contract(edge):
    return [edge.get(key, MISSING) for key in ('source', 'target', 'source_pin', 'target_pin', 'modes')]


def _effective_modes(modes, connections):
    return {mode['id']: set(mode.get('active_connections', []) or [edge['id'] for edge in connections
            if mode['id'] in edge.get('modes', [])]) for mode in modes}


def validate_internal_path_write(nodes, connections, modes, *, previous_nodes=None,
                                 previous_connections=None, previous_modes=None,
                                 allow_legacy_missing=False) -> None:
    """只读最终候选图；结构/端口校验先保证引用，previous 只来自同 Lab 原行。

    所有显式字段严验；仅受影响的探头声明重新检查所选相邻 pair，绝不拼所有
    入出边的笛卡尔积。未知方向可存草稿，运行门由 internal_transition 独立执行。
    """
    old_nodes = {node['id']: node for node in previous_nodes or []}
    old_edges = {edge['id']: edge for edge in previous_connections or []}
    by_node, by_edge = {node['id']: node for node in nodes}, {edge['id']: edge for edge in connections}
    changed_nodes = {ident for ident, node in by_node.items() if ident not in old_nodes or
                     not same_json(_node_contract(node), _node_contract(old_nodes[ident]))}
    changed_edges = {ident for ident in by_edge.keys() | old_edges.keys() if
        ident not in by_edge or ident not in old_edges or
        not same_json(_edge_contract(by_edge[ident]), _edge_contract(old_edges[ident]))}
    before_modes = _effective_modes(previous_modes or [], previous_connections or [])
    after_modes = _effective_modes(modes, connections)
    mode_changed_edges = set()
    for mode in before_modes.keys() | after_modes.keys():
        mode_changed_edges.update(before_modes.get(mode, set()) ^ after_modes.get(mode, set()))
    for node in nodes:
        _validate_declaration(node)
    for probe in nodes:
        declaration = (probe.get('params') or {}).get('rf_path_selection')
        if probe.get('type') != 'probe' or declaration is None:
            continue
        # 原结构门已经证明序列连续、无环且是合法 CE→probe。
        edges = [by_edge[ident] for ident in declaration['connection_ids']]
        path = [by_node[edges[0]['source']]] + [by_node[edge['target']] for edge in edges]
        path_ids, edge_ids = {node['id'] for node in path}, {edge['id'] for edge in edges}
        incident_change = False
        for mode in before_modes.keys() | after_modes.keys():
            before, after = before_modes.get(mode, set()), after_modes.get(mode, set())
            if not (edge_ids <= before or edge_ids <= after):
                continue
            touched = (changed_edges & (before | after)) | (before ^ after)
            if any(edge.get(end) in path_ids for ident in touched
                   for edge in (by_edge.get(ident, {}), old_edges.get(ident, {}))
                   for end in ('source', 'target')):
                incident_change = True
                break
        affected = (any(node['id'] in changed_nodes for node in path) or
                    any(edge['id'] in changed_edges | mode_changed_edges for edge in edges) or incident_change)
        if not affected:
            continue
        for index, node in enumerate(path[1:-1], 1):
            params = node.get('params') or {}
            try:
                if 'internal_paths' not in params:
                    old = (old_nodes.get(node['id'], {}).get('params') or {})
                    # 模板缺声明保形；开关继续由原显式 switch_mappings/port_maps 负责。
                    if (allow_legacy_missing and 'internal_paths' not in old or
                            node.get('type') == 'switch_slot' and 'internal_paths' not in old):
                        continue
                    raise ValueError(f"器件 {node['id']} 内部通路未声明或被主动撤销")
                source, target = _saved_pins(node, edges[index - 1], edges[index])
                if {'from_port': source, 'to_port': target} not in params['internal_paths']:
                    raise ValueError(f"器件 {node['id']} 未声明内部通路 {source}→{target}")
                _check_known_direction(node, source, target)
            except ValueError as exc:
                raise ValueError(f"探头 {probe['id']} 连线 {edges[index - 1]['id']}/{edges[index]['id']}：{exc}") from exc
