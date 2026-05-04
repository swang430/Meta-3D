"""Phase 2.4a schema migration: extend test_executions for VRT + create vrt_kpi_samples.

What this script does (idempotent — safe to re-run):

1. Adds 11 new columns to `test_executions` (all nullable):
   scenario_id, topology_id, mode, notes, config, vrt_runtime_status,
   execution_logs, execution_events, execution_warnings, phase_results,
   hardware_status

2. Drops NOT NULL on `test_executions.test_plan_id` and `test_executions.test_case_id`
   so VRT-direct executions (created via /road-test/executions without a parent
   TestPlan) can land in the table.

3. Creates `vrt_kpi_samples` table with cascade-delete FK to test_executions
   and a (execution_id, time_s) composite index.

Targets PostgreSQL (production). For test environments using SQLite,
`Base.metadata.create_all()` already builds the new schema from the updated
ORM models, so this migration is unnecessary there.

Usage:
    cd api-service
    .venv/bin/python scripts/migrate_phase2_4_schema.py
"""
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from app.db.database import engine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migrate_phase2_4")

# (column_name, SQL type) — all nullable, all idempotent via ADD COLUMN IF NOT EXISTS
NEW_TEST_EXECUTION_COLUMNS = [
    ("scenario_id", "VARCHAR(255)"),
    ("topology_id", "VARCHAR(255)"),
    ("mode", "VARCHAR(50)"),
    ("notes", "TEXT"),
    ("config", "JSONB"),
    ("vrt_runtime_status", "JSONB"),
    ("execution_logs", "JSONB"),
    ("execution_events", "JSONB"),
    ("execution_warnings", "JSONB"),
    ("phase_results", "JSONB"),
    ("hardware_status", "JSONB"),
]


def main() -> int:
    dialect = engine.dialect.name
    if dialect != "postgresql":
        logger.warning(
            "This migration targets PostgreSQL; current dialect is %s. "
            "For SQLite test environments, schema is created from ORM via "
            "Base.metadata.create_all(). Aborting.",
            dialect,
        )
        return 0

    inspector = inspect(engine)
    if "test_executions" not in inspector.get_table_names():
        logger.error(
            "test_executions table does not exist; run app startup once to "
            "create it (init_db) before applying this migration."
        )
        return 1

    existing_cols = {c["name"] for c in inspector.get_columns("test_executions")}
    added = 0
    skipped = 0

    with engine.begin() as conn:
        # 1. Add new columns (idempotent)
        for name, sql_type in NEW_TEST_EXECUTION_COLUMNS:
            if name in existing_cols:
                logger.info("[skip] test_executions.%s already exists", name)
                skipped += 1
                continue
            conn.execute(text(f"ALTER TABLE test_executions ADD COLUMN {name} {sql_type}"))
            logger.info("[ok]   added test_executions.%s (%s)", name, sql_type)
            added += 1

        # 2. Drop NOT NULL on test_plan_id / test_case_id (idempotent: ALTER ... DROP NOT NULL is no-op if already nullable)
        for col in ("test_plan_id", "test_case_id"):
            conn.execute(
                text(f"ALTER TABLE test_executions ALTER COLUMN {col} DROP NOT NULL")
            )
            logger.info("[ok]   ensured test_executions.%s is nullable", col)

        # 3. Create vrt_kpi_samples table
        if "vrt_kpi_samples" not in inspector.get_table_names():
            conn.execute(text("""
                CREATE TABLE vrt_kpi_samples (
                    id UUID PRIMARY KEY,
                    execution_id UUID NOT NULL
                        REFERENCES test_executions(id) ON DELETE CASCADE,
                    time_s DOUBLE PRECISION NOT NULL,
                    rsrp_dbm DOUBLE PRECISION,
                    rsrq_db DOUBLE PRECISION,
                    sinr_db DOUBLE PRECISION,
                    rssi_dbm DOUBLE PRECISION,
                    dl_throughput_mbps DOUBLE PRECISION,
                    ul_throughput_mbps DOUBLE PRECISION,
                    latency_ms DOUBLE PRECISION,
                    bler_percent DOUBLE PRECISION,
                    cqi INTEGER,
                    ri INTEGER,
                    pmi INTEGER,
                    mcs INTEGER,
                    position JSONB,
                    velocity_kmh DOUBLE PRECISION,
                    event_occurred VARCHAR(255),
                    created_at TIMESTAMP NOT NULL DEFAULT now()
                )
            """))
            conn.execute(text(
                "CREATE INDEX ix_vrt_kpi_samples_execution_time "
                "ON vrt_kpi_samples (execution_id, time_s)"
            ))
            logger.info("[ok]   created vrt_kpi_samples table + index")
        else:
            logger.info("[skip] vrt_kpi_samples table already exists")

    logger.info(
        "\nMigration summary: %d columns added, %d skipped, vrt_kpi_samples ready",
        added,
        skipped,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
