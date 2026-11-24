"""登记实验室已审核的现场测量报告，查询和撤销已登记记录。"""
import base64
import csv
import hashlib

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.vrt_port_calibration import VrtPortCalibration
from app.services.road_test.port_calibration import ImportRecord, StrictModel, Text, read_report

router = APIRouter(prefix="/calibrations")


class Revocation(StrictModel):
    reason: Text


def summary(row):
    return {"id": str(row.id), "report_number": row.report_number, "report_file": row.report_file, "issuer": row.issuer, "evidence_sha256": row.evidence_sha256,
            "revoked_at": row.revoked_at, "revocation_reason": row.revocation_reason}


class PortCalibrationSummary(StrictModel):
    id: str
    issuer: str
    report_number: str
    report_file: str
    evidence_sha256: str
    revoked_at: datetime | None
    revocation_reason: str | None


class PortCalibrationDetail(PortCalibrationSummary):
    evidence_b64: str
    readings_b64: str


@router.get("", response_model=list[PortCalibrationSummary])
def list_records(db: Session = Depends(get_db)):
    return [summary(row) for row in db.query(VrtPortCalibration).order_by(VrtPortCalibration.id)]


@router.get("/{record_id}", response_model=PortCalibrationDetail)
def detail(record_id: UUID, db: Session = Depends(get_db)):
    row = db.get(VrtPortCalibration, record_id)
    if row is None:
        raise HTTPException(404, "找不到传导校准记录。")
    return {**summary(row), "evidence_b64": row.evidence_b64, "readings_b64": row.readings_b64}


@router.post("", status_code=201, response_model=PortCalibrationSummary)
def import_record(request: ImportRecord, db: Session = Depends(get_db)):
    try:
        evidence, data, readings, _ = read_report(request.report_file)
        digest = hashlib.sha256(data).hexdigest()
    except (OSError, KeyError, TypeError, ValueError, csv.Error) as exc:
        raise HTTPException(422, str(exc)) from exc
    row = VrtPortCalibration(evidence_sha256=digest, report_file=request.report_file,
                             issuer=evidence.issuer, report_number=evidence.report_number,
                             evidence_b64=base64.b64encode(data).decode(),
                             readings_b64=base64.b64encode(readings).decode())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(VrtPortCalibration).filter_by(evidence_sha256=digest).one_or_none()
        if row is None:
            prior = db.query(VrtPortCalibration).filter_by(issuer=evidence.issuer, report_number=evidence.report_number).first()
            if prior:
                raise HTTPException(409, "同一签发方的报告编号已登记，原文发生变化，请核对报告修订编号。")
            raise
    return summary(row)


@router.post("/{record_id}/revoke", response_model=PortCalibrationSummary)
def revoke(record_id: UUID, request: Revocation, db: Session = Depends(get_db)):
    db.query(VrtPortCalibration).filter(
        VrtPortCalibration.id == record_id, VrtPortCalibration.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc), "revocation_reason": request.reason},
             synchronize_session=False)
    db.commit()
    row = db.get(VrtPortCalibration, record_id)
    if row is None:
        raise HTTPException(404, "找不到传导校准记录。")
    return summary(row)
