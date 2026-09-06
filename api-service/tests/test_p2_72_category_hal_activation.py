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
from app.services.instrument_hal_service import DriverMode, InstrumentHALService
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

    async def connect(self):
        type(self).connected_instrument_ids.append(self.instrument_id)
        return True

    def readiness_metadata(self):
        return {}


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
