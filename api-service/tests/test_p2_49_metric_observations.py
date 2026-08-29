from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.hal.base_station import (
    BaseStationMeasurementWindowRequest,
    BaseStationMetricObservation,
    MockBaseStation,
    ThroughputMetrics,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver


@pytest.mark.asyncio
async def test_uxm_reads_bler_as_ratio_and_preserves_cqi_ri_indices(monkeypatch):
    driver = RealUxmDriver(
        "uxm",
        {"ip_address": "192.0.2.11", "uxm_profile": "irat"},
    )

    def query(command: str) -> str:
        upper = command.upper()
        if "THROUGHPUT:DL:THROUGHPUT:OTA" in upper:
            return "1,2000000,1,3,4000000,5"
        if "THROUGHPUT:UL:THROUGHPUT:OTA" in upper:
            return "1,1000000,1,3,3000000,5"
        if "THROUGHPUT:DL:BLER" in upper:
            return "0,0,0,0,0,0,0,0,0.125,0"
        if "THROUGHPUT:UL:BLER" in upper:
            return "0,0,0,0,0.25,0"
        if ":CSI:CQI:" in upper:
            return "100,100,3,15,11.5,12"
        if ":CSI:RI:" in upper:
            return "0,10,30,0,0,0,0,0"
        raise AssertionError(f"unexpected query: {command}")

    monkeypatch.setattr(driver, "_query", query)

    metrics = await driver.get_throughput_metrics(_read_ue_report=False)

    assert metrics.registered_values == {
        "cqi_index": pytest.approx(11.5),
        "dl_bler_ratio": pytest.approx(0.125),
        "dl_throughput_current_mbps": pytest.approx(2.0),
        "dl_throughput_mbps": pytest.approx(4.0),
        "ri_index": pytest.approx(1.75),
        "ul_bler_ratio": pytest.approx(0.25),
        "ul_throughput_current_mbps": pytest.approx(1.0),
        "ul_throughput_mbps": pytest.approx(3.0),
    }
    # Legacy mirrors remain readable, but the registered RI truth is the
    # sourced instrument index and is not relabeled as a layer count.
    assert metrics.dl_bler == pytest.approx(0.125)
    assert metrics.cqi == 12
    assert metrics.rank_indicator == 3


def test_common_observation_builder_binds_each_value_to_its_query_exchange():
    driver = RealUxmDriver(
        "uxm",
        {"ip_address": "192.0.2.11", "uxm_profile": "irat"},
    )
    registry = driver.resolve_metric_registry()
    metrics = ThroughputMetrics(
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        registered_values={
            "dl_throughput_mbps": 4.0,
            "dl_bler_ratio": 0.125,
        },
    )
    exchanges = (
        SimpleNamespace(
            command=driver._cmds.MEAS_TPUT_DL_OTA.format(cell=driver._cell_id),
            exchange_id="dl-throughput-query",
        ),
        SimpleNamespace(
            command=driver._cmds.MEAS_BLER_DL.format(cell=driver._cell_id),
            exchange_id="dl-bler-query",
        ),
    )

    observations = driver.build_metric_observations(
        registry=registry,
        metrics=metrics,
        scope="pcell",
        exchanges=exchanges,
        query_commands={
            "dl_throughput_mbps": driver._cmds.MEAS_TPUT_DL_OTA.format(
                cell=driver._cell_id
            ),
            "dl_bler_ratio": driver._cmds.MEAS_BLER_DL.format(
                cell=driver._cell_id
            ),
        },
        simulated=False,
    )
    by_key = {item.key: item for item in observations}

    assert by_key["dl_throughput_mbps"].exchange_ids == (
        "dl-throughput-query",
    )
    assert by_key["dl_bler_ratio"].exchange_ids == ("dl-bler-query",)
    assert by_key["ul_throughput_mbps"].value is None
    assert by_key["ul_throughput_mbps"].exchange_ids == ()


def test_cmw_registered_values_keep_percent_semantics():
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    registry = driver.resolve_metric_registry()
    metrics = ThroughputMetrics(
        dl_throughput_mbps=10.0,
        dl_bler=2.5,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        registered_values={
            "dl_throughput_mbps": 10.0,
            "dl_bler_percent": 2.5,
        },
    )

    observations = driver.build_metric_observations(
        registry=registry,
        metrics=metrics,
        scope="pcell",
        exchanges=(
            SimpleNamespace(command="CMW:THROUGHPUT?", exchange_id="tput"),
            SimpleNamespace(command="CMW:BLER?", exchange_id="bler"),
        ),
        query_commands={
            "dl_throughput_mbps": "CMW:THROUGHPUT?",
            "dl_bler_percent": "CMW:BLER?",
        },
        simulated=False,
    )

    assert {item.key: item.value for item in observations} == {
        "dl_bler_percent": 2.5,
        "dl_throughput_mbps": 10.0,
    }
    assert {item.key: item.capability.unit for item in observations} == {
        "dl_bler_percent": "percent",
        "dl_throughput_mbps": "mbps",
    }


@pytest.mark.asyncio
async def test_mock_window_emits_complete_simulated_registry_shape():
    driver = MockBaseStation(
        "mock-uxm",
        {"model": "UXM", "uxm_profile": "irat"},
    )
    await driver.start_signaling()
    request = BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope="pcell",
        lifecycle="unavailable",
        cardinality="requested",
        requested_window_count=1,
        expected_window_count=1,
        window_index=0,
    )

    window = await driver.measure_base_station_window(0, request=request)

    assert window.metric_registry is not None
    assert window.metric_registry.profile_id == "mock_lte_nr_irat"
    assert tuple(item.key for item in window.metric_observations) == tuple(
        item.key for item in window.metric_registry.metrics
    )
    assert all(item.simulated is True for item in window.metric_observations)
    assert all(
        item.metric_semantics_confirmed is False
        for item in window.metric_observations
    )


def test_measurement_window_rejects_registry_observation_drift():
    registry = RealCmw500Driver(
        "cmw", {"ip_address": "192.0.2.10"}
    ).resolve_metric_registry()
    other_registry = MockBaseStation(
        "mock-cmw", {"model": "CMW500"}
    ).resolve_metric_registry()
    observation = BaseStationMetricObservation(
        schema_version=1,
        registry=other_registry,
        registry_digest=other_registry.digest,
        key="dl_throughput_mbps",
        scope="pcell",
        value=1.0,
        simulated=True,
        exchange_ids=(),
        reason="simulated",
    )

    from app.hal.base_station import BaseStationMeasurementWindow
    from datetime import datetime, timezone

    with pytest.raises(ValueError, match="registry"):
        BaseStationMeasurementWindow(
            window_id="window",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            metrics=ThroughputMetrics(
                throughput_scope=ThroughputMetrics.SCOPE_PCELL
            ),
            preclear_off_confirmed=False,
            running_confirmed=False,
            ready_confirmed=False,
            closed_off_confirmed=False,
            evidence=(),
            confirmed=False,
            reason="test",
            metric_registry=registry,
            metric_observations=(observation,),
        )
