"""P1-73C Task 13: one fake transport crosses the real CMW measure lifecycle."""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.hal.base_station import CellState, ThroughputMetrics
from app.hal.cmw500_base_station import RealCmw500Driver
from app.services.mimo_ota.cleanup import cleanup_chamber_instruments
from app.services.mimo_ota.executors.measure import MeasureExecutor


class _Session:
    def __init__(self) -> None:
        self.timeout = 10_000
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeTransportCmw(RealCmw500Driver):
    def __init__(self) -> None:
        super().__init__("cmw-integration", {"ip_address": "192.0.2.10"})
        self._visa_session = _Session()
        self._session_token = "session-integration"
        self._identity_model = "CMW"
        self._identity_model_verified = True
        self._firmware_version = "3.5.40"
        self._installed_options = ["CMW-KS500", "CMW-KS520"]
        self._options_snapshot_verified = True
        self.cell_states = deque(
            [
                "OFF,ADJ",  # config precondition
                "OFF,ADJ",  # route precondition
                "ON,ADJ",  # Cell ON
                "ON,ADJ",  # Extended BLER pre-window live UE check
                "ON,ADJ",  # Extended BLER post-window live UE check
                "OFF,ADJ",  # shared stop readback
                "OFF,ADJ",  # shared SAFE_IDLE readback
                "OFF,ADJ",  # release-time SAFE_IDLE readback
            ]
        )
        self.ps_states = deque(["ATT", "CEST", "CEST", "CEST"])
        self.ebler_states = deque(["OFF", "RUN", "RUN", "RDY", "OFF"])
        self.writes: list[str] = []
        self.queries: list[str] = []

    def _do_write(self, command: str) -> None:
        self.writes.append(command)

    def _do_query(self, command: str) -> str:
        self.queries.append(command)
        if command == "SOURce:LTE:SIGN1:CELL:STATe:ALL?":
            return self.cell_states.popleft()
        if command == "FETCh:LTE:SIGN1:PSWitched:STATe?":
            return self.ps_states.popleft()
        if command == "FETCh:LTE:SIGN1:EBLer:STATe?":
            return self.ebler_states.popleft()
        if command == "ROUTe:LTE:SIGN1?":
            return "TRO,BB1,RF1C,RX1,RF1C,TX1,RF2C,TX2"
        if command == "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?":
            return "BB1,RF1C,RX1,RF1C,TX1,RF2C,TX2"
        if command == "CONFigure:LTE:SIGN1:BAND?":
            return "OB3"
        if command == "CONFigure:LTE:SIGN1:CELL:BANDwidth:DL?":
            return "B200"
        if command == "CONFigure:LTE:SIGN1:RFSettings:CHANnel:DL?":
            return "1300"
        if command == "CONFigure:LTE:SIGN1:DMODe?":
            return "FDD"
        if command == "CONFigure:LTE:SIGN1:CONNection:PCC:NENBantennas?":
            return "TWO"
        if command == "FETCh:LTE:SIGN1:EBLer:PCC:ABSolute?":
            return "0,900,100,5000,123456.5,120000,125000,0,1000,15"
        if command == "FETCh:LTE:SIGN1:EBLer:PCC:RELative?":
            return "0,99.5,0.5,0.5,87.25,0"
        if command == "CONFigure:LTE:SIGN1:EBLer:SFRames?":
            # P1-74：统计基回读，与本用例冻结的 5000 子帧一致
            return "5000"
        if command == "*OPC?":
            return "1"
        if command == "SYSTem:ERRor:ALL?":
            return '0,"No error"'
        raise AssertionError(f"unexpected query: {command}")


def _frozen_route() -> dict:
    return {
        "resolution": {
            "schema_version": 1,
            "adapter": "cmw500",
            "status": "configured",
            "execution_mode": "real",
            "profile": {
                "schema_version": 1,
                "adapter": "cmw500",
                "lte_2x2_internal_route": {
                    "pcc_bb_board": "BB1",
                    "rx_connector": "RF1C",
                    "rx_converter": "RX1",
                    "tx1_connector": "RF1C",
                    "tx1_converter": "TX1",
                    "tx2_connector": "RF2C",
                    "tx2_converter": "TX2",
                },
            },
        }
    }


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_fake_transport_runs_config_route_attach_window_cleanup_then_release():
    driver = _FakeTransportCmw()
    session = driver._visa_session

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        assert await driver.set_cell_config(
            {
                "band": "B3",
                "bandwidth_mhz": 20,
                "earfcn": 1300,
                "duplex": "FDD",
                "mimo_layers": 2,
            }
        ) is True
        route = await driver.apply_internal_lte_2x2_route(_frozen_route())
        assert route.confirmed is True
        assert route.reason == "CMW500 route write and both readbacks confirmed"
        assert await driver.start_signaling(timeout_s=3.0) is True
        samples = await MeasureExecutor._measure_base_station_samples(
            driver,
            window_s=0.1,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            requested_sample_count=3,
            manifest=RealCmw500Driver.adapter_manifest,
            simulated_diagnostic=False,
            statistical_basis_subframes=5000,
        )
        cleanup = await cleanup_chamber_instruments(
            SimpleNamespace(drivers={"baseStation": driver}), "execution-1"
        )

    assert len(samples) == 1
    assert samples[0].window is not None
    assert samples[0].metrics.dl_throughput_mbps == pytest.approx(123.4565)
    assert samples[0].metrics.dl_bler == pytest.approx(0.5)
    assert cleanup.base_station.stop_signaling_confirmed is True
    assert cleanup.base_station.safe_idle_confirmed is True
    assert driver._visa_session is session
    assert session.closed is False

    release = await driver.release_remote_session(
        "session-integration",
        measurement_attempt_id="attempt-integration",
        lease_id="lease-integration",
    )

    assert release.transport_session_released_confirmed is True
    assert release.front_panel_local_confirmed is None
    assert session.closed is True
    assert driver._visa_session is None
    assert driver.ebler_states == deque()


@pytest.mark.asyncio
async def test_route_as_first_write_is_not_rejected_by_a_stale_error_queue():
    # 2026-09-16 起 route 是一次执行里对 CMW 的第一个写。设备级错误队列读后清空：
    # 队列里留着本次执行之前的无关错误（诊断序列 / 原始 SCPI 端点 / 前面板）时，
    # 不得被读成「路由被拒」—— 旧顺序下这一步由 set_cell_config 的清队列兜着。
    class _StaleQueueCmw(_FakeTransportCmw):
        def __init__(self) -> None:
            super().__init__()
            self.error_queue = deque(['-113,"Undefined header"'])

        def _do_query(self, command: str) -> str:
            if command == "SYSTem:ERRor:ALL?":
                self.queries.append(command)
                return self.error_queue.popleft() if self.error_queue else '0,"No error"'
            return super()._do_query(command)

    driver = _StaleQueueCmw()

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        route = await driver.apply_internal_lte_2x2_route(_frozen_route())

    assert route.confirmed is True
    assert route.reason == "CMW500 route write and both readbacks confirmed"
    # 清旧错误发生在路由写入之前，且不混进本次路由的证据往返里。
    first_route_write = next(
        index for index, item in enumerate(driver.writes) if item.startswith("ROUTe:")
    )
    assert first_route_write == 0
    assert driver.queries.index("SYSTem:ERRor:ALL?") < driver.queries.index(
        "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?"
    )


@pytest.mark.asyncio
async def test_extended_bler_window_rejects_a_live_ue_drop_before_recording_connected():
    driver = _FakeTransportCmw()
    driver._cell_state = CellState.CONNECTED
    driver.cell_states = deque(["ON,ADJ", "ON,ADJ"])
    driver.ps_states = deque(["CEST", "ATT"])

    with patch("app.hal.cmw500_base_station.asyncio.sleep", _no_sleep):
        with pytest.raises(RuntimeError, match="UE link"):
            await MeasureExecutor._measure_base_station_samples(
                driver,
                window_s=0.1,
                throughput_scope=ThroughputMetrics.SCOPE_PCELL,
                requested_sample_count=3,
                manifest=RealCmw500Driver.adapter_manifest,
                simulated_diagnostic=False,
                statistical_basis_subframes=5000,
            )
