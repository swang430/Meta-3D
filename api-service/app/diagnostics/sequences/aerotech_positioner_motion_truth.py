"""Destructive Aerotech encoder-motion diagnostic for P1-56.

This sequence deliberately refuses to move until the site configuration
explicitly records degree user-units and a verified safe coordinate range.
It proves only that finite PFBK feedback changed and reached the expected
feedback target after applying the explicitly attested program/PFBK offset.
Physical direction, mechanical zero, and visible movement remain on-site
Hardware Blockers.

Command source: the checked-in Aerotech ASCII/TCP integration guide §§5–§7
and CAICT Socket2 site trace 2026-08-27 use ``MOVEABS X 90 XF10``.  The same
site trace proves PFBK may have a stable offset from the program coordinate;
that offset must therefore be explicitly attested before this sequence moves.
Neither source establishes a safe no-XF form or AXISSTATUS bit assignments, so
neither is used as a success predicate here.
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
    AeroBasicCmd,
    AerotechOperatorStopRequested,
    RealAerotechDriver,
)
from app.services.diagnostic_context import DiagnosticContext
from app.services.instrument_hal_service import is_mock_driver


metadata = SequenceMetadata(
    name="Aerotech positioner motion truth (destructive)",
    description=(
        "破坏性现场诊断：仅在站点已确认 degree user-units 与安全范围后，使用带 XF "
        "的 MOVEABS 小步前进并返回；每段归档 VFBK 与 PFBK 原始时间序列。只证明"
        "编码器反馈变化/到达映射后的反馈坐标，不证明物理方向、机械零位或目视运动。"
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
    if "xf_speed" in params:
        parsed["xf_speed"] = _number_param(
            params, "xf_speed", 0.0, minimum=0.1, maximum=20.0
        )
    if parsed["sample_interval_s"] > parsed["sample_duration_s"]:
        raise ValueError("sample_interval_s 不得大于 sample_duration_s")
    return parsed


def _finite(raw: str) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _azimuth_distance(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


async def _read_position(driver: RealAerotechDriver, axis: str) -> tuple[str, float]:
    raw = await driver._send(f"PFBK({axis})")  # noqa: SLF001
    value = _finite(raw)
    if value is None:
        raise ValueError(f"PFBK({axis}) 返回非有限数值: {raw!r}")
    return raw, value


def _verified_degree_motion_config(
    driver: RealAerotechDriver,
) -> tuple[float, float, float, float]:
    """Reuse the formal driver's complete site-approved motion truth."""
    try:
        lower, upper, feed = driver._require_supported_single_axis_motion()  # noqa: SLF001
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    try:
        offset = driver._verified_program_feedback_offset()  # noqa: SLF001
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    return lower, upper, feed, offset


def _bounded_target(
    start: float,
    step: float,
    *,
    lower: float,
    upper: float,
) -> float:
    """Choose a small move without circular wrapping across a mechanical limit."""
    if not lower <= start <= upper:
        raise ValueError(
            f"起点 {start:g} 超出已验证安全范围 [{lower:g}, {upper:g}]"
        )
    forward = start + step
    if forward <= upper:
        return forward
    reverse = start - step
    if reverse >= lower:
        return reverse
    raise ValueError("已验证安全范围不足以容纳请求的小步动作")


async def _abort_and_refresh(
    driver: RealAerotechDriver,
) -> tuple[bool, Optional[str], Optional[float]]:
    """Finish ABORT/PFBK cleanup before releasing the destructive lease."""
    async def cleanup() -> tuple[bool, Optional[str], Optional[float]]:
        # A segment may already have moved. Do not retain its pre-motion cache
        # while the final encoder truth is unknown.
        driver._invalidate_cached_feedback()  # noqa: SLF001
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
        if not stopped:
            # An instantaneous PFBK remains useful raw evidence, but without
            # zero-velocity proof it is not a stable current-position truth.
            driver._invalidate_cached_feedback()  # noqa: SLF001
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
        segment["command_response_raw"] = await driver._send(  # noqa: SLF001
            command,
            expected_operator_stop_generation=operator_stop_generation,
        )
        segment["command_accepted"] = True
    except AerotechOperatorStopRequested:
        segment["command_started"] = False
        segment["operator_stop_requested"] = True
        return segment
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
            velocity_raw: Optional[str] = None
            position_raw: Optional[str] = None
            velocity_value: Optional[float] = None
            position_value: Optional[float] = None
            sample_error: Optional[str] = None
            try:
                velocity_raw = await driver._send(f"VFBK({axis})")  # noqa: SLF001
                position_raw = await driver._send(f"PFBK({axis})")  # noqa: SLF001
                velocity_value = _finite(velocity_raw)
                position_value = _finite(position_raw)
                if velocity_value is None or position_value is None:
                    raise ValueError("VFBK/PFBK 包含非有限数值")
            except Exception as exc:
                sample_error = f"{type(exc).__name__}: {exc}"
                segment["samples_valid"] = False

            sample = {
                "elapsed_s": round(elapsed, 6),
                "vfbk_raw": velocity_raw,
                "pfbk_raw": position_raw,
                "velocity": velocity_value,
                "position": position_value,
                "error": sample_error,
            }
            segment["samples"].append(sample)

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
    final_velocity = (
        segment["samples"][-1]["velocity"] if segment["samples"] else None
    )
    # Fail closed: exact zero is deliberately stricter than inventing an
    # unsourced velocity tolerance.  False negatives are safer than declaring
    # an axis stopped while it is still moving.
    segment["settled"] = final_velocity == 0.0
    motion_proven = bool(
        segment["command_accepted"]
        and segment["feedback_changed"]
        and segment["target_reached"]
        and segment["samples_valid"]
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
        and segment["settled"]
    )
    detail = (
        f"accepted={segment['command_accepted']}, "
        f"feedback_changed={segment['feedback_changed']}, "
        f"target_reached={segment['target_reached']}, "
        f"samples_valid={segment['samples_valid']}, "
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

    try:
        (
            safe_min,
            safe_max,
            approved_feed,
            coordinate_offset,
        ) = _verified_degree_motion_config(driver)
        if "xf_speed" in params and not math.isclose(
            values["xf_speed"], approved_feed, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError(
                "xf_speed 必须等于站点批准的 motion_truth_xf_speed"
            )
        values["xf_speed"] = approved_feed
    except ValueError as exc:
        return SequenceRunResult(
            success=False,
            summary=f"动作真值配置未获现场证明：{exc}；未发送 ENABLE/MOVEABS。",
        )

    axis = driver.az_axis
    operator_stop_generation = driver.operator_stop_generation()
    try:
        start_raw, start_position = await _read_position(driver, axis)
        program_start = start_position - coordinate_offset
        first_feedback_target = _bounded_target(
            start_position,
            values["step_deg"],
            lower=safe_min,
            upper=safe_max,
        )
        first_command_target = first_feedback_target - coordinate_offset
        await driver._require_axes_stopped()  # noqa: SLF001
        # Command evidence: the repository copy of the Aerotech Ensemble
        # ASCII/TCP integration guide §§5-7 specifies ENABLE, MOVEABS with an
        # explicit XF feed, plus VFBK/PFBK readback before sampling.
        enable_raw = await driver._send(  # noqa: SLF001
            f"ENABLE {axis}",
            expected_operator_stop_generation=operator_stop_generation,
        )
    except ValueError as exc:
        return SequenceRunResult(
            success=False,
            summary=f"安全范围拒绝动作：{exc}；未发送 ENABLE/MOVEABS。",
        )
    except Exception as exc:
        return SequenceRunResult(
            success=False,
            summary=f"起点/ENABLE 失败：{type(exc).__name__}: {exc}",
        )
    first = await _sample_segment(
        driver,
        axis=axis,
        label="MOVEABS bounded forward with XF",
        command=AeroBasicCmd.MOVE_ABS.format(
            axis=axis,
            position=f"{first_command_target:.4f}",
            feed=f"{values['xf_speed']:.4f}",
        ),
        start_position=start_position,
        target=first_feedback_target,
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
                "coordinate_offset_deg": coordinate_offset,
                "enable_response_raw": enable_raw,
                "params": values,
                "segments": segments,
                "physical_position_verified": False,
                "operator_stop_requested": True,
            },
        )
    if not _segment_step(first).success:
        steps = [_segment_step(first)]
        return SequenceRunResult(
            success=False,
            summary=(
                "小步动作未获完整证明；为避免叠加未停止动作，已禁止发送返回段 MOVEABS。"
            ),
            steps=steps,
            extra={
                "axis": axis,
                "start_position": start_position,
                "start_pfbk_raw": start_raw,
                "coordinate_offset_deg": coordinate_offset,
                "enable_response_raw": enable_raw,
                "params": values,
                "segments": segments,
                "physical_position_verified": False,
                "hardware_blocked": [
                    "controller_model_firmware",
                    "physical_direction",
                    "visible_mechanical_motion",
                ],
            },
        )

    second_start = first.get("final_position", first_feedback_target)
    second_command_target = program_start
    second_feedback_target = start_position
    second = await _sample_segment(
        driver,
        axis=axis,
        label="MOVEABS bounded return with XF",
        command=AeroBasicCmd.MOVE_ABS.format(
            axis=axis,
            position=f"{second_command_target:.4f}",
            feed=f"{values['xf_speed']:.4f}",
        ),
        start_position=float(second_start),
        target=second_feedback_target,
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
    final_position_stable = (
        _segment_step(second).success
        or (
            second["abort_attempted"]
            and second.get("abort_succeeded") is True
        )
    )
    if (
        final_position_stable
        and isinstance(final_position, (int, float))
        and math.isfinite(final_position)
    ):
        # This sequence bypasses move_to() so it can preserve raw samples.
        # Publish only a position whose segment settled, or whose ABORT was
        # followed by zero-velocity proof. A moving PFBK remains raw evidence.
        driver._sync_cached_feedback((float(final_position), 0.0))  # noqa: SLF001
    operator_stopped = (
        driver.operator_stop_generation() != operator_stop_generation
    )
    success = not operator_stopped and all(step.success for step in steps)
    if success:
        summary = (
            "编码器动作证据成立：带显式 XF 的小步前进与返回均反馈变化并到达"
            "映射后的 degree 反馈坐标；物理方向/机械零位仍待现场目视确认。"
        )
    elif operator_stopped:
        summary = "操作员已急停；诊断结论无效，未声称转台物理位置有效。"
    else:
        summary = (
            "编码器反馈未证明动作：至少一段未变化、未到目标、未停止或被拒绝；"
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
            "coordinate_offset_deg": coordinate_offset,
            "enable_response_raw": enable_raw,
            "params": values,
            "segments": segments,
            "physical_position_verified": False,
            "operator_stop_requested": operator_stopped,
            "hardware_blocked": [
                "controller_model_firmware",
                "physical_direction",
                "visible_mechanical_motion",
            ],
        },
    )
