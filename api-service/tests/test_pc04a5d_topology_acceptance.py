"""5d 真实HTTP→原始持久化→正式消费者；不替换资格，不制造新实测。"""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

# conftest 导入 app 之前必须由独立 CLI bootstrap；这里拒绝默认库和未准备的库。
assert re.fullmatch(r'sqlite:////tmp/pc04a5d-[A-Za-z0-9]+/test\.sqlite', os.environ.get('DATABASE_URL', ''))
assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
assert Path(os.environ['DATABASE_URL'].removeprefix('sqlite:///')).is_file()

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db.database import Base, get_db
from app.main import app
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.services.bootstrap import run_bootstrap_on_startup
from app.services.mimo_ota.switch_orchestrator import _build_probe_binding, orchestrate_switch_topology
from app.services.calibration.rf_chain_resolver import resolve_rf_chains
from app.services.topology_service import TopologyService
from scripts.pc04a5c_independent_pa import build_candidate
from tests.pc04a5d_browser_fixture import (SOURCE, audit_mock, canonical_hash,
    configure_mock, declaration_graph, seed_world, verify_hal)

ROOT = '/api/v1/switch-topologies'
HISTORY = ('route_calibration_applications', 'route_calibration_selections',
           'probe_path_loss_calibrations', 'diagnostic_runs')
EVIDENCE = Path(os.environ['DATABASE_URL'].removeprefix('sqlite:///')).parent / 'receipts' / (
    'attempt-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8])


def raw_table(db, table):
    """SQL原始全部列；保留JSON字符串、null和缺键，不经响应模型归一化。"""
    return sorted([dict(row) for row in db.execute(text(f'SELECT * FROM {table}')).mappings()],
                  key=lambda row: str(row.get('id')))


def protected(db, source_id):
    return dict(source=next(r for r in raw_table(db,'switch_topologies') if r['id'].replace('-','') == str(source_id).replace('-','')),
        revisions=[r for r in raw_table(db,'switch_topology_revisions')
                   if r['topology_id'].replace('-','') == str(source_id).replace('-','')],
        bindings=raw_table(db,'lab_profiles'),
        history={table:raw_table(db,table) for table in HISTORY})


def audit_topology(db, ident):
    db.expire_all()
    return dict(row=next(r for r in raw_table(db,'switch_topologies') if r['id'].replace('-','') == str(ident).replace('-','')),
        revisions=[r for r in raw_table(db,'switch_topology_revisions') if r['topology_id'].replace('-','') == str(ident).replace('-','')])


def graph(db, ident):
    db.expire_all()
    row = db.get(SwitchTopology, UUID(str(ident)))
    return deepcopy({key:getattr(row,key) for key in ('nodes','connections','operating_modes','version')})


@pytest.fixture
def world(tmp_path, monkeypatch, request):
    path = tmp_path / 'pc04a5d-world.sqlite'
    assert not path.exists()
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    assert run_bootstrap_on_startup(factory) is True
    with factory() as db:
        configure_mock(db)
        manifest = seed_world(db)
        # 只替换存储工厂；HAL的选型、初始化、is_mock_driver与shutdown仍为生产实现。
        with patch('app.db.database.SessionLocal', factory):
            hal_audit = asyncio.run(verify_hal())
        manifest['selected_hal'] = hal_audit
        manifest['database'] = str(path)
        receipts = dict(case=request.node.name, manifest=manifest, http=[], checks={})
        previous = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = lambda: db
        @asynccontextmanager
        async def no_lifespan(application):
            yield
        monkeypatch.setattr(app.router, 'lifespan_context', no_lifespan)
        with TestClient(app, raise_server_exceptions=False) as client:
            def capture(response):
                response.read()
                req = response.request
                receipts['http'].append(dict(method=req.method,url=str(req.url),
                    body=json.loads(req.content) if req.content else None,
                    status=response.status_code,response=response.json() if response.content else None))
            client.event_hooks = {'response':[capture], 'request':[]}
            try:
                yield db, client, manifest, receipts['checks'], factory
            finally:
                receipts['final_mock_audit'] = audit_mock(db)
                receipts['final_persistence'] = {table:raw_table(db,table) for table in
                    ('switch_topologies','switch_topology_revisions',*HISTORY)}
                EVIDENCE.mkdir(parents=True,exist_ok=True)
                (EVIDENCE / (request.node.name + '.json')).write_text(
                    json.dumps(receipts,ensure_ascii=False,sort_keys=True,default=str,indent=2))
                app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
    engine.dispose()


def copy_source(world):
    db, client, manifest, _, _ = world
    scope = {'lab_profile_id':manifest['labs'][0]['lab_id']}
    response = client.post(f"{ROOT}/{manifest['source_id']}/copy", params=scope,json={'name':'5d隔离PA演练副本'})
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['id'] != manifest['source_id']
    assert row['revision'] == 1 and row['is_active'] is False and row['is_default'] is False
    return f"{ROOT}/{row['id']}", scope


def candidate_saved(world):
    _, client, _, _, _ = world
    url, scope = copy_source(world)
    candidate, routes = build_candidate(json.loads(SOURCE.read_text()))
    response = client.patch(url,params=scope,json={'expected_revision':1,**candidate})
    assert response.status_code == 200 and response.json()['revision'] == 2, response.text
    return url, scope, candidate, routes


def test_import_guard_rejects_without_app_import_or_database(tmp_path):
    # 失败守卫在独立Python进程中验证；不借用已导入app的pytest进程证明。
    code = "from tests.pc04a5d_browser_fixture import checked_path; import sys\ntry: checked_path('browser')\nexcept AssertionError: assert 'app.main' not in sys.modules; print('guard-before-app'); sys.exit(7)\nsys.exit(9)"
    valid_directory = Path(tempfile.mkdtemp(prefix='pc04a5d-',dir='/tmp'))
    valid_url = f'sqlite:///{valid_directory}/browser.sqlite'
    for changes in ({'DATABASE_URL':f'sqlite:///{tmp_path}/forbidden.sqlite'},
                    {'DATABASE_URL':os.environ['DATABASE_URL']},
                    {'DATABASE_URL':valid_url,'USE_MOCK_INSTRUMENTS':'false'},
                    {'DATABASE_URL':valid_url,'BOOTSTRAP_ON_STARTUP':'false'}):
        env = {**os.environ,**changes}
        result = subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True)
        assert result.returncode == 7 and result.stdout.strip() == 'guard-before-app', result
    assert not (tmp_path/'forbidden.sqlite').exists()
    assert not (valid_directory/'browser.sqlite').exists()


def test_d01_copy_rename_keep_source_raw_and_execution_choice(world):
    db, client, manifest, checks, _ = world
    source_id = manifest['source_id']; lab = UUID(manifest['labs'][0]['lab_id'])
    chamber = UUID(manifest['labs'][0]['chamber_id'])
    before = protected(db, source_id)
    original = graph(db,source_id)
    selected = orchestrate_switch_topology(db,chamber).topology_id
    assert str(selected) == source_id
    url, scope = copy_source(world)
    ident = url.rsplit('/',1)[1]
    expected = deepcopy(original)
    for edge in expected['connections']:
        for key in ('calibrated_loss_db','calibrated_phase_deg'):
            if key in edge: edge[key] = None
    assert graph(db,ident) == expected
    before_copy = audit_topology(db,ident)
    response = client.patch(url,params=scope,json={'name':'5d仅改名','expected_revision':1})
    assert response.status_code == 200 and response.json()['revision'] == 2, response.text
    after_copy = audit_topology(db,ident)
    assert after_copy['row']['updated_at'] == before_copy['row']['updated_at']
    assert graph(db,ident) == expected
    assert str(orchestrate_switch_topology(db,chamber).topology_id) == source_id
    assert resolve_rf_chains(db,lab).topology_id == source_id
    after = protected(db,source_id)
    # 本副本的修订追加不应混进“原图历史不变”的比较。
    before['revisions'] = [r for r in before['revisions'] if r['topology_id'].replace('-','') == source_id.replace('-','')]
    after['revisions'] = [r for r in after['revisions'] if r['topology_id'].replace('-','') == source_id.replace('-','')]
    assert after == before
    checks.update(source_before=before,source_after=after,copy_before=before_copy,copy_after=after_copy,
                  selected_topology_id=str(selected),raw_copy_hash=canonical_hash(expected))


def test_d04_d05_legal_r2_restores_as_r4_but_r1_rejected_without_writes(world):
    db, client, manifest, checks, _ = world
    source_before = protected(db,manifest['source_id'])
    url,scope,candidate,routes = candidate_saved(world)
    ident = url.rsplit('/',1)[1]
    assert client.get(url+'/revisions',params=scope).status_code == 200
    assert client.get(url+'/revisions/1',params=scope).status_code == 200
    branches = []
    for endpoint in ('restore-preview','restore'):
        before = audit_topology(db,ident)
        response = client.post(url+'/'+endpoint,params=scope,json={'revision':1,'expected_revision':2})
        assert response.status_code == 422, response.text
        assert audit_topology(db,ident) == before
        branches.append(dict(endpoint=endpoint,status=422,before=before,after=audit_topology(db,ident)))
    changed = deepcopy(candidate)
    next(n for n in changed['nodes'] if n['id']==routes['routes'][0]['pa_node_id'])['position']['x'] += 31
    response = client.patch(url,params=scope,json={'expected_revision':2,**changed})
    assert response.status_code == 200 and response.json()['revision'] == 3, response.text
    before = audit_topology(db,ident)
    response = client.post(url+'/restore-preview',params=scope,json={'revision':2,'expected_revision':3})
    assert response.status_code == 200, response.text
    assert audit_topology(db,ident) == before
    response = client.post(url+'/restore',params=scope,json={'revision':2,'expected_revision':3})
    assert response.status_code == 200 and response.json()['revision'] == 4, response.text
    after = audit_topology(db,ident)
    assert graph(db,ident) == {**candidate,'version':json.loads(SOURCE.read_text())['version']}
    assert all(row in after['revisions'] for row in before['revisions'])
    assert after['row']['is_active'] == after['row']['is_default'] == 0
    protected_after = protected(db,manifest['source_id'])
    assert protected_after == source_before
    checks.update(branches=branches,r3=before,r4=after,candidate_hash=canonical_hash(candidate),
                  route_manifest_hash=canonical_hash(routes))


@pytest.mark.parametrize('operation',['patch','restore-preview','restore'])
@pytest.mark.parametrize('token',['stale','missing'])
def test_d05_conflict_and_missing_token_are_zero_write(world,operation,token):
    db,client,_,checks,_ = world
    url,scope,_,_ = candidate_saved(world); ident = url.rsplit('/',1)[1]
    body = {'name':'不能写入'} if operation=='patch' else {'revision':2}
    if token=='stale': body['expected_revision']=1
    before = audit_topology(db,ident)
    response = (client.patch(url,params=scope,json=body) if operation=='patch' else
                client.post(url+'/'+operation,params=scope,json=body))
    assert response.status_code == (409 if token=='stale' else 422), response.text
    assert audit_topology(db,ident) == before
    checks.update(before=before,after=audit_topology(db,ident))


def test_d06_shared_chamber_not_cross_lab_data_isolation(world):
    db,client,manifest,checks,_ = world
    url,scope,_,_ = candidate_saved(world); ident = url.rsplit('/',1)[1]
    shared = {'lab_profile_id':manifest['labs'][1]['lab_id']}
    other = {'lab_profile_id':manifest['labs'][2]['lab_id']}
    first = client.get(url,params=scope); second = client.get(url,params=shared)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    for params in (scope,shared):
        listing = client.get(ROOT,params=params)
        assert listing.status_code == 200
        assert next(r for r in listing.json()['items'] if r['id']==ident) == first.json()
    before = audit_topology(db,ident)
    requests = [('GET',url,None),('POST',url+'/copy',{'name':'越界'}),
                ('PATCH',url,{'name':'越界','expected_revision':2}),
                ('POST',url+'/restore-preview',{'revision':2,'expected_revision':2}),
                ('POST',url+'/restore',{'revision':2,'expected_revision':2}),
                ('GET',url+'/revisions',None),('GET',url+'/revisions/2',None)]
    for method,target,body in requests:
        response = client.request(method,target,params=other,json=body)
        assert response.status_code == 409, response.text
        assert audit_topology(db,ident) == before
    checks.update(shared_record=first.json(),before=before,after=audit_topology(db,ident))


def full_bindings(data):
    nodes = {n['id']:n for n in data['nodes']}
    mode = next(m for m in data['operating_modes'] if m['id']=='mimo_ota')
    active = [e for e in data['connections'] if e['id'] in mode['active_connections']]
    assert len([e for e in active if e['target']=='ce_f64']) == 4
    return [_build_probe_binding(e,nodes,active) for e in active if nodes[e['target']]['type']=='probe']


def test_d07_d08_complete_32_routes_and_unknown_nominal_consumers(world):
    from app.services.declared_rf_routes import resolve_saved_rf_path
    from app.schemas.topology_internal_paths import validate_internal_traversals
    from app.services.topology_loss import effective_connection_loss, loss_sources_for_path, loss_source_for_terminal
    db,client,manifest,checks,_ = world
    url,scope,candidate,routes = candidate_saved(world)
    saved = graph(db,url.rsplit('/',1)[1]); source = json.loads(SOURCE.read_text())
    expected = {(f'B{i+1}',p,q) for i,(p,q) in enumerate(
        (p,q) for p in [1,9,2,10,3,11,4,12,5,13,6,14,7,15,8,16] for q in 'VH')}
    identities = lambda rows:{(r.ce_port,r.probe_id,r.polarization) for r in rows}
    assert identities(full_bindings(source)) == identities(full_bindings(saved)) == expected
    assert {(r['ce_port'],r['probe_id'],r['polarization']) for r in routes['routes']} == expected
    assert resolve_rf_chains(db,UUID(manifest['labs'][0]['lab_id'])).topology_id == manifest['source_id']
    assert identities(resolve_rf_chains(db,UUID(manifest['labs'][0]['lab_id'])).chains) == expected
    complete = {}
    for label,data in [('source',source),('candidate',saved)]:
        paths = TopologyService(data).resolve_paths('mimo_ota')
        assert {p.target_node.id for p in paths} == {r['probe_node_id'] for r in routes['routes']}
        assert len(paths)==32
        if label=='candidate': assert all(p.total_loss_db is None for p in paths)
        complete[label] = [dict(source=p.source_node.id,target=p.target_node.id,total_loss_db=p.total_loss_db) for p in paths]
    outputs = []
    replacement_ids = set()
    for route in routes['routes']:
        ids = route['replacement_connection_ids']; replacement_ids.update(ids)
        edges = [next(e for e in saved['connections'] if e['id']==ident) for ident in ids]
        nodes,selected = resolve_saved_rf_path(saved['nodes'],edges,ids[-1])
        assert [n['id'] for n in nodes] == ['ce_f64',route['pa_node_id'],route['probe_node_id']]
        pa = nodes[1]['params']
        assert pa['port_directions'] == {'in':'input','out':'output'}
        assert pa['gain_db'] == 20
        assert validate_internal_traversals(nodes,selected,active_connections=edges) == [
            dict(node_id=route['pa_node_id'],from_port='in',to_port='out')]
        assert [(e['source_pin'],e['target_pin']) for e in edges] == [(route['ce_port'],'in'),('out','in')]
        assert all(e['cable_loss_db'] is None and 'cable_length_m' not in e and
                   'loss_owner_connection_id' not in e for e in edges)
        losses = [effective_connection_loss(e) for e in loss_sources_for_path(nodes,edges,ids)]
        terminal = effective_connection_loss(loss_source_for_terminal(nodes,edges,ids))
        assert losses == [None,None] and terminal is None
        # 仅本路输出子图，不冒充上面保留四输入的完整模式解析。
        service = TopologyService(dict(nodes=nodes,connections=edges,operating_modes=[
            dict(id='mimo_ota',active_connections=ids)]))
        assert service.resolve_paths('mimo_ota')[0].total_loss_db is None
        matrix = service.get_calibration_matrix('mimo_ota')
        assert matrix and all(r['compensation_db'] is None for r in matrix.values())
        assert _build_probe_binding(edges[-1],{n['id']:n for n in nodes},edges).cable_loss_db is None
        outputs.append(dict(route=route,loss_sources=losses,terminal=terminal,matrix=matrix))
    assert len(replacement_ids)==64
    # 零值是独立小图；不修改unknown候选来凑反例。
    zero = declaration_graph()
    for edge in zero['connections']:
        edge['cable_loss_db']=0; edge.pop('calibrated_loss_db',None)
    assert TopologyService(zero).get_end_to_end_loss('ce','probe') == 0
    terminal = zero['connections'][1]
    assert _build_probe_binding(terminal,{n['id']:n for n in zero['nodes']},zero['connections']).cable_loss_db == 0
    checks.update(complete_mode=complete,output_subgraphs=outputs,identities=sorted(expected),zero_total=0)


@pytest.mark.parametrize('bad',['wrong-pin','reverse-pair','missing-in','missing-out'])
def test_d08_invalid_pa_routes_rejected_without_revision(world,bad):
    db,client,_,checks,_=world
    url,scope,candidate,routes = candidate_saved(world); ident=url.rsplit('/',1)[1]
    broken=deepcopy(candidate); route=routes['routes'][0]
    edges={e['id']:e for e in broken['connections']}
    if bad=='wrong-pin': edges[route['replacement_connection_ids'][0]]['target_pin']='absent'
    elif bad=='reverse-pair':
        next(n for n in broken['nodes'] if n['id']==route['pa_node_id'])['params']['internal_paths']=[dict(from_port='out',to_port='in')]
    elif bad.startswith('missing-'):
        removed=route['replacement_connection_ids'][0 if bad=='missing-in' else 1]
        broken['connections']=[e for e in broken['connections'] if e['id']!=removed]
    before=audit_topology(db,ident)
    response=client.patch(url,params=scope,json={'expected_revision':2,**broken})
    assert response.status_code==422,response.text
    assert audit_topology(db,ident)==before
    checks.update(before=before,after=audit_topology(db,ident))


def test_d08_saved_ce_identity_conflict_fails_loud_in_formal_consumer(world):
    # 裁决C：保存结构校验不是正式执行身份门；保存200不得冒充可执行。
    db,client,_,checks,_=world
    url,scope,candidate,routes=candidate_saved(world); ident=url.rsplit('/',1)[1]
    changed=deepcopy(candidate); route=routes['routes'][0]
    next(e for e in changed['connections'] if e['id']==route['replacement_connection_ids'][1])['ce_port']='B32'
    before=audit_topology(db,ident)
    response=client.patch(url,params=scope,json={'expected_revision':2,**changed})
    assert response.status_code==200 and response.json()['revision']==3,response.text
    saved=graph(db,ident)
    with pytest.raises(ValueError,match='完整通路中的CE输出口声明互相矛盾') as failure:
        full_bindings(saved)
    checks.update(before=before,after=audit_topology(db,ident),save_status=200,
                  formal_consumer_error=str(failure.value),boundary='保存不等于可执行')


def test_d11_d12_synthetic_saved_confirmation_once_and_history_immutable(world,monkeypatch):
    from app.models.diagnostic_run import DiagnosticRun
    from app.models.route_calibration import RouteCalibrationApplication,RouteCalibrationSelection
    from app.models.test_plan import TestExecution
    from app.schemas.route_calibration import RouteSelection,RouteApplicationRecord
    from app.services.mimo_ota.factory import build_mimo_ota_test_case
    from app.services.mimo_ota.route_calibration_freeze import (freeze_execution_route_compensation,
        read_execution_route_compensation,frozen_route_identity_error)
    from app.services.channel_engine_client import ChannelEngineClient
    from app.models.chamber import ChamberConfiguration
    db,client,manifest,checks,_=world
    lab=UUID(manifest['labs'][2]['lab_id']); ident=manifest['collection_id']; url=f'{ROOT}/{ident}'
    scope={'lab_profile_id':str(lab)}
    response=client.get(f'/api/v1/lab-profiles/{lab}/route-calibration-paths',params={
        'topology_id':ident,'operating_mode':'mimo_ota'})
    assert response.status_code==200,response.text
    selection=RouteSelection.model_validate(response.json()[0])
    diagnostic_id,application_id=uuid4(),uuid4()
    reference_digest=hashlib.sha256(b'PC04A5d synthetic stored reference').hexdigest()
    now=datetime.now(timezone.utc)
    boundary={'synthetic_fixture':True,'boundary':'仅已存confirmed消费者输入；未采集、未核采用资格'}
    record=RouteApplicationRecord(id=application_id,predecessor_id=None,acquisition_run_id=diagnostic_id,
        selection_snapshot=selection,method='fixed_route_net_loss_v1',frequency_mhz=2595,
        coverage_snapshot={'frequency_mhz':2595,'polarization':selection.polarization,
            'reference_identity_digest':reference_digest,'adoption_valid_until':(now+timedelta(days=1)).isoformat(),
            'synthetic_fixture':True},
        reference_snapshot={'synthetic_fixture':True,'identity_description':'5d历史模型输入，非实测'},
        net_loss_db=28,adoption_evidence_snapshot={'measurement_provenance':'real',**boundary},
        operator_confirmed=True,certification_status='unknown',confirmed_at=now,confirmed_by=None)
    db.add(DiagnosticRun(id=diagnostic_id,lab_profile_id=lab,kind='scpi_sequence',
        target_name='PC04A5d synthetic stored history',success=False,params=boundary,sequence_evidence=boundary))
    db.flush()
    db.add(RouteCalibrationApplication(id=application_id,lab_profile_id=lab,acquisition_run_id=diagnostic_id,
        topology_id=UUID(ident),chain_id=selection.chain_id,idempotency_key=uuid4(),
        request_payload=boundary,record=record.model_dump(mode='json')))
    db.flush()
    db.add(RouteCalibrationSelection(lab_profile_id=lab,topology_id=UUID(ident),operating_mode='mimo_ota',
        chain_id=selection.chain_id,frequency_mhz=2595,reference_identity_digest=reference_digest,
        application_id=application_id,version=1)); db.commit()
    history={table:raw_table(db,table) for table in HISTORY}
    case,_=build_mimo_ota_test_case(db,name='5d synthetic消费者软件验收',lab_profile_id=lab,
        config_overrides={'frequency_hz':2595e6,'switch_mode_id':'mimo_ota'})
    def freeze():
        execution=TestExecution(test_case_id=case.id,status='pending',config={})
        db.add(execution); db.flush()
        frozen=freeze_execution_route_compensation(db,execution,case); db.commit()
        return execution,frozen
    first,frozen=freeze(); first_row=next(r for r in raw_table(db,'test_executions') if r['id']==first.id.hex)
    assert frozen['route_entries'][0]['source_kind']=='confirmed_route'
    assert frozen['route_entries'][0]['value_db']==28
    response=client.patch(url,params=scope,json={'name':'5d仅改名后恢复','expected_revision':0})
    assert response.status_code==200 and response.json()['revision']==1,response.text
    response=client.post(url+'/restore',params=scope,json={'revision':0,'expected_revision':1})
    assert response.status_code==200 and response.json()['revision']==2,response.text
    assert graph(db,ident)['connections'][1]['calibrated_loss_db'] is None
    second,frozen2=freeze()
    assert frozen2['route_entries'][0]['source_kind']=='confirmed_route'
    assert frozen2['route_entries'][0]['value_db']==28
    consumer=ChannelEngineClient(db)
    monkeypatch.setattr(consumer,'_query_phase_compensation',lambda *args,**kwargs:{})
    chamber=db.get(ChamberConfiguration,UUID(manifest['labs'][2]['chamber_id']))
    consumed=[]
    for payload in (frozen,frozen2):
        entries=consumer._query_calibration_entries(chamber.id,2595e6,chamber,
            path_loss_calibration=None,route_compensation=payload)
        assert len(entries)==1 and entries[0]['cable_loss_db']==28 and entries[0]['probe_gain_dbi']==0
        consumed.append(entries)
    changed=graph(db,ident)
    changed['connections'][0]['source_pin']='other'
    response=client.patch(url,params=scope,json={'expected_revision':2,**changed})
    assert response.status_code==200,response.text
    third,frozen3=freeze()
    assert all(r['source_kind']!='confirmed_route' for r in frozen3['route_entries'])
    assert frozen_route_identity_error(db,frozen) is not None
    assert read_execution_route_compensation(first)==frozen
    assert next(r for r in raw_table(db,'test_executions') if r['id']==first.id.hex)==first_row
    assert {table:raw_table(db,table) for table in HISTORY}==history
    checks.update(synthetic_boundary=boundary,selection=selection.model_dump(mode='json'),E1=frozen,E2=frozen2,E3=frozen3,
        consumer_entries=consumed,history_before=history,history_after={t:raw_table(db,t) for t in HISTORY},
        execution_ids=[str(e.id) for e in (first,second,third)])


def test_mock_real_start_progress_preview_and_confirmation_rejected(world,monkeypatch):
    from app.services.calibration import fixed_route_jobs as jobs
    from app.services.instrument_hal_service import InstrumentHALService,is_mock_driver
    from app.services.instrument_test_lease import InstrumentTestLease
    db,client,manifest,checks,factory=world
    lab=manifest['labs'][2]['lab_id']; ident=manifest['collection_id']
    hal=InstrumentHALService()
    with patch('app.db.database.SessionLocal',factory): asyncio.run(hal.initialize())
    assert hal.drivers and all(is_mock_driver(d) for d in hal.drivers.values())
    lease=InstrumentTestLease(lambda:hal)
    monkeypatch.setattr(jobs,'get_hal_service',lambda:hal)
    monkeypatch.setattr(jobs,'instrument_test_lease',lease.hold)
    monkeypatch.setattr(jobs,'SessionLocal',factory)
    try:
        runs=[]
        for _ in range(2):
            paths=client.get(f'/api/v1/lab-profiles/{lab}/route-calibration-paths',params={
                'topology_id':ident,'operating_mode':'mimo_ota'})
            assert paths.status_code==200,paths.text
            route=paths.json()[0]
            body=dict(chain_id=route['chain_id'],topology_id=ident,operating_mode='mimo_ota',
                route_digest=route['route_digest'],configuration_digest=route['configuration_digest'],
                frequency_mhz=2595,requested_power_dbm=-20,reference_antenna='5d Mock参考输入，非实测',
                receive_cable_loss_db=2,receive_cable_source='5d Mock参考声明',fixed_route_confirmed=True,
                safety_confirmed=True,sample_count=2)
            start=client.post(f'/api/v1/lab-profiles/{lab}/fixed-route-acquisitions',json=body)
            assert start.status_code==202,start.text
            run_id=start.json()['run_id']; target=f'/api/v1/lab-profiles/{lab}/fixed-route-acquisitions/{run_id}'
            deadline=time.monotonic()+15
            while True:
                progress=client.get(target)
                assert progress.status_code==200,progress.text
                value=progress.json()
                if value['status']!='running': break
                assert time.monotonic()<deadline,value
                time.sleep(.03)
            assert value['status']=='simulated',value
            assert value['result']['samples']==[] and value['result']['net_loss_db'] is None
            assert value['result']['formal_eligible'] is False
            preview=client.get(target+'/application-preview')
            assert preview.status_code==200,preview.text
            eligibility=preview.json()['eligibility']
            assert eligibility['measurement_provenance']=='simulated' and eligibility['eligible_for_adoption'] is False
            before={t:raw_table(db,t) for t in ('route_calibration_applications','route_calibration_selections')}
            rejected=client.post(f'/api/v1/lab-profiles/{lab}/route-calibration-applications',json={
                'acquisition_run_id':run_id,'route_digest':route['route_digest'],
                'expected_current_application_id':None,'idempotency_key':str(uuid4()),'confirmed':True,
                'adoption_valid_until':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
            assert rejected.status_code==422,rejected.text
            assert {t:raw_table(db,t) for t in before}==before
            runs.append(dict(run_id=run_id,progress=value,preview=preview.json(),confirmation_status=422))
        assert runs[0]['run_id']!=runs[1]['run_id']
        checks.update(runs=runs,hal={k:dict(class_name=type(d).__name__,is_mock_driver=is_mock_driver(d)) for k,d in hal.drivers.items()})
    finally:
        asyncio.run(hal.shutdown())
