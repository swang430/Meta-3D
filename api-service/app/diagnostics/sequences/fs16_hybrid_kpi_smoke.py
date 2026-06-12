"""FS16 real playback + BS/DUT KPI smoke.

Workshop-tier hybrid path for the current bring-up target:

* channelEmulator is a real PROPSIM FS16 playback driver
* baseStation is normally mock today, but may be real later via
  ``base_station_mode=real``
* DUT/UE performance is represented by the base-station driver's KPI surface

This intentionally does not replace ``conducted_bs_ce_dut_smoke``.  The older
sequence keeps its passthrough semantics; this one exercises the FS16 .smu
playback path and then samples the BS/DUT KPI loop.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any, Callable, Dict, List, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
from app.hal.channel_emulator import ChannelLoadMode
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="FS16 hybrid KPI smoke",
    description=(
        "Loads an SMU playback file on the real FS16, then configures the "
        "currently loaded baseStation driver and samples DUT KPI metrics. "
        "Default base_station_mode=mock protects today's FS16-only workflow; "
        "use base_station_mode=real after a real BS emulator is intentionally "
        "connected."
    ),
    required_categories=["channelEmulator", "baseStation"],
    params_schema=[
        {
            "name": "remote_playback_file",
            "label": "FS16 SMU playback file",
            "type": "string",
            "default": "Emulation0609.smu",
        },
        {
            "name": "verify_remote_file_exists",
            "label": "Verify SMU exists before load",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "start_playback",
            "label": "Start FS16 playback after load",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "stop_after_s",
            "label": "Stop playback after seconds (0 = leave running)",
            "type": "number",
            "default": 5,
        },
        {
            "name": "cleanup_on_finish",
            "label": "Cleanup BS/FS16 state on finish",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "base_station_mode",
            "label": "baseStation mode: mock or real",
            "type": "string",
            "default": "mock",
            "options": ["mock", "real"],
        },
        {"name": "frequency_mhz", "label": "Virtual BS frequency MHz", "type": "number", "default": 3500},
        {"name": "bandwidth_mhz", "label": "Virtual BS bandwidth MHz", "type": "number", "default": 100},
        {"name": "scs_khz", "label": "Virtual BS SCS kHz", "type": "number", "default": 30},
        {"name": "band", "label": "Virtual BS band", "type": "string", "default": "n78"},
        {"name": "mimo_layers", "label": "Virtual BS MIMO layers", "type": "number", "default": 2},
        {"name": "dl_power_dbm", "label": "Virtual BS DL power dBm", "type": "number", "default": -50},
        {"name": "attach_timeout_s", "label": "Mock DUT attach timeout seconds", "type": "number", "default": 15},
        {"name": "attach_poll_interval_s", "label": "Attach poll interval seconds", "type": "number", "default": 1},
        {"name": "throughput_windows", "label": "KPI sample windows", "type": "number", "default": 3},
        {"name": "throughput_window_s", "label": "KPI window seconds", "type": "number", "default": 0.2},
    ],
    safe_during_test=False,
)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _compact_detail(value: Any) -> str:
    if value is None or value is True:
        return "ok"
    text = str(value)
    return text if len(text) <= 240 else text[:237] + "..."


def _driver_class(driver: Any) -> str:
    return type(driver).__name__


def _driver_mode(driver: Any) -> str:
    return "mock" if _driver_class(driver).startswith("Mock") else "real"


def _driver_last_error(driver: Any) -> str:
    try:
        err = getattr(driver, "last_error", None)
        if callable(err):
            err = err()
    except Exception:  # noqa: BLE001
        err = None
    if err:
        return str(err)
    try:
        err = getattr(driver, "_last_error", None)
    except Exception:  # noqa: BLE001
        err = None
    return str(err) if err else ""


def _remote_playback_path(ce: Any, remote_file: str) -> str:
    path_fn = getattr(ce, "remote_playback_path", None)
    if callable(path_fn):
        try:
            return str(path_fn(remote_file))
        except Exception:  # noqa: BLE001
            pass
    private_path_fn = getattr(ce, "_remote_path", None)
    if callable(private_path_fn):
        try:
            return str(private_path_fn(remote_file))
        except Exception:  # noqa: BLE001
            pass
    return remote_file


async def _verify_remote_playback_file(ce: Any, remote_file: str) -> Dict[str, Any]:
    remote_path = _remote_playback_path(ce, remote_file)
    public_checker = getattr(ce, "remote_playback_file_exists", None)
    if callable(public_checker):
        exists = await _maybe_await(public_checker(remote_file))
        checked_by = "remote_playback_file_exists"
    else:
        private_checker = getattr(ce, "_remote_file_exists", None)
        if not callable(private_checker):
            return {
                "remote_playback_path": remote_path,
                "visible": None,
                "checked": False,
                "note": "driver has no file-list precheck; load step will verify",
            }
        exists = await _maybe_await(private_checker(remote_path))
        checked_by = "_remote_file_exists"

    if not exists:
        detail = f"remote playback file not found on FS16: {remote_path}"
        last_error = _driver_last_error(ce)
        if last_error and last_error not in detail:
            detail = f"{detail}; last_error={last_error}"
        raise RuntimeError(detail)

    return {
        "remote_playback_path": remote_path,
        "visible": True,
        "checked": True,
        "checked_by": checked_by,
    }


def _bool_param(params: Dict[str, Any], key: str, default: bool) -> bool:
    value = params.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _float_param(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_param(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _str_param(params: Dict[str, Any], key: str, default: str) -> str:
    value = params.get(key, default)
    return str(value if value is not None else default).strip()


async def _step(
    steps: List[SequenceStepResult],
    log: Callable[[str], None],
    label: str,
    action: Any,
    *,
    require_truthy: bool = True,
    require_not_none: bool = False,
    false_detail: Callable[[], str] | None = None,
) -> Any:
    started = time.monotonic()
    try:
        value = action() if callable(action) else action
        result = await _maybe_await(value)
        if require_truthy and result is False:
            detail = false_detail() if false_detail else ""
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"driver returned False{suffix}")
        if require_not_none and result is None:
            raise RuntimeError("driver returned None")
        steps.append(
            SequenceStepResult(
                label=label,
                success=True,
                detail=_compact_detail(result),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        log(f"  OK {label}")
        return result
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        steps.append(
            SequenceStepResult(
                label=label,
                success=False,
                detail=detail,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        log(f"  FAIL {label}: {detail}")
        raise


def _is_attached(info: Any) -> bool:
    if not isinstance(info, dict):
        return False
    if info.get("connected") is True or info.get("rrc_connected") is True:
        return True
    state = str(
        info.get("rrc_state")
        or info.get("cell_state")
        or info.get("state")
        or ""
    ).upper()
    return state in {"CONNECTED", "CONN", "RRC_CONNECTED"}


async def _wait_for_attach(
    bs: Any,
    *,
    timeout_s: float,
    poll_interval_s: float,
    steps: List[SequenceStepResult],
    log: Callable[[str], None],
) -> tuple[bool, Optional[Dict[str, Any]]]:
    started = time.monotonic()
    deadline = started + max(timeout_s, 0.0)
    last_info: Optional[Dict[str, Any]] = None

    while True:
        try:
            info = await _maybe_await(bs.get_ue_info())
            if isinstance(info, dict):
                last_info = info
            if _is_attached(info):
                steps.append(
                    SequenceStepResult(
                        label="DUT attach",
                        success=True,
                        detail=_compact_detail(info),
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                )
                log(f"  OK DUT attach: {info}")
                return True, last_info
        except Exception as exc:  # noqa: BLE001
            last_info = {"query_error": f"{type(exc).__name__}: {exc}"}

        if time.monotonic() >= deadline:
            detail = (
                "No mock/real UE attached within timeout"
                if last_info is None
                else f"No mock/real UE attached within timeout; last_ue_info={last_info}"
            )
            steps.append(
                SequenceStepResult(
                    label=f"DUT attach (timeout {timeout_s:.1f}s)",
                    success=False,
                    detail=detail,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            log(f"  FAIL DUT attach: {detail}")
            return False, last_info

        await asyncio.sleep(
            min(max(poll_interval_s, 0.01), max(0.0, deadline - time.monotonic()))
        )


def _metrics_to_dict(metrics: Any) -> Dict[str, Any]:
    if hasattr(metrics, "to_dict"):
        return metrics.to_dict()
    if isinstance(metrics, dict):
        return dict(metrics)
    raise TypeError("KPI metric must be dict-like or expose to_dict()")


def _numeric_summary(samples: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    numeric_fields: Dict[str, List[float]] = {}
    for sample in samples:
        for key, value in sample.items():
            if key == "window_index":
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_fields.setdefault(key, []).append(float(value))

    summary: Dict[str, Dict[str, float]] = {}
    for key, values in numeric_fields.items():
        if not values:
            continue
        summary[key] = {
            "mean": round(statistics.fmean(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        }
    return summary


def _restore_attr(obj: Any, name: str, value: Any, existed: bool) -> None:
    if existed:
        setattr(obj, name, value)
    elif hasattr(obj, name):
        try:
            delattr(obj, name)
        except AttributeError:
            pass


async def _cleanup(
    bs: Any,
    ce: Any,
    *,
    stop_bs: bool,
    stop_ce: bool,
    steps: List[SequenceStepResult],
    log: Callable[[str], None],
) -> tuple[List[str], bool, bool]:
    warnings: List[str] = []
    stopped_bs = False
    stopped_ce = False
    if stop_bs and hasattr(bs, "stop_signaling"):
        started = time.monotonic()
        try:
            result = await _maybe_await(bs.stop_signaling())
            if result is False:
                raise RuntimeError("driver returned False")
            steps.append(
                SequenceStepResult(
                    label="BS stop_signaling",
                    success=True,
                    detail=_compact_detail(result),
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            log("  OK BS stop_signaling")
            stopped_bs = True
        except Exception as exc:  # noqa: BLE001
            detail = f"stop_signaling cleanup raised {type(exc).__name__}: {exc}"
            warnings.append(detail)
            steps.append(
                SequenceStepResult(
                    label="BS stop_signaling",
                    success=False,
                    detail=detail,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            log(f"  WARN BS stop_signaling: {detail}")
    if stop_ce and hasattr(ce, "stop_emulation"):
        started = time.monotonic()
        try:
            result = await _maybe_await(ce.stop_emulation())
            if result is False:
                detail = _driver_last_error(ce)
                suffix = f": {detail}" if detail else ""
                raise RuntimeError(f"driver returned False{suffix}")
            steps.append(
                SequenceStepResult(
                    label="FS16 stop playback",
                    success=True,
                    detail=_compact_detail(result),
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            log("  OK FS16 stop playback")
            stopped_ce = True
        except Exception as exc:  # noqa: BLE001
            detail = f"stop_emulation cleanup raised {type(exc).__name__}: {exc}"
            warnings.append(detail)
            steps.append(
                SequenceStepResult(
                    label="FS16 stop playback",
                    success=False,
                    detail=detail,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            log(f"  WARN FS16 stop playback: {detail}")
    return warnings, stopped_bs, stopped_ce


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    del ctx
    drivers = getattr(hal, "drivers", {}) or {}
    ce = drivers.get("channelEmulator")
    if ce is None:
        return SequenceRunResult(
            success=False,
            summary=driver_not_loaded_summary("channelEmulator"),
        )
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(
            success=False,
            summary=driver_not_loaded_summary("baseStation"),
        )

    refusal = mock_driver_refusal_summary("channelEmulator", ce)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    if "fs16" not in _driver_class(ce).lower():
        return SequenceRunResult(
            success=False,
            summary=(
                "fs16_hybrid_kpi_smoke requires a real FS16 playback "
                f"channelEmulator driver, but HAL loaded {_driver_class(ce)}."
            ),
            extra={"channelEmulator_driver": _driver_class(ce)},
        )

    params = params or {}
    remote_file = _str_param(params, "remote_playback_file", "Emulation0609.smu")
    if not remote_file:
        return SequenceRunResult(
            success=False,
            summary="remote_playback_file is required, for example Emulation0609.smu",
        )

    requested_bs_mode = _str_param(params, "base_station_mode", "mock").lower()
    if requested_bs_mode not in {"mock", "real"}:
        return SequenceRunResult(
            success=False,
            summary="base_station_mode must be 'mock' or 'real'",
            extra={"base_station_mode": requested_bs_mode},
        )

    actual_bs_mode = _driver_mode(bs)
    if requested_bs_mode == "mock" and actual_bs_mode != "mock":
        return SequenceRunResult(
            success=False,
            summary=(
                "base_station_mode=mock but HAL loaded a real baseStation "
                f"driver ({_driver_class(bs)}). Set baseStation driver_mode "
                "to mock or switch base_station_mode=real intentionally."
            ),
            extra={"base_station_mode": requested_bs_mode, "base_station_driver": _driver_class(bs)},
        )
    if requested_bs_mode == "real" and actual_bs_mode == "mock":
        return SequenceRunResult(
            success=False,
            summary=(
                "base_station_mode=real but HAL loaded a mock baseStation "
                f"driver ({_driver_class(bs)}). Set baseStation driver_mode "
                "to real and reload HAL before running this branch."
            ),
            extra={"base_station_mode": requested_bs_mode, "base_station_driver": _driver_class(bs)},
        )

    verify_remote = _bool_param(params, "verify_remote_file_exists", True)
    start_playback = _bool_param(params, "start_playback", True)
    cleanup_on_finish = _bool_param(params, "cleanup_on_finish", True)
    stop_after_s = max(0.0, _float_param(params, "stop_after_s", 5.0))
    attach_timeout_s = max(0.0, _float_param(params, "attach_timeout_s", 15.0))
    attach_poll_interval_s = max(
        0.01,
        _float_param(params, "attach_poll_interval_s", 1.0),
    )
    throughput_windows = max(1, min(100, _int_param(params, "throughput_windows", 3)))
    throughput_window_s = max(
        0.01,
        min(60.0, _float_param(params, "throughput_window_s", 0.2)),
    )

    cell_config = {
        "frequency_mhz": _float_param(params, "frequency_mhz", 3500.0),
        "bandwidth_mhz": _float_param(params, "bandwidth_mhz", 100.0),
        "scs_khz": _int_param(params, "scs_khz", 30),
        "band": _str_param(params, "band", "n78"),
        "mimo_layers": _int_param(params, "mimo_layers", 2),
        "dl_power_dbm": _float_param(params, "dl_power_dbm", -50.0),
    }

    original_verify_exists = hasattr(ce, "verify_remote_file_exists")
    original_verify = getattr(ce, "verify_remote_file_exists", None)
    original_auto_exists = hasattr(ce, "auto_start_after_load")
    original_auto = getattr(ce, "auto_start_after_load", None)
    if original_verify_exists:
        setattr(ce, "verify_remote_file_exists", verify_remote)
    if original_auto_exists:
        setattr(ce, "auto_start_after_load", False)

    steps: List[SequenceStepResult] = []
    cleanup_warnings: List[str] = []
    playback_started = False
    bs_signaling_attempted = False
    extra: Dict[str, Any] = {
        "instrument_modes": {
            "channelEmulator": "real",
            "channelEmulator_driver": _driver_class(ce),
            "baseStation": actual_bs_mode,
            "baseStation_driver": _driver_class(bs),
            "DUT": "mock" if requested_bs_mode == "mock" else "real_or_external",
            "kpi_source": (
                "mock baseStation / mock DUT"
                if requested_bs_mode == "mock"
                else "baseStation driver KPI surface"
            ),
        },
        "fs16_playback": {
            "remote_playback_file": remote_file,
            "remote_playback_path": _remote_playback_path(ce, remote_file),
            "verify_remote_file_exists": verify_remote,
            "start_playback": start_playback,
            "stop_after_s": stop_after_s,
            "cleanup_on_finish": cleanup_on_finish,
        },
        "virtual_base_station_config": cell_config,
        "samples": [],
        "kpi_summary": {},
        "ue_info": None,
        "ue_capability": None,
        "cleanup_warnings": cleanup_warnings,
    }

    try:
        await _step(
            steps,
            log,
            "connect channelEmulator (FS16)",
            ce.connect(),
            false_detail=lambda: _driver_last_error(ce),
        )
        if verify_remote:
            verify_info = await _step(
                steps,
                log,
                f"FS16 verify playback file {remote_file}",
                _verify_remote_playback_file(ce, remote_file),
                require_truthy=False,
                require_not_none=True,
            )
            playback_extra = extra.get("fs16_playback")
            if isinstance(playback_extra, dict) and isinstance(verify_info, dict):
                playback_extra.update(verify_info)
            if (
                isinstance(verify_info, dict)
                and verify_info.get("checked") is True
                and original_verify_exists
            ):
                setattr(ce, "verify_remote_file_exists", False)
        await _step(
            steps,
            log,
            f"FS16 load playback {remote_file}",
            ce.load_channel(
                mode=ChannelLoadMode.EXTERNAL_WAVEFORM,
                model_name="fs16_hybrid_kpi_smoke",
                scenario="operator-staged",
                parameters={"remote_playback_file": remote_file},
                waveform_dir=None,
            ),
            false_detail=lambda: _driver_last_error(ce),
        )
        if start_playback:
            await _step(
                steps,
                log,
                "FS16 start playback",
                ce.start_emulation(),
                false_detail=lambda: _driver_last_error(ce),
            )
            playback_started = True

        await _step(
            steps,
            log,
            f"connect baseStation ({requested_bs_mode})",
            bs.connect(),
        )
        await _step(
            steps,
            log,
            (
                "BS set_cell_config "
                f"{cell_config['frequency_mhz']:g}MHz/"
                f"{cell_config['bandwidth_mhz']:g}MHz/"
                f"{cell_config['scs_khz']}kHz/"
                f"{cell_config['band']}/"
                f"{cell_config['mimo_layers']}L"
            ),
            bs.set_cell_config(cell_config),
        )
        if hasattr(bs, "set_downlink_power"):
            await _step(
                steps,
                log,
                f"BS set_downlink_power {cell_config['dl_power_dbm']:g} dBm",
                bs.set_downlink_power(cell_config["dl_power_dbm"]),
            )

        bs_signaling_attempted = True
        await _step(
            steps,
            log,
            f"BS start_signaling timeout={attach_timeout_s:g}s",
            bs.start_signaling(timeout_s=attach_timeout_s),
        )

        attached, ue_info = await _wait_for_attach(
            bs,
            timeout_s=attach_timeout_s,
            poll_interval_s=attach_poll_interval_s,
            steps=steps,
            log=log,
        )
        extra["ue_info"] = ue_info
        if not attached:
            return SequenceRunResult(
                success=False,
                summary="DUT did not attach within timeout",
                steps=steps,
                extra=extra,
            )

        if hasattr(bs, "query_ue_capability"):
            extra["ue_capability"] = await _step(
                steps,
                log,
                "query_ue_capability",
                bs.query_ue_capability(),
                require_truthy=False,
            )

        samples: List[Dict[str, Any]] = []
        for idx in range(throughput_windows):
            metrics = await _step(
                steps,
                log,
                f"KPI window {idx + 1}/{throughput_windows}",
                bs.measure_throughput_window(throughput_window_s),
                require_truthy=False,
                require_not_none=True,
            )
            sample = _metrics_to_dict(metrics)
            sample["window_index"] = idx
            samples.append(sample)

        kpi_summary = _numeric_summary(samples)
        extra["samples"] = samples
        extra["kpi_summary"] = kpi_summary

        dl = kpi_summary.get("dl_throughput_mbps", {}).get("mean")
        ul = kpi_summary.get("ul_throughput_mbps", {}).get("mean")
        parts = [f"FS16 hybrid KPI smoke passed: {remote_file}"]
        if dl is not None:
            parts.append(f"avg DL {dl:.2f} Mbps")
        if ul is not None:
            parts.append(f"avg UL {ul:.2f} Mbps")
        parts.append(f"BS={actual_bs_mode}")
        parts.append("DUT=mock" if requested_bs_mode == "mock" else "DUT=real/external")

        if playback_started and stop_after_s > 0:
            await _step(
                steps,
                log,
                f"wait {stop_after_s:g}s before FS16 stop",
                asyncio.sleep(stop_after_s),
                require_truthy=False,
            )

        if cleanup_on_finish or stop_after_s > 0:
            if bs_signaling_attempted and hasattr(bs, "stop_signaling"):
                await _step(
                    steps,
                    log,
                    "BS stop_signaling",
                    bs.stop_signaling(),
                )
                bs_signaling_attempted = False
            if playback_started:
                await _step(
                    steps,
                    log,
                    "FS16 stop playback",
                    ce.stop_emulation(),
                    false_detail=lambda: _driver_last_error(ce),
                )
                playback_started = False

        return SequenceRunResult(
            success=True,
            summary="; ".join(parts),
            steps=steps,
            extra=extra,
        )
    except Exception as exc:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"FS16 hybrid KPI smoke failed: {type(exc).__name__}: {exc}",
            steps=steps,
            extra=extra,
        )
    finally:
        if cleanup_on_finish or stop_after_s > 0:
            warnings, stopped_bs, stopped_ce = await _cleanup(
                bs,
                ce,
                stop_bs=bs_signaling_attempted,
                stop_ce=playback_started,
                steps=steps,
                log=log,
            )
            cleanup_warnings.extend(warnings)
            if stopped_bs:
                bs_signaling_attempted = False
            if stopped_ce:
                playback_started = False
        playback_state = extra.get("fs16_playback")
        if isinstance(playback_state, dict):
            playback_state["playback_left_running"] = bool(playback_started)
            playback_state["bs_signaling_left_running"] = bool(bs_signaling_attempted)
        _restore_attr(
            ce,
            "verify_remote_file_exists",
            original_verify,
            original_verify_exists,
        )
        _restore_attr(ce, "auto_start_after_load", original_auto, original_auto_exists)
