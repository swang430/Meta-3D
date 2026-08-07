"""UXM RF App maximum downlink throughput control-loop diagnostic.

This sequence intentionally does not configure/restart the cell and has no
performance pass threshold.  Success means the software controlled the RF App
measurement lifecycle and received at least one real DL throughput sample.
"""
from __future__ import annotations

import asyncio
import math
import statistics
import time
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="UXM RF App 最大DL吞吐测试",
    description=(
        "保持当前小区和UE Attach状态，只执行RF App下行MAC Padding/BTPut启动、"
        "真实吞吐与BLER采样、停止和原设置恢复。无吞吐或BLER合格门限。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "NR小区", "type": "string", "default": "CELL1"},
        {"name": "duration_s", "label": "持续时间（秒）", "type": "number", "default": 30},
        {
            "name": "sample_interval_s",
            "label": "采样间隔（秒）",
            "type": "number",
            "default": 1,
        },
        {
            "name": "measurement_length_slots",
            "label": "BTPut窗口（DL Slot）",
            "type": "number",
            "default": 200,
        },
    ],
    safe_during_test=False,
)


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _number_stats(values: Iterable[Optional[float]]) -> Optional[Dict[str, float]]:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not valid:
        return None
    return {
        "mean": statistics.fmean(valid),
        "min": min(valid),
        "max": max(valid),
        "std": statistics.pstdev(valid) if len(valid) > 1 else 0.0,
    }


def _validate_params(params: Dict[str, Any]) -> tuple[str, float, float, int]:
    cell = str(params.get("cell", "CELL1")).strip().upper()
    duration_s = float(params.get("duration_s", 30))
    interval_s = float(params.get("sample_interval_s", 1))
    raw_length = float(params.get("measurement_length_slots", 200))
    if not raw_length.is_integer():
        raise ValueError("measurement_length_slots 必须是整数")
    length = int(raw_length)
    if cell != "CELL1":
        raise ValueError("第一版仅支持 CELL1")
    if not 1 <= duration_s <= 600:
        raise ValueError("duration_s 必须在 1..600 秒之间")
    if not 0.2 <= interval_s <= 10:
        raise ValueError("sample_interval_s 必须在 0.2..10 秒之间")
    if interval_s > duration_s:
        raise ValueError("sample_interval_s 不能大于 duration_s")
    if length < 200 or length > 360000 or length % 200 != 0:
        raise ValueError("measurement_length_slots 必须为 200..360000 且为200的整数倍")
    return cell, duration_s, interval_s, length


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    del ctx  # The bound HAL is the only context this hardware diagnostic needs.
    drivers = getattr(hal, "drivers", {}) or {}
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(False, driver_not_loaded_summary("baseStation"))
    refusal = mock_driver_refusal_summary("baseStation", bs)
    if refusal:
        return SequenceRunResult(False, refusal)

    steps: list[SequenceStepResult] = []
    samples: list[Dict[str, Any]] = []
    runtime_errors: list[str] = []
    context: Dict[str, Any] = {}
    start_detail: Dict[str, Any] = {}
    cleanup: Dict[str, Any] = {"required": False, "stopped": False}
    final_status: Dict[str, Any] = {}
    started_at = _utc_now()
    failure: Optional[str] = None
    started = False

    try:
        cell, duration_s, interval_s, length = _validate_params(params)
    except (TypeError, ValueError) as exc:
        return SequenceRunResult(
            success=False,
            summary=f"参数校验失败: {exc}",
            steps=[SequenceStepResult("参数校验", False, str(exc))],
        )

    required_methods = (
        "get_rf_app_dl_throughput_context",
        "start_rf_app_max_dl_throughput",
        "read_rf_app_max_dl_throughput",
        "stop_rf_app_max_dl_throughput",
        "get_rf_app_dl_throughput_final_status",
    )
    missing = [name for name in required_methods if not callable(getattr(bs, name, None))]
    profile_name = getattr(getattr(bs, "_cmds", None), "PROFILE_NAME", None)
    if missing or profile_name != "IRAT_LITE":
        detail = (
            f"需要真实 UXM IRAT_LITE Profile；当前 profile={profile_name or 'unknown'}, "
            f"missing_methods={missing}"
        )
        return SequenceRunResult(
            success=False,
            summary=detail,
            steps=[SequenceStepResult("检查 UXM RF App Profile", False, detail)],
        )

    async def step(label: str, awaitable: Any) -> Any:
        begin = time.monotonic()
        try:
            value = await awaitable
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            steps.append(
                SequenceStepResult(
                    label=label,
                    success=False,
                    detail=detail,
                    duration_ms=int((time.monotonic() - begin) * 1000),
                )
            )
            log(f"  ✗ {label}: {detail}")
            raise
        steps.append(
            SequenceStepResult(
                label=label,
                success=True,
                detail=str(value) if value is not None else "ok",
                duration_ms=int((time.monotonic() - begin) * 1000),
            )
        )
        log(f"  ✓ {label}")
        return value

    try:
        context = await step(
            "检查 UXM在线及IRAT_LITE应用",
            bs.get_rf_app_dl_throughput_context(cell),
        )
        cell_config = context.get("cell_config", {})
        status = str(cell_config.get("status", "")).strip().upper()
        if status not in {"CONN", "CONNECTED"}:
            steps.append(
                SequenceStepResult(
                    "确认 CELL1 为 CONN/CONNected",
                    False,
                    f"当前状态 {status or 'unknown'}",
                )
            )
            raise RuntimeError(f"CELL1 必须为 CONN/CONNected，当前为 {status or 'unknown'}")
        steps.append(
            SequenceStepResult(
                "确认 CELL1 为 CONN/CONNected",
                True,
                f"status={status}",
            )
        )
        steps.append(
            SequenceStepResult(
                "记录当前 Band/ARFCN/带宽/Cell Power",
                True,
                str(cell_config),
            )
        )
        log(
            "  · 当前小区保持不变: "
            f"band={cell_config.get('band')} arfcn={cell_config.get('dl_arfcn')} "
            f"bw={cell_config.get('dl_bandwidth')} power={cell_config.get('dl_power_dbm_per_bw')}"
        )

        start_detail = await step(
            "启动 RF App 最大下行吞吐",
            bs.start_rf_app_max_dl_throughput(cell, length),
        )
        started = True
        cleanup["required"] = True

        sample_started = time.monotonic()
        sample_count = max(1, math.ceil(duration_s / interval_s))
        try:
            for index in range(sample_count):
                await asyncio.sleep(interval_s)
                sample = await bs.read_rf_app_max_dl_throughput(cell)
                sample = dict(sample or {})
                sample["sample_index"] = index + 1
                samples.append(sample)
                throughput = sample.get("dl_throughput_mbps")
                bler = sample.get("dl_bler")
                log(
                    f"  · sample {index + 1}/{sample_count}: "
                    f"DL={throughput if throughput is not None else 'NaN'} Mbps, "
                    f"BLER={bler if bler is not None else 'NaN'}, "
                    f"source={sample.get('source', 'unknown')}"
                )
            valid_count = sum(
                1 for sample in samples if sample.get("valid") and sample.get("dl_throughput_mbps") is not None
            )
            steps.append(
                SequenceStepResult(
                    "连续采样真实DL吞吐/BLER",
                    True,
                    f"{len(samples)} samples, {valid_count} valid throughput samples",
                    int((time.monotonic() - sample_started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            runtime_errors.append(detail)
            steps.append(
                SequenceStepResult(
                    "连续采样真实DL吞吐/BLER",
                    False,
                    detail,
                    int((time.monotonic() - sample_started) * 1000),
                )
            )
            raise
    except Exception as exc:  # noqa: BLE001
        failure = f"{type(exc).__name__}: {exc}"
        if failure not in runtime_errors:
            runtime_errors.append(failure)
    finally:
        cleanup_required = started or bool(
            getattr(bs, "rf_app_dl_throughput_cleanup_required", False)
        )
        cleanup["required"] = cleanup_required
        if cleanup_required:
            try:
                # Shield the instrument stop/restore from normal task
                # cancellation so a user cancel does not leave BTPut running.
                cleanup_result = await asyncio.shield(
                    bs.stop_rf_app_max_dl_throughput()
                )
                cleanup.update(dict(cleanup_result or {}))
                cleanup["stopped"] = bool(cleanup.get("stopped", True))
                steps.append(
                    SequenceStepResult(
                        "停止吞吐并恢复原测量设置",
                        cleanup["stopped"],
                        str(cleanup_result),
                    )
                )
                log("  ✓ 停止吞吐并恢复原测量设置")
            except Exception as exc:  # noqa: BLE001
                cleanup["stopped"] = False
                cleanup["error"] = f"{type(exc).__name__}: {exc}"
                runtime_errors.append(cleanup["error"])
                failure = failure or cleanup["error"]
                steps.append(
                    SequenceStepResult(
                        "停止吞吐并恢复原测量设置",
                        False,
                        cleanup["error"],
                    )
                )
                log(f"  ✗ 停止吞吐并恢复原测量设置: {cleanup['error']}")

    # Final audit is useful even after a sampling/cleanup error.  Do not let a
    # failed audit hide the original error.
    try:
        final_status = await step(
            "查询最终小区/测量状态和SCPI错误队列",
            bs.get_rf_app_dl_throughput_final_status(cell),
        )
    except Exception as exc:  # noqa: BLE001
        audit_error = f"{type(exc).__name__}: {exc}"
        runtime_errors.append(audit_error)
        failure = failure or audit_error

    valid_samples = [
        sample
        for sample in samples
        if sample.get("valid") and sample.get("dl_throughput_mbps") is not None
    ]
    throughput_stats = _number_stats(
        sample.get("dl_throughput_mbps") for sample in valid_samples
    )
    bler_stats = _number_stats(sample.get("dl_bler") for sample in samples)
    kpi_summary: Dict[str, Any] = {}
    if throughput_stats:
        kpi_summary["dl_throughput_mbps"] = throughput_stats
    if bler_stats:
        kpi_summary["dl_bler"] = bler_stats

    final_scpi_errors = final_status.get("scpi_errors", [])
    if final_scpi_errors:
        runtime_errors.extend(str(error) for error in final_scpi_errors)
        failure = failure or f"SCPI error queue: {final_scpi_errors}"
    if started and not valid_samples:
        failure = failure or "全程未读取到有效DL吞吐样本"
    if started and not cleanup.get("stopped"):
        failure = failure or "停止吞吐失败"
    if not started:
        failure = failure or "启动吞吐失败"

    finished_at = _utc_now()
    extra = {
        "instrument_modes": {
            "baseStation": "real",
            "kpi_source": "UXM RF App BTPut/TMONitor",
        },
        "uxm_rf_app_dl_throughput": {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_s": duration_s,
            "sample_interval_s": interval_s,
            "measurement_length_slots": length,
            "valid_sample_count": len(valid_samples),
            "total_sample_count": len(samples),
            "no_performance_threshold": True,
        },
        "instrument": {
            "identity": context.get("identity"),
            "app_name": context.get("app_name"),
            "detected_test_app": context.get("detected_test_app"),
            "command_profile": context.get("command_profile"),
        },
        "cell_config": context.get("cell_config", {}),
        "start": start_detail,
        "samples": samples,
        "kpi_summary": kpi_summary,
        "cleanup": cleanup,
        "final_status": final_status,
        "scpi_errors": {
            "preexisting": context.get("preexisting_scpi_errors", []),
            "during_run": runtime_errors,
            "final": final_scpi_errors,
        },
    }
    if failure:
        return SequenceRunResult(
            success=False,
            summary=f"UXM RF App 最大DL吞吐控制流程失败: {failure}",
            steps=steps,
            extra=extra,
        )
    return SequenceRunResult(
        success=True,
        summary=(
            f"控制流程执行成功：获得 {len(valid_samples)} 个真实DL吞吐样本；"
            "吞吐和BLER仅作信息记录，不设合格门限"
        ),
        steps=steps,
        extra=extra,
    )
