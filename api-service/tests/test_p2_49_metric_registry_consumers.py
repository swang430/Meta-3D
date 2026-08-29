from __future__ import annotations

from copy import deepcopy

import pytest
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
from app.services.report_service import (
    _base_station_projection_is_sanitized,
    build_base_station_metric_projection_attestation,
)
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

    attestation = build_base_station_metric_projection_attestation(
        evidence,
        payload,
    )
    assert _base_station_projection_is_sanitized(payload, attestation) is True
    drifted = deepcopy(payload)
    drifted[0]["dl_throughput_mbps"]["formal_value"] = 1.0
    assert _base_station_projection_is_sanitized(drifted, attestation) is False


def test_report_projection_validator_accepts_registry_without_legacy_bler_metric():
    evidence = _current_registry_evidence()
    registry = evidence["metric_registry"]
    for metric in registry["metrics"]:
        if metric["key"] == "dl_bler_percent":
            metric["key"] = "dl_bler_ratio"
            metric["unit"] = "ratio"
    registry["metrics"] = sorted(registry["metrics"], key=lambda item: item["key"])
    registry_payload = {
        key: value for key, value in registry.items() if key != "digest"
    }
    registry["digest"] = canonical_snapshot_digest(registry_payload)
    window = evidence["measurement_windows"][0]
    window["metric_registry_digest"] = registry["digest"]
    for metric in window["metrics"].values():
        metric["registry_digest"] = registry["digest"]
    bler = window["metrics"].pop("dl_bler_percent")
    bler["unit"] = "ratio"
    window["metrics"]["dl_bler_ratio"] = bler
    rows = project_base_station_metrics_by_position(
        evidence,
        expected_config=REQUESTED_CONFIG,
        expected_positions=[POSITION],
        execution_config=_formal_execution_config(evidence),
    )
    row = rows[0]
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
    ]

    attestation = build_base_station_metric_projection_attestation(
        evidence,
        payload,
    )
    assert _base_station_projection_is_sanitized(payload, attestation) is True
    drifted = deepcopy(payload)
    drifted[0]["dl_bler_percent"] = deepcopy(
        drifted[0]["metrics"]["dl_bler_ratio"]
    )
    assert _base_station_projection_is_sanitized(drifted, attestation) is False


def test_report_projection_attestation_rejects_tampered_generic_metric():
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
    attestation = build_base_station_metric_projection_attestation(
        evidence,
        payload,
    )

    assert _base_station_projection_is_sanitized(payload, attestation) is True
    tampered = deepcopy(payload)
    tampered[0]["metrics"]["cqi_index"]["formal_value"] = 99.0
    tampered[0]["metrics"]["cqi_index"]["diagnostic_value"] = 99.0
    assert _base_station_projection_is_sanitized(tampered, attestation) is False

    injected = deepcopy(payload)
    injected[0]["metrics"]["fabricated_metric"] = deepcopy(
        injected[0]["metrics"]["cqi_index"]
    )
    assert _base_station_projection_is_sanitized(injected, attestation) is False
    with pytest.raises(
        ValueError,
        match="projection disagrees with frozen registry",
    ):
        build_base_station_metric_projection_attestation(evidence, injected)


def test_attestation_rejects_trusted_metric_on_non_authoritative_capability():
    """内审 F1 行为门：篡改 registry 能力等级必须被冻结链拒绝。

    实证（2026-08-29 双层旁路探针）：「非 authoritative 能力 + trusted
    指标」在 evidence 冻结链里是**不可表达的状态**——本测试把 cqi_index
    能力降级为 diagnostic_only 并如实重算 registry digest + 窗口
    registry_digest 引用，仍被模型层拒绝（窗口内每条 metric 记录还
    各自钉着 registry digest 与 evidence 等级镜像，单点篡改必然漂移）。
    report_service.build_...attestation 里的显式「trusted 需
    authoritative」判据是合法数据流内不可达的纵深防线（探针证实
    删它两层仍拒），本门锁的是拒绝行为本身，不锁哪一层实现。
    """
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
    # 前置自检：payload 里 cqi_index 确实是 trusted（否则本门测不到目标判据）
    assert payload[0]["metrics"]["cqi_index"]["status"] == "trusted"

    demoted = deepcopy(evidence)
    registry = demoted["metric_registry"]
    for capability in registry["metrics"]:
        if capability["key"] == "cqi_index":
            capability["evidence"] = "diagnostic_only"
    # registry 是 digest 密封的（改能力不重算 digest 会先撞
    # "metric registry digest mismatch"——那是另一道门）；这里如实重算
    # digest，让本门打到目标判据「trusted 需 authoritative」上
    registry["digest"] = canonical_snapshot_digest(
        {
            "schema_version": registry["schema_version"],
            "adapter_id": registry["adapter_id"],
            "profile_id": registry["profile_id"],
            "metrics": registry["metrics"],
        }
    )
    # measurement window（P2-48）同样引用 registry digest，冻结链逐层密封，
    # 一并如实更新——本门要打的是最后那道「trusted 需 authoritative」判据
    for window in demoted.get("measurement_windows", []):
        window["metric_registry_digest"] = registry["digest"]
    with pytest.raises(ValueError, match="semantics drifted"):
        build_base_station_metric_projection_attestation(demoted, payload)
