from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel


def _cmw_profile(rx: str = "RF1C") -> dict:
    return {
        "schema_version": 1,
        "adapter": "cmw500",
        "lte_2x2_internal_route": {
            "pcc_bb_board": "SUA1",
            "rx_connector": rx,
            "rx_converter": "RX1",
            "tx1_connector": "RF1O",
            "tx1_converter": "TX1",
            "tx2_connector": "RF3C",
            "tx2_converter": "TX2",
        },
    }


@pytest.fixture
def atomic_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()
    category = InstrumentCategory(
        id=uuid4(),
        category_key="baseStation",
        category_name="基站模拟器",
        driver_mode="mock",
        is_active=True,
    )
    cmw = InstrumentModel(
        id=uuid4(),
        category_id=category.id,
        vendor="Rohde & Schwarz",
        model="CMW500",
        capabilities={},
        is_available=True,
    )
    uxm = InstrumentModel(
        id=uuid4(),
        category_id=category.id,
        vendor="Keysight",
        model="UXM 5G E7515B",
        capabilities={},
        is_available=True,
    )
    category.selected_model_id = cmw.id
    connection = InstrumentConnection(
        id=uuid4(),
        category_id=category.id,
        endpoint="TCPIP0::192.168.0.149::hislip0::INSTR",
        controller_ip="192.168.0.149",
        port=4880,
        protocol="hislip",
        notes="saved CMW",
        connection_params={
            "timeout_sec": 30,
            "base_station_adapter_profile": _cmw_profile(),
        },
        base_station_model_presets=None,
        created_by="test",
    )
    db.add_all([category, cmw, uxm, connection])
    db.commit()
    category_id = category.id
    cmw_id = cmw.id
    uxm_id = uxm.id
    db.close()

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield Session, category_id, cmw_id, uxm_id
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        Base.metadata.drop_all(engine)


def test_switch_save_preserves_old_model_and_atomically_projects_target(atomic_db):
    Session, category_id, cmw_id, uxm_id = atomic_db
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/instruments/baseStation",
            json={
                "modelId": str(uxm_id),
                "connection": {
                    "endpoint": "TCPIP0::192.168.1.112::5125::SOCKET",
                    "controller": "socket",
                    "notes": "saved UXM",
                    "connection_params": {"timeout_sec": 15},
                    "base_station_adapter_profile": None,
                },
            },
        )
    assert response.status_code == 200, response.text

    with Session() as db:
        category = db.get(InstrumentCategory, category_id)
        connection = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.category_id == category_id)
            .one()
        )
        assert category.selected_model_id == uxm_id
        assert connection.endpoint == "TCPIP0::192.168.1.112::5125::SOCKET"
        assert connection.controller_ip == "192.168.1.112"
        assert connection.port == 5125
        assert connection.protocol == "socket"
        assert connection.connection_params == {"timeout_sec": 15}
        presets = connection.base_station_model_presets
        assert set(presets) == {str(cmw_id), str(uxm_id)}
        assert presets[str(cmw_id)]["base_station_adapter_profile"] == _cmw_profile()
        assert presets[str(cmw_id)]["endpoint"].endswith("hislip0::INSTR")
        assert presets[str(uxm_id)]["base_station_adapter_profile"] is None


def test_target_without_port_clears_previous_model_port(atomic_db):
    Session, category_id, _cmw_id, uxm_id = atomic_db
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/instruments/baseStation",
            json={
                "modelId": str(uxm_id),
                "connection": {
                    "endpoint": "192.168.1.112",
                    "controller": "socket",
                    "base_station_adapter_profile": None,
                },
            },
        )
    assert response.status_code == 200, response.text
    with Session() as db:
        connection = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.category_id == category_id)
            .one()
        )
        assert connection.controller_ip == "192.168.1.112"
        assert connection.port is None


def test_invalid_target_profile_rolls_back_model_connection_and_presets(atomic_db):
    Session, category_id, cmw_id, uxm_id = atomic_db
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/instruments/baseStation",
            json={
                "modelId": str(uxm_id),
                "connection": {
                    "endpoint": "192.168.1.112:5125",
                    "base_station_adapter_profile": _cmw_profile(),
                },
            },
        )
    assert response.status_code == 422, response.text
    with Session() as db:
        category = db.get(InstrumentCategory, category_id)
        connection = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.category_id == category_id)
            .one()
        )
        assert category.selected_model_id == cmw_id
        assert connection.endpoint.endswith("hislip0::INSTR")
        assert connection.base_station_model_presets is None
