from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import replace

from app.core.logging_config import current_execution_id
from app.hal.base_station import BaseStationCleanupResult
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.scpi_evidence import EvidenceLevel, ScpiExchangeRef
from app.services import execution_scpi_evidence as evidence_service
from app.services.execution_scpi_evidence import (
    append_base_station_measurement_window,
    confirm_base_station_attach,
    confirm_base_station_configuration_and_route,
    finalize_execution_scpi_evidence,
    record_base_station_config_capture,
    record_base_station_throughput_capture,
    register_required_scpi_evidence,
)
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota.executors.measure import MeasureExecutor
from app.services.mimo_ota.base_station_execution_evidence import (
    canonical_snapshot_digest,
)
from tests.p1_73c_evidence_fixtures import POSITION
from tests.test_p1_73c_base_station_window_writer import (
    _Db,
    _config_receipt,
    _execution,
    _route_result,
)
from tests.test_p1_73c_end_to_end_contract import _valid_uxm_evidence
from tests.test_p2_47_base_station_attach_evidence import _receipt as _attach_receipt
from tests.test_p2_49_metric_registry_evidence import (
    _registered_window,
    _registry,
)


def _lease() -> ActiveBaseStationLeaseIdentity:
    return ActiveBaseStationLeaseIdentity(
        lease_id="lease-new",
        measurement_attempt_id="attempt-new",
        adapter_id="cmw500",
        session_token="session-new",
        instrument_id="baseStation",
    )


def _exchange(execution, exchange_id: str, sequence: int) -> ScpiExchangeRef:
    return ScpiExchangeRef(
        exchange_id=exchange_id,
        instrument_id="baseStation",
        operation="query",
        command=f"REDACTED:{sequence}?",
        execution_id=str(execution.id),
        capture_id="capture-cmw",
        sequence=sequence,
        result_type="response",
        response="confirmed",
    )


def _current_cmw_execution(monkeypatch):
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
        attach_operations=[],
    )
    lease = _lease()
    monkeypatch.setattr(
        evidence_service,
        "active_base_station_lease_identity",
        lambda: lease,
    )
    db = _Db(execution)
    confirm_base_station_configuration_and_route(
        db,
        execution.id,
        attempt_id="attempt-new",
        lease_identity=lease,
        config_receipt=_config_receipt(),
        route_receipt=_route_result(),
    )
    confirm_base_station_attach(
        db,
        execution.id,
        attempt_id="attempt-new",
        lease_identity=lease,
        manifest=RealCmw500Driver.adapter_manifest,
        receipt=_attach_receipt("cmw500"),
    )
    window = _registered_window()
    append_base_station_measurement_window(
        db,
        execution.id,
        attempt_id="attempt-new",
        lease_identity=lease,
        position=POSITION,
        ue_link_state="connected",
        window=window,
        cleanup=BaseStationCleanupResult(True, True, ()),
    )
    return execution, lease, window.window_id


def test_measure_no_longer_dispatches_base_station_evidence_by_hasattr():
    source = inspect.getsource(MeasureExecutor.execute)

    assert 'hasattr(base_station, "build_p0_5_config_evidence")' not in source
    assert 'hasattr(base_station, "build_p0_5_throughput_evidence")' not in source


def test_cmw_confirmed_receipts_project_common_e3_and_e4(monkeypatch):
    execution, lease, window_id = _current_cmw_execution(monkeypatch)
    current_execution_id.set(str(execution.id))
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.pcell.config_applied",
        evidence_key="base_station.config_apply",
        requested=1300,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        evidence_key="base_station.dl_throughput",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        required_evidence_level=EvidenceLevel.OUTCOME,
    )
    ids = [
        "config-1",
        "attach-0",
        "attach-1",
        "attach-3",
        "metric-throughput",
    ]
    exchanges = [
        _exchange(execution, exchange_id, index)
        for index, exchange_id in enumerate(ids)
    ]

    record_base_station_config_capture(
        execution,
        requirement_id="base_station.pcell.config_applied",
        requested=1300,
        driver=None,
        exchanges=exchanges,
        manifest=RealCmw500Driver.adapter_manifest,
        attempt_id="attempt-new",
        lease_identity=lease,
    )
    record_base_station_throughput_capture(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=None,
        exchanges=exchanges,
        attempt_id="attempt-new",
        lease_identity=lease,
        window_id=window_id,
    )

    items = {
        item["requirement_id"]: item
        for item in execution.config["scpi_evidence"]["items"]
    }
    config = items["base_station.pcell.config_applied"]
    assert config["instrument"] == "cmw500"
    assert config["evidence_key"] == "base_station.config_apply"
    assert config["evidence_level"] == "E3"
    assert config["verdict"] == "passed"
    assert config["readback"]["lte_dl_earfcn"] == 1300
    throughput = items["base_station.throughput.azimuth.000"]
    assert throughput["instrument"] == "cmw500"
    assert throughput["evidence_key"] == "base_station.dl_throughput"
    assert throughput["evidence_level"] == "E4"
    assert throughput["verdict"] == "passed"
    assert throughput["readback"] == 96.5
    finalized = finalize_execution_scpi_evidence(execution)
    assert finalized.formal_acceptance is True


def test_cmw_projection_rejects_wrong_attempt_and_non_authoritative_metric(
    monkeypatch,
):
    execution, lease, window_id = _current_cmw_execution(monkeypatch)
    current_execution_id.set(str(execution.id))
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        evidence_key="base_station.dl_throughput",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        required_evidence_level=EvidenceLevel.OUTCOME,
    )
    exchange = _exchange(execution, "metric-throughput", 0)

    record_base_station_throughput_capture(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=None,
        exchanges=[exchange],
        attempt_id="attempt-other",
        lease_identity=replace(lease, measurement_attempt_id="attempt-other"),
        window_id=window_id,
    )

    item = execution.config["scpi_evidence"]["items"][0]
    assert item["verdict"] == "unknown"
    assert item["evidence_level"] != "E4"

    raw = deepcopy(execution.config["base_station_execution_evidence"])
    registry = raw["metric_registry"]
    registry["metrics"] = [
        {
            **registry_item,
            **(
                {"evidence": "diagnostic_only"}
                if registry_item["key"] == "dl_throughput_mbps"
                else {}
            ),
        }
        for registry_item in registry["metrics"]
    ]
    registry["digest"] = canonical_snapshot_digest(
        {key: value for key, value in registry.items() if key != "digest"}
    )
    row = raw["measurement_windows"][0]
    row["metric_registry_digest"] = registry["digest"]
    metric = row["metrics"]["dl_throughput_mbps"]
    metric["evidence"] = "diagnostic_only"
    metric["registry_digest"] = registry["digest"]
    execution.config["base_station_execution_evidence"] = raw

    record_base_station_throughput_capture(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=None,
        exchanges=[exchange],
        attempt_id="attempt-new",
        lease_identity=lease,
        window_id=window_id,
    )

    item = execution.config["scpi_evidence"]["items"][0]
    assert item["verdict"] == "unknown"
    assert item["evidence_level"] != "E4"


def test_cmw_projection_rejects_exchanges_from_wrong_instrument(monkeypatch):
    execution, lease, _window_id = _current_cmw_execution(monkeypatch)
    current_execution_id.set(str(execution.id))
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.pcell.config_applied",
        evidence_key="base_station.config_apply",
        requested=1300,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    ids = ["config-1", "attach-0", "attach-1", "attach-3"]
    exchanges = [
        _exchange(execution, exchange_id, index).model_copy(
            update={"instrument_id": "channelEmulator"}
        )
        for index, exchange_id in enumerate(ids)
    ]

    record_base_station_config_capture(
        execution,
        requirement_id="base_station.pcell.config_applied",
        requested=1300,
        driver=None,
        exchanges=exchanges,
        manifest=RealCmw500Driver.adapter_manifest,
        attempt_id="attempt-new",
        lease_identity=lease,
    )

    item = execution.config["scpi_evidence"]["items"][0]
    assert item["verdict"] == "unknown"
    assert "instrument" in item["reason"]


def test_cmw_projection_rejects_lease_attempt_identity_drift(monkeypatch):
    execution, lease, window_id = _current_cmw_execution(monkeypatch)
    current_execution_id.set(str(execution.id))
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.pcell.config_applied",
        evidence_key="base_station.config_apply",
        requested=1300,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        evidence_key="base_station.dl_throughput",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        required_evidence_level=EvidenceLevel.OUTCOME,
    )
    drifted_lease = replace(lease, measurement_attempt_id="attempt-other")
    ids = [
        "config-1",
        "attach-0",
        "attach-1",
        "attach-3",
        "metric-throughput",
    ]
    exchanges = [
        _exchange(execution, exchange_id, index)
        for index, exchange_id in enumerate(ids)
    ]

    record_base_station_config_capture(
        execution,
        requirement_id="base_station.pcell.config_applied",
        requested=1300,
        driver=None,
        exchanges=exchanges,
        manifest=RealCmw500Driver.adapter_manifest,
        attempt_id="attempt-new",
        lease_identity=drifted_lease,
    )
    record_base_station_throughput_capture(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=None,
        exchanges=exchanges,
        attempt_id="attempt-new",
        lease_identity=drifted_lease,
        window_id=window_id,
    )

    items = {
        item["requirement_id"]: item
        for item in execution.config["scpi_evidence"]["items"]
    }
    assert items["base_station.pcell.config_applied"]["verdict"] == "unknown"
    assert items["base_station.throughput.azimuth.000"]["verdict"] == "unknown"


def test_cmw_projection_rejects_confirmed_field_without_exchange_proof(monkeypatch):
    execution, lease, _window_id = _current_cmw_execution(monkeypatch)
    current_execution_id.set(str(execution.id))
    raw = deepcopy(execution.config["base_station_execution_evidence"])
    raw["adapter_operations"][0]["fields"][0]["exchange_ids"] = []
    execution.config["base_station_execution_evidence"] = raw
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.pcell.config_applied",
        evidence_key="base_station.config_apply",
        requested=1300,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    ids = ["config-1", "attach-0", "attach-1", "attach-3"]
    exchanges = [
        _exchange(execution, exchange_id, index)
        for index, exchange_id in enumerate(ids)
    ]

    record_base_station_config_capture(
        execution,
        requirement_id="base_station.pcell.config_applied",
        requested=1300,
        driver=None,
        exchanges=exchanges,
        manifest=RealCmw500Driver.adapter_manifest,
        attempt_id="attempt-new",
        lease_identity=lease,
    )

    item = execution.config["scpi_evidence"]["items"][0]
    assert item["verdict"] == "unknown"


def test_cmw_projection_rejects_window_lifecycle_mirror_drift(monkeypatch):
    execution, lease, window_id = _current_cmw_execution(monkeypatch)
    current_execution_id.set(str(execution.id))
    raw = deepcopy(execution.config["base_station_execution_evidence"])
    raw["measurement_windows"][0]["running_confirmed"] = False
    execution.config["base_station_execution_evidence"] = raw
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        evidence_key="base_station.dl_throughput",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        required_evidence_level=EvidenceLevel.OUTCOME,
    )

    record_base_station_throughput_capture(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=None,
        exchanges=[_exchange(execution, "metric-throughput", 0)],
        attempt_id="attempt-new",
        lease_identity=lease,
        window_id=window_id,
    )

    item = execution.config["scpi_evidence"]["items"][0]
    assert item["verdict"] == "unknown"


def test_malformed_current_evidence_never_falls_back_to_legacy_uxm_builder():
    execution = _execution()
    current_execution_id.set(str(execution.id))
    execution.config["base_station_execution_evidence"]["adapter"] = "malformed"
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.pcell.config_applied",
        evidence_key="base_station.config_apply",
        requested=1300,
        required_evidence_level=EvidenceLevel.APPLIED,
    )
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        evidence_key="base_station.dl_throughput",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        required_evidence_level=EvidenceLevel.OUTCOME,
    )

    class _LegacyBuilderMustNotRun:
        def build_p0_5_config_evidence(self, **_kwargs):
            raise AssertionError("malformed current evidence must not use legacy config")

        def build_p0_5_throughput_evidence(self, **_kwargs):
            raise AssertionError(
                "malformed current evidence must not use legacy throughput"
            )

    driver = _LegacyBuilderMustNotRun()
    record_base_station_config_capture(
        execution,
        requirement_id="base_station.pcell.config_applied",
        requested=1300,
        driver=driver,
        exchanges=[],
    )
    record_base_station_throughput_capture(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=driver,
        exchanges=[],
    )

    items = {
        item["requirement_id"]: item
        for item in execution.config["scpi_evidence"]["items"]
    }
    assert items["base_station.pcell.config_applied"]["verdict"] == "unknown"
    assert items["base_station.throughput.azimuth.000"]["verdict"] == "unknown"


def test_current_uxm_scope_mismatch_cannot_be_rescued_by_catalog_fallback():
    execution = _execution()
    uxm_evidence = _valid_uxm_evidence()
    uxm_evidence["execution_id"] = str(execution.id)
    execution.config["base_station_execution_evidence"] = uxm_evidence
    current_execution_id.set(str(execution.id))
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.pcell.config_applied",
        evidence_key="base_station.config_apply",
        requested=636666,
        required_evidence_level=EvidenceLevel.APPLIED,
    )

    class _LegacyBuilderMustNotRun:
        def build_p0_5_config_evidence(self, **_kwargs):
            raise AssertionError("scope mismatch must not use catalog fallback")

    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-other",
        measurement_attempt_id="attempt-other",
        adapter_id="uxm",
        session_token="session-other",
        instrument_id="baseStation",
    )
    record_base_station_config_capture(
        execution,
        requirement_id="base_station.pcell.config_applied",
        requested=636666,
        driver=_LegacyBuilderMustNotRun(),
        exchanges=[],
        manifest=RealUxmDriver.adapter_manifest,
        attempt_id="attempt-other",
        lease_identity=lease,
    )

    item = execution.config["scpi_evidence"]["items"][0]
    assert item["verdict"] == "unknown"


def test_authoritative_zero_throughput_is_an_outcome_not_missing(monkeypatch):
    execution, lease, window_id = _current_cmw_execution(monkeypatch)
    current_execution_id.set(str(execution.id))
    raw = deepcopy(execution.config["base_station_execution_evidence"])
    raw["measurement_windows"][0]["metrics"]["dl_throughput_mbps"][
        "value"
    ] = 0.0
    execution.config["base_station_execution_evidence"] = raw
    register_required_scpi_evidence(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        evidence_key="base_station.dl_throughput",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        required_evidence_level=EvidenceLevel.OUTCOME,
    )
    exchange = _exchange(execution, "metric-throughput", 0)

    record_base_station_throughput_capture(
        execution,
        requirement_id="base_station.throughput.azimuth.000",
        requested={"azimuth_deg": 0.0, "window_s": 1.0},
        driver=None,
        exchanges=[exchange],
        attempt_id="attempt-new",
        lease_identity=lease,
        window_id=window_id,
    )

    item = execution.config["scpi_evidence"]["items"][0]
    assert item["verdict"] == "passed"
    assert item["evidence_level"] == "E4"
    assert item["readback"] == 0.0
