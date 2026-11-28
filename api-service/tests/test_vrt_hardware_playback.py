import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from tests.test_road_test_executions import _isolated_db

from app.hal.base_station import CellState


def _calibrated_ports():
    return [dict(input_port=t, output_port=r, emulator_output_dbm=-40, emulator_output_setting_dbm=-50,
                 emulator_input={"max_safe_input_dbm":-5, "uncertainty_db":1})
            for t in range(1, 5) for r in (1, 2)]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None, "power", "frequency", "wire", "output", "missing_setting", "changed_setting", "disconnect", "stop", "revoked_during_load", "revoked_during_attach"])
async def test_device_control_sequence(fault):
    from app.services.road_test.conducted_hardware import hardware_playback

    station = AsyncMock()
    station.get_cell_state.side_effect = [CellState.OFF, CellState.CONNECTED]
    station.read_conducted_working_point.return_value = (3600000000, 100, -19 if fault == "power" else -20)
    station.start_conducted_signaling = AsyncMock(return_value=True)
    station.stop_signaling.return_value = fault != "stop"
    station.ensure_safe_idle.return_value = True
    channel = AsyncMock()
    channel.load_local_scenario.return_value = True
    channel.get_channel_state.return_value = dict(simulation_state="STOPPED", active_input_ports=[1,2,3,4],
        active_channels=8, active_output_ports=[1,3] if fault == "wire" else [1,2], topology_source="readback")
    channel.read_playback_state.side_effect = ["CLOSED", "RUNNING"]
    channel.read_conducted_group_working_points.return_value = [(3500 if fault == "frequency" else 3600,100)]
    channel.read_conducted_output_setting.side_effect = [-50, -41 if fault == "output" else -50, -50, -51]
    channel.start_emulation.return_value = True
    channel.stop_emulation.return_value = True
    channel.close_conducted_project.return_value = True
    channel.set_conducted_output_enabled.return_value = True
    setup = {"binding":{"real_preflight":{"calibration":{"applicable":True, "scope":{
        "center_frequency_hz":3600000000, "bandwidth_mhz":100,"tx_power_dbm":-20}, "ports":_calibrated_ports(), "required_margin_db":3}}},
        "asset":{"instrument_path":"route.smu"}, "port_mapping":[dict(input_port=t, output_port=r)
        for t in range(1,5) for r in (1,2)]}
    calibration = setup["binding"]["real_preflight"]["calibration"]
    if fault == "missing_setting":
        del calibration["ports"][-1]["emulator_output_setting_dbm"]
    attaching = asyncio.Event()
    if fault == "revoked_during_attach":
        async def wait_for_terminal(_cancelled):
            attaching.set()
            await asyncio.Event().wait()
        station.start_conducted_signaling.side_effect = wait_for_terminal

    async def exercise():
        def verify_calibration():
            if attaching.is_set():
                raise RuntimeError("等待连接期间校准已撤销")
            if fault == "revoked_during_load" and channel.load_local_scenario.await_count:
                raise RuntimeError("工程加载期间校准已撤销")
        async with hardware_playback(setup, station, channel, asyncio.Event(), lambda: None, verify_calibration):
            if fault == "changed_setting":
                from app.services.road_test.conducted_hardware import check_running_power
                channel.measure_input.return_value = (-20, 3)
                channel.read_running_output_average_dbm.return_value = -50
                await check_running_power(station, channel, calibration)
            if fault == "disconnect":
                raise ConnectionError("连接中断")
    if fault:
        with pytest.raises((RuntimeError, ConnectionError)):
            await asyncio.wait_for(exercise(), 5)
    else:
        await exercise()
    if fault == "power":
        station.stop_signaling.assert_not_awaited()
        channel.load_local_scenario.assert_not_awaited()
        return
    station.stop_signaling.assert_awaited_once()
    channel.stop_emulation.assert_awaited_once()
    if fault == "stop":
        channel.close_conducted_project.assert_not_awaited()
    else:
        channel.close_conducted_project.assert_awaited_once()
    if fault == "revoked_during_load":
        assert all(not args.args[1] for args in channel.set_conducted_output_enabled.await_args_list)
    if fault in {"revoked_during_load", "wire", "power", "frequency", "output", "missing_setting"}:
        station.start_conducted_signaling.assert_not_awaited()
        channel.start_emulation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reply,ok", [("0", True), ("1", False), ("", False)])
async def test_f64_output_disable_readback_is_port_scoped(reply, ok):
    from app.hal.propsim_f64 import RealPropsimF64Driver
    driver = object.__new__(RealPropsimF64Driver)
    driver._scpi_lock = asyncio.Lock()
    driver._write = AsyncMock()
    driver._query = AsyncMock(return_value=reply)
    driver._first_error = AsyncMock(return_value=None)
    assert await driver.set_conducted_output_enabled(7, False) is ok
    driver._write.assert_awaited_once_with("OUTPUT:ENABLE 7,0")
    driver._query.assert_awaited_once_with("OUTPUT:ENABLE? 7")


@pytest.mark.asyncio
@pytest.mark.parametrize("reading", [-45, -20, None])
async def test_running_average_and_limit(reading):
    from app.services.road_test.conducted_hardware import check_running_power
    station = AsyncMock()
    station.read_conducted_working_point.return_value = (3600000000, 100, -20)
    channel = AsyncMock()
    channel.measure_input.return_value = (-20, 3)
    channel.read_conducted_output_setting.return_value = -50
    channel.read_running_output_average_dbm.return_value = reading
    evidence = {"scope": {"center_frequency_hz":3600000000, "bandwidth_mhz":100, "tx_power_dbm":-20},
                "ports":_calibrated_ports(), "required_margin_db":3}
    if reading == -45:
        assert (await check_running_power(station, channel, evidence))["running_output_average_dbm"] == {"1": -45, "2": -45}
    else:
        with pytest.raises(RuntimeError, match="运行平均功率"):
            await check_running_power(station, channel, evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reply", [True, False])
async def test_worker_with_mock_devices_never_creates_measured_samples(monkeypatch, stop_reply):
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone, timedelta
    from uuid import uuid4
    from unittest.mock import Mock
    from app.hal.base_station import MockBaseStation
    from app.hal.channel_emulator import MockChannelEmulator
    from app.models.vrt_port_calibration import VrtPortCalibration
    from app.schemas.road_test import TestMode, ExecutionStatus
    from app.services.road_test import conducted_runner as runner
    from tests.test_road_test_executions import _TestingSessionLocal

    station = Mock(spec=MockBaseStation)
    channel = Mock(spec=MockChannelEmulator)
    station.conducted_cell = "测试小区"
    station.read_conducted_working_point = AsyncMock(return_value=(3600000000, 100, -20))
    station.get_cell_state.side_effect = [CellState.OFF, CellState.CONNECTED, CellState.CONNECTED]
    station.start_conducted_signaling = AsyncMock(return_value=True)
    station.stop_signaling.return_value = True
    station.ensure_safe_idle.return_value = True
    station.get_throughput_metrics.return_value = SimpleNamespace(dl_throughput_current_mbps=11.5)
    channel.load_local_scenario = AsyncMock(return_value=True)
    channel.set_conducted_output_enabled = AsyncMock(return_value=True)
    channel.read_conducted_group_working_points = AsyncMock(return_value=[(3600, 100)])
    channel.read_conducted_output_setting = AsyncMock(return_value=-50)
    channel.measure_input = AsyncMock(return_value=(-20, 3))
    channel.read_running_output_average_dbm = AsyncMock(return_value=-50)
    channel.read_playback_state = AsyncMock(side_effect=["CLOSED","RUNNING","RUNNING"])
    channel.get_channel_state.side_effect = [
        dict(simulation_state="STOPPED", topology_source="readback", active_channels=8,
             active_input_ports=[1,2,3,4], active_output_ports=[1,2]),
        {"simulation_state":"RUNNING"}, {"simulation_state":"RUNNING"}]
    channel.start_emulation.return_value = True
    channel.stop_emulation.return_value = stop_reply
    channel.close_conducted_project = AsyncMock(return_value=True)
    hal = SimpleNamespace(drivers={"baseStation":station, "channelEmulator":channel})
    monkeypatch.setattr(runner, "get_hal_service", lambda:hal)
    @asynccontextmanager
    async def lease(*args, **kwargs):
        assert kwargs.get("control_f64", True) and kwargs.get("control_uxm", True)
        yield
    monkeypatch.setattr(runner, "instrument_test_lease", lease)
    monkeypatch.setattr(runner, "verify_channel_asset_smu_project_bytes", lambda *_:"ab"*32)
    from app.api import road_test
    monkeypatch.setattr(road_test, "_archive_execution_report", AsyncMock())
    with _TestingSessionLocal() as db:
        cert = VrtPortCalibration(id=uuid4(), evidence_sha256="ef"*32, issuer="fixture", evidence_b64="",
                                  readings_b64="", report_file="fixture.json", report_number="fixture")
        db.add(cert)
        db.commit()
        scope = dict(center_frequency_hz=3600000000, bandwidth_mhz=100, tx_power_dbm=-20)
        calibration = dict(applicable=True, id=str(cert.id), evidence_sha256=cert.evidence_sha256, scope=scope,
                           valid_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                           ports=_calibrated_ports(), required_margin_db=3)
        setup = dict(ready=True, calibration_id=str(cert.id), binding={"execution_mode":"real",
                     "real_preflight":{"calibration":calibration}}, asset={"id":str(uuid4()), "sha256":"ab"*32,
                     "instrument_path":"route.smu"}, port_mapping=[dict(input_port=t,output_port=r)
                     for t in range(1,5) for r in (1,2)])
        row = runner.executions.create(db, mode=TestMode.CONDUCTED, scenario_id="fixture")
        row.vrt_conducted_setup = setup
        row.status = ExecutionStatus.INITIALIZING.value
        db.commit()
        key = str(row.id)
        run = runner.Playback(asyncio.get_running_loop().create_future())
        await runner._run(db.get_bind(), key, setup, None, 1e-9, run, "test")
        db.refresh(row)
        assert row.status == ("completed" if stop_reply else "failed"), row.error_message
        assert row.hardware_status["conducted_stop_confirmed"] == stop_reply
        assert ("conducted_shutdown_ports" in row.hardware_status) != stop_reply
        samples = runner.executions.query_kpi_samples(db, key)
        assert samples and all(s.observation["provenance"] == "simulated" for s in samples)
        assert next(s.observation["value"] for s in samples if s.observation["metric"] == "dl_throughput_mbps") == 11.5

        if not stop_reply:
            from app.api.instrument import _exclusive_f64_control_operation
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as blocked:
                async with _exclusive_f64_control_operation(db):
                    pytest.fail("停止失败后仍取得了信道仿真器控制权")
            assert blocked.value.status_code == 409
            # 重启后仅允许复核停止。本测试设备仍是模拟对象，生产绑定门单独测试。
            runner.recover_conducted_runs(db)
            assert runner._unsettled(db)[0].id == row.id
            monkeypatch.setattr(runner, "_recovery_guard", lambda *_: "目标小区已变更")
            with pytest.raises(HTTPException, match="目标小区"):
                await runner.control(db, row, "stop")
            assert station.stop_signaling.await_count == 1
            monkeypatch.setattr(runner, "_recovery_guard", lambda *_: None)
            channel.stop_emulation.return_value = True
            await runner.control(db, row, "stop")
            assert row.hardware_status["conducted_stop_confirmed"] is True
            assert not runner._unsettled(db)
            assert row.status == "failed"
            station.start_conducted_signaling.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoked_queued_uxm_activation_is_never_sent(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import Mock

    from app.hal.uxm_base_station import RealUxmDriver
    from app.services.road_test.conducted_hardware import _start_cell

    driver = object.__new__(RealUxmDriver)
    driver._cell_id = "CELL0"
    driver._cmds = SimpleNamespace(CELL_STATE_ON="enable {cell}")
    driver._visa_session = SimpleNamespace(timeout=5000)
    driver._set_status = Mock()
    driver._write = Mock()
    driver._query = Mock(return_value="1")
    queued = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    submit = loop.run_in_executor
    with ThreadPoolExecutor(max_workers=1) as occupied:
        occupied.submit(release.wait, 5)

        def enqueue(executor, call, *args):
            queued.set()
            return submit(occupied, call, *args)
        monkeypatch.setattr(loop, "run_in_executor", enqueue)

        def verify():
            if queued.is_set():
                raise RuntimeError("排队期间校准已撤销")

        channel = SimpleNamespace(set_conducted_output_enabled=AsyncMock(return_value=True))
        try:
            with pytest.raises(RuntimeError, match="排队期间"):
                await asyncio.wait_for(_start_cell(driver, channel, [1, 2], asyncio.Event(), verify), 3)
        finally:
            release.set()
        assert channel.set_conducted_output_enabled.await_count == 2
    driver._write.assert_not_called()
    driver._query.assert_not_called()
    assert driver._visa_session.timeout == 5000


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_query", ["operation_complete", "connection_status"])
async def test_slow_uxm_reply_releases_independent_outputs_before_session_handoff(blocked_query):
    import threading
    from unittest.mock import Mock

    from app.hal.uxm_base_station import RealUxmDriver
    from app.services.road_test.conducted_hardware import _start_cell

    driver = object.__new__(RealUxmDriver)
    driver._cell_id = "CELL0"
    driver._cmds = SimpleNamespace(CELL_STATE_ON="enable {cell}")
    driver._cmd = Mock(return_value="connection_status")
    driver._set_status = Mock()
    driver._visa_session = SimpleNamespace(timeout=5000)
    driver._write = Mock()
    waiting, release, finished = threading.Event(), threading.Event(), threading.Event()
    def query(command):
        if (command == "connection_status") == (blocked_query == "connection_status"):
            waiting.set()
            release.wait(timeout=5)
            finished.set()
        return "IDLE" if command == "connection_status" else "1"
    driver._query = query

    def verify():
        if waiting.is_set():
            raise RuntimeError("等待回读期间校准已撤销")

    muted = []
    async def disable(port, enabled):
        assert not enabled and not finished.is_set()
        muted.append(port)
        if len(muted) == 2:
            release.set()
        return True
    channel = SimpleNamespace(set_conducted_output_enabled=disable)
    try:
        with pytest.raises(RuntimeError, match="撤销"):
            await _start_cell(driver, channel, [1, 2], asyncio.Event(), verify)
    finally:
        release.set()
    assert muted == [1, 2] and finished.is_set()
    assert driver._visa_session.timeout == 5000


@pytest.mark.asyncio
async def test_disable_remaining_outputs_and_stop_if_one_port_rejects():
    from app.services.road_test.conducted_hardware import _shutdown
    from unittest.mock import call
    station = AsyncMock()
    channel = AsyncMock()
    station.stop_signaling.return_value = True
    station.ensure_safe_idle.return_value = True
    channel.set_conducted_output_enabled.side_effect = [ConnectionError("断线"), True]
    channel.stop_emulation.return_value = True
    with pytest.raises(RuntimeError, match="输出口 7"):
        await _shutdown(station, channel, [7, 8])
    assert channel.set_conducted_output_enabled.await_args_list == [call(7, False), call(8, False)]
    channel.stop_emulation.assert_awaited_once()
    channel.close_conducted_project.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("actual_hz", [3600000000, 3500000000])
async def test_working_point_reads_integrated_power_from_controlled_cell_only(actual_hz):
    from unittest.mock import Mock, call
    from app.hal.uxm_base_station import RealUxmDriver
    from app.hal.uxm_command_profiles import UxmLteNrIratProfile
    driver = object.__new__(RealUxmDriver)
    driver._cmds = UxmLteNrIratProfile
    driver._cell_id = "CELL3"
    # Custom FR：同一 ARFCN 可对应不同的实际中频。
    replies = {"ARFCN?": "640000", "FREQuency?": str(actual_hz), "BW?": "BW100", "CHANnel?": "-20"}
    driver._query = Mock(side_effect=lambda command: replies[command.rsplit(":", 1)[1]])
    assert await driver.read_conducted_working_point() == (actual_hz, 100, -20)
    assert driver._query.call_args_list == [
        call("BSE:CONFig:NR5G:CELL3:DL:FREQuency?"),
        call("BSE:CONFig:NR5G:CELL3:DL:BW?"),
        call("BSE:CONFig:NR5G:CELL3:DL:POWer:CHANnel?"),
    ]

    if actual_hz != 3600000000:
        from app.services.road_test.conducted_hardware import hardware_playback
        driver.get_cell_state = AsyncMock(return_value=CellState.OFF)
        channel = AsyncMock()
        scope = {"center_frequency_hz":3600000000, "bandwidth_mhz":100, "tx_power_dbm":-20}
        setup = {"binding":{"real_preflight":{"calibration":{"applicable":True, "scope":scope}}},
                 "port_mapping":[]}
        with pytest.raises(RuntimeError, match="载频"):
            async with hardware_playback(setup, driver, channel, asyncio.Event(), lambda: None, lambda: None):
                pytest.fail("实际中频不符仍进入播放")
        channel.load_local_scenario.assert_not_awaited()


@pytest.mark.asyncio
async def test_stopped_emulator_does_not_read_retained_power():
    from app.hal.propsim_f64 import RealPropsimF64Driver
    driver = object.__new__(RealPropsimF64Driver)
    driver._scpi_lock = asyncio.Lock()
    driver._query_simulation_state = AsyncMock(return_value="STOPPED")
    driver._query_with_retry = AsyncMock()
    assert await driver.read_running_output_average_dbm(2) is None
    driver._query_with_retry.assert_not_awaited()


def test_current_throughput_uses_its_own_validity_and_value():
    from app.hal.base_station import ThroughputMetrics
    from app.services.road_test.measurement_evidence import confirmed_throughput_scope
    rates = ThroughputMetrics(dl_throughput_mbps=9, dl_throughput_current_mbps=0, throughput_scope="pcell")
    assert confirmed_throughput_scope("dl_throughput_mbps", 0, rates, current=True) == "pcell"
    assert confirmed_throughput_scope("dl_throughput_mbps", 9, rates, current=True) is None
    rates.kpi_valid["dl_throughput_current"] = False
    assert confirmed_throughput_scope("dl_throughput_mbps", 0, rates, current=True) is None


@pytest.mark.asyncio
async def test_disconnected_cell_records_missing_throughput_without_reading_retained_rate(monkeypatch):
    from unittest.mock import Mock
    from app.hal.base_station import CellState
    from app.services.road_test import conducted_runner as runner

    station = AsyncMock()
    station.get_cell_state.return_value = CellState.IDLE
    record = Mock()
    monkeypatch.setattr(runner.executions, "record_observation", record)

    await runner._sample(None, "isolated", station, AsyncMock(), 2.0, physical=True)

    station.get_throughput_metrics.assert_not_awaited()
    samples = {item.kwargs["metric"]: item.kwargs for item in record.call_args_list}
    assert samples["connection_state"]["value"] is False
    assert samples["dl_throughput_mbps"]["value"] is None
    assert samples["dl_throughput_mbps"]["throughput_readback"] is None
