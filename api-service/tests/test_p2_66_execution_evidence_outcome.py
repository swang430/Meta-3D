from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.hal.base_station_compatibility import (
    build_frozen_compatibility_payload,
    build_measure_execution_requirements,
    build_no_adapter_verdict,
    canonical_payload_digest,
    evaluate_base_station_compatibility,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.base_station_adapter_profile import (
    FREEZE_CONFIG_KEY,
    freeze_base_station_adapter_profile,
)
from app.services.execution_evidence_outcome import (
    project_execution_evidence_outcome,
    validate_frozen_compatibility_snapshot,
)
from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    _qualification_payload_digest,
)


def _qualification(classification: str) -> dict:
    diagnostic = classification == "diagnostic"
    payload = {
        "schema_version": 1,
        "classification": classification,
        "policy_mode": "diagnostic" if diagnostic else "formal",
        "policy": None,
        "binding_digest": "b" * 64,
        "binding_status": "configured",
        "execution_mode": "real",
        "adapter_id": "uxm",
        "site_certification": None,
        "site_certification_digest": None,
        "reasons": ["test_case_policy_diagnostic"] if diagnostic else [],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["qualification_digest"] = _qualification_payload_digest(payload)
    return payload


def _compatibility(*, no_adapter: bool = False) -> dict:
    requirements = build_measure_execution_requirements("nr5g")
    verdict = (
        build_no_adapter_verdict(requirements)
        if no_adapter
        else evaluate_base_station_compatibility(
            requirements,
            RealUxmDriver.adapter_manifest,
        )
    )
    return build_frozen_compatibility_payload(requirements, verdict)


def _freeze(*, no_adapter: bool = False) -> dict:
    manifest = None if no_adapter else RealUxmDriver.adapter_manifest.model_dump(
        mode="json"
    )
    identity = {
        "schema_version": 1,
        "resolution": {
            "schema_version": 1,
            "adapter": None if no_adapter else "uxm",
            "status": "diagnostic_unbound" if no_adapter else "configured",
            "execution_mode": "simulated" if no_adapter else "real",
            "profile": None,
        },
        "binding_digest": "b" * 64,
        "resolved_binding": {
            "status": "diagnostic_unbound" if no_adapter else "configured",
            "binding_digest": "b" * 64,
            "manifest": manifest,
        },
        "compatibility": _compatibility(no_adapter=no_adapter),
    }
    return {**identity, "digest": canonical_payload_digest(identity)}


def _execution(
    *,
    status: str = "completed",
    qualification: str | None = "formal",
    no_adapter: bool = False,
    include_freeze: bool = True,
):
    config = {}
    if include_freeze:
        config[FREEZE_CONFIG_KEY] = _freeze(no_adapter=no_adapter)
    if qualification is not None:
        frozen_qualification = _qualification(qualification)
        if no_adapter:
            frozen_qualification.update(
                {
                    "binding_status": "diagnostic_unbound",
                    "execution_mode": "simulated",
                    "adapter_id": None,
                }
            )
            frozen_qualification["qualification_digest"] = (
                _qualification_payload_digest(frozen_qualification)
            )
        config[EXECUTION_QUALIFICATION_KEY] = frozen_qualification
    return SimpleNamespace(status=status, config=config)


def test_completed_compatible_formal_is_valid_test_completion():
    outcome = project_execution_evidence_outcome(_execution())

    assert outcome.compatibility_classification == "compatible"
    assert outcome.completion_semantic == "valid_test_completed"
    assert outcome.formal_eligible is True
    assert outcome.pipeline_status == "completed"
    assert outcome.compatibility_digest == canonical_payload_digest(
        _compatibility()
    )
    assert outcome.reasons == ()


def test_compatible_formal_does_not_override_nonterminal_pipeline_status():
    outcome = project_execution_evidence_outcome(_execution(status="running"))

    assert outcome.compatibility_classification == "compatible"
    assert outcome.completion_semantic == "not_completed"
    assert outcome.formal_eligible is False


def test_completed_diagnostic_is_explicit_diagnostic_completion():
    outcome = project_execution_evidence_outcome(
        _execution(qualification="diagnostic")
    )

    assert outcome.compatibility_classification == "diagnostic"
    assert outcome.completion_semantic == "diagnostic_completed"
    assert outcome.formal_eligible is False
    assert outcome.qualification_classification == "diagnostic"
    assert "test_case_policy_diagnostic" in outcome.reasons


def test_completed_no_adapter_is_diagnostic_not_formal_success():
    outcome = project_execution_evidence_outcome(
        _execution(qualification="diagnostic", no_adapter=True)
    )

    assert outcome.compatibility_classification == "diagnostic"
    assert outcome.completion_semantic == "diagnostic_completed"
    assert outcome.formal_eligible is False


def test_compatible_simulated_binding_cannot_claim_formal_completion():
    execution = _execution()
    frozen = deepcopy(execution.config[FREEZE_CONFIG_KEY])
    frozen["resolution"]["execution_mode"] = "simulated"
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )
    qualification = deepcopy(execution.config[EXECUTION_QUALIFICATION_KEY])
    qualification["execution_mode"] = "simulated"
    qualification["qualification_digest"] = _qualification_payload_digest(
        qualification
    )
    execution.config = {
        FREEZE_CONFIG_KEY: frozen,
        EXECUTION_QUALIFICATION_KEY: qualification,
    }

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.completion_semantic == "pipeline_completed"
    assert outcome.formal_eligible is False


def test_qualification_binding_digest_must_match_adapter_freeze():
    execution = _execution()
    qualification = deepcopy(execution.config[EXECUTION_QUALIFICATION_KEY])
    qualification["binding_digest"] = "c" * 64
    qualification["qualification_digest"] = _qualification_payload_digest(
        qualification
    )
    execution.config[EXECUTION_QUALIFICATION_KEY] = qualification

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any("binding" in reason for reason in outcome.reasons)


def test_compatibility_manifest_must_match_the_same_frozen_binding():
    execution = _execution()
    frozen = deepcopy(execution.config[FREEZE_CONFIG_KEY])
    requirements = build_measure_execution_requirements("lte")
    verdict = evaluate_base_station_compatibility(
        requirements,
        RealCmw500Driver.adapter_manifest,
    )
    frozen["compatibility"] = build_frozen_compatibility_payload(
        requirements,
        verdict,
    )
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )
    execution.config[FREEZE_CONFIG_KEY] = frozen

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.completion_semantic == "pipeline_completed"
    assert outcome.formal_eligible is False
    assert any("manifest" in reason for reason in outcome.reasons)


def test_historical_row_without_freeze_remains_legacy_pipeline_completion():
    outcome = project_execution_evidence_outcome(
        _execution(qualification=None, include_freeze=False)
    )

    assert outcome.compatibility_classification == "legacy"
    assert outcome.completion_semantic == "pipeline_completed"
    assert outcome.formal_eligible is False
    assert outcome.compatibility_digest is None


def test_historical_explicit_diagnostic_qualification_stays_diagnostic():
    outcome = project_execution_evidence_outcome(
        _execution(qualification="diagnostic", include_freeze=False)
    )

    assert outcome.compatibility_classification == "diagnostic"
    assert outcome.completion_semantic == "diagnostic_completed"
    assert outcome.formal_eligible is False


def test_outer_freeze_digest_tamper_fails_closed():
    execution = _execution()
    execution.config[FREEZE_CONFIG_KEY]["binding_digest"] = "c" * 64

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.completion_semantic == "pipeline_completed"
    assert outcome.formal_eligible is False
    assert any("digest" in reason for reason in outcome.reasons)


def test_inner_requirements_digest_tamper_fails_closed_even_with_new_outer_digest():
    execution = _execution()
    frozen = execution.config[FREEZE_CONFIG_KEY]
    frozen["compatibility"]["verdict"]["requirements_digest"] = "d" * 64
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.completion_semantic == "pipeline_completed"
    assert any("requirements" in reason for reason in outcome.reasons)


def test_explicit_incompatible_verdict_is_never_a_valid_completion():
    execution = _execution()
    frozen = execution.config[FREEZE_CONFIG_KEY]
    requirements = build_measure_execution_requirements("nr5g")
    incompatible = evaluate_base_station_compatibility(
        requirements,
        RealUxmDriver.adapter_manifest.model_copy(
            update={"rat_capabilities": ()}
        ),
    )
    frozen["compatibility"] = build_frozen_compatibility_payload(
        requirements,
        incompatible,
    )
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.completion_semantic == "pipeline_completed"
    assert any("incompatible" in reason for reason in outcome.reasons)


def test_no_adapter_verdict_requires_simulated_diagnostic_unbound_resolution():
    execution = _execution(qualification="diagnostic", no_adapter=True)
    frozen = execution.config[FREEZE_CONFIG_KEY]
    frozen["resolution"]["status"] = "configured"
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.completion_semantic == "pipeline_completed"
    assert any("no_adapter" in reason for reason in outcome.reasons)


def test_malformed_explicit_qualification_fails_closed_as_diagnostic():
    execution = _execution()
    execution.config[EXECUTION_QUALIFICATION_KEY]["classification"] = "diagnostic"

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "diagnostic"
    assert outcome.completion_semantic == "diagnostic_completed"
    assert outcome.formal_eligible is False
    assert outcome.qualification_classification == "diagnostic"


def test_snapshot_validator_rejects_outer_digest_and_accepts_legacy():
    frozen = _freeze()
    assert validate_frozen_compatibility_snapshot(frozen) is None

    tampered = deepcopy(frozen)
    tampered["resolution"]["adapter"] = "cmw500"
    assert "digest" in (validate_frozen_compatibility_snapshot(tampered) or "")
    assert validate_frozen_compatibility_snapshot(None) is None


def test_existing_freeze_is_rejected_before_reuse_when_evidence_drifted():
    driver = SimpleNamespace(
        adapter_id="uxm",
        _connection_host=None,
        _connection_port=None,
        _connection_resource=None,
    )
    frozen = _freeze()
    frozen.update(
        expected_driver_module=type(driver).__module__,
        expected_driver_name=type(driver).__name__,
        expected_driver_connection={"host": None, "port": None, "resource": None},
    )
    frozen["compatibility"]["verdict"]["requirements_digest"] = "d" * 64
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )
    execution = SimpleNamespace(config={FREEZE_CONFIG_KEY: frozen})
    hal = SimpleNamespace(drivers={"baseStation": driver})

    with pytest.raises(ValueError, match="requirements digest"):
        freeze_base_station_adapter_profile(None, hal, execution, None)
