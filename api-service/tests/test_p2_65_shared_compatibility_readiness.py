"""P2-65: preview/readiness/freeze share one compatibility truth."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.base_station_compatibility import (
    BaseStationCompatibilityVerdict,
    build_compatibility_payload,
    build_measure_execution_requirements_from_configuration,
    build_frozen_compatibility_payload,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.services.base_station_adapter_profile import (
    freeze_base_station_adapter_profile,
)
from app.services.base_station_compatibility import (
    build_base_station_compatibility_preview,
)
from tests.base_station_mock_factory import registered_mock_base_station


def _cmw_profile() -> dict[str, object]:
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


def _saved_case_and_binding(
    db,
    *,
    model_name: str,
    requested_rat: str,
    driver_mode: str = "real",
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
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint="192.0.2.10",
        connection_params=(
            {"base_station_adapter_profile": _cmw_profile()}
            if model_name == "CMW500"
            else None
        ),
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": "192.0.2.10",
                "driver_mode": driver_mode,
                "role": "baseStation",
            }
        ],
    )
    db.add_all([connection, lab])
    db.flush()
    case = TestCase(
        name=f"case-{uuid4()}",
        test_type="MIMO_OTA",
        configuration={
            "component_carriers": [{"radio_technology": requested_rat}]
        },
        created_by="test",
        lab_profile_id=lab.id,
    )
    db.add(case)
    db.commit()
    if driver_mode == "mock":
        driver = registered_mock_base_station("mock", {"model": model_name})
    else:
        driver = (
            RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
            if model_name == "CMW500"
            else RealUxmDriver("uxm", {"ip_address": "192.0.2.10"})
        )
    return case, lab, SimpleNamespace(drivers={"baseStation": driver})


@pytest.mark.parametrize(
    ("configuration", "requested_rat"),
    [
        ({}, "nr5g"),
        ({"component_carriers": []}, "nr5g"),
        ({"component_carriers": [{}]}, "nr5g"),
        (
            {"component_carriers": [{"radio_technology": "lte"}]},
            "lte",
        ),
    ],
)
def test_saved_configuration_projection_matches_freeze_defaults(
    configuration, requested_rat
):
    requirements = build_measure_execution_requirements_from_configuration(
        configuration
    )

    assert requirements.requested_rat == requested_rat
    assert requirements.digest


def test_saved_configuration_projection_rejects_invalid_rat_without_normalizing():
    with pytest.raises(ValueError, match="not a valid RAT"):
        build_measure_execution_requirements_from_configuration(
            {"component_carriers": [{"radio_technology": "LTE"}]}
        )


@pytest.mark.parametrize(
    ("configuration", "manifest", "status"),
    [
        ({}, RealUxmDriver.adapter_manifest, "compatible"),
        (
            {"component_carriers": [{"radio_technology": "lte"}]},
            RealUxmDriver.adapter_manifest,
            "incompatible",
        ),
        (
            {"component_carriers": [{"radio_technology": "lte"}]},
            RealCmw500Driver.adapter_manifest,
            "compatible",
        ),
        ({}, RealCmw500Driver.adapter_manifest, "incompatible"),
        ({}, None, "no_adapter"),
    ],
)
def test_common_payload_is_the_exact_freeze_projection(
    configuration, manifest, status
):
    requirements = build_measure_execution_requirements_from_configuration(
        configuration
    )

    payload = build_compatibility_payload(requirements, manifest)

    assert payload["verdict"]["status"] == status
    assert payload["verdict"]["requirements_digest"] == requirements.digest
    assert payload == build_frozen_compatibility_payload(
        requirements,
        # The common builder is authoritative; reconstructing from its verdict
        # proves the legacy freeze wrapper serializes the identical payload.
        BaseStationCompatibilityVerdict.model_validate(payload["verdict"]),
    )


@pytest.mark.parametrize(
    ("model_name", "requested_rat", "status"),
    [
        ("UXM 5G E7515B", "nr5g", "compatible"),
        ("UXM 5G E7515B", "lte", "incompatible"),
        ("CMW500", "lte", "compatible"),
        ("CMW500", "nr5g", "incompatible"),
    ],
)
def test_saved_test_case_preview_uses_resolver_and_common_projection_without_io(
    db, model_name, requested_rat, status, monkeypatch
):
    case, lab, hal = _saved_case_and_binding(
        db,
        model_name=model_name,
        requested_rat=requested_rat,
    )
    driver = hal.drivers["baseStation"]
    monkeypatch.setattr(
        driver,
        "connect",
        lambda: pytest.fail("compatibility preview must not perform instrument I/O"),
    )

    preview = build_base_station_compatibility_preview(
        db,
        hal,
        lab,
        test_case_id=case.id,
    )

    assert preview.status == status
    assert preview.compatible is (status == "compatible")
    assert preview.test_case_id == str(case.id)
    assert preview.lab_profile_id == str(lab.id)
    assert preview.binding_digest
    assert preview.requirements is not None
    assert preview.requirements.requested_rat == requested_rat
    assert preview.verdict is not None
    assert preview.verdict.status == status
    assert preview.requirements.digest == preview.verdict.requirements_digest


def test_preview_without_saved_test_case_context_is_explicitly_not_evaluated(db):
    _, lab, hal = _saved_case_and_binding(
        db,
        model_name="UXM 5G E7515B",
        requested_rat="nr5g",
    )

    preview = build_base_station_compatibility_preview(
        db,
        hal,
        lab,
        test_case_id=None,
    )

    assert preview.status == "not_evaluated"
    assert preview.compatible is None
    assert preview.binding_digest is None
    assert preview.requirements is None
    assert preview.verdict is None
    assert preview.reasons


def test_preview_missing_test_case_is_explicitly_invalid(db):
    _, lab, hal = _saved_case_and_binding(
        db,
        model_name="UXM 5G E7515B",
        requested_rat="nr5g",
    )

    preview = build_base_station_compatibility_preview(
        db,
        hal,
        lab,
        test_case_id=uuid4(),
    )

    assert preview.status == "invalid"
    assert preview.compatible is False
    assert preview.binding_digest is None
    assert preview.verdict is None
    assert any("TestCase" in reason for reason in preview.reasons)


def test_compatible_registered_mock_is_explicitly_simulated(db):
    case, lab, hal = _saved_case_and_binding(
        db,
        model_name="UXM 5G E7515B",
        requested_rat="nr5g",
        driver_mode="mock",
    )

    preview = build_base_station_compatibility_preview(
        db,
        hal,
        lab,
        test_case_id=case.id,
    )

    assert preview.status == "compatible"
    assert preview.compatible is True
    assert preview.execution_mode == "simulated"


def test_authoritative_unbound_mock_is_explicitly_no_adapter(db):
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
    db.flush()
    case = TestCase(
        name=f"case-{uuid4()}",
        test_type="MIMO_OTA",
        configuration={"component_carriers": [{"radio_technology": "nr5g"}]},
        created_by="test",
        lab_profile_id=lab.id,
    )
    db.add(case)
    db.commit()
    hal = SimpleNamespace(
        drivers={
            "baseStation": registered_mock_base_station(
                "mock",
                {"model": "UXM 5G E7515B"},
            )
        }
    )

    preview = build_base_station_compatibility_preview(
        db,
        hal,
        lab,
        test_case_id=case.id,
    )

    assert preview.status == "no_adapter"
    assert preview.compatible is True
    assert preview.execution_mode == "simulated"
    assert preview.binding_digest
    assert preview.verdict is not None
    assert preview.verdict.manifest_digest is None


@pytest.mark.parametrize(
    ("model_name", "requested_rat"),
    [
        ("UXM 5G E7515B", "nr5g"),
        ("CMW500", "lte"),
    ],
)
def test_preview_and_execution_freeze_persist_the_identical_compatibility_payload(
    db, model_name, requested_rat
):
    case, lab, hal = _saved_case_and_binding(
        db,
        model_name=model_name,
        requested_rat=requested_rat,
    )
    preview = build_base_station_compatibility_preview(
        db,
        hal,
        lab,
        test_case_id=case.id,
    )
    execution = TestExecution(
        test_case_id=case.id,
        status="pending",
        config={},
        executed_by="test",
    )
    db.add(execution)
    db.flush()

    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)

    assert frozen["binding_digest"] == preview.binding_digest
    assert frozen["compatibility"] == {
        "schema_version": 1,
        "requirements": preview.requirements.model_dump(mode="json"),
        "verdict": preview.verdict.model_dump(mode="json"),
    }


def test_preview_sync_and_readiness_accept_saved_test_case_context():
    from app.api.instrument import HALReadinessResponse, get_hal_readiness
    from app.api.lab_profile import (
        InstrumentBindingSyncResponse,
        preview_base_station_binding,
        sync_current_instrument_binding,
    )
    from app.schemas.base_station_binding import BaseStationBindingPreviewResponse

    assert "test_case_id" in inspect.signature(preview_base_station_binding).parameters
    assert "test_case_id" in inspect.signature(sync_current_instrument_binding).parameters
    assert "test_case_id" in inspect.signature(get_hal_readiness).parameters
    assert "testcase_compatibility" in BaseStationBindingPreviewResponse.model_fields
    assert "testcase_compatibility" in InstrumentBindingSyncResponse.model_fields
    assert "base_station_testcase_compatibility" in HALReadinessResponse.model_fields
