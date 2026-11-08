"""完整模拟必须实际消费共享事务，且所有证据仍为模拟。"""
import asyncio
from uuid import uuid4
import pytest
from app.schemas.fixed_route_acquisition import FixedRouteRequest, FixedRouteResult
from app.services.calibration import fixed_route_acquisition as collector
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.signal_analyzer import MockSignalAnalyzer
from tests.test_pc_04a_fixed_route_acquisition import request, instruments
from tests.test_pc04a8_mock_contract import mock_payload


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    async def settle(): pass
    monkeypatch.setattr(collector, '_settle', settle)


async def test_explicit_samples_are_consumed_by_queries_and_stopped_transaction():
    result=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),request=request(mock_input=mock_payload()),configuration={})
    await collector.collect_fixed_route(MockChannelEmulator('ce',{}),MockSignalAnalyzer('sa',{}),result,output_port=1,cancel=asyncio.Event())
    assert result.status=='simulated',result.error
    assert result.net_loss_db==29
    queries=[e for e in result.exchanges if e.response is not None]
    assert queries, '不得只列命令预览并复制样本'
    assert all(e.simulated for e in result.exchanges)
    assert [e.response for e in queries if e.command=='DIAG:SIMU:STATE?']==['STOPPED','RUNNING','RUNNING','STOPPED']
    commands=[e.command for e in result.exchanges]
    assert commands.index('DIAG:SIMU:GO') < commands.index('OUTPut:MEASure:RESult:GET? 1,1')
    assert commands.index('DIAG:SIMU:STOP') < next(i for i,c in enumerate(commands) if c.startswith('OUTPut:INTERFerence:REMove'))
    assert result.cleanup_confirmed is None
    assert result.states['simulated_cleanup_confirmed'] is True


async def test_initial_running_is_rejected_without_writes():
    ce,sa,writes,_,_=instruments(state='RUNNING')
    result=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),request=request(),configuration={})
    await collector._collect_fixed_route_transaction(ce,sa,result,output_port=1,cancel=asyncio.Event())
    assert result.status=='failed'
    assert writes==[]


def test_model_switch_has_no_samples_and_rejects_manual_cable():
    payload=request().model_dump()
    payload.update(mock_model='full_route_v1',receive_cable_loss_db=None,receive_cable_source=None)
    value=FixedRouteRequest.model_validate(payload)
    assert value.mock_model=='full_route_v1' and value.mock_input is None
    payload['receive_cable_loss_db']=0
    with pytest.raises(ValueError): FixedRouteRequest.model_validate(payload)


def model_result():
    from app.schemas.route_calibration import RouteSelection
    lab,topo,chamber=uuid4(),uuid4(),uuid4()
    def node(ident,kind,value=None,key='loss_db'):
        params={} if value is None else {'simulation_model':{'frequency_mhz':2595.,key:value}}
        return dict(id=ident,type=kind,params=params)
    nodes=[node('ce','ce_port'),node('tx1','cable',1.),node('pa','amplifier',10.,'gain_db'),node('tx2','cable',2.),node('probe','probe',3.,'gain_db')]
    nodes[-1]['params'].update(probe_id=1,polarization='V')
    refs=[node('air','air_path',40.),node('sgh','reference_antenna',4.,'gain_db'),node('rx','receive_cable',.2),node('sa','signal_analyzer')]
    refs[-1]['params']['instrument_category_id']='sa-category'
    def edges(ns):
        return [dict(id=f'e-{a["id"]}-{b["id"]}',source=a['id'],target=b['id'],source_pin='out',target_pin='in') for a,b in zip(ns,ns[1:])]
    tx,rx=edges(nodes),edges([nodes[-1],*refs])
    route=RouteSelection(lab_profile_id=lab,chamber_id=chamber,topology_id=topo,operating_mode='mimo_ota',chain_id=tx[-1]['id'],ce_port='B1.1',probe_id=1,polarization='V',node_ids=[n['id'] for n in nodes],connection_ids=[e['id'] for e in tx],nodes=nodes,connections=tx,ports=[dict(connection_id=e['id'],**{k:v for k,v in e.items() if k!='id'}) for e in tx],calibration_node_ids=[n['id'] for n in refs],calibration_connection_ids=[e['id'] for e in rx],calibration_nodes=refs,calibration_connections=rx,reference_antenna_id='sgh',analyzer_category_id='sa-category',route_digest='a'*64)
    payload=request().model_dump();payload.update(chain_id=route.chain_id, mock_model='full_route_v1',receive_cable_loss_db=None,receive_cable_source=None)
    return FixedRouteResult(version=2,run_id=uuid4(),lab_profile_id=lab,request=payload,configuration={'route_selection':route.model_dump(mode='json'),'analyzer_binding':{'category_id':'sa-category'},'analyzer_instrument_id':'sa'})


@pytest.mark.parametrize('representation',['nodes','edges'])
async def test_model_requires_persisted_cable_then_deembeds_once(tmp_path,representation):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.database import Base
    from app.models.diagnostic_run import DiagnosticRun
    from app.services.calibration import fixed_route_simulation as model
    engine=create_engine('sqlite:///'+str(tmp_path/'model.db'))
    Base.metadata.create_all(engine)
    result=model_result() if representation=='nodes' else edge_model_result()
    with Session(engine) as db:
        model.prepare_model_record(db,result)
        record=result.receive_cable_calibration.model_dump()
        with Session(engine) as observer:
            assert observer.get(DiagnosticRun,record['run_id']) is not None
        assert result.request.receive_cable_loss_db is None
    await collector.collect_fixed_route(MockChannelEmulator('ce',{}),MockSignalAnalyzer('sa',{}),result,output_port=1,cancel=asyncio.Event())
    assert result.status=='simulated',result.error
    assert result.net_loss_db==pytest.approx(26.)
    assert result.samples[0].received_dbm==pytest.approx(-46.2)
    assert record['loss_db']==pytest.approx(.2)
    assert record['simulated'] is True
    assert result.cleanup_confirmed is None
    assert result.simulation_input_source=='model_synthetic'


@pytest.mark.parametrize('fault',['missing_air','frequency','analyzer','missing_value'])
def test_model_rejects_incomplete_identity_or_quantity(fault):
    from app.services.calibration import fixed_route_simulation as model
    result=model_result()
    route=result.configuration['route_selection']
    if fault=='missing_air': route['calibration_nodes'][0]['type']='pad'
    elif fault=='frequency': route['calibration_nodes'][2]['params']['simulation_model']['frequency_mhz']=3500.
    elif fault=='analyzer': result.configuration['analyzer_binding']['category_id']='another'
    else: route['nodes'][1]['params'].pop('simulation_model')
    with pytest.raises(ValueError): model.model_quantities(result.configuration,result.request)


@pytest.mark.parametrize('fault',['wrong_port','missing_frequency','reject_go','timeout','stop_not_confirmed','cancel'])
async def test_transport_faults_cannot_finish_as_success(monkeypatch,fault):
    from app.services.calibration.fixed_route_simulation import SimulatedRouteTransport
    original_write=SimulatedRouteTransport._write
    original_query=SimulatedRouteTransport._query
    cancel=asyncio.Event()
    async def write(self,command):
        if fault=='reject_go' and command=='DIAG:SIMU:GO': raise ValueError('模拟设备拒绝启动')
        await original_write(self,command)
        if fault=='missing_frequency' and command.startswith('OUTPut:INTERFerence:FREQuency:'): self.frequency_mhz=None
        if fault=='wrong_port' and command=='DIAG:SIMU:GO': self.output_port=2
        if fault=='stop_not_confirmed' and command=='DIAG:SIMU:STOP': self.state='RUNNING'
    async def query(self,command):
        if command.startswith('OUTPut:MEASure:RESult:'):
            if fault=='timeout': raise TimeoutError('模拟查询超时')
            if fault=='cancel': cancel.set()
        return await original_query(self,command)
    monkeypatch.setattr(SimulatedRouteTransport,'_write',write)
    monkeypatch.setattr(SimulatedRouteTransport,'_query',query)
    result=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),request=request(mock_input=mock_payload()),configuration={})
    await collector.collect_fixed_route(MockChannelEmulator('ce',{}),MockSignalAnalyzer('sa',{}),result,output_port=1,cancel=cancel)
    assert result.status in ('failed','cancelled','cleanup_unconfirmed')
    assert result.net_loss_db is None and result.sample_std_db is None
    assert result.cleanup_confirmed is None
    assert all(e.simulated for e in result.exchanges)
    if fault=='stop_not_confirmed':
        assert result.status=='cleanup_unconfirmed'
        assert not any(':REMove ' in e.command for e in result.exchanges)
    else: assert any(':REMove ' in e.command for e in result.exchanges)


@pytest.mark.parametrize('mixed',[False,True])
async def test_public_collector_rejects_real_and_mixed_without_io(mixed):
    ce,sa,writes,queries,_=instruments()
    if mixed: sa=MockSignalAnalyzer('sa',{})
    result=FixedRouteResult(run_id=uuid4(),lab_profile_id=uuid4(),request=request(),configuration={})
    await collector.collect_fixed_route(ce,sa,result,output_port=1,cancel=asyncio.Event())
    assert result.status=='failed' and result.net_loss_db is None
    assert writes==queries==result.exchanges==[]


@pytest.mark.parametrize('source',['request','result','cable'])
def test_model_provenance_survives_forged_completed_history(source):
    from app.services.calibration.fixed_route_evidence import check_fixed_route_evidence
    from app.services.calibration.fixed_route_jobs import record,build_record_row
    from app.schemas.fixed_route_acquisition import SimulatedReceiveCableRecord
    from datetime import datetime,timezone
    result=model_result()
    if source!='request': result.request.mock_model=None
    if source=='result': result.simulation_input_source='model_synthetic'
    if source=='cable':
        result.receive_cable_calibration=SimulatedReceiveCableRecord(run_id=uuid4(),lab_profile_id=result.lab_profile_id,
            cable_node_id='rx',frequency_mhz=2595.,input_reference_plane='rx:in',output_reference_plane='rx:out',
            source_power_dbm=-20.,received_power_dbm=-20.2,loss_db=.2,formula='synthetic observation')
    result.status='completed';result.cleanup_confirmed=True
    row=build_record_row(result);row.run_at=datetime.now(timezone.utc)
    restored=record(row)
    assert restored.status=='simulated' and restored.result.cleanup_confirmed is None
    assert check_fixed_route_evidence(result)[0]=='simulated'


def edge_model_result():
    result=model_result()
    route=result.configuration['route_selection']
    route['nodes']=[route['nodes'][i] for i in (0,2,4)]
    route['node_ids']=[n['id'] for n in route['nodes']]
    route['connections']=[dict(id='e-ce-pa',source='ce',target='pa',source_pin='out',target_pin='in',
        simulation_model={'frequency_mhz':2595.,'loss_db':1.}),
        dict(id=route['chain_id'],source='pa',target='probe',source_pin='out',target_pin='in',
        simulation_model={'frequency_mhz':2595.,'loss_db':2.})]
    route['connection_ids']=[e['id'] for e in route['connections']]
    route['ports']=[{k:v for k,v in e.items() if k not in ('id','simulation_model')}|{'connection_id':e['id']} for e in route['connections']]
    return result


def test_edge_cables_produce_identical_loss_without_nominal_fallback():
    from app.services.calibration.fixed_route_simulation import model_quantities
    result=edge_model_result()
    _,values,_=model_quantities(result.configuration,result.request)
    assert sum(values.values())==pytest.approx(26.2)
    # 同名标称值不参加合成计算。
    result.configuration['route_selection']['connections'][0]['cable_loss_db']=999.
    assert sum(model_quantities(result.configuration,result.request)[1].values())==pytest.approx(26.2)


@pytest.mark.parametrize('fault',['node_and_edge','missing_edge','mixed','reference_edge','extra_value','frequency'])
def test_model_rejects_mixed_or_duplicate_physical_segments(fault):
    from app.services.calibration.fixed_route_simulation import model_quantities
    result=model_result() if fault=='node_and_edge' else edge_model_result()
    route=result.configuration['route_selection']
    if fault=='node_and_edge':route['connections'][0]['simulation_model']={'frequency_mhz':2595.,'loss_db':1.}
    elif fault=='missing_edge':route['connections'][0].pop('simulation_model')
    elif fault=='mixed':route['nodes'][1]['type']='cable'
    elif fault=='reference_edge':route['calibration_connections'][2]['simulation_model']={'frequency_mhz':2595.,'loss_db':1.}
    elif fault=='extra_value':route['connections'][0]['simulation_model']['gain_db']=0.
    else:route['connections'][0]['simulation_model']['frequency_mhz']=3500.
    with pytest.raises(ValueError):model_quantities(result.configuration,result.request)


def test_connection_schema_preserves_model_without_backfilling_missing():
    from app.schemas.switch_topology import TopologyConnection
    edge=dict(id='e',source='ce',target='pa')
    assert 'simulation_model' not in TopologyConnection.model_validate(edge).model_dump(exclude_unset=True)
    edge['simulation_model']={'frequency_mhz':3500.,'loss_db':1.25}
    assert TopologyConnection.model_validate(edge).model_dump(exclude_unset=True)['simulation_model']==edge['simulation_model']
    for bad in (None,{'frequency_mhz':3500.,'loss_db':True},{'frequency_mhz':3500.,'loss_db':-1.},
                {'frequency_mhz':3500.,'gain_db':1.},{'frequency_mhz':3500.,'loss_db':1.,'extra':0.}):
        with pytest.raises(ValueError):TopologyConnection.model_validate(edge|{'simulation_model':bad})


def test_node_and_edge_identifiers_cannot_overwrite_physical_segment_values():
    from app.services.calibration.fixed_route_simulation import model_quantities
    result=edge_model_result();route=result.configuration['route_selection']
    replacement='connection:e-ce-pa'
    route['nodes'][1]['id']=replacement
    route['node_ids'][1]=replacement
    route['connections'][0]['target']=replacement;route['connections'][1]['source']=replacement
    route['ports'][0]['target']=replacement;route['ports'][1]['source']=replacement
    assert sum(model_quantities(result.configuration,result.request)[1].values())==pytest.approx(26.2)
