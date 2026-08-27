"""P1-56: controller ACK is not proof that the turntable moved."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.hal.aerotech_positioner import (
    AerotechError,
    AerotechOperatorStopRequested,
    AerotechOutcomeUnknown,
    AerotechTaskFault,
    RealAerotechDriver,
)
from app.hal.ets_positioner import RealEtsEmcenterDriver
from app.services import instrument_test_lease as lease_module
from app.services.instrument_test_lease import InstrumentTestLease
from app.services.mimo_ota.cleanup import cleanup_chamber_instruments


REPO_ROOT = Path(__file__).resolve().parents[2]


class ScriptedMotionDriver(RealAerotechDriver):
    def __init__(self, responses: dict[str, list[Any]], *, tolerance: float = 0.5):
        super().__init__(
            "p1-56-positioner",
            {
                "ip": "192.0.2.10",
                "position_tolerance_deg": tolerance,
                "poll_interval_s": 0.0,
                "settle_timeout_s": 0.1,
                "motion_truth_units_verified": True,
                "motion_truth_user_units": "degree",
                "motion_truth_min_deg": 0.0,
                "motion_truth_max_deg": 360.0,
                "motion_truth_xf_speed": 5.0,
            },
        )
        self._axes_present = ["X"]
        self._responses = defaultdict(list, responses)
        self.sent: list[str] = []

    async def _send(
        self,
        command: str,
        *,
        expected_operator_stop_generation: int | None = None,
    ) -> str:
        if (
            expected_operator_stop_generation is not None
            and self.operator_stop_generation()
            != expected_operator_stop_generation
        ):
            raise AerotechOperatorStopRequested("operator stop requested")
        self.sent.append(command)
        queue = self._responses[command]
        if queue:
            value = queue.pop(0)
            if isinstance(value, BaseException):
                raise value
            return str(value)
        if command.startswith(
            ("ENABLE ", "MOVEABS ", "HOME ", "ABORT ", "WAIT INPOS ")
        ):
            return ""
        if command == "VFBK(X)":
            return "0"
        if command == "VFBK(Y)":
            return "0"
        raise AssertionError(f"unexpected command without response: {command}")


def _driver(*positions: Any, tolerance: float = 0.5) -> ScriptedMotionDriver:
    return ScriptedMotionDriver(
        {
            "PFBK(X)": list(positions),
        },
        tolerance=tolerance,
    )


@pytest.mark.asyncio
async def test_formal_aerotech_motion_requires_verified_degree_configuration_before_io():
    driver = _driver(0.0, 90.0)
    driver.config.pop("motion_truth_units_verified")

    assert await driver.move_to(90.0, 0.0) is False
    assert driver.sent == []


@pytest.mark.asyncio
async def test_formal_aerotech_move_uses_sourced_xf_and_wait_inpos_not_axisstatus():
    driver = _driver(0.0, 90.0)
    assert await driver.move_to(90.0, 0.0) is True
    assert "MOVEABS X 90.0000 XF5.0000" in driver.sent
    assert "WAIT INPOS X" in driver.sent
    assert not any(command.startswith("AXISSTATUS(") for command in driver.sent)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["move", "position", "stop", "reset"])
async def test_unverified_emcenter_positioner_operations_are_disabled_before_scpi_io(
    operation: str,
):
    driver = RealEtsEmcenterDriver("p1-56-ets", {"ip": "192.0.2.20"})
    writes: list[str] = []
    queries: list[str] = []
    driver._write = writes.append  # type: ignore[method-assign]
    driver._query = lambda command: queries.append(command) or "90"  # type: ignore[method-assign]

    if operation == "move":
        result = await driver.move_to(90.0, 0.0)
    elif operation == "position":
        with pytest.raises(RuntimeError, match="no checked-in vendor evidence"):
            await driver.get_position()
        result = False
    elif operation == "stop":
        result = await driver.stop()
    else:
        result = await driver.reset()

    assert result is False
    assert writes == []
    assert queries == []


@pytest.mark.asyncio
async def test_unverified_emcenter_metrics_never_publish_a_fake_zero_degree_position():
    driver = RealEtsEmcenterDriver("p1-56-ets", {"ip": "192.0.2.20"})

    metrics = await driver.get_metrics()

    assert metrics.metrics["azimuth"] is None
    assert metrics.metrics["position_verified"] is False
    assert metrics.metrics["position_unit"] == "unknown"


@pytest.mark.asyncio
async def test_operator_stop_is_rechecked_inside_the_motion_tx_lock():
    driver = RealAerotechDriver("p1-56-atomic-stop", {"ip": "192.0.2.10"})
    driver._writer = object()
    driver._reader = object()
    expected_generation = driver.operator_stop_generation()

    await driver._lock.acquire()
    send_task = asyncio.create_task(
        driver._send(
            "MOVEABS X 90.0000",
            expected_operator_stop_generation=expected_generation,
        )
    )
    await asyncio.sleep(0)
    driver.note_operator_stop()
    driver._lock.release()

    with pytest.raises(AerotechOperatorStopRequested):
        await send_task


@pytest.mark.asyncio
async def test_operator_stop_during_silent_reconnect_blocks_motion_retry():
    driver = RealAerotechDriver("p1-56-reconnect-stop", {"ip": "192.0.2.10"})
    driver._reader = object()
    driver._writer = SimpleNamespace(is_closing=lambda: True)
    driver._axes_present = ["X"]
    transmitted: list[str] = []
    expected_generation = driver.operator_stop_generation()

    async def reconnect() -> bool:
        driver.note_operator_stop()
        driver._writer = SimpleNamespace(is_closing=lambda: False)
        return True

    async def transmit(command: str) -> str:
        transmitted.append(command)
        return ""

    driver._silent_reconnect = reconnect  # type: ignore[method-assign]
    driver._tx_rx = transmit  # type: ignore[method-assign]

    with pytest.raises(AerotechOperatorStopRequested):
        await driver._send(
            "MOVEABS X 90.0000 XF5.0000",
            expected_operator_stop_generation=expected_generation,
        )
    assert transmitted == []


@pytest.mark.asyncio
async def test_transport_loss_never_replays_a_non_idempotent_motion_command():
    driver = RealAerotechDriver("transport-test", {"ip": "192.0.2.10"})
    driver._axes_present = ["X"]
    driver._reader = object()  # type: ignore[assignment]
    driver._writer = SimpleNamespace(is_closing=lambda: False)  # type: ignore[assignment]
    transmitted: list[str] = []

    async def transmit(command: str) -> str:
        transmitted.append(command)
        raise ConnectionResetError("ambiguous write outcome")

    async def reconnect() -> bool:
        return True

    driver._tx_rx = transmit  # type: ignore[method-assign]
    driver._silent_reconnect = reconnect  # type: ignore[method-assign]

    with pytest.raises(AerotechOutcomeUnknown, match="not replayed"):
        await driver._send("MOVEABS X 90.0000 XF5.0000")
    assert transmitted == ["MOVEABS X 90.0000 XF5.0000"]


@pytest.mark.asyncio
async def test_transport_loss_may_retry_a_read_only_feedback_query_once():
    driver = RealAerotechDriver("transport-test", {"ip": "192.0.2.10"})
    driver._axes_present = ["X"]
    driver._reader = object()  # type: ignore[assignment]
    driver._writer = SimpleNamespace(is_closing=lambda: False)  # type: ignore[assignment]
    attempts = 0

    async def transmit(_command: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionResetError("idle close")
        return "90"

    async def reconnect() -> bool:
        return True

    driver._tx_rx = transmit  # type: ignore[method-assign]
    driver._silent_reconnect = reconnect  # type: ignore[method-assign]

    assert await driver._send("PFBK(X)") == "90"
    assert attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        AerotechTaskFault("task fault"),
        AerotechError("Connection lost during PFBK and reconnect failed"),
    ],
)
async def test_axis_probe_does_not_misclassify_task_or_transport_fault_as_absent(
    failure: AerotechError,
):
    driver = RealAerotechDriver("probe-fault", {"ip": "192.0.2.10"})

    async def fail_probe(_command: str) -> str:
        raise failure

    driver._send = fail_probe  # type: ignore[method-assign]

    with pytest.raises(type(failure), match=str(failure)):
        await driver._probe_axis("Y")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["move", "home"])
async def test_operator_stop_after_wait_cannot_publish_motion_success(
    operation: str,
):
    positions = (0.0, 90.0) if operation == "move" else (90.0, 0.0)
    driver = _driver(*positions)

    async def wait_then_stop(*, expected_operator_stop_generation=None):
        assert expected_operator_stop_generation == 0
        driver.note_operator_stop()

    driver._wait_for_settle = wait_then_stop  # type: ignore[method-assign]

    if operation == "move":
        result = await driver.move_to(90.0, 0.0)
    else:
        result = await driver.reset()

    assert result is False
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_controller_task_fault_is_never_treated_as_a_success_reply():
    class Writer:
        def write(self, _payload: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

    driver = RealAerotechDriver("transport-test", {"ip": "192.0.2.10"})
    driver._axes_present = ["X"]
    reader = asyncio.StreamReader()
    reader.feed_data(b"#42\n")
    driver._reader = reader
    driver._writer = Writer()  # type: ignore[assignment]

    with pytest.raises(AerotechTaskFault, match="task fault"):
        await driver._tx_rx("PFBK(X)")


def test_every_live_multistep_positioner_consumer_retains_stop_generation():
    """Removing any production wiring reopens the operator-stop restart bug."""
    paths = (
        "api-service/app/services/mimo_ota/executors/measure.py",
        "api-service/app/services/probe_calibration_service.py",
    )
    for relative_path in paths:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "operator_stop_generation" in source, relative_path
        assert "expected_operator_stop_generation" in source, relative_path

    for relative_path in (
        "api-service/app/services/quiet_zone_validation_service.py",
        "api-service/app/services/channel_calibration_service.py",
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "positioner.move_to(" not in source, relative_path

    cleanup = (
        REPO_ROOT / "api-service/app/services/mimo_ota/cleanup.py"
    ).read_text(encoding="utf-8")
    assert "expected_operator_stop_generation" in cleanup


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "forbidden_prefix"),
    [("move", "MOVEABS "), ("home", "HOME ")],
)
async def test_formal_motion_does_not_restart_after_stop_during_preflight(
    operation: str,
    forbidden_prefix: str,
):
    driver = _driver(0.0, 90.0)
    original_feedback = driver._read_motion_feedback
    first_feedback = True

    async def stop_after_preflight_feedback(
        *, expected_operator_stop_generation=None,
    ):
        nonlocal first_feedback
        feedback = await original_feedback(
            expected_operator_stop_generation=expected_operator_stop_generation
        )
        if first_feedback:
            first_feedback = False
            driver.note_operator_stop()
        return feedback

    driver._read_motion_feedback = stop_after_preflight_feedback  # type: ignore[method-assign]

    if operation == "move":
        result = await driver.move_to(90.0, 0.0)
    else:
        result = await driver.reset()

    assert result is False
    assert not any(command.startswith(forbidden_prefix) for command in driver.sent)


@pytest.mark.asyncio
async def test_formal_case_inherits_stop_generation_from_launch_before_precheck(
    monkeypatch,
):
    """A stop during PRECHECK/REFERENCE must still cancel later MEASURE motion."""
    from contextlib import asynccontextmanager

    import app.hal.positioner as positioner_module
    import app.services.test_case_runner as runner
    from app.services.mimo_ota.executors.measure import MeasureExecutor

    assert hasattr(
        positioner_module,
        "current_positioner_operation_stop_generation",
    ), "formal-case lifecycle has no retained operator-stop baseline"
    assert (
        "current_positioner_operation_stop_generation"
        in __import__("inspect").getsource(MeasureExecutor.execute)
    ), "MEASURE does not consume the formal-case lifecycle baseline"
    launch_source = __import__("inspect").getsource(
        runner.launch_test_case_execution
    )
    assert launch_source.index(
        "retain_positioner_stop_generation"
    ) < launch_source.index("create_task("), (
        "formal-case baseline must be retained before the background task is created"
    )

    generation = 7
    observed: list[int | None] = []

    class Positioner:
        def operator_stop_generation(self) -> int:
            return generation

    class DB:
        class Query:
            def __init__(self, execution):
                self.execution = execution

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self.execution

        def query(self, *_args, **_kwargs):
            return self.Query(SimpleNamespace(
                config={runner.FREEZE_CONFIG_KEY: {"digest": "test-freeze"}},
            ))

        def close(self) -> None:
            return None

    @asynccontextmanager
    async def lease(_purpose: str, **_kwargs):
        yield SimpleNamespace(measurement_attempt_id=None)

    async def run_case_loop(_db, _execution_id, *, defer_report=False) -> None:
        assert defer_report is True
        observed.append(
            positioner_module.current_positioner_operation_stop_generation.get()
        )

    monkeypatch.setattr(runner, "SessionLocal", DB)
    monkeypatch.setattr(runner, "instrument_test_lease", lease)
    monkeypatch.setattr(runner, "_run_case_loop", run_case_loop)
    monkeypatch.setattr(
        runner,
        "get_hal_service",
        lambda: SimpleNamespace(drivers={"positioner": Positioner()}),
        raising=False,
    )

    token = positioner_module.current_positioner_operation_stop_generation.set(7)
    try:
        # Models an operator stop after the HTTP request accepted the run and
        # created its task, but before that task receives scheduler time.
        generation = 8
        await runner._run_case("00000000-0000-0000-0000-000000000156")
    finally:
        positioner_module.current_positioner_operation_stop_generation.reset(token)

    assert observed == [7]
    assert positioner_module.current_positioner_operation_stop_generation.get() is None


def test_commissioning_entrypoints_retain_stop_generation_before_lease():
    """All live commissioning owners establish the baseline before waiting."""
    import inspect

    from app.api import commissioning

    for owner in (
        commissioning.run_phase,
        commissioning.run_adhoc_phase,
        commissioning.run_all_phases,
    ):
        source = inspect.getsource(owner)
        assert source.index(
            "retain_positioner_stop_generation"
        ) < source.index("instrument_test_lease("), owner.__name__


@pytest.mark.asyncio
async def test_move_fails_when_controller_settles_but_encoder_does_not_move():
    driver = _driver(0.0, 0.0)

    assert await driver.move_to(90.0, 0.0) is False
    assert driver.last_error is not None
    assert "motion_not_observed" in driver.last_error
    # ABORT 后的最终 PFBK 未取得，动作前缓存不再是当前位置证据。
    assert driver._current_azimuth is None


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
    assert driver._current_azimuth is None


@pytest.mark.asyncio
async def test_move_rejects_final_feedback_outside_tolerance():
    driver = _driver(0.0, 88.0)

    assert await driver.move_to(90.0, 0.0) is False
    assert driver.last_error is not None
    assert "target_not_reached" in driver.last_error
    assert driver._current_azimuth is None
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_home_fails_when_encoder_stays_away_from_zero():
    driver = _driver(30.0, 30.0)

    assert await driver.reset() is False
    assert driver._current_azimuth is None
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_home_aborts_and_preserves_cancellation():
    driver = _driver(30.0, 30.0)

    async def cancelled(**_kwargs) -> None:
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

    async def timeout(**_kwargs) -> None:
        raise asyncio.TimeoutError

    driver._wait_for_settle = timeout  # type: ignore[method-assign]

    assert await driver.move_to(90.0, 0.0) is False
    assert "MOVEABS X 90.0000 XF5.0000" in driver.sent
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_stop_does_not_report_success_while_velocity_is_nonzero():
    driver = _driver(12.0)
    driver.settle_timeout_s = 0.001
    driver.poll_interval_s = 0.0
    original_send = driver._send

    async def moving_send(
        command: str,
        *,
        expected_operator_stop_generation: int | None = None,
    ) -> str:
        if command == "VFBK(X)":
            driver.sent.append(command)
            return "1"
        return await original_send(
            command,
            expected_operator_stop_generation=expected_operator_stop_generation,
        )

    driver._send = moving_send  # type: ignore[method-assign]

    assert await driver.stop() is False
    assert "ABORT X" in driver.sent
    assert "VFBK(X)" in driver.sent


@pytest.mark.asyncio
async def test_stop_succeeds_after_velocity_reaches_exact_zero():
    driver = ScriptedMotionDriver(
        {
            "VFBK(X)": ["1", "0"],
        }
    )

    assert await driver.stop() is True
    assert driver.sent.count("VFBK(X)") == 2


@pytest.mark.asyncio
async def test_move_refuses_new_command_when_previous_motion_is_active():
    driver = ScriptedMotionDriver(
        {
            "VFBK(X)": ["1"],
            "PFBK(X)": [0.0, 90.0],
        }
    )

    assert await driver.move_to(90.0, 0.0) is False
    assert not any(command.startswith("MOVEABS ") for command in driver.sent)


@pytest.mark.asyncio
async def test_home_refuses_new_command_when_previous_motion_is_active():
    driver = ScriptedMotionDriver(
        {
            "VFBK(X)": ["1"],
            "PFBK(X)": [30.0, 0.0],
        }
    )

    assert await driver.reset() is False
    assert not any(command.startswith("HOME ") for command in driver.sent)


@pytest.mark.asyncio
async def test_stop_requires_zero_velocity_on_every_actual_axis():
    driver = ScriptedMotionDriver(
        {
            "VFBK(X)": ["0"] * 1000,
            "VFBK(Y)": ["1"] * 1000,
        }
    )
    driver._axes_present = ["X", "Y"]
    driver.settle_timeout_s = 0.001
    driver.poll_interval_s = 0.0

    assert await driver.stop() is False
    assert "VFBK(X)" in driver.sent
    assert "VFBK(Y)" in driver.sent


@pytest.mark.asyncio
async def test_move_aborts_and_preserves_cancellation():
    driver = _driver(0.0)

    async def cancelled(**_kwargs) -> None:
        raise asyncio.CancelledError

    driver._wait_for_settle = cancelled  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await driver.move_to(90.0, 0.0)
    assert "MOVEABS X 90.0000 XF5.0000" in driver.sent
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_move_aborts_when_cancelled_while_waiting_for_command_response():
    driver = ScriptedMotionDriver(
        {
            "PFBK(X)": [0.0, 0.0],
            "MOVEABS X 90.0000 XF5.0000": [asyncio.CancelledError()],
        }
    )

    with pytest.raises(asyncio.CancelledError):
        await driver.move_to(90.0, 0.0)
    assert "MOVEABS X 90.0000 XF5.0000" in driver.sent
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
    driver._current_elevation = 0.0

    with pytest.raises(ValueError, match="finite numeric"):
        await driver.get_position()

    metrics = await driver.get_metrics()
    assert metrics.metrics["azimuth"] is None
    assert metrics.metrics["elevation"] is None
    assert metrics.metrics["position_verified"] is False


@pytest.mark.asyncio
async def test_mimo_cleanup_surfaces_positioner_home_false_as_warning():
    class Positioner:
        def __init__(self) -> None:
            self.disconnected = False

        async def move_to(self, azimuth: float, elevation: float) -> bool:
            return False

        async def stop(self) -> bool:
            return True

        async def disconnect(self) -> bool:
            self.disconnected = True
            return True

    positioner = Positioner()
    hal = type("Hal", (), {"drivers": {"positioner": positioner}})()

    warnings = await cleanup_chamber_instruments(hal, "execution-p1-56")

    assert len(warnings) == 1
    assert "positioner.move_to(home) 被拒" in warnings[0]
    assert positioner.disconnected is True


@pytest.mark.asyncio
async def test_mimo_cleanup_retains_control_session_when_stop_is_unconfirmed():
    class Positioner:
        def __init__(self) -> None:
            self.disconnected = False

        async def move_to(self, azimuth: float, elevation: float) -> bool:
            return False

        async def stop(self) -> bool:
            return False

        async def disconnect(self) -> bool:
            self.disconnected = True
            return True

    positioner = Positioner()
    hal = type("Hal", (), {"drivers": {"positioner": positioner}})()

    warnings = await cleanup_chamber_instruments(hal, "execution-p1-56")

    assert any("停止未确认" in warning for warning in warnings)
    assert positioner.disconnected is False


@pytest.mark.asyncio
async def test_abort_with_unknown_final_feedback_clears_verified_position_cache():
    driver = _driver()
    driver._current_azimuth = 42.0
    driver._current_elevation = 0.0

    async def stopped() -> bool:
        return True

    async def feedback_failed():
        raise ConnectionError("PFBK unavailable")

    driver.stop = stopped  # type: ignore[method-assign]
    driver._read_motion_feedback = feedback_failed  # type: ignore[method-assign]

    await driver._abort_unverified_motion(reason="test")
    metrics = await driver.get_metrics()

    assert metrics.metrics["azimuth"] is None
    assert metrics.metrics["elevation"] is None
    assert metrics.metrics["position_verified"] is False
