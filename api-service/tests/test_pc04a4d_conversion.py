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


@pytest.mark.parametrize('value', ['missing', None, 0, 2.5, '2.50'])
def test_task4_raw_sparse_loss_survives_unrelated_conversion(world, value):
    """GET会转型，保形断言必须读SQL原行；未知多hop不是0。"""
    from app.models.switch_topology import SwitchTopology
    db,lab,client=world
    url,scope=create(world)
    row=db.get(SwitchTopology,uuid.UUID(url.rsplit('/',1)[1]))
    edges=copy.deepcopy(row.connections)
    if value=='missing':
        edges[0].pop('cable_loss_db')
    else:
        edges[0]['cable_loss_db']=value
    row.connections=edges;db.commit()
    p=preview(world,url,scope,{'nodes':[{'node_id':'ce','ports':['OUT']}]})
    assert commit(world,url,scope,p).status_code==200
    db.expire_all();saved=db.get(SwitchTopology,row.id)
    assert saved.connections==edges
    matrix=client.get(url+'/calibration-matrix/mimo_ota',params=scope)
    assert matrix.status_code==200,matrix.text
    expected=None if value in ('missing',None) else float(value)+2
    assert next(iter(matrix.json()['matrix'].values()))['total_loss_db']==expected


@pytest.mark.parametrize('kind,field,unit', [('amplifier','gain_db','dB'),('pad','attenuation_db','dB'),
    ('combiner','loss_db','dB'),('probe','gain_dbi','dBi'),('antenna','gain_dbi','dBi'),
    ('reference_antenna','gain_dbi','dBi')])
def test_task4_source_only_preserves_six_legacy_nominals_and_integrated_pa(world,kind,field,unit):
    from app.models.switch_topology import SwitchTopology
    db,lab,client=world
    url,scope=create(world)
    row=db.get(SwitchTopology,uuid.UUID(url.rsplit('/',1)[1]))
    row.nodes=[dict(id='legacy',type=kind,label='原声明',params={field:'2.50',
        'opaque':[None,0]})]
    row.connections=[];row.operating_modes=[];db.commit()
    nodes=copy.deepcopy(row.nodes)
    nodes[0]['params']['nominal_metadata']={field:{'unit':unit,'source_note':'Task4仅补来源待核'}}
    response=client.patch(url,params=scope,json={'nodes':nodes})
    assert response.status_code==200,response.text
    db.expire_all();assert db.get(SwitchTopology,row.id).nodes[0]['params'][field]=='2.50'
    # 集成PA边不拆成节点，不改原量值/长度/校准零，也不借GET模型做before。
    row=db.get(SwitchTopology,row.id)
    row.nodes=graph()['nodes'];row.connections=graph()['connections'];row.operating_modes=graph()['operating_modes']
    edges=copy.deepcopy(row.connections);edges[0].update(pa_gain_db='12.50',cable_loss_db='2.50',calibrated_loss_db=0)
    row.connections=edges;db.commit()
    edges=copy.deepcopy(edges);edges[0]['nominal_metadata']={'pa_gain_db':{'unit':'dB','source_note':'Task4集成PA原声明待核'}}
    response=client.patch(url,params=scope,json={'connections':edges})
    assert response.status_code==200,response.text
    db.expire_all();saved=db.get(SwitchTopology,row.id)
    assert len(saved.nodes)==3 and saved.connections[0]['pa_gain_db']=='12.50'
    assert saved.connections[0]['cable_loss_db']=='2.50' and saved.connections[0]['calibrated_loss_db']==0


def test_task4_existing_diagnostic_report_read_download_unchanged_by_conversion(world,tmp_path,monkeypatch):
    """真实报告端点与文件下载；仅Mock诊断，不授予正式测量资格。"""
    import hashlib
    from app.models.report import TestReport
    from app.models.test_plan import TestExecution
    from tests.test_p1_81_diagnostic_report_trust import _diagnostic_execution
    db,lab,client=world
    url,scope=create(world)
    source=_diagnostic_execution({'cqi_index'})
    execution=TestExecution(id=source.id,status='completed',config=source.config,
        measurements=source.measurements,duration_sec=source.duration_sec,
        completed_at=source.completed_at,topology_id=url.rsplit('/',1)[1])
    report=TestReport(id=uuid.uuid4(),title='Task4 Mock诊断报告',report_type='single_execution',
        format='pdf',status='completed',generated_by='user',test_execution_ids=[str(execution.id)],
        content_data={'report_family':'mimo_ota'})
    db.add_all([execution,report]);db.commit()
    monkeypatch.chdir(tmp_path)
    endpoint='/api/v1/reports/'+str(report.id)
    generated=client.post(endpoint+'/generate')
    assert generated.status_code==200,generated.text
    assert generated.json()['execution_evidence_outcome']['formal_eligible'] is False
    detail=client.get(endpoint);download=client.get(endpoint+'/download')
    assert detail.status_code==200 and download.status_code==200
    before=copy.deepcopy(execution.config)
    p=preview(world,url,scope,{'connections':[{'connection_id':'b','loss_owner_connection_id':'a',
        'same_physical_cable_confirmed':True}]})
    assert commit(world,url,scope,p).status_code==200
    assert client.get(endpoint).json()==detail.json()
    after=client.get(endpoint+'/download')
    assert after.status_code==200 and hashlib.sha256(after.content).digest()==hashlib.sha256(download.content).digest()
    db.expire_all();assert db.get(TestExecution,execution.id).config==before


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


def test_preview_zero_sql_writes_and_nonempty_history_immutable(world,monkeypatch):
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
    def forbidden_hal():
        raise AssertionError('只读转换预览不得访问HAL')
    monkeypatch.setattr('app.services.instrument_hal_service.get_hal_service',forbidden_hal)
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


def test_preview_repairs_old_unrunnable_source_without_mutation(world):
    from app.models.switch_topology import SwitchTopology
    db,lab,client=world
    url,scope=create(world)
    row=db.get(SwitchTopology,uuid.UUID(url.rsplit('/',1)[1]))
    nodes=copy.deepcopy(row.nodes)
    nodes[1]['params'].pop('ports');nodes[1]['params'].pop('internal_paths')
    row.nodes=nodes;db.commit()
    before=raw(world,url)
    changes={'nodes':[{'node_id':'wire','ports':['IN','OUT'],
                       'internal_paths':[{'from_port':'IN','to_port':'OUT'}]}]}
    p=preview(world,url,scope,changes)
    assert any('旧' in warning and '未知' in warning for warning in p['warnings'])
    assert any('通用总损耗' in warning and '4' in warning for warning in p['warnings'])
    assert raw(world,url)==before
    assert commit(world,url,scope,p).status_code==200
    response=client.get(url+'/paths/mimo_ota',params=scope)
    assert response.status_code==200 and len(response.json())==1,response.text


@pytest.mark.parametrize('legacy,target', [('ce_port','channel_emulator'),
    ('bse_port','communication_tester'),('sa_port','signal_analyzer')])
def test_equivalent_type_conversion_preserves_http_paths_and_matrix(world,legacy,target):
    data=graph()
    data['nodes'][0]['type']=legacy
    data['nodes'][-1]['params'].pop('rf_path_selection')
    url,scope=create(world,data)
    client=world[2]
    before_paths=client.get(url+'/paths/mimo_ota',params=scope)
    assert before_paths.status_code==200 and len(before_paths.json())==1,before_paths.text
    p=preview(world,url,scope,{'nodes':[{'node_id':'ce','target_type':target,
                                        **({'ce_port':'B1.1'} if legacy=='ce_port' else {})}]})
    assert commit(world,url,scope,p).status_code==200
    after_paths=client.get(url+'/paths/mimo_ota',params=scope)
    assert after_paths.status_code==200 and len(after_paths.json())==1,after_paths.text
    assert any('通用总损耗' in warning and '4' in warning for warning in p['warnings'])
    assert after_paths.json()[0]['source_node']['type']==target
    assert after_paths.json()[0]['total_loss_db']==4
    matrix=client.get(url+'/calibration-matrix/mimo_ota',params=scope)
    assert matrix.status_code==200 and len(matrix.json()['matrix'])==1,matrix.text
    assert next(iter(matrix.json()['matrix'].values()))['total_loss_db']==4


@pytest.mark.parametrize('explicit_selection',[False,True])
def test_unknown_legacy_draft_preview_and_commit_remain_valid(world,explicit_selection):
    from app.models.switch_topology import SwitchTopology
    db,lab,client=world
    url,scope=create(world)
    row=db.get(SwitchTopology,uuid.UUID(url.rsplit('/',1)[1]))
    nodes=copy.deepcopy(row.nodes);nodes[1]['params']={}
    if not explicit_selection:nodes[-1]['params'].pop('rf_path_selection')
    row.nodes=nodes;db.commit()
    before=raw(world,url)
    p=preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    assert any('未声明' in warning for warning in p['warnings'])
    assert raw(world,url)==before
    assert commit(world,url,scope,p).status_code==200
    assert client.get(url,params=scope).json()['connections'][0]['cable_loss_db'] is None


def test_preview_does_not_suppress_unexpected_parser_exception(world,monkeypatch):
    from app.services.topology_service import TopologyService
    url,scope=create(world)
    before=raw(world,url)
    def unexpected(self,mode):
        raise RuntimeError('非运行资格的程序错误')
    monkeypatch.setattr(TopologyService,'resolve_paths',unexpected)
    with pytest.raises(RuntimeError,match='非运行资格的程序错误'):
        preview(world,url,scope,{'connections':[{'connection_id':'a','cable_loss_db':None}]})
    assert raw(world,url)==before
