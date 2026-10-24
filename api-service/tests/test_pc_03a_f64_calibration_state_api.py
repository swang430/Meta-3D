"""专用入口复用诊断审计；历史缺损不从当前设备状态补真。"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.models.diagnostic_run import DiagnosticRun
from contextlib import asynccontextmanager
from types import SimpleNamespace
from tests.test_p2_58_channel_emulator_binding import _configured
from app.hal.channel_emulator import MockChannelEmulator
from app.api import diagnostic_sequence
from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile


@pytest.fixture
def client(db_session):
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def test_history_is_lab_scoped_and_handles_incomplete_rows(client, lab_profile, db_session):
    for lab_id, name in [(lab_profile.id, 'propsim_f64_calibration_state'),
                         (lab_profile.id, 'propsim_f64_license_truth')]:
        db_session.add(DiagnosticRun(kind='scpi_sequence', lab_profile_id=lab_id,
            target_name=name, success=False, sequence_evidence={'extra': {'calibration_state': 'bad'}}))
    db_session.commit()
    response = client.get(f'/api/v1/lab-profiles/{lab_profile.id}/f64-calibration-state')
    assert response.status_code == 200, response.text
    records = response.json()
    assert len(records) == 1
    assert records[0]['state'] is None
    assert records[0]['record_status'] == 'incomplete'
    assert records[0]['formal_eligible'] is False
    assert records[0]['run_at'].endswith(('Z', '+00:00'))
    assert client.get(f'/api/v1/lab-profiles/{uuid.uuid4()}/f64-calibration-state').status_code == 404


def test_invalid_request_does_not_create_run(client, lab_profile, db_session):
    before = db_session.query(DiagnosticRun).count()
    response = client.post(f'/api/v1/lab-profiles/{lab_profile.id}/f64-calibration-state',
        json={'group_id': True, 'input_port': 1, 'output_port': 2})
    assert response.status_code == 422, response.text
    assert db_session.query(DiagnosticRun).count() == before


@pytest.mark.parametrize('model_name,drift', [('PROPSIM F64', False), ('FS16', False), ('PROPSIM F64', True)])
def test_capture_rechecks_binding_before_remote_and_persists_real_mock_response(client, db_session, monkeypatch, model_name, drift):
    category, model, connection, lab = _configured(db_session, driver_mode='mock', model_name=model_name)
    if drift:
        connection.endpoint = 'changed-after-sync'
        db_session.commit()
    hal = SimpleNamespace(drivers={'channelEmulator': MockChannelEmulator('ce', {})})
    options_seen = []

    @asynccontextmanager
    async def lease(purpose, **options):
        options_seen.append(options)
        error = options['validate_before_remote'](hal)
        if error:
            raise ValueError(error)
        yield SimpleNamespace()

    monkeypatch.setattr(diagnostic_sequence, 'instrument_test_lease', lease)
    monkeypatch.setattr(diagnostic_sequence, 'get_hal_service', lambda: hal)
    response = client.post(f'/api/v1/lab-profiles/{lab.id}/f64-calibration-state',
        json={'group_id': 2, 'input_port': 1, 'output_port': 3})
    assert response.status_code == 200, response.text
    value = response.json()
    assert options_seen[0]['control_uxm'] is False
    assert options_seen[0]['enable_monitoring'] is False
    if model_name == 'PROPSIM F64' and not drift:
        assert value['state']['acquisition_status'] == 'simulated'
        assert value['state']['formal_eligible'] is False
        assert all(item['status'] == 'simulated' for item in value['state']['fields'])
        assert client.get(f'/api/v1/lab-profiles/{lab.id}/f64-calibration-state').json()[0] == value
    else:
        assert value['success'] is False
        assert value['state'] is None


def test_active_formal_execution_refuses_capture_before_lease(client, lab_profile, monkeypatch):
    # 此门需要有效实验室绑定，不能用更早的缺绑定拒绝冒充执行互斥。
    db = app.dependency_overrides[get_db]()
    _, _, _, lab = _configured(db, driver_mode='mock')
    monkeypatch.setattr(diagnostic_sequence, 'has_active_case_run', lambda: 'running-case')
    response = client.post(f'/api/v1/lab-profiles/{lab.id}/f64-calibration-state',
        json={'group_id': 2, 'input_port': 1, 'output_port': 3})
    assert response.status_code == 409


def test_openapi_and_types_include_pc03_read_and_history():
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[2]
    checked = yaml.safe_load((root / 'api/openapi.yaml').read_text())
    path = '/api/v1/lab-profiles/{lab_profile_id}/f64-calibration-state'
    for document in (app.openapi(), checked):
        assert {'post', 'get'} <= document['paths'][path].keys()
        props = document['components']['schemas']['F64CalibrationState']['properties']
        assert props['formal_eligible']['const'] is False
        assert props['diagnostic_only']['const'] is True
    generated = (root / 'gui/src/types/api.generated.ts').read_text()
    assert path in generated and 'F64StateRecord:' in generated
