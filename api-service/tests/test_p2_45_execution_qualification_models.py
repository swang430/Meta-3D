from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.instrument import InstrumentConnection
from app.models.test_plan import TestCase
from app.schemas.instrument import InstrumentConnectionUpdate
from app.schemas.test_plan import TestCaseCreate, TestCaseUpdate
from app.services.execution_qualification import (
    BaseStationCertificationProofs,
    BaseStationSiteCertification,
    TestCaseExecutionPolicy,
    parse_base_station_site_certification,
    parse_test_case_execution_policy,
)


NOW = datetime(2026, 8, 29, 4, 30, tzinfo=timezone.utc)


def _active_certification(**overrides):
    payload = {
        "schema_version": 1,
        "status": "active",
        "lab_profile_id": str(uuid4()),
        "instrument_connection_id": str(uuid4()),
        "binding_digest": "b" * 64,
        "adapter_id": "cmw500",
        "model": "CMW",
        "firmware_version": "3.8.10",
        "options": ["KS500", "KS520"],
        "source_execution_id": str(uuid4()),
        "evidence_digest": "e" * 64,
        "required_proofs": {
            "config_readback": True,
            "route_readback": True,
            "route_not_applicable": False,
            "cleanup": True,
            "transport_release": True,
        },
        "certified_by": "site-operator",
        "certified_at": NOW,
        "reason": "现场真机配置、清理和释放闭环已复核",
        "revoked_by": None,
        "revoked_at": None,
        "revocation_reason": None,
    }
    payload.update(overrides)
    return BaseStationSiteCertification.model_validate(payload)


def test_test_case_policy_is_strict_frozen_and_requires_diagnostic_audit():
    policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode="diagnostic",
        reason="现场先打通硬件，校准后再正式复测",
        updated_by="site-operator",
        updated_at=NOW,
    )

    assert policy.model_dump(mode="json") == {
        "schema_version": 1,
        "mode": "diagnostic",
        "reason": "现场先打通硬件，校准后再正式复测",
        "updated_by": "site-operator",
        "updated_at": "2026-08-29T04:30:00Z",
    }
    with pytest.raises(ValidationError):
        policy.mode = "formal"
    for field, value in (("reason", " "), ("updated_by", "")):
        with pytest.raises(ValidationError):
            TestCaseExecutionPolicy.model_validate(
                {
                    "schema_version": 1,
                    "mode": "diagnostic",
                    "reason": "valid reason",
                    "updated_by": "operator",
                    "updated_at": NOW,
                    field: value,
                }
            )


def test_explicit_malformed_policy_fails_loud_and_missing_policy_is_formal():
    assert parse_test_case_execution_policy(None) is None
    with pytest.raises(ValueError, match="execution policy"):
        parse_test_case_execution_policy({"mode": "diagnostic"})


def test_site_certification_is_strict_frozen_and_binds_all_required_proofs():
    certification = _active_certification()

    assert certification.required_proofs == BaseStationCertificationProofs(
        config_readback=True,
        route_readback=True,
        route_not_applicable=False,
        cleanup=True,
        transport_release=True,
    )
    assert certification.certification_digest is not None
    assert len(certification.certification_digest) == 64
    with pytest.raises(ValidationError):
        certification.status = "revoked"

    for field in (
        "config_readback",
        "cleanup",
        "transport_release",
    ):
        proofs = certification.required_proofs.model_dump()
        proofs[field] = False
        with pytest.raises(ValidationError):
            _active_certification(required_proofs=proofs)

    with pytest.raises(ValidationError):
        _active_certification(
            required_proofs={
                "config_readback": True,
                "route_readback": False,
                "route_not_applicable": False,
                "cleanup": True,
                "transport_release": True,
            }
        )


def test_revoked_certification_keeps_original_evidence_and_requires_revoke_audit():
    revoked = _active_certification(
        status="revoked",
        revoked_by="quality-owner",
        revoked_at=NOW,
        revocation_reason="仪器固件已变更，旧认证失效",
    )
    assert revoked.source_execution_id
    assert revoked.evidence_digest == "e" * 64

    for field in ("revoked_by", "revoked_at", "revocation_reason"):
        payload = revoked.model_dump()
        payload[field] = None
        with pytest.raises(ValidationError):
            BaseStationSiteCertification.model_validate(payload)


def test_explicit_malformed_certification_fails_loud_and_missing_is_unqualified():
    assert parse_base_station_site_certification(None) is None
    with pytest.raises(ValueError, match="site certification"):
        parse_base_station_site_certification({"status": "active"})


def test_server_owned_fields_exist_only_on_orm_models_not_generic_write_schemas():
    assert "execution_policy" in TestCase.__table__.columns
    assert "base_station_site_certification" in InstrumentConnection.__table__.columns

    assert "execution_policy" not in TestCaseCreate.model_fields
    assert "execution_policy" not in TestCaseUpdate.model_fields
    assert "base_station_site_certification" not in InstrumentConnectionUpdate.model_fields
