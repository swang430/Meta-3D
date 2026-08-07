from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.services.instrument_hal_service import DriverMode, InstrumentHALService


@pytest.fixture
def test_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    monkeypatch.setattr("app.db.database.engine", engine)
    monkeypatch.setattr("app.db.database.SessionLocal", TestSessionLocal)

    def _override():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override
    try:
        yield TestSessionLocal
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=engine)


def _seed_channel_emulator(
    SessionLocal,
    *,
    control_mode: str = "software",
):
    db = SessionLocal()
    try:
        cat = InstrumentCategory(
            id=uuid.uuid4(),
            category_key="channelEmulator",
            category_name="信道仿真器",
            category_name_en="Channel Emulator",
            is_active=True,
            driver_mode="real",
        )
        model = InstrumentModel(
            id=uuid.uuid4(),
            category_id=cat.id,
            vendor="Keysight",
            model="PROPSIM FS16",
            full_name="Keysight PROPSIM FS16",
            capabilities={"channels": 16, "interfaces": ["LAN"]},
        )
        cat.selected_model_id = model.id
        conn = InstrumentConnection(
            id=uuid.uuid4(),
            category_id=cat.id,
            endpoint="TCPIP0::192.168.0.100::hislip0::INSTR",
            controller_ip="192.168.0.100",
            port=3334,
            protocol="SCPI",
            status="connected",
            connection_params={"control_mode": control_mode},
            created_by="test",
        )
        db.add_all([cat, model, conn])
        db.commit()
        return cat.id, conn.id
    finally:
        db.close()


def _connection_params(SessionLocal, conn_id) -> dict:
    db = SessionLocal()
    try:
        conn = db.query(InstrumentConnection).filter(InstrumentConnection.id == conn_id).one()
        return dict(conn.connection_params or {})
    finally:
        db.close()


def test_manual_local_scpi_command_is_rejected_without_touching_hal(test_db, monkeypatch):
    _seed_channel_emulator(test_db, control_mode="manual_local")

    def fail_if_hal_routed(_category_key: str):
        raise AssertionError("manual_local must not route through HAL")

    monkeypatch.setattr("app.api.instrument._get_loaded_hal_driver", fail_if_hal_routed)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/instruments/channelEmulator/scpi-command",
            json={"command": "*IDN?", "timeout_ms": 5000},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "manual_local" in body["error"]


def test_manual_local_scpi_probe_returns_rejected_results(test_db):
    _seed_channel_emulator(test_db, control_mode="manual_local")

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/instruments/channelEmulator/scpi-probe",
            json={"timeout_ms": 5000},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["results"]
    assert all(result["success"] is False for result in body["results"])
    assert all("manual_local" in result["error"] for result in body["results"])


@pytest.mark.asyncio
async def test_monitoring_metrics_skip_manual_local_driver():
    class FakeDriver:
        control_mode = "manual_local"

        async def get_metrics(self):
            raise AssertionError("manual_local driver should not be polled")

    service = InstrumentHALService(mode=DriverMode.REAL)
    service._initialized = True
    service.drivers["channel_emulator"] = FakeDriver()

    metrics = await service.get_aggregated_metrics()

    assert metrics


def test_switching_back_to_software_persists_mode_and_reloads_hal(test_db, monkeypatch):
    _cat_id, conn_id = _seed_channel_emulator(test_db, control_mode="manual_local")
    fake_hal = SimpleNamespace(mode=DriverMode.MOCK, drivers={})
    reload_calls: list[DriverMode] = []

    def fake_get_hal_service():
        return fake_hal

    async def fake_reload(mode: DriverMode):
        reload_calls.append(mode)
        fake_hal.drivers["channelEmulator"] = object()

    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service",
        fake_get_hal_service,
    )
    monkeypatch.setattr(
        "app.services.instrument_hal_service.reload_hal_service_atomic",
        fake_reload,
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/instruments/channelEmulator/control-mode",
            json={"mode": "software"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "software"
    assert body["driver_loaded"] is True
    assert reload_calls == [DriverMode.MOCK]
    assert _connection_params(test_db, conn_id)["control_mode"] == "software"
