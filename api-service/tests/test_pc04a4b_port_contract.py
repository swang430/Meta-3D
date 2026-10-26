"""端口写契约通过真实 HTTP 验证；错误写入不能改变原图或默认位。"""
import copy
import json

import pytest

from tests.test_p1_57_topology_lab_context import client, setup_database, world, _mk_row


def graph():
    return dict(nodes=[dict(id='a', type='pad', label='DL不是角色', params={'ports': ['out']}),
                       dict(id='b', type='pad', label='B', params={'ports': ['in']})],
                connections=[dict(id='ab', source='a', source_pin='out', target='b', target_pin='in')],
                operating_modes=[])


def seed(world, data=None, *, default=False):
    row = _mk_row(world['db'], world['switch_id'], world['chamber_a'].id)
    for key, value in (data or graph()).items():
        setattr(row, key, copy.deepcopy(value))
    row.is_default = default
    world['db'].commit()
    return row, f'/api/v1/switch-topologies/{row.id}', {'lab_profile_id': str(world['lab_a'].id)}


def post(world, data):
    return client.post('/api/v1/switch-topologies', json={**data, 'name': '新图',
        'switch_category_id': str(world['switch_id']), 'lab_profile_id': str(world['lab_a'].id)})


@pytest.mark.parametrize('fault', ['missing_ports', 'orphan', 'bse_conflict', 'invalid_enum'])
def test_post_rejects_new_contract_errors_before_default_write(world, fault):
    keep, url, scope = seed(world, default=True)
    data = graph()
    params = data['nodes'][0]['params']
    if fault == 'missing_ports':
        params.pop('ports')
    elif fault == 'orphan':
        params['port_directions'] = {'missing': 'output'}
    elif fault == 'bse_conflict':
        data['nodes'][0]['type'] = 'communication_tester'
        params.update(port_roles={'out': 'dl'}, port_directions={'out': 'input'})
    else:
        params['port_directions'] = {'out': 'DL'}
    response = post(world, {**data, 'is_default': True})
    assert response.status_code == 422, response.text
    assert 'a' in str(response.json()['detail'])
    assert client.get(url, params=scope).json()['is_default'] is True
    world['db'].refresh(keep)
    assert keep.is_default and keep.name == 'Row'
    assert world['db'].query(type(keep)).count() == 1


def test_patch_rejects_output_to_output_before_name_or_default_write(world):
    keep, keep_url, scope = seed(world, default=True)
    row, url, _ = seed(world)
    data = graph()
    data['nodes'][0]['params']['port_directions'] = {'out': 'output'}
    data['nodes'][1]['params']['port_directions'] = {'in': 'output'}
    response = client.patch(url, params=scope, json={**data, 'name': '禁止写入', 'is_default': True})
    assert response.status_code == 422, response.text
    assert 'ab' in str(response.json()['detail'])
    assert client.get(keep_url, params=scope).json()['is_default'] is True
    assert client.get(url, params=scope).json()['name'] == 'Row'
    world['db'].refresh(row)
    world['db'].refresh(keep)
    assert row.nodes == graph()['nodes'] and row.name == 'Row' and not row.is_default
    assert keep.is_default


def test_import_explicit_error_does_not_replace_existing(world, monkeypatch):
    from app.api import switch_topology as api
    row, url, scope = seed(world, default=True)
    data = graph()
    data['nodes'][0]['params']['port_directions'] = {'out': 'bad'}
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: {**data, 'name': '错误模板'})
    response = client.post('/api/v1/switch-topologies/import/from-template', params={**scope,
        'switch_category_id': str(world['switch_id']), 'template_id': 'bad', 'replace_existing': True})
    assert response.status_code == 422, response.text
    assert client.get(url, params=scope).json()['is_default'] is True
    world['db'].refresh(row)
    assert row.name == 'Row' and row.nodes == graph()['nodes']


@pytest.mark.parametrize('source,target,allowed', [
    ('input', 'input', False), ('input', 'output', False),
    ('input', 'bidirectional', False), ('input', 'unknown', False),
    ('output', 'input', True), ('output', 'output', False),
    ('output', 'bidirectional', True), ('output', 'unknown', True),
    ('bidirectional', 'input', True), ('bidirectional', 'output', False),
    ('bidirectional', 'bidirectional', True), ('bidirectional', 'unknown', True),
    ('unknown', 'input', True), ('unknown', 'output', False),
    ('unknown', 'bidirectional', True), ('unknown', 'unknown', True),
])
def test_all_sixteen_effective_direction_pairs(world, source, target, allowed):
    data = graph()
    data['connections'][0]['direction'] = 'UL'  # 业务标签不反转接线次序。
    for node, pin, direction in zip(data['nodes'], ('out', 'in'), (source, target)):
        node['params']['port_directions'] = {pin: direction}
    response = post(world, data)
    assert response.status_code == (201 if allowed else 422), response.text
    if allowed:
        assert response.json()['nodes'][0]['params']['port_directions'] == {'out': source}


@pytest.mark.parametrize('ports', [None, [], {}, 'out', [True], [1], [''], [' out'], ['out '], ['out', 'out']])
def test_new_port_ids_are_strict(world, ports):
    data = graph()
    data['nodes'][0]['params']['ports'] = ports
    assert post(world, data).status_code == 422


@pytest.mark.parametrize('directions', [None, [], True, 1, '', {'out': True}, {'out': 1},
    {'out': []}, {'out': ''}, {'out': 'OUTPUT'}, {'OUT': 'output'}])
def test_direction_map_is_strict_and_case_sensitive(world, directions):
    data = graph()
    data['nodes'][0]['params']['port_directions'] = directions
    assert post(world, data).status_code == 422


@pytest.mark.parametrize('kind', ['communication_tester', 'bse_port'])
@pytest.mark.parametrize('role,direction,status', [('dl', 'unknown', 201), ('dl', 'output', 201),
    ('dl', 'input', 422), ('dl', 'bidirectional', 422), ('ul', 'input', 422),
    ('ul', 'output', 422), ('ul', 'bidirectional', 422)])
def test_bse_roles_are_authoritative_at_both_node_types(world, kind, role, direction, status):
    data = graph()
    data['nodes'][0].update(type=kind, params={'ports': ['out'], 'port_roles': {'out': role},
                                          'port_directions': {'out': direction}})
    assert post(world, data).status_code == status


@pytest.mark.parametrize('roles', [None, [], {'out': 'unknown'}, {'missing': 'dl'}, {'out': True}])
def test_bse_role_map_rejects_explicit_bad_declarations(world, roles):
    data = graph()
    data['nodes'][0].update(type='bse_port', params={'ports': ['out'], 'port_roles': roles})
    assert post(world, data).status_code == 422


def test_partial_maps_case_distinct_ids_and_nonbse_extensions_do_not_guess_roles(world):
    data = graph()
    data['nodes'][0]['params'] = {'ports': ['out', 'OUT', 'DL1'],
        'port_directions': {'OUT': 'input'}, 'port_roles': {'out': 'ul'}, 'inputs': 100, 'outputs': 200}
    response = post(world, data)
    assert response.status_code == 201, response.text
    assert response.json()['nodes'][0]['params'] == data['nodes'][0]['params']
    assert 'port_directions' not in response.json()['nodes'][1]['params']


@pytest.mark.parametrize('edit', ['name', 'label', 'position', 'roundtrip', 'edge_nominal'])
def test_legacy_missing_ports_unrelated_edits_preserve_sparse_json(world, edit):
    data = graph()
    for node in data['nodes']:
        node['params'] = {'opaque': {'keep': True}}
    for key in ('source_pin', 'target_pin'):
        data['connections'][0].pop(key)
    row, url, scope = seed(world, data)
    before = json.dumps(row.connections)
    fetched = client.get(url, params=scope).json()
    payload = {'name': '仅改名'}
    if edit in ('label', 'position', 'roundtrip'):
        payload = {key: fetched[key] for key in ('nodes', 'connections', 'operating_modes')}
        if edit == 'label':
            payload['nodes'][0]['label'] = '新标签'
        if edit == 'position':
            payload['nodes'][0]['position'] = {'x': 1, 'y': 2}
    elif edit == 'edge_nominal':
        payload = {'connections': [{**fetched['connections'][0], 'pa_gain_db': 0, 'modes': ['calibration']}]}
    response = client.patch(url, params=scope, json=payload)
    assert response.status_code == 200, response.text
    world['db'].refresh(row)
    assert all(node['params'] == {'opaque': {'keep': True}} for node in row.nodes)
    assert 'source_pin' not in row.connections[0] and 'target_pin' not in row.connections[0]
    if edit != 'edge_nominal':
        assert json.dumps(row.connections) == before


@pytest.mark.parametrize('change', ['new_edge', 'new_node', 'type', 'directions', 'ports', 'pin'])
def test_legacy_exemption_cannot_cover_new_or_reconnected_graph(world, change):
    data = graph()
    for node in data['nodes']:
        node['params'] = {}
    row, url, scope = seed(world, data)
    changed = copy.deepcopy(data)
    if change == 'new_edge':
        changed['connections'].append({**changed['connections'][0], 'id': 'new'})
    elif change == 'new_node':
        changed['nodes'].append(dict(id='new', type='pad', label='new', params={}))
    elif change == 'type':
        changed['nodes'][0]['type'] = 'amplifier'
    elif change == 'directions':
        changed['nodes'][0]['params']['port_directions'] = {}
    elif change == 'ports':
        changed['nodes'][0]['params']['ports'] = ['out']
    else:
        changed['connections'][0]['source_pin'] = 'other'
    response = client.patch(url, params=scope, json=changed)
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.nodes == data['nodes'] and row.connections == data['connections']


@pytest.mark.parametrize('partial', [True, False])
def test_changed_node_checks_all_incident_edges_across_modes(world, partial):
    data = graph()
    data['nodes'].append(dict(id='c', type='pad', label='校准端', params={'ports': ['in']}))
    data['connections'].append(dict(id='ac', source='a', source_pin='out', target='c', target_pin='in', modes=['calibration']))
    row, url, scope = seed(world, data)
    nodes = copy.deepcopy(data['nodes'])
    nodes[0]['params']['port_directions'] = {'out': 'input'}
    payload = {'nodes': nodes} if partial else {**data, 'nodes': nodes}
    response = client.patch(url, params=scope, json=payload)
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.nodes == data['nodes']


@pytest.mark.parametrize('map_value', [{}, {'out': 'unknown'}, None])
def test_clearing_generic_map_does_not_clear_bse_role(world, map_value):
    data = graph()
    data['nodes'][0].update(type='bse_port', params={'ports': ['out'], 'port_roles': {'out': 'ul'},
                                                 'port_directions': {'out': 'input'}})
    row, url, scope = seed(world, data)
    nodes = copy.deepcopy(data['nodes'])
    if map_value is None:
        nodes[0]['params'].pop('port_directions')
    else:
        nodes[0]['params']['port_directions'] = map_value
    response = client.patch(url, params=scope, json={'nodes': nodes})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.nodes == data['nodes']


def test_real_legacy_caict_import_roundtrip_does_not_materialize_ports(world):
    scope = {'lab_profile_id': str(world['lab_a'].id)}
    response = client.post('/api/v1/switch-topologies/import/from-template', params={**scope,
        'switch_category_id': str(world['switch_id']), 'template_id': 'caict_v4'})
    assert response.status_code == 200, response.text
    raw = response.json()
    legacy = [node for node in raw['nodes'] if 'ports' not in node['params']]
    assert legacy, '必须覆盖真实旧版未声明节点，不能用补齐模板冒充兼容'
    payload = {key: raw[key] for key in ('nodes', 'connections', 'operating_modes')}
    payload['name'] = '旧版无关保存'
    saved = client.patch(f"/api/v1/switch-topologies/{raw['id']}", params=scope, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()['nodes'] == raw['nodes']


def test_parser_reports_effective_direction_and_provenance_without_name_guessing():
    from app.schemas.topology_ports import resolve_port_direction
    assert resolve_port_direction({'type': 'bse_port', 'params': {'port_roles': {'RF5': 'dl'},
        'port_directions': {'RF5': 'unknown'}}}, 'RF5') == ('output', 'BSE')
    assert resolve_port_direction({'type': 'pad', 'params': {'port_directions': {'p': 'bidirectional'}}},
                                  'p') == ('bidirectional', 'explicit')
    assert resolve_port_direction({'type': 'pad', 'params': {'port_roles': {'DL1': 'dl'}}},
                                  'DL1') == ('unknown', 'unknown')


@pytest.mark.parametrize('kind', ['channel_emulator', 'emcenter', 'amplifier', 'combiner',
    'signal_analyzer', 'vna', 'termination', 'air_path', 'cable'])
def test_no_new_device_kind_gets_implicit_ports(world, kind):
    data = dict(nodes=[dict(id='new', type=kind, label='器件', params={
        'inputs': 4, 'outputs': 32, 'num_ports': 36})], connections=[], operating_modes=[])
    assert post(world, data).status_code == 422


def test_new_sparse_connection_uses_declared_ports_without_persisting_default_pins(world):
    data = graph()
    data['connections'] = [dict(id='sparse', source='a', target='b')]
    saved = post(world, data)
    assert saved.status_code == 201, saved.text
    assert saved.json()['connections'] == data['connections']


def test_port_removal_rejection_locates_referencing_edge(world):
    row, url, scope = seed(world)
    nodes = copy.deepcopy(row.nodes)
    nodes[0]['params']['ports'] = ['replacement']
    response = client.patch(url, params=scope, json={'nodes': nodes})
    assert response.status_code == 422, response.text
    assert all(token in str(response.json()['detail']) for token in ('ab', 'a', 'out'))
    world['db'].refresh(row)
    assert row.nodes == graph()['nodes']


@pytest.mark.parametrize('kind,key,value,status', [
    ('pad', 'port_directions', {}, 200),
    ('bse_port', 'port_directions', {}, 200),
    ('bse_port', 'port_roles', {}, 200),
    ('pad', 'port_directions', {'out': 'output'}, 422),
    ('bse_port', 'port_roles', {'out': 'dl'}, 422),
    ('pad', 'port_directions', None, 422),
    ('pad', 'port_directions', [], 422),
    ('bse_port', 'port_roles', None, 422),
    ('bse_port', 'port_roles', [], 422),
])
def test_import_missing_ports_allows_only_empty_or_absent_maps(world, monkeypatch, kind, key, value, status):
    from app.api import switch_topology as api
    payload = dict(name='旧缺声明', nodes=[dict(id='legacy', type=kind, label='旧节点',
        params={key: value})], connections=[], operating_modes=[])
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: payload)
    response = client.post('/api/v1/switch-topologies/import/from-template', params={
        'lab_profile_id': str(world['lab_a'].id), 'switch_category_id': str(world['switch_id']),
        'template_id': 'legacy'})
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()['nodes'][0]['params'] == {key: {}}
    else:
        from app.models.switch_topology import SwitchTopology
        assert world['db'].query(SwitchTopology).count() == 0
