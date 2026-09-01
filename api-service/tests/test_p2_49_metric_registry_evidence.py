from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.hal.base_station import (
    BaseStationCleanupResult,
    BaseStationMetricObservation,
    BaseStationMeasurementWindow,
)
from app.hal.base_station_compatibility import (
    build_measure_execution_requirements,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.services.execution_scpi_evidence import (
    append_base_station_measurement_window,
    begin_execution_base_station_measurement,
    initialize_base_station_execution_evidence,
)
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota.base_station_execution_evidence import (
    parse_base_station_execution_evidence,
)
from tests.p1_73c_evidence_fixtures import POSITION
from tests.test_p1_73c_base_station_evidence_writer import (
    _CmwDriver,
    _execution as _new_execution,
    _frozen,
    _request,
)
from tests.test_p1_73c_base_station_window_writer import (
    _Db,
    _execution,
)
from tests.test_p2_48_measurement_window_evidence import _trust_window


def _registry():
    return RealCmw500Driver(
        "cmw", {"ip_address": "192.0.2.10"}
    ).resolve_metric_registry()


def _registered_window() -> BaseStationMeasurementWindow:
    legacy = _trust_window()
    lifecycle_ids = ("life-1", "metric-throughput", "metric-bler")
    trust = replace(
        legacy.trust,
        stages=tuple(
            replace(stage, exchange_ids=lifecycle_ids)
            for stage in legacy.trust.stages
        ),
        exchange_ids=lifecycle_ids,
    )
    registry = _registry()
    values = {
        "dl_bler_percent": (0.4, "metric-bler"),
        "dl_throughput_mbps": (96.5, "metric-throughput"),
    }
    observations = tuple(
        BaseStationMetricObservation(
            schema_version=1,
            registry=registry,
            registry_digest=registry.digest,
            key=metric.key,
            scope="pcell",
            value=values[metric.key][0],
            simulated=False,
            exchange_ids=(values[metric.key][1],),
            reason="current-window instrument readback",
        )
        for metric in registry.metrics
    )
    return replace(
        legacy,
        evidence=(
            legacy.evidence[0].model_copy(
                update={"exchange_ids": list(lifecycle_ids)}
            ),
        ),
        trust=trust,
        metric_registry=registry,
        metric_observations=observations,
    )


def test_initial_writer_freezes_exact_adapter_metric_registry():
    execution = _new_execution()

    saved = initialize_base_station_execution_evidence(
        execution,
        frozen_adapter=_frozen(),
        requested_config=_request(),
        requested_positions=[POSITION],
        driver=_CmwDriver(),
    )

    registry = _registry()
    assert saved["metric_registry_contract_version"] == 1
    assert saved["metric_registry"] == {
        "schema_version": 1,
        "adapter_id": "cmw500",
        "profile_id": "cmw500_lte",
        "metrics": [
            metric.model_dump(mode="json") for metric in registry.metrics
        ],
        "digest": registry.digest,
    }


def test_execution_entry_freezes_uxm_registry_before_measurement_io(monkeypatch):
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services import execution_scpi_evidence as module
    from app.services.mimo_ota.executors import _helpers

    calls: list[tuple[str, object]] = []
    legacy_requirements = build_measure_execution_requirements(
        "nr5g"
    ).model_dump(mode="json")
    execution = SimpleNamespace(
        id="execution-uxm",
        config={
            "base_station_adapter_profile_freeze": {
                "resolution": {"adapter": "uxm"},
                "compatibility": {"requirements": legacy_requirements},
            }
        },
    )
    test_case = SimpleNamespace(
        configuration=MIMOOTAConfiguration().model_dump(mode="json")
    )
    driver = object()
    db = SimpleNamespace(commit=lambda: calls.append(("commit", None)))

    def initialize(target, **kwargs):
        calls.append(("initialize", kwargs["driver"]))
        assert target is execution

    def reject_modern_loader(_execution):
        raise AssertionError(
            "pre-P2-54 null profile must use the legacy TestCase"
        )

    monkeypatch.setattr(
        module, "initialize_base_station_execution_evidence", initialize
    )
    monkeypatch.setattr(
        module,
        "begin_base_station_measurement_attempt",
        lambda target_db, execution_id: (
            calls.append(("attempt", execution_id)) or "attempt-uxm"
        ),
    )
    monkeypatch.setattr(
        _helpers,
        "load_mimo_ota_config",
        reject_modern_loader,
    )

    assert begin_execution_base_station_measurement(
        db,
        execution,
        test_case,
        driver=driver,
    ) == "attempt-uxm"
    assert calls == [
        ("initialize", driver),
        ("attempt", "execution-uxm"),
        ("commit", None),
    ]


def test_current_writer_persists_registered_observations_not_legacy_aliases():
    execution = _execution()
    evidence = execution.config["base_station_execution_evidence"]
    registry = _registry()
    evidence.update(
        measurement_window_contract_version=1,
        metric_registry_contract_version=1,
        metric_registry={
            "schema_version": 1,
            "adapter_id": registry.adapter_id,
            "profile_id": registry.profile_id,
            "metrics": [
                metric.model_dump(mode="json") for metric in registry.metrics
            ],
            "digest": registry.digest,
        },
    )
    window = _registered_window()
    # Prove the writer consumes observations instead of these legacy mirrors.
    window.metrics.dl_throughput_mbps = 999.0
    window.metrics.dl_bler = 999.0

    append_base_station_measurement_window(
        _Db(execution),
        execution.id,
        attempt_id="attempt-new",
        lease_identity=ActiveBaseStationLeaseIdentity(
            lease_id="lease-new",
            measurement_attempt_id="attempt-new",
            adapter_id="cmw500",
            session_token="session-new",
        ),
        position=POSITION,
        ue_link_state="connected",
        window=window,
        cleanup=BaseStationCleanupResult(True, True, ()),
    )

    row = execution.config["base_station_execution_evidence"][
        "measurement_windows"
    ][0]
    assert row["metric_registry_digest"] == registry.digest
    assert row["metrics"]["dl_throughput_mbps"] == {
        "measurement_attempt_id": "attempt-new",
        "session_token": "session-new",
        "registry_digest": registry.digest,
        "scope": "pcell",
        "direction": "downlink",
        "value": 96.5,
        "unit": "mbps",
        "evidence": "authoritative",
        "source_reference": registry.capability(
            "dl_throughput_mbps"
        ).source_reference,
        "simulated": False,
        "reason": "current-window instrument readback",
        "exchange_ids": ["metric-throughput"],
    }
    assert row["metrics"]["dl_bler_percent"]["value"] == 0.4


def test_current_registry_contract_rejects_registry_or_observation_drift():
    execution = _execution()
    evidence = execution.config["base_station_execution_evidence"]
    registry = _registry()
    evidence.update(
        measurement_window_contract_version=1,
        metric_registry_contract_version=1,
        metric_registry={
            "schema_version": 1,
            "adapter_id": registry.adapter_id,
            "profile_id": registry.profile_id,
            "metrics": [
                metric.model_dump(mode="json") for metric in registry.metrics
            ],
            "digest": registry.digest,
        },
    )
    window = _registered_window()
    drifted = replace(
        window.metric_observations[0],
        value=None,
        exchange_ids=(),
        reason="unavailable",
    )
    window = replace(
        window,
        metric_observations=(drifted, *window.metric_observations[1:]),
    )
    # A legitimate unavailable value remains explicit and must not be filled
    # from ThroughputMetrics or any other adapter alias.
    append_base_station_measurement_window(
        _Db(execution),
        execution.id,
        attempt_id="attempt-new",
        lease_identity=ActiveBaseStationLeaseIdentity(
            lease_id="lease-new",
            measurement_attempt_id="attempt-new",
            adapter_id="cmw500",
            session_token="session-new",
        ),
        position=POSITION,
        ue_link_state="connected",
        window=window,
        cleanup=BaseStationCleanupResult(True, True, ()),
    )
    stored = execution.config["base_station_execution_evidence"]
    assert stored["measurement_windows"][0]["metrics"][
        window.metric_observations[0].key
    ]["value"] is None

    malformed = deepcopy(stored)
    malformed["metric_registry"]["digest"] = "wrong"
    assert parse_base_station_execution_evidence(malformed) is None


def test_historical_evidence_keeps_registry_fields_absent():
    execution = _execution()
    value = deepcopy(execution.config["base_station_execution_evidence"])

    assert "metric_registry_contract_version" not in value
    assert "metric_registry" not in value
    assert parse_base_station_execution_evidence(value) == value

    value["metric_registry_contract_version"] = None
    assert parse_base_station_execution_evidence(value) is None
