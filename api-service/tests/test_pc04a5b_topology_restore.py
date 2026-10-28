"""历史恢复真实HTTP：不默认化raw、不恢复资格、不覆盖新令牌。"""
from copy import deepcopy
import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from tests.test_pc04a5a_topology_library import db, client, world, lab, source, ROOT, raw
from tests.test_pc04a5b_topology_revisions import patch, rows


def test_preview_read_only_restore_is_new_revision(client, db, lab, source):
    original = deepcopy(source.connections)
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '误保存'}).status_code == 200
    params = {'lab_profile_id': str(lab.id)}
    body = {'revision': 0, 'expected_revision': 1}
    preview = client.post(f'{ROOT}/{source.id}/restore-preview', params=params, json=body)
    assert preview.status_code == 200, preview.text
    assert raw(preview.json()['snapshot']['connections']) == raw(original)
    assert preview.json()['candidate']['connections'][0]['calibrated_loss_db'] is None
    assert 'calibrated_loss_db' not in preview.json()['candidate']['connections'][1]
    assert len(rows(db, source)) == 2
    restored = client.post(f'{ROOT}/{source.id}/restore', params=params, json=body)
    assert restored.status_code == 200, restored.text
    assert restored.json()['revision'] == 2 and restored.json()['name'] == '原图'
    history = rows(db, source)
    assert history[-1].operation == 'restore' and history[-1].restored_from_revision == 0
    assert raw(history[0].snapshot['connections']) == raw(original)
    assert client.post(f'{ROOT}/{source.id}/restore', params=params, json=body).status_code == 409
    assert len(rows(db, source)) == 3


def test_read_old_history_never_lazy_writes(client, db, lab, source):
    response = client.get(f'{ROOT}/{source.id}/revisions', params={'lab_profile_id': str(lab.id)})
    assert response.status_code == 200 and response.json() == {'total': 0, 'items': []}
    assert rows(db, source) == []


def restore_call(client, lab, source, revision=0, expected=1, preview=False):
    return client.post(f'{ROOT}/{source.id}/' + ('restore-preview' if preview else 'restore'),
        params={'lab_profile_id': str(lab.id)}, json={'revision': revision, 'expected_revision': expected})


def test_restore_same_candidate_still_appends(client, db, lab, source):
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '误保存'}).status_code == 200
    assert restore_call(client, lab, source).json()['revision'] == 2
    assert restore_call(client, lab, source, expected=2).json()['revision'] == 3
    assert [r.operation for r in rows(db, source)] == ['baseline', 'update', 'restore', 'restore']


def test_restore_keeps_scope_status_and_creation_metadata(client, db, lab, source):
    original_date = source.installed_date.isoformat()
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '误保存',
        'is_active': False, 'is_default': False}).status_code == 200
    keys = ('id', 'chamber_id', 'switch_category_id', 'created_at', 'created_by', 'is_active', 'is_default')
    db.refresh(source)
    before = {key: getattr(source, key) for key in keys}
    assert restore_call(client, lab, source).status_code == 200
    db.refresh(source)
    assert {key: getattr(source, key) for key in keys} == before
    history = rows(db, source)
    assert history[0].snapshot['installed_date'] == original_date
    assert history[-1].snapshot['installed_date'] == original_date
    assert history[0].recorded_metadata['is_active'] is True
    assert history[-1].recorded_metadata['is_active'] is False


def test_history_pagination_and_foreign_revision_404(client, db, lab, source):
    for i in range(101):
        response = patch(client, lab, source, {'expected_revision': i, 'name': f'保存{i}'})
        assert response.status_code == 200, response.text
    params = {'lab_profile_id': str(lab.id), 'skip': 50, 'limit': 50}
    response = client.get(f'{ROOT}/{source.id}/revisions', params=params)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 102
    assert [r['revision'] for r in response.json()['items']] == list(range(51, 1, -1))
    assert all('snapshot' not in r for r in response.json()['items'])
    copy = client.post(f'{ROOT}/{source.id}/copy', params={'lab_profile_id': str(lab.id)}, json={'name': '另图'})
    assert copy.status_code == 201
    assert client.get(f"{ROOT}/{copy.json()['id']}/revisions/101", params=params).status_code == 404
    assert client.get(f'{ROOT}/{source.id}/revisions/0', params=params).json()['operation'] == 'baseline'
    assert client.get(f'{ROOT}/{source.id}/revisions', params={**params, 'limit': 101}).status_code == 422


@pytest.mark.parametrize('kind', ['port', 'internal', 'reference', 'owner', 'negative', 'bool', 'string', 'infinite'])
def test_invalid_history_cannot_relax_current_save_gates(client, db, lab, source, kind):
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '当前'}).status_code == 200
    old = rows(db, source)[0]
    snapshot = deepcopy(old.snapshot)
    if kind == 'port':
        snapshot['nodes'][0]['params']['ports'] = ['different']
    elif kind == 'internal':
        snapshot['nodes'][0]['params']['internal_paths'] = [{'from_port': 'out', 'to_port': 'missing'}]
    elif kind == 'reference':
        snapshot['operating_modes'][0]['active_connections'] = ['missing']
    elif kind == 'owner':
        snapshot['connections'][0]['loss_owner_connection_id'] = 'missing'
    else:
        snapshot['connections'][0]['cable_loss_db'] = {'negative': -1, 'bool': True,
            'string': '3.5', 'infinite': float('inf')}[kind]
    old.snapshot = snapshot
    db.commit()
    before = raw(source.connections)
    for preview in (True, False):
        response = restore_call(client, lab, source, preview=preview)
        assert response.status_code == 422, response.text
        assert len(rows(db, source)) == 2
        db.refresh(source)
        assert source.revision == 1 and source.name == '当前'
        assert raw(source.connections) == before


def test_restore_snapshot_insert_failure_rolls_back(client, db, lab, source):
    from app.models.switch_topology_revision import SwitchTopologyRevision
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '当前'}).status_code == 200
    def fail(mapper, connection, target):
        if target.operation == 'restore':
            raise IntegrityError('forced', {}, Exception('snapshot failure'))
    event.listen(SwitchTopologyRevision, 'before_insert', fail)
    try:
        assert restore_call(client, lab, source).status_code == 500
    finally:
        event.remove(SwitchTopologyRevision, 'before_insert', fail)
    db.refresh(source)
    assert source.revision == 1 and source.name == '当前'
    assert source.connections[0]['calibrated_loss_db'] == 8.5
    assert len(rows(db, source)) == 2


def test_stale_preview_rejected_at_restore(client, db, lab, source):
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '当前'}).status_code == 200
    assert restore_call(client, lab, source, preview=True).status_code == 200
    assert patch(client, lab, source, {'expected_revision': 1, 'name': '后来'}).status_code == 200
    assert restore_call(client, lab, source).status_code == 409
    assert len(rows(db, source)) == 3
    db.refresh(source)
    assert source.name == '后来'


def test_raw_history_does_not_gain_default_pins(client, db, lab, source):
    edges = deepcopy(source.connections)
    del edges[1]['source_pin']
    del edges[1]['target_pin']
    source.connections = edges
    db.commit()
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '当前'}).status_code == 200
    params = {'lab_profile_id': str(lab.id)}
    detail = client.get(f'{ROOT}/{source.id}/revisions/0', params=params)
    assert detail.status_code == 200, detail.text
    edge = detail.json()['snapshot']['connections'][1]
    assert 'source_pin' not in edge and 'target_pin' not in edge
    assert restore_call(client, lab, source).status_code == 200
    db.refresh(source)
    assert 'source_pin' not in source.connections[1] and 'target_pin' not in source.connections[1]


@pytest.mark.parametrize('body', [{}, {'revision': True, 'expected_revision': 1},
    {'revision': 0, 'expected_revision': '1'}, {'revision': -1, 'expected_revision': 1},
    {'revision': 0, 'expected_revision': 1, 'candidate': {}}])
def test_restore_request_rejects_invalid_tokens(client, db, lab, source, body):
    for suffix in ('restore-preview', 'restore'):
        assert client.post(f'{ROOT}/{source.id}/{suffix}', params={'lab_profile_id': str(lab.id)}, json=body).status_code == 422
    assert rows(db, source) == []


def test_history_scope_and_read_endpoints_never_issue_writes(client, db, world, lab, source):
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '当前'}).status_code == 200
    statements = []
    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())
    event.listen(db.bind, 'before_cursor_execute', observe)
    try:
        scope = {'lab_profile_id': str(lab.id)}
        for suffix in ('revisions', 'revisions/0'):
            assert client.get(f'{ROOT}/{source.id}/{suffix}', params=scope).status_code == 200
        assert restore_call(client, lab, source, preview=True).status_code == 200
        assert not set(statements) & {'INSERT','UPDATE','DELETE'}
        foreign = {'lab_profile_id': str(world[2][1].id)}
        for suffix in ('revisions', 'revisions/0'):
            assert client.get(f'{ROOT}/{source.id}/{suffix}', params=foreign).status_code == 409
        for suffix in ('restore-preview', 'restore'):
            assert client.post(f'{ROOT}/{source.id}/{suffix}', params=foreign,
                json={'revision':0,'expected_revision':1}).status_code == 409
    finally:
        event.remove(db.bind, 'before_cursor_execute', observe)
    assert len(rows(db, source)) == 2


@pytest.mark.parametrize('bad', ['params', 'date', 'name', 'graph', 'missing-field'])
def test_malformed_snapshot_rejected_without_writes(client, db, lab, source, bad):
    assert patch(client, lab, source, {'expected_revision': 0, 'name': '当前'}).status_code == 200
    history = rows(db, source)[0]
    snapshot = deepcopy(history.snapshot)
    if bad == 'params': snapshot['nodes'][0]['params'] = []
    if bad == 'date': snapshot['installed_date'] = 42
    if bad == 'name': snapshot['name'] = '\x00坏名称'
    if bad == 'graph': snapshot['connections'] = None
    if bad == 'missing-field': snapshot.pop('version')
    history.snapshot = snapshot
    db.commit()
    for preview in (True,False):
        response = restore_call(client, lab, source, preview=preview)
        assert response.status_code == 422, response.text
    assert len(rows(db, source)) == 2
