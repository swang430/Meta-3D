"""GET /instruments/{cat}/channel-models — DB fallback (Codex P2 on #13).

Stage 1 source of truth for the F64 channel-model list is the operator-
curated ``InstrumentConnection.connection_params['available_channel_models']``
in the DB, not a live SCPI/FTP query (F64 ATE Server has no MMEM, and
the CAICT chamber unit's FTP is closed — see memory
`project_f64_ate_server_capabilities`).

Pre-fix: the endpoint short-circuited to ``driver_not_loaded`` whenever
HAL hadn't bound a driver — so the operator couldn't see the curated
list during offline planning, HAL-mock mode, or before the F64 was
reachable. The fix reads the same DB list and runs it through the same
normaliser the driver uses, returning items even with no live driver.

These tests pin both sides of the contract:
  - shared normaliser in ``channel_emulator`` produces the API shape
  - endpoint surfaces DB items when driver is None
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.channel_emulator import normalize_channel_model_entries
from app.main import app


# ---------------------------------------------------------------------------
# Normaliser unit tests — single source of truth, must match the F64 driver
# ---------------------------------------------------------------------------

class TestNormaliseEntries:
    def test_empty_input_returns_empty(self):
        assert normalize_channel_model_entries([]) == []
        assert normalize_channel_model_entries(None) == []

    def test_bare_string_becomes_dict(self):
        out = normalize_channel_model_entries(["urban_macro.smu"])
        assert out == [{
            "filename": "urban_macro.smu",
            "label": "urban_macro.smu",
            "description": None,
            "type": "smu",
        }]

    def test_dict_entry_with_label_and_description_preserved(self):
        out = normalize_channel_model_entries([
            {"filename": "ramp.rtc", "label": "Ramp test", "description": "3GPP TR 38.901"},
        ])
        assert out == [{
            "filename": "ramp.rtc",
            "label": "Ramp test",
            "description": "3GPP TR 38.901",
            "type": "rtc",
        }]

    def test_dropped_when_filename_missing(self):
        out = normalize_channel_model_entries([
            {"label": "no filename"},  # silently dropped
            {"filename": "ok.smu"},
        ])
        assert [e["filename"] for e in out] == ["ok.smu"]

    def test_dropped_when_filename_not_string(self):
        out = normalize_channel_model_entries([
            {"filename": 42},                     # bad type — drop
            {"filename": ""},                     # empty — drop
            {"filename": "valid.smu"},
        ])
        assert [e["filename"] for e in out] == ["valid.smu"]

    def test_non_dict_non_string_entries_dropped(self):
        out = normalize_channel_model_entries([
            "good.smu",
            42,
            ["nested", "list"],
            {"filename": "also_good.rtc"},
        ])
        filenames = [e["filename"] for e in out]
        assert filenames == ["good.smu", "also_good.rtc"]

    def test_type_inferred_from_extension(self):
        out = normalize_channel_model_entries([
            "a.smu", "b.rtc", "c.asc", "d.txt", "noext",
        ])
        types = {e["filename"]: e["type"] for e in out}
        assert types == {
            "a.smu": "smu",
            "b.rtc": "rtc",
            "c.asc": "asc",
            "d.txt": "txt",
            "noext": "unknown",
        }


# ---------------------------------------------------------------------------
# Endpoint integration — DB fallback when no driver is bound
# ---------------------------------------------------------------------------

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


@pytest.fixture
def channel_emulator_category(db):
    """Seed a channelEmulator category + connection with a curated list
    in connection_params, mirroring how an operator configures the F64
    before the instrument is reachable."""
    from app.models.instrument import (
        InstrumentCategory,
        InstrumentConnection,
    )
    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="channelEmulator",
        category_name="Channel Emulator (test)",
        display_order=10,
        is_active=True,
    )
    db.add(cat)
    db.flush()

    conn = InstrumentConnection(
        id=uuid.uuid4(),
        category_id=cat.id,
        controller_ip="192.168.0.100",
        port=5025,
        protocol="socket",
        connection_params={
            "available_channel_models": [
                "EPA_5Hz.smu",
                {
                    "filename": "EVA_70Hz.smu",
                    "label": "EVA 70 Hz (high-speed train)",
                    "description": "3GPP TS 36.521-1 Table B.2.2-1",
                },
                {"filename": "urban_macro.rtc"},
            ],
        },
        status="disconnected",
    )
    db.add(conn)
    db.commit()
    return cat


@pytest.fixture
def hal_with_no_drivers(monkeypatch):
    """Force the endpoint into the no-driver branch — what the operator
    sees when HAL hasn't loaded yet OR the F64 connect() failed."""
    class _EmptyHal:
        drivers: Dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service",
        lambda: _EmptyHal(),
    )


class TestEndpointFallsBackToDb:
    def test_curated_list_visible_without_live_driver(
        self, client, channel_emulator_category, hal_with_no_drivers
    ):
        r = client.get("/api/v1/instruments/channelEmulator/channel-models")
        assert r.status_code == 200, r.text
        body = r.json()
        # DB had three entries — all surfaced via normaliser.
        assert len(body["items"]) == 3
        filenames = [e["filename"] for e in body["items"]]
        assert filenames == ["EPA_5Hz.smu", "EVA_70Hz.smu", "urban_macro.rtc"]
        # And since we found items, reason is cleared — GUI shouldn't
        # still show "drivers not loaded" warning when there's a list.
        assert body["reason"] is None

    def test_label_and_description_preserved_through_endpoint(
        self, client, channel_emulator_category, hal_with_no_drivers
    ):
        r = client.get("/api/v1/instruments/channelEmulator/channel-models")
        body = r.json()
        eva = next(e for e in body["items"] if e["filename"] == "EVA_70Hz.smu")
        assert eva["label"] == "EVA 70 Hz (high-speed train)"
        assert eva["description"] == "3GPP TS 36.521-1 Table B.2.2-1"
        assert eva["type"] == "smu"

    def test_bare_string_normalises_to_full_entry(
        self, client, channel_emulator_category, hal_with_no_drivers
    ):
        r = client.get("/api/v1/instruments/channelEmulator/channel-models")
        body = r.json()
        epa = next(e for e in body["items"] if e["filename"] == "EPA_5Hz.smu")
        # No label provided in DB — label defaults to filename.
        assert epa["label"] == "EPA_5Hz.smu"
        assert epa["description"] is None
        assert epa["type"] == "smu"


class TestReasonStillFlagsEmptyDb:
    def test_empty_connection_params_reports_driver_not_loaded(
        self, client, db, hal_with_no_drivers
    ):
        """No driver AND no curated list — the GUI still gets the
        ``driver_not_loaded`` reason so it can suggest the right next
        step (configure available_channel_models in instrument resources
        or bring HAL up)."""
        from app.models.instrument import InstrumentCategory, InstrumentConnection
        cat = InstrumentCategory(
            id=uuid.uuid4(),
            category_key="channelEmulator",
            category_name="Empty CE",
            display_order=11,
            is_active=True,
        )
        conn = InstrumentConnection(
            id=uuid.uuid4(),
            category_id=cat.id,
            controller_ip="192.168.0.100",
            port=5025,
            protocol="socket",
            connection_params={},  # ← empty: no available_channel_models key
            status="disconnected",
        )
        db.add_all([cat, conn])
        db.commit()

        r = client.get("/api/v1/instruments/channelEmulator/channel-models")
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["reason"] == "driver_not_loaded"
