from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.hal.base_station import BaseStationCleanupResult
from app.services.mimo_ota.cleanup import cleanup_chamber_instruments


class _BaseStation:
    def __init__(self, *, stop=True, idle=True):
        self.stop = stop
        self.idle = idle
        self.calls: list[str] = []

    async def stop_signaling(self):
        self.calls.append("stop")
        return self.stop

    async def ensure_safe_idle(self):
        self.calls.append("safe-idle")
        return self.idle

    async def disconnect(self):
        self.calls.append("disconnect")
        raise AssertionError("MEASURE cleanup must leave transport release to the lease")


@pytest.mark.asyncio
async def test_measure_cleanup_returns_exact_base_station_truth_without_disconnect():
    driver = _BaseStation()
    result = await cleanup_chamber_instruments(
        SimpleNamespace(drivers={"baseStation": driver}), "execution-1"
    )

    assert isinstance(result.base_station, BaseStationCleanupResult)
    assert result.base_station.stop_signaling_confirmed is True
    assert result.base_station.safe_idle_confirmed is True
    assert result.warnings == []
    assert driver.calls == ["stop", "safe-idle"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("stop", "idle"), [(False, True), (None, True), (True, False)])
async def test_false_none_or_failed_safe_idle_is_visible_and_never_confirmed(stop, idle):
    driver = _BaseStation(stop=stop, idle=idle)
    result = await cleanup_chamber_instruments(
        SimpleNamespace(drivers={"baseStation": driver}), "execution-1"
    )

    assert result.base_station == BaseStationCleanupResult(
        stop_signaling_confirmed=stop is True,
        safe_idle_confirmed=idle is True,
        warnings=tuple(result.warnings),
    )
    assert result.warnings
    assert "disconnect" not in driver.calls


@pytest.mark.asyncio
async def test_cleanup_exception_preserves_both_failed_confirmations():
    class Broken(_BaseStation):
        async def stop_signaling(self):
            self.calls.append("stop")
            raise RuntimeError("stop rejected")

        async def ensure_safe_idle(self):
            self.calls.append("safe-idle")
            raise RuntimeError("state unavailable")

    driver = Broken()
    result = await cleanup_chamber_instruments(
        SimpleNamespace(drivers={"baseStation": driver}), "execution-1"
    )

    assert result.base_station.stop_signaling_confirmed is False
    assert result.base_station.safe_idle_confirmed is False
    assert "stop rejected" in " ".join(result.warnings)
    assert "state unavailable" in " ".join(result.warnings)
