"""
Lab Profile Model — Phase 0

A LabProfile bundles the per-laboratory configuration needed to run a TestCase:
which chamber, which calibration certificate is currently active, which
instrument units (vendor/model/connection) are wired up, and lab-level network
settings.

Before this abstraction existed, each TestCase carried a loose `test_environment`
JSON without referential integrity, and the active calibration could not be
bound to a specific run. LabProfile makes "CAICT-Lab-1" a first-class object
that TestCase + TestExecution can reference.

Notes:
- `instrument_bindings` is JSONB for now to avoid touching the global
  one-connection-per-category model. The shape is documented in the column
  comment; future work may promote this to a join table once multiple labs
  start sharing the same physical instruments.
- `is_active` enables soft-deactivation without breaking historical executions
  that point at this profile.
"""
import uuid
from sqlalchemy import Column, String, Boolean, Text, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base

_JSON_PG_OR_SQLITE = JSONB().with_variant(JSON(), "sqlite")


class LabProfile(Base):
    """Per-laboratory configuration bundle (chamber + calibration + instruments + network)."""

    __tablename__ = "lab_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True, index=True,
                  comment='Lab identifier, e.g. "CAICT-Lab-1"')
    description = Column(Text)
    organization = Column(String(255), comment='Operating organization, e.g. "中国信通院"')
    location = Column(String(500), comment="Street address or facility")

    chamber_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chamber_configurations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Anechoic chamber configuration this lab uses",
    )

    active_calibration_certificate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("calibration_certificates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Currently-valid system calibration certificate. Historical certs "
                "remain queryable via calibration_certificates.lab_name and dates.",
    )

    instrument_bindings = Column(
        _JSON_PG_OR_SQLITE,
        comment='Array of {category_id, instrument_model_id, connection_endpoint, '
                'driver_mode, role}. Schema: '
                '[{"category_id": uuid, "instrument_model_id": uuid?, '
                '"connection_endpoint": "192.168.1.10:5025", '
                '"driver_mode": "auto|mock|real", "role": "primary_channel_emulator"}]',
    )

    network_config = Column(
        _JSON_PG_OR_SQLITE,
        comment="Lab-level network parameters: subnet, vlan, time_sync_server, etc.",
    )

    extra_metadata = Column(
        _JSON_PG_OR_SQLITE,
        comment="Free-form: accreditation body, contact info, equipment notes, etc.",
    )

    is_active = Column(Boolean, default=True, nullable=False, index=True,
                       comment="Soft-deactivation flag; historical executions stay valid")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100))

    chamber_config = relationship("ChamberConfiguration", foreign_keys=[chamber_config_id])
    active_calibration_certificate = relationship(
        "CalibrationCertificate", foreign_keys=[active_calibration_certificate_id]
    )
