"""P1-73C Task 15: CMW readiness is current LabProfile-bound truth."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.services.instrument_hal_service import build_cmw500_lte_2x2_readiness
from app.services.base_station_binding import build_base_station_binding_preview


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _configured(db, *, binding_endpoint: str = "192.0.2.10"):
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode="real",
    )
    db.add(category)
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="R&S",
        model="CMW500",
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint="192.0.2.10",
        connection_params={
            "base_station_adapter_profile": {
                "schema_version": 1,
                "adapter": "cmw500",
                "lte_2x2_internal_route": {
                    "pcc_bb_board": "BB1",
                    "rx_connector": "RF1C",
                    "rx_converter": "RX1",
                    "tx1_connector": "RF1C",
                    "tx1_converter": "TX1",
                    "tx2_connector": "RF2C",
                    "tx2_converter": "TX2",
                },
            }
        },
        cmw500_lte_2x2_formal_enabled=True,
        cmw500_lte_2x2_formal_updated_at=datetime(
            2026, 8, 26, 12, 0, tzinfo=timezone.utc
        ),
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": binding_endpoint,
                "driver_mode": "real",
                "role": "baseStation",
            }
        ],
    )
    db.add_all([connection, lab])
    db.commit()
    driver = RealCmw500Driver("cmw", {"ip_address": connection.endpoint})
    driver._identity_model = "CMW"
    driver._identity_model_verified = True
    driver._firmware_version = "3.5.40"
    driver._installed_options = ["CMW-KS500", "CMW-KS520"]
    driver._options_snapshot_verified = True
    return lab, connection, driver


def test_readiness_uses_current_bound_connection_and_duplex_specific_options(db):
    lab, connection, driver = _configured(db)

    readiness = build_cmw500_lte_2x2_readiness(
        db,
        lab_profile_id=lab.id,
        hal=SimpleNamespace(drivers={"baseStation": driver}),
    )

    assert readiness.connection_id == str(connection.id)
    assert readiness.adapter_registered is True
    assert readiness.identity_verified is True
    assert readiness.firmware_version == "3.5.40"
    assert readiness.options == ["CMW-KS500", "CMW-KS520"]
    assert readiness.formal_enabled is True
    assert readiness.formal_updated_at == "2026-08-26T12:00:00"
    assert readiness.fdd_ready is True
    assert readiness.tdd_ready is False
    assert readiness.status == "ready"
    preview = build_base_station_binding_preview(
        db,
        SimpleNamespace(drivers={"baseStation": driver}),
        lab,
    )
    assert readiness.binding_digest == preview.binding_digest


def test_readiness_binding_drift_is_warning_not_another_connection_fallback(db):
    lab, connection, driver = _configured(db, binding_endpoint="192.0.2.99")

    readiness = build_cmw500_lte_2x2_readiness(
        db,
        lab_profile_id=lab.id,
        hal=SimpleNamespace(drivers={"baseStation": driver}),
    )

    assert readiness.status == "warning"
    assert readiness.connection_id is None
    assert readiness.fdd_ready is False
    assert "binding" in readiness.detail.lower()
    assert readiness.binding_digest is None


def test_readiness_rejects_loaded_driver_from_another_connection(db):
    lab, connection, _driver = _configured(db)
    driver = RealCmw500Driver("cmw-other", {"ip_address": "192.0.2.77"})
    driver._identity_model = "CMW"
    driver._identity_model_verified = True
    driver._firmware_version = "3.5.40"
    driver._installed_options = ["CMW-KS500", "CMW-KS520"]
    driver._options_snapshot_verified = True

    readiness = build_cmw500_lte_2x2_readiness(
        db,
        lab_profile_id=lab.id,
        hal=SimpleNamespace(drivers={"baseStation": driver}),
    )

    assert readiness.status == "warning"
    assert readiness.connection_id is None
    assert readiness.fdd_ready is False
    assert readiness.tdd_ready is False
    assert "connection" in readiness.detail.lower()
    assert readiness.binding_digest is None


def test_readiness_mock_is_diagnostic_and_never_formal_ready(db):
    from app.hal.base_station import MockBaseStation

    lab, connection, _driver = _configured(db)
    category = db.query(InstrumentCategory).filter_by(category_key="baseStation").one()
    category.driver_mode = "mock"
    bindings = [dict(binding) for binding in lab.instrument_bindings]
    bindings[0]["driver_mode"] = "mock"
    lab.instrument_bindings = bindings
    db.commit()
    mock = MockBaseStation("mock", {"model": "CMW500"})

    readiness = build_cmw500_lte_2x2_readiness(
        db,
        lab_profile_id=lab.id,
        hal=SimpleNamespace(drivers={"baseStation": mock}),
    )

    assert readiness.status == "diagnostic"
    assert readiness.connection_id == str(connection.id)
    assert readiness.fdd_ready is False
    assert readiness.tdd_ready is False
    assert readiness.binding_digest


def test_uxm_binding_is_not_applicable_to_cmw_mirror_without_profile_requirement(db):
    lab, connection, _driver = _configured(db)
    category = db.query(InstrumentCategory).filter_by(category_key="baseStation").one()
    model = db.query(InstrumentModel).filter_by(category_id=category.id).one()
    model.vendor = "Keysight"
    model.model = "UXM 5G E7515B"
    connection.connection_params = None
    db.commit()
    driver = RealUxmDriver("uxm", {"ip_address": connection.endpoint})

    readiness = build_cmw500_lte_2x2_readiness(
        db,
        lab_profile_id=lab.id,
        hal=SimpleNamespace(drivers={"baseStation": driver}),
    )

    assert readiness.status == "not_applicable"
    assert readiness.binding_digest
    assert "profile" not in readiness.detail.lower()
