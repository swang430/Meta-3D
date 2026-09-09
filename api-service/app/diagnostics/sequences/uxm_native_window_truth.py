"""UXM 原生 Single + Length 有限窗口现场诊断（P2-52 / U-13）。

仓库手册原件 `5G_NR_Test_Application_SCPI_Reference.zip` 的
Examples > Measuring BLER 给出 Clear → State 0 → Length → Continuous 0 →
State 1，并说明 BLER 结果首字段 progress-count 达到 Length 时测量结束。

该文档的 Application Mode 只标 NSA | SA，没有覆盖 LTE_NR_IRAT；当前方言的
错误队列也仍是 unverified，所以本序列绝不发送错误队列查询。它只记录两次真机
行为观察，永远不正式判绿，不写 execution/report/KPI，也不改变正式 lifecycle
或 provenance 白名单。
"""
from __future__ import annotations

import asyncio
import inspect
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
)
from app.diagnostics.sequences.uxm_scpi_compatibility import (
    _profile_for_driver,
)
from app.services.instrument_hal_service import is_mock_driver


metadata = SequenceMetadata(
    name="UXM 原生 Single + Length 有限窗口观察",
    description=(
        "P2-52/U-13 现场载体：操作员确认后，在真实 LTE_NR_IRAT 驱动上按"
        "手册既有 Clear/State 0/Length/Continuous 0/State 1 顺序执行两个"
        "窗口，以 DL BLER 首字段 progress-count 精确到界、到界停住和第二"
        "窗口重新起算形成诊断证据。手册范围只标 NSA/SA，故结果始终 "
        "unverified，不进入正式 KPI/lifecycle。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {
            "name": "confirm_write",
            "label": "确认写入真实 UXM（必须显式勾选）",
            "type": "boolean",
            "default": False,
        },
        {
            "name": "measurement_length",
            "label": "原生窗口长度（2000..360000，200 的倍数）",
            "type": "number",
            "default": 2000,
        },
        {
            "name": "poll_interval_s",
            "label": "进度轮询间隔（秒）",
            "type": "number",
            "default": 0.2,
        },
        {
            "name": "timeout_s",
            "label": "每窗口超时（秒）",
            "type": "number",
            "default": 15,
        },
    ],
    safe_during_test=False,
)


_CONNECTED_PROTOCOL_STATES = frozenset({"CONN", "CONNECTED"})
_MAX_PROGRESS_POLLS = 6001
_CELL = "CELL1"


@dataclass(frozen=True)
class _ValidatedParams:
    measurement_length: int
    poll_interval_s: float
    timeout_s: float


class _ObservationBlocked(RuntimeError):
    pass


def _base_extra() -> Dict[str, Any]:
    return {
        "verdict": "ABORTED",
        "formal_verdict": "unverified",
        "requested_length": None,
        "observed_boundary": None,
        "single_shot_observed": None,
        "repeatable_observed": None,
        "windows": [],
        "cleanup": {
            "attempted": False,
            "state_off_sent": False,
            "continuous_mode_restore_required": False,
            "continuous_mode_restored": None,
            "device_acceptance": "unverified",
            "errors": [],
        },
    }


def _validate_params(params: Dict[str, Any]) -> tuple[Optional[_ValidatedParams], str]:
    if params.get("confirm_write") is not True:
        return None, "confirm_write 必须是布尔 true"

    length_raw = params.get("measurement_length", 2000)
    if (
        isinstance(length_raw, bool)
        or not isinstance(length_raw, (int, float))
        or not math.isfinite(float(length_raw))
        or not float(length_raw).is_integer()
    ):
        return None, "measurement_length 必须是有限整数"
    length = int(length_raw)
    if not 2000 <= length <= 360000 or length % 200 != 0:
        return None, "measurement_length 必须在 2000..360000 且为 200 的倍数"

    poll_raw = params.get("poll_interval_s", 0.2)
    timeout_raw = params.get("timeout_s", 15)
    if (
        isinstance(poll_raw, bool)
        or isinstance(timeout_raw, bool)
        or not isinstance(poll_raw, (int, float))
        or not isinstance(timeout_raw, (int, float))
        or not math.isfinite(float(poll_raw))
        or not math.isfinite(float(timeout_raw))
    ):
        return None, "poll_interval_s / timeout_s 必须是有限数字"
    poll = float(poll_raw)
    timeout = float(timeout_raw)
    if not 0.05 <= poll <= 5:
        return None, "poll_interval_s 必须在 0.05..5 秒"
    if not 1 <= timeout <= 600:
        return None, "timeout_s 必须在 1..600 秒"
    if poll > timeout:
        return None, "poll_interval_s 不能大于 timeout_s"
    if math.ceil(timeout / poll) + 2 > _MAX_PROGRESS_POLLS:
        return None, f"每窗口最多 {_MAX_PROGRESS_POLLS} 次进度读取"
    return _ValidatedParams(length, poll, timeout), ""


def _parse_progress(raw: Optional[str]) -> int:
    token = (raw or "").strip().split(",", 1)[0].strip()
    try:
        value = float(token)
    except ValueError as error:
        raise _ObservationBlocked(f"progress-count 解析失败: {raw!r}") from error
    if not math.isfinite(value) or value < 0 or not value.is_integer():
        raise _ObservationBlocked(f"progress-count 解析失败: {raw!r}")
    return int(value)


async def _invoke_driver_method(method: Callable[..., Any], *args: Any) -> Any:
    """同步 VISA 在线程执行；取消时等线程真实停止后再传播。"""
    if inspect.iscoroutinefunction(method):
        return await method(*args)
    worker = asyncio.create_task(asyncio.to_thread(method, *args))
    try:
        result = await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
        try:
            worker.result()
        except Exception:  # noqa: BLE001
            pass
        raise
    if inspect.isawaitable(result):
        return await result
    return result


async def run(
    ctx: Any,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    del ctx
    extra = _base_extra()
    validated, params_error = _validate_params(params)
    if validated is None:
        return SequenceRunResult(
            success=False,
            summary=f"ABORTED: 参数未通过写入确认门：{params_error}；未发送任何 SCPI。",
            extra=extra,
        )
    extra["requested_length"] = validated.measurement_length

    drivers = getattr(hal, "drivers", {}) or {}
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(
            success=False, summary=driver_not_loaded_summary("baseStation"), extra=extra
        )
    if is_mock_driver(bs):
        return SequenceRunResult(
            success=False,
            summary=(
                f"baseStation 当前是 mock 驱动（{type(bs).__name__}，HAL 在 mock 模式）。"
                "本探针只允许连接真实 UXM 后运行。"
            ),
            extra=extra,
        )
    query = getattr(bs, "_query", None)
    write = getattr(bs, "_write", None)
    if not callable(query) or not callable(write):
        return SequenceRunResult(
            success=False,
            summary="ABORTED: baseStation 驱动缺 _query/_write；未发送任何 SCPI。",
            extra=extra,
        )

    profile = _profile_for_driver(bs)
    profile_name = getattr(profile, "PROFILE_NAME", "?")
    extra["profile"] = profile_name
    if profile_name != "LTE_NR_IRAT":
        return SequenceRunResult(
            success=False,
            summary=f"ABORTED: 只允许 LTE_NR_IRAT；当前={profile_name!r}，未发送任何 SCPI。",
            extra=extra,
        )

    required_names = (
        "CELL_STATUS_QUERY",
        "MEAS_BTHROUGHPUT_CLEAR",
        "MEAS_BTHROUGHPUT_STATE",
        "MEAS_BTHROUGHPUT_LENGTH_ALL",
        "MEAS_BTHROUGHPUT_CONTINUOUS_ALL",
        "MEAS_BLER_DL",
    )
    commands = {name: getattr(profile, name, None) for name in required_names}
    missing = [
        name for name, value in commands.items()
        if not isinstance(value, str) or not value
    ]
    if missing:
        return SequenceRunResult(
            success=False,
            summary=f"ABORTED: LTE_NR_IRAT profile 缺 {missing}；未发送任何 SCPI。",
            extra=extra,
        )

    steps: List[SequenceStepResult] = []
    write_attempted = False
    single_mode_attempted = False
    cancelled: Optional[asyncio.CancelledError] = None
    result_summary = ""
    result_verdict = "ABORTED"

    def add_step(
        label: str,
        success: bool,
        detail: str,
        *,
        raw: Optional[str] = None,
        started: Optional[float] = None,
    ) -> None:
        steps.append(SequenceStepResult(
            label=label,
            success=success,
            detail=detail,
            raw=raw,
            duration_ms=(
                int((time.monotonic() - started) * 1000)
                if started is not None else None
            ),
        ))
        log(f"  {'✓' if success else '✗'} {label}: {detail}")

    async def query_raw(command: str) -> Optional[str]:
        value = await _invoke_driver_method(query, command)
        return value if isinstance(value, str) else (None if value is None else str(value))

    async def checked_query(command: str, label: str) -> str:
        started = time.monotonic()
        try:
            raw = await query_raw(command)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            add_step(label, False, f"查询异常 {type(error).__name__}: {error}", started=started)
            raise _ObservationBlocked(
                f"{label} 查询异常 {type(error).__name__}: {error}"
            ) from error
        add_step(label, True, "查询完成", raw=raw, started=started)
        return "" if raw is None else raw

    async def checked_write(command: str, label: str) -> None:
        nonlocal write_attempted
        write_attempted = True
        started = time.monotonic()
        try:
            await _invoke_driver_method(write, command)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            add_step(label, False, f"写入异常 {type(error).__name__}: {error}", started=started)
            raise _ObservationBlocked(
                f"{command} 写入异常 {type(error).__name__}: {error}"
            ) from error
        add_step(
            label,
            True,
            "传输完成；LTE_NR_IRAT 设备接受性仍未验证",
            started=started,
        )

    async def observe_window(index: int) -> Dict[str, Any]:
        nonlocal single_mode_attempted
        length = validated.measurement_length
        await checked_write(commands["MEAS_BTHROUGHPUT_CLEAR"], f"窗口 {index} 清除旧测量")
        await checked_write(
            f'{commands["MEAS_BTHROUGHPUT_STATE"]} 0', f"窗口 {index} 停止测量"
        )
        await checked_write(
            f'{commands["MEAS_BTHROUGHPUT_LENGTH_ALL"]} {length}',
            f"窗口 {index} 请求有限长度",
        )
        # 从调用这一刻起写入结果可能含糊（例如 VISA timeout 发生在设备已接受后），
        # cleanup 必须按“可能已切到 Single”处理。
        single_mode_attempted = True
        extra["cleanup"]["continuous_mode_restore_required"] = True
        extra["cleanup"]["continuous_mode_restored"] = False
        await checked_write(
            f'{commands["MEAS_BTHROUGHPUT_CONTINUOUS_ALL"]} 0',
            f"窗口 {index} 请求 Single 模式",
        )
        await checked_write(
            f'{commands["MEAS_BTHROUGHPUT_STATE"]} 1', f"窗口 {index} 启动测量"
        )

        result_query = commands["MEAS_BLER_DL"].format(cell=_CELL)
        progress: List[int] = []
        started = time.monotonic()
        for _ in range(_MAX_PROGRESS_POLLS):
            if time.monotonic() - started > validated.timeout_s:
                raise _ObservationBlocked(
                    f"窗口 {index} progress-count 在 {validated.timeout_s:g}s 内未到界，超时"
                )
            raw = await checked_query(result_query, f"窗口 {index} 读取 progress-count")
            current = _parse_progress(raw)
            if progress and current < progress[-1]:
                raise _ObservationBlocked(
                    f"窗口 {index} progress-count 回退: {progress[-1]} -> {current}"
                )
            if current > length:
                raise _ObservationBlocked(
                    f"窗口 {index} progress-count 越过请求边界: {current} > {length}"
                )
            progress.append(current)
            if index == 2 and len(progress) == 1 and current >= length:
                raise _ObservationBlocked(
                    f"窗口 2 首样本 {current} 继承窗口 1 终值，未观察到独立重启"
                )
            if current == length:
                await asyncio.sleep(validated.poll_interval_s)
                settled_raw = await checked_query(
                    result_query, f"窗口 {index} 到界后复核 progress-count"
                )
                settled = _parse_progress(settled_raw)
                progress.append(settled)
                if settled != length:
                    raise _ObservationBlocked(
                        f"窗口 {index} Single 到界后未停住: {settled} != {length}"
                    )
                return {
                    "index": index,
                    "progress": progress,
                    "boundary_reached": True,
                    "settled_at_boundary": True,
                }
            await asyncio.sleep(validated.poll_interval_s)
        raise _ObservationBlocked(f"窗口 {index} 进度读取次数超过安全上限")

    async def cleanup() -> None:
        cleanup_state = extra["cleanup"]
        cleanup_state["attempted"] = True
        try:
            # 先停再恢复 Continuous，避免切换模式时继续运行；手册条目明确
            # Continuous=1 是连续模式及默认值。Length 留存但在连续模式下不生效，
            # 不猜测手册范围之外的 Length 恢复值。
            await _invoke_driver_method(
                write, f'{commands["MEAS_BTHROUGHPUT_STATE"]} 0'
            )
            cleanup_state["state_off_sent"] = True
            add_step(
                "cleanup STATe 0",
                True,
                "传输完成；设备接受性未验证",
            )
            if single_mode_attempted:
                await _invoke_driver_method(
                    write, f'{commands["MEAS_BTHROUGHPUT_CONTINUOUS_ALL"]} 1'
                )
                cleanup_state["continuous_mode_restored"] = True
                add_step(
                    "cleanup Continuous 1",
                    True,
                    "已恢复生产测量依赖的连续模式；设备接受性未验证",
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            cleanup_state["exception"] = f"{type(error).__name__}: {error}"
            cleanup_state["errors"].append(cleanup_state["exception"])
            add_step("cleanup", False, cleanup_state["exception"])

    try:
        status_command = commands["CELL_STATUS_QUERY"].format(cell=_CELL)
        status_raw = await checked_query(status_command, "确认 CELL1 已连接")
        status = status_raw.strip().strip('"').upper()
        extra["connected_state_raw"] = status_raw
        if status not in _CONNECTED_PROTOCOL_STATES:
            raise _ObservationBlocked(
                f"CELL1 协议状态 {status_raw!r} 不是 CONN/CONNECTED，未发送窗口写命令"
            )

        first = await observe_window(1)
        extra["windows"].append(first)
        second = await observe_window(2)
        extra["windows"].append(second)
        extra["observed_boundary"] = True
        extra["single_shot_observed"] = True
        extra["repeatable_observed"] = True
        result_verdict = "OBSERVED"
        result_summary = (
            "OBSERVED: 两个 UXM 原生 Single + Length 窗口均精确到界、到界后停住且"
            "第二窗口未继承；但手册范围只标 NSA/SA，LTE_NR_IRAT 仍 unverified，"
            "且未发送无权威依据的 IRAT 错误队列查询，不进入正式 KPI/lifecycle。"
        )
    except asyncio.CancelledError as error:
        cancelled = error
    except _ObservationBlocked as error:
        result_verdict = "BLOCKED" if write_attempted else "ABORTED"
        result_summary = f"{result_verdict}: {error}"
        extra["observed_boundary"] = False if write_attempted else None
        extra["single_shot_observed"] = False if write_attempted else None
        extra["repeatable_observed"] = False if write_attempted else None
    except Exception as error:  # noqa: BLE001
        result_verdict = "BLOCKED" if write_attempted else "ABORTED"
        result_summary = f"{result_verdict}: 未预期异常 {type(error).__name__}: {error}"
    finally:
        if write_attempted:
            cleanup_task = asyncio.create_task(cleanup())
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError as error:
                    cancelled = cancelled or error
                    continue
            try:
                cleanup_task.result()
            except asyncio.CancelledError as error:
                cancelled = cancelled or error
            except Exception as error:  # noqa: BLE001
                extra["cleanup"]["exception"] = f"{type(error).__name__}: {error}"

    if cancelled is not None:
        raise cancelled
    cleanup_complete = (
        extra["cleanup"]["state_off_sent"] is True
        and (
            extra["cleanup"]["continuous_mode_restore_required"] is False
            or extra["cleanup"]["continuous_mode_restored"] is True
        )
    )
    if write_attempted and not cleanup_complete:
        cleanup_detail = extra["cleanup"].get("exception") or (
            "STATe 0 / Continuous 1 必需恢复未完成"
        )
        was_observed = result_verdict == "OBSERVED"
        result_verdict = "BLOCKED"
        if was_observed:
            result_summary = (
                "BLOCKED: 窗口行为已观察，但 cleanup 未同时完成 STATe 0 与 "
                f"Continuous 1 恢复：{cleanup_detail}"
            )
        else:
            result_summary = f"{result_summary}; cleanup 未完成：{cleanup_detail}"
    extra["verdict"] = result_verdict
    return SequenceRunResult(
        success=False,
        summary=result_summary,
        steps=steps,
        extra=extra,
    )
