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


def legacy_bse_direct_topology(topology):
    # 旧正式解析允许 BSE→CE→probe；采集解析仍应拒绝 CE 入边，不能为修冻结而放宽它。
    nodes = copy.deepcopy(topology.nodes)
    for node in nodes:
        if node['type'] == 'ce_port':
            node['type'] = 'channel_emulator'
            node['params'] = {'ports': ['in', 'out'], 'ce_port': node['label']}
        else:
            node['params']['ports'] = ['in']
    nodes += [dict(id='bse', type='communication_tester', label='BSE',
        params={'ports': ['DL1'], 'port_roles': {'DL1': 'dl'}}),
        dict(id='unused', type='pad', label='断开衰减器', params={'ports': ['in', 'out']})]
    topology.nodes = nodes
    topology.connections = [dict(edge, source_pin='out', target_pin='in')
        for edge in topology.connections] + [dict(id='bse-feed', source='bse',
            source_pin='DL1', target='ce_b1', target_pin='in', modes=['mimo_ota'])]
    modes = copy.deepcopy(topology.operating_modes)
    modes[0]['active_connections'].append('bse-feed')
    topology.operating_modes = modes


def mixed_bse_pad_topology(topology, *, explicit):
    legacy_bse_direct_topology(topology)
    pad = dict(id='selected-pad', type='pad', label='选中衰减器', params={'ports': ['in', 'out']})
    if explicit:
        declared(pad)
    topology.nodes = [*topology.nodes, pad]
    topology.connections = [dict(edge, source='selected-pad')
        if edge['id'] == 'conn_p0h' else edge for edge in topology.connections] + [
        dict(id='pad-feed', source='ce_b2', source_pin='out', target='selected-pad',
            target_pin='in', modes=['mimo_ota'])]
    modes = copy.deepcopy(topology.operating_modes)
    modes[0]['active_connections'].append('pad-feed')
    topology.operating_modes = modes


@pytest.mark.asyncio
@pytest.mark.parametrize('provenance', ['real', 'simulated', 'unknown', 'missing'])
async def test_mixed_legacy_and_declared_routes_freeze_formal_identity_without_capture_qualification(
        client, configured, topology_two_chains, db_session, legacy, launch, provenance):
    from app.services.calibration.route_calibration import list_route_selections
    mixed_bse_pad_topology(topology_two_chains, explicit=True)
    if provenance == 'missing':
        db_session.delete(legacy)
    else:
        legacy.use_mock = {'real': False, 'simulated': True, 'unknown': None}[provenance]
    db_session.commit()
    with pytest.raises(ValueError, match='CE源端存在回接'):
        list_route_selections(db_session, configured.id, topology_two_chains.id, 'mimo_ota')
    first = await launch()
    frozen_before = read_execution_route_compensation(first)
    for execution in (first, await launch()):
        frozen = read_execution_route_compensation(execution)
        actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
        assert (frozen_route_identity_error(db_session, frozen),
            frozen_route_identity_error(db_session, frozen, resolved_topology=actual)) == (None, None)
        assert len(frozen['route_entries']) == len(actual.probe_bindings) == 2
        selected = next(row for row in frozen['route_entries'] if row['chain_id'] == 'conn_p0h')
        assert selected['execution_route_identity']['internal_paths'] == [
            {'node_id': 'selected-pad', 'from_port': 'in', 'to_port': 'out'}]
        assert all(row['route_digest'] is None for row in frozen['route_entries'])
        assert all(row['source_kind'] == ('legacy_certificate' if provenance == 'real' else 'unavailable')
            for row in frozen['route_entries'])
        assert all(source['source_kind'] != 'confirmed_route' for source in frozen['source_records'])
        verdict = evaluate_path_loss_preflight(db_session, execution,
            chamber_id=configured.chamber_config_id, frequency_mhz=2595, operating_mode='mimo_ota',
            precheck_strict_cal=True, channel_emulator_execution_mode='real')
        if provenance == 'real':
            assert verdict.blocker is None and verdict.application['status'] == 'applied'
            assert [row['value_db'] for row in frozen['route_entries']] == [20, 30]
        else:
            assert verdict.blocker is not None and verdict.applied_certificate is None
            assert all(row['value_db'] is None for row in frozen['route_entries'])
        assert read_execution_route_compensation(execution) == frozen
    nodes = copy.deepcopy(topology_two_chains.nodes)
    del next(row for row in nodes if row['id'] == 'selected-pad')['params']['internal_paths']
    saved = client.patch(f'/api/v1/switch-topologies/{topology_two_chains.id}',
        params={'lab_profile_id': str(configured.id)}, json={'nodes': nodes})
    assert saved.status_code == 200, saved.text
    changed_actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert frozen_route_identity_error(db_session, frozen_before) is not None
    assert frozen_route_identity_error(db_session, frozen_before, resolved_topology=changed_actual) is not None
    assert read_execution_route_compensation(first) == frozen_before


@pytest.mark.asyncio
@pytest.mark.parametrize('reference_kind', ['receive_cable', 'reference_antenna', 'scope'])
async def test_mixed_normal_route_cannot_gain_reference_segment_execution_qualification(
        client, configured, topology_two_chains, db_session, legacy, launch, reference_kind):
    mixed_bse_pad_topology(topology_two_chains, explicit=True)
    nodes = copy.deepcopy(topology_two_chains.nodes)
    selected = next(row for row in nodes if row['id'] == 'selected-pad')
    if reference_kind == 'scope':
        selected['params']['connection_scope'] = 'calibration'
    else:
        selected['type'] = reference_kind
    topology_two_chains.nodes = nodes
    db_session.commit()
    try:
        execution = await launch()
    except ValueError as exc:
        assert '校准参考接线' in str(exc)
    else:
        verdict = evaluate_path_loss_preflight(db_session, execution,
            chamber_id=configured.chamber_config_id, frequency_mhz=2595, operating_mode='mimo_ota',
            precheck_strict_cal=True, channel_emulator_execution_mode='real')
        assert verdict.blocker is not None and verdict.applied_certificate is None


@pytest.mark.asyncio
@pytest.mark.parametrize('declaration_target', ['unused', 'ce_b1'])
@pytest.mark.parametrize('use_mock', [False, True, None])
async def test_unrelated_internal_declaration_preserves_legacy_direct_freeze_and_preflight(
        client, configured, topology_two_chains, db_session, legacy, launch,
        declaration_target, use_mock):
    from app.services.calibration.route_calibration import list_route_selections
    legacy_bse_direct_topology(topology_two_chains)
    legacy.use_mock = use_mock
    db_session.commit()
    execution = await launch()
    frozen = read_execution_route_compensation(execution)
    before = copy.deepcopy(frozen)
    assert all(row['execution_route_identity'] is None for row in frozen['route_entries'])
    actual_before = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert frozen_route_identity_error(db_session, frozen) is None
    assert frozen_route_identity_error(db_session, frozen, resolved_topology=actual_before) is None

    nodes = copy.deepcopy(topology_two_chains.nodes)
    next(node for node in nodes if node['id'] == declaration_target)['params']['internal_paths'] = []
    saved = client.patch(f'/api/v1/switch-topologies/{topology_two_chains.id}',
        params={'lab_profile_id': str(configured.id)}, json={'nodes': nodes})
    assert saved.status_code == 200, saved.text
    with pytest.raises(ValueError, match='CE源端存在回接'):
        list_route_selections(db_session, configured.id, topology_two_chains.id, 'mimo_ota')
    actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert actual.probe_bindings == actual_before.probe_bindings
    assert frozen_route_identity_error(db_session, frozen, resolved_topology=actual) is None
    assert frozen_route_identity_error(db_session, frozen) is None
    fresh = await launch()
    assert frozen_route_identity_error(db_session, read_execution_route_compensation(fresh)) is None
    for candidate in (execution, fresh):
        verdict = evaluate_path_loss_preflight(db_session, candidate,
            chamber_id=configured.chamber_config_id, frequency_mhz=2595, operating_mode='mimo_ota',
            precheck_strict_cal=True, channel_emulator_execution_mode='real')
        if use_mock is False:
            assert verdict.blocker is None
            assert verdict.application['status'] == 'applied'
            assert verdict.applied_certificate.path_loss_db_by_rf_chain['conn_p0v']['total_insertion_loss_db'] == 20
        else:
            assert verdict.blocker is not None
            assert verdict.application['provenance'] == ('simulated' if use_mock else 'unknown')
            assert verdict.applied_certificate is None
            assert all(row['value_db'] is None for row in verdict.route_compensation['route_entries'])
    assert read_execution_route_compensation(execution) == before


@pytest.mark.asyncio
async def test_absent_frozen_identity_rejects_new_selected_internal_identity_on_both_sides(
        client, configured, topology_two_chains, db_session, legacy, launch):
    mixed_bse_pad_topology(topology_two_chains, explicit=False)
    db_session.commit()
    execution = await launch()
    frozen = read_execution_route_compensation(execution)
    before = copy.deepcopy(frozen)
    assert all(row['execution_route_identity'] is None for row in frozen['route_entries'])
    assert frozen_route_identity_error(db_session, frozen) is None
    nodes = copy.deepcopy(topology_two_chains.nodes)
    declared(next(node for node in nodes if node['id'] == 'selected-pad'))
    saved = client.patch(f'/api/v1/switch-topologies/{topology_two_chains.id}',
        params={'lab_profile_id': str(configured.id)}, json={'nodes': nodes})
    assert saved.status_code == 200, saved.text
    actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert next(row for row in actual.probe_bindings if row.connection_id == 'conn_p0h').execution_route_identity[
        'internal_paths'] == [{'node_id': 'selected-pad', 'from_port': 'in', 'to_port': 'out'}]
    assert frozen_route_identity_error(db_session, frozen) is not None
    assert frozen_route_identity_error(db_session, frozen, resolved_topology=actual) is not None
    verdict = evaluate_path_loss_preflight(db_session, execution,
        chamber_id=configured.chamber_config_id, frequency_mhz=2595, operating_mode='mimo_ota',
        precheck_strict_cal=True, channel_emulator_execution_mode='real')
    assert verdict.blocker is not None and verdict.applied_certificate is None
    assert verdict.application['reason'] == 'route_identity_mismatch'
    assert read_execution_route_compensation(execution) == before


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
