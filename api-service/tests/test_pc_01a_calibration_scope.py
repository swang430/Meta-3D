"""从真实 LabProfile HTTP 入口验证只读配置范围，不连接仪器。"""
import copy
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.lab_profile import LabProfile
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.models.probe import Probe
from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile


@pytest.fixture
def client(db_session):
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def snapshot(client, lab):
    response = client.get(f'/api/v1/lab-profiles/{lab.id}/calibration-scope')
    assert response.status_code == 200, response.text
    return response.json()


def compare(client, lab, baseline):
    return client.post(f'/api/v1/lab-profiles/{lab.id}/calibration-scope/compare',
                       json={'baseline': baseline})


def test_scope_uses_resolver_and_never_claims_physical_or_calibration_truth(client, lab_profile, db_session):
    before = db_session.query(LabProfile).count()
    value = snapshot(client, lab_profile)
    assert value['physical_identity'] == 'unverified'
    assert value['formal_eligible'] is False
    assert value['payload']['lab_profile_id'] == str(lab_profile.id)
    assert [(c['chain_id'], c['ce_port']) for c in value['payload']['chains']] == [
        ('conn_p0h', 'B1.2'), ('conn_p0v', 'B1.1')]
    result = compare(client, lab_profile, value)
    assert result.status_code == 200
    assert result.json()['changed_sections'] == []
    assert result.json()['requires_review'] is False  # 仅没有配置差异，不是校准可复用
    assert result.json()['formal_eligible'] is False
    assert db_session.query(LabProfile).count() == before


def test_rename_and_list_order_do_not_change_scope(client, lab_profile, topology_two_chains, db_session):
    baseline = snapshot(client, lab_profile)
    lab_profile.name = '更名不等于换实物'
    topology_two_chains.name = '新显示名称'
    topology_two_chains.connections = list(reversed(topology_two_chains.connections))
    db_session.commit()
    assert snapshot(client, lab_profile)['digest'] == baseline['digest']


def test_changed_port_identifies_affected_chain(client, lab_profile, topology_two_chains, db_session):
    baseline = snapshot(client, lab_profile)
    connections = copy.deepcopy(topology_two_chains.connections)
    connections[0]['ce_port'] = 'B9'
    topology_two_chains.connections = connections
    db_session.commit()
    result = compare(client, lab_profile, baseline).json()
    assert result['requires_review'] is True
    assert 'chains' in result['changed_sections']
    assert result['affected_chain_ids'] == ['conn_p0v']


def test_geometry_and_cross_lab_require_all_chains_review(client, lab_profile, chamber, db_session):
    baseline = snapshot(client, lab_profile)
    chamber.chamber_radius_m += 1
    db_session.commit()
    result = compare(client, lab_profile, baseline).json()
    assert 'chamber' in result['changed_sections']
    assert result['affected_chain_ids'] == ['conn_p0h', 'conn_p0v']
    clone = LabProfile(name='复制配置不是复制校准', chamber_config_id=chamber.id)
    db_session.add(clone)
    db_session.commit()
    result = compare(client, clone, baseline).json()
    assert 'lab_profile_id' in result['changed_sections']
    assert result['requires_review'] is True
    assert result['formal_eligible'] is False


def test_corrupt_baseline_rejected_and_missing_lab_controlled(client, lab_profile):
    baseline = snapshot(client, lab_profile)
    baseline['payload']['operating_mode'] = 'forged'
    assert compare(client, lab_profile, baseline).status_code == 422
    assert client.get(f'/api/v1/lab-profiles/{uuid.uuid4()}/calibration-scope').status_code == 422


def test_browser_number_roundtrip_keeps_same_snapshot(client, lab_profile):
    baseline = snapshot(client, lab_profile)
    # 浏览器 JSON.stringify(4.0) 为 4；不能将未改动的保存快照误判成损坏。
    def js_numbers(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: js_numbers(v) for k, v in value.items()}
        if isinstance(value, list):
            return [js_numbers(v) for v in value]
        return value
    response = compare(client, lab_profile, js_numbers(baseline))
    assert response.status_code == 200, response.text
    assert response.json()['changed_sections'] == []


def test_unknown_mode_remains_gap(client, lab_profile):
    value = client.get(f'/api/v1/lab-profiles/{lab_profile.id}/calibration-scope?operating_mode=missing').json()
    assert value['configuration_complete'] is False
    assert value['warnings']
    assert value['formal_eligible'] is False


def test_resources_show_saved_binding_drift_without_credentials(client, lab_profile, db_session):
    category = InstrumentCategory(category_key='channelEmulator', category_name='CE', driver_mode='mock', is_active=True)
    db_session.add(category)
    db_session.flush()
    connection = InstrumentConnection(category_id=category.id, endpoint='saved-endpoint',
                                      password_encrypted='must-not-leak', connection_params={'password': 'also-secret'})
    db_session.add(connection)
    lab_profile.instrument_bindings = [{'category_id': str(category.id), 'connection_endpoint': 'old-endpoint',
                                        'driver_mode': 'real', 'role': 'primary_channel_emulator'}]
    db_session.commit()
    baseline = snapshot(client, lab_profile)
    assert baseline['payload']['resources'][0]['saved']['endpoint'] == 'saved-endpoint'
    assert baseline['configuration_complete'] is False
    assert any('不一致' in w for w in baseline['warnings'])
    assert 'must-not-leak' not in str(baseline) and 'also-secret' not in str(baseline)
    connection.endpoint = 'new-device-config'
    db_session.commit()
    result = compare(client, lab_profile, baseline).json()
    assert 'resources' in result['changed_sections']
    assert result['affected_chain_ids'] == ['conn_p0h', 'conn_p0v']


@pytest.mark.parametrize('exists', [True, False])
def test_binding_warning_distinguishes_disabled_from_missing(client, lab_profile, db_session, exists):
    category_id = uuid.uuid4()
    if exists:
        db_session.add(InstrumentCategory(id=category_id, category_key='vna',
                                         category_name='矢量网络分析仪', is_active=False))
    lab_profile.instrument_bindings = [{'category_id': str(category_id)}]
    db_session.commit()
    value = snapshot(client, lab_profile)
    if exists:
        assert f'绑定仪器已停用：矢量网络分析仪（vna，{category_id}）' in value['warnings']
        assert not any('不存在' in warning for warning in value['warnings'])
    else:
        assert f'绑定仪器类别已不存在：{category_id}' in value['warnings']
        assert not any('停用' in warning for warning in value['warnings'])
    assert value['configuration_complete'] is False
    assert value['formal_eligible'] is False


def test_in_path_device_parameters_and_cable_changes_are_detected(client, lab_profile, topology_two_chains, db_session):
    baseline = snapshot(client, lab_profile)
    nodes = copy.deepcopy(topology_two_chains.nodes)
    nodes[0]['params']['hardware_id'] = 'changed-saved-device'
    topology_two_chains.nodes = nodes
    db_session.commit()
    assert 'topology' in compare(client, lab_profile, baseline).json()['changed_sections']
    baseline = snapshot(client, lab_profile)
    connections = copy.deepcopy(topology_two_chains.connections)
    connections[0]['switch_port'] = 'changed-switch-port'
    topology_two_chains.connections = connections
    db_session.commit()
    assert 'topology' in compare(client, lab_profile, baseline).json()['changed_sections']


def test_topology_device_declarations_are_visible_without_secrets(client, lab_profile, topology_two_chains, db_session):
    nodes = copy.deepcopy(topology_two_chains.nodes)
    nodes[0]['params'].update({'model': 'F64', 'vendor': 'Keysight', 'inputs': 2, 'outputs': 32,
                               'password': 'node-secret'})
    topology_two_chains.nodes = nodes
    db_session.commit()
    value = snapshot(client, lab_profile)
    node = next(n for n in value['payload']['topology']['nodes'] if n['id'] == 'ce_b1')
    assert node['parameters'] == {'model': 'F64', 'vendor': 'Keysight', 'inputs': 2, 'outputs': 32}
    assert 'node-secret' not in str(value)


@pytest.mark.parametrize('change', ['loss', 'polarization', 'source_label'])
def test_only_dependent_chain_is_affected_by_local_topology_change(client, lab_profile, topology_two_chains, db_session, change):
    # 让另一条链属于另一个探头，避免“改极化”同时引入重复目的地。
    nodes = copy.deepcopy(topology_two_chains.nodes)
    nodes[3]['params']['probe_id'] = 1
    topology_two_chains.nodes = nodes
    db_session.commit()
    baseline = snapshot(client, lab_profile)
    nodes = copy.deepcopy(topology_two_chains.nodes)
    if change == 'loss':
        connections = copy.deepcopy(topology_two_chains.connections)
        connections[0]['calibrated_loss_db'] = 1.5
        topology_two_chains.connections = connections
    elif change == 'polarization':
        nodes[2]['params']['polarization'] = 'H'
    else:
        nodes[0]['label'] = 'B9'
    topology_two_chains.nodes = nodes
    db_session.commit()
    assert compare(client, lab_profile, baseline).json()['affected_chain_ids'] == ['conn_p0v']


@pytest.mark.parametrize('field,value', [('controller_ip', '192.0.2.1'), ('port', 5050)])
def test_transport_columns_change_scope(client, lab_profile, db_session, field, value):
    category = InstrumentCategory(category_key='channelEmulator', category_name='CE', is_active=True)
    db_session.add(category)
    db_session.flush()
    connection = InstrumentConnection(category_id=category.id, endpoint='saved-endpoint')
    db_session.add(connection)
    lab_profile.instrument_bindings = [{'category_id': str(category.id), 'connection_endpoint': 'saved-endpoint'}]
    db_session.commit()
    baseline = snapshot(client, lab_profile)
    setattr(connection, field, value)
    db_session.commit()
    assert 'resources' in compare(client, lab_profile, baseline).json()['changed_sections']


@pytest.mark.parametrize('field,value', [('gain_db', 7), ('max_power_dbm', 10), ('frequency_range_mhz', {'min': 500, 'max': 6000})])
def test_probe_physical_declarations_change_scope(client, lab_profile, chamber, db_session, field, value):
    probe = Probe(chamber_config_id=chamber.id, probe_number=1, ring=1, polarization='V',
                  position={'azimuth': 0, 'elevation': 0, 'radius': 4})
    db_session.add(probe)
    db_session.commit()
    baseline = snapshot(client, lab_profile)
    setattr(probe, field, value)
    db_session.commit()
    assert 'probes' in compare(client, lab_profile, baseline).json()['changed_sections']


def test_shared_device_change_affects_both_downstream_chains(client, lab_profile, topology_two_chains, db_session):
    nodes = copy.deepcopy(topology_two_chains.nodes)
    # 同一设备不等于同一物理输出；泛型多端口CE由连接显式声明输出，不猜显示标签。
    nodes[0]['type'] = 'channel_emulator'
    nodes[0]['params']['ports'] = ['out1', 'out2']
    topology_two_chains.nodes = nodes
    edges = copy.deepcopy(topology_two_chains.connections)
    edges[0].update(source_pin='out1', ce_port='1')
    edges[1].update(source='ce_b1', source_pin='out2', ce_port='2')
    topology_two_chains.connections = edges
    db_session.commit()
    baseline = snapshot(client, lab_profile)
    assert [(chain['chain_id'], chain['ce_port']) for chain in baseline['payload']['chains']] == [
        ('conn_p0h', '2'), ('conn_p0v', '1')]
    nodes = copy.deepcopy(topology_two_chains.nodes)
    nodes[0]['params']['model'] = 'changed-shared-device'
    topology_two_chains.nodes = nodes
    db_session.commit()
    assert compare(client, lab_profile, baseline).json()['affected_chain_ids'] == ['conn_p0h', 'conn_p0v']


def test_removed_chain_is_included_without_affecting_unchanged_chain(client, lab_profile, topology_two_chains, db_session):
    baseline = snapshot(client, lab_profile)
    topology_two_chains.connections = topology_two_chains.connections[1:]
    modes = copy.deepcopy(topology_two_chains.operating_modes)
    modes[0]['active_connections'] = ['conn_p0h']
    topology_two_chains.operating_modes = modes
    db_session.commit()
    assert compare(client, lab_profile, baseline).json()['affected_chain_ids'] == ['conn_p0v']
