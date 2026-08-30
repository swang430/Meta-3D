from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.test_plan import TestExecution
from app.services.base_station_model_preset_recovery import (
    recover_cmw500_model_preset,
)


ROUTE = {
    "pcc_bb_board": "SUA1",
    "rx_connector": "RF1C",
    "rx_converter": "RX1",
    "tx1_connector": "RF1O",
    "tx1_converter": "TX1",
    "tx2_connector": "RF3C",
    "tx2_converter": "TX2",
}


@pytest.fixture
def recovery_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def _records(db, *, execution_mode="real", route_confirmed=True, applied_route=None):
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode="real",
    )
    db.add(category)
    db.flush()
    cmw = InstrumentModel(
        category_id=category.id,
        vendor="R&S",
        model="CMW500",
        capabilities={},
    )
    uxm = InstrumentModel(
        category_id=category.id,
        vendor="Keysight",
        model="UXM 5G E7515B",
        capabilities={},
    )
    db.add_all([cmw, uxm])
    db.flush()
    category.selected_model_id = uxm.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint="192.168.1.112",
        protocol="SOCKET",
        notes="active UXM",
        connection_params={"uxm_only": True},
        base_station_model_presets={
            str(uxm.id): {
                "schema_version": 1,
                "model_id": str(uxm.id),
                "endpoint": "192.168.1.112",
                "controller": "SOCKET",
                "notes": "active UXM",
                "connection_params": {"uxm_only": True},
                "base_station_adapter_profile": None,
            }
        },
    )
    db.add(connection)
    db.flush()
    profile = {
        "schema_version": 1,
        "adapter": "cmw500",
        "lte_2x2_internal_route": ROUTE,
    }
    execution = TestExecution(
        status="failed",
        config={
            "base_station_adapter_profile_freeze": {
                "instrument_model_id": str(cmw.id),
                "instrument_connection_id": str(connection.id),
                "expected_driver_connection": {
                    "resource": "TCPIP0::192.168.0.149::hislip0::INSTR",
                },
                "resolution": {
                    "status": "configured",
                    "adapter": "cmw500",
                    "execution_mode": execution_mode,
                    "profile": profile,
                },
            },
            "base_station_execution_evidence": {
                "adapter": "cmw500",
                "execution_mode": execution_mode,
                "route_confirmed": route_confirmed,
                "applied_route": {
                    "payload": applied_route if applied_route is not None else ROUTE,
                },
                "identity": {
                    "instrument_connection_id": str(connection.id),
                },
            },
        },
    )
    db.add(execution)
    db.commit()
    return category, cmw, uxm, connection, execution


def test_recovery_preserves_active_uxm_and_adds_only_evidence_backed_cmw_preset(
    recovery_db,
):
    category, cmw, uxm, connection, execution = _records(recovery_db)
    before = (category.selected_model_id, connection.endpoint, connection.connection_params)

    preview = recover_cmw500_model_preset(
        recovery_db,
        connection_id=connection.id,
        model_id=cmw.id,
        source_execution_id=execution.id,
        apply=False,
    )
    assert preview.changed is True
    assert set(connection.base_station_model_presets) == {str(uxm.id)}

    applied = recover_cmw500_model_preset(
        recovery_db,
        connection_id=connection.id,
        model_id=cmw.id,
        source_execution_id=execution.id,
        apply=True,
    )
    assert applied.changed is True
    assert applied.preset.endpoint == "TCPIP0::192.168.0.149::hislip0::INSTR"
    assert applied.preset.controller == ""
    assert applied.preset.notes == ""
    assert applied.preset.connection_params == {}
    assert applied.preset.base_station_adapter_profile["lte_2x2_internal_route"] == ROUTE
    assert set(connection.base_station_model_presets) == {str(uxm.id), str(cmw.id)}
    assert (category.selected_model_id, connection.endpoint, connection.connection_params) == before

    repeated = recover_cmw500_model_preset(
        recovery_db,
        connection_id=connection.id,
        model_id=cmw.id,
        source_execution_id=execution.id,
        apply=True,
    )
    assert repeated.changed is False


@pytest.mark.parametrize(
    ("execution_mode", "route_confirmed", "applied_route"),
    [
        ("simulated", True, ROUTE),
        ("real", False, ROUTE),
        ("real", True, {**ROUTE, "tx2_connector": "RF2C"}),
    ],
)
def test_recovery_rejects_simulated_unconfirmed_or_mismatched_evidence(
    recovery_db, execution_mode, route_confirmed, applied_route
):
    _category, cmw, _uxm, connection, execution = _records(
        recovery_db,
        execution_mode=execution_mode,
        route_confirmed=route_confirmed,
        applied_route=applied_route,
    )
    with pytest.raises(ValueError):
        recover_cmw500_model_preset(
            recovery_db,
            connection_id=connection.id,
            model_id=cmw.id,
            source_execution_id=execution.id,
            apply=True,
        )
