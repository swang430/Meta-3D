"""Regression coverage for the alembic chain.

The chain must support TWO deploy paths converging on the same end state:

1. **Greenfield** — empty DB, run ``alembic upgrade head`` from scratch.
   The baseline migration creates all current tables; subsequent
   migrations detect the new columns already exist and skip.

2. **Brownfield** — DB existed before alembic adoption (tables created
   via ``Base.metadata.create_all()``) but missing the columns that
   later model edits introduced. Stamped at baseline, then upgraded:
   the drift-fix migrations actually add the missing columns.

A regression caught by Codex review on PR #2 was that the baseline was
a no-op while the next migration ran ``op.add_column`` against tables
that didn't exist yet — fine for already-stamped DBs, but the chain
couldn't bootstrap a fresh install. This test exercises both paths.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


# Tables + columns the chain MUST land regardless of starting state.
_EXPECTED_COLUMNS: dict[str, list[str]] = {
    "chamber_configurations": ["cable_sgh_to_sa_loss_db", "is_system_preset"],
    "probe_path_loss_calibrations": [
        "path_loss_db_by_rf_chain", "lab_profile_id",
        "operating_mode", "topology_id",
    ],
    "probe_patterns": [
        "source", "probe_model", "probe_vendor", "probe_serial",
        "imported_file_format", "coordinate_system",
    ],
    "bootstrap_history": ["seeder_name", "seeder_version"],
}
_EXPECTED_INDEXES: dict[str, list[str]] = {
    "chamber_configurations": ["ix_chamber_configurations_is_system_preset"],
    "probe_path_loss_calibrations": [
        "ix_probe_path_loss_calibrations_lab_profile_id",
    ],
    "probe_patterns": ["ix_probe_patterns_source"],
}


def _alembic_config(database_url: str) -> Config:
    """Build a Config that points alembic at our migrations dir, against
    a chosen DB URL. Mirrors what scripts/bootstrap.py does at runtime."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _assert_chain_end_state(engine) -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for table, cols in _EXPECTED_COLUMNS.items():
        assert table in tables, f"table {table!r} missing after upgrade"
        actual = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            assert col in actual, f"column {table}.{col} missing after upgrade"
    for table, indexes in _EXPECTED_INDEXES.items():
        actual_ix = {ix["name"] for ix in insp.get_indexes(table)}
        for ix_name in indexes:
            assert ix_name in actual_ix, f"index {ix_name} missing on {table}"


def test_greenfield_upgrade_from_scratch(tmp_path):
    """An empty DB must reach the head state via `alembic upgrade head`
    alone, with no manual create_all() or stamp() needed."""
    db_path = tmp_path / "greenfield.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)

    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")

    _assert_chain_end_state(engine)

    # alembic_version recorded at head
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    assert row is not None
    assert row[0] == "e863f092696b"


def test_brownfield_stamp_then_upgrade(tmp_path):
    """Existing DB with model-level create_all() but missing the drift
    columns: stamp baseline, then upgrade — the drift fix migrations
    should fire and add the columns rather than silently no-op."""
    db_path = tmp_path / "brownfield.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)

    # Pre-build the schema like the legacy create_all() path did.
    import app.models as _m
    for mod_info in pkgutil.iter_modules(_m.__path__):
        importlib.import_module(f"app.models.{mod_info.name}")
    from app.db.database import Base
    Base.metadata.create_all(bind=engine)

    # Simulate drift: tear out exactly the columns / table the later
    # migrations introduced. Indexes first — SQLite blocks DROP COLUMN
    # if an index references the column.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS bootstrap_history"))
        for table, ixs in _EXPECTED_INDEXES.items():
            for ix in ixs:
                conn.execute(text(f"DROP INDEX IF EXISTS {ix}"))
        for table, cols in _EXPECTED_COLUMNS.items():
            if table == "bootstrap_history":
                continue
            for col in cols:
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {col}"))

    # Sanity: drift is indeed present
    insp = inspect(engine)
    assert "is_system_preset" not in {
        c["name"] for c in insp.get_columns("chamber_configurations")
    }
    assert "bootstrap_history" not in insp.get_table_names()

    # Stamp baseline (no-op SQL; just records the version), then upgrade
    cfg = _alembic_config(url)
    command.stamp(cfg, "40fd1c51ff40")
    command.upgrade(cfg, "head")

    _assert_chain_end_state(engine)


def test_idempotent_upgrade_already_at_head(tmp_path):
    """Running `alembic upgrade head` against a DB that's already at
    head must be a no-op, not raise."""
    db_path = tmp_path / "at_head.db"
    url = f"sqlite:///{db_path}"
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    # Second run — should not error
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    _assert_chain_end_state(engine)
