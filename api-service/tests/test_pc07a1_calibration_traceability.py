"""只追溯原执行冻结；不把诊断候选或当前数据库补成采用事实。"""
import copy
import importlib
from datetime import datetime

import pytest

from tests.test_pc04a2_route_freeze import (
    db_session, chamber, topology_two_chains, lab_profile, client, configured,
    real_capture, legacy, launch, confirm, payload,
)
from app.hal.base_station_compatibility import canonical_payload_digest
from app.services.mimo_ota.path_loss_preflight import evaluate_path_loss_preflight


@pytest.fixture
async def application(client, configured, real_capture, legacy, launch, db_session):
    run = real_capture()
    response = confirm(client, configured, payload(client, configured, run))
    assert response.status_code == 201, response.text
    execution = await launch()
    return evaluate_path_loss_preflight(
        db_session, execution, chamber_id=configured.chamber_config_id,
        frequency_mhz=2595, operating_mode='mimo_ota', precheck_strict_cal=True,
        channel_emulator_execution_mode='real',
    ).application


def project(application):
    module = importlib.import_module('app.services.mimo_ota.calibration_traceability')
    return module.build_calibration_traceability(application)


def resign(application):
    frozen = application['route_compensation']
    frozen['digest'] = canonical_payload_digest({k: v for k, v in frozen.items() if k != 'digest'})


@pytest.mark.asyncio
async def test_mixed_routes_keep_exact_source_and_evidence_without_raw(application):
    original = copy.deepcopy(application)
    result = project(application)
    frozen = application['route_compensation']
    expected = [(r['chain_id'], r['source_kind'], r['source_id'], 'applied')
                for r in frozen['route_entries']]
    assert result['raw_readings_embedded'] is False
    assert [(r['chain_id'], r['source_kind'], r['source_id'], r['application_state'])
            for r in result['routes']] == expected
    assert result['execution_frequency_mhz'] == 2595
    assert result['status'] == 'applied'
    for route in result['routes']:
        source = next(s['snapshot'] for s in frozen['source_records']
                      if (s['source_kind'], s['source_id']) == (route['source_kind'], route['source_id']))
        assert route['source_snapshot'] == source
        if route['source_kind'] == 'confirmed_route':
            assert route['source_snapshot']['predecessor_id'] is None
            assert route['source_snapshot']['acquisition_run_id']
            assert route['source_snapshot']['adoption_evidence_snapshot']['checked_exchange_indices']
            assert route['certification_status'] == 'unknown'
    result['routes'][0]['source_snapshot'].clear()
    assert application == original


@pytest.mark.asyncio
async def test_diagnostic_sources_and_same_id_other_kind_do_not_become_routes(application):
    frozen = application['route_compensation']
    confirmed = next(s for s in frozen['source_records'] if s['source_kind'] == 'confirmed_route')
    frozen['source_records'].append(dict(source_kind='legacy_certificate',
        source_id=confirmed['source_id'], snapshot={'diagnostic_only': True}))
    frozen['source_records'].append(dict(source_kind='legacy_certificate',
        source_id='unused-diagnostic', snapshot={'diagnostic_only': True}))
    resign(application)
    result = project(application)
    assert len(result['routes']) == 2
    assert result['routes'][0]['source_snapshot'] == confirmed['snapshot']
    assert not any(r['source_id'] == 'unused-diagnostic' for r in result['routes'])


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'unknown_kind', 'broken', 'partial_applied'])
async def test_incomplete_association_is_unknown_never_guessed(application, damage):
    frozen = application['route_compensation']
    if damage == 'missing':
        frozen['source_records'] = []
    elif damage == 'duplicate':
        first_route = frozen['route_entries'][0]
        matched = next(s for s in frozen['source_records']
                       if (s['source_kind'], s['source_id']) ==
                       (first_route['source_kind'], first_route['source_id']))
        frozen['source_records'].append(copy.deepcopy(matched))
    elif damage == 'unknown_kind':
        frozen['route_entries'][0]['source_kind'] = 'not_supported'
    elif damage == 'broken':
        frozen['source_records'] = [None]
    else:
        application['applied_chain_ids'] = ['conn_p0v']
    resign(application)
    result = project(application)
    assert result['routes']
    assert result['routes'][0]['application_state'] == 'unknown'
    assert result['routes'][0]['source_snapshot'] is None


@pytest.mark.asyncio
async def test_frozen_selection_is_not_application(application):
    application.update(status='not_applied', reason='diagnostic',
                       value_disclosure='none', applied_chain_ids=[])
    result = project(application)
    assert result['status'] == 'not_applied'
    assert [r['application_state'] for r in result['routes']] == ['selected', 'selected']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['confirmed_route', 'legacy_certificate'])
async def test_single_source_execution_uses_only_its_selected_rows(
        client, configured, real_capture, legacy, launch, db_session, topology_two_chains, kind):
    if kind == 'confirmed_route':
        topology_two_chains.operating_modes = [{'id': 'mimo_ota', 'name': 'normal',
                                               'active_connections': ['conn_p0v']}]
        db_session.commit()
        run = real_capture()
        assert confirm(client, configured, payload(client, configured, run)).status_code == 201
    else:
        # 旧来源覆盖频点与本次执行频点不同，仍沿既有±5%政策选中；展示不得抹平。
        legacy.frequency_mhz = 2500
        db_session.commit()
    execution = await launch()
    application = evaluate_path_loss_preflight(
        db_session, execution, chamber_id=configured.chamber_config_id, frequency_mhz=2595,
        operating_mode='mimo_ota', precheck_strict_cal=True,
        channel_emulator_execution_mode='real').application
    result = project(application)
    assert result['execution_frequency_mhz'] == 2595
    assert {r['source_kind'] for r in result['routes']} == {kind}
    assert {r['application_state'] for r in result['routes']} == {'applied'}
    assert {r['source_snapshot']['frequency_mhz'] for r in result['routes']} == (
        {2595} if kind == 'confirmed_route' else {2500})


@pytest.mark.asyncio
async def test_legal_quiet_zone_evidence_does_not_reproduce_a_formal_display_difference(
        application, launch, db_session, configured):
    from app.api.test_execution import _formal_validation_pass
    from app.services.mimo_ota.executors.analysis import AnalysisExecutor
    from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
    from app.services.mimo_ota.quiet_zone_evidence import build_quiet_zone_evidence
    from app.services.test_execution import StepExecutionContext, StepDescriptor
    from tests.test_mimo_ota_report_verified_backcompat import _path_loss_report_phases
    phases = _path_loss_report_phases(application, verified=True)
    phases['measure'].pop('path_loss_calibration_use_mock')
    phases['precheck']['quiet_zone_evidence'] = build_quiet_zone_evidence(1.0)
    execution = await launch()
    execution.measurements = {'phases': phases}
    execution.validation_pass = True
    context = StepExecutionContext(db=db_session,
        step=StepDescriptor(id='analysis', type='MIMO_OTA_ANALYSIS', parameters={}),
        test_execution=execution, lab_profile=configured, calibration_certificate=None)
    await AnalysisExecutor().execute(context)
    assert phases['measure']['path_loss_application']['status'] == 'applied'
    assert execution.validation_pass is None
    assert _formal_validation_pass(execution, 'MIMO_OTA') is None
    content = _build_mimo_ota_content_data(execution, datetime.utcnow())
    assert content['formal_path_loss_verified'] is True
    assert content['formal_quiet_zone_verified'] is False


@pytest.mark.parametrize('value', [None, {}, [], {'schema_version': 2}, {'schema_version': 1}])
def test_missing_history_does_not_reconstruct_sources(value):
    result = project(value)
    assert result['status'] == 'unknown'
    assert result['routes'] == []
    assert result['execution_frequency_mhz'] is None
    assert result['raw_readings_embedded'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['simulated', 'unknown', 'damaged', 'not_applied', 'v1_missing'])
async def test_untrusted_application_never_gains_formal_eligibility(application, state):
    from app.services.mimo_ota.path_loss_application import path_loss_measurement_is_verified
    if state == 'v1_missing':
        application = {'schema_version': 1, 'status': 'applied', 'provenance': 'real',
            'reason': 'selected', 'gate_mode': 'strict', 'certificate_id': None,
            'value_disclosure': 'verified'}
    elif state == 'not_applied':
        application.update(status='not_applied', reason='diagnostic',
                           applied_chain_ids=[], value_disclosure='none')
    elif state == 'damaged':
        application['route_compensation']['digest'] = 'broken'
    else:
        application['provenance'] = state
    assert path_loss_measurement_is_verified({'path_loss_application': application,
        'path_loss_verified': True, 'path_loss_calibration_use_mock': False}) is False
    result = project(application)
    assert not any(r['application_state'] == 'applied' for r in result['routes'])
