from __future__ import annotations

from copy import deepcopy

import pytest
from uuid import uuid4

from app.models.test_plan import TestExecution
from app.services.execution_scpi_evidence import (
    load_base_station_execution_evidence,
    save_base_station_execution_evidence,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    base_station_execution_evidence_is_formally_acceptable,
    canonical_snapshot_digest,
    parse_base_station_execution_evidence,
)
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence


def test_exact_cmw_snapshot_is_canonical_and_formally_acceptable():
    evidence = valid_cmw_evidence()

    assert parse_base_station_execution_evidence(evidence) == evidence
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is True


def test_formal_evidence_accepts_option_tokens_exactly_as_cmw500_reports_them():
    evidence = valid_cmw_evidence()
    evidence["identity"]["options"] = ["KS550", "KS520"]
    evidence["requested_config"]["payload"]["duplex"] = "tdd"
    digest = canonical_snapshot_digest(evidence["requested_config"]["payload"])
    evidence["requested_config"]["digest"] = digest
    evidence["measurement_windows"][0]["config_digest"] = digest

    assert base_station_execution_evidence_is_formally_acceptable(evidence) is True


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(extra="forged"),
        lambda value: value["identity"].update(extra="forged"),
        lambda value: value["measurement_windows"][0].update(extra="forged"),
        lambda value: value["control_releases"][0].update(extra="forged"),
    ],
)
def test_extra_fields_and_malformed_nested_rows_are_rejected(mutation):
    evidence = valid_cmw_evidence()
    mutation(evidence)

    assert parse_base_station_execution_evidence(evidence) is None
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


def test_boolean_confirmations_are_exact_booleans_not_truthy_integers():
    evidence = valid_cmw_evidence()
    evidence["config_confirmed"] = 1

    assert parse_base_station_execution_evidence(evidence) is None
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("execution_mode",), "simulated"),
        (("formal_capability_approval", "enabled"), False),
        (("formal_capability_approval", "instrument_connection_id"), "other"),
        (("config_confirmed",), False),
        (("route_confirmed",), False),
        (("current_measurement_attempt_state",), "failed"),
        (("measurement_windows", 0, "cleanup", "safe_idle_confirmed"), False),
        (("control_releases", 0, "transport_session_released_confirmed"), False),
    ],
)
def test_formal_whitelist_fails_closed_for_untrusted_cmw_states(path, replacement):
    evidence = valid_cmw_evidence()
    target = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


def test_cmw_capability_requires_the_frozen_duplex_options():
    evidence = valid_cmw_evidence()
    evidence["identity"]["options"] = ["CMW-KS520"]

    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


def test_cmw_lte_2x2_formal_capability_rejects_other_frozen_layer_counts():
    evidence = valid_cmw_evidence()
    evidence["requested_config"]["payload"]["mimo_layers"] = 4
    digest = canonical_snapshot_digest(evidence["requested_config"]["payload"])
    evidence["requested_config"]["digest"] = digest
    evidence["measurement_windows"][0]["config_digest"] = digest

    assert parse_base_station_execution_evidence(evidence) == evidence
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


@pytest.mark.parametrize("transmission_mode", ["TM1", "TM2", "TM6", "TM7"])
def test_cmw_lte_2x2_formal_capability_rejects_single_layer_modes(
    transmission_mode,
):
    evidence = valid_cmw_evidence()
    evidence["requested_config"]["payload"]["lte_transmission_mode"] = (
        transmission_mode
    )
    digest = canonical_snapshot_digest(evidence["requested_config"]["payload"])
    evidence["requested_config"]["digest"] = digest
    evidence["measurement_windows"][0]["config_digest"] = digest

    assert parse_base_station_execution_evidence(evidence) == evidence
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


def test_default_disabled_cmw_approval_without_timestamp_is_valid_but_not_formal():
    evidence = valid_cmw_evidence()
    evidence["formal_capability_approval"].update(enabled=False, updated_at=None)

    assert parse_base_station_execution_evidence(evidence) == evidence
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("model", "CMW500"), ("firmware_version", "3.5.39")],
)
def test_cmw_identity_must_match_the_driver_verified_model_and_minimum_firmware(
    field, replacement
):
    evidence = valid_cmw_evidence()
    evidence["identity"][field] = replacement

    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


def test_execution_exchange_ids_must_be_unique():
    evidence = valid_cmw_evidence()
    evidence["exchange_ids"].append("life-1")

    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


def test_current_attempt_scope_ignores_old_audit_rows_but_rejects_current_duplicates():
    evidence = valid_cmw_evidence()
    old_window = deepcopy(evidence["measurement_windows"][0])
    old_window.update(
        window_id="window-old",
        measurement_attempt_id="attempt-old",
        lease_id="lease-old",
        session_token="session-old",
    )
    for metric in old_window["metrics"].values():
        metric["measurement_attempt_id"] = "attempt-old"
        metric["session_token"] = "session-old"
    old_release = deepcopy(evidence["control_releases"][0])
    old_release.update(
        measurement_attempt_id="attempt-old",
        lease_id="lease-old",
        session_token="session-old",
    )
    evidence["measurement_windows"].append(old_window)
    evidence["control_releases"].append(old_release)

    assert base_station_execution_evidence_is_formally_acceptable(evidence) is True

    evidence["control_releases"].append(deepcopy(evidence["control_releases"][0]))
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is False


def test_uxm_uses_not_applicable_approval_and_does_not_require_cmw_route():
    evidence = valid_cmw_evidence()
    evidence["adapter"] = "uxm"
    evidence["identity"].update(
        adapter="uxm",
        model="E7515B",
        adapter_profile_digest=None,
    )
    evidence["formal_capability_approval"] = {
        "schema_version": 1,
        "status": "not_applicable",
        "instrument_connection_id": None,
        "capability": None,
        "enabled": None,
        "updated_at": None,
    }
    evidence["route_confirmed"] = None
    evidence["requested_route"] = None
    evidence["applied_route"] = None
    evidence["measurement_windows"][0]["adapter"] = "uxm"
    evidence["measurement_windows"][0]["route_digest"] = None
    evidence["control_releases"][0]["adapter_id"] = "uxm"

    assert parse_base_station_execution_evidence(evidence) == evidence
    assert base_station_execution_evidence_is_formally_acceptable(evidence) is True


def test_execution_storage_is_server_bound_and_brownfield_reads_fail_closed():
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    evidence = valid_cmw_evidence()
    evidence["execution_id"] = str(execution.id)

    saved = save_base_station_execution_evidence(execution, evidence)
    assert load_base_station_execution_evidence(execution) == saved

    execution.config["base_station_execution_evidence"]["execution_id"] = "other"
    assert load_base_station_execution_evidence(execution) is None

    evidence["execution_id"] = "other"
    with pytest.raises(ValueError, match="execution_id mismatch"):
        save_base_station_execution_evidence(execution, evidence)
