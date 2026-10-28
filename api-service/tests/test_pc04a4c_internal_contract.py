"""内部通路写入必须经真实 HTTP 校验，且拒绝前不改变原图。"""
from tests.topology_revision_requests import saved_revision as _saved_revision
import copy
import json

import pytest

from tests.test_pc04a4b_port_contract import client, setup_database, world, graph, post, seed


def test_post_rejects_internal_reference_outside_ports(world):
    payload = graph()
    payload['nodes'][0]['params']['internal_paths'] = [
        {'from_port': 'missing', 'to_port': 'out'}]
    response = post(world, payload)
    assert response.status_code == 422, response.text
    assert 'a' in str(response.json()['detail'])


def declared_graph(kind='pad', *, unknown=False):
    return dict(nodes=[
        dict(id='ce', type='ce_port', label='CE', params={'ports': ['out']}),
        dict(id='a', type=kind, label='器件', params={'ports': ['IN', 'OUT'],
            'port_directions': {'IN': 'unknown' if unknown else 'input', 'OUT': 'output'},
            'internal_paths': [{'from_port': 'IN', 'to_port': 'OUT'}], 'opaque': {'keep': None}}),
        dict(id='p', type='probe', label='探头', params={'ports': ['in'], 'probe_id': 1,
            'polarization': 'V', 'rf_path_selection': {'connection_ids': ['ca', 'ap'], 'switch_mappings': []}})],
        connections=[dict(id='ca', source='ce', source_pin='out', target='a', target_pin='IN', modes=['normal']),
                     dict(id='ap', source='a', source_pin='OUT', target='p', target_pin='in', modes=['normal'])],
        operating_modes=[dict(id='normal', name='正常', active_connections=[])])


@pytest.mark.parametrize('value', [None, True, 1, {}, '', [None], [True], [1], [[]], [{}],
    [{'from_port': 'IN'}], [{'from_port': 'IN', 'to_port': 'OUT', 'gain_db': 1}],
    [{'from_port': True, 'to_port': 'OUT'}], [{'from_port': 1, 'to_port': 'OUT'}],
    [{'from_port': '', 'to_port': 'OUT'}], [{'from_port': ' IN', 'to_port': 'OUT'}],
    [{'from_port': 'IN', 'to_port': 'OUT '}], [{'from_port': 'in', 'to_port': 'OUT'}],
    [{'from_port': 'IN', 'to_port': 'IN'}],
    [{'from_port': 'IN', 'to_port': 'OUT'}, {'from_port': 'IN', 'to_port': 'OUT'}]])
def test_post_invalid_pair_is_atomic_before_default_write(world, value):
    keep, url, scope = seed(world, default=True)
    data = declared_graph()
    data['nodes'][1]['params']['internal_paths'] = value
    response = post(world, {**data, 'is_default': True})
    assert response.status_code == 422, response.text
    assert 'a' in str(response.json()['detail'])
    assert client.get(url, params=scope).json()['is_default'] is True
    world['db'].refresh(keep)
    assert keep.is_default and keep.nodes == graph()['nodes']
    assert world['db'].query(type(keep)).count() == 1


@pytest.mark.parametrize('kind', ['amplifier', 'pad', 'cable', 'receive_cable', 'combiner', 'switch_slot'])
def test_valid_device_declaration_roundtrip_without_defaults(world, kind):
    data = declared_graph(kind)
    # 参考器件和开关在此只验证独立器件声明，不伪造普通执行链。
    data['connections'] = []; data['operating_modes'] = []
    data['nodes'] = data['nodes'][1:2]
    response = post(world, data)
    assert response.status_code == 201, response.text
    assert response.json()['nodes'][0]['params'] == data['nodes'][0]['params']


@pytest.mark.parametrize('kind', ['termination', 'ce_port', 'channel_emulator', 'bse_port',
    'communication_tester', 'sa_port', 'signal_analyzer', 'vna', 'emcenter'])
def test_non_transit_devices_cannot_declare_internal_forwarding(world, kind):
    data = declared_graph(kind)
    data['nodes'] = data['nodes'][1:2]; data['connections'] = []; data['operating_modes'] = []
    assert post(world, data).status_code == 422


@pytest.mark.parametrize('kind', ['amplifier', 'pad', 'cable', 'receive_cable'])
def test_two_port_types_reject_three_ports(world, kind):
    data = declared_graph(kind)
    data['nodes'][1]['params']['ports'].append('EXTRA')
    assert post(world, data).status_code == 422


def test_reverse_pair_must_be_explicit_and_pa_cannot_be_bidirectional(world):
    data = declared_graph('cable')
    params = data['nodes'][1]['params']
    params['port_directions'] = {'IN': 'bidirectional', 'OUT': 'bidirectional'}
    params['internal_paths'].append({'from_port': 'OUT', 'to_port': 'IN'})
    assert post(world, data).status_code == 201
    data['nodes'][1]['type'] = 'amplifier'
    assert post(world, data).status_code == 422


def test_combiner_allows_only_the_two_explicit_input_pairs(world):
    data = declared_graph('combiner')
    params = data['nodes'][1]['params']
    params['ports'] = ['IN', 'IN2', 'OUT']
    params['port_directions']['IN2'] = 'input'
    params['internal_paths'].append({'from_port': 'IN2', 'to_port': 'OUT'})
    response = post(world, data)
    assert response.status_code == 201, response.text
    assert response.json()['nodes'][1]['params'] == params


@pytest.mark.parametrize('edit', ['remove_pair', 'delete_key', 'direction', 'ports', 'type', 'pin'])
def test_patch_rejects_invalidated_selected_pair_without_name_or_default_change(world, edit):
    keep, keep_url, scope = seed(world, default=True)
    data = declared_graph()
    row, url, _ = seed(world, data)
    saved_before = client.get(url, params=scope).json()['nodes']
    changed = copy.deepcopy(data)
    params = changed['nodes'][1]['params']
    if edit == 'remove_pair': params['internal_paths'] = []
    elif edit == 'delete_key': params.pop('internal_paths')
    elif edit == 'direction': params['port_directions']['IN'] = 'output'
    elif edit == 'ports': params['ports'].remove('IN')
    elif edit == 'type': changed['nodes'][1]['type'] = 'termination'
    else: changed['connections'][0]['target_pin'] = 'OUT'
    response = client.patch(url, params=scope, json={**({**changed, 'name': '不能写', 'is_default': True}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == 422, response.text
    assert 'a' in str(response.json()['detail'])
    assert client.get(url, params=scope).json()['nodes'] == saved_before
    assert client.get(keep_url, params=scope).json()['is_default'] is True
    world['db'].refresh(row); world['db'].refresh(keep)
    assert row.name == 'Row' and not row.is_default and row.nodes == data['nodes']
    assert row.connections == data['connections'] and keep.is_default
    assert world['db'].query(type(row)).count() == 2


def test_bad_template_pair_does_not_replace_existing(world, monkeypatch):
    from app.api import switch_topology as api
    row, url, scope = seed(world, default=True)
    saved_before = client.get(url, params=scope).json()['nodes']
    data = declared_graph(); data['nodes'][1]['params']['internal_paths'] = []
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: {**data, 'name': '错误模板'})
    response = client.post('/api/v1/switch-topologies/import/from-template', params={**scope,
        'switch_category_id': str(world['switch_id']), 'template_id': 'bad', 'replace_existing': True})
    assert response.status_code == 422, response.text
    assert client.get(url, params=scope).json()['nodes'] == saved_before
    world['db'].refresh(row)
    assert row.is_default and row.name == 'Row' and row.nodes == graph()['nodes']
    assert world['db'].query(type(row)).count() == 1


def test_unknown_declaration_saves_draft_but_runtime_helper_rejects(world):
    from app.schemas.topology_internal_paths import validate_internal_traversals
    data = declared_graph(unknown=True)
    response = post(world, data)
    assert response.status_code == 201, response.text
    assert response.json()['nodes'][1]['params'] == data['nodes'][1]['params']
    with pytest.raises(ValueError, match='方向未声明'):
        validate_internal_traversals(data['nodes'], data['connections'], active_connections=data['connections'])


def test_missing_key_and_empty_are_distinct_and_empty_draft_can_save(world):
    data = declared_graph(); data['nodes'][2]['params'].pop('rf_path_selection')
    data['nodes'][1]['params']['internal_paths'] = []
    response = post(world, data)
    assert response.status_code == 201, response.text
    assert response.json()['nodes'][1]['params']['internal_paths'] == []
    assert 'internal_paths' not in response.json()['nodes'][0]['params']


@pytest.mark.parametrize('edit', ['name', 'position', 'nominal', 'roundtrip'])
def test_unrelated_legacy_roundtrip_keeps_sparse_pins_and_missing_declaration(world, edit):
    data = declared_graph(); data['nodes'][1]['params'].pop('internal_paths')
    data['nodes'][1]['params'].pop('ports'); data['nodes'][1]['params'].pop('port_directions')
    data['nodes'][2]['params'].pop('rf_path_selection')
    data['connections'][0].pop('target_pin'); data['connections'][1].pop('source_pin')
    row, url, scope = seed(world, data)
    before = json.dumps(row.connections)
    fetched = client.get(url, params=scope).json()
    body = {'name': '无关改名'}
    if edit in ('position', 'roundtrip'):
        body = {key: fetched[key] for key in ('nodes', 'connections', 'operating_modes')}
        if edit == 'position': body['nodes'][1]['position'] = {'x': 3, 'y': 2}
    elif edit == 'nominal':
        body = {'nodes': copy.deepcopy(data['nodes'])}
        body['nodes'][1]['params']['gain_db'] = None
    response = client.patch(url, params=scope, json={**(body), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == 200, response.text
    world['db'].refresh(row)
    assert 'internal_paths' not in row.nodes[1]['params']
    assert json.dumps(row.connections) == before


@pytest.mark.parametrize('fallback', [True, False])
def test_all_modes_protect_selected_pair_even_when_current_mode_unrelated(world, fallback):
    data = declared_graph()
    data['operating_modes'] = [dict(id='view', name='当前', active_connections=[]),
        dict(id='normal', name='非当前', active_connections=[] if fallback else ['ca', 'ap'])]
    row, url, scope = seed(world, data)
    nodes = copy.deepcopy(data['nodes']); nodes[1]['params']['internal_paths'] = []
    response = client.patch(url, params=scope, json={**({'nodes': nodes}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == 422, response.text
    assert 'p' in str(response.json()['detail']) and 'a' in str(response.json()['detail'])
    world['db'].refresh(row)
    assert row.nodes == data['nodes']


def test_enabling_mode_or_probe_selection_cannot_borrow_legacy_exemption(world):
    data = declared_graph(); data['nodes'][1]['params'].pop('internal_paths')
    data['operating_modes'][0]['active_connections'] = ['ca']
    row, url, scope = seed(world, data)
    response = client.patch(url, params=scope, json={**({'operating_modes': [
        dict(id='normal', name='启用', active_connections=['ca', 'ap'])]}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.operating_modes == data['operating_modes']


def test_original_legacy_selected_route_unrelated_edit_preserves_declaration(world):
    data = declared_graph(); data['nodes'][1]['params'].pop('internal_paths')
    row, url, scope = seed(world, data)
    response = client.patch(url, params=scope, json={**({'name': '兼容旧图'}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == 200, response.text
    world['db'].refresh(row)
    assert row.nodes == data['nodes'] and row.connections == data['connections']


def test_nonbse_opaque_role_extension_does_not_redeclare_legacy_path(world):
    data = declared_graph(); data['nodes'][1]['params'].pop('internal_paths')
    row, url, scope = seed(world, data)
    nodes = copy.deepcopy(data['nodes'])
    nodes[1]['params']['port_roles'] = {'opaque': {'keep': True}}
    response = client.patch(url, params=scope, json={**({'nodes': nodes}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == 200, response.text
    world['db'].refresh(row)
    assert row.nodes[1]['params']['port_roles'] == {'opaque': {'keep': True}}
    assert 'internal_paths' not in row.nodes[1]['params']


@pytest.mark.parametrize('kind', ['amplifier', 'pad', 'cable', 'receive_cable'])
def test_runtime_legacy_whitelist_requires_real_two_port_evidence(kind):
    from app.schemas.topology_internal_paths import internal_transition
    node = declared_graph(kind)['nodes'][1]; node['params'].pop('internal_paths')
    assert internal_transition(node, 'IN', 'OUT', incoming_count=1, outgoing_count=1) == 'legacy'
    for source, target, count in [(None, 'OUT', 1), ('IN', None, 1), ('IN', 'IN', 1), ('IN', 'OUT', 2)]:
        with pytest.raises(ValueError):
            internal_transition(node, source, target, incoming_count=count, outgoing_count=1)
    node['params'].pop('ports')
    with pytest.raises(ValueError):
        internal_transition(node, 'IN', 'OUT', incoming_count=1, outgoing_count=1)


def test_runtime_declared_membership_termination_and_sparse_pins_are_not_inferred():
    from app.schemas.topology_internal_paths import internal_transition, validate_internal_traversals
    data = declared_graph()
    assert validate_internal_traversals(data['nodes'], data['connections'],
        active_connections=data['connections']) == [{'node_id': 'a', 'from_port': 'IN', 'to_port': 'OUT'}]
    for source, target in [('OUT', 'IN'), ('IN', 'IN')]:
        with pytest.raises(ValueError):
            internal_transition(data['nodes'][1], source, target, incoming_count=1, outgoing_count=1)
    data['connections'][0].pop('target_pin')
    with pytest.raises(ValueError, match='ca'):
        validate_internal_traversals(data['nodes'], data['connections'], active_connections=data['connections'])
    node = declared_graph()['nodes'][1]; node['type'] = 'termination'; node['params'].pop('internal_paths')
    with pytest.raises(ValueError, match='负载'):
        internal_transition(node, 'IN', 'OUT', incoming_count=1, outgoing_count=1)


@pytest.mark.parametrize('same_mode', [True, False])
def test_new_incident_branch_rechecks_only_same_mode_legacy_selection(world, same_mode):
    data = declared_graph(); data['nodes'][1]['params'].pop('internal_paths')
    data['nodes'].append(dict(id='q', type='probe', label='另一端', params={'ports': ['in']}))
    row, url, scope = seed(world, data)
    changed = copy.deepcopy(data)
    changed['connections'].append(dict(id='aq', source='a', source_pin='OUT', target='q', target_pin='in',
        modes=['normal' if same_mode else 'other']))
    changed['operating_modes'].append(dict(id='other', name='其它模式', active_connections=[]))
    response = client.patch(url, params=scope, json={**(changed), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == (422 if same_mode else 200), response.text
    world['db'].refresh(row)
    assert row.connections == (data if same_mode else changed)['connections']


def test_two_mode_combiner_does_not_invent_cross_mode_pairs(world):
    data = declared_graph('combiner')
    params = data['nodes'][1]['params']
    params['ports'] += ['IN2', 'OUT2']
    params['port_directions'].update(IN2='input', OUT2='output')
    params['internal_paths'].append({'from_port': 'IN2', 'to_port': 'OUT2'})
    data['nodes'].append(dict(id='q', type='probe', label='另一模式探头', params={'ports': ['in'],
        'probe_id': 2, 'polarization': 'H',
        'rf_path_selection': {'connection_ids': ['ca2', 'aq'], 'switch_mappings': []}}))
    data['connections'] += [dict(id='ca2', source='ce', source_pin='out', target='a', target_pin='IN2', modes=['other']),
        dict(id='aq', source='a', source_pin='OUT2', target='q', target_pin='in', modes=['other'])]
    data['operating_modes'].append(dict(id='other', name='其他', active_connections=[]))
    response = post(world, data)
    assert response.status_code == 201, response.text
    assert response.json()['nodes'][1]['params']['internal_paths'] == params['internal_paths']
