from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.hal.base_station_compatibility import (
    build_frozen_compatibility_payload,
    build_measure_execution_requirements,
    canonical_payload_digest,
    evaluate_base_station_compatibility,
)
from app.hal.uxm_base_station import RealUxmDriver
from app.models.test_plan import TestExecution
from app.services.base_station_adapter_profile import (
    FREEZE_CONFIG_KEY,
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
from app.services.execution_evidence_outcome import project_execution_evidence_outcome
from app.services.mimo_ota.base_station_execution_evidence import (
    BASE_STATION_EXECUTION_EVIDENCE_FIELD,
    evaluate_base_station_metric_trust,
)
from app.services.mimo_ota.factory import build_mimo_ota_test_case
from app.services.mimo_ota.executors._helpers import load_mimo_ota_config
from app.schemas.mimo_ota.config import canonicalize_mimo_ota_configuration_payload
from tests.p1_73c_evidence_fixtures import POSITION, REQUESTED_CONFIG
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
    assert load_mimo_ota_config(execution).precheck_strict_cal is True
    assert frozen.policy_mode == "formal"
    assert frozen.binding_digest == certification.binding_digest
    assert frozen.site_certification_digest == certification.certification_digest
    assert execution.config[EXECUTION_QUALIFICATION_KEY] == frozen.model_dump(
        mode="json"
    )
    assert validate_frozen_execution_qualification(
        execution.config[EXECUTION_QUALIFICATION_KEY]
    ) is None

    original = load_mimo_ota_config(execution)
    case.configuration = canonicalize_mimo_ota_configuration_payload(
        {"mimo_layers": 4, "mcs": 3}
    )
    db.flush()
    immutable = load_mimo_ota_config(execution)
    assert immutable.mimo_layers == original.mimo_layers
    assert immutable.mac_profile.profile_digest == original.mac_profile.profile_digest

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


def test_frozen_configuration_must_match_frozen_requirements(db):
    _connection, lab, case, hal, _certification = _active_site(db)
    execution = _pending_execution(db, case)
    adapter_freeze = freeze_base_station_adapter_profile(db, hal, execution, lab)
    freeze_execution_qualification(db, execution, case)

    adapter_freeze["mimo_ota_configuration"] = (
        canonicalize_mimo_ota_configuration_payload({"mimo_layers": 4, "mcs": 3})
    )
    adapter_freeze["digest"] = canonical_payload_digest(
        {key: value for key, value in adapter_freeze.items() if key != "digest"}
    )
    execution.config[FREEZE_CONFIG_KEY] = adapter_freeze

    outcome = project_execution_evidence_outcome(execution)
    assert outcome.compatibility_classification == "invalid"
    assert "configuration" in "\n".join(outcome.reasons)


def test_formal_metric_uses_site_certification_instead_of_retired_cmw_approval(db):
    connection, lab, case, source, hal = _source_execution(db)
    activate_base_station_site_certification(
        db,
        hal,
        connection_id=connection.id,
        source_execution_id=source.id,
        certified_by="quality-owner",
        reason="site evidence complete",
    )
    execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, execution, lab)
    frozen = freeze_execution_qualification(db, execution, case)
    evidence = deepcopy(source.config[BASE_STATION_EXECUTION_EVIDENCE_FIELD])

    assert frozen.classification == "formal"
    assert evidence["formal_capability_approval"]["enabled"] is False
    result = evaluate_base_station_metric_trust(
        evidence,
        "dl_throughput_mbps",
        expected_config=REQUESTED_CONFIG,
        expected_position=POSITION,
        execution_config=execution.config,
    )

    assert result.status == "trusted"
    assert result.formal_value == 96.5


def test_formal_metric_rejects_hardware_identity_changed_after_site_certification(db):
    connection, lab, case, source, hal = _source_execution(db)
    activate_base_station_site_certification(
        db,
        hal,
        connection_id=connection.id,
        source_execution_id=source.id,
        certified_by="quality-owner",
        reason="site evidence complete",
    )
    execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, execution, lab)
    freeze_execution_qualification(db, execution, case)
    evidence = deepcopy(source.config[BASE_STATION_EXECUTION_EVIDENCE_FIELD])
    evidence["identity"]["firmware_version"] = "3.5.41"

    result = evaluate_base_station_metric_trust(
        evidence,
        "dl_throughput_mbps",
        expected_config=REQUESTED_CONFIG,
        expected_position=POSITION,
        execution_config=execution.config,
    )

    assert result.status == "diagnostic"
    assert result.formal_value is None
    assert result.diagnostic_value == 96.5
    assert result.reason == "site_certification_identity_mismatch"


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
    assert load_mimo_ota_config(diagnostic_execution).precheck_strict_cal is False

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


def test_each_execution_reads_calibration_gate_from_its_own_frozen_qualification(db):
    _connection, lab, case, hal, _certification = _active_site(db)
    formal_execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, formal_execution, lab)
    formal = freeze_execution_qualification(db, formal_execution, case)
    assert formal.classification == "formal"

    case.execution_policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode="diagnostic",
        reason="later diagnostic run",
        updated_by="site-operator",
        updated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    db.flush()
    diagnostic_execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, diagnostic_execution, lab)
    diagnostic = freeze_execution_qualification(db, diagnostic_execution, case)
    assert diagnostic.classification == "diagnostic"

    assert load_mimo_ota_config(formal_execution).precheck_strict_cal is True
    assert load_mimo_ota_config(diagnostic_execution).precheck_strict_cal is False


def test_pre_p1_75_formal_execution_keeps_its_frozen_qualification_gate(db):
    _connection, lab, case, hal, _certification = _active_site(db)
    execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, execution, lab)
    frozen = freeze_execution_qualification(db, execution, case)
    assert frozen.classification == "formal"

    config = dict(execution.config)
    old_freeze = dict(config[FREEZE_CONFIG_KEY])
    old_freeze.pop("compatibility")
    old_freeze["digest"] = canonical_payload_digest(
        {key: value for key, value in old_freeze.items() if key != "digest"}
    )
    config[FREEZE_CONFIG_KEY] = old_freeze
    execution.config = config

    assert load_mimo_ota_config(execution).precheck_strict_cal is True


def test_pre_p2_54_null_mac_profile_freeze_remains_loadable_legacy(db):
    _connection, lab, case, hal, _certification = _active_site(db)
    expected_kind = canonicalize_mimo_ota_configuration_payload(
        case.configuration
    )["mac_profile"]["profile"]["kind"]
    execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, execution, lab)
    freeze_execution_qualification(db, execution, case)

    config = dict(execution.config)
    old_freeze = dict(config[FREEZE_CONFIG_KEY])
    requirements = build_measure_execution_requirements("nr5g")
    verdict = evaluate_base_station_compatibility(
        requirements,
        RealUxmDriver.adapter_manifest,
    )
    old_freeze["compatibility"] = build_frozen_compatibility_payload(
        requirements,
        verdict,
    )
    old_freeze.pop("mimo_ota_configuration")
    old_freeze["digest"] = canonical_payload_digest(
        {key: value for key, value in old_freeze.items() if key != "digest"}
    )
    config[FREEZE_CONFIG_KEY] = old_freeze
    execution.config = config

    assert old_freeze["compatibility"]["requirements"]["mac_profile"] is None
    assert load_mimo_ota_config(execution).mac_profile.profile.kind == expected_kind


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


def test_explicit_malformed_qualification_is_never_backfilled_from_current_state(db):
    _connection, lab, case, hal, _certification = _active_site(db)
    execution = _pending_execution(db, case)
    freeze_base_station_adapter_profile(db, hal, execution, lab)
    execution.config = {
        **execution.config,
        EXECUTION_QUALIFICATION_KEY: None,
    }
    db.flush()

    with pytest.raises(
        ValueError,
        match="frozen execution qualification is missing",
    ):
        freeze_execution_qualification(db, execution, case)
