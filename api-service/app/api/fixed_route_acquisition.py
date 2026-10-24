"""按实验室隔离的固定通路自动采集入口，不发校准证书。"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.lab_profile import LabProfile
from app.models.diagnostic_run import DiagnosticRun
from app.schemas.fixed_route_acquisition import FixedRouteRequest, FixedRouteRecord
from app.services.calibration import fixed_route_jobs as jobs
from app.services.calibration.route_batch_jobs import batch_child_context

router = APIRouter(prefix='/lab-profiles', tags=['固定通路自动采集'])


def _row(db, lab_id, run_id):
    row = db.query(DiagnosticRun).filter_by(id=run_id, lab_profile_id=lab_id, target_name=jobs.TARGET, kind='scpi_sequence').one_or_none()
    if row is None:
        raise HTTPException(404, '本实验室中没有这条采集记录')
    return row


@router.post('/{lab_profile_id}/fixed-route-acquisitions', response_model=FixedRouteRecord, status_code=202)
async def start(lab_profile_id: UUID, request: FixedRouteRequest, db: Session = Depends(get_db)):
    try:
        return await jobs.start(db, lab_profile_id, request)
    except jobs.AcquisitionBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/{lab_profile_id}/fixed-route-acquisitions', response_model=list[FixedRouteRecord])
def history(lab_profile_id: UUID, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    if db.get(LabProfile, lab_profile_id) is None:
        raise HTTPException(404, '实验室配置不存在')
    rows = db.query(DiagnosticRun).filter_by(lab_profile_id=lab_profile_id, target_name=jobs.TARGET, kind='scpi_sequence').order_by(DiagnosticRun.run_at.desc(), DiagnosticRun.id.desc()).limit(limit).all()
    return [jobs.record(row, batch_context=batch_child_context(db,row)) for row in rows]


@router.get('/{lab_profile_id}/fixed-route-acquisitions/{run_id}', response_model=FixedRouteRecord)
def progress(lab_profile_id: UUID, run_id: UUID, db: Session = Depends(get_db)):
    row = _row(db, lab_profile_id, run_id)
    return jobs.record(row, batch_context=batch_child_context(db,row))


@router.post('/{lab_profile_id}/fixed-route-acquisitions/{run_id}/cancel', response_model=FixedRouteRecord)
async def cancel(lab_profile_id: UUID, run_id: UUID, db: Session = Depends(get_db)):
    row = _row(db, lab_profile_id, run_id)
    context = batch_child_context(db,row)
    if context is not None:
        parent = context.get('job_id')
        raise HTTPException(409, '此采集属于批作业，请从所属批入口取消；未确认已停发。'
            + (f' /api/v1/lab-profiles/{lab_profile_id}/route-calibration-batches/{parent}/cancel' if parent else ' 父批关联未核验，请现场核验。'))
    try:
        jobs.request_cancel(run_id)
    except jobs.AcquisitionBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return jobs.record(row, batch_context=batch_child_context(db,row))
