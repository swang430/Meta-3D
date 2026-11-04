"""撤销经过真实API/采集生产链；仅复用外部VISA脚本，不改历史冻结。"""
import copy
from uuid import uuid4

import pytest

from tests.test_pc04a2_route_application import db_session, payload, confirm
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured
from tests.test_pc04a2_route_eligibility import real_capture, preview
from tests.test_pc04a2_route_freeze import launch, entries


def endpoint(lab, application):
    return f'/api/v1/lab-profiles/{lab.id}/route-calibration-applications/{application["id"]}/revocation'


@pytest.mark.asyncio
async def test_revocation_blocks_new_selection_and_readoption_but_preserves_history(
        client, configured, real_capture, db_session, launch):
    row = real_capture()
    original = copy.deepcopy(row.sequence_evidence)
    request = payload(client, configured, row)
    saved = confirm(client, configured, request).json()
    before = await launch()
    frozen = copy.deepcopy(before.config['route_calibration_freeze'])
    assert entries(before)['conn_p0v']['source_id'] == saved['id']
    url = endpoint(configured, saved)
    assert client.get(url).json() is None
    response = client.post(url, json={'confirmed': True, 'reason': '参考测量经复核有误'})
    assert response.status_code == 201, response.text
    revoked = response.json()
    assert revoked['acquisition_run_id'] == str(row.id)
    assert revoked['revoked_by'] is None
    assert client.get(url).json() == revoked
    retry = client.post(url, json={'confirmed': True, 'reason': '参考测量经复核有误'})
    assert retry.status_code == 200 and retry.json() == revoked
    assert client.post(url, json={'confirmed': True, 'reason': '另一个理由'}).status_code == 409
    candidate = preview(client, configured, row).json()
    assert candidate['eligibility']['eligible_for_adoption'] is False
    assert 'acquisition_revoked' in candidate['eligibility']['blockers']
    assert candidate['old_value_db'] is None and candidate['new_net_loss_db'] is None
    assert confirm(client, configured, {**request, 'idempotency_key': str(uuid4()),
        'expected_current_application_id': saved['id']}).status_code == 422
    after = await launch()
    assert entries(after)['conn_p0v']['source_kind'] == 'unavailable'
    assert entries(after)['conn_p0v']['value_db'] is None
    db_session.refresh(before)
    assert before.config['route_calibration_freeze'] == frozen
    history = client.get(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications', params={
        'topology_id': saved['selection_snapshot']['topology_id'], 'chain_id': 'conn_p0v'})
    assert history.json() == [saved]
    assert row.sequence_evidence == original
    # 新的独立采集仍可以确认和用于新执行；撤销不是整条链永久封禁。
    fresh = real_capture('-20', '-10')
    fresh_preview = preview(client, configured, fresh).json()
    assert fresh_preview['old_value_db'] is None and fresh_preview['delta_db'] is None
    replacement = confirm(client, configured, payload(client, configured, fresh))
    assert replacement.status_code == 201, replacement.text
    assert entries(await launch())['conn_p0v']['source_id'] == replacement.json()['id']


def test_revocation_requires_explicit_confirmation_reason_and_same_lab(client, configured, real_capture):
    saved = confirm(client, configured, payload(client, configured, real_capture())).json()
    url = endpoint(configured, saved)
    for body in ({'confirmed': 1, 'reason': 'x'}, {'confirmed': True, 'reason': ' '},
                 {'reason': 'x'}, {'confirmed': True, 'reason': 'x', 'revoked_by': '伪造身份'}):
        assert client.post(url, json=body).status_code == 422
    wrong = url.replace(str(configured.id), str(uuid4()))
    assert client.post(wrong, json={'confirmed': True, 'reason': 'x'}).status_code == 404
    assert client.get(wrong).status_code == 404
    assert client.get(url).json() is None


@pytest.mark.parametrize('entrypoint', ['session', 'adhoc'])
def test_commissioning_entries_skip_revoked_measurement(client, configured, real_capture, db_session, monkeypatch, entrypoint):
    from app.api import commissioning as api
    from app.models.test_plan import TestExecution
    from app.services.test_execution import StepExecutionResult, StepExecutionStatus
    saved = confirm(client, configured, payload(client, configured, real_capture())).json()
    assert client.post(endpoint(configured, saved), json={'confirmed': True, 'reason': '失效'}).status_code == 201
    monkeypatch.setattr(api, '_freeze_instrument_lease', lambda *args, **kwargs: lambda *args: None)
    async def no_hardware(context):
        return StepExecutionResult(status=StepExecutionStatus.SUCCESS)
    monkeypatch.setattr(api, 'dispatch_step', no_hardware)
    body = {'lab_profile_id': str(configured.id)}
    if entrypoint == 'adhoc':
        body.update(phase_name='analysis', config_overrides={'frequency_hz': 2595e6})
        url = '/api/v1/commissioning/diagnostic/run-phase'
    else:
        body['frequency_hz'] = 2595e6
        url = '/api/v1/commissioning/sessions'
    response = client.post(url, json=body)
    assert response.status_code in (200, 201), response.text
    execution = db_session.query(TestExecution).order_by(TestExecution.started_at.desc()).first()
    assert entries(execution)['conn_p0v']['source_kind'] == 'unavailable'
    assert entries(execution)['conn_p0v']['reason'] == 'acquisition_revoked'


def test_revocation_waits_for_freeze_transaction(client, configured, real_capture, db_session):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import event
    from sqlalchemy.orm import sessionmaker
    from uuid import UUID
    from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation
    from app.services.calibration.route_revocation import revoke_route_calibration
    from app.schemas.route_calibration import RevokeRouteCalibration
    saved = confirm(client, configured, payload(client, configured, real_capture())).json()
    frozen = resolve_effective_route_compensation(db_session, configured.id, 'mimo_ota', 2595)
    assert frozen['route_entries'][0]['source_kind'] == 'confirmed_route'
    engine = db_session.get_bind()
    factory = sessionmaker(bind=engine)
    attempted = Event()
    def entering_lock(connection, cursor, statement, *args):
        if statement.startswith('UPDATE diagnostic_runs'):
            attempted.set()
    event.listen(engine, 'before_cursor_execute', entering_lock)
    lab_id = configured.id
    def revoke():
        with factory() as independent:
            return revoke_route_calibration(independent, lab_id, UUID(saved['id']),
                RevokeRouteCalibration(confirmed=True, reason='失效'))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(revoke)
            try:
                assert attempted.wait(5)
                assert not future.done()
            finally:
                db_session.commit()  # 先提交的冻结保留当时证据，之后撤销才返回。
            assert future.result(timeout=5)[1] is True
    finally:
        event.remove(engine, 'before_cursor_execute', entering_lock)
    current = resolve_effective_route_compensation(db_session, lab_id, 'mimo_ota', 2595)
    assert all(row['source_kind'] != 'confirmed_route' for row in current['route_entries'])
    db_session.rollback()


def test_revocation_contract_matches_live_and_generated_types():
    from pathlib import Path
    import yaml
    from app.main import app
    root = Path(__file__).resolve().parents[2]
    checked = yaml.safe_load((root / 'api/openapi.yaml').read_text())
    live = app.openapi()
    route = '/api/v1/lab-profiles/{lab_profile_id}/route-calibration-applications/{application_id}/revocation'
    assert checked['paths'][route] == live['paths'][route]
    for name in ('RevokeRouteCalibration', 'RouteRevocationRecord'):
        assert checked['components']['schemas'][name] == live['components']['schemas'][name]
        assert name in (root / 'gui/src/types/api.generated.ts').read_text()
        assert name in (root / 'gui/src/types/api.ts').read_text()


def test_revocation_storage_failure_never_reports_success(client, configured, real_capture, db_session):
    from sqlalchemy import event
    from app.models.route_calibration import RouteCalibrationRevocation
    saved = confirm(client, configured, payload(client, configured, real_capture())).json()
    def fail_write(connection, cursor, statement, *args):
        if statement.startswith('INSERT INTO route_calibration_revocations'):
            raise RuntimeError('revocation storage failure')
    engine = db_session.get_bind()
    event.listen(engine, 'before_cursor_execute', fail_write)
    try:
        with pytest.raises(RuntimeError, match='revocation storage failure'):
            client.post(endpoint(configured, saved), json={'confirmed': True, 'reason': '失效'})
    finally:
        event.remove(engine, 'before_cursor_execute', fail_write)
    assert db_session.query(RouteCalibrationRevocation).count() == 0
    assert client.get(endpoint(configured, saved)).json() is None
