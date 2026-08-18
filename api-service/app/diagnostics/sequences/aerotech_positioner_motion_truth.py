"""Destructive Aerotech encoder-motion diagnostic for P1-56.

This sequence deliberately does not translate controller coordinates into a
physical DUT azimuth.  It proves only that finite PFBK feedback changed and
reached the requested controller-coordinate target.  User units, direction,
offset and visible mechanical movement remain an on-site Hardware Blocker.

Command source: checked-in
``Instrument_API_Doc/Aerotech/Aerotech_Ensemble_ASCII_TCP转台控制集成说明.docx``
§5–§6 explicitly gives ``ENABLE X``, ``MOVEABS X 90 [XF10]``,
``AXISSTATUS(X)`` and ``PFBK(X)`` plus the wait/readback-before-sampling loop.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Callable, Dict, List, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
)
from app.hal.aerotech_positioner import (
    AxisStatusBit,
    RealAerotechDriver,
    parse_axis_status_bitmask,
)
from app.services.diagnostic_context import DiagnosticContext
from app.services.instrument_hal_service import is_mock_driver


metadata = SequenceMetadata(
    name="Aerotech positioner motion truth (destructive)",
    description=(
        "破坏性现场诊断：保持轴 ENABLE，先发送不带 XF 的小步 MOVEABS，再发送带 XF "
        "的对照命令；每段按固定间隔归档 AXISSTATUS 与 PFBK 原始时间序列。只证明"
        "编码器反馈变化/到达控制器坐标，不证明物理角度、方向、单位或偏置。"
    ),
    required_categories=["positioner"],
    params_schema=[
        {
            "name": "step_deg",
            "label": "控制器坐标小步进（0.1–30，默认 10）",
            "type": "number",
            "default": 10.0,
        },
        {
            "name": "xf_speed",
            "label": "XF 进给速度（0.1–20，默认 5）",
            "type": "number",
            "default": 5.0,
        },
        {
            "name": "sample_duration_s",
            "label": "每段采样秒数（0.2–10，默认 10）",
            "type": "number",
            "default": 10.0,
        },
        {
            "name": "sample_interval_s",
            "label": "采样间隔秒数（0.1–1，默认 0.2）",
            "type": "number",
            "default": 0.2,
        },
        {
            "name": "tolerance_deg",
            "label": "控制器坐标判定容差（0.01–5，默认 0.5）",
            "type": "number",
            "default": 0.5,
        },
    ],
    safe_during_test=False,
)


def _number_param(
    params: Dict[str, Any],
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = params.get(name, default)
    if isinstance(raw, bool):
        raise ValueError(f"{name} 必须是 {minimum}..{maximum} 的有限数值")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} 必须是 {minimum}..{maximum} 的有限数值"
        ) from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须是 {minimum}..{maximum} 的有限数值")
    return value


def _parse_params(params: Dict[str, Any]) -> Dict[str, float]:
    parsed = {
        "step_deg": _number_param(
            params, "step_deg", 10.0, minimum=0.1, maximum=30.0
        ),
        "xf_speed": _number_param(
            params, "xf_speed", 5.0, minimum=0.1, maximum=20.0
        ),
        "sample_duration_s": _number_param(
            params, "sample_duration_s", 10.0, minimum=0.2, maximum=10.0
        ),
        "sample_interval_s": _number_param(
            params, "sample_interval_s", 0.2, minimum=0.1, maximum=1.0
        ),
        "tolerance_deg": _number_param(
            params, "tolerance_deg", 0.5, minimum=0.01, maximum=5.0
        ),
    }
    if parsed["sample_interval_s"] > parsed["sample_duration_s"]:
        raise ValueError("sample_interval_s 不得大于 sample_duration_s")
    return parsed


def _finite(raw: str) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _axis_status_bitmask(raw: str) -> Optional[int]:
    try:
        return parse_axis_status_bitmask(raw)
    except ValueError:
        return None


def _azimuth_distance(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


async def _read_position(driver: RealAerotechDriver, axis: str) -> tuple[str, float]:
    raw = await driver._send(f"PFBK({axis})")  # noqa: SLF001
    value = _finite(raw)
    if value is None:
        raise ValueError(f"PFBK({axis}) 返回非有限数值: {raw!r}")
    return raw, value


async def _abort_and_refresh(
    driver: RealAerotechDriver,
) -> tuple[bool, Optional[str], Optional[float]]:
    """Finish ABORT/PFBK cleanup before releasing the destructive lease."""
    async def cleanup() -> tuple[bool, Optional[str], Optional[float]]:
        stopped = False
        errors: list[str] = []
        try:
            stopped = await driver.stop()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"stop {type(exc).__name__}: {exc}")
        if not stopped and not errors:
            errors.append("driver.stop() returned False")

        post_abort_position: Optional[float] = None
        try:
            position = await driver.get_position()
            if math.isfinite(position[0]):
                post_abort_position = float(position[0])
            else:
                errors.append("post-ABORT PFBK was non-finite")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"PFBK {type(exc).__name__}: {exc}")
        return bool(stopped), "; ".join(errors) or None, post_abort_position

    worker = asyncio.create_task(cleanup())
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            continue
    return worker.result()


async def _sample_segment(
    driver: RealAerotechDriver,
    *,
    axis: str,
    label: str,
    command: str,
    start_position: float,
    target: float,
    duration_s: float,
    interval_s: float,
    tolerance: float,
    operator_stop_generation: Optional[int] = None,
) -> Dict[str, Any]:
    segment: Dict[str, Any] = {
        "label": label,
        "command": command,
        "target": target,
        "start_position": start_position,
        "command_accepted": False,
        "command_response_raw": None,
        "feedback_changed": False,
        "target_reached": False,
        "axis_fault": False,
        "samples_valid": True,
        "samples": [],
        "abort_attempted": False,
        "abort_succeeded": None,
        "abort_error": None,
        "post_abort_position": None,
        "settled": False,
        "operator_stop_requested": False,
    }

    async def abort_segment() -> None:
        segment["abort_attempted"] = True
        (
            segment["abort_succeeded"],
            segment["abort_error"],
            segment["post_abort_position"],
        ) = await _abort_and_refresh(driver)

    if (
        operator_stop_generation is not None
        and driver.operator_stop_generation() != operator_stop_generation
    ):
        segment["operator_stop_requested"] = True
        return segment

    segment["command_started"] = True
    try:
        segment["command_response_raw"] = await driver._send(command)  # noqa: SLF001
        segment["command_accepted"] = True
    except asyncio.CancelledError:
        await abort_segment()
        raise
    except Exception as exc:  # controller rejection belongs in the trace
        segment["command_error"] = f"{type(exc).__name__}: {exc}"
        await abort_segment()
        return segment

    started = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - started
            status_raw: Optional[str] = None
            position_raw: Optional[str] = None
            status_value: Optional[int] = None
            position_value: Optional[float] = None
            sample_error: Optional[str] = None
            try:
                status_raw = await driver._send(f"AXISSTATUS({axis})")  # noqa: SLF001
                position_raw = await driver._send(f"PFBK({axis})")  # noqa: SLF001
                status_value = _axis_status_bitmask(status_raw)
                position_value = _finite(position_raw)
                if status_value is None or position_value is None:
                    raise ValueError("AXISSTATUS/PFBK 包含非有限数值")
            except Exception as exc:
                sample_error = f"{type(exc).__name__}: {exc}"
                segment["samples_valid"] = False

            sample = {
                "elapsed_s": round(elapsed, 6),
                "axisstatus_raw": status_raw,
                "pfbk_raw": position_raw,
                "axisstatus": status_value,
                "position": position_value,
                "error": sample_error,
            }
            segment["samples"].append(sample)
            if status_value is not None and status_value & (1 << AxisStatusBit.FAULT):
                segment["axis_fault"] = True

            if elapsed + 1e-9 >= duration_s:
                break
            await asyncio.sleep(min(interval_s, duration_s - elapsed))
    except asyncio.CancelledError:
        await abort_segment()
        raise

    finite_positions = [
        sample["position"]
        for sample in segment["samples"]
        if sample["position"] is not None
    ]
    if finite_positions:
        segment["feedback_changed"] = any(
            _azimuth_distance(position, start_position) > tolerance
            for position in finite_positions
        )
        segment["target_reached"] = (
            _azimuth_distance(finite_positions[-1], target) <= tolerance
        )
        segment["final_position"] = finite_positions[-1]
    final_status = segment["samples"][-1]["axisstatus"] if segment["samples"] else None
    segment["settled"] = bool(
        final_status is not None
        and final_status & (1 << AxisStatusBit.IN_POSITION)
        and not final_status & (1 << AxisStatusBit.MOVE_ACTIVE)
    )
    motion_proven = bool(
        segment["command_accepted"]
        and segment["feedback_changed"]
        and segment["target_reached"]
        and segment["samples_valid"]
        and not segment["axis_fault"]
        and segment["settled"]
    )
    if segment["command_accepted"] and not motion_proven:
        await abort_segment()
    return segment


def _segment_step(segment: Dict[str, Any]) -> SequenceStepResult:
    success = bool(
        segment["command_accepted"]
        and segment["feedback_changed"]
        and segment["target_reached"]
        and segment["samples_valid"]
        and not segment["axis_fault"]
        and segment["settled"]
    )
    detail = (
        f"accepted={segment['command_accepted']}, "
        f"feedback_changed={segment['feedback_changed']}, "
        f"target_reached={segment['target_reached']}, "
        f"samples_valid={segment['samples_valid']}, "
        f"axis_fault={segment['axis_fault']}, "
        f"settled={segment['settled']}, "
        f"target={segment['target']:.4f}, "
        f"final={segment.get('final_position')!r}"
    )
    return SequenceStepResult(
        label=segment["label"],
        success=success,
        detail=detail,
        raw=json.dumps(segment, ensure_ascii=False, sort_keys=True),
    )


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    try:
        values = _parse_params(params)
    except ValueError as exc:
        return SequenceRunResult(success=False, summary=f"参数错误：{exc}")

    driver = (getattr(hal, "drivers", {}) or {}).get("positioner")
    if driver is None:
        return SequenceRunResult(
            success=False,
            summary=driver_not_loaded_summary("positioner"),
        )
    if is_mock_driver(driver):
        return SequenceRunResult(
            success=False,
            summary="positioner 当前为 mock；本动作诊断只允许真实 Aerotech 硬件。",
        )
    if not isinstance(driver, RealAerotechDriver):
        return SequenceRunResult(
            success=False,
            summary=(
                f"positioner 驱动 {type(driver).__name__} 不是 RealAerotechDriver；"
                "不得把 Aerotech 命令发给其他方言。"
            ),
        )
    if getattr(driver, "_writer", None) is None:
        return SequenceRunResult(
            success=False,
            summary="真实 Aerotech positioner 未连接；未发送 ENABLE/MOVEABS。",
        )
    if not getattr(driver, "_axes_present", None):
        return SequenceRunResult(
            success=False,
            summary="真实 Aerotech 未发现可用轴；未发送 ENABLE/MOVEABS。",
        )

    axis = driver.az_axis
    operator_stop_generation = driver.operator_stop_generation()
    try:
        start_raw, start_position = await _read_position(driver, axis)
        await driver._require_axes_stopped()  # noqa: SLF001
        # Command evidence: the repository copy of the Aerotech Ensemble
        # ASCII/TCP integration manual §5-§6 specifies ENABLE, MOVEABS with
        # optional XF feed, and AXISSTATUS/PFBK polling before sampling.
        enable_raw = await driver._send(f"ENABLE {axis}")  # noqa: SLF001
    except Exception as exc:
        return SequenceRunResult(
            success=False,
            summary=f"起点/ENABLE 失败：{type(exc).__name__}: {exc}",
        )

    first_target = (start_position + values["step_deg"]) % 360.0
    first = await _sample_segment(
        driver,
        axis=axis,
        label="MOVEABS without XF",
        command=f"MOVEABS {axis} {first_target:.4f}",
        start_position=start_position,
        target=first_target,
        duration_s=values["sample_duration_s"],
        interval_s=values["sample_interval_s"],
        tolerance=values["tolerance_deg"],
        operator_stop_generation=operator_stop_generation,
    )

    segments = [first]
    if driver.operator_stop_generation() != operator_stop_generation:
        return SequenceRunResult(
            success=False,
            summary="操作员已急停；诊断已中止，未发送第二段 MOVEABS。",
            steps=[_segment_step(first)],
            extra={
                "axis": axis,
                "start_position": start_position,
                "start_pfbk_raw": start_raw,
                "enable_response_raw": enable_raw,
                "params": values,
                "segments": segments,
                "physical_position_verified": False,
                "operator_stop_requested": True,
            },
        )
    if first["abort_attempted"] and (
        first["abort_succeeded"] is not True
        or not isinstance(first.get("post_abort_position"), (int, float))
    ):
        steps = [_segment_step(first)]
        return SequenceRunResult(
            success=False,
            summary=(
                "第一段动作未获证明且 ABORT/PFBK 收尾未确认；为避免叠加未停止动作，"
                "已禁止发送第二段 MOVEABS。"
            ),
            steps=steps,
            extra={
                "axis": axis,
                "start_position": start_position,
                "start_pfbk_raw": start_raw,
                "enable_response_raw": enable_raw,
                "params": values,
                "segments": segments,
                "physical_position_verified": False,
                "hardware_blocked": [
                    "controller_model_firmware",
                    "user_units",
                    "physical_direction",
                    "coordinate_offset",
                    "visible_mechanical_motion",
                ],
            },
        )

    first_reached = bool(first["target_reached"] and first["feedback_changed"])
    second_start = (
        first.get("post_abort_position")
        if first["abort_attempted"]
        else first.get("final_position", start_position)
    )
    second_target = start_position if first_reached else first_target
    second = await _sample_segment(
        driver,
        axis=axis,
        label="MOVEABS with XF",
        command=(
            f"MOVEABS {axis} {second_target:.4f} "
            f"XF{values['xf_speed']:.4f}"
        ),
        start_position=float(second_start),
        target=second_target,
        duration_s=values["sample_duration_s"],
        interval_s=values["sample_interval_s"],
        tolerance=values["tolerance_deg"],
        operator_stop_generation=operator_stop_generation,
    )

    segments.append(second)
    steps = [_segment_step(segment) for segment in segments]
    final_position = (
        second.get("post_abort_position")
        if second["abort_attempted"]
        else second.get("final_position")
    )
    if isinstance(final_position, (int, float)) and math.isfinite(final_position):
        # This sequence bypasses move_to() so it can preserve raw samples.
        # Keep the driver's cache aligned with the last finite encoder truth.
        driver._current_azimuth = float(final_position)  # noqa: SLF001
    operator_stopped = (
        driver.operator_stop_generation() != operator_stop_generation
    )
    success = not operator_stopped and all(step.success for step in steps)
    if success:
        summary = (
            "编码器动作证据成立：不带 XF 与带 XF 两段均反馈变化并到达控制器坐标；"
            "物理角度/方向/单位/偏置仍待现场目视确认。"
        )
    elif operator_stopped:
        summary = "操作员已急停；诊断结论无效，未声称转台物理位置有效。"
    else:
        summary = (
            "编码器反馈未证明动作：至少一段未变化、未到目标、被拒绝或报告轴故障；"
            "未声称转台物理位置有效。"
        )
    log(f"  · start PFBK({axis})={start_raw!r}; ENABLE={enable_raw!r}")
    for segment in segments:
        log(f"  · {segment['label']}: {_segment_step(segment).detail}")
    return SequenceRunResult(
        success=success,
        summary=summary,
        steps=steps,
        extra={
            "axis": axis,
            "start_position": start_position,
            "start_pfbk_raw": start_raw,
            "enable_response_raw": enable_raw,
            "params": values,
            "segments": segments,
            "physical_position_verified": False,
            "operator_stop_requested": operator_stopped,
            "hardware_blocked": [
                "controller_model_firmware",
                "user_units",
                "physical_direction",
                "coordinate_offset",
                "visible_mechanical_motion",
            ],
        },
    )
