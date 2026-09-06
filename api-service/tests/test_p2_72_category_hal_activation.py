"""P2-72：仪器配置保存后按类别激活 HAL。"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.instrument import InstrumentCategory, InstrumentModel
from app.services import instrument_hal_service as hal_mod
from app.hal.base import InstrumentStatus
from app.services.instrument_hal_service import (
    DriverMode,
    HALCategoryActivation,
    HALCategoryActivationError,
    InstrumentHALService,
    activate_hal_category_atomic,
)
from app.services.instrument_test_lease import InstrumentTestLease
from app.services.readiness import (
    DriverReadinessRow,
    ReadinessReport,
    build_calibration_readiness,
    build_dut_attach_readiness,
    build_lab_profile_readiness,
    build_subnet_reachability,
)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


def _override_get_db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    Base.metadata.create_all(bind=engine)
    import app.db.database as dbmod

    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


class _RecordingDriver:
    connected_instrument_ids: list[str] = []

    def __init__(self, instrument_id, config):
        self.instrument_id = instrument_id
        self.config = config
        self._status = InstrumentStatus.DISCONNECTED
        self.disconnect_calls = 0
        self.disconnect_result = True

    async def connect(self):
        type(self).connected_instrument_ids.append(self.instrument_id)
        self._status = InstrumentStatus.READY
        return True

    async def disconnect(self):
        self.disconnect_calls += 1
        if self.disconnect_result is True:
            self._status = InstrumentStatus.DISCONNECTED
        return self.disconnect_result

    def get_status(self):
        return self._status

    @property
    def status(self):
        return self._status

    def readiness_metadata(self):
        return {}


class _SafelyParkedDriver(_RecordingDriver):
    def __init__(self, instrument_id, config):
        super().__init__(instrument_id, config)
        self._status = InstrumentStatus.DISCONNECTED
        self.local_control_reserved = True
        self.local_release_failed = False


class _FailingConnectDriver(_RecordingDriver):
    async def connect(self):
        type(self).connected_instrument_ids.append(self.instrument_id)
        self._status = InstrumentStatus.ERROR
        self._last_error = "connect failed by fixture"
        return False


class _CancellableConnectDriver(_RecordingDriver):
    instances: list["_CancellableConnectDriver"] = []
    connect_started: asyncio.Event
    connect_release: asyncio.Event

    def __init__(self, instrument_id, config):
        super().__init__(instrument_id, config)
        self.session_open = False
        type(self).instances.append(self)

    async def connect(self):
        self.session_open = True
        type(self).connect_started.set()
        await type(self).connect_release.wait()
        self._status = InstrumentStatus.READY
        return True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.session_open = False
        self._status = InstrumentStatus.DISCONNECTED
        return True


class _CancellableDisconnectDriver(_RecordingDriver):
    def __init__(self, instrument_id, config):
        super().__init__(instrument_id, config)
        self.disconnect_started = asyncio.Event()
        self.disconnect_release = asyncio.Event()

    async def disconnect(self):
        self.disconnect_calls += 1
        self.disconnect_started.set()
        await self.disconnect_release.wait()
        self._status = InstrumentStatus.DISCONNECTED
        return True


class _CancellableTopologyDriver(_RecordingDriver):
    instances: list["_CancellableTopologyDriver"] = []
    topology_started: asyncio.Event
    topology_release: asyncio.Event
    _default_topology_profile_id = "p2_72_cancel_fixture"

    def __init__(self, instrument_id, config):
        super().__init__(instrument_id, config)
        type(self).instances.append(self)

    async def apply_topology_profile(self, _profile):
        type(self).topology_started.set()
        await type(self).topology_release.wait()
        return {"applied": True}


def _seed_category(db, category_key: str, *, display_order: int) -> InstrumentCategory:
    category = InstrumentCategory(
        id=uuid.uuid4(),
        category_key=category_key,
        category_name=category_key,
        is_active=True,
        display_order=display_order,
        driver_mode="real",
    )
    db.add(category)
    db.flush()
    model = InstrumentModel(
        id=uuid.uuid4(),
        category_id=category.id,
        vendor="TestVendor",
        model=f"{category_key}-MODEL",
        full_name=f"{category_key} test model",
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    db.commit()
    db.refresh(category)
    return category


def _readiness_with_rows(db, *category_keys: str) -> ReadinessReport:
    rows = [
        DriverReadinessRow(
            category=category_key,
            model=f"old-{category_key}",
            endpoint="",
            status="ok",
            detail="existing runtime",
        )
        for category_key in category_keys
    ]
    lab = build_lab_profile_readiness(db)
    return ReadinessReport(
        drivers=rows,
        lab_profile=lab,
        calibration=build_calibration_readiness(db, lab),
        dut_attach=build_dut_attach_readiness(),
        generated_at_iso="2026-09-06T00:00:00",
        subnets=build_subnet_reachability(rows),
    )


def test_initialize_from_db_can_target_one_category_without_touching_others(
    monkeypatch,
    db,
):
    """目标初始化只连接所选类别，并保留其他已加载驱动实例。"""
    _seed_category(db, "baseStation", display_order=1)
    _seed_category(db, "channelEmulator", display_order=2)
    _RecordingDriver.connected_instrument_ids = []
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {
            "baseStation": {"baseStation-MODEL": _RecordingDriver},
            "channelEmulator": {"channelEmulator-MODEL": _RecordingDriver},
        },
    )

    service = InstrumentHALService(mode=DriverMode.REAL)
    unrelated_driver = object()
    service.drivers["channelEmulator"] = unrelated_driver
    service.last_readiness_report = _readiness_with_rows(
        db,
        "channelEmulator",
        "positioner",
    )

    asyncio.run(service._initialize_from_db(only_category_key="baseStation"))

    assert len(_RecordingDriver.connected_instrument_ids) == 1
    assert _RecordingDriver.connected_instrument_ids[0].startswith("baseStation_")
    assert service.drivers["channelEmulator"] is unrelated_driver
    assert isinstance(service.drivers["baseStation"], _RecordingDriver)
    rows = {
        row.category: row
        for row in service.last_readiness_report.drivers
    }
    assert set(rows) == {"baseStation", "channelEmulator", "positioner"}
    assert rows["baseStation"].model == "TestVendor baseStation-MODEL"
    assert rows["channelEmulator"].model == "old-channelEmulator"
    assert rows["positioner"].model == "old-positioner"


def _install_global_service(monkeypatch, service: InstrumentHALService) -> None:
    from app.services import instrument_test_lease as lease_mod

    async def _park_only_target(_category_key: str) -> bool:
        return True

    monkeypatch.setattr(hal_mod, "_hal_service", service)
    monkeypatch.setattr(hal_mod, "_hal_lifecycle_lock", None)
    monkeypatch.setattr(lease_mod, "park_idle_instrument", _park_only_target)


def test_activation_replaces_only_target_driver(monkeypatch, db):
    _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _RecordingDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    old_base = _RecordingDriver("old-base", {"model": "OLD"})
    old_base._status = InstrumentStatus.READY
    original_f64 = object()
    service.drivers.update({
        "baseStation": old_base,
        "channelEmulator": original_f64,
    })
    _install_global_service(monkeypatch, service)

    result = asyncio.run(activate_hal_category_atomic("baseStation"))

    assert result.status == "activated"
    assert old_base.disconnect_calls == 1
    assert service.drivers["baseStation"] is not old_base
    assert service.drivers["channelEmulator"] is original_f64


def test_matching_connected_runtime_is_unchanged(monkeypatch, db):
    from app.services import instrument_test_lease as lease_mod

    category = _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _RecordingDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    resolved = service._resolve_category_runtime(db, category)
    assert resolved is not None
    loaded = _RecordingDriver(resolved.instrument_id, resolved.driver_config)
    loaded._status = InstrumentStatus.READY
    service.drivers["baseStation"] = loaded
    _install_global_service(monkeypatch, service)
    parked: list[str] = []

    async def _park_target(category_key: str) -> bool:
        parked.append(category_key)
        return True

    monkeypatch.setattr(lease_mod, "park_idle_instrument", _park_target)

    result = asyncio.run(activate_hal_category_atomic("baseStation"))

    assert result.status == "unchanged"
    assert loaded.disconnect_calls == 0
    assert service.drivers["baseStation"] is loaded
    assert parked == ["baseStation"]


def test_matching_safely_parked_runtime_is_unchanged(monkeypatch, db):
    category = _seed_category(db, "channelEmulator", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {
            "channelEmulator": {
                "channelEmulator-MODEL": _SafelyParkedDriver,
            },
        },
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    resolved = service._resolve_category_runtime(db, category)
    assert resolved is not None
    loaded = _SafelyParkedDriver(
        resolved.instrument_id,
        resolved.driver_config,
    )
    service.drivers["channelEmulator"] = loaded
    _install_global_service(monkeypatch, service)

    result = asyncio.run(activate_hal_category_atomic("channelEmulator"))

    assert result.status == "unchanged"
    assert loaded.disconnect_calls == 0
    assert service.drivers["channelEmulator"] is loaded


def test_failed_local_release_is_not_reused_as_safely_parked(monkeypatch, db):
    category = _seed_category(db, "channelEmulator", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {
            "channelEmulator": {
                "channelEmulator-MODEL": _SafelyParkedDriver,
            },
        },
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    resolved = service._resolve_category_runtime(db, category)
    assert resolved is not None
    loaded = _SafelyParkedDriver(
        resolved.instrument_id,
        resolved.driver_config,
    )
    loaded.local_release_failed = True
    service.drivers["channelEmulator"] = loaded
    _install_global_service(monkeypatch, service)

    result = asyncio.run(activate_hal_category_atomic("channelEmulator"))

    assert result.status == "activated"
    assert loaded.disconnect_calls == 1
    assert service.drivers["channelEmulator"] is not loaded


@pytest.mark.parametrize(
    ("loaded_status", "loaded_config"),
    [
        (InstrumentStatus.DISCONNECTED, "resolved"),
        (InstrumentStatus.READY, {"model": "stale-model"}),
    ],
)
def test_disconnected_or_stale_runtime_is_rebuilt(
    monkeypatch,
    db,
    loaded_status,
    loaded_config,
):
    category = _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _RecordingDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    resolved = service._resolve_category_runtime(db, category)
    assert resolved is not None
    config = (
        resolved.driver_config
        if loaded_config == "resolved"
        else loaded_config
    )
    loaded = _RecordingDriver(resolved.instrument_id, config)
    loaded._status = loaded_status
    service.drivers["baseStation"] = loaded
    _install_global_service(monkeypatch, service)

    result = asyncio.run(activate_hal_category_atomic("baseStation"))

    assert result.status == "activated"
    assert loaded.disconnect_calls == 1
    assert service.drivers["baseStation"] is not loaded


def test_failed_new_connect_removes_stale_target_but_keeps_others(monkeypatch, db):
    _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _FailingConnectDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    old_base = _RecordingDriver("old-base", {"model": "OLD"})
    old_base._status = InstrumentStatus.READY
    original_f64 = object()
    service.drivers.update({
        "baseStation": old_base,
        "channelEmulator": original_f64,
    })
    _install_global_service(monkeypatch, service)

    with pytest.raises(HALCategoryActivationError, match="connect failed"):
        asyncio.run(activate_hal_category_atomic("baseStation"))

    assert "baseStation" not in service.drivers
    assert service.drivers["channelEmulator"] is original_f64


def test_real_cmw_disconnect_refusal_keeps_old_object(monkeypatch, db):
    _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _RecordingDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    original_cmw = _RecordingDriver("old-cmw", {"model": "CMW500"})
    original_cmw.adapter_id = "cmw500"
    original_cmw.disconnect_result = False
    original_cmw._status = InstrumentStatus.READY
    service.drivers["baseStation"] = original_cmw
    _install_global_service(monkeypatch, service)

    with pytest.raises(HALCategoryActivationError, match="安全断开"):
        asyncio.run(activate_hal_category_atomic("baseStation"))

    assert service.drivers["baseStation"] is original_cmw


def test_non_cmw_disconnect_refusal_stops_replacement_and_removes_stale_object(
    monkeypatch,
    db,
):
    _seed_category(db, "channelEmulator", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {
            "channelEmulator": {
                "channelEmulator-MODEL": _RecordingDriver,
            },
        },
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    old_f64 = _RecordingDriver("old-f64", {"model": "OLD"})
    old_f64.disconnect_result = False
    old_f64._status = InstrumentStatus.READY
    untouched_base = object()
    service.drivers.update({
        "channelEmulator": old_f64,
        "baseStation": untouched_base,
    })
    service.last_readiness_report = _readiness_with_rows(
        db,
        "channelEmulator",
        "baseStation",
    )
    _install_global_service(monkeypatch, service)

    with pytest.raises(HALCategoryActivationError, match="断开未确认"):
        asyncio.run(activate_hal_category_atomic("channelEmulator"))

    assert old_f64.disconnect_calls == 1
    assert "channelEmulator" not in service.drivers
    assert service.drivers["baseStation"] is untouched_base
    rows = {
        row.category: row
        for row in service.last_readiness_report.drivers
    }
    assert rows["channelEmulator"].status == "fail"
    assert rows["baseStation"].status == "ok"


def test_cancel_during_disconnect_waits_for_terminal_cleanup_and_marks_not_ready(
    monkeypatch,
    db,
):
    category = _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _RecordingDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    resolved = service._resolve_category_runtime(db, category)
    assert resolved is not None
    old_base = _CancellableDisconnectDriver(
        resolved.instrument_id,
        {"model": "OLD"},
    )
    old_base._status = InstrumentStatus.READY
    service.drivers["baseStation"] = old_base
    service.last_readiness_report = _readiness_with_rows(db, "baseStation")
    _install_global_service(monkeypatch, service)

    async def _scenario():
        task = asyncio.create_task(activate_hal_category_atomic("baseStation"))
        await old_base.disconnect_started.wait()
        task.cancel()
        old_base.disconnect_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_scenario())

    assert old_base.disconnect_calls == 1
    assert "baseStation" not in service.drivers
    row = next(
        row for row in service.last_readiness_report.drivers
        if row.category == "baseStation"
    )
    assert row.status == "fail"


def test_cancel_during_connect_closes_orphan_session_and_marks_not_ready(
    monkeypatch,
    db,
):
    _seed_category(db, "baseStation", display_order=1)
    _CancellableConnectDriver.instances = []
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {
            "baseStation": {
                "baseStation-MODEL": _CancellableConnectDriver,
            },
        },
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    service.last_readiness_report = _readiness_with_rows(db, "baseStation")
    _install_global_service(monkeypatch, service)

    async def _scenario():
        _CancellableConnectDriver.connect_started = asyncio.Event()
        _CancellableConnectDriver.connect_release = asyncio.Event()
        task = asyncio.create_task(activate_hal_category_atomic("baseStation"))
        await _CancellableConnectDriver.connect_started.wait()
        task.cancel()
        _CancellableConnectDriver.connect_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_scenario())

    assert len(_CancellableConnectDriver.instances) == 1
    created = _CancellableConnectDriver.instances[0]
    assert created.disconnect_calls == 1
    assert created.session_open is False
    assert "baseStation" not in service.drivers
    row = next(
        row for row in service.last_readiness_report.drivers
        if row.category == "baseStation"
    )
    assert row.status == "fail"


def test_cancel_during_post_connect_topology_disconnects_published_runtime(
    monkeypatch,
    db,
):
    from app.services import topology_profile_service

    _seed_category(db, "baseStation", display_order=1)
    _CancellableTopologyDriver.instances = []
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {
            "baseStation": {
                "baseStation-MODEL": _CancellableTopologyDriver,
            },
        },
    )
    monkeypatch.setattr(
        topology_profile_service,
        "get_dataclass",
        lambda _db, _profile_id: object(),
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    untouched_f64 = object()
    service.drivers["channelEmulator"] = untouched_f64
    service.last_readiness_report = _readiness_with_rows(
        db,
        "baseStation",
        "channelEmulator",
    )
    _install_global_service(monkeypatch, service)

    async def _scenario():
        _CancellableTopologyDriver.topology_started = asyncio.Event()
        _CancellableTopologyDriver.topology_release = asyncio.Event()
        task = asyncio.create_task(activate_hal_category_atomic("baseStation"))
        await _CancellableTopologyDriver.topology_started.wait()
        task.cancel()
        _CancellableTopologyDriver.topology_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_scenario())

    assert len(_CancellableTopologyDriver.instances) == 1
    created = _CancellableTopologyDriver.instances[0]
    assert created.disconnect_calls == 1
    assert "baseStation" not in service.drivers
    assert service.drivers["channelEmulator"] is untouched_f64
    rows = {
        row.category: row
        for row in service.last_readiness_report.drivers
    }
    assert rows["baseStation"].status == "fail"
    assert rows["channelEmulator"].status == "ok"


def test_inactive_category_unloads_only_target(monkeypatch, db):
    category = _seed_category(db, "baseStation", display_order=1)
    category.is_active = False
    db.commit()
    service = InstrumentHALService(mode=DriverMode.REAL)
    old_base = _RecordingDriver("old-base", {"model": "OLD"})
    old_base._status = InstrumentStatus.READY
    original_f64 = object()
    service.drivers.update({
        "baseStation": old_base,
        "channelEmulator": original_f64,
    })
    service.last_readiness_report = _readiness_with_rows(
        db,
        "baseStation",
        "channelEmulator",
    )
    _install_global_service(monkeypatch, service)

    result = asyncio.run(activate_hal_category_atomic("baseStation"))

    assert result.status == "inactive"
    assert old_base.disconnect_calls == 1
    assert "baseStation" not in service.drivers
    assert service.drivers["channelEmulator"] is original_f64
    assert {
        row.category for row in service.last_readiness_report.drivers
    } == {"channelEmulator"}


def test_invalid_committed_configuration_removes_stale_target(monkeypatch, db):
    category = _seed_category(db, "baseStation", display_order=1)
    category.selected_model_id = None
    db.commit()
    service = InstrumentHALService(mode=DriverMode.REAL)
    old_base = _RecordingDriver("old-base", {"model": "OLD"})
    old_base._status = InstrumentStatus.READY
    original_f64 = object()
    service.drivers.update({
        "baseStation": old_base,
        "channelEmulator": original_f64,
    })
    service.last_readiness_report = _readiness_with_rows(
        db,
        "baseStation",
        "channelEmulator",
    )
    _install_global_service(monkeypatch, service)

    with pytest.raises(
        hal_mod.HALCategoryConfigurationError,
        match="no selected model",
    ):
        asyncio.run(activate_hal_category_atomic("baseStation"))

    assert old_base.disconnect_calls == 1
    assert "baseStation" not in service.drivers
    assert service.drivers["channelEmulator"] is original_f64
    rows = {
        row.category: row
        for row in service.last_readiness_report.drivers
    }
    assert rows["baseStation"].status == "skipped"
    assert rows["channelEmulator"].status == "ok"


def test_targeted_park_failure_is_reported_as_activation_failure(monkeypatch, db):
    from app.services import instrument_test_lease as lease_mod

    _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _RecordingDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    _install_global_service(monkeypatch, service)

    async def _park_fails(_category_key: str) -> bool:
        raise RuntimeError("safe idle failed")

    monkeypatch.setattr(lease_mod, "park_idle_instrument", _park_fails)

    with pytest.raises(HALCategoryActivationError, match="驻车失败"):
        asyncio.run(activate_hal_category_atomic("baseStation"))

    row = next(
        row for row in service.last_readiness_report.drivers
        if row.category == "baseStation"
    )
    assert row.status == "fail"


def test_targeted_park_false_is_not_reported_as_activation_success(monkeypatch, db):
    from app.services import instrument_test_lease as lease_mod

    _seed_category(db, "baseStation", display_order=1)
    monkeypatch.setattr(
        hal_mod,
        "_real_driver_registry",
        lambda: {"baseStation": {"baseStation-MODEL": _RecordingDriver}},
    )
    service = InstrumentHALService(mode=DriverMode.REAL)
    _install_global_service(monkeypatch, service)

    async def _park_unconfirmed(_category_key: str) -> bool:
        return False

    monkeypatch.setattr(
        lease_mod,
        "park_idle_instrument",
        _park_unconfirmed,
    )

    with pytest.raises(HALCategoryActivationError, match="驻车未确认"):
        asyncio.run(activate_hal_category_atomic("baseStation"))

    row = next(
        row for row in service.last_readiness_report.drivers
        if row.category == "baseStation"
    )
    assert row.status == "fail"


@pytest.mark.parametrize(
    ("category_key", "expected_flags"),
    [
        ("channelEmulator", (True, False)),
        ("baseStation", (False, True)),
    ],
)
def test_targeted_idle_park_controls_only_requested_instrument(
    monkeypatch,
    category_key,
    expected_flags,
):
    calls: list[tuple[bool, bool]] = []
    lease = InstrumentTestLease(lambda: object())

    async def _settle(_hal, _purpose, *, control_f64, control_uxm, outcome=None):
        calls.append((control_f64, control_uxm))

    monkeypatch.setattr(lease, "_settle_local_controls", _settle)

    assert asyncio.run(lease.park_idle_instrument(category_key)) is True
    assert calls == [expected_flags]


def test_targeted_idle_park_is_noop_for_uncontrolled_category(monkeypatch):
    lease = InstrumentTestLease(lambda: object())

    async def _forbidden(*args, **kwargs):
        pytest.fail("非 F64/BaseStation 类别不得触碰硬件控制会话")

    monkeypatch.setattr(lease, "_settle_local_controls", _forbidden)

    assert asyncio.run(lease.park_idle_instrument("positioner")) is True


def test_activation_endpoint_returns_runtime_identity():
    result = HALCategoryActivation(
        category_key="baseStation",
        status="activated",
        driver_class="RealUxmDriver",
        instrument_id="baseStation_12345678",
        simulated=False,
        message="已激活",
    )
    with patch(
        "app.services.instrument_hal_service.activate_hal_category_atomic",
        new=AsyncMock(return_value=result),
    ):
        response = client.post(
            "/api/v1/instruments/baseStation/hal/activate"
        )

    assert response.status_code == 200
    assert response.json() == {
        "category_key": "baseStation",
        "status": "activated",
        "driver_class": "RealUxmDriver",
        "instrument_id": "baseStation_12345678",
        "simulated": False,
        "message": "已激活",
    }


def test_activation_endpoint_refuses_blocker_without_force_hint():
    from app.services.hal_reload_policy import ReloadBlocker

    blocker = ReloadBlocker(
        kind="instrument_lease",
        id="manual-scpi",
        name="manual-scpi",
        status="running",
        detail="仪表正在使用",
    )
    with patch(
        "app.services.hal_reload_policy.find_reload_blockers",
        return_value=[blocker],
    ), patch(
        "app.services.instrument_hal_service.activate_hal_category_atomic",
        new=AsyncMock(),
    ) as activate:
        response = client.post(
            "/api/v1/instruments/baseStation/hal/activate"
        )

    assert response.status_code == 409
    body = response.json()
    assert body["refused"] is True
    assert body["blockers"][0]["kind"] == "instrument_lease"
    assert "force_hint" not in body
    activate.assert_not_awaited()


def test_activation_endpoint_rechecks_blockers_inside_guard():
    from app.services.hal_reload_policy import ReloadBlocker

    blocker = ReloadBlocker(
        kind="instrument_lease",
        id="late-lease",
        name="late-lease",
        status="running",
        detail="第一次检查后开始占用",
    )
    with patch(
        "app.services.hal_reload_policy.find_reload_blockers",
        side_effect=[[], [blocker]],
    ) as find_blockers, patch(
        "app.services.instrument_hal_service.activate_hal_category_atomic",
        new=AsyncMock(),
    ) as activate:
        response = client.post(
            "/api/v1/instruments/baseStation/hal/activate"
        )

    assert response.status_code == 409
    assert find_blockers.call_count == 2
    activate.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (hal_mod.HALCategoryNotFoundError("missing"), 404),
        (hal_mod.HALCategoryConfigurationError("bad config"), 422),
        (hal_mod.HALCategoryActivationError("connect failed"), 503),
    ],
)
def test_activation_endpoint_maps_domain_errors(error, expected_status):
    with patch(
        "app.services.instrument_hal_service.activate_hal_category_atomic",
        new=AsyncMock(side_effect=error),
    ):
        response = client.post(
            "/api/v1/instruments/baseStation/hal/activate"
        )

    assert response.status_code == expected_status
    assert str(error) in response.json()["detail"]


def test_activation_route_is_live_openapi_and_has_no_force_parameter():
    operation = app.openapi()["paths"][
        "/api/v1/instruments/{category_key}/hal/activate"
    ]["post"]

    assert {parameter["name"] for parameter in operation["parameters"]} == {
        "category_key"
    }


def test_driver_mode_endpoint_docs_do_not_require_global_reload():
    from app.api.instrument import reload_hal_service, set_instrument_driver_mode

    documentation = set_instrument_driver_mode.__doc__ or ""
    reload_documentation = reload_hal_service.__doc__ or ""

    assert "重新切换全局 HAL 模式" not in documentation
    assert "HAL 激活端点" in documentation
    assert "Use after editing instrument selection" not in reload_documentation
    assert "whole-HAL recovery" in reload_documentation
