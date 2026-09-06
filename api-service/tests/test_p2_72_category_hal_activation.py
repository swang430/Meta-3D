"""P2-72：仪器配置保存后按类别激活 HAL。"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import InstrumentCategory, InstrumentModel
from app.services import instrument_hal_service as hal_mod
from app.hal.base import InstrumentStatus
from app.services.instrument_hal_service import (
    DriverMode,
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


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    Base.metadata.create_all(bind=engine)
    import app.db.database as dbmod

    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)
    yield
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


class _FailingConnectDriver(_RecordingDriver):
    async def connect(self):
        type(self).connected_instrument_ids.append(self.instrument_id)
        self._status = InstrumentStatus.ERROR
        self._last_error = "connect failed by fixture"
        return False


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

    result = asyncio.run(activate_hal_category_atomic("baseStation"))

    assert result.status == "unchanged"
    assert loaded.disconnect_calls == 0
    assert service.drivers["baseStation"] is loaded


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
    _install_global_service(monkeypatch, service)

    result = asyncio.run(activate_hal_category_atomic("baseStation"))

    assert result.status == "inactive"
    assert old_base.disconnect_calls == 1
    assert "baseStation" not in service.drivers
    assert service.drivers["channelEmulator"] is original_f64


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
