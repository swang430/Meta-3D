"""只读取原执行与保存采集；独立审计包不是新报告或校准资格。"""
import copy
import hashlib
import json
from datetime import datetime,timezone
from pydantic import ValidationError
from app.models.test_plan import TestExecution
from app.models.diagnostic_run import DiagnosticRun
from app.schemas.fixed_route_acquisition import FixedRouteResult
from app.schemas.route_calibration import RouteApplicationRecord,RouteSelection
from app.schemas.report import CalibrationAuditSource,ReportCalibrationAudit
from app.services.calibration.fixed_route_jobs import TARGET
from app.services.calibration.route_calibration import _application_scope
from app.services.calibration.report_revocation_impact import report_calibration_revocation_impact
from app.services.mimo_ota.calibration_traceability import build_calibration_traceability


def _source(db,route,lab_id):
    snapshot=route.get('source_snapshot')
    # 损坏历史标识不能作为查询键；异常原值仍保留在包内traceability原文。
    def identifier(key):
        value=route.get(key)
        return value if isinstance(value,str) else None
    result=CalibrationAuditSource(chain_id=identifier('chain_id'),source_id=identifier('source_id'),
        source_kind=identifier('source_kind'),application_state=route.get('application_state','unknown'),
        availability='unsupported',reason='旧源或缺损来源仅保留原快照，不查相似记录替代。',
        acquisition_run_id=None,frozen_source_snapshot=copy.deepcopy(snapshot),recorded_evidence=None,
        retrieved_sha256=None,checked_exchange_indices=[])
    if route.get('source_kind')!='confirmed_route' or not isinstance(snapshot,dict):
        return result
    result.availability='unavailable'
    result.reason='原采集缺失、身份/内容关联冲突或交换索引不可核对；未附入原始读数。'
    try:
        source=RouteApplicationRecord.model_validate(snapshot)
        if str(source.id)!=route.get('source_id') or str(source.selection_snapshot.lab_profile_id)!=lab_id:
            return result
        result.acquisition_run_id=source.acquisition_run_id
        row=db.query(DiagnosticRun).filter_by(id=source.acquisition_run_id,
            lab_profile_id=source.selection_snapshot.lab_profile_id,kind='scpi_sequence',target_name=TARGET).one_or_none()
        if row is None or not isinstance(row.sequence_evidence,dict):return result
        original=row.sequence_evidence
        capture=FixedRouteResult.model_validate(original['extra']['fixed_route_acquisition'])
        if (capture.run_id!=row.id or capture.lab_profile_id!=row.lab_profile_id or
            capture.method!=source.method or capture.request.frequency_mhz!=source.frequency_mhz or
            capture.net_loss_db!=source.net_loss_db or capture.request.chain_id!=source.selection_snapshot.chain_id or
            RouteSelection.model_validate(capture.configuration.get('route_selection'))!=source.selection_snapshot):
            return result
        _,reference=_application_scope(capture,source.selection_snapshot)
        if source.reference_snapshot!=reference:return result
        evidence=source.adoption_evidence_snapshot
        if evidence.get('acquisition_run_id')!=str(row.id):return result
        indices=evidence.get('checked_exchange_indices')
        if (not isinstance(indices,list) or not indices or
            any(type(i) is not int or i<0 or i>=len(capture.exchanges) for i in indices) or
            len(set(indices))!=len(indices)):return result
        # 透传保存原文，不输出model_validate补默认值或record()投影后的数据。
        result.recorded_evidence=copy.deepcopy(original)
        result.retrieved_sha256=hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        result.checked_exchange_indices=copy.deepcopy(indices)
        result.availability='available'
        result.reason='当前取得保存原文且身份关联一致；不证明历史未改动，不重新授予来源或计量资格。'
    except (ValidationError,ValueError,TypeError,KeyError,AttributeError):
        return result
    return result


def build_report_calibration_audit(db,report):
    from app.services.report_service import normalized_report_execution_ids,is_mimo_ota_execution
    ids=normalized_report_execution_ids(report)
    if len(ids)!=1:raise ValueError('校准审计包仅支持关联唯一MIMO执行的报告。')
    execution=db.get(TestExecution,ids[0])
    if execution is None or not is_mimo_ota_execution(db,execution):
        raise ValueError('关联的MIMO执行不存在或身份不明确。')
    measurements=execution.measurements if isinstance(execution.measurements,dict) else {}
    phases=measurements.get('phases');measure=phases.get('measure') if isinstance(phases,dict) else None
    application=measure.get('path_loss_application') if isinstance(measure,dict) else None
    frozen=application.get('route_compensation') if isinstance(application,dict) else None
    if not isinstance(frozen,dict) or frozen.get('execution_id')!=str(execution.id):
        application=None;frozen={}
    trace=build_calibration_traceability(application)
    return ReportCalibrationAudit(report_id=report.id,execution_id=execution.id,
        exported_at=datetime.now(timezone.utc),original_report_content=copy.deepcopy(report.content_data or {}),
        traceability=trace,sources=[_source(db,route,frozen.get('lab_profile_id')) for route in trace['routes']],
        current_revocation=report_calibration_revocation_impact(db,report),limitations=[
            '独立校准审计包，不是正式报告；历史判词不代表当前可交付资格。',
            '原报告、原冻结与当前取回的采集原文分列；retrieved_sha256仅标识此次取回内容，不是归档时签名或历史防篡改证明。',
            '原采集request/samples/exchanges及missing_items、冻结source_snapshot/reference/coverage和应用位置按原字段保留，未补当前配置。',
            '完整计量不确定度预算未建立，保持unknown；重复性统计不等于完整预算。缺失范围不扩展为带宽或空间覆盖。'])
