"""库写入口的真实 HTTP/SQL 契约；夹具仅内存，不读取用户库。"""
import json
from copy import deepcopy
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology

ROOT = '/api/v1/switch-topologies'


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def graph(topology):
    return deepcopy([topology.nodes, topology.connections, topology.operating_modes])


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    old = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield session
    finally:
        if old is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = old
        session.close(); engine.dispose()


@pytest.fixture
def client(db):
    # 无 lifespan 的 TestClient；只走真实路由/SQL，不初始化硬件。
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def world(db):
    chambers = [create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'隔离暗室{i}') for i in range(2)]
    categories = [InstrumentCategory(category_key=f'switch{i}', category_name=f'开关{i}', driver_mode='mock') for i in range(2)]
    db.add_all(chambers + categories); db.flush()
    labs = [LabProfile(name=f'隔离Lab{i}', chamber_config_id=c.id, is_active=True) for i, c in enumerate(chambers)]
    labs.append(LabProfile(name='共享暗室Lab', chamber_config_id=chambers[0].id, is_active=True))
    db.add_all(labs); db.commit()
    return chambers, categories, labs


@pytest.fixture
def lab(world):
    return world[2][0]


@pytest.fixture
def source(db, world, lab):
    # 含旧字符串、缺键、null、布尔/数字和 opaque；结构仍可被真实 resolver 解析。
    nodes = [dict(id='ce', type='ce_port', label='B1.1', position={'x': 1, 'y': 2}, params={'ports': ['out']}),
             dict(id='probe', type='probe', label='探头0V', params={'ports': ['in'], 'probe_id': 0, 'polarization': 'V',
                 'opaque': {'number': '1', 'bool': True, 'null': None},
                 'rf_path_selection': {'connection_ids': ['e'], 'switch_mappings': []}})]
    edges = [dict(id='e', source='ce', source_pin='out', target='probe', target_pin='in',
                  cable_loss_db='2.5', calibrated_loss_db=8.5, calibrated_phase_deg=None,
                  opaque={'keep': [False, 0, '0', None]}),
             dict(id='unused', source='ce', source_pin='out', target='probe', target_pin='in')]
    row = SwitchTopology(switch_category_id=world[1][0].id, chamber_id=lab.chamber_config_id,
        name='原图', description='保留描述', version='旧版', site_name='隔离地点', system_model='旧型号',
        installed_by='测试夹具', installed_date=datetime(2019, 1, 1), nodes=nodes, connections=edges,
        operating_modes=[dict(id='mimo_ota', name='正常模式', active_connections=['e'], opaque={'keep': True})],
        is_active=True, is_default=True, updated_at=datetime(2020, 1, 1))
    row.update_statistics(); db.add(row); db.commit()
    return row


@pytest.fixture
def other_active(db, source):
    row = SwitchTopology(switch_category_id=source.switch_category_id, chamber_id=source.chamber_id,
        name='执行选择', nodes=deepcopy(source.nodes), connections=deepcopy(source.connections),
        operating_modes=deepcopy(source.operating_modes), is_active=True, updated_at=datetime(2021, 1, 1))
    row.update_statistics(); db.add(row); db.commit()
    return row


def copy_request(client, lab, source, **body):
    return client.post(f'{ROOT}/{source.id}/copy', params={'lab_profile_id': str(lab.id)}, json=body)


def test_copy_preserves_raw_except_calibration(client, db, lab, source, other_active):
    before = graph(source)
    selected = orchestrate_switch_topology(db, lab.chamber_config_id)
    assert selected.success and selected.topology_id == str(other_active.id)
    response = copy_request(client, lab, source, name='  接线副本  ')
    assert response.status_code == 201, response.text
    copied = db.get(SwitchTopology, UUID(response.json()['id']))
    assert copied.id != source.id and copied.name == '接线副本'
    assert copied.is_active is False and copied.is_default is False
    expected = deepcopy(before)
    for edge in expected[1]:
        for key in ('calibrated_loss_db', 'calibrated_phase_deg'):
            if key in edge:
                edge[key] = None
    assert raw(graph(copied)) == raw(expected)
    for key in ('description', 'version', 'site_name', 'system_model', 'installed_date', 'installed_by', 'chamber_id', 'switch_category_id'):
        assert getattr(copied, key) == getattr(source, key)
    assert copied.total_connections == len(before[1]) and copied.total_nodes == len(before[0])
    db.refresh(source)
    assert raw(graph(source)) == raw(before)
    assert orchestrate_switch_topology(db, lab.chamber_config_id).topology_id == selected.topology_id


def test_name_only_sql_preserves_timestamp_and_execution(client, db, lab, source, other_active):
    before, updated = graph(source), source.updated_at
    selected = orchestrate_switch_topology(db, lab.chamber_config_id).topology_id
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE switch_topologies'):
            statements.append(statement)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        response = client.patch(f'{ROOT}/{source.id}', params={'lab_profile_id': str(lab.id)}, json={'name': '  重命名  '})
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)
    assert response.status_code == 200, response.text
    db.expire_all(); db.refresh(source)
    assert source.updated_at == updated
    assert source.name == '重命名' and raw(graph(source)) == raw(before)
    assert orchestrate_switch_topology(db, lab.chamber_config_id).topology_id == selected
    assert any('updated_at=switch_topologies.updated_at' in sql for sql in statements), statements


def test_name_only_does_not_roll_back_a_newer_database_timestamp(client, db, lab, source):
    source_id = source.id
    cached = source.updated_at
    newer = datetime(2024, 1, 1)
    # 另一个SQL写入已提交新时间，ORM对象仍保留旧缓存；禁止把旧datetime写回。
    with db.bind.begin() as connection:
        connection.execute(update(SwitchTopology).where(SwitchTopology.id == source_id).values(updated_at=newer))
    assert source.updated_at == cached
    response = client.patch(f'{ROOT}/{source_id}', params={'lab_profile_id': str(lab.id)}, json={'name': '不回退时间'})
    assert response.status_code == 200, response.text
    db.expire_all(); db.refresh(source)
    assert source.updated_at == newer


def test_non_name_only_patch_keeps_existing_timestamp_semantics(client, db, lab, source):
    updated = source.updated_at
    response = client.patch(f'{ROOT}/{source.id}', params={'lab_profile_id': str(lab.id)},
                            json={'name': '联合元数据', 'description': '更新描述'})
    assert response.status_code == 200, response.text
    db.expire_all(); db.refresh(source)
    assert source.updated_at > updated and source.description == '更新描述'


@pytest.mark.parametrize('name', ['', '   ', None, 'x' * 201, 'a\x00b', 'a\nb', '\tb'])
@pytest.mark.parametrize('operation', ['copy', 'patch', 'create'])
def test_invalid_names_rejected_atomically(client, db, lab, source, name, operation):
    before = raw(graph(source)); count = db.query(SwitchTopology).count()
    if operation == 'copy':
        response = copy_request(client, lab, source, name=name)
    elif operation == 'patch':
        response = client.patch(f'{ROOT}/{source.id}', params={'lab_profile_id': str(lab.id)}, json={'name': name})
    else:
        response = client.post(ROOT, json={'name': name, 'lab_profile_id': str(lab.id), 'switch_category_id': str(source.switch_category_id)})
    assert response.status_code == 422, response.text
    db.expire_all(); db.refresh(source)
    assert source.name == '原图' and raw(graph(source)) == before
    assert db.query(SwitchTopology).count() == count


def test_duplicate_names_unicode_and_shared_lab_allowed(client, db, world, source):
    first = copy_request(client, world[2][0], source, name='可见中文\u200d名')
    second = copy_request(client, world[2][2], source, name='可见中文\u200d名')
    assert first.status_code == second.status_code == 201
    assert first.json()['name'] == second.json()['name']
    assert first.json()['id'] != second.json()['id']


@pytest.mark.parametrize('case, expected', [('other-chamber', 409), ('bad-lab', 422), ('missing-source', 404), ('extra', 422)])
def test_copy_scope_and_body_guard(client, db, world, lab, source, case, expected):
    count = db.query(SwitchTopology).count()
    lab_id = world[2][1].id if case == 'other-chamber' else uuid4() if case == 'bad-lab' else lab.id
    source_id = uuid4() if case == 'missing-source' else source.id
    body = {'name': '副本', **({'is_active': True} if case == 'extra' else {})}
    response = client.post(f'{ROOT}/{source_id}/copy', params={'lab_profile_id': str(lab_id)}, json=body)
    assert response.status_code == expected, response.text
    assert db.query(SwitchTopology).count() == count


def test_unserializable_source_rolls_back_before_commit(client, db, lab, source):
    nodes = deepcopy(source.nodes); nodes[0]['label'] = {'bad': 'object'}
    source.nodes = nodes; db.commit()
    count = db.query(SwitchTopology).count()
    response = copy_request(client, lab, source, name='不提交半成品')
    assert response.status_code == 422, response.text
    assert db.query(SwitchTopology).count() == count


def test_probe_missing_id_is_422_before_statistics_and_keeps_source(client, db, lab, source):
    nodes = deepcopy(source.nodes)
    nodes[1].pop('id')
    source.nodes = nodes; db.commit()
    before, count = raw(graph(source)), db.query(SwitchTopology).count()
    response = copy_request(client, lab, source, name='缺ID源图不能复制')
    assert response.status_code == 422, response.text
    db.expire_all(); db.refresh(source)
    assert raw(graph(source)) == before
    assert db.query(SwitchTopology).count() == count


@pytest.mark.parametrize('field', ['connections', 'nodes', 'operating_modes'])
@pytest.mark.parametrize('value', [None, [None]])
def test_malformed_raw_graph_is_422_without_partial_copy(client, db, lab, source, field, value):
    setattr(source, field, value); db.commit()
    count = db.query(SwitchTopology).count()
    response = copy_request(client, lab, source, name='损坏图不提交')
    assert response.status_code == 422, response.text
    assert db.query(SwitchTopology).count() == count


def test_copy_preserves_loss_owner_edges(client, db, lab, source):
    nodes = deepcopy(source.nodes)
    nodes[1]['params']['rf_path_selection']['connection_ids'] = ['e', 'alias']
    nodes.append(dict(id='wire', type='cable', label='整根线缆', params={'ports': ['in', 'out'],
        'port_directions': {'in': 'input', 'out': 'output'},
        'internal_paths': [{'from_port': 'in', 'to_port': 'out'}]}))
    edges = [dict(id='e', source='ce', source_pin='out', target='wire', target_pin='in',
                  cable_loss_db='2.5', calibrated_loss_db=4, calibrated_phase_deg=5),
             dict(id='alias', source='wire', source_pin='out', target='probe', target_pin='in',
                  cable_loss_db='2.5', loss_owner_connection_id='e', calibrated_loss_db=4),
             dict(id='unused', source='ce', source_pin='out', target='probe', target_pin='in',
                  calibrated_phase_deg=12)]
    source.nodes = nodes; source.connections = edges
    source.operating_modes = [dict(id='mimo_ota', name='正常', active_connections=['e', 'alias'])]
    db.commit()
    assert orchestrate_switch_topology(db, lab.chamber_config_id).success
    before = graph(source)
    response = copy_request(client, lab, source, name='归属副本')
    assert response.status_code == 201, response.text
    copied = db.get(SwitchTopology, UUID(response.json()['id']))
    expected = deepcopy(before)
    for edge in expected[1]:
        for key in ('calibrated_loss_db', 'calibrated_phase_deg'):
            if key in edge:
                edge[key] = None
    assert raw(graph(copied)) == raw(expected)
    assert copied.connections[1]['loss_owner_connection_id'] == 'e'
    db.refresh(source)
    assert raw(graph(source)) == raw(before)


def test_copy_leaves_all_external_evidence_rows_unchanged(client, db, lab, source):
    from app.models.route_calibration import RouteCalibrationApplication, RouteCalibrationSelection
    from app.models.probe_calibration import ProbePathLossCalibration, MultiFrequencyPathLoss
    application = RouteCalibrationApplication(lab_profile_id=lab.id, acquisition_run_id=uuid4(),
        topology_id=source.id, chain_id='e', idempotency_key=uuid4(),
        request_payload={'fixture': '不可当实测'}, record={'fixture': True, 'opaque': [None, '1', 1]})
    db.add(application); db.flush()
    selection = RouteCalibrationSelection(lab_profile_id=lab.id, topology_id=source.id, operating_mode='mimo_ota',
        chain_id='e', frequency_mhz=3500, reference_identity_digest='f' * 64, application_id=application.id, version=1)
    cert = ProbePathLossCalibration(chamber_id=source.chamber_id, lab_profile_id=lab.id, topology_id=source.id,
        frequency_mhz=3500, probe_path_losses={'fixture': '非实测'}, sgh_model='fixture', sgh_gain_dbi=0,
        use_mock=True, valid_until=datetime(2030, 1, 1))
    sweep = MultiFrequencyPathLoss(chamber_id=source.chamber_id, lab_profile_id=lab.id, topology_id=str(source.id),
        probe_id=0, polarization='V', freq_start_mhz=3500, freq_stop_mhz=3500, freq_step_mhz=1,
        num_points=1, frequency_points_mhz=[3500], path_loss_db=[0], use_mock=True, valid_until=datetime(2030, 1, 1))
    db.add_all([selection, cert, sweep]); db.commit()
    tables = [model.__table__ for model in (RouteCalibrationApplication, RouteCalibrationSelection,
                                            ProbePathLossCalibration, MultiFrequencyPathLoss)]
    def evidence():
        return json.dumps({table.name: [dict(row) for row in db.execute(table.select()).mappings()] for table in tables},
                          sort_keys=True, default=str)
    before = evidence()
    response = copy_request(client, lab, source, name='不复制采用和证书')
    assert response.status_code == 201, response.text
    db.expire_all()
    assert evidence() == before
    copied_id = UUID(response.json()['id'])
    assert db.query(RouteCalibrationApplication).filter_by(topology_id=copied_id).count() == 0
    assert db.query(RouteCalibrationSelection).filter_by(topology_id=copied_id).count() == 0


@pytest.mark.parametrize('replace', [False, True])
@pytest.mark.parametrize('has_existing', [False, True])
def test_template_only_appends_inactive_and_never_replaces(client, db, lab, source, monkeypatch, replace, has_existing):
    import app.api.switch_topology as api
    category = source.switch_category_id if has_existing else uuid4()
    before = raw(graph(source)); selected = orchestrate_switch_topology(db, lab.chamber_config_id).topology_id
    monkeypatch.setattr(api, '_load_template', lambda _: lambda: dict(name='模板草稿', is_active=True, is_default=True,
        nodes=[], connections=[], operating_modes=[]))
    response = client.post(f'{ROOT}/import/from-template', params={'lab_profile_id': str(lab.id),
        'switch_category_id': str(category), 'template_id': 'fixture', 'replace_existing': replace})
    assert response.status_code == (409 if has_existing and replace else 200), response.text
    if response.status_code == 200:
        imported = db.get(SwitchTopology, UUID(response.json()['id']))
        assert imported.is_active is False and imported.is_default is False
    db.expire_all(); db.refresh(source)
    assert raw(graph(source)) == before and source.is_default is True
    assert orchestrate_switch_topology(db, lab.chamber_config_id).topology_id == selected
