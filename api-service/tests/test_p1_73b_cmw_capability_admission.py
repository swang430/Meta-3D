"""P1-73B Task 11: CMW500 formal capability has one durable source."""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.instrument import (
    Cmw500FormalCapabilityUpdate,
    update_cmw500_lte_2x2_formal_capability,
    update_instrument_category,
)
from app.db.database import Base
from app.hal.cmw500_base_station import RealCmw500Driver
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.schemas.instrument import (
    FEConnectionUpdate,
    InstrumentConnectionCreate,
    InstrumentConnectionUpdate,
    UpdateInstrumentCategoryRequest,
)
from app.services.base_station_adapter_profile import freeze_base_station_adapter_profile
from app.services.instrument_hal_service import get_real_driver_class


def _route_profile():
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


def _configured(db, *, category_key="baseStation", model_name="CMW500"):
    category = InstrumentCategory(category_key=category_key, category_name=category_key)
    db.add(category)
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="R&S",
        model=model_name,
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint="192.0.2.10",
        connection_params={"base_station_adapter_profile": _route_profile()},
        created_by="test",
    )
    db.add(connection)
    db.commit()
    return category, model, connection


def test_formal_capability_defaults_false_and_only_dedicated_endpoint_can_toggle(
    db, monkeypatch,
):
    category, _, connection = _configured(db)
    db.refresh(connection)
    assert connection.cmw500_lte_2x2_formal_enabled is False
    assert connection.cmw500_lte_2x2_formal_updated_at is None

    original_commit = db.commit
    commits = 0

    def commit():
        nonlocal commits
        commits += 1
        original_commit()

    monkeypatch.setattr(db, "commit", commit)

    result = update_cmw500_lte_2x2_formal_capability(
        connection.id,
        Cmw500FormalCapabilityUpdate(enabled=True),
        db,
    )
    db.refresh(connection)
    assert result.enabled is True
    assert commits == 1
    assert connection.cmw500_lte_2x2_formal_enabled is True
    assert isinstance(connection.cmw500_lte_2x2_formal_updated_at, datetime)
    assert category.category_key == "baseStation"


def test_formal_capability_locks_category_before_connection(db, monkeypatch):
    category, _, connection = _configured(db)
    locked_entities = []
    original = Query.with_for_update

    def _tracked_with_for_update(query, *args, **kwargs):
        locked_entities.append(query.column_descriptions[0].get("entity"))
        return original(query, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", _tracked_with_for_update)
    update_cmw500_lte_2x2_formal_capability(
        connection.id,
        Cmw500FormalCapabilityUpdate(enabled=True),
        db,
    )

    assert locked_entities[:2] == [InstrumentCategory, InstrumentConnection]


def test_cmw500_remains_registered_as_the_base_station_adapter():
    assert get_real_driver_class("baseStation", "CMW500") is RealCmw500Driver


@pytest.mark.parametrize(
    ("category_key", "model_name"),
    [("signalAnalyzer", "CMW500"), ("baseStation", "UXM 5G E7515B")],
)
def test_dedicated_endpoint_rejects_wrong_category_or_model(db, category_key, model_name):
    _, _, connection = _configured(db, category_key=category_key, model_name=model_name)
    with pytest.raises(Exception) as exc_info:
        update_cmw500_lte_2x2_formal_capability(
            connection.id,
            Cmw500FormalCapabilityUpdate(enabled=True),
            db,
        )
    assert getattr(exc_info.value, "status_code", None) == 422


def test_generic_connection_payload_cannot_accept_or_smuggle_formal_enablement(db):
    _, _, connection = _configured(db)
    with pytest.raises(ValidationError):
        FEConnectionUpdate.model_validate({"cmw500_lte_2x2_formal_enabled": True})
    with pytest.raises(ValidationError):
        InstrumentConnectionUpdate.model_validate(
            {"cmw500_lte_2x2_formal_enabled": True}
        )
    with pytest.raises(ValidationError):
        InstrumentConnectionCreate.model_validate({
            "category_id": str(uuid4()),
            "created_by": "test",
            "cmw500_lte_2x2_formal_enabled": True,
        })

    update_instrument_category(
        "baseStation",
        UpdateInstrumentCategoryRequest(
            connection=FEConnectionUpdate(
                connection_params={
                    "cmw500_lte_2x2_formal_enabled": True,
                    "formal_enabled": True,
                }
            )
        ),
        db,
    )
    db.refresh(connection)
    assert connection.cmw500_lte_2x2_formal_enabled is False


def test_execution_freezes_approval_and_later_toggle_does_not_rewrite_it(db):
    category, model, connection = _configured(db)
    category.driver_mode = "real"
    connection.cmw500_lte_2x2_formal_enabled = True
    connection.cmw500_lte_2x2_formal_updated_at = datetime(2026, 8, 26, 8, 0, 0)
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[{
            "category_id": str(category.id),
            "instrument_model_id": str(model.id),
            "connection_endpoint": connection.endpoint,
            "driver_mode": "real",
            "role": "baseStation",
        }],
    )
    # P1-75 兼容性硬门：CMW500 冻结需要显式 lte 的 TestCase 需求端。
    case = TestCase(
        name="p1-73b capability fixture",
        test_type="MIMO_OTA",
        configuration={
            "component_carriers": [
                {
                    "radio_technology": "lte",
                    "band": "B3",
                    "duplex": "fdd",
                    "lte_transmission_mode": "TM3",
                    "lte_dl_earfcn": 1575,
                    "frequency_hz": 1_842_500_000.0,
                    "bandwidth_mhz": 20.0,
                    "role": "pcell",
                }
            ]
        },
        created_by="test",
    )
    db.add(case)
    db.flush()
    execution = TestExecution(test_case_id=case.id, status="pending", config={})
    db.add_all([lab, execution])
    db.commit()
    driver = RealCmw500Driver("cmw", {"ip_address": connection.endpoint})
    frozen = freeze_base_station_adapter_profile(
        db, SimpleNamespace(drivers={"baseStation": driver}), execution, lab
    )

    approval = frozen["cmw500_lte_2x2_formal_capability"]
    assert approval == {
        "schema_version": 1,
        "instrument_connection_id": str(connection.id),
        "enabled": True,
        "updated_at": "2026-08-26T08:00:00",
    }

    connection.cmw500_lte_2x2_formal_enabled = False
    db.commit()
    assert freeze_base_station_adapter_profile(
        db, SimpleNamespace(drivers={"baseStation": driver}), execution, lab
    )["cmw500_lte_2x2_formal_capability"]["enabled"] is True
