"""PC04A2 Task1：真实HTTP/数据库路径选择及冻结，仅外部仪器Mock。"""
import copy
from uuid import UUID, uuid4

import pytest

from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured, finish, start
from app.models.lab_profile import LabProfile
from app.models.diagnostic_run import DiagnosticRun


@pytest.fixture
def graph(db_session, topology_two_chains):
    topology_two_chains.nodes = [
        {'id':'ce1','type':'ce_port','label':'B1.1','params':{}},
        {'id':'pad1','type':'pad','label':'不是F64端口','params':{'ports':['in','out']}},
        {'id':'probe1v','type':'probe','label':'探头','params':{'probe_id':1,'polarization':'V'}},
        {'id':'reference1','type':'reference_antenna','label':'参考天线','params':{'connection_scope':'calibration','serial':'REF1'}},
        {'id':'rx-cable1','type':'receive_cable','label':'接收线','params':{'connection_scope':'calibration','source':'2595MHz记录'}},
        {'id':'sa1','type':'signal_analyzer','label':'分析仪','params':{'connection_scope':'calibration'}},
    ]
    topology_two_chains.connections = [
        {'id':'ce-pad','source':'ce1','target':'pad1','source_pin':'out','target_pin':'in'},
        {'id':'pad-probe','source':'pad1','target':'probe1v','source_pin':'out','target_pin':'in'},
        {'id':'probe-reference','source':'probe1v','target':'reference1'},
        {'id':'reference-cable','source':'reference1','target':'rx-cable1'},
        {'id':'cable-sa','source':'rx-cable1','target':'sa1'},
    ]
    topology_two_chains.operating_modes = [
        {'id':'mimo_ota','name':'正常','active_connections':['ce-pad','pad-probe']},
        {'id':'calibration','name':'校准','active_connections':['probe-reference','reference-cable','cable-sa']},
    ]
    db_session.commit()
    return topology_two_chains


def paths(client, lab, graph, **params):
    return client.get(f'/api/v1/lab-profiles/{lab.id}/route-calibration-paths', params={
        'topology_id':str(graph.id),'operating_mode':'mimo_ota',**params})


def test_passive_hops_and_calibration_references_remain_separate(client, configured, graph):
    response=paths(client, configured, graph)
    assert response.status_code == 200, response.text
    route=response.json()[0]
    assert route['node_ids'] == ['ce1','pad1','probe1v']
    assert route['connection_ids'] == ['ce-pad','pad-probe']
    assert route['chain_id'] == 'pad-probe'
    assert route['ce_port'] == 'B1.1'
    assert route['probe_id'] == 1 and route['polarization'] == 'V'
    assert route['calibration_node_ids'] == ['reference1','rx-cable1','sa1']
    assert route['calibration_connection_ids'] == ['probe-reference','reference-cable','cable-sa']
    assert route['calibration_nodes'][0]['params']['serial'] == 'REF1'


@pytest.mark.parametrize('failure', ['branch','cycle','unknown_ce'])
def test_ambiguous_or_unknown_paths_are_rejected(client, configured, graph, db_session, failure):
    nodes,connections,modes=copy.deepcopy(graph.nodes),copy.deepcopy(graph.connections),copy.deepcopy(graph.operating_modes)
    if failure=='branch':
        connections.append({'id':'shortcut','source':'ce1','target':'probe1v'})
        modes[0]['active_connections'].append('shortcut')
    elif failure=='cycle':
        connections.append({'id':'loop','source':'pad1','target':'ce1'})
        modes[0]['active_connections'].append('loop')
    else:
        nodes[0]['label']='unknown'
    graph.nodes,graph.connections,graph.operating_modes=nodes,connections,modes
    db_session.commit()
    response=paths(client, configured, graph)
    assert response.status_code == 422, response.text
    assert db_session.query(DiagnosticRun).count() == 0


def test_cross_lab_topology_is_conflict_and_does_not_start_a_job(client, configured, graph, db_session):
    other=LabProfile(name='另一实验室',chamber_config_id=uuid4(),is_active=True)
    db_session.add(other);db_session.commit()
    response=paths(client,other,graph)
    assert response.status_code == 409, response.text
    assert db_session.query(DiagnosticRun).count() == 0


def test_selected_digest_is_checked_and_complete_snapshot_survives_later_edits(client, configured, graph, db_session):
    response=paths(client,configured,graph)
    assert response.status_code == 200, response.text
    selection=response.json()[0]
    payload=dict(chain_id=selection['chain_id'],topology_id=str(graph.id),route_digest=selection['route_digest'],
        configuration_digest=selection['configuration_digest'],frequency_mhz=2595,requested_power_dbm=-20,
        reference_antenna='REF1 中心V',receive_cable_loss_db=2,receive_cable_source='2595MHz记录',
        fixed_route_confirmed=True,safety_confirmed=True,sample_count=2)
    base=f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions'
    bad=client.post(base,json={**payload,'route_digest':'0'*64})
    assert bad.status_code==422, bad.text
    assert db_session.query(DiagnosticRun).count()==0
    started=client.post(base,json=payload)
    assert started.status_code==202,started.text
    value=finish(client,configured,started.json()['run_id'])
    assert value['result']['version']==2
    frozen=copy.deepcopy(value['result']['configuration']['route_selection'])
    assert frozen['connection_ids']==['ce-pad','pad-probe']
    assert frozen['calibration_nodes'][0]['params']['serial']=='REF1'
    graph.nodes=[];graph.connections=[];graph.operating_modes=[];db_session.commit()
    historical=client.get(base+'/'+started.json()['run_id']).json()
    assert historical['result']['configuration']['route_selection']==frozen
    assert historical['result']['formal_eligible'] is False


def test_legacy_request_still_freezes_a_unique_complete_version2_route(client, configured, graph):
    response=start(client,configured,chain_id='pad-probe')
    assert response.status_code==202,response.text
    value=finish(client,configured,response.json()['run_id'])
    assert value['result']['version']==2
    assert value['result']['configuration']['route_selection']['node_ids']==['ce1','pad1','probe1v']
    assert value['result']['configuration']['chain']['ce_port']=='B1.1'


def test_legacy_request_does_not_allow_ambiguous_path(client, configured, graph, db_session):
    # 先取合法图摘要，再制造歧义；正式集合现在会在普通scope读取时提前拒绝。
    digest=client.get(f'/api/v1/lab-profiles/{configured.id}/calibration-scope').json()['digest']
    graph.connections=[*graph.connections,{'id':'shortcut','source':'ce1','target':'probe1v'}]
    modes=copy.deepcopy(graph.operating_modes);modes[0]['active_connections'].append('shortcut')
    graph.operating_modes=modes;db_session.commit()
    scope=client.get(f'/api/v1/lab-profiles/{configured.id}/calibration-scope')
    assert scope.status_code==422,scope.text
    response=client.post(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions',json=dict(
        chain_id='pad-probe',configuration_digest=digest,frequency_mhz=2595,requested_power_dbm=-20,
        reference_antenna='REF V中心',receive_cable_loss_db=2,receive_cable_source='2595MHz记录',
        fixed_route_confirmed=True,safety_confirmed=True,sample_count=2))
    assert response.status_code==422,response.text
    assert db_session.query(DiagnosticRun).count()==0


def test_legacy_request_rechecks_same_reference_selection_before_lease(client, configured, graph, db_session, monkeypatch):
    from contextlib import asynccontextmanager
    from app.services.calibration import fixed_route_jobs as jobs
    from app.models.switch_topology import SwitchTopology
    original=jobs.instrument_test_lease
    @asynccontextmanager
    async def changed_before_remote(*args,**kwargs):
        with jobs.SessionLocal() as db:
            row=db.get(SwitchTopology,graph.id)
            nodes=copy.deepcopy(row.nodes);nodes[3]['params']['serial']='REF2'
            row.nodes=nodes;db.commit()
        async with original(*args,**kwargs) as lease:
            yield lease
    monkeypatch.setattr(jobs,'instrument_test_lease',changed_before_remote)
    response=start(client,configured,chain_id='pad-probe')
    assert response.status_code==202,response.text
    value=finish(client,configured,response.json()['run_id'])
    assert value['status']=='failed',value
    assert value['result']['exchanges']==[]
    assert value['result']['configuration']['route_selection']['calibration_nodes'][0]['params']['serial']=='REF1'


def test_corrupt_version2_history_is_incomplete_not_backfilled(client, configured, graph, db_session):
    response=start(client,configured,chain_id='pad-probe')
    value=finish(client,configured,response.json()['run_id'])
    row=db_session.get(DiagnosticRun, UUID(value['run_id']))
    envelope=copy.deepcopy(row.sequence_evidence)
    del envelope['extra']['fixed_route_acquisition']['configuration']['route_selection']
    row.sequence_evidence=envelope;db_session.commit()
    history=client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{row.id}').json()
    assert history['status']=='incomplete'
    assert history['result'] is None


def test_explicit_ce_port_wins_over_intermediate_labels_and_positions_do_not_change_digest(client, configured, graph, db_session):
    graph.connections=[{**edge,**({'ce_port':'B3'} if edge['id']=='pad-probe' else {})} for edge in graph.connections]
    db_session.commit()
    before=paths(client,configured,graph).json()[0]
    assert before['ce_port']=='B3'
    graph.nodes=[{**node,'position':{'x':900,'y':800},'label':'显示名称' if node['id']=='pad1' else node['label']} for node in graph.nodes]
    db_session.commit()
    after=paths(client,configured,graph).json()[0]
    assert after['route_digest']==before['route_digest']


def test_one_f64_output_cannot_silently_feed_two_selected_routes(client, configured, graph, db_session):
    nodes=copy.deepcopy(graph.nodes)
    nodes[0]['type']='channel_emulator';nodes[0]['params']={'ce_port':'1'}
    nodes.append({'id':'probe2','type':'probe','label':'另一探头','params':{'probe_id':2,'polarization':'V'}})
    graph.nodes=nodes
    graph.connections=[*graph.connections,{'id':'second','source':'ce1','target':'probe2'}]
    modes=copy.deepcopy(graph.operating_modes);modes[0]['active_connections'].append('second')
    graph.operating_modes=modes;db_session.commit()
    response=paths(client,configured,graph)
    assert response.status_code==422,response.text


def test_version1_history_remains_read_only_without_current_route_backfill(client, configured, graph, db_session):
    from app.schemas.fixed_route_acquisition import FixedRouteResult
    from tests.test_pc_04a_fixed_route_acquisition import request
    from app.services.calibration import fixed_route_jobs as jobs
    run_id=uuid4()
    value=FixedRouteResult(run_id=run_id,lab_profile_id=configured.id,request=request(),configuration={'old_marker':'原始快照'},status='simulated')
    row=DiagnosticRun(id=run_id,kind='scpi_sequence',lab_profile_id=configured.id,target_name=jobs.TARGET,
        success=True,sequence_evidence=jobs._sequence_evidence(value))
    db_session.add(row);db_session.commit()
    history=client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}').json()
    assert history['result']['version']==1
    assert history['result']['configuration']=={'old_marker':'原始快照'}


@pytest.mark.parametrize('failure',['cycle','branch','back_to_probe'])
def test_reference_segment_rejects_cycles_and_nonunique_wiring(client, configured, graph, db_session, failure):
    edge={'id':'bad-reference','source':'rx-cable1','target':'reference1'}
    if failure=='branch':
        edge={'id':'bad-reference','source':'reference1','target':'sa1'}
    elif failure=='back_to_probe':
        edge={'id':'bad-reference','source':'sa1','target':'probe1v'}
    graph.connections=[*graph.connections,edge]
    modes=copy.deepcopy(graph.operating_modes);modes[1]['active_connections'].append(edge['id'])
    graph.operating_modes=modes;db_session.commit()
    response=paths(client,configured,graph)
    assert response.status_code==422,response.text
    assert start(client,configured,chain_id='pad-probe').status_code==422
    assert db_session.query(DiagnosticRun).count()==0


@pytest.mark.parametrize('failure',['empty','node_order','port_endpoint','edge_endpoint'])
def test_inconsistent_version2_history_is_incomplete_without_returning_loss(client, configured, graph, db_session, failure):
    response=start(client,configured,chain_id='pad-probe')
    value=finish(client,configured,response.json()['run_id'])
    row=db_session.get(DiagnosticRun,UUID(value['run_id']))
    envelope=copy.deepcopy(row.sequence_evidence)
    result=envelope['extra']['fixed_route_acquisition']
    result['status']='completed';result['net_loss_db']=23.0
    route=result['configuration']['route_selection']
    if failure=='empty':
        for key in ('node_ids','connection_ids','ports','nodes','connections'):route[key]=[]
    elif failure=='node_order':
        route['node_ids']=list(reversed(route['node_ids']))
    elif failure=='port_endpoint':
        route['ports'][0]['target']='probe1v'
    else:
        route['connections'][0]['source']='pad1'
    row.sequence_evidence=envelope;db_session.commit()
    history=client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{row.id}').json()
    assert history['status']=='incomplete',history
    assert history['result'] is None
