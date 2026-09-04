from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from app.models.instrument import InstrumentConnection
from app.hal.base import InstrumentStatus
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.propsim_f64 import F64SysInfo, RealPropsimF64Driver
from app.hal.propsim_fs16 import RealPropsimFs16Driver
from app.schemas.instrument import (
    FEConnectionUpdate,
    InstrumentConnectionResponse,
    InstrumentConnectionUpdate,
)
from app.services.channel_emulator_certification import (
    ChannelEmulatorCertificationIdentity,
    ChannelEmulatorCertificationProofs,
    ChannelEmulatorSiteCertification,
    activate_channel_emulator_site_certification,
    derive_channel_emulator_site_certification_from_execution,
    revoke_channel_emulator_site_certification,
)
from app.hal.base_station_compatibility import canonical_payload_digest
from app.services.channel_emulator_operation_receipt import (
    CE_OPERATION_RECEIPTS_CONFIG_KEY,
    channel_emulator_operation_receipt_chain_digest,
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


def test_revoke_service_locks_once_and_preserves_all_source_proof():
    active = ChannelEmulatorSiteCertification.model_validate(
        _certification_payload()
    )
    connection = SimpleNamespace(
        channel_emulator_site_certification=active.model_dump(mode="json")
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.one_or_none.return_value = (
        connection
    )

    revoked = revoke_channel_emulator_site_certification(
        db,
        connection_id="22222222-2222-2222-2222-222222222222",
        revoked_by=" quality-owner ",
        reason=" 连接将被维护 ",
    )

    assert revoked.status == "revoked"
    assert revoked.source_execution_id == active.source_execution_id
    assert revoked.terminal_evidence_digest == active.terminal_evidence_digest
    assert revoked.operation_receipts_digest == active.operation_receipts_digest
    assert revoked.measurement_evidence_digest == active.measurement_evidence_digest
    assert revoked.revoked_by == "quality-owner"
    assert revoked.revocation_reason == "连接将被维护"
    assert connection.channel_emulator_site_certification == revoked.model_dump(
        mode="json"
    )
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(connection)
    db.rollback.assert_not_called()


def test_revoke_service_rolls_back_when_active_certification_is_missing():
    connection = SimpleNamespace(channel_emulator_site_certification=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.one_or_none.return_value = (
        connection
    )

    with pytest.raises(ValueError, match="active"):
        revoke_channel_emulator_site_certification(
            db,
            connection_id="22222222-2222-2222-2222-222222222222",
            revoked_by="quality-owner",
            reason="连接将被维护",
        )

    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


def test_revoke_service_rolls_back_when_database_commit_fails():
    active = ChannelEmulatorSiteCertification.model_validate(
        _certification_payload()
    )
    connection = SimpleNamespace(
        channel_emulator_site_certification=active.model_dump(mode="json")
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.one_or_none.return_value = (
        connection
    )
    db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        revoke_channel_emulator_site_certification(
            db,
            connection_id="22222222-2222-2222-2222-222222222222",
            revoked_by="quality-owner",
            reason="连接将被维护",
        )

    db.rollback.assert_called_once_with()


def _certification_execution_fixture():
    from tests.test_p2_60_channel_operation_receipt import (
        _v2_terminal_projection_fixture,
    )
    from tests.test_p2_59_3_channel_emulator_session import (
        _execution_with_ce_evidence,
        _frozen_binding_for_driver,
        _frozen_plan,
    )

    _execution, terminal, receipts = _v2_terminal_projection_fixture()
    driver = RealPropsimF64Driver(
        "ce-runtime", {"ip_address": "192.0.2.59", "port": 3334}
    )
    binding = _frozen_binding_for_driver(driver, execution_mode="real")
    plan = _frozen_plan(driver)
    rebound_receipts = []
    for receipt in receipts:
        payload = {
            **{key: item for key, item in receipt.items() if key != "digest"},
            "binding_freeze_digest": binding["digest"],
            "plan_digest": plan["digest"],
            "adapter_id": plan["adapter_id"],
        }
        rebound_receipts.append(
            {**payload, "digest": canonical_payload_digest(payload)}
        )
    receipts = rebound_receipts

    def confirmed_receipt(source: dict, *, receipt_id: str, sequence: int, operation: str, field: str, value: float):
        payload = {
            **{key: item for key, item in source.items() if key != "digest"},
            "receipt_id": receipt_id,
            "sequence": sequence,
            "phase": "adjust",
            "operation": operation,
            "invocation_id": f"invocation-{sequence}",
            "fields": [{
                "field": field,
                "requested": value,
                "applied": value,
                "applied_present": True,
                "status": "confirmed",
                "provenance": "authoritative_readback",
                "exchange_ids": [f"exchange-{receipt_id}"],
                "source_reference": f"f64.{field}",
            }],
            "exchange_ids": [f"exchange-{receipt_id}"],
        }
        return {**payload, "digest": canonical_payload_digest(payload)}

    gain = confirmed_receipt(
        receipts[0], receipt_id="receipt-gain", sequence=0,
        operation="set_output_gain", field="gain_db", value=-3.0,
    )
    level = confirmed_receipt(
        receipts[0], receipt_id="receipt-level", sequence=1,
        operation="set_output_level_dbm", field="level_dbm", value=-20.0,
    )
    safe_payload = {
        **{key: item for key, item in receipts[0].items() if key != "digest"},
        "sequence": 2,
    }
    safe = {**safe_payload, "digest": canonical_payload_digest(safe_payload)}
    release_payload = {
        **{key: item for key, item in receipts[1].items() if key != "digest"},
        "sequence": 3,
    }
    release = {
        **release_payload,
        "digest": canonical_payload_digest(release_payload),
    }
    receipts = [gain, level, safe, release]
    identity = {
        "schema_version": 1,
        "instrument_id": terminal["instrument_id"],
        "adapter_id": plan["adapter_id"],
        "model": "PROPSIM F64",
        "firmware_version": "9.8.7",
        "serial_number": "SN-F64",
        "options": ["F64-OPT"],
        "options_observed": True,
        "simulated": False,
        "captured_from_live_connection": True,
    }
    identity["digest"] = canonical_payload_digest(identity)
    terminal_payload = {
        **{key: item for key, item in terminal.items() if key != "digest"},
        "schema_version": 3,
        "binding_freeze_digest": binding["digest"],
        "plan_digest": plan["digest"],
        "adapter_id": plan["adapter_id"],
        "driver_module": binding["expected_driver_module"],
        "driver_name": binding["expected_driver_name"],
        "driver_connection": binding["expected_driver_connection"],
        "hardware_identity": identity,
        "operation_receipt_count": len(receipts),
        "operation_receipts_digest": channel_emulator_operation_receipt_chain_digest(receipts),
        "operation_receipt_ids": [item["receipt_id"] for item in receipts],
        "safe_idle_receipt_id": safe["receipt_id"],
        "transport_release_receipt_id": release["receipt_id"],
    }
    terminal = {
        **terminal_payload,
        "digest": canonical_payload_digest(terminal_payload),
    }
    execution = _execution_with_ce_evidence(binding, plan, terminal)
    execution.config[CE_OPERATION_RECEIPTS_CONFIG_KEY] = receipts
    execution.config["channel_emulator_terminal_evidence"] = [terminal]
    execution.config["base_station_execution_evidence"] = {
        "current_measurement_attempt_id": terminal["measurement_attempt_id"],
        "current_measurement_attempt_state": "completed",
    }
    execution.measurements = {
        "phases": {
            "measure": {
                "frequency_consistency": {
                    "consistent": True,
                    "testcase_identity": "NR-ARFCN 633334 / BW 100 MHz",
                    "per_instrument": {
                        "BaseStation": "NR-ARFCN 633334 / BW 100 MHz",
                        "F64": "NR-ARFCN 633334 / BW 100 MHz",
                    },
                    "fully_verified": True,
                    "unverified": [],
                    "mismatches": [],
                    "f64_center_readback_mhz": 3500.01,
                    "f64_bandwidth_source": "channel_asset_or_scd_declared",
                },
                "path_loss_verified": True,
                "path_loss_application": {
                    "schema_version": 1,
                    "status": "applied",
                    "provenance": "real",
                    "reason": "selected",
                    "gate_mode": "strict",
                    "certificate_id": "path-loss-cert",
                    "value_disclosure": "verified",
                },
            }
        }
    }
    return execution


def test_activation_derivation_requires_one_complete_real_v3_evidence_scope():
    execution = _certification_execution_fixture()
    frozen_binding = execution.config["channel_emulator_binding_freeze"]

    certification = derive_channel_emulator_site_certification_from_execution(
        execution,
        connection_id=frozen_binding["instrument_connection_id"],
        current_binding_digest=frozen_binding["binding_digest"],
        current_adapter_id=execution.config["channel_emulator_execution_plan_freeze"]["adapter_id"],
        certified_by="quality-owner",
        reason="完整真实执行证据复核通过",
    )

    assert certification.status == "active"
    assert certification.source_execution_id == str(execution.id)
    assert certification.model == "PROPSIM F64"
    assert certification.required_proofs == _proofs()
    assert certification.load_mode == "native_model"


def _derive_certification(execution):
    frozen_binding = execution.config["channel_emulator_binding_freeze"]
    return derive_channel_emulator_site_certification_from_execution(
        execution,
        connection_id=frozen_binding["instrument_connection_id"],
        current_binding_digest=frozen_binding["binding_digest"],
        current_adapter_id=execution.config[
            "channel_emulator_execution_plan_freeze"
        ]["adapter_id"],
        certified_by="quality-owner",
        reason="完整真实执行证据复核通过",
    )


def _replace_terminal_identity(execution, **updates):
    terminal = execution.config["channel_emulator_terminal_evidence"][0]
    identity = {**terminal["hardware_identity"], **updates}
    identity_payload = {
        key: value for key, value in identity.items() if key != "digest"
    }
    identity = {
        **identity_payload,
        "digest": canonical_payload_digest(identity_payload),
    }
    terminal_payload = {
        **{key: value for key, value in terminal.items() if key != "digest"},
        "hardware_identity": identity,
    }
    execution.config["channel_emulator_terminal_evidence"][0] = {
        **terminal_payload,
        "digest": canonical_payload_digest(terminal_payload),
    }


@pytest.mark.parametrize(
    "schema_version",
    [1, 2],
)
def test_activation_derivation_rejects_legacy_terminal_evidence(schema_version):
    execution = _certification_execution_fixture()
    terminal = execution.config["channel_emulator_terminal_evidence"][0]
    terminal["schema_version"] = schema_version

    with pytest.raises(ValueError, match="terminal"):
        _derive_certification(execution)


@pytest.mark.parametrize(
    "identity_updates",
    [
        {"model": None},
        {"firmware_version": None},
        {"serial_number": None},
        {"options_observed": False},
        {"captured_from_live_connection": False},
        {"simulated": True},
    ],
)
def test_activation_derivation_rejects_unknown_or_simulated_identity(
    identity_updates,
):
    execution = _certification_execution_fixture()
    _replace_terminal_identity(execution, **identity_updates)

    with pytest.raises(ValueError, match="identity|terminal"):
        _derive_certification(execution)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (
            lambda execution: execution.config[
                "channel_emulator_binding_freeze"
            ].update(execution_mode="simulated"),
            "binding|scope|simulated",
        ),
        (
            lambda execution: execution.config[
                "channel_emulator_binding_freeze"
            ].update(binding_digest="0" * 64),
            "binding|scope",
        ),
        (
            lambda execution: execution.config[
                "channel_emulator_execution_plan_freeze"
            ].update(adapter_id="propsim_fs16"),
            "plan|binding",
        ),
        (
            lambda execution: execution.config[
                "channel_emulator_load_request_freeze"
            ].update(requested_load_mode="external_waveform"),
            "asset|plan|load",
        ),
    ],
)
def test_activation_derivation_rejects_mock_or_frozen_scope_drift(
    mutation,
    message,
):
    execution = _certification_execution_fixture()
    mutation(execution)

    with pytest.raises(ValueError, match=message):
        _derive_certification(execution)


@pytest.mark.parametrize(
    "terminal_field",
    ["safe_idle_confirmed", "transport_released_confirmed"],
)
def test_activation_derivation_rejects_incomplete_safe_idle_or_release(
    terminal_field,
):
    execution = _certification_execution_fixture()
    terminal = execution.config["channel_emulator_terminal_evidence"][0]
    terminal_payload = {
        **{key: value for key, value in terminal.items() if key != "digest"},
        terminal_field: False,
    }
    execution.config["channel_emulator_terminal_evidence"][0] = {
        **terminal_payload,
        "digest": canonical_payload_digest(terminal_payload),
    }

    with pytest.raises(ValueError, match="terminal|lifecycle|release|safe"):
        _derive_certification(execution)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda execution: execution.config["channel_emulator_terminal_evidence"][0].update(schema_version=2), "terminal"),
        (lambda execution: execution.measurements["phases"]["measure"]["frequency_consistency"].update(fully_verified=False), "frequency"),
        (lambda execution: execution.measurements["phases"]["measure"]["path_loss_application"].update(provenance="simulated"), "path-loss"),
    ],
)
def test_activation_derivation_rejects_non_certifiable_evidence(mutation, message):
    execution = _certification_execution_fixture()
    mutation(execution)
    frozen_binding = execution.config["channel_emulator_binding_freeze"]

    with pytest.raises(ValueError, match=message):
        derive_channel_emulator_site_certification_from_execution(
            execution,
            connection_id=frozen_binding["instrument_connection_id"],
            current_binding_digest=frozen_binding["binding_digest"],
            current_adapter_id=execution.config["channel_emulator_execution_plan_freeze"]["adapter_id"],
            certified_by="quality-owner",
            reason="完整真实执行证据复核通过",
        )


def test_activation_does_not_accept_an_unreferenced_cross_session_receipt():
    execution = _certification_execution_fixture()
    receipts = execution.config[CE_OPERATION_RECEIPTS_CONFIG_KEY]
    orphan_payload = {
        **{key: item for key, item in receipts[0].items() if key != "digest"},
        "session_id": "orphan-session",
        "lease_id": "orphan-lease",
    }
    receipts[0] = {
        **orphan_payload,
        "digest": canonical_payload_digest(orphan_payload),
    }
    terminal = execution.config["channel_emulator_terminal_evidence"][0]
    selected = []
    for sequence, receipt in enumerate(receipts[1:]):
        payload = {
            **{key: item for key, item in receipt.items() if key != "digest"},
            "sequence": sequence,
        }
        selected.append({**payload, "digest": canonical_payload_digest(payload)})
    receipts[1:] = selected
    terminal_payload = {
        **{key: item for key, item in terminal.items() if key != "digest"},
        "operation_receipt_count": len(selected),
        "operation_receipts_digest": channel_emulator_operation_receipt_chain_digest(selected),
        "operation_receipt_ids": [item["receipt_id"] for item in selected],
    }
    execution.config["channel_emulator_terminal_evidence"][0] = {
        **terminal_payload,
        "digest": canonical_payload_digest(terminal_payload),
    }
    frozen_binding = execution.config["channel_emulator_binding_freeze"]

    with pytest.raises(ValueError, match="path-loss receipt"):
        derive_channel_emulator_site_certification_from_execution(
            execution,
            connection_id=frozen_binding["instrument_connection_id"],
            current_binding_digest=frozen_binding["binding_digest"],
            current_adapter_id=execution.config["channel_emulator_execution_plan_freeze"]["adapter_id"],
            certified_by="quality-owner",
            reason="完整真实执行证据复核通过",
        )


def test_activate_service_uses_execution_then_locked_resolver_and_commits_once(monkeypatch):
    from app.models.instrument import InstrumentConnection
    from app.models.lab_profile import LabProfile
    from app.models.test_plan import TestCase, TestExecution
    from app.services import channel_emulator_binding as binding_module

    execution = _certification_execution_fixture()
    execution.test_case_id = "case-1"
    test_case = SimpleNamespace(id="case-1", lab_profile_id="lab-1")
    lab = SimpleNamespace(id="lab-1")
    connection = SimpleNamespace(
        id="ce-connection",
        channel_emulator_site_certification=None,
    )
    frozen_binding = execution.config["channel_emulator_binding_freeze"]
    frozen_plan = execution.config["channel_emulator_execution_plan_freeze"]
    resolved = SimpleNamespace(
        execution_mode="real",
        instrument_connection_id="ce-connection",
        instrument_model_id="ce-model",
        binding_digest=frozen_binding["binding_digest"],
        manifest=SimpleNamespace(adapter_id=frozen_plan["adapter_id"]),
    )
    monkeypatch.setattr(
        binding_module,
        "resolve_channel_emulator_binding",
        MagicMock(return_value=resolved),
    )

    connection_query = MagicMock()
    connection_query.filter.return_value.scalar.return_value = connection.id
    connection_query.filter.return_value.one.return_value = connection
    execution_query = MagicMock()
    execution_query.filter.return_value.with_for_update.return_value.one_or_none.return_value = execution
    case_query = MagicMock()
    case_query.filter.return_value.one_or_none.return_value = test_case
    lab_query = MagicMock()
    lab_query.filter.return_value.one_or_none.return_value = lab
    db = MagicMock()
    db.query.side_effect = lambda model: (
        connection_query
        if model in {InstrumentConnection, InstrumentConnection.id}
        else {
            TestExecution: execution_query,
            TestCase: case_query,
            LabProfile: lab_query,
        }[model]
    )

    certification = activate_channel_emulator_site_certification(
        db,
        object(),
        connection_id=connection.id,
        source_execution_id=execution.id,
        certified_by="quality-owner",
        reason="完整真实执行证据复核通过",
    )

    assert certification.status == "active"
    assert certification.source_execution_id == execution.id
    assert "channel_emulator_execution_qualification" not in execution.config
    assert connection.channel_emulator_site_certification == certification.model_dump(mode="json")
    binding_module.resolve_channel_emulator_binding.assert_called_once_with(
        db, ANY, lab, lock=True
    )
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(connection)
    db.rollback.assert_not_called()


def test_activate_service_rolls_back_on_any_derivation_error(monkeypatch):
    from app.models.instrument import InstrumentConnection
    from app.models.lab_profile import LabProfile
    from app.models.test_plan import TestCase, TestExecution
    from app.services import channel_emulator_binding as binding_module

    execution = _certification_execution_fixture()
    execution.test_case_id = "case-1"
    execution.measurements["phases"]["measure"]["frequency_consistency"]["fully_verified"] = False
    connection = SimpleNamespace(id="ce-connection", channel_emulator_site_certification=None)
    connection_query = MagicMock()
    connection_query.filter.return_value.scalar.return_value = connection.id
    connection_query.filter.return_value.one.return_value = connection
    execution_query = MagicMock()
    execution_query.filter.return_value.with_for_update.return_value.one_or_none.return_value = execution
    case_query = MagicMock()
    case_query.filter.return_value.one_or_none.return_value = SimpleNamespace(
        id="case-1", lab_profile_id="lab-1"
    )
    lab_query = MagicMock()
    lab_query.filter.return_value.one_or_none.return_value = SimpleNamespace(id="lab-1")
    db = MagicMock()
    db.query.side_effect = lambda model: (
        connection_query
        if model in {InstrumentConnection, InstrumentConnection.id}
        else {
            TestExecution: execution_query,
            TestCase: case_query,
            LabProfile: lab_query,
        }[model]
    )
    frozen = execution.config["channel_emulator_binding_freeze"]
    plan = execution.config["channel_emulator_execution_plan_freeze"]
    monkeypatch.setattr(
        binding_module,
        "resolve_channel_emulator_binding",
        lambda *_args, **_kwargs: SimpleNamespace(
            execution_mode="real",
            instrument_connection_id=connection.id,
            instrument_model_id="ce-model",
            binding_digest=frozen["binding_digest"],
            manifest=SimpleNamespace(adapter_id=plan["adapter_id"]),
        ),
    )

    with pytest.raises(ValueError, match="frequency"):
        activate_channel_emulator_site_certification(
            db,
            object(),
            connection_id=connection.id,
            source_execution_id=execution.id,
            certified_by="quality-owner",
            reason="完整真实执行证据复核通过",
        )

    assert connection.channel_emulator_site_certification is None
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


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


def test_f64_certification_identity_is_a_pure_projection_of_live_cached_truth():
    driver = RealPropsimF64Driver("ce-f64", {"ip_address": "192.0.2.61"})
    driver._visa_resource = object()
    driver._status = InstrumentStatus.READY
    driver._identity_response = "Keysight Technologies,F8800A,SN-F64,9.8.7"
    driver.sys_info = F64SysInfo(
        raw="PROPSIM F64,64,RF,v1.0,16",
        product_family="PROPSIM F64",
        channel_count=64,
        signal_type="RF",
        firmware_version="v1.0",
        secondary_count=16,
    )
    driver.product_family = "PROPSIM F64"
    driver.firmware_version = "v1.0"
    driver._installed_options = [" B ", "A", "A"]
    driver._certification_options_observed = True

    identity = driver.capture_channel_emulator_certification_identity()

    assert identity == ChannelEmulatorCertificationIdentity.model_validate(
        identity.model_dump(mode="json")
    )
    assert identity.instrument_id == "ce-f64"
    assert identity.adapter_id == "propsim_f64"
    assert identity.model == "PROPSIM F64"
    assert identity.firmware_version == "9.8.7"
    assert identity.serial_number == "SN-F64"
    assert identity.options == ("A", "B")
    assert identity.options_observed is True
    assert identity.simulated is False
    assert identity.captured_from_live_connection is True
    assert identity.certification_eligible is True


def test_confirmed_zero_options_are_distinct_from_unobserved_options():
    driver = RealPropsimF64Driver("ce-f64", {"ip_address": "192.0.2.61"})
    driver._visa_resource = object()
    driver._status = InstrumentStatus.READY
    driver._identity_response = "Keysight Technologies,F8800A,SN-F64,9.8.7"
    driver.product_family = "PROPSIM F64"
    driver._installed_options = []
    driver._certification_options_observed = True

    confirmed_empty = driver.capture_channel_emulator_certification_identity()
    assert confirmed_empty.options == ()
    assert confirmed_empty.options_observed is True
    assert confirmed_empty.certification_eligible is True

    driver._certification_options_observed = False
    unobserved = driver.capture_channel_emulator_certification_identity()
    assert unobserved.options == ()
    assert unobserved.options_observed is False
    assert unobserved.certification_eligible is False
    assert unobserved.digest != confirmed_empty.digest


def test_fs16_and_mock_identity_never_invent_missing_certification_truth():
    fs16 = RealPropsimFs16Driver("ce-fs16", {"ip_address": "192.0.2.62"})
    fs16._visa_resource = object()
    fs16._status = InstrumentStatus.READY
    fs16._identity_response = "Keysight Technologies,F8820A,SN-FS16,10.2"
    fs16._product_family = "PROPSIM FS16"
    fs16._installed_options = []
    fs16._certification_options_observed = False
    fs16_identity = fs16.capture_channel_emulator_certification_identity()
    assert fs16_identity.model == "PROPSIM FS16"
    assert fs16_identity.serial_number == "SN-FS16"
    assert fs16_identity.options_observed is False
    assert fs16_identity.certification_eligible is False

    mock = MockChannelEmulator("ce-mock", {"model": "Mock Channel Emulator"})
    mock_identity = mock.capture_channel_emulator_certification_identity()
    assert mock_identity.simulated is True
    assert mock_identity.captured_from_live_connection is False
    assert mock_identity.certification_eligible is False


def test_certification_identity_rejects_digest_or_scope_tampering():
    mock = MockChannelEmulator("ce-mock", {"model": "Mock Channel Emulator"})
    payload = mock.capture_channel_emulator_certification_identity().model_dump(mode="json")
    with pytest.raises(ValidationError, match="digest"):
        ChannelEmulatorCertificationIdentity.model_validate(
            {**payload, "instrument_id": "different"}
        )
