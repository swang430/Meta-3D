"""P2-59 ③：execution-frozen 的 channelEmulator 单一会话。"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from app.hal.channel_emulator import MockChannelEmulator
from app.hal.channel_emulator_execution_plan import (
    resolve_channel_emulator_execution_plan,
)
from app.hal.base_station_compatibility import canonical_payload_digest
from app.models.test_plan import TestExecution
from app.services.channel_emulator_binding import ResolvedChannelEmulatorBinding


BINDING_DIGEST = "b" * 64


class _FlushOnlyDb:
    def __init__(self) -> None:
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1


def _resolved_binding(*, execution_mode: str = "simulated") -> ResolvedChannelEmulatorBinding:
    return ResolvedChannelEmulatorBinding(
        schema_version=1,
        status="configured",
        execution_mode=execution_mode,
        category_id="ce-category",
        instrument_model_id="ce-model",
        instrument_connection_id="ce-connection",
        lab_profile_id="lab-1",
        manifest=MockChannelEmulator.adapter_manifest,
        expected_driver_module="app.hal.propsim_f64",
        expected_driver_name="RealPropsimF64Driver",
        expected_transport={"host": "192.0.2.59", "port": 3334, "resource": None},
        binding_digest=BINDING_DIGEST,
        runtime_driver={
            "driver_module": "app.hal.channel_emulator",
            "driver_name": "MockChannelEmulator",
            "adapter_id": "mock_channel_emulator",
            "simulated": execution_mode == "simulated",
            "transport": None,
        },
    )


def test_binding_freeze_persists_execution_mode_under_its_outer_digest(monkeypatch):
    from app.services import channel_emulator_binding as module

    resolved = _resolved_binding()
    monkeypatch.setattr(
        module,
        "resolve_channel_emulator_binding",
        lambda *_args, **_kwargs: resolved,
    )
    db = _FlushOnlyDb()
    execution = TestExecution(config={})

    frozen = module.freeze_channel_emulator_binding(
        db,
        SimpleNamespace(),
        execution,
        SimpleNamespace(),
    )

    assert frozen["execution_mode"] == "simulated"
    assert "execution_mode" in module.CE_FREEZE_IDENTITY_KEYS
    identity = {key: value for key, value in frozen.items() if key != "digest"}
    assert frozen["digest"] == canonical_payload_digest(identity)
    tampered = {**frozen, "execution_mode": "real"}
    try:
        module._validate_existing_channel_emulator_freeze(tampered)
    except ValueError as exc:
        assert "digest" in str(exc) or "malformed" in str(exc)
    else:  # pragma: no cover - regression message
        raise AssertionError("execution_mode tampering must invalidate the freeze")


class _RealCe:
    adapter_manifest = MockChannelEmulator.adapter_manifest.model_copy(
        update={"adapter_id": "real_ce"}
    )

    def __init__(self) -> None:
        self.instrument_id = "ce-runtime"
        self.events: list[str] = []
        self._connection_host = "192.0.2.59"
        self._connection_port = 3334
        self._connection_resource = None

    async def acquire_remote_control(self) -> bool:
        self.events.append("acquire")
        return True

    async def stop_emulation(self) -> bool:
        self.events.append("safe-idle")
        return True

    async def release_to_local_control(self) -> bool:
        self.events.append("release")
        return True


def _frozen_binding_for_driver(driver, *, execution_mode: str) -> dict:
    identity = {
        "schema_version": 1,
        "category_id": "ce-category",
        "instrument_model_id": "ce-model",
        "instrument_connection_id": "ce-connection",
        "lab_profile_id": "lab-1",
        "execution_mode": execution_mode,
        "expected_driver_module": type(driver).__module__,
        "expected_driver_name": type(driver).__name__,
        "expected_driver_connection": (
            None
            if execution_mode == "simulated"
            else {"host": "192.0.2.59", "port": 3334, "resource": None}
        ),
        "binding_digest": BINDING_DIGEST,
        "resolved_binding": {
            "schema_version": 1,
            "status": "configured",
            "category_id": "ce-category",
            "instrument_model_id": "ce-model",
            "instrument_connection_id": "ce-connection",
            "lab_profile_id": "lab-1",
            "manifest": driver.adapter_manifest.model_dump(mode="json"),
            "expected_driver_module": type(driver).__module__,
            "expected_driver_name": type(driver).__name__,
            "expected_transport": {
                "host": "192.0.2.59",
                "port": 3334,
                "resource": None,
            },
            "binding_digest": BINDING_DIGEST,
        },
    }
    return {**identity, "digest": canonical_payload_digest(identity)}


def _frozen_plan(driver, *, source: str = "hal") -> dict:
    plan = resolve_channel_emulator_execution_plan(
        manifest=driver.adapter_manifest,
        driver_source=source,
        requested_load_mode="native_model",
        binding_digest=BINDING_DIGEST,
    )
    return {**plan.as_payload(), "digest": plan.digest}


def _scope_execution(plan: dict, *, frozen_mimo: dict | None = None):
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.base_station_adapter_profile import (
        FREEZE_CONFIG_KEY,
        MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    )
    from app.services.channel_emulator_execution_plan import (
        CHANNEL_ASSET_RESOLUTION_FREEZE_KEY,
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
    )

    frozen_mimo = frozen_mimo or MIMOOTAConfiguration.model_validate(
        {"engine_mode": "keysight_gcm", "emulation_file": "scenario.smu"}
    ).model_dump(mode="json")
    base_payload = {MIMO_OTA_CONFIGURATION_FREEZE_KEY: frozen_mimo}
    return SimpleNamespace(
        id="execution-1",
        config={
            FREEZE_CONFIG_KEY: {
                **base_payload,
                "digest": canonical_payload_digest(base_payload),
            },
            CE_PLAN_FREEZE_CONFIG_KEY: plan,
            CE_LOAD_REQUEST_FREEZE_CONFIG_KEY: _load_request_for_evidence(
                frozen_mimo, plan
            ),
        },
    )


def test_real_binding_validator_matches_exact_live_class_and_connection():
    from app.services import channel_emulator_binding as module

    driver = _RealCe()
    frozen = _frozen_binding_for_driver(driver, execution_mode="real")

    assert module.validate_frozen_channel_emulator_before_remote(
        SimpleNamespace(drivers={"channelEmulator": driver}),
        frozen,
    ) is None


def test_real_binding_validator_rejects_identity_drift_before_remote():
    from app.services import channel_emulator_binding as module

    driver = _RealCe()
    frozen = _frozen_binding_for_driver(driver, execution_mode="real")

    class Replacement(_RealCe):
        pass

    replacement = Replacement()
    assert "registry class" in module.validate_frozen_channel_emulator_before_remote(
        SimpleNamespace(drivers={"channelEmulator": replacement}), frozen
    )

    driver._connection_port = 9999
    assert "connection" in module.validate_frozen_channel_emulator_before_remote(
        SimpleNamespace(drivers={"channelEmulator": driver}), frozen
    )

    assert "missing" in module.validate_frozen_channel_emulator_before_remote(
        SimpleNamespace(drivers={}), frozen
    )


def test_simulated_binding_validator_only_accepts_authoritative_ce_mock():
    from app.hal.rf_switch import MockRfSwitch
    from app.services import channel_emulator_binding as module

    mock = MockChannelEmulator("ce", {})
    frozen = _frozen_binding_for_driver(mock, execution_mode="simulated")
    hal = SimpleNamespace(drivers={"channelEmulator": mock})
    assert module.validate_frozen_channel_emulator_before_remote(hal, frozen) is None

    assert "mock" in module.validate_frozen_channel_emulator_before_remote(
        SimpleNamespace(drivers={"channelEmulator": _RealCe()}), frozen
    )
    assert "channelEmulator" in module.validate_frozen_channel_emulator_before_remote(
        SimpleNamespace(drivers={"channelEmulator": MockRfSwitch("switch", {})}),
        frozen,
    )


class _LeaseCe:
    instrument_id = "ce-instrument"

    def __init__(self, events: list[str], *, release_ok: bool = True) -> None:
        self.events = events
        self.release_ok = release_ok

    async def acquire_remote_control(self) -> bool:
        self.events.append("acquire")
        return True

    async def release_to_local_control(self) -> bool:
        self.events.append("release")
        return self.release_ok


@pytest.mark.asyncio
async def test_lease_outcome_records_actual_channel_emulator_acquire_and_release():
    from app.services.instrument_test_lease import InstrumentTestLease

    events: list[str] = []
    lease = InstrumentTestLease(
        lambda: SimpleNamespace(
            drivers={"channelEmulator": _LeaseCe(events)},
            clear_metrics_cache=None,
        )
    )

    async with lease.hold("ce-session", control_uxm=False) as outcome:
        assert outcome.channel_emulator_remote_acquired_confirmed is True
        assert outcome.channel_emulator_transport_released_confirmed is None
        assert outcome.channel_emulator_instrument_id == "ce-instrument"

    assert events == ["acquire", "release"]
    assert outcome.channel_emulator_transport_released_confirmed is True


@pytest.mark.asyncio
async def test_lease_outcome_keeps_simulated_channel_emulator_control_not_applicable():
    from app.services.instrument_test_lease import InstrumentTestLease

    mock = MockChannelEmulator("ce", {})
    lease = InstrumentTestLease(
        lambda: SimpleNamespace(
            drivers={"channelEmulator": mock},
            clear_metrics_cache=None,
        )
    )

    async with lease.hold("ce-simulated", control_uxm=False) as outcome:
        assert outcome.channel_emulator_remote_acquired_confirmed is None
        assert outcome.channel_emulator_instrument_id is None

    assert outcome.channel_emulator_transport_released_confirmed is None


@pytest.mark.asyncio
async def test_lease_outcome_does_not_claim_release_when_channel_emulator_rejects_it():
    from app.services.instrument_test_lease import (
        InstrumentTestLease,
        InstrumentTestLeaseReleaseError,
    )

    events: list[str] = []
    lease = InstrumentTestLease(
        lambda: SimpleNamespace(
            drivers={"channelEmulator": _LeaseCe(events, release_ok=False)},
            clear_metrics_cache=None,
        )
    )
    outcome = None
    with pytest.raises(InstrumentTestLeaseReleaseError):
        async with lease.hold("ce-session", control_uxm=False) as outcome:
            pass

    assert outcome is not None
    assert outcome.channel_emulator_transport_released_confirmed is False


def _install_real_lease(monkeypatch, module, hal):
    from app.services.instrument_test_lease import InstrumentTestLease
    from app.services import instrument_hal_service

    monkeypatch.setattr(instrument_hal_service, "_hal_service", hal)
    lease = InstrumentTestLease(instrument_hal_service.get_hal_service)
    monkeypatch.setattr(module, "instrument_test_lease", lease.hold)
    return lease


@pytest.mark.asyncio
async def test_scope_validates_then_orders_operation_safe_idle_and_release(monkeypatch):
    from app.services import channel_emulator_execution_session as module
    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    execution = _scope_execution(_frozen_plan(driver))

    async with module.channel_emulator_execution_scope(
        None,
        execution,
        purpose="formal-case:execution-1",
        binding=_frozen_binding_for_driver(driver, execution_mode="real"),
        plan=_frozen_plan(driver),
        hal=hal,
        validate_before_remote=lambda _hal: None,
    ) as outcome:
        driver.events.append("operation")
        await cleanup_chamber_instruments(hal, "execution-1")
        assert outcome.channel_emulator_remote_acquired_confirmed is True

    assert driver.events == ["acquire", "operation", "safe-idle", "release"]
    assert outcome.channel_emulator_transport_released_confirmed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("execution_mode", ["real", "simulated"])
async def test_scope_safe_idle_and_release_use_the_exact_acquired_driver_after_force_reload(
    monkeypatch, execution_mode
):
    """force reload must not splice a replacement into an active lifecycle."""
    from app.services import channel_emulator_execution_session as module
    from app.services import instrument_hal_service

    acquired = (
        _RealCe()
        if execution_mode == "real"
        else MockChannelEmulator("frozen-mock", {})
    )
    acquired.events = []

    async def acquire_remote_control():
        acquired.events.append("acquire")
        return True

    async def stop_emulation():
        acquired.events.append("safe-idle")
        return True

    async def release_to_local_control():
        acquired.events.append("release")
        return True

    acquired.acquire_remote_control = acquire_remote_control
    acquired.stop_emulation = stop_emulation
    acquired.release_to_local_control = release_to_local_control
    initial_drivers = (
        {"channelEmulator": acquired} if execution_mode == "real" else {}
    )
    initial_hal = SimpleNamespace(drivers=initial_drivers, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, initial_hal)
    if execution_mode == "simulated":
        monkeypatch.setattr(module, "MockChannelEmulator", lambda *_args: acquired)

    replacement = _RealCe()
    replacement.events = []
    reloaded_hal = SimpleNamespace(
        drivers={"channelEmulator": replacement}, clear_metrics_cache=None
    )
    binding = _frozen_binding_for_driver(acquired, execution_mode=execution_mode)
    plan = _frozen_plan(
        acquired,
        source="hal" if execution_mode == "real" else "fallback_mock",
    )

    async with module.channel_emulator_execution_scope(
        None,
        _scope_execution(plan),
        purpose="force-reload:execution-1",
        binding=binding,
        plan=plan,
        hal=initial_hal,
        validate_before_remote=lambda _hal: None,
    ) as outcome:
        acquired.events.append("operation")
        outcome.mark_operation_result(True)
        instrument_hal_service._hal_service = reloaded_hal
        # Production executors call get_hal_service() again inside the body.
        # A forced reload must not redirect configuration/playback to the new
        # instance while stop/release still target the acquired instance.
        body_hal = instrument_hal_service.get_hal_service()
        assert body_hal.drivers["channelEmulator"] is acquired

    assert acquired.events == ["acquire", "operation", "safe-idle", "release"]
    assert replacement.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raised",
    [None, RuntimeError("operation failed"), asyncio.CancelledError()],
)
async def test_bypass_terminal_clear_occurs_after_passthrough_on_every_exit(
    monkeypatch, raised
):
    """Pre-bypass GOS cannot stand in for terminal SAFE_IDLE after STATIC."""
    from app.services import channel_emulator_execution_session as module

    class PassthroughCe(_RealCe):
        async def set_passthrough_mode(self) -> bool:
            self.events.append("passthrough-on")
            return True

        async def clear_passthrough_mode(self) -> bool:
            self.events.append("passthrough-clear")
            return True

    driver = PassthroughCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    terminal: list[dict] = []
    db = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(
        module,
        "persist_channel_emulator_terminal_evidence",
        lambda _db, _execution_id, evidence: terminal.append(evidence),
    )

    async def run():
        async with module.channel_emulator_execution_scope(
            db,
            _scope_execution(_frozen_plan(driver)),
            purpose="bypass:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ) as outcome:
            driver.events.append("bypass-pre-stop")
            assert await module.ensure_channel_emulator_safe_idle() is True
            module.require_channel_emulator_passthrough_clear()
            assert await driver.set_passthrough_mode() is True
            if raised is not None:
                raise raised
            outcome.mark_operation_result(True)

    if raised is None:
        await run()
    else:
        with pytest.raises(type(raised)):
            await run()
    assert driver.events.count("safe-idle") == 1
    assert driver.events == [
        "acquire",
        "bypass-pre-stop",
        "safe-idle",
        "passthrough-on",
        "passthrough-clear",
        "release",
    ]
    assert terminal[0]["safe_idle_action"] == "clear_passthrough_mode"
    assert terminal[0]["safe_idle_confirmed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("start_result", [True, False, RuntimeError("start failed")])
async def test_bypass_fade_rearms_terminal_stop_before_start_can_change_output(
    monkeypatch, start_result
):
    """A fade start after STATIC must leave the terminal action at GOS."""
    from app.services import channel_emulator_execution_session as module

    class FadingCe(_RealCe):
        async def set_passthrough_mode(self) -> bool:
            self.events.append("passthrough-on")
            return True

        async def clear_passthrough_mode(self) -> bool:
            self.events.append("passthrough-clear")
            return True

        async def start_emulation(self) -> bool:
            self.events.append("fade-start-maybe-active")
            if isinstance(start_result, BaseException):
                raise start_result
            return start_result

    driver = FadingCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    terminal: list[dict] = []
    db = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(
        module,
        "persist_channel_emulator_terminal_evidence",
        lambda _db, _execution_id, evidence: terminal.append(evidence),
    )

    async def run():
        async with module.channel_emulator_execution_scope(
            db,
            _scope_execution(_frozen_plan(driver)),
            purpose="bypass-fade:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ) as outcome:
            assert await module.ensure_channel_emulator_safe_idle() is True
            module.require_channel_emulator_passthrough_clear()
            assert await driver.set_passthrough_mode() is True
            module.require_channel_emulator_stop_after_output_change()
            started = await driver.start_emulation()
            outcome.mark_operation_result(started)

    if isinstance(start_result, BaseException):
        with pytest.raises(type(start_result), match="start failed"):
            await run()
    else:
        await run()

    assert driver.events == [
        "acquire",
        "safe-idle",
        "passthrough-on",
        "fade-start-maybe-active",
        "safe-idle",
        "release",
    ]
    assert "passthrough-clear" not in driver.events
    assert terminal[0]["safe_idle_action"] == "stop_emulation"
    assert terminal[0]["safe_idle_confirmed"] is True
    assert terminal[0]["terminal_state"] == (
        "completed" if start_result is True else "failed"
    )


@pytest.mark.asyncio
async def test_bypass_fade_caller_cancel_waits_for_terminal_stop_before_release(
    monkeypatch,
):
    """Real task cancellation during start cannot strand GO or skip release."""
    from app.services import channel_emulator_execution_session as module

    start_entered = asyncio.Event()
    never_finishes = asyncio.Event()

    class BlockingFadeCe(_RealCe):
        async def set_passthrough_mode(self) -> bool:
            self.events.append("passthrough-on")
            return True

        async def clear_passthrough_mode(self) -> bool:
            self.events.append("passthrough-clear")
            return True

        async def start_emulation(self) -> bool:
            self.events.append("fade-start-maybe-active")
            start_entered.set()
            await never_finishes.wait()
            return True

    driver = BlockingFadeCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    terminal: list[dict] = []
    db = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(
        module,
        "persist_channel_emulator_terminal_evidence",
        lambda _db, _execution_id, evidence: terminal.append(evidence),
    )

    async def run():
        async with module.channel_emulator_execution_scope(
            db,
            _scope_execution(_frozen_plan(driver)),
            purpose="bypass-fade-cancel:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            assert await module.ensure_channel_emulator_safe_idle() is True
            module.require_channel_emulator_passthrough_clear()
            assert await driver.set_passthrough_mode() is True
            module.require_channel_emulator_stop_after_output_change()
            await driver.start_emulation()

    task = asyncio.create_task(run())
    await start_entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert driver.events == [
        "acquire",
        "safe-idle",
        "passthrough-on",
        "fade-start-maybe-active",
        "safe-idle",
        "release",
    ]
    assert terminal[0]["safe_idle_action"] == "stop_emulation"
    assert terminal[0]["safe_idle_confirmed"] is True
    assert terminal[0]["terminal_state"] == "cancelled"


def test_measure_rearms_terminal_stop_before_bypass_fade_start():
    """Protect the production call site, not only the session state helper."""
    from app.services.mimo_ota.executors.measure import MeasureExecutor

    source = inspect.getsource(MeasureExecutor.execute)
    fade_branch = source[source.index("if config.f64_bypass_mode is not None and config.f64_fade_after_attach:") :]
    arm = fade_branch.index("require_channel_emulator_stop_after_output_change()")
    start = fade_branch.index("faded = await emulator.start_emulation()")
    assert arm < start


@pytest.mark.asyncio
async def test_scope_rejects_live_plan_or_binding_drift_before_any_ce_io(monkeypatch):
    from app.services import channel_emulator_execution_session as module
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    frozen_binding = _frozen_binding_for_driver(driver, execution_mode="real")
    frozen_plan = _frozen_plan(driver)
    driver._connection_port = 9999

    with pytest.raises(InstrumentTestLeaseError, match="connection"):
        async with module.channel_emulator_execution_scope(
            None,
            _scope_execution(frozen_plan),
            purpose="formal-case:execution-1",
            binding=frozen_binding,
            plan=frozen_plan,
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            raise AssertionError("identity drift must reject before yield")

    assert driver.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "bad_digest", "plan_self_proof"])
async def test_scope_rejects_invalid_load_request_before_any_instrument_io(
    monkeypatch, fault
):
    from app.hal.channel_emulator_execution_plan import (
        resolve_channel_emulator_execution_plan,
    )
    from app.services import channel_emulator_execution_session as module
    from app.services.channel_emulator_execution_plan import (
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
    )
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    events: list[str] = []
    driver = _RealCe()
    driver.events = events

    class BaseStation:
        async def acquire_remote_control(self):
            events.append("bs-acquire")
            raise AssertionError("load request gate must precede BaseStation I/O")

    hal = SimpleNamespace(
        drivers={"channelEmulator": driver, "baseStation": BaseStation()},
        clear_metrics_cache=None,
    )
    _install_real_lease(monkeypatch, module, hal)
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    native_plan = _frozen_plan(driver)
    execution = _scope_execution(native_plan)
    plan = native_plan
    if fault == "missing":
        execution.config.pop(CE_LOAD_REQUEST_FREEZE_CONFIG_KEY)
    elif fault == "bad_digest":
        execution.config[CE_LOAD_REQUEST_FREEZE_CONFIG_KEY]["digest"] = "bad"
    else:
        alternate = resolve_channel_emulator_execution_plan(
            manifest=driver.adapter_manifest,
            driver_source="hal",
            requested_load_mode="external_waveform",
            binding_digest=BINDING_DIGEST,
        )
        plan = {**alternate.as_payload(), "digest": alternate.digest}
        execution.config[CE_PLAN_FREEZE_CONFIG_KEY] = plan
        request = execution.config[CE_LOAD_REQUEST_FREEZE_CONFIG_KEY]
        request["plan_digest"] = plan["digest"]
        request["digest"] = canonical_payload_digest(
            {key: value for key, value in request.items() if key != "digest"}
        )

    with pytest.raises(InstrumentTestLeaseError):
        async with module.channel_emulator_execution_scope(
            None,
            execution,
            purpose="r5-load-gate:execution-1",
            binding=binding,
            plan=plan,
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            events.append("positioner-io")

    assert events == []


@pytest.mark.asyncio
async def test_scope_rejects_rehashed_asset_load_chain_before_any_instrument_io(
    monkeypatch,
):
    """Request/plan rehash cannot replace the independently frozen asset source."""
    from app.hal.channel_emulator_execution_plan import (
        resolve_channel_emulator_execution_plan,
    )
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services import channel_emulator_execution_session as module
    from app.services.base_station_adapter_profile import (
        FREEZE_CONFIG_KEY,
        MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    )
    from app.services.channel_emulator_execution_plan import (
        CHANNEL_ASSET_RESOLUTION_FREEZE_KEY,
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
    )
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    events: list[str] = []
    driver = _RealCe()
    driver.events = events

    hal = SimpleNamespace(
        drivers={"channelEmulator": driver},
        clear_metrics_cache=None,
    )
    _install_real_lease(monkeypatch, module, hal)
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    asset_id = "f2b3465e-c86e-45a8-b1e8-9d1aaf03d37a"
    frozen_mimo = MIMOOTAConfiguration.model_validate(
        {"engine_mode": "keysight_gcm", "channel_asset_id": asset_id}
    ).model_dump(mode="json")
    asset_payload = {
        "schema_version": 1,
        "channel_asset_id": asset_id,
        "source_type": "standard_3gpp",
        "executable_content_digest": "e" * 64,
    }
    asset_identity = {
        **asset_payload,
        "digest": canonical_payload_digest(asset_payload),
    }
    base_payload = {
        MIMO_OTA_CONFIGURATION_FREEZE_KEY: frozen_mimo,
        CHANNEL_ASSET_RESOLUTION_FREEZE_KEY: asset_identity,
    }
    forged = resolve_channel_emulator_execution_plan(
        manifest=driver.adapter_manifest,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest=BINDING_DIGEST,
    )
    forged_plan = {**forged.as_payload(), "digest": forged.digest}
    forged_request = _load_request_for_evidence(
        frozen_mimo,
        forged_plan,
        source="channel_asset",
        channel_asset_id=asset_id,
        channel_asset_source_type="vendor_file",
        effective_engine_mode="keysight_gcm",
    )
    execution = SimpleNamespace(
        id="execution-1",
        config={
            FREEZE_CONFIG_KEY: {
                **base_payload,
                "digest": canonical_payload_digest(base_payload),
            },
            CE_LOAD_REQUEST_FREEZE_CONFIG_KEY: forged_request,
            CE_PLAN_FREEZE_CONFIG_KEY: forged_plan,
        },
    )

    with pytest.raises(InstrumentTestLeaseError, match="独立冻结资产来源"):
        async with module.channel_emulator_execution_scope(
            None,
            execution,
            purpose="r5-asset-truth-gate:execution-1",
            binding=binding,
            plan=forged_plan,
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            events.append("positioner-io")

    assert events == []


@pytest.mark.asyncio
async def test_complete_run_rejects_path_loss_before_any_instrument_io(monkeypatch):
    """The run-level path-loss gate precedes CE/BS acquire and the operation."""
    from app.hal.base_station import (
        BaseStationControlReleaseResult,
        BaseStationRemoteSessionResult,
    )
    from app.services import base_station_execution_session as base_session
    from app.services import channel_emulator_execution_session as ce_session
    from app.services.instrument_test_lease import InstrumentTestLease, InstrumentTestLeaseError
    from app.services.mimo_ota import path_loss_preflight as preflight_module
    from app.services.mimo_ota.executors import _helpers

    events: list[str] = []
    ce = _RealCe()
    ce.events = events

    class BaseStation:
        adapter_id = "uxm"
        instrument_id = "bs-runtime"

        async def acquire_remote_control(self):
            events.append("bs-acquire")
            return BaseStationRemoteSessionResult(
                adapter_id=self.adapter_id,
                session_token="session",
                acquired_confirmed=True,
                warnings=(),
            )

        async def release_remote_session(self, *_args, **_kwargs):
            events.append("bs-release")
            return BaseStationControlReleaseResult(
                measurement_attempt_id=None,
                lease_id="lease",
                adapter_id=self.adapter_id,
                session_token="session",
                remote_session_acquired_confirmed=True,
                transport_session_released_confirmed=True,
                front_panel_local_confirmed=None,
                warnings=(),
            )

    hal = SimpleNamespace(
        drivers={"channelEmulator": ce, "baseStation": BaseStation()},
        clear_metrics_cache=None,
    )
    monkeypatch.setattr(base_session, "_get_hal_service", lambda: hal)
    monkeypatch.setattr(
        ce_session,
        "instrument_test_lease",
        InstrumentTestLease(lambda: hal).hold,
    )
    monkeypatch.setattr(
        _helpers,
        "load_mimo_ota_config",
        lambda _execution: SimpleNamespace(
            primary_carrier=SimpleNamespace(frequency_hz=3.5e9),
            switch_mode_id="mimo_ota",
            precheck_strict_cal=True,
        ),
    )
    monkeypatch.setattr(
        preflight_module,
        "evaluate_path_loss_preflight",
        lambda *_args, **_kwargs: SimpleNamespace(blocker="untrusted calibration"),
    )
    monkeypatch.setattr(
        ce_session,
        "persist_channel_emulator_terminal_evidence",
        lambda *_args, **_kwargs: None,
    )

    class Db:
        def get(self, _model, _pk):
            return SimpleNamespace(chamber_config=SimpleNamespace(id="chamber"))

        def rollback(self):
            pass

    execution = SimpleNamespace(
        id="execution-1",
        config={
            "channel_emulator_binding_freeze": {
                "lab_profile_id": "11111111-1111-1111-1111-111111111111"
            },
            "channel_emulator_execution_plan_freeze": {},
        },
    )
    operation_called = False

    async def operation():
        nonlocal operation_called
        operation_called = True
        raise AssertionError("path-loss gate must precede the operation")

    with pytest.raises(InstrumentTestLeaseError, match="untrusted calibration"):
        await base_session.run_base_station_execution_session(
            Db(),
            execution,
            SimpleNamespace(
                lab_profile_id="11111111-1111-1111-1111-111111111111"
            ),
            purpose="formal-case:execution-1",
            step_type="MIMO_OTA_MEASURE",
            validate_before_remote=lambda _hal: None,
            operation=operation,
        )

    assert operation_called is False
    assert events == []


@pytest.mark.asyncio
async def test_scope_installs_mock_only_for_explicit_simulated_freeze(monkeypatch):
    from app.services import channel_emulator_execution_session as module
    from app.services.instrument_hal_service import get_hal_service

    frozen_mock = MockChannelEmulator("frozen-mock", {})
    hal = SimpleNamespace(drivers={}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    inspect_now = asyncio.Event()

    async def unrelated_hal_reader():
        await inspect_now.wait()
        return get_hal_service().drivers.get("channelEmulator")

    # 在 scope 之前创建，模拟并发状态 / preview / freeze 请求；它不得继承当前
    # execution task 后续安装的 scoped overlay。
    unrelated = asyncio.create_task(unrelated_hal_reader())

    plan = _frozen_plan(frozen_mock, source="fallback_mock")
    async with module.channel_emulator_execution_scope(
        None,
        _scope_execution(plan),
        purpose="diagnostic:execution-1",
        binding=_frozen_binding_for_driver(frozen_mock, execution_mode="simulated"),
        plan=plan,
        hal=hal,
        validate_before_remote=lambda _hal: None,
    ):
        assert "channelEmulator" not in hal.drivers
        assert isinstance(
            get_hal_service().drivers["channelEmulator"], MockChannelEmulator
        )
        inspect_now.set()
        assert await unrelated is None

    assert "channelEmulator" not in hal.drivers


@pytest.mark.asyncio
async def test_simulated_scope_does_not_shadow_concurrent_real_hal_reload(monkeypatch):
    """在租约锁前赢下的真实 HAL reload 必须对 scope 可见并触发身份拒绝。"""
    from app.services import channel_emulator_execution_session as module
    from app.services import instrument_hal_service
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    frozen_mock = MockChannelEmulator("frozen-mock", {})
    initial_hal = SimpleNamespace(drivers={}, clear_metrics_cache=None)
    lease = _install_real_lease(monkeypatch, module, initial_hal)
    real = _RealCe()
    reloaded_hal = SimpleNamespace(
        drivers={"channelEmulator": real}, clear_metrics_cache=None
    )

    async def run_scope():
        plan = _frozen_plan(frozen_mock, source="fallback_mock")
        async with module.channel_emulator_execution_scope(
            None,
            _scope_execution(plan),
            purpose="diagnostic:execution-1",
            binding=_frozen_binding_for_driver(
                frozen_mock, execution_mode="simulated"
            ),
            plan=plan,
            hal=initial_hal,
            validate_before_remote=lambda _hal: None,
        ):
            raise AssertionError("real reload must invalidate simulated freeze")

    async with lease.hal_mutation_guard():
        task = asyncio.create_task(run_scope())
        await asyncio.sleep(0)
        instrument_hal_service._hal_service = reloaded_hal

    with pytest.raises(InstrumentTestLeaseError, match="mock to real"):
        await task
    assert real.events == []
    assert initial_hal.drivers == {}


@pytest.mark.asyncio
async def test_scope_acquires_channel_emulator_last_so_later_acquire_failure_cannot_skip_safe_idle(
    monkeypatch,
):
    """CE 一旦取得就必须进入 scope body，退出时才能唯一执行 SAFE_IDLE。

    BaseStation acquire 在 CE 之后失败会让 async context 尚未 yield，旧实现只做
    CE release、从未 stop_emulation。租约应先取得 BaseStation，最后才取得 CE。
    """
    from app.hal.base_station import (
        BaseStationControlReleaseResult,
        BaseStationRemoteSessionResult,
    )
    from app.services import channel_emulator_execution_session as module

    events: list[str] = []
    ce = _RealCe()
    ce.events = events

    class RejectingBaseStation:
        adapter_id = "uxm"
        instrument_id = "bs-runtime"

        async def acquire_remote_control(self):
            events.append("bs-acquire")
            return BaseStationRemoteSessionResult(
                adapter_id=self.adapter_id,
                session_token="rejected",
                acquired_confirmed=False,
                warnings=(),
            )

        async def release_remote_session(
            self,
            expected_session_token,
            *,
            measurement_attempt_id=None,
            lease_id="",
        ):
            events.append("bs-release")
            return BaseStationControlReleaseResult(
                measurement_attempt_id=measurement_attempt_id,
                lease_id=lease_id,
                adapter_id=self.adapter_id,
                session_token=expected_session_token,
                remote_session_acquired_confirmed=False,
                transport_session_released_confirmed=True,
                front_panel_local_confirmed=None,
                warnings=(),
            )

    hal = SimpleNamespace(
        drivers={"channelEmulator": ce, "baseStation": RejectingBaseStation()},
        clear_metrics_cache=None,
    )
    _install_real_lease(monkeypatch, module, hal)

    with pytest.raises(Exception, match="Remote|控制会话"):
        async with module.channel_emulator_execution_scope(
            None,
            _scope_execution(_frozen_plan(ce)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(ce, execution_mode="real"),
            plan=_frozen_plan(ce),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            raise AssertionError("rejected BaseStation acquire must not yield")

    assert events[0] == "bs-acquire"
    assert "acquire" not in events
    assert "safe-idle" not in events


@pytest.mark.asyncio
async def test_cancellation_during_safe_idle_waits_for_stop_before_release_and_propagates(
    monkeypatch,
):
    from app.services import channel_emulator_execution_session as module

    stop_entered = asyncio.Event()
    allow_stop_to_finish = asyncio.Event()

    class BlockingSafeIdleCe(_RealCe):
        async def stop_emulation(self) -> bool:
            self.events.append("safe-idle-enter")
            stop_entered.set()
            await allow_stop_to_finish.wait()
            self.events.append("safe-idle-complete")
            return True

    driver = BlockingSafeIdleCe()
    hal = SimpleNamespace(
        drivers={"channelEmulator": driver}, clear_metrics_cache=None
    )
    _install_real_lease(monkeypatch, module, hal)

    async def run_scope():
        async with module.channel_emulator_execution_scope(
            None,
            _scope_execution(_frozen_plan(driver)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ) as outcome:
            driver.events.append("operation")
            outcome.mark_operation_result(True)

    task = asyncio.create_task(run_scope())
    await stop_entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()  # 追加 cancel 也不得越过仍在执行的 SAFE_IDLE。
    await asyncio.sleep(0)
    assert "release" not in driver.events

    allow_stop_to_finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert driver.events == [
        "acquire",
        "operation",
        "safe-idle-enter",
        "safe-idle-complete",
        "release",
    ]


@pytest.mark.asyncio
async def test_scope_never_falls_back_to_mock_for_real_freeze(monkeypatch):
    from app.services import channel_emulator_execution_session as module
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    expected = _RealCe()
    hal = SimpleNamespace(drivers={}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)

    with pytest.raises(InstrumentTestLeaseError, match="missing"):
        async with module.channel_emulator_execution_scope(
            None,
            _scope_execution(_frozen_plan(expected)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(expected, execution_mode="real"),
            plan=_frozen_plan(expected),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            raise AssertionError("real freeze must not get a mock")

    assert hal.drivers == {}


@pytest.mark.asyncio
async def test_scope_malformed_binding_keeps_the_validation_error(monkeypatch):
    from app.services import channel_emulator_execution_session as module
    from app.services.instrument_test_lease import InstrumentTestLeaseError

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    terminal: list[dict] = []
    db = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(
        module,
        "persist_channel_emulator_terminal_evidence",
        lambda _db, _execution_id, evidence: terminal.append(evidence),
    )

    with pytest.raises(InstrumentTestLeaseError, match="binding"):
        async with module.channel_emulator_execution_scope(
            db,
            _scope_execution(_frozen_plan(driver)),
            purpose="formal-case:execution-1",
            binding=[],
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            raise AssertionError("malformed freeze must not yield")

    assert driver.events == []
    assert terminal[0]["terminal_state"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raised",
    [RuntimeError("operation failed"), asyncio.CancelledError()],
)
async def test_scope_safe_idles_and_releases_after_exception_or_cancel(
    monkeypatch, raised
):
    from app.services import channel_emulator_execution_session as module
    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)

    with pytest.raises(type(raised)):
        async with module.channel_emulator_execution_scope(
            None,
            _scope_execution(_frozen_plan(driver)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            driver.events.append("operation")
            await cleanup_chamber_instruments(hal, "execution-1")
            raise raised

    assert driver.events == ["acquire", "operation", "safe-idle", "release"]


@pytest.mark.asyncio
async def test_scope_safe_idle_rejection_fails_loud_but_still_releases(monkeypatch):
    from app.services import channel_emulator_execution_session as module

    driver = _RealCe()

    async def rejected() -> bool:
        driver.events.append("safe-idle")
        return False

    driver.stop_emulation = rejected
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)

    with pytest.raises(module.ChannelEmulatorExecutionSessionError, match="safe idle"):
        async with module.channel_emulator_execution_scope(
            None,
            _scope_execution(_frozen_plan(driver)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            driver.events.append("operation")

    assert driver.events == ["acquire", "operation", "safe-idle", "release"]


@pytest.mark.asyncio
async def test_driver_cancelled_error_is_safe_idle_failure_not_caller_cancellation(
    monkeypatch,
):
    """A driver may raise CancelledError internally without cancelling this task."""

    from app.services import channel_emulator_execution_session as module

    driver = _RealCe()

    async def internally_cancelled_stop() -> bool:
        driver.events.append("safe-idle")
        raise asyncio.CancelledError("driver operation cancelled internally")

    driver.stop_emulation = internally_cancelled_stop
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    terminal: list[dict] = []
    db = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(
        module,
        "persist_channel_emulator_terminal_evidence",
        lambda _db, _execution_id, evidence: terminal.append(evidence),
    )

    with pytest.raises(
        module.ChannelEmulatorExecutionSessionError,
        match="cancelled internally",
    ):
        async with module.channel_emulator_execution_scope(
            db,
            _scope_execution(_frozen_plan(driver)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ) as outcome:
            driver.events.append("operation")
            outcome.mark_operation_result(True)

    assert asyncio.current_task() is not None
    assert asyncio.current_task().cancelling() == 0
    assert driver.events == ["acquire", "operation", "safe-idle", "release"]
    assert terminal[0]["terminal_state"] == "failed"
    assert terminal[0]["safe_idle_confirmed"] is False
    assert terminal[0]["safe_idle_error_type"] == (
        "ChannelEmulatorExecutionSessionError"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation_error",
    [RuntimeError("operation failed"), asyncio.CancelledError()],
)
async def test_scope_preserves_operation_and_safe_idle_failures_then_releases(
    monkeypatch, operation_error
):
    from app.services import channel_emulator_execution_session as module

    driver = _RealCe()

    async def failed_stop() -> bool:
        driver.events.append("safe-idle")
        raise OSError("GOS transport failed")

    driver.stop_emulation = failed_stop
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    terminal: list[dict] = []
    db = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(
        module,
        "persist_channel_emulator_terminal_evidence",
        lambda _db, _execution_id, evidence: terminal.append(evidence),
    )

    with pytest.raises(type(operation_error)) as caught:
        async with module.channel_emulator_execution_scope(
            db,
            _scope_execution(_frozen_plan(driver)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            driver.events.append("operation")
            raise operation_error

    assert driver.events == ["acquire", "operation", "safe-idle", "release"]
    assert isinstance(
        getattr(caught.value, "channel_emulator_safe_idle_error", None), OSError
    )
    assert any("SAFE_IDLE" in note for note in getattr(caught.value, "__notes__", ()))
    assert terminal[0]["safe_idle_confirmed"] is False
    assert terminal[0]["safe_idle_error_type"] == "OSError"
    assert terminal[0]["terminal_state"] == (
        "cancelled" if isinstance(operation_error, asyncio.CancelledError) else "failed"
    )


@pytest.mark.asyncio
async def test_failed_scope_rolls_back_business_state_before_terminal_commit(monkeypatch):
    from app.services import channel_emulator_execution_session as module

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    events: list[str] = []

    class Db:
        business_dirty = True

        def rollback(self) -> None:
            events.append("rollback")
            self.business_dirty = False

    db = Db()

    def persist(persist_db, execution_id, evidence):
        assert persist_db is db
        assert execution_id == "execution-1"
        assert db.business_dirty is False
        assert evidence["terminal_state"] == "failed"
        events.append("terminal-commit")

    monkeypatch.setattr(module, "persist_channel_emulator_terminal_evidence", persist)

    with pytest.raises(RuntimeError, match="business failed"):
        async with module.channel_emulator_execution_scope(
            db,
            _scope_execution(_frozen_plan(driver)),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            events.append("business-write")
            raise RuntimeError("business failed")

    assert events == ["business-write", "rollback", "terminal-commit"]


@pytest.mark.asyncio
async def test_scope_persists_terminal_truth_only_after_safe_idle_and_release(monkeypatch):
    from app.services import channel_emulator_execution_session as module

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    captured: list[dict] = []

    def persist(_db, execution_id, evidence):
        assert execution_id == "execution-1"
        assert driver.events == ["acquire", "operation", "safe-idle", "release"]
        captured.append(evidence)

    monkeypatch.setattr(module, "persist_channel_emulator_terminal_evidence", persist)
    async with module.channel_emulator_execution_scope(
        object(),
        _scope_execution(_frozen_plan(driver)),
        purpose="formal-case:execution-1",
        binding=_frozen_binding_for_driver(driver, execution_mode="real"),
        plan=_frozen_plan(driver),
        hal=hal,
        validate_before_remote=lambda _hal: None,
    ) as outcome:
        driver.events.append("operation")
        outcome.mark_operation_result(True)

    assert captured[0]["terminal_state"] == "completed"
    assert captured[0]["safe_idle_confirmed"] is True
    assert captured[0]["remote_acquired_confirmed"] is True
    assert captured[0]["transport_released_confirmed"] is True
    assert captured[0]["instrument_id"] == "ce-runtime"
    assert captured[0]["operation_scope"] == "formal-case:execution-1"
    payload = {key: value for key, value in captured[0].items() if key != "digest"}
    assert captured[0]["digest"] == canonical_payload_digest(payload)


@pytest.mark.asyncio
async def test_scope_does_not_turn_unmarked_normal_exit_into_success(monkeypatch):
    from app.services import channel_emulator_execution_session as module

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    captured: list[dict] = []
    monkeypatch.setattr(
        module,
        "persist_channel_emulator_terminal_evidence",
        lambda _db, _execution_id, evidence: captured.append(evidence),
    )

    async with module.channel_emulator_execution_scope(
        object(),
        _scope_execution(_frozen_plan(driver)),
        purpose="formal-case:execution-1",
        binding=_frozen_binding_for_driver(driver, execution_mode="real"),
        plan=_frozen_plan(driver),
        hal=hal,
        validate_before_remote=lambda _hal: None,
    ):
        driver.events.append("operation")

    assert captured[0]["terminal_state"] == "failed"


def _terminal_evidence(
    binding: dict,
    plan: dict,
    *,
    execution_mode: str,
    terminal_state: str = "completed",
    session_id: str = "session-1",
    operation_scope: str | None = None,
) -> dict:
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "execution_id": "execution-1",
        "binding_digest": binding["binding_digest"],
        "binding_freeze_digest": binding["digest"],
        "plan_digest": plan["digest"],
        "execution_mode": execution_mode,
        "adapter_id": plan["adapter_id"],
        "driver_module": binding["expected_driver_module"],
        "driver_name": binding["expected_driver_name"],
        "driver_connection": binding["expected_driver_connection"],
        "lease_id": "lease-1",
        "instrument_id": "ce-runtime",
        "remote_acquired_confirmed": True if execution_mode == "real" else None,
        "required_safe_idle_action": "stop_emulation",
        "safe_idle_action": "stop_emulation",
        "safe_idle_confirmed": terminal_state == "completed",
        "transport_released_confirmed": True if execution_mode == "real" else None,
        "operation_succeeded": terminal_state == "completed",
        "terminal_state": terminal_state,
        "error_type": None if terminal_state == "completed" else "RuntimeError",
        "safe_idle_error_type": None,
    }
    if operation_scope is not None:
        payload["operation_scope"] = operation_scope
    return {**payload, "digest": canonical_payload_digest(payload)}


def test_p2_66_validates_safe_idle_action_per_execution_scope():
    """Earlier PRECHECK scopes must not inherit MEASURE's bypass cleanup."""
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    frozen_mimo = MIMOOTAConfiguration.model_validate(
        {
            "engine_mode": "keysight_gcm",
            "emulation_file": "scenario.smu",
            "f64_bypass_mode": 2,
            "f64_fade_after_attach": False,
        }
    ).model_dump(mode="json")
    precheck = _terminal_evidence(binding, plan, execution_mode="real")
    measure = _terminal_evidence(binding, plan, execution_mode="real")
    measure.update(
        session_id="session-2",
        required_safe_idle_action="clear_passthrough_mode",
        safe_idle_action="clear_passthrough_mode",
    )
    measure["digest"] = canonical_payload_digest(
        {key: value for key, value in measure.items() if key != "digest"}
    )
    execution = _execution_with_ce_evidence(
        binding,
        plan,
        precheck,
        frozen_mimo=frozen_mimo,
    )
    execution.config[CE_TERMINAL_EVIDENCE_CONFIG_KEY] = [precheck, measure]

    assert _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    ) == (None, None)


def test_p2_66_preserves_completed_real_execution_with_v1_manifest_and_plan():
    """②部署后不能把③已经完成且不可变的 v1 正式执行反向降成 invalid。"""

    from app.hal.channel_emulator_execution_plan import (
        CHANNEL_EMULATOR_EXECUTION_PLAN_V1_OPERATIONS,
    )
    from app.hal.channel_emulator_manifest import (
        CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    raw_manifest = binding["resolved_binding"]["manifest"]
    legacy_manifest = {
        **raw_manifest,
        "schema_version": 1,
        "operations": [
            item
            for item in raw_manifest["operations"]
            if item["operation"] in CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS
        ],
    }
    binding["resolved_binding"] = {
        **binding["resolved_binding"],
        "manifest": legacy_manifest,
    }
    binding["digest"] = canonical_payload_digest(
        {key: value for key, value in binding.items() if key != "digest"}
    )

    current_plan = _frozen_plan(driver)
    legacy_plan_payload = {
        **{key: value for key, value in current_plan.items() if key != "digest"},
        "schema_version": 1,
        "operations": [
            item
            for item in current_plan["operations"]
            if item["operation"] in CHANNEL_EMULATOR_EXECUTION_PLAN_V1_OPERATIONS
        ],
    }
    legacy_plan = {
        **legacy_plan_payload,
        "digest": canonical_payload_digest(legacy_plan_payload),
    }
    terminal = _terminal_evidence(
        binding,
        legacy_plan,
        execution_mode="real",
    )
    execution = _execution_with_ce_evidence(binding, legacy_plan, terminal)

    assert _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    ) == (None, None)


def test_p2_66_rejects_terminal_action_that_misses_scope_requirement():
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    terminal = _terminal_evidence(binding, plan, execution_mode="real")
    terminal["safe_idle_action"] = "clear_passthrough_mode"
    terminal["digest"] = canonical_payload_digest(
        {key: value for key, value in terminal.items() if key != "digest"}
    )
    execution = _execution_with_ce_evidence(binding, plan, terminal)

    classification, reason = _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )
    assert classification == "invalid"
    assert "scope requirement" in reason


def _load_request_for_evidence(
    frozen_mimo: dict,
    plan: dict,
    *,
    source: str = "mimo_configuration",
    channel_asset_id: str | None = None,
    channel_asset_source_type: str | None = None,
    effective_engine_mode: str | None = None,
) -> dict:
    from app.hal.channel_emulator_execution_plan import (
        requested_channel_emulator_load_mode,
    )

    engine_mode = effective_engine_mode or frozen_mimo["engine_mode"]
    payload = {
        "schema_version": 1,
        "source": source,
        "mimo_configuration_digest": canonical_payload_digest(frozen_mimo),
        "channel_asset_id": channel_asset_id,
        "channel_asset_source_type": channel_asset_source_type,
        "effective_engine_mode": engine_mode,
        "requested_load_mode": requested_channel_emulator_load_mode(engine_mode),
        "plan_digest": plan["digest"],
    }
    return {**payload, "digest": canonical_payload_digest(payload)}


def _execution_with_ce_evidence(
    binding: dict,
    plan: dict,
    terminal: dict,
    *,
    frozen_mimo: dict | None = None,
    load_request: dict | None = None,
):
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.base_station_adapter_profile import (
        FREEZE_CONFIG_KEY,
        MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    )
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.channel_emulator_binding import CE_FREEZE_CONFIG_KEY
    from app.services.channel_emulator_execution_plan import (
        CHANNEL_ASSET_RESOLUTION_FREEZE_KEY,
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
    )

    frozen_mimo = frozen_mimo or MIMOOTAConfiguration.model_validate(
        {"engine_mode": "keysight_gcm", "emulation_file": "scenario.smu"}
    ).model_dump(mode="json")
    load_request = load_request or _load_request_for_evidence(frozen_mimo, plan)
    base_station_payload = {MIMO_OTA_CONFIGURATION_FREEZE_KEY: frozen_mimo}
    if load_request.get("source") == "channel_asset":
        asset_payload = {
            "schema_version": 1,
            "channel_asset_id": load_request["channel_asset_id"],
            "source_type": load_request["channel_asset_source_type"],
            "executable_content_digest": "e" * 64,
        }
        base_station_payload[CHANNEL_ASSET_RESOLUTION_FREEZE_KEY] = {
            **asset_payload,
            "digest": canonical_payload_digest(asset_payload),
        }
    base_station_freeze = {
        **base_station_payload,
        "digest": canonical_payload_digest(base_station_payload),
    }
    return SimpleNamespace(
        id="execution-1",
        status="completed",
        config={
            FREEZE_CONFIG_KEY: base_station_freeze,
            CE_FREEZE_CONFIG_KEY: binding,
            CE_LOAD_REQUEST_FREEZE_CONFIG_KEY: load_request,
            CE_PLAN_FREEZE_CONFIG_KEY: plan,
            CE_TERMINAL_EVIDENCE_CONFIG_KEY: [terminal],
        },
    )


def test_p2_66_uses_frozen_channel_asset_load_truth_instead_of_stale_mimo_engine():
    from app.hal.channel_emulator_execution_plan import (
        resolve_channel_emulator_execution_plan,
    )
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    asset_id = "f2b3465e-c86e-45a8-b1e8-9d1aaf03d37a"
    frozen_mimo = MIMOOTAConfiguration.model_validate(
        {
            "engine_mode": "keysight_gcm",
            "emulation_file": "stale.smu",
            "channel_asset_id": asset_id,
        }
    ).model_dump(mode="json")
    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    resolved_plan = resolve_channel_emulator_execution_plan(
        manifest=driver.adapter_manifest,
        driver_source="hal",
        requested_load_mode="external_waveform",
        binding_digest=binding["binding_digest"],
    )
    plan = {**resolved_plan.as_payload(), "digest": resolved_plan.digest}
    terminal = _terminal_evidence(binding, plan, execution_mode="real")
    request = _load_request_for_evidence(
        frozen_mimo,
        plan,
        source="channel_asset",
        channel_asset_id=asset_id,
        channel_asset_source_type="standard_3gpp",
        effective_engine_mode="mimo_first_asc",
    )
    execution = _execution_with_ce_evidence(
        binding,
        plan,
        terminal,
        frozen_mimo=frozen_mimo,
        load_request=request,
    )

    assert _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    ) == (None, None)


def test_p2_66_rejects_rehashed_asset_source_that_disagrees_with_independent_freeze():
    from app.hal.channel_emulator_execution_plan import (
        resolve_channel_emulator_execution_plan,
    )
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.channel_emulator_execution_plan import (
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
        CE_PLAN_FREEZE_CONFIG_KEY,
    )
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    asset_id = "f2b3465e-c86e-45a8-b1e8-9d1aaf03d37a"
    frozen_mimo = MIMOOTAConfiguration.model_validate(
        {"engine_mode": "keysight_gcm", "channel_asset_id": asset_id}
    ).model_dump(mode="json")
    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    external = resolve_channel_emulator_execution_plan(
        manifest=driver.adapter_manifest,
        driver_source="hal",
        requested_load_mode="external_waveform",
        binding_digest=BINDING_DIGEST,
    )
    original_plan = {**external.as_payload(), "digest": external.digest}
    original_request = _load_request_for_evidence(
        frozen_mimo,
        original_plan,
        source="channel_asset",
        channel_asset_id=asset_id,
        channel_asset_source_type="standard_3gpp",
        effective_engine_mode="mimo_first_asc",
    )
    execution = _execution_with_ce_evidence(
        binding,
        original_plan,
        _terminal_evidence(binding, original_plan, execution_mode="real"),
        frozen_mimo=frozen_mimo,
        load_request=original_request,
    )

    native = resolve_channel_emulator_execution_plan(
        manifest=driver.adapter_manifest,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest=BINDING_DIGEST,
    )
    forged_plan = {**native.as_payload(), "digest": native.digest}
    forged_request = _load_request_for_evidence(
        frozen_mimo,
        forged_plan,
        source="channel_asset",
        channel_asset_id=asset_id,
        channel_asset_source_type="vendor_file",
        effective_engine_mode="keysight_gcm",
    )
    execution.config[CE_PLAN_FREEZE_CONFIG_KEY] = forged_plan
    execution.config[CE_LOAD_REQUEST_FREEZE_CONFIG_KEY] = forged_request
    execution.config[CE_TERMINAL_EVIDENCE_CONFIG_KEY] = [
        _terminal_evidence(binding, forged_plan, execution_mode="real")
    ]

    classification, reason = _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    )
    assert classification == "invalid"
    assert "独立冻结资产来源" in reason


@pytest.mark.parametrize(
    ("mutate", "reason_fragment"),
    [
        (lambda frozen: frozen.update(schema_version=999), "binding"),
        (lambda frozen: frozen.update(execution_mode="unsafe"), "binding"),
        (lambda frozen: frozen.update(unexpected="accepted-by-digest"), "binding"),
    ],
)
def test_p2_66_rejects_semantically_malformed_ce_binding_even_with_fresh_digest(
    mutate,
    reason_fragment,
):
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    mutate(binding)
    binding["digest"] = canonical_payload_digest(
        {key: value for key, value in binding.items() if key != "digest"}
    )
    terminal = _terminal_evidence(binding, plan, execution_mode="real")
    outcome = project_execution_evidence_outcome(
        _execution_with_ce_evidence(binding, plan, terminal)
    )

    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any(reason_fragment in reason for reason in outcome.reasons)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda terminal: terminal.update(schema_version=999),
        lambda terminal: terminal.update(session_id=""),
        lambda terminal: terminal.update(lease_id=""),
        lambda terminal: terminal.update(instrument_id=""),
        lambda terminal: terminal.update(execution_mode="unsafe"),
        lambda terminal: terminal.update(error_type="RuntimeError"),
        lambda terminal: terminal.update(unexpected="accepted-by-digest"),
    ],
)
def test_p2_66_rejects_semantically_malformed_completed_ce_terminal_even_with_fresh_digest(
    mutate,
):
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    terminal = _terminal_evidence(binding, plan, execution_mode="real")
    mutate(terminal)
    terminal["digest"] = canonical_payload_digest(
        {key: value for key, value in terminal.items() if key != "digest"}
    )
    outcome = project_execution_evidence_outcome(
        _execution_with_ce_evidence(binding, plan, terminal)
    )

    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any("terminal evidence" in reason for reason in outcome.reasons)


def test_p2_66_rejects_plan_derived_from_a_different_manifest():
    """Matching binding_digest is not proof that the plan came from that binding."""

    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    binding_driver = _RealCe()

    class DifferentAdapter(_RealCe):
        adapter_manifest = _RealCe.adapter_manifest.model_copy(
            update={"adapter_id": "different_adapter"}
        )

    binding = _frozen_binding_for_driver(binding_driver, execution_mode="real")
    foreign_plan = _frozen_plan(DifferentAdapter())
    terminal = _terminal_evidence(binding, foreign_plan, execution_mode="real")

    outcome = project_execution_evidence_outcome(
        _execution_with_ce_evidence(binding, foreign_plan, terminal)
    )

    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any(
        "plan" in reason and "binding manifest" in reason
        for reason in outcome.reasons
    )


@pytest.mark.parametrize(
    ("driver_source", "requested_load_mode"),
    [
        ("fallback_mock", "native_model"),
        ("hal", "external_waveform"),
    ],
)
def test_p2_66_rejects_plan_source_or_load_mode_that_disagrees_with_frozen_truth(
    driver_source,
    requested_load_mode,
):
    """Plan fields cannot choose their own inputs and then verify themselves."""
    from app.hal.channel_emulator_execution_plan import (
        resolve_channel_emulator_execution_plan,
    )
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    foreign = resolve_channel_emulator_execution_plan(
        manifest=driver.adapter_manifest,
        driver_source=driver_source,
        requested_load_mode=requested_load_mode,
        binding_digest=binding["binding_digest"],
    )
    plan = {**foreign.as_payload(), "digest": foreign.digest}
    terminal = _terminal_evidence(binding, plan, execution_mode="real")

    outcome = project_execution_evidence_outcome(
        _execution_with_ce_evidence(binding, plan, terminal)
    )

    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any("plan" in reason for reason in outcome.reasons)


def test_p2_66_rejects_clear_terminal_when_frozen_bypass_then_fades_to_go():
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.base_station_adapter_profile import (
        FREEZE_CONFIG_KEY,
        MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    )
    from app.services.channel_emulator_execution_plan import (
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    terminal = _terminal_evidence(binding, plan, execution_mode="real")
    terminal["safe_idle_action"] = "clear_passthrough_mode"
    terminal["digest"] = canonical_payload_digest(
        {key: value for key, value in terminal.items() if key != "digest"}
    )
    execution = _execution_with_ce_evidence(binding, plan, terminal)
    mimo = MIMOOTAConfiguration.model_validate(
        {
            "engine_mode": "keysight_gcm",
            "emulation_file": "scenario.smu",
            "f64_bypass_mode": 2,
            "f64_fade_after_attach": True,
        }
    ).model_dump(mode="json")
    payload = {MIMO_OTA_CONFIGURATION_FREEZE_KEY: mimo}
    execution.config[FREEZE_CONFIG_KEY] = {
        **payload,
        "digest": canonical_payload_digest(payload),
    }
    execution.config[CE_LOAD_REQUEST_FREEZE_CONFIG_KEY] = (
        _load_request_for_evidence(mimo, plan)
    )

    outcome = project_execution_evidence_outcome(execution)

    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False
    assert any("safe idle action" in reason for reason in outcome.reasons)


def test_p2_66_keeps_complete_diagnostic_unbound_mock_session_diagnostic():
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    mock = MockChannelEmulator("frozen-mock", {})
    resolved = {
        "schema_version": 1,
        "status": "diagnostic_unbound",
        "category_id": "ce-category",
        "instrument_model_id": None,
        "instrument_connection_id": None,
        "lab_profile_id": "lab-1",
        "manifest": None,
        "expected_driver_module": None,
        "expected_driver_name": None,
        "expected_transport": None,
        "binding_digest": BINDING_DIGEST,
    }
    identity = {
        "schema_version": 1,
        "category_id": "ce-category",
        "instrument_model_id": None,
        "instrument_connection_id": None,
        "lab_profile_id": "lab-1",
        "execution_mode": "simulated",
        "expected_driver_module": None,
        "expected_driver_name": None,
        "expected_driver_connection": None,
        "binding_digest": BINDING_DIGEST,
        "resolved_binding": resolved,
    }
    binding = {**identity, "digest": canonical_payload_digest(identity)}
    plan = _frozen_plan(mock, source="fallback_mock")
    terminal = _terminal_evidence(binding, plan, execution_mode="simulated")

    outcome = project_execution_evidence_outcome(
        _execution_with_ce_evidence(binding, plan, terminal)
    )

    assert outcome.compatibility_classification == "diagnostic"
    assert outcome.completion_semantic == "diagnostic_completed"
    assert outcome.formal_eligible is False


def test_p2_66_terminal_projection_blocks_failed_or_tampered_ce_session():
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    failed = _terminal_evidence(
        binding, plan, execution_mode="real", terminal_state="failed"
    )
    execution = _execution_with_ce_evidence(binding, plan, failed)
    outcome = project_execution_evidence_outcome(execution)
    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False

    failed["safe_idle_confirmed"] = True
    outcome = project_execution_evidence_outcome(execution)
    assert outcome.compatibility_classification == "invalid"
    assert any("digest" in reason for reason in outcome.reasons)


def test_p2_66_successful_retry_supersedes_failed_same_operation_scope():
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    failed = _terminal_evidence(
        binding,
        plan,
        execution_mode="real",
        terminal_state="failed",
        session_id="failed-session",
        operation_scope="commissioning-phase:execution-1:measure",
    )
    completed = _terminal_evidence(
        binding,
        plan,
        execution_mode="real",
        session_id="successful-retry",
        operation_scope="commissioning-phase:execution-1:measure",
    )
    execution = _execution_with_ce_evidence(binding, plan, completed)
    execution.config[CE_TERMINAL_EVIDENCE_CONFIG_KEY] = [failed, completed]

    assert _channel_emulator_terminal_projection(
        execution.config,
        execution_id=execution.id,
        pipeline_status=execution.status,
    ) == (None, None)


def test_p2_66_rejects_orphan_channel_emulator_load_request_freeze():
    from app.services.channel_emulator_execution_plan import (
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY,
    )
    from app.services.execution_evidence_outcome import (
        _channel_emulator_terminal_projection,
    )

    assert _channel_emulator_terminal_projection(
        {CE_LOAD_REQUEST_FREEZE_CONFIG_KEY: {}},
        execution_id="orphan-load-request",
        pipeline_status="completed",
    ) == (
        "invalid",
        "channelEmulator binding / execution plan freeze is incomplete",
    )


@pytest.mark.parametrize("driver_source", ["hal", "fallback_mock"])
def test_p2_66_terminal_projection_keeps_simulated_ce_diagnostic(driver_source):
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = MockChannelEmulator("frozen-mock", {})
    binding = _frozen_binding_for_driver(driver, execution_mode="simulated")
    plan = _frozen_plan(driver, source=driver_source)
    execution = _execution_with_ce_evidence(
        binding,
        plan,
        _terminal_evidence(binding, plan, execution_mode="simulated"),
    )
    outcome = project_execution_evidence_outcome(execution)
    assert outcome.compatibility_classification == "diagnostic"
    assert outcome.formal_eligible is False


def test_report_completed_projection_requires_channel_emulator_terminal_evidence():
    """REPORT must evaluate CE evidence against the lifecycle it will publish."""

    from datetime import datetime, timezone

    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.mimo_ota.executors.report import (
        ReportLifecycleProjection,
        _build_mimo_ota_content_data,
    )

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    execution = _execution_with_ce_evidence(
        binding,
        plan,
        _terminal_evidence(binding, plan, execution_mode="real"),
    )
    del execution.config[CE_TERMINAL_EVIDENCE_CONFIG_KEY]
    execution.status = "running"
    execution.measurements = {
        "phases": {"measure": {}, "analysis": {"verdict": "PASS"}}
    }
    execution.validation_pass = True
    execution.started_at = datetime(2026, 9, 2, 0, 0, 0)
    execution.completed_at = None
    execution.duration_sec = None
    completed_at = datetime(2026, 9, 2, 0, 1, 0)

    content = _build_mimo_ota_content_data(
        execution,
        datetime(2026, 9, 2, 0, 1, 1, tzinfo=timezone.utc),
        "missing-ce-terminal",
        lifecycle_projection=ReportLifecycleProjection(
            status="completed",
            completed_at=completed_at,
            duration_sec=60.0,
        ),
    )

    outcome = content["execution_evidence_outcome"]
    assert execution.status == "running"
    assert outcome["pipeline_status"] == "completed"
    assert outcome["compatibility_classification"] == "invalid"
    assert outcome["formal_eligible"] is False
    assert any("terminal evidence" in reason for reason in outcome["reasons"])
    assert content["overall_result"] == "undetermined"


@pytest.mark.asyncio
async def test_measure_cleanup_does_not_repeat_scope_owned_safe_idle():
    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    driver = _RealCe()
    result = await cleanup_chamber_instruments(
        SimpleNamespace(drivers={"channelEmulator": driver}),
        "execution-1",
        channel_emulator_safe_idle_owned=True,
    )

    assert driver.events == []
    assert result.warnings == []
