"""修订写入口真实HTTP契约；不访问用户数据库。"""
from copy import deepcopy
import pytest
from sqlalchemy import select
from tests.test_pc04a5a_topology_library import db, client, world, lab, source, other_active, ROOT, raw
from app.models.switch_topology import SwitchTopology
from uuid import UUID, uuid4
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db.database import Base, get_db
from app.main import app
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor


@pytest.fixture
def concurrent_world(tmp_path):
    from app.models.chamber import create_chamber_from_preset, ChamberType
    from app.models.instrument import InstrumentCategory
    from app.models.lab_profile import LabProfile
    engine = create_engine('sqlite:///' + str(tmp_path / 'concurrent.sqlite'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine,autoflush=False)
    with factory() as session:
        chamber = create_chamber_from_preset(ChamberType.TYPE_C.value,name='并发隔离')
        category = InstrumentCategory(category_key='revision-switch',category_name='隔离开关',driver_mode='mock')
        session.add_all([chamber,category]);session.flush()
        labrow = LabProfile(name='并发Lab',chamber_config_id=chamber.id,is_active=True)
        row = SwitchTopology(chamber_id=chamber.id,switch_category_id=category.id,name='并发原图',
            nodes=[],connections=[],operating_modes=[],is_default=False)
        row.update_statistics();session.add_all([labrow,row]);session.commit()
        ids = str(labrow.id), str(row.id), str(category.id)
    def sessions():
        with factory() as session:
            yield session
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = sessions
    try:
        yield factory, TestClient(app,raise_server_exceptions=False), ids
    finally:
        if old is None:
            app.dependency_overrides.pop(get_db,None)
        else:
            app.dependency_overrides[get_db] = old
        engine.dispose()


def patch(client, lab, source, body):
    return client.patch(f'{ROOT}/{source.id}', params={'lab_profile_id': str(lab.id)}, json=body)


def rows(db, source):
    from app.models.switch_topology_revision import SwitchTopologyRevision
    db.expire_all()
    return db.scalars(select(SwitchTopologyRevision).where(
        SwitchTopologyRevision.topology_id == source.id).order_by(SwitchTopologyRevision.revision)).all()


def test_old_row_first_write_and_stale_noop(client, db, lab, source):
    before = deepcopy(source.connections)
    assert client.get(f'{ROOT}/{source.id}', params={'lab_profile_id': str(lab.id)}).json()['revision'] == 0
    saved = patch(client, lab, source, {'name': '修订一', 'expected_revision': 0})
    assert saved.status_code == 200, saved.text
    assert saved.json()['revision'] == 1
    history = rows(db, source)
    assert [(x.revision, x.operation) for x in history] == [(0, 'baseline'), (1, 'update')]
    assert raw(history[0].snapshot['connections']) == raw(before)
    assert patch(client, lab, source, {'name': '修订一', 'expected_revision': 0}).status_code == 409
    assert patch(client, lab, source, {'name': '修订一', 'expected_revision': 1}).json()['revision'] == 1
    assert len(rows(db, source)) == 2


@pytest.mark.parametrize('token', [None, True, False, -1, 1.0, '0'])
def test_invalid_tokens_rejected(client, db, lab, source, token):
    assert patch(client, lab, source, {'name': '不得写', 'expected_revision': token}).status_code == 422
    assert rows(db, source) == []


def test_missing_token_rejected(client, db, lab, source):
    assert patch(client, lab, source, {'name': '旧客户端'}).status_code == 422
    db.refresh(source)
    assert source.name == '原图'
    assert rows(db, source) == []


def test_create_copy_import_record_revision_one(client, db, world, lab, source, monkeypatch):
    import app.api.switch_topology as api
    result = client.post(ROOT, json={'name':'创建', 'switch_category_id':str(source.switch_category_id),
                                    'lab_profile_id':str(lab.id)})
    assert result.status_code == 201, result.text
    assert patch(client,lab,source,{'expected_revision':0,'name':'先有历史'}).status_code == 200
    copied = client.post(f'{ROOT}/{source.id}/copy', params={'lab_profile_id':str(lab.id)},json={'name':'复制'})
    assert copied.status_code == 201, copied.text
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: {'name':'导入', 'nodes':[], 'connections':[], 'operating_modes':[]})
    imported = client.post(f'{ROOT}/import/from-template',params={'lab_profile_id':str(lab.id),
        'switch_category_id':str(world[1][1].id), 'template_id':'isolated'})
    assert imported.status_code == 200, imported.text
    for response, operation in [(result,'create'),(copied,'copy'),(imported,'import')]:
        assert response.json()['revision'] == 1
        row = db.get(SwitchTopology,UUID(response.json()['id']))
        assert [(r.revision,r.operation) for r in rows(db,row)] == [(1,operation)]
    assert [(r.revision,r.operation) for r in rows(db,source)] == [(0,'baseline'),(1,'update')]


@pytest.mark.parametrize('operation',['create','patch'])
def test_snapshot_failure_rolls_back_target_and_default_peers(client, db, lab, source, other_active, operation):
    before = [(r.id,r.revision,r.name,r.is_default,r.updated_at) for r in (source,other_active)]
    count = db.query(SwitchTopology).count()
    def fail(conn,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO switch_topology_revisions'):
            raise IntegrityError(statement,parameters,Exception('隔离快照故障'))
    event.listen(db.bind,'before_cursor_execute',fail)
    try:
        if operation == 'create':
            response = client.post(ROOT,json={'name':'失败创建','lab_profile_id':str(lab.id),
                'switch_category_id':str(source.switch_category_id),'is_default':True})
        else:
            response = patch(client,lab,other_active,{'expected_revision':0,'name':'失败更新','is_default':True})
        assert response.status_code == 500
    finally:
        event.remove(db.bind,'before_cursor_execute',fail)
    db.expire_all()
    assert db.query(SwitchTopology).count() == count
    assert [(r.id,r.revision,r.name,r.is_default,r.updated_at) for r in (source,other_active)] == before
    assert rows(db,source) == rows(db,other_active) == []


def test_default_peer_scope_and_metadata(client, db, world, lab, source, other_active):
    untouched = []
    for chamber,category in [(world[0][0],world[1][1]),(world[0][1],world[1][0])]:
        row = SwitchTopology(chamber_id=chamber.id,switch_category_id=category.id,name='其它scope',
            is_default=True,nodes=[],connections=[],operating_modes=[])
        row.update_statistics();db.add(row);untouched.append(row)
    db.commit()
    response = patch(client,lab,other_active,{'expected_revision':0,'is_default':True})
    assert response.status_code == 200, response.text
    history = rows(db,source)
    assert [(r.revision,r.operation) for r in history] == [(0,'baseline'),(1,'update')]
    assert history[-1].recorded_metadata['is_default'] is False
    for row in untouched:
        db.refresh(row)
        assert row.revision == 0 and row.is_default is True and rows(db,row) == []


def test_name_does_not_change_execution_selection(client, db, lab, source, other_active):
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    selected = orchestrate_switch_topology(db,lab.chamber_config_id).topology_id
    before = source.updated_at, other_active.updated_at
    response = patch(client,lab,source,{'expected_revision':0,'name':'改名','chamber_id':str(source.chamber_id)})
    assert response.status_code == 200, response.text
    db.refresh(source);db.refresh(other_active)
    assert (source.updated_at,other_active.updated_at) == before
    assert other_active.revision == 0 and rows(db,other_active) == []
    assert orchestrate_switch_topology(db,lab.chamber_config_id).topology_id == selected


def test_boolean_to_number_is_not_noop(client, db, lab, source):
    nodes = deepcopy(source.nodes);nodes[1]['params']['opaque']['bool'] = 1
    response = patch(client,lab,source,{'expected_revision':0,'nodes':nodes})
    assert response.status_code == 200, response.text
    assert response.json()['revision'] == 1
    db.refresh(source)
    assert type(source.nodes[1]['params']['opaque']['bool']) is int
    nodes = deepcopy(source.nodes);nodes[1]['params']['missing'] = None
    response = patch(client,lab,source,{'expected_revision':1,'nodes':nodes})
    assert response.status_code == 200 and response.json()['revision'] == 2
    assert 'missing' not in rows(db,source)[1].snapshot['nodes'][1]['params']
    assert rows(db,source)[2].snapshot['nodes'][1]['params']['missing'] is None


def test_conversion_requires_both_tokens(client, db, lab, source):
    scope = {'lab_profile_id':str(lab.id)}
    changes = {'connections':[{'connection_id':'e','cable_loss_db':None}]}
    preview = client.post(f'{ROOT}/{source.id}/conversion-preview',params=scope,json=changes)
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert patch(client,lab,source,{'name':'元数据','expected_revision':0}).status_code == 200
    newer = client.post(f'{ROOT}/{source.id}/conversion-preview',params=scope,json=changes).json()
    assert newer['source_digest'] == p['source_digest']
    body = {'expected_revision':p['revision'],'conversion':{'source_digest':p['source_digest'],'changes':p['changes']}}
    assert patch(client,lab,source,body).status_code == 409
    body['expected_revision'] = newer['revision']
    assert patch(client,lab,source,{**body,'name':'混合'}).status_code == 422
    assert patch(client,lab,source,{**body,'conversion':{**body['conversion'],'source_digest':'错误'}}).status_code == 409
    assert patch(client,lab,source,body).status_code == 200
    assert [(r.revision,r.operation) for r in rows(db,source)] == [(0,'baseline'),(1,'update'),(2,'conversion')]


def test_noop_conversion_does_not_create_history(client, db, lab, source):
    scope = {'lab_profile_id':str(lab.id)}
    p = client.post(f'{ROOT}/{source.id}/conversion-preview',params=scope,
                   json={'nodes':[{'node_id':'ce','ports':['out']}]}).json()
    response = patch(client,lab,source,{'expected_revision':p['revision'],
        'conversion':{'source_digest':p['source_digest'],'changes':p['changes']}})
    assert response.status_code == 200, response.text
    assert response.json()['revision'] == 0 and rows(db,source) == []


@pytest.mark.parametrize('body',[{'description':'新描述'},{'is_default':False},{'is_default':True},{'chamber_id':'same'}])
def test_non_promotion_never_writes_default_peers(client, db, lab, source, other_active, body):
    # 两个历史default并存时，不得借普通保存自动修库；只有明确false→true才让位。
    other_active.is_default = True;db.commit()
    before = other_active.revision,other_active.is_default,other_active.updated_at
    if body.get('chamber_id') == 'same':
        body = {'chamber_id':str(source.chamber_id)}
    response = patch(client,lab,source,dict(body,expected_revision=0))
    assert response.status_code == 200, response.text
    db.refresh(other_active)
    assert (other_active.revision,other_active.is_default,other_active.updated_at) == before
    assert rows(db,other_active) == []


def test_active_state_change_advances_revision(client, db, lab, source):
    before = deepcopy(source.connections)
    response = patch(client,lab,source,{'expected_revision':0,'is_active':False})
    assert response.status_code == 200 and response.json()['revision'] == 1
    history = rows(db,source)
    assert history[-1].recorded_metadata['is_active'] is False
    assert raw(history[0].snapshot['connections']) == raw(history[1].snapshot['connections']) == raw(before)


def test_conversion_raw_cas_rejection_rolls_back_without_baseline(client, db, lab, source, monkeypatch):
    import app.api.switch_topology as api
    from sqlalchemy import update
    scope = {'lab_profile_id':str(lab.id)}
    p = client.post(f'{ROOT}/{source.id}/conversion-preview',params=scope,
        json={'connections':[{'connection_id':'e','cable_loss_db':None}]}).json()
    before = deepcopy(source.nodes)
    original = api._conversion_candidate
    def changed_raw(snapshot, changes):
        candidate = original(snapshot, changes)
        # 只在底层存储注入竞争，真实路由/构造器/双CAS仍执行。
        db.execute(update(SwitchTopology).where(SwitchTopology.id == source.id).values(
            nodes=[dict(node, label='竞争原值') for node in before]).execution_options(synchronize_session=False))
        return candidate
    monkeypatch.setattr(api,'_conversion_candidate',changed_raw)
    response = patch(client,lab,source,{'expected_revision':p['revision'],
        'conversion':{'source_digest':p['source_digest'],'changes':p['changes']}})
    assert response.status_code == 409, response.text
    db.refresh(source)
    assert source.revision == 0 and source.nodes == before and rows(db,source) == []


def test_revision_cas_rowcount_failure_rolls_back_without_baseline(client, db, lab, source, monkeypatch):
    import app.api.switch_topology as api
    from sqlalchemy import update
    original = api.cas_revision
    def changed_revision(session, row, expected, values, **kwargs):
        session.execute(update(SwitchTopology).where(SwitchTopology.id == row.id).values(
            revision=9).execution_options(synchronize_session=False))
        return original(session,row,expected,values,**kwargs)
    monkeypatch.setattr(api,'cas_revision',changed_revision)
    response = patch(client,lab,source,{'expected_revision':0,'name':'不能越过CAS'})
    assert response.status_code == 409, response.text
    db.refresh(source)
    assert source.revision == 0 and source.name == '原图' and rows(db,source) == []


def test_copy_metadata_records_final_statistics_timestamp(client, db, lab, source, monkeypatch):
    import time
    original = SwitchTopology.update_statistics
    def delayed_statistics(row):
        original(row)
        # 实际跨越SQLite CURRENT_TIMESTAMP秒精度，暴露先记metadata后flush统计的顺序错误。
        if row.name == '复制时间':
            time.sleep(1.1)
    monkeypatch.setattr(SwitchTopology,'update_statistics',delayed_statistics)
    response = client.post(f'{ROOT}/{source.id}/copy', params={'lab_profile_id':str(lab.id)},json={'name':'复制时间'})
    assert response.status_code == 201, response.text
    copied = db.get(SwitchTopology,UUID(response.json()['id']))
    assert rows(db,copied)[0].recorded_metadata['updated_at'] == copied.updated_at.isoformat()


def test_delete_and_chamber_delete_keep_history(client, db, world, lab, source):
    from app.models.probe import Probe
    assert patch(client,lab,source,{'expected_revision':0,'name':'留历史'}).status_code == 200
    assert client.delete(f'{ROOT}/{source.id}',params={'lab_profile_id':str(lab.id)}).status_code == 409
    chamber = world[0][0]
    probe = Probe(chamber_config_id=chamber.id,probe_number=1,ring=1,polarization='V',
                  position={'azimuth':0,'elevation':0,'radius':1})
    db.add(probe);db.flush()
    probe_id = probe.id
    chamber.is_system_preset = False
    for bound in world[2]:
        if bound.chamber_config_id == chamber.id:
            bound.chamber_config_id = world[0][1].id
    db.commit()
    assert client.delete(f'/api/v1/chambers/{chamber.id}').status_code == 409
    db.expire_all()
    assert db.get(type(chamber),chamber.id) is not None
    assert db.get(Probe,probe_id) is not None
    assert db.get(SwitchTopology,source.id) is not None and len(rows(db,source)) == 2


@pytest.mark.parametrize('operation',['patch','copy','import'])
def test_response_failure_precedes_commit(client, db, lab, source, monkeypatch, operation):
    import app.api.switch_topology as api
    nodes = deepcopy(source.nodes);nodes[0]['label'] = {'invalid':'label'}
    source.nodes = nodes;db.commit()
    before = source.name, source.revision, source.is_default, source.updated_at
    count = db.query(SwitchTopology).count()
    if operation == 'patch':
        response = patch(client,lab,source,{'expected_revision':0,'name':'不得提交'})
    elif operation == 'copy':
        response = client.post(f'{ROOT}/{source.id}/copy',params={'lab_profile_id':str(lab.id)},json={'name':'不得复制'})
    else:
        monkeypatch.setattr(api,'_load_template',lambda _: lambda: {'name':'坏模板','nodes':nodes,
            'connections':deepcopy(source.connections),'operating_modes':deepcopy(source.operating_modes)})
        response = client.post(f'{ROOT}/import/from-template',params={'lab_profile_id':str(lab.id),
            'switch_category_id':str(source.switch_category_id),'template_id':'isolated'})
    assert response.status_code == 422, response.text
    db.expire_all()
    assert db.query(SwitchTopology).count() == count
    assert (source.name,source.revision,source.is_default,source.updated_at) == before
    assert rows(db,source) == []


def test_two_sessions_same_revision_one_winner(concurrent_world):
    factory,http,(labid,rowid,_) = concurrent_world
    barrier = Barrier(2)
    def write(name):
        barrier.wait(10)
        return http.patch(f'{ROOT}/{rowid}',params={'lab_profile_id':labid},
                          json={'expected_revision':0,'name':name})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(write,['甲','乙']))
    assert sorted(r.status_code for r in responses) == [200,409], [r.text for r in responses]
    winner = next(r.json() for r in responses if r.status_code == 200)
    with factory() as session:
        row = session.get(SwitchTopology,UUID(rowid))
        assert row.name == winner['name'] and row.revision == 1
        assert [(r.revision,r.operation) for r in rows(session,row)] == [(0,'baseline'),(1,'update')]


def test_two_default_creates_empty_scope(concurrent_world):
    factory,http,(labid,rowid,category) = concurrent_world
    with factory() as session:
        session.delete(session.get(SwitchTopology,UUID(rowid)))
        session.commit()
    barrier = Barrier(2)
    def create(name):
        barrier.wait(10)
        return http.post(ROOT,json={'name':name,'lab_profile_id':labid,
            'switch_category_id':category,'is_default':True})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create,['默认甲','默认乙']))
    codes = sorted(r.status_code for r in responses)
    assert codes in ([201,201],[201,409]), [r.text for r in responses]
    with factory() as session:
        defaults = session.query(SwitchTopology).filter(SwitchTopology.is_default.is_(True)).all()
        assert len(defaults) == 1
        if codes == [201,201]:
            created = [session.get(SwitchTopology,UUID(r.json()['id'])) for r in responses]
            former = next(row for row in created if not row.is_default)
            assert [(r.revision,r.operation) for r in rows(session,former)] == [(1,'create'),(2,'update')]
