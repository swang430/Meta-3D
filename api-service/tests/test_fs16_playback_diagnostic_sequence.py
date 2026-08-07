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


class FakeFs16AddEmulationDriver:
    def __init__(self) -> None:
        self.source_exists = True
        self.model_source = r"D:\Models\3GPP_5GNR_2x2_TDLA30-5_low_correlation.ctap"
        self.connector_by_channel = {
            1: "1,RF-1,RF-1,1,1",
            2: "2,RF-2,RF-2,1,1",
            3: "3,RF-3,RF-3,1,1",
            4: "4,RF-4,RF-4,1,1",
        }
        self.connect_should_succeed = True
        self._last_error = ""
        self.commands: list[tuple] = []
        self.connect = AsyncMock(return_value=True)
        self.start_emulation = AsyncMock(return_value=True)
        self.stop_emulation = AsyncMock(return_value=True)

    async def remote_emulation_file_exists(self, source: str) -> bool:
        self.commands.append(("exists", source))
        return self.source_exists

    async def open_emulation_for_edit(self, source: str) -> bool:
        self.commands.append(("edit", source))
        return True

    async def query_channel_model_source(self, channel: int) -> str:
        self.commands.append(("model_source", channel))
        return self.model_source

    async def set_center_frequency(self, channel: int, frequency_mhz: float) -> bool:
        self.commands.append(("center_frequency", channel, frequency_mhz))
        return True

    async def set_input_enabled(self, channel: int, enabled: bool) -> bool:
        self.commands.append(("input_enabled", channel, enabled))
        return True

    async def set_input_level(self, channel: int, level_dbm: float) -> bool:
        self.commands.append(("input_level", channel, level_dbm))
        return True

    async def set_input_crest_factor(self, channel: int, crest_factor_db: float) -> bool:
        self.commands.append(("crest_factor", channel, crest_factor_db))
        return True

    async def set_output_enabled(self, channel: int, enabled: bool) -> bool:
        self.commands.append(("output_enabled", channel, enabled))
        return True

    async def set_output_level(self, channel: int, level_dbm: float) -> bool:
        self.commands.append(("output_level", channel, level_dbm))
        return True

    async def query_center_frequency(self, channel: int) -> str:
        self.commands.append(("center_frequency_readback", channel))
        return "2010.000"

    async def query_channel_connector(self, channel: int) -> str:
        self.commands.append(("connector", channel))
        return self.connector_by_channel.get(channel, "0,RF-0,RF-0,0,0")

    async def connect_edited_emulation(self) -> bool:
        self.commands.append(("connect_edited",))
        if not self.connect_should_succeed:
            self._last_error = "CALC:FILT:CONN refused"
            return False
        return True

    async def query_simulation_state(self) -> str:
        return "READY"

    async def query_model_info(self) -> str:
        return "5G TDD,2x2,n34"


class TestFs16PlaybackSequenceMetadata:
    def test_loader_discovers_fs16_playback_sequence(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        entry = next(s for s in resp.json() if s["key"] == "fs16_playback_smoke")
        assert entry["required_categories"] == ["channelEmulator"]
        assert entry["safe_during_test"] is False
        assert any(p["name"] == "remote_playback_file" for p in entry["params_schema"])

    def test_loader_discovers_fs16_add_emulation_sequence(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        entry = next(s for s in resp.json() if s["key"] == "fs16_add_emulation")
        assert entry["required_categories"] == ["channelEmulator"]
        assert entry["safe_during_test"] is False
        assert any(p["name"] == "source_smu_file" for p in entry["params_schema"])
        assert any(p["name"] == "connect_after_edit" for p in entry["params_schema"])


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


class TestFs16AddEmulationSequenceRun:
    def test_default_params_open_edit_apply_connect_and_readback(
        self,
        db,
        lab_with_ce,
        monkeypatch,
    ):
        ce = FakeFs16AddEmulationDriver()
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_add_emulation/run",
            json={
                "lab_profile_id": str(lab_with_ce.id),
                "run_by": "pytest",
                "params": {},
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        result = body["extra"]["fs16_add_emulation"]
        assert result["source_smu_file"] == r"D:\User Emulations\Emulation15.wiz\Emulation15.smu"
        assert len(result["wizard_steps"]) == 5
        assert result["wizard_steps"][-1]["step"] == 5
        assert "CALC:FILT:CONN" in result["applied_scpi"]
        assert result["readback"]["simulation_state"] == "READY"
        assert ("edit", r"D:\User Emulations\Emulation15.wiz\Emulation15.smu") in ce.commands
        assert ("connect_edited",) in ce.commands

        audit = (
            db.query(DiagnosticRun)
            .filter(DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"]))
            .first()
        )
        assert audit is not None
        assert audit.success is True
        assert audit.target_name == "fs16_add_emulation"

    def test_parameter_overrides_are_used(self, lab_with_ce, monkeypatch):
        ce = FakeFs16AddEmulationDriver()
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_add_emulation/run",
            json={
                "lab_profile_id": str(lab_with_ce.id),
                "params": {
                    "source_smu_file": r"D:\User Emulations\Alt.smu",
                    "center_frequency_mhz": 2020.5,
                    "out_level_dbm": -28.25,
                    "channel_numbers": "1",
                    "output_numbers": "1",
                    "connector_map": "BS1.1=RF1",
                },
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        result = body["extra"]["fs16_add_emulation"]
        assert result["source_smu_file"] == r"D:\User Emulations\Alt.smu"
        assert "CALC:FILT:CENT:CH 1,2020.500" in result["applied_scpi"]
        assert "OUTP:LEV:AMP:CH 1,-28.250" in result["applied_scpi"]
        assert ("center_frequency", 1, 2020.5) in ce.commands
        assert ("output_level", 1, -28.25) in ce.commands

    def test_missing_source_smu_fails_before_edit(self, lab_with_ce, monkeypatch):
        ce = FakeFs16AddEmulationDriver()
        ce.source_exists = False
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_add_emulation/run",
            json={"lab_profile_id": str(lab_with_ce.id), "params": {}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "source .smu not found" in body["summary"]
        assert not any(cmd[0] == "edit" for cmd in ce.commands)

    def test_channel_model_mismatch_fails_step_2(self, lab_with_ce, monkeypatch):
        ce = FakeFs16AddEmulationDriver()
        ce.model_source = r"D:\Models\unexpected.ctap"
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_add_emulation/run",
            json={"lab_profile_id": str(lab_with_ce.id), "params": {}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "channel model readback mismatch" in body["summary"]
        wizard_steps = body["extra"]["fs16_add_emulation"]["wizard_steps"]
        assert wizard_steps[-1]["step"] == 2
        assert wizard_steps[-1]["success"] is False

    def test_connector_mismatch_fails_step_4(self, lab_with_ce, monkeypatch):
        ce = FakeFs16AddEmulationDriver()
        ce.connector_by_channel = {i: f"{i},RF-9,RF-9,1,1" for i in range(1, 5)}
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_add_emulation/run",
            json={"lab_profile_id": str(lab_with_ce.id), "params": {}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "connector readback mismatch" in body["summary"]
        wizard_steps = body["extra"]["fs16_add_emulation"]["wizard_steps"]
        assert wizard_steps[-1]["step"] == 4
        assert wizard_steps[-1]["success"] is False

    def test_connect_failure_surfaces_driver_error(self, lab_with_ce, monkeypatch):
        ce = FakeFs16AddEmulationDriver()
        ce.connect_should_succeed = False
        _patched_hal(monkeypatch, {"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/fs16_add_emulation/run",
            json={"lab_profile_id": str(lab_with_ce.id), "params": {}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "CALC:FILT:CONN refused" in body["summary"]
        wizard_steps = body["extra"]["fs16_add_emulation"]["wizard_steps"]
        assert wizard_steps[-1]["step"] == 5
        assert wizard_steps[-1]["success"] is False
