from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from app.models.instrument import InstrumentConnection
from app.schemas.instrument import (
    FEConnectionUpdate,
    InstrumentConnectionResponse,
    InstrumentConnectionUpdate,
)
from app.services.channel_emulator_certification import (
    ChannelEmulatorCertificationProofs,
    ChannelEmulatorSiteCertification,
)


API_SERVICE_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    API_SERVICE_ROOT
    / "alembic"
    / "versions"
    / "c5e7f9a1b3d6_add_channel_emulator_site_certification.py"
)


def _proofs(**updates: bool) -> ChannelEmulatorCertificationProofs:
    payload = {
        "binding_plan_asset": True,
        "hardware_identity_options": True,
        "operation_receipts": True,
        "frequency": True,
        "level": True,
        "path_loss": True,
        "safe_idle": True,
        "transport_release": True,
    }
    payload.update(updates)
    return ChannelEmulatorCertificationProofs.model_validate(payload)


def _certification_payload(**updates):
    payload = {
        "schema_version": 1,
        "status": "active",
        "lab_profile_id": "11111111-1111-1111-1111-111111111111",
        "instrument_connection_id": "22222222-2222-2222-2222-222222222222",
        "instrument_model_id": "33333333-3333-3333-3333-333333333333",
        "binding_digest": "a" * 64,
        "adapter_id": "propsim_f64",
        "plan_digest": "b" * 64,
        "asset_digest": "c" * 64,
        "load_mode": "native_model",
        "model": "PROPSIM F64",
        "firmware_version": "1.2.3",
        "serial_number": "F64-SERIAL",
        "options": [" B ", "A", "A"],
        "identity_digest": "d" * 64,
        "source_execution_id": "44444444-4444-4444-4444-444444444444",
        "terminal_evidence_digest": "e" * 64,
        "operation_receipts_digest": "f" * 64,
        "measurement_evidence_digest": "1" * 64,
        "required_proofs": _proofs().model_dump(mode="json"),
        "certified_by": " quality-owner ",
        "certified_at": datetime(2026, 9, 5, tzinfo=timezone.utc),
        "reason": " 真实执行证据复核通过 ",
        "revoked_by": None,
        "revoked_at": None,
        "revocation_reason": None,
    }
    payload.update(updates)
    return payload


def test_certification_proofs_require_every_server_derived_class():
    assert _proofs().model_dump() == {
        "binding_plan_asset": True,
        "hardware_identity_options": True,
        "operation_receipts": True,
        "frequency": True,
        "level": True,
        "path_loss": True,
        "safe_idle": True,
        "transport_release": True,
    }
    for field in ChannelEmulatorCertificationProofs.model_fields:
        with pytest.raises(ValidationError, match="requires"):
            _proofs(**{field: False})
    with pytest.raises(ValidationError):
        ChannelEmulatorCertificationProofs.model_validate(
            {**_proofs().model_dump(), "client_approved": True}
        )


def test_site_certification_is_strict_canonical_and_digest_bound():
    certification = ChannelEmulatorSiteCertification.model_validate(
        _certification_payload()
    )
    assert certification.options == ("A", "B")
    assert certification.certified_by == "quality-owner"
    assert certification.reason == "真实执行证据复核通过"
    assert len(certification.certification_digest) == 64
    assert certification.certification_digest == certification.certification_digest

    with pytest.raises(ValidationError):
        ChannelEmulatorSiteCertification.model_validate(
            _certification_payload(browser_authorized=True)
        )
    with pytest.raises(ValidationError, match="digest"):
        ChannelEmulatorSiteCertification.model_validate(
            _certification_payload(binding_digest="not-a-digest")
        )
    with pytest.raises(ValidationError, match="revocation"):
        ChannelEmulatorSiteCertification.model_validate(
            _certification_payload(revoked_by="operator")
        )


def test_revoked_certification_requires_complete_audit_and_keeps_source_proof():
    active = ChannelEmulatorSiteCertification.model_validate(
        _certification_payload()
    )
    revoked_at = datetime(2026, 9, 6, tzinfo=timezone.utc)
    revoked = ChannelEmulatorSiteCertification.model_validate(
        active.model_copy(
            update={
                "status": "revoked",
                "revoked_by": "quality-owner",
                "revoked_at": revoked_at,
                "revocation_reason": "仪器连接已变更",
            }
        )
    )
    assert revoked.source_execution_id == active.source_execution_id
    assert revoked.operation_receipts_digest == active.operation_receipts_digest
    assert revoked.revoked_at == revoked_at
    assert revoked.certification_digest != active.certification_digest

    with pytest.raises(ValidationError, match="revocation"):
        ChannelEmulatorSiteCertification.model_validate(
            active.model_copy(update={"status": "revoked"})
        )


def test_connection_models_expose_read_only_server_certification():
    assert "channel_emulator_site_certification" in InstrumentConnection.__table__.columns
    assert (
        InstrumentConnection.__table__.columns[
            "channel_emulator_site_certification"
        ].nullable
        is True
    )
    assert "channel_emulator_site_certification" in InstrumentConnectionResponse.model_fields
    assert "channel_emulator_site_certification" not in InstrumentConnectionUpdate.model_fields
    assert "channel_emulator_site_certification" not in FEConnectionUpdate.model_fields


def _migration_module():
    spec = importlib.util.spec_from_file_location("mig_p2_61", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_migration(engine, fn) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            fn()
        connection.commit()


def test_migration_adds_nullable_server_column_without_promoting_history():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE instrument_connections (id VARCHAR(36) PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO instrument_connections (id) VALUES ('legacy')")
        )
    module = _migration_module()

    _run_migration(engine, module.upgrade)
    columns = {item["name"] for item in inspect(engine).get_columns("instrument_connections")}
    assert "channel_emulator_site_certification" in columns
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT channel_emulator_site_certification "
                "FROM instrument_connections WHERE id='legacy'"
            )
        ).scalar_one() is None

    _run_migration(engine, module.upgrade)
    _run_migration(engine, module.downgrade)
    columns = {item["name"] for item in inspect(engine).get_columns("instrument_connections")}
    assert "channel_emulator_site_certification" not in columns
    engine.dispose()
