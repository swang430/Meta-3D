"""P1-56: controller ACK is not proof that the turntable moved."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from app.hal.aerotech_positioner import AxisStatusBit, RealAerotechDriver
from app.services.mimo_ota.cleanup import cleanup_chamber_instruments


class ScriptedMotionDriver(RealAerotechDriver):
    def __init__(self, responses: dict[str, list[Any]], *, tolerance: float = 0.5):
        super().__init__(
            "p1-56-positioner",
            {
                "ip": "192.0.2.10",
                "position_tolerance_deg": tolerance,
                "poll_interval_s": 0.0,
                "settle_timeout_s": 0.1,
            },
        )
        self._axes_present = ["X"]
        self._responses = defaultdict(list, responses)
        self.sent: list[str] = []

    async def _send(self, command: str) -> str:
        self.sent.append(command)
        queue = self._responses[command]
        if queue:
            value = queue.pop(0)
            if isinstance(value, BaseException):
                raise value
            return str(value)
        if command.startswith(("MOVEABS ", "HOME ")):
            return ""
        if command == "AXISSTATUS(X)":
            return str(1 << AxisStatusBit.IN_POSITION)
        raise AssertionError(f"unexpected command without response: {command}")


def _driver(*positions: Any, tolerance: float = 0.5) -> ScriptedMotionDriver:
    return ScriptedMotionDriver(
        {
            "PFBK(X)": list(positions),
            "AXISSTATUS(X)": [str(1 << AxisStatusBit.IN_POSITION)] * 4,
        },
        tolerance=tolerance,
    )


@pytest.mark.asyncio
async def test_move_fails_when_controller_settles_but_encoder_does_not_move():
    driver = _driver(0.0, 0.0)

    assert await driver.move_to(90.0, 0.0) is False
    assert driver.last_error is not None
    assert "motion_not_observed" in driver.last_error
    assert driver._current_azimuth == 0.0


@pytest.mark.asyncio
async def test_move_succeeds_only_after_finite_feedback_reaches_target():
    driver = _driver(0.0, 90.0)

    assert await driver.move_to(90.0, 0.0) is True
    assert driver._current_azimuth == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_move_already_at_target_does_not_require_artificial_motion():
    driver = _driver(90.1, 90.2)

    assert await driver.move_to(90.0, 0.0) is True


@pytest.mark.asyncio
async def test_move_uses_circular_azimuth_error_at_zero_boundary():
    driver = _driver(359.8, 0.1)

    assert await driver.move_to(0.0, 0.0) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_feedback", ["", "not-a-number", "nan", "inf", "-inf"])
async def test_move_rejects_invalid_feedback_instead_of_coercing_it_to_zero(
    bad_feedback: str,
):
    driver = _driver(bad_feedback)

    assert await driver.move_to(0.0, 0.0) is False
    assert driver._current_azimuth == 0.0


@pytest.mark.asyncio
async def test_move_rejects_final_feedback_outside_tolerance():
    driver = _driver(0.0, 88.0)

    assert await driver.move_to(90.0, 0.0) is False
    assert driver.last_error is not None
    assert "target_not_reached" in driver.last_error


@pytest.mark.asyncio
async def test_home_fails_when_encoder_stays_away_from_zero():
    driver = _driver(30.0, 30.0)

    assert await driver.reset() is False
    assert driver._current_azimuth == 0.0


@pytest.mark.asyncio
async def test_real_get_position_propagates_invalid_feedback_instead_of_stale_cache():
    driver = _driver("garbage")
    driver._current_azimuth = 42.0

    with pytest.raises(ValueError, match="finite numeric"):
        await driver.get_position()


@pytest.mark.asyncio
async def test_mimo_cleanup_surfaces_positioner_home_false_as_warning():
    class Positioner:
        async def move_to(self, azimuth: float, elevation: float) -> bool:
            return False

        async def disconnect(self) -> bool:
            return True

    hal = type("Hal", (), {"drivers": {"positioner": Positioner()}})()

    warnings = await cleanup_chamber_instruments(hal, "execution-p1-56")

    assert len(warnings) == 1
    assert "positioner.move_to(home) 被拒" in warnings[0]
