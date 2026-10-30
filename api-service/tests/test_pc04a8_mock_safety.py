"""生产HTTP与零I/O拒绝矩阵；沿用已有隔离fixture，不改其实现。"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.models.diagnostic_run import DiagnosticRun
from app.schemas.fixed_route_acquisition import FixedRouteResult
from tests.test_pc_04a_fixed_route_api import configured, client, start, finish
from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_acquisition import request
from tests.test_pc04a8_mock_contract import mock_payload
from tests.test_pc06a1_batch_plan import shared_switch


def test_http_explicit_mock_two_runs_do_not_gain_adoption(client, configured):
    for _ in range(2):
        response=start(client,configured,mock_input=mock_payload())
        assert response.status_code==202,response.text
        run_id=response.json()['run_id']
        record=finish(client,configured,run_id)
        assert record['result']['net_loss_db']==29.
        preview=client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}/application-preview')
        assert preview.status_code==200,preview.text
        assert preview.json()['eligibility']['measurement_provenance']=='simulated'
        assert preview.json()['new_net_loss_db'] is None


@pytest.mark.parametrize('fault',['missing','duplicate','auto','endpoint','model','missing_driver','real_ce','real_sa'])
def test_current_binding_and_runtime_guard_is_zero_io(db_session,configured,fault,monkeypatch):
    from app.hal.channel_emulator import MockChannelEmulator
    from app.hal.signal_analyzer import MockSignalAnalyzer
    from app.services.calibration.fixed_route_jobs import require_explicit_mock_context
    hal=SimpleNamespace(drivers={'channelEmulator':MockChannelEmulator('ce',{}),
                                 'signalAnalyzer':MockSignalAnalyzer('sa',{})})
    bindings=[dict(b) for b in configured.instrument_bindings]
    if fault=='missing': bindings=[]
    elif fault=='duplicate': bindings.append(bindings[0])
    elif fault=='auto': bindings[0]['driver_mode']='auto'
    elif fault=='endpoint': bindings[0]['connection_endpoint']='drift'
    elif fault=='model': bindings[0]['instrument_model_id']=str(uuid4())
    elif fault=='missing_driver': hal.drivers.pop('signalAnalyzer')
    else:
        from app.hal.propsim_f64 import RealPropsimF64Driver
        from app.hal.rs_fsva import RealRsFsvaDriver
        hal.drivers['channelEmulator' if fault=='real_ce' else 'signalAnalyzer']=(
            RealPropsimF64Driver('ce',{'ip':'192.0.2.10'}) if fault=='real_ce' else
            RealRsFsvaDriver('sa',{'ip':'192.0.2.10'}))
    configured.instrument_bindings=bindings;db_session.commit()
    calls=[]
    async def forbidden(*args,**kwargs):
        calls.append(args)
        raise AssertionError('守卫不得操作硬件')
    for driver in hal.drivers.values():
        for method in ('connect','_query','_write','acquire_remote','release_remote'):
            monkeypatch.setattr(driver,method,forbidden,raising=False)
    with pytest.raises(ValueError): require_explicit_mock_context(db_session,configured.id,hal)
    assert calls==[] and db_session.query(DiagnosticRun).count()==0


@pytest.mark.asyncio
async def test_low_level_explicit_input_rejects_real_before_first_io(monkeypatch):
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.rs_fsva import RealRsFsvaDriver
    from app.services.calibration.fixed_route_acquisition import collect_fixed_route
    ce=RealPropsimF64Driver('ce',{'ip':'192.0.2.10'});sa=RealRsFsvaDriver('sa',{'ip':'192.0.2.10'})
    calls=[]
    async def forbidden(*args,**kwargs):
        calls.append(args)
        raise AssertionError('不允许硬件I/O')
    monkeypatch.setattr(ce,'_query',forbidden);monkeypatch.setattr(ce,'_write',forbidden)
    value=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),request=request(mock_input=mock_payload()),configuration={})
    await collect_fixed_route(ce,sa,value,output_port=1,cancel=asyncio.Event())
    assert value.status=='failed' and '全Mock' in value.error
    assert calls==[] and value.exchanges==[] and value.cleanup_confirmed is None


@pytest.mark.parametrize('source',['request','result'])
def test_explicit_source_survives_forged_completed_read(client,configured,db_session,source):
    from app.services.calibration.fixed_route_evidence import check_fixed_route_evidence
    response=start(client,configured,mock_input=mock_payload());assert response.status_code==202,response.text
    run_id=response.json()['run_id'];finish(client,configured,run_id)
    row=db_session.get(DiagnosticRun,uuid4().__class__(run_id))
    import copy
    envelope=copy.deepcopy(row.sequence_evidence);raw=envelope['extra']['fixed_route_acquisition']
    raw.update(status='completed',cleanup_confirmed=True)
    for event in raw['exchanges']: event['simulated']=False
    if source=='request': raw['simulation_input_source']=None
    else: raw['request']['mock_input']=None
    row.sequence_evidence=envelope;db_session.commit()
    url=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}'
    detail=client.get(url).json()
    assert detail['status']=='simulated' and detail['result']['cleanup_confirmed'] is None
    assert check_fixed_route_evidence(FixedRouteResult.model_validate(raw))[0]=='simulated'
    assert client.get(url+'/application-preview').json()['new_net_loss_db'] is None
    assert db_session.get(DiagnosticRun,row.id).sequence_evidence==envelope
    history=client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions').json()
    assert next(r for r in history if r['run_id']==run_id)['status']=='simulated'
    from tests.test_pc04a2_route_application import payload,confirm,counts
    from app.models.probe_calibration import ProbePathLossCalibration
    before=(counts(db_session),db_session.query(ProbePathLossCalibration).count())
    assert confirm(client,configured,payload(client,configured,row)).status_code==422
    assert (counts(db_session),db_session.query(ProbePathLossCalibration).count())==before
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation
    frozen=resolve_effective_route_compensation(db_session,configured.id,'mimo_ota',2595.)
    assert all(e['source_kind']!='confirmed_route' for e in frozen['route_entries'])


def test_explicit_cancel_then_second_run_releases_lock(client,configured):
    first=start(client,configured,mock_input=mock_payload());assert first.status_code==202
    run_id=first.json()['run_id'];url=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}'
    assert client.post(url+'/cancel').status_code==200
    value=finish(client,configured,run_id)
    assert value['status']=='cancelled' and value['result']['net_loss_db'] is None
    assert value['result']['sample_std_db'] is None
    second=start(client,configured,mock_input=mock_payload());assert second.status_code==202,second.text
    assert finish(client,configured,second.json()['run_id'])['status']=='simulated'


@pytest.mark.parametrize('change',['sample','cable','expected'])
def test_explicit_batch_digest_binds_samples_and_reference(db_session,configured,topology_two_chains,change):
    import copy
    from app.hal.channel_emulator import MockChannelEmulator
    from app.hal.signal_analyzer import MockSignalAnalyzer
    from app.schemas.route_batch import BatchPlanRequest
    from app.services.calibration.route_batch_plan import build_batch_plan
    from tests.test_pc06a1_batch_plan import request_for
    body=request_for(topology_two_chains,chains=('conn_p0v','conn_p0h')).model_dump(mode='json')
    body['mock_inputs']=[dict(chain_id=c,frequency_mhz=f,**mock_payload())
        for c in reversed(body['chain_ids']) for f in reversed(body['frequencies_mhz'])]
    body['mock_inputs'][0]['expected_loss_db']=123.
    hal=SimpleNamespace(drivers={'channelEmulator':MockChannelEmulator('ce',{}),'signalAnalyzer':MockSignalAnalyzer('sa',{})})
    plan=build_batch_plan(db_session,configured.id,BatchPlanRequest.model_validate(body),hal)
    assert len(plan.items)==4
    for item in plan.items:
        entry=next(r for r in body['mock_inputs'] if (r['chain_id'],r['frequency_mhz'])==
            (item.request.chain_id,item.request.frequency_mhz))
        assert item.request.mock_input.expected_loss_db==entry['expected_loss_db']
    original=plan.model_dump(mode='json')
    with pytest.raises(ValidationError): plan.items[0].request.mock_input.samples[0].received_dbm=9.
    assert plan.model_dump(mode='json')==original
    body=copy.deepcopy(body);body['preview_digest']=plan.preview_digest
    if change=='sample': body['mock_inputs'][0]['samples'][0]['received_dbm']=-40.
    elif change=='cable': body['references'][0]['receive_cable_loss_db']=3.
    else: body['mock_inputs'][0]['expected_loss_db']=321.
    with pytest.raises(ValueError,match='摘要'): build_batch_plan(db_session,configured.id,BatchPlanRequest.model_validate(body),hal)


@pytest.fixture
def batch_mock(client,db_session,monkeypatch):
    from app.services.calibration import fixed_route_jobs as single,route_batch_jobs as jobs
    from app.api import route_batch as api
    from sqlalchemy.orm import sessionmaker
    hal=single.get_hal_service()
    monkeypatch.setattr(jobs,'get_hal_service',lambda:hal)
    monkeypatch.setattr(api,'get_hal_service',lambda:hal)
    monkeypatch.setattr(jobs,'SessionLocal',sessionmaker(bind=db_session.get_bind(),expire_on_commit=False))
    monkeypatch.setattr(jobs,'instrument_test_lease',single.instrument_test_lease)
    yield jobs,hal
    client.portal.call(jobs.shutdown_route_batch_jobs)


def batch_body(topo,chains=('conn_p0v',)):
    from tests.test_pc06a1_batch_plan import request_for
    body=request_for(topo,chains=chains,frequencies=(2595.,)).model_dump(mode='json')
    body['mock_inputs']=[dict(chain_id=c,frequency_mhz=2595.,**mock_payload()) for c in chains]
    return body


def batch_wait(client,url,status):
    import time
    for _ in range(500):
        value=client.get(url).json()
        if value['status']==status:return value
        time.sleep(.01)
    pytest.fail(str(value))


@pytest.mark.parametrize('fault',['none','binding_after_preview','runtime_after_wait'])
def test_batch_http_replay_drift_and_manual_boundary(client,configured,db_session,topology_two_chains,batch_mock,fault):
    import copy
    from tests.test_pc06a1_batch_api import continuation
    jobs,hal=batch_mock
    url=f'/api/v1/lab-profiles/{configured.id}/route-calibration-batches'
    body=batch_body(topology_two_chains)
    preview=client.post(url+'/preview',json=body);assert preview.status_code==200,preview.text
    body['preview_digest']=preview.json()['preview_digest']
    if fault=='binding_after_preview':
        configured.instrument_bindings=[{**b,'driver_mode':'auto'} for b in configured.instrument_bindings];db_session.commit()
    key={'Idempotency-Key':str(uuid4())}
    response=client.post(url,json=body,headers=key)
    if fault=='binding_after_preview':
        assert response.status_code==422 and db_session.query(DiagnosticRun).count()==0
        return
    assert response.status_code==202,response.text
    ident=response.json()['job_id'];run_url=url+'/'+ident
    assert client.post(url,json=body,headers=key).json()['job_id']==ident
    changed=copy.deepcopy(body);changed['mock_inputs'][0]['samples'][0]['received_dbm']=-30.
    assert client.post(url,json=changed,headers=key).status_code==409
    assert db_session.query(DiagnosticRun).count()==1
    waiting=batch_wait(client,run_url,'waiting_manual')
    calls=[]
    if fault=='runtime_after_wait':
        from app.hal.propsim_f64 import RealPropsimF64Driver
        ce=RealPropsimF64Driver('ce-real',{'ip':'192.0.2.10'})
        async def forbidden(*a,**k): calls.append(a);raise AssertionError('不得硬件动作')
        ce._query=forbidden;ce._write=forbidden
        hal.drivers['channelEmulator']=ce
    assert client.post(run_url+'/continue',json=continuation(waiting)).status_code==200
    value=batch_wait(client,run_url,'paused_failure' if fault=='runtime_after_wait' else 'completed')
    if fault=='runtime_after_wait':
        assert calls==[] and value['items'][0]['run_id'] is None
        assert client.post(run_url+'/cancel').status_code==200
        value=batch_wait(client,run_url,'cancelled')
    assert calls==[] and not jobs._running
    if fault=='none':
        child=client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/'+value['items'][0]['run_id']).json()
        assert child['result']['net_loss_db']==29. and child['status']=='simulated'


def test_explicit_batch_real_switch_is_rejected_before_io(client,configured,shared_switch,batch_mock,db_session):
    topo,_=shared_switch
    url=f'/api/v1/lab-profiles/{configured.id}/route-calibration-batches/preview'
    response=client.post(url,json=batch_body(topo,('ov',)))
    assert response.status_code==422,response.text
    assert db_session.query(DiagnosticRun).count()==0
