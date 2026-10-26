"""标称写入从真实 HTTP 验证，旧坏值只用于初始化历史记录。"""
import copy
import json
from pathlib import Path

import pytest

from tests.test_p1_57_topology_lab_context import client, setup_database, world, _mk_row

CRUD = {'/api/v1/switch-topologies': ('get', 'post'),
        '/api/v1/switch-topologies/{topology_id}': ('get', 'patch'),
        '/api/v1/switch-topologies/import/from-template': ('post',)}


def test_checked_crud_and_schema_closure_match_live_contract():
    import yaml
    from app.main import app
    checked = yaml.safe_load((Path(__file__).resolve().parents[2] / 'api/openapi.yaml').read_text())
    live = app.openapi()
    seen = set()
    def check_refs(value):
        if isinstance(value, dict):
            ref = value.get('$ref')
            if ref and ref.startswith('#/components/schemas/'):
                name = ref.rsplit('/', 1)[-1]
                if name not in seen:
                    seen.add(name)
                    assert checked['components']['schemas'][name] == live['components']['schemas'][name]
                    check_refs(live['components']['schemas'][name])
            for child in value.values():
                check_refs(child)
        elif isinstance(value, list):
            for child in value:
                check_refs(child)
    for path, methods in CRUD.items():
        for method in methods:
            assert checked['paths'].get(path, {}).get(method) == live['paths'][path][method]
            check_refs(live['paths'][path][method])


def body():
    return dict(nodes=[dict(id='a', type='amplifier', label='PA', params={'ports': ['out']}),
                       dict(id='p', type='probe', label='P', params={'ports': ['in']})],
                connections=[dict(id='ap', source='a', target='p')], operating_modes=[])


def row_and_scope(world, data=None):
    row = _mk_row(world['db'], world['switch_id'], world['chamber_a'].id)
    if data:
        for key, value in data.items():
            setattr(row, key, copy.deepcopy(value))
        world['db'].commit()
    return row, f'/api/v1/switch-topologies/{row.id}', {'lab_profile_id': str(world['lab_a'].id)}


@pytest.mark.parametrize('value', [None, 0, -3.5, 21.25])
def test_pa_edge_roundtrip_keeps_null_zero_and_metadata(world, value):
    row, url, scope = row_and_scope(world)
    payload = body()
    payload['connections'][0].update(pa_gain_db=value, nominal_metadata={'pa_gain_db': {
        'unit': 'dB', 'source_note': None, 'frequency_range_mhz': None}})
    saved = client.patch(url, params=scope, json=payload)
    assert saved.status_code == 200, saved.text
    fetched = client.get(url, params=scope)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()['connections'] == payload['connections']


@pytest.mark.parametrize('kind,key,bad', [
    ('amplifier', 'gain_db', v) for v in [True, '12', [12], {'v': 12}]
] + [('pad', 'attenuation_db', -1), ('combiner', 'loss_db', -0.1),
     ('reference_antenna', 'gain_dbi', False)])
def test_invalid_node_nominal_is_rejected_atomically(world, kind, key, bad):
    row, url, scope = row_and_scope(world)
    response = client.patch(url, params=scope, json={'name': '不应保存', 'nodes': [
        dict(id='a', type=kind, label='器件', params={key: bad})]})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.nodes == [] and row.name == 'Row'


@pytest.mark.parametrize('metadata', [
    {'gain_db': {'unit': 'dBi'}}, {'unknown': {'unit': 'dB'}},
    {'gain_db': {'unit': 'dB', 'source_note': 1}},
    *[{'gain_db': {'unit': 'dB', 'frequency_range_mhz': v}} for v in
      [[1], [2, 1], [0, 2], [-1, 2], [True, 2], ['1', 2], [1, None]]],
    {'gain_db': {'unit': 'dB', 'extra': 1}}, None, [],
])
def test_metadata_raw_types_and_units_are_rejected(world, metadata):
    row, url, scope = row_and_scope(world)
    response = client.patch(url, params=scope, json={'nodes': [dict(id='a', type='amplifier',
        label='PA', params={'nominal_metadata': metadata})]})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.nodes == []


def test_new_metadata_normalizes_source_but_unchanged_history_keeps_spacing(world):
    initial = body()
    initial['nodes'][0]['params'] = {'gain_db': '12', 'nominal_metadata': {
        'gain_db': {'unit': 'dB', 'source_note': '  旧说明  ', 'frequency_range_mhz': [100, 100]}}}
    row, url, scope = row_and_scope(world, initial)
    fetched = client.get(url, params=scope).json()
    saved = client.patch(url, params=scope, json={'nodes': fetched['nodes'], 'name': '新名'})
    assert saved.status_code == 200, saved.text
    assert saved.json()['nodes'][0]['params'] == initial['nodes'][0]['params']
    changed = copy.deepcopy(fetched['nodes'])
    changed[0]['params']['gain_db'] = None
    changed[0]['params']['nominal_metadata']['gain_db']['source_note'] = '   '
    saved = client.patch(url, params=scope, json={'nodes': changed})
    assert saved.status_code == 200, saved.text
    assert saved.json()['nodes'][0]['params']['gain_db'] is None
    assert saved.json()['nodes'][0]['params']['nominal_metadata']['gain_db']['source_note'] is None


@pytest.mark.parametrize('old,new,status', [('12', '12', 200), ('12', '13', 422),
    (1, True, 422), (True, 1, 200), ('12', 12, 200)])
def test_old_pa_preserved_by_strict_json_type_not_python_equality(world, old, new, status):
    initial = body()
    initial['connections'][0]['pa_gain_db'] = old
    row, url, scope = row_and_scope(world, initial)
    for fetched in [client.get(url, params=scope).json(),
                    client.get('/api/v1/switch-topologies', params=scope).json()['items'][0]]:
        value = fetched['connections'][0]['pa_gain_db']
        assert type(value) is type(old) and value == old
    payload = copy.deepcopy(initial)
    payload['connections'][0]['pa_gain_db'] = new
    response = client.patch(url, params=scope, json=payload)
    assert response.status_code == status, response.text
    world['db'].refresh(row)
    value = row.connections[0]['pa_gain_db']
    expected = old if status == 422 else new
    assert type(value) is type(expected) and value == expected


@pytest.mark.parametrize('value,status', [(0, 201), (None, 201), (-2, 201), ('12', 422), (True, 422)])
def test_post_validates_new_values_and_preserves_sparse_connections(world, value, status):
    payload = body()
    payload.update(name='新拓扑', switch_category_id=str(world['switch_id']),
                   lab_profile_id=str(world['lab_a'].id))
    payload['connections'][0]['pa_gain_db'] = value
    response = client.post('/api/v1/switch-topologies', json=payload)
    assert response.status_code == status, response.text
    if status == 201:
        assert response.json()['connections'] == payload['connections']


def test_invalid_template_cannot_replace_existing_row(world, monkeypatch):
    from app.api import switch_topology as api
    row, url, scope = row_and_scope(world)
    invalid = {**body(), 'name': '坏模板'}
    invalid['nodes'][0]['params'] = {'gain_db': '12'}
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: invalid)
    response = client.post('/api/v1/switch-topologies/import/from-template', params={**scope,
        'switch_category_id': str(world['switch_id']), 'template_id': 'bad', 'replace_existing': True})
    assert response.status_code == 422, response.text
    assert client.get(url, params=scope).json()['name'] == 'Row'


def test_template_and_list_keep_typed_nonpa_values_and_raw_pa_metadata(world, monkeypatch):
    from app.api import switch_topology as api
    payload = {**body(), 'name': '合法模板'}
    payload['connections'][0].update(cable_loss_db='2.5', calibrated_loss_db='0', pa_gain_db=0,
        nominal_metadata={'cable_loss_db': {'unit': 'dB', 'source_note': '  铭牌  ',
                                          'frequency_range_mhz': [100, 200]}})
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: payload)
    scope = {'lab_profile_id': str(world['lab_a'].id)}
    imported = client.post('/api/v1/switch-topologies/import/from-template', params={**scope,
        'switch_category_id': str(world['switch_id']), 'template_id': 'valid'})
    assert imported.status_code == 200, imported.text
    listed = client.get('/api/v1/switch-topologies', params=scope)
    assert listed.status_code == 200, listed.text
    edge = imported.json()['connections'][0]
    assert edge == listed.json()['items'][0]['connections'][0]
    assert edge['cable_loss_db'] == 2.5 and edge['calibrated_loss_db'] == 0
    assert edge['pa_gain_db'] == 0
    assert edge['nominal_metadata']['cable_loss_db']['source_note'] == '铭牌'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_nominal_is_rejected_before_any_write(world, value):
    row, url, scope = row_and_scope(world)
    response = client.patch(url, params=scope,
        content=json.dumps({'name': '不应保存', 'nodes': [dict(id='a', type='amplifier',
            label='PA', params={'gain_db': value})]}), headers={'content-type': 'application/json'})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.nodes == [] and row.name == 'Row'


@pytest.mark.parametrize('declarations', [{'missing': ['cable_loss_db']}, {'ap': ['pa_gain_db']},
    {'ap': ['cable_loss_db', 'cable_loss_db']}, {'ap': ['cable_length_m']}])
def test_invalid_numeric_declaration_is_atomic(world, declarations):
    initial = body()
    row, url, scope = row_and_scope(world, initial)
    payload = copy.deepcopy(initial)
    payload['connections'][0]['cable_loss_db'] = 2.5
    response = client.patch(url, params=scope, json={**payload, 'name': '不应保存',
        'connection_numeric_declarations': declarations})
    assert response.status_code == 422, response.text
    world['db'].refresh(row)
    assert row.connections == initial['connections'] and row.name == 'Row'


def test_typed_display_preserves_history_unless_explicit_numeric_declaration(world):
    initial = body()
    initial['connections'][0].update(cable_loss_db='2.5', calibrated_loss_db='0',
                                      opaque={'identity': [1, True]})
    row, url, scope = row_and_scope(world, initial)
    stored = json.dumps(row.connections)
    fetched = client.get(url, params=scope).json()
    assert fetched['connections'] == [dict(id='ap', source='a', target='p', cable_loss_db=2.5,
                                          calibrated_loss_db=0.0)]
    response = client.patch(url, params=scope, json={'connections': fetched['connections']})
    assert response.status_code == 200, response.text
    world['db'].refresh(row)
    assert json.dumps(row.connections) == stored
    response = client.patch(url, params=scope, json={'connections': fetched['connections'],
        'connection_numeric_declarations': {'ap': ['cable_loss_db']}})
    assert response.status_code == 200, response.text
    assert 'connection_numeric_declarations' not in response.json()
    world['db'].refresh(row)
    assert row.connections == [dict(id='ap', source='a', target='p', cable_loss_db=2.5,
                                   calibrated_loss_db='0', opaque={'identity': [1, True]})]


def test_sparse_add_delete_reorder_and_real_numeric_change_follow_request(world):
    initial = body()
    initial['connections'].append(dict(id='ap2', source='a', target='p', cable_loss_db='2.5'))
    row, url, scope = row_and_scope(world, initial)
    changed = [dict(id='ap2', source='a', target='p', cable_loss_db=0),
               dict(id='ap', source='a', target='p', source_pin='out', pa_gain_db=None)]
    assert client.patch(url, params=scope, json={'connections': changed}).status_code == 200
    world['db'].refresh(row)
    assert row.connections == changed
    changed[1].pop('source_pin')
    assert client.patch(url, params=scope, json={'connections': changed}).status_code == 200
    world['db'].refresh(row)
    assert row.connections == changed


def test_cross_lab_cannot_borrow_old_invalid_value_exemption(world):
    initial = body()
    initial['nodes'][0]['params']['gain_db'] = '12'
    row, url, scope = row_and_scope(world, initial)
    response = client.patch(url, params={'lab_profile_id': str(world['lab_b'].id)}, json=initial)
    assert response.status_code == 409, response.text


def test_nested_opaque_metadata_name_is_not_a_nominal_declaration(world):
    payload = body()
    payload.update(name='扩展参数', switch_category_id=str(world['switch_id']),
                   lab_profile_id=str(world['lab_a'].id))
    opaque = {'nominal_metadata': {'vendor': {'note': '厂商自定义数据，不是本片字段'}}}
    payload['nodes'][0]['params']['opaque_config'] = opaque
    response = client.post('/api/v1/switch-topologies', json=payload)
    assert response.status_code == 201, response.text
    assert response.json()['nodes'][0]['params']['opaque_config'] == opaque


def test_extra_mode_params_remains_ignored_by_original_typed_contract(world):
    payload = body()
    payload.update(name='模式类型边界', switch_category_id=str(world['switch_id']),
                   lab_profile_id=str(world['lab_a'].id))
    payload['operating_modes'] = [dict(id='mimo_ota', name='模式', params={'nominal_metadata': {}})]
    response = client.post('/api/v1/switch-topologies', json=payload)
    assert response.status_code == 201, response.text
    assert 'params' not in response.json()['operating_modes'][0]
