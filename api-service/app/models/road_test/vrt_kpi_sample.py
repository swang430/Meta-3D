"""VRT KPI time-series sample model.

A single point in the time series collected during a VRT execution. Stored
as 1:N rows under a TestExecution to keep query/charting fast — embedding
hundreds-to-thousands of points in a JSON column would make scans slow and
prevent indexed time-range queries.
"""
import uuid

from sqlalchemy import Column, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.db.database import Base


class VrtKpiSample(Base):
    """One time-series KPI sample collected during a VRT execution."""

    __tablename__ = "vrt_kpi_samples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("test_executions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Parent TestExecution (cascade-delete on execution removal)",
    )

    # Sample timing (within execution)
    time_s = Column(Float, nullable=False, comment="Seconds since execution start")

    # Radio link KPIs
    rsrp_dbm = Column(Float)
    rsrq_db = Column(Float)
    sinr_db = Column(Float)
    rssi_dbm = Column(Float)

    # Throughput
    dl_throughput_mbps = Column(Float)
    ul_throughput_mbps = Column(Float)

    # Latency / quality
    latency_ms = Column(Float)
    bler_percent = Column(Float)

    # Modulation / MIMO
    cqi = Column(Integer)
    ri = Column(Integer)
    pmi = Column(Integer)
    mcs = Column(Integer)

    # Vehicle state at sample time
    position = Column(JSON, comment="{lat, lon, alt}")
    velocity_kmh = Column(Float)

    # Optional event marker (e.g., 'handover', 'beam_switch')
    event_occurred = Column(String(255))

    # Insert time (server-side)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# Composite index for time-range queries within an execution (charting / pagination)
Index(
    "ix_vrt_kpi_samples_execution_time",
    VrtKpiSample.execution_id,
    VrtKpiSample.time_s,
)
