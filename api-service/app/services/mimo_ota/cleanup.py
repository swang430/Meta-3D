"""Best-effort instrument cleanup for MIMO_OTA executors.

Used in finally-blocks so a half-finished measurement loop doesn't leave the
chamber in a hot state (UXM still signaling, F64 still emulating, turntable
parked at some random azimuth). Each step is wrapped in its own try/except
because cleanup must be idempotent and swallow secondary failures —
re-raising here would mask the original error that triggered cleanup.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, List

from app.hal.base_station import BaseStationCleanupResult, BaseStationDriver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChamberCleanupResult(Sequence[str]):
    """MEASURE cleanup truth plus the legacy warning-sequence projection."""

    warnings: list[str]
    base_station: BaseStationCleanupResult

    def __getitem__(self, index):
        return self.warnings[index]

    def __len__(self) -> int:
        return len(self.warnings)

    def __iter__(self) -> Iterator[str]:
        return iter(self.warnings)


async def cleanup_chamber_instruments(
    hal: Any,
    execution_id: Any,
    *,
    expected_operator_stop_generation: int | None = None,
) -> ChamberCleanupResult:
    """Stop signaling, confirm SAFE_IDLE, home positioner and stop emulation.

    Transport release is owned by ``instrument_test_lease`` and is deliberately
    absent here.  The result remains a warning sequence for legacy consumers.
    Never raises.
    """
    warnings: List[str] = []
    stop_signaling_confirmed = False
    safe_idle_confirmed = False

    base_station = hal.drivers.get("baseStation")
    if base_station is not None:
        # Phase 2g: SCells must be removed before stop_signaling so the next
        # test starts with a clean PCell. Wrapped before the generic
        # stop/disconnect tuple so its failure doesn't skip those.
        remove_scells = getattr(base_station, "remove_all_secondary_cells", None)
        class_remove_scells = getattr(
            type(base_station), "remove_all_secondary_cells", None
        )
        if (
            callable(remove_scells)
            and (
                "remove_all_secondary_cells" in vars(base_station)
                or class_remove_scells
                is not BaseStationDriver.remove_all_secondary_cells
            )
        ):
            try:
                scells_removed = await remove_scells()
                if scells_removed is not True:
                    msg = (
                        "baseStation.remove_all_secondary_cells was not "
                        "confirmed during cleanup; residual SCells may remain"
                    )
                    warnings.append(msg)
                    logger.warning("[%s] %s", execution_id, msg)
            except Exception as e:  # noqa: BLE001
                msg = f"baseStation.remove_all_secondary_cells failed during cleanup: {e}"
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)

        for action_name, coro in (
            ("stop_signaling", lambda: base_station.stop_signaling()),
            ("ensure_safe_idle", lambda: base_station.ensure_safe_idle()),
        ):
            try:
                confirmed = await coro()
                if action_name == "stop_signaling":
                    stop_signaling_confirmed = confirmed is True
                else:
                    safe_idle_confirmed = confirmed is True
                if confirmed is not True:
                    msg = (
                        f"baseStation.{action_name} was not confirmed during cleanup"
                    )
                    warnings.append(msg)
                    logger.warning("[%s] %s", execution_id, msg)
            except Exception as e:  # noqa: BLE001
                msg = f"baseStation.{action_name} failed during cleanup: {e}"
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)

    positioner = hal.drivers.get("positioner")
    if positioner is not None:
        # Best-effort home before disconnect — operator-friendly between runs.
        safe_to_disconnect = False
        try:
            move_kwargs = (
                {
                    "expected_operator_stop_generation":
                        expected_operator_stop_generation
                }
                if expected_operator_stop_generation is not None
                else {}
            )
            home_confirmed = await positioner.move_to(0.0, 0.0, **move_kwargs)
            if home_confirmed:
                safe_to_disconnect = True
            else:
                msg = (
                    "positioner.move_to(home) 被拒；编码器未证明回零，"
                    "cleanup 改为确认急停后再决定是否断开"
                )
                warnings.append(msg)
                logger.warning("[%s] %s", execution_id, msg)
        except Exception as e:  # noqa: BLE001
            msg = f"positioner.move_to(home) failed during cleanup: {e}"
            warnings.append(msg)
            logger.warning("[%s] %s", execution_id, msg)
        if not safe_to_disconnect:
            try:
                safe_to_disconnect = await positioner.stop()
            except Exception as e:  # noqa: BLE001
                msg = f"positioner.stop failed during cleanup: {e}"
                warnings.append(msg)
                logger.error("[%s] %s", execution_id, msg)
            if not safe_to_disconnect:
                msg = (
                    "positioner 停止未确认；为保留 ABORT/VFBK 控制通道，"
                    "cleanup 不断开转台会话，需人工核对"
                )
                warnings.append(msg)
                logger.error("[%s] %s", execution_id, msg)

        if safe_to_disconnect:
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

    return ChamberCleanupResult(
        warnings=warnings,
        base_station=BaseStationCleanupResult(
            stop_signaling_confirmed=stop_signaling_confirmed,
            safe_idle_confirmed=safe_idle_confirmed,
            warnings=tuple(warnings),
        ),
    )
