"""本次传导小区、工程与输出端口的设备控制。"""
import asyncio
import math
from contextlib import asynccontextmanager

from app.hal.base_station import CellState
from app.services.instrument_test_lease import await_completion_despite_cancellation


class PlaybackStopRequested(Exception):
    """操作人员要求停止，区别于设备通信中断。"""


async def _shutdown(station, channel, ports, *, expected_cell=None):
    failures = []

    async def confirm(label, operation):
        try:
            if await operation is not True:
                failures.append(label)
        except (Exception, asyncio.CancelledError) as exc:
            failures.append(f"{label}（{exc}）")

    if expected_cell is not None and station.conducted_cell != expected_cell:
        failures.append(f"原小区 {expected_cell} 的控制对象已变化，未能确认停发")
    else:
        await confirm("指定小区停发", station.stop_signaling())
        await confirm("指定小区关闭回读", station.ensure_safe_idle())
    for port in ports:
        await confirm(f"输出口 {port} 禁用回读", channel.set_conducted_output_enabled(port, False))
    await confirm("播放停止", channel.stop_emulation())
    if not failures:
        await confirm("工程卸载", channel.close_conducted_project())
    if failures:
        raise RuntimeError("以下停止操作未确认：" + "、".join(failures))


async def _start_cell(station, stop):
    attach = asyncio.create_task(station.start_signaling())
    stopping = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait((attach, stopping), return_when=asyncio.FIRST_COMPLETED)
        if stop.is_set():
            raise PlaybackStopRequested("等待终端连接期间收到停止请求。")
        return await attach
    finally:
        for task in (attach, stopping):
            task.cancel()
        await asyncio.gather(attach, stopping, return_exceptions=True)


def _output_limits(calibration):
    limits = {}
    for path in calibration["ports"]:
        port = path["output_port"]
        limit = path["emulator_output_dbm"]
        if not math.isfinite(limit):
            raise RuntimeError("校准记录缺少有效的输出参考面读数。")
        limits[port] = min(limits.get(port, limit), limit)
    if len(limits) != 2:
        raise RuntimeError("校准记录未覆盖两个物理输出口。")
    return limits


async def check_running_power(station, channel, calibration):
    """最近的输出平均值超过校准时的峰值即中止；低于它不能重新证明峰值安全。"""
    scope = calibration["scope"]
    expected = (scope["center_frequency_hz"], scope["bandwidth_mhz"], scope["tx_power_dbm"])
    if await station.read_conducted_working_point() != expected:
        raise RuntimeError("运行中指定小区的载频、带宽或整带宽功率已变化。")
    # User Reference §20.4.4.6：同一输入口的平均电平 dBm 和峰均比 dB。
    # 两者相加为这次测量窗口内的峰值估计，仍按现场校准的不确定度预留余量。
    input_limits = {}
    for path in calibration["ports"]:
        port = path["input_port"]
        plane = path["emulator_input"]
        limit = plane["max_safe_input_dbm"] - plane["uncertainty_db"] - calibration["required_margin_db"]
        input_limits[port] = min(input_limits.get(port, limit), limit)
    if len(input_limits) != 4:
        raise RuntimeError("校准记录未覆盖四个物理输入口。")
    peaks = {}
    for port, limit in input_limits.items():
        measurement = await channel.measure_input(port, measurement_time_s=0.5)
        if measurement is None:
            raise RuntimeError(f"输入口 {port} 的运行电平无法测量。")
        average, crest = measurement
        peak = average + crest
        if not math.isfinite(peak) or crest < 0 or peak > limit:
            raise RuntimeError(f"输入口 {port} 的峰值读数无效或安全余量不足。")
        peaks[str(port)] = peak
    limits = _output_limits(calibration)
    readings = {}
    for port, limit in limits.items():
        value = await channel.read_running_output_average_dbm(port)
        if value is None or not math.isfinite(value) or value > limit:
            raise RuntimeError(f"输出口 {port} 的运行平均功率缺测或超过现场校准的输出电平。")
        readings[str(port)] = value
    return {"running_output_average_dbm": readings, "running_input_window_peak_dbm": peaks}


@asynccontextmanager
async def hardware_playback(setup, station, channel, stop, verify_project, record_ports=None):
    calibration = setup["binding"]["real_preflight"]["calibration"]
    if calibration["applicable"] is not True:
        raise RuntimeError("本次工作点缺少适用的逐路校准。")
    scope = calibration["scope"]
    expected = (scope["center_frequency_hz"], scope["bandwidth_mhz"], scope["tx_power_dbm"])
    paths = setup["port_mapping"]
    inputs = {path["input_port"] for path in paths}
    outputs = {path["output_port"] for path in paths}
    owned_ports = []
    cell = station.conducted_cell
    def check_stop():
        if stop.is_set():
            raise PlaybackStopRequested("已请求停止本次传导执行。")

    check_stop()
    if await station.get_cell_state() != CellState.OFF:
        raise RuntimeError("本次基站小区尚未确认关闭。")
    if await station.read_conducted_working_point() != expected:
        raise RuntimeError("指定小区载频、带宽或整带宽功率与校准工作点不一致。")
    verify_project()
    path = setup["asset"]["instrument_path"]
    if any(ord(ch) < 32 or ch in ';"' for ch in path):
        raise RuntimeError("工程路径含有设备文件参数不能使用的字符。")
    if await channel.read_playback_state() not in ("CLOSED", "STOPPED"):
        raise RuntimeError("信道仿真器已有播放或状态未知，拒绝接管。")
    if record_ports:
        record_ports([])
    try:
        if not await channel.load_local_scenario(path):
            raise RuntimeError("信道仿真器拒绝加载本次工程。")
        verify_project()
        state = await channel.get_channel_state()
        if (state.get("simulation_state") != "STOPPED" or state.get("topology_source") != "readback"
                or set(state.get("active_input_ports") or ()) != inputs
                or set(state.get("active_output_ports") or ()) != outputs or state.get("active_channels") != 8):
            raise RuntimeError("工程加载后未确认停止或物理端口与八路映射不一致。")
        owned_ports = sorted(outputs)
        if record_ports:
            record_ports(owned_ports)
        points = await channel.read_conducted_group_working_points()
        if not points or any(point != (expected[0] / 1e6, expected[1]) for point in points):
            raise RuntimeError("信道组的实际载频或带宽与本次工程不一致。")
        limits = _output_limits(calibration)
        if set(limits) != outputs:
            raise RuntimeError("输出参考面登记与物理接线不一致。")
        for port in owned_ports:
            configured = await channel.read_conducted_output_setting(port)
            if configured is None or not math.isfinite(configured) or configured > limits[port]:
                raise RuntimeError(f"输出口 {port} 的工程电平无法核验或超过校准登记电平。")
        for port in owned_ports:
            check_stop()
            if not await channel.set_conducted_output_enabled(port, True):
                raise RuntimeError(f"无法确认输出口 {port} 启用。")
        check_stop()
        if not await channel.start_emulation():
            raise RuntimeError("设备未确认开始播放。")
        check_stop()
        if await channel.read_playback_state() != "RUNNING":
            raise RuntimeError("信道仿真器尚未回读正在播放。")
        if not await _start_cell(station, stop) or await station.get_cell_state() != CellState.CONNECTED:
            raise RuntimeError("指定小区未确认终端连接。")
        yield
    finally:
        outcome = await await_completion_despite_cancellation(_shutdown(station, channel, owned_ports, expected_cell=cell))
        if outcome.error:
            raise outcome.error
        if record_ports:
            record_ports(None)
        if outcome.delayed_cancellation:
            raise outcome.delayed_cancellation
