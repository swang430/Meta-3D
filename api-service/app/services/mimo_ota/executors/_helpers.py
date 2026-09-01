"""Shared helpers for MIMO_OTA executors.

Cross-step state is persisted on `TestExecution.measurements` keyed by phase
name (precheck / reference / measure / analysis / report). Earlier phases
write; later phases read. Keeping this in one column matches the VRT pattern.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from app.models.test_plan import TestExecution
from app.schemas.mimo_ota.config import MIMOOTAConfiguration


def get_phase_results(execution: TestExecution) -> Dict[str, Dict[str, Any]]:
    """Return the per-phase result blob, initializing it on first access."""
    if execution.measurements is None:
        execution.measurements = {}
    if "phases" not in execution.measurements:
        execution.measurements["phases"] = {}
    return execution.measurements["phases"]


def write_phase_result(
    execution: TestExecution, phase_key: str, payload: Dict[str, Any]
) -> None:
    """Persist one phase's output. Caller is responsible for db.commit()."""
    from sqlalchemy.orm.attributes import flag_modified

    phases = get_phase_results(execution)
    phases[phase_key] = payload
    # In-place mutation of JSON column — SQLAlchemy's default change tracking
    # does NOT detect dict-internal edits, so explicitly flag the column dirty.
    flag_modified(execution, "measurements")


def read_phase_result(execution: TestExecution, phase_key: str) -> Dict[str, Any]:
    """Pull a previous phase's results; raises if missing."""
    phases = get_phase_results(execution)
    if phase_key not in phases:
        raise RuntimeError(
            f"Required upstream phase '{phase_key}' has no results — "
            "executor order may have been violated."
        )
    return phases[phase_key]


def load_mimo_ota_config(execution: TestExecution) -> MIMOOTAConfiguration:
    """Fetch + validate the MIMOOTAConfiguration from the bound TestCase.

    `execution.test_case_id` is required. We don't lazy-load via relationship
    because executions can be created without a TestCase in some edge cases;
    raise loud and clear if that happened for an MIMO_OTA flow.
    """
    if execution.test_case_id is None:
        raise RuntimeError(
            "MIMO_OTA execution has no test_case_id — factory must bind one"
        )
    # Lazy import to avoid circular dependencies (test_plan models import this module's domain)
    from app.models.test_plan import TestCase

    session = _session_for(execution)
    tc = session.query(TestCase).filter(TestCase.id == execution.test_case_id).first()
    if tc is None or tc.configuration is None:
        raise RuntimeError(
            f"TestCase {execution.test_case_id} missing or has empty configuration"
        )
    payload = dict(tc.configuration)
    execution_config = execution.config if isinstance(execution.config, dict) else {}
    from app.services.base_station_adapter_profile import (
        FREEZE_CONFIG_KEY,
        MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    )

    frozen = execution_config.get(FREEZE_CONFIG_KEY)
    if isinstance(frozen, dict):
        if MIMO_OTA_CONFIGURATION_FREEZE_KEY in frozen:
            snapshot = frozen[MIMO_OTA_CONFIGURATION_FREEZE_KEY]
            if not isinstance(snapshot, dict):
                raise RuntimeError("frozen MIMO OTA configuration is malformed")
            payload = dict(snapshot)
        else:
            compatibility = frozen.get("compatibility")
            requirements = (
                compatibility.get("requirements")
                if isinstance(compatibility, dict)
                else None
            )
            if isinstance(requirements, dict) and "mac_profile" in requirements:
                raise RuntimeError("frozen MIMO OTA configuration is missing")
    # P2-45: the calibration gate belongs to this immutable execution, not to
    # the shared TestCase row.  A later policy/certification change or a
    # concurrent execution must never relabel an already-frozen run.  Legacy
    # executions without a qualification envelope keep their stored config.
    from app.services.execution_evidence_outcome import (
        project_execution_evidence_outcome,
    )

    outcome = project_execution_evidence_outcome(execution)
    if outcome.qualification_classification != "legacy":
        payload["precheck_strict_cal"] = (
            outcome.qualification_classification == "formal"
            and outcome.compatibility_classification
            not in {"diagnostic", "invalid"}
        )
    return MIMOOTAConfiguration.model_validate(payload)


def _session_for(execution: TestExecution):
    """Best-effort retrieval of the SQLAlchemy session that owns this row."""
    from sqlalchemy.orm import object_session

    sess = object_session(execution)
    if sess is None:
        raise RuntimeError(
            f"TestExecution {execution.id} is detached; cannot resolve session"
        )
    return sess


def stddev(values: list) -> float:
    """Sample standard deviation; 0.0 for n<2."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(var)
