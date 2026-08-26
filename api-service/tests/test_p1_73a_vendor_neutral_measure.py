"""P1-73A Task 4：MEASURE 与输入闭环不得按 UXM 类型分叉。"""

from __future__ import annotations

import inspect

from app.services.input_level_controller import InputLevelController, InputLevelResult
from app.services.mimo_ota.executors.measure import (
    MeasureExecutor,
    _build_pcell_requested_config,
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
