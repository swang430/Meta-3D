"""FS16 playback smoke test.

Workshop-tier entry point for the real-FS16 / mock-surrounding-instruments
bring-up path.  It deliberately does not use the older conducted passthrough
sequence: the only real hardware action here is to load an already-staged
playback file on the FS16 and optionally start playback.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List

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
    name="FS16 playback smoke",
    description=(
        "Loads an operator-staged SMU playback file on the real PROPSIM FS16 "
        "and optionally starts playback. Use this for conducted bring-up when "
        "BS/SA are still mock and CE must not be passthrough."
    ),
    required_categories=["channelEmulator"],
    params_schema=[
        {
            "name": "remote_playback_file",
            "label": "FS16 内 SMU playback 文件",
            "type": "string",
            "default": "Emulation0609.smu",
        },
        {
            "name": "verify_remote_file_exists",
            "label": "加载前校验 FS16 文件存在",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "start_playback",
            "label": "加载成功后启动 playback",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "stop_after_s",
            "label": "运行多少秒后停止（0=不自动停止）",
            "type": "number",
            "default": 0,
        },
        {
            "name": "cleanup_on_finish",
            "label": "结束时停止 playback",
            "type": "boolean",
            "default": False,
        },
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


async def _step(
    steps: List[SequenceStepResult],
    log: Callable[[str], None],
    label: str,
    action: Any,
    *,
    require_truthy: bool = True,
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
        steps.append(
            SequenceStepResult(
                label=label,
                success=True,
                detail=_compact_detail(result),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        log(f"  ✓ {label}")
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
        log(f"  ✗ {label}: {detail}")
        raise


def _bool_param(params: Dict[str, Any], key: str, default: bool) -> bool:
    value = params.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _float_param(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default) or 0)
    except (TypeError, ValueError):
        return default


def _restore_attr(obj: Any, name: str, value: Any, existed: bool) -> None:
    if existed:
        setattr(obj, name, value)
    elif hasattr(obj, name):
        try:
            delattr(obj, name)
        except AttributeError:
            pass


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

    refusal = mock_driver_refusal_summary("channelEmulator", ce)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)

    params = params or {}
    remote_file = str(params.get("remote_playback_file") or "").strip()
    if not remote_file:
        return SequenceRunResult(
            success=False,
            summary="remote_playback_file is required, for example Emulation0609.smu",
        )

    verify_remote = _bool_param(params, "verify_remote_file_exists", True)
    start_playback = _bool_param(params, "start_playback", True)
    cleanup_on_finish = _bool_param(params, "cleanup_on_finish", False)
    stop_after_s = max(0.0, _float_param(params, "stop_after_s", 0.0))

    original_verify_exists = hasattr(ce, "verify_remote_file_exists")
    original_verify = getattr(ce, "verify_remote_file_exists", None)
    original_auto_exists = hasattr(ce, "auto_start_after_load")
    original_auto = getattr(ce, "auto_start_after_load", None)
    if original_verify_exists:
        setattr(ce, "verify_remote_file_exists", verify_remote)
    if original_auto_exists:
        # Keep load/start as separate visible steps and avoid double-starting
        # when connection_params already has auto_start_after_load=true.
        setattr(ce, "auto_start_after_load", False)

    steps: List[SequenceStepResult] = []
    playback_started = False
    try:
        if hasattr(ce, "connect"):
            await _step(
                steps,
                log,
                "connect channelEmulator",
                ce.connect(),
                false_detail=lambda: _driver_last_error(ce),
            )

        await _step(
            steps,
            log,
            f"FS16 load playback {remote_file}",
            ce.load_channel(
                mode=ChannelLoadMode.EXTERNAL_WAVEFORM,
                model_name="fs16_playback_smoke",
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

        if stop_after_s > 0:
            await _step(
                steps,
                log,
                f"wait {stop_after_s:g}s",
                asyncio.sleep(stop_after_s),
                require_truthy=False,
            )

        if playback_started and (cleanup_on_finish or stop_after_s > 0):
            await _step(
                steps,
                log,
                "FS16 stop playback",
                ce.stop_emulation(),
            )
            playback_started = False

        state = "started and left running" if playback_started else "loaded"
        return SequenceRunResult(
            success=True,
            summary=f"FS16 playback smoke passed: {remote_file} {state}",
            steps=steps,
            extra={
                "remote_playback_file": remote_file,
                "verify_remote_file_exists": verify_remote,
                "start_playback": start_playback,
                "cleanup_on_finish": cleanup_on_finish,
                "stop_after_s": stop_after_s,
                "playback_left_running": playback_started,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"FS16 playback smoke failed: {type(exc).__name__}: {exc}",
            steps=steps,
            extra={"remote_playback_file": remote_file},
        )
    finally:
        _restore_attr(
            ce,
            "verify_remote_file_exists",
            original_verify,
            original_verify_exists,
        )
        _restore_attr(ce, "auto_start_after_load", original_auto, original_auto_exists)
