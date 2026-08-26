"""P1-73A: LTE/NR share one explicit, RAT-aware PCell truth."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.commissioning import CreateSessionRequest, _request_overrides
from app.hal.lte_earfcn import (
    lte_dl_earfcn_to_frequency_mhz,
    validate_lte_downlink_operating_point,
)
from app.hal.base_station import BaseStationRequestedConfig
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.mimo_ota.executors.measure import (
    _build_pcell_requested_config,
)
from app.services.mimo_ota.executors.analysis import AnalysisExecutor
from app.services.test_execution import StepExecutionStatus


LTE_B3_PCELL = {
    "radio_technology": "lte",
    "band": "B3",
    "duplex": "fdd",
    "lte_dl_earfcn": 1575,
    "frequency_hz": 1_842_500_000.0,
    "bandwidth_mhz": 20.0,
    "role": "pcell",
}


def test_lte_downlink_formula_uses_manual_table_2_55():
    assert lte_dl_earfcn_to_frequency_mhz("B3", 1575) == pytest.approx(1842.5)
    assert validate_lte_downlink_operating_point(
        band="B3",
        duplex="fdd",
        dl_earfcn=1575,
        frequency_mhz=1842.5,
    ) == pytest.approx(1842.5)


def test_lte_tdd_formula_uses_manual_table_2_56():
    assert lte_dl_earfcn_to_frequency_mhz("B40", 39150) == pytest.approx(2350.0)
    assert validate_lte_downlink_operating_point(
        band="B40",
        duplex="tdd",
        dl_earfcn=39150,
        frequency_mhz=2350.0,
    ) == pytest.approx(2350.0)


@pytest.mark.parametrize("band,earfcn", [("B29", 9700), ("B46", 50000), ("B999", 1)])
def test_scc_only_or_unknown_lte_band_is_not_a_pcell(band: str, earfcn: int):
    with pytest.raises(ValueError, match="PCell|unsupported"):
        lte_dl_earfcn_to_frequency_mhz(band, earfcn)


def test_lte_pcell_is_explicit_and_does_not_receive_nr_defaults():
    config = MIMOOTAConfiguration.model_validate(
        {"component_carriers": [LTE_B3_PCELL]}
    )

    assert len(config.component_carriers or []) == 1
    assert config.primary_carrier.radio_technology == "lte"
    assert config.primary_carrier.lte_dl_earfcn == 1575
    assert config.primary_carrier.nr_arfcn is None
    assert config.primary_carrier.subcarrier_spacing_khz is None
    assert config.theoretical_peak_throughput_mbps is None


@pytest.mark.parametrize(
    "patch,match",
    [
        ({"lte_dl_earfcn": None}, "lte_dl_earfcn"),
        ({"band": None}, "band"),
        ({"duplex": None}, "duplex"),
        ({"nr_arfcn": 636666}, "nr_arfcn"),
        ({"subcarrier_spacing_khz": 30}, "subcarrier_spacing_khz"),
        ({"frequency_hz": 1_843_000_000.0}, "frequency"),
        ({"duplex": "tdd"}, "duplex"),
    ],
)
def test_lte_pcell_rejects_missing_nr_or_mismatched_fields(patch: dict, match: str):
    carrier = {**LTE_B3_PCELL, **patch}
    with pytest.raises(ValidationError, match=match):
        MIMOOTAConfiguration.model_validate({"component_carriers": [carrier]})


def test_lte_rejects_scell_and_requires_explicit_peak_for_ratio():
    with pytest.raises(ValidationError, match="single PCell"):
        MIMOOTAConfiguration.model_validate(
            {
                "component_carriers": [
                    LTE_B3_PCELL,
                    {**LTE_B3_PCELL, "role": "scell"},
                ]
            }
        )

    config = MIMOOTAConfiguration.model_validate(
        {
            "component_carriers": [LTE_B3_PCELL],
            "theoretical_peak_throughput_mbps": 150.0,
        }
    )
    assert config.theoretical_peak_throughput_mbps == 150.0

    for invalid in (0, -1, math.inf, math.nan):
        with pytest.raises(ValidationError, match="theoretical_peak"):
            MIMOOTAConfiguration.model_validate(
                {
                    "component_carriers": [LTE_B3_PCELL],
                    "theoretical_peak_throughput_mbps": invalid,
                }
            )


def test_legacy_nr_payload_keeps_existing_defaults():
    config = MIMOOTAConfiguration.model_validate({})
    assert config.primary_carrier.radio_technology == "nr5g"
    assert config.primary_carrier.subcarrier_spacing_khz == 30
    assert config.primary_carrier.lte_dl_earfcn is None
    assert config.theoretical_peak_throughput_mbps == 450.0


def test_legacy_nr_payload_rejects_explicit_null_subcarrier_spacing():
    with pytest.raises(ValidationError, match="subcarrier_spacing_khz"):
        MIMOOTAConfiguration.model_validate({"subcarrier_spacing_khz": None})


def test_commissioning_lte_request_builds_the_same_explicit_pcell():
    request = CreateSessionRequest.model_validate(
        {
            "radio_technology": "lte",
            "frequency_hz": 1_842_500_000.0,
            "bandwidth_mhz": 20.0,
            "band": "B3",
            "duplex": "fdd",
            "lte_dl_earfcn": 1575,
        }
    )
    overrides = _request_overrides(request)
    config = MIMOOTAConfiguration.model_validate(overrides)

    assert overrides["component_carriers"] == [LTE_B3_PCELL]
    assert config.primary_carrier.radio_technology == "lte"
    assert config.theoretical_peak_throughput_mbps is None


def test_commissioning_lte_request_does_not_accept_prototype_defaults():
    with pytest.raises(ValidationError, match="frequency_hz"):
        CreateSessionRequest.model_validate(
            {
                "radio_technology": "lte",
                "bandwidth_mhz": 20.0,
                "band": "B3",
                "duplex": "fdd",
                "lte_dl_earfcn": 1575,
            }
        )

    with pytest.raises(ValidationError, match="lte_dl_earfcn"):
        CreateSessionRequest.model_validate(
            {
                "radio_technology": "lte",
                "frequency_hz": 1_842_500_000.0,
                "bandwidth_mhz": 20.0,
                "band": "B3",
                "duplex": "fdd",
            }
        )


@pytest.mark.parametrize("invalid_scs", [0, 17])
def test_commissioning_rejects_invalid_explicit_nr_scs(invalid_scs: int):
    with pytest.raises(ValidationError, match="subcarrier_spacing_khz"):
        CreateSessionRequest.model_validate(
            {
                "frequency_hz": 3_500_000_000.0,
                "bandwidth_mhz": 100.0,
                "band": "n78",
                "nr_arfcn": 633333,
                "subcarrier_spacing_khz": invalid_scs,
            }
        )


def test_measure_builds_one_vendor_neutral_lte_request():
    config = MIMOOTAConfiguration.model_validate(
        {"component_carriers": [LTE_B3_PCELL]}
    )

    requested = _build_pcell_requested_config(config)

    assert isinstance(requested, BaseStationRequestedConfig)
    assert requested.radio_technology == "lte"
    assert requested.channel_kind == "lte_dl_earfcn"
    assert requested.lte_dl_earfcn == 1575
    assert requested.nr_arfcn is None
    assert requested.subcarrier_spacing_khz is None
    with pytest.raises(FrozenInstanceError):
        requested.radio_technology = "nr5g"


@pytest.mark.asyncio
async def test_fake_uxm_and_cmw_receive_the_same_typed_request():
    class FakeAdapter:
        def __init__(self, adapter_id: str):
            self.adapter_id = adapter_id
            self.received = None

        async def apply_requested_config(self, requested):
            self.received = requested
            return True

    config = MIMOOTAConfiguration.model_validate(
        {"component_carriers": [LTE_B3_PCELL]}
    )
    requested = _build_pcell_requested_config(config)
    uxm = FakeAdapter("uxm")
    cmw = FakeAdapter("cmw500")

    assert await uxm.apply_requested_config(requested) is True
    assert await cmw.apply_requested_config(requested) is True
    assert uxm.received is requested
    assert cmw.received is requested


@pytest.mark.asyncio
async def test_real_adapters_reject_mismatched_rat_before_driver_write(monkeypatch):
    lte = _build_pcell_requested_config(
        MIMOOTAConfiguration.model_validate(
            {"component_carriers": [LTE_B3_PCELL]}
        )
    )
    nr = replace(
        lte,
        radio_technology="nr5g",
        channel_kind="nr_arfcn",
        band="n78",
        duplex="tdd",
        nr_arfcn=640000,
        lte_dl_earfcn=None,
        subcarrier_spacing_khz=30,
    )
    uxm = RealUxmDriver("uxm", {"ip_address": "192.0.2.1"})
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    async def forbidden_write(_payload):
        raise AssertionError("RAT mismatch must be rejected before driver I/O")

    monkeypatch.setattr(uxm, "set_cell_config", forbidden_write)
    monkeypatch.setattr(cmw, "set_cell_config", forbidden_write)

    assert await uxm.apply_requested_config(lte) is False
    assert await cmw.apply_requested_config(nr) is False


@pytest.mark.asyncio
async def test_cmw500_translates_vendor_neutral_lte_band(monkeypatch):
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})
    writes: list[str] = []
    monkeypatch.setattr(cmw, "_write", writes.append)
    monkeypatch.setattr(cmw, "_query", lambda _command: "1")

    assert await cmw.set_cell_config({"band": "B3", "earfcn": 1575}) is True
    assert any(command.endswith(" OB3") for command in writes)
    assert not any("OBB3" in command for command in writes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bandwidth_mhz", "cmw_token"),
    [
        (1.4, "B014"),
        (3.0, "B030"),
        (5.0, "B050"),
        (10.0, "B100"),
        (15.0, "B150"),
        (20.0, "B200"),
    ],
)
async def test_cmw500_translates_each_supported_lte_bandwidth_exactly(
    monkeypatch, bandwidth_mhz, cmw_token,
):
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})
    writes: list[str] = []
    monkeypatch.setattr(cmw, "_write", writes.append)
    monkeypatch.setattr(cmw, "_query", lambda _command: "1")

    assert await cmw.set_cell_config({"bandwidth_mhz": bandwidth_mhz}) is True
    assert any(command.endswith(f" {cmw_token}") for command in writes)
    assert not any("BANDwidth:UL" in command for command in writes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"bandwidth_mhz": 100.0},
        {"mimo_layers": 8},
    ],
)
async def test_cmw500_rejects_requests_beyond_declared_limits_before_io(
    monkeypatch, overrides,
):
    requested = _build_pcell_requested_config(
        MIMOOTAConfiguration.model_validate(
            {"component_carriers": [LTE_B3_PCELL]}
        )
    )
    requested = replace(requested, **overrides)
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    async def forbidden_write(_payload):
        raise AssertionError("adapter limits must be checked before driver I/O")

    monkeypatch.setattr(cmw, "set_cell_config", forbidden_write)

    assert await cmw.apply_requested_config(requested) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"bandwidth_mhz": 10.5},
        {"mimo_layers": 3},
    ],
)
async def test_cmw500_rejects_lossy_parameter_translation_before_io(
    monkeypatch, overrides,
):
    requested = _build_pcell_requested_config(
        MIMOOTAConfiguration.model_validate(
            {"component_carriers": [LTE_B3_PCELL]}
        )
    )
    requested = replace(requested, **overrides)
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    async def forbidden_write(_payload):
        raise AssertionError("lossy adapter translation must be rejected before I/O")

    monkeypatch.setattr(cmw, "set_cell_config", forbidden_write)

    assert await cmw.apply_requested_config(requested) is False


@pytest.mark.asyncio
async def test_cmw500_rejects_option_gated_band_when_snapshot_is_unknown(
    monkeypatch,
):
    requested = _build_pcell_requested_config(
        MIMOOTAConfiguration.model_validate(
            {"component_carriers": [LTE_B3_PCELL]}
        )
    )
    requested = replace(
        requested,
        band="B42",
        duplex="tdd",
        lte_dl_earfcn=42590,
        frequency_mhz=3500.0,
    )
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    async def forbidden_write(_payload):
        raise AssertionError("unknown option snapshot must block before driver I/O")

    monkeypatch.setattr(cmw, "set_cell_config", forbidden_write)

    assert await cmw.apply_requested_config(requested) is False


@pytest.mark.asyncio
async def test_analysis_keeps_lte_ratio_and_verdict_unknown_without_peak(monkeypatch):
    from app.services.mimo_ota.executors import analysis as analysis_module

    config = SimpleNamespace(
        theoretical_peak_throughput_mbps=None,
        pass_criteria=SimpleNamespace(
            min_throughput_ratio=0.5,
            min_throughput_mbps=50.0,
            max_rsrp_variance_db=8.0,
            min_sinr_db=10.0,
            min_avg_rank_indicator=1.5,
        ),
    )
    measure = {
        "measurement_verified": True,
        "frequency_consistency": {"fully_verified": True},
        "path_loss_verified": True,
        "path_loss_calibration_use_mock": False,
        "throughput_verified": True,
        "azimuth_results": [{
            "throughput_mbps": 100.0,
            "rsrp_dbm": -80.0,
            "sinr_db": 25.0,
            "rank_indicator": 2.0,
        }],
    }
    execution = SimpleNamespace(
        id="lte-no-peak",
        validation_pass=True,
        validation_details=None,
    )
    context = SimpleNamespace(
        test_execution=execution,
        db=SimpleNamespace(commit=lambda: None),
    )
    monkeypatch.setattr(analysis_module, "load_mimo_ota_config", lambda _e: config)
    monkeypatch.setattr(
        analysis_module,
        "read_phase_result",
        lambda _e, phase: measure if phase == "measure" else {"quiet_zone_pass": True},
    )
    monkeypatch.setattr(analysis_module, "write_phase_result", lambda *_args: None)
    monkeypatch.setattr(
        analysis_module, "path_loss_application_is_formally_verified", lambda _v: True
    )
    monkeypatch.setattr(analysis_module, "throughput_scope_is_verified", lambda _v: True)
    monkeypatch.setattr(analysis_module, "rf_kpi_scope_is_verified", lambda _v: True)
    monkeypatch.setattr(
        analysis_module, "quiet_zone_scope_is_formally_verified", lambda _v: True
    )

    result = await AnalysisExecutor().execute(context)

    assert result.status == StepExecutionStatus.SUCCESS
    assert result.measurements["avg_throughput_mbps"] == 100.0
    assert result.measurements["throughput_ratio"] is None
    assert result.measurements["throughput_pass"] is None
    assert result.measurements["verdict"] == "UNKNOWN"
    assert result.measurements["margin_db"] is None
    assert execution.validation_pass is None
