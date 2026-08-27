"""P1-56 destructive Aerotech motion-truth diagnostic contract."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.diagnostics import loader
from app.diagnostics.sequences import aerotech_positioner_motion_truth as sequence
from app.hal.aerotech_positioner import (
    AerotechOperatorStopRequested,
    RealAerotechDriver,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class MotionDiagnosticDriver(RealAerotechDriver):
    def __init__(
        self,
        *,
        moves_without_xf: bool,
        moves_with_xf: bool,
        velocity: str = "0",
        velocity_responses: list[str] | None = None,
        abort_positions: list[float] | None = None,
        abort_raises: bool = False,
    ) -> None:
        super().__init__(
            "motion-diagnostic",
            {
                "ip": "192.0.2.10",
                "motion_truth_units_verified": True,
                "motion_truth_user_units": "degree",
                "motion_truth_min_deg": 0.0,
                "motion_truth_max_deg": 360.0,
                "motion_truth_xf_speed": 5.0,
                "motion_truth_coordinate_offset_verified": True,
                "motion_truth_coordinate_offset_deg": 0.0,
            },
        )
        self._axes_present = ["X"]
        self._writer = object()
        self.position = 10.0
        self.moves_without_xf = moves_without_xf
        self.moves_with_xf = moves_with_xf
        self.velocity = velocity
        self.velocity_responses = list(velocity_responses or [])
        self.abort_positions = list(abort_positions or [])
        self.abort_raises = abort_raises
        self.commands: list[str] = []
        self.command_stop_generations: list[tuple[str, int | None]] = []

    async def _send(
        self,
        command: str,
        *,
        expected_operator_stop_generation: int | None = None,
    ) -> str:
        self.command_stop_generations.append(
            (command, expected_operator_stop_generation)
        )
        if (
            expected_operator_stop_generation is not None
            and self.operator_stop_generation()
            != expected_operator_stop_generation
        ):
            raise AerotechOperatorStopRequested("operator stop requested")
        self.commands.append(command)
        if command == "PFBK(X)":
            return str(self.position)
        if command == "VFBK(X)":
            if self.velocity_responses:
                return self.velocity_responses.pop(0)
            return self.velocity
        if command.startswith("MOVEABS X"):
            has_xf = any(token.startswith("XF") for token in command.split())
            if (has_xf and self.moves_with_xf) or (
                not has_xf and self.moves_without_xf
            ):
                command_target = float(command.split()[2])
                self.position = command_target + float(
                    self.config["motion_truth_coordinate_offset_deg"]
                )
            return ""
        if command == "ENABLE X":
            return ""
        if command == "ABORT X":
            if self.abort_positions:
                self.position = self.abort_positions.pop(0)
            if self.abort_raises:
                raise RuntimeError("ABORT rejected")
            return ""
        raise AssertionError(f"unexpected command: {command}")


def _hal(driver: Any) -> Any:
    return SimpleNamespace(drivers={"positioner": driver})


@pytest.fixture
def fast_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(sequence.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(sequence.asyncio, "sleep", clock.sleep)
    return clock


def test_sequence_is_registered_as_unsafe_positioner_diagnostic():
    loader.reset_cache()
    entries = {entry["key"]: entry for entry in loader.list_sequences()}

    entry = entries["aerotech_positioner_motion_truth"]
    assert entry["required_categories"] == ["positioner"]
    assert entry["safe_during_test"] is False


@pytest.mark.asyncio
async def test_invalid_parameters_fail_before_any_controller_command(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"step_deg": 31.0},
        log=lambda _message: None,
    )

    assert result.success is False
    assert "step_deg" in result.summary
    assert driver.commands == []


@pytest.mark.asyncio
async def test_authoritative_mock_gate_refuses_before_motion(monkeypatch, fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)
    monkeypatch.setattr(sequence, "is_mock_driver", lambda candidate: candidate is driver)

    result = await sequence.run(
        SimpleNamespace(), _hal(driver), {}, log=lambda _message: None
    )

    assert result.success is False
    assert "mock" in result.summary.lower()
    assert driver.commands == []


@pytest.mark.asyncio
async def test_disconnected_driver_is_refused_before_motion(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)
    driver._writer = None

    result = await sequence.run(
        SimpleNamespace(), _hal(driver), {}, log=lambda _message: None
    )

    assert result.success is False
    assert "未连接" in result.summary
    assert driver.commands == []


@pytest.mark.asyncio
async def test_unknown_user_units_fail_before_enable_or_wrapped_motion(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)
    driver.position = 10000.0
    driver.config.pop("motion_truth_units_verified")

    result = await sequence.run(
        SimpleNamespace(), _hal(driver), {}, log=lambda _message: None
    )

    assert result.success is False
    assert "motion_truth_units_verified" in result.summary
    assert not any(
        command.startswith(("ENABLE ", "MOVEABS ")) for command in driver.commands
    )


@pytest.mark.asyncio
async def test_caller_cannot_override_the_site_approved_motion_feed(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"xf_speed": 6.0},
        log=lambda _message: None,
    )

    assert result.success is False
    assert "motion_truth_xf_speed" in result.summary
    assert not any(
        command.startswith(("ENABLE ", "MOVEABS ")) for command in driver.commands
    )


@pytest.mark.asyncio
async def test_unknown_coordinate_offset_fails_before_enable_or_motion(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)
    driver.config.pop("motion_truth_coordinate_offset_verified")
    driver.config.pop("motion_truth_coordinate_offset_deg")

    result = await sequence.run(
        SimpleNamespace(), _hal(driver), {}, log=lambda _message: None
    )

    assert result.success is False
    assert "motion_truth_coordinate_offset" in result.summary
    assert not any(
        command.startswith(("ENABLE ", "MOVEABS ")) for command in driver.commands
    )


@pytest.mark.asyncio
async def test_sequence_uses_only_sourced_xf_motion_and_records_raw_samples(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {
            "step_deg": 10.0,
            "xf_speed": 5.0,
            "sample_duration_s": 0.4,
            "sample_interval_s": 0.2,
            "tolerance_deg": 0.5,
        },
        log=lambda _message: None,
    )

    assert result.success is True
    assert driver._current_azimuth == pytest.approx(10.0)
    assert driver._current_elevation == pytest.approx(0.0)
    assert (await driver.get_metrics()).metrics["position_verified"] is True
    assert driver.commands.count("ENABLE X") == 1
    moves = [command for command in driver.commands if command.startswith("MOVEABS")]
    assert moves == [
        "MOVEABS X 20.0000 XF5.0000",
        "MOVEABS X 10.0000 XF5.0000",
    ]
    move_generations = [
        generation
        for command, generation in driver.command_stop_generations
        if command.startswith("MOVEABS")
    ]
    assert move_generations == [0, 0]
    assert not any(command.startswith("DISABLE") for command in driver.commands)
    assert len(result.extra["segments"]) == 2
    for step, segment in zip(result.steps, result.extra["segments"], strict=True):
        assert step.raw is not None
        assert json.loads(step.raw)["samples"] == segment["samples"]
        assert len(segment["samples"]) >= 3
        assert all("vfbk_raw" in sample for sample in segment["samples"])
        assert all("pfbk_raw" in sample for sample in segment["samples"])
        assert segment["command_accepted"] is True
        assert segment["feedback_changed"] is True
        assert segment["target_reached"] is True


@pytest.mark.asyncio
async def test_sequence_maps_verified_program_to_feedback_coordinate(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)
    driver.config["motion_truth_coordinate_offset_deg"] = 90.0
    driver.position = 190.0

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {
            "step_deg": 10.0,
            "sample_duration_s": 0.2,
            "sample_interval_s": 0.2,
        },
        log=lambda _message: None,
    )

    assert result.success is True
    moves = [command for command in driver.commands if command.startswith("MOVEABS")]
    assert moves == [
        "MOVEABS X 110.0000 XF5.0000",
        "MOVEABS X 100.0000 XF5.0000",
    ]
    assert result.extra["coordinate_offset_deg"] == pytest.approx(90.0)
    assert result.extra["segments"][0]["target"] == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_no_encoder_motion_fails_and_forbids_return_segment(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=False, moves_with_xf=False)

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.4, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    assert result.success is False
    assert "小步动作未获完整证明" in result.summary
    assert [segment["feedback_changed"] for segment in result.extra["segments"]] == [False]
    moves = [command for command in driver.commands if command.startswith("MOVEABS")]
    assert moves == ["MOVEABS X 20.0000 XF5.0000"]
    assert all(step.raw for step in result.steps)
    assert driver.commands.count("ABORT X") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("velocity", ["nan", "inf", "not-a-number"])
async def test_invalid_velocity_cannot_be_washed_into_success_by_final_position(
    fast_clock,
    velocity: str,
):
    driver = MotionDiagnosticDriver(
        moves_without_xf=True,
        moves_with_xf=True,
        velocity=velocity,
        velocity_responses=["0"],
    )

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.2, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    assert result.success is False
    assert all(step.success is False for step in result.steps)
    assert len(result.extra["segments"]) == 1
    segment = result.extra["segments"][0]
    assert segment["samples_valid"] is False
    assert segment["abort_attempted"] is True
    assert segment["abort_succeeded"] is False
    assert driver.commands.count("ABORT X") == 1


@pytest.mark.asyncio
async def test_nonzero_velocity_cannot_finish_diagnostic(fast_clock):
    driver = MotionDiagnosticDriver(
        moves_without_xf=True,
        moves_with_xf=True,
        velocity="1",
        velocity_responses=["0"],
    )

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.2, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    assert result.success is False
    assert len(result.extra["segments"]) == 1
    assert result.extra["segments"][0]["settled"] is False
    assert result.extra["segments"][0]["abort_succeeded"] is False
    assert driver.commands.count("ABORT X") == 1
    assert len(
        [command for command in driver.commands if command.startswith("MOVEABS ")]
    ) == 1


@pytest.mark.asyncio
async def test_abort_failure_stops_before_second_motion_command(fast_clock):
    driver = MotionDiagnosticDriver(
        moves_without_xf=False,
        moves_with_xf=False,
        abort_raises=True,
    )

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.2, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    assert result.success is False
    assert len(result.extra["segments"]) == 1
    assert result.extra["segments"][0]["abort_succeeded"] is False
    moves = [command for command in driver.commands if command.startswith("MOVEABS")]
    assert len(moves) == 1
    assert " XF" in moves[0]


@pytest.mark.asyncio
async def test_operator_emergency_stop_during_first_segment_forbids_second_move(
    fast_clock,
):
    driver = MotionDiagnosticDriver(moves_without_xf=True, moves_with_xf=True)
    original_send = driver._send

    async def stop_after_first_move(
        command: str,
        *,
        expected_operator_stop_generation: int | None = None,
    ) -> str:
        response = await original_send(
            command,
            expected_operator_stop_generation=expected_operator_stop_generation,
        )
        if command.startswith("MOVEABS X"):
            driver.note_operator_stop()
        return response

    driver._send = stop_after_first_move  # type: ignore[method-assign]

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.2, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    moves = [command for command in driver.commands if command.startswith("MOVEABS")]
    assert result.success is False
    assert "急停" in result.summary
    assert moves == ["MOVEABS X 20.0000 XF5.0000"]


@pytest.mark.asyncio
async def test_abort_refresh_is_retained_as_final_encoder_truth(fast_clock):
    driver = MotionDiagnosticDriver(
        moves_without_xf=False,
        moves_with_xf=False,
        abort_positions=[12.0],
    )

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.2, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    first = result.extra["segments"][0]
    assert first["abort_succeeded"] is True
    assert first["post_abort_position"] == pytest.approx(12.0)
    assert driver._current_azimuth == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_abort_refresh_still_runs_when_stop_raises(fast_clock):
    driver = MotionDiagnosticDriver(
        moves_without_xf=False,
        moves_with_xf=False,
    )

    async def failing_stop() -> bool:
        raise RuntimeError("stop failed")

    driver.stop = failing_stop  # type: ignore[method-assign]
    driver.position = 7.0

    segment = await sequence._sample_segment(
        driver,
        axis="X",
        label="test",
        command="MOVEABS X 20.0000",
        start_position=10.0,
        target=20.0,
        duration_s=0.2,
        interval_s=0.2,
        tolerance=0.5,
    )

    assert segment["abort_succeeded"] is False
    assert segment["post_abort_position"] == pytest.approx(7.0)
    # 这是未证明零速时的瞬时读数，可保留为诊断证据，
    # 但不能发布成稳定的当前位置。
    assert driver._current_azimuth is None
    assert (await driver.get_metrics()).metrics["position_verified"] is False


@pytest.mark.asyncio
async def test_abort_refresh_failure_invalidates_cached_position(fast_clock):
    driver = MotionDiagnosticDriver(
        moves_without_xf=False,
        moves_with_xf=False,
    )
    driver._current_azimuth = 33.0
    driver._current_elevation = 0.0

    async def failing_get_position():
        raise ConnectionError("PFBK unavailable")

    driver.get_position = failing_get_position  # type: ignore[method-assign]

    stopped, error, position = await sequence._abort_and_refresh(driver)
    metrics = await driver.get_metrics()

    assert stopped is True
    assert "PFBK" in (error or "")
    assert position is None
    assert metrics.metrics["azimuth"] is None
    assert metrics.metrics["position_verified"] is False


@pytest.mark.asyncio
async def test_unconfirmed_second_segment_abort_does_not_republish_instant_pfbk(
    fast_clock,
):
    driver = MotionDiagnosticDriver(
        moves_without_xf=False,
        moves_with_xf=True,
        abort_raises=True,
    )
    original_send = driver._send
    move_count = 0

    async def fail_return_move(
        command: str,
        *,
        expected_operator_stop_generation: int | None = None,
    ) -> str:
        nonlocal move_count
        if command.startswith("MOVEABS X"):
            move_count += 1
            if move_count == 2:
                driver.moves_with_xf = False
        return await original_send(
            command,
            expected_operator_stop_generation=expected_operator_stop_generation,
        )

    driver._send = fail_return_move  # type: ignore[method-assign]

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.2, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )
    metrics = await driver.get_metrics()

    assert result.success is False
    assert result.extra["segments"][1]["abort_succeeded"] is False
    assert result.extra["segments"][1]["post_abort_position"] is not None
    assert metrics.metrics["azimuth"] is None
    assert metrics.metrics["position_verified"] is False


@pytest.mark.asyncio
async def test_cancelled_diagnostic_aborts_before_releasing_motion(
    monkeypatch: pytest.MonkeyPatch,
):
    driver = MotionDiagnosticDriver(moves_without_xf=False, moves_with_xf=False)

    async def cancel_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(sequence.asyncio, "sleep", cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await sequence.run(
            SimpleNamespace(),
            _hal(driver),
            {"sample_duration_s": 0.4, "sample_interval_s": 0.2},
            log=lambda _message: None,
        )

    assert "MOVEABS X 20.0000 XF5.0000" in driver.commands
    assert "ABORT X" in driver.commands


@pytest.mark.asyncio
async def test_cancelled_move_command_response_still_aborts_diagnostic():
    driver = MotionDiagnosticDriver(moves_without_xf=False, moves_with_xf=False)
    original_send = driver._send

    async def cancelling_send(
        command: str,
        *,
        expected_operator_stop_generation: int | None = None,
    ) -> str:
        if command.startswith("MOVEABS X"):
            driver.commands.append(command)
            raise asyncio.CancelledError
        return await original_send(
            command,
            expected_operator_stop_generation=expected_operator_stop_generation,
        )

    driver._send = cancelling_send  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await sequence.run(
            SimpleNamespace(), _hal(driver), {}, log=lambda _message: None
        )

    assert any(command.startswith("MOVEABS X") for command in driver.commands)
    assert "ABORT X" in driver.commands


@pytest.mark.asyncio
async def test_out_of_range_start_is_rejected_before_enable():
    driver = MotionDiagnosticDriver(moves_without_xf=False, moves_with_xf=False)
    driver.config["motion_truth_min_deg"] = 0.0
    driver.config["motion_truth_max_deg"] = 30.0
    driver.position = 45.0

    result = await sequence.run(
        SimpleNamespace(), _hal(driver), {}, log=lambda _message: None
    )

    assert result.success is False
    assert not any(command.startswith("ENABLE ") for command in driver.commands)
    assert not any(command.startswith("MOVEABS ") for command in driver.commands)
