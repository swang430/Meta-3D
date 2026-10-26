"""方向声明沿现有摘要；旧快照不回写，Mock/缺绑定不因此获得资格。"""
import copy
import json

import pytest

from tests.test_pc04a2_route_selection import (
    client, configured, graph, db_session, chamber, topology_two_chains, lab_profile, paths,
)
from tests.test_pc_04a_fixed_route_api import finish


def acquisition_payload(route, graph):
    return dict(chain_id=route['chain_id'], topology_id=str(graph.id), route_digest=route['route_digest'],
        configuration_digest=route['configuration_digest'], frequency_mhz=2595, requested_power_dbm=-20,
        reference_antenna='REF1 中心V', receive_cable_loss_db=2, receive_cable_source='2595MHz记录',
        fixed_route_confirmed=True, safety_confirmed=True, sample_count=2)


@pytest.mark.parametrize('location', ['normal', 'reference'])
def test_explicit_direction_changes_digest_rejects_old_selection_and_keeps_snapshot(
        client, configured, graph, db_session, location):
    # 声明端口的历史图先落库；稀疏参考边仍不补pin。
    graph.nodes = [{**node, 'params': {**node['params'], 'ports': ['in', 'out']}}
                   for node in graph.nodes]
    db_session.commit()
    original = paths(client, configured, graph)
    assert original.status_code == 200, original.text
    before = original.json()[0]
    url = f'/api/v1/switch-topologies/{graph.id}'
    scope = {'lab_profile_id': str(configured.id)}
    raw = client.get(url, params=scope).json()
    stored = json.dumps(graph.connections)
    payload = {key: copy.deepcopy(raw[key]) for key in ('nodes', 'connections', 'operating_modes')}
    unchanged = client.patch(url, params=scope, json=payload)
    assert unchanged.status_code == 200, unchanged.text
    assert paths(client, configured, graph).json()[0]['route_digest'] == before['route_digest']

    base = f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions'
    started = client.post(base, json=acquisition_payload(before, graph))
    assert started.status_code == 202, started.text
    history = finish(client, configured, started.json()['run_id'])
    snapshot = copy.deepcopy(history['result']['configuration']['route_selection'])
    assert history['result']['formal_eligible'] is False

    ident = 'pad1' if location == 'normal' else 'reference1'
    node = next(node for node in payload['nodes'] if node['id'] == ident)
    node['params']['port_directions'] = {'in': 'input', 'out': 'output'}
    saved = client.patch(url, params=scope, json=payload)
    assert saved.status_code == 200, saved.text
    after = paths(client, configured, graph).json()[0]
    assert after['route_digest'] != before['route_digest']
    if location == 'normal':
        assert after['configuration_digest'] != before['configuration_digest']
    nodes_key = 'nodes' if location == 'normal' else 'calibration_nodes'
    assert next(n for n in after[nodes_key] if n['id'] == ident)['params']['port_directions'] == node['params']['port_directions']
    stale = client.post(base, json=acquisition_payload(before, graph))
    assert stale.status_code == 422, stale.text
    historical = client.get(base + '/' + started.json()['run_id']).json()
    assert historical['result']['configuration']['route_selection'] == snapshot
    assert historical['result']['formal_eligible'] is False
    current = client.post(base, json=acquisition_payload(after, graph))
    assert current.status_code == 202, current.text
    assert finish(client, configured, current.json()['run_id'])['result']['formal_eligible'] is False
    db_session.refresh(graph)
    assert json.dumps(graph.connections) == stored


def test_legacy_missing_declarations_get_patch_keeps_route_and_configuration_digests(
        client, configured, graph, db_session):
    before = paths(client, configured, graph).json()[0]
    stored = json.dumps(graph.connections)
    url = f'/api/v1/switch-topologies/{graph.id}'
    scope = {'lab_profile_id': str(configured.id)}
    raw = client.get(url, params=scope).json()
    for payload in ({'name': '仅改名'}, {key: raw[key] for key in ('nodes', 'connections', 'operating_modes')}):
        saved = client.patch(url, params=scope, json=payload)
        assert saved.status_code == 200, saved.text
        after = paths(client, configured, graph).json()[0]
        assert after['route_digest'] == before['route_digest']
        assert after['configuration_digest'] == before['configuration_digest']
        db_session.refresh(graph)
        assert json.dumps(graph.connections) == stored
        assert all('port_directions' not in n['params'] for n in graph.nodes)


def test_explicit_directions_cannot_replace_missing_instrument_bindings(
        client, configured, graph, db_session):
    from app.models.diagnostic_run import DiagnosticRun
    configured.instrument_bindings = []
    graph.nodes = [{**node, 'params': {**node['params'], 'ports': ['in', 'out']}}
                   for node in graph.nodes]
    db_session.commit()
    base = f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions'
    before = paths(client, configured, graph).json()[0]
    assert client.post(base, json=acquisition_payload(before, graph)).status_code == 422
    nodes = copy.deepcopy(graph.nodes)
    for node in nodes:
        node['params']['port_directions'] = {'in': 'input', 'out': 'output'}
    saved = client.patch(f'/api/v1/switch-topologies/{graph.id}',
        params={'lab_profile_id': str(configured.id)}, json={'nodes': nodes})
    assert saved.status_code == 200, saved.text
    after = paths(client, configured, graph).json()[0]
    assert after['route_digest'] != before['route_digest']
    rejected = client.post(base, json=acquisition_payload(after, graph))
    assert rejected.status_code == 422, rejected.text
    assert db_session.query(DiagnosticRun).count() == 0
