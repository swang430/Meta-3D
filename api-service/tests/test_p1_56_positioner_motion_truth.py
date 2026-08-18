"""P1-56: controller ACK is not proof that the turntable moved."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from types import SimpleNamespace
from typing import Any

import pytest

from app.hal.aerotech_positioner import AxisStatusBit, RealAerotechDriver
from app.services import instrument_test_lease as lease_module
from app.services.instrument_test_lease import InstrumentTestLease
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
        if command.startswith(("MOVEABS ", "HOME ", "ABORT ")):
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
    assert driver._current_azimuth == pytest.approx(88.0)
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_home_fails_when_encoder_stays_away_from_zero():
    driver = _driver(30.0, 30.0)

    assert await driver.reset() is False
    assert driver._current_azimuth == pytest.approx(30.0)
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_move_rejects_fractional_axis_status_instead_of_truncating_bitmask():
    driver = ScriptedMotionDriver(
        {
            "PFBK(X)": [0.0, 90.0, 90.0],
            "AXISSTATUS(X)": ["4.5"],
        }
    )

    assert await driver.move_to(90.0, 0.0) is False
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_home_aborts_and_preserves_cancellation():
    driver = _driver(30.0, 30.0)

    async def cancelled() -> None:
        raise asyncio.CancelledError

    driver._wait_for_settle = cancelled  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await driver.reset()
    assert "HOME X" in driver.sent
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_target", [True, float("nan"), float("inf"), float("-inf")])
async def test_move_rejects_non_finite_target_before_any_controller_io(bad_target):
    driver = _driver(0.0, 90.0)

    assert await driver.move_to(bad_target, 0.0) is False
    assert driver.sent == []


@pytest.mark.asyncio
async def test_move_aborts_after_settle_timeout():
    driver = _driver(0.0)

    async def timeout() -> None:
        raise asyncio.TimeoutError

    driver._wait_for_settle = timeout  # type: ignore[method-assign]

    assert await driver.move_to(90.0, 0.0) is False
    assert "MOVEABS X 90.0000" in driver.sent
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_move_aborts_and_preserves_cancellation():
    driver = _driver(0.0)

    async def cancelled() -> None:
        raise asyncio.CancelledError

    driver._wait_for_settle = cancelled  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await driver.move_to(90.0, 0.0)
    assert "MOVEABS X 90.0000" in driver.sent
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_move_aborts_when_cancelled_while_waiting_for_command_response():
    driver = ScriptedMotionDriver(
        {
            "PFBK(X)": [0.0, 0.0],
            "MOVEABS X 90.0000": [asyncio.CancelledError()],
        }
    )

    with pytest.raises(asyncio.CancelledError):
        await driver.move_to(90.0, 0.0)
    assert "MOVEABS X 90.0000" in driver.sent
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_move_waits_for_shared_operation_guard(monkeypatch: pytest.MonkeyPatch):
    lease = InstrumentTestLease(lambda: SimpleNamespace(drivers={}))
    monkeypatch.setattr(lease_module, "_LEASE", lease)
    driver = _driver(0.0, 90.0)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_diagnostic_guard() -> None:
        async with lease_module.instrument_test_lease(
            "diagnostic-sequence:aerotech-positioner-motion-truth",
            control_f64=False,
            control_uxm=False,
        ):
            entered.set()
            await release.wait()

    holder = asyncio.create_task(hold_diagnostic_guard())
    await entered.wait()
    mover = asyncio.create_task(driver.move_to(90.0, 0.0))
    await asyncio.sleep(0)

    assert mover.done() is False
    assert driver.sent == []

    release.set()
    await holder
    assert await mover is True


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
