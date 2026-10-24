"""批HTTP生产链：真实临时DB/租约/采集，只有外部仪器transport脚本化。"""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.main import app
from app.models.diagnostic_run import DiagnosticRun
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured
from tests.test_pc06a1_batch_plan import shared_switch, request_for
from tests.test_pc06a1_batch_jobs import runtime, serial_graph
from tests.test_pc06a1_batch_safety import safety_runtime


@pytest.fixture
def db_session(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path / "batch-api.db"}',connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine,expire_on_commit=False)() as db:
        yield db
    engine.dispose()


@pytest.fixture
async def api(db_session,runtime):
    jobs,_=runtime
    previous=dict(app.dependency_overrides)
    app.dependency_overrides[get_db]=lambda:db_session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        try:
            yield client
        finally:
            await jobs.shutdown_route_batch_jobs()
            app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def root(lab):
    return f'/api/v1/lab-profiles/{lab.id}/route-calibration-batches'


async def previewed(api,lab,topo,**kwargs):
    body=request_for(topo,frequencies=(2595.,),**kwargs).model_dump(mode='json')
    response=await api.post(root(lab)+'/preview',json=body)
    assert response.status_code==200,response.text
    plan=response.json()
    if plan['switch_scope_digest']:
        body['switch_wiring_confirmation']=dict(operator='操作员自述',confirmed_at=datetime.now(timezone.utc).isoformat(),
            note='已核对本次清单接线',switch_scope_digest=plan['switch_scope_digest'])
        response=await api.post(root(lab)+'/preview',json=body)
        assert response.status_code==200,response.text
        plan=response.json()
    body['preview_digest']=plan['preview_digest']
    return body,plan


async def start(api,lab,body,key=None):
    response=await api.post(root(lab),json=body,headers={'Idempotency-Key':str(key or uuid4())})
    assert response.status_code==202,response.text
    return response.json()


async def state(api,lab,ident,wanted):
    for _ in range(700):
        response=await api.get(root(lab)+'/'+ident)
        assert response.status_code==200,response.text
        value=response.json()
        if value['status']==wanted:
            return value
        if value['status'] in ('failed','cleanup_unconfirmed','interrupted'):
            pytest.fail(str(value))
        await asyncio.sleep(.005)
    pytest.fail('未到达状态：'+wanted)


def continuation(value):
    item=value['items'][value['current_index']]
    return dict(item_id=item['item_id'],transition_id=value['transition_id'],
        reference_antenna=item['request']['reference_antenna'],manual_confirmed=True,skip_failed=False)


def adoption(child,**changes):
    body=dict(acquisition_run_id=child['run_id'],route_digest=child['result']['request']['route_digest'],
        expected_current_application_id=None,idempotency_key=str(uuid4()),confirmed=True,
        adoption_valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    body.update(changes)
    return body


async def test_serial_http_full_chain_parent_release_guards_child_adoption(api,db_session,configured,shared_switch,safety_runtime):
    jobs,hal,calls=safety_runtime
    topo,conn=serial_graph(db_session,shared_switch)
    # 同CE同SP6T互斥目标；transport只模拟回读，不替代生产切换/采集/最终化。
    driver=hal.drivers['rfSwitch']
    driver._mappings=conn.connection_params['port_maps']
    transport=driver._send_command
    position={'value':'1'}
    async def switch(command):
        if command in ('1:INT_RELAY_A_1','1:INT_RELAY_A_2'):
            position['value']=command[-1]
        if command=='1:INT_RELAY_A?':
            calls.append(command);return position['value']
        return await transport(command)
    driver._send_command=switch
    body,plan=await previewed(api,configured,topo)
    assert [i['request']['chain_id'] for i in plan['items']]==['oh','ov']
    assert calls==[] and db_session.query(DiagnosticRun).count()==0
    for path in ('calibration-scope','route-calibration-paths'):
        response=await api.get(f'/api/v1/lab-profiles/{configured.id}/{path}',
            params={'topology_id':str(topo.id),'operating_mode':'mimo_ota'})
        assert response.status_code in (409,422)
    value=await start(api,configured,body)
    ident=value['job_id']
    first=await state(api,configured,ident,'waiting_manual')
    proceed=await api.post(root(configured)+'/'+ident+'/continue',json=continuation(first))
    assert proceed.status_code==200,proceed.text
    second=await state(api,configured,ident,'waiting_manual')
    assert second['current_index']==1
    run_id=second['items'][0]['run_id']
    child_url=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}'
    child=(await api.get(child_url)).json()
    assert child['status']=='completed'
    assert child['batch_context']['active'] is True and child['batch_context']['finalized'] is False
    assert child['result']['states']['f64_control_released'] is None
    history=(await api.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions')).json()
    assert history[0]['batch_context']['job_id']==ident
    cancelled=await api.post(child_url+'/cancel')
    assert cancelled.status_code==409 and ident in cancelled.text
    candidate=(await api.get(child_url+'/application-preview')).json()
    assert candidate['eligibility']['eligible_for_adoption'] is False
    confirm_url=f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications'
    assert (await api.post(confirm_url,json=adoption(child))).status_code==422
    stale=await api.post(root(configured)+'/'+ident+'/continue',json=continuation(first))
    assert stale.status_code==422
    assert (await api.post(root(configured)+'/'+ident+'/continue',json=continuation(second))).status_code==200
    final=await state(api,configured,ident,'completed')
    assert final['f64_control_released'] is True and final['finalization_committed'] is True
    child=(await api.get(child_url)).json()
    assert child['batch_context']['finalized'] is True
    candidate=(await api.get(child_url+'/application-preview')).json()
    assert candidate['eligibility']['eligible_for_adoption'] is True
    assert (await api.post(confirm_url,json=adoption(child))).status_code==201
    assert (await api.get(root(configured))).json()[0]['job_id']==ident


async def test_individual_saved_candidates_allow_serial_ce_without_relaxing_formal_set(api,db_session,configured,shared_switch):
    topo,_=serial_graph(db_session,shared_switch)
    url=f'/api/v1/lab-profiles/{configured.id}/route-calibration-paths'
    params=dict(topology_id=str(topo.id),operating_mode='mimo_ota')
    formal=await api.get(url,params=params)
    assert formal.status_code==422,formal.text
    candidates=await api.get(url,params={**params,'selection_scope':'individual'})
    assert candidates.status_code==200,candidates.text
    rows=candidates.json()
    assert [(r['chain_id'],r['ce_port']) for r in rows]==[('oh','B1.1'),('ov','B1.1')]
    body=request_for(topo,chains=tuple(r['chain_id'] for r in rows),frequencies=(2595.,)).model_dump(mode='json')
    preview=await api.post(root(configured)+'/preview',json=body)
    assert preview.status_code==200,preview.text
    for row,item in zip(rows,preview.json()['items'],strict=True):
        assert row['configuration_digest']==item['configuration_scope']['digest']==item['request']['configuration_digest']
        assert row['route_digest']==item['route_selection']['route_digest']
    formal_again=await api.get(url,params=params)
    assert formal_again.status_code==422
    assert (await api.get(url,params={**params,'selection_scope':'simultaneous'})).status_code==422
    assert (await api.get(url,params={**params,'selection_scope':'invalid'})).status_code==422
    assert db_session.query(DiagnosticRun).count()==0


@pytest.mark.parametrize('frequencies',[(1000000.,),(2595.,1000000.)])
async def test_start_preflight_frequency_rejection_leaves_no_parent_and_key_can_retry(api,db_session,configured,shared_switch,runtime,frequencies):
    from app.services.execution_exclusion_guard import active_unsafe_diagnostic
    jobs,_=runtime;topo,_=shared_switch;key=uuid4()
    body=request_for(topo,frequencies=frequencies).model_dump(mode='json')
    preview=await api.post(root(configured)+'/preview',json=body)
    assert preview.status_code==200,preview.text
    body['preview_digest']=preview.json()['preview_digest']
    response=await api.post(root(configured),json=body,headers={'Idempotency-Key':str(key)})
    assert response.status_code==422 and '频段' in response.text
    assert (await api.get(root(configured))).json()==[]
    with sessionmaker(bind=db_session.get_bind())() as independent:
        assert independent.query(DiagnosticRun).count()==0
    assert not jobs._running and active_unsafe_diagnostic() is None
    corrected,_=await previewed(api,configured,topo)
    accepted=await api.post(root(configured),json=corrected,headers={'Idempotency-Key':str(key)})
    assert accepted.status_code==202,accepted.text
    await api.post(root(configured)+'/'+accepted.json()['job_id']+'/cancel')


@pytest.mark.parametrize('stage',['flush','commit','validation','cancelled_validation'])
async def test_start_transaction_failure_rolls_back_pending_parent(api,db_session,configured,shared_switch,runtime,monkeypatch,stage):
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.services.calibration import fixed_route_jobs as single
    from app.services.execution_exclusion_guard import active_unsafe_diagnostic
    jobs,hal=runtime;topo,_=shared_switch
    request=request_for(topo,frequencies=(2595.,))
    plan=build_batch_plan(db_session,configured.id,request,hal)
    request=request.model_copy(update={'preview_digest':plan.preview_digest})
    failure=asyncio.CancelledError if stage=='cancelled_validation' else ValueError
    def rejected(*args,**kwargs):raise failure('启动核验测试失败')
    with monkeypatch.context() as patch:
        if stage=='flush':
            original_flush=db_session.flush
            def flush_parent(*args,**kwargs):
                if any(isinstance(row,DiagnosticRun) for row in db_session.new):rejected()
                return original_flush(*args,**kwargs)
            patch.setattr(db_session,'flush',flush_parent)
        elif stage=='commit':
            patch.setattr(db_session,stage,rejected)
        else:
            patch.setattr(single,'resolve_configuration',rejected)
        with pytest.raises(failure):
            await jobs.start(db_session,configured.id,request,idempotency_key=uuid4())
    assert db_session.query(DiagnosticRun).count()==0
    with sessionmaker(bind=db_session.get_bind())() as independent:
        assert independent.query(DiagnosticRun).count()==0
    assert not jobs._running and active_unsafe_diagnostic() is None


async def test_pending_response_loss_idempotency_is_lab_and_content_scoped(api,db_session,configured,shared_switch,runtime):
    jobs,hal=runtime
    topo,_=shared_switch
    body,_=await previewed(api,configured,topo)
    key=uuid4()
    value=await start(api,configured,body,key)
    replay=await start(api,configured,body,key)
    assert replay['job_id']==value['job_id']
    assert db_session.query(DiagnosticRun).count()==1
    waiting=await state(api,configured,value['job_id'],'waiting_manual')
    assert not any('INTERFerence:ADD' in cmd for cmd in hal.drivers['channelEmulator']._visa_resource.commands)
    changed=copy.deepcopy(body);changed['requested_power_dbm']=-21
    assert (await api.post(root(configured),json=changed,headers={'Idempotency-Key':str(key)})).status_code==409
    assert (await api.post(root(configured),json=body,headers={'Idempotency-Key':str(uuid4())})).status_code==409
    foreign=root(type('Lab',(),{'id':uuid4()})())
    for suffix,method,body2 in [('', 'get',None),('/'+value['job_id'],'get',None),
            ('/'+value['job_id']+'/cancel','post',None),('/'+value['job_id']+'/continue','post',continuation(waiting))]:
        response=await api.request(method,foreign+suffix,**({'json':body2} if body2 is not None else {}))
        assert response.status_code==404,response.text
    assert (await api.get(root(configured)+'/'+str(uuid4()))).status_code==404
    cancelled=await api.post(root(configured)+'/'+value['job_id']+'/cancel')
    assert cancelled.status_code==200 and cancelled.json()['cancel_requested'] is True
    assert cancelled.json()['f64_control_released'] is None
    await state(api,configured,value['job_id'],'cancelled')
    assert (await api.post(root(configured)+'/'+value['job_id']+'/cancel')).status_code==409
    from app.models.lab_profile import LabProfile
    other=LabProfile(name='另一实验室',chamber_config_id=configured.chamber_config_id,
        instrument_bindings=copy.deepcopy(configured.instrument_bindings))
    db_session.add(other);db_session.commit()
    other_body,_=await previewed(api,other,topo)
    next_job=await start(api,other,other_body,key)
    assert next_job['job_id']!=value['job_id'] and next_job['lab_id']==str(other.id)


@pytest.mark.parametrize('change',[{'fixed_route_confirmed':1},{'safety_confirmed':False},
    {'chain_ids':[]},{'sample_count':True},{'net_loss_db':1},{'preview_digest':'bad'}])
async def test_invalid_inputs_never_create_batch(api,configured,shared_switch,db_session,change):
    topo,_=shared_switch
    body=request_for(topo).model_dump(mode='json');body.update(change)
    response=await api.post(root(configured),json=body,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==422,response.text
    assert db_session.query(DiagnosticRun).count()==0


async def test_finalization_failure_get_preview_confirm_stay_unknown(api,configured,shared_switch,runtime,db_session,monkeypatch):
    jobs,_=runtime
    def storage_failure(*args):
        raise RuntimeError('scripted final transaction failure')
    monkeypatch.setattr(jobs,'_finalize',storage_failure)
    topo,_=shared_switch
    body,_=await previewed(api,configured,topo)
    value=await start(api,configured,body)
    ident=value['job_id'];task=jobs._running[UUID(ident)].task
    first=await state(api,configured,ident,'waiting_manual')
    await api.post(root(configured)+'/'+ident+'/continue',json=continuation(first))
    second=await state(api,configured,ident,'waiting_manual')
    run_id=second['items'][0]['run_id']
    await api.post(root(configured)+'/'+ident+'/continue',json=continuation(second))
    await task
    final=(await api.get(root(configured)+'/'+ident)).json()
    assert final['status']=='interrupted' and final['f64_control_released'] is None
    assert final['finalization_committed'] is False
    child_url=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}'
    child=(await api.get(child_url)).json()
    assert child['batch_context']['active'] is False and child['batch_context']['finalized'] is False
    assert child['result']['states']['f64_control_released'] is None
    candidate=(await api.get(child_url+'/application-preview')).json()
    assert candidate['eligibility']['measurement_provenance']=='unknown'
    assert candidate['eligibility']['eligible_for_adoption'] is False and candidate['new_net_loss_db'] is None
    assert (await api.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications',
        json=adoption(child))).status_code==422


@pytest.mark.parametrize('fault',['parent_lab','orphan','lease','finalization','uncommitted','parent_active'])
async def test_parent_context_corruption_blocks_all_adoption_consumers(api,configured,shared_switch,runtime,db_session,fault):
    jobs,_=runtime
    topo,_=shared_switch
    body,_=await previewed(api,configured,topo)
    value=await start(api,configured,body)
    ident=value['job_id']
    for _ in range(2):
        waiting=await state(api,configured,ident,'waiting_manual')
        assert (await api.post(root(configured)+'/'+ident+'/continue',json=continuation(waiting))).status_code==200
    final=await state(api,configured,ident,'completed')
    parent=db_session.get(DiagnosticRun,UUID(ident))
    if fault=='parent_lab':
        # 模拟跨实验室审计关系损坏，而非客户端有权修改历史。
        parent.lab_profile_id=uuid4()
    elif fault=='orphan':
        db_session.delete(parent)
    else:
        saved=jobs._payload(parent)
        saved[{'lease':'lease_id','finalization':'finalization_id','uncommitted':'finalization_committed',
            'parent_active':'status'}[fault]]={'lease':'wrong','finalization':'wrong','uncommitted':False,'parent_active':'running'}[fault]
        jobs._save_parent(parent,saved)
    db_session.commit()
    child_url=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{final["items"][0]["run_id"]}'
    child=(await api.get(child_url)).json()
    assert child['batch_context']['finalized'] is False
    assert child['result']['states']['f64_control_released'] is None
    preview=(await api.get(child_url+'/application-preview')).json()
    assert preview['eligibility']['eligible_for_adoption'] is False
    assert preview['eligibility']['measurement_provenance']=='unknown'
    assert (await api.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications',
        json=adoption(child))).status_code==422


async def test_mock_batch_finishes_but_never_adopts(api,configured,topology_two_chains,runtime,db_session,monkeypatch):
    from app.hal.channel_emulator import MockChannelEmulator
    from app.hal.signal_analyzer import MockSignalAnalyzer
    from app.models.instrument import InstrumentCategory
    jobs,hal=runtime
    hal.drivers.update(channelEmulator=MockChannelEmulator('ce',{}),signalAnalyzer=MockSignalAnalyzer('sa',{}))
    configured.instrument_bindings=[{**b,'driver_mode':'mock'} for b in configured.instrument_bindings]
    db_session.query(InstrumentCategory).filter(InstrumentCategory.category_key.in_(['channelEmulator','signalAnalyzer'])).update(
        {'driver_mode':'mock'},synchronize_session=False)
    db_session.commit()
    monkeypatch.setattr(jobs,'_prepare_item',hal.batch_prepare)
    body,_=await previewed(api,configured,topology_two_chains,chains=('conn_p0v',))
    value=await start(api,configured,body);ident=value['job_id']
    waiting=await state(api,configured,ident,'waiting_manual')
    assert (await api.post(root(configured)+'/'+ident+'/continue',json=continuation(waiting))).status_code==200
    final=await state(api,configured,ident,'completed')
    run_id=final['items'][0]['run_id']
    child_url=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}'
    child=(await api.get(child_url)).json()
    assert child['status']=='simulated' and child['result']['net_loss_db'] is None
    candidate=(await api.get(child_url+'/application-preview')).json()
    assert candidate['eligibility']['measurement_provenance']=='simulated'
    assert candidate['eligibility']['eligible_for_adoption'] is False
    assert (await api.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications',
        json=adoption(child))).status_code==422


async def test_mock_serial_switch_steps_use_real_builder_without_io_or_position_claim(api,configured,shared_switch,safety_runtime,db_session,monkeypatch):
    from app.hal.channel_emulator import MockChannelEmulator
    from app.hal.signal_analyzer import MockSignalAnalyzer
    from app.models.instrument import InstrumentCategory
    from app.services.calibration import route_batch_switch as switching
    jobs,hal,_=safety_runtime
    topo,conn=serial_graph(db_session,shared_switch)
    hal.drivers.update(channelEmulator=MockChannelEmulator('ce',{}),signalAnalyzer=MockSignalAnalyzer('sa',{}))
    configured.instrument_bindings=[{**b,'driver_mode':'mock'} if b['category_id']!=str(topo.switch_category_id) else b for b in configured.instrument_bindings]
    db_session.query(InstrumentCategory).filter(InstrumentCategory.category_key.in_(['channelEmulator','signalAnalyzer'])).update({'driver_mode':'mock'},synchronize_session=False)
    db_session.commit()
    io=[];built=[];builder=switching.build_emcenter_switch_command
    async def forbidden(command):
        io.append(command);raise AssertionError('模拟批不得调用真实开关transport')
    def record_builder(relay,target):
        built.append((relay,target));return builder(relay,target)
    monkeypatch.setattr(hal.drivers['rfSwitch'],'_send_command',forbidden)
    monkeypatch.setattr(switching,'build_emcenter_switch_command',record_builder)
    body,_=await previewed(api,configured,topo)
    value=await start(api,configured,body);ident=value['job_id']
    for index in (0,1):
        waiting=await state(api,configured,ident,'waiting_manual')
        assert waiting['current_index']==index
        assert (await api.post(root(configured)+'/'+ident+'/continue',json=continuation(waiting))).status_code==200
    final=await state(api,configured,ident,'completed')
    assert built==[('1:INT_RELAY_A',2),('1:INT_RELAY_A',1)]
    assert io==[] and final['f64_control_released'] is None
    for item,command in zip(final['items'],['1:INT_RELAY_A_2','1:INT_RELAY_A_1'],strict=True):
        assert item['status']=='simulated'
        receipts=item.get('switch_receipts',[])
        assert len(receipts)==1 and receipts[0]['command']==command
        assert receipts[0]['simulated'] is True and receipts[0]['raw'] is None
        assert receipts[0].get('position') is None and receipts[0].get('write_return') is None
        candidate=(await api.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{item["run_id"]}/application-preview')).json()
        assert candidate['eligibility']['eligible_for_adoption'] is False
        assert candidate['eligibility']['measurement_provenance']=='simulated'


async def test_scope_drift_after_preview_and_missing_idempotency_refuse_start(api,configured,shared_switch,db_session):
    topo,conn=shared_switch
    body,_=await previewed(api,configured,topo)
    assert (await api.post(root(configured),json=body)).status_code==422
    conn.endpoint='192.0.2.99';db_session.commit()
    response=await api.post(root(configured),json=body,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==422,response.text
    assert db_session.query(DiagnosticRun).count()==0


def test_batch_contract_models_live_and_handwritten_openapi_agree():
    from pathlib import Path
    import yaml
    live=app.openapi()
    written=yaml.safe_load((Path(__file__).parents[2]/'api/openapi.yaml').read_text())
    candidate_path='/api/v1/lab-profiles/{lab_profile_id}/route-calibration-paths'
    assert written['paths'][candidate_path]==live['paths'][candidate_path]
    paths={path for path in live['paths'] if '/route-calibration-batches' in path}
    assert len(paths)==5
    for path in paths:
        assert written['paths'].get(path)==live['paths'][path]
    names=['BatchPlanRequest','BatchPlan','BatchPlanItem','BatchReference','BatchSwitchStep',
        'BatchSwitchWiringConfirmation','BatchContinueRequest','BatchJobItem','BatchJobRecord',
        'RouteSelection','FixedRouteRecord','FixedRouteBatchContext']
    for name in names:
        assert written['components']['schemas'].get(name)==live['components']['schemas'][name],name


def test_gui_batch_service_defaults_identity_and_idempotency():
    """真实TS服务在外部HTTP边界执行；默认mode/身份拒绝/重试键可观察。"""
    import subprocess
    from pathlib import Path
    gui=Path(__file__).parents[2]/'gui'
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('typescript');
const source=fs.readFileSync('src/api/labProfileService.ts','utf8');
const calls=[];let next={};
const client={post:async(...args)=>{calls.push(args);return {data:next}},get:async(...args)=>{calls.push(args);return {data:next}}};
const exports={};
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,
  {exports,require:name=>{assert.equal(name,'./client');return {default:client}}});
(async()=>{
  next={lab_profile_id:'lab',topology_id:'topo',operating_mode:'mimo_ota'};
  await exports.previewRouteCalibrationBatch('lab',{topology_id:'topo'});
  next={lab_id:'lab',job_id:'job'};
  await exports.startRouteCalibrationBatch('lab',{preview_digest:'digest'},'stable-key');
  await exports.startRouteCalibrationBatch('lab',{preview_digest:'digest'},'stable-key');
  assert.equal(calls[1][2].headers['Idempotency-Key'],'stable-key');
  assert.equal(calls[2][2].headers['Idempotency-Key'],'stable-key');
  await exports.fetchRouteCalibrationBatch('lab','job');
  await exports.continueRouteCalibrationBatch('lab','job',{item_id:'item',transition_id:'transition'});
  await exports.cancelRouteCalibrationBatch('lab','job');
  next=[{lab_id:'lab',job_id:'job'}];await exports.fetchRouteCalibrationBatches('lab');
  next={lab_id:'other',job_id:'job'};
  await assert.rejects(()=>exports.fetchRouteCalibrationBatch('lab','job'));
  next={lab_id:'lab',job_id:'other'};
  await assert.rejects(()=>exports.cancelRouteCalibrationBatch('lab','job'));
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=gui,text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('fault',['plan','item'])
async def test_damaged_parent_http_history_remains_incomplete(api,configured,shared_switch,runtime,db_session,fault):
    jobs,_=runtime
    topo,_=shared_switch
    body,_=await previewed(api,configured,topo)
    value=await start(api,configured,body)
    ident=value['job_id'];task=jobs._running[UUID(ident)].task
    await api.post(root(configured)+'/'+ident+'/cancel');await task
    parent=db_session.get(DiagnosticRun,UUID(ident));saved=jobs._payload(parent)
    if fault=='plan': saved['plan']={}
    else: saved['items'][0]['status']='invented-state'
    jobs._save_parent(parent,saved);db_session.commit()
    for url in (root(configured)+'/'+ident,root(configured)):
        response=await api.get(url)
        assert response.status_code==200,response.text
        record=response.json() if url.endswith(ident) else response.json()[0]
        assert record['status']=='incomplete' and record['f64_control_released'] is None
        assert record['finalization_committed'] is False and record['items']==[]


@pytest.mark.parametrize('endpoint',['detail','history','application-preview'])
@pytest.mark.parametrize('field',['finalization_id','lease_id'])
async def test_damaged_batch_context_stays_readable_unknown(api,configured,topology_two_chains,runtime,db_session,endpoint,field):
    jobs,_=runtime
    body,_=await previewed(api,configured,topology_two_chains,chains=('conn_p0v',))
    value=await start(api,configured,body);ident=value['job_id']
    waiting=await state(api,configured,ident,'waiting_manual')
    assert (await api.post(root(configured)+'/'+ident+'/continue',json=continuation(waiting))).status_code==200
    final=await state(api,configured,ident,'completed')
    parent=db_session.get(DiagnosticRun,UUID(ident))
    saved=jobs._payload(parent);saved[field]={'damaged':True}
    jobs._save_parent(parent,saved)
    child=db_session.get(DiagnosticRun,UUID(final['items'][0]['run_id']))
    if field=='lease_id':
        # 保持父子lease关系一致，证明元数据损坏即使未被旧关系检查挡住也不能透传或授权。
        evidence=copy.deepcopy(child.sequence_evidence)
        evidence['extra']['fixed_route_acquisition']['states']['lease_id']={'damaged':True}
        child.sequence_evidence=evidence
    db_session.commit()
    original_parent=copy.deepcopy(parent.sequence_evidence)
    original_child=copy.deepcopy(child.sequence_evidence)
    assert (await api.get(root(configured)+'/'+ident)).json()['status']=='incomplete'
    base=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions'
    url=base if endpoint=='history' else base+'/'+str(child.id)+('/application-preview' if endpoint=='application-preview' else '')
    response=await api.get(url)
    assert response.status_code==200,response.text
    result=response.json()
    if endpoint=='application-preview':
        assert result['eligibility']['measurement_provenance']=='unknown'
        assert result['eligibility']['eligible_for_adoption'] is False and result['new_net_loss_db'] is None
    else:
        record=result[0] if endpoint=='history' else result
        assert record['batch_context']['active'] is False and record['batch_context']['finalized'] is False
        assert record['batch_context']['finalization_id'] is None and record['batch_context']['lease_id'] is None
        assert record['result']['states']['f64_control_released'] is None
    request=dict(acquisition_run_id=str(child.id),route_digest=final['plan']['items'][0]['request']['route_digest'],
        expected_current_application_id=None,idempotency_key=str(uuid4()),confirmed=True,
        adoption_valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    assert (await api.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications',json=request)).status_code==422
    db_session.refresh(parent);db_session.refresh(child)
    assert parent.sequence_evidence==original_parent and child.sequence_evidence==original_child
