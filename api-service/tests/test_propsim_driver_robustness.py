"""PROPSIM F64 driver robustness tests (P0–P2 gap fixes).

Pin the behavioral contracts we just established:
  - set_mimo_config validates against channel_count + protects loaded files
  - get_metrics queries all inputs/outputs by **回读的物理口数** (F64R-2; 旧行为按
    tx×rx 推, 那是逻辑通道口径), partial failures don't crash
  - get_channel_state preserves static fields when SCPI queries fail mid-call
  - autoset_input_level uses *OPC? polling (not hardcoded sleep)
  - query_runtime_environment skips malformed groups instead of dropping all
  - get_output_power / get_output_calibration retry on 'not ready'
  - get_capabilities reflects probed *OPT? options (license-aware)

Mock VISA pattern matches test_propsim_calibration_tone.py — direct patches
of _write/_query so test responses stay tight to the SCPI contract.
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.hal.propsim_f64 import RealPropsimF64Driver


_SENTINEL = object()


def _make_driver(
    *,
    has_interference_generator=_SENTINEL,
    tx_antennas: int = 2,
    rx_antennas: int = 2,
    channel_count: int = 64,
    loaded_file: Optional[str] = None,
    active_inputs: Optional[int] = None,
    active_outputs: Optional[int] = None,
):
    """active_inputs / active_outputs: F64R-2 起端口寻址用**从仿真回读的物理口数**
    (`MODEL:INFO?`), 不再从 tx×rx 推。给了就预置成"已加载"等效态; 不给 = 拓扑未知
    (驱动会 fail-loud / 读操作降级)。tx_antennas/rx_antennas 只剩声明式元数据语义。"""
    cfg: dict = {}
    if has_interference_generator is not _SENTINEL:
        cfg["has_interference_generator"] = has_interference_generator
    drv = RealPropsimF64Driver("propsim-test", cfg)

    visa_mock = MagicMock()
    visa_mock.query.return_value = '0,"No error"'
    visa_mock.write.return_value = None
    drv._visa_resource = visa_mock
    drv._tx_antennas = tx_antennas
    drv._rx_antennas = rx_antennas
    drv._channel_count = channel_count
    drv._loaded_emulation_file = loaded_file
    drv._active_inputs = active_inputs
    drv._active_outputs = active_outputs
    if active_inputs and active_outputs:
        drv._active_channels = active_inputs * active_outputs
        # 全交叉拓扑按手册恒为 **1 组** (同输入或同输出即同组, 有传递性) —— 别按
        # outputs 造 N 组, 那是物理上不可能的形态 (组数 ≤ min(inputs, outputs))。
        drv._group_repr_channels = [1]
        # 端口**号**列表 —— 逐口查询/下发用这个 (这里造连续口, 非连续形态由
        # test_f64_topology_readback_f64r2.py 覆盖)
        drv._active_input_ports = list(range(1, active_inputs + 1))
        drv._active_output_ports = list(range(1, active_outputs + 1))

    async def _async_write(cmd, timeout=None):
        visa_mock.write(cmd)

    async def _async_query(cmd, timeout=None):
        return visa_mock.query(cmd)

    drv._write = _async_write  # type: ignore[assignment]
    drv._query = _async_query  # type: ignore[assignment]
    return drv, visa_mock


def _writes(visa_mock):
    return [c.args[0] for c in visa_mock.write.call_args_list]


def _queries(visa_mock):
    return [c.args[0] for c in visa_mock.query.call_args_list]


# ============================================================================
# P0-1: set_mimo_config — channel-count guard + loaded-file protection
# ============================================================================

class TestSetMimoConfig:

    @pytest.mark.asyncio
    async def test_caches_topology_on_clean_state(self):
        drv, _ = _make_driver(channel_count=64, loaded_file=None)
        ok = await drv.set_mimo_config(4, 4)
        assert ok is True
        assert drv._tx_antennas == 4
        assert drv._rx_antennas == 4

    @pytest.mark.asyncio
    async def test_refuses_when_paths_exceed_device_capacity(self):
        # 9x8 = 72 paths, F64 max 64
        drv, _ = _make_driver(channel_count=64, loaded_file=None)
        ok = await drv.set_mimo_config(9, 8)
        assert ok is False
        # cache untouched
        assert drv._tx_antennas == 2
        assert drv._rx_antennas == 2
        assert "exceeds device capacity" in (drv._last_error or "")

    @pytest.mark.asyncio
    async def test_refuses_topology_change_after_file_loaded(self):
        drv, _ = _make_driver(
            tx_antennas=2, rx_antennas=2,
            loaded_file="/tmp/my_2x2.smu",
        )
        ok = await drv.set_mimo_config(4, 4)
        assert ok is False
        assert drv._tx_antennas == 2  # unchanged
        assert drv._rx_antennas == 2

    @pytest.mark.asyncio
    async def test_noop_when_file_loaded_and_topology_matches(self):
        drv, _ = _make_driver(
            tx_antennas=4, rx_antennas=4,
            loaded_file="/tmp/my_4x4.smu",
        )
        ok = await drv.set_mimo_config(4, 4)
        assert ok is True

    @pytest.mark.asyncio
    async def test_boundary_at_exact_channel_count(self):
        # 8x8 = 64 paths exactly equals capacity → allowed
        drv, _ = _make_driver(channel_count=64, loaded_file=None)
        ok = await drv.set_mimo_config(8, 8)
        assert ok is True


# ============================================================================
# P0-2: get_metrics — dynamic per-channel query
# ============================================================================

class TestGetMetrics:

    @pytest.mark.asyncio
    async def test_queries_all_inputs_and_outputs_per_topology(self):
        # F64R-2: 口数来自回读的拓扑 (4 输入 / 8 输出), tx×rx 只是声明式元数据。
        drv, visa = _make_driver(tx_antennas=4, rx_antennas=2, channel_count=64,
                                 active_inputs=4, active_outputs=8)
        # 4 inputs + 8 outputs = 12 query channels.
        # SYST:INFO?, SYST:VERS?, *IDN? could also be queried elsewhere; stub
        # all queries to return a numeric power so per-channel parses succeed.
        visa.query.return_value = "-12.5"

        metrics = await drv.get_metrics()
        m = metrics.metrics
        assert set(m["input_powers_dbm"].keys()) == {1, 2, 3, 4}
        assert set(m["output_powers_dbm"].keys()) == {1, 2, 3, 4, 5, 6, 7, 8}
        # All values populated (no nulls when SCPI returns valid floats)
        assert all(v == -12.5 for v in m["input_powers_dbm"].values())

    @pytest.mark.asyncio
    async def test_not_ready_response_yields_none_for_that_channel(self):
        drv, visa = _make_driver(tx_antennas=2, rx_antennas=1,
                                 active_inputs=2, active_outputs=2)

        def _query(cmd):
            if "OUTP:MEAS:RES:GET? 1" in cmd:
                return "not ready"
            return "-15.0"
        visa.query.side_effect = _query

        metrics = await drv.get_metrics()
        m = metrics.metrics
        assert m["output_powers_dbm"][1] is None
        assert m["output_powers_dbm"][2] == -15.0
        # Inputs OK
        assert m["input_powers_dbm"][1] == -15.0

    @pytest.mark.asyncio
    async def test_per_channel_exception_recorded_in_query_errors(self):
        drv, visa = _make_driver(tx_antennas=2, rx_antennas=1,
                                 active_inputs=2, active_outputs=2)

        def _query(cmd):
            if "INP:MEAS:RES:GET? 2" in cmd:
                raise RuntimeError("input 2 down")
            return "-10.0"
        visa.query.side_effect = _query

        metrics = await drv.get_metrics()
        m = metrics.metrics
        assert m["input_powers_dbm"][2] is None
        assert m["input_powers_dbm"][1] == -10.0
        assert any("input_2" in err for err in m["query_errors"])
        # Status NOT downgraded — partial failure is not full failure
        assert metrics.status in ("normal", "idle")

    @pytest.mark.asyncio
    async def test_output_count_comes_from_topology_not_tx_times_rx(self):
        """F64R-2: 输出口数 = **回读的物理输出口**, 跟 tx×rx 和 channel_count 都无关。

        旧行为 min(tx×rx, channel_count) 的问题: tx×rx 是**逻辑通道**口径 —— MPAC OTA
        下 4 输入×32 探头 = 128 通道而输出口只有 32, 按 tx×rx 会把 32 个探头算成 16
        (只查/只配一半)。这里 tx×rx=72、channel_count=16 都是干扰项, 唯一依据是回读的
        32 个物理输出口。"""
        drv, visa = _make_driver(tx_antennas=9, rx_antennas=8, channel_count=16,
                                 active_inputs=4, active_outputs=32)
        visa.query.return_value = "-5.0"
        metrics = await drv.get_metrics()
        assert max(metrics.metrics["output_powers_dbm"].keys()) == 32
        assert len(metrics.metrics["output_powers_dbm"]) == 32


# ============================================================================
# P1-3: get_channel_state — partial-failure semantics
# ============================================================================

class TestGetChannelState:

    @pytest.mark.asyncio
    async def test_static_fields_always_returned(self):
        drv, visa = _make_driver(tx_antennas=2, rx_antennas=2)
        # Force one of the SCPI queries to fail
        def _query(cmd):
            if "DIAG:SIMU:MODEL:STATIC?" in cmd:
                raise RuntimeError("scpi timeout")
            return "1.2.3"
        visa.query.side_effect = _query

        state = await drv.get_channel_state()
        # Static fields present even though one query failed
        assert state["mimo_config"] == "2x2"
        assert state["pipeline"] is None  # no pipeline active
        assert "scpi_version" in state  # the other query succeeded
        # And errors are surfaced, not swallowed
        assert "query_errors" in state
        assert any("bypass_mode" in err for err in state["query_errors"])

    @pytest.mark.asyncio
    async def test_no_query_errors_key_when_all_succeed(self):
        drv, visa = _make_driver()
        def _query(cmd):
            if "STATIC?" in cmd:
                return "0"
            return "1.2.3"
        visa.query.side_effect = _query

        state = await drv.get_channel_state()
        assert state["bypass_mode"] == 0
        assert state["scpi_version"] == "1.2.3"
        assert "query_errors" not in state

    @pytest.mark.asyncio
    async def test_disconnected_returns_status_only(self):
        drv, _ = _make_driver()
        drv._visa_resource = None
        state = await drv.get_channel_state()
        assert state == {"status": "disconnected"}


# ============================================================================
# P1-4: autoset_input_level — *OPC? polling
# ============================================================================

class TestAutosetInputLevel:

    @pytest.mark.asyncio
    async def test_uses_opc_query_after_autoset_write(self):
        drv, visa = _make_driver()

        # First query: INP:LEV:MEAS? response. Second query: *OPC?.
        responses = iter(["-15.0,8.5", "1"])

        async def _async_query(cmd, timeout=None):
            visa.query(cmd, timeout=timeout)
            return next(responses)

        drv._query = _async_query  # type: ignore[assignment]

        result = await drv.autoset_input_level(input_num=1, measurement_time_s=1.0)

        assert result == -15.0
        # Verify *OPC? was the last query (replacing hardcoded sleep)
        queried = [c.args[0] for c in visa.query.call_args_list]
        assert "*OPC?" in queried
        # AUTOSET write happened
        assert any("INP:LEV:AUTOSET" in w for w in _writes(visa))


# ============================================================================
# P1-5: query_runtime_environment — robust parser
# ============================================================================

class TestQueryRuntimeEnvironment:

    @pytest.mark.asyncio
    async def test_skips_malformed_group_keeps_rest(self):
        drv, visa = _make_driver()
        # Two groups: ch1 OK (env=1, gain=2.0, delay=10, doppler=5)
        #             ch2 malformed (gain not a float)
        #             ch3 OK
        visa.query.return_value = (
            "1,1,2.0,10,5,"
            "2,1,not_a_float,10,5,"
            "3,1,4.5,20,10"
        )
        result = await drv.query_runtime_environment([1, 2, 3])
        # ch1 and ch3 should parse; ch2 skipped
        assert 1 in result
        assert 3 in result
        assert 2 not in result
        assert result[1]["gain_db"] == 2.0
        assert result[3]["gain_db"] == 4.5

    @pytest.mark.asyncio
    async def test_truncated_trailing_group_does_not_crash(self):
        drv, visa = _make_driver()
        # 5 + 3 tokens — last group cut off
        visa.query.return_value = "1,1,2.0,10,5,2,1,3.0"
        result = await drv.query_runtime_environment([1, 2])
        assert 1 in result
        # Truncated tail silently dropped — no exception, no crash
        assert 2 not in result

    @pytest.mark.asyncio
    async def test_scpi_failure_returns_empty_dict(self):
        drv, _ = _make_driver()

        async def _raise(cmd, timeout=None):
            raise RuntimeError("scpi timeout")

        drv._query = _raise  # type: ignore[assignment]
        result = await drv.query_runtime_environment([1, 2])
        assert result == {}


# ============================================================================
# P2-6/7: not-ready retry on get_output_power / get_output_calibration
# ============================================================================

class TestNotReadyRetry:

    @pytest.mark.asyncio
    async def test_get_output_power_retries_until_ready(self):
        drv, visa = _make_driver()
        responses = iter(["not ready", "not ready", "-12.5"])

        async def _async_query(cmd, timeout=None):
            visa.query(cmd)
            return next(responses)

        drv._query = _async_query  # type: ignore[assignment]

        result = await drv.get_output_power(1, retries=3, retry_delay_s=0.001)
        assert result == -12.5
        # 3 attempts made
        assert visa.query.call_count == 3

    @pytest.mark.asyncio
    async def test_get_output_power_returns_none_after_all_retries_not_ready(self):
        drv, visa = _make_driver()
        visa.query.return_value = "not ready"
        result = await drv.get_output_power(1, retries=3, retry_delay_s=0.001)
        assert result is None
        assert visa.query.call_count == 3

    @pytest.mark.asyncio
    async def test_get_output_calibration_retries_then_parses(self):
        drv, visa = _make_driver()
        responses = iter(["not ready", "1.5,30.0"])

        async def _async_query(cmd, timeout=None):
            visa.query(cmd)
            return next(responses)

        drv._query = _async_query  # type: ignore[assignment]

        result = await drv.get_output_calibration(1, retries=2, retry_delay_s=0.001)
        assert result == {"gain_db": 1.5, "phase_deg": 30.0}

    @pytest.mark.asyncio
    async def test_retry_recovers_from_transient_exception(self):
        drv, visa = _make_driver()
        call_count = {"i": 0}

        async def _async_query(cmd, timeout=None):
            call_count["i"] += 1
            if call_count["i"] == 1:
                raise RuntimeError("transient timeout")
            visa.query(cmd)
            return "-10.0"

        drv._query = _async_query  # type: ignore[assignment]

        result = await drv.get_output_power(1, retries=3, retry_delay_s=0.001)
        assert result == -10.0
        assert call_count["i"] == 2  # retried once, succeeded second time


# ============================================================================
# P2-8: get_capabilities reflects probed options
# ============================================================================

class TestGetCapabilities:

    @pytest.mark.asyncio
    async def test_includes_interference_gen_capability_when_licensed(self):
        drv, _ = _make_driver()
        drv.has_interference_generator = True
        drv._installed_options = ["K01", "K05"]

        caps = await drv.get_capabilities()
        intgen = next(c for c in caps if c.name == "Internal Interference Generator")
        assert intgen.supported is True
        assert intgen.parameters["license_status"] == "licensed"
        assert "K01" in intgen.parameters["matched_options"]

    @pytest.mark.asyncio
    async def test_intgen_unsupported_when_no_license(self):
        drv, _ = _make_driver()
        drv.has_interference_generator = False
        drv._installed_options = ["K05"]

        caps = await drv.get_capabilities()
        intgen = next(c for c in caps if c.name == "Internal Interference Generator")
        assert intgen.supported is False
        assert intgen.parameters["matched_options"] == []

    @pytest.mark.asyncio
    async def test_installed_options_capability_lists_all_probed(self):
        drv, _ = _make_driver()
        drv._installed_options = ["K01", "K02", "K05"]

        caps = await drv.get_capabilities()
        opts_cap = next(c for c in caps if c.name == "Installed Options")
        assert opts_cap.parameters["options"] == ["K01", "K02", "K05"]
        assert opts_cap.supported is True

    @pytest.mark.asyncio
    async def test_installed_options_unsupported_when_probe_returned_nothing(self):
        drv, _ = _make_driver()
        drv._installed_options = []
        caps = await drv.get_capabilities()
        opts_cap = next(c for c in caps if c.name == "Installed Options")
        assert opts_cap.supported is False
