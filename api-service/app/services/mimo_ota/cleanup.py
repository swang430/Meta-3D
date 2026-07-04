"""Best-effort instrument cleanup for MIMO_OTA executors.

Used in finally-blocks so a half-finished measurement loop doesn't leave the
chamber in a hot state (UXM still signaling, F64 still emulating, turntable
parked at some random azimuth). Each step is wrapped in its own try/except
because cleanup must be idempotent and swallow secondary failures —
re-raising here would mask the original error that triggered cleanup.
"""
from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


async def cleanup_chamber_instruments(hal: Any, execution_id: Any) -> List[str]:
    """Stop signaling, home positioner, stop emulation, disconnect drivers.

    Returns the list of warnings encountered (so the caller can surface them
    in the result payload). Never raises.
    """
    warnings: List[str] = []

    base_station = hal.drivers.get("baseStation")
    if base_station is not None:
        # Phase 2g: SCells must be removed before stop_signaling so the next
        # test starts with a clean PCell. Wrapped before the generic
        # stop/disconnect tuple so its failure doesn't skip those.
        if hasattr(base_station, "remove_all_secondary_cells"):
            try:
                await base_station.remove_all_secondary_cells()
            except Exception as e:  # noqa: BLE001
                msg = f"baseStation.remove_all_secondary_cells failed during cleanup: {e}"
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)

        for action_name, coro in (
            ("stop_signaling", lambda: base_station.stop_signaling()),
            ("disconnect", lambda: base_station.disconnect()),
        ):
            try:
                await coro()
            except Exception as e:  # noqa: BLE001
                msg = f"baseStation.{action_name} failed during cleanup: {e}"
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)

    positioner = hal.drivers.get("positioner")
    if positioner is not None:
        # Best-effort home before disconnect — operator-friendly between runs.
        try:
            await positioner.move_to(0.0, 0.0)
        except Exception as e:  # noqa: BLE001
            msg = f"positioner.move_to(home) failed during cleanup: {e}"
            warnings.append(msg)
            logger.warning("[%s] %s", execution_id, msg)
        try:
            await positioner.disconnect()
        except Exception as e:  # noqa: BLE001
            msg = f"positioner.disconnect failed during cleanup: {e}"
            warnings.append(msg)
            logger.warning("[%s] %s", execution_id, msg)

    emulator = hal.drivers.get("channelEmulator")
    if emulator is not None and hasattr(emulator, "stop_emulation"):
        try:
            # #206 后 stop_emulation 的 False 带真实语义 (GOS 被拒, 仪器可能
            # 仍在发射) — 尽力而为语境不 abort, 但要进 warnings 可见
            if not await emulator.stop_emulation():
                msg = (
                    "channelEmulator.stop_emulation 被拒 (GOS SYST:ERR?, "
                    "仪器可能仍在发射) — cleanup 继续但需人工确认"
                )
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)
        except Exception as e:  # noqa: BLE001
            msg = f"channelEmulator.stop_emulation failed during cleanup: {e}"
            warnings.append(msg)
            logger.warning("[%s] %s", execution_id, msg)

    return warnings
