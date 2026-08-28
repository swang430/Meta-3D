"""P1-73B Task 7A：CMW 内部 route profile 的解析、选择与冻结真值。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.base_station_adapter_profile import BaseStationAdapterProfile
from app.hal.base_station import MockBaseStation
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.schemas.instrument import FEConnectionUpdate, UpdateInstrumentCategoryRequest
from app.api.instrument import update_instrument_category
from app.services.base_station_adapter_profile import (
    freeze_base_station_adapter_profile,
    freeze_execution_base_station_adapter_profile,
    validate_frozen_base_station_before_remote,
)


def _profile() -> dict[str, object]:
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


def _configured_execution(db, *, model_name: str, params: dict | None):
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode="real",
    )
    db.add(category)
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="R&S" if model_name == "CMW500" else "Keysight",
        model=model_name,
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint="192.0.2.10",
        connection_params=params,
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[{
            "category_id": str(category.id),
            "instrument_model_id": str(model.id),
            "connection_endpoint": "192.0.2.10",
            "driver_mode": "real",
            "role": "baseStation",
        }],
    )
    execution = TestExecution(status="pending", config={})
    db.add_all([connection, lab, execution])
    db.commit()
    return category, model, connection, lab, execution


def test_cmw_profile_is_strict_and_rejects_blank_extra_or_reused_tx_paths():
    parsed = BaseStationAdapterProfile.model_validate(_profile())
    assert parsed.lte_2x2_internal_route.tx2_connector == "RF2C"

    for mutate in ("blank", "extra", "connector", "converter"):
        raw = _profile()
        route = raw["lte_2x2_internal_route"]
        assert isinstance(route, dict)
        if mutate == "blank":
            route["rx_converter"] = "  "
        elif mutate == "extra":
            route["invented"] = "x"
        elif mutate == "connector":
            route["tx2_connector"] = route["tx1_connector"]
        else:
            route["tx2_converter"] = route["tx1_converter"]
        with pytest.raises(ValidationError):
            BaseStationAdapterProfile.model_validate(raw)


def test_cmw_real_resolution_freezes_profile_and_identity_once(db):
    _, model, connection, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    hal = SimpleNamespace(drivers={"baseStation": driver})

    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)

    assert frozen["resolution"]["adapter"] == "cmw500"
    assert frozen["resolution"]["status"] == "configured"
    assert frozen["resolution"]["execution_mode"] == "real"
    assert frozen["instrument_model_id"] == str(model.id)
    assert frozen["instrument_connection_id"] == str(connection.id)
    assert frozen["digest"]
    assert validate_frozen_base_station_before_remote(hal, frozen) is None

    connection.connection_params = {
        "base_station_adapter_profile": {
            **_profile(),
            "lte_2x2_internal_route": {
                **_profile()["lte_2x2_internal_route"],
                "tx2_connector": "RF3C",
            },
        }
    }
    db.commit()
    assert freeze_base_station_adapter_profile(db, hal, execution, lab) == frozen


def test_cmw_missing_profile_fails_with_actionable_route_error(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"operator_note": "route not configured"},
    )
    hal = SimpleNamespace(
        drivers={"baseStation": RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})}
    )

    with pytest.raises(ValueError, match="CMW500.*Route.*七个字段"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)


def test_uxm_freezes_not_applicable_without_reading_cmw_profile(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="UXM 5G E7515B",
        params=None,
    )
    hal = SimpleNamespace(
        drivers={"baseStation": RealUxmDriver("uxm", {"ip_address": "192.0.2.10"})}
    )

    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)

    assert frozen["resolution"] == {
        "schema_version": 1,
        "adapter": "uxm",
        "status": "not_applicable",
        "execution_mode": "real",
        "profile": None,
    }


def test_binding_and_selected_model_mismatch_fails_before_hardware_io(db):
    category, model, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    other = InstrumentModel(
        category_id=category.id,
        vendor="Keysight",
        model="UXM 5G E7515B",
        capabilities={},
    )
    db.add(other)
    db.flush()
    category.selected_model_id = other.id
    db.commit()
    hal = SimpleNamespace(
        drivers={"baseStation": RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})}
    )

    with pytest.raises(ValueError, match="binding.*selected_model_id"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)


def test_lab_binding_endpoint_must_match_the_selected_connection(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    bindings = list(lab.instrument_bindings)
    bindings[0] = {**bindings[0], "connection_endpoint": "192.0.2.99"}
    lab.instrument_bindings = bindings
    db.commit()
    hal = SimpleNamespace(
        drivers={"baseStation": RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})}
    )

    with pytest.raises(ValueError, match="connection endpoint"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)


def test_loaded_real_driver_must_match_registry_class(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    hal = SimpleNamespace(
        drivers={"baseStation": RealUxmDriver("uxm", {"ip_address": "192.0.2.11"})}
    )

    with pytest.raises(ValueError, match="loaded driver"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)


def test_lock_time_validator_rejects_driver_reload_without_io(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    hal = SimpleNamespace(
        drivers={"baseStation": RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})}
    )
    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)
    hal.drivers["baseStation"] = RealUxmDriver(
        "uxm", {"ip_address": "192.0.2.11"}
    )

    assert "loaded driver" in validate_frozen_base_station_before_remote(hal, frozen)


def test_lock_time_validator_rejects_same_driver_class_with_different_endpoint(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    hal = SimpleNamespace(
        drivers={"baseStation": RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})}
    )
    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)
    hal.drivers["baseStation"] = RealCmw500Driver(
        "cmw", {"ip_address": "192.0.2.99"}
    )

    assert "connection identity" in validate_frozen_base_station_before_remote(
        hal, frozen
    )


def test_freeze_rejects_stale_loaded_driver_after_locked_connection_endpoint_changes(db):
    _, _, connection, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    hal = SimpleNamespace(
        drivers={"baseStation": RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})}
    )
    connection.endpoint = "192.0.2.99"
    bindings = list(lab.instrument_bindings)
    bindings[0] = {**bindings[0], "connection_endpoint": "192.0.2.99"}
    lab.instrument_bindings = bindings
    db.commit()

    with pytest.raises(ValueError, match="connection identity"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)

    assert "base_station_adapter_profile_freeze" not in execution.config


def test_authoritative_mock_keeps_configured_cmw_profile_but_marks_simulated(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    hal = SimpleNamespace(
        drivers={"baseStation": MockBaseStation("mock", {})}
    )

    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)

    assert frozen["resolution"]["adapter"] == "cmw500"
    assert frozen["resolution"]["status"] == "configured"
    assert frozen["resolution"]["execution_mode"] == "simulated"
    assert frozen["resolution"]["profile"] == _profile()


def test_authoritative_mock_without_selected_model_is_diagnostic_unbound(db):
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode="mock",
    )
    db.add(category)
    db.flush()
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint=None,
        connection_params=None,
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[{
            "category_id": str(category.id),
            "instrument_model_id": None,
            "connection_endpoint": None,
            "driver_mode": "mock",
            "role": "baseStation",
        }],
    )
    execution = TestExecution(status="pending", config={})
    db.add_all([connection, lab, execution])
    db.commit()
    hal = SimpleNamespace(
        drivers={"baseStation": MockBaseStation("mock", {})}
    )

    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)

    assert frozen["resolution"] == {
        "schema_version": 1,
        "adapter": None,
        "status": "diagnostic_unbound",
        "execution_mode": "simulated",
        "profile": None,
    }
    assert frozen["instrument_model_id"] is None


def test_non_authoritative_fake_driver_is_rejected(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    fake = SimpleNamespace(adapter_id="cmw500")
    hal = SimpleNamespace(drivers={"baseStation": fake})

    with pytest.raises(ValueError, match="loaded driver"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)


def test_connection_update_defers_adapter_profile_validation_to_selected_manifest(db):
    update = FEConnectionUpdate(base_station_adapter_profile=_profile())
    assert update.base_station_adapter_profile == _profile()

    invalid = _profile()
    invalid["lte_2x2_internal_route"].pop("tx2_converter")
    request = FEConnectionUpdate(base_station_adapter_profile=invalid)
    _configured_execution(db, model_name="CMW500", params={})
    with pytest.raises(Exception) as exc_info:
        update_instrument_category(
            "baseStation",
            UpdateInstrumentCategoryRequest(connection=request),
            db,
        )
    assert getattr(exc_info.value, "status_code", None) == 422


def test_uxm_manifest_rejects_cmw_profile_and_smuggled_profile_json(db):
    _configured_execution(db, model_name="UXM 5G E7515B", params={})

    for connection in (
        FEConnectionUpdate(base_station_adapter_profile=_profile()),
        FEConnectionUpdate(
            connection_params={"base_station_adapter_profile": _profile()}
        ),
    ):
        with pytest.raises(Exception) as exc_info:
            update_instrument_category(
                "baseStation",
                UpdateInstrumentCategoryRequest(connection=connection),
                db,
            )
        assert getattr(exc_info.value, "status_code", None) == 422


def test_connection_update_persists_typed_profile_without_erasing_other_params(db):
    _, _, connection, _, _ = _configured_execution(
        db,
        model_name="CMW500",
        params={"operator_note": {"keep": True}},
    )

    update_instrument_category(
        "baseStation",
        UpdateInstrumentCategoryRequest(
            connection=FEConnectionUpdate(
                base_station_adapter_profile=_profile(),
            )
        ),
        db,
    )

    db.refresh(connection)
    assert connection.connection_params == {
        "operator_note": {"keep": True},
        "base_station_adapter_profile": _profile(),
    }


def test_old_execution_with_progress_cannot_backfill_current_profile(db):
    _, _, _, lab, execution = _configured_execution(
        db,
        model_name="CMW500",
        params={"base_station_adapter_profile": _profile()},
    )
    execution.measurements = {"phases": {"measure": {"status": "success"}}}
    db.commit()
    test_case = SimpleNamespace(lab_profile_id=lab.id)
    hal = SimpleNamespace(
        drivers={"baseStation": RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})}
    )

    with pytest.raises(ValueError, match="cannot be backfilled"):
        freeze_execution_base_station_adapter_profile(
            db, hal, execution, test_case
        )
