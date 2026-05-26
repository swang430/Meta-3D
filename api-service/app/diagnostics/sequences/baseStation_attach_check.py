"""Quick base-station attach + UE info probe.

Sets a minimal cell config on the bound baseStation, kicks signaling, waits
for a DUT to attach, and reports UE capability + RRC info if it does.

Use this when commissioning or path-loss looks fine but throughput is zero
— it isolates "is the DUT actually camping on our cell?" from the rest of
the chain.

Does mutate state (start_signaling), so `safe_during_test=False`.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    driver_not_loaded_summary,
    SequenceStepResult,
)
from app.services.diagnostic_context import DiagnosticContext


metadata = SequenceMetadata(
    name="Base station attach probe",
    description=(
        "Configures one cell, starts signaling, waits up to N seconds for "
        "DUT attach, queries UE capability + RRC info. Strictly a debug "
        "probe — leaves the BS in a signaling state, run the cleanup "
        "sequence or stop the BS yourself when done."
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "frequency_mhz", "label": "频率 (MHz)", "type": "number", "default": 3500},
        {"name": "bandwidth_mhz", "label": "带宽 (MHz)", "type": "number", "default": 100},
        {"name": "scs_khz", "label": "SCS (kHz)", "type": "number", "default": 30},
        {"name": "band", "label": "Band", "type": "string", "default": "n78"},
        {"name": "attach_timeout_s", "label": "Attach 等待 (秒)", "type": "number", "default": 15},
    ],
    safe_during_test=False,
)


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

    freq_mhz = float(params.get("frequency_mhz", 3500))
    bw_mhz = float(params.get("bandwidth_mhz", 100))
    scs_khz = int(params.get("scs_khz", 30))
    band = str(params.get("band", "n78"))
    timeout_s = float(params.get("attach_timeout_s", 15))

    steps: list[SequenceStepResult] = []

    async def _step(label: str, coro):
        started = time.monotonic()
        try:
            result = await coro
            steps.append(SequenceStepResult(
                label=label,
                success=True,
                detail=str(result) if result is not None else "ok",
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            log(f"  ✓ {label}")
            return result
        except Exception as e:  # noqa: BLE001
            steps.append(SequenceStepResult(
                label=label,
                success=False,
                detail=f"{type(e).__name__}: {e}",
                duration_ms=int((time.monotonic() - started) * 1000),
            ))
            log(f"  ✗ {label}: {e}")
            raise

    try:
        await _step("connect", bs.connect())
        await _step(
            f"set_cell_config {freq_mhz}MHz / {bw_mhz}MHz / {scs_khz}kHz / {band}",
            bs.set_cell_config({
                "frequency_mhz": freq_mhz,
                "bandwidth_mhz": bw_mhz,
                "scs_khz": scs_khz,
                "band": band,
                "mimo_layers": 2,
                "dl_power_dbm": -50,
            }),
        )
        await _step("start_signaling", bs.start_signaling())

        # Wait for attach
        log(f"  · waiting up to {timeout_s:.0f}s for DUT attach...")
        attached = False
        ue_info: Dict[str, Any] | None = None
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if hasattr(bs, "get_ue_info"):
                try:
                    info = await bs.get_ue_info()
                    if info and info.get("connected"):
                        attached = True
                        ue_info = info
                        break
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.sleep(1.0)

        if not attached:
            steps.append(SequenceStepResult(
                label=f"DUT attach (timeout {timeout_s:.0f}s)",
                success=False,
                detail="No UE attached within timeout — DUT off, wrong band, or RF path broken",
            ))
            return SequenceRunResult(
                success=False,
                summary="DUT did not attach within timeout",
                steps=steps,
                extra={"attached": False},
            )

        steps.append(SequenceStepResult(
            label="DUT attach",
            success=True,
            detail=f"connected: {ue_info}",
        ))
        log(f"  ✓ DUT attached: {ue_info}")

        # Capability + RRC if the driver exposes them
        cap = None
        if hasattr(bs, "query_ue_capability"):
            cap = await _step("query_ue_capability", bs.query_ue_capability())

        return SequenceRunResult(
            success=True,
            summary="DUT attached and reported capability",
            steps=steps,
            extra={"ue_info": ue_info, "ue_capability": cap},
        )
    except Exception as e:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"Sequence aborted: {e}",
            steps=steps,
        )
