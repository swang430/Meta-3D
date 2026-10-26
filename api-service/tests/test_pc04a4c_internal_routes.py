"""内部通路必须在真实保存图的三类运行查询生效，不访问仪器。"""
import copy

import pytest

from tests.test_pc04a2_route_selection import (
    client, configured, graph, paths, db_session, chamber, topology_two_chains, lab_profile)
from app.models.diagnostic_run import DiagnosticRun
from app.services.topology_service import TopologyService
from tests.test_pc06a1_batch_plan import shared_switch


def declared(node, pairs=None):
    node['params'].update(ports=['in', 'out'],
        port_directions={'in': 'input', 'out': 'output'},
        internal_paths=[{'from_port': 'in', 'to_port': 'out'}] if pairs is None else pairs)


@pytest.mark.parametrize('kind', ['switch_slot', 'combiner'])
@pytest.mark.parametrize('fault', ['none', 'selected_pair', 'bad_declaration', 'missing_pin',
                                  'unknown_pin', 'direction', 'termination', 'selection_empty',
                                  'selection_missing_edge', 'selection_wrong_terminal',
                                  'selection_terminal_removed', 'selection_terminal_retargeted'])
def test_validate_distinguishes_unselected_cross_pair_from_real_structure_errors(
        client, configured, shared_switch, db_session, kind, fault):
    topo, _ = shared_switch
    nodes, edges = copy.deepcopy(topo.nodes), copy.deepcopy(topo.connections)
    node = next(row for row in nodes if row['id'] == 'sw')
    node['type'] = kind
    node['params'].update(ports=['in1', 'in2', 'out1', 'out2'],
        port_directions={'in1': 'input', 'in2': 'input', 'out1': 'output', 'out2': 'output'},
        internal_paths=[{'from_port': 'in1', 'to_port': 'out1'}, {'from_port': 'in2', 'to_port': 'out2'}])
    if kind == 'combiner':
        for probe in nodes:
            if probe['type'] == 'probe':
                probe['params']['rf_path_selection']['switch_mappings'] = []
    if fault == 'selected_pair':
        node['params']['internal_paths'].pop(0)
    elif fault == 'bad_declaration':
        node['params']['internal_paths'][0]['gain_db'] = 1
    elif fault == 'missing_pin':
        del edges[0]['target_pin']
    elif fault == 'unknown_pin':
        edges[0]['target_pin'] = 'not-a-port'
    elif fault == 'direction':
        node['params']['port_directions']['in1'] = 'output'
    elif fault == 'termination':
        node['type'] = 'termination'
        node['params']['internal_paths'] = []
    elif fault == 'selection_terminal_removed':
        edges.pop(2)
        modes = copy.deepcopy(topo.operating_modes)
        modes[0]['active_connections'].remove('ov')
        topo.operating_modes = modes
    elif fault == 'selection_terminal_retargeted':
        edges[2]['target'] = 'ph'
    elif fault.startswith('selection_'):
        probe = next(row for row in nodes if row['id'] == 'pv')
        probe['params']['rf_path_selection']['connection_ids'] = {
            'selection_empty': [], 'selection_missing_edge': ['missing', 'ov'],
            'selection_wrong_terminal': ['ih', 'oh']}[fault]
    topo.nodes, topo.connections = nodes, edges
    db_session.commit()
    before = copy.deepcopy(topo.connections)
    response = client.get(f'/api/v1/switch-topologies/{topo.id}/validate',
        params={'lab_profile_id': str(configured.id)})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['is_valid'] is (fault == 'none'), value
    errors = [issue for issue in value['issues'] if issue['severity'] == 'error']
    if fault == 'none':
        assert errors == []
        public = client.get(f'/api/v1/switch-topologies/{topo.id}/paths/mimo_ota',
            params={'lab_profile_id': str(configured.id)})
        assert public.status_code == 200 and len(public.json()) == 2, public.text
    else:
        assert any(issue['node_id'] in ('sw', 'pv') for issue in errors), value
    db_session.refresh(topo)
    assert topo.connections == before


def complete_reference(graph):
    nodes, edges = copy.deepcopy(graph.nodes), copy.deepcopy(graph.connections)
    nodes[4]['params']['ports'] = ['in', 'out']
    edges[3]['target_pin'], edges[4]['source_pin'] = 'in', 'out'
    graph.nodes, graph.connections = nodes, edges


@pytest.mark.parametrize('explicit', [True, False])
def test_actual_saved_pins_restore_public_paths_and_loss(client, configured, graph, db_session, explicit):
    nodes = copy.deepcopy(graph.nodes[:3])
    declared(nodes[1])
    if not explicit:
        del nodes[1]['params']['internal_paths']
    graph.nodes, graph.connections = nodes, copy.deepcopy(graph.connections[:2])
    graph.operating_modes = graph.operating_modes[:1]
    db_session.commit()
    base = f'/api/v1/switch-topologies/{graph.id}'
    params = {'lab_profile_id': str(configured.id)}
    response = client.get(base + '/paths/mimo_ota', params=params)
    assert response.status_code == 200, response.text
    assert [row['path_id'] for row in response.json()] == ['ce1_to_probe1v']
    assert 'ce1_to_probe1v' in client.get(base + '/calibration-matrix/mimo_ota', params=params).json()['matrix']
    assert TopologyService(graph.__dict__).get_end_to_end_loss('ce1', 'probe1v') == 0


@pytest.mark.parametrize('entry', ['ordinary', 'individual', 'explicit'])
def test_reference_pair_checked_in_all_route_entrypoints(client, configured, graph, db_session, entry):
    complete_reference(graph)
    nodes = copy.deepcopy(graph.nodes)
    declared(nodes[4], [])
    graph.nodes = nodes
    db_session.commit()
    if entry == 'ordinary':
        response = paths(client, configured, graph)
        assert response.status_code == 422, response.text
        assert 'rx-cable1' in str(response.json()['detail'])
    else:
        from app.services.calibration.route_calibration import (
            list_individual_route_selections, resolve_explicit_route_selection)
        with pytest.raises(ValueError, match='rx-cable1'):
            if entry == 'individual':
                list_individual_route_selections(db_session, configured.id, graph.id, 'mimo_ota')
            else:
                resolve_explicit_route_selection(db_session, configured.id, graph.id, 'mimo_ota',
                    'pad-probe', ['ce-pad', 'pad-probe'])


@pytest.mark.parametrize('fault', ['ports', 'incoming_pin', 'outgoing_pin'])
def test_legacy_reference_cable_requires_actual_ports_and_pins(client, configured, graph, db_session, fault):
    nodes, edges = copy.deepcopy(graph.nodes), copy.deepcopy(graph.connections)
    if fault == 'ports':
        del nodes[4]['params']['ports']
    elif fault == 'incoming_pin':
        del edges[3]['target_pin']
    else:
        del edges[4]['source_pin']
    graph.nodes, graph.connections = nodes, edges
    db_session.commit()
    before = copy.deepcopy(graph.connections)
    response = paths(client, configured, graph)
    assert response.status_code == 422, response.text
    assert 'rx-cable1' in str(response.json()['detail'])
    db_session.refresh(graph)
    assert graph.connections == before

@pytest.mark.parametrize('fault', ['empty', 'unknown', 'dirty', 'load', 'three_ports'])
def test_actual_target_rejects_invalid_internal_pair(client, configured, graph, db_session, fault):
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    nodes = copy.deepcopy(graph.nodes)
    declared(nodes[1])
    if fault == 'empty':
        nodes[1]['params']['internal_paths'] = []
    elif fault == 'unknown':
        del nodes[1]['params']['port_directions']
    elif fault == 'dirty':
        nodes[1]['params']['internal_paths'] = None
    elif fault == 'load':
        nodes[1]['type'] = 'termination'
    else:
        nodes[1]['params']['ports'].append('third')
        del nodes[1]['params']['internal_paths']
    graph.nodes = nodes
    db_session.commit()
    with pytest.raises(ValueError, match='pad1'):
        orchestrate_switch_topology(db_session, configured.chamber_config_id)


def branch_graph(*, selected=True):
    nodes = [dict(id='ce1', type='ce_port', label='B1.1', params={'ports': ['out']}),
        dict(id='pa', type='amplifier', params={}), dict(id='pad', type='pad', params={}),
        dict(id='comb', type='combiner', params={'ports': ['in', 'other', 'out'],
            'port_directions': {'in': 'input', 'other': 'input', 'out': 'output'},
            'internal_paths': [{'from_port': 'in', 'to_port': 'out'}, {'from_port': 'other', 'to_port': 'out'}]}),
        dict(id='p', type='probe', params={'ports': ['in'], 'probe_id': 0, 'polarization': 'V'}),
        dict(id='ce2', type='ce_port', label='B1.2', params={'ports': ['out']})]
    declared(nodes[1]); declared(nodes[2])
    edges = [dict(id='a', source='ce1', source_pin='out', target='pa', target_pin='in'),
        dict(id='b', source='pa', source_pin='out', target='pad', target_pin='in'),
        dict(id='c', source='pad', source_pin='out', target='comb', target_pin='in'),
        dict(id='d', source='comb', source_pin='out', target='p', target_pin='in'),
        dict(id='other', source='ce2', source_pin='out', target='comb', target_pin='other')]
    if selected:
        nodes[4]['params']['rf_path_selection'] = {'connection_ids': ['a', 'b', 'c', 'd'], 'switch_mappings': []}
    for node in nodes:
        node.setdefault('label', node['id'])
    return dict(name='内部通路实际链', nodes=nodes, connections=edges,
        operating_modes=[dict(id='mimo_ota', name='正常', active_connections=[e['id'] for e in edges])])


def test_real_post_patch_selects_only_declared_combiner_branch(client, configured, db_session, topology_two_chains):
    data = branch_graph()
    data.update(lab_profile_id=str(configured.id), switch_category_id=str(topology_two_chains.switch_category_id))
    response = client.post('/api/v1/switch-topologies', params={'lab_profile_id': str(configured.id)}, json=data)
    assert response.status_code == 201, response.text
    graph_id = response.json()['id']
    params = {'lab_profile_id': str(configured.id)}
    public = client.get(f'/api/v1/switch-topologies/{graph_id}/paths/mimo_ota', params=params)
    assert public.status_code == 200, public.text
    assert [r['path_id'] for r in public.json()] == ['ce1_to_p']
    routes = client.get(f'/api/v1/lab-profiles/{configured.id}/route-calibration-paths',
        params={'topology_id': graph_id, 'operating_mode': 'mimo_ota'})
    assert routes.status_code == 200, routes.text
    assert routes.json()[0]['connection_ids'] == ['a', 'b', 'c', 'd']
    assert routes.json()[0]['ce_port'] == 'B1.1'
    changed = copy.deepcopy(data)
    changed['nodes'][4]['params']['rf_path_selection']['connection_ids'] = ['other', 'd']
    patched = client.patch(f'/api/v1/switch-topologies/{graph_id}', params=params,
        json={'nodes': changed['nodes']})
    assert patched.status_code == 200, patched.text
    public = client.get(f'/api/v1/switch-topologies/{graph_id}/paths/mimo_ota', params=params)
    assert [r['path_id'] for r in public.json()] == ['ce2_to_p']


@pytest.mark.parametrize('selected', [False, True])
def test_same_endpoint_diamond_requires_selection_not_matrix_overwrite(client, configured, graph, db_session, selected):
    data = branch_graph(selected=selected)
    data['connections'][-1]['source'] = 'ce1'
    # 同一CE的两条候选最终到同一探头，旧path_id无法区分。
    graph.nodes, graph.connections, graph.operating_modes = data['nodes'], data['connections'], data['operating_modes']
    db_session.commit()
    base = f'/api/v1/switch-topologies/{graph.id}'
    for endpoint in ('paths', 'calibration-matrix'):
        response = client.get(base + f'/{endpoint}/mimo_ota', params={'lab_profile_id': str(configured.id)})
        assert response.status_code == (200 if selected else 422), response.text
        if not selected:
            assert '显式' in str(response.json()['detail'])


def test_bfs_keeps_input_port_state_and_termination_never_expands():
    data = branch_graph(selected=False)
    data['nodes'][3]['params']['internal_paths'] = [{'from_port': 'other', 'to_port': 'out'}]
    assert TopologyService(data).get_end_to_end_loss('ce1', 'p') is None
    assert TopologyService(data).get_end_to_end_loss('ce2', 'p') == 0
    data['nodes'][3]['type'] = 'termination'
    data['nodes'][3]['params']['internal_paths'] = []
    assert TopologyService(data).get_end_to_end_loss('ce2', 'comb') == 0
    assert TopologyService(data).get_end_to_end_loss('ce2', 'p') is None


@pytest.mark.parametrize('cross_modes', [False, True])
def test_bfs_uses_one_effective_mode_not_union_counts_or_cross_mode_wiring(cross_modes):
    data = dict(nodes=[dict(id='ce', type='ce_port'), dict(id='other', type='ce_port'),
        dict(id='pad', type='pad', params={'ports': ['in', 'out']}), dict(id='p', type='probe')],
        connections=[dict(id='i', source='ce', source_pin='out', target='pad', target_pin='in'),
            dict(id='o', source='pad', source_pin='out', target='p', target_pin='in'),
            dict(id='other', source='other', source_pin='out', target='pad', target_pin='in')],
        operating_modes=[dict(id='normal', active_connections=['i'] if cross_modes else ['i', 'o']),
            dict(id='alternate', active_connections=['o'] if cross_modes else ['other', 'o'])])
    if cross_modes:
        data['connections'].pop()
    assert TopologyService(data).get_end_to_end_loss('ce', 'p') == (None if cross_modes else 0)


def test_validate_keeps_dangling_edge_diagnostics_with_internal_checks():
    data = branch_graph()
    data['connections'][0]['source'] = 'missing'
    issues = TopologyService(data).validate()
    assert any(issue.connection_id == 'a' and 'missing' in issue.message for issue in issues)


def test_saved_probe_selection_also_constrains_bfs_and_inactive_mode(client, configured, graph, db_session):
    data = branch_graph()
    assert TopologyService(data).get_end_to_end_loss('ce2', 'p') is None
    data['operating_modes'][0]['active_connections'] = ['other', 'd']
    graph.nodes, graph.connections, graph.operating_modes = data['nodes'], data['connections'], data['operating_modes']
    db_session.commit()
    response = client.get(f'/api/v1/switch-topologies/{graph.id}/paths/mimo_ota',
        params={'lab_profile_id': str(configured.id)})
    assert response.status_code == 200, response.text
    assert response.json() == []


@pytest.mark.parametrize('kind', ['probe', 'antenna'])
def test_normal_probe_is_endpoint_not_internal_transit_even_with_pair(client, configured, graph, db_session, kind):
    nodes, edges = copy.deepcopy(graph.nodes[:3]), copy.deepcopy(graph.connections[:2])
    declared(nodes[2])
    nodes[2]['type'] = kind
    nodes.append(dict(id='final', type='probe', params={'probe_id': 2, 'polarization': 'V'}))
    edges.append(dict(id='probe-forward', source='probe1v', source_pin='out', target='final', target_pin='in'))
    graph.nodes, graph.connections = nodes, edges
    graph.operating_modes = [dict(id='mimo_ota', active_connections=[edge['id'] for edge in edges])]
    db_session.commit()
    response = paths(client, configured, graph, selection_scope='individual')
    assert response.status_code == 422, response.text


def test_invalid_queries_never_fetch_hal_or_create_jobs(client, configured, graph, db_session, monkeypatch):
    from app.services import instrument_hal_service
    def forbidden():
        raise AssertionError('非法图查询不得进入HAL')
    monkeypatch.setattr(instrument_hal_service, 'get_hal_service', forbidden)
    nodes = copy.deepcopy(graph.nodes)
    declared(nodes[1], [])
    graph.nodes = nodes
    db_session.commit()
    assert paths(client, configured, graph).status_code == 422
    base = f'/api/v1/switch-topologies/{graph.id}'
    params = {'lab_profile_id': str(configured.id)}
    assert client.get(base + '/paths/mimo_ota', params=params).json() == []
    assert client.get(base + '/calibration-matrix/mimo_ota', params=params).json()['matrix'] == {}
    assert db_session.query(DiagnosticRun).count() == 0


@pytest.mark.parametrize('segment', ['normal', 'reference'])
def test_changed_pair_invalidates_old_request_and_batch_preview_and_mock_reenters(
        client, configured, graph, db_session, segment):
    from tests.test_pc06a1_batch_plan import request_for
    from tests.test_pc_04a_fixed_route_api import finish
    from app.services.instrument_test_lease import is_test_lease_active
    from app.services.execution_exclusion_guard import active_unsafe_diagnostic
    nodes = copy.deepcopy(graph.nodes)
    declared(nodes[1]); declared(nodes[4])
    for index, ports in ((0, ['out']), (2, ['in', 'out']), (3, ['in', 'out']), (5, ['in'])):
        nodes[index]['params']['ports'] = ports
    edges = copy.deepcopy(graph.connections)
    for edge in edges:
        edge.setdefault('source_pin', 'out')
        edge.setdefault('target_pin', 'in')
    graph.nodes, graph.connections = nodes, edges
    db_session.commit()
    route = paths(client, configured, graph).json()[0]
    selected_digest = paths(client, configured, graph, selection_scope='individual').json()[0]['configuration_digest']
    body = dict(topology_id=str(graph.id), chain_id='pad-probe', route_digest=route['route_digest'],
        configuration_digest=route['configuration_digest'], frequency_mhz=2595, requested_power_dbm=-20,
        reference_antenna='REF1 中心V', receive_cable_loss_db=2, receive_cable_source='2595MHz记录',
        fixed_route_confirmed=True, safety_confirmed=True, sample_count=2)
    batch_root = f'/api/v1/lab-profiles/{configured.id}/route-calibration-batches'
    batch = request_for(graph, chains=('pad-probe',), frequencies=(2595.,)).model_dump(mode='json')
    preview = client.post(batch_root + '/preview', json=batch)
    assert preview.status_code == 200, preview.text
    batch['preview_digest'] = preview.json()['preview_digest']
    nodes, edges = copy.deepcopy(graph.nodes), copy.deepcopy(graph.connections)
    index, edge_index = (1, 0) if segment == 'normal' else (4, 3)
    nodes[index]['params'].update(ports=['new', 'out'], port_directions={'new': 'input', 'out': 'output'},
        internal_paths=[{'from_port': 'new', 'to_port': 'out'}])
    edges[edge_index]['target_pin'] = 'new'
    changed = client.patch(f'/api/v1/switch-topologies/{graph.id}',
        params={'lab_profile_id': str(configured.id)}, json={'nodes': nodes, 'connections': edges})
    assert changed.status_code == 200, changed.text
    route_after = paths(client, configured, graph).json()[0]
    assert route_after['route_digest'] != route['route_digest']
    selected_after = paths(client, configured, graph, selection_scope='individual').json()[0]['configuration_digest']
    assert selected_after != selected_digest
    if segment == 'normal':
        assert route_after['configuration_digest'] != route['configuration_digest']
    else:
        assert route_after['configuration_digest'] == route['configuration_digest']
    fixed_root = f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions'
    assert client.post(fixed_root, json=body).status_code == 422
    assert client.post(batch_root, json=batch, headers={'Idempotency-Key': 'd3932fe5-bd48-4267-a664-5a9f7fca0070'}).status_code == 422
    assert db_session.query(DiagnosticRun).count() == 0
    assert not is_test_lease_active() and active_unsafe_diagnostic() is None
    body.update(route_digest=route_after['route_digest'], configuration_digest=route_after['configuration_digest'])
    histories = []
    for _ in range(2):
        started = client.post(fixed_root, json=body)
        assert started.status_code == 202, started.text
        value = finish(client, configured, started.json()['run_id'])
        assert value['status'] == 'simulated', value
        assert value['result']['samples'] == [] and value['result']['net_loss_db'] is None
        assert value['result']['formal_eligible'] is False
        assert not is_test_lease_active() and active_unsafe_diagnostic() is None
        histories.append((started.json()['run_id'], copy.deepcopy(value['result'])))
    for run_id, snapshot in histories:
        assert client.get(fixed_root + '/' + run_id).json()['result'] == snapshot


@pytest.mark.parametrize('segment', ['normal', 'reference'])
def test_pair_changed_before_control_is_rechecked_without_io(
        client, configured, graph, db_session, monkeypatch, segment):
    from contextlib import asynccontextmanager
    from tests.test_pc_04a_fixed_route_api import start, finish
    from app.services.calibration import fixed_route_jobs as jobs
    from app.models.switch_topology import SwitchTopology
    from app.services.instrument_test_lease import is_test_lease_active
    original = jobs.instrument_test_lease
    @asynccontextmanager
    async def changed_before_remote(*args, **kwargs):
        with jobs.SessionLocal() as db:
            row = db.get(SwitchTopology, graph.id)
            nodes = copy.deepcopy(row.nodes)
            declared(nodes[1 if segment == 'normal' else 4], [])
            row.nodes = nodes
            db.commit()
        async with original(*args, **kwargs) as lease:
            yield lease
    monkeypatch.setattr(jobs, 'instrument_test_lease', changed_before_remote)
    response = start(client, configured, chain_id='pad-probe')
    assert response.status_code == 202, response.text
    value = finish(client, configured, response.json()['run_id'])
    assert value['status'] == 'failed', value
    assert value['result']['exchanges'] == []
    assert value['result']['net_loss_db'] is None
    assert not is_test_lease_active()


def test_declared_splitter_is_not_a_simultaneous_or_batch_switch(client, configured, graph, db_session):
    from app.services.calibration.route_batch_plan import build_batch_plan
    from tests.test_pc06a1_batch_plan import request_for
    nodes = [dict(id='ce', type='ce_port', label='B1.1', params={}),
        dict(id='split', type='combiner', params={'ports': ['in', 'v', 'h'],
            'port_directions': {'in': 'input', 'v': 'output', 'h': 'output'},
            'internal_paths': [{'from_port': 'in', 'to_port': 'v'}, {'from_port': 'in', 'to_port': 'h'}]}),
        dict(id='pv', type='probe', params={'probe_id': 0, 'polarization': 'V',
            'rf_path_selection': {'connection_ids': ['feed', 'v'], 'switch_mappings': []}}),
        dict(id='ph', type='probe', params={'probe_id': 0, 'polarization': 'H',
            'rf_path_selection': {'connection_ids': ['feed', 'h'], 'switch_mappings': []}})]
    edges = [dict(id='feed', source='ce', source_pin='out', target='split', target_pin='in'),
        dict(id='v', source='split', source_pin='v', target='pv', target_pin='in'),
        dict(id='h', source='split', source_pin='h', target='ph', target_pin='in')]
    graph.nodes, graph.connections = nodes, edges
    graph.operating_modes = [dict(id='mimo_ota', active_connections=['feed', 'v', 'h'])]
    db_session.commit()
    assert paths(client, configured, graph).status_code == 422
    with pytest.raises(ValueError, match='互斥开关'):
        build_batch_plan(db_session, configured.id, request_for(graph, chains=('v', 'h'), frequencies=(2595.,)), None)


@pytest.mark.parametrize('fault', ['missing_mapping', 'wrong_pair', 'relay_conflict', 'empty_internal'])
def test_switch_internal_declaration_does_not_replace_mapping_or_interlock(
        configured, shared_switch, db_session, fault):
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    topo, connection = shared_switch
    nodes = copy.deepcopy(topo.nodes)
    switch = next(n for n in nodes if n['id'] == 'sw')
    switch['params'].update(ports=['in1', 'in2', 'out1', 'out2'],
        port_directions={'in1': 'input', 'in2': 'input', 'out1': 'output', 'out2': 'output'},
        internal_paths=[{'from_port': 'in1', 'to_port': 'out1'}, {'from_port': 'in2', 'to_port': 'out2'}])
    topo.nodes = nodes
    db_session.commit()
    actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert [b.ce_port for b in actual.probe_bindings] == ['B1.1', 'B1.2']
    assert all(b.execution_route_identity['internal_paths'] for b in actual.probe_bindings)
    params = copy.deepcopy(connection.connection_params)
    if fault == 'missing_mapping':
        params['port_maps'] = {}
    elif fault == 'wrong_pair':
        params['port_maps']['v']['topology_input_pin'] = 'in2'
    elif fault == 'relay_conflict':
        params['port_maps']['h']['switch_id'] = '1:INT_RELAY_A'
    else:
        nodes = copy.deepcopy(topo.nodes)
        next(n for n in nodes if n['id'] == 'sw')['params']['internal_paths'] = []
        topo.nodes = nodes
    connection.connection_params = params
    db_session.commit()
    with pytest.raises(ValueError):
        orchestrate_switch_topology(db_session, configured.chamber_config_id)


@pytest.mark.parametrize('failure', ['empty', 'reverse', 'termination'])
def test_saved_route_cannot_cross_forbidden_pad(client, configured, graph, db_session, failure):
    nodes = copy.deepcopy(graph.nodes)
    declared(nodes[1], [] if failure == 'empty' else [{'from_port': 'out', 'to_port': 'in'}])
    if failure == 'termination':
        nodes[1]['type'] = 'termination'
        nodes[1]['params']['internal_paths'] = []
    graph.nodes = nodes
    db_session.commit()
    response = paths(client, configured, graph)
    assert response.status_code == 422, response.text
    assert 'pad1' in str(response.json()['detail'])
    assert db_session.query(DiagnosticRun).count() == 0


@pytest.mark.parametrize('missing', ['incoming', 'outgoing', 'both', 'incoming_object'])
@pytest.mark.parametrize('explicit', [True, False])
def test_public_queries_do_not_invent_missing_saved_pins(
        client, configured, graph, db_session, missing, explicit):
    nodes, edges = copy.deepcopy(graph.nodes[:3]), copy.deepcopy(graph.connections[:2])
    declared(nodes[1])
    if not explicit:
        del nodes[1]['params']['internal_paths']
    if missing in ('incoming', 'both'):
        del edges[0]['target_pin']
    if missing in ('outgoing', 'both'):
        del edges[1]['source_pin']
    if missing == 'incoming_object':
        edges[0]['target_pin'] = {'not': 'a saved pin'}
    graph.nodes, graph.connections = nodes, edges
    graph.operating_modes = graph.operating_modes[:1]
    db_session.commit()
    before = copy.deepcopy(graph.connections)
    base = f'/api/v1/switch-topologies/{graph.id}'
    params = {'lab_profile_id': str(configured.id)}
    response = client.get(base + '/paths/mimo_ota', params=params)
    assert response.status_code == 200, response.text
    assert response.json() == []
    matrix = client.get(base + '/calibration-matrix/mimo_ota', params=params)
    assert matrix.status_code == 200, matrix.text
    assert 'ce1_to_probe1v' not in matrix.json()['matrix']
    assert TopologyService(graph.__dict__).get_end_to_end_loss('ce1', 'probe1v') is None
    issues = client.get(base + '/validate', params=params).json()['issues']
    assert any('pad1' in issue['message'] and
        ('ce-pad' in issue['message'] if missing == 'incoming' else 'pad-probe' in issue['message'])
        for issue in issues)
    db_session.refresh(graph)
    assert graph.connections == before
