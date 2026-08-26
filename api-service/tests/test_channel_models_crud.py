"""POST / DELETE /instruments/{cat}/channel-models — curated-list CRUD.

Replaces the "hand-edit the JSON in connection_params" workflow with
surgical add / remove that preserves unrelated config keys.

Contract pins:
  - Add: dedupes by filename, preserves other connection_params keys,
    creates an InstrumentConnection record if none exists yet.
  - Delete: matches mixed-shape entries (bare string OR dict),
    404 on missing entry, preserves other keys.
  - Both: idempotent on the "successful" response shape — same as GET,
    so the GUI can use the response to refresh the card without a
    follow-up query.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_category(db, *, with_connection: bool = True, initial_params=None):
    from app.models.instrument import InstrumentCategory, InstrumentConnection
    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="channelEmulator",
        category_name="Channel Emulator (test)",
        display_order=10,
        is_active=True,
    )
    db.add(cat)
    db.flush()
    if with_connection:
        conn = InstrumentConnection(
            id=uuid.uuid4(),
            category_id=cat.id,
            controller_ip="192.168.0.100",
            port=5025,
            protocol="socket",
            connection_params=initial_params or {},
            status="disconnected",
        )
        db.add(conn)
    db.commit()
    return cat


def _nr_model(filename: str, **extra):
    return {
        "filename": filename,
        "radio_technology": "nr5g",
        "channel_kind": "nr_arfcn",
        "band": "N78",
        "nr_arfcn": 640000,
        **extra,
    }


# ---------------------------------------------------------------------------
# POST — add channel model
# ---------------------------------------------------------------------------

class TestAddChannelModel:
    def test_add_to_empty_list_returns_single_entry(self, client, db):
        _seed_category(db, initial_params={})
        r = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("EPA_5Hz.smu"),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["filename"] == "EPA_5Hz.smu"
        assert body["items"][0]["type"] == "smu"
        # No label provided → defaults to filename via normaliser.
        assert body["items"][0]["label"] == "EPA_5Hz.smu"

    def test_add_with_label_and_description(self, client, db):
        _seed_category(db, initial_params={})
        r = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model(
                "EVA_70Hz.smu",
                label="EVA 70 Hz",
                description="3GPP TS 36.521-1 Table B.2.2-1",
            ),
        )
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["label"] == "EVA 70 Hz"
        assert item["description"] == "3GPP TS 36.521-1 Table B.2.2-1"

    def test_add_appends_to_existing(self, client, db):
        _seed_category(
            db,
            initial_params={"available_channel_models": ["EPA_5Hz.smu"]},
        )
        r = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("urban_macro.rtc"),
        )
        assert r.status_code == 200
        filenames = [e["filename"] for e in r.json()["items"]]
        assert filenames == ["EPA_5Hz.smu", "urban_macro.rtc"]

    def test_duplicate_filename_returns_409(self, client, db):
        _seed_category(
            db,
            initial_params={"available_channel_models": ["EPA_5Hz.smu"]},
        )
        r = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("EPA_5Hz.smu"),
        )
        assert r.status_code == 409
        assert "already" in r.json()["detail"].lower()

    def test_duplicate_detection_across_shapes(self, client, db):
        """If the existing entry is a bare string and the new one is a
        dict with the same filename — still a duplicate. Normaliser-
        based comparison catches it."""
        _seed_category(
            db,
            initial_params={"available_channel_models": ["EPA_5Hz.smu"]},
        )
        r = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("EPA_5Hz.smu", label="EPA new label"),
        )
        assert r.status_code == 409

    def test_empty_filename_rejected(self, client, db):
        _seed_category(db, initial_params={})
        r = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("   "),
        )
        assert r.status_code == 422

    def test_unknown_category_404(self, client):
        r = client.post(
            "/api/v1/instruments/no_such_cat/channel-models",
            json=_nr_model("x.smu"),
        )
        assert r.status_code == 404

    def test_preserves_unrelated_connection_params(self, client, db):
        """The whole point of dedicated endpoints — don't blow away
        other config keys when editing channel models."""
        _seed_category(
            db,
            initial_params={
                "port_maps": {"input": 1, "output": 2},
                "alignment_name": "lab-2026-05-13",
                "available_channel_models": ["EPA_5Hz.smu"],
            },
        )
        client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("new.smu"),
        )

        # Read back via DB — the GET endpoint normalises, so we need
        # to look at the raw row to confirm other keys survived.
        from app.models.instrument import InstrumentConnection, InstrumentCategory
        s = TestingSessionLocal()
        try:
            cat = s.query(InstrumentCategory).filter_by(category_key="channelEmulator").one()
            conn = s.query(InstrumentConnection).filter_by(category_id=cat.id).one()
            params = conn.connection_params
            assert params["port_maps"] == {"input": 1, "output": 2}
            assert params["alignment_name"] == "lab-2026-05-13"
            assert len(params["available_channel_models"]) == 2
        finally:
            s.close()

    def test_creates_connection_when_missing(self, client, db):
        """Seed a category without any InstrumentConnection row — the
        add endpoint should create one so the operator isn't blocked."""
        _seed_category(db, with_connection=False)
        r = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("fresh.smu"),
        )
        assert r.status_code == 200, r.text
        assert r.json()["items"][0]["filename"] == "fresh.smu"

    def test_new_manual_entry_requires_explicit_frequency_identity(self, client, db):
        _seed_category(db, initial_params={})
        response = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json={"filename": "untyped.smu"},
        )
        assert response.status_code == 422

    def test_lte_entry_keeps_earfcn_out_of_nr_slot(self, client, db):
        _seed_category(db, initial_params={})
        response = client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json={
                "filename": "lte-b3.smu",
                "radio_technology": "lte",
                "channel_kind": "lte_dl_earfcn",
                "band": "B3",
                "lte_dl_earfcn": 1575,
            },
        )
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["radio_technology"] == "lte"
        assert item["channel_kind"] == "lte_dl_earfcn"
        assert item["lte_dl_earfcn"] == 1575
        assert item["nr_arfcn"] is None
        assert item["center_frequency_mhz"] == pytest.approx(1842.5)


# ---------------------------------------------------------------------------
# DELETE — remove channel model
# ---------------------------------------------------------------------------

class TestRemoveChannelModel:
    def test_remove_existing_returns_remaining_items(self, client, db):
        _seed_category(
            db,
            initial_params={
                "available_channel_models": [
                    "EPA_5Hz.smu",
                    {"filename": "EVA_70Hz.smu", "label": "EVA"},
                    "urban_macro.rtc",
                ],
            },
        )
        r = client.delete("/api/v1/instruments/channelEmulator/channel-models/EVA_70Hz.smu")
        assert r.status_code == 200, r.text
        filenames = [e["filename"] for e in r.json()["items"]]
        assert filenames == ["EPA_5Hz.smu", "urban_macro.rtc"]

    def test_remove_bare_string_entry(self, client, db):
        _seed_category(
            db,
            initial_params={
                "available_channel_models": ["EPA_5Hz.smu", "urban_macro.rtc"],
            },
        )
        r = client.delete("/api/v1/instruments/channelEmulator/channel-models/EPA_5Hz.smu")
        assert r.status_code == 200
        assert [e["filename"] for e in r.json()["items"]] == ["urban_macro.rtc"]

    def test_remove_nonexistent_returns_404(self, client, db):
        _seed_category(
            db,
            initial_params={"available_channel_models": ["EPA_5Hz.smu"]},
        )
        r = client.delete("/api/v1/instruments/channelEmulator/channel-models/no_such.smu")
        assert r.status_code == 404

    def test_remove_when_list_empty_returns_404(self, client, db):
        _seed_category(db, initial_params={})
        r = client.delete("/api/v1/instruments/channelEmulator/channel-models/x.smu")
        assert r.status_code == 404

    def test_remove_when_no_connection_returns_404(self, client, db):
        _seed_category(db, with_connection=False)
        r = client.delete("/api/v1/instruments/channelEmulator/channel-models/x.smu")
        assert r.status_code == 404

    def test_remove_preserves_unrelated_params(self, client, db):
        _seed_category(
            db,
            initial_params={
                "port_maps": {"input": 1},
                "available_channel_models": ["delete_me.smu", "keep_me.smu"],
            },
        )
        client.delete("/api/v1/instruments/channelEmulator/channel-models/delete_me.smu")

        from app.models.instrument import InstrumentConnection, InstrumentCategory
        s = TestingSessionLocal()
        try:
            cat = s.query(InstrumentCategory).filter_by(category_key="channelEmulator").one()
            conn = s.query(InstrumentConnection).filter_by(category_id=cat.id).one()
            params = conn.connection_params
            assert params["port_maps"] == {"input": 1}
            assert len(params["available_channel_models"]) == 1
        finally:
            s.close()

    def test_remove_unknown_category_returns_404(self, client):
        r = client.delete("/api/v1/instruments/no_such_cat/channel-models/x.smu")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Round-trip — POST then DELETE then GET shows clean state
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_add_then_remove_then_get_is_empty(self, client, db):
        _seed_category(db, initial_params={})
        client.post(
            "/api/v1/instruments/channelEmulator/channel-models",
            json=_nr_model("x.smu"),
        )
        client.delete("/api/v1/instruments/channelEmulator/channel-models/x.smu")
        # Patch HAL out of the way so GET hits the DB-fallback branch.
        # (TestClient runs without a real HAL service, so the get_hal_service
        # call inside the endpoint either errors or returns None — both
        # land in the DB-fallback path either way.)
        r = client.get("/api/v1/instruments/channelEmulator/channel-models")
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["reason"] == "driver_not_loaded"
