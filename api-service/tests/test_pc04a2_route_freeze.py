"""执行创建时一次冻结混合来源；真实新来源仅替换外部VISA transport。"""
import asyncio
import copy
from datetime import datetime,timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_pc04a2_route_application import db_session, payload, confirm
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured
from tests.test_pc04a2_route_eligibility import real_capture
from app.models.probe_calibration import ProbePathLossCalibration
from app.models.test_plan import TestExecution
from app.services.mimo_ota.factory import build_mimo_ota_test_case
from app.services.mimo_ota.path_loss_preflight import evaluate_path_loss_preflight


@pytest.fixture
def legacy(db_session,configured,topology_two_chains):
    cert=ProbePathLossCalibration(chamber_id=configured.chamber_config_id,lab_profile_id=configured.id,
        topology_id=topology_two_chains.id,operating_mode='mimo_ota',frequency_mhz=2595,
        use_mock=False,status='valid',calibrated_at=datetime.utcnow(),valid_until=datetime.utcnow()+timedelta(days=2),
        probe_path_losses={'0':{'path_loss_db':123}},avg_path_loss_db=123,sgh_model='old-reference',sgh_gain_dbi=8,
        path_loss_db_by_rf_chain={
            'conn_p0v':dict(probe_id=0,polarization='V',ce_port='B1.1',total_insertion_loss_db=20),
            'conn_p0h':dict(probe_id=0,polarization='H',ce_port='B1.2',total_insertion_loss_db=30)})
    db_session.add(cert);db_session.commit()
    return cert


@pytest.fixture
def launch(db_session,configured,monkeypatch):
    from app.services import test_case_runner as runner
    # 其它仪表冻结已由其专属测试覆盖；此处不触碰真实硬件/后台相位。
    for name in ('freeze_execution_base_station_adapter_profile','freeze_execution_channel_emulator_binding',
            'freeze_execution_channel_emulator_plan','freeze_channel_emulator_execution_qualification',
            'freeze_execution_positioner_coordinate_profile'):
        monkeypatch.setattr(runner,name,lambda *args,**kwargs:None)
    monkeypatch.setattr(runner,'get_hal_service',lambda:SimpleNamespace(drivers={}))
    async def no_hardware(execution_id):
        return None
    monkeypatch.setattr(runner,'_run_case',no_hardware)
    async def create(frequency_mhz=2595):
        case,_=build_mimo_ota_test_case(db_session,name='freeze case',lab_profile_id=configured.id,
            config_overrides={'frequency_hz':frequency_mhz*1e6,'switch_mode_id':'mimo_ota'})
        execution=runner.launch_test_case_execution(db_session,case.id)
        task=runner._RUNNING_TASKS.get(str(execution.id))
        if task is not None:
            await task
        execution.status='completed';db_session.commit()
        return execution
    return create


def entries(execution):
    return {entry['chain_id']:entry for entry in (execution.config or {}).get('route_calibration_freeze',{}).get('route_entries',[])}


@pytest.mark.asyncio
@pytest.mark.parametrize('entrypoint',['runner','session','adhoc'])
async def test_missing_chamber_creation_freezes_unavailable_and_strict_hardware_stays_blocked(
        client,configured,db_session,launch,monkeypatch,entrypoint):
    from app.api import commissioning as api
    from app.services.test_execution import StepExecutionResult,StepExecutionStatus
    from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation
    chamber_id=configured.chamber_config_id
    configured.chamber_config_id=None;db_session.commit()
    monkeypatch.setattr(api,'_freeze_instrument_lease',lambda *args,**kwargs:lambda *args:None)
    async def no_hardware(context):
        return StepExecutionResult(status=StepExecutionStatus.SUCCESS)
    monkeypatch.setattr(api,'dispatch_step',no_hardware)
    if entrypoint=='runner':
        execution=await launch()
    else:
        endpoint='/api/v1/commissioning/sessions' if entrypoint=='session' else '/api/v1/commissioning/diagnostic/run-phase'
        body={'lab_profile_id':str(configured.id)}
        if entrypoint=='adhoc':body.update(phase_name='analysis',config_overrides={'frequency_hz':2595e6})
        else:body['frequency_hz']=2595e6
        response=client.post(endpoint,json=body)
        assert response.status_code in (200,201),response.text
        execution=db_session.query(TestExecution).order_by(TestExecution.started_at.desc()).first()
    frozen=read_execution_route_compensation(execution)
    assert frozen['chamber_id'] is None and frozen['topology_id'] is None
    assert frozen['legacy_selection_reason']=='missing_configuration'
    assert frozen['route_entries']==[] and frozen['source_records']==[] and frozen['warnings']
    verdict=evaluate_path_loss_preflight(db_session,execution,chamber_id=None,frequency_mhz=2595,
        operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real')
    assert verdict.blocker is not None and verdict.application['status']=='not_applied'
    configured.chamber_config_id=chamber_id;db_session.commit()
    assert read_execution_route_compensation(execution)==frozen  # 后配暗室不能补填旧执行


@pytest.mark.asyncio
async def test_new_confirmation_does_not_change_already_frozen_execution(client,configured,real_capture,
        legacy,launch,db_session,topology_two_chains):
    first=await launch()
    assert {key:value['value_db'] for key,value in entries(first).items()}=={'conn_p0v':20,'conn_p0h':30}
    original=copy.deepcopy(first.config['route_calibration_freeze'])
    row=real_capture()
    response=confirm(client,configured,payload(client,configured,row))
    assert response.status_code==201,response.text
    second=await launch()
    selected=entries(second)
    assert selected['conn_p0v']['value_db']==28 and selected['conn_p0v']['source_kind']=='confirmed_route'
    assert selected['conn_p0h']['value_db']==30 and selected['conn_p0h']['source_kind']=='legacy_certificate'
    assert selected['conn_p0v']['source_id']==response.json()['id']
    assert selected['conn_p0h']['source_id']==str(legacy.id)
    assert selected['conn_p0v']['certification_status']=='unknown'
    verdict=evaluate_path_loss_preflight(db_session,second,chamber_id=configured.chamber_config_id,
        frequency_mhz=2595,operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real')
    from app.services.mimo_ota.path_loss_application import parse_path_loss_application,path_loss_application_is_formally_verified
    application=verdict.application
    assert application['schema_version']==2 and application['status']=='applied'
    assert application['reason']=='selected' and application['certificate_id'] is None
    assert parse_path_loss_application(application)==application
    assert path_loss_application_is_formally_verified(application)
    partial={**application,'status':'applied','reason':'selected','value_disclosure':'verified','applied_chain_ids':['conn_p0v']}
    assert not path_loss_application_is_formally_verified(partial)
    from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation
    second_original=copy.deepcopy(second.config['route_calibration_freeze'])
    legacy.path_loss_db_by_rf_chain={};legacy.status='invalidated'
    topology_two_chains.connections=[];db_session.commit()
    assert read_execution_route_compensation(first)==original
    assert read_execution_route_compensation(second)==second_original
    assert first.config['route_calibration_freeze']==original


@pytest.mark.asyncio
async def test_frequency_mismatch_keeps_legacy_and_missing_chain_does_not_use_average(client,configured,
        real_capture,legacy,launch,db_session):
    row=real_capture()
    assert confirm(client,configured,payload(client,configured,row)).status_code==201
    legacy.frequency_mhz=3500
    legacy.path_loss_db_by_rf_chain={'conn_p0v':legacy.path_loss_db_by_rf_chain['conn_p0v']}
    db_session.commit()
    execution=await launch(3500)
    selected=entries(execution)
    assert selected.get('conn_p0v',{}).get('value_db')==20
    assert selected['conn_p0v']['source_kind']=='legacy_certificate'
    assert selected['conn_p0h']['source_kind']=='unavailable' and selected['conn_p0h']['value_db'] is None


def test_legacy_execution_without_freeze_never_queries_current_to_claim_application(db_session,configured,legacy):
    case,_=build_mimo_ota_test_case(db_session,name='historical',lab_profile_id=configured.id,
        config_overrides={'frequency_hz':2595e6})
    execution=TestExecution(test_case_id=case.id,status='completed',config={})
    db_session.add(execution);db_session.commit()
    result=evaluate_path_loss_preflight(db_session,execution,chamber_id=configured.chamber_config_id,
        frequency_mhz=2595,operating_mode='mimo_ota',precheck_strict_cal=True,
        channel_emulator_execution_mode='real')
    assert result.application['status']=='unknown'
    assert result.applied_certificate is None and result.blocker is not None


@pytest.mark.asyncio
async def test_precheck_reads_same_frozen_source_after_current_certificate_changes(configured,legacy,launch,db_session,monkeypatch):
    from app.services.mimo_ota.executors.precheck import PrecheckExecutor
    from app.services.test_execution import StepExecutionContext,StepDescriptor
    execution=await launch()
    legacy.status='invalidated';db_session.commit()
    monkeypatch.setattr('app.services.instrument_hal_service.get_hal_service',lambda:SimpleNamespace(drivers={}))
    context=StepExecutionContext(db=db_session,step=StepDescriptor(id='precheck',type='MIMO_OTA_PRECHECK',parameters={}),
        test_execution=execution,lab_profile=configured,calibration_certificate=None)
    result=await PrecheckExecutor().execute(context)
    assert result.measurements['path_loss_calibration_valid'] is True
    assert result.measurements['path_loss_application']['route_compensation']==execution.config['route_calibration_freeze']


@pytest.mark.parametrize('entrypoint',['session','adhoc'])
def test_commissioning_creation_freezes_before_return_or_dispatch(client,configured,legacy,db_session,monkeypatch,entrypoint):
    from app.api import commissioning as api
    from app.services.test_execution import StepExecutionResult,StepExecutionStatus
    monkeypatch.setattr(api,'_freeze_instrument_lease',lambda *args,**kwargs:lambda *args:None)
    observed=[]
    async def dispatch(context):
        observed.append(copy.deepcopy(context.test_execution.config))
        return StepExecutionResult(status=StepExecutionStatus.SUCCESS)
    monkeypatch.setattr(api,'dispatch_step',dispatch)
    if entrypoint=='session':
        response=client.post('/api/v1/commissioning/sessions',json={
            'lab_profile_id':str(configured.id),'frequency_hz':2595e6})
    else:
        response=client.post('/api/v1/commissioning/diagnostic/run-phase',json={
            'lab_profile_id':str(configured.id),'phase_name':'analysis',
            'config_overrides':{'frequency_hz':2595e6}})
    assert response.status_code in (200,201),response.text
    execution=db_session.query(TestExecution).order_by(TestExecution.started_at.desc()).first()
    assert {key:value['value_db'] for key,value in entries(execution).items()}=={'conn_p0v':20,'conn_p0h':30}
    if entrypoint=='adhoc':
        assert observed and observed[0]['route_calibration_freeze']==execution.config['route_calibration_freeze']


def test_existing_commissioning_phase_never_backfills_a_legacy_freeze(client,configured,legacy,db_session,monkeypatch):
    from app.api import commissioning as api
    from app.services.test_execution import StepExecutionResult,StepExecutionStatus
    monkeypatch.setattr(api,'_freeze_instrument_lease',lambda *args,**kwargs:lambda *args:None)
    async def dispatch(context):
        return StepExecutionResult(status=StepExecutionStatus.SUCCESS)
    monkeypatch.setattr(api,'dispatch_step',dispatch)
    response=client.post('/api/v1/commissioning/sessions',json={'lab_profile_id':str(configured.id),'frequency_hz':2595e6})
    assert response.status_code==201,response.text
    execution=db_session.query(TestExecution).one()
    execution.config={key:value for key,value in execution.config.items() if key!='route_calibration_freeze'}
    db_session.commit()
    response=client.post(f'/api/v1/commissioning/sessions/{execution.id}/phase/analysis')
    assert response.status_code==200,response.text
    db_session.refresh(execution)
    assert 'route_calibration_freeze' not in execution.config


@pytest.mark.asyncio
async def test_changed_live_route_cannot_receive_an_old_frozen_compensation(configured,legacy,launch,
        db_session,topology_two_chains,monkeypatch):
    execution=await launch()
    topology_two_chains.connections=[{**edge,**({'ce_port':'B3'} if edge['id']=='conn_p0v' else {})}
        for edge in topology_two_chains.connections]
    db_session.commit()
    from app.services.path_loss_calibration_service import ProbePathLossCalibrationService
    def no_latest(*args,**kwargs):
        raise AssertionError('读取执行不得重新选择证书')
    monkeypatch.setattr(ProbePathLossCalibrationService,'resolve_latest_calibration',no_latest)
    result=evaluate_path_loss_preflight(db_session,execution,chamber_id=configured.chamber_config_id,
        frequency_mhz=2595,operating_mode='mimo_ota',precheck_strict_cal=True,
        channel_emulator_execution_mode='real')
    assert result.blocker is not None
    assert result.applied_certificate is None
    assert entries(execution)['conn_p0v']['value_db']==20


@pytest.mark.asyncio
async def test_frozen_confirmed_identity_cannot_be_relabelled(client,configured,real_capture,legacy,launch):
    from app.hal.base_station_compatibility import canonical_payload_digest
    from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation
    row=real_capture();assert confirm(client,configured,payload(client,configured,row)).status_code==201
    execution=await launch();original=copy.deepcopy(execution.config['route_calibration_freeze'])
    for field,value in [('probe_id',99),('polarization','H'),('ce_port','B3')]:
        changed=copy.deepcopy(original)
        target=next(entry for entry in changed['route_entries'] if entry['source_kind']=='confirmed_route')
        target[field]=value
        changed['digest']=canonical_payload_digest({key:value for key,value in changed.items() if key!='digest'})
        view=SimpleNamespace(id=execution.id,config={'route_calibration_freeze':changed})
        with pytest.raises(ValueError):
            read_execution_route_compensation(view)


@pytest.mark.asyncio
async def test_display_and_unrelated_metadata_do_not_change_execution_target(configured,legacy,launch,
        db_session,topology_two_chains):
    execution=await launch()
    topology_two_chains.nodes=[{**node,'label':node['label'] if node['type']=='ce_port' else '新显示名',
        'position':{'x':100,'y':200},'params':{**node.get('params',{}),'calibration_note':'仅备注'}}
        for node in topology_two_chains.nodes]
    db_session.commit()
    result=evaluate_path_loss_preflight(db_session,execution,chamber_id=configured.chamber_config_id,
        frequency_mhz=2595,operating_mode='mimo_ota',precheck_strict_cal=True,
        channel_emulator_execution_mode='real')
    assert result.blocker is None
    assert result.applied_certificate.path_loss_db_by_rf_chain['conn_p0v']['total_insertion_loss_db']==20


@pytest.mark.asyncio
@pytest.mark.parametrize('use_mock,provenance',[(True,'simulated'),(None,'unknown')])
async def test_frozen_rejected_candidate_keeps_reason_without_granting_chain_values(configured,legacy,launch,
        db_session,use_mock,provenance):
    legacy.use_mock=use_mock;db_session.commit()
    execution=await launch()
    result=evaluate_path_loss_preflight(db_session,execution,chamber_id=configured.chamber_config_id,
        frequency_mhz=2595,operating_mode='mimo_ota',precheck_strict_cal=True,
        channel_emulator_execution_mode='real')
    assert result.selected_certificate is not None
    assert str(result.selected_certificate.id)==str(legacy.id)
    assert result.applied_certificate is None and provenance in result.blocker
    assert all(row['value_db'] is None for row in entries(execution).values())


@pytest.mark.asyncio
async def test_partial_newer_legacy_certificate_does_not_hide_an_older_covered_chain(configured,legacy,launch,db_session):
    legacy.calibrated_at=datetime.utcnow()-timedelta(hours=2)
    newer=ProbePathLossCalibration(chamber_id=legacy.chamber_id,lab_profile_id=legacy.lab_profile_id,
        topology_id=legacy.topology_id,operating_mode='mimo_ota',frequency_mhz=2595,use_mock=False,status='valid',
        calibrated_at=datetime.utcnow()-timedelta(hours=1),valid_until=datetime.utcnow()+timedelta(days=1),
        probe_path_losses={'0':{'path_loss_db':999}},avg_path_loss_db=999,sgh_model='other-old',sgh_gain_dbi=8,
        path_loss_db_by_rf_chain={'conn_p0v':dict(probe_id=0,polarization='V',ce_port='B1.1',total_insertion_loss_db=25)})
    db_session.add(newer);db_session.commit()
    execution=await launch()
    selected=entries(execution)
    assert selected['conn_p0v']['value_db']==25
    assert selected['conn_p0h']['value_db']==30
    assert selected['conn_p0v']['source_id']==str(newer.id)
    assert selected['conn_p0h']['source_id']==str(legacy.id)


@pytest.mark.asyncio
async def test_actual_measure_target_is_checked_even_if_current_database_changes_again(configured,legacy,launch,
        db_session,topology_two_chains):
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    from app.services.mimo_ota.route_calibration_freeze import frozen_route_identity_error
    execution=await launch()
    saved=copy.deepcopy(topology_two_chains.connections)
    topology_two_chains.connections=[{**edge,**({'ce_port':'B3'} if edge['id']=='conn_p0v' else {})} for edge in saved]
    db_session.commit()
    actual=orchestrate_switch_topology(db_session,configured.chamber_config_id,'mimo_ota')
    topology_two_chains.connections=saved;db_session.commit()
    # 实际消费对象已指向B3；再读当前DB又是B1.1，不能用后一次查询替它做判定。
    assert frozen_route_identity_error(db_session,execution.config['route_calibration_freeze']) is None
    assert frozen_route_identity_error(db_session,execution.config['route_calibration_freeze'],resolved_topology=actual) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('with_confirmation',[True,False])
@pytest.mark.parametrize('pad_label',['衰减器','?'])
async def test_multihop_freeze_uses_complete_route_without_relabelling_actual_target(client,configured,real_capture,
        legacy,launch,db_session,topology_two_chains,with_confirmation,pad_label):
    from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology
    from app.services.mimo_ota.route_calibration_freeze import frozen_route_identity_error,read_execution_route_compensation
    topology_two_chains.nodes=[*topology_two_chains.nodes,
        {'id':'pad-middle','type':'pad','label':pad_label,'params':{'ports':['in','out']}}]
    topology_two_chains.connections=[{**edge,**({'source':'pad-middle'} if edge['id']=='conn_p0v' else {})}
        for edge in topology_two_chains.connections]+[
        {'id':'feed-pad','source':'ce_b1','target':'pad-middle','source_pin':'out','target_pin':'in'}]
    topology_two_chains.operating_modes=[{'id':'mimo_ota','name':'normal',
        'active_connections':['feed-pad','conn_p0v','conn_p0h']}]
    db_session.commit()
    row=real_capture()
    if with_confirmation:
        response=confirm(client,configured,payload(client,configured,row))
        assert response.status_code==201,response.text
    execution=await launch()
    selected=entries(execution)
    assert selected['conn_p0v']['ce_port']=='B1.1'
    assert selected['conn_p0v']['source_kind']==('confirmed_route' if with_confirmation else 'legacy_certificate')
    assert selected['conn_p0v']['value_db']==(28 if with_confirmation else 20)
    assert selected['conn_p0h']['value_db']==30
    frozen=read_execution_route_compensation(execution)
    assert frozen_route_identity_error(db_session,frozen) is None
    if with_confirmation:
        verdict=evaluate_path_loss_preflight(db_session,execution,chamber_id=configured.chamber_config_id,
            frequency_mhz=2595,operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real')
        assert verdict.application['status']=='applied' and verdict.application['reason']=='selected'
        assert verdict.applied_certificate is None and verdict.blocker is None
    actual=orchestrate_switch_topology(db_session,configured.chamber_config_id,'mimo_ota')
    assert next(binding.ce_port for binding in actual.probe_bindings if binding.connection_id=='conn_p0v')=='B1.1'
    assert frozen_route_identity_error(db_session,frozen,resolved_topology=actual) is None
