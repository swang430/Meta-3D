"""P1-59：CA 正式吞吐必须来自所有 NR cells 的聚合真值。"""

from __future__ import annotations

import asyncio

import pytest

from app.hal.base_station import ThroughputMetrics
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import UxmLteNrIratProfile


@pytest.fixture
def driver() -> RealUxmDriver:
    return RealUxmDriver(
        "uxm-irat",
        {"ip": "10.0.0.2", "uxm_profile": "irat"},
    )


def _stub_queries(driver: RealUxmDriver, responses: dict[str, str]) -> list[str]:
    queries: list[str] = []

    def _do_query(command: str, **_kwargs) -> str:
        queries.append(command)
        return responses.get(command, "")

    driver._do_query = _do_query  # type: ignore[method-assign]
    driver._do_write = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    return queries


def test_irat_profile_declares_vendor_sourced_all_nr_queries() -> None:
    assert UxmLteNrIratProfile.MEAS_TPUT_DL_OTA_ALL == (
        "BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:ALL?"
    )
    assert UxmLteNrIratProfile.MEAS_TPUT_UL_OTA_ALL == (
        "BSE:MEASure:NR5G:BTHRoughput:UL:THRoughput:OTA:ALL?"
    )


def test_throughput_scope_is_part_of_the_serialized_contract() -> None:
    metrics = ThroughputMetrics(
        dl_throughput_mbps=0.0,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
    )

    assert metrics.to_dict()["throughput_scope"] == "pcell"


def test_single_carrier_reads_only_per_cell_throughput(
    driver: RealUxmDriver,
) -> None:
    dl_command = UxmLteNrIratProfile.MEAS_TPUT_DL_OTA.format(cell="CELL1")
    ul_command = UxmLteNrIratProfile.MEAS_TPUT_UL_OTA.format(cell="CELL1")
    queries = _stub_queries(
        driver,
        {
            dl_command: "10,1000000,0,0,2000000,0",
            ul_command: "10,3000000,0,0,4000000,0",
        },
    )

    metrics = asyncio.run(
        driver.get_throughput_metrics(
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        )
    )

    assert dl_command in queries
    assert ul_command in queries
    assert not any("THRoughput:OTA:ALL?" in command for command in queries)
    assert metrics.throughput_scope == ThroughputMetrics.SCOPE_PCELL
    assert metrics.dl_throughput_mbps == pytest.approx(2.0)
    assert metrics.ul_throughput_mbps == pytest.approx(4.0)


def test_ca_reads_only_all_nr_throughput(driver: RealUxmDriver) -> None:
    dl_command = UxmLteNrIratProfile.MEAS_TPUT_DL_OTA_ALL
    ul_command = UxmLteNrIratProfile.MEAS_TPUT_UL_OTA_ALL
    queries = _stub_queries(
        driver,
        {
            dl_command: "10,5000000,0,0,6000000,0",
            ul_command: "10,7000000,0,0,8000000,0",
        },
    )

    metrics = asyncio.run(
        driver.get_throughput_metrics(
            throughput_scope=ThroughputMetrics.SCOPE_NR_ALL_CELLS,
        )
    )

    assert dl_command in queries
    assert ul_command in queries
    assert not any("THRoughput:OTA:CELL1?" in command for command in queries)
    assert metrics.throughput_scope == ThroughputMetrics.SCOPE_NR_ALL_CELLS
    assert metrics.dl_throughput_mbps == pytest.approx(6.0)
    assert metrics.ul_throughput_mbps == pytest.approx(8.0)


def test_missing_all_nr_queries_never_fall_back_to_pcell(
    driver: RealUxmDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(UxmLteNrIratProfile, "MEAS_TPUT_DL_OTA_ALL", None)
    monkeypatch.setattr(UxmLteNrIratProfile, "MEAS_TPUT_UL_OTA_ALL", None)
    queries = _stub_queries(
        driver,
        {
            UxmLteNrIratProfile.MEAS_TPUT_DL_OTA.format(cell="CELL1"):
                "10,9000000,0,0,10000000,0",
            UxmLteNrIratProfile.MEAS_TPUT_UL_OTA.format(cell="CELL1"):
                "10,11000000,0,0,12000000,0",
        },
    )

    metrics = asyncio.run(
        driver.get_throughput_metrics(
            throughput_scope=ThroughputMetrics.SCOPE_NR_ALL_CELLS,
        )
    )

    assert not any("THRoughput:OTA" in command for command in queries)
    assert metrics.dl_throughput_mbps is None
    assert metrics.ul_throughput_mbps is None
    assert metrics.kpi_valid["dl_throughput"] is False
    assert metrics.kpi_valid["ul_throughput"] is False
    assert metrics.throughput_scope == ThroughputMetrics.SCOPE_UNKNOWN
