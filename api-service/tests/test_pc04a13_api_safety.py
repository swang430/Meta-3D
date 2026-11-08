"""公开HTTP入口及人工等待后全Mock重核；不使用内部事务测试的守卫替身。"""
import copy
import time
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy.orm import sessionmaker
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.rs_fsva import RealRsFsvaDriver
from app.models.diagnostic_run import DiagnosticRun
from app.services.instrument_test_lease import InstrumentTestLease
from tests.test_rf_chain_resolver import db_session,chamber,topology_two_chains,lab_profile
from tests.test_pc_04a_fixed_route_api import client,configured,start
from tests.test_pc06a1_batch_plan import request_for


@pytest.fixture
def batch_hal(client,db_session,monkeypatch):
    from app.api import route_batch as api
    from app.services.calibration import route_batch_jobs as batch,fixed_route_jobs as single
    hal=single.get_hal_service()
    monkeypatch.setattr(api,'get_hal_service',lambda:hal)
    monkeypatch.setattr(batch,'get_hal_service',lambda:hal)
    monkeypatch.setattr(batch,'SessionLocal',sessionmaker(bind=db_session.get_bind(),expire_on_commit=False))
    monkeypatch.setattr(batch,'instrument_test_lease',InstrumentTestLease(lambda:hal).hold)
    return hal


@pytest.mark.parametrize('kind',['real','mixed'])
def test_single_and_batch_http_reject_before_any_io(client,configured,topology_two_chains,db_session,batch_hal,monkeypatch,kind):
    root=f'/api/v1/lab-profiles/{configured.id}/route-calibration-batches'
    body=request_for(topology_two_chains,chains=('conn_p0v',),frequencies=(2595.,)).model_dump(mode='json')
    plan=client.post(root+'/preview',json=body)
    assert plan.status_code==200,plan.text
    body['preview_digest']=plan.json()['preview_digest']
    batch_hal.drivers['channelEmulator']=RealPropsimF64Driver('real',{'ip':'192.0.2.10'})
    if kind=='real': batch_hal.drivers['signalAnalyzer']=RealRsFsvaDriver('real-sa',{'ip':'192.0.2.10'})
    calls=[]
    async def forbidden(*a,**k): calls.append(a);raise AssertionError('不允许访问仪器')
    for driver in batch_hal.drivers.values():
        for method in ('_query','_write','acquire_remote','connect'):
            monkeypatch.setattr(driver,method,forbidden,raising=False)
    for response in (start(client,configured),client.post(root+'/preview',json=body),
                     client.post(root,json=body,headers={'Idempotency-Key':str(uuid4())})):
        assert response.status_code==422,response.text
        assert 'Mock' in response.text
    assert calls==[] and db_session.query(DiagnosticRun).count()==0


def test_waiting_batch_rechecks_runtime_before_switch_or_capture(client,configured,topology_two_chains,batch_hal,monkeypatch):
    from app.services.calibration import route_batch_jobs as batch
    root=f'/api/v1/lab-profiles/{configured.id}/route-calibration-batches'
    body=request_for(topology_two_chains,chains=('conn_p0v',),frequencies=(2595.,)).model_dump(mode='json')
    plan=client.post(root+'/preview',json=body);assert plan.status_code==200,plan.text
    body['preview_digest']=plan.json()['preview_digest']
    response=client.post(root,json=body,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==202,response.text
    url=root+'/'+response.json()['job_id']
    def poll(status):
        for _ in range(100):
            value=client.get(url).json()
            if value['status']==status:return value
            time.sleep(.01)
        pytest.fail(str(value))
    value=poll('waiting_manual')
    original=batch_hal.drivers['signalAnalyzer']
    batch_hal.drivers['signalAnalyzer']=RealRsFsvaDriver('drift',{'ip':'192.0.2.10'})
    calls=[]
    async def forbidden(*a,**k):calls.append(a);raise AssertionError('等待后禁止任何开关或采集')
    monkeypatch.setattr(batch,'apply_batch_switch_steps',forbidden)
    monkeypatch.setattr(batch,'collect_fixed_route',forbidden)
    item=value['items'][0]
    try:
        response=client.post(url+'/continue',json=dict(item_id=item['item_id'],transition_id=value['transition_id'],
            reference_antenna=item['request']['reference_antenna'],manual_confirmed=True))
        assert response.status_code==200,response.text
        value=poll('paused_failure')
        assert 'Mock' in value['error'] and calls==[]
    finally:
        batch_hal.drivers['signalAnalyzer']=original
        client.post(url+'/cancel')
        poll('cancelled')
