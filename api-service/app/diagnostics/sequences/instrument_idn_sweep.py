"""Ping every instrument bound to the LabProfile and report *IDN?.

Used as the first thing operators run when they walk into a rack: "are
all the boxes alive and still the model number I think they are?"
Doesn't move any RF state — safe to run at any time.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
)
from app.services.diagnostic_context import DiagnosticContext

logger = logging.getLogger(__name__)


metadata = SequenceMetadata(
    name="Instrument *IDN? sweep",
    description=(
        "Walks every category bound to the selected LabProfile and queries "
        "*IDN?. First-thing-in-the-morning sanity check — confirms each "
        "box is online and still the vendor/model the lab profile claims."
    ),
    required_categories=[],  # uses whatever the lab has bound; never required-fixed
    params_schema=[],  # parameter-less
    safe_during_test=True,  # *IDN? doesn't disturb anything
)


async def run(
    ctx: DiagnosticContext,
    hal: Any,  # InstrumentHALService — typed loosely so tests can pass mocks
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    """Iterate the lab's instrument bindings, query *IDN? on each."""
    if ctx.lab_profile_id is None:
        return SequenceRunResult(
            success=False,
            summary="No LabProfile selected — IDN sweep needs at least one bound instrument",
        )

    if not ctx.instrument_bindings:
        return SequenceRunResult(
            success=False,
            summary=f"LabProfile '{ctx.lab_profile_name}' has no instrument_bindings",
        )

    drivers = getattr(hal, "drivers", {}) or {}
    steps: list[SequenceStepResult] = []
    failures = 0

    for binding in ctx.instrument_bindings:
        cat_key = binding.category_key or "(unknown)"
        endpoint = binding.connection_endpoint or "(no endpoint)"
        label = f"{cat_key} @ {endpoint}"

        driver = drivers.get(binding.category_key) if binding.category_key else None
        if driver is None:
            steps.append(SequenceStepResult(
                label=label,
                success=False,
                detail=f"No HAL driver loaded for category '{cat_key}' — check HAL init logs",
            ))
            failures += 1
            log(f"  ✗ {label}: driver not loaded")
            continue

        # Try the standard ways HAL drivers expose IDN. Different vendors
        # called it different things in the codebase, so try a few.
        idn = None
        err: str | None = None
        started = time.monotonic()
        for method_name in ("get_identity", "query_idn", "query"):
            method = getattr(driver, method_name, None)
            if method is None:
                continue
            try:
                if method_name == "query":
                    idn = await method("*IDN?")
                else:
                    idn = await method()
                break
            except Exception as e:  # noqa: BLE001
                err = f"{method_name}() raised: {e}"
                continue

        duration_ms = int((time.monotonic() - started) * 1000)
        if idn is None:
            steps.append(SequenceStepResult(
                label=label,
                success=False,
                detail=err or "Driver exposes none of get_identity/query_idn/query",
                duration_ms=duration_ms,
            ))
            failures += 1
            log(f"  ✗ {label}: {err or 'no IDN method available'}")
        else:
            idn_str = str(idn).strip()
            steps.append(SequenceStepResult(
                label=label,
                success=True,
                detail=idn_str,
                duration_ms=duration_ms,
            ))
            log(f"  ✓ {label}: {idn_str}")

    summary = (
        f"All {len(steps)} bound instruments responded"
        if failures == 0
        else f"{failures}/{len(steps)} instruments did not respond"
    )
    return SequenceRunResult(
        success=failures == 0,
        summary=summary,
        steps=steps,
        extra={"total": len(steps), "failures": failures},
    )
