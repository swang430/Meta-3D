"""Phase 2a-import: add provenance columns to probe_patterns.

Adds 6 columns to support distinguishing vendor-datasheet-imported patterns
from in-chamber-measured patterns:
  - source                  (default 'in_chamber_measured', backfill existing rows)
  - probe_model
  - probe_vendor
  - probe_serial
  - imported_file_format
  - coordinate_system       (default 'az_el')

Idempotent: checks information_schema before each ALTER. Safe to re-run.

Usage:
    cd api-service
    .venv/bin/python scripts/migrate_probe_pattern_source_columns.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from app.db.database import SessionLocal, engine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migrate_probe_pattern")

TABLE = "probe_patterns"

# (column_name, column_def_sql, post_backfill_sql_or_none)
NEW_COLUMNS = [
    ("source", "VARCHAR(30) NOT NULL DEFAULT 'in_chamber_measured'", None),
    ("probe_model", "VARCHAR(100)", None),
    ("probe_vendor", "VARCHAR(100)", None),
    ("probe_serial", "VARCHAR(100)", None),
    ("imported_file_format", "VARCHAR(20)", None),
    ("coordinate_system", "VARCHAR(20) DEFAULT 'az_el'", None),
]

INDEXES = [
    ("ix_probe_patterns_source", "CREATE INDEX IF NOT EXISTS ix_probe_patterns_source ON probe_patterns (source)"),
]


def _existing_columns() -> set[str]:
    inspector = inspect(engine)
    if TABLE not in inspector.get_table_names():
        raise RuntimeError(
            f"Table '{TABLE}' does not exist. Initialize the schema first via "
            "Base.metadata.create_all (e.g., start the API once)."
        )
    return {c["name"] for c in inspector.get_columns(TABLE)}


def main() -> None:
    existing = _existing_columns()
    logger.info("Existing %s columns: %d", TABLE, len(existing))

    db = SessionLocal()
    try:
        added: list[str] = []
        for name, coldef, _ in NEW_COLUMNS:
            if name in existing:
                logger.info("  [skip] %s already present", name)
                continue
            stmt = f"ALTER TABLE {TABLE} ADD COLUMN {name} {coldef}"
            logger.info("  [ddl ] %s", stmt)
            db.execute(text(stmt))
            added.append(name)

        for index_name, ddl in INDEXES:
            logger.info("  [idx ] %s", index_name)
            try:
                db.execute(text(ddl))
            except Exception as e:  # noqa: BLE001
                # SQLite + Postgres both support IF NOT EXISTS, but legacy MySQL
                # versions don't — log and continue.
                logger.warning("    skipped (%s)", e)

        db.commit()
        logger.info("Done. Added %d columns: %s", len(added), added)
    finally:
        db.close()


if __name__ == "__main__":
    main()
