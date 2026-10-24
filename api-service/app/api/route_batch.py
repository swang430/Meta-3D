"""实验室隔离的逐通路批采集；预览零I/O，取消仅提交请求。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.diagnostic_run import DiagnosticRun
from app.models.lab_profile import LabProfile
from app.schemas.route_batch import BatchPlanRequest, BatchPlan, BatchContinueRequest, BatchJobRecord
from app.services.calibration import route_batch_jobs as jobs
from app.services.calibration.fixed_route_jobs import AcquisitionBusy
from app.services.calibration.route_batch_plan import build_batch_plan
from app.services.calibration.route_calibration import RouteScopeConflict

router=APIRouter(prefix='/lab-profiles',tags=['拓扑逐通路批采集'])
BASE='/{lab_profile_id}/route-calibration-batches'


def _lab(db,lab_id):
    if db.get(LabProfile,lab_id) is None:
        raise HTTPException(404,'实验室配置不存在')


def _row(db,lab_id,job_id):
    row=db.query(DiagnosticRun).filter_by(id=job_id,lab_profile_id=lab_id,
        target_name=jobs.TARGET,kind='scpi_sequence').one_or_none()
    if row is None:
        raise HTTPException(404,'本实验室中没有此批记录')
    return row


def _record(db,row):
    """序列化缺损历史只显示unknown，不重建计划或释放证明。"""
    try:
        return BatchJobRecord.model_validate(jobs.record(db,row))
    except ValidationError:
        return BatchJobRecord(job_id=row.id,lab_id=row.lab_profile_id,status='incomplete',
            finalization_committed=False,f64_control_released=None,items=[],error='批审计记录缺损，需现场核验')


@router.post(BASE+'/preview',response_model=BatchPlan)
def preview(lab_profile_id: UUID,request: BatchPlanRequest,db: Session=Depends(get_db)):
    try:
        return build_batch_plan(db,lab_profile_id,request,None)
    except RouteScopeConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.post(BASE,response_model=BatchJobRecord,status_code=202)
async def start(lab_profile_id: UUID,request: BatchPlanRequest,
        idempotency_key: UUID=Header(alias='Idempotency-Key'),db: Session=Depends(get_db)):
    _lab(db,lab_profile_id)
    try:
        value=await jobs.start(db,lab_profile_id,request,idempotency_key=idempotency_key)
        return _record(db,_row(db,lab_profile_id,UUID(value['job_id'])))
    except (AcquisitionBusy,RouteScopeConflict) as exc:
        raise HTTPException(409,str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get(BASE,response_model=list[BatchJobRecord])
def history(lab_profile_id: UUID,limit: int=Query(20,ge=1,le=100),db: Session=Depends(get_db)):
    _lab(db,lab_profile_id)
    rows=db.query(DiagnosticRun).filter_by(lab_profile_id=lab_profile_id,target_name=jobs.TARGET,
        kind='scpi_sequence').order_by(DiagnosticRun.run_at.desc(),DiagnosticRun.id.desc()).limit(limit).all()
    return [_record(db,row) for row in rows]


@router.get(BASE+'/{job_id}',response_model=BatchJobRecord)
def progress(lab_profile_id: UUID,job_id: UUID,db: Session=Depends(get_db)):
    return _record(db,_row(db,lab_profile_id,job_id))


@router.post(BASE+'/{job_id}/continue',response_model=BatchJobRecord)
async def continue_job(lab_profile_id: UUID,job_id: UUID,request: BatchContinueRequest,db: Session=Depends(get_db)):
    row=_row(db,lab_profile_id,job_id)
    try:
        jobs.continue_job(db,lab_profile_id,job_id,**request.model_dump())
    except AcquisitionBusy as exc:
        raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return _record(db,row)


@router.post(BASE+'/{job_id}/cancel',response_model=BatchJobRecord)
async def cancel(lab_profile_id: UUID,job_id: UUID,db: Session=Depends(get_db)):
    row=_row(db,lab_profile_id,job_id)
    try:
        jobs.request_cancel(job_id)
    except AcquisitionBusy as exc:
        raise HTTPException(409,str(exc)) from exc
    return _record(db,row)
