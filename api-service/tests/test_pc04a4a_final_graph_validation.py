"""最终保存图必须满足显式路径契约；真实HTTP及正式解析器，不访问硬件。"""
from tests.topology_revision_requests import saved_revision as _saved_revision
import copy
from uuid import UUID

import pytest
from sqlalchemy import event

from tests.test_p1_57_topology_lab_context import client, setup_database, world, _mk_row
from app.models.switch_topology import SwitchTopology
from app.services.declared_rf_routes import resolve_saved_rf_path
from app.services.calibration.rf_chain_resolver import resolve_rf_chains


def graph(*, explicit=True):
    params = {'ports': ['in'], 'probe_id': 0, 'polarization': 'V'}
    if explicit:
        params['rf_path_selection'] = {'connection_ids': ['cp'], 'switch_mappings': []}
    return dict(nodes=[
        dict(id='ce', type='ce_port', label='B1.1', params={'ports': ['out']}),
        dict(id='probe', type='probe', label='探头', params=params)],
        connections=[dict(id='cp', source='ce', source_pin='out', target='probe', target_pin='in')],
        operating_modes=[dict(id='mimo_ota', name='正常', active_connections=['cp'])])


def write(world, monkeypatch, entrypoint, payload, target=None):
    scope = {'lab_profile_id': str(world['lab_a'].id)}
    if entrypoint == 'post':
        return client.post('/api/v1/switch-topologies', json={**payload, **scope,
            'switch_category_id': str(world['switch_id']), 'name': '新图', 'is_default': True})
    if entrypoint == 'patch':
        return client.patch(f'/api/v1/switch-topologies/{target.id}', params=scope,
                            json={**({**payload, 'name': '新图', 'is_default': True}), 'expected_revision': _saved_revision(client, f'/api/v1/switch-topologies/{target.id}', scope)})
    from app.api import switch_topology as api
    # 只替代模板文件加载，保留实际导入校验、替换和存储链。
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: {
        **copy.deepcopy(payload), 'name': '新图', 'is_default': True})
    return client.post('/api/v1/switch-topologies/import/from-template', params={
        **scope, 'switch_category_id': str(world['switch_id']),
        'template_id': 'final_graph', 'replace_existing': True})


def snapshot(db):
    db.expire_all()
    return {str(row.id): (row.name, row.is_default, copy.deepcopy(row.nodes),
        copy.deepcopy(row.connections), copy.deepcopy(row.operating_modes))
        for row in db.query(SwitchTopology).all()}


@pytest.mark.parametrize('entrypoint', ['post', 'patch', 'import'])
@pytest.mark.parametrize('missing', [('source_pin',), ('target_pin',), ('source_pin', 'target_pin')])
def test_incomplete_explicit_path_rejected_before_any_topology_write(
        world, monkeypatch, entrypoint, missing):
    db = world['db']
    old_default = _mk_row(db, world['switch_id'], world['chamber_a'].id, '原默认图')
    old_default.is_default = True
    db.commit()
    target = _mk_row(db, world['switch_id'], world['chamber_a'].id, '待修改图')
    before = snapshot(db)
    payload = graph()
    for key in missing:
        del payload['connections'][0][key]
    writes = []
    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        sql = statement.lstrip().upper()
        if sql.startswith(('UPDATE SWITCH_TOPOLOGIES', 'INSERT INTO SWITCH_TOPOLOGIES',
                           'DELETE FROM SWITCH_TOPOLOGIES')):
            writes.append(sql)
    event.listen(db.get_bind(), 'before_cursor_execute', capture)
    try:
        response = write(world, monkeypatch, entrypoint, payload, target)
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', capture)
    assert response.status_code == 422, response.text
    assert '显式路径必须保存完整端口' in response.json()['detail']
    assert writes == [], '拒绝必须早于默认位让位、删旧图或新增行'
    assert snapshot(db) == before


@pytest.mark.parametrize('entrypoint', ['post', 'patch', 'import'])
@pytest.mark.parametrize('explicit', [False, True])
def test_saved_complete_explicit_or_sparse_legacy_path_remains_consumable(
        world, monkeypatch, entrypoint, explicit):
    payload = graph(explicit=explicit)
    if not explicit:
        del payload['connections'][0]['source_pin']
        del payload['connections'][0]['target_pin']
    target = _mk_row(world['db'], world['switch_id'], world['chamber_a'].id) if entrypoint == 'patch' else None
    response = write(world, monkeypatch, entrypoint, payload, target)
    assert response.status_code == (201 if entrypoint == 'post' else 200), response.text
    ident = response.json()['id']
    scope = {'lab_profile_id': str(world['lab_a'].id)}
    saved = client.get(f'/api/v1/switch-topologies/{ident}', params=scope).json()
    assert saved['connections'] == payload['connections']
    world['db'].expire_all()
    row = world['db'].query(SwitchTopology).filter_by(id=UUID(ident)).one()
    assert row.connections == payload['connections']
    path_nodes, path_edges = resolve_saved_rf_path(row.nodes, row.connections, 'cp')
    assert [n['id'] for n in path_nodes] == ['ce', 'probe']
    assert path_edges == payload['connections']
    resolved = resolve_rf_chains(world['db'], world['lab_a'].id, 'mimo_ota')
    if entrypoint == 'import':
        # PC04A5a有意契约：模板保形草稿可读取，但不自动用于正式执行。
        assert row.is_active is False and row.is_default is False
        assert not resolved.success
    else:
        assert resolved.success, resolved.warnings
        assert [(c.chain_id, c.ce_port, c.probe_id, c.polarization) for c in resolved.chains] == [('cp', 'B1.1', 0, 'V')]
    repeated = client.patch(f'/api/v1/switch-topologies/{ident}', params=scope, json={**({
        key: saved[key] for key in ('nodes', 'connections', 'operating_modes')}), 'expected_revision': _saved_revision(client, f'/api/v1/switch-topologies/{ident}', scope)})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()['connections'] == payload['connections']
