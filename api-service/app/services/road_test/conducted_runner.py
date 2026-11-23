"""在服务端持有传导执行的设备租约；仅开放已核实可隔离运行的模拟驱动。"""
import asyncio
import hashlib
import math
import shutil
from pathlib import Path
from contextlib import ExitStack
from tempfile import TemporaryDirectory
from dataclasses import dataclass, field

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.hal.base_station import CellState
from app.hal.channel_emulator import ChannelLoadMode
from app.schemas.road_test import ExecutionStatus
from app.services.execution_exclusion_guard import (
    release_unsafe_diagnostic, try_acquire_unsafe_diagnostic,
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


async def _sample(db, key, station, channel, elapsed):
    info = await station.get_ue_info()
    rates = await station.get_throughput_metrics()
    for metric, value, driver in (
        ("connection_state", info.get("connected"), station),
        ("dl_throughput_mbps", rates.dl_throughput_mbps, station),
        ("playback_position_s", None, channel),
    ):
        executions.record_observation(db, key, metric=metric, value=value, driver=driver, time_s=elapsed)


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


async def _run(bind, key, snapshot, directory, duration, run, token):
    try:
        with Session(bind) as db, ExitStack() as resources:
            try:
                staged_directory = resources.enter_context(TemporaryDirectory(prefix="vrt-waveforms-"))
                _stage_waveforms(directory, snapshot["asset"]["links"], staged_directory)
                async with instrument_test_lease("传导虚拟路测 " + key, control_f64=False,
                                                 control_uxm=False, validate_before_remote=_mock_only):
                    hal = get_hal_service()
                    reason = _mock_only(hal)
                    if reason:
                        raise RuntimeError(reason)
                    channel = hal.drivers["channelEmulator"]
                    station = hal.drivers["baseStation"]
                    try:
                        if run.stop.is_set():
                            raise InterruptedError("加载前已收到停止请求。")
                        if not await channel.load_channel(ChannelLoadMode.EXTERNAL_WAVEFORM, snapshot["asset"]["sha256"],
                                                          snapshot["scenario_id"], {}, waveform_dir=staged_directory):
                            raise RuntimeError("模拟驱动拒绝加载工程。")
                        if run.stop.is_set():
                            raise InterruptedError("加载过程中收到停止请求。")
                        if not await station.start_signaling() or (await station.get_ue_info()).get("connected") is not True:
                            raise RuntimeError("模拟基站未确认连接。")
                        if run.stop.is_set():
                            raise InterruptedError("启动播放前已收到停止请求。")
                        if not await channel.set_mimo_config(4, 2) or not await channel.start_emulation():
                            raise RuntimeError("模拟驱动拒绝启动播放。")
                        clock = asyncio.get_running_loop()
                        start = clock.time()
                        while True:
                            if (await channel.get_channel_state()).get("running") is not True:
                                raise RuntimeError("模拟驱动未确认正在播放。")
                            if not run.ready.done():
                                if executions.start(db, key, expected_status=ExecutionStatus.INITIALIZING) is None:
                                    raise RuntimeError("执行状态已改变。")
                                executions.append_log(db, executions.get(db, key).id, level="INFO",
                                                      message="模拟驱动已确认播放。", source="System")
                            elapsed = clock.time() - start
                            executions.update_runtime_status(db, key, elapsed_time_s=elapsed,
                                                             progress_percent=min(100, 100 * elapsed / duration))
                            await _sample(db, key, station, channel, elapsed)
                            if not run.ready.done():
                                run.ready.set_result(None)
                            if elapsed >= duration or run.stop.is_set():
                                break
                            try:
                                await asyncio.wait_for(run.stop.wait(), min(1, duration - elapsed))
                            except asyncio.TimeoutError:
                                pass
                    except InterruptedError:
                        if not run.stop.is_set():
                            raise
                    finally:
                        await _stop_devices(channel, station)
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
        raise HTTPException(409, "该传导执行不支持手动暂停、恢复或标记完成。")
    if action == "stop":
        if run:
            run.stop.set()
            error = await asyncio.shield(run.task)
            if error:
                raise HTTPException(409, error)
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
    from app.api.road_test_conducted import Selection, resolve
    saved = row.vrt_conducted_setup
    if not isinstance(saved, dict):
        raise HTTPException(409, "请先保存本次传导测试的准备记录。")
    selected = {k: saved.get(k) for k in Selection.model_fields}
    selected.update(scenario_id=row.scenario_id, topology_id=row.topology_id)
    playback_files = {}
    try:
        selection = Selection.model_validate(selected)
    except ValidationError as exc:
        raise HTTPException(409, "保存的传导准备记录不完整，请重新准备。") from exc
    fresh = resolve(db, selection, playback_files=playback_files)
    if not fresh["ready"] or fresh != saved:
        raise HTTPException(409, "；".join(fresh["reasons"]) or "准备记录已变化，请重新保存。")
    if fresh["asset"].get("mock_only") is not True or (fresh.get("binding") or {}).get("execution_mode") != "simulated":
        raise HTTPException(409, "此次执行需要明确绑定八路文件的模拟专用资产。")
    directory = playback_files.get("directory")
    if not directory:
        raise HTTPException(409, "模拟资产缺少已核验的文件目录。")
    duration = saved["scenario_snapshot"]["route"]["duration_s"]
    if not math.isfinite(duration) or duration <= 0:
        raise HTTPException(409, "场景缺少有效的路线时长。")
    reason = _mock_only(get_hal_service())
    if reason or positioner_refresh_busy():
        raise HTTPException(409, reason or "仪器正由其他操作占用。")
    token = try_acquire_unsafe_diagnostic("传导虚拟路测 " + key)
    if not token:
        raise HTTPException(409, "仪器正由其他操作占用。")
    try:
        if executions._transition(db, key, ExecutionStatus.INITIALIZING, expected_status=ExecutionStatus.IDLE,
                                  log_message="正在启动模拟传导播放。") is None:
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
    from app.models.test_plan import TestExecution
    rows = db.query(TestExecution).filter(
        TestExecution.mode == "conducted",
        TestExecution.status.in_(("initializing", "running", "paused")),
    ).all()
    for row in rows:
        executions.fail(db, str(row.id), "服务曾中断，本次执行已结束，未取得设备停止回读。")
