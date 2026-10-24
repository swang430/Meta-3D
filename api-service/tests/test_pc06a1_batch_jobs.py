"""批生命周期：真实临时DB与共享lease，外部采集边界可脚本化。"""
import asyncio
import copy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured
from tests.test_pc06a1_batch_plan import shared_switch, request_for
from app.models.diagnostic_run import DiagnosticRun
from app.services.execution_exclusion_guard import active_unsafe_diagnostic, try_acquire_unsafe_diagnostic
from app.services.instrument_test_lease import InstrumentTestLease


@pytest.fixture
def runtime(db_session, configured, monkeypatch):
    from app.services.calibration import fixed_route_jobs as single
    try:
        from app.services.calibration import route_batch_jobs as jobs
    except ImportError:
        pytest.fail('缺少批协调器，无法在单项间保持独占与父子最终事务')
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.rs_fsva import RealRsFsvaDriver
    from app.hal.base import InstrumentStatus
    from tests.test_p1_66_f64_probe_truth import _ScriptedVisaResource, _ScriptedRM, SYS_INFO_WITH_INT
    from app.models.instrument import InstrumentCategory
    ce=RealPropsimF64Driver('ce-real-script',{'ip':'192.0.2.10'})
    sa=RealRsFsvaDriver('sa-real-script',{'ip':'192.0.2.10'})
    ce._visa_resource=_ScriptedVisaResource({'*IDN?':'Keysight Technologies,F8800A,SN-CE,8.0',
        'SYSTem:ERRor?':'0,"No error"','DIAG:SIMU:STATE?':'RUNNING','OUTPut:INTERFerence:GET?':'0',
        'OUTPut:LOSS:GET? 1':'0','OUTPut:LOSS:GET? 2':'0',
        'OUTPut:MEASure:RESult:GET? 1,1':'-30','OUTPut:MEASure:RESult:GET? 2,1':'-30',
        'SYST:INFO?':SYS_INFO_WITH_INT,
        'SYSTem:CALIBration:VALid?':'1,1','SYSTem:CALIBration:USER:GET?':'',
        'OUTPut:GAIN:CH? 1':'0','OUTPut:GAIN:CH? 2':'0'})
    monkeypatch.setattr('pyvisa.ResourceManager',lambda *a,**k:_ScriptedRM(ce._visa_resource or reconnect_resource))
    reconnect_resource=ce._visa_resource
    sa._visa_session=_ScriptedVisaResource({'*IDN?':'Rohde&Schwarz,FSVA3044,SN-SA,1.0',
        'SENSe:CORRection:TRANsducer:CATalog?':"0,0",'SENSe:CORRection:TRANsducer:STATe?':'0',
        'INITiate:IMMediate; *OPC?':'1','CALCulate:MARKer:FUNCtion:POWer:RESult? CPOWer':'-60'})
    ce._status=InstrumentStatus.READY;ce._local_control_reserved=False;ce.has_interference_generator=True
    configured.instrument_bindings=[{**b,'driver_mode':'real'} if b['driver_mode']=='mock' else b for b in configured.instrument_bindings]
    db_session.query(InstrumentCategory).filter(InstrumentCategory.category_key.in_(['channelEmulator','signalAnalyzer'])).update({'driver_mode':'real'},synchronize_session=False)
    db_session.commit()
    hal=SimpleNamespace(drivers={'channelEmulator':ce,'signalAnalyzer':sa})
    factory=sessionmaker(bind=db_session.get_bind(),expire_on_commit=False)
    lease=InstrumentTestLease(lambda:hal)
    for module in (single,jobs):
        monkeypatch.setattr(module,'SessionLocal',factory)
        monkeypatch.setattr(module,'get_hal_service',lambda:hal)
    monkeypatch.setattr(jobs,'instrument_test_lease',lease.hold)
    hal.batch_prepare=jobs._prepare_item
    # 仅生命周期测试隔离Task3切换接口；未冒充真实开关动作或auto资格。
    monkeypatch.setattr(jobs,'_prepare_item',jobs._wait_manual)
    return jobs,hal


async def wait_state(jobs,db,job_id,state):
    for _ in range(500):
        db.expire_all()
        value=jobs.record(db,db.get(DiagnosticRun,job_id))
        if value['status']==state:
            return value
        if value['status'] in ('failed','cleanup_unconfirmed','interrupted') and value['status']!=state:
            pytest.fail(str(value))
        await asyncio.sleep(.005)
    pytest.fail('批未进入预期状态：'+state)


async def advance(jobs,db,lab,job_id):
    value=await wait_state(jobs,db,job_id,'waiting_manual')
    item=value['items'][value['current_index']]
    jobs.continue_job(db,lab.id,job_id,item_id=item['item_id'],transition_id=value['transition_id'],
        reference_antenna=item['request']['reference_antenna'],manual_confirmed=True)
    await asyncio.sleep(.01)


async def start_previewed(jobs,db,lab_id,request,*,idempotency_key):
    from app.services.calibration.route_batch_plan import build_batch_plan
    preview=build_batch_plan(db,lab_id,request,jobs.get_hal_service())
    return await jobs.start(db,lab_id,request.model_copy(update={'preview_digest':preview.preview_digest}),
        idempotency_key=idempotency_key)


def serial_graph(db,shared_switch):
    topo,conn=shared_switch
    edges=copy.deepcopy(topo.connections);edges[1]['source']='ce1';edges[1]['target_pin']='in1';topo.connections=edges
    params=copy.deepcopy(conn.connection_params)
    params['port_maps']['h']['switch_id']='1:INT_RELAY_A'
    params['port_maps']['h']['topology_input_pin']='in1'
    conn.connection_params=params;db.commit()
    return topo,conn


async def test_serial_batches_hold_guard_across_manual_wait_and_reenter(db_session,configured,shared_switch,runtime,monkeypatch):
    jobs,hal=runtime
    from app.services.calibration import fixed_route_jobs as single
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.services.calibration.route_calibration import evaluate_route_application
    from app.services.calibration.route_calibration import confirm_route_application
    from app.schemas.route_calibration import ConfirmRouteApplication
    from datetime import datetime,timezone,timedelta
    topo,_=serial_graph(db_session,shared_switch)
    calls=[]
    original_collect=jobs.collect_fixed_route
    async def collect(ce,sa,result,**kwargs):
        calls.append(result.request.chain_id)
        await original_collect(ce,sa,result,**kwargs)
    monkeypatch.setattr(jobs,'collect_fixed_route',collect)
    for _ in range(2):
        request=request_for(topo,frequencies=(2595.,))
        preview=build_batch_plan(db_session,configured.id,request,hal)
        request=request.model_copy(update={'preview_digest':preview.preview_digest})
        value=await jobs.start(db_session,configured.id,request,idempotency_key=uuid4())
        ident=UUID(value['job_id'])
        await advance(jobs,db_session,configured,ident)
        value=await wait_state(jobs,db_session,ident,'waiting_manual')
        assert value['current_index']==1 and active_unsafe_diagnostic()==jobs.TARGET
        assert try_acquire_unsafe_diagnostic('unsafe') is None
        from fastapi import HTTPException
        from app.api.test_plan import execute_test_case
        from app.api import diagnostic_sequence as diagnostic_api
        from tests.test_diagnostic_execution_exclusion import _sequence, _request, _patch_sequence
        async def forbidden(*args,**kwargs): pytest.fail('互斥拒绝前不得进入诊断或SCPI')
        _patch_sequence(monkeypatch,_sequence(safe=False,run=forbidden))
        with pytest.raises(HTTPException) as conflict:
            await execute_test_case(uuid4(),db_session)
        assert conflict.value.status_code==409
        from app.api.fixed_route_acquisition import start as single_api_start
        with pytest.raises(HTTPException) as conflict:
            await single_api_start(configured.id,preview.items[0].request,db_session)
        assert conflict.value.status_code==409
        with pytest.raises(HTTPException) as conflict:
            await diagnostic_api.run_diagnostic_sequence('unsafe',_request(configured.id),db_session)
        assert conflict.value.status_code==409
        with pytest.raises(single.AcquisitionBusy):
            await single.start(db_session,configured.id,preview.items[0].request)
        first=db_session.get(DiagnosticRun,UUID(value['items'][0]['run_id']))
        child=single.record(first,batch_context=jobs.batch_child_context(db_session,first))
        assert child.status=='completed' and child.result.states['f64_control_released'] is None
        assert not evaluate_route_application(db_session,configured.id,first.id).eligibility.eligible_for_adoption
        confirmation=ConfirmRouteApplication(acquisition_run_id=first.id,route_digest=child.result.request.route_digest,
            expected_current_application_id=None,idempotency_key=uuid4(),confirmed=True,
            adoption_valid_until=datetime.now(timezone.utc)+timedelta(days=1))
        with pytest.raises(ValueError,match='不适用于本次采用'):
            confirm_route_application(db_session,configured.id,confirmation,'test')
        task=jobs._running[ident].task
        await advance(jobs,db_session,configured,ident)
        await task
        db_session.expire_all()
        final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
        assert final['status']=='completed' and final['finalization_committed'] is True
        assert active_unsafe_diagnostic() is None
        context=jobs.batch_child_context(db_session,db_session.get(DiagnosticRun,first.id))
        assert context['finalized'] is True and context['active'] is False
        candidate=evaluate_route_application(db_session,configured.id,first.id)
        assert candidate.eligibility.eligible_for_adoption
        adopted,created=confirm_route_application(db_session,configured.id,confirmation.model_copy(update={
            'expected_current_application_id':candidate.expected_current_application_id}),'test')
        assert created and adopted.acquisition_run_id==first.id and adopted.net_loss_db==28.
        parent=db_session.get(DiagnosticRun,ident)
        frozen=copy.deepcopy(parent.sequence_evidence)
        for key,bad in [('finalization_id','wrong'),('lease_id','wrong'),('finalization_committed',False),
                        ('all_started_cleanup_confirmed',False),('status','cleanup_unconfirmed')]:
            changed=copy.deepcopy(final);changed[key]=bad
            jobs._save_parent(parent,changed);db_session.commit()
            assert not evaluate_route_application(db_session,configured.id,first.id).eligibility.eligible_for_adoption
            parent.sequence_evidence=copy.deepcopy(frozen);db_session.commit()
    assert calls==['oh','ov','oh','ov']


async def test_active_child_and_restart_use_parent_not_single_registry(db_session,configured,shared_switch,runtime,monkeypatch):
    jobs,_=runtime
    from app.services.calibration import fixed_route_jobs as single
    entered=asyncio.Event();release=asyncio.Event()
    async def collect(ce,sa,result,**kwargs):
        entered.set();await release.wait();result.status='completed';result.cleanup_confirmed=True
    monkeypatch.setattr(jobs,'collect_fixed_route',collect)
    topo,_=shared_switch
    value=await start_previewed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);await advance(jobs,db_session,configured,ident);await entered.wait()
    db_session.expire_all();parent=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    row=db_session.get(DiagnosticRun,UUID(parent['items'][0]['run_id']))
    assert row.id not in single._running
    assert single.record(row,batch_context=jobs.batch_child_context(db_session,row)).status=='running'
    from app.api.fixed_route_acquisition import history,progress
    assert progress(configured.id,row.id,db_session).status=='running'
    assert history(configured.id,20,db_session)[0].status=='running'
    active=jobs._running.pop(ident)
    try:
        assert single.record(row,batch_context=jobs.batch_child_context(db_session,row)).status=='interrupted'
        assert jobs.record(db_session,db_session.get(DiagnosticRun,ident))['status']=='interrupted'
        assert single.record(row).result.states['f64_control_released'] is None
    finally:
        jobs._running[ident]=active
        jobs.request_cancel(ident);release.set();await active.task


@pytest.mark.parametrize('stage',['preview','remote','between'])
@pytest.mark.parametrize('drift',['mapping','binding','port'])
async def test_saved_drift_refuses_next_emission(db_session,configured,shared_switch,runtime,monkeypatch,stage,drift):
    jobs,hal=runtime
    from app.services.calibration.route_batch_plan import build_batch_plan
    topo,conn=serial_graph(db_session,shared_switch)
    request=request_for(topo,frequencies=(2595.,))
    plan=build_batch_plan(db_session,configured.id,request,hal)
    request=request.model_copy(update={'preview_digest':plan.preview_digest})
    def mutate():
        if drift=='mapping':
            params=copy.deepcopy(conn.connection_params);params['port_maps']['v']['switch_id']='1:INT_RELAY_X'
            conn.connection_params=params
        elif drift=='binding': conn.endpoint='192.0.2.99'
        else:
            edges=copy.deepcopy(topo.connections);edges[0]['target_pin']='in9';topo.connections=edges
        db_session.commit()
    calls=[]
    async def collect(ce,sa,result,**kwargs):
        calls.append(result.request.chain_id);result.status='completed';result.cleanup_confirmed=True
    monkeypatch.setattr(jobs,'collect_fixed_route',collect)
    if stage=='preview':
        mutate()
        with pytest.raises(ValueError): await jobs.start(db_session,configured.id,request,idempotency_key=uuid4())
        assert not calls and active_unsafe_diagnostic() is None
        return
    value=await jobs.start(db_session,configured.id,request,idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    if stage=='remote': mutate()
    else:
        await advance(jobs,db_session,configured,ident)
        await wait_state(jobs,db_session,ident,'waiting_manual');mutate()
        await advance(jobs,db_session,configured,ident)
    await task
    assert calls==([] if stage=='remote' else ['oh'])
    assert active_unsafe_diagnostic() is None


async def test_shutdown_cancels_waiting_batch_and_awaits_release(db_session,configured,shared_switch,runtime):
    jobs,_=runtime;topo,_=shared_switch
    value=await start_previewed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);await wait_state(jobs,db_session,ident,'waiting_manual')
    await jobs.shutdown_route_batch_jobs()
    db_session.expire_all();value=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert value['status']=='cancelled' and all(i['status']=='cancelled' for i in value['items'])
    assert not jobs._running and active_unsafe_diagnostic() is None


@pytest.mark.parametrize('fault',['tone','lease','item_commit','final_commit','crash_before_final'])
async def test_failure_windows_never_grant_child_adoption(db_session,configured,shared_switch,runtime,monkeypatch,fault):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from app.services.calibration import fixed_route_jobs as single
    from app.services.calibration.route_calibration import evaluate_route_application
    jobs,hal=runtime;topo,_=shared_switch
    original=jobs.collect_fixed_route
    calls=[]
    async def collect(ce,sa,result,**kwargs):
        calls.append(result.run_id)
        await original(ce,sa,result,**kwargs)
        if fault=='tone': result.status='cleanup_unconfirmed';result.cleanup_confirmed=False
    monkeypatch.setattr(jobs,'collect_fixed_route',collect)
    if fault=='lease':
        async def refused(): return False
        monkeypatch.setattr(hal.drivers['channelEmulator'],'release_to_local_control',refused)
    class Crash(BaseException): pass
    if fault=='crash_before_final':
        def crash(*args): raise Crash('进程在最终事务前终止')
        monkeypatch.setattr(jobs,'_finalize',crash)
    failed=[]
    def fail_commit(session):
        if failed: return
        for row in list(session.dirty):
            if not isinstance(row,DiagnosticRun) or row.target_name!=jobs.TARGET: continue
            value=jobs._payload(row)
            if ((fault=='final_commit' and value.get('finalization_committed')) or
                (fault=='item_commit' and value['items'][0]['status']=='completed')):
                failed.append(True);raise RuntimeError('注入真实DB commit失败')
    event.listen(Session,'before_commit',fail_commit)
    try:
        value=await start_previewed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
        ident=UUID(value['job_id']);task=jobs._running[ident].task
        await advance(jobs,db_session,configured,ident)
        if fault in ('lease','final_commit','crash_before_final'):
            await advance(jobs,db_session,configured,ident)
        if fault=='crash_before_final':
            with pytest.raises(Crash): await task
        else: await task
        assert len(calls)==(1 if fault in ('tone','item_commit') else 2)
        db_session.expire_all()
        for run_id in calls:
            row=db_session.get(DiagnosticRun,run_id)
            context=jobs.batch_child_context(db_session,row)
            assert context['finalized'] is False
            for _ in range(2):
                result=single.record(row,batch_context=context).result
                assert result.states['f64_control_released'] is (False if fault=='lease' else None)
                assert not evaluate_route_application(db_session,configured.id,run_id).eligibility.eligible_for_adoption
        assert active_unsafe_diagnostic() is None
        if fault in ('item_commit','final_commit'): assert failed
    finally:
        event.remove(Session,'before_commit',fail_commit)


async def test_start_commit_failure_never_spawns_task_or_holds_guard(db_session,configured,shared_switch,runtime,monkeypatch):
    jobs,_=runtime;topo,_=shared_switch
    def refused(): raise RuntimeError('父记录落盘失败')
    monkeypatch.setattr(db_session,'commit',refused)
    with pytest.raises(RuntimeError,match='父记录落盘失败'):
        await start_previewed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    assert not jobs._running and active_unsafe_diagnostic() is None


async def test_missing_switch_module_refuses_emission_not_manual_bypass(db_session,configured,shared_switch,runtime,monkeypatch):
    jobs,hal=runtime;topo,_=shared_switch
    monkeypatch.setattr(jobs,'_prepare_item',hal.batch_prepare)
    async def forbidden(*args,**kwargs): pytest.fail('未接Task3不能对开关路径发射')
    monkeypatch.setattr(jobs,'collect_fixed_route',forbidden)
    value=await start_previewed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);await jobs._running[ident].task
    db_session.expire_all();value=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert value['status']=='failed' and '尚未接入' in value['error']
    assert all(i['run_id'] is None for i in value['items'])


def test_batch_context_cannot_be_boolean_or_foreign_job(db_session,configured,shared_switch,runtime):
    jobs,hal=runtime;topo,_=serial_graph(db_session,shared_switch)
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.services.calibration import fixed_route_jobs as single
    item=build_batch_plan(db_session,configured.id,request_for(topo,frequencies=(2595.,)),hal).items[0]
    for context in (True,jobs.BatchItemContext(uuid4(),item.item_id)):
        with pytest.raises(ValueError):
            single.resolve_configuration(db_session,configured.id,item.request,hal,batch_item_context=context)
    with pytest.raises(ValueError):
        single.resolve_configuration(db_session,configured.id,item.request,hal)


def test_corrupt_parent_history_is_incomplete_not_rebuilt(db_session,configured,runtime):
    jobs,_=runtime
    from app.schemas.diagnostic_evidence import SequenceEvidence
    ident=uuid4()
    row=DiagnosticRun(id=ident,lab_profile_id=configured.id,target_name=jobs.TARGET,kind='scpi_sequence',success=False,
        sequence_evidence=SequenceEvidence(summary='损坏历史',duration_ms=0,steps=[],log=[],extra={jobs.TARGET:{
            'job_id':str(ident),'lab_id':str(configured.id)}}).model_dump(mode='json'))
    db_session.add(row);db_session.commit()
    assert jobs.record(db_session,row)['status']=='incomplete'


@pytest.mark.parametrize('digest',[None,'0'*64])
async def test_start_requires_matching_preview_before_any_task(db_session,configured,shared_switch,runtime,digest):
    jobs,_=runtime;topo,_=shared_switch
    request=request_for(topo,frequencies=(2595.,)).model_copy(update={'preview_digest':digest})
    try:
        with pytest.raises(ValueError):
            await jobs.start(db_session,configured.id,request,idempotency_key=uuid4())
        assert not jobs._running and db_session.query(DiagnosticRun).count()==0
        assert active_unsafe_diagnostic() is None
    finally:
        await jobs.shutdown_route_batch_jobs()
