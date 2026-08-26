from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.hal.base_station import BaseStationControlReleaseResult
from app.models.test_plan import TestExecution
from app.services.execution_scpi_evidence import (
    append_base_station_control_release,
    begin_base_station_measurement_attempt,
    persist_execution_base_station_release,
    set_base_station_measurement_attempt_state,
)
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence


class _Query:
    def __init__(self, execution):
        self.execution = execution
        self.locked = False

    def filter(self, *_args):
        return self

    def with_for_update(self):
        self.locked = True
        return self

    def one_or_none(self):
        return self.execution

    def first(self):
        return self.execution


class _Db:
    def __init__(self, execution):
        self.query_object = _Query(execution)
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0

    def query(self, _model):
        return self.query_object

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _execution():
    execution = TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )
    evidence = valid_cmw_evidence()
    evidence["execution_id"] = str(execution.id)
    execution.config = {"base_station_execution_evidence": evidence}
    return execution


def test_begin_attempt_locks_row_and_never_falls_back_to_old_completed_attempt():
    execution = _execution()
    old = deepcopy(execution.config["base_station_execution_evidence"])
    db = _Db(execution)

    attempt_id = begin_base_station_measurement_attempt(db, execution.id)

    UUID(attempt_id)
    assert attempt_id != "attempt-1"
    current = execution.config["base_station_execution_evidence"]
    assert current["current_measurement_attempt_id"] == attempt_id
    assert current["current_measurement_attempt_state"] == "running"
    assert current["measurement_windows"] == old["measurement_windows"]
    assert current["control_releases"] == old["control_releases"]
    assert db.query_object.locked is True
    assert db.flushes == 1


def test_running_attempt_rejects_a_second_measurement_before_switching_pointer():
    execution = _execution()
    execution.config["base_station_execution_evidence"][
        "current_measurement_attempt_state"
    ] = "running"
    db = _Db(execution)

    with pytest.raises(ValueError, match="already running"):
        begin_base_station_measurement_attempt(db, execution.id)

    assert execution.config["base_station_execution_evidence"][
        "current_measurement_attempt_id"
    ] == "attempt-1"
    assert db.flushes == 0


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_failed_or_cancelled_current_attempt_remains_current(state):
    execution = _execution()
    db = _Db(execution)
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)

    set_base_station_measurement_attempt_state(
        db, execution.id, attempt_id=attempt_id, state=state
    )

    evidence = execution.config["base_station_execution_evidence"]
    assert evidence["current_measurement_attempt_id"] == attempt_id
    assert evidence["current_measurement_attempt_state"] == state


def test_release_append_is_attempt_and_lease_bound_and_idempotent():
    execution = _execution()
    db = _Db(execution)
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)
    result = BaseStationControlReleaseResult(
        measurement_attempt_id=attempt_id,
        lease_id="lease-new",
        adapter_id="cmw500",
        session_token="session-new",
        remote_session_acquired_confirmed=True,
        transport_session_released_confirmed=True,
        front_panel_local_confirmed=None,
        warnings=("front-panel Local unknown",),
    )

    append_base_station_control_release(db, execution.id, result)
    append_base_station_control_release(db, execution.id, result)

    releases = execution.config["base_station_execution_evidence"]["control_releases"]
    assert [item["lease_id"] for item in releases].count("lease-new") == 1

    conflicting = BaseStationControlReleaseResult(
        **{**result.__dict__, "session_token": "different-session"}
    )
    with pytest.raises(ValueError, match="conflicting control release"):
        append_base_station_control_release(db, execution.id, conflicting)


def test_release_for_non_current_attempt_cannot_complete_current_attempt():
    execution = _execution()
    db = _Db(execution)
    current = begin_base_station_measurement_attempt(db, execution.id)
    old_release = BaseStationControlReleaseResult(
        measurement_attempt_id="attempt-1",
        lease_id="old-extra",
        adapter_id="cmw500",
        session_token="old-session",
        remote_session_acquired_confirmed=True,
        transport_session_released_confirmed=True,
        front_panel_local_confirmed=None,
        warnings=(),
    )

    append_base_station_control_release(db, execution.id, old_release)

    evidence = execution.config["base_station_execution_evidence"]
    assert evidence["current_measurement_attempt_id"] == current
    assert evidence["current_measurement_attempt_state"] == "running"


def _release(attempt_id: str, *, lease_id: str, session_token: str):
    return BaseStationControlReleaseResult(
        measurement_attempt_id=attempt_id,
        lease_id=lease_id,
        adapter_id="cmw500",
        session_token=session_token,
        remote_session_acquired_confirmed=True,
        transport_session_released_confirmed=True,
        front_panel_local_confirmed=None,
        warnings=("front-panel Local unknown",),
    )


def test_release_cannot_complete_attempt_without_matching_window_and_cleanup():
    execution = _execution()
    db = _Db(execution)
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)

    persist_execution_base_station_release(
        db,
        execution.id,
        attempt_id=attempt_id,
        outcome=SimpleNamespace(
            base_station_release=_release(
                attempt_id, lease_id="lease-new", session_token="session-new"
            )
        ),
    )

    evidence = execution.config["base_station_execution_evidence"]
    assert evidence["current_measurement_attempt_id"] == attempt_id
    assert evidence["current_measurement_attempt_state"] == "failed"


def test_matching_window_cleanup_and_release_complete_exact_current_attempt():
    execution = _execution()
    db = _Db(execution)
    attempt_id = begin_base_station_measurement_attempt(db, execution.id)
    evidence = execution.config["base_station_execution_evidence"]
    window = deepcopy(evidence["measurement_windows"][0])
    window.update(
        window_id="window-new",
        measurement_attempt_id=attempt_id,
        lease_id="lease-new",
        session_token="session-new",
    )
    for metric in window["metrics"].values():
        metric["measurement_attempt_id"] = attempt_id
        metric["session_token"] = "session-new"
    evidence["measurement_windows"].append(window)

    persist_execution_base_station_release(
        db,
        execution.id,
        attempt_id=attempt_id,
        outcome=SimpleNamespace(
            base_station_release=_release(
                attempt_id, lease_id="lease-new", session_token="session-new"
            )
        ),
    )

    current = execution.config["base_station_execution_evidence"]
    assert current["current_measurement_attempt_id"] == attempt_id
    assert current["current_measurement_attempt_state"] == "completed"
