"""元数据不成为物理身份；真实 HTTP 回传保留原连接表示。"""
import copy
import json

import pytest

from tests.test_pc04a2_route_selection import (
    client, configured, graph, db_session, chamber, topology_two_chains, lab_profile, paths,
)


@pytest.mark.parametrize('location', ['normal', 'reference', 'reference_edge', 'none'])
def test_metadata_and_clean_http_roundtrip_do_not_change_existing_route_identity(
        client, configured, graph, db_session, location):
    before = paths(client, configured, graph).json()[0]
    stored = json.dumps(graph.connections)
    url = f'/api/v1/switch-topologies/{graph.id}'
    scope = {'lab_profile_id': str(configured.id)}
    fetched = client.get(url, params=scope)
    assert fetched.status_code == 200, fetched.text
    raw = fetched.json()
    assert raw['connections'] == graph.connections
    payload = {k: copy.deepcopy(raw[k]) for k in ('nodes', 'connections', 'operating_modes')}
    metadata = {'unit': 'dBi', 'source_note': '目录待核', 'frequency_range_mhz': None}
    if location in ('normal', 'reference'):
        ident = 'probe1v' if location == 'normal' else 'reference1'
        node = next(n for n in payload['nodes'] if n['id'] == ident)
        node['params']['nominal_metadata'] = {'gain_dbi': metadata}
    elif location == 'reference_edge':
        payload['connections'][2]['nominal_metadata'] = {'cable_loss_db': {**metadata, 'unit': 'dB'}}
    response = client.patch(url, params=scope, json=payload)
    assert response.status_code == 200, response.text
    after = paths(client, configured, graph).json()[0]
    assert after['route_digest'] == before['route_digest']
    if location == 'reference':
        assert after['calibration_nodes'][0]['params']['nominal_metadata']['gain_dbi'] == metadata
    elif location == 'reference_edge':
        assert after['calibration_connections'][0]['nominal_metadata'] == payload['connections'][2]['nominal_metadata']
    else:
        db_session.refresh(graph)
        assert json.dumps(graph.connections) == stored


def test_typed_legacy_reference_edge_roundtrip_preserves_stored_json_and_digest(
        client, configured, graph, db_session):
    edges = copy.deepcopy(graph.connections)
    edges[2].update(cable_loss_db='2.5', calibrated_loss_db='0', opaque={'keep': True})
    graph.connections = edges
    db_session.commit()
    before = paths(client, configured, graph).json()[0]
    stored = json.dumps(graph.connections)
    url = f'/api/v1/switch-topologies/{graph.id}'
    scope = {'lab_profile_id': str(configured.id)}
    raw = client.get(url, params=scope).json()
    assert raw['connections'][2]['cable_loss_db'] == 2.5
    assert raw['connections'][2]['calibrated_loss_db'] == 0
    assert 'opaque' not in raw['connections'][2]
    for payload in ({'name': '只改名'}, {k: raw[k] for k in ('nodes', 'connections', 'operating_modes')}):
        response = client.patch(url, params=scope, json=payload)
        assert response.status_code == 200, response.text
        db_session.refresh(graph)
        assert json.dumps(graph.connections) == stored
        assert paths(client, configured, graph).json()[0]['route_digest'] == before['route_digest']
