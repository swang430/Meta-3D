"""Phase 0 schema migration: create lab_profiles + bind TestCase to lab + calibration.

What this script does (idempotent — safe to re-run):

1. Creates `lab_profiles` table (ORM-driven via Base.metadata.create_all for
   the single new table) with FKs to chamber_configurations and
   calibration_certificates.

2. Adds two new nullable FK columns to `test_cases`:
   - lab_profile_id (REFERENCES lab_profiles ON DELETE SET NULL)
   - calibration_certificate_id (REFERENCES calibration_certificates ON DELETE SET NULL)

Targets PostgreSQL (production). For SQLite test environments, schema is
created automatically by Base.metadata.create_all() on app startup.

Usage:
    cd api-service
    .venv/bin/python scripts/migrate_phase0_lab_profile.py
"""
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from app.db.database import engine
from app.models.lab_profile import LabProfile  # noqa: F401 — registers table on Base

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migrate_phase0")

NEW_TEST_CASE_COLUMNS = [
    (
        "lab_profile_id",
        "UUID",
        "ALTER TABLE test_cases ADD CONSTRAINT fk_test_cases_lab_profile "
        "FOREIGN KEY (lab_profile_id) REFERENCES lab_profiles(id) ON DELETE SET NULL",
        "fk_test_cases_lab_profile",
    ),
    (
        "calibration_certificate_id",
        "UUID",
        "ALTER TABLE test_cases ADD CONSTRAINT fk_test_cases_calibration_cert "
        "FOREIGN KEY (calibration_certificate_id) REFERENCES calibration_certificates(id) ON DELETE SET NULL",
        "fk_test_cases_calibration_cert",
    ),
]


def _has_constraint(conn, table_name: str, constraint_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = :t AND constraint_name = :c"
        ),
        {"t": table_name, "c": constraint_name},
    ).first()
    return row is not None


def main() -> int:
    dialect = engine.dialect.name
    if dialect != "postgresql":
        logger.warning(
            "This migration targets PostgreSQL; current dialect is %s. "
            "For SQLite tests, Base.metadata.create_all() handles the new schema. "
            "Aborting.",
            dialect,
        )
        return 0

    inspector = inspect(engine)

    # 1. Create lab_profiles table (idempotent — checks existing tables first)
    if "lab_profiles" not in inspector.get_table_names():
        LabProfile.__table__.create(engine)
        logger.info("[ok]   created lab_profiles table")
    else:
        logger.info("[skip] lab_profiles table already exists")

    # 2. Add new FK columns to test_cases
    if "test_cases" not in inspector.get_table_names():
        logger.error(
            "test_cases table does not exist; run app startup once to create "
            "it before applying this migration."
        )
        return 1

    existing_cols = {c["name"] for c in inspector.get_columns("test_cases")}

    with engine.begin() as conn:
        for name, sql_type, fk_sql, constraint_name in NEW_TEST_CASE_COLUMNS:
            if name in existing_cols:
                logger.info("[skip] test_cases.%s already exists", name)
            else:
                conn.execute(text(f"ALTER TABLE test_cases ADD COLUMN {name} {sql_type}"))
                logger.info("[ok]   added test_cases.%s (%s)", name, sql_type)

            if _has_constraint(conn, "test_cases", constraint_name):
                logger.info("[skip] FK constraint %s already exists", constraint_name)
            else:
                conn.execute(text(fk_sql))
                logger.info("[ok]   added FK constraint %s", constraint_name)

            # Always ensure index exists (idempotent IF NOT EXISTS)
            idx_name = f"ix_test_cases_{name}"
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON test_cases ({name})"
            ))
            logger.info("[ok]   ensured index %s", idx_name)

    logger.info("\nPhase 0 migration complete: lab_profiles + test_cases FKs ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
