"""P2-62：第三种 Channel Emulator adapter 的参数化接入认证。"""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
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
from app.services.channel_emulator_binding import resolve_channel_emulator_binding
from app.services.channel_emulator_model_preset import (
    require_saved_active_channel_emulator_preset,
    save_channel_emulator_model_preset,
)
from tests.channel_emulator_certification_kit import (
    CERTFAKE_CE_MANIFEST,
    CERTFAKE_CE_PROFILE,
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
