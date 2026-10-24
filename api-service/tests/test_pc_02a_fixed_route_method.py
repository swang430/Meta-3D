"""PC-02A：验证计算预览，不借预览授予现场校准资格。"""
import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def payload():
    return {
        'lab_profile_id': '11111111-1111-4111-8111-111111111111',
        'chain_id': 'probe-0-v', 'ce_port': 'B1.1',
        'switch_identity': 'EMCenter-operator-record', 'fixed_route': 'input1-output3',
        'reference_antenna': 'reference-serial-1', 'frequency_mhz': 3500,
        'ce_output_power_dbm': -20, 'ce_power_source': '输出口功率记录001',
        'sa_input_power_dbm': -50, 'sa_power_source': '分析仪输入口读数记录002',
        'receive_cable_loss_db': 2, 'receive_cable_source': '接收线缆记录003，3500MHz',
        'switch_mode': 'fixed',
    }


def preview(client, payload):
    return client.post('/api/v1/calibration/path-loss/fixed-route/preview', json=payload)


@pytest.mark.parametrize('sa,cable,expected', [(-50, 2, 28), (-10, 2, -12), (-50, -2, 32), (0, 0, -20)])
def test_reference_correction_and_gain_keep_sign(client, payload, sa, cable, expected):
    # 错误abs()或接收线缆加减号会破坏独立手算结果。
    payload.update(sa_input_power_dbm=sa, receive_cable_loss_db=cable)
    response = preview(client, payload)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['net_loss_db'] == expected
    assert value['formal_eligible'] is False
    assert value['input_provenance'] == 'operator_entered'
    assert value['declaration'] == payload
    assert 'path_loss_db' not in value


@pytest.mark.parametrize('field', ['switch_identity', 'fixed_route', 'reference_antenna',
    'ce_power_source', 'sa_power_source', 'receive_cable_source', 'chain_id', 'ce_port'])
def test_missing_reference_or_switch_is_not_silently_defaulted(client, payload, field):
    payload[field] = '  '
    assert preview(client, payload).status_code == 422
    del payload[field]
    assert preview(client, payload).status_code == 422


@pytest.mark.parametrize('change', [
    {'switch_mode': 'automatic'}, {'probe_gain_dbi': 5}, {'pa_gain_db': 10},
    {'formal_eligible': True}, {'frequency_mhz': 0},
    {'ce_output_power_dbm': 'NaN'}, {'sa_input_power_dbm': 'Infinity'},
    {'receive_cable_loss_db': '-Infinity'},
])
def test_rejects_switching_duplicate_corrections_and_unusable_numbers(client, payload, change):
    assert preview(client, payload | change).status_code == 422


def test_preview_has_no_persistence_and_does_not_mutate_inputs(client, payload):
    before = copy.deepcopy(payload)
    first = preview(client, payload)
    second = preview(client, payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert payload == before


def test_openapi_mirrors_include_fixed_route_only_and_no_formal_promotion():
    from pathlib import Path
    import yaml
    checked = yaml.safe_load((Path(__file__).resolve().parents[2] / 'api/openapi.yaml').read_text())
    for document in (app.openapi(), checked):
        assert '/api/v1/calibration/path-loss/fixed-route/preview' in document['paths']
        schemas = document['components']['schemas']
        request = schemas['FixedRouteCalibrationDeclaration']['properties']
        assert request['switch_mode']['const'] == 'fixed'
        assert schemas['FixedRouteCalibrationPreview']['properties']['formal_eligible']['const'] is False
