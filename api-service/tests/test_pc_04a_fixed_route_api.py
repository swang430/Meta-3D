"""PC-04A生产HTTP/真实DB/真实租约正反例；仅仪器使用Mock。"""
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import get_db
from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection
from app.models.lab_profile import LabProfile
from app.models.diagnostic_run import DiagnosticRun
from app.models.probe_calibration import ProbePathLossCalibration
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.services.instrument_test_lease import InstrumentTestLease
from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile


@pytest.fixture
def configured(db_session, lab_profile):
    bindings = []
    for key, model_name in [('channelEmulator', 'PROPSIM F64'), ('signalAnalyzer', 'FSVA3000')]:
        cat = InstrumentCategory(category_key=key, category_name=key, driver_mode='mock')
        db_session.add(cat)
        db_session.flush()
        model = InstrumentModel(category_id=cat.id, model=model_name, vendor='test', capabilities={})
        db_session.add(model)
        db_session.flush()
        cat.selected_model_id = model.id
        db_session.add(InstrumentConnection(category_id=cat.id, endpoint='192.0.2.10', created_by='test'))
        bindings.append(dict(category_id=str(cat.id), instrument_model_id=str(model.id),
            connection_endpoint='192.0.2.10', driver_mode='mock'))
    lab_profile.instrument_bindings = bindings
    db_session.commit()
    return lab_profile


@pytest.fixture
def client(db_session, monkeypatch):
    from app.services.calibration import fixed_route_jobs as jobs
    hal = SimpleNamespace(drivers={'channelEmulator': MockChannelEmulator('ce', {}),
                                  'signalAnalyzer': MockSignalAnalyzer('sa', {})})
    lease = InstrumentTestLease(lambda: hal)
    monkeypatch.setattr(jobs, 'get_hal_service', lambda: hal)
    monkeypatch.setattr(jobs, 'instrument_test_lease', lease.hold)
    monkeypatch.setattr(jobs, 'SessionLocal', sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def start(client, lab, **changes):
    scope = client.get(f'/api/v1/lab-profiles/{lab.id}/calibration-scope').json()
    payload = dict(chain_id='conn_p0v', configuration_digest=scope['digest'], frequency_mhz=2595,
        requested_power_dbm=-20, reference_antenna='SN-REF 静区中心V', receive_cable_loss_db=2,
        receive_cable_source='SN-CABLE 2595MHz记录', fixed_route_confirmed=True, safety_confirmed=True,
        sample_count=2)
    payload.update(changes)
    return client.post(f'/api/v1/lab-profiles/{lab.id}/fixed-route-acquisitions', json=payload)


def finish(client, lab, run_id):
    for _ in range(100):
        value = client.get(f'/api/v1/lab-profiles/{lab.id}/fixed-route-acquisitions/{run_id}').json()
        if value['status'] != 'running':
            return value
        time.sleep(.03)
    pytest.fail('采集未结束')


def test_two_real_http_runs_keep_mock_evidence_and_never_write_old_certificates(client, configured, db_session):
    before = db_session.query(ProbePathLossCalibration).count()
    for _ in range(2):
        response = start(client, configured)
        assert response.status_code == 202, response.text
        value = finish(client, configured, response.json()['run_id'])
        assert value['status'] == 'simulated', value
        assert value['result']['samples'] == [] and value['result']['net_loss_db'] is None
        assert value['result']['formal_eligible'] is False
        assert value['result']['configuration']['chain']['ce_port'] == 'B1.1'
    rows = client.get(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions').json()
    assert len(rows) == 2
    assert db_session.query(ProbePathLossCalibration).count() == before


def test_cancel_is_a_server_operation_and_releases_exclusion(client, configured):
    response = start(client, configured)
    assert response.status_code == 202, response.text
    run_id = response.json()['run_id']
    cancelled = client.post(f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}/cancel')
    assert cancelled.status_code == 200, cancelled.text
    value = finish(client, configured, run_id)
    assert value['status'] == 'cancelled'
    assert value['result']['net_loss_db'] is None
    assert start(client, configured).status_code == 202


@pytest.mark.parametrize('change', [dict(chain_id='other'), dict(configuration_digest='0'*64), dict(fixed_route_confirmed=False), dict(ce_output_power_dbm=-20)])
def test_invalid_or_stale_configuration_never_creates_hardware_job(client, configured, db_session, change):
    response = start(client, configured, **change)
    assert response.status_code == 422, response.text
    assert db_session.query(DiagnosticRun).count() == 0


def test_saved_analyzer_drift_or_disabled_never_connects(client, configured, db_session):
    cat = db_session.query(InstrumentCategory).filter_by(category_key='signalAnalyzer').one()
    cat.is_active = False
    db_session.commit()
    assert start(client, configured).status_code == 422
    cat.is_active = True
    conn = db_session.query(InstrumentConnection).filter_by(category_id=cat.id).one()
    conn.endpoint = 'changed'
    db_session.commit()
    assert start(client, configured).status_code == 422


def test_history_cross_lab_and_process_restart_never_backfill_or_resume(client, configured, db_session):
    from app.services.calibration.fixed_route_jobs import TARGET
    run_id = uuid4()
    row = DiagnosticRun(id=run_id, kind='scpi_sequence', lab_profile_id=configured.id,
        target_name=TARGET, success=False, sequence_evidence={'status': 'running'})
    db_session.add(row)
    other = LabProfile(name='other')
    db_session.add(other)
    db_session.commit()
    url = f'/api/v1/lab-profiles/{configured.id}/fixed-route-acquisitions/{run_id}'
    value = client.get(url).json()
    assert value['status'] in ('interrupted', 'incomplete')
    assert value['formal_eligible'] is False
    assert client.get(f'/api/v1/lab-profiles/{other.id}/fixed-route-acquisitions/{run_id}').status_code == 404
    assert client.post(url + '/cancel').status_code == 409


def test_case_execution_blocks_calibration_before_remote(client, configured, monkeypatch):
    from app.services.calibration import fixed_route_jobs as jobs
    monkeypatch.setattr(jobs, 'has_active_case_run', lambda: 'case-running')
    assert start(client, configured).status_code == 409


def test_live_checked_openapi_and_generated_types_cover_all_pc04_routes():
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[2]
    checked = yaml.safe_load((root / 'api/openapi.yaml').read_text())
    base = '/api/v1/lab-profiles/{lab_profile_id}/fixed-route-acquisitions'
    for doc in (app.openapi(), checked):
        assert {'get', 'post'} <= doc['paths'][base].keys()
        assert 'get' in doc['paths'][base + '/{run_id}']
        assert 'post' in doc['paths'][base + '/{run_id}/cancel']
        assert 'ce_output_power_dbm' not in doc['components']['schemas']['FixedRouteRequest']['properties']
        assert doc['components']['schemas']['FixedRouteResult']['properties']['formal_eligible']['const'] is False
    generated = (root / 'gui/src/types/api.generated.ts').read_text()
    assert base in generated and 'FixedRouteRecord:' in generated
