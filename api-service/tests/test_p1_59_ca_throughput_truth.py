"""P1-59：CA 正式吞吐必须来自所有 NR cells 的聚合真值。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.hal.base_station import ThroughputMetrics
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import UxmLteNrIratProfile
from app.services.mimo_ota.executors.measure import MeasureExecutor
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.report_service import report_has_provenance_trust


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


def _scell(frequency_hz: float = 3.7e9) -> SimpleNamespace:
    return SimpleNamespace(
        frequency_hz=frequency_hz,
        bandwidth_mhz=100,
        subcarrier_spacing_khz=30,
        band="n78",
    )


@pytest.mark.asyncio
async def test_no_scell_needs_no_ca_driver_capability() -> None:
    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        SimpleNamespace(),
        [],
        inherit=False,
        execution_id="single-carrier",
    )

    assert added == []
    assert blocker is None


@pytest.mark.asyncio
async def test_ca_inherit_mode_fails_before_sampling() -> None:
    driver = SimpleNamespace(
        add_secondary_cell=AsyncMock(return_value=True),
        activate_secondary_cells=AsyncMock(return_value=True),
    )

    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [_scell()],
        inherit=True,
        execution_id="ca-inherit",
    )

    assert added == []
    assert blocker and "inherit" in blocker
    driver.add_secondary_cell.assert_not_awaited()
    driver.activate_secondary_cells.assert_not_awaited()


@pytest.mark.parametrize(
    "driver, missing_name",
    [
        (SimpleNamespace(activate_secondary_cells=AsyncMock()), "add_secondary_cell"),
        (SimpleNamespace(add_secondary_cell=AsyncMock()), "activate_secondary_cells"),
    ],
)
@pytest.mark.asyncio
async def test_ca_requires_both_driver_capabilities(
    driver: SimpleNamespace,
    missing_name: str,
) -> None:
    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [_scell()],
        inherit=False,
        execution_id="ca-capability",
    )

    assert added == []
    assert blocker and missing_name in blocker


@pytest.mark.asyncio
async def test_any_scell_add_failure_blocks_activation_and_sampling() -> None:
    driver = SimpleNamespace(
        add_secondary_cell=AsyncMock(side_effect=[True, False]),
        activate_secondary_cells=AsyncMock(return_value=True),
    )

    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [_scell(), _scell(3.8e9)],
        inherit=False,
        execution_id="ca-add-failure",
    )

    assert len(added) == 1
    assert blocker and "SCell 2" in blocker
    driver.activate_secondary_cells.assert_not_awaited()


@pytest.mark.asyncio
async def test_scell_activation_false_blocks_sampling() -> None:
    driver = SimpleNamespace(
        add_secondary_cell=AsyncMock(return_value=True),
        activate_secondary_cells=AsyncMock(return_value=False),
    )

    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [_scell()],
        inherit=False,
        execution_id="ca-activation-failure",
    )

    assert len(added) == 1
    assert blocker and "激活" in blocker


@pytest.mark.parametrize("failure_stage", ["add", "activate"])
@pytest.mark.asyncio
async def test_ca_driver_exception_is_an_actionable_blocker(
    failure_stage: str,
) -> None:
    driver = SimpleNamespace(
        add_secondary_cell=AsyncMock(
            side_effect=RuntimeError("add exploded")
            if failure_stage == "add"
            else None,
            return_value=True,
        ),
        activate_secondary_cells=AsyncMock(
            side_effect=RuntimeError("activate exploded")
            if failure_stage == "activate"
            else None,
            return_value=True,
        ),
    )

    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [_scell()],
        inherit=False,
        execution_id="ca-exception",
    )

    assert blocker and "exploded" in blocker
    if failure_stage == "add":
        assert added == []
        driver.activate_secondary_cells.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_scells_must_activate_before_all_nr_scope_is_allowed() -> None:
    driver = SimpleNamespace(
        add_secondary_cell=AsyncMock(return_value=True),
        activate_secondary_cells=AsyncMock(return_value=True),
    )

    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [_scell(), _scell(3.8e9)],
        inherit=False,
        execution_id="ca-success",
    )

    assert blocker is None
    assert [item["cc_index"] for item in added] == [1, 2]
    driver.activate_secondary_cells.assert_awaited_once_with()


def test_trusted_throughput_requires_the_exact_requested_scope() -> None:
    pcell_zero = ThroughputMetrics(
        dl_throughput_mbps=0.0,
        kpi_valid={"dl_throughput": True},
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
    )

    assert MeasureExecutor._trusted_throughput_value(
        pcell_zero,
        required_scope=ThroughputMetrics.SCOPE_PCELL,
    ) == pytest.approx(0.0)
    assert MeasureExecutor._trusted_throughput_value(
        pcell_zero,
        required_scope=ThroughputMetrics.SCOPE_NR_ALL_CELLS,
    ) is None


def test_completed_scan_with_wrong_scope_is_not_throughput_verified() -> None:
    assert MeasureExecutor._all_requested_throughput_is_valid(
        [0.0],
        [{"throughput_valid": True, "throughput_scope": "pcell"}],
        required_scope=ThroughputMetrics.SCOPE_NR_ALL_CELLS,
    ) is False


def _report_execution(
    *,
    carrier_count: int,
    top_scope: str | None,
    azimuth_scope: str | None,
) -> SimpleNamespace:
    azimuth = {
        "azimuth_deg": 0.0,
        "throughput_mbps": 123.0,
        "throughput_valid": True,
        "rsrp_dbm": -80.0,
        "sinr_db": 30.0,
        "rank_indicator": 2.0,
    }
    if azimuth_scope is not None:
        azimuth["throughput_scope"] = azimuth_scope
    measure = {
        "measurement_verified": True,
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "carrier_aggregation": {"num_component_carriers": carrier_count},
        "azimuth_results": [azimuth],
    }
    if top_scope is not None:
        measure["throughput_scope"] = top_scope
    return SimpleNamespace(
        id="p1-59-report",
        measurements={
            "phases": {
                "measure": measure,
                "analysis": {"verdict": "PASS"},
            }
        },
        status="completed",
        duration_sec=1.0,
        started_at=datetime(2026, 8, 21),
        completed_at=datetime(2026, 8, 21),
        validation_pass=True,
    )


@pytest.mark.parametrize(
    "carrier_count,top_scope,azimuth_scope",
    [
        (2, ThroughputMetrics.SCOPE_PCELL, ThroughputMetrics.SCOPE_PCELL),
        (2, None, None),
        (1, ThroughputMetrics.SCOPE_NR_ALL_CELLS,
         ThroughputMetrics.SCOPE_NR_ALL_CELLS),
    ],
)
def test_report_rejects_missing_or_wrong_carrier_scope(
    carrier_count: int,
    top_scope: str | None,
    azimuth_scope: str | None,
) -> None:
    content = _build_mimo_ota_content_data(
        _report_execution(
            carrier_count=carrier_count,
            top_scope=top_scope,
            azimuth_scope=azimuth_scope,
        ),
        datetime(2026, 8, 21),
    )

    assert content["formal_throughput_verified"] is False
    assert content["overall_result"] == "unknown"
    assert content["table_data"][0]["Throughput (Mbps)"] == "N/A"


@pytest.mark.parametrize(
    "carrier_count,scope",
    [
        (1, ThroughputMetrics.SCOPE_PCELL),
        (2, ThroughputMetrics.SCOPE_NR_ALL_CELLS),
    ],
)
def test_report_accepts_only_scope_matching_the_carrier_count(
    carrier_count: int,
    scope: str,
) -> None:
    content = _build_mimo_ota_content_data(
        _report_execution(
            carrier_count=carrier_count,
            top_scope=scope,
            azimuth_scope=scope,
        ),
        datetime(2026, 8, 21),
    )

    assert content["formal_throughput_verified"] is True
    assert content["throughput_trust_schema_version"] == 2
    assert content["throughput_scope"] == scope
    assert content["table_data"][0]["Throughput (Mbps)"] == "123.0"


def test_historical_throughput_trust_schema_one_is_fail_closed() -> None:
    schema_one = {
        "calibration_trust_schema_version": 1,
        "throughput_trust_schema_version": 1,
    }
    schema_two = {
        "calibration_trust_schema_version": 1,
        "throughput_trust_schema_version": 2,
    }

    assert report_has_provenance_trust(schema_one) is False
    assert report_has_provenance_trust(schema_two) is True
