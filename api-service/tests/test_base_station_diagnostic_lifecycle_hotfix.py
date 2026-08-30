from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.hal.base_station import BaseStationControlReleaseResult
from app.models.test_plan import TestExecution
from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    _qualification_payload_digest,
)
from app.services.execution_scpi_evidence import (
    persist_execution_base_station_release,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    base_station_attempt_diagnostic_lifecycle_is_complete,
    base_station_attempt_lifecycle_is_complete,
    canonical_snapshot_digest,
)
from tests.p1_73c_evidence_fixtures import REQUESTED_CONFIG, valid_cmw_evidence


ATTEMPT_ID = "attempt-diagnostic"
LEASE_ID = "lease-diagnostic"
SESSION_TOKEN = "session-diagnostic"


def _diagnostic_qualification() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "classification": "diagnostic",
        "policy_mode": "formal",
        "policy": None,
        "binding_digest": "a" * 64,
        "binding_status": "diagnostic_unbound",
        "execution_mode": "simulated",
        "adapter_id": None,
        "site_certification": None,
        "site_certification_digest": None,
        "reasons": ["base_station_binding_diagnostic_unbound"],
        "frozen_at": now,
    }
    payload["qualification_digest"] = _qualification_payload_digest(payload)
    return payload


def _diagnostic_evidence(*, with_release: bool = True) -> dict:
    value = valid_cmw_evidence()
    value.update(
        adapter="uxm",
        execution_mode="simulated",
        identity={
            "adapter": "uxm",
            "model": "MockBaseStation",
            "firmware_version": None,
            "options": [],
            "instrument_connection_id": "connection-diagnostic",
            "adapter_profile_digest": None,
        },
        formal_capability_approval={
            "schema_version": 1,
            "status": "not_applicable",
            "instrument_connection_id": None,
            "capability": None,
            "enabled": None,
            "updated_at": None,
        },
        config_confirmed=False,
        route_confirmed=None,
        requested_route=None,
        applied_route=None,
        requested_positions=[{"azimuth_deg": 0.0, "elevation_deg": 0.0}],
        current_measurement_attempt_id=ATTEMPT_ID,
        current_measurement_attempt_state="running",
        measurement_window_contract_version=1,
        measurement_windows=[],
        control_releases=[],
        exchange_ids=[],
    )
    config_digest = canonical_snapshot_digest(REQUESTED_CONFIG)
    started = datetime(2026, 8, 30, tzinfo=timezone.utc)
    for index in range(3):
        request = {
            "schema_version": 1,
            "scope": "pcell",
            "lifecycle": "unavailable",
            "cardinality": "requested",
            "requested_window_count": 3,
            "expected_window_count": 3,
            "window_index": index,
        }
        window_started = started + timedelta(seconds=index * 2)
        value["measurement_windows"].append(
            {
                "window_id": f"window-diagnostic-{index}",
                "measurement_attempt_id": ATTEMPT_ID,
                "lease_id": LEASE_ID,
                "adapter": "uxm",
                "session_token": SESSION_TOKEN,
                "config_digest": config_digest,
                "route_digest": None,
                "position": {"azimuth_deg": 0.0, "elevation_deg": 0.0},
                "ue_link_state": "connected",
                "started_at": window_started.isoformat().replace("+00:00", "Z"),
                "completed_at": (window_started + timedelta(seconds=1))
                .isoformat()
                .replace("+00:00", "Z"),
                "preclear_off_confirmed": False,
                "running_confirmed": False,
                "ready_confirmed": False,
                "closed_off_confirmed": False,
                "cleanup": {
                    "stop_signaling_confirmed": True,
                    "safe_idle_confirmed": True,
                    "warnings": [],
                },
                "lifecycle_exchange_ids": [],
                "metrics": {},
                "trust": {
                    "schema_version": 1,
                    "request": request,
                    "request_digest": canonical_snapshot_digest(request),
                    "stages": [
                        {
                            "stage": stage,
                            "status": "unavailable",
                            "reason": "simulated diagnostic lifecycle",
                            "exchange_ids": [],
                        }
                        for stage in ("clear", "run", "ready", "closed")
                    ],
                    "simulated": True,
                    "exchange_ids": [],
                    "reason": "simulated diagnostic window",
                    "context_confirmed": False,
                },
            }
        )
    if with_release:
        value["control_releases"] = [
            {
                "measurement_attempt_id": ATTEMPT_ID,
                "lease_id": LEASE_ID,
                "adapter_id": "uxm",
                "session_token": SESSION_TOKEN,
                "remote_session_acquired_confirmed": True,
                "transport_session_released_confirmed": True,
                "front_panel_local_confirmed": None,
                "warnings": [],
            }
        ]
    return value


def test_diagnostic_attempt_completes_without_fabricating_formal_truth():
    value = _diagnostic_evidence()

    assert base_station_attempt_diagnostic_lifecycle_is_complete(
        value, ATTEMPT_ID
    ) is True
    assert base_station_attempt_lifecycle_is_complete(value, ATTEMPT_ID) is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["measurement_windows"].pop(),
        lambda value: value["measurement_windows"][1]["trust"]["request"].update(
            window_index=0
        ),
        lambda value: value["measurement_windows"][0]["cleanup"].update(
            stop_signaling_confirmed=False
        ),
        lambda value: value["measurement_windows"][0]["trust"].update(
            simulated=False
        ),
        lambda value: value["measurement_windows"][0].update(config_digest="wrong"),
        lambda value: value["control_releases"][0].update(
            transport_session_released_confirmed=False
        ),
    ],
)
def test_diagnostic_attempt_still_fails_closed_for_incomplete_session_truth(mutate):
    value = _diagnostic_evidence()
    mutate(value)
    for window in value["measurement_windows"]:
        request = window["trust"]["request"]
        window["trust"]["request_digest"] = canonical_snapshot_digest(request)

    assert base_station_attempt_diagnostic_lifecycle_is_complete(
        value, ATTEMPT_ID
    ) is False


class _Query:
    def __init__(self, execution):
        self.execution = execution

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def one_or_none(self):
        return self.execution

    def first(self):
        return self.execution


class _Db:
    def __init__(self, execution):
        self.query_object = _Query(execution)

    def query(self, _model):
        return self.query_object

    def flush(self):
        pass

    def commit(self):
        pass


def _execution(*, qualification: dict | None) -> TestExecution:
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    evidence = _diagnostic_evidence(with_release=False)
    evidence["execution_id"] = str(execution.id)
    config = {"base_station_execution_evidence": evidence}
    if qualification is not None:
        config[EXECUTION_QUALIFICATION_KEY] = qualification
    execution.config = config
    return execution


def _release() -> BaseStationControlReleaseResult:
    return BaseStationControlReleaseResult(
        measurement_attempt_id=ATTEMPT_ID,
        lease_id=LEASE_ID,
        adapter_id="uxm",
        session_token=SESSION_TOKEN,
        remote_session_acquired_confirmed=True,
        transport_session_released_confirmed=True,
        front_panel_local_confirmed=None,
        warnings=(),
    )


def test_release_finalizes_only_an_explicitly_frozen_diagnostic_execution():
    execution = _execution(qualification=_diagnostic_qualification())

    state = persist_execution_base_station_release(
        _Db(execution),
        execution.id,
        attempt_id=ATTEMPT_ID,
        outcome=SimpleNamespace(base_station_release=_release()),
    )

    assert state == "completed"
    assert execution.config["base_station_execution_evidence"][
        "current_measurement_attempt_state"
    ] == "completed"


@pytest.mark.parametrize(
    "qualification",
    [
        None,
        {"classification": "diagnostic"},
        {**_diagnostic_qualification(), "classification": "formal"},
    ],
)
def test_missing_tampered_or_non_diagnostic_qualification_cannot_relax_terminal_gate(
    qualification,
):
    execution = _execution(qualification=qualification)

    state = persist_execution_base_station_release(
        _Db(execution),
        execution.id,
        attempt_id=ATTEMPT_ID,
        outcome=SimpleNamespace(base_station_release=_release()),
    )

    assert state == "failed"
