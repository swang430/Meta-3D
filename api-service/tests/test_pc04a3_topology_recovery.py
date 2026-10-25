"""PC04A3：真实保存入口拒绝损坏显式声明，历史读取保持不变。"""
import copy

import pytest
from tests.test_p1_57_topology_lab_context import client, setup_database, world, _mk_row


def explicit_graph():
    return dict(nodes=[
        dict(id='ce', type='ce_port', label='B1.1', params={'ports': ['out']}),
        dict(id='c', type='cable', label='线缆', params={'ports': ['A', 'B']}),
        dict(id='p', type='probe', label='探头', params={'ports': ['in'], 'probe_id': 0,
             'polarization': 'V', 'rf_path_selection': {'connection_ids': ['a', 'b'], 'switch_mappings': []}})],
        connections=[dict(id='a', source='ce', source_pin='out', target='c', target_pin='A'),
                     dict(id='b', source='c', source_pin='B', target='p', target_pin='in')],
        operating_modes=[dict(id='mimo_ota', name='正常', active_connections=['a', 'b'])])


def save_graph(world, graph=None):
    row = _mk_row(world['db'], world['switch_id'], world['chamber_a'].id)
    for key, value in (graph or explicit_graph()).items():
        setattr(row, key, copy.deepcopy(value))
    world['db'].commit()
    return row


def patch(world, row, changed):
    return client.patch(f'/api/v1/switch-topologies/{row.id}',
        params={'lab_profile_id': str(world['lab_a'].id)}, json=changed)


@pytest.mark.parametrize('remove_middle', [False, True])
def test_patch_rejects_dangling_explicit_path_atomically(world, remove_middle):
    before = explicit_graph()
    row = save_graph(world, before)
    changed = copy.deepcopy(before)
    changed['connections'] = [] if remove_middle else changed['connections'][1:]
    changed['operating_modes'][0]['active_connections'] = [] if remove_middle else ['b']
    if remove_middle:
        changed['nodes'] = [n for n in changed['nodes'] if n['id'] != 'c']
    response = patch(world, row, changed)
    assert response.status_code == 422, response.text
    assert 'p' in str(response.json()['detail'])
    world['db'].refresh(row)
    assert {key: getattr(row, key) for key in before} == before


@pytest.mark.parametrize('declaration', [
    {'connection_ids': ['a', 'a', 'b'], 'switch_mappings': []},
    {'connection_ids': ['missing', 'b'], 'switch_mappings': []},
    {'connection_ids': ['b', 'a'], 'switch_mappings': []},
    {'connection_ids': ['a'], 'switch_mappings': []},
    {'connection_ids': ['a', 'b'], 'switch_mappings': [{'node_id': 'c', 'path_name': 'stale'}]},
    {'connection_ids': ['a', 'b'], 'switch_mappings': [{'node_id': [], 'path_name': 'bad'}]},
    {'connection_ids': ['a', 'b'], 'switch_mappings': None},
    [],
])
def test_invalid_declaration_is_rejected_without_partial_write(world, declaration):
    before = explicit_graph()
    row = save_graph(world, before)
    changed = copy.deepcopy(before)
    changed['nodes'][-1]['params']['rf_path_selection'] = declaration
    response = patch(world, row, {**changed, 'name': '不得写入'})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.name == 'Row'
    assert {key: getattr(row, key) for key in before} == before


def test_create_rejects_bad_declaration(world):
    graph = explicit_graph()
    graph['nodes'][-1]['params']['rf_path_selection']['connection_ids'] = ['missing']
    response = client.post('/api/v1/switch-topologies', json={**graph, 'name': '坏声明',
        'switch_category_id': str(world['switch_id']), 'lab_profile_id': str(world['lab_a'].id)})
    assert response.status_code == 422, response.text
    from app.models.switch_topology import SwitchTopology
    assert world['db'].query(SwitchTopology).count() == 0


def test_import_rejects_bad_declaration_before_replacement(world, monkeypatch):
    from app.api import switch_topology
    row = save_graph(world)
    graph = explicit_graph()
    graph['nodes'][-1]['params']['rf_path_selection']['connection_ids'] = ['missing']
    monkeypatch.setattr(switch_topology, '_load_template', lambda _: lambda: {**graph, 'name': '坏模板'})
    response = client.post('/api/v1/switch-topologies/import/from-template', params={
        'switch_category_id': str(world['switch_id']), 'lab_profile_id': str(world['lab_a'].id),
        'template_id': 'bad', 'replace_existing': True})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.name == 'Row' and row.nodes == explicit_graph()['nodes']


def test_partial_name_patch_validates_merged_history_but_get_stays_readable(world):
    graph = explicit_graph()
    graph['nodes'][-1]['params']['rf_path_selection']['connection_ids'] = ['missing']
    row = save_graph(world, graph)
    response = client.get(f'/api/v1/switch-topologies/{row.id}', params={'lab_profile_id': str(world['lab_a'].id)})
    assert response.status_code == 200, response.text
    response = patch(world, row, {'name': '不得写入'})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.name == 'Row' and row.nodes == graph['nodes']


def test_atomic_rewire_and_delete_probe_are_allowed(world):
    row = save_graph(world)
    graph = explicit_graph()
    for edge in graph['connections']:
        edge['id'] += '-new'
    graph['nodes'][-1]['params']['rf_path_selection']['connection_ids'] = ['a-new', 'b-new']
    graph['operating_modes'][0]['active_connections'] = ['a-new', 'b-new']
    response = patch(world, row, graph)
    assert response.status_code == 200, response.text
    assert response.json()['nodes'][-1]['params']['rf_path_selection']['connection_ids'] == ['a-new', 'b-new']
    graph['nodes'] = graph['nodes'][:-1]
    graph['connections'] = graph['connections'][:1]
    graph['operating_modes'][0]['active_connections'] = ['a-new']
    response = patch(world, row, graph)
    assert response.status_code == 200, response.text
    assert all(node['id'] != 'p' for node in response.json()['nodes'])


@pytest.mark.parametrize('declared', [False, True])
def test_old_graph_and_other_mode_branches_remain_editable(world, declared):
    graph = explicit_graph()
    if not declared:
        del graph['nodes'][-1]['params']['rf_path_selection']
    graph['connections'].append(dict(id='other', source='ce', source_pin='out', target='c', target_pin='B'))
    graph['operating_modes'].append(dict(id='other', name='其他', active_connections=['other']))
    row = save_graph(world, graph)
    response = patch(world, row, {'name': '允许修改'})
    assert response.status_code == 200, response.text
    assert response.json()['name'] == '允许修改'


def test_physical_cable_loss_is_not_counted_twice():
    from app.services.topology_service import TopologyService
    graph = explicit_graph()
    graph['nodes'][1]['params'].update(cable_loss_db=20, unknown_loss_db=30)
    graph['connections'][0]['cable_loss_db'] = 0
    graph['connections'][1]['cable_loss_db'] = 2
    service = TopologyService(graph)
    assert service.resolve_paths('mimo_ota')[0].total_loss_db == 2
    matrix = service.get_calibration_matrix('mimo_ota')
    assert next(iter(matrix.values()))['total_loss_db'] == 2
    graph['connections'][1]['calibrated_loss_db'] = 1.5
    assert TopologyService(graph).resolve_paths('mimo_ota')[0].total_loss_db == 1.5
