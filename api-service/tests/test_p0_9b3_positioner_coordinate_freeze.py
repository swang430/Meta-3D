"""P0-9B-3：Aerotech 坐标合同必须绑定当前 execution。"""

from copy import deepcopy

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.aerotech_positioner import RealAerotechDriver
from app.hal.positioner import MockPositioner
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services.positioner_coordinate_profile import (
    FREEZE_CONFIG_KEY,
    _canonical_digest,
    freeze_execution_positioner_coordinate_profile,
    freeze_positioner_coordinate_profile,
    validate_frozen_positioner_before_motion,
)


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


def _motion_params(**overrides) -> dict[str, object]:
    params: dict[str, object] = {
        "motion_truth_units_verified": True,
        "motion_truth_user_units": "degree",
        "motion_truth_min_deg": 0.0,
        "motion_truth_max_deg": 360.0,
        "motion_truth_xf_speed": 5.0,
        "motion_truth_coordinate_offset_verified": True,
        "motion_truth_coordinate_offset_deg": 90.0,
        "motion_truth_coordinate_offset_verification_source": (
            "docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md"
            "#44-aerotech-转台"
        ),
        "motion_truth_coordinate_offset_verified_at": (
            "2026-08-27T16:59:50+08:00"
        ),
        "position_tolerance_deg": 0.5,
        "azimuth_axis": "X",
        "elevation_axis": "Y",
    }
    params.update(overrides)
    return params


def _configured_execution(db, *, params=None, driver_mode="real"):
    category = InstrumentCategory(
        category_key="positioner",
        category_name="Positioner",
        driver_mode=driver_mode,
    )
    db.add(category)
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="Aerotech",
        model="A3200",
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint="192.0.2.16:8000",
        controller_ip="192.0.2.16",
        port=8000,
        protocol="TCP",
        connection_params=params,
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[{
            "category_id": str(category.id),
            "instrument_model_id": str(model.id),
            "connection_endpoint": "192.0.2.16:8000",
            "driver_mode": driver_mode,
            "role": "positioner",
        }],
    )
    execution = TestExecution(status="pending", config={})
    db.add_all([connection, lab, execution])
    db.commit()
    return category, model, connection, lab, execution


def _real_driver(params=None):
    return RealAerotechDriver(
        "aerotech",
        {
            "ip": "192.0.2.16",
            "port": 8000,
            **(params or _motion_params()),
        },
    )


def test_real_aerotech_freezes_persisted_coordinate_contract_once(db):
    params = _motion_params()
    _, model, connection, lab, execution = _configured_execution(db, params=params)
    hal = SimpleNamespace(drivers={"positioner": _real_driver(params)})

    frozen = freeze_positioner_coordinate_profile(db, hal, execution, lab)

    assert frozen["resolution"] == {
        "schema_version": 1,
        "adapter": "aerotech",
        "status": "verified",
        "execution_mode": "real",
    }
    assert frozen["instrument_model_id"] == str(model.id)
    assert frozen["instrument_connection_id"] == str(connection.id)
    assert frozen["profile"]["user_units"] == "degree"
    assert frozen["profile"]["coordinate_offset_deg"] == 90.0
    assert frozen["profile"]["coordinate_offset_verified"] is True
    assert frozen["profile"]["coordinate_offset_verification_source"].endswith(
        "2026-08-27-lte-cmw500-onsite-summary.md#44-aerotech-转台"
    )
    assert frozen["profile"]["coordinate_offset_verified_at"] == (
        "2026-08-27T16:59:50+08:00"
    )
    assert frozen["profile"]["azimuth_axis"] == "X"
    assert frozen["source_reference"].endswith(
        "2026-08-27-lte-cmw500-onsite-summary.md#44-aerotech-转台"
    )
    assert frozen["frozen_at"]
    assert frozen["digest"]
    assert validate_frozen_positioner_before_motion(hal, frozen) is None

    connection.connection_params = _motion_params(
        motion_truth_coordinate_offset_deg=45.0
    )
    db.commit()
    assert freeze_positioner_coordinate_profile(db, hal, execution, lab) == frozen


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"motion_truth_units_verified": 1}, "units_verified"),
        ({"motion_truth_user_units": "count"}, "user_units"),
        ({"motion_truth_coordinate_offset_verified": "true"}, "offset_verified"),
        (
            {"motion_truth_coordinate_offset_verification_source": ""},
            "verification_source",
        ),
        (
            {"motion_truth_coordinate_offset_verified_at": "yesterday"},
            "verified_at",
        ),
        ({"motion_truth_coordinate_offset_deg": float("nan")}, "offset_deg"),
        ({"motion_truth_min_deg": 10.0, "motion_truth_max_deg": 10.0}, "range"),
        ({"motion_truth_xf_speed": 0.0}, "xf_speed"),
        ({"position_tolerance_deg": 1.5}, "tolerance"),
    ],
)
def test_real_aerotech_rejects_unverified_or_invalid_persisted_truth(
    db, overrides, message
):
    params = _motion_params(**overrides)
    _, _, _, lab, execution = _configured_execution(db, params=params)
    hal = SimpleNamespace(drivers={"positioner": _real_driver(params)})

    with pytest.raises(ValueError, match=message):
        freeze_positioner_coordinate_profile(db, hal, execution, lab)

    assert FREEZE_CONFIG_KEY not in execution.config


def test_freeze_rejects_binding_endpoint_and_loaded_driver_config_drift(db):
    params = _motion_params()
    _, _, _, lab, execution = _configured_execution(db, params=params)
    bindings = list(lab.instrument_bindings)
    bindings[0] = {**bindings[0], "connection_endpoint": "192.0.2.99:8000"}
    lab.instrument_bindings = bindings
    db.commit()

    hal = SimpleNamespace(drivers={"positioner": _real_driver(params)})
    with pytest.raises(ValueError, match="connection endpoint"):
        freeze_positioner_coordinate_profile(db, hal, execution, lab)

    bindings[0] = {**bindings[0], "connection_endpoint": "192.0.2.16:8000"}
    lab.instrument_bindings = bindings
    db.commit()
    hal.drivers["positioner"] = _real_driver(
        _motion_params(motion_truth_coordinate_offset_deg=45.0)
    )
    with pytest.raises(ValueError, match="loaded driver.*coordinate"):
        freeze_positioner_coordinate_profile(db, hal, execution, lab)


def test_lock_time_validator_rejects_offset_axis_endpoint_and_class_drift(db):
    params = _motion_params()
    _, _, _, lab, execution = _configured_execution(db, params=params)
    hal = SimpleNamespace(drivers={"positioner": _real_driver(params)})
    frozen = freeze_positioner_coordinate_profile(db, hal, execution, lab)

    cases = [
        _real_driver(_motion_params(motion_truth_coordinate_offset_deg=45.0)),
        _real_driver(_motion_params(azimuth_axis="A")),
        RealAerotechDriver(
            "other-endpoint",
            {"ip": "192.0.2.99", "port": 8000, **params},
        ),
        MockPositioner("mock", {}),
    ]
    for replacement in cases:
        hal.drivers["positioner"] = replacement
        assert validate_frozen_positioner_before_motion(hal, frozen) is not None


def test_lock_time_validator_rejects_mutated_frozen_payload_even_if_driver_matches(db):
    params = _motion_params()
    _, _, _, lab, execution = _configured_execution(db, params=params)
    hal = SimpleNamespace(drivers={"positioner": _real_driver(params)})
    frozen = freeze_positioner_coordinate_profile(db, hal, execution, lab)

    tampered = deepcopy(frozen)
    tampered["profile"]["coordinate_offset_deg"] = 45.0
    hal.drivers["positioner"] = _real_driver(
        _motion_params(motion_truth_coordinate_offset_deg=45.0)
    )

    assert "digest" in validate_frozen_positioner_before_motion(hal, tampered)


def test_old_execution_with_progress_cannot_backfill_current_coordinate(db):
    params = _motion_params()
    _, _, _, lab, execution = _configured_execution(db, params=params)
    execution.measurements = {"phases": {"measure": {"status": "success"}}}
    db.commit()
    test_case = SimpleNamespace(lab_profile_id=lab.id)
    hal = SimpleNamespace(drivers={"positioner": _real_driver(params)})

    with pytest.raises(ValueError, match="cannot be backfilled"):
        freeze_execution_positioner_coordinate_profile(
            db, hal, execution, test_case
        )


def test_authoritative_mock_is_diagnostic_and_never_verified(db):
    params = _motion_params()
    _, _, _, lab, execution = _configured_execution(
        db, params=params, driver_mode="mock"
    )
    hal = SimpleNamespace(drivers={"positioner": MockPositioner("mock", {})})

    frozen = freeze_positioner_coordinate_profile(db, hal, execution, lab)

    assert frozen["resolution"] == {
        "schema_version": 1,
        "adapter": "aerotech",
        "status": "diagnostic",
        "execution_mode": "simulated",
    }
    assert frozen["profile"] is None
    assert validate_frozen_positioner_before_motion(hal, frozen) is None


def test_authoritative_mock_without_catalog_binding_is_diagnostic_unbound(db):
    lab = LabProfile(name=f"lab-{uuid4()}", instrument_bindings=[])
    execution = TestExecution(status="pending", config={})
    db.add_all([lab, execution])
    db.commit()
    hal = SimpleNamespace(drivers={"positioner": MockPositioner("mock", {})})

    frozen = freeze_positioner_coordinate_profile(db, hal, execution, lab)

    assert frozen["resolution"] == {
        "schema_version": 1,
        "adapter": None,
        "status": "diagnostic_unbound",
        "execution_mode": "simulated",
    }
    assert frozen["profile"] is None
    assert frozen["instrument_model_id"] is None
    assert validate_frozen_positioner_before_motion(hal, frozen) is None


def test_authoritative_mock_with_unbound_catalog_model_is_diagnostic_unbound(db):
    category = InstrumentCategory(
        category_key="positioner",
        category_name="Positioner",
        driver_mode="mock",
    )
    db.add(category)
    db.flush()
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[{
            "category_id": str(category.id),
            "instrument_model_id": None,
            "connection_endpoint": None,
            "driver_mode": "mock",
            "role": "positioner",
        }],
    )
    execution = TestExecution(status="pending", config={})
    db.add_all([lab, execution])
    db.commit()
    hal = SimpleNamespace(drivers={"positioner": MockPositioner("mock", {})})

    frozen = freeze_positioner_coordinate_profile(db, hal, execution, lab)

    assert frozen["resolution"] == {
        "schema_version": 1,
        "adapter": None,
        "status": "diagnostic_unbound",
        "execution_mode": "simulated",
    }
    assert frozen["category_id"] == str(category.id)
    assert frozen["instrument_model_id"] is None
    assert validate_frozen_positioner_before_motion(hal, frozen) is None


def test_real_non_aerotech_resolution_remains_not_applicable():
    class _OtherRealPositioner:
        _connection_host = "192.0.2.17"
        _connection_resource = None
        port = 2000

    driver = _OtherRealPositioner()
    identity = {
        "schema_version": 1,
        "resolution": {
            "schema_version": 1,
            "adapter": None,
            "status": "not_applicable",
            "execution_mode": "real",
        },
        "expected_driver_module": type(driver).__module__,
        "expected_driver_name": type(driver).__name__,
        "expected_driver_connection": {
            "host": "192.0.2.17",
            "port": 2000,
            "resource": None,
        },
        "profile": None,
    }
    frozen = {**identity, "digest": _canonical_digest(identity)}

    assert validate_frozen_positioner_before_motion(
        SimpleNamespace(drivers={"positioner": driver}), frozen
    ) is None
