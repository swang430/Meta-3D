"""Conducted BS -> CE -> DUT smoke test.

Workshop-tier entry point for quickly validating a conducted RF chain:
base-station emulator feeds the channel emulator, the channel emulator runs
in passthrough mode, and the DUT is expected to attach through the cable path.

This sequence intentionally records only a diagnostic_run. It does not create
formal TestPlan/TestExecution rows or certification reports.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from pydantic import ValidationError

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
)
from app.services.conducted import ConductedSmokeConfig, run_conducted_smoke
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="Conducted BS-CE-DUT smoke",
    description=(
        "Runs a conducted BS -> channel-emulator -> DUT smoke test. The CE is "
        "put into passthrough, the BS starts one cell, the DUT must attach, "
        "and throughput is sampled over several stat windows. Mock drivers "
        "are allowed for CI/demo; absent drivers fail loudly."
    ),
    required_categories=["baseStation", "channelEmulator"],
    params_schema=[
        {"name": "frequency_mhz", "label": "频率 (MHz)", "type": "number", "default": 3500},
        {"name": "bandwidth_mhz", "label": "带宽 (MHz)", "type": "number", "default": 100},
        {"name": "scs_khz", "label": "SCS (kHz)", "type": "number", "default": 30},
        {"name": "band", "label": "Band", "type": "string", "default": "n78"},
        {"name": "mimo_layers", "label": "MIMO layers", "type": "number", "default": 2},
        {"name": "dl_power_dbm", "label": "DL power (dBm)", "type": "number", "default": -50},
        {"name": "ce_input_port", "label": "CE input port", "type": "string", "default": "A1"},
        {"name": "ce_output_port", "label": "CE output port", "type": "string", "default": "MAIN"},
        {"name": "attach_timeout_s", "label": "Attach 等待 (秒)", "type": "number", "default": 15},
        {"name": "throughput_windows", "label": "吞吐窗口数量", "type": "number", "default": 3},
        {"name": "throughput_window_s", "label": "单窗口时长 (秒)", "type": "number", "default": 0.2},
        {"name": "cleanup_on_finish", "label": "结束后清理 BS/CE 状态", "type": "boolean", "default": True},
    ],
    safe_during_test=False,
)


def _to_sequence_steps(steps) -> list[SequenceStepResult]:
    return [
        SequenceStepResult(
            label=s.label,
            success=s.success,
            detail=s.detail,
            duration_ms=s.duration_ms,
        )
        for s in steps
    ]


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(
            success=False,
            summary=driver_not_loaded_summary("baseStation"),
        )
    ce = drivers.get("channelEmulator")
    if ce is None:
        return SequenceRunResult(
            success=False,
            summary=driver_not_loaded_summary("channelEmulator"),
        )

    try:
        config = ConductedSmokeConfig.model_validate(params or {})
    except ValidationError as err:
        return SequenceRunResult(
            success=False,
            summary=f"Invalid conducted smoke parameters: {err}",
            extra={"validation_errors": err.errors()},
        )

    result = await run_conducted_smoke(
        base_station=bs,
        channel_emulator=ce,
        config=config,
        log=log,
    )
    return SequenceRunResult(
        success=result.success,
        summary=result.summary,
        steps=_to_sequence_steps(result.steps),
        extra=result.extra,
    )
