"""Bootstrap history table.

Records which seed jobs have already run against this database, so the
bootstrap CLI is idempotent across deploy / restart / re-run. Conceptually
parallel to alembic_version: alembic owns schema, bootstrap owns
*default data*, both leave a per-DB tombstone so reruns are no-ops.

Each entry is one (seeder_name, seeder_version) pair. Bumping a seeder
version is the supported way to ship new defaults to existing
installations — bootstrap will see the version mismatch and re-run that
seeder (which must still be idempotent against existing rows it owns).
"""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.database import Base


class BootstrapHistory(Base):
    __tablename__ = "bootstrap_history"

    seeder_name = Column(String(100), primary_key=True,
                         comment="Stable identifier of the seeder, e.g. 'chamber_presets'")
    seeder_version = Column(Integer, nullable=False,
                            comment="Bump this in the seeder when default data changes; "
                                    "bootstrap re-runs when DB version < code version")
    rows_inserted = Column(Integer, nullable=False, default=0,
                           comment="How many rows the last successful run created")
    rows_skipped = Column(Integer, nullable=False, default=0,
                          comment="How many rows were already present and left untouched")
    last_run_at = Column(DateTime, server_default=func.now(),
                         onupdate=func.now(), nullable=False)
