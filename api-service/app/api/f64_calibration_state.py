"""PC-03A：复用诊断租约与审计，不新增校准资格或数据库真值。"""
from uuid import UUID
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.diagnostic_sequence import RunSequenceRequest, run_diagnostic_sequence
from app.db.database import get_db
from app.models.diagnostic_run import DiagnosticRun, DiagnosticKind
from app.models.lab_profile import LabProfile
from app.schemas.f64_calibration_state import F64CalibrationState, F64StateRecord, F64StateRequest

router = APIRouter(prefix='/lab-profiles', tags=['F64 状态记录'])
SEQUENCE_KEY = 'propsim_f64_calibration_state'


def _lab(db, lab_id):
    if db.get(LabProfile, lab_id) is None:
        raise HTTPException(status_code=404, detail='实验室配置不存在')


def _record(row):
    state = None
    envelope = row.sequence_evidence
    extra = envelope.get('extra') if isinstance(envelope, dict) else None
    payload = extra.get('calibration_state') if isinstance(extra, dict) else None
    try:
        state = F64CalibrationState.model_validate(payload)
    except ValidationError:
        pass  # 历史缺损明确显示不完整，不重建或查询当前仪器。
    binding = extra.get('binding') if isinstance(extra, dict) else None
    if state and (not isinstance(binding, dict)
        or binding.get('lab_profile_id') != str(row.lab_profile_id)
        or binding.get('binding_digest') != state.binding_digest):
        state = None
    # SQLite 的 CURRENT_TIMESTAMP 为 UTC，但读取后无时区；必须在接口明确时区。
    run_at = row.run_at if row.run_at.tzinfo is not None else row.run_at.replace(tzinfo=timezone.utc)
    return F64StateRecord(diagnostic_run_id=row.id, lab_profile_id=row.lab_profile_id,
        run_at=run_at, success=row.success, error_message=row.error_message,
        record_status='complete' if state else 'incomplete', state=state)


@router.get('/{lab_profile_id}/f64-calibration-state', response_model=list[F64StateRecord])
def history(lab_profile_id: UUID, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    _lab(db, lab_profile_id)
    rows = db.query(DiagnosticRun).filter(DiagnosticRun.lab_profile_id == lab_profile_id,
        DiagnosticRun.kind == DiagnosticKind.SCPI_SEQUENCE.value,
        DiagnosticRun.target_name == SEQUENCE_KEY).order_by(DiagnosticRun.run_at.desc(), DiagnosticRun.id.desc()).limit(limit).all()
    return [_record(row) for row in rows]


@router.post('/{lab_profile_id}/f64-calibration-state', response_model=F64StateRecord)
async def capture(lab_profile_id: UUID, request: F64StateRequest, db: Session = Depends(get_db)):
    _lab(db, lab_profile_id)
    outcome = await run_diagnostic_sequence(SEQUENCE_KEY,
        RunSequenceRequest(lab_profile_id=lab_profile_id, params=request.model_dump()), db)
    row = db.get(DiagnosticRun, outcome.diagnostic_run_id)
    return _record(row)
