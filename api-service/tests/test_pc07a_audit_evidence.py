"""真实HTTP只读审计包；仪器数据为隔离构造，不代表现场测量。"""
import copy
import hashlib
import json
from uuid import UUID,uuid4
import pytest
from tests.test_pc07a_revocation_impact import (
    archived,db_session,chamber,topology_two_chains,lab_profile,client,configured,
    real_capture,legacy,launch,confirm,payload,application,
)


def source(report):
    return next(row for row in report.content_data['calibration_traceability']['routes']
                if row['source_kind']=='confirmed_route')


@pytest.mark.asyncio
async def test_audit_export_keeps_original_evidence_and_revocation_is_not_formal_delivery(archived,client,db_session,configured,tmp_path):
    from app.models.diagnostic_run import DiagnosticRun
    execution,report=archived
    frozen=copy.deepcopy(report.content_data);config=copy.deepcopy(execution.config)
    route=source(report);run_id=UUID(route['source_snapshot']['acquisition_run_id'])
    run=db_session.get(DiagnosticRun,run_id);raw=copy.deepcopy(run.sequence_evidence)
    url=f'/api/v1/reports/{report.id}/calibration-audit'
    response=client.get(url)
    assert response.status_code==200,response.text
    (tmp_path/'audit-response.json').write_text(response.text)
    data=response.json()
    assert data['audit_kind']=='calibration_audit' and data['formal_eligible'] is False
    assert data['original_report_content']==frozen
    item=next(r for r in data['sources'] if r['source_id']==route['source_id'])
    assert item['availability']=='available' and item['recorded_evidence']==raw
    assert item['retrieved_sha256']==hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    assert item['frozen_source_snapshot']==route['source_snapshot']
    assert data['uncertainty_budget_status']=='unknown'
    assert 'attachment;' in response.headers['content-disposition']
    assert str(report.id) in response.headers['content-disposition']
    # 当前选择指针和实验室名称改变，不从当前配置补历史。
    from app.models.route_calibration import RouteCalibrationSelection
    db_session.query(RouteCalibrationSelection).delete(synchronize_session=False)
    configured.name='后来修改的实验室名称';db_session.commit()
    unchanged=client.get(url).json()
    assert unchanged['traceability']==data['traceability'] and unchanged['sources']==data['sources']
    # 后来的采用撤销不抹掉原始审计材料，也不放开正式PDF交付。
    revoked=client.post(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications/{route["source_id"]}/revocation',json={'confirmed':True,'reason':'核查参考件'})
    assert revoked.status_code==201
    report.file_path=str(tmp_path/'original.pdf');(tmp_path/'original.pdf').write_bytes(b'original');db_session.commit()
    assert client.get(f'/api/v1/reports/{report.id}/download').status_code==409
    after=client.get(url);assert after.status_code==200,after.text
    assert after.json()['current_revocation']['status']=='revoked'
    assert after.json()['original_report_content']==frozen and after.json()['formal_eligible'] is False
    db_session.refresh(report);db_session.refresh(execution);db_session.refresh(run)
    assert report.content_data==frozen and execution.config==config and run.sequence_evidence==raw
    assert (tmp_path/'original.pdf').read_bytes()==b'original'


@pytest.mark.asyncio
@pytest.mark.parametrize('corruption',['run_id','lab_id','net_loss','malformed','indices','kind','target','analyzer','missing'])
async def test_unrelated_or_corrupt_capture_is_not_attached(archived,client,db_session,corruption):
    from app.models.diagnostic_run import DiagnosticRun
    _,report=archived;route=source(report)
    row=db_session.get(DiagnosticRun,UUID(route['source_snapshot']['acquisition_run_id']))
    evidence=copy.deepcopy(row.sequence_evidence)
    capture=evidence['extra']['fixed_route_acquisition']
    if corruption=='run_id':capture['run_id']=str(uuid4())
    elif corruption=='lab_id':capture['lab_profile_id']=str(uuid4())
    elif corruption=='net_loss':capture['net_loss_db']+=1
    elif corruption=='indices':capture['exchanges']=[]
    elif corruption=='kind':row.kind='other'
    elif corruption=='target':row.target_name='other'
    elif corruption=='analyzer':capture['configuration']['analyzer_binding']={'other':'instrument'}
    else:evidence={'extra':{'fixed_route_acquisition':'corrupt'}}
    row.sequence_evidence=None if corruption=='missing' else evidence;db_session.commit()
    result=client.get(f'/api/v1/reports/{report.id}/calibration-audit')
    assert result.status_code==200,result.text
    item=next(r for r in result.json()['sources'] if r['source_id']==route['source_id'])
    assert item['availability']=='unavailable' and item['recorded_evidence'] is None and item['retrieved_sha256'] is None
    assert item['frozen_source_snapshot']==route['source_snapshot']


@pytest.mark.asyncio
async def test_malformed_historical_identifier_preserves_unknown_audit(archived,client,db_session):
    from datetime import datetime
    from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
    execution,report=archived
    measurements=copy.deepcopy(execution.measurements)
    frozen=measurements['phases']['measure']['path_loss_application']['route_compensation']
    frozen['route_entries'][0]['source_id']={'legacy':'unparseable'}
    execution.measurements=measurements
    report.content_data=_build_mimo_ota_content_data(execution,datetime.utcnow());db_session.commit()
    assert client.get(f'/api/v1/reports/{report.id}').status_code==200
    response=client.get(f'/api/v1/reports/{report.id}/calibration-audit')
    assert response.status_code==200,response.text
    assert response.json()['traceability']['routes'][0]['source_id']=={'legacy':'unparseable'}
    assert response.json()['sources'][0]['source_id'] is None
    assert response.json()['sources'][0]['recorded_evidence'] is None
    assert response.json()['formal_eligible'] is False


def test_audit_contract():
    from pathlib import Path
    import yaml
    from app.main import app
    root=Path(__file__).parents[2]
    checked=yaml.safe_load((root/'api/openapi.yaml').read_text());live=app.openapi()
    for name in ['ReportCalibrationAudit','CalibrationAuditSource']:
        assert checked['components']['schemas'][name]==live['components']['schemas'][name]
        assert name in (root/'gui/src/types/api.generated.ts').read_text()
    route='/api/v1/reports/{report_id}/calibration-audit'
    assert checked['paths'][route]==live['paths'][route]


def test_gui_audit_request_rejects_wrong_report_or_formal_envelope():
    from pathlib import Path
    import subprocess
    script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
let next={report_id:'report',audit_kind:'calibration_audit',formal_eligible:false};let calls=[];
const client={get:async(...args)=>{calls.push(args);return {data:JSON.stringify(next)}}};const exports={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/api/reportService.ts','utf8'),
{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports,require:name=>{assert.equal(name,'./client');return {default:client}}});
(async()=>{
 assert.equal(JSON.parse(await exports.fetchCalibrationAudit('report')).formal_eligible,false);
 assert.equal(calls[0][1].responseType,'text');
 assert.equal(calls[0][0],'/reports/report/calibration-audit');
 for(const patch of [{report_id:'other'},{audit_kind:'formal'},{formal_eligible:true}]){
  const old=next;next={...next,...patch};await assert.rejects(()=>exports.fetchCalibrationAudit('report'));next=old;
 }
 const raw='{\"report_id\":\"report\",\"audit_kind\":\"calibration_audit\",\"formal_eligible\":false,\"frequency\":2595.0}';
 client.get=async()=>({data:raw});assert.equal(await exports.fetchCalibrationAudit('report'),raw);
 client.get=async()=>{throw Error('unavailable')};await assert.rejects(()=>exports.fetchCalibrationAudit('report'));
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).parents[2]/'gui',capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
