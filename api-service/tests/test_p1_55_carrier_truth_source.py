"""P1-55: PCell is the only MIMO OTA operating-point truth."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.api.test_plan import create_test_case as create_test_case_endpoint
from app.api.test_plan import update_test_case as update_test_case_endpoint
from app.models.test_plan import TestCase
from app.schemas.mimo_ota.config import ComponentCarrierConfig, MIMOOTAConfiguration
from app.schemas.test_plan import TestCaseCreate, TestCaseUpdate
from app.services.test_plan_service import TestCaseService


PCELL = {
    "frequency_hz": 3_549_990_000.0,
    "bandwidth_mhz": 40.0,
    "subcarrier_spacing_khz": 30,
    "role": "pcell",
}


@pytest.mark.parametrize(
    ("field", "conflicting_value"),
    [
        ("frequency_hz", 3_600_000_000.0),
        ("bandwidth_mhz", 100.0),
        ("subcarrier_spacing_khz", 15),
    ],
)
def test_explicit_top_level_carrier_conflict_is_rejected(
    field: str,
    conflicting_value: float,
):
    payload = {
        field: conflicting_value,
        "component_carriers": [deepcopy(PCELL)],
    }

    with pytest.raises(ValidationError, match=rf"{field}.*component_carriers\[0\]"):
        MIMOOTAConfiguration.model_validate(payload)


def test_missing_legacy_mirrors_are_filled_from_pcell():
    config = MIMOOTAConfiguration.model_validate(
        {"component_carriers": [deepcopy(PCELL)]}
    )

    assert config.frequency_hz == PCELL["frequency_hz"]
    assert config.bandwidth_mhz == PCELL["bandwidth_mhz"]
    assert config.subcarrier_spacing_khz == PCELL["subcarrier_spacing_khz"]
    assert config.primary_carrier.frequency_hz == PCELL["frequency_hz"]


def test_internal_component_carrier_model_cannot_bypass_conflict_gate():
    with pytest.raises(ValidationError, match=r"frequency_hz.*component_carriers\[0\]"):
        MIMOOTAConfiguration.model_validate(
            {
                "frequency_hz": 3_600_000_000.0,
                "component_carriers": (ComponentCarrierConfig(**PCELL),),
            }
        )


def test_legacy_top_level_only_builds_one_pcell():
    config = MIMOOTAConfiguration.model_validate(
        {
            "frequency_hz": 3_700_000_000.0,
            "bandwidth_mhz": 80.0,
            "subcarrier_spacing_khz": 60,
        }
    )

    assert len(config.component_carriers or []) == 1
    assert config.primary_carrier.frequency_hz == 3_700_000_000.0
    assert config.primary_carrier.bandwidth_mhz == 80.0
    assert config.primary_carrier.subcarrier_spacing_khz == 60


def test_pcell_normalization_does_not_change_scell_values():
    scell = {
        "frequency_hz": 3_700_000_000.0,
        "bandwidth_mhz": 80.0,
        "subcarrier_spacing_khz": 60,
        "role": "pcell",
    }
    config = MIMOOTAConfiguration.model_validate(
        {
            **{key: PCELL[key] for key in (
                "frequency_hz", "bandwidth_mhz", "subcarrier_spacing_khz"
            )},
            "component_carriers": [deepcopy(PCELL), deepcopy(scell)],
        }
    )

    assert config.primary_carrier.role == "pcell"
    assert config.component_carriers[1].role == "scell"
    assert config.component_carriers[1].frequency_hz == scell["frequency_hz"]
    assert config.component_carriers[1].bandwidth_mhz == scell["bandwidth_mhz"]


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def _db_schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _create_case(db, *, test_type: str, configuration: dict) -> TestCase:
    return TestCaseService().create_test_case(
        db,
        name=f"{test_type}-truth",
        test_type=test_type,
        configuration=configuration,
        created_by="p1-55-test",
    )


def test_service_rejects_conflicting_mimo_create_before_commit(db):
    conflict = {
        "frequency_hz": 3_600_000_000.0,
        "component_carriers": [deepcopy(PCELL)],
    }

    with pytest.raises((ValueError, ValidationError), match="frequency_hz.*component_carriers"):
        _create_case(db, test_type="MIMO_OTA", configuration=conflict)

    assert db.query(TestCase).count() == 0


def test_service_persists_missing_mirrors_from_pcell(db):
    row = _create_case(
        db,
        test_type="MIMO_OTA",
        configuration={"component_carriers": [deepcopy(PCELL)]},
    )

    assert row.configuration["frequency_hz"] == PCELL["frequency_hz"]
    assert row.configuration["bandwidth_mhz"] == PCELL["bandwidth_mhz"]
    assert row.configuration["subcarrier_spacing_khz"] == PCELL["subcarrier_spacing_khz"]


def test_service_rejects_conflicting_mimo_update_without_mutating_row(db):
    row = _create_case(
        db,
        test_type="MIMO_OTA",
        configuration={"component_carriers": [deepcopy(PCELL)]},
    )
    original = deepcopy(row.configuration)

    with pytest.raises((ValueError, ValidationError), match="bandwidth_mhz.*component_carriers"):
        TestCaseService().update_test_case(
            db,
            row.id,
            configuration={
                "bandwidth_mhz": 100.0,
                "component_carriers": [deepcopy(PCELL)],
            },
        )

    db.refresh(row)
    assert row.configuration == original


def test_service_cannot_retype_a_conflicting_free_form_case_to_mimo(db):
    conflict = {
        "frequency_hz": 3_600_000_000.0,
        "component_carriers": [deepcopy(PCELL)],
    }
    row = _create_case(db, test_type="Custom", configuration=conflict)

    with pytest.raises(
        (ValueError, ValidationError),
        match="frequency_hz.*component_carriers",
    ):
        TestCaseService().update_test_case(db, row.id, test_type="MIMO_OTA")

    db.refresh(row)
    assert row.test_type == "Custom"
    assert row.configuration == conflict


def test_non_mimo_configuration_remains_free_form(db):
    payload = {
        "frequency_hz": 3_600_000_000.0,
        "component_carriers": [deepcopy(PCELL)],
        "custom": "kept",
    }
    row = _create_case(db, test_type="Custom", configuration=payload)

    assert row.configuration == payload


def test_create_api_maps_carrier_conflict_to_actionable_422(db):
    request = TestCaseCreate(
        name="conflicting-create",
        test_type="MIMO_OTA",
        configuration={
            "frequency_hz": 3_600_000_000.0,
            "component_carriers": [deepcopy(PCELL)],
        },
        created_by="p1-55-test",
    )

    with pytest.raises(HTTPException) as raised:
        create_test_case_endpoint(request=request, db=db)

    assert raised.value.status_code == 422
    assert "frequency_hz" in str(raised.value.detail)
    assert "component_carriers[0]" in str(raised.value.detail)


def test_update_api_maps_carrier_conflict_to_actionable_422(db):
    row = _create_case(
        db,
        test_type="MIMO_OTA",
        configuration={"component_carriers": [deepcopy(PCELL)]},
    )
    request = TestCaseUpdate(
        configuration={
            "bandwidth_mhz": 100.0,
            "component_carriers": [deepcopy(PCELL)],
        }
    )

    with pytest.raises(HTTPException) as raised:
        update_test_case_endpoint(test_case_id=row.id, request=request, db=db)

    assert raised.value.status_code == 422
    assert "bandwidth_mhz" in str(raised.value.detail)
    assert "component_carriers[0]" in str(raised.value.detail)
