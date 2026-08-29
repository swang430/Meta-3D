from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.base_station import MockBaseStation
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.services.base_station_binding import resolve_base_station_binding


def _cmw_profile(tx2_connector: str = "RF2C") -> dict[str, object]:
    return {
        "schema_version": 1,
        "adapter": "cmw500",
        "lte_2x2_internal_route": {
            "pcc_bb_board": "BB1",
            "rx_connector": "RF1C",
            "rx_converter": "RX1",
            "tx1_connector": "RF1C",
            "tx1_converter": "TX1",
            "tx2_connector": tx2_connector,
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


def _configured(
    db,
    *,
    model_name: str,
    driver_mode: str = "real",
    endpoint: str = "192.0.2.10",
    profile: dict[str, object] | None = None,
):
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode=driver_mode,
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
    params = (
        {"base_station_adapter_profile": profile or _cmw_profile()}
        if model_name == "CMW500"
        else None
    )
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint=endpoint,
        connection_params=params,
        cmw500_lte_2x2_formal_enabled=model_name == "CMW500",
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": endpoint,
                "driver_mode": driver_mode,
                "role": "baseStation",
            }
        ],
    )
    db.add_all([connection, lab])
    db.commit()
    return category, model, connection, lab


def _real_driver(model_name: str, endpoint: str = "192.0.2.10"):
    if model_name == "CMW500":
        return RealCmw500Driver("cmw", {"ip_address": endpoint})
    return RealUxmDriver("uxm", {"ip_address": endpoint})


@pytest.mark.parametrize(
    ("model_name", "adapter", "profile_status"),
    [
        ("CMW500", "cmw500", "configured"),
        ("UXM 5G E7515B", "uxm", "not_applicable"),
    ],
)
def test_real_bindings_resolve_one_common_immutable_shape_without_io(
    db, model_name, adapter, profile_status, monkeypatch
):
    _, model, connection, lab = _configured(db, model_name=model_name)
    driver = _real_driver(model_name)
    monkeypatch.setattr(
        driver,
        "connect",
        lambda: pytest.fail("resolver must not connect or issue instrument I/O"),
    )

    resolved = resolve_base_station_binding(
        db,
        SimpleNamespace(drivers={"baseStation": driver}),
        lab,
    )

    assert resolved.status == profile_status
    assert resolved.execution_mode == "real"
    assert resolved.manifest.adapter_id == adapter
    assert resolved.instrument_model_id == str(model.id)
    assert resolved.instrument_connection_id == str(connection.id)
    assert resolved.expected_transport is not None
    assert resolved.expected_transport.host == "192.0.2.10"
    assert resolved.binding_digest
    assert resolved.stable_projection()["binding_digest"] == resolved.binding_digest
    with pytest.raises(Exception):
        resolved.status = "changed"
    with pytest.raises(Exception):
        resolved.expected_transport.host = "192.0.2.99"
    if resolved.profile is not None:
        with pytest.raises(Exception):
            resolved.profile.lte_2x2_internal_route.tx2_connector = "RF3C"


def test_configured_authoritative_mock_keeps_manifest_and_profile_but_is_simulated(db):
    _, _, _, lab = _configured(db, model_name="CMW500", driver_mode="mock")
    mock = MockBaseStation("mock", {"model": "CMW500"})

    resolved = resolve_base_station_binding(
        db,
        SimpleNamespace(drivers={"baseStation": mock}),
        lab,
    )

    assert resolved.manifest.adapter_id == "cmw500"
    assert resolved.status == "configured"
    assert resolved.execution_mode == "simulated"
    assert resolved.profile is not None
    assert resolved.profile.model_dump(mode="json") == _cmw_profile()
    assert resolved.runtime_driver.simulated is True


def test_only_authoritative_mock_may_resolve_diagnostic_unbound(db):
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode="mock",
    )
    db.add(category)
    db.flush()
    connection = InstrumentConnection(category_id=category.id, endpoint=None)
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": None,
                "connection_endpoint": None,
                "driver_mode": "mock",
                "role": "baseStation",
            }
        ],
    )
    db.add_all([connection, lab])
    db.commit()

    resolved = resolve_base_station_binding(
        db,
        SimpleNamespace(drivers={"baseStation": MockBaseStation("mock", {})}),
        lab,
    )

    assert resolved.status == "diagnostic_unbound"
    assert resolved.manifest is None
    assert resolved.profile is None
    assert resolved.instrument_model_id is None
    assert resolved.instrument_connection_id is None
    assert resolved.expected_transport is None

    with pytest.raises(ValueError, match="authoritative mock"):
        resolve_base_station_binding(
            db,
            SimpleNamespace(drivers={"baseStation": SimpleNamespace()}),
            lab,
        )

    category.driver_mode = "real"
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["driver_mode"] = "real"
    lab.instrument_bindings = bindings
    db.commit()
    with pytest.raises(ValueError, match="loaded driver mode"):
        resolve_base_station_binding(
            db,
            SimpleNamespace(
                drivers={"baseStation": MockBaseStation("mock", {})}
            ),
            lab,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("binding_model_missing", "both be configured"),
        ("selected_model_missing", "both be configured"),
        ("binding_model_mismatch", "selected_model_id"),
        ("binding_missing", "exactly one"),
        ("binding_duplicate", "exactly one"),
        ("binding_endpoint", "endpoint"),
        ("profile_missing", "required adapter profile is missing"),
        ("profile_unexpected", "not applicable"),
        ("driver_missing", "loaded driver"),
        ("driver_class", "registry class"),
        ("driver_endpoint", "transport"),
    ],
)
def test_resolver_fails_loud_for_every_split_truth(db, mutation, message):
    category, model, connection, lab = _configured(db, model_name="CMW500")
    driver = _real_driver("CMW500")
    if mutation == "binding_model_missing":
        bindings = deepcopy(lab.instrument_bindings)
        bindings[0]["instrument_model_id"] = None
        lab.instrument_bindings = bindings
    elif mutation == "selected_model_missing":
        category.selected_model_id = None
    elif mutation == "binding_model_mismatch":
        other = InstrumentModel(
            category_id=category.id,
            vendor="Keysight",
            model="UXM 5G E7515B",
            capabilities={},
        )
        db.add(other)
        db.flush()
        bindings = deepcopy(lab.instrument_bindings)
        bindings[0]["instrument_model_id"] = str(other.id)
        lab.instrument_bindings = bindings
    elif mutation == "binding_missing":
        lab.instrument_bindings = []
    elif mutation == "binding_duplicate":
        lab.instrument_bindings = [
            *lab.instrument_bindings,
            deepcopy(lab.instrument_bindings[0]),
        ]
    elif mutation == "binding_endpoint":
        bindings = deepcopy(lab.instrument_bindings)
        bindings[0]["connection_endpoint"] = "192.0.2.99"
        lab.instrument_bindings = bindings
    elif mutation == "profile_missing":
        connection.connection_params = None
    elif mutation == "profile_unexpected":
        model.model = "UXM 5G E7515B"
        connection.connection_params = {"base_station_adapter_profile": _cmw_profile()}
        driver = _real_driver("UXM 5G E7515B")
    elif mutation == "driver_missing":
        driver = None
    elif mutation == "driver_class":
        driver = _real_driver("UXM 5G E7515B")
    elif mutation == "driver_endpoint":
        driver = _real_driver("CMW500", "192.0.2.99")
    db.commit()

    with pytest.raises(ValueError, match=message):
        resolve_base_station_binding(
            db,
            SimpleNamespace(drivers={} if driver is None else {"baseStation": driver}),
            lab,
        )


def test_binding_digest_is_stable_and_changes_for_each_persisted_truth(db):
    category, model, connection, lab = _configured(db, model_name="CMW500")
    hal = SimpleNamespace(drivers={"baseStation": _real_driver("CMW500")})

    first = resolve_base_station_binding(db, hal, lab)
    second = resolve_base_station_binding(db, hal, lab)
    assert first.binding_digest == second.binding_digest

    original = first.binding_digest
    connection.cmw500_lte_2x2_formal_enabled = False
    db.commit()
    approval_changed = resolve_base_station_binding(db, hal, lab)
    # P2-45: the retired CMW approval is not binding truth and must not churn
    # the binding digest. Formal qualification freezes site certification
    # separately from the P2-44 binding digest.
    assert approval_changed.binding_digest == original

    connection.connection_params = {
        "base_station_adapter_profile": _cmw_profile("RF3C")
    }
    db.commit()
    profile_changed = resolve_base_station_binding(db, hal, lab)
    assert profile_changed.binding_digest != approval_changed.binding_digest

    connection.endpoint = "192.0.2.20"
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["connection_endpoint"] = "192.0.2.20"
    lab.instrument_bindings = bindings
    hal.drivers["baseStation"] = _real_driver("CMW500", "192.0.2.20")
    db.commit()
    endpoint_changed = resolve_base_station_binding(db, hal, lab)
    assert endpoint_changed.binding_digest != profile_changed.binding_digest

    other = InstrumentModel(
        category_id=category.id,
        vendor="Keysight",
        model="UXM 5G E7515B",
        capabilities={},
    )
    db.add(other)
    db.flush()
    category.selected_model_id = other.id
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["instrument_model_id"] = str(other.id)
    lab.instrument_bindings = bindings
    connection.connection_params = None
    hal.drivers["baseStation"] = _real_driver("UXM 5G E7515B", "192.0.2.20")
    db.commit()
    model_changed = resolve_base_station_binding(db, hal, lab)
    assert model_changed.binding_digest != endpoint_changed.binding_digest


def test_runtime_driver_identity_is_auditable_but_does_not_pollute_digest(db):
    _, _, _, lab = _configured(db, model_name="CMW500", driver_mode="mock")
    first = resolve_base_station_binding(
        db,
        SimpleNamespace(
            drivers={"baseStation": MockBaseStation("mock-one", {"model": "CMW500"})}
        ),
        lab,
    )
    second = resolve_base_station_binding(
        db,
        SimpleNamespace(
            drivers={"baseStation": MockBaseStation("mock-two", {"model": "CMW500"})}
        ),
        lab,
    )

    assert first.binding_digest == second.binding_digest
    assert first.runtime_driver != second.runtime_driver


@pytest.mark.parametrize(
    ("category_mode", "stale_binding_mode"),
    [
        ("real", "mock"),
        ("real", "auto"),
        ("mock", "real"),
        ("mock", "auto"),
        ("auto", "real"),
        ("auto", "mock"),
    ],
)
def test_resolver_rejects_every_stale_lab_profile_driver_mode(
    db,
    category_mode,
    stale_binding_mode,
):
    _, _, _, lab = _configured(
        db,
        model_name="CMW500",
        driver_mode=category_mode,
    )
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["driver_mode"] = stale_binding_mode
    lab.instrument_bindings = bindings
    db.commit()
    driver = (
        MockBaseStation("mock", {"model": "CMW500"})
        if category_mode == "mock"
        else _real_driver("CMW500")
    )

    with pytest.raises(ValueError, match="driver mode"):
        resolve_base_station_binding(
            db,
            SimpleNamespace(drivers={"baseStation": driver}),
            lab,
        )


@pytest.mark.parametrize("category_mode", ["real", "mock"])
def test_resolver_rejects_loaded_driver_that_violates_explicit_mode(
    db,
    category_mode,
):
    _, _, _, lab = _configured(
        db,
        model_name="CMW500",
        driver_mode=category_mode,
    )
    driver = (
        MockBaseStation("mock", {"model": "CMW500"})
        if category_mode == "real"
        else _real_driver("CMW500")
    )

    with pytest.raises(ValueError, match="loaded driver mode"):
        resolve_base_station_binding(
            db,
            SimpleNamespace(drivers={"baseStation": driver}),
            lab,
        )
