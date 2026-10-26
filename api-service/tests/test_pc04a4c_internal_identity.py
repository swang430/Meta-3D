"""真实执行 builder/preflight 与 actual-target 核对内部穿越，不改历史。"""
import copy

import pytest

from tests.test_pc04a2_route_freeze import (
    db_session, chamber, topology_two_chains, lab_profile, client, configured, launch,
    real_capture, legacy, confirm, payload)
from tests.test_pc04a4c_internal_routes import declared
from app.services.mimo_ota.route_calibration_freeze import (
    read_execution_route_compensation, frozen_route_identity_error)
from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
from app.services.mimo_ota.path_loss_preflight import evaluate_path_loss_preflight


def insert_pad(topology, *, explicit):
    pad = dict(id='pad', type='pad', label='衰减器', params={'ports': ['in', 'out']})
    if explicit:
        declared(pad)
    topology.nodes = [*copy.deepcopy(topology.nodes), pad]
    topology.connections = [{**edge, 'source': 'pad', 'source_pin': 'out'}
        if edge['id'] == 'conn_p0v' else edge for edge in topology.connections] + [
        dict(id='feed', source='ce_b1', source_pin='out', target='pad', target_pin='in', modes=['mimo_ota'])]
    modes = copy.deepcopy(topology.operating_modes)
    modes[0]['active_connections'].append('feed')
    topology.operating_modes = modes


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['add', 'delete', 'empty', 'reverse', 'port'])
async def test_current_internal_change_rejects_old_freeze_without_switch(
        client, configured, topology_two_chains, db_session, legacy, launch, change):
    insert_pad(topology_two_chains, explicit=change != 'add')
    db_session.commit()
    execution = await launch()
    frozen = read_execution_route_compensation(execution)
    before = copy.deepcopy(frozen)
    actual_before = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert frozen_route_identity_error(db_session, frozen, resolved_topology=actual_before) is None
    nodes, edges = copy.deepcopy(topology_two_chains.nodes), copy.deepcopy(topology_two_chains.connections)
    pad = next(node for node in nodes if node['id'] == 'pad')
    if change == 'add':
        declared(pad)
    elif change == 'delete':
        del pad['params']['internal_paths']
    elif change == 'empty':
        pad['params']['internal_paths'] = []
    elif change == 'reverse':
        pad['params']['internal_paths'] = [{'from_port': 'out', 'to_port': 'in'}]
    else:
        pad['params'].update(ports=['new', 'out'], port_directions={'new': 'input', 'out': 'output'},
            internal_paths=[{'from_port': 'new', 'to_port': 'out'}])
        next(edge for edge in edges if edge['id'] == 'feed')['target_pin'] = 'new'
    topology_two_chains.nodes, topology_two_chains.connections = nodes, edges
    db_session.commit()
    assert frozen_route_identity_error(db_session, frozen)
    try:
        actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    except ValueError:
        assert change in ('empty', 'reverse')
    else:
        assert frozen_route_identity_error(db_session, frozen, resolved_topology=actual)
    verdict = evaluate_path_loss_preflight(db_session, execution, chamber_id=configured.chamber_config_id,
        frequency_mhz=2595, operating_mode='mimo_ota', precheck_strict_cal=True,
        channel_emulator_execution_mode='real')
    assert verdict.blocker is not None
    assert verdict.application['status'] == 'not_applied'
    assert read_execution_route_compensation(execution) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('explicit', [True, False])
async def test_confirmed_source_history_projects_own_internal_snapshot_only(
        client, configured, topology_two_chains, db_session, legacy, launch, real_capture, explicit):
    insert_pad(topology_two_chains, explicit=explicit)
    db_session.commit()
    run = real_capture()
    response = confirm(client, configured, payload(client, configured, run))
    assert response.status_code == 201, response.text
    execution = await launch()
    frozen = read_execution_route_compensation(execution)
    entry = next(row for row in frozen['route_entries'] if row['chain_id'] == 'conn_p0v')
    assert entry['source_kind'] == 'confirmed_route'
    assert entry['value_db'] == 28
    if explicit:
        assert entry['execution_route_identity']['internal_paths'] == [
            {'node_id': 'pad', 'from_port': 'in', 'to_port': 'out'}]
    else:
        assert 'internal_paths' not in entry['execution_route_identity']
    topology_two_chains.nodes = []
    topology_two_chains.connections = []
    db_session.commit()
    assert read_execution_route_compensation(execution) == frozen


@pytest.mark.asyncio
async def test_unselected_pair_changes_route_digest_not_actual_execution_identity(
        client, configured, topology_two_chains, db_session, legacy, launch):
    from app.services.calibration.route_calibration import list_route_selections
    insert_pad(topology_two_chains, explicit=True)
    nodes = copy.deepcopy(topology_two_chains.nodes)
    next(n for n in nodes if n['id'] == 'pad')['params']['port_directions'] = {
        'in': 'bidirectional', 'out': 'bidirectional'}
    topology_two_chains.nodes = nodes
    db_session.commit()
    before = next(row for row in list_route_selections(db_session, configured.id, topology_two_chains.id, 'mimo_ota')
                  if row.chain_id == 'conn_p0v')
    execution = await launch()
    frozen = read_execution_route_compensation(execution)
    nodes = copy.deepcopy(topology_two_chains.nodes)
    next(n for n in nodes if n['id'] == 'pad')['params']['internal_paths'].append(
        {'from_port': 'out', 'to_port': 'in'})
    topology_two_chains.nodes = nodes
    db_session.commit()
    after = next(row for row in list_route_selections(db_session, configured.id, topology_two_chains.id, 'mimo_ota')
                 if row.chain_id == 'conn_p0v')
    assert after.route_digest != before.route_digest
    assert frozen_route_identity_error(db_session, frozen) is None
    actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert frozen_route_identity_error(db_session, frozen, resolved_topology=actual) is None


def test_identity_projects_selected_pairs_not_unselected_rows_or_current_validation():
    from app.services.declared_rf_routes import rf_execution_identity
    nodes = [{'id': 'ce', 'type': 'ce_port'}, {'id': 'comb', 'type': 'combiner',
        'params': {'internal_paths': [{'from_port': 'A', 'to_port': 'Z'}]}},
        {'id': 'p', 'type': 'probe'}]
    edges = [dict(id='i', source='ce', target='comb', source_pin='out', target_pin='A'),
        dict(id='o', source='comb', target='p', source_pin='Z', target_pin='in')]
    first = rf_execution_identity(nodes, edges)
    assert first['internal_paths'] == [{'node_id': 'comb', 'from_port': 'A', 'to_port': 'Z'}]
    nodes[1]['params']['internal_paths'].append({'from_port': 'B', 'to_port': 'Z'})
    assert rf_execution_identity(nodes, edges) == first
    # 历史自身只做身份投影，不因新运行严验、旧方向缺失或坏声明而拒绝读取。
    nodes[1]['params']['internal_paths'] = []
    assert rf_execution_identity(nodes, edges) == first
    del nodes[1]['params']['internal_paths']
    assert 'internal_paths' not in rf_execution_identity(nodes, edges)
