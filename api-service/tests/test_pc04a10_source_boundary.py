"""CE源端以保存端口/pair为边界；恢复节点入度门或裁剪模式边必须使本测试失败。"""
import copy

import pytest

from app.services.declared_rf_routes import resolve_saved_rf_path
from app.services.mimo_ota.switch_orchestrator import _build_probe_binding


def node(ident, kind, directions, **params):
    return dict(id=ident, type=kind, label='B1.1' if ident == 'ce' else ident,
        params=dict(ports=list(directions), port_directions=directions, **params))


def edge(ident, source, source_pin, target, target_pin):
    return dict(id=ident, source=source, source_pin=source_pin, target=target,
        target_pin=target_pin, modes=['mimo_ota'])


def boundary_graph(*, explicit=False, pa=False, ce_type='ce_port'):
    nodes = [node('ce', ce_type, {'B1.1': 'output', 'input1': 'input', 'input2': 'input'}, ce_port='B1.1'),
        node('p', 'probe', {'in': 'input'}, probe_id=0, polarization='V'),
        node('bse', 'communication_tester', {'DL': 'output', 'UL': 'input'},
            port_roles={'DL': 'dl', 'UL': 'ul'}),
        node('link', 'antenna', {'rf': 'output'})]
    edges = [edge('terminal', 'ce', 'B1.1', 'p', 'in'),
        edge('feed', 'bse', 'DL', 'ce', 'input1'),
        edge('uplink', 'link', 'rf', 'bse', 'UL')]
    if pa:
        nodes.append(node('pa', 'amplifier', {'in': 'input', 'out': 'output'},
            internal_paths=[dict(from_port='in', to_port='out')]))
        edges[0]['source'], edges[0]['source_pin'] = 'pa', 'out'
        edges.insert(0, edge('ce-pa', 'ce', 'B1.1', 'pa', 'in'))
    if explicit:
        nodes[1]['params']['rf_path_selection'] = dict(
            connection_ids=['ce-pa', 'terminal'] if pa else ['terminal'], switch_mappings=[])
    return nodes, edges


def resolve(nodes, edges, consumer):
    if consumer == 'shared':
        return resolve_saved_rf_path(nodes, edges, 'terminal')
    binding = _build_probe_binding(next(e for e in edges if e['id'] == 'terminal'),
        {n['id']: n for n in nodes}, edges)
    assert binding.ce_port == 'B1.1'
    assert binding.connection_id == 'terminal'
    assert [p['connection_id'] for p in binding.execution_route_identity['ports']] == (
        ['ce-pa', 'terminal'] if any(n['id'] == 'pa' for n in nodes) else
        ['ce-x', 'terminal'] if any(n['id'] == 'x' for n in nodes) else ['terminal'])
    return binding


@pytest.mark.parametrize('consumer', ['shared', 'execution'])
@pytest.mark.parametrize('ce_type', ['ce_port', 'channel_emulator'])
@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize('pa', [False, True])
def test_declared_independent_input_and_bse_ul_do_not_become_output_return(consumer, ce_type, explicit, pa):
    nodes, edges = boundary_graph(explicit=explicit, pa=pa, ce_type=ce_type)
    before = copy.deepcopy((nodes, edges))
    result = resolve(nodes, edges, consumer)
    if consumer == 'shared':
        path_nodes, path_edges = result
        assert [n['id'] for n in path_nodes] == (['ce', 'pa', 'p'] if pa else ['ce', 'p'])
        assert [e['id'] for e in path_edges] == (['ce-pa', 'terminal'] if pa else ['terminal'])
    assert (nodes, edges) == before


@pytest.mark.parametrize('consumer', ['shared', 'execution'])
@pytest.mark.parametrize('ce_type', ['ce_port', 'channel_emulator'])
@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize('pa', [False, True])
@pytest.mark.parametrize('fault', ['unknown_input', 'bidir_input', 'unknown_output', 'missing_input_pin',
    'missing_output_pin', 'missing_source_pin', 'outside_ports', 'source_ul', 'bse_conflict',
    'fake_bse_name', 'selected_output', 'other_output', 'duplicate_input'])
def test_unproven_or_conflicting_source_boundary_is_rejected(consumer, ce_type, explicit, pa, fault):
    nodes, edges = boundary_graph(explicit=explicit, pa=pa, ce_type=ce_type)
    ce, bse = nodes[0], nodes[2]
    feed = next(e for e in edges if e['id'] == 'feed')
    first = edges[0]
    if fault == 'unknown_input': ce['params']['port_directions'].pop('input1')
    elif fault == 'bidir_input': ce['params']['port_directions']['input1'] = 'bidirectional'
    elif fault == 'unknown_output': ce['params']['port_directions'].pop('B1.1')
    elif fault == 'missing_input_pin': feed.pop('target_pin')
    elif fault == 'missing_output_pin': first.pop('source_pin')
    elif fault == 'missing_source_pin': feed.pop('source_pin')
    elif fault == 'outside_ports': feed['source_pin'] = 'invented'
    elif fault == 'source_ul': feed['source_pin'] = 'UL'
    elif fault == 'bse_conflict': bse['params']['port_directions']['DL'] = 'input'
    elif fault == 'fake_bse_name':
        bse['type'] = 'cable'; bse['params'].pop('port_directions')
    elif fault == 'selected_output': feed['target_pin'] = 'B1.1'
    elif fault == 'other_output':
        ce['params']['ports'].append('B1.2'); ce['params']['port_directions']['B1.2'] = 'output'
        feed['target_pin'] = 'B1.2'
    else: edges.append({**feed, 'id': 'duplicate-feed'})
    with pytest.raises(ValueError):
        resolve(nodes, edges, consumer)


@pytest.mark.parametrize('consumer', ['shared', 'execution'])
def test_two_inputs_can_share_completed_upstream_source_without_inventing_cycle(consumer):
    nodes, edges = boundary_graph()
    edges.append(edge('feed2', 'bse', 'DL', 'ce', 'input2'))
    resolve(nodes, edges, consumer)


@pytest.mark.parametrize('consumer', ['shared', 'execution'])
@pytest.mark.parametrize('bidirectional', [False, True])
def test_upstream_passive_pair_uses_only_its_saved_input_and_not_unrelated_ports(consumer, bidirectional):
    nodes, edges = boundary_graph()
    nodes.append(node('up', 'combiner', {'a': 'input', 'b': 'output', 'c': 'input', 'd': 'output'},
        internal_paths=[dict(from_port='a', to_port='b'), dict(from_port='c', to_port='d')]))
    if bidirectional:
        nodes[-1]['params']['port_directions'].update(a='bidirectional', b='bidirectional')
    feed = next(e for e in edges if e['id'] == 'feed')
    feed['source'], feed['source_pin'] = 'up', 'b'
    edges += [edge('bse-up', 'bse', 'DL', 'up', 'a'),
        edge('irrelevant', 'link', 'missing', 'up', 'c')]
    resolve(nodes, edges, consumer)


@pytest.mark.parametrize('fault', [None, 'selected_port', 'reachable_selected_pair', 'missing_pair'])
def test_shared_node_independent_pairs_are_not_node_level_return(fault):
    nodes, edges = boundary_graph(explicit=True)
    nodes.append(node('x', 'combiner', {'a': 'input', 'b': 'output', 'c': 'input', 'd': 'output'},
        internal_paths=[dict(from_port='a', to_port='b'), dict(from_port='c', to_port='d')]))
    edges[0].update(source='x', source_pin='b')
    edges.insert(0, edge('ce-x', 'ce', 'B1.1', 'x', 'a'))
    feed = next(e for e in edges if e['id'] == 'feed')
    feed.update(source='x', source_pin='d')
    edges.append(edge('bse-x', 'bse', 'DL', 'x', 'c'))
    nodes[1]['params']['rf_path_selection']['connection_ids'] = ['ce-x', 'terminal']
    if fault == 'selected_port': feed['source_pin'] = 'b'
    elif fault == 'reachable_selected_pair':
        nodes[-1]['params']['internal_paths'].append(dict(from_port='a', to_port='d'))
    elif fault == 'missing_pair': nodes[-1]['params']['internal_paths'].pop()
    if fault:
        with pytest.raises(ValueError): resolve_saved_rf_path(nodes, edges, 'terminal')
    else:
        for consumer in ('shared', 'execution'): resolve(nodes, edges, consumer)


@pytest.mark.parametrize('consumer', ['shared', 'execution'])
@pytest.mark.parametrize('fault', ['cycle', 'return', 'self_output', 'ambiguous', 'missing_pair'])
def test_reachable_upstream_cycle_or_selected_ports_are_rejected(consumer, fault):
    nodes, edges = boundary_graph(pa=True)
    nodes += [node(n, 'cable', {'in': 'input', 'out': 'output'},
        internal_paths=[dict(from_port='in', to_port='out')]) for n in ('a', 'b')]
    feed = next(e for e in edges if e['id'] == 'feed')
    feed.update(source='a', source_pin='out')
    edges.append(edge('b-a', 'b', 'out', 'a', 'in'))
    if fault == 'cycle': edges.append(edge('a-b', 'a', 'out', 'b', 'in'))
    elif fault == 'return': edges.append(edge('pa-b', 'pa', 'out', 'b', 'in'))
    elif fault == 'self_output': edges.append(edge('ce-b', 'ce', 'B1.1', 'b', 'in'))
    else:
        edges.append(edge('bse-b', 'bse', 'DL', 'b', 'in'))
        if fault == 'ambiguous': edges.append(edge('duplicate', 'bse', 'DL', 'b', 'in'))
        else: nodes[-1]['params']['internal_paths'] = []
    with pytest.raises(ValueError): resolve(nodes, edges, consumer)


@pytest.mark.parametrize('consumer', ['shared', 'execution'])
@pytest.mark.parametrize('pa', [False, True])
def test_no_ce_input_keeps_legacy_direction_compatibility(consumer, pa):
    nodes, edges = boundary_graph(pa=pa)
    edges = [e for e in edges if e['id'] not in ('feed', 'uplink')]
    nodes[0]['params'] = {}
    resolve(nodes, edges, consumer)
