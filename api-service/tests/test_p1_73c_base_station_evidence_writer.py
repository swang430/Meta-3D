from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest

from app.hal.base_station import BaseStationIdentity, BaseStationRequestedConfig
from app.models.test_plan import TestExecution
from app.services.execution_scpi_evidence import (
    initialize_base_station_execution_evidence,
)


ROUTE = {
    "pcc_bb_board": "BB1",
    "rx_connector": "RF1C",
    "rx_converter": "RX1",
    "tx1_connector": "RF1C",
    "tx1_converter": "TX1",
    "tx2_connector": "RF2C",
    "tx2_converter": "TX2",
}


class _CmwDriver:
    adapter_id = "cmw500"
    simulated = False
    identity_snapshot_verified = True

    def get_base_station_identity(self):
        return BaseStationIdentity(
            adapter_id="cmw500",
            model="CMW",
            firmware_version="3.5.40",
            options=("CMW-KS500", "CMW-KS520"),
        )


def _frozen(*, enabled: bool = True):
    value = {
        "schema_version": 1,
        "resolution": {
            "schema_version": 1,
            "adapter": "cmw500",
            "status": "configured",
            "execution_mode": "real",
            "profile": {
                "schema_version": 1,
                "adapter": "cmw500",
                "lte_2x2_internal_route": ROUTE,
            },
        },
        "category_id": "category-1",
        "instrument_model_id": "model-1",
        "instrument_connection_id": "connection-1",
        "lab_profile_id": "lab-1",
        "expected_driver_module": __name__,
        "expected_driver_name": "_CmwDriver",
        "expected_driver_connection": {
            "host": "192.0.2.10",
            "port": 4880,
            "resource": None,
        },
        "cmw500_lte_2x2_formal_capability": {
            "schema_version": 1,
            "instrument_connection_id": "connection-1",
            "enabled": enabled,
            "updated_at": "2026-08-26T08:00:00+00:00",
        },
    }
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**value, "digest": hashlib.sha256(encoded).hexdigest()}


def _request():
    return BaseStationRequestedConfig(
        radio_technology="lte",
        channel_kind="lte_dl_earfcn",
        frequency_mhz=1805.0,
        bandwidth_mhz=20.0,
        band="B3",
        duplex="fdd",
        nr_arfcn=None,
        lte_dl_earfcn=1300,
        subcarrier_spacing_khz=None,
        mimo_layers=2,
        downlink_power_dbm=-50.0,
    )


def _execution():
    return TestExecution(
        id=uuid4(), status="running", executed_by="test", config={}
    )


def test_initial_writer_uses_only_frozen_scope_and_verified_driver_identity():
    execution = _execution()

    saved = initialize_base_station_execution_evidence(
        execution,
        frozen_adapter=_frozen(),
        requested_config=_request(),
        requested_positions=[
            {"azimuth_deg": 0.0, "elevation_deg": 0.0},
            {"azimuth_deg": 90.0, "elevation_deg": 0.0},
        ],
        driver=_CmwDriver(),
    )

    assert saved["execution_id"] == str(execution.id)
    assert saved["adapter"] == "cmw500"
    assert saved["identity"] == {
        "adapter": "cmw500",
        "model": "CMW",
        "firmware_version": "3.5.40",
        "options": ["CMW-KS500", "CMW-KS520"],
        "instrument_connection_id": "connection-1",
        "adapter_profile_digest": _frozen()["digest"],
    }
    assert saved["formal_capability_approval"]["enabled"] is True
    assert saved["requested_config"]["payload"]["lte_dl_earfcn"] == 1300
    assert saved["requested_positions"] == [
        {"azimuth_deg": 0.0, "elevation_deg": 0.0},
        {"azimuth_deg": 90.0, "elevation_deg": 0.0},
    ]
    assert saved["config_confirmed"] is False
    assert saved["route_confirmed"] is False
    assert saved["requested_route"]["payload"] == ROUTE
    assert saved["applied_route"] is None
    assert saved["current_measurement_attempt_id"] is None
    assert saved["measurement_windows"] == []
    assert saved["control_releases"] == []


def test_initial_writer_is_idempotent_but_never_rewrites_execution_scope():
    execution = _execution()
    kwargs = {
        "frozen_adapter": _frozen(),
        "requested_config": _request(),
        "requested_positions": [{"azimuth_deg": 0.0, "elevation_deg": 0.0}],
        "driver": _CmwDriver(),
    }
    first = initialize_base_station_execution_evidence(execution, **kwargs)
    second = initialize_base_station_execution_evidence(execution, **kwargs)
    assert second == first

    with pytest.raises(ValueError, match="immutable scope"):
        initialize_base_station_execution_evidence(
            execution,
            **{
                **kwargs,
                "requested_positions": [
                    {"azimuth_deg": 180.0, "elevation_deg": 0.0}
                ],
            },
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda frozen, driver: frozen["resolution"].update(adapter="uxm"),
        lambda frozen, driver: setattr(driver, "identity_snapshot_verified", False),
        lambda frozen, driver: frozen[
            "cmw500_lte_2x2_formal_capability"
        ].update(instrument_connection_id="other"),
    ],
)
def test_initial_writer_rejects_mismatched_or_unverified_server_sources(mutation):
    execution = _execution()
    frozen = _frozen()
    driver = _CmwDriver()
    mutation(frozen, driver)

    with pytest.raises(ValueError):
        initialize_base_station_execution_evidence(
            execution,
            frozen_adapter=frozen,
            requested_config=_request(),
            requested_positions=[{"azimuth_deg": 0.0, "elevation_deg": 0.0}],
            driver=driver,
        )
