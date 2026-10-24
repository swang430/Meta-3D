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
    for _ in range(500):
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


def test_disabled_channel_emulator_is_rejected_even_when_stale_hal_still_loaded(client, configured, db_session):
    cat = db_session.query(InstrumentCategory).filter_by(category_key='channelEmulator').one()
    cat.is_active = False
    db_session.commit()
    # start会取得包含“已停用”事实的新摘要，不能用旧摘要拒绝冒充停用门。
    assert start(client, configured).status_code == 422


async def test_stop_failure_survives_subsequent_lease_release_failure(db_session, monkeypatch):
    from contextlib import asynccontextmanager
    from app.services.calibration import fixed_route_jobs as jobs
    from app.schemas.fixed_route_acquisition import FixedRouteResult
    from tests.test_pc_04a_fixed_route_acquisition import request
    import asyncio
    result = FixedRouteResult(run_id=uuid4(), lab_profile_id=uuid4(), request=request(), configuration={})
    async def collect(ce, sa, current, **options):
        current.status, current.error = 'cleanup_unconfirmed', '可能仍在发射：stop rejected'
        current.cleanup_confirmed = False
    @asynccontextmanager
    async def lease(*args, **kwargs):
        # 这里只构造已经发生的双重失败，测试危险状态优先级，不验证绑定/采集。
        kwargs['validate_before_remote'](None)
        yield SimpleNamespace(lease_id='lease')
        raise RuntimeError('ATE socket close failed')
    monkeypatch.setattr(jobs, 'collect_fixed_route', collect)
    monkeypatch.setattr(jobs, 'instrument_test_lease', lease)
    monkeypatch.setattr(jobs, 'resolve_configuration', lambda *args: ({}, 1, None, None))
    monkeypatch.setattr(jobs, 'has_active_case_run', lambda: None)
    monkeypatch.setattr(jobs, 'has_running_case_run_row', lambda db: None)
    monkeypatch.setattr(jobs, 'SessionLocal', sessionmaker(bind=db_session.get_bind(), expire_on_commit=False))
    db_session.add(LabProfile(id=result.lab_profile_id, name='失败优先级'))
    db_session.add(DiagnosticRun(id=result.run_id, lab_profile_id=result.lab_profile_id, target_name=jobs.TARGET,
        kind='scpi_sequence', success=False, sequence_evidence=result.model_dump(mode='json')))
    db_session.commit()
    await jobs._execute(result, 'unused', asyncio.Event())
    db_session.expire_all()
    saved = db_session.get(DiagnosticRun, result.run_id).sequence_evidence['extra']['fixed_route_acquisition']
    assert saved['status'] == 'cleanup_unconfirmed'
    assert '可能仍在发射' in saved['error'] and 'ATE socket close failed' in saved['error']


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


def test_graceful_shutdown_waits_for_acquisition_cleanup_and_saved_terminal(client, configured):
    from app.services.calibration import fixed_route_jobs as jobs
    response = start(client, configured)
    run_id = response.json()['run_id']
    client.portal.call(jobs.shutdown_fixed_route_jobs)
    value = finish(client, configured, run_id)
    assert value['status'] == 'cancelled'
    assert not jobs._running


def test_acquisition_running_and_terminal_are_readable_in_shared_diagnostic_history(client, configured):
    response = start(client, configured)
    run_id = response.json()['run_id']
    for terminal in (False, True):
        if terminal:
            finish(client, configured, run_id)
        listing = client.get('/api/v1/diagnostic-runs', params={'kind':'scpi_sequence'}).json()
        listed = next(item for item in listing['items'] if item['id'] == run_id)
        detail = client.get(f'/api/v1/diagnostic-runs/{run_id}')
        assert detail.status_code == 200, detail.text
        assert listed['sequence_verdict'] == 'UNDETERMINED'
        envelope = detail.json()['sequence_evidence']
        assert envelope['summary'] and isinstance(envelope['log'], list) and isinstance(envelope['steps'], list)
        result = envelope['extra']['fixed_route_acquisition']
        assert result['run_id'] == run_id and result['formal_eligible'] is False
        assert result['net_loss_db'] is None and result['samples'] == []
        if terminal:
            assert result['status'] == 'simulated'
            assert '模拟' in envelope['summary']
            assert envelope['duration_ms'] > 0


def test_real_http_lease_and_real_driver_transport_keeps_measured_source_not_setting(client, configured, db_session, monkeypatch):
    from app.services.calibration import fixed_route_jobs as jobs
    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.rs_fsva import RealRsFsvaDriver
    from tests.test_p1_66_f64_probe_truth import _ScriptedVisaResource
    ce = RealPropsimF64Driver('ce-real-script', {'ip':'192.0.2.10'})
    sa = RealRsFsvaDriver('sa-real-script', {'ip':'192.0.2.10'})
    ce_resource = _ScriptedVisaResource({'*IDN?':'Keysight Technologies,F8800A,SN-CE,8.0',
        'SYSTem:ERRor?':'0,"No error"', 'DIAG:SIMU:STATE?':'RUNNING',
        'OUTPut:INTERFerence:GET?':'0','OUTPut:LOSS:GET? 1':'0',
        'OUTPut:MEASure:RESult:GET? 1,1':'-25','SYSTem:CALIBration:VALid?':'1,1',
        'SYSTem:CALIBration:USER:GET?':'','OUTPut:GAIN:CH? 1':'0'})
    sa_resource = _ScriptedVisaResource({'*IDN?':'Rohde&Schwarz,FSVA3044,SN-SA,1.0',
        'SENSe:CORRection:TRANsducer:CATalog?':'0,10000','INITiate:IMMediate; *OPC?':'1',
        'CALCulate:MARKer:FUNCtion:POWer:RESult? CPOWer':'-50'})
    ce._visa_resource, sa._visa_session = ce_resource, sa_resource
    from app.hal.base import InstrumentStatus
    ce._status = InstrumentStatus.READY
    ce._local_control_reserved = False
    ce.has_interference_generator = True
    # 保留真实_query/_write/_do_query/_do_write、SCPI锁及真实租约，仅替换VISA资源。
    hal = SimpleNamespace(drivers={'channelEmulator':ce,'signalAnalyzer':sa})
    lease = InstrumentTestLease(lambda:hal)
    monkeypatch.setattr(jobs, 'get_hal_service', lambda:hal)
    monkeypatch.setattr(jobs, 'instrument_test_lease', lease.hold)
    bindings = []
    for binding in configured.instrument_bindings:
        bindings.append({**binding,'driver_mode':'real'})
    configured.instrument_bindings = bindings
    db_session.query(InstrumentCategory).update({'driver_mode':'real'})
    db_session.commit()
    response = start(client, configured)
    assert response.status_code == 202, response.text
    value = finish(client, configured, response.json()['run_id'])
    assert value['status'] == 'completed', value
    assert value['result']['net_loss_db'] == 23  # -25 - (-50+2)，不能用请求-20得到28。
    assert value['result']['cleanup_confirmed'] is True
    assert 'OUTPut:MEASure:RESult:GET? 1,1' in ce_resource.commands
    assert any(command.endswith(',0') and ':STatus ' in command for command in ce_resource.commands)
    assert ce_resource.closed and not lease.is_active


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
