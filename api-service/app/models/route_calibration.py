"""操作员采用记录，不是计量认证；记录追加，只有当前选择指针可推进。"""
import uuid
from sqlalchemy import Column, String, Float, Integer, JSON, ForeignKey, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base


class RouteCalibrationApplication(Base):
    __tablename__='route_calibration_applications'
    __table_args__=(UniqueConstraint('lab_profile_id','idempotency_key',name='uq_route_application_idempotency'),)
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    lab_profile_id=Column(UUID(as_uuid=True),ForeignKey('lab_profiles.id'),nullable=False,index=True)
    acquisition_run_id=Column(UUID(as_uuid=True),ForeignKey('diagnostic_runs.id'),nullable=False)
    topology_id=Column(UUID(as_uuid=True),ForeignKey('switch_topologies.id'),nullable=False)
    chain_id=Column(String(500),nullable=False)
    idempotency_key=Column(UUID(as_uuid=True),nullable=False)
    request_payload=Column(JSON,nullable=False)
    record=Column(JSON,nullable=False)


class RouteCalibrationSelection(Base):
    __tablename__='route_calibration_selections'
    __table_args__=(UniqueConstraint('lab_profile_id','topology_id','operating_mode','chain_id',
        'frequency_mhz','reference_identity_digest',name='uq_route_selection_scope'),)
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    lab_profile_id=Column(UUID(as_uuid=True),ForeignKey('lab_profiles.id'),nullable=False)
    topology_id=Column(UUID(as_uuid=True),ForeignKey('switch_topologies.id'),nullable=False)
    operating_mode=Column(String(100),nullable=False)
    chain_id=Column(String(500),nullable=False)
    frequency_mhz=Column(Float,nullable=False)
    reference_identity_digest=Column(String(64),nullable=False)
    application_id=Column(UUID(as_uuid=True),ForeignKey('route_calibration_applications.id'),nullable=False)
    version=Column(Integer,nullable=False)


@event.listens_for(RouteCalibrationApplication,'before_update')
@event.listens_for(RouteCalibrationApplication,'before_delete')
def _immutable_application(mapper,connection,target):
    raise ValueError('确认采用记录不可修改或删除；请追加新记录')
