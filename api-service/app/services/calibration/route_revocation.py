"""采用撤销的单一读取与追加入口；不重写历史，不接触仪器。"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import update

from app.models.diagnostic_run import DiagnosticRun
from app.models.route_calibration import RouteCalibrationApplication, RouteCalibrationRevocation
from app.schemas.route_calibration import RouteRevocationRecord


def lock_acquisition_runs(db, run_ids):
    """复用采集行建立确认/撤销/冻结的提交次序，锁保持到调用方commit/rollback。

    SQLite不支持SELECT FOR UPDATE，使用不改列值的UPDATE取得数据库写锁；
    PostgreSQL按UUID稳定顺序取行锁。失败直接传播，不能继续冻结为可用。
    """
    for run_id in sorted(set(run_ids), key=str):
        if db.get_bind().dialect.name == 'sqlite':
            db.execute(update(DiagnosticRun).where(DiagnosticRun.id == run_id)
                       .values(id=DiagnosticRun.id).execution_options(synchronize_session=False))
        else:
            db.query(DiagnosticRun.id).filter_by(id=run_id).with_for_update().one()


def revoked_run_ids(db, lab_id):
    return {row[0] for row in db.query(RouteCalibrationRevocation.acquisition_run_id)
            .filter_by(lab_profile_id=lab_id).all()}


def _application(db, lab_id, application_id):
    row = db.query(RouteCalibrationApplication).filter_by(id=application_id, lab_profile_id=lab_id).one_or_none()
    if row is None:
        raise LookupError('本实验室中没有这条采用记录')
    return row


def read_route_revocation(db, lab_id, application_id):
    application = _application(db, lab_id, application_id)
    row = db.query(RouteCalibrationRevocation).filter_by(lab_profile_id=lab_id,
        acquisition_run_id=application.acquisition_run_id).one_or_none()
    return RouteRevocationRecord.model_validate(row.record) if row is not None else None


def revoke_route_calibration(db, lab_id, application_id, request):
    from app.services.calibration.route_calibration import RouteApplicationConflict
    try:
        application = _application(db, lab_id, application_id)
        lock_acquisition_runs(db, [application.acquisition_run_id])
        existing = read_route_revocation(db, lab_id, application_id)
        if existing is not None:
            if existing.reason != request.reason:
                raise RouteApplicationConflict('该次采集已按另一理由撤销，原记录不可覆盖')
            db.commit()
            return existing, False
        record = RouteRevocationRecord(id=uuid4(), lab_profile_id=lab_id,
            application_id=application.id, acquisition_run_id=application.acquisition_run_id,
            reason=request.reason, revoked_at=datetime.now(timezone.utc), revoked_by=None)
        db.add(RouteCalibrationRevocation(id=record.id, lab_profile_id=lab_id,
            application_id=application.id, acquisition_run_id=application.acquisition_run_id,
            record=record.model_dump(mode='json')))
        db.commit()
        return record, True
    except Exception:
        db.rollback()
        raise
