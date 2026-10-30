"""显式演练输入经过生产模型及计算，不从期待值反推结果。"""
import asyncio
import math
from uuid import uuid4

import pytest
from pydantic import ValidationError
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.schemas.fixed_route_acquisition import FixedRouteRequest, FixedRouteResult
from app.services.calibration.fixed_route_acquisition import collect_fixed_route
from tests.test_pc_04a_fixed_route_acquisition import request


def mock_payload():
    return dict(samples=[dict(source_before_dbm=-20., received_dbm=-50., source_after_dbm=-18.),
                         dict(source_before_dbm=-22., received_dbm=-52., source_after_dbm=-20.)],
                expected_loss_db=999.)


@pytest.mark.asyncio
@pytest.mark.parametrize('cable,source,want', [(2.,'synthetic cable',29.), (0.,'synthetic zero',31.),
                                             (None,'synthetic cable',None), (2.,None,None)])
async def test_explicit_mock_uses_measured_sample_formula_once(cable,source,want):
    body=request().model_dump()
    body.update(mock_input=mock_payload(), receive_cable_loss_db=cable, receive_cable_source=source)
    value=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),
        request=FixedRouteRequest.model_validate(body),configuration={})
    value=await collect_fixed_route(MockChannelEmulator('ce',{}),MockSignalAnalyzer('sa',{}),
        value,output_port=1,cancel=asyncio.Event())
    assert value.status=='simulated' and value.formal_eligible is False
    assert value.simulation_input_source=='operator_supplied_synthetic'
    assert len(value.samples)==2 and value.net_loss_db==want
    assert value.sample_std_db==(0. if want is not None else None)
    assert value.cleanup_confirmed is None
    assert all(e.simulated and e.response is None for e in value.exchanges)


@pytest.mark.parametrize('value', [True,'-20',float('nan'),float('inf')])
def test_mock_sample_rejects_nonfinite_or_coerced_values(value):
    body=request().model_dump();body['mock_input']=mock_payload()
    body['mock_input']['samples'][0]['source_before_dbm']=value
    with pytest.raises(ValidationError): FixedRouteRequest.model_validate(body)


@pytest.mark.parametrize('field', ['host_time','formal_eligible','measurement_provenance','simulated','simulation_input_source'])
def test_mock_input_cannot_claim_trusted_identity(field):
    body=request().model_dump();body['mock_input']=mock_payload()
    body['mock_input']['samples'][0][field]=True
    with pytest.raises(ValidationError): FixedRouteRequest.model_validate(body)


@pytest.mark.asyncio
async def test_negative_gain_and_sample_standard_deviation():
    body=request().model_dump();body['mock_input']=mock_payload()
    body['mock_input']['samples'][0]['received_dbm']=-10.
    body['mock_input']['samples'][1]['received_dbm']=-14.
    value=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),request=body,configuration={})
    await collect_fixed_route(MockChannelEmulator('ce',{}),MockSignalAnalyzer('sa',{}),value,
        output_port=1,cancel=asyncio.Event())
    assert value.net_loss_db == -10.
    assert value.sample_std_db == pytest.approx(math.sqrt(2))


@pytest.mark.parametrize('count',[1,3])
def test_single_sample_count_must_match(count):
    body=request().model_dump();body['mock_input']=mock_payload()
    body['mock_input']['samples']=(body['mock_input']['samples']*2)[:count]
    with pytest.raises(ValidationError): FixedRouteRequest.model_validate(body)


@pytest.mark.parametrize('fault',['empty','duplicate','extra','missing','count'])
def test_batch_explicit_matrix_is_complete_unique_and_counted(fault):
    from app.schemas.route_batch import BatchPlanRequest
    from tests.test_pc06a1_batch_plan import request_for
    from types import SimpleNamespace
    body=request_for(SimpleNamespace(id=uuid4())).model_dump(mode='json')
    rows=[dict(chain_id=c,frequency_mhz=f,**mock_payload()) for c in body['chain_ids'] for f in body['frequencies_mhz']]
    if fault=='empty': rows=[]
    elif fault=='duplicate': rows.append(rows[0])
    elif fault=='extra': rows.append(dict(chain_id='extra',frequency_mhz=2595.,**mock_payload()))
    elif fault=='missing': rows.pop()
    else: rows[0]['samples']=rows[0]['samples'][:1]
    body['mock_inputs']=rows
    with pytest.raises(ValidationError): BatchPlanRequest.model_validate(body)


@pytest.mark.asyncio
async def test_cleanup_failure_clears_both_statistics_but_retains_samples(monkeypatch):
    from tests.test_pc_04a_fixed_route_acquisition import instruments,collect
    ce,sa,*_=instruments(stop_error=True)
    value=await collect(ce,sa,monkeypatch)
    assert value.status=='cleanup_unconfirmed' and len(value.samples)==2
    assert value.net_loss_db is None and value.sample_std_db is None
