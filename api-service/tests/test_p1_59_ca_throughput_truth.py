"""P1-59：CA 正式吞吐必须来自所有 NR cells 的聚合真值。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.hal.base_station import ThroughputMetrics
from app.hal.scpi_evidence import (
    ScpiExchangeRef,
    exchange_matches_catalog_role,
    load_default_p0_5_catalog,
)
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import UxmLteNrIratProfile
from app.diagnostics.sequences import uxm_scpi_compatibility
from app.api.test_execution import _formal_validation_pass
from app.services.mimo_ota.cleanup import cleanup_chamber_instruments
from app.services.mimo_ota.executors.analysis import AnalysisExecutor
from app.services.mimo_ota.executors.measure import MeasureExecutor
from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.report_service import report_has_provenance_trust
from app.services.test_execution import StepExecutionStatus


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


def test_ca_all_nr_queries_are_critical_for_the_irat_compatibility_probe() -> None:
    applicable, _not_in_profile = uxm_scpi_compatibility._critical_partition(
        UxmLteNrIratProfile,
    )

    assert {
        "MEAS_TPUT_DL_OTA_ALL",
        "MEAS_TPUT_UL_OTA_ALL",
    } <= applicable


def test_all_nr_query_matches_the_sourced_throughput_evidence_role() -> None:
    exchange = ScpiExchangeRef(
        exchange_id="p1-59-all-nr",
        instrument_id="uxm-irat",
        operation="query",
        command=UxmLteNrIratProfile.MEAS_TPUT_DL_OTA_ALL,
        execution_id="p1-59",
        capture_id="p1-59-capture",
        sequence=1,
        result_type="response",
        response="10,5000000,0,0,6000000,0",
    )
    entry = load_default_p0_5_catalog().entries["uxm.dl_throughput"]

    assert "all nr" in entry.source.section.lower()
    assert "ALL" in entry.notes
    assert exchange_matches_catalog_role(
        exchange,
        "uxm.dl_throughput",
        "query",
    ) is True


def _scell(frequency_hz: float = 3.7e9) -> SimpleNamespace:
    return SimpleNamespace(
        frequency_hz=frequency_hz,
        bandwidth_mhz=100,
        subcarrier_spacing_khz=30,
        band="n78",
    )


@pytest.mark.asyncio
async def test_cleanup_surfaces_rejected_scell_removal() -> None:
    base_station = SimpleNamespace(
        remove_all_secondary_cells=AsyncMock(return_value=False),
        stop_signaling=AsyncMock(return_value=True),
        disconnect=AsyncMock(return_value=True),
    )
    hal = SimpleNamespace(drivers={"baseStation": base_station})

    warnings = await cleanup_chamber_instruments(hal, "p1-59-cleanup")

    assert any("remove_all_secondary_cells" in warning for warning in warnings)


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
        SCELL_ACTIVATION_READBACK_AUTHORITATIVE=True,
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
        SCELL_ACTIVATION_READBACK_AUTHORITATIVE=True,
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
        SCELL_ACTIVATION_READBACK_AUTHORITATIVE=True,
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
        SCELL_ACTIVATION_READBACK_AUTHORITATIVE=True,
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
    driver.activate_secondary_cells.assert_awaited_once_with(
        expected_indices=[1, 2],
    )


@pytest.mark.asyncio
async def test_real_uxm_activation_blocks_without_authoritative_active_state_readback() -> None:
    driver = RealUxmDriver(
        "uxm-5g",
        {"ip": "10.0.0.2", "uxm_profile": "5g"},
    )
    driver._query = MagicMock(  # type: ignore[method-assign]
        side_effect=["2,1", "1"],
    )
    driver._write = MagicMock()  # type: ignore[method-assign]
    driver._drain_errors = MagicMock(  # type: ignore[method-assign]
        side_effect=[[], [], []],
    )

    activated = await driver.activate_secondary_cells(expected_indices=[1, 2])

    assert activated is False
    driver._query.assert_not_called()
    driver._write.assert_not_called()
    driver._drain_errors.assert_not_called()


@pytest.mark.asyncio
async def test_real_uxm_ca_blocks_before_first_scell_write_without_readback() -> None:
    driver = RealUxmDriver(
        "uxm-5g",
        {"ip": "10.0.0.2", "uxm_profile": "5g"},
    )
    driver.add_secondary_cell = AsyncMock(return_value=True)  # type: ignore[method-assign]

    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [_scell()],
        inherit=False,
        execution_id="ca-no-readback",
    )

    assert added == []
    assert blocker and "激活态权威回读" in blocker
    driver.add_secondary_cell.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_uxm_add_rejects_missing_profile_templates_without_io() -> None:
    driver = RealUxmDriver(
        "uxm-irat",
        {"ip": "10.0.0.2", "uxm_profile": "irat"},
    )
    driver._query = MagicMock()  # type: ignore[method-assign]
    driver._write = MagicMock()  # type: ignore[method-assign]

    added = await driver.add_secondary_cell(
        1,
        {
            "frequency_mhz": 3700,
            "bandwidth_mhz": 100,
            "scs_khz": 30,
            "band": "n78",
        },
    )

    assert added is False
    driver._query.assert_not_called()
    driver._write.assert_not_called()


@pytest.mark.asyncio
async def test_real_uxm_add_consumes_write_rejection() -> None:
    driver = RealUxmDriver(
        "uxm-5g",
        {"ip": "10.0.0.2", "uxm_profile": "5g"},
    )
    driver._query = MagicMock(return_value="1")  # type: ignore[method-assign]
    driver._write = MagicMock()  # type: ignore[method-assign]
    driver._drain_errors = MagicMock(  # type: ignore[method-assign]
        side_effect=[[], ['-222,"Data out of range"']],
    )

    added = await driver.add_secondary_cell(
        1,
        {
            "frequency_mhz": 3700,
            "bandwidth_mhz": 100,
            "scs_khz": 30,
            "band": "n78",
        },
    )

    assert added is False
    assert driver._write.call_count == 5


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


@pytest.mark.asyncio
async def test_analysis_rejects_legacy_ca_verdict_without_scope_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.mimo_ota.executors import analysis as analysis_module

    measure = {
        "measurement_verified": True,
        "frequency_consistency": {"fully_verified": True},
        "path_loss_application": {
            "schema_version": 1,
            "status": "applied",
            "provenance": "real",
            "reason": "selected",
            "gate_mode": "strict",
            "certificate_id": "p1-59-analysis-real-cert",
            "value_disclosure": "verified",
        },
        "path_loss_verified": True,
        "throughput_verified": True,
        "carrier_aggregation": {"num_component_carriers": 2},
        "azimuth_results": [
            {
                "azimuth_deg": 0.0,
                "throughput_mbps": 350.0,
                "throughput_valid": True,
                "rsrp_dbm": -80.0,
                "sinr_db": 30.0,
                "rank_indicator": 2.0,
            }
        ],
    }
    config = SimpleNamespace(
        theoretical_peak_throughput_mbps=450.0,
        pass_criteria=SimpleNamespace(
            min_throughput_ratio=0.5,
            min_throughput_mbps=300.0,
            max_rsrp_variance_db=8.0,
            min_sinr_db=10.0,
            min_avg_rank_indicator=1.5,
        ),
    )
    execution = SimpleNamespace(
        id="p1-59-analysis-legacy-ca",
        validation_pass=True,
        validation_details={"verdict": "PASS"},
    )
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )

    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _execution, phase: (
            measure if phase == "measure" else {"quiet_zone_pass": True}
        ),
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_: None)

    result = await AnalysisExecutor().execute(context)

    assert result.status == StepExecutionStatus.SUCCESS
    assert result.measurements["verdict"] == "UNKNOWN"
    assert result.measurements["throughput_verified"] is False
    assert execution.validation_pass is None


def test_history_rejects_legacy_ca_verdict_without_scope_proof() -> None:
    execution = SimpleNamespace(
        config={
            "step_descriptors": [{"type": "MIMO_OTA_MEASURE"}],
        },
        measurements={
            "phases": {
                "measure": {
                    "path_loss_verified": True,
                    "path_loss_calibration_use_mock": False,
                    "throughput_verified": True,
                    "carrier_aggregation": {"num_component_carriers": 2},
                    "azimuth_results": [
                        {
                            "throughput_mbps": 350.0,
                            "throughput_valid": True,
                        }
                    ],
                }
            }
        },
        validation_pass=True,
    )

    assert _formal_validation_pass(execution) is None


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
        "path_loss_application": {
            "schema_version": 1,
            "status": "applied",
            "provenance": "real",
            "reason": "selected",
            "gate_mode": "strict",
            "certificate_id": "p1-59-report-real-cert",
            "value_disclosure": "verified",
        },
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
    assert content["overall_result"] == "undetermined"
    assert content["execution_summary"]["pending"] == 0
    assert content["execution_summary"]["undetermined"] == 1
    assert content["execution_summary"]["pass_rate"] is None
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
