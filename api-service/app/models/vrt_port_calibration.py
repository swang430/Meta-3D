"""保存现场报告原文和撤销原因，历史执行另存当时的适用性结果。"""
from uuid import uuid4

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class VrtPortCalibration(Base):
    __tablename__ = "vrt_port_calibrations"
    __table_args__ = (UniqueConstraint("issuer", "report_number", name="uq_vrt_calibration_issuer_report"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    evidence_sha256 = Column(String(64), nullable=False, unique=True)
    issuer = Column(String(128), nullable=False)
    evidence_b64 = Column(Text, nullable=False)
    report_file = Column(String(255), nullable=False)
    report_number = Column(String(500), nullable=False)
    readings_b64 = Column(Text, nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    revocation_reason = Column(Text)
