"""P2-1 Phase 2.1: persisted UXM topology profile.

Replaces the in-code-only ``UxmTopologyProfile`` dataclass registry (kept
in ``app/hal/uxm_test_profiles.py``). Operators can now create / edit /
delete topology profiles in the GUI without a code change + redeploy.

The 7 historical in-code built-in templates (``caict_n78_2x2`` etc.)
are seeded by Alembic on first migration and marked
``is_system_preset=True`` so the GUI shows them as read-only — same
pattern as ``ChamberConfiguration.is_system_preset``. Operators clone
a preset to customise.

Schema choice — flat columns (not a single JSON blob) — matches the
chamber model: makes ``SELECT ... WHERE band='N78'`` cheap and Pydantic
schema mapping straightforward. The trade-off is that adding a new
field requires an Alembic migration; that's acceptable here because
the NR/MIMO/MAC-throughput surface only changes when a new UXM Test
App ships, not on operator activity.
"""
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Float, JSON, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.db.database import Base


class InstrumentTopologyProfile(Base):
    """A persisted topology profile bound to a UXM Test App.

    See ``UxmTopologyProfile`` (``app/hal/uxm_test_profiles.py``) for the
    field-by-field semantics — this table mirrors that dataclass field
    set. The dataclass remains the canonical runtime shape;
    ``topology_profile_service.to_dataclass()`` builds one from a row.
    """
    __tablename__ = "instrument_topology_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Stable string identifier — distinct from UUID PK so seeded
    # built-ins keep their historical "caict_n78_2x2" identity across
    # re-seeds, and so the existing API contract
    # (``connection_params['topology_profile_id']`` references a string,
    # not a UUID) stays unchanged.
    profile_id = Column(
        String(100), unique=True, nullable=False, index=True,
        comment="Stable identifier — built-ins use code-defined IDs "
                "('caict_n78_2x2'); operator-created use 'custom_<slug>'.",
    )
    name = Column(String(255), nullable=False, comment="Friendly name shown in GUI dropdown")
    description = Column(Text, comment="Operator-visible description")
    category = Column(
        String(50), default="general", nullable=False,
        comment="Grouping: siso | mimo | calibration | general",
    )

    # --- NR cell params ---
    band = Column(String(20), default="N78", nullable=False)
    frequency_mhz = Column(Float, default=3500.0, nullable=False)
    bandwidth_mhz = Column(Float, default=100.0, nullable=False)
    scs_khz = Column(Integer, default=30, nullable=False)
    duplex = Column(String(10), default="TDD", nullable=False)
    arfcn = Column(Integer, nullable=True)

    # --- MIMO ---
    mimo_layers = Column(Integer, default=2, nullable=False)
    mimo_port_preset = Column(String(20), default="2x2", nullable=False)

    # --- Power ---
    dl_power_dbm = Column(Float, default=-50.0, nullable=False)
    ssb_power_dbm = Column(Float, default=-50.0, nullable=False)

    # --- FRC / modulation ---
    modulation = Column(String(20), default="256QAM", nullable=False)
    target_mcs = Column(Integer, default=28, nullable=False)

    # --- 3GPP MAC throughput knobs (TR 37.977) ---
    sched_algo = Column(String(20), default="FULLBUFFER", nullable=False)
    enable_amc = Column(Boolean, default=False, nullable=False)
    tdd_pattern = Column(String(20), default="DDDSU", nullable=False)
    tdd_period = Column(String(20), default="5MS", nullable=False)
    harq_max_trans = Column(Integer, default=4, nullable=False)
    harq_processes = Column(Integer, default=16, nullable=False)
    csi_rs_ports = Column(Integer, nullable=True)
    stat_count = Column(Integer, default=5000, nullable=False)

    # --- Cell + state file ---
    cell_id = Column(String(20), default="CELL0", nullable=False)
    state_file = Column(
        String(500), nullable=True,
        comment="Optional UXM instrument-side SCPI export file path (created by "
                "SYSTem:SCPI:EXPort); when set, configure/set_cell_config "
                "short-circuit to SYSTem:SCPI:IMPort + :STATus? readback (P1-67).",
    )

    # --- Test App compat declaration ---
    compatible_test_apps = Column(
        JSON, default=list, nullable=False,
        comment='List of Test App PROFILE_NAME values this profile is '
                'compatible with (e.g. ["5G_NR_Test"]). Empty = any.',
    )

    notes = Column(Text, default="", comment="Operator notes / connection hints")

    # --- System preset marker — see chamber.is_system_preset for the
    # rationale. PUT / DELETE on a row with is_system_preset=True is
    # rejected at the API layer so the canonical built-ins survive
    # operator edits; clone-to-edit is the supported mutation path. ---
    is_system_preset = Column(
        Boolean, nullable=False, default=False, server_default='false',
        index=True,
        comment='True for the 7 built-in profiles seeded by the Alembic '
                'data migration; rejects PUT/DELETE. Operator copies clear it.',
    )

    # --- Audit ---
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), nullable=True)
