"""操作员明确的同线缆量值归属；不推定物理实物或测量资格。"""
from .topology_nominal import MISSING, same_json
from .topology_internal_paths import _effective_modes

OWNER_KEY = 'loss_owner_connection_id'


def ownership_groups(nodes, connections):
    """验证最小两边引用结构，返回(alias, owner, 中转节点)。"""
    by_id = {edge['id']: edge for edge in connections}
    by_node = {node['id']: node for node in nodes}
    used, groups = set(), []
    for alias in connections:
        if OWNER_KEY not in alias:
            continue
        ident, owner_id = alias['id'], alias[OWNER_KEY]
        if (not isinstance(owner_id, str) or not owner_id or owner_id.strip() != owner_id
                or owner_id == ident or owner_id not in by_id):
            raise ValueError(f'损耗归属 {ident}/{owner_id} 必须引用另一条已保存连线')
        owner = by_id[owner_id]
        if OWNER_KEY in owner or ident in used or owner_id in used:
            raise ValueError(f'损耗归属 {ident}/{owner_id} 不允许环、级联或重复分组')
        adjacent = [(a, b) for a,b in ((alias,owner),(owner,alias))
                    if a.get('target') == b.get('source') and
                    by_node.get(a.get('target'),{}).get('type') in {'cable','receive_cable'}]
        if len(adjacent) != 1:
            raise ValueError(f'损耗归属 {ident}/{owner_id} 必须是同一线缆节点的一入一出两侧')
        incoming,outgoing = adjacent[0]
        used.update((ident,owner_id))
        groups.append((alias,owner,by_node[incoming['target']],incoming,outgoing))
    return groups


def validate_loss_owner_write(nodes, connections, modes, *, previous_connections=None):
    groups = ownership_groups(nodes, connections)
    effective = _effective_modes(modes,connections)
    previous = {edge['id']:edge for edge in previous_connections or []}
    current_ids = {edge['id'] for edge in connections}
    for ident, edge in previous.items():
        if OWNER_KEY in edge and ident not in current_ids:
            raise ValueError(f'损耗归属 {ident}/{edge[OWNER_KEY]} 须先显式撤销引用，再删除连线或线缆')
    for alias,owner,node,incoming,outgoing in groups:
        ids = {alias['id'],owner['id']}
        for mode, active in effective.items():
            if ids & active and not ids <= active:
                raise ValueError(f'模式 {mode} 损耗归属 {alias["id"]}/{owner["id"]} 不能仅激活半组')
        old = previous.get(alias['id'])
        if old and any(not same_json(alias.get(key,MISSING),old.get(key,MISSING))
                for key in ('cable_loss_db','calibrated_loss_db')):
            raise ValueError(f'连线 {alias["id"]} 的旧损耗不参与归属 {owner["id"]}，请先解组或编辑owner')
