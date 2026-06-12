"""Conducted BS -> CE -> DUT diagnostic sequence tests."""
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
from app.hal.base_station import MockBaseStation, ThroughputMetrics
from app.hal.channel_emulator import MockChannelEmulator
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
def chamber(db):
    c = create_chamber_from_preset(
        ChamberType.TYPE_C.value,
        name="Conducted Smoke Chamber",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab_with_bs_ce(db, chamber):
    bs_cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="baseStation",
        category_name="Base Station",
        is_active=True,
    )
    ce_cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="channelEmulator",
        category_name="Channel Emulator",
        is_active=True,
    )
    db.add_all([bs_cat, ce_cat])
    db.commit()
    lab = LabProfile(
        name="Conducted-Smoke-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(bs_cat.id),
                "connection_endpoint": "TCPIP0::192.168.0.10::hislip0::INSTR",
                "driver_mode": "real",
                "role": "primary_base_station",
            },
            {
                "category_id": str(ce_cat.id),
                "connection_endpoint": "TCPIP0::192.168.0.11::5025::SOCKET",
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


def _fast_bs(*, attach: bool = True):
    bs = MagicMock()
    bs.connect = AsyncMock(return_value=True)
    bs.set_cell_config = AsyncMock(return_value=True)
    bs.set_downlink_power = AsyncMock(return_value=True)
    bs.start_signaling = AsyncMock(return_value=True)
    bs.stop_signaling = AsyncMock(return_value=True)
    bs.get_ue_info = AsyncMock(return_value={"connected": attach, "imsi": "001010..."})
    bs.query_ue_capability = AsyncMock(return_value={"max_dl_layers": 4, "source": "fake"})
    bs.measure_throughput_window = AsyncMock(
        return_value=ThroughputMetrics(
            dl_throughput_mbps=123.0,
            ul_throughput_mbps=45.0,
            dl_bler=0.01,
            ul_bler=0.02,
            cqi=14,
            rank_indicator=2,
        )
    )
    return bs


def _fast_ce(*, passthrough_ok: bool = True):
    ce = MagicMock()
    ce.connect = AsyncMock(return_value=True)
    ce.set_passthrough_mode = AsyncMock(return_value=passthrough_ok)
    ce.clear_passthrough_mode = AsyncMock(return_value=True)
    return ce


class TestConductedSequenceMetadata:
    def test_loader_discovers_conducted_smoke_sequence(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        entry = next(
            s for s in resp.json() if s["key"] == "conducted_bs_ce_dut_smoke"
        )
        assert entry["required_categories"] == ["baseStation", "channelEmulator"]
        assert entry["safe_during_test"] is False
        assert any(p["name"] == "ce_input_port" for p in entry["params_schema"])
        assert any(p["name"] == "throughput_windows" for p in entry["params_schema"])


class TestConductedSequenceRun:
    def test_mock_bs_ce_full_success(self, db, lab_with_bs_ce, monkeypatch):
        bs = MockBaseStation("mock-bs", {"model": "Mock"})
        ce = MockChannelEmulator("mock-ce", {"model": "Mock"})
        _patched_hal(monkeypatch, {"baseStation": bs, "channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/conducted_bs_ce_dut_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "run_by": "pytest",
                "params": {
                    "attach_timeout_s": 0.2,
                    "attach_poll_interval_s": 0.01,
                    "throughput_windows": 2,
                    "throughput_window_s": 0.01,
                },
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert "passed" in body["summary"]
        assert body["extra"]["ue_info"]["connected"] is True
        assert len(body["extra"]["samples"]) == 2
        assert "dl_throughput_mbps" in body["extra"]["kpi_summary"]
        labels = [s["label"] for s in body["steps"]]
        assert any(label.startswith("CE passthrough") for label in labels)
        assert any(label.startswith("throughput window") for label in labels)

        audit = (
            db.query(DiagnosticRun)
            .filter(DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"]))
            .first()
        )
        assert audit is not None
        assert audit.success is True
        assert audit.run_by == "pytest"
        assert audit.target_name == "conducted_bs_ce_dut_smoke"

    def test_missing_bs_driver_fails_cleanly(self, lab_with_bs_ce, monkeypatch):
        _patched_hal(monkeypatch, {"channelEmulator": _fast_ce()})
        resp = client.post(
            "/api/v1/diagnostic-sequences/conducted_bs_ce_dut_smoke/run",
            json={"lab_profile_id": str(lab_with_bs_ce.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "baseStation" in body["summary"]
        assert "未加载" in body["summary"]

    def test_missing_ce_driver_fails_cleanly(self, lab_with_bs_ce, monkeypatch):
        _patched_hal(monkeypatch, {"baseStation": _fast_bs()})
        resp = client.post(
            "/api/v1/diagnostic-sequences/conducted_bs_ce_dut_smoke/run",
            json={"lab_profile_id": str(lab_with_bs_ce.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "channelEmulator" in body["summary"]
        assert "未加载" in body["summary"]

    def test_attach_timeout_still_cleans_up(self, lab_with_bs_ce, monkeypatch):
        bs = _fast_bs(attach=False)
        ce = _fast_ce()
        _patched_hal(monkeypatch, {"baseStation": bs, "channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/conducted_bs_ce_dut_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "params": {
                    "attach_timeout_s": 0.01,
                    "attach_poll_interval_s": 0.005,
                    "throughput_windows": 1,
                    "throughput_window_s": 0.01,
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "did not attach" in body["summary"]
        assert body["extra"]["cleanup_warnings"] == []
        bs.stop_signaling.assert_awaited_once()
        ce.clear_passthrough_mode.assert_awaited_once()
        bs.measure_throughput_window.assert_not_called()

    def test_ce_passthrough_failure_does_not_start_bs(self, lab_with_bs_ce, monkeypatch):
        bs = _fast_bs()
        ce = _fast_ce(passthrough_ok=False)
        _patched_hal(monkeypatch, {"baseStation": bs, "channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/conducted_bs_ce_dut_smoke/run",
            json={"lab_profile_id": str(lab_with_bs_ce.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "driver returned False" in body["summary"]
        bs.start_signaling.assert_not_called()
        bs.stop_signaling.assert_not_called()
        ce.clear_passthrough_mode.assert_not_called()
