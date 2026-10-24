"""本片结构校验通过真实 API 和数据库验证，不触及硬件。"""
import copy

import pytest
from tests.test_p1_57_topology_lab_context import (
    client, setup_database, world, _mk_row,
)


def graph():
    return {"nodes": [{"id": n, "type": "pad", "label": n, "params": {"ports": ["in", "out"]}} for n in ("a", "b")],
            "connections": [{"id": "ab", "source": "a", "target": "b", "source_pin": "out", "target_pin": "in"}],
            "operating_modes": [{"id": "mimo_ota", "name": "测试", "active_connections": ["ab"]}]}


@pytest.fixture
def saved(world):
    row = _mk_row(world['db'], world['switch_id'], world['chamber_a'].id)
    for key, value in graph().items():
        setattr(row, key, value)
    world['db'].commit()
    return row


@pytest.mark.parametrize('change', [
    {"nodes": [graph()['nodes'][0], graph()['nodes'][0]]},
    {"connections": graph()['connections'] * 2},
    {"operating_modes": graph()['operating_modes'] * 2},
    {"nodes": [graph()['nodes'][1]]},
    {"operating_modes": [{"id": "x", "name": "坏引用", "active_connections": ["missing"]}]},
    {"nodes": None},
    {"nodes": [{**graph()['nodes'][0], "params": {"ports": ["in"]}}, graph()['nodes'][1]]},
])
def test_patch_rejects_invalid_merged_graph_without_mutation(world, saved, change):
    before = copy.deepcopy(saved.nodes), copy.deepcopy(saved.connections), copy.deepcopy(saved.operating_modes)
    response = client.patch(f'/api/v1/switch-topologies/{saved.id}', params={'lab_profile_id': str(world['lab_a'].id)}, json=change)
    assert response.status_code == 422, response.text
    world['db'].refresh(saved)
    assert (saved.nodes, saved.connections, saved.operating_modes) == before


def test_patch_allows_atomic_delete_and_valid_partial_update(world, saved):
    url = f'/api/v1/switch-topologies/{saved.id}'
    params = {'lab_profile_id': str(world['lab_a'].id)}
    response = client.patch(url, params=params, json={'name': '局部修改'})
    assert response.status_code == 200, response.text
    assert response.json()['connections'][0]['id'] == 'ab'
    response = client.patch(url, params=params, json={'nodes': [graph()['nodes'][1]], 'connections': [], 'operating_modes': []})
    assert response.status_code == 200, response.text
    assert [n['id'] for n in response.json()['nodes']] == ['b']


def test_create_rejects_invalid_structure(world):
    response = client.post('/api/v1/switch-topologies', json={**graph(), 'nodes': [], 'name': '坏图', 'switch_category_id': str(world['switch_id']), 'lab_profile_id': str(world['lab_a'].id)})
    assert response.status_code == 422, response.text


def test_import_rejects_bad_template_before_replacement(world, saved, monkeypatch):
    from app.api import switch_topology
    monkeypatch.setattr(switch_topology, '_load_template', lambda _: lambda: {**graph(), 'nodes': [], 'name': '坏模板'})
    response = client.post('/api/v1/switch-topologies/import/from-template', params={'switch_category_id': str(world['switch_id']), 'lab_profile_id': str(world['lab_a'].id), 'template_id': 'bad', 'replace_existing': True})
    assert response.status_code == 422, response.text
    world['db'].refresh(saved)
    assert saved.name == 'Row'


def test_calibration_scope_cannot_enter_normal_active_connections(world, saved):
    nodes = graph()['nodes']
    nodes[0]['params']['connection_scope'] = 'calibration'
    response = client.patch(f'/api/v1/switch-topologies/{saved.id}', params={'lab_profile_id': str(world['lab_a'].id)}, json={'nodes': nodes})
    assert response.status_code == 422, response.text
    response = client.patch(f'/api/v1/switch-topologies/{saved.id}', params={'lab_profile_id': str(world['lab_a'].id)}, json={'nodes': nodes, 'operating_modes': [{'id': 'calibration', 'name': '校准接线', 'active_connections': ['ab']}]})
    assert response.status_code == 200, response.text
    assert response.json()['operating_modes'][0]['active_connections'] == ['ab']


def test_historical_invalid_graph_still_readable(world, saved):
    saved.nodes = []
    world['db'].commit()
    response = client.get(f'/api/v1/switch-topologies/{saved.id}', params={'lab_profile_id': str(world['lab_a'].id)})
    assert response.status_code == 200, response.text
    assert response.json()['connections'][0]['id'] == 'ab'


def test_calibration_scope_rejected_in_effective_connection_mode_fallback(world, saved):
    nodes = graph()['nodes']
    nodes[0]['type'] = 'ce_port'
    nodes[1]['type'] = 'probe'
    nodes[1]['params']['connection_scope'] = 'calibration'
    connections = [{**graph()['connections'][0], 'modes': ['mimo_ota']}]
    modes = [{'id': 'mimo_ota', 'name': '正常测试', 'active_connections': []}]
    # 此输入在原解析器确实会成为路径和矩阵，不是仅检查字段存在。
    from app.services.topology_service import TopologyService
    service = TopologyService({'nodes': nodes, 'connections': connections, 'operating_modes': modes})
    assert len(service.resolve_paths('mimo_ota')) == 1
    assert service.get_calibration_matrix('mimo_ota')
    before = copy.deepcopy(saved.nodes), copy.deepcopy(saved.connections), copy.deepcopy(saved.operating_modes)
    response = client.patch(f'/api/v1/switch-topologies/{saved.id}', params={'lab_profile_id': str(world['lab_a'].id)}, json={'nodes': nodes, 'connections': connections, 'operating_modes': modes})
    assert response.status_code == 422, response.text
    world['db'].refresh(saved)
    assert (saved.nodes, saved.connections, saved.operating_modes) == before


def test_calibration_only_fallback_remains_available_without_normal_paths(world, saved):
    nodes = graph()['nodes']
    nodes[0]['type'] = 'ce_port'
    nodes[1]['type'] = 'probe'
    nodes[1]['params']['connection_scope'] = 'calibration'
    connections = [{**graph()['connections'][0], 'modes': ['calibration']}]
    modes = [{'id': ident, 'name': ident, 'active_connections': []} for ident in ('mimo_ota', 'calibration')]
    url = f'/api/v1/switch-topologies/{saved.id}'
    params = {'lab_profile_id': str(world['lab_a'].id)}
    response = client.patch(url, params=params, json={'nodes': nodes, 'connections': connections, 'operating_modes': modes})
    assert response.status_code == 200, response.text
    normal_paths = client.get(f'{url}/paths/mimo_ota', params=params)
    normal_matrix = client.get(f'{url}/calibration-matrix/mimo_ota', params=params)
    calibration_paths = client.get(f'{url}/paths/calibration', params=params)
    assert normal_paths.status_code == normal_matrix.status_code == calibration_paths.status_code == 200
    assert normal_paths.json() == []
    assert normal_matrix.json()['matrix'] == {}
    assert len(calibration_paths.json()) == 1
