"""4e组合验收：真实HTTP/SQL/正式冻结；量值均为隔离验收输入，非硬件证据。"""
from tests.topology_revision_requests import saved_revision as _saved_revision
import copy
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.switch_topology import SwitchTopology
from app.models.diagnostic_run import DiagnosticRun
from app.models.instrument import InstrumentCategory
from app.services.topology_service import TopologyService
from app.services.mimo_ota.switch_orchestrator import _build_probe_binding
from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation
from tests.test_pc04a4d_loss_truth import bootstrap, world, graph, create
from tests.test_pc04a4d_conversion import raw, preview, commit
from tests.test_pc04a2_route_application import db_session, payload, confirm, counts
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured, start
from tests.test_pc04a2_route_eligibility import real_capture, preview as application_preview
from tests.test_pc04a2_route_freeze import legacy, launch, entries


@pytest.fixture(autouse=True)
def evidence(request, monkeypatch, tmp_path):
    """保存真实请求/响应和显式SQL/冻结快照，不替换业务结果。"""
    root = Path(os.environ.get('PC04A4E_EVIDENCE_DIR', str(tmp_path)))
    root.mkdir(parents=True, exist_ok=True)
    events = []
    original = TestClient.request

    def traced(self, method, url, **kwargs):
        response = original(self, method, url, **kwargs)
        events.append(dict(method=method, url=str(url), params=kwargs.get('params'),
                           request=kwargs.get('json'), status=response.status_code,
                           response=response.json()))
        return response

    monkeypatch.setattr(TestClient, 'request', traced)
    yield lambda name, value: events.append(dict(snapshot=name, value=copy.deepcopy(value)))
    target = root / (request.node.name.replace('/', '_') + '.json')
    target.write_text(json.dumps(events, ensure_ascii=False, indent=2, default=str))


def sql_graph(db, ident):
    db.expire_all()
    return dict(db.execute(text('SELECT nodes, connections, operating_modes FROM switch_topologies WHERE id=:id'),
                           {'id': ident.hex}).mappings().one())


def metadata(unit='dB'):
    return dict(unit=unit, source_note='隔离验收输入，非实物测量', frequency_range_mhz=[2500, 2700])


def test_e01_combined_post_patch_get_and_real_template_conversion(world, evidence):
    db, lab, http = world
    data = graph()
    data['nodes'][-1]['params'].update(nominal_metadata={'gain_dbi': metadata('dBi')})
    # 在同一张图共同保存标称、角色、pair与同线缆声明；缺省PA数值保持缺键。
    data['connections'][1]['loss_owner_connection_id'] = 'a'
    data['connections'][0]['nominal_metadata'] = {'pa_gain_db': metadata()}
    url, scope = create(world, data)
    ident = UUID(url.rsplit('/', 1)[1])
    saved = db.get(SwitchTopology, ident)
    saved.connections = [{**edge, 'opaque': {'keep': True}} for edge in saved.connections]
    db.commit()
    before = sql_graph(db, ident)
    fetched = http.get(url, params=scope).json()
    fetched['nodes'][1]['position'] = {'x': 17, 'y': 29}
    result = http.patch(url, params=scope, json={**({'name': '组合声明', 'nodes': fetched['nodes'],
                                              'connections': fetched['connections']}), 'expected_revision': _saved_revision(http, url, scope)})
    assert result.status_code == 200, result.text
    persisted = db.get(SwitchTopology, ident)
    db.refresh(persisted)
    assert persisted.connections == json.loads(before['connections'])
    assert 'pa_gain_db' not in persisted.connections[0]
    assert http.get(url, params=scope).json()['nodes'][1]['position'] == {'x': 17, 'y': 29}
    original = sql_graph(db, ident)
    bad = copy.deepcopy(result.json()['nodes'])
    bad[1]['params']['internal_paths'][0]['to_port'] = 'MISSING'
    assert http.patch(url, params=scope, json={**({'nodes': bad}), 'expected_revision': _saved_revision(http, url, scope)}).status_code == 422
    assert sql_graph(db, ident) == original
    from app.api.switch_topology import _TEMPLATES_DIR
    template = _TEMPLATES_DIR / 'caict_v4.py'
    template_hash = hashlib.sha256(template.read_bytes()).hexdigest()
    imported = http.post('/api/v1/switch-topologies/import/from-template', params={
        **scope, 'switch_category_id': str(uuid4()), 'template_id': 'caict_v4'})
    assert imported.status_code == 200, imported.text
    value = imported.json()
    imported_url = '/api/v1/switch-topologies/' + value['id']
    old = sql_graph(db, UUID(value['id']))
    converted_node = next(n for n in value['nodes'] if n['type'] == 'signal_analyzer')
    pins = sorted({e['target_pin'] for e in value['connections'] if e['target'] == converted_node['id']})
    change = {'nodes': [{'node_id': converted_node['id'], 'target_type': 'sa_port',
                         'ports': pins, 'port_directions': {p: 'input' for p in pins}}]}
    adjacent_ids = {e['source'] for e in value['connections'] if e['target'] == converted_node['id']}
    for adjacent_id in sorted(adjacent_ids):
        adjacent_pins = sorted({e['source_pin'] for e in value['connections'] if e['source'] == adjacent_id} |
                               {e['target_pin'] for e in value['connections'] if e['target'] == adjacent_id})
        change['nodes'].append({'node_id': adjacent_id, 'ports': adjacent_pins})
    p = preview(world, imported_url, scope, change)
    assert sql_graph(db, UUID(value['id'])) == old
    converted = commit(world, imported_url, scope, p)
    assert converted.status_code == 200, converted.text
    assert converted.json()['id'] == value['id']
    after = sql_graph(db, UUID(value['id']))
    assert after['connections'] == old['connections'] and after['operating_modes'] == old['operating_modes']
    edited_ids = {converted_node['id'], *adjacent_ids}
    assert [n for n in json.loads(after['nodes']) if n['id'] not in edited_ids] == [
        n for n in json.loads(old['nodes']) if n['id'] not in edited_ids]
    assert hashlib.sha256(template.read_bytes()).hexdigest() == template_hash
    evidence('身份及原件', dict(lab_id=lab.id, chamber_id=lab.chamber_config_id, topology_id=ident,
                              imported_topology_id=value['id'], template=str(template), sha256=template_hash,
                              before=before, after=sql_graph(db, ident), imported_before=old, imported_after=after))


@pytest.mark.parametrize('entry', ['patch', 'conversion'])
@pytest.mark.parametrize('mutation', ['remove_port', 'rename_port', 'bad_pair', 'delete_edge', 'bse_conflict'])
def test_e02_cross_mode_references_atomic(world, evidence, entry, mutation):
    db, lab, http = world
    data = graph()
    data['nodes'].append(dict(id='bse', type='communication_tester', label='BSE', params={
        'ports': ['RF'], 'port_roles': {'RF': 'dl'}, 'port_directions': {'RF': 'output'}}))
    data['operating_modes'].append(dict(id='calibration', name='参考', active_connections=['a', 'b']))
    url, scope = create(world, data)
    before = raw(world, url)
    if mutation in ('remove_port', 'rename_port'):
        edits = {'node_id': 'wire', 'ports': ['IN'] if mutation == 'remove_port' else ['IN', 'NEW']}
    elif mutation == 'bad_pair':
        edits = {'node_id': 'wire', 'internal_paths': [{'from_port': 'IN', 'to_port': 'MISSING'}]}
    elif mutation == 'bse_conflict':
        edits = {'node_id': 'bse', 'port_directions': {'RF': 'input'}}
    else:
        edits = None
    if entry == 'conversion':
        # conversion不提供删除边入口，伪造删除字段必须被拒，不能静默删引用。
        changes = {'nodes': [edits]} if edits else {'connections': [{'connection_id': 'a', 'delete': True}]}
        result = http.post(url + '/conversion-preview', params=scope, json=changes)
    else:
        updated = copy.deepcopy(data)
        if edits:
            next(n for n in updated['nodes'] if n['id'] == edits['node_id'])['params'].update(
                {k: v for k, v in edits.items() if k != 'node_id'})
        else:
            updated['connections'] = updated['connections'][1:]
        result = http.patch(url, params=scope, json={**(updated), 'expected_revision': _saved_revision(http, url, scope)})
    assert result.status_code == 422, result.text
    assert raw(world, url) == before
    if mutation in ('remove_port', 'rename_port'):
        assert 'wire' in result.text and ('b' in result.text or 'OUT' in result.text)
    evidence('原子拒绝', dict(lab_id=lab.id, topology_url=url, before=list(before), after=list(raw(world, url))))


def test_e02_legal_rewire_and_unknown_do_not_grant_capability(world):
    _, _, http = world
    url, scope = create(world)
    data = graph()
    data['nodes'][1]['params'].update(ports=['IN', 'NEW'], port_directions={'IN': 'input', 'NEW': 'output'},
        internal_paths=[{'from_port': 'IN', 'to_port': 'NEW'}])
    data['connections'][1]['source_pin'] = 'NEW'
    response = http.patch(url, params=scope, json={**(data), 'expected_revision': _saved_revision(http, url, scope)})
    assert response.status_code == 200, response.text
    for directions in ({}, {'IN': 'unknown', 'NEW': 'unknown'}):
        data['nodes'][1]['params']['port_directions'] = directions
        response = http.patch(url, params=scope, json={**(data), 'expected_revision': _saved_revision(http, url, scope)})
        assert response.status_code == 200, response.text
        actual = next(n for n in response.json()['nodes'] if n['id'] == 'wire')['params']['port_directions']
        assert not any(v == 'bidirectional' for v in actual.values())
        with pytest.raises(ValueError, match='方向未声明'):
            TopologyService(response.json()).resolve_paths('mimo_ota')


@pytest.mark.parametrize('kind', ['cable', 'receive_cable'])
def test_e03_http_group_undo_zero_unknown_and_terminal(world, evidence, kind):
    _, _, http = world
    data = graph()
    data['nodes'][1]['type'] = kind
    mode = 'mimo_ota'
    if kind == 'receive_cable':
        # 接收线不授正常链资格；在参考模式验证同一个损耗消费者。
        mode = 'calibration'
        data['nodes'][-1]['params'].pop('rf_path_selection')
        data['operating_modes'][0]['id'] = mode
        for edge in data['connections']:
            edge['modes'] = [mode]
    for edge, phase in zip(data['connections'], [10, 20]):
        edge['calibrated_phase_deg'] = phase
    url, scope = create(world, data)

    def values():
        current = http.get(url, params=scope).json()
        service = TopologyService(current)
        path = service.resolve_paths(mode)[0]
        assert path.total_phase_deg == 30
        if kind == 'receive_cable':
            with pytest.raises(ValueError, match='正常路径不能包含校准参考接线'):
                _build_probe_binding(current['connections'][-1], {n['id']: n for n in current['nodes']}, current['connections'])
            return path.total_loss_db, None
        binding = _build_probe_binding(current['connections'][-1], {n['id']: n for n in current['nodes']}, current['connections'])
        return path.total_loss_db, binding.cable_loss_db

    terminal = 2 if kind == 'cable' else None
    assert values() == (4, terminal)
    p = preview(world, url, scope, {'connections': [{'connection_id': 'b', 'loss_owner_connection_id': 'a',
                                                   'same_physical_cable_confirmed': True}]})
    assert commit(world, url, scope, p).status_code == 200
    assert values() == (2, terminal)
    for value in (0, None):
        edges = http.get(url, params=scope).json()['connections']
        edges[0]['calibrated_loss_db'] = value
        if value is None:
            edges[0]['cable_loss_db'] = None
        assert http.patch(url, params=scope, json={**({'connections': edges}), 'expected_revision': _saved_revision(http, url, scope)}).status_code == 200
        assert values() == (value, value if kind == 'cable' else None)
    assert http.patch(url, params=scope, json={**(data), 'expected_revision': _saved_revision(http, url, scope)}).status_code == 200
    assert values() == (4, terminal)
    for modes in ([dict(id=mode, name='半组', active_connections=['b'])],
                  [dict(id=mode, name='半组', active_connections=['a']), dict(id='other', name='另一模式', active_connections=['b'])]):
        bad = copy.deepcopy(data)
        bad['connections'][1]['loss_owner_connection_id'] = 'a'
        bad['operating_modes'] = modes
        before = raw(world, url)
        response = http.patch(url, params=scope, json={**(bad), 'expected_revision': _saved_revision(http, url, scope)})
        assert response.status_code == 422, response.text
        assert raw(world, url) == before
    evidence('通用与末边', dict(kind=kind, topology_url=url, restored=values()))


def with_reference(topology):
    """映射原probe1v参考接入到冻结夹具probe_0_v；PA边身份独立。"""
    base_nodes = copy.deepcopy(topology.nodes)
    for node in base_nodes:
        if node['type'] == 'ce_port':
            node['params'].update(ports=['out'], port_directions={'out': 'output'})
        if node['type'] == 'probe':
            node['params'].update(ports=['in', 'out'], port_directions={'in': 'input', 'out': 'output'})
    topology.nodes = [*base_nodes,
        dict(id='wire', type='cable', label='正常线', params={'ports': ['in', 'out'],
            'port_directions': {'in': 'input', 'out': 'output'},
            'internal_paths': [{'from_port': 'in', 'to_port': 'out'}]}),
        dict(id='reference1', type='reference_antenna', label='参考天线', params={'connection_scope': 'calibration',
            'ports': ['in', 'out'], 'port_directions': {'in': 'input', 'out': 'output'}}),
        dict(id='rx-cable1', type='receive_cable', label='接收线', params={'connection_scope': 'calibration',
            'ports': ['in', 'out'], 'port_directions': {'in': 'input', 'out': 'output'},
            'internal_paths': [{'from_port': 'in', 'to_port': 'out'}]}),
        dict(id='sa1', type='signal_analyzer', label='分析仪', params={'connection_scope': 'calibration',
            'ports': ['in'], 'port_directions': {'in': 'input'}})]
    topology.connections = [dict(id='owner', source='ce_b1', source_pin='out', target='wire', target_pin='in', cable_loss_db=2),
        *[{**e, **(dict(source='wire', source_pin='out', cable_loss_db=2, calibrated_loss_db=None)
            if e['id'] == 'conn_p0v' else {})} for e in topology.connections],
        dict(id='pa-reference-edge', source='probe_0_v', target='reference1'),
        dict(id='reference-cable', source='reference1', target='rx-cable1', target_pin='in', cable_loss_db=2),
        dict(id='cable-sa', source='rx-cable1', source_pin='out', target='sa1', cable_loss_db=2)]
    topology.operating_modes = [
        {**m, 'active_connections': ['owner', *m['active_connections']]} for m in topology.operating_modes] + [
        dict(id='calibration', name='参考', active_connections=['pa-reference-edge', 'reference-cable', 'cable-sa'])]


@pytest.mark.asyncio
async def test_e04_e05_selected_reference_pa_http_metadata_owner_and_two_freezes(
        client, configured, real_capture, legacy, launch, db_session, topology_two_chains, chamber, monkeypatch, evidence):
    topology = topology_two_chains
    assert all(c.driver_mode == 'mock' for c in db_session.query(InstrumentCategory))
    assert all(b['driver_mode'] == 'mock' for b in configured.instrument_bindings)
    with_reference(topology)
    db_session.commit()
    endpoint = f'/api/v1/lab-profiles/{configured.id}'
    params = dict(topology_id=str(topology.id), operating_mode='mimo_ota')
    selected = client.get(endpoint + '/route-calibration-paths', params=params)
    assert selected.status_code == 200, selected.text
    selection = next(s for s in selected.json() if s['chain_id'] == 'conn_p0v')
    pa_edge_id = 'pa-reference-edge'
    assert selection['calibration_connection_ids'] and pa_edge_id in selection['calibration_connection_ids']
    assert selection['node_ids'][-1] == 'probe_0_v'
    row = real_capture()  # 生产builder/runner/parser，仅VISA由既有脚本替换；非硬件。
    original_run = copy.deepcopy(row.sequence_evidence)
    run_get = client.get(endpoint + f'/fixed-route-acquisitions/{row.id}').json()
    assert pa_edge_id in run_get['result']['configuration']['route_selection']['calibration_connection_ids']
    assert row.sequence_evidence['extra']['fixed_route_acquisition']['configuration']['route_selection'] == run_get['result']['configuration']['route_selection']
    adopted = confirm(client, configured, payload(client, configured, row))
    assert adopted.status_code == 201, adopted.text
    first = await launch()
    first_freeze = copy.deepcopy(read_execution_route_compensation(first))
    certificate = {c.name: getattr(legacy, c.name) for c in legacy.__table__.columns}
    history_params = {'topology_id': str(topology.id), 'chain_id': 'conn_p0v'}
    history = client.get(endpoint + '/route-calibration-applications', params=history_params)
    assert history.status_code == 200, history.text
    applications = history.json()
    assert applications == [adopted.json()]
    sql_before = sql_graph(db_session, topology.id)
    url = f'/api/v1/switch-topologies/{topology.id}'
    scope = {'lab_profile_id': str(configured.id)}
    fetched = client.get(url, params=scope).json()
    for edge in fetched['connections']:
        if edge['id'] == pa_edge_id:
            edge['nominal_metadata'] = {'pa_gain_db': metadata()}
    saved = client.patch(url, params=scope, json={**({'connections': fetched['connections']}), 'expected_revision': _saved_revision(client, url, scope)})
    assert saved.status_code == 200, saved.text
    sql_after = sql_graph(db_session, topology.id)
    raw_pa = next(e for e in json.loads(sql_after['connections']) if e['id'] == pa_edge_id)
    assert 'pa_gain_db' not in raw_pa and 'cable_loss_db' not in raw_pa
    after = client.get(endpoint + '/route-calibration-paths', params=params)
    assert after.status_code == 200, after.text
    after_selection = next(s for s in after.json() if s['chain_id'] == 'conn_p0v')
    assert after_selection['route_digest'] == selection['route_digest']
    assert after_selection['calibration_connections'][0]['nominal_metadata']['pa_gain_db'] == metadata()
    assert after_selection['connections'] == selection['connections']
    # PA元数据单独保存后，再用HTTP声明正常线owner，分别验证两种不变性。
    edges = copy.deepcopy(saved.json()['connections'])
    next(e for e in edges if e['id'] == 'conn_p0v')['loss_owner_connection_id'] = 'owner'
    saved = client.patch(url, params=scope, json={**({'connections': edges}), 'expected_revision': _saved_revision(client, url, scope)})
    assert saved.status_code == 200, saved.text
    candidate = application_preview(client, configured, row)
    assert candidate.status_code == 200 and candidate.json()['eligibility']['eligible_for_adoption'], candidate.text
    assert candidate.json()['new_net_loss_db'] == 28
    history = client.get(endpoint + '/route-calibration-applications', params=history_params)
    assert history.status_code == 200, history.text
    assert history.json() == applications
    renewed = confirm(client, configured, payload(client, configured, row))
    assert renewed.status_code == 201, renewed.text
    assert renewed.json()['acquisition_run_id'] == str(row.id)
    assert renewed.json()['selection_snapshot']['calibration_connection_ids'] == selection['calibration_connection_ids']
    history = client.get(endpoint + '/route-calibration-applications', params=history_params)
    assert history.status_code == 200, history.text
    assert {record['id'] for record in history.json()} == {adopted.json()['id'], renewed.json()['id']}
    assert all(record in history.json() for record in applications)
    second = await launch()
    assert entries(second)['conn_p0v']['source_kind'] == 'confirmed_route'
    assert entries(second)['conn_p0v']['value_db'] == 28
    assert entries(second)['conn_p0v']['source_id'] == renewed.json()['id']
    from app.services.mimo_ota.path_loss_preflight import evaluate_path_loss_preflight
    from app.services.channel_engine_client import ChannelEngineClient
    verdict = evaluate_path_loss_preflight(db_session, second, chamber_id=chamber.id, frequency_mhz=2595,
        operating_mode='mimo_ota', precheck_strict_cal=True, channel_emulator_execution_mode='real')
    assert verdict.blocker is None
    engine = ChannelEngineClient(db_session)
    monkeypatch.setattr(engine, '_query_phase_compensation', lambda *args, **kwargs: {})
    consumed = engine._query_calibration_entries(chamber.id, 2595e6, chamber, path_loss_calibration=None,
                                                route_compensation=verdict.route_compensation)
    assert next(e for e in consumed if e['port_id'] == 1)['cable_loss_db'] == 28
    assert next(e for e in consumed if e['port_id'] == 1)['probe_gain_dbi'] == 0
    assert read_execution_route_compensation(first) == first_freeze
    assert row.sequence_evidence == original_run
    assert {c.name: getattr(legacy, c.name) for c in legacy.__table__.columns} == certificate
    evidence('身份与SQL及冻结', dict(lab_id=configured.id, chamber_id=configured.chamber_config_id,
        topology_id=topology.id, probe_mapping={'probe1v': 'probe_0_v'}, chain_id='conn_p0v', pa_edge_id=pa_edge_id,
        run_id=row.id, application_id=adopted.json()['id'], renewed_application_id=renewed.json()['id'],
        first_execution_id=first.id, second_execution_id=second.id, consumed=consumed,
        sql_before=sql_before, sql_after=sql_after, original_run=original_run, application=applications,
        first_freeze=first_freeze, second_freeze=read_execution_route_compensation(second)))
    # 实际pin/pair身份变化不能沿用旧采用，且不改旧冻结。
    changed = copy.deepcopy(saved.json()['nodes'])
    wire = next(n for n in changed if n['id'] == 'wire')
    wire['params']['ports'] = ['in', 'other']
    wire['params']['port_directions'] = {'in': 'input', 'other': 'output'}
    wire['params']['internal_paths'] = [{'from_port': 'in', 'to_port': 'other'}]
    edges = copy.deepcopy(saved.json()['connections'])
    next(e for e in edges if e['id'] == 'conn_p0v')['source_pin'] = 'other'
    response = client.patch(url, params=scope, json={**({'nodes': changed, 'connections': edges}), 'expected_revision': _saved_revision(client, url, scope)})
    assert response.status_code == 200, response.text
    assert not application_preview(client, configured, row).json()['eligibility']['eligible_for_adoption']
    third = await launch()
    assert entries(third).get('conn_p0v', {}).get('source_kind') != 'confirmed_route'
    assert read_execution_route_compensation(first) == first_freeze


def test_e06_legacy_reference_scope_not_capture_permission(client, configured, db_session, topology_two_chains, evidence):
    topology = topology_two_chains
    with_reference(topology)
    db_session.commit()
    endpoint = f'/api/v1/lab-profiles/{configured.id}'
    baseline = client.get(endpoint + '/calibration-scope').json()
    topology.nodes = [{**n, 'params': {'connection_scope': 'calibration'}} if n['id'] == 'rx-cable1' else n
                      for n in topology.nodes]
    db_session.commit()  # 仅制造历史缺声明原行，不经POST赋予新图资格。
    url = f'/api/v1/switch-topologies/{topology.id}'
    scope = {'lab_profile_id': str(configured.id)}
    changes = {'connections': [{'connection_id': 'cable-sa', 'loss_owner_connection_id': 'reference-cable',
                                'same_physical_cable_confirmed': True}]}
    p = client.post(url + '/conversion-preview', params=scope, json=changes)
    assert p.status_code == 200, p.text
    saved = client.patch(url, params=scope, json={**({'conversion': {
        'source_digest': p.json()['source_digest'], 'changes': p.json()['changes']}}), 'expected_revision': p.json()['revision']})
    assert saved.status_code == 200, saved.text
    current = client.get(endpoint + '/calibration-scope')
    comparison = client.post(endpoint + '/calibration-scope/compare', json={'baseline': baseline})
    assert current.status_code == comparison.status_code == 200
    assert current.json()['payload']['topology']['loss_ownership'] == [
        {'id': 'cable-sa', 'loss_owner_connection_id': 'reference-cable'}]
    assert comparison.json()['requires_review']
    before = (db_session.query(DiagnosticRun).count(), counts(db_session))
    rejected = client.get(endpoint + '/route-calibration-paths', params={'topology_id': str(topology.id), 'operating_mode': 'mimo_ota'})
    assert rejected.status_code == 422 and '内部通路未声明' in rejected.text
    capture = start(client, configured)
    assert capture.status_code == 422, capture.text
    assert (db_session.query(DiagnosticRun).count(), counts(db_session)) == before
    topology.operating_modes = [m for m in topology.operating_modes if m['id'] != 'calibration']
    db_session.commit()
    no_mode = client.get(endpoint + '/calibration-scope')
    assert no_mode.status_code == 200, no_mode.text
    assert 'loss_ownership' not in no_mode.json()['payload']['topology']
    evidence('身份及未新增记录', dict(lab_id=configured.id, topology_id=topology.id, before=before,
        after=(db_session.query(DiagnosticRun).count(), counts(db_session)), saved_sql=sql_graph(db_session, topology.id)))
