"""FS16 hybrid KPI diagnostic sequence tests."""
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
def lab_with_bs_ce(db):
    chamber = create_chamber_from_preset(
        ChamberType.TYPE_C.value,
        name="FS16 Hybrid KPI Chamber",
    )
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
    db.add_all([chamber, bs_cat, ce_cat])
    db.commit()
    lab = LabProfile(
        name="FS16-Hybrid-KPI-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(bs_cat.id),
                "connection_endpoint": "mock://base-station",
                "driver_mode": "mock",
                "role": "primary_base_station",
            },
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
        self.remote_file_visible = True

    def remote_playback_path(self, path_or_name: str) -> str:
        text = str(path_or_name).strip().strip('"').strip("'")
        if ":\\" in text:
            return text
        return f"D:\\User Playbacks\\{text}"

    async def remote_playback_file_exists(self, path_or_name: str) -> bool:
        return self.remote_file_visible


class MockFastBaseStation:
    def __init__(self) -> None:
        self.connect = AsyncMock(return_value=True)
        self.set_cell_config = AsyncMock(return_value=True)
        self.set_downlink_power = AsyncMock(return_value=True)
        self.start_signaling = AsyncMock(return_value=True)
        self.stop_signaling = AsyncMock(return_value=True)
        self.get_ue_info = AsyncMock(
            return_value={"connected": True, "imsi": "001010000000001"}
        )
        self.query_ue_capability = AsyncMock(
            return_value={"max_dl_layers": 4, "source": "mock"}
        )
        self.measure_throughput_window = AsyncMock(
            return_value=ThroughputMetrics(
                dl_throughput_mbps=123.0,
                ul_throughput_mbps=45.0,
                dl_bler=0.01,
                ul_bler=0.02,
                cqi=14,
                rank_indicator=2,
                mcs_dl=26,
                mcs_ul=22,
                rsrp_dbm=-78.0,
                sinr_db=18.0,
            )
        )


class FakeRealBaseStation(MockFastBaseStation):
    pass


class TestFs16HybridKpiSequenceMetadata:
    def test_loader_discovers_hybrid_sequence(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        entry = next(s for s in resp.json() if s["key"] == "fs16_hybrid_kpi_smoke")
        assert entry["required_categories"] == ["channelEmulator", "baseStation"]
        assert entry["safe_during_test"] is False
        assert any(p["name"] == "remote_playback_file" for p in entry["params_schema"])
        bs_mode = next(p for p in entry["params_schema"] if p["name"] == "base_station_mode")
        assert bs_mode["options"] == ["mock", "real"]


class TestFs16HybridKpiSequenceRun:
    def test_real_fs16_with_mock_bs_returns_kpi_summary(
        self,
        db,
        lab_with_bs_ce,
        monkeypatch,
    ):
        ce = FakeFs16PlaybackDriver()
        bs = MockFastBaseStation()
        _patched_hal(monkeypatch, {"channelEmulator": ce, "baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_hybrid_kpi_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "run_by": "pytest",
                "params": {
                    "remote_playback_file": "Emulation0609.smu",
                    "base_station_mode": "mock",
                    "frequency_mhz": 3600,
                    "mimo_layers": 2,
                    "throughput_windows": 2,
                    "throughput_window_s": 0.01,
                    "stop_after_s": 0,
                    "cleanup_on_finish": True,
                },
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert "avg DL 123.00 Mbps" in body["summary"]
        assert body["extra"]["instrument_modes"]["channelEmulator"] == "real"
        assert body["extra"]["instrument_modes"]["baseStation"] == "mock"
        assert body["extra"]["instrument_modes"]["DUT"] == "mock"
        assert body["extra"]["fs16_playback"]["playback_left_running"] is False
        assert body["extra"]["fs16_playback"]["bs_signaling_left_running"] is False
        assert body["extra"]["kpi_summary"]["dl_throughput_mbps"]["mean"] == 123.0
        assert body["extra"]["kpi_summary"]["sinr_db"]["mean"] == 18.0
        assert len(body["extra"]["samples"]) == 2
        labels = [step["label"] for step in body["steps"]]
        assert "BS stop_signaling" in labels
        assert "FS16 stop playback" in labels
        assert "FS16 verify playback file Emulation0609.smu" in labels
        assert body["extra"]["fs16_playback"]["visible"] is True
        assert (
            body["extra"]["fs16_playback"]["remote_playback_path"]
            == "D:\\User Playbacks\\Emulation0609.smu"
        )

        ce.connect.assert_awaited_once()
        ce.load_channel.assert_awaited_once()
        _, kwargs = ce.load_channel.await_args
        assert kwargs["mode"] == ChannelLoadMode.EXTERNAL_WAVEFORM
        assert kwargs["parameters"] == {"remote_playback_file": "Emulation0609.smu"}
        ce.start_emulation.assert_awaited_once()
        ce.stop_emulation.assert_awaited_once()
        bs.set_cell_config.assert_awaited_once()
        cell_config = bs.set_cell_config.await_args.args[0]
        assert cell_config["frequency_mhz"] == 3600
        assert cell_config["mimo_layers"] == 2

        audit = (
            db.query(DiagnosticRun)
            .filter(DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"]))
            .first()
        )
        assert audit is not None
        assert audit.success is True
        assert audit.target_name == "fs16_hybrid_kpi_smoke"

    def test_smu_load_failure_surfaces_fs16_last_error(
        self,
        lab_with_bs_ce,
        monkeypatch,
    ):
        ce = FakeFs16PlaybackDriver()
        ce._last_error = (
            'FS16 playback load failed: -300,"Device-specific error;'
            'SMU file corrupt or missing"'
        )
        ce.load_channel = AsyncMock(return_value=False)
        bs = MockFastBaseStation()
        _patched_hal(monkeypatch, {"channelEmulator": ce, "baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_hybrid_kpi_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "params": {
                    "remote_playback_file": "Emulation0609.smu",
                    "base_station_mode": "mock",
                },
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "SMU file corrupt or missing" in body["summary"]
        failed_steps = [step for step in body["steps"] if step["success"] is False]
        assert failed_steps[0]["label"] == "FS16 load playback Emulation0609.smu"
        assert "SMU file corrupt or missing" in failed_steps[0]["detail"]

    def test_smu_visibility_failure_stops_before_load(
        self,
        lab_with_bs_ce,
        monkeypatch,
    ):
        ce = FakeFs16PlaybackDriver()
        ce.remote_file_visible = False
        ce._last_error = "MMEM:CAT? did not list Emulation0609.smu"
        bs = MockFastBaseStation()
        _patched_hal(monkeypatch, {"channelEmulator": ce, "baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_hybrid_kpi_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "params": {
                    "remote_playback_file": "Emulation0609.smu",
                    "base_station_mode": "mock",
                },
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "remote playback file not found on FS16" in body["summary"]
        assert "MMEM:CAT? did not list Emulation0609.smu" in body["summary"]
        labels = [step["label"] for step in body["steps"]]
        assert labels == [
            "connect channelEmulator (FS16)",
            "FS16 verify playback file Emulation0609.smu",
        ]
        ce.load_channel.assert_not_called()
        ce.start_emulation.assert_not_called()
        bs.connect.assert_not_called()

    def test_mock_mode_refuses_real_base_station_driver(
        self,
        lab_with_bs_ce,
        monkeypatch,
    ):
        ce = FakeFs16PlaybackDriver()
        bs = FakeRealBaseStation()
        _patched_hal(monkeypatch, {"channelEmulator": ce, "baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_hybrid_kpi_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "params": {"base_station_mode": "mock"},
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "base_station_mode=mock" in body["summary"]
        assert "FakeRealBaseStation" in body["summary"]
        ce.connect.assert_not_called()
        bs.connect.assert_not_called()

    def test_attach_timeout_still_surfaces_cleanup_steps(
        self,
        lab_with_bs_ce,
        monkeypatch,
    ):
        ce = FakeFs16PlaybackDriver()
        bs = MockFastBaseStation()
        bs.get_ue_info = AsyncMock(return_value={"connected": False, "imsi": "001010000000001"})
        _patched_hal(monkeypatch, {"channelEmulator": ce, "baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_hybrid_kpi_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "params": {
                    "remote_playback_file": "Emulation0609.smu",
                    "base_station_mode": "mock",
                    "attach_timeout_s": 0.01,
                    "attach_poll_interval_s": 0.01,
                    "stop_after_s": 0,
                    "cleanup_on_finish": True,
                },
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is False
        assert body["summary"] == "DUT did not attach within timeout"
        labels = [step["label"] for step in body["steps"]]
        assert any(label.startswith("DUT attach") for label in labels)
        assert "BS stop_signaling" in labels
        assert "FS16 stop playback" in labels
        assert body["extra"]["cleanup_warnings"] == []
        assert body["extra"]["fs16_playback"]["playback_left_running"] is False
        assert body["extra"]["fs16_playback"]["bs_signaling_left_running"] is False
        bs.stop_signaling.assert_awaited_once()
        ce.stop_emulation.assert_awaited_once()

    def test_cleanup_disabled_reports_playback_left_running(
        self,
        lab_with_bs_ce,
        monkeypatch,
    ):
        ce = FakeFs16PlaybackDriver()
        bs = MockFastBaseStation()
        _patched_hal(monkeypatch, {"channelEmulator": ce, "baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_hybrid_kpi_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "params": {
                    "remote_playback_file": "Emulation0609.smu",
                    "base_station_mode": "mock",
                    "throughput_windows": 1,
                    "throughput_window_s": 0.01,
                    "stop_after_s": 0,
                    "cleanup_on_finish": False,
                },
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["extra"]["fs16_playback"]["playback_left_running"] is True
        assert body["extra"]["fs16_playback"]["bs_signaling_left_running"] is True
        ce.stop_emulation.assert_not_called()
        bs.stop_signaling.assert_not_called()

    def test_real_mode_allows_real_base_station_branch(
        self,
        lab_with_bs_ce,
        monkeypatch,
    ):
        ce = FakeFs16PlaybackDriver()
        bs = FakeRealBaseStation()
        _patched_hal(monkeypatch, {"channelEmulator": ce, "baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_hybrid_kpi_smoke/run",
            json={
                "lab_profile_id": str(lab_with_bs_ce.id),
                "params": {
                    "base_station_mode": "real",
                    "throughput_windows": 1,
                    "throughput_window_s": 0.01,
                    "stop_after_s": 0,
                },
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["extra"]["instrument_modes"]["baseStation"] == "real"
        assert body["extra"]["instrument_modes"]["DUT"] == "real_or_external"
        bs.connect.assert_awaited_once()
        bs.set_cell_config.assert_awaited_once()


class TestMockBaseStationKpiSurface:
    @pytest.mark.asyncio
    async def test_mock_kpis_include_rsrp_and_sinr(self):
        bs = MockBaseStation("mock-bs", {})

        await bs.connect()
        await bs.set_downlink_power(-50)
        await bs.start_signaling(timeout_s=0)

        metrics = (await bs.measure_throughput_window(0)).to_dict()

        assert -120.0 <= metrics["rsrp_dbm"] <= -45.0
        assert -5.0 <= metrics["sinr_db"] <= 30.0
        assert metrics["rsrp_dbm"] != -999.0
        assert metrics["sinr_db"] != -999.0
