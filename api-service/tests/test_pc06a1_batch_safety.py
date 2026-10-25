"""严格回读与批安全边界；真实HAL只替换外部transport。"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.hal.rf_switch import EtslSwitchDriver
from app.schemas.route_batch import BatchSwitchStep
from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured
from tests.test_pc06a1_batch_plan import shared_switch, request_for
from tests.test_pc06a1_batch_jobs import runtime, start_previewed, wait_state, advance
from app.models.diagnostic_run import DiagnosticRun
from uuid import UUID


async def start_confirmed(jobs,db,lab_id,request,*,idempotency_key):
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.schemas.route_batch import BatchSwitchWiringConfirmation
    from datetime import datetime,timezone
    plan=build_batch_plan(db,lab_id,request,None)
    if plan.switch_scope_digest:
        request=request.model_copy(update={'switch_wiring_confirmation':BatchSwitchWiringConfirmation(
            operator='测试操作员自述',confirmed_at=datetime.now(timezone.utc),note='已核对明确映射接线',
            switch_scope_digest=plan.switch_scope_digest)})
    return await start_previewed(jobs,db,lab_id,request,idempotency_key=idempotency_key)


def switch_runtime(monkeypatch, *, relay_type='sp6t', target=1, reply='1'):
    mapping=dict(switch_id='1:INT_RELAY_A',relay_type=relay_type,input_port=0,output_port=target,
        topology_input_pin='in1',topology_output_pin='out1')
    driver=EtslSwitchDriver('switch-1',dict(ip='192.0.2.20',port_maps={'v':mapping}))
    calls=[]
    async def transport(command):
        calls.append(command)
        if command=='*IDN?': return 'ETS-Lindgren EMCenter version 4.3.4'
        if command=='1:*IDN?': return 'ETS-Lindgren, EMSwitch 7001-003, 4.3.3'
        if command in ('INTLK? SAFETYRELAY','1:INTLK? SAFETYRELAY'): return '0'
        if command.endswith('?'): return reply
        return 'OK'
    monkeypatch.setattr(driver,'_send_command',transport)
    step=BatchSwitchStep(node_id='sw',path_name='v',category_id=uuid4(),connection_id=uuid4(),
        endpoint='192.0.2.20',instrument_model_id=uuid4(),driver_mode='real',mapping=mapping,
        connection_config={'endpoint':'192.0.2.20'})
    return driver,step,calls


@pytest.mark.parametrize('kind,target,raw,expected,error',[
    ('spdt','NC','NC','NC',False),('spdt','NO','NO','NO',False),
    ('spdt','NC','ERROR 201 NC',None,True),('spdt','NC','0',None,True),
    ('spdt','NC',None,None,True),('spdt','NC','',None,True),
    ('sp6t',1,'1',1,False),('sp6t',1,'0',0,False),
    ('sp6t',1,'7',None,True),('sp6t',1,'NC',None,True),
])
async def test_strict_receipt_never_coerces_error_or_sp6t_open_into_spdt(monkeypatch,kind,target,raw,expected,error):
    driver,_,_=switch_runtime(monkeypatch,relay_type=kind,target=target,reply=raw)
    method=getattr(driver,'read_mapped_path_receipt',None)
    assert method is not None, '缺少原始严格receipt，不允许旧get_path整数冒充回读'
    receipt=await method('v')
    assert receipt['raw']==raw and receipt['relay_type']==kind
    assert receipt['position']==expected and bool(receipt['error'])==error
    assert receipt['command']=='1:INT_RELAY_A?' and receipt['simulated'] is False


async def test_legacy_get_path_rejects_error_containing_nc(monkeypatch):
    driver,_,_=switch_runtime(monkeypatch,reply='ERROR 201 NC')
    assert await driver.get_path('1:INT_RELAY_A')==-1


async def apply(hal,steps,sink):
    try:
        from app.services.calibration.route_batch_switch import apply_batch_switch_steps
    except ImportError:
        pytest.fail('缺少逐项严格切换实现')
    return await apply_batch_switch_steps(hal,steps,sink)


async def test_real_auto_uses_existing_builder_then_matching_raw_receipt(monkeypatch):
    driver,step,calls=switch_runtime(monkeypatch)
    receipts=[]
    assert await apply(SimpleNamespace(drivers={'rfSwitch':driver}),[step],receipts.append) is True
    assert calls==['*IDN?','1:*IDN?','1:INT_RELAY_A?','1:INTLK? SAFETYRELAY','1:INT_RELAY_A_1','1:INT_RELAY_A?']
    assert receipts[-1]['position']==1 and receipts[-1]['raw']=='1'


@pytest.mark.parametrize('fault',['write_false','unknown','wrong','timeout','interlock','identity','mapping','identity_timeout'])
async def test_auto_refuses_unqualified_write_or_raw(monkeypatch,fault):
    driver,step,calls=switch_runtime(monkeypatch)
    original=driver._send_command
    async def transport(command):
        if fault=='identity_timeout' and command=='*IDN?': raise TimeoutError('identity timeout')
        if fault=='write_false' and command.endswith('_1'): return None
        if fault=='unknown' and command=='1:INT_RELAY_A?': return 'ERROR NC'
        if fault=='wrong' and command=='1:INT_RELAY_A?': return '2'
        if fault=='timeout' and command=='1:INT_RELAY_A?': raise TimeoutError('test timeout')
        if fault=='interlock' and command=='1:INTLK? SAFETYRELAY': return 'ERROR 3'
        if fault=='identity' and command=='*IDN?': return ''
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    if fault=='mapping': driver._mappings['v']={**step.mapping,'output_port':2}
    receipts=[]
    assert await apply(SimpleNamespace(drivers={'rfSwitch':driver}),[step],receipts.append) is False
    assert receipts and receipts[-1]['error']
    if fault=='identity_timeout': assert receipts[-1]['command']=='*IDN?'


async def test_fixed_direct_does_not_touch_switch(monkeypatch):
    driver,_,calls=switch_runtime(monkeypatch)
    assert await apply(SimpleNamespace(drivers={'rfSwitch':driver}),[],[].append) is True
    assert calls==[]


@pytest.fixture
def safety_runtime(runtime,shared_switch,db_session,monkeypatch):
    jobs,hal=runtime
    monkeypatch.setattr(jobs,'_prepare_item',hal.batch_prepare)
    _,conn=shared_switch
    # 自动正例只覆盖本次手册已证明互锁适用性的SP6T，绝不把型号字符串当卡型证明。
    conn.connection_params={**conn.connection_params,'port_maps':{name:{**mapping,'relay_type':'sp6t',
        'output_port':1 if name=='v' else 2} for name,mapping in conn.connection_params['port_maps'].items()}}
    db_session.commit()
    driver,_,calls=switch_runtime(monkeypatch)
    driver._mappings=conn.connection_params['port_maps']
    positions={'1:INT_RELAY_A':'1','1:INT_RELAY_B':'2'}
    original=driver._send_command
    async def transport(command):
        if command in ('1:INT_RELAY_A?','1:INT_RELAY_B?'):
            calls.append(command);return positions[command[:-1]]
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    hal.drivers['rfSwitch']=driver
    return jobs,hal,calls


async def test_first_reference_confirmation_and_no_repeat_for_same_frequency_route(db_session,configured,shared_switch,safety_runtime):
    jobs,hal,calls=safety_runtime
    topo,_=shared_switch
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,chains=('ov',)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await wait_state(jobs,db_session,ident,'waiting_manual')
    assert calls==[], '首项摆位确认前不得切换'
    await advance(jobs,db_session,configured,ident)
    # 相同路线/参考位置的第二频点不需要第二次人工确认。
    try:
        await asyncio.wait_for(asyncio.shield(task),8)
    except TimeoutError:
        jobs.request_cancel(ident);await task
        pytest.fail('同参考无换线不应再次人工暂停')
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert final['status']=='completed' and [i['status'] for i in final['items']]==['completed','completed']


async def test_switch_failure_pauses_without_collect_and_continue_explicitly_skips(db_session,configured,shared_switch,safety_runtime,monkeypatch):
    jobs,hal,calls=safety_runtime
    driver=hal.drivers['rfSwitch'];original=driver._send_command
    async def transport(command):
        if command=='1:INT_RELAY_B?': return '1'
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    topo,_=shared_switch
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await advance(jobs,db_session,configured,ident)
    for _ in range(400):
        db_session.expire_all();value=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
        if value['status'] not in ('running','waiting_manual'): break
        await asyncio.sleep(.005)
    try:
        assert value['status']=='paused_failure' and value['items'][0]['run_id'] is None
        failed=value['items'][0]
        with pytest.raises(ValueError):
            jobs.continue_job(db_session,configured.id,ident,item_id=failed['item_id'],transition_id=value['transition_id'],
                reference_antenna=failed['request']['reference_antenna'],manual_confirmed=True)
        jobs.continue_job(db_session,configured.id,ident,item_id=failed['item_id'],transition_id=value['transition_id'],
            reference_antenna=failed['request']['reference_antenna'],manual_confirmed=True,skip_failed=True)
        await advance(jobs,db_session,configured,ident)
        await task
        db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
        assert [i['status'] for i in final['items']]==['failed','completed']
        assert final['status']=='failed'
    finally:
        if not task.done(): jobs.request_cancel(ident);await task


@pytest.mark.parametrize('stage',['pending','manual','switching','measuring','failure'])
async def test_cancel_each_stage_never_starts_next_item(db_session,configured,shared_switch,safety_runtime,monkeypatch,stage):
    jobs,hal,calls=safety_runtime
    topo,_=shared_switch
    entered=asyncio.Event();release=asyncio.Event()
    driver=hal.drivers['rfSwitch'];original=driver._send_command
    async def transport(command):
        if stage=='switching' and command.endswith('_2'):
            entered.set();await release.wait()
        if stage=='failure' and command=='1:INT_RELAY_B?': return '1'
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    original_collect=jobs.collect_fixed_route
    collected=[]
    async def collect(*args,**kwargs):
        collected.append(args[2].request.chain_id)
        return await original_collect(*args,**kwargs)
    monkeypatch.setattr(jobs,'collect_fixed_route',collect)
    ce=hal.drivers['channelEmulator'];original_write=ce._write
    async def ce_write(command):
        result=await original_write(command)
        if stage=='measuring' and 'OUTPut:INTERFerence:ADD' in command:
            entered.set();await release.wait()
        return result
    monkeypatch.setattr(ce,'_write',ce_write)
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    if stage in ('switching','measuring','failure'):
        await advance(jobs,db_session,configured,ident)
        if stage=='failure': await wait_state(jobs,db_session,ident,'paused_failure')
        else: await asyncio.wait_for(entered.wait(),2)
    elif stage=='manual': await wait_state(jobs,db_session,ident,'waiting_manual')
    jobs.request_cancel(ident);jobs.request_cancel(ident)
    release.set();await task
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert final['status']=='cancelled'
    assert collected==(['oh'] if stage=='measuring' else [])
    assert final['items'][1]['status']=='cancelled' and final['items'][1]['run_id'] is None
    count=len(calls)
    with pytest.raises(ValueError): jobs.request_cancel(ident)
    assert len(calls)==count


async def test_cleanup_unknown_blocks_manual_permanently_and_overrides_cancel(db_session,configured,shared_switch,safety_runtime,monkeypatch):
    jobs,hal,_=safety_runtime
    ce=hal.drivers['channelEmulator']
    resource=ce._visa_resource
    original=resource.write
    async_cancel=False
    def write(command):
        nonlocal async_cancel
        if 'OUTPut:INTERFerence:REMove pc04_' in command:
            async_cancel=True
            active=next(iter(jobs._running.values()));active.cancel.set()
            raise RuntimeError('停止失败')
        return original(command)
    monkeypatch.setattr(resource,'write',write)
    topo,_=shared_switch
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await advance(jobs,db_session,configured,ident);await task
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert async_cancel and final['status']=='cleanup_unconfirmed'
    assert '可能' in final['error'] and '发射' in final['error']
    assert final['items'][1]['run_id'] is None
    child=db_session.get(DiagnosticRun,UUID(final['items'][0]['run_id']))
    result=child.sequence_evidence['extra']['fixed_route_acquisition']
    assert result['net_loss_db'] is None and result['cleanup_confirmed'] is False
    with pytest.raises(ValueError):
        jobs.continue_job(db_session,configured.id,ident,item_id=final['items'][1]['item_id'],transition_id='old',
            reference_antenna=final['items'][1]['request']['reference_antenna'],manual_confirmed=True)


async def test_identity_changes_between_items_refuses_second_collect(db_session,configured,shared_switch,safety_runtime,monkeypatch):
    jobs,hal,_=safety_runtime
    driver=hal.drivers['rfSwitch'];original=driver._send_command;chassis_queries=0
    async def transport(command):
        nonlocal chassis_queries
        if command=='*IDN?':
            chassis_queries+=1
            if chassis_queries>1: return 'ETS-Lindgren EMCenter version 9.9.9'
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    topo,_=shared_switch
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,chains=('ov',)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await advance(jobs,db_session,configured,ident)
    try:
        value=await wait_state(jobs,db_session,ident,'paused_failure')
        assert value['items'][0]['status']=='completed' and value['items'][1]['run_id'] is None
        assert any(r['error'] for r in value['items'][1]['switch_receipts'])
    finally:
        if not task.done(): jobs.request_cancel(ident)
        await task


def test_wiring_declaration_is_scoped_to_frozen_bindings_and_changes_preview_digest(db_session,configured,shared_switch):
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.schemas import route_batch as schema
    from datetime import datetime, timezone
    declaration_type=getattr(schema,'BatchSwitchWiringConfirmation',None)
    assert declaration_type is not None, '缺少带具体映射范围的操作员声明'
    topo,conn=shared_switch
    request=request_for(topo)
    preview=build_batch_plan(db_session,configured.id,request,None)
    confirmation=declaration_type(operator='操作员自述姓名',confirmed_at=datetime.now(timezone.utc),
        note='已核对本清单明确映射接线；不是RF现场验收',switch_scope_digest=preview.switch_scope_digest)
    confirmed=request.model_copy(update={'switch_wiring_confirmation':confirmation})
    plan=build_batch_plan(db_session,configured.id,confirmed,None)
    assert plan.preview_digest!=preview.preview_digest
    assert plan.switch_wiring_confirmation==confirmation
    params=dict(conn.connection_params);maps={k:dict(v) for k,v in params['port_maps'].items()}
    maps['v']['output_port']='NO';params['port_maps']=maps;conn.connection_params=params;db_session.commit()
    with pytest.raises(ValueError,match='声明.*范围|范围.*声明'):
        build_batch_plan(db_session,configured.id,confirmed,None)


@pytest.mark.parametrize('drift',['endpoint','transport'])
async def test_saved_drift_while_waiting_causes_zero_switch_io(db_session,configured,shared_switch,safety_runtime,drift):
    jobs,hal,calls=safety_runtime
    topo,connection=shared_switch
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await wait_state(jobs,db_session,ident,'waiting_manual')
    # 等待期间改保存端点；HAL仍是旧连接，不能先操作旧映射再报漂移。
    if drift=='endpoint': connection.endpoint='192.0.2.99'
    else: connection.connection_params={**connection.connection_params,'transport':'raw'}
    db_session.commit()
    await advance(jobs,db_session,configured,ident)
    try:
        await wait_state(jobs,db_session,ident,'paused_failure')
        assert calls==[]
    finally:
        jobs.request_cancel(ident);await task


async def test_fixed_direct_job_has_zero_switch_calls(db_session,configured,shared_switch,safety_runtime):
    jobs,hal,calls=safety_runtime
    import copy
    topo,_=shared_switch
    nodes=copy.deepcopy(topo.nodes)
    topo.nodes=[n for n in nodes if n['id']!='sw']
    for n in topo.nodes:
        n['params'].pop('rf_path_selection',None)
    topo.connections=[dict(id='ov',source='ce1',source_pin='out',target='pv',target_pin='in'),
        dict(id='oh',source='ce2',source_pin='out',target='ph',target_pin='in')]
    topo.operating_modes=[dict(id='mimo_ota',active_connections=['ov','oh'])]
    db_session.commit()
    value=await start_previewed(jobs,db_session,configured.id,request_for(topo,chains=('ov',),frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await advance(jobs,db_session,configured,ident);await task
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert final['status']=='completed' and calls==[]


async def test_mock_manual_never_claims_physical_safe(db_session,configured,shared_switch,safety_runtime):
    from app.hal.channel_emulator import MockChannelEmulator
    from app.hal.signal_analyzer import MockSignalAnalyzer
    from app.models.instrument import InstrumentCategory
    jobs,hal,calls=safety_runtime
    hal.drivers['channelEmulator']=MockChannelEmulator('ce',{})
    hal.drivers['signalAnalyzer']=MockSignalAnalyzer('sa',{})
    configured.instrument_bindings=[{**b,'driver_mode':'mock'} if b['connection_endpoint']=='192.0.2.10' else b
        for b in configured.instrument_bindings]
    db_session.query(InstrumentCategory).filter(InstrumentCategory.category_key.in_(['channelEmulator','signalAnalyzer'])).update({'driver_mode':'mock'},synchronize_session=False)
    db_session.commit()
    topo,_=shared_switch
    value=await start_previewed(jobs,db_session,configured.id,request_for(topo,chains=('ov',),frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    waiting=await wait_state(jobs,db_session,ident,'waiting_manual')
    assert '模拟人工步骤' in waiting['manual_notice'] and '未确认' in waiting['manual_notice']
    await advance(jobs,db_session,configured,ident);await task
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert final['items'][0]['status']=='simulated' and calls==[]
    child=db_session.get(DiagnosticRun,UUID(final['items'][0]['run_id']))
    result=child.sequence_evidence['extra']['fixed_route_acquisition']
    assert result['cleanup_confirmed'] is None and result['net_loss_db'] is None
    assert jobs.batch_child_context(db_session,child)['finalized'] is False


async def test_repeated_task_cancellation_waits_for_tone_cleanup(db_session,configured,shared_switch,safety_runtime,monkeypatch):
    from app.services.execution_exclusion_guard import active_unsafe_diagnostic
    jobs,hal,_=safety_runtime
    ce=hal.drivers['channelEmulator'];original_write=ce._write
    started=asyncio.Event();cleaning=asyncio.Event();release=asyncio.Event()
    async def write(command):
        result=await original_write(command)
        if 'OUTPut:INTERFerence:ADD' in command: started.set()
        if 'OUTPut:INTERFerence:REMove pc04_' in command:
            cleaning.set();await release.wait()
        return result
    monkeypatch.setattr(ce,'_write',write)
    topo,_=shared_switch
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await advance(jobs,db_session,configured,ident);await started.wait()
    task.cancel();await cleaning.wait();task.cancel()
    await asyncio.sleep(.01)
    assert not task.done() and active_unsafe_diagnostic()==jobs.TARGET
    release.set();await task
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert final['status']=='cancelled' and final['items'][1]['run_id'] is None
    assert final['cancel_requested'] is True and final['items'][1]['status']=='cancelled'
    child=db_session.get(DiagnosticRun,UUID(final['items'][0]['run_id']))
    assert child.sequence_evidence['extra']['fixed_route_acquisition']['cleanup_confirmed'] is True


async def test_same_reference_auto_route_change_does_not_repeat_manual(db_session,configured,shared_switch,safety_runtime):
    jobs,hal,_=safety_runtime
    topo,_=shared_switch
    request=request_for(topo,frequencies=(2595.,))
    request=request.model_copy(update={'references':tuple(r.model_copy(update={'reference_antenna':'同一固定位置参考件'}) for r in request.references)})
    value=await start_confirmed(jobs,db_session,configured.id,request,idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await advance(jobs,db_session,configured,ident)
    try:
        await asyncio.wait_for(asyncio.shield(task),7)
    except TimeoutError:
        jobs.request_cancel(ident);await task
        pytest.fail('同参考且由自动开关换路、不需换线时不应重复暂停')
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert [i['status'] for i in final['items']]==['completed','completed']


@pytest.mark.parametrize('key,value',[('transport','raw'),('port',9999),('command_style','verbose'),('line_terminator','lf')])
async def test_same_host_but_other_effective_transport_refuses_all_io(monkeypatch,key,value):
    driver,step,calls=switch_runtime(monkeypatch)
    assert hasattr(step,'connection_config'), '冻结步骤缺少生效连接与封装配置'
    step=step.model_copy(update={'connection_config':{'endpoint':'192.0.2.20',key:value}})
    receipts=[]
    assert await apply(SimpleNamespace(drivers={'rfSwitch':driver}),[step],receipts.append) is False
    assert calls==[] and receipts[-1]['error']


async def test_task_cancel_during_switch_waits_for_inflight_transport(db_session,configured,shared_switch,safety_runtime,monkeypatch):
    from app.services.execution_exclusion_guard import active_unsafe_diagnostic
    jobs,hal,_=safety_runtime
    driver=hal.drivers['rfSwitch'];original=driver._send_command
    entered=asyncio.Event();release=asyncio.Event();finished=asyncio.Event()
    async def transport(command):
        if command.endswith('_2'):
            entered.set();await release.wait();finished.set()
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    topo,_=shared_switch
    value=await start_confirmed(jobs,db_session,configured.id,request_for(topo,frequencies=(2595.,)),idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    await advance(jobs,db_session,configured,ident);await entered.wait()
    try:
        task.cancel();await asyncio.sleep(.02)
        assert not task.done() and active_unsafe_diagnostic()==jobs.TARGET
    finally:
        release.set();await task
    assert finished.is_set()
    db_session.expire_all();final=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
    assert final['status']=='cancelled' and all(i['run_id'] is None for i in final['items'])


async def test_failed_prepare_after_move_requires_confirmation_when_returning_to_old_reference(db_session,configured,shared_switch,safety_runtime,monkeypatch):
    jobs,hal,_=safety_runtime
    topo,_=shared_switch
    driver=hal.drivers['rfSwitch'];original=driver._send_command;reads=0
    async def transport(command):
        nonlocal reads
        if command=='1:INT_RELAY_A?':
            reads+=1
            if reads==4: return '2'
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    request=request_for(topo,chains=('ov',),frequencies=(2000.,2595.,3500.))
    request=request.model_copy(update={'references':tuple(r.model_copy(update={
        'reference_antenna':'位置B' if r.frequency_mhz==2595. else '位置A'}) for r in request.references)})
    value=await start_confirmed(jobs,db_session,configured.id,request,idempotency_key=uuid4())
    ident=UUID(value['job_id']);task=jobs._running[ident].task
    try:
        await advance(jobs,db_session,configured,ident)  # A成功
        await advance(jobs,db_session,configured,ident)  # 已明确移到B，此后切换失败
        value=await wait_state(jobs,db_session,ident,'paused_failure')
        failed=value['items'][1]
        jobs.continue_job(db_session,configured.id,ident,item_id=failed['item_id'],transition_id=value['transition_id'],
            reference_antenna='位置B',manual_confirmed=True,skip_failed=True)
        await asyncio.sleep(.05)
        db_session.expire_all();value=jobs.record(db_session,db_session.get(DiagnosticRun,ident))
        assert value['status']=='waiting_manual' and value['current_index']==2
        assert value['items'][2]['run_id'] is None, '参考件仍在B，返回A必须重新确认后才能采集'
    finally:
        if not task.done(): jobs.request_cancel(ident)
        await task


async def test_spdt_bare_interlock_zero_never_qualifies_auto(monkeypatch):
    driver,step,calls=switch_runtime(monkeypatch,relay_type='spdt',target='NC',reply='NC')
    receipts=[]
    assert await apply(SimpleNamespace(drivers={'rfSwitch':driver}),[step],receipts.append) is False
    assert not any(command.endswith('_NC') for command in calls)
    assert receipts[-1]['error']


async def test_sp6t_interlock_is_addressed_to_target_slot(monkeypatch):
    driver,step,calls=switch_runtime(monkeypatch,relay_type='sp6t',target=1,reply='1')
    original=driver._send_command
    async def transport(command):
        if command=='1:INTLK? SAFETYRELAY':
            calls.append(command);return '0'
        return await original(command)
    monkeypatch.setattr(driver,'_send_command',transport)
    receipts=[]
    assert await apply(SimpleNamespace(drivers={'rfSwitch':driver}),[step],receipts.append) is True
    assert 'INTLK? SAFETYRELAY' not in calls
    assert calls.index('1:INTLK? SAFETYRELAY')<calls.index('1:INT_RELAY_A_1')


async def test_other_slot_or_unaddressed_zero_cannot_allow_unknown_target_interlock(monkeypatch):
    driver,step,calls=switch_runtime(monkeypatch,relay_type='sp6t',target=1,reply='1')
    original=driver._send_command
    async def transport(command):
        if command=='1:INTLK? SAFETYRELAY':
            calls.append(command);return None
        return await original(command)  # 裸查询0不得授权slot1。
    monkeypatch.setattr(driver,'_send_command',transport)
    receipts=[]
    assert await apply(SimpleNamespace(drivers={'rfSwitch':driver}),[step],receipts.append) is False
    assert '1:INT_RELAY_A_1' not in calls and receipts[-1]['error']
