"""P2-59 ③：execution-frozen 的 channelEmulator 单一会话。"""

from __future__ import annotations

import asyncio
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
        assert "digest" in str(exc)
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
        "resolved_binding": {"binding_digest": BINDING_DIGEST},
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

    lease = InstrumentTestLease(lambda: hal)
    monkeypatch.setattr(module, "instrument_test_lease", lease.hold)
    return lease


@pytest.mark.asyncio
async def test_scope_validates_then_orders_operation_safe_idle_and_release(monkeypatch):
    from app.services import channel_emulator_execution_session as module
    from app.services.mimo_ota.cleanup import cleanup_chamber_instruments

    driver = _RealCe()
    hal = SimpleNamespace(drivers={"channelEmulator": driver}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)
    execution = SimpleNamespace(id="execution-1", config={})

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
            SimpleNamespace(id="execution-1", config={}),
            purpose="formal-case:execution-1",
            binding=frozen_binding,
            plan=frozen_plan,
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            raise AssertionError("identity drift must reject before yield")

    assert driver.events == []


@pytest.mark.asyncio
async def test_scope_installs_mock_only_for_explicit_simulated_freeze(monkeypatch):
    from app.services import channel_emulator_execution_session as module

    frozen_mock = MockChannelEmulator("frozen-mock", {})
    hal = SimpleNamespace(drivers={}, clear_metrics_cache=None)
    _install_real_lease(monkeypatch, module, hal)

    async with module.channel_emulator_execution_scope(
        None,
        SimpleNamespace(id="execution-1", config={}),
        purpose="diagnostic:execution-1",
        binding=_frozen_binding_for_driver(frozen_mock, execution_mode="simulated"),
        plan=_frozen_plan(frozen_mock),
        hal=hal,
        validate_before_remote=lambda _hal: None,
    ):
        assert isinstance(hal.drivers["channelEmulator"], MockChannelEmulator)

    assert "channelEmulator" not in hal.drivers


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
            SimpleNamespace(id="execution-1", config={}),
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
            SimpleNamespace(id="execution-1", config={}),
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
            SimpleNamespace(id="execution-1", config={}),
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
            SimpleNamespace(id="execution-1", config={}),
            purpose="formal-case:execution-1",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=_frozen_plan(driver),
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            driver.events.append("operation")

    assert driver.events == ["acquire", "operation", "safe-idle", "release"]


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
            SimpleNamespace(id="execution-1", config={}),
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
            SimpleNamespace(id="execution-1", config={}),
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
        SimpleNamespace(id="execution-1", config={}),
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
        SimpleNamespace(id="execution-1", config={}),
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
) -> dict:
    payload = {
        "schema_version": 1,
        "session_id": "session-1",
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
        "instrument_id": "ce-runtime" if execution_mode == "real" else None,
        "remote_acquired_confirmed": True if execution_mode == "real" else None,
        "safe_idle_confirmed": terminal_state == "completed",
        "transport_released_confirmed": True if execution_mode == "real" else None,
        "operation_succeeded": terminal_state == "completed",
        "terminal_state": terminal_state,
        "error_type": None if terminal_state == "completed" else "RuntimeError",
        "safe_idle_error_type": None,
    }
    return {**payload, "digest": canonical_payload_digest(payload)}


def test_p2_66_terminal_projection_blocks_failed_or_tampered_ce_session():
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.channel_emulator_binding import CE_FREEZE_CONFIG_KEY
    from app.services.channel_emulator_execution_plan import CE_PLAN_FREEZE_CONFIG_KEY
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = _RealCe()
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    failed = _terminal_evidence(
        binding, plan, execution_mode="real", terminal_state="failed"
    )
    execution = SimpleNamespace(
        id="execution-1",
        status="completed",
        config={
            CE_FREEZE_CONFIG_KEY: binding,
            CE_PLAN_FREEZE_CONFIG_KEY: plan,
            CE_TERMINAL_EVIDENCE_CONFIG_KEY: [failed],
        },
    )
    outcome = project_execution_evidence_outcome(execution)
    assert outcome.compatibility_classification == "invalid"
    assert outcome.formal_eligible is False

    failed["safe_idle_confirmed"] = True
    outcome = project_execution_evidence_outcome(execution)
    assert outcome.compatibility_classification == "invalid"
    assert any("digest" in reason for reason in outcome.reasons)


def test_p2_66_terminal_projection_keeps_simulated_ce_diagnostic():
    from app.services.channel_emulator_execution_session import (
        CE_TERMINAL_EVIDENCE_CONFIG_KEY,
    )
    from app.services.channel_emulator_binding import CE_FREEZE_CONFIG_KEY
    from app.services.channel_emulator_execution_plan import CE_PLAN_FREEZE_CONFIG_KEY
    from app.services.execution_evidence_outcome import project_execution_evidence_outcome

    driver = MockChannelEmulator("frozen-mock", {})
    binding = _frozen_binding_for_driver(driver, execution_mode="simulated")
    plan = _frozen_plan(driver)
    execution = SimpleNamespace(
        id="execution-1",
        status="completed",
        config={
            CE_FREEZE_CONFIG_KEY: binding,
            CE_PLAN_FREEZE_CONFIG_KEY: plan,
            CE_TERMINAL_EVIDENCE_CONFIG_KEY: [
                _terminal_evidence(binding, plan, execution_mode="simulated")
            ],
        },
    )
    outcome = project_execution_evidence_outcome(execution)
    assert outcome.compatibility_classification == "diagnostic"
    assert outcome.formal_eligible is False


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
