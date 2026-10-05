"""Migration leaves old instrument files unclaimed instead of guessing selected model."""
import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_old_rows_keep_unknown_owner_and_new_scd_names_are_scoped(monkeypatch):
    path = Path(__file__).parents[1] / "alembic/versions/c1e3f5a7b9d2_channel_asset_model_ownership.py"
    spec = importlib.util.spec_from_file_location("ownership_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE instrument_models (id VARCHAR(32) PRIMARY KEY)")
        conn.exec_driver_sql("INSERT INTO instrument_models VALUES ('a'), ('b')")
        conn.exec_driver_sql("CREATE TABLE channel_assets (id VARCHAR PRIMARY KEY)")
        conn.exec_driver_sql("INSERT INTO channel_assets VALUES ('old')")
        conn.exec_driver_sql("CREATE TABLE standard_channel_definitions (id VARCHAR PRIMARY KEY, "
            "instrument_connection_id VARCHAR NOT NULL, standard_name VARCHAR NOT NULL, "
            "CONSTRAINT uq_scd_binding_standard_name UNIQUE(instrument_connection_id, standard_name))")
        conn.exec_driver_sql("INSERT INTO standard_channel_definitions VALUES ('old', 'conn', 'same')")
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(conn)))
        migration.upgrade()
        assert conn.exec_driver_sql("SELECT instrument_model_id FROM channel_assets").scalar() is None
        assert conn.exec_driver_sql("SELECT instrument_model_id FROM standard_channel_definitions").scalar() is None
        conn.exec_driver_sql("INSERT INTO standard_channel_definitions VALUES ('new1','conn','same','a')")
        conn.exec_driver_sql("INSERT INTO standard_channel_definitions VALUES ('new2','conn','same','b')")
        with pytest.raises(sa.exc.IntegrityError):
            conn.exec_driver_sql("INSERT INTO standard_channel_definitions VALUES ('dup','conn','same','a')")
    engine.dispose()


@pytest.mark.skipif(not os.getenv("P2_79_TEST_DATABASE"), reason="requires isolated PostgreSQL database")
def test_postgres_migration_preserves_unknown_rows_and_enforces_model_scope():
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.config import settings
    from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection
    from app.models.standard_channel import StandardChannelDefinition
    database = os.environ["P2_79_TEST_DATABASE"]
    assert database.startswith("p279a_owner_"), "never run against operational DB"
    engine = sa.create_engine(make_url(settings.database_url).set(database=database))
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "c1e3f5a7b9d2"
            assert connection.exec_driver_sql("SELECT count(*) FROM channel_assets WHERE source_type='vendor_file' AND instrument_model_id IS NOT NULL").scalar() == 0
            category = InstrumentCategory(category_key="p279a-migration-test", category_name="隔离迁移测试")
            db.add(category)
            db.flush()
            models = [InstrumentModel(category_id=category.id, vendor="test", model=name, capabilities={}) for name in ("A", "B")]
            db.add_all(models)
            db.flush()
            conn = InstrumentConnection(category_id=category.id, connection_params={})
            db.add(conn)
            db.flush()
            def row(owner):
                return StandardChannelDefinition(instrument_connection_id=conn.id, instrument_model_id=owner,
                    radio_technology="nr5g", channel_kind="nr_arfcn", band="N78", arfcn=640000,
                    bandwidth_mhz=100, model="CDLC", scenario="UMa", mimo="4x4", polarization="DP",
                    version=1, standard_name="same", association_source="declared_only")
            db.add_all([row(models[0].id), row(models[1].id), row(None)])
            db.flush()
            with pytest.raises(sa.exc.IntegrityError):
                with db.begin_nested():
                    db.add(row(models[0].id))
                    db.flush()
        finally:
            db.close()
            transaction.rollback()
    engine.dispose()
