"""FS16 playback diagnostic sequence tests."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.diagnostics import loader
from app.hal.channel_emulator import ChannelLoadMode
from app.main import app
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.diagnostic_run import DiagnosticRun
from app.models.instrument import InstrumentCategory
from app.models.lab_profile import LabProfile


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
        Base.metadata.drop_all(bind=engine)
        loader.reset_cache()


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def lab_with_ce(db):
    chamber = create_chamber_from_preset(
        ChamberType.TYPE_C.value,
        name="FS16 Playback Chamber",
    )
    ce_cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="channelEmulator",
        category_name="Channel Emulator",
        is_active=True,
    )
    db.add_all([chamber, ce_cat])
    db.commit()
    lab = LabProfile(
        name="FS16-Playback-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(ce_cat.id),
                "connection_endpoint": "TCPIP0::192.168.0.100::hislip0::INSTR",
                "driver_mode": "real",
                "role": "primary_channel_emulator",
            },
        ],
        is_active=True,
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def _patched_hal(monkeypatch, drivers: dict):
    fake_hal = MagicMock()
    fake_hal.drivers = drivers
    monkeypatch.setattr(
        "app.api.diagnostic_sequence.get_hal_service",
        lambda: fake_hal,
    )
    return fake_hal


class FakeFs16PlaybackDriver:
    def __init__(self) -> None:
        self.verify_remote_file_exists = False
        self.auto_start_after_load = True
        self.connect = AsyncMock(return_value=True)
        self.load_channel = AsyncMock(return_value=True)
        self.start_emulation = AsyncMock(return_value=True)
        self.stop_emulation = AsyncMock(return_value=True)


class TestFs16PlaybackSequenceMetadata:
    def test_loader_discovers_fs16_playback_sequence(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        entry = next(s for s in resp.json() if s["key"] == "fs16_playback_smoke")
        assert entry["required_categories"] == ["channelEmulator"]
        assert entry["safe_during_test"] is False
        assert any(p["name"] == "remote_playback_file" for p in entry["params_schema"])


class TestFs16PlaybackSequenceRun:
    def test_loads_and_starts_remote_smu(self, db, lab_with_ce, monkeypatch):
        ce = FakeFs16PlaybackDriver()
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_playback_smoke/run",
            json={
                "lab_profile_id": str(lab_with_ce.id),
                "run_by": "pytest",
                "params": {
                    "remote_playback_file": "Emulation0609.smu",
                    "verify_remote_file_exists": True,
                    "start_playback": True,
                    "cleanup_on_finish": False,
                },
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["extra"]["playback_left_running"] is True
        assert body["extra"]["remote_playback_file"] == "Emulation0609.smu"
        ce.connect.assert_awaited_once()
        ce.load_channel.assert_awaited_once()
        _, kwargs = ce.load_channel.await_args
        assert kwargs["mode"] == ChannelLoadMode.EXTERNAL_WAVEFORM
        assert kwargs["parameters"] == {"remote_playback_file": "Emulation0609.smu"}
        ce.start_emulation.assert_awaited_once()
        ce.stop_emulation.assert_not_called()

        audit = (
            db.query(DiagnosticRun)
            .filter(DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"]))
            .first()
        )
        assert audit is not None
        assert audit.success is True
        assert audit.target_name == "fs16_playback_smoke"

    def test_missing_ce_driver_fails_cleanly(self, lab_with_ce, monkeypatch):
        _patched_hal(monkeypatch, {})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_playback_smoke/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "channelEmulator" in body["summary"]
        assert "未加载" in body["summary"]

    def test_load_failure_surfaces_driver_last_error(self, lab_with_ce, monkeypatch):
        ce = FakeFs16PlaybackDriver()
        ce._last_error = "remote playback file not found on FS16: D:\\User Playbacks\\Emulation0609.smu"
        ce.load_channel = AsyncMock(return_value=False)
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_playback_smoke/run",
            json={
                "lab_profile_id": str(lab_with_ce.id),
                "params": {"remote_playback_file": "Emulation0609.smu"},
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "remote playback file not found" in body["summary"]
        assert "remote playback file not found" in body["steps"][1]["detail"]
