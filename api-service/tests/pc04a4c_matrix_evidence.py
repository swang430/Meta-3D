"""Task4专用ORM/生产builder补证；不启动HAL、不构造real量值、不执行OTA。"""
import copy
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

url = os.environ.get('DATABASE_URL', '')
database = Path(url.removeprefix('sqlite:///'))
if (not re.fullmatch(r'sqlite:////tmp/pc04a4c-[A-Za-z0-9]+/browser.sqlite', url)
        or not database.is_file() or os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'):
    raise RuntimeError('仅允许已seed的Task4专用SQLite和全Mock')

import httpx
from app.db.database import SessionLocal
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.models.diagnostic_run import DiagnosticRun
from app.services.topology_service import TopologyService
from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
from app.services.mimo_ota.route_calibration_freeze import (
    resolve_effective_route_compensation, frozen_route_identity_error,
    read_execution_route_compensation)
from app.hal.base_station_compatibility import canonical_payload_digest

client = httpx.Client(base_url='http://127.0.0.1:18096/api/v1', timeout=30)
calls = []


def call(method, path, data=None, expected=200, headers=None):
    response = client.request(method, path, json=data, headers=headers)
    body = response.json()
    exchange = dict(method=method, path=path, request=data, headers=headers, status=response.status_code, response=body)
    calls.append(exchange)
    print(json.dumps({'exchange': exchange}, ensure_ascii=False), flush=True)
    assert response.status_code == expected, exchange
    return body


labs = call('GET', '/lab-profiles')
lab = next(row for row in labs if row['name'] == 'PC04A4c内部通路甲')
lab_id, chamber_id = UUID(lab['id']), UUID(lab['chamber_config_id'])
with SessionLocal() as db:
    assert all(row.driver_mode == 'mock' for row in db.query(InstrumentCategory))
    assert all(binding['driver_mode'] == 'mock' for row in db.query(LabProfile) for binding in row.instrument_bindings)
    switch = db.query(InstrumentCategory).filter_by(category_key='rfSwitch').one()
    category_id = str(switch.id)


def node(ident, kind, ports, directions, **extra):
    return dict(id=ident, type=kind, label=ident, position=dict(x=80, y=80),
        params=dict(ports=ports, port_directions=directions, **extra))


def pair(first='in', second='out'):
    return dict(from_port=first, to_port=second)


def edge(ident, source, target, first='out', second='in'):
    return dict(id=ident, source=source, target=target, source_pin=first, target_pin=second, cable_loss_db=0)


def create(name, nodes, edges, modes=None):
    data = dict(name=name, lab_profile_id=str(lab_id), switch_category_id=category_id,
        nodes=nodes, connections=edges, operating_modes=modes or [dict(id='mimo_ota', name='MIMO OTA 测试', active_connections=[row['id'] for row in edges])])
    return call('POST', '/switch-topologies', data, 201)


def endpoint(topo, suffix=''):
    return f"/switch-topologies/{topo['id']}{suffix}?lab_profile_id={lab_id}"


def default_only(db, topology_id):
    # 仅本新库的软件fixture选定正式resolver目标；不修改任何用户图或资格。
    for row in db.query(SwitchTopology).filter_by(chamber_id=chamber_id):
        row.is_default = str(row.id) == topology_id
        row.is_active = str(row.id) == topology_id
    db.commit()


def switch_evidence():
    maps = {
        'v': dict(switch_id='1:INT_RELAY_A', relay_type='spdt', input_port=0, output_port='NC', topology_input_pin='in1', topology_output_pin='out1'),
        'h': dict(switch_id='1:INT_RELAY_B', relay_type='spdt', input_port=0, output_port='NO', topology_input_pin='in2', topology_output_pin='out2'),
    }
    nodes = [node('ce1', 'ce_port', ['out'], {'out': 'output'}), node('ce2', 'ce_port', ['out'], {'out': 'output'}),
        node('sw', 'switch_slot', ['in1', 'in2', 'out1', 'out2'], {'in1': 'input', 'in2': 'input', 'out1': 'output', 'out2': 'output'},
            internal_paths=[pair('in1', 'out1'), pair('in2', 'out2')], instrument_category_id=category_id),
        node('pv', 'probe', ['in'], {'in': 'input'}, probe_id=0, polarization='V', rf_path_selection=dict(connection_ids=['iv', 'ov'], switch_mappings=[dict(node_id='sw', path_name='v')])),
        node('ph', 'probe', ['in'], {'in': 'input'}, probe_id=0, polarization='H', rf_path_selection=dict(connection_ids=['ih', 'oh'], switch_mappings=[dict(node_id='sw', path_name='h')]))]
    nodes[0]['label'], nodes[1]['label'] = 'B1.1', 'B1.2'
    edges = [edge('iv', 'ce1', 'sw', 'out', 'in1'), edge('ih', 'ce2', 'sw', 'out', 'in2'), edge('ov', 'sw', 'pv', 'out1'), edge('oh', 'sw', 'ph', 'out2')]
    topo = create('Task4 C09 原开关身份', nodes, edges)
    with SessionLocal() as db:
        connection = db.query(InstrumentConnection).filter_by(category_id=UUID(category_id)).one()
        default_only(db, topo['id'])
    results = []
    try:
        for fault in ('valid', 'missing_mapping', 'wrong_pair', 'relay_conflict'):
            params = dict(port_maps=copy.deepcopy(maps))
            if fault == 'missing_mapping':
                params['port_maps'] = {}
            elif fault == 'wrong_pair':
                params['port_maps']['v']['topology_input_pin'] = 'in2'
            elif fault == 'relay_conflict':
                params['port_maps']['h']['switch_id'] = '1:INT_RELAY_A'
            call('PUT', '/instruments/rfSwitch', dict(connection=dict(connection_params=params)))
            with SessionLocal() as db:
                before_jobs = db.query(DiagnosticRun).count()
                try:
                    actual = orchestrate_switch_topology(db, chamber_id)
                    assert fault == 'valid', fault
                    identities = [row.execution_route_identity for row in actual.probe_bindings]
                    assert all(row['internal_paths'] for row in identities)
                    assert sorted((row.connection_id, row.ce_port) for row in actual.probe_bindings) == [('oh', 'B1.2'), ('ov', 'B1.1')]
                    results.append(dict(fault=fault, identities=identities))
                except ValueError as error:
                    assert fault != 'valid', str(error)
                    results.append(dict(fault=fault, rejected=str(error)))
                assert db.query(DiagnosticRun).count() == before_jobs
            call('GET', endpoint(topo))
    finally:
        # 专用库恢复本组合法Mock映射，供随后同图真实UI保存；不是恢复用户配置。
        call('PUT', '/instruments/rfSwitch', dict(connection=dict(connection_params=dict(port_maps=maps))))
    print(json.dumps(dict(row='C09', topology_id=topo['id'], results=results, retained_valid_mock_mapping=True,
        boundary='仅生产builder零I/O；原映射/relay身份，无真实开关动作'), ensure_ascii=False))


def freeze_evidence():
    nodes = [node('ce', 'ce_port', ['out'], {'out': 'output'}),
        node('pad', 'pad', ['in', 'out'], {'in': 'input', 'out': 'output'}, internal_paths=[pair()]),
        node('p', 'probe', ['in'], {'in': 'input'}, probe_id=0, polarization='V', rf_path_selection=dict(connection_ids=['a', 'b'], switch_mappings=[]))]
    nodes[0]['label'] = 'B1.1'
    topo = create('Task4 C12 无开关冻结两端', nodes, [edge('a', 'ce', 'pad'), edge('b', 'pad', 'p')])
    results = []
    with SessionLocal() as db:
        default_only(db, topo['id'])
        row = db.get(SwitchTopology, UUID(topo['id']))
        original_nodes, original_edges = copy.deepcopy(row.nodes), copy.deepcopy(row.connections)
        for legacy in (False, True):
            start_nodes = copy.deepcopy(original_nodes)
            if legacy:
                del start_nodes[1]['params']['internal_paths']
            row.nodes, row.connections = start_nodes, copy.deepcopy(original_edges)
            db.commit()
            frozen = resolve_effective_route_compensation(db, lab_id, 'mimo_ota', 2595.)
            frozen['execution_id'] = str(uuid4())
            frozen['digest'] = canonical_payload_digest(frozen)
            execution = SimpleNamespace(id=UUID(frozen['execution_id']), config={'route_calibration_freeze': frozen})
            before = read_execution_route_compensation(execution)
            actual = orchestrate_switch_topology(db, chamber_id)
            assert frozen_route_identity_error(db, frozen, resolved_topology=actual) is None
            assert frozen_route_identity_error(db, frozen) is None
            assert all(item['value_db'] is None and item['source_kind'] == 'unavailable' for item in frozen['route_entries'])
            candidate = copy.deepcopy(original_nodes)
            edges = copy.deepcopy(original_edges)
            if not legacy:
                candidate[1]['params'].update(ports=['new', 'out'], port_directions={'new': 'input', 'out': 'output'}, internal_paths=[pair('new', 'out')])
                edges[0]['target_pin'] = 'new'
            row.nodes, row.connections = candidate, edges
            db.commit()
            actual = orchestrate_switch_topology(db, chamber_id)
            db_error = frozen_route_identity_error(db, frozen)
            actual_error = frozen_route_identity_error(db, frozen, resolved_topology=actual)
            print(json.dumps(dict(freeze_probe=dict(legacy=legacy, frozen=frozen, db_error=db_error, actual_error=actual_error,
                actual_topology_id=actual.topology_id, actual_identities=[binding.execution_route_identity for binding in actual.probe_bindings])), ensure_ascii=False), flush=True)
            assert db_error and actual_error
            assert read_execution_route_compensation(execution) == before
            results.append(dict(legacy=legacy, frozen=before, db_current_error=db_error, actual_target_error=actual_error,
                actual_identities=[binding.execution_route_identity for binding in actual.probe_bindings]))
        row.nodes, row.connections = original_nodes, original_edges
        db.commit()
    call('GET', endpoint(topo))
    print(json.dumps(dict(row='C12', topology_id=topo['id'], results=results, boundary='纯builder/冻结读取补证；未创建真实执行、无量值/CE/ASC动作'), ensure_ascii=False))


def reference_evidence():
    with SessionLocal() as db:
        history = call('GET', f'/lab-profiles/{lab_id}/fixed-route-acquisitions')
        source = db.get(SwitchTopology, UUID(history[0]['result']['request']['topology_id']))
        nodes, edges, modes = copy.deepcopy(source.nodes), copy.deepcopy(source.connections), copy.deepcopy(source.operating_modes)
    nodes += [node('refpa', 'amplifier', ['IN', 'OUT'], {'IN': 'input', 'OUT': 'output'}, internal_paths=[pair('IN', 'OUT')], connection_scope='calibration'),
        node('rxcable', 'receive_cable', ['IN', 'OUT'], {'IN': 'input', 'OUT': 'output'}, internal_paths=[pair('IN', 'OUT')], connection_scope='calibration')]
    next(item for item in edges if item['id'] == 'r3').update(target='refpa', target_pin='IN')
    edges += [edge('r4', 'refpa', 'rxcable', 'OUT', 'IN'), edge('r5', 'rxcable', 'sa', 'OUT', 'IN')]
    modes[1]['active_connections'] += ['r4', 'r5']
    topo = create('Task4 C08 参考PA与接收线', nodes, edges, modes)
    with SessionLocal() as db:
        default_only(db, topo['id'])
    route_url = f'/lab-profiles/{lab_id}/route-calibration-paths?topology_id={topo["id"]}&operating_mode=mimo_ota'
    call('GET', route_url)
    results = []
    with SessionLocal() as db:
        row = db.get(SwitchTopology, UUID(topo['id']))
        baseline_nodes, baseline_edges = copy.deepcopy(row.nodes), copy.deepcopy(row.connections)
        for ident, incoming, outgoing in (('refpa', 'r3', 'r4'), ('rxcable', 'r4', 'r5')):
            for explicit in (True, False):
                for fault in ('pair', 'incoming', 'outgoing', 'both'):
                    if not explicit and fault == 'pair':
                        continue
                    ns, es = copy.deepcopy(baseline_nodes), copy.deepcopy(baseline_edges)
                    target = next(item for item in ns if item['id'] == ident)
                    if not explicit:
                        del target['params']['internal_paths']
                    if fault == 'pair':
                        target['params']['internal_paths'] = []
                    if fault in ('incoming', 'both'):
                        del next(item for item in es if item['id'] == incoming)['target_pin']
                    if fault in ('outgoing', 'both'):
                        del next(item for item in es if item['id'] == outgoing)['source_pin']
                    # 显式标注的历史脏形态fixture，不是经HTTP成功保存的新图。
                    row.nodes, row.connections = ns, es
                    db.commit()
                    rejected = call('GET', route_url, expected=422)
                    assert ident in rejected['detail']
                    fetched = call('GET', endpoint(topo))
                    assert fetched['connections'] == es
                    results.append(dict(node=ident, explicit=explicit, fault=fault, rejected=rejected, fixture_kind='专用库ORM构造非法历史形态'))
        row.nodes, row.connections = baseline_nodes, baseline_edges
        db.commit()
    call('GET', route_url)
    print(json.dumps(dict(row='C08', topology_id=topo['id'], reference_results=results), ensure_ascii=False))


def final_orm_evidence():
    log = Path(os.environ['PC04A4C_MATRIX_LOG'])
    matrix = json.loads(log.read_text().splitlines()[1])
    assert not matrix.get('failed'), matrix.get('error')
    sparse = []
    for exchange in matrix['calls']:
        graph = exchange.get('response')
        if (exchange['row'] == 'C08' and exchange['method'] == 'GET' and isinstance(graph, dict)
                and 'connections' in graph and any('source_pin' not in edge or 'target_pin' not in edge for edge in graph['connections'])):
            service = TopologyService(graph)
            assert service.get_end_to_end_loss('ce', 'p') is None
            sparse.append(dict(topology_id=graph['id'], loss=None, saved_connections=graph['connections']))
    assert len(sparse) == 6, len(sparse)
    with SessionLocal() as db:
        matches = []
        for value in matrix['rows']:
            row = db.get(SwitchTopology, UUID(value['topology_id']))
            # C11/C16以后源行不会被展示副本替代；每行JSON依据可独立检索。
            matches.append(dict(matrix_row=value['id'], source_id=str(row.id), display_id=value['display_topology_id'], exists=True))
        assert db.query(DiagnosticRun).count() == 2
        assert all(row.driver_mode == 'mock' for row in db.query(InstrumentCategory))
        assert all(binding['driver_mode'] == 'mock' for row in db.query(LabProfile) for binding in row.instrument_bindings)
        print(json.dumps(dict(row='ORM', database=url, sparse_bfs=sparse, source_display_rows=matches,
            topology_rows=db.query(SwitchTopology).count(), diagnostic_runs=2, all_categories_and_bindings_mock=True), ensure_ascii=False))


def binding_evidence():
    graphs = call('GET', f'/switch-topologies?lab_profile_id={lab_id}&limit=100')['items']
    topo = next(graph for graph in graphs if graph['name'] == 'Task4 C16 两端unknown')
    call('PATCH', endpoint(topo), dict(is_active=True))
    route_url = f'/lab-profiles/{lab_id}/route-calibration-paths?topology_id={topo["id"]}&operating_mode=mimo_ota'
    fixed_url = f'/lab-profiles/{lab_id}/fixed-route-acquisitions'
    before = call('GET', fixed_url)
    with SessionLocal() as db:
        default_only(db, topo['id'])
        profile = db.get(LabProfile, lab_id)
        bindings = copy.deepcopy(profile.instrument_bindings)
        analyzer = db.query(InstrumentCategory).filter_by(category_key='signalAnalyzer').one()
        profile.instrument_bindings = [binding for binding in bindings if binding['category_id'] != str(analyzer.id)]
        db.commit()
    try:
        route = call('GET', route_url)[0]
        body = dict(topology_id=topo['id'], chain_id=route['chain_id'], route_digest=route['route_digest'],
            configuration_digest=route['configuration_digest'], frequency_mhz=2595., requested_power_dbm=-30.,
            reference_antenna='Task4明确方向但缺绑定', receive_cable_loss_db=2., receive_cable_source='隔离fixture',
            fixed_route_confirmed=True, safety_confirmed=True, sample_count=2)
        rejection = call('POST', fixed_url, body, 422)
        assert '绑定' in str(rejection) or 'signalAnalyzer' in str(rejection), rejection
        assert call('GET', fixed_url) == before
    finally:
        with SessionLocal() as db:
            db.get(LabProfile, lab_id).instrument_bindings = bindings
            db.commit()
    for run in before:
        route = run['result']['configuration']['route_selection']
        adoption = dict(acquisition_run_id=run['run_id'], route_digest=route['route_digest'],
            expected_current_application_id=None, idempotency_key=str(uuid4()), confirmed=True,
            adoption_valid_until='2026-10-28T00:00:00Z')
        call('POST', f'/lab-profiles/{lab_id}/route-calibration-applications', adoption, 422)
    assert call('GET', fixed_url) == before
    print(json.dumps(dict(row='C16', topology_id=topo['id'], missing_binding_rejected=rejection,
        history_count=len(before), adoption_rejected=len(before), restored_bindings=True), ensure_ascii=False))


def atomic_evidence():
    history = call('GET', f'/lab-profiles/{lab_id}/fixed-route-acquisitions')
    topology_id = history[0]['result']['request']['topology_id']
    graph = call('GET', f'/switch-topologies/{topology_id}?lab_profile_id={lab_id}')
    other = next(row for row in labs if row['name'] == 'PC04A4c内部通路乙')

    def snapshot():
        with SessionLocal() as db:
            graphs = [dict(id=str(row.id), name=row.name, active=row.is_active, default=row.is_default,
                nodes=copy.deepcopy(row.nodes), connections=copy.deepcopy(row.connections), modes=copy.deepcopy(row.operating_modes))
                for row in db.query(SwitchTopology).order_by(SwitchTopology.id)]
            histories = [dict(id=str(row.id), evidence=copy.deepcopy(row.sequence_evidence))
                for row in db.query(DiagnosticRun).order_by(DiagnosticRun.id)]
            return dict(graphs=graphs, histories=histories)

    before = snapshot()
    bad = copy.deepcopy(graph['nodes'])
    next(node for node in bad if node['id'] == 'pa')['params']['internal_paths'] = []
    create_data = dict(name='Task4禁止出现默认行', is_default=True, lab_profile_id=str(lab_id), switch_category_id=category_id,
        nodes=bad, connections=graph['connections'], operating_modes=graph['operating_modes'])
    call('POST', '/switch-topologies', create_data, 422)
    call('PATCH', endpoint(graph), dict(nodes=bad, name='禁止写入', is_default=True), 422)
    call('PATCH', endpoint(graph), dict(operating_modes=[dict(id='mimo_ota', active_connections=['missing-edge'])]), 422)
    call('PATCH', f'/switch-topologies/{topology_id}?lab_profile_id={other["id"]}', dict(name='cross'), 409)
    call('POST', f'/switch-topologies/import/from-template?switch_category_id={category_id}&lab_profile_id=bad&template_id=caict_v4&replace_existing=true', expected=422)
    call('POST', f'/switch-topologies/import/from-template?switch_category_id={category_id}&lab_profile_id={lab_id}&template_id=does_not_exist&replace_existing=true', expected=404)
    after = snapshot()
    assert before == after
    call('GET', endpoint(graph))
    print(json.dumps(dict(row='C06', orm_before=before, orm_after=after, byte_identical=True,
        digest=canonical_payload_digest(before), graph_count=len(before['graphs']), history_count=len(before['histories'])), ensure_ascii=False))


def reference_preview_evidence():
    fixed_url = f'/lab-profiles/{lab_id}/fixed-route-acquisitions'
    before = call('GET', fixed_url)
    topo_id = before[0]['result']['request']['topology_id']
    topo = call('GET', f'/switch-topologies/{topo_id}?lab_profile_id={lab_id}')
    with SessionLocal() as db:
        default_only(db, topo_id)
    route_url = f'/lab-profiles/{lab_id}/route-calibration-paths?topology_id={topo_id}&operating_mode=mimo_ota'
    route = call('GET', route_url)[0]
    selected = call('GET', route_url + '&selection_scope=individual')[0]
    body = dict(topology_id=topo_id, chain_ids=['n4'], frequencies_mhz=[2595.],
        references=[dict(chain_id='n4', frequency_mhz=2595., reference_antenna='Task4参考摘要', receive_cable_loss_db=2., receive_cable_source='隔离fixture')],
        requested_power_dbm=-30., sample_count=2, fixed_route_confirmed=True, safety_confirmed=True)
    batch_url = f'/lab-profiles/{lab_id}/route-calibration-batches'
    preview = call('POST', batch_url + '/preview', body)
    nodes, edges = copy.deepcopy(topo['nodes']), copy.deepcopy(topo['connections'])
    ref = next(node for node in nodes if node['id'] == 'ref')
    pin = ref['params']['ports'][0] + '_NEXT'
    ref['params'].update(ports=[pin, 'OUT'], port_directions={pin: 'input', 'OUT': 'output'}, internal_paths=[pair(pin, 'OUT')])
    next(edge for edge in edges if edge['id'] == 'r2')['target_pin'] = pin
    call('PATCH', endpoint(topo), dict(nodes=nodes, connections=edges))
    changed = call('GET', route_url)[0]
    changed_selected = call('GET', route_url + '&selection_scope=individual')[0]
    assert changed['route_digest'] != route['route_digest']
    assert changed['configuration_digest'] == route['configuration_digest']
    assert changed_selected['configuration_digest'] != selected['configuration_digest']
    stale = call('POST', batch_url, {**body, 'preview_digest': preview['preview_digest']}, 422,
        headers={'Idempotency-Key': str(uuid4())})
    assert '预览摘要' in stale['detail']
    assert call('GET', fixed_url) == before
    print(json.dumps(dict(row='C11', segment='reference', before=route, after=changed,
        selected_before=selected['configuration_digest'], selected_after=changed_selected['configuration_digest'],
        stale_preview_rejected=stale, history_unchanged=True), ensure_ascii=False))


if __name__ == '__main__':
    {'switch': switch_evidence, 'freeze': freeze_evidence, 'reference': reference_evidence, 'orm': final_orm_evidence,
        'binding': binding_evidence, 'atomic': atomic_evidence, 'reference_preview': reference_preview_evidence}[sys.argv[1]]()
