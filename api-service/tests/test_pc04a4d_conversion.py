"""真实HTTP转换、零写预览与双连接CAS；仅使用调用方专用临时SQLite。"""
import copy
import uuid
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from tests.test_pc04a4d_loss_truth import bootstrap, world, graph, create


def raw(world, url):
    db, _, _ = world
    db.rollback()
    return db.execute(text('SELECT nodes, connections, operating_modes, is_default, name FROM switch_topologies WHERE id=:id'),
                      {'id':uuid.UUID(url.rsplit('/',1)[1]).hex}).one()


def preview(world, url, scope, changes):
    response = world[2].post(url+'/conversion-preview', params=scope, json=changes)
    assert response.status_code == 200, response.text
    return response.json()


def commit(world, url, scope, p):
    return world[2].patch(url, params=scope, json={'conversion':{
        'source_digest':p['source_digest'], 'changes':p['changes']}})


def test_real_http_preview_cancel_and_confirm(world):
    url, scope = create(world)
    before = raw(world,url)
    changes={'nodes':[{'node_id':'ce','target_type':'channel_emulator','ce_port':'B1.1'}]}
    p=preview(world,url,scope,changes)
    assert raw(world,url)==before
    assert p['candidate']['nodes'][0]['id']=='ce'
    response=commit(world,url,scope,p)
    assert response.status_code==200,response.text
    assert response.json()['nodes'][0]['type']=='channel_emulator'
    assert commit(world,url,scope,p).status_code==409


def test_ownership_confirmation_preserves_values_and_undo(world):
    url, scope=create(world)
    before=raw(world,url)
    changes={'connections':[{'connection_id':'b','loss_owner_connection_id':'a',
                            'same_physical_cable_confirmed':True}]}
    p=preview(world,url,scope,changes)
    assert any('通用' in item and '4' in item and '2' in item for item in p['warnings'])
    assert raw(world,url)==before
    assert commit(world,url,scope,p).status_code==200
    p=preview(world,url,scope,{'connections':[{'connection_id':'b','loss_owner_connection_id':None,
                                             'same_physical_cable_confirmed':True}]})
    assert commit(world,url,scope,p).status_code==200
    saved=world[2].get(url,params=scope).json()
    assert 'loss_owner_connection_id' not in saved['connections'][1]
    assert [e['cable_loss_db'] for e in saved['connections']]==[2,2]


def test_stale_conversion_preserves_other_writer(world):
    url,scope=create(world)
    p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    data=graph(); data['connections'][0]['cable_loss_db']=7
    assert world[2].patch(url,params=scope,json={'connections':data['connections']}).status_code==200
    before=raw(world,url)
    assert commit(world,url,scope,p).status_code==409
    assert raw(world,url)==before


@pytest.mark.parametrize('changes', [
    {}, {'nodes':[{'node_id':'ce'}]}, {'nodes':[{'node_id':'absent','ports':['P']}]},
    {'nodes':[{'node_id':'ce','ports':None}]},
    {'nodes':[{'node_id':'ce','ce_port':''}]},
    {'nodes':[{'node_id':'ce','target_type':'channel_emulator'}]},
    {'nodes':[{'node_id':'wire','target_type':'channel_emulator'}]},
    {'nodes':[{'node_id':'ce','ports':['OUT']},{'node_id':'ce','ports':['OUT']}]},
    {'nodes':[{'node_id':'ce','ports':['OUT'],'label':'injected'}]},
    {'nodes':[{'node_id':'ce','ports':['OTHER']}]},
    {'nodes':[{'node_id':'ce','port_directions':{'OUT':'input'}}]},
    {'nodes':[{'node_id':'wire','internal_paths':[{'from_port':'IN','to_port':'MISSING'}]}]},
    {'nodes':[{'node_id':'wire','internal_paths':[{'from_port':'IN','to_port':'OUT','gain':3}]}]},
    {'connections':[{'connection_id':'b','loss_owner_connection_id':'a'}]},
    {'connections':[{'connection_id':'b','loss_owner_connection_id':None}]},
    {'connections':[{'connection_id':'b','source_pin':None}]},
    {'connections':[{'connection_id':'b','cable_loss_db':'3'}]},
    {'connections':[{'connection_id':'b','cable_loss_db':True}]},
    {'connections':[{'connection_id':'b','loss_owner_connection_id':'a','same_physical_cable_confirmed':True},
                    {'connection_id':'a','cable_loss_db':3}]},
    {'connections':[{'connection_id':'b','loss_owner_connection_id':'b','same_physical_cable_confirmed':True}]},
    {'connections':[{'connection_id':'b','source':'ce'}]}, {'candidate':{},'nodes':[]},
])
def test_invalid_preview_atomic(world,changes):
    url,scope=create(world)
    before=raw(world,url)
    response=world[2].post(url+'/conversion-preview',params=scope,json=changes)
    assert response.status_code==422,response.text
    assert raw(world,url)==before


@pytest.mark.parametrize('kind', ['graph','name'])
def test_real_double_connection_interleaving_after_snapshot_before_update(world,monkeypatch,kind):
    import app.api.switch_topology as api
    url,scope=create(world)
    p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    reached,release=threading.Event(),threading.Event()
    original=api._conversion_candidate
    def barrier(source,changes):
        result=original(source,changes)
        reached.set()
        assert release.wait(15)
        return result
    monkeypatch.setattr(api,'_conversion_candidate',barrier)
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(commit,world,url,scope,p)
        try:
            assert reached.wait(15)
            # 第二个真实HTTP请求和独立Session在A读快照后提交。
            data=graph();data['connections'][0]['cable_loss_db']=9
            update={'connections':data['connections']} if kind=='graph' else {'name':'另一会话名称'}
            other=world[2].patch(url,params=scope,json=update)
            assert other.status_code==200,other.text
        finally:
            release.set()
        response=pending.result(15)
    assert response.status_code==(409 if kind=='graph' else 200),response.text
    saved=world[2].get(url,params=scope).json()
    assert saved['connections'][0]['cable_loss_db']==(9 if kind=='graph' else None)
    if kind=='name':assert saved['name']=='另一会话名称'
    # 原digest拒绝后，新快照确实可以提交，不留dirty待get_db退出写入。
    monkeypatch.setattr(api,'_conversion_candidate',original)
    p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':4}]})
    assert commit(world,url,scope,p).status_code==200


def test_real_sqlite_busy_rollback(world,monkeypatch):
    from app.db.database import engine
    import app.api.switch_topology as api
    url,scope=create(world)
    p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    before=raw(world,url)
    original=api._conversion_snapshot
    def timeout_snapshot(db,*args):
        db.execute(text('PRAGMA busy_timeout=10'))
        return original(db,*args)
    monkeypatch.setattr(api,'_conversion_snapshot',timeout_snapshot)
    with engine.connect() as blocker:
        blocker.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            response=commit(world,url,scope,p)
            assert response.status_code==409,response.text
        finally:
            blocker.rollback()
    assert raw(world,url)==before
    assert commit(world,url,scope,p).status_code==200


def test_busy_preview_allowed_and_forged_commit_atomic(world,monkeypatch):
    import app.api.switch_topology as api
    url,scope=create(world)
    monkeypatch.setattr(api.execution_exclusion_guard,'active_unsafe_diagnostic',lambda:'busy')
    before=raw(world,url)
    p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    assert commit(world,url,scope,p).status_code==409
    monkeypatch.setattr(api.execution_exclusion_guard,'active_unsafe_diagnostic',lambda:None)
    for extra in ({'candidate':{}},{'name':'bad'},{'connection_numeric_declarations':{}}):
        response=world[2].patch(url,params=scope,json={'conversion':{
            'source_digest':p['source_digest'],'changes':p['changes']},**extra})
        assert response.status_code==422,response.text
    assert commit(world,url,scope,{**p,'source_digest':'forged'}).status_code==409
    assert raw(world,url)==before


@pytest.mark.parametrize('legacy,target,pin', [('ce_port','channel_emulator','OUT'),
    ('bse_port','communication_tester','OUT'),('sa_port','signal_analyzer','IN')])
def test_three_old_types_keep_raw_identity_and_opaque(world,legacy,target,pin):
    db,lab,client=world
    url,scope=create(world)
    # 旧图真实DB原始形状：单器件，无猜测端口、模式或能力。
    from app.models.switch_topology import SwitchTopology
    row=db.get(SwitchTopology,uuid.UUID(url.rsplit('/',1)[1]))
    row.nodes=[dict(id='legacy',type=legacy,label='旧标签',opaque={'truth':False},params={'opaque':[1,None]})]
    row.connections=[];row.operating_modes=[];db.commit()
    before=raw(world,url)
    changes={'nodes':[dict(node_id='legacy',target_type=target,ports=[pin],
         port_directions={pin:'unknown'},**({'ce_port':'B1.1'} if legacy=='ce_port' else {}))]}
    p=preview(world,url,scope,changes)
    assert raw(world,url)==before
    assert commit(world,url,scope,p).status_code==200
    db.expire_all();saved=db.get(SwitchTopology,row.id)
    assert saved.nodes[0]['id']=='legacy'
    assert saved.nodes[0]['opaque']=={'truth':False}
    assert saved.nodes[0]['params']['opaque']==[1,None]
    assert saved.connections==[] and saved.operating_modes==[]


def test_caict_real_import_preview_no_template_rewrite(world):
    from pathlib import Path
    from hashlib import sha256
    db,lab,client=world
    path=Path('scripts/dev-fixtures/topology-templates/caict_v4.py')
    digest=sha256(path.read_bytes()).hexdigest()
    response=client.post('/api/v1/switch-topologies/import/from-template',params={
        'switch_category_id':str(uuid.uuid4()),'lab_profile_id':str(lab.id),'template_id':'caict_v4'})
    # 路由从OpenAPI原import生产入口核验，非直接调用模板生成函数。
    assert response.status_code==200,response.text
    url='/api/v1/switch-topologies/'+response.json()['id'];scope={'lab_profile_id':str(lab.id)}
    before=raw(world,url)
    node=response.json()['nodes'][0]
    p=preview(world,url,scope,{'connections':[{'connection_id':response.json()['connections'][0]['id'],
                                           'cable_loss_db':None}]})
    assert raw(world,url)==before
    assert sha256(path.read_bytes()).hexdigest()==digest


def test_no_default_pin_in_conversion(world):
    from app.models.switch_topology import SwitchTopology
    db,lab,client=world
    url,scope=create(world)
    row=db.get(SwitchTopology,uuid.UUID(url.rsplit('/',1)[1]))
    data=copy.deepcopy(row.connections);data[0].pop('source_pin')
    nodes=copy.deepcopy(row.nodes);nodes[-1]['params'].pop('rf_path_selection')
    row.nodes=nodes;row.connections=data;db.commit()
    before=raw(world,url)
    response=client.post(url+'/conversion-preview',params=scope,json={
        'nodes':[{'node_id':'ce','ports':['out'],'port_directions':{'out':'output'}}]})
    assert response.status_code==422,response.text
    assert raw(world,url)==before


def test_cross_lab_conversion_read_and_write_are_404(world):
    from app.models.lab_profile import LabProfile
    from app.models.chamber import ChamberType,create_chamber_from_preset
    db,lab,client=world
    url,scope=create(world)
    changes={'connections':[{'connection_id':'a','cable_loss_db':None}]}
    p=preview(world,url,scope,changes)
    chamber=create_chamber_from_preset(ChamberType.TYPE_C.value,name='转换异Lab')
    db.add(chamber);db.flush()
    other=LabProfile(name='转换异Lab'+str(uuid.uuid4()),chamber_config_id=chamber.id,is_active=True)
    db.add(other);db.commit()
    scope={'lab_profile_id':str(other.id)}
    assert client.post(url+'/conversion-preview',params=scope,json=changes).status_code==404
    assert commit(world,url,scope,p).status_code==404


def test_final_validation_uses_original_before_not_candidate(world):
    """把previous错误换成candidate会隐去受影响判据，方向矛盾不能入库。"""
    url,scope=create(world)
    before=raw(world,url)
    changes={'nodes':[{'node_id':'ce','port_directions':{'OUT':'input'}}]}
    response=world[2].post(url+'/conversion-preview',params=scope,json=changes)
    assert response.status_code==422,response.text
    assert raw(world,url)==before


def test_preview_zero_sql_writes_and_nonempty_history_immutable(world):
    import datetime
    import hashlib
    import json
    from sqlalchemy import event
    from app.db.database import engine
    from app.models.calibration import CalibrationCertificate
    from app.models.test_plan import TestExecution
    db,lab,client=world
    url,scope=create(world)
    cert=CalibrationCertificate(certificate_number='conversion-'+str(uuid.uuid4()),
        calibration_date=datetime.datetime(2026,1,1),valid_until=datetime.datetime(2027,1,1),
        overall_pass=False,system_configuration={'fixture':'非现场','frozen':[2,None]})
    execution=TestExecution(status='completed',topology_id=url.rsplit('/',1)[1],
        config={'fixture':'非现场','snapshot':graph()},test_results={'conclusion':'unknown'})
    db.add_all([cert,execution]);db.commit()
    def history():
        result={name:[list(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY id'))]
            for name in ('calibration_certificates','test_executions','route_calibration_applications')}
        return hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()
    before_history=history();before=raw(world,url)
    statements=[]
    def observe(conn,cursor,statement,params,context,many):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(engine,'before_cursor_execute',observe)
    try:
        p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    finally:
        event.remove(engine,'before_cursor_execute',observe)
    assert not set(statements)&{'INSERT','UPDATE','DELETE'},statements
    assert raw(world,url)==before and history()==before_history
    assert commit(world,url,scope,p).status_code==200
    assert history()==before_history


def test_bse_authoritative_conflict_and_all_modes_referenced(world):
    from app.models.switch_topology import SwitchTopology
    db,lab,client=world
    url,scope=create(world)
    row=db.get(SwitchTopology,uuid.UUID(url.rsplit('/',1)[1]))
    nodes=copy.deepcopy(row.nodes)
    nodes[0]['type']='bse_port';nodes[0]['params']['port_roles']={'OUT':'dl'}
    # 无probe显式CE路径，验证BSE自己权威角色的冲突而非CE路径起点。
    nodes[-1]['params'].pop('rf_path_selection')
    row.nodes=nodes;db.commit()
    before=raw(world,url)
    response=client.post(url+'/conversion-preview',params=scope,json={
        'nodes':[{'node_id':'ce','port_directions':{'OUT':'input'}}]})
    assert response.status_code==422 and 'port_roles' in response.text,response.text
    assert raw(world,url)==before


@pytest.mark.parametrize('code', [5,6,517,262])
def test_sqlite_extended_busy_locked_codes_rollback(world,monkeypatch,code):
    """实际BUSY另测；本例注入DBAPI准确码，证明extended码分类不靠英文字符串。"""
    import sqlite3
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.dml import Update
    from sqlalchemy.exc import OperationalError
    url,scope=create(world)
    p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    before=raw(world,url)
    execute=Session.execute
    def refuse(self,statement,*args,**kwargs):
        if isinstance(statement,Update):
            error=sqlite3.OperationalError('不可据此文本分类')
            error.sqlite_errorcode=code
            raise OperationalError(str(statement),{},error)
        return execute(self,statement,*args,**kwargs)
    monkeypatch.setattr(Session,'execute',refuse)
    assert commit(world,url,scope,p).status_code==409
    assert raw(world,url)==before


def test_digest_numeric_equivalence_and_missing_null_differ():
    from app.services.topology_conversion import conversion_source_digest
    source={'id':'x','chamber_id':'lab','switch_category_id':'cat',**graph()}
    one=copy.deepcopy(source);one['connections'][0]['cable_loss_db']=2.0
    assert conversion_source_digest(source)==conversion_source_digest(one)
    one['connections'][0].pop('cable_loss_db')
    two=copy.deepcopy(one);two['connections'][0]['cable_loss_db']=None
    assert conversion_source_digest(one)!=conversion_source_digest(two)


def test_pure_builder_does_not_mutate_source_or_add_unrequested_keys():
    from app.schemas.topology_conversion import TopologyConversionRequest
    from app.services.topology_conversion import build_conversion
    source=graph();before=copy.deepcopy(source)
    candidate=build_conversion(source,TopologyConversionRequest.model_validate({
        'connections':[{'connection_id':'a','cable_loss_db':None}]}))
    assert source==before
    assert candidate['nodes']==before['nodes']
    assert candidate['operating_modes']==before['operating_modes']
    assert candidate['connections'][1]==before['connections'][1]
    assert candidate['connections'][0]['cable_loss_db'] is None
    assert 'loss_owner_connection_id' not in candidate['connections'][1]


def test_conversion_rejects_half_group_in_any_mode(world):
    data=graph()
    data['operating_modes'].append({'id':'other','name':'另模式','active_connections':['a']})
    url,scope=create(world,data)
    before=raw(world,url)
    response=world[2].post(url+'/conversion-preview',params=scope,json={'connections':[{
        'connection_id':'b','loss_owner_connection_id':'a','same_physical_cable_confirmed':True}]})
    assert response.status_code==422 and 'other' in response.text,response.text
    assert raw(world,url)==before
