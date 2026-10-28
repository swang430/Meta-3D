"""5c 完整raw→真实库写入→消费者；SQLite/Mock软件验证，不代表现场资格。"""
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID

import pytest

from tests.test_pc04a5a_topology_library import db, client, world, lab
from scripts.pc04a5c_independent_pa import build_candidate
from app.services.mimo_ota.switch_orchestrator import _build_probe_binding
from app.models.switch_topology import SwitchTopology
from app.models.switch_topology_revision import SwitchTopologyRevision
from tests.test_pc04a5b_restore_qualification import records

ROOT = '/api/v1/switch-topologies'


@pytest.fixture
def raw_source():
    return json.loads((Path(__file__).parent / 'fixtures/pc04a5c_caict_source.json').read_text())


def full_bindings(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    mode = next(m for m in graph['operating_modes'] if m['id'] == 'mimo_ota')
    active = [e for e in graph['connections'] if e['id'] in mode['active_connections']]
    # 必须使用完整模式，包含四条BSE→CE入边；绝不先过滤上游以制造GREEN。
    return [_build_probe_binding(e, nodes, active) for e in active if nodes[e['target']]['type'] == 'probe']


def test_full_mode_preserves_32_bindings_with_four_bse_inputs(raw_source):
    graph, manifest = build_candidate(raw_source)
    original = full_bindings(raw_source)
    assert len(original) == 32
    expected = {(f'B{i+1}', probe, pol) for i, (probe, pol) in enumerate(
        (p, q) for p in [1,9,2,10,3,11,4,12,5,13,6,14,7,15,8,16] for q in 'VH')}
    assert {(b.ce_port, b.probe_id, b.polarization) for b in original} == expected
    print('ORIGINAL complete mimo_ota: 32 bindings; four BSE inputs retained')
    candidate = full_bindings(graph)
    assert {(b.ce_port, b.probe_id, b.polarization) for b in candidate} == expected
    assert {b.connection_id for b in candidate} == {r['replacement_connection_ids'][1] for r in manifest['routes']}
    assert all(b.cable_loss_db is None for b in candidate)


def test_full_mode_without_upstream_inputs_still_has_32_bindings(raw_source):
    graph, _ = build_candidate(raw_source)
    graph['connections'] = [e for e in graph['connections'] if e['target'] != 'ce_f64']
    assert len(full_bindings(graph)) == 32


@pytest.mark.parametrize('bad', ['probe-input','pa-input','label-disguise','self','multi-parent','cycle','bse-transit'])
def test_complete_mode_rejects_real_backfeeds_and_intermediate_faults(raw_source, bad):
    graph, manifest = build_candidate(raw_source)
    route = manifest['routes'][0]
    first, last = [next(e for e in graph['connections'] if e['id'] == ident) for ident in route['replacement_connection_ids']]
    if bad in ('probe-input','pa-input','label-disguise'):
        source = route['probe_node_id'] if bad != 'pa-input' else route['pa_node_id']
        node = next(n for n in graph['nodes'] if n['id'] == source)
        if bad == 'label-disguise':
            node['label'] = 'baseStation'
        extra = dict(id='bad', source=source, target='ce_f64', source_pin='out', target_pin='in1')
        graph['connections'].append(extra)
    elif bad == 'self':
        first['source'] = route['pa_node_id']
    elif bad == 'multi-parent':
        graph['connections'].append(dict(first, id='bad'))
    elif bad == 'cycle':
        first['source'] = manifest['routes'][1]['pa_node_id']
        other = next(e for e in graph['connections'] if e['id'] == manifest['routes'][1]['replacement_connection_ids'][0])
        other['source'] = route['pa_node_id']
    else:
        next(n for n in graph['nodes'] if n['id'] == route['pa_node_id'])['type'] = 'communication_tester'
    mode = next(m for m in graph['operating_modes'] if m['id'] == 'mimo_ota')
    if bad in ('probe-input','pa-input','label-disguise','multi-parent'):
        mode['active_connections'].append('bad')
    with pytest.raises(ValueError):
        full_bindings(graph)


@pytest.fixture
def source(db, world, lab, raw_source):
    row = SwitchTopology(name='5c隔离完整旧raw', chamber_id=lab.chamber_config_id,
        switch_category_id=world[1][0].id, version=raw_source['version'],
        nodes=deepcopy(raw_source['nodes']), connections=deepcopy(raw_source['connections']),
        operating_modes=deepcopy(raw_source['operating_modes']), is_active=True, is_default=True)
    row.update_statistics(); db.add(row); db.commit()
    return row


def raw_graph(db, ident):
    db.expire_all()
    row = db.get(SwitchTopology, UUID(str(ident)))
    return deepcopy({key: getattr(row, key) for key in ('nodes','connections','operating_modes')})


def all_columns(db, row):
    db.refresh(row)
    return deepcopy({c.name: getattr(row, c.name) for c in row.__table__.columns})


def history(db, ident):
    db.expire_all()
    return [deepcopy({c.name: getattr(r, c.name) for c in r.__table__.columns}) for r in
            db.query(SwitchTopologyRevision).filter_by(topology_id=UUID(str(ident))).order_by(SwitchTopologyRevision.revision)]


def copy_save(client, db, lab, source, raw_source):
    graph, manifest = build_candidate(raw_source)
    assert len([n for n in graph['nodes'] if n['id'].startswith('pc04a5c_pa_')]) == 32
    assert len([e for e in graph['connections'] if e['id'].endswith(('__pa_in','__pa_out'))]) == 64
    params = {'lab_profile_id': str(lab.id)}
    response = client.post(f'{ROOT}/{source.id}/copy', params=params, json={'name':'CAICT 独立PA副本（隔离软件验证）'})
    assert response.status_code == 201, response.text
    copied = response.json()
    assert copied['id'] != str(source.id)
    assert copied['is_active'] is False and copied['is_default'] is False and copied['revision'] == 1
    url = f"{ROOT}/{copied['id']}"
    saved = client.patch(url, params=params, json={'expected_revision':1, **graph})
    assert saved.status_code == 200, saved.text
    assert saved.json()['revision'] == 2
    assert raw_graph(db, copied['id']) == graph
    return url, params, graph, manifest


def test_real_copy_patch_history_and_source_every_column_unchanged(client, db, lab, source, raw_source):
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    from app.models.test_plan import TestExecution
    # 明确synthetic旧执行冻结，只检验写入口绝不触碰；不是新的采集/confirmed证据。
    execution = TestExecution(status='completed', config={'route_calibration_freeze':{
        'synthetic':True, 'legacy_marker':[None,0,'0',False], 'topology_id':str(source.id)}})
    db.add(execution); db.commit()
    frozen = deepcopy(execution.config)
    before, old_history, qualification = all_columns(db, source), history(db, source.id), records(db)
    selected = orchestrate_switch_topology(db, lab.chamber_config_id)
    assert selected.success and selected.topology_id == str(source.id)
    url, params, graph, _ = copy_save(client, db, lab, source, raw_source)
    ident = url.rsplit('/',1)[1]
    assert client.patch(url, params=params, json={'expected_revision':1, **graph}).status_code == 409
    assert all_columns(db, source) == before and history(db, source.id) == old_history
    assert records(db) == qualification
    db.refresh(execution)
    assert execution.config == frozen
    assert orchestrate_switch_topology(db, lab.chamber_config_id).topology_id == str(source.id)
    revisions = history(db, ident)
    assert [r['revision'] for r in revisions] == [1,2]
    original = {key: deepcopy(raw_source[key]) for key in ('nodes','connections','operating_modes')}
    for edge in original['connections']:
        for key in ('calibrated_loss_db','calibrated_phase_deg'):
            if key in edge: edge[key] = None
    assert {key: revisions[0]['snapshot'][key] for key in original} == original
    assert {key: revisions[1]['snapshot'][key] for key in graph} == graph
    calibration = client.get(f'/api/v1/lab-profiles/{lab.id}/route-calibration-paths',
        params={'topology_id':ident, 'operating_mode':'mimo_ota'})
    assert calibration.status_code == 422, calibration.text
    print('INACTIVE calibration rejected:', calibration.text)
    original_calibration = client.get(f'/api/v1/lab-profiles/{lab.id}/route-calibration-paths',
        params={'topology_id':str(source.id), 'operating_mode':'mimo_ota'})
    print('ORIGINAL explicit calibration:', original_calibration.status_code, original_calibration.text)
    from app.services.topology_service import TopologyService
    for label, complete in [('original',raw_source),('candidate',graph)]:
        try:
            paths = TopologyService(complete).resolve_paths('mimo_ota')
            print('FULL TopologyService',label,'OK',len(paths))
        except ValueError as exc:
            print('FULL TopologyService',label,'ValueError',str(exc))


def test_saved_32_declared_output_subpaths_keep_unknown_loss(client, db, lab, source, raw_source):
    from app.services.declared_rf_routes import resolve_saved_rf_path
    from app.schemas.topology_internal_paths import validate_internal_traversals
    from app.services.topology_loss import loss_sources_for_path, loss_source_for_terminal, effective_connection_loss
    from app.services.topology_service import TopologyService
    url, _, _, manifest = copy_save(client, db, lab, source, raw_source)
    saved = raw_graph(db, url.rsplit('/',1)[1])
    for route in manifest['routes']:
        ids = route['replacement_connection_ids']
        edges = [next(e for e in saved['connections'] if e['id'] == ident) for ident in ids]
        nodes, selected = resolve_saved_rf_path(saved['nodes'], edges, ids[-1])
        assert [n['id'] for n in nodes] == ['ce_f64',route['pa_node_id'],route['probe_node_id']]
        assert validate_internal_traversals(nodes, selected, active_connections=edges) == [
            dict(node_id=route['pa_node_id'], from_port='in', to_port='out')]
        assert [effective_connection_loss(e) for e in loss_sources_for_path(nodes, edges, ids)] == [None,None]
        assert effective_connection_loss(loss_source_for_terminal(nodes, edges, ids)) is None
        # 这是明确选定的输出子图，不冒充完整模式解析。
        service = TopologyService(dict(nodes=nodes, connections=edges, operating_modes=[
            dict(id='mimo_ota',active_connections=ids)]))
        assert len(service.resolve_paths('mimo_ota')) == 1
        assert service.resolve_paths('mimo_ota')[0].total_loss_db is None
        assert all(row['compensation_db'] is None for row in service.get_calibration_matrix('mimo_ota').values())
        binding = _build_probe_binding(edges[-1], {n['id']:n for n in nodes}, edges)
        assert (binding.ce_port,binding.probe_id,binding.polarization) == (route['ce_port'],route['probe_id'],route['polarization'])


@pytest.mark.parametrize('bad', ['reverse','missing-in','missing-out','ce-identity','wrong-probe'])
def test_output_route_bad_identity_or_half_chain_is_not_accepted(raw_source, bad):
    graph, manifest = build_candidate(raw_source)
    route = manifest['routes'][0]
    edges = [next(e for e in graph['connections'] if e['id'] == ident) for ident in route['replacement_connection_ids']]
    nodes = {n['id']:n for n in graph['nodes']}
    if bad == 'reverse': nodes[route['pa_node_id']]['params']['internal_paths'] = [dict(from_port='out',to_port='in')]
    if bad == 'missing-in': edges.pop(0)
    if bad == 'missing-out':
        from app.services.declared_rf_routes import resolve_saved_rf_path
        with pytest.raises(ValueError): resolve_saved_rf_path(nodes, edges[:1], route['replacement_connection_ids'][1])
        return
    if bad == 'ce-identity': edges[-1]['ce_port'] = 'B32'
    if bad == 'wrong-probe': nodes[route['probe_node_id']]['params']['probe_id'] = 99
    try:
        binding = _build_probe_binding(edges[-1],nodes,edges)
    except ValueError:
        return
    assert (binding.ce_port,binding.probe_id,binding.polarization) != ('B1',1,'V')


def test_restore_r1_rejected_zero_write_then_r2_restores_as_r4(client, db, lab, source, raw_source):
    before = all_columns(db, source)
    url, params, graph, manifest = copy_save(client, db, lab, source, raw_source)
    ident = url.rsplit('/',1)[1]
    baseline = history(db, ident)
    assert client.get(url+'/revisions/1', params=params).status_code == 200
    for endpoint in ('restore-preview','restore'):
        response = client.post(url+'/'+endpoint, params=params,json={'revision':1,'expected_revision':2})
        assert response.status_code == 422, response.text
        assert history(db, ident) == baseline and raw_graph(db, ident) == graph
        assert db.get(SwitchTopology,UUID(ident)).revision == 2
    changed = deepcopy(graph)
    next(n for n in changed['nodes'] if n['id'] == manifest['routes'][0]['pa_node_id'])['position']['x'] += 31
    response = client.patch(url, params=params, json={'expected_revision':2, **changed})
    assert response.status_code == 200 and response.json()['revision'] == 3, response.text
    at_three = history(db, ident)
    preview = client.post(url+'/restore-preview',params=params,json={'revision':2,'expected_revision':3})
    assert preview.status_code == 200, preview.text
    assert history(db,ident) == at_three and raw_graph(db,ident) == changed
    response = client.post(url+'/restore',params=params,json={'revision':2,'expected_revision':3})
    assert response.status_code == 200 and response.json()['revision'] == 4, response.text
    assert raw_graph(db,ident) == graph
    assert history(db,ident)[:3] == at_three
    assert response.json()['is_active'] is False and response.json()['is_default'] is False
    assert all_columns(db,source) == before


@pytest.mark.parametrize('bad', ['stale','cross-scope','missing-token','wrong-pin','half-chain'])
def test_write_failures_leave_every_revision_unchanged(client, db, world, lab, source, raw_source, bad):
    url, params, graph, manifest = copy_save(client, db, lab, source, raw_source)
    ident = url.rsplit('/',1)[1]
    before = history(db,ident)
    if bad == 'stale':
        response = client.post(url+'/restore',params=params,json={'revision':2,'expected_revision':1}); expected = 409
    elif bad == 'cross-scope':
        response = client.post(url+'/restore',params={'lab_profile_id':str(world[2][1].id)},json={'revision':2,'expected_revision':2}); expected = 409
    else:
        changed = deepcopy(graph)
        body = {'expected_revision':2, **changed}
        if bad == 'missing-token': body.pop('expected_revision')
        if bad == 'wrong-pin': next(e for e in changed['connections'] if e['id']==manifest['routes'][0]['replacement_connection_ids'][0])['target_pin']='out'
        if bad == 'half-chain': changed['connections'] = [e for e in changed['connections'] if e['id'] != manifest['routes'][0]['replacement_connection_ids'][0]]; body['connections']=changed['connections']
        response = client.patch(url,params=params,json=body); expected = 422
    assert response.status_code == expected, response.text
    assert history(db,ident) == before and raw_graph(db,ident) == graph
