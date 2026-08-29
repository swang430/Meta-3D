from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    BaseStationSiteCertification,
    _qualification_payload_digest,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    canonical_snapshot_digest,
    evaluate_base_station_metric_trust,
    project_base_station_metrics_by_position,
)
from app.services.report_service import _base_station_projection_is_sanitized
from tests.p1_73c_evidence_fixtures import POSITION, REQUESTED_CONFIG
from tests.test_p2_48_measurement_window_evidence import _current_formal_value


def _current_registry_evidence():
    value = _current_formal_value()
    capabilities = [
        {
            "key": "cqi_index",
            "direction": "downlink",
            "unit": "index",
            "scopes": ["pcell"],
            "evidence": "authoritative",
            "source_reference": "manual §CQI",
        },
        {
            "key": "dl_bler_percent",
            "direction": "downlink",
            "unit": "percent",
            "scopes": ["pcell"],
            "evidence": "authoritative",
            "source_reference": "manual §BLER",
        },
        {
            "key": "dl_throughput_mbps",
            "direction": "downlink",
            "unit": "mbps",
            "scopes": ["pcell"],
            "evidence": "authoritative",
            "source_reference": "manual §throughput",
        },
        {
            "key": "rsrp_raw",
            "direction": "downlink",
            "unit": "raw",
            "scopes": ["pcell"],
            "evidence": "diagnostic_only",
            "source_reference": "manual §UE report",
        },
    ]
    payload = {
        "schema_version": 1,
        "adapter_id": "cmw500",
        "profile_id": "consumer_contract",
        "metrics": capabilities,
    }
    digest = canonical_snapshot_digest(payload)
    value["metric_registry_contract_version"] = 1
    value["metric_registry"] = {**payload, "digest": digest}
    window = value["measurement_windows"][0]
    window["metric_registry_digest"] = digest
    common = {
        "measurement_attempt_id": "attempt-1",
        "session_token": "session-1",
        "registry_digest": digest,
        "scope": "pcell",
        "simulated": False,
        "reason": "current-window instrument readback",
    }
    window["metrics"] = {
        "cqi_index": {
            **common,
            "direction": "downlink",
            "value": 11.5,
            "unit": "index",
            "evidence": "authoritative",
            "source_reference": "manual §CQI",
            "exchange_ids": ["metric-cqi"],
        },
        "dl_bler_percent": {
            **common,
            "direction": "downlink",
            "value": 0.4,
            "unit": "percent",
            "evidence": "authoritative",
            "source_reference": "manual §BLER",
            "exchange_ids": ["metric-bler"],
        },
        "dl_throughput_mbps": {
            **common,
            "direction": "downlink",
            "value": 96.5,
            "unit": "mbps",
            "evidence": "authoritative",
            "source_reference": "manual §throughput",
            "exchange_ids": ["metric-throughput"],
        },
        "rsrp_raw": {
            **common,
            "direction": "downlink",
            "value": 42.0,
            "unit": "raw",
            "evidence": "diagnostic_only",
            "source_reference": "manual §UE report",
            "exchange_ids": ["metric-rsrp"],
        },
    }
    ids = ["life-1", "life-2", "metric-cqi", "metric-bler", "metric-throughput", "metric-rsrp"]
    window["lifecycle_exchange_ids"] = ids
    window["trust"]["exchange_ids"] = ids
    for stage in window["trust"]["stages"]:
        stage["exchange_ids"] = ids
    value["exchange_ids"] = ids
    return value


def _formal_execution_config(evidence):
    certification = BaseStationSiteCertification(
        schema_version=1,
        status="active",
        lab_profile_id="lab-1",
        instrument_connection_id=evidence["identity"]["instrument_connection_id"],
        binding_digest="a" * 64,
        adapter_id=evidence["adapter"],
        model=evidence["identity"]["model"],
        firmware_version=evidence["identity"]["firmware_version"],
        options=tuple(evidence["identity"]["options"]),
        source_execution_id="source-1",
        evidence_digest="b" * 64,
        required_proofs={
            "config_readback": True,
            "route_readback": True,
            "route_not_applicable": False,
            "cleanup": True,
            "transport_release": True,
        },
        certified_by="quality-owner",
        certified_at=datetime.now(timezone.utc),
        reason="site evidence complete",
    )
    qualification = {
        "schema_version": 1,
        "classification": "formal",
        "policy_mode": "formal",
        "policy": None,
        "binding_digest": certification.binding_digest,
        "binding_status": "configured",
        "execution_mode": "real",
        "adapter_id": evidence["adapter"],
        "site_certification": certification.model_dump(mode="json"),
        "site_certification_digest": certification.certification_digest,
        "reasons": [],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    qualification["qualification_digest"] = _qualification_payload_digest(
        qualification
    )
    return {EXECUTION_QUALIFICATION_KEY: qualification}


def test_generic_projection_preserves_every_registered_metric_and_compat_mirrors():
    evidence = _current_registry_evidence()
    rows = project_base_station_metrics_by_position(
        evidence,
        expected_config=REQUESTED_CONFIG,
        expected_positions=[POSITION],
        execution_config=_formal_execution_config(evidence),
    )

    assert set(rows[0]["metrics"]) == {
        "cqi_index",
        "dl_bler_percent",
        "dl_throughput_mbps",
        "rsrp_raw",
    }
    assert rows[0]["metrics"]["cqi_index"].formal_value == 11.5
    assert rows[0]["metrics"]["rsrp_raw"].status == "diagnostic"
    assert rows[0]["metrics"]["rsrp_raw"].formal_value is None
    assert rows[0]["dl_throughput_mbps"] is rows[0]["metrics"][
        "dl_throughput_mbps"
    ]
    assert rows[0]["dl_bler_percent"] is rows[0]["metrics"][
        "dl_bler_percent"
    ]


def test_current_registry_never_falls_back_to_legacy_alias_or_unknown_key():
    evidence = _current_registry_evidence()
    evidence["measurement_windows"][0]["metrics"]["cqi_index"]["value"] = None
    evidence["measurement_windows"][0]["metrics"]["cqi_index"]["exchange_ids"] = []
    config = _formal_execution_config(evidence)

    missing = evaluate_base_station_metric_trust(
        evidence, "cqi_index", REQUESTED_CONFIG, POSITION, execution_config=config
    )
    legacy_alias = evaluate_base_station_metric_trust(
        evidence,
        "rank_indicator",
        REQUESTED_CONFIG,
        POSITION,
        execution_config=config,
    )

    assert missing.formal_value is None
    assert missing.status == "unknown"
    assert legacy_alias.formal_value is None
    assert legacy_alias.reason == "metric_not_declared_in_registry"


def test_report_projection_validator_accepts_generic_map_and_rejects_drift():
    evidence = _current_registry_evidence()
    rows = project_base_station_metrics_by_position(
        evidence,
        expected_config=REQUESTED_CONFIG,
        expected_positions=[POSITION],
        execution_config=_formal_execution_config(evidence),
    )
    payload = [
        {
            "position": row["position"],
            "metrics": {
                key: metric.model_dump(mode="json")
                for key, metric in row["metrics"].items()
            },
            "dl_throughput_mbps": row["dl_throughput_mbps"].model_dump(
                mode="json"
            ),
            "dl_bler_percent": row["dl_bler_percent"].model_dump(mode="json"),
        }
        for row in rows
    ]

    assert _base_station_projection_is_sanitized(payload) is True
    drifted = deepcopy(payload)
    drifted[0]["dl_throughput_mbps"]["formal_value"] = 1.0
    assert _base_station_projection_is_sanitized(drifted) is False


def test_report_projection_validator_accepts_registry_without_legacy_bler_metric():
    evidence = _current_registry_evidence()
    rows = project_base_station_metrics_by_position(
        evidence,
        expected_config=REQUESTED_CONFIG,
        expected_positions=[POSITION],
        execution_config=_formal_execution_config(evidence),
    )
    row = rows[0]
    metrics = {
        key: metric.model_dump(mode="json")
        for key, metric in row["metrics"].items()
    }
    metrics["dl_bler_ratio"] = metrics.pop("dl_bler_percent")
    metrics["dl_bler_ratio"]["unit"] = "ratio"
    legacy_unknown = {
        "status": "unknown",
        "formal_value": None,
        "diagnostic_value": None,
        "unit": None,
        "reason": "metric_not_declared_in_registry",
        "exchange_ids": [],
    }
    payload = [
        {
            "position": row["position"],
            "metrics": metrics,
            "dl_throughput_mbps": row["dl_throughput_mbps"].model_dump(
                mode="json"
            ),
            "dl_bler_percent": legacy_unknown,
        }
    ]

    assert _base_station_projection_is_sanitized(payload) is True
    drifted = deepcopy(payload)
    drifted[0]["dl_bler_percent"] = deepcopy(
        drifted[0]["metrics"]["dl_bler_ratio"]
    )
    assert _base_station_projection_is_sanitized(drifted) is False
