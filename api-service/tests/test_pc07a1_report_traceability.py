"""报告只认原执行冻结来源；自洽客户端 JSON 不能成为追溯真值。"""
import copy
import json
import subprocess
from datetime import datetime

import pytest

from tests.test_pc07a1_calibration_traceability import (
    db_session, chamber, topology_two_chains, lab_profile, client, configured,
    real_capture, legacy, launch, confirm, payload, application,
)
from tests.test_mimo_ota_report_verified_backcompat import _path_loss_report_phases
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.mimo_ota.calibration_traceability import build_calibration_traceability
from app.services.report_service import ReportService
from app.api import report as report_api


@pytest.fixture
async def archived(application, launch, db_session):
    execution = await launch()
    execution.measurements = {'phases': _path_loss_report_phases(application, verified=True)}
    db_session.commit()
    content = _build_mimo_ota_content_data(execution, datetime.utcnow())
    report = ReportService().create_report(db_session, title='原执行追溯',
        report_type='single_execution', format='pdf', generated_by='mimo_ota.executors.report',
        test_execution_ids=[execution.id])
    report.content_data = content
    report.status = 'completed'
    db_session.commit()
    return execution, report


@pytest.mark.asyncio
async def test_builder_and_pdf_show_frozen_mixed_identity_unknown_and_pointers(archived, tmp_path):
    execution, report = archived
    content = report.content_data
    trace = content['calibration_traceability']
    assert trace['execution_frequency_mhz'] == 2595
    assert {r['source_kind'] for r in trace['routes']} == {'confirmed_route', 'legacy_certificate'}
    assert {r['application_state'] for r in trace['routes']} == {'applied'}
    adopted = next(r for r in trace['routes'] if r['source_kind'] == 'confirmed_route')
    assert adopted['certification_status'] == 'unknown'
    assert adopted['source_snapshot']['predecessor_id'] is None
    assert trace['raw_readings_embedded'] is False
    from app.services.pdf_generator import PDFGenerator
    pdf = tmp_path / 'traceability.pdf'
    (tmp_path / 'traceability.json').write_text(json.dumps(content, ensure_ascii=False, indent=2))
    PDFGenerator().generate_report(content, None, str(pdf))
    text = subprocess.check_output(['pdftotext', '-layout', str(pdf), '-'], text=True)
    for value in ('2595', 'unknown', '原始读数未内嵌', adopted['source_id'],
                  adopted['source_snapshot']['acquisition_run_id'], '参考面', '前序'):
        assert value in text
    assert '认证通过' not in text


@pytest.mark.asyncio
async def test_report_internal_application_cannot_drift_while_projection_stays_original(archived, db_session):
    _, report = archived
    forged = copy.deepcopy(report.content_data)
    from app.services.mimo_ota.path_loss_application import parse_path_loss_application
    forged['path_loss_application'] = parse_path_loss_application(None)
    forged['formal_path_loss_verified'] = False
    report.content_data = forged
    assert not report_api._mimo_report_is_provenance_sanitized(db_session, report)


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['selected', 'simulated', 'missing', 'association_unknown'])
async def test_projection_preserves_selection_and_unknown_without_formal_promotion(archived, state):
    execution, _ = archived
    phases = copy.deepcopy(execution.measurements['phases'])
    app = phases['measure']['path_loss_application']
    if state == 'selected':
        app.update(status='not_applied', reason='diagnostic', value_disclosure='none', applied_chain_ids=[])
    elif state == 'simulated':
        app.update(provenance='simulated', value_disclosure='none')
    elif state == 'missing':
        phases['measure'].pop('path_loss_application')
    else:
        from app.hal.base_station_compatibility import canonical_payload_digest
        frozen = app['route_compensation']
        frozen['source_records'] = []
        frozen['digest'] = canonical_payload_digest({k: v for k, v in frozen.items() if k != 'digest'})
    execution.measurements = {'phases': phases}
    content = _build_mimo_ota_content_data(execution, datetime.utcnow())
    trace = content['calibration_traceability']
    assert content['formal_path_loss_verified'] is False
    assert content['overall_result'] != 'passed'
    if state == 'selected':
        assert {row['application_state'] for row in trace['routes']} == {'selected'}
    if state == 'association_unknown':
        assert {row['application_state'] for row in trace['routes']} == {'unknown'}
        assert all(row['source_snapshot'] is None for row in trace['routes'])


@pytest.mark.asyncio
@pytest.mark.parametrize('entrypoint', ['detail', 'download', 'list'])
async def test_report_trust_rejects_self_consistent_forgery_against_original_execution(archived, db_session, entrypoint):
    execution, report = archived
    assert report_api._mimo_report_is_provenance_sanitized(db_session, report)
    forged = copy.deepcopy(report.content_data)
    # v1 本身合法：攻击者不是破坏格式，而是替换实际来源后重算全部报告内镜像。
    forged_application = {'schema_version': 1, 'status': 'applied', 'provenance': 'real',
        'reason': 'selected', 'gate_mode': 'strict', 'certificate_id': 'forged-cert',
        'value_disclosure': 'verified'}
    from app.services.mimo_ota.path_loss_application import parse_path_loss_application
    forged['path_loss_application'] = parse_path_loss_application(forged_application)
    forged['formal_path_loss_verified'] = True
    forged['calibration_traceability'] = build_calibration_traceability(forged_application)
    report.content_data = forged
    assert not report_api._mimo_report_is_provenance_sanitized(db_session, report)
    if entrypoint == 'list':
        summary = report_api._report_summary(db_session, report)
        assert summary.requires_regeneration is True
        assert summary.regeneration_available is True
    else:
        from fastapi import HTTPException
        operation = report_api.get_report if entrypoint == 'detail' else report_api.download_report
        with pytest.raises(HTTPException) as rejected:
            operation(report.id, db=db_session)
        assert rejected.value.status_code == 409


@pytest.mark.asyncio
async def test_missing_new_key_keeps_legacy_trust_gate(archived, db_session):
    _, report = archived
    old = copy.deepcopy(report.content_data)
    old.pop('calibration_traceability', None)
    report.content_data = old
    assert report_api._mimo_report_is_provenance_sanitized(db_session, report)


@pytest.mark.asyncio
async def test_client_create_and_update_cannot_write_traceability(archived, db_session):
    _, report = archived
    service = ReportService()
    created = service.create_report(db_session, title='client', report_type='single_execution',
        format='pdf', generated_by='client', content_data={'calibration_traceability': {'forged': True}})
    assert 'calibration_traceability' not in created.content_data
    updated = service.update_report(db_session, report.id,
        content_data={'calibration_traceability': {'forged': True}})
    assert 'calibration_traceability' not in updated.content_data


@pytest.mark.asyncio
async def test_first_generation_and_rebuild_ignore_current_adoption_and_config(
        archived, configured, client, real_capture, db_session, monkeypatch, tmp_path):
    execution, report = archived
    original = copy.deepcopy(report.content_data['calibration_traceability'])
    legacy_content = copy.deepcopy(report.content_data)
    legacy_content.pop('calibration_traceability')
    report.content_data = legacy_content
    run = real_capture('-20', '-10')
    assert confirm(client, configured, payload(client, configured, run)).status_code == 201
    from app.models.test_plan import TestCase
    current_case = db_session.get(TestCase, execution.test_case_id)
    current_case.configuration = {**current_case.configuration, 'frequency_hz': 3500e6}
    db_session.commit()
    # 非历史执行的来源查询一旦发生，测试立即失败。
    from app.models.route_calibration import RouteCalibrationApplication, RouteCalibrationSelection
    from app.models.probe_calibration import ProbePathLossCalibration
    query = db_session.query
    get = db_session.get
    forbidden = (RouteCalibrationApplication, RouteCalibrationSelection, ProbePathLossCalibration)
    def no_current_sources(*entities, **kwargs):
        assert not any(entity is kind for entity in entities for kind in forbidden)
        return query(*entities, **kwargs)
    def no_current_get(entity, *args, **kwargs):
        assert entity not in forbidden
        return get(entity, *args, **kwargs)
    monkeypatch.setattr(db_session, 'query', no_current_sources)
    monkeypatch.setattr(db_session, 'get', no_current_get)
    monkeypatch.chdir(tmp_path)
    service = ReportService()
    for _ in range(2):
        result = service.generate_report(db_session, report.id,
            content_data_override={'calibration_traceability': {'forged': True}})
        assert result.content_data['calibration_traceability'] == original
        assert result.content_data['calibration_traceability']['execution_frequency_mhz'] == 2595
        assert result.status == 'completed', result.error_message
        assert report_api._mimo_report_is_provenance_sanitized(db_session, result)
        response = client.get(f'/api/v1/reports/{report.id}')
        assert response.status_code == 200, response.text
        assert response.json()['content_data']['calibration_traceability'] == original
