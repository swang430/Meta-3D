"""P2-79B：只在指定隔离 PostgreSQL 上验证真实锁/identity-map 行为。"""
from copy import deepcopy
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.services.channel_emulator_model_preset import save_channel_emulator_model_preset

pytestmark = pytest.mark.skipif(
    not os.getenv("P2_79_TEST_DATABASE"), reason="requires isolated PostgreSQL database")


@pytest.fixture
def pg_owner():
    database = os.environ["P2_79_TEST_DATABASE"]
    assert database.startswith("p279a_owner_"), "never run against operational DB"
    engine = sa.create_engine(make_url(settings.database_url).set(database=database))
    db = Session(engine, autoflush=False)
    category = db.query(InstrumentCategory).filter_by(category_key="channelEmulator").one()
    connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one()
    old_selected = category.selected_model_id
    fields = ("endpoint", "controller_ip", "port", "protocol", "notes",
              "connection_params", "channel_emulator_model_presets")
    original = {name: deepcopy(getattr(connection, name)) for name in fields}
    models = [InstrumentModel(id=uuid4(), category_id=category.id, vendor="test",
                              model=f"p279-{uuid4()}", capabilities={}) for _ in range(2)]
    db.add_all(models)
    db.flush()
    category.selected_model_id = models[0].id
    connection.channel_emulator_model_presets = {}
    save_channel_emulator_model_preset(
        category=category, current_model=models[0], target_model=models[0], connection=connection,
        endpoint="test:3334", controller="", notes="", parsed_controller_ip=None, parsed_port=None,
        connection_params={"available_channel_models": [{"filename": "common.smu"}], "keep": "A"})
    db.commit()
    ids = category.id, connection.id, models[0].id, models[1].id
    db.close()
    try:
        yield engine, ids
    finally:
        with Session(engine) as restore:
            from app.models.standard_channel import StandardChannelDefinition
            from app.models.channel_asset import ChannelAsset
            restore.query(StandardChannelDefinition).filter(
                StandardChannelDefinition.instrument_model_id.in_(ids[2:])).delete(synchronize_session=False)
            restore.query(ChannelAsset).filter(
                ChannelAsset.name.like(f"p279-{ids[2]}-%")).delete(synchronize_session=False)
            c = restore.get(InstrumentCategory, ids[0])
            conn = restore.get(InstrumentConnection, ids[1])
            c.selected_model_id = old_selected
            for name, value in original.items():
                setattr(conn, name, value)
            restore.flush()
            restore.query(InstrumentModel).filter(InstrumentModel.id.in_(ids[2:])).delete(synchronize_session=False)
            restore.commit()
        engine.dispose()


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_real_model_list_writer_waits_then_keeps_latest_preset_map(pg_owner, operation):
    from app.api.instrument import add_channel_model_entry, remove_channel_model_entry, AddChannelModelRequest

    engine, (category_id, connection_id, a_id, b_id) = pg_owner
    preloaded, sql_attempt = Event(), Event()

    def observe(_conn, _cursor, statement, _params, _context, _many):
        if current_thread().name.startswith("p279-writer") and (
                "FOR UPDATE" in statement.upper() or "UPDATE INSTRUMENT_CONNECTIONS" in statement.upper()):
            sql_attempt.set()

    sa.event.listen(engine, "before_cursor_execute", observe)
    holder = Session(engine, autoflush=False)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="p279-writer")
    try:
        cat = holder.query(InstrumentCategory).filter_by(id=category_id).with_for_update().one()
        conn = holder.query(InstrumentConnection).filter_by(id=connection_id).with_for_update().one()

        def writer():
            with Session(engine, autoflush=False) as db:
                db.execute(sa.text("SET LOCAL lock_timeout = '3s'"))
                old_cat = db.get(InstrumentCategory, category_id)
                old_conn = db.get(InstrumentConnection, connection_id)
                assert old_cat.selected_model_id == a_id
                assert old_conn.connection_params["keep"] == "A"
                preloaded.set()
                if operation == "add":
                    return add_channel_model_entry("channelEmulator", AddChannelModelRequest(
                        filename="added.smu", radio_technology="nr5g", channel_kind="nr_arfcn",
                        band="N78", nr_arfcn=640000), db)
                return remove_channel_model_entry("channelEmulator", "common.smu", db)

        future = pool.submit(writer)
        assert preloaded.wait(2)
        a, b = holder.get(InstrumentModel, a_id), holder.get(InstrumentModel, b_id)
        save_channel_emulator_model_preset(
            category=cat, current_model=a, target_model=b, connection=conn, endpoint="test:3334",
            controller="", notes="", parsed_controller_ip=None, parsed_port=None,
            connection_params={"available_channel_models": [
                {"filename": "common.smu"}, {"filename": "B.smu"}], "keep": "B"})
        holder.flush()
        assert sql_attempt.wait(2)
        assert not future.done(), "writer must wait for the held transaction"
        holder.commit()
        future.result(timeout=5)
        with Session(engine) as verify:
            saved_cat = verify.get(InstrumentCategory, category_id)
            saved = verify.get(InstrumentConnection, connection_id)
            assert saved_cat.selected_model_id == b_id
            assert set(saved.channel_emulator_model_presets) == {str(a_id), str(b_id)}
            assert saved.connection_params["keep"] == "B"
            filenames = [row["filename"] for row in saved.connection_params["available_channel_models"]]
            assert filenames == (["common.smu", "B.smu", "added.smu"] if operation == "add" else ["B.smu"])
            assert saved.channel_emulator_model_presets[str(b_id)]["connection_params"] == saved.connection_params
    finally:
        holder.rollback()
        holder.close()
        pool.shutdown(wait=True)
        sa.event.remove(engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("operation", ["associate", "delete"])
def test_scd_writer_reloads_owner_before_updating_projection(pg_owner, operation):
    from app.models.standard_channel import StandardChannelDefinition
    from app.services.standard_channel_service import create_scd, associate_file, delete_scd

    engine, (category_id, connection_id, a_id, b_id) = pg_owner
    with Session(engine, autoflush=False) as stale:
        row = create_scd(stale, instrument_connection_id=connection_id, instrument_model_id=a_id,
            radio_technology="nr5g", channel_kind="nr_arfcn", band="N78", arfcn=640000,
            lte_dl_earfcn=None, bandwidth_mhz=100, model="CDLC", scenario="UMa",
            mimo="2x2", polarization="DP")
        row.associated_file_path = "old.smu"
        stale.commit()
        stale.get(StandardChannelDefinition, row.id)
        stale.get(InstrumentCategory, category_id)
        stale.get(InstrumentConnection, connection_id)
        with Session(engine, autoflush=False) as other:
            actual = other.get(StandardChannelDefinition, row.id)
            actual.instrument_model_id = b_id
            cat, conn = other.get(InstrumentCategory, category_id), other.get(InstrumentConnection, connection_id)
            save_channel_emulator_model_preset(
                category=cat, current_model=other.get(InstrumentModel, a_id),
                target_model=other.get(InstrumentModel, b_id), connection=conn, endpoint="test:3334",
                controller="", notes="", parsed_controller_ip=None, parsed_port=None,
                connection_params={"available_channel_models": [
                    {"filename": "old.smu", "scd_id": str(row.id), "instrument_model_id": str(b_id)}],
                    "keep": "B"})
            other.commit()
        if operation == "associate":
            updated = associate_file(stale, row.id, file_path="new.smu")
            assert updated.instrument_model_id == b_id
        else:
            delete_scd(stale, row.id)
        with Session(engine) as verify:
            conn = verify.get(InstrumentConnection, connection_id)
            assert conn.connection_params["keep"] == "B"
            projected = conn.connection_params["available_channel_models"]
            assert [entry["filename"] for entry in projected] == (["new.smu"] if operation == "associate" else [])
            assert conn.channel_emulator_model_presets[str(b_id)]["connection_params"] == conn.connection_params


@pytest.mark.parametrize("drift", ["selected_model", "source_owner"])
def test_confirmation_rechecks_saved_model_and_source_after_old_cache(pg_owner, drift):
    from app.models.channel_asset import ChannelAsset
    from app.services.channel_asset_service import confirm_channel_asset_ownership, ChannelAssetError

    engine, (category_id, connection_id, a_id, b_id) = pg_owner
    with Session(engine, autoflush=False) as stale:
        asset = ChannelAsset(name=f"p279-{a_id}-{uuid4()}", source_type="vendor_file",
            payload={}, allowed_targets=["gcm_native"], is_active=True)
        stale.add(asset)
        stale.commit()
        old_asset = stale.get(ChannelAsset, asset.id)
        old_category = stale.get(InstrumentCategory, category_id)
        old_connection = stale.get(InstrumentConnection, connection_id)
        assert old_category.selected_model_id == a_id
        with Session(engine) as other:
            if drift == "selected_model":
                other.get(InstrumentCategory, category_id).selected_model_id = b_id
            else:
                actual = other.get(ChannelAsset, old_asset.id)
                actual.instrument_connection_id = connection_id
                actual.instrument_model_id = b_id
            other.commit()
        with pytest.raises(ChannelAssetError):
            confirm_channel_asset_ownership(stale, [old_asset.id], old_connection.id, a_id)
        stale.rollback()
        with Session(engine) as verify:
            actual = verify.get(ChannelAsset, old_asset.id)
            assert actual.instrument_model_id == (None if drift == "selected_model" else b_id)


def test_derived_source_lookup_does_not_reuse_old_owner_identity_map(pg_owner):
    from app.models.channel_asset import ChannelAsset
    from app.services.channel_asset_ownership import owned_channel_model_params

    engine, (_category_id, connection_id, a_id, b_id) = pg_owner
    with Session(engine) as stale:
        asset = ChannelAsset(name=f"p279-{a_id}-{uuid4()}", source_type="vendor_file",
            payload={}, allowed_targets=["gcm_native"], is_active=True,
            instrument_connection_id=connection_id, instrument_model_id=a_id,
            associated_file_path="asset.smu")
        stale.add(asset)
        stale.commit()
        old_asset = stale.get(ChannelAsset, asset.id)
        assert old_asset.instrument_model_id == a_id
        with Session(engine) as other:
            other.get(ChannelAsset, old_asset.id).instrument_model_id = b_id
            other.commit()
        params = owned_channel_model_params(stale, connection_id, a_id, {
            "available_channel_models": [{"filename": "asset.smu", "channel_asset_id": str(old_asset.id)}]})
        assert params["available_channel_models"] == []


def test_real_put_reloads_other_saved_model_before_writing(pg_owner):
    from app.api.instrument import update_instrument_category, UpdateInstrumentCategoryRequest

    engine, (category_id, connection_id, a_id, b_id) = pg_owner
    with Session(engine, autoflush=False) as stale:
        old_cat = stale.get(InstrumentCategory, category_id)
        old_conn = stale.get(InstrumentConnection, connection_id)
        assert old_cat.selected_model_id == a_id
        with Session(engine, autoflush=False) as other:
            cat, conn = other.get(InstrumentCategory, category_id), other.get(InstrumentConnection, connection_id)
            save_channel_emulator_model_preset(
                category=cat, current_model=other.get(InstrumentModel, a_id),
                target_model=other.get(InstrumentModel, b_id), connection=conn,
                endpoint="test:3334", controller="", notes="", parsed_controller_ip=None, parsed_port=None,
                connection_params={"keep": "B"})
            other.commit()
        update_instrument_category("channelEmulator", UpdateInstrumentCategoryRequest(
            modelId=str(a_id), connection={"endpoint": "test:3334", "connection_params": {"keep": "A-new"}}), stale)
        with Session(engine) as verify:
            saved = verify.get(InstrumentConnection, old_conn.id)
            assert set(saved.channel_emulator_model_presets) == {str(a_id), str(b_id)}
            assert saved.channel_emulator_model_presets[str(b_id)]["connection_params"]["keep"] == "B"
            assert saved.connection_params["keep"] == "A-new"


def test_scan_takes_category_before_namespace_and_connection_locks(pg_owner):
    from app.services.smu_project_inventory import _lock_sync_truth_rows

    engine, (category_id, connection_id, _a_id, _b_id) = pg_owner
    attempted, finished = Event(), Event()
    statements = []
    def observe(_conn, _cursor, statement, _params, _context, _many):
        if current_thread().name.startswith("p279-scan") and (
                "FOR UPDATE" in statement.upper() or statement.upper().startswith("LOCK TABLE")):
            statements.append(statement.upper())
            attempted.set()
    sa.event.listen(engine, "before_cursor_execute", observe)
    holder = Session(engine)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="p279-scan")
    try:
        holder.query(InstrumentCategory).filter_by(id=category_id).with_for_update().one()
        def scan():
            with Session(engine, autoflush=False) as db:
                db.execute(sa.text("SET LOCAL lock_timeout = '3s'"))
                _lock_sync_truth_rows(db, connection_id)
                db.rollback()
            finished.set()
        future = pool.submit(scan)
        assert attempted.wait(2)
        assert not finished.wait(0.2), "scan must wait for category before taking downstream locks"
        holder.commit()
        future.result(timeout=5)
        assert "INSTRUMENT_CATEGORIES" in statements[0]
        assert any(statement.startswith("LOCK TABLE") for statement in statements[1:])
    finally:
        holder.rollback()
        holder.close()
        pool.shutdown(wait=True)
        sa.event.remove(engine, "before_cursor_execute", observe)
