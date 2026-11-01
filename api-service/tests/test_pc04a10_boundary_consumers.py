"""源端边界经真实HTTP、正式解析、scope、冻结、批计划消费；仅仪器Mock。"""
import copy

import pytest

from tests.test_pc04a2_route_selection import (
    client, configured, graph, db_session, chamber, topology_two_chains, lab_profile, paths,
)
from tests.test_pc04a10_source_boundary import boundary_graph, edge
from tests.test_pc06a1_batch_plan import request_for, shared_switch


def save_boundary(graph, db, *, explicit=False, pa=False, ce_type='ce_port'):
    nodes, edges = boundary_graph(explicit=explicit, pa=pa, ce_type=ce_type)
    # 参考测量段沿用独立out端；不能让不相关的结构缺项遮蔽本片源端门。
    nodes[1]['params']['ports'].append('out')
    nodes[1]['params']['port_directions']['out'] = 'output'
    reference_nodes = copy.deepcopy(graph.nodes[3:])
    reference_edges = copy.deepcopy(graph.connections[2:])
    reference_edges[0]['source'] = 'p'
    graph.nodes, graph.connections = nodes + reference_nodes, edges + reference_edges
    graph.operating_modes = [dict(id='mimo_ota', name='正常', active_connections=[e['id'] for e in edges]),
        dict(id='calibration', name='校准', active_connections=[e['id'] for e in reference_edges])]
    db.commit()
    return graph


@pytest.mark.parametrize('explicit', [False, True])
@pytest.mark.parametrize('pa', [False, True])
@pytest.mark.parametrize('ce_type', ['ce_port', 'channel_emulator'])
def test_legal_input_reaches_http_scope_batch_and_formal_freeze_without_upstream_loss(
        client, configured, graph, db_session, explicit, pa, ce_type):
    from app.services.calibration.route_calibration import resolve_explicit_route_selection
    from app.services.calibration.configuration_scope import build_selected_route_calibration_scope
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.services.calibration.rf_chain_resolver import resolve_rf_chains
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    from app.services.mimo_ota.route_calibration_freeze import (
        resolve_effective_route_compensation, frozen_route_identity_error,
    )
    save_boundary(graph, db_session, explicit=explicit, pa=pa, ce_type=ce_type)
    expected = ['ce-pa', 'terminal'] if pa else ['terminal']
    before = copy.deepcopy((graph.nodes, graph.connections, graph.operating_modes))
    for selection_scope in ('individual', 'simultaneous'):
        response = paths(client, configured, graph, selection_scope=selection_scope)
        assert response.status_code == 200, response.text
        route = response.json()[0]
        assert route['connection_ids'] == expected
        assert route['calibration_connection_ids'] == ['probe-reference', 'reference-cable', 'cable-sa']
    selected = resolve_explicit_route_selection(db_session, configured.id, graph.id, 'mimo_ota', 'terminal', expected)
    assert selected.connection_ids == expected
    scope = build_selected_route_calibration_scope(db_session, configured.id, 'mimo_ota',
        topology_id=graph.id, chain_id='terminal')
    assert scope.configuration_complete, scope.warnings
    plan = build_batch_plan(db_session, configured.id, request_for(graph, chains=('terminal',), frequencies=(2595.,)), None)
    assert plan.items[0].route_selection.connection_ids == expected
    actual = orchestrate_switch_topology(db_session, configured.chamber_config_id)
    assert actual.success and len(actual.probe_bindings) == 1
    assert actual.probe_bindings[0].cable_loss_db is None
    assert resolve_rf_chains(db_session, configured.id).chains[0].chain_id == 'terminal'
    frozen = resolve_effective_route_compensation(db_session, configured.id, 'mimo_ota', 2595.)
    assert frozen_route_identity_error(db_session, frozen, resolved_topology=actual) is None
    assert frozen['route_entries'][0]['value_db'] is None  # 路径可读不制造confirmed补偿。
    assert (graph.nodes, graph.connections, graph.operating_modes) == before


@pytest.mark.parametrize('selection_scope', ['individual', 'simultaneous'])
def test_http_unknown_input_reports_mode_pin_and_connection_not_empty_success(
        client, configured, graph, db_session, selection_scope):
    save_boundary(graph, db_session)
    nodes = copy.deepcopy(graph.nodes)
    nodes[0]['params']['port_directions'].pop('input1')
    graph.nodes = nodes; db_session.commit()
    response = paths(client, configured, graph, selection_scope=selection_scope)
    assert response.status_code == 422, response.text
    detail = response.json()['detail']
    assert all(token in detail for token in ('mimo_ota', 'feed', 'ce.input1', '声明'))


def test_wrong_boundary_blocks_acquisition_before_job_or_instrument_io(client, configured, graph, db_session):
    from app.models.diagnostic_run import DiagnosticRun
    from tests.test_pc04a4b_port_identity import acquisition_payload
    save_boundary(graph, db_session)
    response = paths(client, configured, graph)
    assert response.status_code == 200, response.text
    payload = acquisition_payload(response.json()[0], graph)
    edges = copy.deepcopy(graph.connections)
    next(e for e in edges if e['id'] == 'feed')['target_pin'] = 'B1.1'
    graph.connections = edges; db_session.commit()
    started = client.post(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions', json=payload)
    assert started.status_code == 422, started.text
    assert db_session.query(DiagnosticRun).count() == 0


def test_bad_edge_only_in_other_mode_does_not_expand_current_boundary(client, configured, graph, db_session):
    save_boundary(graph, db_session)
    graph.connections = [*graph.connections, edge('other-mode-bad', 'p', 'missing', 'ce', 'B1.1')]
    graph.operating_modes = [*graph.operating_modes,
        dict(id='other', name='其他模式', active_connections=['other-mode-bad'])]
    db_session.commit()
    response = paths(client, configured, graph)
    assert response.status_code == 200, response.text
    assert response.json()[0]['connection_ids'] == ['terminal']


@pytest.mark.parametrize('explicit', [False, True])
def test_formal_rejection_also_names_current_mode(configured, graph, db_session, explicit):
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    save_boundary(graph, db_session, explicit=explicit)
    nodes = copy.deepcopy(graph.nodes)
    nodes[0]['params']['port_directions'].pop('input1')
    graph.nodes = nodes; db_session.commit()
    with pytest.raises(ValueError, match='mimo_ota.*feed.*ce.input1'):
        orchestrate_switch_topology(db_session, configured.chamber_config_id)


def test_structural_draft_save_is_not_promoted_to_complete_mode_runtime_gate(client, configured, graph, db_session):
    from tests.topology_revision_requests import saved_revision
    save_boundary(graph, db_session, explicit=True)
    nodes = copy.deepcopy(graph.nodes)
    nodes[0]['params']['port_directions'].pop('input1')
    url = f'/api/v1/switch-topologies/{graph.id}'
    scope = {'lab_profile_id': str(configured.id)}
    saved = client.patch(url, params=scope, json=dict(nodes=nodes,
        expected_revision=saved_revision(client, url, scope)))
    assert saved.status_code == 200, saved.text
    db_session.refresh(graph)
    assert graph.nodes == nodes
    runtime = paths(client, configured, graph)
    assert runtime.status_code == 422, runtime.text
    assert 'ce.input1' in runtime.json()['detail']


def test_independent_input_does_not_relax_simultaneous_vs_serial_resource_gate(configured, shared_switch, db_session):
    from app.services.calibration.route_calibration import list_route_selections, list_individual_route_selections
    from app.services.calibration.route_batch_plan import build_batch_plan
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    topology, connection = shared_switch
    nodes, edges, modes = copy.deepcopy(topology.nodes), copy.deepcopy(topology.connections), copy.deepcopy(topology.operating_modes)
    nodes[0]['params'].update(ports=['in', 'out'], port_directions={'in': 'input', 'out': 'output'})
    nodes.append(dict(id='bse', type='bse_port', params={'ports': ['DL'], 'port_roles': {'DL': 'dl'}}))
    edges[1].update(source='ce1', target_pin='in1')
    edges.append(edge('upstream-feed', 'bse', 'DL', 'ce1', 'in'))
    modes[0]['active_connections'].append('upstream-feed')
    mappings = copy.deepcopy(connection.connection_params)
    mappings['port_maps']['h'].update(switch_id='1:INT_RELAY_A', topology_input_pin='in1')
    connection.connection_params = mappings
    topology.nodes, topology.connections, topology.operating_modes = nodes, edges, modes
    db_session.commit()
    assert {r.chain_id for r in list_individual_route_selections(db_session, configured.id, topology.id, 'mimo_ota')} == {'ov', 'oh'}
    assert len(build_batch_plan(db_session, configured.id, request_for(topology, frequencies=(2595.,)), None).items) == 2
    with pytest.raises(ValueError):
        list_route_selections(db_session, configured.id, topology.id, 'mimo_ota')
    with pytest.raises(ValueError):
        orchestrate_switch_topology(db_session, configured.chamber_config_id)
