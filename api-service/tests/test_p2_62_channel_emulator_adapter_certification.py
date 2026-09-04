"""P2-62：第三种 Channel Emulator adapter 的参数化接入认证。"""

import asyncio

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.core.logging_config import current_execution_id
from app.hal.channel_emulator import ChannelEmulatorDriver
from app.hal.channel_emulator_execution_plan import (
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import CHANNEL_EMULATOR_OPERATIONS
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services.channel_emulator_binding import resolve_channel_emulator_binding
from app.services.channel_emulator_certification import (
    _has_certifiable_channel_emulator_frequency_evidence,
    derive_channel_emulator_site_certification_from_execution,
)
from app.services.channel_emulator_model_preset import (
    require_saved_active_channel_emulator_preset,
    save_channel_emulator_model_preset,
)
from app.services.channel_emulator_operation_receipt import (
    CE_OPERATION_RECEIPTS_CONFIG_KEY,
    ChannelEmulatorOperationRecorderOwner,
    channel_emulator_operation_recorder_scope,
    record_channel_emulator_operation,
)
from tests.channel_emulator_certification_kit import (
    CERTFAKE_CE_MANIFEST,
    CERTFAKE_CE_PROFILE,
    CertFakeChannelTransport,
    CertFakeChannelEmulatorDriver,
    CertFakeChannelEmulatorProfile,
    temporary_certfake_channel_emulator_registration,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_certfake_ce_five_piece_registration_contract_is_complete():
    parsed = CertFakeChannelEmulatorProfile.model_validate(CERTFAKE_CE_PROFILE)

    assert parsed.adapter == "certfake_ce"
    assert CERTFAKE_CE_MANIFEST.adapter_id == "certfake_ce"
    assert {item.operation for item in CERTFAKE_CE_MANIFEST.operations} == set(
        CHANNEL_EMULATOR_OPERATIONS
    )
    assert all(
        item.source_reference and "test fixture" in item.source_reference
        for item in CERTFAKE_CE_MANIFEST.operations
    )
    assert CertFakeChannelEmulatorDriver.adapter_manifest is CERTFAKE_CE_MANIFEST


def test_certfake_ce_manifest_and_driver_cover_the_same_operations():
    declared = {
        item.operation
        for item in CERTFAKE_CE_MANIFEST.operations
        if item.support == "implemented"
    }
    implemented = {
        operation
        for operation in CHANNEL_EMULATOR_OPERATIONS
        if getattr(CertFakeChannelEmulatorDriver, operation)
        is not getattr(ChannelEmulatorDriver, operation)
    }

    assert implemented == declared


def test_certfake_ce_never_leaks_into_production_code():
    app_root = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        path.relative_to(app_root).as_posix()
        for path in app_root.rglob("*.py")
        if "certfake_ce" in path.read_text(encoding="utf-8").casefold()
    ]

    assert offenders == []


def _configured_certfake(db):
    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        driver_mode="real",
    )
    db.add(category)
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="Test Fixture",
        model="Certification Fixture CE",
        capabilities={},
    )
    db.add(model)
    db.flush()
    connection = InstrumentConnection(category_id=category.id, created_by="test")
    db.add(connection)
    save_channel_emulator_model_preset(
        category=category,
        current_model=None,
        target_model=model,
        connection=connection,
        endpoint="192.0.2.62",
        controller="fixture",
        notes="P2-62",
        connection_params={"profile": CERTFAKE_CE_PROFILE},
        parsed_controller_ip="192.0.2.62",
        parsed_port=None,
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": "192.0.2.62",
                "driver_mode": "real",
                "role": "primary_channel_emulator",
            }
        ],
    )
    db.add(lab)
    db.commit()
    return category, model, connection, lab


def test_certfake_ce_saved_preset_binding_and_plan_need_no_production_registration(db):
    _, model, connection, lab = _configured_certfake(db)
    saved = require_saved_active_channel_emulator_preset(
        model=model, connection=connection
    )
    driver = CertFakeChannelEmulatorDriver(
        "ce-certfake", {"ip_address": "192.0.2.62"}
    )

    with temporary_certfake_channel_emulator_registration():
        binding = resolve_channel_emulator_binding(
            db,
            SimpleNamespace(drivers={"channelEmulator": driver}),
            lab,
        )
    plan = resolve_channel_emulator_execution_plan(
        manifest=CERTFAKE_CE_MANIFEST,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest=binding.binding_digest,
    )

    assert saved.endpoint == "192.0.2.62"
    assert binding.status == "configured"
    assert binding.manifest.adapter_id == "certfake_ce"
    assert plan.adapter_id == "certfake_ce"
    assert all(plan.planned(operation) for operation in CHANNEL_EMULATOR_OPERATIONS)


def test_certfake_ce_binding_and_saved_preset_fail_closed_on_drift(db):
    _, model, connection, lab = _configured_certfake(db)
    connection.endpoint = "192.0.2.99"

    with pytest.raises(ValueError, match="preset.*不一致"):
        require_saved_active_channel_emulator_preset(
            model=model, connection=connection
        )
    driver = CertFakeChannelEmulatorDriver(
        "ce-certfake", {"ip_address": "192.0.2.62"}
    )
    with temporary_certfake_channel_emulator_registration():
        with pytest.raises(ValueError, match="endpoint|连接"):
            resolve_channel_emulator_binding(
                db,
                SimpleNamespace(drivers={"channelEmulator": driver}),
                lab,
            )


class _LockedExecutionQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def one_or_none(self):
        return self.row


class _ReceiptDb:
    def __init__(self, row):
        self.row = row
        self.commits = 0

    def query(self, _model):
        return _LockedExecutionQuery(self.row)

    def commit(self):
        self.commits += 1


def _certfake_recorder(row, driver, *, execution_mode="real"):
    plan = resolve_channel_emulator_execution_plan(
        manifest=CERTFAKE_CE_MANIFEST,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest="b" * 64,
    )
    return ChannelEmulatorOperationRecorderOwner(
        db=_ReceiptDb(row),
        execution_pk=row.id,
        execution_id=str(row.id),
        session_id="session-certfake",
        operation_scope=f"certification:{row.id}",
        measurement_attempt_id="attempt-certfake",
        binding_digest="b" * 64,
        binding_freeze_digest="f" * 64,
        plan_digest=plan.digest,
        asset_digest="a" * 64,
        lease_id="lease-certfake",
        instrument_id=driver.instrument_id,
        adapter_id="certfake_ce",
        execution_mode=execution_mode,
        plan=plan,
        driver=driver,
    )


async def _record_certfake_operation(row, driver, *, operation, requested, invoke):
    owner = _certfake_recorder(row, driver)
    token = current_execution_id.set(str(row.id))
    try:
        with channel_emulator_operation_recorder_scope(owner):
            result = await record_channel_emulator_operation(
                phase="configure",
                operation=operation,
                requested=requested,
                invoke=invoke,
            )
    finally:
        current_execution_id.reset(token)
    return result, row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][-1]


@pytest.mark.asyncio
async def test_certfake_ce_receipt_separates_complete_and_partial_readback():
    complete = CertFakeChannelEmulatorDriver("ce-certfake", {})
    row = TestExecution(id=uuid4(), config={})
    result, receipt = await _record_certfake_operation(
        row,
        complete,
        operation="set_path_loss",
        requested={"path_loss_db": 42.0, "distance_m": 3.0},
        invoke=lambda: complete.set_path_loss(42.0, 3.0),
    )

    assert result is True
    assert receipt["terminal_state"] == "completed"
    assert {field["status"] for field in receipt["fields"]} == {"confirmed"}
    assert len(receipt["error_queue_exchange_ids"]) == 1

    partial_transport = CertFakeChannelTransport(partial_fields={"distance_m"})
    partial = CertFakeChannelEmulatorDriver(
        "ce-certfake", {"transport": partial_transport}
    )
    row = TestExecution(id=uuid4(), config={})
    result, receipt = await _record_certfake_operation(
        row,
        partial,
        operation="set_path_loss",
        requested={"path_loss_db": 42.0, "distance_m": 3.0},
        invoke=lambda: partial.set_path_loss(42.0, 3.0),
    )

    fields = {field["field"]: field for field in receipt["fields"]}
    assert result is True
    assert fields["path_loss_db"]["status"] == "confirmed"
    assert fields["distance_m"]["status"] == "unknown"
    assert fields["distance_m"]["applied_present"] is False


@pytest.mark.asyncio
async def test_certfake_ce_error_queue_rejection_is_not_a_success_receipt():
    transport = CertFakeChannelTransport(rejected_operations={"set_output_gain"})
    driver = CertFakeChannelEmulatorDriver("ce-certfake", {"transport": transport})
    row = TestExecution(id=uuid4(), config={})
    result, receipt = await _record_certfake_operation(
        row,
        driver,
        operation="set_output_gain",
        requested={"output_num": 1, "gain_db": -3.0},
        invoke=lambda: driver.set_output_gain(1, -3.0),
    )

    assert result is False
    assert receipt["terminal_state"] == "rejected"
    assert receipt["operation_succeeded"] is False
    assert {field["status"] for field in receipt["fields"]} == {"unknown"}
    assert len(receipt["error_queue_exchange_ids"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "requested", "invoke_name", "invoke_args"),
    [
        (
            "load_channel",
            {"model_name": "fixture-native-model"},
            "load_channel",
            ("native_model", "fixture-native-model", "UMa", {}),
        ),
        ("start_emulation", {"state": "running"}, "start_emulation", ()),
        (
            "set_output_level_dbm",
            {"level_dbm": -20.0, "output_ports": [1, 2]},
            "set_output_level_dbm",
            (-20.0, [1, 2]),
        ),
        ("stop_emulation", {"state": "idle"}, "stop_emulation", ()),
    ],
)
async def test_certfake_ce_asset_run_adjust_stop_use_the_common_receipt_pipeline(
    operation, requested, invoke_name, invoke_args
):
    driver = CertFakeChannelEmulatorDriver("ce-certfake", {})
    row = TestExecution(id=uuid4(), config={})
    invoke = getattr(driver, invoke_name)

    result, receipt = await _record_certfake_operation(
        row,
        driver,
        operation=operation,
        requested=requested,
        invoke=lambda: invoke(*invoke_args),
    )

    assert result is True
    assert receipt["adapter_id"] == "certfake_ce"
    assert receipt["execution_id"] == str(row.id)
    assert receipt["terminal_state"] == "completed"
    assert receipt["simulated"] is False


@pytest.mark.asyncio
async def test_certfake_ce_timeout_persists_cancelled_receipt():
    transport = CertFakeChannelTransport(delay_s=1.0)
    driver = CertFakeChannelEmulatorDriver("ce-certfake", {"transport": transport})
    row = TestExecution(id=uuid4(), config={})

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            _record_certfake_operation(
                row,
                driver,
                operation="start_emulation",
                requested={"state": "running"},
                invoke=driver.start_emulation,
            ),
            timeout=0.01,
        )

    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][-1]
    assert receipt["terminal_state"] == "cancelled"
    assert receipt["operation_succeeded"] is None
    assert receipt["error_type"] == "CancelledError"


@pytest.mark.asyncio
async def test_certfake_ce_explicit_cancellation_persists_cancelled_receipt():
    transport = CertFakeChannelTransport(delay_s=1.0)
    driver = CertFakeChannelEmulatorDriver("ce-certfake", {"transport": transport})
    row = TestExecution(id=uuid4(), config={})
    task = asyncio.create_task(
        _record_certfake_operation(
            row,
            driver,
            operation="start_emulation",
            requested={"state": "running"},
            invoke=driver.start_emulation,
        )
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][-1]
    assert receipt["terminal_state"] == "cancelled"
    assert receipt["operation_succeeded"] is None


@pytest.mark.asyncio
async def test_certfake_ce_simulated_transport_never_confirms_fields():
    transport = CertFakeChannelTransport(simulated=True)
    driver = CertFakeChannelEmulatorDriver("ce-certfake", {"transport": transport})
    row = TestExecution(id=uuid4(), config={})
    owner = _certfake_recorder(row, driver, execution_mode="simulated")
    token = current_execution_id.set(str(row.id))
    try:
        with channel_emulator_operation_recorder_scope(owner):
            assert await record_channel_emulator_operation(
                phase="configure",
                operation="set_path_loss",
                requested={"path_loss_db": 42.0},
                invoke=lambda: driver.set_path_loss(42.0),
            ) is True
    finally:
        current_execution_id.reset(token)

    receipt = row.config[CE_OPERATION_RECEIPTS_CONFIG_KEY][-1]
    assert receipt["simulated"] is True
    assert {field["status"] for field in receipt["fields"]} == {"unknown"}
    assert {field["provenance"] for field in receipt["fields"]} == {"simulated"}


@pytest.mark.asyncio
async def test_certfake_ce_session_always_safe_idles_before_transport_release(
    monkeypatch,
):
    from app.services import channel_emulator_execution_session as session_module
    from tests.test_p2_59_3_channel_emulator_session import (
        _frozen_binding_for_driver,
        _frozen_plan,
        _install_real_lease,
        _scope_execution,
    )

    driver = CertFakeChannelEmulatorDriver(
        "ce-certfake",
        {"ip_address": "192.0.2.59", "port": 3334},
    )
    hal = SimpleNamespace(
        drivers={"channelEmulator": driver}, clear_metrics_cache=None
    )
    _install_real_lease(monkeypatch, session_module, hal)
    plan = _frozen_plan(driver)
    execution = _scope_execution(plan)

    async with session_module.channel_emulator_execution_scope(
        None,
        execution,
        purpose="p2-62-certification",
        binding=_frozen_binding_for_driver(driver, execution_mode="real"),
        plan=plan,
        hal=hal,
        validate_before_remote=lambda _hal: None,
    ) as outcome:
        driver.events.append("operation")
        driver._running = True

    assert driver.events == ["acquire", "operation", "safe-idle", "release"]
    assert driver._running is False
    assert outcome.channel_emulator_remote_acquired_confirmed is True
    assert outcome.channel_emulator_transport_released_confirmed is True


@pytest.mark.asyncio
async def test_certfake_ce_safe_idle_rejection_fails_loud_and_still_releases(
    monkeypatch,
):
    from app.services import channel_emulator_execution_session as session_module
    from tests.test_p2_59_3_channel_emulator_session import (
        _frozen_binding_for_driver,
        _frozen_plan,
        _install_real_lease,
        _scope_execution,
    )

    driver = CertFakeChannelEmulatorDriver(
        "ce-certfake", {"ip_address": "192.0.2.59", "port": 3334}
    )

    async def reject_safe_idle():
        driver.events.append("safe-idle")
        return False

    driver.stop_emulation = reject_safe_idle
    hal = SimpleNamespace(
        drivers={"channelEmulator": driver}, clear_metrics_cache=None
    )
    _install_real_lease(monkeypatch, session_module, hal)
    plan = _frozen_plan(driver)

    with pytest.raises(
        session_module.ChannelEmulatorExecutionSessionError, match="safe idle"
    ):
        async with session_module.channel_emulator_execution_scope(
            None,
            _scope_execution(plan),
            purpose="p2-62-safe-idle-rejection",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=plan,
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ):
            driver.events.append("operation")

    assert driver.events == ["acquire", "operation", "safe-idle", "release"]


@pytest.mark.asyncio
async def test_certfake_ce_release_rejection_is_never_reported_as_success(monkeypatch):
    from app.services import channel_emulator_execution_session as session_module
    from app.services.instrument_test_lease import InstrumentTestLeaseReleaseError
    from tests.test_p2_59_3_channel_emulator_session import (
        _frozen_binding_for_driver,
        _frozen_plan,
        _install_real_lease,
        _scope_execution,
    )

    driver = CertFakeChannelEmulatorDriver(
        "ce-certfake", {"ip_address": "192.0.2.59", "port": 3334}
    )

    async def reject_release():
        driver.events.append("release")
        return False

    driver.release_to_local_control = reject_release
    hal = SimpleNamespace(
        drivers={"channelEmulator": driver}, clear_metrics_cache=None
    )
    _install_real_lease(monkeypatch, session_module, hal)
    plan = _frozen_plan(driver)
    outcome = None

    with pytest.raises(InstrumentTestLeaseReleaseError):
        async with session_module.channel_emulator_execution_scope(
            None,
            _scope_execution(plan),
            purpose="p2-62-release-rejection",
            binding=_frozen_binding_for_driver(driver, execution_mode="real"),
            plan=plan,
            hal=hal,
            validate_before_remote=lambda _hal: None,
        ) as outcome:
            driver.events.append("operation")

    assert outcome is not None
    assert outcome.channel_emulator_transport_released_confirmed is False
    assert driver.events == ["acquire", "operation", "safe-idle", "release"]


def _derive_with_current_frozen_binding(execution):
    binding = execution.config["channel_emulator_binding_freeze"]
    plan = execution.config["channel_emulator_execution_plan_freeze"]
    return derive_channel_emulator_site_certification_from_execution(
        execution,
        connection_id=binding["instrument_connection_id"],
        current_binding_digest=binding["binding_digest"],
        current_adapter_id=plan["adapter_id"],
        certified_by="p2-62-certifier",
        reason="第三 adapter 共同认证证据通过",
    )


def test_site_certification_consumes_vendor_neutral_frequency_evidence():
    from tests.test_p2_61_channel_emulator_certification import (
        _certification_execution_fixture,
    )

    execution = _certification_execution_fixture()
    frequency = execution.measurements["phases"]["measure"][
        "frequency_consistency"
    ]
    frequency.pop("f64_center_readback_mhz")
    frequency.pop("f64_bandwidth_source")
    frequency["per_instrument"].pop("F64")
    frequency["channel_emulator_evidence"] = {
        "schema_version": 1,
        "adapter_id": "propsim_f64",
        "instrument_id": "ce-runtime",
        "center_readback_mhz": 3500.01,
        "bandwidth_source": "channel_asset_or_scd_declared",
        "fully_verified": True,
    }

    certification = _derive_with_current_frozen_binding(execution)

    assert certification.required_proofs.frequency is True


def test_site_certification_rejects_frequency_evidence_from_another_adapter():
    from tests.test_p2_61_channel_emulator_certification import (
        _certification_execution_fixture,
    )

    execution = _certification_execution_fixture()
    frequency = execution.measurements["phases"]["measure"][
        "frequency_consistency"
    ]
    frequency["channel_emulator_evidence"] = {
        "schema_version": 1,
        "adapter_id": "certfake_ce",
        "instrument_id": "ce-runtime",
        "center_readback_mhz": 3500.01,
        "bandwidth_source": "channel_asset_or_scd_declared",
        "fully_verified": True,
    }

    with pytest.raises(ValueError, match="frequency"):
        _derive_with_current_frozen_binding(execution)


def test_site_certification_does_not_treat_explicit_null_evidence_as_legacy():
    from tests.test_p2_61_channel_emulator_certification import (
        _certification_execution_fixture,
    )

    execution = _certification_execution_fixture()
    frequency = execution.measurements["phases"]["measure"][
        "frequency_consistency"
    ]
    frequency["channel_emulator_evidence"] = None

    with pytest.raises(ValueError, match="frequency"):
        _derive_with_current_frozen_binding(execution)


def test_certfake_frequency_evidence_is_adapter_and_instrument_bound():
    frequency = {
        "fully_verified": True,
        "channel_emulator_evidence": {
            "schema_version": 1,
            "adapter_id": "certfake_ce",
            "instrument_id": "ce-certfake",
            "center_readback_mhz": 3500.0,
            "bandwidth_source": "channel_asset_or_scd_declared",
            "fully_verified": True,
        },
    }

    assert _has_certifiable_channel_emulator_frequency_evidence(
        frequency,
        current_adapter_id="certfake_ce",
        instrument_id="ce-certfake",
    )
    assert not _has_certifiable_channel_emulator_frequency_evidence(
        frequency,
        current_adapter_id="certfake_ce",
        instrument_id="another-instrument",
    )
    assert not _has_certifiable_channel_emulator_frequency_evidence(
        frequency,
        current_adapter_id="propsim_f64",
        instrument_id="ce-certfake",
    )


def test_non_f64_frequency_gap_diagnostic_uses_vendor_neutral_label():
    from app.services.mimo_ota.executors.measure import (
        _describe_f64_frequency_verification_gap,
    )

    message = _describe_f64_frequency_verification_gap(
        f64_center_mhz=None,
        f64_bandwidth_source="channel_asset_or_scd_declared",
        declared_bandwidth_mhz=100.0,
        instrument_label="ChannelEmulator",
    )

    assert "ChannelEmulator 中心频率未回读" in message
    assert "F64" not in message
