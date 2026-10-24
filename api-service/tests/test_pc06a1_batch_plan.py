"""PC06A1：保存图驱动的零 I/O 清单及正式集合边界。"""
import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured
from tests.test_pc_04a_fixed_route_api import client
from tests.test_pc04a2_route_eligibility import real_capture
from tests.test_pc04a2_route_freeze import launch
from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection
from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
from app.services.calibration.rf_chain_resolver import resolve_rf_chains


@pytest.fixture
def shared_switch(db_session, configured, topology_two_chains):
    cat = InstrumentCategory(category_key='rfSwitch', category_name='开关', driver_mode='real')
    db_session.add(cat); db_session.flush()
    model = InstrumentModel(category_id=cat.id, model='EMCenter', vendor='ETS', capabilities={})
    db_session.add(model); db_session.flush(); cat.selected_model_id=model.id
    maps = {
        'v':dict(switch_id='1:INT_RELAY_A',relay_type='spdt',input_port=0,output_port='NC',topology_input_pin='in1',topology_output_pin='out1'),
        'h':dict(switch_id='1:INT_RELAY_B',relay_type='spdt',input_port=0,output_port='NO',topology_input_pin='in2',topology_output_pin='out2'),
    }
    conn=InstrumentConnection(category_id=cat.id,endpoint='192.0.2.20',created_by='test',connection_params={'port_maps':maps})
    db_session.add(conn)
    configured.instrument_bindings=[*configured.instrument_bindings,dict(category_id=str(cat.id),
        instrument_model_id=str(model.id),connection_endpoint=conn.endpoint,driver_mode='real')]
    topo=topology_two_chains
    topo.switch_category_id=cat.id
    topo.nodes=[
        dict(id='ce1',type='ce_port',label='B1.1',params={}),
        dict(id='ce2',type='ce_port',label='B1.2',params={}),
        dict(id='sw',type='switch_slot',params={'instrument_category_id':str(cat.id)}),
        dict(id='pv',type='probe',params={'probe_id':0,'polarization':'V','rf_path_selection':{
            'connection_ids':['iv','ov'],'switch_mappings':[{'node_id':'sw','path_name':'v'}]}}),
        dict(id='ph',type='probe',params={'probe_id':0,'polarization':'H','rf_path_selection':{
            'connection_ids':['ih','oh'],'switch_mappings':[{'node_id':'sw','path_name':'h'}]}}),
    ]
    topo.connections=[dict(id='iv',source='ce1',source_pin='out',target='sw',target_pin='in1'),
        dict(id='ih',source='ce2',source_pin='out',target='sw',target_pin='in2'),
        dict(id='ov',source='sw',source_pin='out1',target='pv',target_pin='in'),
        dict(id='oh',source='sw',source_pin='out2',target='ph',target_pin='in')]
    topo.operating_modes=[dict(id='mimo_ota',active_connections=['iv','ih','ov','oh'])]
    db_session.commit()
    return topo,conn


def request_for(topo, chains=('ov','oh'), frequencies=(2595.,3500.)):
    from app.schemas.route_batch import BatchPlanRequest
    return BatchPlanRequest(topology_id=topo.id,chain_ids=list(chains),frequencies_mhz=list(frequencies),
        references=[dict(chain_id=c,frequency_mhz=f,reference_antenna=f'REF {c} 中心',
            receive_cable_loss_db=2.,receive_cable_source=f'线缆 {f}MHz') for c in chains for f in frequencies],
        requested_power_dbm=-20.,sample_count=2,fixed_route_confirmed=True,safety_confirmed=True)


def test_saved_independent_switch_ports_reach_real_orchestrator_and_freeze(db_session,configured,shared_switch):
    from app.services.calibration.route_calibration import list_route_selections
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation,frozen_route_identity_error
    topo,_=shared_switch
    actual=orchestrate_switch_topology(db_session,configured.chamber_config_id)
    assert [(r.connection_id,r.ce_port,r.polarization) for r in actual.probe_bindings]==[('ov','B1.1','V'),('oh','B1.2','H')]
    assert len(resolve_rf_chains(db_session,configured.id).chains)==2
    assert len(list_route_selections(db_session,configured.id,topo.id,'mimo_ota'))==2
    frozen=resolve_effective_route_compensation(db_session,configured.id,'mimo_ota',2595.)
    assert frozen_route_identity_error(db_session,frozen,resolved_topology=actual) is None
    for replacement in ('missing','changed'):
        bad=copy.deepcopy(actual)
        if replacement=='missing': bad.probe_bindings.pop()
        else: bad.probe_bindings[1].probe_id=9
        assert frozen_route_identity_error(db_session,frozen,resolved_topology=bad)


def test_batch_expands_stably_and_binds_reference_per_frequency(db_session,configured,shared_switch):
    from app.services.calibration.route_batch_plan import build_batch_plan
    topo,_=shared_switch
    plan=build_batch_plan(db_session,configured.id,request_for(topo),SimpleNamespace(drivers={}))
    assert [(i.request.chain_id,i.request.frequency_mhz) for i in plan.items]==[
        ('oh',2595.),('oh',3500.),('ov',2595.),('ov',3500.)]
    assert len({i.item_id for i in plan.items})==4
    assert all(i.request.receive_cable_source==f'线缆 {i.request.frequency_mhz}MHz' for i in plan.items)
    assert plan.preview_digest==build_batch_plan(db_session,configured.id,request_for(topo),None).preview_digest
    assert len(plan.items[0].switch_steps)==1


def test_same_ce_serial_scope_does_not_call_formal_resolver(db_session,configured,shared_switch,monkeypatch):
    from app.services.calibration import configuration_scope as scopes
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.services.calibration.route_calibration import list_route_selections
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation
    topo,conn=shared_switch
    edges=copy.deepcopy(topo.connections);edges[1]['source']='ce1';edges[1]['target_pin']='in1';topo.connections=edges
    params=copy.deepcopy(conn.connection_params)
    params['port_maps']['h']['switch_id']='1:INT_RELAY_A';params['port_maps']['h']['topology_input_pin']='in1'
    conn.connection_params=params;db_session.commit()
    for call in (lambda:resolve_rf_chains(db_session,configured.id),
                 lambda:list_route_selections(db_session,configured.id,topo.id,'mimo_ota'),
                 lambda:scopes.build_calibration_scope(db_session,configured.id),
                 lambda:scopes.build_calibration_scope(db_session,configured.id,topology_id=topo.id),
                 lambda:resolve_effective_route_compensation(db_session,configured.id,'mimo_ota',2595.)):
        with pytest.raises(ValueError): call()
    def forbidden(*args,**kwargs): raise AssertionError('单项不应调用全局集合')
    monkeypatch.setattr(scopes,'resolve_rf_chains',forbidden)
    monkeypatch.setattr('app.services.calibration.route_calibration.list_route_selections',forbidden)
    v=scopes.build_selected_route_calibration_scope(db_session,configured.id,'mimo_ota',topology_id=topo.id,chain_id='ov')
    h=scopes.build_selected_route_calibration_scope(db_session,configured.id,'mimo_ota',topology_id=topo.id,chain_id='oh')
    assert [c.chain_id for c in v.payload.chains]==['ov']
    assert v.digest!=h.digest
    plan=build_batch_plan(db_session,configured.id,request_for(topo,frequencies=(2595.,)),None)
    assert len(plan.items)==2


@pytest.mark.parametrize('fault',['port','pair','passive_branch','no_declaration','cycle'])
def test_invalid_saved_route_is_rejected_in_normal_production_chain(db_session,configured,shared_switch,fault):
    topo,_=shared_switch
    nodes,edges=copy.deepcopy(topo.nodes),copy.deepcopy(topo.connections)
    if fault=='port': edges[2]['source_pin']='NO'
    elif fault=='pair': nodes[3]['params']['rf_path_selection']['connection_ids']=['ih','ov']
    elif fault=='passive_branch': nodes[2]['type']='pad'
    elif fault=='no_declaration': del nodes[3]['params']['rf_path_selection']
    else: nodes[3]['params']['rf_path_selection']['connection_ids']=['iv','ov','iv']
    topo.nodes,topo.connections=nodes,edges;db_session.commit()
    with pytest.raises(ValueError): orchestrate_switch_topology(db_session,configured.chamber_config_id)


@pytest.mark.parametrize('fault',['mapping','binding','path','port'])
def test_selected_scope_detects_saved_identity_drift(db_session,configured,shared_switch,fault):
    from app.services.calibration.configuration_scope import build_selected_route_calibration_scope
    topo,conn=shared_switch
    def scope(): return build_selected_route_calibration_scope(db_session,configured.id,'mimo_ota',topology_id=topo.id,chain_id='ov')
    before=scope().digest
    if fault=='mapping':
        params=copy.deepcopy(conn.connection_params);params['port_maps']['v']['switch_id']='1:INT_RELAY_C';conn.connection_params=params
    elif fault=='binding': conn.endpoint='192.0.2.99'
    elif fault=='path':
        nodes=copy.deepcopy(topo.nodes);nodes[3]['params']['rf_path_selection']['connection_ids']=['ih','ov'];topo.nodes=nodes
    else:
        edges=copy.deepcopy(topo.connections);edges[0]['target_pin']='in9';topo.connections=edges
    db_session.commit()
    try: assert scope().digest!=before
    except ValueError: pass


@pytest.mark.parametrize('fault',['duplicate_chain','duplicate_frequency','nan','reference','calibration','digest','cross_lab'])
def test_batch_rejects_invalid_or_stale_inputs(db_session,configured,shared_switch,fault):
    from app.schemas.route_batch import BatchPlanRequest
    from app.services.calibration.route_batch_plan import build_batch_plan
    topo,_=shared_switch
    data=request_for(topo).model_dump(mode='json')
    if fault=='duplicate_chain': data['chain_ids'].append('ov')
    elif fault=='duplicate_frequency': data['frequencies_mhz'].append(2595.)
    elif fault=='nan': data['frequencies_mhz'][0]=float('nan')
    elif fault=='reference': data['references'][0]['receive_cable_source']=''
    elif fault=='calibration': data['operating_mode']='calibration'
    elif fault=='digest': data['preview_digest']='0'*64
    else: topo.chamber_id=uuid4();db_session.commit()
    with pytest.raises(ValueError): build_batch_plan(db_session,configured.id,BatchPlanRequest(**data),None)


def test_fixed_direct_plan_has_no_switch_steps(db_session,configured,topology_two_chains):
    from app.services.calibration.route_batch_plan import build_batch_plan
    plan=build_batch_plan(db_session,configured.id,request_for(topology_two_chains,chains=('conn_p0v',),frequencies=(2595.,)),None)
    assert plan.items[0].switch_steps==()


@pytest.mark.asyncio
async def test_two_confirmed_switch_routes_reach_local_compensation_once(client,db_session,configured,
        shared_switch,real_capture,monkeypatch,chamber,launch,tmp_path):
    from tests.test_pc04a2_route_application import payload,confirm
    from tests import test_pc04a2_route_eligibility as capture_module
    from tests.test_pc_04a_fixed_route_api import start
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation,frozen_route_identity_error
    from app.services.channel_engine_client import ChannelEngineClient
    # 只脚本化外部功率仪器transport；没有调用真实开关或伪造采用判据。
    for chain,output,source,received in [('ov',1,'-30','-60'),('oh',2,'-20','-60')]:
        monkeypatch.setattr(capture_module,'start',lambda c,l,chain=chain:start(c,l,chain_id=chain))
        row=real_capture(source,received,output=output)
        response=confirm(client,configured,payload(client,configured,row))
        assert response.status_code==201,response.text
    execution=await launch()
    frozen=execution.config['route_calibration_freeze']
    entries={e['chain_id']:e for e in frozen['route_entries']}
    assert {k:(v['ce_port'],v['value_db'],v['source_kind']) for k,v in entries.items()}=={
        'ov':('B1.1',28.,'confirmed_route'),'oh':('B1.2',38.,'confirmed_route')}
    actual=orchestrate_switch_topology(db_session,chamber.id)
    assert frozen_route_identity_error(db_session,frozen,resolved_topology=actual) is None
    engine=ChannelEngineClient(db_session)
    monkeypatch.setattr(engine,'_query_phase_compensation',lambda *args,**kwargs:{})
    rows=engine._query_calibration_entries(chamber.id,2595e6,chamber,path_loss_calibration=None,route_compensation=frozen)
    assert [(r['port_id'],r['cable_loss_db'],r['probe_gain_dbi']) for r in rows]==[(1,28.,0),(2,38.,0)]
    import os
    if os.environ.get('CHANNEL_ENGINE_PATH'):
        from tests.test_pc04a2_route_compensation import assert_final_loaded_asc
        await assert_final_loaded_asc(engine,rows,chamber,monkeypatch,tmp_path,28)


def test_serial_batch_rejects_same_ce_on_independent_relays(db_session,configured,shared_switch):
    from app.services.calibration.route_batch_plan import build_batch_plan
    topo,_=shared_switch
    edges=copy.deepcopy(topo.connections);edges[1]['source']='ce1';topo.connections=edges;db_session.commit()
    with pytest.raises(ValueError,match='物理输出'):
        resolve_rf_chains(db_session,configured.id)
    with pytest.raises(ValueError,match='互斥'):
        build_batch_plan(db_session,configured.id,request_for(topo),None)


@pytest.mark.parametrize('fault',['missing_pin_pair','relay_conflict','invalid_relay'])
def test_saved_mapping_missing_pair_or_formal_conflict_rejects(db_session,configured,shared_switch,fault):
    topo,conn=shared_switch
    params=copy.deepcopy(conn.connection_params)
    if fault=='missing_pin_pair': del params['port_maps']['v']['topology_output_pin']
    elif fault=='relay_conflict': params['port_maps']['h']['switch_id']='1:INT_RELAY_A'
    else: params['port_maps']['v']['switch_id']='1:NOT_A_RELAY'
    conn.connection_params=params;db_session.commit()
    with pytest.raises(ValueError): orchestrate_switch_topology(db_session,configured.chamber_config_id)


def test_instrument_save_and_read_preserve_explicit_topology_pin_pair(client,db_session,shared_switch):
    _,conn=shared_switch
    params=copy.deepcopy(conn.connection_params)
    response=client.put('/api/v1/instruments/rfSwitch',json={'connection':{'connection_params':params}})
    assert response.status_code==200,response.text
    assert response.json()['connection']['connection_params']['port_maps']['v']=={
        'switch_id':'1:INT_RELAY_A','relay_type':'spdt','input_port':0,'output_port':'NC',
        'topology_input_pin':'in1','topology_output_pin':'out1'}
    db_session.expire_all()
    assert db_session.get(InstrumentConnection,conn.id).connection_params==params


@pytest.mark.parametrize('change',['relay','binding','notes'])
def test_explicit_switch_freeze_checks_physical_mapping_in_both_independent_comparisons(
        db_session,configured,shared_switch,change):
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation,frozen_route_identity_error
    topo,conn=shared_switch
    frozen=resolve_effective_route_compensation(db_session,configured.id,'mimo_ota',2595.)
    if change=='binding':
        conn.endpoint='192.0.2.77'
        configured.instrument_bindings=[{**b,'connection_endpoint':'192.0.2.77'}
            if b['category_id']==str(topo.switch_category_id) else b for b in configured.instrument_bindings]
    else:
        params=copy.deepcopy(conn.connection_params)
        if change=='relay': params['port_maps']['v']['switch_id']='1:INT_RELAY_C'
        else: params['port_maps']['v']['notes']='仅备注，不改变物理通路'
        conn.connection_params=params
    db_session.commit()
    actual=orchestrate_switch_topology(db_session,configured.chamber_config_id)
    # CE/probe端点保持不变，只有独立解析出的开关执行身份能发现前两种改变。
    assert [(b.ce_port,b.probe_id,b.polarization) for b in actual.probe_bindings]==[('B1.1',0,'V'),('B1.2',0,'H')]
    db_error=frozen_route_identity_error(db_session,frozen)
    actual_error=frozen_route_identity_error(db_session,frozen,resolved_topology=actual)
    if change=='notes': assert db_error is None and actual_error is None
    else: assert db_error is not None and actual_error is not None


def test_batch_output_nested_working_copies_cannot_rewrite_frozen_plan(db_session,configured,shared_switch):
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.schemas.route_batch import BatchPlan,BatchPlanItem,BatchSwitchStep
    topo,_=shared_switch
    plan=build_batch_plan(db_session,configured.id,request_for(topo),None)
    original=plan.model_dump(mode='json')
    item=plan.items[0]
    mapping=item.switch_steps[0].mapping
    mapping['output_port']='NC'
    request=item.request
    request.frequency_mhz=100.
    route=item.route_selection
    route.nodes[0]['params']['ce_port']='B9'
    route.connection_ids.append('invented')
    scope=item.configuration_scope
    scope.payload.resources[0]['driver_mode']='rewritten'
    scope.payload.chains[0].ce_port='B9'
    assert plan.model_dump(mode='json')==original
    assert item.request.frequency_mhz==2595.
    assert item.switch_steps[0].mapping['output_port']=='NO'

    # 构造输入也须去别名，不能从先前交给输出模型的对象反向改写计划。
    request=item.request;route=item.route_selection;scope=item.configuration_scope
    detached=BatchPlanItem(item_id=item.item_id,request=request,route_selection=route,
        configuration_scope=scope,switch_steps=item.switch_steps)
    before=detached.model_dump(mode='json')
    request.frequency_mhz=100.
    route.nodes[0]['params']['ce_port']='B9'
    scope.payload.chains[0].ce_port='B9'
    assert detached.model_dump(mode='json')==before

    step_input=item.switch_steps[0].model_dump()
    step_input['mapping']['metadata']={'ports':[1]}
    step=BatchSwitchStep(**step_input)
    step_input['mapping']['metadata']['ports'].append(2)
    step.mapping['metadata']['ports'].append(3)
    assert step.model_dump()['mapping']['metadata']['ports']==[1]

    restored=BatchPlan.model_validate_json(plan.model_dump_json())
    assert restored.model_dump(mode='json')==original
    assert restored.preview_digest==plan.preview_digest
    import hashlib,json
    body={key:original[key] for key in ('version','lab_profile_id','topology_id','operating_mode','items')}
    encoded=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    assert hashlib.sha256(encoded.encode()).hexdigest()==restored.preview_digest
    restored.items[0].configuration_scope.payload.chains[0].ce_port='B9'
    restored.items[0].switch_steps[0].mapping['output_port']='NC'
    assert restored.model_dump(mode='json')==original
