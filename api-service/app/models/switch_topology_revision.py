"""不可变接线声明快照；不代表执行或校准资格。"""
import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.database import Base
from app.models.switch_topology import _JSON_PG_OR_SQLITE


class SwitchTopologyRevision(Base):
    __tablename__ = 'switch_topology_revisions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topology_id = Column(UUID(as_uuid=True), ForeignKey('switch_topologies.id', ondelete='RESTRICT'), nullable=False)
    revision = Column(Integer, nullable=False)
    operation = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    restored_from_revision = Column(Integer, nullable=True)
    snapshot = Column(_JSON_PG_OR_SQLITE, nullable=False)
    recorded_metadata = Column(_JSON_PG_OR_SQLITE, nullable=False)
    __table_args__ = (UniqueConstraint('topology_id', 'revision', name='uq_switch_topology_revision'),)
