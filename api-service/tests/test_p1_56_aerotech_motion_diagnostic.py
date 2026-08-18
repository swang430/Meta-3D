"""P1-56 destructive Aerotech motion-truth diagnostic contract."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.diagnostics import loader
from app.diagnostics.sequences import aerotech_positioner_motion_truth as sequence
from app.hal.aerotech_positioner import AxisStatusBit, RealAerotechDriver


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
        axisstatus: str | None = None,
    ) -> None:
        super().__init__("motion-diagnostic", {"ip": "192.0.2.10"})
        self._axes_present = ["X"]
        self._writer = object()
        self.position = 10.0
        self.moves_without_xf = moves_without_xf
        self.moves_with_xf = moves_with_xf
        self.axisstatus = axisstatus or str(1 << AxisStatusBit.IN_POSITION)
        self.commands: list[str] = []

    async def _send(self, command: str) -> str:
        self.commands.append(command)
        if command == "PFBK(X)":
            return str(self.position)
        if command == "AXISSTATUS(X)":
            return self.axisstatus
        if command.startswith("MOVEABS X "):
            has_xf = " XF" in command
            if (has_xf and self.moves_with_xf) or (
                not has_xf and self.moves_without_xf
            ):
                self.position = float(command.split()[2])
            return ""
        if command == "ENABLE X":
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
async def test_sequence_keeps_enable_and_records_raw_no_xf_and_xf_samples(fast_clock):
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
    assert driver.commands.count("ENABLE X") == 1
    moves = [command for command in driver.commands if command.startswith("MOVEABS")]
    assert moves == ["MOVEABS X 20.0000", "MOVEABS X 10.0000 XF5.0000"]
    assert not any(command.startswith("DISABLE") for command in driver.commands)
    assert len(result.extra["segments"]) == 2
    for step, segment in zip(result.steps, result.extra["segments"], strict=True):
        assert step.raw is not None
        assert json.loads(step.raw)["samples"] == segment["samples"]
        assert len(segment["samples"]) >= 3
        assert all("axisstatus_raw" in sample for sample in segment["samples"])
        assert all("pfbk_raw" in sample for sample in segment["samples"])
        assert segment["command_accepted"] is True
        assert segment["feedback_changed"] is True
        assert segment["target_reached"] is True


@pytest.mark.asyncio
async def test_no_encoder_motion_fails_both_segments_but_keeps_raw_trace(fast_clock):
    driver = MotionDiagnosticDriver(moves_without_xf=False, moves_with_xf=False)

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.4, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    assert result.success is False
    assert "编码器反馈未证明动作" in result.summary
    assert [segment["feedback_changed"] for segment in result.extra["segments"]] == [
        False,
        False,
    ]
    moves = [command for command in driver.commands if command.startswith("MOVEABS")]
    assert " XF" not in moves[0]
    assert " XF" in moves[1]
    assert all(step.raw for step in result.steps)


@pytest.mark.asyncio
async def test_invalid_axis_status_cannot_be_washed_into_success_by_final_position(
    fast_clock,
):
    driver = MotionDiagnosticDriver(
        moves_without_xf=True,
        moves_with_xf=True,
        axisstatus="nan",
    )

    result = await sequence.run(
        SimpleNamespace(),
        _hal(driver),
        {"sample_duration_s": 0.2, "sample_interval_s": 0.2},
        log=lambda _message: None,
    )

    assert result.success is False
    assert all(step.success is False for step in result.steps)
