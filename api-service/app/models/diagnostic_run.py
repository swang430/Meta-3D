"""Audit row for the workshop-tier diagnostic tools.

P3 (Phase 1): SCPI Console, SCPI sequences, and Commissioning ad-hoc all
write a row here whenever an operator runs something. The point is *not* to
substitute for TestExecution / CalibrationCertificate — those are formal,
audited, signed. This table answers the much fuzzier question that comes
up during debugging: "what did I (or my colleague) try last week, and did
it work?" Without it the only record is in shell history + log files.

Why a single table for SCPI + commissioning + sequence runs:
- They share lifecycle (start → run → success/error → optional log pointer).
- Operators search across them ("find all runs against PROPSIM today").
- Schema differences (params, output) are JSON; per-kind tables would force
  joins for every list view.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.db.database import Base


_JSON_PG_OR_SQLITE = JSONB().with_variant(JSON(), "sqlite")


class DiagnosticKind(str, enum.Enum):
    """Coarse type of run — used to filter list views and route to detail UI."""

    SCPI_COMMAND = "scpi_command"
    SCPI_SEQUENCE = "scpi_sequence"
    COMMISSIONING_PHASE = "commissioning_phase"  # single executor ad-hoc
    COMMISSIONING_FULL = "commissioning_full"    # 5-phase smoke test


class DiagnosticRun(Base):
    """One workshop-tier run.

    Outputs are truncated on write (~2KB) so a chatty SCPI sweep doesn't
    blow up row size. The full HAL/SCPI trace stays in the log files,
    pointed at by ``hal_trace_log_path``.
    """

    __tablename__ = "diagnostic_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    kind = Column(
        String(40),
        nullable=False,
        index=True,
        comment="One of DiagnosticKind values",
    )

    # Optional: SCPI commands fired at a hardcoded IP don't need a lab.
    lab_profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("lab_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    target_name = Column(
        String(255),
        nullable=False,
        comment=(
            "Human-readable target identifier. For SCPI_COMMAND this is the "
            "category key (e.g. 'channelEmulator'); for SCPI_SEQUENCE it's "
            "the sequence module name; for COMMISSIONING_PHASE it's the "
            "phase name (precheck/measure/...); for COMMISSIONING_FULL it's "
            "the test_case name or session id."
        ),
    )

    # Inputs as supplied by the operator (frequency, command text, overrides...).
    params = Column(_JSON_PG_OR_SQLITE)

    success = Column(Boolean, nullable=False, default=False, index=True)

    # First ~2KB of stdout / SCPI response / executor result; truncated on write.
    output_excerpt = Column(Text)

    error_message = Column(Text)

    duration_ms = Column(Integer, comment="Wall-clock duration end-to-end")

    hal_trace_log_path = Column(
        String(512),
        comment=(
            "Pointer into HAL/SCPI logs (path or path:start_line-end_line) so "
            "the GUI 'show full trace' link can fetch the slice without us "
            "duplicating verbose SCPI traffic into this row."
        ),
    )

    run_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    run_by = Column(String(100), comment="Operator id / name; free text for now")
