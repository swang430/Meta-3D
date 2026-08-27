from __future__ import annotations

from copy import deepcopy
import hashlib
import json


REQUESTED_CONFIG = {
    "radio_technology": "lte",
    "band": "B3",
    "duplex": "fdd",
    "lte_dl_earfcn": 1300,
    "lte_transmission_mode": "TM3",
    "bandwidth_mhz": 20.0,
    "mimo_layers": 2,
}
POSITION = {"azimuth_deg": 0.0, "elevation_deg": 0.0}


def _digest(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def valid_cmw_evidence() -> dict:
    route = {
        "pcc_bb_board": "BB1",
        "rx_connector": "RF1C",
        "rx_converter": "RX1",
        "tx1_connector": "RF1C",
        "tx1_converter": "TX1",
        "tx2_connector": "RF2C",
        "tx2_converter": "TX2",
    }
    config_digest = _digest(REQUESTED_CONFIG)
    route_digest = _digest(route)
    return {
        "schema_version": 1,
        "execution_id": "execution-1",
        "adapter": "cmw500",
        "execution_mode": "real",
        "identity": {
            "adapter": "cmw500",
            "model": "CMW",
            "firmware_version": "3.5.40",
            "options": ["CMW-KS500", "CMW-KS520"],
            "instrument_connection_id": "connection-1",
            "adapter_profile_digest": "profile-digest",
        },
        "formal_capability_approval": {
            "schema_version": 1,
            "status": "configured",
            "instrument_connection_id": "connection-1",
            "capability": "cmw500_lte_2x2",
            "enabled": True,
            "updated_at": "2026-08-26T08:00:00Z",
        },
        "mode": "dispatch",
        "config_confirmed": True,
        "route_confirmed": True,
        "requested_config": {
            "payload": deepcopy(REQUESTED_CONFIG),
            "digest": config_digest,
        },
        "requested_route": {
            "payload": deepcopy(route),
            "digest": route_digest,
        },
        "applied_route": {
            "payload": deepcopy(route),
            "digest": route_digest,
        },
        "requested_positions": [deepcopy(POSITION)],
        "current_measurement_attempt_id": "attempt-1",
        "current_measurement_attempt_state": "completed",
        "measurement_windows": [
            {
                "window_id": "window-1",
                "measurement_attempt_id": "attempt-1",
                "lease_id": "lease-1",
                "adapter": "cmw500",
                "session_token": "session-1",
                "config_digest": config_digest,
                "route_digest": route_digest,
                "position": deepcopy(POSITION),
                "ue_link_state": "connected",
                "started_at": "2026-08-26T08:00:01Z",
                "completed_at": "2026-08-26T08:00:02Z",
                "preclear_off_confirmed": True,
                "running_confirmed": True,
                "ready_confirmed": True,
                "closed_off_confirmed": True,
                "cleanup": {
                    "stop_signaling_confirmed": True,
                    "safe_idle_confirmed": True,
                    "warnings": [],
                },
                "lifecycle_exchange_ids": ["life-1", "life-2"],
                "metrics": {
                    "dl_throughput_mbps": {
                        "measurement_attempt_id": "attempt-1",
                        "session_token": "session-1",
                        "value": 96.5,
                        "unit": "Mbps",
                        "exchange_ids": ["metric-throughput"],
                    },
                    "dl_bler_percent": {
                        "measurement_attempt_id": "attempt-1",
                        "session_token": "session-1",
                        "value": 0.4,
                        "unit": "%",
                        "exchange_ids": ["metric-bler"],
                    },
                },
            }
        ],
        "control_releases": [
            {
                "measurement_attempt_id": "attempt-1",
                "lease_id": "lease-1",
                "adapter_id": "cmw500",
                "session_token": "session-1",
                "remote_session_acquired_confirmed": True,
                "transport_session_released_confirmed": True,
                "front_panel_local_confirmed": None,
                "warnings": ["front panel Local state is not instrument-confirmed"],
            }
        ],
        "exchange_ids": [
            "life-1",
            "life-2",
            "metric-throughput",
            "metric-bler",
        ],
    }
