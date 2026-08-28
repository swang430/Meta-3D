from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.cmw500_base_station import RealCmw500Driver
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.services.base_station_adapter_profile import (
    FREEZE_CONFIG_KEY,
    freeze_base_station_adapter_profile,
)
from app.services.execution_qualification import (
    activate_base_station_site_certification,
    revoke_base_station_site_certification,
)
from app.services.execution_scpi_evidence import save_base_station_execution_evidence
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence


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


def _cmw_profile():
    return {
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


def _source_execution(db):
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
        connection_params={"base_station_adapter_profile": _cmw_profile()},
        cmw500_lte_2x2_formal_enabled=False,
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": "192.0.2.10",
                "driver_mode": "real",
                "role": "baseStation",
            }
        ],
    )
    db.add_all([connection, lab])
    db.flush()
    case = TestCase(
        name="certification source",
        test_type="MIMO_OTA",
        configuration={},
        created_by="test",
        lab_profile_id=lab.id,
    )
    db.add(case)
    db.flush()
    execution = TestExecution(
        test_case_id=case.id,
        status="completed",
        executed_by="test",
        config={},
    )
    db.add(execution)
    db.flush()
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    hal = SimpleNamespace(drivers={"baseStation": driver})
    freeze_base_station_adapter_profile(db, hal, execution, lab)
    evidence = valid_cmw_evidence()
    evidence["execution_id"] = str(execution.id)
    evidence["identity"]["instrument_connection_id"] = str(connection.id)
    evidence["formal_capability_approval"].update(
        instrument_connection_id=str(connection.id),
        enabled=False,
        updated_at=None,
    )
    save_base_station_execution_evidence(execution, evidence)
    db.commit()
    return connection, lab, case, execution, hal


def test_active_certification_is_derived_only_from_server_execution_evidence(db):
    connection, lab, _case, execution, hal = _source_execution(db)

    certification = activate_base_station_site_certification(
        db,
        hal,
        connection_id=connection.id,
        source_execution_id=execution.id,
        certified_by="quality-owner",
        reason="现场真机配置、窗口、清理与释放已复核",
    )

    db.refresh(connection)
    assert certification.status == "active"
    assert certification.lab_profile_id == str(lab.id)
    assert certification.instrument_connection_id == str(connection.id)
    assert certification.source_execution_id == str(execution.id)
    assert certification.adapter_id == "cmw500"
    assert certification.model == "CMW"
    assert certification.required_proofs.model_dump() == {
        "config_readback": True,
        "route_readback": True,
        "route_not_applicable": False,
        "cleanup": True,
        "transport_release": True,
    }
    assert connection.base_station_site_certification == certification.model_dump(
        mode="json"
    )
    assert connection.cmw500_lte_2x2_formal_enabled is False


@pytest.mark.parametrize(
    "mutation",
    [
        "execution_running",
        "simulated",
        "wrong_execution_id",
        "config_unknown",
        "route_unknown",
        "attempt_failed",
        "cleanup_unknown",
        "release_unknown",
        "binding_digest",
        "connection_id",
    ],
)
def test_certification_rejects_every_incomplete_or_wrong_scope(db, mutation):
    connection, _lab, _case, execution, hal = _source_execution(db)
    evidence = deepcopy(execution.config["base_station_execution_evidence"])
    if mutation == "execution_running":
        execution.status = "running"
    elif mutation == "simulated":
        evidence["execution_mode"] = "simulated"
    elif mutation == "wrong_execution_id":
        evidence["execution_id"] = "old-execution"
    elif mutation == "config_unknown":
        evidence["config_confirmed"] = False
    elif mutation == "route_unknown":
        evidence["route_confirmed"] = False
        evidence["applied_route"] = None
    elif mutation == "attempt_failed":
        evidence["current_measurement_attempt_state"] = "failed"
    elif mutation == "cleanup_unknown":
        evidence["measurement_windows"][0]["cleanup"]["safe_idle_confirmed"] = False
    elif mutation == "release_unknown":
        evidence["control_releases"][0][
            "transport_session_released_confirmed"
        ] = False
    elif mutation == "binding_digest":
        execution.config = {
            **execution.config,
            FREEZE_CONFIG_KEY: {
                **execution.config[FREEZE_CONFIG_KEY],
                "binding_digest": "old-binding",
            },
        }
    elif mutation == "connection_id":
        evidence["identity"]["instrument_connection_id"] = str(uuid4())
        evidence["formal_capability_approval"]["instrument_connection_id"] = (
            evidence["identity"]["instrument_connection_id"]
        )
    if mutation not in {"execution_running", "binding_digest"}:
        execution.config = {
            **execution.config,
            "base_station_execution_evidence": evidence,
        }
    db.commit()

    with pytest.raises(ValueError):
        activate_base_station_site_certification(
            db,
            hal,
            connection_id=connection.id,
            source_execution_id=execution.id,
            certified_by="quality-owner",
            reason="should fail",
        )
    db.refresh(connection)
    assert connection.base_station_site_certification is None


def test_revocation_keeps_source_evidence_and_records_server_time(db):
    connection, _lab, _case, execution, hal = _source_execution(db)
    active = activate_base_station_site_certification(
        db,
        hal,
        connection_id=connection.id,
        source_execution_id=execution.id,
        certified_by="quality-owner",
        reason="site proof complete",
    )

    revoked = revoke_base_station_site_certification(
        db,
        connection_id=connection.id,
        revoked_by="quality-owner",
        reason="firmware changed",
    )

    assert revoked.status == "revoked"
    assert revoked.source_execution_id == active.source_execution_id
    assert revoked.evidence_digest == active.evidence_digest
    assert revoked.revoked_by == "quality-owner"
    assert revoked.revoked_at is not None
    assert revoked.revocation_reason == "firmware changed"
