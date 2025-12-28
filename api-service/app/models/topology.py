"""Topology database models"""
from sqlalchemy import Column, String, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from app.db.database import Base


class TopologyType(str, enum.Enum):
    """Topology type"""
    OTA = "ota"
    CONDUCTED = "conducted"
    HYBRID = "hybrid"


class Topology(Base):
    """
    Topology - System hardware topology configuration

    Defines the physical setup of instruments and devices for testing.
    """
    __tablename__ = "topologies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic info
    name = Column(String(255), nullable=False, comment="Topology name")
    description = Column(Text, nullable=True, comment="Topology description")
    topology_type = Column(
        String(50),
        nullable=False,
        default=TopologyType.OTA.value,
        comment="Topology type: ota | conducted | hybrid"
    )

    # Device configuration (JSON)
    devices = Column(Text, nullable=True, comment="JSON array of device configurations")

    # Status
    is_active = Column(Boolean, default=True, comment="Whether topology is active")
    is_default = Column(Boolean, default=False, comment="Whether this is the default topology")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Creator
    created_by = Column(String(255), nullable=True)
