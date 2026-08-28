from __future__ import annotations

from datetime import datetime, timezone

from app.models.test_plan import TestExecution
from app.services.base_station_adapter_profile import (
    freeze_base_station_adapter_profile,
)
from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    TestCaseExecutionPolicy,
    activate_base_station_site_certification,
    freeze_execution_qualification,
    revoke_base_station_site_certification,
    validate_frozen_execution_qualification,
)
from app.services.mimo_ota.factory import build_mimo_ota_test_case
from tests.test_p2_45_site_certification_api import _source_execution, db  # noqa: F401


def _pending_execution(db, case):
    execution = TestExecution(
        test_case_id=case.id,
        status="pending",
        executed_by="test",
        config={},
    )
    db.add(execution)
    db.flush()
    return execution


def _active_site(db):
    connection, lab, case, source, hal = _source_execution(db)
    certification = activate_base_station_site_certification(
        db,
        hal,
        connection_id=connection.id,
        source_execution_id=source.id,
        certified_by="quality-owner",
        reason="site evidence complete",
    )
    return connection, lab, case, hal, certification


def test_matching_active_certification_freezes_formal_and_later_changes_do_not_relabel(
    db,
):
    connection, lab, case, hal, certification = _active_site(db)
    execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, execution, lab)

    frozen = freeze_execution_qualification(db, execution, case)

    assert frozen.classification == "formal"
    assert case.configuration["precheck_strict_cal"] is True
    assert frozen.policy_mode == "formal"
    assert frozen.binding_digest == certification.binding_digest
    assert frozen.site_certification_digest == certification.certification_digest
    assert execution.config[EXECUTION_QUALIFICATION_KEY] == frozen.model_dump(
        mode="json"
    )
    assert validate_frozen_execution_qualification(
        execution.config[EXECUTION_QUALIFICATION_KEY]
    ) is None

    case.execution_policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode="diagnostic",
        reason="new work only",
        updated_by="operator",
        updated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    revoke_base_station_site_certification(
        db,
        connection_id=connection.id,
        revoked_by="quality-owner",
        reason="firmware changed",
    )
    db.commit()

    assert freeze_execution_qualification(db, execution, case) == frozen


def test_next_execution_becomes_diagnostic_for_policy_revocation_or_adhoc(db):
    connection, lab, case, hal, _certification = _active_site(db)
    case.execution_policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode="diagnostic",
        reason="hardware bring-up",
        updated_by="site-operator",
        updated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    db.commit()

    diagnostic_execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, diagnostic_execution, lab)
    diagnostic = freeze_execution_qualification(
        db, diagnostic_execution, case
    )
    assert diagnostic.classification == "diagnostic"
    assert diagnostic.policy_mode == "diagnostic"
    assert "test_case_policy_diagnostic" in diagnostic.reasons
    assert case.configuration["precheck_strict_cal"] is False

    case.execution_policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode="formal",
        reason="formal candidate",
        updated_by="quality-owner",
        updated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    db.commit()
    adhoc_execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, adhoc_execution, lab)
    adhoc = freeze_execution_qualification(
        db,
        adhoc_execution,
        case,
        force_diagnostic=True,
    )
    assert adhoc.classification == "diagnostic"
    assert "adhoc_forced_diagnostic" in adhoc.reasons

    revoke_base_station_site_certification(
        db,
        connection_id=connection.id,
        revoked_by="quality-owner",
        reason="site state changed",
    )
    revoked_execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, revoked_execution, lab)
    revoked = freeze_execution_qualification(db, revoked_execution, case)
    assert revoked.classification == "diagnostic"
    assert "site_certification_not_active" in revoked.reasons
    assert case.configuration["precheck_strict_cal"] is False


def test_factory_copies_server_policy_to_execution_snapshot(db):
    _connection, lab, source, _source_execution_row, _hal = _source_execution(db)
    policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode="diagnostic",
        reason="explicit source policy",
        updated_by="operator",
        updated_at=datetime.now(timezone.utc),
    )
    source.execution_policy = policy.model_dump(mode="json")
    db.commit()

    snapshot, _steps = build_mimo_ota_test_case(
        db,
        name="execution snapshot",
        lab_profile_id=lab.id,
        config_overrides={},
        execution_policy=source.execution_policy,
    )

    assert snapshot.execution_policy == policy.model_dump(mode="json")
    assert snapshot.configuration["precheck_strict_cal"] is False

    formal_snapshot, _steps = build_mimo_ota_test_case(
        db,
        name="formal execution snapshot",
        lab_profile_id=lab.id,
        config_overrides={"precheck_strict_cal": False},
        execution_policy=None,
    )
    assert formal_snapshot.configuration["precheck_strict_cal"] is True


def test_qualification_digest_tamper_is_rejected(db):
    _connection, lab, case, hal, _certification = _active_site(db)
    execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, execution, lab)
    frozen = freeze_execution_qualification(db, execution, case).model_dump(
        mode="json"
    )
    frozen["classification"] = "diagnostic"

    assert validate_frozen_execution_qualification(frozen) == (
        "frozen execution qualification digest mismatch"
    )
