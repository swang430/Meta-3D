"""P1-73A Task 4：MEASURE 与输入闭环不得按 UXM 类型分叉。"""

from __future__ import annotations

import inspect

import app.services.mimo_ota.executors.measure as measure_module
from app.hal.base_station import MockBaseStation
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.input_level_controller import InputLevelController, InputLevelResult
from app.services.mimo_ota.executors.measure import (
    MeasureExecutor,
    _build_pcell_requested_config,
    _formal_mac_configuration_blocker,
)


class _Ce:
    def get_active_input_count(self):
        return 2

    def get_active_input_ports(self):
        return [1, 2]

    async def autoset_inputs(self, *_args):
        return True

    async def measure_input(self, *_args):
        return (-30.0, 10.0)

    async def get_input_level_limits(self, *_args):
        return (-60.0, -10.0)

    async def set_input_measurement_mode(self, *_args):
        return True

    async def set_burst_trigger_level(self, *_args):
        return True

    async def get_group_clipping(self, *_args, **_kwargs):
        return 0.0

    async def get_system_status(self):
        return ({}, [])


class _Config:
    mimo_layers = 2
    precheck_strict_input_level = True
    input_loop_initial_dl_power_dbm = -10.0


class _Uxm:
    adapter_id = "uxm"
    input_level_control_supported = True

    def __init__(self):
        self.calls: list[float] = []

    async def set_downlink_power(self, power_dbm: float):
        self.calls.append(power_dbm)
        return True


class _Cmw:
    adapter_id = "cmw500"
    input_level_control_supported = False

    def __init__(self):
        self.calls: list[float] = []

    async def set_downlink_power(self, power_dbm: float):
        self.calls.append(power_dbm)
        raise AssertionError("P1-73A 不得调用未开放的 CMW 功率能力")


def test_measure_source_has_no_vendor_type_branch_or_cmw_scpi():
    source = inspect.getsource(MeasureExecutor)
    assert "RealUxmDriver" not in source
    assert "RealCmw500Driver" not in source
    assert "cmw500_base_station" not in source
    assert "ROUTe:LTE" not in source
    assert "CONFigure:LTE" not in source
    assert "uxm_inherit" not in source
    assert "uxm_config_capture_manager" not in source
    assert '"UXM": uxm_identity' not in source


def test_real_cmw_is_blocked_from_formal_kpi_without_mac_configuration():
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    blocker = _formal_mac_configuration_blocker(cmw)

    assert blocker is not None
    assert "MAC" in blocker


def test_cmw_pcell_confirmation_does_not_remove_missing_mac_blocker():
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    assert _formal_mac_configuration_blocker(cmw) is not None


def test_uxm_and_mock_keep_their_existing_mac_paths():
    uxm = RealUxmDriver("uxm", {"ip_address": "192.0.2.1"})
    mock = MockBaseStation("mock", {})

    assert _formal_mac_configuration_blocker(uxm) is None
    assert _formal_mac_configuration_blocker(mock) is None


async def test_cmw_does_not_call_inherited_rrc_stub_after_attach(monkeypatch):
    helper = getattr(measure_module, "_reconfigure_rrc_if_supported", None)
    assert callable(helper)

    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    async def forbidden_stub(**_kwargs):
        raise AssertionError("CMW must not call the inherited RRC stub")

    monkeypatch.setattr(cmw, "reconfigure_rrc", forbidden_stub)
    assert await helper(cmw, mimo_layers=2, modulation="64QAM") is None


async def test_explicit_rrc_capability_keeps_supported_adapter_path():
    class _Supported:
        rrc_reconfiguration_supported = True

        def __init__(self):
            self.calls = []

        async def reconfigure_rrc(self, **kwargs):
            self.calls.append(kwargs)
            return True

    helper = getattr(measure_module, "_reconfigure_rrc_if_supported", None)
    assert callable(helper)
    adapter = _Supported()
    assert await helper(adapter, mimo_layers=4, modulation="256QAM") is True
    assert adapter.calls == [{"mimo_layers": 4, "modulation": "256QAM"}]


async def test_uxm_input_loop_keeps_behavior_with_common_result_and_legacy_mirror():
    uxm = _Uxm()
    payload = await MeasureExecutor()._run_input_level_closed_loop(
        emulator=_Ce(),
        base_station=uxm,
        config=_Config(),
        execution_id="execution-uxm",
    )

    assert payload["success"] is True
    assert payload["base_station_dl_power_dbm"] == -10.0
    assert payload["uxm_dl_power_dbm"] == payload["base_station_dl_power_dbm"]
    assert uxm.calls == [-10.0]


async def test_cmw_input_loop_is_warning_only_and_never_uses_uxm_power_path():
    cmw = _Cmw()
    payload = await MeasureExecutor()._run_input_level_closed_loop(
        emulator=_Ce(),
        base_station=cmw,
        config=_Config(),
        execution_id="execution-cmw",
    )

    assert payload["skipped"] is True
    assert payload["formal_eligible"] is False
    assert "Warning" in payload["reason"]
    assert "CMW500" in payload["reason"]
    assert "uxm_dl_power_dbm" not in payload
    assert cmw.calls == []


def test_input_level_result_common_power_is_authoritative_and_legacy_is_read_only():
    result = InputLevelResult(success=True, base_station_dl_power_dbm=-12.0)
    assert result.base_station_dl_power_dbm == -12.0
    assert result.uxm_dl_power_dbm == -12.0

    try:
        result.uxm_dl_power_dbm = -20.0
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("legacy UXM mirror must be read-only")


def test_input_level_controller_uses_vendor_neutral_power_names():
    source = inspect.getsource(InputLevelController)
    assert "initial_uxm_dl_power_dbm" not in source
    assert "uxm_power_step_db" not in source
    assert "uxm_power" not in source


def test_lte_request_does_not_promote_uxm_bandwidth_power_to_cmw_contract():
    class _Carrier:
        radio_technology = "lte"
        frequency_hz = 1_950_000_000.0
        bandwidth_mhz = 20
        band = "1"
        duplex = "FDD"
        lte_dl_earfcn = 100
        lte_transmission_mode = "TM3"
        subcarrier_spacing_khz = None

    class _RequestConfig:
        primary_carrier = _Carrier()
        mimo_layers = 2
        target_tx_power_dbm = -20.0
        uxm_dl_power_dbm_per_bw = -46.0
        mimo_port_preset = None
        sched_algo = None
        csi_rs_ports = None

    request = _build_pcell_requested_config(_RequestConfig())
    assert request.downlink_power_dbm_per_bandwidth is None
