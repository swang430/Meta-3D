"""P1-73C Task 16: UXM and CMW publish one vendor-neutral result shape."""

from copy import deepcopy

from app.services.mimo_ota.base_station_execution_evidence import (
    project_base_station_metrics_by_position,
)
from tests.p1_73c_evidence_fixtures import (
    POSITION,
    REQUESTED_CONFIG,
    valid_cmw_evidence,
)


def _valid_uxm_evidence() -> dict:
    evidence = deepcopy(valid_cmw_evidence())
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
    return evidence


def _public_projection(evidence: dict) -> list[dict]:
    rows = project_base_station_metrics_by_position(
        evidence,
        expected_config=REQUESTED_CONFIG,
        expected_positions=[POSITION],
    )
    return [
        {
            "position": row["position"],
            "dl_throughput_mbps": row["dl_throughput_mbps"].model_dump(mode="json"),
            "dl_bler_percent": row["dl_bler_percent"].model_dump(mode="json"),
        }
        for row in rows
    ]


def test_same_test_case_has_one_public_metric_shape_for_uxm_and_cmw():
    uxm_projection = _public_projection(_valid_uxm_evidence())
    cmw_projection = _public_projection(valid_cmw_evidence())

    assert uxm_projection == cmw_projection
    assert set(cmw_projection[0]) == {
        "position",
        "dl_throughput_mbps",
        "dl_bler_percent",
    }
    serialized = repr(cmw_projection)
    assert "requested_route" not in serialized
    assert "formal_capability_approval" not in serialized
    assert "cmw500" not in serialized.lower()


def test_adapter_specific_fields_remain_inside_the_versioned_evidence_envelope():
    execution_config = {
        "base_station_execution_evidence": valid_cmw_evidence(),
        "mimo_ota_theoretical_peak_throughput_mbps": 100.0,
    }

    assert execution_config["base_station_execution_evidence"]["schema_version"] == 1
    assert "requested_route" not in {
        key for key in execution_config if key != "base_station_execution_evidence"
    }
    assert "formal_capability_approval" not in {
        key for key in execution_config if key != "base_station_execution_evidence"
    }
