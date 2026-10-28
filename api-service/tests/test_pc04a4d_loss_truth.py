"""真实HTTP和实际解析器：未知不是零，归属不是另一份量值。"""
from tests.topology_revision_requests import saved_revision as _saved_revision
import copy
import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import SessionLocal, Base, engine
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.models.instrument import InstrumentCategory
from app.services.bootstrap import run_bootstrap_on_startup
from tests.test_pc04a2_route_application import db_session, payload, confirm
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured
from tests.test_pc04a2_route_eligibility import real_capture
from tests.test_pc04a2_route_freeze import legacy, launch, entries


@pytest.fixture(scope='module', autouse=True)
def bootstrap():
    if engine.dialect.name != 'sqlite' or not str(engine.url).startswith('sqlite:////tmp/'):
        raise RuntimeError('本模块只允许调用方在app导入前指定专用/tmp新SQLite，禁止修改默认数据库')
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal)
    with SessionLocal() as db:
        for category in db.query(InstrumentCategory):
            category.driver_mode = 'mock'
        for lab in db.query(LabProfile):
            lab.instrument_bindings = [{**b, 'driver_mode': 'mock'} for b in lab.instrument_bindings or []]
        db.commit()
        assert all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory))
        assert all(b['driver_mode'] == 'mock' for l in db.query(LabProfile) for b in l.instrument_bindings or [])


@pytest.fixture
def world():
    with SessionLocal() as db:
        chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'归属测试{uuid.uuid4()}')
        db.add(chamber); db.flush()
        lab = LabProfile(name=f'归属测试{uuid.uuid4()}', chamber_config_id=chamber.id, is_active=True)
        db.add(lab); db.commit()
        with TestClient(app) as client:
            yield db, lab, client


def graph():
    return dict(nodes=[
        dict(id='ce', type='ce_port', label='B1.1', params={'ports':['OUT'], 'port_directions':{'OUT':'output'}}),
        dict(id='wire', type='cable', label='线缆', params={'ports':['IN','OUT'],
            'port_directions':{'IN':'input','OUT':'output'}, 'internal_paths':[{'from_port':'IN','to_port':'OUT'}]}),
        dict(id='probe', type='probe', label='探头', params={'ports':['IN'], 'probe_id':0, 'polarization':'V',
            'port_directions':{'IN':'input'}, 'rf_path_selection':{'connection_ids':['a','b'],'switch_mappings':[]}})],
        connections=[dict(id='a',source='ce',source_pin='OUT',target='wire',target_pin='IN',cable_loss_db=2,modes=['mimo_ota']),
                     dict(id='b',source='wire',source_pin='OUT',target='probe',target_pin='IN',cable_loss_db=2,modes=['mimo_ota'])],
        operating_modes=[dict(id='mimo_ota',name='正常',active_connections=['a','b'])])


def create(world, data=None):
    db, lab, client = world
    response = client.post('/api/v1/switch-topologies',json=dict(name='损耗',
        switch_category_id=str(uuid.uuid4()),lab_profile_id=str(lab.id),is_default=True,**(data or graph())))
    assert response.status_code == 201, response.text
    return f"/api/v1/switch-topologies/{response.json()['id']}", {'lab_profile_id':str(lab.id)}


@pytest.mark.parametrize('value', [None,0])
def test_http_clear_and_zero_roundtrip(world,value):
    _,_,client=world
    url,scope=create(world)
    edges=graph()['connections']; edges[0]['cable_loss_db']=value
    response=client.patch(url,params=scope,json={**({'connections':edges}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code==200,response.text
    assert client.get(url,params=scope).json()['connections'][0]['cable_loss_db']==value
    assert next(x for x in client.get('/api/v1/switch-topologies',params=scope).json()['items'] if url.endswith(x['id']))['connections'][0]['cable_loss_db']==value
    paths=client.get(url+'/paths/mimo_ota',params=scope)
    assert paths.status_code==200,paths.text
    matrix=client.get(url+'/calibration-matrix/mimo_ota',params=scope)
    assert matrix.status_code==200,matrix.text
    assert next(iter(matrix.json()['matrix'].values()))['total_loss_db']==(None if value is None else 2)


@pytest.mark.parametrize('owner_value,expected', [(2,2),(0,0),(None,None)])
def test_http_owner_keeps_alias_and_terminal_changes_source(world,owner_value,expected):
    from app.services.mimo_ota.switch_orchestrator import _build_probe_binding
    from app.services.topology_service import TopologyService
    _,_,client=world
    url,scope=create(world)
    data=graph(); data['connections'][0]['cable_loss_db']=owner_value
    data['connections'][1]['loss_owner_connection_id']='a'
    response=client.patch(url,params=scope,json={**(data), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code==200,response.text
    saved=client.get(url,params=scope).json()
    assert saved['connections'][1]['loss_owner_connection_id']=='a'
    assert saved['connections'][1]['cable_loss_db']==2
    service=TopologyService(saved)
    assert service.get_end_to_end_loss('ce','probe')==expected
    binding=_build_probe_binding(saved['connections'][1],{n['id']:n for n in saved['nodes']},saved['connections'])
    assert binding.cable_loss_db==expected


@pytest.mark.parametrize('bad', ['missing','delete-alias','self','cycle','half','cross-mode','reconnect','alias-value','type','second-alias','alias-pin'])
def test_http_invalid_ownership_is_atomic(world,bad):
    _,_,client=world
    initial=graph();initial['connections'][1]['loss_owner_connection_id']='a'
    url,scope=create(world,initial)
    data=copy.deepcopy(initial)
    if bad=='missing': data['connections'].pop(0)
    if bad=='delete-alias':
        data['connections'].pop(1)
        data['operating_modes'][0]['active_connections']=['a']
        data['nodes'][2]['params'].pop('rf_path_selection')
    if bad=='self': data['connections'][1]['loss_owner_connection_id']='b'
    if bad=='cycle': data['connections'][0]['loss_owner_connection_id']='b'
    if bad=='half': data['operating_modes'][0]['active_connections']=['b']
    if bad=='reconnect': data['connections'][0]['target']='probe'
    if bad=='alias-value': data['connections'][1]['cable_loss_db']=3
    if bad=='type':data['nodes'][1]['type']='pad'
    if bad=='alias-pin':data['connections'][1]['source_pin']='IN'
    if bad=='cross-mode':
        data['operating_modes'][0]['active_connections']=['a']
        data['operating_modes'].append(dict(id='calibration',name='校准',active_connections=['b']))
    if bad=='second-alias':
        data['connections'].append({**data['connections'][1],'id':'c'})
        data['operating_modes'][0]['active_connections'].append('c')
    before=client.get(url,params=scope).json()
    response=client.patch(url,params=scope,json={**(data), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code==422,response.text
    after=client.get(url,params=scope).json()
    assert after==before


def test_zero_calibrated_precedes_nominal_and_unknown_does_not_become_zero():
    from app.services.mimo_ota.switch_orchestrator import _build_probe_binding
    data=graph(); data['connections'][1]['calibrated_loss_db']=0
    assert _build_probe_binding(data['connections'][1],{n['id']:n for n in data['nodes']},data['connections']).cable_loss_db==0


def test_effective_loss_contract():
    from app.services.topology_loss import effective_connection_loss
    assert effective_connection_loss({'calibrated_loss_db':0,'cable_loss_db':5})==0
    assert effective_connection_loss({'calibrated_loss_db':-2,'cable_loss_db':5})==-2
    assert effective_connection_loss({'cable_loss_db':None}) is None
    assert effective_connection_loss({}) is None


@pytest.mark.parametrize('legacy_reference', [False,True])
@pytest.mark.parametrize('location', ['normal','reference'])
@pytest.mark.parametrize('fallback', [False,True])
def test_ownership_changes_scope_not_route_or_physical_identity(world,location,fallback,legacy_reference):
    from app.services.calibration.route_calibration import list_route_selections
    from app.services.calibration.configuration_scope import build_selected_route_calibration_scope
    from app.services.calibration.rf_chain_resolver import resolve_rf_chains
    db,lab,client=world
    data=graph()
    data['nodes'][2]['params']['ports'].append('REF')
    data['nodes'][2]['params']['port_directions']['REF']='output'
    data['nodes'] += [dict(id='receive',type='receive_cable',label='接收线缆',params={
        'ports':['IN','OUT'],'port_directions':{'IN':'input','OUT':'output'},
        'internal_paths':[{'from_port':'IN','to_port':'OUT'}], 'connection_scope':'calibration'}),
        dict(id='sa',type='signal_analyzer',label='SA',params={'ports':['IN'],'port_directions':{'IN':'input'},'connection_scope':'calibration'})]
    data['connections'] += [dict(id='r1',source='probe',source_pin='REF',target='receive',target_pin='IN',cable_loss_db=2,modes=['calibration']),
        dict(id='r2',source='receive',source_pin='OUT',target='sa',target_pin='IN',cable_loss_db=2,modes=['calibration'])]
    data['operating_modes'].append(dict(id='calibration',name='参考',active_connections=['r1','r2']))
    if fallback:
        for mode in data['operating_modes']:mode['active_connections']=[]
    url,scope=create(world,data)
    ident=uuid.UUID(url.rsplit('/',1)[1])
    if legacy_reference:
        # 历史原行缺声明；不能用当前POST凭空制造可采集资格。
        data['nodes'][-2]['params']={'connection_scope':'calibration'}
        saved=db.get(SwitchTopology,ident)
        saved.nodes=copy.deepcopy(data['nodes'])
        db.commit()
    if not legacy_reference:
        before=list_route_selections(db,lab.id,ident,'mimo_ota')[0]
    identity=resolve_rf_chains(db,lab.id).chains[0].execution_route_identity
    endpoint=f'/api/v1/lab-profiles/{lab.id}/calibration-scope'
    baseline=client.get(endpoint).json()
    assert 'payload' in baseline,baseline
    if not legacy_reference:
        selected_before=build_selected_route_calibration_scope(db,lab.id,'mimo_ota',topology_id=ident,chain_id='b')
    assert 'loss_ownership' not in baseline['payload']['topology']
    data['connections'][1 if location=='normal' else 3]['loss_owner_connection_id']='a' if location=='normal' else 'r1'
    changes={'nodes':[], 'connections':[{'connection_id':'b' if location=='normal' else 'r2',
        'loss_owner_connection_id':'a' if location=='normal' else 'r1','same_physical_cable_confirmed':True}]}
    preview=client.post(url+'/conversion-preview',params=scope,json=changes)
    assert preview.status_code==200,preview.text
    response=client.patch(url,params=scope,json={**({'conversion':{
        'source_digest':preview.json()['source_digest'],'changes':preview.json()['changes']}}), 'expected_revision': preview.json()['revision']})
    assert response.status_code==200,response.text
    db.expire_all()
    if legacy_reference:
        with pytest.raises(ValueError,match='内部通路未声明'):
            list_route_selections(db,lab.id,ident,'mimo_ota')
        strict=client.get(f'/api/v1/lab-profiles/{lab.id}/route-calibration-paths',params={
            'topology_id':str(ident),'operating_mode':'mimo_ota'})
        assert strict.status_code==422,strict.text
    else:
        after=list_route_selections(db,lab.id,ident,'mimo_ota')[0]
        assert after.route_digest==before.route_digest
    assert resolve_rf_chains(db,lab.id).chains[0].execution_route_identity==identity
    baseline_json=json.dumps(baseline,sort_keys=True)
    current=client.get(endpoint)
    comparison=client.post(endpoint+'/compare',json={'baseline':baseline})
    assert current.status_code==200,current.text
    assert comparison.status_code==200,comparison.text
    assert current.json()['digest']!=baseline['digest']
    expected=[{'id':'b' if location=='normal' else 'r2','loss_owner_connection_id':'a' if location=='normal' else 'r1'}]
    assert current.json()['payload']['topology']['loss_ownership']==expected
    assert comparison.json()['requires_review'] is True
    assert json.dumps(baseline,sort_keys=True)==baseline_json
    if legacy_reference and location=='reference':
        # 没有保存参考模式时，孤立的边modes不是所选参考路径。
        saved=db.get(SwitchTopology,ident)
        saved.operating_modes=[m for m in saved.operating_modes if m['id']!='calibration']
        db.commit()
        no_mode=client.get(endpoint)
        assert no_mode.status_code==200,no_mode.text
        assert 'loss_ownership' not in no_mode.json()['payload']['topology']
    if not legacy_reference:
        selected_after=build_selected_route_calibration_scope(db,lab.id,'mimo_ota',topology_id=ident,chain_id='b')
        assert selected_after.digest!=selected_before.digest
        assert selected_after.payload.topology['loss_ownership']==expected


@pytest.mark.parametrize('value', [None,'missing',0])
@pytest.mark.parametrize('shape', ['direct','two-hop'])
def test_http_actual_resolver_lab_scope_and_legacy_unknown_before_lease(world,monkeypatch,value,shape):
    import asyncio
    from app.services.calibration.rf_chain_resolver import resolve_rf_chains
    from app.services.path_loss_calibration_service import ProbePathLossCalibrationService
    db,lab,client=world
    data=graph()
    if shape=='direct':
        data['nodes'].pop(1)
        data['connections']=[{**data['connections'][1],'source':'ce'}]
        data['nodes'][-1]['params']['rf_path_selection']['connection_ids']=['b']
        data['operating_modes'][0]['active_connections']=['b']
    edge=data['connections'][-1]
    if value=='missing':edge.pop('cable_loss_db')
    else:edge['cable_loss_db']=value
    url,scope=create(world,data)
    result=client.get(f'/api/v1/lab-profiles/{lab.id}/rf-chains')
    assert result.status_code==200,result.text
    expected=0 if value==0 else None
    assert len(result.json()['chains'])==1 and result.json()['chains'][0]['cable_loss_db']==expected
    snapshot=client.get(f'/api/v1/lab-profiles/{lab.id}/calibration-scope')
    assert snapshot.status_code==200,snapshot.text
    assert snapshot.json()['payload']['chains'][0]['cable_loss_db']==expected
    assert resolve_rf_chains(db,lab.id).chains[0].cable_loss_db==expected
    if value=='missing':assert 'cable_loss_db' not in client.get(url,params=scope).json()['connections'][-1]
    if expected is None:
        def forbidden(*args,**kwargs):raise AssertionError('未知链不应触碰lease或preflight')
        monkeypatch.setattr('app.services.instrument_test_lease.instrument_test_lease',forbidden)
        service=ProbePathLossCalibrationService(db,use_mock=False)
        monkeypatch.setattr(service,'preflight_sa_power_via_ce_tone',forbidden)
        result=asyncio.run(service.start_calibration_for_lab_profile(lab.id,'mimo_ota',3500,'SGH',10))
        assert not result.success and 'b' in result.message and '未知' in result.message
    else:
        service=ProbePathLossCalibrationService(db,use_mock=True)
        result=asyncio.run(service.start_calibration_for_lab_profile(lab.id,'mimo_ota',3500,'SGH',10))
        assert result.success,result.message


@pytest.mark.parametrize('bad',[True,'2',-1])
def test_http_new_bad_nominal_rejected(world,bad):
    _,_,client=world
    data=graph();data['connections'][0]['cable_loss_db']=bad
    response=client.post('/api/v1/switch-topologies',json=dict(name='坏数值',switch_category_id=str(uuid.uuid4()),
        lab_profile_id=str(world[1].id),**data))
    assert response.status_code==422,response.text


def test_http_import_owner_null_and_alias_zero_source(world,monkeypatch):
    from app.api import switch_topology as api
    _,lab,client=world
    data=graph();data['name']='导入';data['connections'][0].update(cable_loss_db=None,calibrated_loss_db=0)
    data['connections'][1]['loss_owner_connection_id']='a'
    monkeypatch.setattr(api,'_load_template',lambda _:lambda:data)
    response=client.post('/api/v1/switch-topologies/import/from-template',params={
        'switch_category_id':str(uuid.uuid4()),'lab_profile_id':str(lab.id),'template_id':'test'})
    assert response.status_code==200,response.text
    assert response.json()['connections'][0]['cable_loss_db'] is None
    assert response.json()['connections'][1]['loss_owner_connection_id']=='a'


def test_http_import_invalid_owner_fails_before_replacement(world,monkeypatch):
    from app.api import switch_topology as api
    _,lab,client=world
    url,scope=create(world)
    original=client.get(url,params=scope).json()
    data=graph();data['name']='非法导入';data['connections'][1]['loss_owner_connection_id']='missing'
    monkeypatch.setattr(api,'_load_template',lambda _:lambda:data)
    response=client.post('/api/v1/switch-topologies/import/from-template',params={
        'switch_category_id':original['switch_category_id'],'lab_profile_id':str(lab.id),
        'template_id':'test','replace_existing':True})
    assert response.status_code==422,response.text
    assert client.get(url,params=scope).json()==original


@pytest.mark.parametrize('value',[True,-1,float('nan')])
def test_http_import_invalid_nominal_fails_before_replacement(world,monkeypatch,value):
    from app.api import switch_topology as api
    _,lab,client=world
    url,scope=create(world)
    original=client.get(url,params=scope).json()
    data=graph();data['name']='非法量值';data['connections'][0]['cable_loss_db']=value
    monkeypatch.setattr(api,'_load_template',lambda _:lambda:data)
    response=client.post('/api/v1/switch-topologies/import/from-template',params={
        'switch_category_id':original['switch_category_id'],'lab_profile_id':str(lab.id),
        'template_id':'test','replace_existing':True})
    assert response.status_code==422,response.text
    assert client.get(url,params=scope).json()==original


def test_upstream_group_never_sums_into_formal_terminal_and_phase_is_unchanged(world):
    from app.services.mimo_ota.switch_orchestrator import _build_probe_binding
    from app.services.topology_service import TopologyService
    _,_,client=world
    data=graph()
    pad=copy.deepcopy(data['nodes'][1]);pad.update(id='pad',type='pad')
    data['nodes'].insert(2,pad)
    data['connections'][1].update(target='pad',loss_owner_connection_id='a')
    data['connections'].append(dict(id='c',source='pad',source_pin='OUT',target='probe',target_pin='IN',cable_loss_db=3))
    data['nodes'][-1]['params']['rf_path_selection']['connection_ids']=['a','b','c']
    data['operating_modes'][0]['active_connections']=['a','b','c']
    for edge,phase in zip(data['connections'],[10,20,30]):edge['calibrated_phase_deg']=phase
    url,scope=create(world,data)
    saved=client.get(url,params=scope).json()
    service=TopologyService(saved)
    assert service.resolve_paths('mimo_ota')[0].total_loss_db==5
    assert service.resolve_paths('mimo_ota')[0].total_phase_deg==60
    assert _build_probe_binding(saved['connections'][-1],{n['id']:n for n in saved['nodes']},saved['connections']).cable_loss_db==3
    saved['connections'][0]['cable_loss_db']=None
    assert TopologyService(saved).get_end_to_end_loss('ce','probe') is None
    assert _build_probe_binding(saved['connections'][-1],{n['id']:n for n in saved['nodes']},saved['connections']).cable_loss_db==3


def test_explicit_ungroup_restores_both_original_values(world):
    from app.services.topology_service import TopologyService
    _,_,client=world
    data=graph();data['connections'][1]['loss_owner_connection_id']='a'
    url,scope=create(world,data)
    assert TopologyService(client.get(url,params=scope).json()).get_end_to_end_loss('ce','probe')==2
    data['connections'][1].pop('loss_owner_connection_id')
    response=client.patch(url,params=scope,json={**({'connections':data['connections']}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code==200,response.text
    assert TopologyService(response.json()).get_end_to_end_loss('ce','probe')==4
    assert [e['cable_loss_db'] for e in response.json()['connections']]==[2,2]


@pytest.mark.parametrize('owner',[None,'','b','missing'])
def test_post_owner_invalid_reference_is_not_dropped(world,owner):
    _,lab,client=world
    data=graph();data['connections'][1]['loss_owner_connection_id']=owner
    response=client.post('/api/v1/switch-topologies',json=dict(name='坏归属',switch_category_id=str(uuid.uuid4()),
        lab_profile_id=str(lab.id),**data))
    assert response.status_code==422,response.text


@pytest.mark.parametrize('ids',[['a'],['b'],['a','a','b']])
def test_runtime_does_not_borrow_unselected_owner_or_trust_old_write(ids):
    from app.services.topology_loss import loss_sources_for_path
    data=graph();data['connections'][1]['loss_owner_connection_id']='a'
    with pytest.raises(ValueError):loss_sources_for_path(data['nodes'],data['connections'],ids)


def test_end_to_end_ownership_keeps_the_actual_mode_edge_set():
    from app.services.topology_service import TopologyService
    data=graph();data['nodes'][1]['params'].pop('internal_paths')
    data['connections'][1]['loss_owner_connection_id']='a'
    data['connections'] += [{**data['connections'][0],'id':'other-a'},
        {**data['connections'][1],'id':'other-b','loss_owner_connection_id':'other-a'}]
    data['operating_modes'].append(dict(id='other',name='另一模式',active_connections=['other-a','other-b']))
    assert TopologyService(data).get_end_to_end_loss('ce','probe')==2


def test_service_export_does_not_add_missing_loss_or_owner():
    from app.services.topology_service import TopologyService
    data=graph();data['connections'][0].pop('cable_loss_db')
    exported=TopologyService(data).to_dict()['connections']
    assert 'cable_loss_db' not in exported[0]
    assert all('loss_owner_connection_id' not in edge for edge in exported)


@pytest.mark.parametrize('entry',['topology','selected'])
@pytest.mark.parametrize('value',[3,0,None])
def test_explicit_scope_chain_uses_actual_terminal_not_identity_placeholder(world,entry,value):
    from app.services.calibration.configuration_scope import build_calibration_scope, build_selected_route_calibration_scope, scope_digest
    from app.schemas.calibration_scope import CalibrationScopeSnapshot
    db,lab,_=world
    data=graph();data['connections'][0]['cable_loss_db']=value
    data['connections'][1]['loss_owner_connection_id']='a'
    url,_=create(world,data)
    ident=uuid.UUID(url.rsplit('/',1)[1])
    if entry=='topology':current=build_calibration_scope(db,lab.id,'mimo_ota',topology_id=ident)
    else:current=build_selected_route_calibration_scope(db,lab.id,'mimo_ota',topology_id=ident,chain_id='b')
    assert current.payload.chains[0].cable_loss_db==value
    # 历史payload自行校验摘要，不以当前图补全它的旧占位值。
    baseline=current.model_copy(deep=True)
    baseline.payload.chains[0].cable_loss_db=0
    baseline.digest=scope_digest(baseline.payload)
    original=baseline.model_dump_json()
    parsed=CalibrationScopeSnapshot.model_validate_json(original)
    assert scope_digest(parsed.payload)==baseline.digest
    assert parsed.model_dump_json()==original


@pytest.mark.asyncio
@pytest.mark.parametrize('location',['normal','reference'])
async def test_confirmed_whole_chain_not_readded_and_history_not_rewritten(client,configured,real_capture,
        legacy,launch,db_session,topology_two_chains,location):
    from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation
    topology=topology_two_chains
    topology.nodes=[*topology.nodes,dict(id='wire',type='cable',label='线缆',params={'ports':['in','out'],
        'port_directions':{'in':'input','out':'output'},'internal_paths':[{'from_port':'in','to_port':'out'}]})]
    topology.connections=[{**edge,**({'source':'wire','source_pin':'out','cable_loss_db':2,'calibrated_loss_db':None}
        if edge['id']=='conn_p0v' else {})} for edge in topology.connections]
    topology.connections=[dict(id='owner',source='ce_b1',source_pin='out',target='wire',target_pin='in',cable_loss_db=2),*topology.connections]
    topology.operating_modes=[{**m,'active_connections':['owner',*m['active_connections']]} for m in topology.operating_modes]
    if location=='reference':
        topology.nodes=[*topology.nodes,dict(id='receive',type='receive_cable',label='接收线缆',params={
            'connection_scope':'calibration','ports':['in','out'],'port_directions':{'in':'input','out':'output'},
            'internal_paths':[{'from_port':'in','to_port':'out'}]}),
            dict(id='sa',type='signal_analyzer',label='分析仪',params={'connection_scope':'calibration'})]
        topology.connections=[*topology.connections,
            dict(id='r1',source='probe_0_v',source_pin='ref',target='receive',target_pin='in',cable_loss_db=2),
            dict(id='r2',source='receive',source_pin='out',target='sa',target_pin='in',cable_loss_db=2)]
        topology.operating_modes=[*topology.operating_modes,dict(id='calibration',active_connections=['r1','r2'])]
    db_session.commit()
    row=real_capture()
    evidence=copy.deepcopy(row.sequence_evidence)
    response=confirm(client,configured,payload(client,configured,row))
    assert response.status_code==201,response.text
    first=await launch()
    freeze=copy.deepcopy(first.config['route_calibration_freeze'])
    certificate=lambda:hashlib.sha256(json.dumps({column.name:getattr(legacy,column.name)
        for column in legacy.__table__.columns},sort_keys=True,default=str).encode()).hexdigest()
    cert=certificate()
    alias,owner=('conn_p0v','owner') if location=='normal' else ('r2','r1')
    topology.connections=[{**edge,**({'loss_owner_connection_id':owner} if edge['id']==alias else {})}
        for edge in topology.connections]
    db_session.commit()
    second=await launch()
    assert entries(second)['conn_p0v']['source_kind']=='confirmed_route'
    assert entries(second)['conn_p0v']['value_db']==28
    if location=='normal':
        topology.connections=[{**edge,**({'cable_loss_db':None} if edge['id']=='owner' else {})}
            for edge in topology.connections]
        db_session.commit()
        unknown_nominal=await launch()
        assert entries(unknown_nominal)['conn_p0v']['source_kind']=='confirmed_route'
        assert entries(unknown_nominal)['conn_p0v']['value_db']==28
    assert read_execution_route_compensation(first)==freeze
    assert certificate()==cert and row.sequence_evidence==evidence
    # 真正端点变化不因量值归属声明获得豁免。
    topology.connections=[{**edge,**({'source_pin':'other'} if edge['id']=='owner' else {})} for edge in topology.connections]
    db_session.commit()
    third=await launch()
    assert entries(third).get('conn_p0v',{}).get('source_kind')!='confirmed_route'
