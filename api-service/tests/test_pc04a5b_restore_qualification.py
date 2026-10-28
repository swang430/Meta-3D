"""实际恢复API之后，沿现有confirmed/current/freeze门，不新造采用规则。"""
import copy
import pytest
from sqlalchemy import text
from tests.test_pc04a2_route_application import db_session, payload, confirm
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured
from tests.test_pc04a2_route_eligibility import real_capture
from tests.test_pc04a2_route_freeze import legacy, launch, entries


def records(db):
    return {table: sorted(str(tuple(row)) for row in db.execute(text(f'SELECT * FROM {table}')))
        for table in ('route_calibration_applications', 'route_calibration_selections',
                      'probe_path_loss_calibrations', 'diagnostic_runs')}


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['normal', 'reference'])
async def test_restore_preserves_confirmed_once_and_changed_identity_rejected(client, configured,
        real_capture, legacy, launch, db_session, topology_two_chains, location):
    from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation, frozen_route_identity_error
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation
    from app.services.calibration.route_calibration import list_route_selections
    topology = topology_two_chains
    # 复用4d普通/参考路径的真实模型；所有新增声明显式合法。
    topology.nodes = [*topology.nodes, dict(id='wire', type='cable', label='线缆', params={
        'ports':['in','out'], 'port_directions':{'in':'input','out':'output'},
        'internal_paths':[{'from_port':'in','to_port':'out'}]})]
    topology.nodes = [{**n, 'params':{**n.get('params',{}), 'ports':['out','other']}}
        if n['id']=='ce_b1' else n for n in topology.nodes]
    topology.connections = [dict(id='owner', source='ce_b1', source_pin='out', target='wire', target_pin='in', cable_loss_db=2),
        *[{**edge, **({'source':'wire', 'source_pin':'out', 'cable_loss_db':2, 'calibrated_loss_db':99}
            if edge['id']=='conn_p0v' else {})} for edge in topology.connections]]
    topology.operating_modes = [{**m, 'name':m.get('name','普通'), 'active_connections':['owner', *m['active_connections']]}
        for m in topology.operating_modes]
    if location == 'reference':
        topology.nodes = [{**n, 'params':{**n.get('params',{}),
            **({'ports':['in','ref'], 'port_directions':{'in':'input','ref':'output'}} if n['id']=='probe_0_v' else {})}}
            for n in topology.nodes]
        topology.nodes = [*topology.nodes,
            dict(id='receive', type='receive_cable', label='接收线缆', params={'connection_scope':'calibration',
                'ports':['in','out'], 'port_directions':{'in':'input','out':'output'},
                'internal_paths':[{'from_port':'in','to_port':'out'}]}),
            dict(id='sa', type='signal_analyzer', label='SA', params={'connection_scope':'calibration',
                'ports':['in'], 'port_directions':{'in':'input'}})]
        topology.connections = [*topology.connections,
            dict(id='r1', source='probe_0_v', source_pin='ref', target='receive', target_pin='in', cable_loss_db=2),
            dict(id='r2', source='receive', source_pin='out', target='sa', target_pin='in', cable_loss_db=2)]
        topology.operating_modes = [*topology.operating_modes, dict(id='calibration',name='参考',active_connections=['r1','r2'])]
    db_session.commit()
    run = real_capture()
    assert confirm(client, configured, payload(client, configured, run)).status_code == 201
    first = await launch()
    frozen = copy.deepcopy(first.config['route_calibration_freeze'])
    assert entries(first)['conn_p0v']['value_db'] == 28
    url = f'/api/v1/switch-topologies/{topology.id}'
    params = {'lab_profile_id':str(configured.id)}
    saved = client.patch(url, params=params, json={'name':'误保存', 'expected_revision':0})
    assert saved.status_code == 200, saved.text
    before = records(db_session)
    result = client.post(url+'/restore', params=params, json={'revision':0,'expected_revision':1})
    assert result.status_code == 200, result.text
    db_session.refresh(topology)
    assert next(e for e in topology.connections if e['id']=='conn_p0v')['calibrated_loss_db'] is None
    assert records(db_session) == before
    assert read_execution_route_compensation(first) == frozen
    current = list_route_selections(db_session, configured.id, topology.id, 'mimo_ota')
    assert any(s.chain_id=='conn_p0v' for s in current)
    second = await launch()
    assert entries(second)['conn_p0v']['source_kind'] == 'confirmed_route'
    assert entries(second)['conn_p0v']['value_db'] == 28  # 不再加标称4或内嵌99
    assert frozen_route_identity_error(db_session, frozen) is None
    # 将确实改变身份的历史保存，再恢复它；当前与旧freeze均拒旧匹配。
    topology.connections = [{**edge, **({'source_pin':'other'} if edge['id']=='owner' else {})}
        for edge in topology.connections]
    db_session.commit()
    assert client.patch(url, params=params, json={'name':'改变身份', 'expected_revision':2}).status_code == 200
    reverted = client.post(url+'/restore', params=params, json={'revision':0,'expected_revision':3})
    assert reverted.status_code == 200, reverted.text
    before_change = records(db_session)
    changed = client.post(url+'/restore', params=params, json={'revision':3,'expected_revision':4})
    assert changed.status_code == 200, changed.text
    assert records(db_session) == before_change
    assert frozen_route_identity_error(db_session, frozen) is not None
    current = resolve_effective_route_compensation(db_session, configured.id, 'mimo_ota', 2595)
    assert next((r for r in current['route_entries'] if r['chain_id']=='conn_p0v'), {}).get('source_kind') != 'confirmed_route'
    third = await launch()
    assert entries(third).get('conn_p0v',{}).get('source_kind') != 'confirmed_route'
    assert read_execution_route_compensation(first) == frozen
