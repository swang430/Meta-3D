"""纯端口声明解析与写前校验；不访问仪器，不授予执行或硬件资格。"""
from .topology_nominal import MISSING, same_json


PORT_DIRECTIONS = {'input', 'output', 'bidirectional', 'unknown'}
BSE_TYPES = {'communication_tester', 'bse_port'}
# 应用声明的旧/新等价器件类型；不是仪器能力或执行资格白名单。
RF_ENDPOINT_TYPE_GROUPS = (
    frozenset({'ce_port', 'channel_emulator'}),
    frozenset(BSE_TYPES),
    frozenset({'sa_port', 'signal_analyzer'}),
)


def resolve_port_direction(node, port):
    """返回（有效方向，BSE/explicit/unknown）；ID、型号和业务标签不推导方向。"""
    params = node.get('params') or {}
    roles = params.get('port_roles')
    role = roles.get(port) if isinstance(roles, dict) else None
    if node.get('type') in BSE_TYPES and role in ('dl', 'ul'):
        return ('output' if role == 'dl' else 'input', 'BSE')
    directions = params.get('port_directions')
    direction = directions.get(port) if isinstance(directions, dict) else None
    if isinstance(direction, str) and direction in PORT_DIRECTIONS:
        return direction, 'explicit'
    return 'unknown', 'unknown'


def _declaration_changed(node, previous):
    if previous is None or node.get('type') != previous.get('type'):
        return True
    params, old = node.get('params') or {}, previous.get('params') or {}
    keys = ['ports', 'port_directions']
    if node.get('type') in BSE_TYPES:
        keys.append('port_roles')
    return any(not same_json(params.get(key, MISSING), old.get(key, MISSING)) for key in keys)


def _validate_node(node, *, require_ports):
    params = node.get('params') or {}
    ports = params.get('ports', MISSING)
    ident = node['id']
    if ports is MISSING:
        if require_ports:
            raise ValueError(f'器件 {ident} 必须声明非空 ports 端口清单')
        ports = []
    elif (not isinstance(ports, list) or not ports or
          any(not isinstance(p, str) or not p or p.strip() != p for p in ports) or
          len(ports) != len(set(ports))):
        raise ValueError(f'器件 {ident} 的 ports 必须为非空、无首尾空白且唯一的字符串端口清单')
    maps = [('port_directions', PORT_DIRECTIONS)]
    if node.get('type') in BSE_TYPES:
        maps.append(('port_roles', {'dl', 'ul'}))
    for key, values in maps:
        if key not in params:
            continue
        mapping = params[key]
        if not isinstance(mapping, dict):
            raise ValueError(f'器件 {ident} 的 {key} 必须为非 null 对象')
        for port, value in mapping.items():
            if port not in ports or not isinstance(value, str) or value not in values:
                raise ValueError(f'器件 {ident} 端口 {port} 的 {key} 声明无效或未列入 ports')
    if node.get('type') in BSE_TYPES:
        for port, role in params.get('port_roles', {}).items():
            explicit = params.get('port_directions', {}).get(port, 'unknown')
            effective = 'output' if role == 'dl' else 'input'
            if explicit not in ('unknown', effective):
                raise ValueError(f'器件 {ident} 端口 {port} 的 port_directions 与 BSE port_roles 冲突')


def validate_port_write(nodes, connections, *, previous_nodes=None,
                        previous_connections=None, allow_legacy_missing=False):
    """校验最终候选图；previous 仅调用者已按同 Lab 加载的原行。

    旧缺声明只在同 ID、类型及声明未改时兼容。模板入口只豁免缺失 ports，
    不豁免显式坏 map；新增/重接边或声明变化逐条检查全部关联边，不按模式过滤。
    不补默认 ports、pins 或方向，也不修改任何输入 JSON。
    """
    old_nodes = {node['id']: node for node in previous_nodes or []}
    old_edges = {edge['id']: edge for edge in previous_connections or []}
    node_index = {node['id']: node for node in nodes}
    changed = {node['id'] for node in nodes if _declaration_changed(node, old_nodes.get(node['id']))}
    for node in nodes:
        _validate_node(node, require_ports=node['id'] in changed and not allow_legacy_missing)
    for edge in connections:
        previous = old_edges.get(edge['id'])
        reconnect = previous is None or any(
            not same_json(edge.get(key, MISSING), previous.get(key, MISSING))
            for key in ('source', 'source_pin', 'target', 'target_pin'))
        affected = reconnect or edge['source'] in changed or edge['target'] in changed
        if not affected:
            continue
        for end, forbidden, default in (('source', 'input', 'out'), ('target', 'output', 'in')):
            node = node_index[edge[end]]  # 原结构校验先确认节点引用有效。
            port = edge.get(f'{end}_pin', default)
            ports = (node.get('params') or {}).get('ports', MISSING)
            if ports is MISSING and allow_legacy_missing:
                continue
            if not isinstance(ports, list) or port not in ports:
                raise ValueError(f"连线 {edge['id']} 的 {end} 器件 {node['id']} 端口 {port} 未列入显式 ports")
            direction, _ = resolve_port_direction(node, port)
            if direction == forbidden:
                raise ValueError(f"连线 {edge['id']} 的 {end} 器件 {node['id']} 端口 {port} 方向 {direction} 不允许此接线")
