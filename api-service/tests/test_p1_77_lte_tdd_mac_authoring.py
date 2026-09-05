from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.base_station_compatibility import (
    build_measure_execution_requirements_from_configuration,
    evaluate_base_station_compatibility,
)
from app.hal.base_station_mac_profile import FrozenMacTestProfile
from app.hal.cmw500_base_station import RealCmw500Driver
from app.main import app
from app.models.test_plan import TestCase
from app.schemas.mimo_ota.config import (
    MIMOOTAConfiguration,
    canonicalize_mimo_ota_configuration_payload,
)


def _lte_tdd_configuration(**updates: object) -> dict:
    payload = {
        "component_carriers": [
            {
                "radio_technology": "lte",
                "frequency_hz": 2_565_000_000.0,
                "bandwidth_mhz": 20.0,
                "subcarrier_spacing_khz": None,
                "band": "B41",
                "duplex": "tdd",
                "lte_dl_earfcn": 40340,
                "lte_transmission_mode": "TM3",
                "role": "pcell",
            }
        ],
        "mimo_layers": 2,
        "stat_count": 5000,
        "lte_tdd_frame_structure": {
            "uldl_configuration": 2,
            "special_subframe": 4,
            "rmc_version": 1,
        },
    }
    payload.update(updates)
    return payload


@pytest.fixture
def test_case_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)
    previous = app.dependency_overrides.get(get_db)

    def _override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), session_factory
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_server_freezes_lte_tdd_authoring_input_as_the_only_mac_truth():
    validated = MIMOOTAConfiguration.model_validate(_lte_tdd_configuration())
    assert "lte_tdd_frame_structure" not in validated.model_dump(mode="json")
    canonical = canonicalize_mimo_ota_configuration_payload(_lte_tdd_configuration())

    assert "lte_tdd_frame_structure" not in canonical
    frozen = FrozenMacTestProfile.model_validate(canonical["mac_profile"])
    profile = frozen.profile
    assert profile.kind == "lte_rmc"
    assert profile.rat == "lte"
    assert profile.duplex == "tdd"
    assert profile.uldl_configuration == 2
    assert profile.special_subframe == 4
    assert profile.rmc_version == 1
    assert profile.statistical_window.count == 5000
    assert frozen == FrozenMacTestProfile.freeze(profile)


@pytest.mark.parametrize(
    "authoring",
    [
        None,
        {"uldl_configuration": 2},
        {"special_subframe": 4},
        {"uldl_configuration": False, "special_subframe": 4, "rmc_version": 1},
        {"uldl_configuration": 2, "special_subframe": True, "rmc_version": 1},
        {"uldl_configuration": 7, "special_subframe": 4, "rmc_version": 1},
        {"uldl_configuration": 2, "special_subframe": 8, "rmc_version": 1},
        {"uldl_configuration": 2, "special_subframe": 4, "rmc_version": 2},
        {
            "uldl_configuration": 2,
            "special_subframe": 4,
            "rmc_version": 1,
            "unknown": "must-not-persist",
        },
    ],
)
def test_lte_tdd_authoring_is_strict_and_never_uses_instrument_defaults(authoring):
    raw = _lte_tdd_configuration(lte_tdd_frame_structure=authoring)

    with pytest.raises(ValidationError):
        MIMOOTAConfiguration.model_validate(raw)


def test_lte_tdd_missing_authoring_stays_actionably_blocked():
    raw = _lte_tdd_configuration()
    raw.pop("lte_tdd_frame_structure")

    with pytest.raises(ValidationError, match="lte_tdd_frame_structure"):
        MIMOOTAConfiguration.model_validate(raw)


def test_fdd_nr_and_frozen_profile_reject_lte_tdd_authoring_smuggling():
    fdd = _lte_tdd_configuration()
    fdd["component_carriers"] = [
        {
            "radio_technology": "lte",
            "frequency_hz": 1_815_000_000.0,
            "bandwidth_mhz": 20.0,
            "subcarrier_spacing_khz": None,
            "band": "B3",
            "duplex": "fdd",
            "lte_dl_earfcn": 1300,
            "lte_transmission_mode": "TM3",
            "role": "pcell",
        }
    ]
    with pytest.raises(ValidationError, match="FDD.*lte_tdd_frame_structure"):
        MIMOOTAConfiguration.model_validate(fdd)

    nr = {"lte_tdd_frame_structure": deepcopy(fdd["lte_tdd_frame_structure"])}
    with pytest.raises(ValidationError, match="NR.*lte_tdd_frame_structure"):
        MIMOOTAConfiguration.model_validate(nr)

    dual = canonicalize_mimo_ota_configuration_payload(_lte_tdd_configuration())
    dual["lte_tdd_frame_structure"] = deepcopy(
        _lte_tdd_configuration()["lte_tdd_frame_structure"]
    )
    with pytest.raises(ValidationError, match="mac_profile.*lte_tdd_frame_structure"):
        MIMOOTAConfiguration.model_validate(dual)


def test_rmc_version_requirement_comes_from_the_selected_bandwidth_plan():
    missing_for_20 = _lte_tdd_configuration()
    missing_for_20["lte_tdd_frame_structure"].pop("rmc_version")
    with pytest.raises(ValidationError, match="rmc_version.*required"):
        MIMOOTAConfiguration.model_validate(missing_for_20)

    stray_for_10 = _lte_tdd_configuration()
    stray_for_10["component_carriers"][0]["bandwidth_mhz"] = 10.0
    with pytest.raises(ValidationError, match="rmc_version.*omitted"):
        MIMOOTAConfiguration.model_validate(stray_for_10)

    stray_for_10["lte_tdd_frame_structure"].pop("rmc_version")
    canonical = canonicalize_mimo_ota_configuration_payload(stray_for_10)
    assert canonical["mac_profile"]["profile"]["rmc_version"] is None


def test_post_persists_only_the_server_frozen_profile(test_case_api):
    client, session_factory = test_case_api

    response = client.post(
        "/api/v1/test-plans/cases",
        json={
            "name": "LTE TDD authoring",
            "test_type": "MIMO_OTA",
            "configuration": _lte_tdd_configuration(),
            "created_by": "p1-77-test",
        },
    )

    assert response.status_code == 201, response.text
    returned = response.json()["configuration"]
    assert "lte_tdd_frame_structure" not in returned
    FrozenMacTestProfile.model_validate(returned["mac_profile"])
    with session_factory() as session:
        stored = session.get(TestCase, UUID(response.json()["id"]))
        assert stored is not None
        assert stored.configuration == returned


def test_patch_repairs_legacy_tdd_atomically_and_invalid_retry_rolls_back(
    test_case_api,
):
    client, session_factory = test_case_api
    legacy = _lte_tdd_configuration()
    legacy.pop("lte_tdd_frame_structure")
    with session_factory() as session:
        row = TestCase(
            name="legacy LTE TDD",
            test_type="MIMO_OTA",
            configuration=legacy,
            created_by="historical-import",
        )
        session.add(row)
        session.commit()
        case_id = str(row.id)

    valid = _lte_tdd_configuration()
    repaired = client.patch(
        f"/api/v1/test-plans/cases/{case_id}",
        json={"configuration": valid},
    )
    assert repaired.status_code == 200, repaired.text
    saved = repaired.json()["configuration"]
    assert "lte_tdd_frame_structure" not in saved
    first_digest = saved["mac_profile"]["profile_digest"]

    invalid = _lte_tdd_configuration()
    invalid["lte_tdd_frame_structure"].pop("rmc_version")
    rejected = client.patch(
        f"/api/v1/test-plans/cases/{case_id}",
        json={"configuration": invalid},
    )
    assert rejected.status_code == 422
    assert "rmc_version" in rejected.json()["detail"]
    with session_factory() as session:
        stored = session.get(TestCase, UUID(case_id))
        assert stored is not None
        assert stored.configuration["mac_profile"]["profile_digest"] == first_digest
        assert "lte_tdd_frame_structure" not in stored.configuration


def test_canonical_profile_flows_unchanged_into_cmw_compatibility():
    canonical = canonicalize_mimo_ota_configuration_payload(
        _lte_tdd_configuration()
    )

    requirements = build_measure_execution_requirements_from_configuration(
        canonical
    )
    verdict = evaluate_base_station_compatibility(
        requirements,
        RealCmw500Driver.adapter_manifest,
    )

    assert requirements.mac_profile is not None
    assert (
        requirements.mac_profile.profile_digest
        == canonical["mac_profile"]["profile_digest"]
    )
    assert verdict.compatible is True
    assert verdict.status == "compatible"
