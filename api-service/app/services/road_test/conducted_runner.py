"""服务端在绑定的设备租约中控制传导播放，直到结束或安全停止。"""
import asyncio
import hashlib
import math
import shutil
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.test_plan import TestExecution
from app.models.vrt_port_calibration import VrtPortCalibration

from app.hal.base_station import CellState
from app.services.road_test.measurement_evidence import calibrated_setup, real_driver_pair
from app.services.road_test.conducted_hardware import PlaybackStopRequested, hardware_playback, check_running_power, _shutdown
from app.services.smu_project_inventory import verify_channel_asset_smu_project_bytes
from app.models.channel_asset import ChannelAsset
from app.hal.channel_emulator import ChannelLoadMode
from app.schemas.road_test import ExecutionStatus
from app.services.execution_exclusion_guard import (
    release_unsafe_diagnostic, try_acquire_unsafe_diagnostic, update_conducted_stop, restore_conducted_stops,
)
from app.services.instrument_hal_service import get_hal_service, is_mock_driver
from app.services.instrument_test_lease import instrument_test_lease, positioner_refresh_busy
from app.services.road_test.vrt_execution_service import vrt_execution_service as executions


@dataclass
class Playback:
    ready: asyncio.Future
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


_active: dict[str, Playback] = {}


def _mock_only(hal):
    if not all(is_mock_driver(hal.drivers.get(key)) for key in ("baseStation", "channelEmulator")):
        return "真实设备启动前仍需核对绑定仪器的载频、带宽、功率和适用校准。"
    return None


async def _sample(db, key, station, channel, elapsed, *, physical=False):
    if physical:
        cell = await station.get_cell_state()
        if cell == CellState.ERROR:
            raise RuntimeError("指定小区的连接状态无法回读。")
        connected = cell == CellState.CONNECTED
    else:
        connected = (await station.get_ue_info()).get("connected")
    rates = None
    throughput = None
    if not physical or connected:
        rates = await station.get_throughput_metrics()
        throughput = rates.dl_throughput_current_mbps if physical else rates.dl_throughput_mbps
    for metric, value, driver in (
        ("connection_state", connected, station),
        ("dl_throughput_mbps", throughput, station),
        ("playback_position_s", None, channel),
    ):
        executions.record_observation(db, key, metric=metric, value=value, driver=driver, time_s=elapsed,
                                      throughput_readback=rates, current_throughput=physical)


async def _stop_devices(channel, station):
    try:
        if not await channel.stop_emulation() or (await channel.get_channel_state()).get("running") is not False:
            raise RuntimeError("未取得模拟信道仿真器的停止确认。")
    finally:
        if not await station.stop_signaling() or await station.get_cell_state() != CellState.OFF:
            raise RuntimeError("未取得模拟基站的停止确认。")


def _stage_waveforms(directory, links, destination):
    """只复制本次清单列出的文件，对驱动将读取的副本重新验算。"""
    for link in links:
        name = link["file"]
        staged = Path(destination) / name
        shutil.copyfile(Path(directory) / name, staged)
        with staged.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != link["sha256"]:
            raise ValueError(f"加载前文件 {name} 的内容与已保存的摘要不一致。")


@asynccontextmanager
async def _mock_playback(snapshot, staged_directory, station, channel, run):
    try:
        if run.stop.is_set():
            raise PlaybackStopRequested("加载前已收到停止请求。")
        if not await channel.load_channel(ChannelLoadMode.EXTERNAL_WAVEFORM, snapshot["asset"]["sha256"],
                                          snapshot["scenario_id"], {}, waveform_dir=staged_directory):
            raise RuntimeError("模拟驱动拒绝加载工程。")
        if run.stop.is_set():
            raise PlaybackStopRequested("加载过程中收到停止请求。")
        if not await station.start_signaling() or (await station.get_ue_info()).get("connected") is not True:
            raise RuntimeError("模拟基站未确认连接。")
        if run.stop.is_set():
            raise PlaybackStopRequested("启动播放前已收到停止请求。")
        # 传导准备已核验四发二收的八路组合；OTA 探头是暗室输出映射，
        # 不能作为通信天线数。OTA 保留工程加载后的通信配置。
        if snapshot["asset"]["kind"] == "asc_manifest" and not await channel.set_mimo_config(4, 2):
            raise RuntimeError("模拟驱动拒绝传导通信配置。")
        if not await channel.start_emulation():
            raise RuntimeError("模拟驱动拒绝启动播放。")
        yield
    finally:
        await _stop_devices(channel, station)


def _real_guard(db, snapshot, hal):
    from app.api.road_test_conducted import Selection, resolve

    if not real_driver_pair(hal.drivers):
        return "实际加载的基站和信道仿真器与本次真实执行不符。"
    db.expire_all()
    selection = Selection.model_validate({k: snapshot.get(k) for k in Selection.model_fields})
    if resolve(db, selection) != snapshot or not calibrated_setup("conducted", snapshot):
        return "设备绑定、场景或逐路校准已发生变化。"
    return None


def _record_shutdown(db, row, ports, cell=None):
    status = dict(row.hardware_status or {})
    if cell is not None:
        status["controlled_cell"] = cell
    if ports is None:
        status["conducted_stop_confirmed"] = True
        previous_ports = status.pop("conducted_shutdown_ports", [])
        status["instrument_status"] = {
            "baseStation": f"指定小区 {status.get('controlled_cell')} 已回读关闭。",
            "channelEmulator": (f"输出口 {previous_ports} 已逐口回读禁用，" if previous_ports else "")
                               + "播放已停止，工程已卸载。"
        }
    else:
        status["instrument_status"] = {"baseStation": "本次小区尚未完成停止复核。",
                                       "channelEmulator": "尚未完成本次工程的停止复核。"}
        status["conducted_stop_confirmed"] = False
        status["conducted_shutdown_ports"] = ports
    row.hardware_status = status
    key = str(row.id)
    db.commit()
    update_conducted_stop(key, ports is not None)


def _unsettled(db):
    return db.query(TestExecution).filter(
        TestExecution.mode == "conducted",
        TestExecution.hardware_status["conducted_shutdown_ports"].as_string().is_not(None),
    ).all()


def _recovery_guard(db, row, hal):
    setup = row.vrt_conducted_setup
    from app.models.lab_profile import LabProfile
    from app.services.base_station_binding import resolve_base_station_binding
    from app.services.channel_emulator_binding import resolve_channel_emulator_binding
    if not real_driver_pair(hal.drivers):
        return "设备驱动已变化，无法接管原设备。"
    if hal.drivers["baseStation"].conducted_cell != row.hardware_status.get("controlled_cell"):
        return "当前控制的小区与原执行不符。"
    lab = db.get(LabProfile, UUID(setup["lab_profile_id"]))
    if lab is None:
        return "原实验室绑定不可用。"
    binding = setup["binding"]
    if (resolve_base_station_binding(db, hal, lab).binding_digest != binding["real_preflight"]["base_station_binding_digest"]
            or resolve_channel_emulator_binding(db, hal, lab).binding_digest != binding["binding_digest"]):
        return "设备连接与原执行不一致，无法接管。"
    return None


async def _recover_stop(db, row):
    if positioner_refresh_busy():
        raise HTTPException(409, "设备正由其他测试占用。")
    token = try_acquire_unsafe_diagnostic("传导执行停止复核", recovery_execution_id=str(row.id))
    if not token:
        raise HTTPException(409, "设备正由其他操作占用。")
    try:
        async with instrument_test_lease("传导执行停止复核", recovery_execution_id=str(row.id), enable_monitoring=False, restore_f64_alignment=False,
                                         validate_before_remote=lambda hal: _recovery_guard(db, row, hal)):
            hal = get_hal_service()
            reason = _recovery_guard(db, row, hal)
            if reason:
                raise ValueError(reason)
            await _shutdown(hal.drivers["baseStation"], hal.drivers["channelEmulator"],
                            row.hardware_status["conducted_shutdown_ports"], expected_cell=row.hardware_status["controlled_cell"])
            _record_shutdown(db, row, None)
        executions.append_log(db, row.id, level="INFO", source="System",
                              message="已重新确认本次小区关闭、登记输出口禁用和工程卸载。")
    except Exception as exc:
        raise HTTPException(409, f"停止复核未完成：{exc}") from exc
    finally:
        release_unsafe_diagnostic(token)


async def _run(bind, key, snapshot, directory, duration, run, token):
    physical = snapshot["binding"]["execution_mode"] == "real"
    try:
        with Session(bind) as db:
            try:
                async with AsyncExitStack() as resources:
                    staged_directory = None
                    if not physical:
                        staged_directory = resources.enter_context(TemporaryDirectory(prefix="vrt-waveforms-"))
                        _stage_waveforms(directory, snapshot["asset"]["links"], staged_directory)
                    validate = (lambda hal: _real_guard(db, snapshot, hal)) if physical else _mock_only
                    await resources.enter_async_context(instrument_test_lease(
                        "传导虚拟路测 " + key, control_f64=physical, control_uxm=physical,
                        enable_monitoring=False, restore_f64_alignment=False, validate_before_remote=validate))
                    hal = get_hal_service()
                    channel = hal.drivers["channelEmulator"]
                    station = hal.drivers["baseStation"]
                    if physical:
                        row = executions.get(db, key)
                        cell = station.conducted_cell

                        def verify_project():
                            asset = db.get(ChannelAsset, UUID(snapshot["asset"]["id"]), populate_existing=True)
                            if verify_channel_asset_smu_project_bytes(db, asset) != snapshot["asset"]["sha256"].lower():
                                raise RuntimeError("部署工程的当前文件摘要与冻结记录不一致。")
                        playback = hardware_playback(snapshot, station, channel, run.stop, verify_project,
                                                     lambda ports: _record_shutdown(db, row, ports, cell))
                    else:
                        playback = _mock_playback(snapshot, staged_directory, station, channel, run)
                    try:
                        await resources.enter_async_context(playback)
                        clock = asyncio.get_running_loop()
                        start = clock.time()
                        while not run.stop.is_set():
                            if physical:
                                calibration = snapshot["binding"]["real_preflight"]["calibration"]
                                current = db.get(VrtPortCalibration, UUID(calibration["id"]), populate_existing=True)
                                if (current is None or current.revoked_at is not None
                                        or datetime.now(timezone.utc) >= datetime.fromisoformat(calibration["valid_until"])):
                                    raise RuntimeError("本次校准已失效，正在停止设备。")
                                power = await check_running_power(station, channel, calibration)
                                row.hardware_status = {**row.hardware_status, **power,
                                                       "output_average_read_at": datetime.now(timezone.utc).isoformat()}
                                db.commit()
                                playing = await channel.read_playback_state() == "RUNNING"
                            else:
                                playing = (await channel.get_channel_state()).get("running") is True
                            if not playing:
                                raise RuntimeError("未取得信道仿真器的播放确认。")
                            if not run.ready.done():
                                if executions.start(db, key, expected_status=ExecutionStatus.INITIALIZING) is None:
                                    raise RuntimeError("执行状态已改变。")
                                executions.append_log(db, executions.get(db, key).id, level="INFO",
                                                      message="设备回读确认正在播放。" if physical else "模拟驱动已确认播放。", source="System")
                            elapsed = clock.time() - start
                            executions.update_runtime_status(db, key, elapsed_time_s=elapsed,
                                                             progress_percent=min(100, 100 * elapsed / duration))
                            await _sample(db, key, station, channel, elapsed, physical=physical)
                            if not run.ready.done():
                                run.ready.set_result(None)
                            if elapsed >= duration or run.stop.is_set():
                                break
                            try:
                                await asyncio.wait_for(run.stop.wait(), min(1, duration - elapsed))
                            except asyncio.TimeoutError:
                                pass
                    except PlaybackStopRequested:
                        pass  # 设备清理在离开上下文时完成，随后保存停止状态。
                finish = executions.stop if run.stop.is_set() else executions.complete
                expected = ExecutionStatus.RUNNING if run.ready.done() else ExecutionStatus.INITIALIZING
                if finish(db, key, expected_status=expected) is None:
                    raise RuntimeError("停止后执行记录已改变。")
            except (Exception, asyncio.CancelledError) as exc:
                db.rollback()
                reason = str(exc) or "服务结束，执行中断。"
                executions.fail(db, key, reason)
                if not run.ready.done():
                    run.ready.set_result(reason)
                return reason
            if not run.stop.is_set():
                from app.api.road_test import _archive_execution_report
                await _archive_execution_report(key, db)
    finally:
        if not run.ready.done():
            run.ready.set_result("播放未能启动，请查看执行错误。")
        release_unsafe_diagnostic(token)
        _active.pop(key, None)


async def control(db, row, action):
    key = str(row.id)
    run = _active.get(key)
    if action in ("pause", "resume", "complete"):
        raise HTTPException(409, "该虚拟路测不支持手动暂停、恢复或标记完成。")
    if action == "stop":
        if run:
            run.stop.set()
            error = await asyncio.shield(run.task)
            if error:
                raise HTTPException(409, error)
            return
        if "conducted_shutdown_ports" in (row.hardware_status or {}):
            from app.services.instrument_test_lease import await_completion_despite_cancellation
            outcome = await await_completion_despite_cancellation(_recover_stop(db, row))
            if outcome.error:
                raise outcome.error
            if outcome.delayed_cancellation:
                raise outcome.delayed_cancellation
            return
        if row.status == "idle" and executions.stop(db, key, expected_status=ExecutionStatus.IDLE):
            return
        if row.status == "stopped":
            return
        if row.status in ("initializing", "running", "paused"):
            executions.fail(db, key, "服务已失去此次执行的控制权，设备停止状态未知。")
        raise HTTPException(409, "当前执行没有可控制的播放任务。")
    if action != "start" or row.status != "idle" or run:
        raise HTTPException(409, "当前执行状态不允许启动。")
    if row.mode == "ota":
        from app.api.road_test_ota import Selection, resolve
        saved = row.vrt_ota_setup
    else:
        from app.api.road_test_conducted import Selection, resolve
        saved = row.vrt_conducted_setup
    if not isinstance(saved, dict):
        raise HTTPException(409, "请先保存本次所选模式的准备记录。")
    selected = {k: saved.get(k) for k in Selection.model_fields}
    selected.update(scenario_id=row.scenario_id)
    if row.mode == "conducted":
        selected["topology_id"] = row.topology_id
    playback_files = {}
    try:
        selection = Selection.model_validate(selected)
    except ValidationError as exc:
        raise HTTPException(409, "保存的准备记录不完整，请重新准备。") from exc
    fresh = resolve(db, selection, playback_files=playback_files)
    if not fresh["ready"] or fresh != saved:
        raise HTTPException(409, "；".join(fresh["reasons"]) or "准备记录已变化，请重新保存。")
    physical = (fresh.get("binding") or {}).get("execution_mode") == "real"
    directory = playback_files.get("directory")
    if row.mode == "ota" and (physical or _unsettled(db)):
        raise HTTPException(409, "真实 OTA 仍待现场验收，或已有设备尚未确认安全停止。")
    if physical:
        if fresh["scenario_snapshot"]["network"]["type"] != "5G_NR":
            raise HTTPException(409, "本次设备回读流程仅适用于 5G NR 下行场景。")
        if _unsettled(db):
            raise HTTPException(409, "仍有真实传导执行未确认停止，请先对原执行重试停止。")
        if not calibrated_setup("conducted", fresh) or not real_driver_pair(get_hal_service().drivers):
            raise HTTPException(409, "真实执行需要匹配的 UXM、F64 和已核验的逐路校准。")
    elif not (fresh["asset"].get("mock_only") is True and directory and fresh["binding"]["execution_mode"] == "simulated"):
        raise HTTPException(409, "此次模拟执行需要明确绑定已核对文件的模拟专用资产。")
    duration = saved["scenario_snapshot"]["route"]["duration_s"]
    if not math.isfinite(duration) or duration <= 0:
        raise HTTPException(409, "场景缺少有效的路线时长。")
    reason = None if physical else _mock_only(get_hal_service())
    if reason or positioner_refresh_busy():
        raise HTTPException(409, reason or "仪器正由其他操作占用。")
    token = try_acquire_unsafe_diagnostic("传导虚拟路测 " + key)
    if not token:
        raise HTTPException(409, "仪器正由其他操作占用。")
    try:
        if executions._transition(db, key, ExecutionStatus.INITIALIZING, expected_status=ExecutionStatus.IDLE,
                                  log_message="正在启动真实传导播放。" if physical else "正在启动模拟传导播放。") is None:
            raise HTTPException(409, "执行状态已改变。")
        run = Playback(asyncio.get_running_loop().create_future())
        _active[key] = run
        run.task = asyncio.create_task(_run(db.get_bind(), key, fresh, directory, duration, run, token))
    except BaseException:
        release_unsafe_diagnostic(token)
        raise
    error = await asyncio.shield(run.ready)
    if error:
        raise HTTPException(409, error)


async def shutdown_conducted_runs():
    runs = list(_active.values())
    for run in runs:
        run.stop.set()
    await asyncio.gather(*(asyncio.shield(run.task) for run in runs))


def recover_conducted_runs(db):
    restore_conducted_stops([str(row.id) for row in _unsettled(db)])
    rows = db.query(TestExecution).filter(
        TestExecution.mode.in_(("conducted", "ota")),
        TestExecution.status.in_(("initializing", "running", "paused")),
    ).all()
    for row in rows:
        state = row.hardware_status or {}
        # 重启只能终止失去控制权的任务，不能凭数据库记录宣称设备已停止。
        row.hardware_status = {**state, "vrt_restart_recovery": {
            "previous_status": row.status,
            "recovered_at": datetime.now(timezone.utc).isoformat(),
            "device_stop_verified": state.get("conducted_stop_confirmed") is True,
        }}
        reason = ("服务曾中断，停止回读已保存，执行收尾未完成。"
                  if state.get("conducted_stop_confirmed") is True
                  else "服务曾中断，本次执行已结束，未取得设备停止回读。")
        executions.fail(db, str(row.id), reason)
