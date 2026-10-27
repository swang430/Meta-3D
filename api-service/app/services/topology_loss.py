"""拓扑量值源：未知不补零，归属只换源，不改变物理身份。"""
from app.schemas.topology_loss_ownership import OWNER_KEY, ownership_groups
from app.schemas.topology_internal_paths import validate_internal_traversals


def effective_connection_loss(connection: dict) -> float | None:
    value = connection.get('calibrated_loss_db')
    if value is None:
        value = connection.get('cable_loss_db')
    return None if value is None else float(value)


def loss_sources_for_path(nodes: list[dict], connections: list[dict], selected_ids: list[str]) -> list[dict]:
    by_id = {edge['id']: edge for edge in connections}
    if (len(by_id) != len(connections) or len(selected_ids) != len(set(selected_ids))
            or any(ident not in by_id for ident in selected_ids)):
        raise ValueError('损耗路径包含重复或缺失连线')
    selected = set(selected_ids)
    for alias,owner,node,incoming,outgoing in ownership_groups(nodes,connections):
        ids={alias['id'],owner['id']}
        if not ids & selected:
            continue
        if not ids <= selected or selected_ids.index(outgoing['id']) != selected_ids.index(incoming['id']) + 1:
            raise ValueError(f'损耗归属 {alias["id"]}/{owner["id"]} 必须完整位于同一所选路径')
        validate_internal_traversals([{},node,{}],[incoming,outgoing],active_connections=connections)
    result, seen = [],set()
    for ident in selected_ids:
        edge=by_id[ident]
        source=by_id[edge[OWNER_KEY]] if OWNER_KEY in edge else edge
        if source['id'] not in seen:
            result.append(source);seen.add(source['id'])
    return result


def loss_source_for_terminal(nodes, connections, selected_ids) -> dict:
    loss_sources_for_path(nodes,connections,selected_ids)
    if not selected_ids:
        raise ValueError('损耗路径为空')
    by_id={edge['id']:edge for edge in connections}
    terminal=by_id[selected_ids[-1]]
    return by_id[terminal[OWNER_KEY]] if OWNER_KEY in terminal else terminal
