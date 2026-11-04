"""撤销是当前独立事实，不改写历史报告内容或文件。"""
import copy
import pytest

from tests.test_pc07a1_report_traceability import (
    db_session, chamber, topology_two_chains, lab_profile, client, configured,
    real_capture, legacy, launch, confirm, payload, application,
)


@pytest.fixture
async def archived(application,launch,configured,db_session):
    from datetime import datetime
    from app.services.mimo_ota.path_loss_preflight import evaluate_path_loss_preflight
    from tests.test_mimo_ota_report_verified_backcompat import _path_loss_report_phases
    from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
    from app.services.report_service import ReportService
    execution=await launch()
    own_application=evaluate_path_loss_preflight(db_session,execution,chamber_id=configured.chamber_config_id,
        frequency_mhz=2595,operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real').application
    execution.measurements={'phases':_path_loss_report_phases(own_application,verified=True)}
    db_session.commit()
    report=ReportService().create_report(db_session,title='当前撤销影响',report_type='single_execution',format='pdf',
        generated_by='mimo_ota.executors.report',test_execution_ids=[execution.id])
    report.content_data=_build_mimo_ota_content_data(execution,datetime.utcnow());report.status='completed'
    db_session.commit()
    return execution,report


@pytest.mark.asyncio
async def test_revoked_applied_source_blocks_generation_and_delivery_preserving_archive(
        archived, client, configured, db_session, tmp_path):
    execution, report = archived
    artifact = tmp_path/'original.pdf'
    artifact.write_bytes(b'original archive bytes')
    report.file_path = str(artifact)
    db_session.commit()
    original = copy.deepcopy(report.content_data)
    original_config = copy.deepcopy(execution.config)
    route = next(row for row in original['calibration_traceability']['routes'] if row['source_kind']=='confirmed_route')
    ident = route['source_id']
    result = client.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications/{ident}/revocation',
        json={'confirmed':True,'reason':'参考读数异常'})
    assert result.status_code == 201
    detail = client.get(f'/api/v1/reports/{report.id}')
    assert detail.status_code == 200, detail.text
    impact = detail.json()['calibration_revocation_impact']
    assert impact['status']=='revoked' and impact['items'][0]['source_id']==ident
    listing = client.get('/api/v1/reports').json()['reports']
    listed = next(row for row in listing if row['id']==str(report.id))
    assert listed['calibration_revocation_impact']['status']=='revoked'
    assert client.get(f'/api/v1/reports/{report.id}/download').status_code == 409
    assert client.post(f'/api/v1/reports/{report.id}/generate').status_code == 409
    from app.services.report_service import ReportService, ReportGenerationConflict
    with pytest.raises(ReportGenerationConflict,match='撤销'):
        ReportService().generate_report(db_session,report.id)
    fresh = ReportService().create_report(db_session,title='撤销后首次生成',report_type='single_execution',
        format='pdf',generated_by='test',test_execution_ids=[execution.id])
    assert client.post(f'/api/v1/reports/{fresh.id}/generate').status_code == 409
    db_session.refresh(report);db_session.refresh(execution)
    assert report.content_data==original and execution.config==original_config
    assert report.status=='completed' and artifact.read_bytes()==b'original archive bytes'


@pytest.mark.asyncio
async def test_later_unused_measurement_does_not_revoke_original_report(
        archived, client, configured, real_capture, db_session, tmp_path):
    _, report = archived
    artifact=tmp_path/'original.pdf';artifact.write_bytes(b'original')
    report.file_path=str(artifact);db_session.commit()
    later=confirm(client,configured,payload(client,configured,real_capture('-20','-10'))).json()
    assert client.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications/{later["id"]}/revocation',
        json={'confirmed':True,'reason':'后来一次采集异常'}).status_code==201
    detail=client.get(f'/api/v1/reports/{report.id}')
    assert detail.status_code==200
    assert detail.json()['calibration_revocation_impact']['items']==[]
    assert client.get(f'/api/v1/reports/{report.id}/download').status_code==200


@pytest.mark.asyncio
@pytest.mark.parametrize('state',['selected','missing','other_lab','wrong_execution'])
async def test_missing_or_unused_or_other_lab_source_never_becomes_revoked(
        archived, client, configured, db_session, state):
    from app.services.calibration.report_revocation_impact import report_calibration_revocation_impact
    from app.models.route_calibration import RouteCalibrationRevocation
    from app.models.lab_profile import LabProfile
    from uuid import UUID,uuid4
    execution,report=archived
    source=next(row for row in report.content_data['calibration_traceability']['routes'] if row['source_kind']=='confirmed_route')
    if state=='other_lab':
        other=LabProfile(id=uuid4(),name='另一实验室',is_active=True)
        db_session.add(other);db_session.flush()
        run=UUID(source['source_snapshot']['acquisition_run_id']);ident=uuid4()
        db_session.add(RouteCalibrationRevocation(id=ident,lab_profile_id=other.id,acquisition_run_id=run,
            application_id=UUID(source['source_id']),record={'id':str(ident),'lab_profile_id':str(other.id),
            'acquisition_run_id':str(run),'application_id':source['source_id'],'reason':'另一实验室',
            'revoked_at':'2026-11-04T09:00:00Z','revoked_by':None}))
    else:
        assert client.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications/{source["source_id"]}/revocation',
            json={'confirmed':True,'reason':'测试未使用来源'}).status_code==201
        measurements=copy.deepcopy(execution.measurements)
        if state=='missing':measurements['phases']['measure'].pop('path_loss_application')
        elif state=='wrong_execution':
            from app.hal.base_station_compatibility import canonical_payload_digest
            frozen=measurements['phases']['measure']['path_loss_application']['route_compensation']
            frozen['execution_id']=str(uuid4())
            frozen['digest']=canonical_payload_digest({k:v for k,v in frozen.items() if k!='digest'})
        else:measurements['phases']['measure']['path_loss_application'].update(
            status='not_applied',reason='diagnostic',value_disclosure='none',applied_chain_ids=[])
        execution.measurements=measurements
    db_session.commit()
    impact=report_calibration_revocation_impact(db_session,report)
    assert impact.status=='unknown' and impact.items==[]


@pytest.mark.asyncio
async def test_completed_traceable_archive_is_never_overwritten_even_before_revocation(archived,db_session,tmp_path):
    from app.services.report_service import ReportService,ReportGenerationConflict
    execution,report=archived
    artifact=tmp_path/'immutable.pdf';artifact.write_bytes(b'original')
    report.file_path=str(artifact);db_session.commit()
    original=copy.deepcopy(report.content_data)
    with pytest.raises(ReportGenerationConflict,match='原地重建'):
        ReportService().generate_report(db_session,report.id)
    assert artifact.read_bytes()==b'original' and report.content_data==original
    # 现有create入口仍可另建；不会覆盖原档。
    new=ReportService().create_report(db_session,title='另建',report_type='single_execution',format='pdf',
        generated_by='test',test_execution_ids=[execution.id])
    assert new.id!=report.id and new.status=='pending'



@pytest.mark.asyncio
async def test_late_generation_claim_cannot_replace_newly_archived_report(archived,db_session,tmp_path,monkeypatch):
    from app.services import report_service as service
    from app.models.report import TestReport
    _,report=archived
    report.status='pending';report.file_path=None;db_session.commit()
    original=copy.deepcopy(report.content_data)
    artifact=tmp_path/'winner.pdf';artifact.write_bytes(b'winner archive')
    original_claim=service.claim_report_generation
    def publish_before_late_claim(db,report_id,**kwargs):
        # 精确复现：入口已读取pending，另一writer在原子claim之前完成归档。
        db.query(TestReport).filter(TestReport.id==report_id).update(
            {TestReport.status:'completed',TestReport.file_path:str(artifact)},synchronize_session=False)
        db.commit()
        return original_claim(db,report_id,**kwargs)
    monkeypatch.setattr(service,'claim_report_generation',publish_before_late_claim)
    with pytest.raises(service.ReportGenerationConflict):
        service.ReportService().generate_report(db_session,report.id)
    db_session.refresh(report)
    assert report.status=='completed' and report.file_path==str(artifact)
    assert report.content_data==original and artifact.read_bytes()==b'winner archive'


@pytest.mark.asyncio
async def test_failed_archive_has_no_retry_but_completed_archive_keeps_download(archived,client,db_session,tmp_path):
    _,report=archived
    artifact=tmp_path/'kept.pdf';artifact.write_bytes(b'original')
    report.file_path=str(artifact);report.status='failed';db_session.commit()
    rows=client.get('/api/v1/reports').json()['reports']
    row=next(item for item in rows if item['id']==str(report.id))
    assert row['requires_regeneration'] and not row['regeneration_available']
    assert '不原地重建' in row['regeneration_reason']
    report.status='completed';db_session.commit()
    rows=client.get('/api/v1/reports').json()['reports']
    row=next(item for item in rows if item['id']==str(report.id))
    assert not row['requires_regeneration']
    assert client.get(f'/api/v1/reports/{report.id}/download').status_code==200


def test_revocation_impact_contract():
    from pathlib import Path
    import yaml
    from app.main import app
    root=Path(__file__).parents[2]
    checked=yaml.safe_load((root/'api/openapi.yaml').read_text())['components']['schemas']
    live=app.openapi()['components']['schemas']
    for name in ('ReportCalibrationRevocationImpact','ReportRevokedCalibrationSource','ReportResponse'):
        assert checked[name]==live[name]
        assert name in (root/'gui/src/types/api.generated.ts').read_text()
    assert checked['ReportSummary']['properties']['calibration_revocation_impact']==live['ReportSummary']['properties']['calibration_revocation_impact']
