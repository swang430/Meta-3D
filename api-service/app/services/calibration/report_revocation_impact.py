"""原执行实际应用来源与当前撤销事实的交集；不改历史，不查当前配置补真。"""
from datetime import datetime, timezone
from uuid import UUID

from app.models.test_plan import TestExecution
from app.models.route_calibration import RouteCalibrationRevocation
from app.schemas.report import ReportCalibrationRevocationImpact, ReportRevokedCalibrationSource
from app.schemas.route_calibration import RouteRevocationRecord
from app.services.mimo_ota.calibration_traceability import build_calibration_traceability


def report_calibration_revocation_impact(db, report):
    from app.services.report_service import normalized_report_execution_ids
    execution_ids = normalized_report_execution_ids(report)
    unknown = not execution_ids
    items = []
    checked_source_count = 0
    for ident in dict.fromkeys(execution_ids):
        execution = db.get(TestExecution, ident)
        if execution is None:
            unknown = True
            continue
        measurements = execution.measurements if isinstance(execution.measurements, dict) else {}
        phases = measurements.get('phases')
        measure = phases.get('measure') if isinstance(phases, dict) else None
        application = measure.get('path_loss_application') if isinstance(measure, dict) else None
        frozen = application.get('route_compensation') if isinstance(application, dict) else None
        if not isinstance(frozen, dict) or frozen.get('execution_id') != str(execution.id):
            unknown = True
            continue
        trace = build_calibration_traceability(application)
        routes = trace['routes']
        if not any(route.get('application_state') == 'applied' for route in routes):
            unknown = True
        for route in routes:
            if route.get('application_state') != 'applied':
                # 未应用的候选不构成报告使用了该测量的事实。
                continue
            if route.get('source_kind') != 'confirmed_route':
                unknown = True  # #556撤销制度未覆盖既有证书，不宣称全部检查完毕。
                continue
            snapshot = route.get('source_snapshot')
            try:
                source_id = UUID(str(route['source_id']))
                if UUID(str(snapshot['id'])) != source_id:
                    raise ValueError('来源快照身份不一致')
                lab_id = UUID(str(snapshot['selection_snapshot']['lab_profile_id']))
                run_id = UUID(str(snapshot['acquisition_run_id']))
                if str(lab_id) != application['route_compensation']['lab_profile_id']:
                    raise ValueError('来源快照实验室不一致')
            except (KeyError, TypeError, ValueError):
                unknown = True
                continue
            event = db.query(RouteCalibrationRevocation).filter_by(
                lab_profile_id=lab_id, acquisition_run_id=run_id).one_or_none()
            checked_source_count += 1
            if event is not None:
                items.append(ReportRevokedCalibrationSource(execution_id=ident, chain_id=route['chain_id'],
                    source_id=source_id, revocation=RouteRevocationRecord.model_validate(event.record)))
    return ReportCalibrationRevocationImpact(status='revoked' if items else 'unknown' if unknown else 'not_detected',
        checked_at=datetime.now(timezone.utc), checked_source_count=checked_source_count, items=items,
        limitation='仅核对原执行实际应用的新采用测量撤销；未检测到撤销不代表正式资格。旧证书及缺损追溯范围未核验，原结论和原文件保持历史记录。')
