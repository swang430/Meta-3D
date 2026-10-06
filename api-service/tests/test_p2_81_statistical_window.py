"""P2-81: adapter-specific statistical basis must fail before instrument I/O."""
import pytest

from app.hal.base_station_compatibility import (
    build_measure_execution_requirements_from_configuration,
    evaluate_base_station_compatibility,
    manifest_compatibility_digest,
    digest_safe_manifest_payload,
)
from app.hal.base_station_manifest import BaseStationAdapterManifest
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from tests.test_p2_54_mac_profile_compatibility import _lte_configuration
from tests.test_p2_65_shared_compatibility_readiness import db, _saved_case_and_binding
from app.services.test_plan_service import TestCaseService, MIMOOTACarrierTruthError
from app.services import topology_profile_service


@pytest.mark.parametrize("count", [99, 400001])
def test_cmw_rejects_statistical_basis_before_any_io(count):
    config = {**_lte_configuration(), "stat_count": count}
    requirements = build_measure_execution_requirements_from_configuration(config)
    verdict = evaluate_base_station_compatibility(
        requirements, RealCmw500Driver.adapter_manifest,
    )
    assert verdict.compatible is False
    assert any("statistical_window" in reason for reason in verdict.reasons)


@pytest.mark.parametrize("count", [100, 5000, 400000])
def test_cmw_accepts_inclusive_documented_boundaries(count):
    requirements = build_measure_execution_requirements_from_configuration(
        {**_lte_configuration(), "stat_count": count},
    )
    assert evaluate_base_station_compatibility(
        requirements, RealCmw500Driver.adapter_manifest,
    ).compatible


@pytest.mark.parametrize("count", [1, 99, 400001])
def test_uxm_does_not_inherit_cmw_parameter_range(count):
    requirements = build_measure_execution_requirements_from_configuration(
        {"stat_count": count},
    )
    assert evaluate_base_station_compatibility(
        requirements, RealUxmDriver.adapter_manifest,
    ).compatible


def test_catalog_exposes_auditable_cmw_range_and_unknown_uxm_range():
    cmw = RealCmw500Driver.adapter_manifest.model_dump(mode="json")
    constraint = cmw["mac_profiles"][0]["statistical_window"]
    assert (constraint["minimum"], constraint["maximum"], constraint["unit"]) == (
        100, 400000, "subframes",
    )
    assert "953" in constraint["source_reference"]
    assert RealUxmDriver.adapter_manifest.model_dump(mode="json")[
        "mac_profiles"
    ][0]["statistical_window"] is None


def test_pre_p2_81_manifest_preserves_historical_identity_digests():
    current = RealCmw500Driver.adapter_manifest
    raw = current.model_dump(mode="json")
    for capability in raw["mac_profiles"]:
        capability.pop("statistical_window", None)
    historical = BaseStationAdapterManifest.model_validate(raw)
    assert manifest_compatibility_digest(current) == manifest_compatibility_digest(historical)
    assert digest_safe_manifest_payload(current, exclude_none=False) == (
        digest_safe_manifest_payload(historical, exclude_none=False)
    )


@pytest.mark.parametrize("count", [99, 400001])
def test_bound_case_update_rejects_invalid_count_without_partial_save(db, count):
    case, lab, _ = _saved_case_and_binding(db, model_name="CMW500", requested_rat="lte")
    original = dict(case.configuration)
    with pytest.raises(MIMOOTACarrierTruthError, match="statistical_window"):
        TestCaseService().update_test_case(
            db, case.id, configuration={**_lte_configuration(), "stat_count": count},
            name="must-not-persist",
        )
    db.expire_all()
    assert TestCaseService().get_test_case(db, case.id).configuration == original
    assert TestCaseService().get_test_case(db, case.id).name != "must-not-persist"


def test_bound_case_create_rejects_invalid_count(db):
    _, lab, _ = _saved_case_and_binding(db, model_name="CMW500", requested_rat="lte")
    with pytest.raises(MIMOOTACarrierTruthError, match="statistical_window"):
        TestCaseService().create_test_case(
            db, name="invalid", test_type="MIMO_OTA", created_by="test",
            lab_profile_id=lab.id,
            configuration={**_lte_configuration(), "stat_count": 99},
        )


@pytest.mark.parametrize("count", [0, -1])
def test_topology_save_checks_common_positive_count_without_cmw_domain(db, count):
    with pytest.raises(ValueError):
        topology_profile_service.create(db, name="invalid", fields={"stat_count": count})


def test_topology_nr_positive_count_is_not_cmw_bounded(db):
    row = topology_profile_service.create(db, name="NR", fields={"stat_count": 400001})
    assert row.stat_count == 400001


def test_null_configuration_rebind_keeps_saved_configuration(db):
    case, lab, _ = _saved_case_and_binding(db, model_name="CMW500", requested_rat="lte")
    original = dict(case.configuration)
    result = TestCaseService().update_test_case(db, case.id, configuration=None, lab_profile_id=lab.id)
    assert result.configuration == original


def test_inactive_bound_lab_remains_editable_and_range_checked(db):
    case, lab, _ = _saved_case_and_binding(db, model_name="CMW500", requested_rat="lte")
    lab.is_active = False
    db.commit()
    result = TestCaseService().update_test_case(db, case.id, configuration={**_lte_configuration(), "stat_count": 100})
    assert result.configuration["mac_profile"]["profile"]["statistical_window"]["count"] == 100
    with pytest.raises(MIMOOTACarrierTruthError):
        TestCaseService().update_test_case(db, case.id, configuration={**_lte_configuration(), "stat_count": 99})


def test_core_openapi_and_checked_contract_expose_statistical_constraint():
    from app.main import app
    from pathlib import Path
    import yaml
    checked = yaml.safe_load((Path(__file__).resolve().parents[2] / "api/openapi.yaml").read_text())
    for schemas in (app.openapi()["components"]["schemas"], checked["components"]["schemas"]):
        assert "statistical_window" in schemas["BaseStationMacProfileCapability"]["properties"]
        assert schemas["BaseStationStatisticalWindowConstraint"]["properties"]["minimum"]["exclusiveMinimum"] == 0


def test_preview_declared_domain_does_not_require_loaded_hal(db, monkeypatch):
    from app.api.lab_profile import preview_base_station_binding
    from app.services import instrument_hal_service
    _, lab, hal = _saved_case_and_binding(db, model_name="CMW500", requested_rat="lte")
    hal.drivers.clear()
    monkeypatch.setattr(instrument_hal_service, "get_hal_service", lambda: hal)
    result = preview_base_station_binding(lab.id, test_case_id=None, db=db)
    assert result.status == "invalid"
    assert result.declared_mac_manifest.mac_profiles[0].statistical_window.minimum == 100


def test_duplicate_bad_historical_topology_returns_controlled_error(db):
    from fastapi import HTTPException
    from app.api.instrument import duplicate_topology_profile_endpoint
    row = topology_profile_service.create(db, name="historical", fields={"stat_count": 5000})
    row.stat_count = 0
    db.commit()
    with pytest.raises(HTTPException) as exc:
        duplicate_topology_profile_endpoint("baseStation", row.profile_id, db=db)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("driver_mode", ["real", "mock"])
@pytest.mark.parametrize("count", [99, 400001])
def test_preview_and_freeze_reject_same_count_before_remote(db, driver_mode, count):
    from app.services.base_station_compatibility import build_base_station_compatibility_preview
    from app.services.base_station_adapter_profile import freeze_base_station_adapter_profile
    from app.models.test_plan import TestExecution

    case, lab, hal = _saved_case_and_binding(
        db, model_name="CMW500", requested_rat="lte", driver_mode=driver_mode,
    )
    # Historical/imported row bypassed the new save gate. It still cannot execute.
    case.configuration = {**_lte_configuration(), "stat_count": count}
    db.commit()
    preview = build_base_station_compatibility_preview(db, hal, lab, test_case_id=case.id)
    assert preview.status == "incompatible"
    assert any("statistical_window" in reason for reason in preview.reasons)
    execution = TestExecution(test_case_id=case.id, status="pending", config={}, executed_by="test")
    db.add(execution)
    db.flush()
    with pytest.raises(ValueError, match="statistical_window"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)
    assert execution.config == {}


def test_http_save_returns_controlled_error_without_writing(db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import get_db
    case, lab, _ = _saved_case_and_binding(db, model_name="CMW500", requested_rat="lte")
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        result = client.patch(f"/api/v1/test-plans/cases/{case.id}", json={
            "name": "must-not-save", "configuration": {**_lte_configuration(), "stat_count": 99},
        })
        assert result.status_code == 422
        assert "statistical_window" in result.json()["detail"]
        db.expire_all()
        assert TestCaseService().get_test_case(db, case.id).name != "must-not-save"
    finally:
        app.dependency_overrides.pop(get_db, None)
