from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.hal.base_station import (
    BaseStationApplyReceipt,
    BaseStationFieldReceipt,
    MacThroughputConfigResult,
)
from app.hal.scpi_evidence import ScpiExchangeRef

from app.hal.base_station_compatibility import (
    build_frozen_compatibility_payload,
    build_measure_execution_requirements_from_configuration,
    evaluate_base_station_compatibility,
    canonical_payload_digest,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services.base_station_adapter_profile import (
    frozen_mac_profile_from_adapter_freeze,
)
from app.services import execution_scpi_evidence as evidence_writer
from app.services.execution_scpi_evidence import (
    confirm_base_station_mac_profile,
    initialize_base_station_execution_evidence,
)
from app.services.execution_evidence_outcome import (
    validate_frozen_mac_profile_evidence,
)
from tests.test_p2_43_base_station_adapter_evidence import (
    _Db,
    _execution,
    _lease,
)
from tests.p1_73c_evidence_fixtures import POSITION, valid_cmw_evidence
from tests.test_p1_73c_base_station_evidence_writer import (
    _CmwDriver,
    _execution as _new_execution,
    _frozen as _cmw_frozen,
    _request as _cmw_request,
)
from app.services.mimo_ota.executors.measure import (
    _build_pcell_requested_config,
    _frozen_mac_measurement_basis,
    _frozen_mcs_consistency_request,
)
from app.schemas.mimo_ota.config import (
    MIMOOTAConfiguration,
    canonicalize_mimo_ota_configuration_payload,
)


def _freeze() -> dict:
    requirements = build_measure_execution_requirements_from_configuration({})
    verdict = evaluate_base_station_compatibility(
        requirements,
        RealUxmDriver.adapter_manifest,
    )
    return {
        "compatibility": build_frozen_compatibility_payload(
            requirements,
            verdict,
        ),
        "resolved_binding": {
            "manifest": RealUxmDriver.adapter_manifest.model_dump(mode="json"),
        },
    }


def _cmw_freeze() -> dict:
    requirements = build_measure_execution_requirements_from_configuration(
        {
            "component_carriers": [
                {
                    "radio_technology": "lte",
                    "frequency_hz": 1_842_500_000.0,
                    "bandwidth_mhz": 20.0,
                    "subcarrier_spacing_khz": None,
                    "band": "B3",
                    "duplex": "fdd",
                    "lte_dl_earfcn": 1575,
                    "lte_transmission_mode": "TM3",
                    "role": "pcell",
                }
            ],
            "mimo_layers": 2,
        }
    )
    verdict = evaluate_base_station_compatibility(
        requirements,
        RealCmw500Driver.adapter_manifest,
    )
    frozen = _cmw_frozen()
    frozen["compatibility"] = build_frozen_compatibility_payload(
        requirements,
        verdict,
    )
    frozen["resolved_binding"] = {
        "manifest": RealCmw500Driver.adapter_manifest.model_dump(mode="json"),
    }
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )
    return frozen


def test_attempt_profile_is_read_only_from_the_execution_freeze():
    frozen = _freeze()
    profile = frozen_mac_profile_from_adapter_freeze(frozen)

    changed_current = build_measure_execution_requirements_from_configuration(
        {"mcs": 3, "stat_count": 9}
    ).mac_profile

    assert profile is not None
    assert changed_current is not None
    assert changed_current.profile_digest != profile.profile_digest
    assert profile.profile.kind == "nr_throughput"
    assert profile.profile.mcs == 28
    assert profile.profile.statistical_window.count == 5000
    assert frozen_mac_profile_from_adapter_freeze(frozen) == profile


def test_attempt_profile_rejects_digest_drift_before_use():
    frozen = _freeze()
    frozen["compatibility"]["requirements"]["mac_profile"][
        "profile_digest"
    ] = "0" * 64

    try:
        frozen_mac_profile_from_adapter_freeze(frozen)
    except ValueError as exc:
        assert "MAC profile" in str(exc)
    else:  # pragma: no cover - documents the RED contract
        raise AssertionError("digest drift must fail closed")


def test_pre_p2_54_compatibility_has_no_profile_without_becoming_malformed():
    frozen = _freeze()
    legacy = deepcopy(frozen)
    legacy["compatibility"]["requirements"].pop("mac_profile")

    assert frozen_mac_profile_from_adapter_freeze(legacy) is None


def test_explicit_null_compatibility_is_not_misclassified_as_legacy():
    with pytest.raises(ValueError, match="compatibility"):
        frozen_mac_profile_from_adapter_freeze({"compatibility": None})


def _mac_result(
    profile_digest: str,
    *,
    simulated: bool = False,
    include_exchange: bool = True,
):
    exchange_ids = () if simulated or not include_exchange else ("mac-1",)
    receipt = BaseStationApplyReceipt(
        schema_version=1,
        operation="mac_throughput_config",
        fields=(
            BaseStationFieldReceipt(
                field="scheduler",
                requested="full_throughput",
                applied=None if simulated else "full_throughput",
                status="unknown" if simulated else "confirmed",
                reason="simulated" if simulated else "confirmed",
                exchange_ids=exchange_ids,
            ),
        ),
        reason="simulated" if simulated else "confirmed",
        simulated=simulated,
        operation_succeeded=True,
        profile_digest=profile_digest,
    )
    return MacThroughputConfigResult(
        receipt=receipt,
        profile_digest=profile_digest,
    )


def _uxm_application_exchanges(execution_id: str):
    return (
        ScpiExchangeRef(
            exchange_id="mac-write-1",
            instrument_id="uxm",
            operation="command",
            command="catalog-backed-write",
            execution_id=execution_id,
            capture_id="mac-capture-1",
            sequence=0,
            result_type="ok",
        ),
        ScpiExchangeRef(
            exchange_id="mac-error-queue-1",
            instrument_id="uxm",
            operation="query",
            command="SYST:ERR?",
            execution_id=execution_id,
            capture_id="mac-capture-1",
            sequence=1,
            result_type="response",
            response='0,"No error"',
        ),
    )


def _partial_uxm_mac_result(profile_digest: str, execution_id: str):
    receipt = BaseStationApplyReceipt(
        schema_version=1,
        operation="mac_throughput_config",
        fields=(
            BaseStationFieldReceipt(
                field="mac_profile",
                requested={"kind": "nr_throughput"},
                applied=None,
                status="unknown",
                reason=(
                    "command groups and error queue were observed, but no "
                    "full-profile readback exists"
                ),
                exchange_ids=("mac-write-1", "mac-error-queue-1"),
            ),
        ),
        reason="UXM command/error-queue evidence is complete",
        simulated=False,
        operation_succeeded=True,
        profile_digest=profile_digest,
    )
    return MacThroughputConfigResult(
        applied=("PDSCH_SCHED_ALGO",),
        receipt=receipt,
        profile_digest=profile_digest,
        application_exchanges=_uxm_application_exchanges(execution_id),
    )


def test_confirmed_mac_receipt_requires_field_exchange_evidence(monkeypatch):
    execution = _execution(adapter="uxm")
    profile = frozen_mac_profile_from_adapter_freeze(_freeze())
    assert profile is not None
    execution.config["base_station_execution_evidence"].update(
        {
            "mac_profile_contract_version": 1,
            "mac_profile_digest": profile.profile_digest,
            "mac_profile_receipts": [],
        }
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("uxm"),
    )

    with pytest.raises(ValueError, match="exchange"):
        confirm_base_station_mac_profile(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease("uxm"),
            result=_mac_result(profile.profile_digest, include_exchange=False),
        )


def test_mac_receipt_is_bound_to_attempt_lease_and_frozen_profile(monkeypatch):
    execution = _execution(adapter="cmw500")
    frozen = _cmw_freeze()
    profile = frozen_mac_profile_from_adapter_freeze(frozen)
    assert profile is not None
    evidence = execution.config["base_station_execution_evidence"]
    evidence.update(
        {
            "mac_profile_contract_version": 1,
            "mac_profile_digest": profile.profile_digest,
            "mac_profile_receipts": [],
        }
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("cmw500"),
    )

    confirm_base_station_mac_profile(
        _Db(execution),
        execution.id,
        attempt_id="attempt-1",
        lease_identity=_lease("cmw500"),
        result=_mac_result(profile.profile_digest),
    )

    stored = execution.config["base_station_execution_evidence"]
    lifecycle = valid_cmw_evidence()
    stored.update(
        {
            "config_confirmed": True,
            "route_confirmed": True,
            "applied_route": deepcopy(lifecycle["applied_route"]),
            "current_measurement_attempt_state": "completed",
            "measurement_windows": deepcopy(lifecycle["measurement_windows"]),
            "control_releases": deepcopy(lifecycle["control_releases"]),
        }
    )
    stored["exchange_ids"] = list(
        dict.fromkeys(stored["exchange_ids"] + lifecycle["exchange_ids"])
    )
    assert stored["mac_profile_receipts"][0]["profile_digest"] == (
        profile.profile_digest
    )
    assert stored["mac_profile_receipts"][0]["confirmed"] is True
    assert (
        validate_frozen_mac_profile_evidence(
            execution.config,
            frozen,
            require_formal_confirmation=True,
        )
        is None
    )

    receipt = stored["mac_profile_receipts"][0]
    receipt["lease_id"] = "other-lease"
    receipt["session_token"] = "other-session"
    assert "lease" in (
        validate_frozen_mac_profile_evidence(
            execution.config,
            frozen,
            require_formal_confirmation=True,
        )
        or ""
    )

    stored["mac_profile_digest"] = "f" * 64
    assert validate_frozen_mac_profile_evidence(
        execution.config,
        frozen,
        require_formal_confirmation=True,
    ) is not None


def test_uxm_unverified_error_queue_cannot_create_formal_application_evidence(
    monkeypatch,
):
    execution = _execution(adapter="uxm")
    profile = frozen_mac_profile_from_adapter_freeze(_freeze())
    assert profile is not None
    evidence = execution.config["base_station_execution_evidence"]
    evidence.update(
        {
            "mac_profile_contract_version": 1,
            "mac_profile_digest": profile.profile_digest,
            "mac_profile_receipts": [],
        }
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("uxm"),
    )

    with pytest.raises(ValueError, match="application evidence is incomplete"):
        confirm_base_station_mac_profile(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease("uxm"),
            result=_partial_uxm_mac_result(profile.profile_digest, str(execution.id)),
        )

    assert execution.config["base_station_execution_evidence"][
        "mac_profile_receipts"
    ] == []


def test_uxm_authoritative_application_proof_uses_real_hal_command_token(
    monkeypatch,
):
    execution = _execution(adapter="uxm")
    profile = frozen_mac_profile_from_adapter_freeze(_freeze())
    assert profile is not None
    evidence = execution.config["base_station_execution_evidence"]
    evidence.update(
        {
            "mac_profile_contract_version": 1,
            "mac_profile_digest": profile.profile_digest,
            "mac_profile_receipts": [],
        }
    )
    lease = _lease("uxm")
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: lease,
    )
    monkeypatch.setattr(
        evidence_writer,
        "exchange_is_error_queue_query",
        lambda exchange, *, instrument: exchange.operation == "query",
    )
    monkeypatch.setattr(
        evidence_writer,
        "exchange_has_clean_error_queue_response",
        lambda exchange, *, instrument: True,
    )

    confirm_base_station_mac_profile(
        _Db(execution),
        execution.id,
        attempt_id="attempt-1",
        lease_identity=lease,
        result=_partial_uxm_mac_result(
            profile.profile_digest,
            str(execution.id),
        ),
    )

    stored = execution.config["base_station_execution_evidence"]
    assert stored["mac_profile_receipts"][0]["application_evidence"][
        "exchanges"
    ][0]["role"] == "command"


@pytest.mark.parametrize("invalid_shape", ("queue_before_final_write", "wrong_instrument"))
def test_uxm_mac_application_evidence_binds_post_write_queue_and_active_instrument(
    monkeypatch,
    invalid_shape,
):
    execution = _execution(adapter="uxm")
    profile = frozen_mac_profile_from_adapter_freeze(_freeze())
    assert profile is not None
    execution.config["base_station_execution_evidence"].update(
        {
            "mac_profile_contract_version": 1,
            "mac_profile_digest": profile.profile_digest,
            "mac_profile_receipts": [],
        }
    )
    lease = SimpleNamespace(
        lease_id="lease-1",
        measurement_attempt_id="attempt-1",
        adapter_id="uxm",
        session_token="session-1",
        instrument_id="uxm",
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: lease,
    )
    result = _partial_uxm_mac_result(profile.profile_digest, str(execution.id))
    rows = list(result.application_exchanges)
    if invalid_shape == "queue_before_final_write":
        rows = [
            rows[1].model_copy(update={"sequence": 0}),
            rows[0].model_copy(update={"sequence": 1}),
        ]
    else:
        rows = [row.model_copy(update={"instrument_id": "other-uxm"}) for row in rows]
    exchange_ids = tuple(row.exchange_id for row in rows)
    receipt = replace(
        result.receipt,
        fields=tuple(
            replace(field, exchange_ids=exchange_ids)
            for field in result.receipt.fields
        ),
    )
    result = replace(
        result,
        receipt=receipt,
        application_exchanges=tuple(rows),
    )

    with pytest.raises(ValueError, match="MAC application evidence"):
        confirm_base_station_mac_profile(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=lease,
            result=result,
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda rows: [rows[0].model_copy(update={"result_type": "intent"}), rows[1]],
        lambda rows: [rows[0].model_copy(update={"execution_id": "other"}), rows[1]],
        lambda rows: [rows[0], rows[1].model_copy(update={"capture_id": "other"})],
        lambda rows: [rows[0], rows[1].model_copy(update={"instrument_id": "other"})],
        lambda rows: [rows[0].model_copy(update={"simulated": True}), rows[1]],
        lambda rows: [rows[0]],
        lambda rows: [
            rows[0],
            rows[1].model_copy(update={"response": '-113,"Undefined header"'}),
        ],
    ),
)
def test_uxm_mac_application_evidence_rejects_unbound_or_incomplete_exchange_proof(
    monkeypatch,
    mutate,
):
    execution = _execution(adapter="uxm")
    profile = frozen_mac_profile_from_adapter_freeze(_freeze())
    assert profile is not None
    execution.config["base_station_execution_evidence"].update(
        {
            "mac_profile_contract_version": 1,
            "mac_profile_digest": profile.profile_digest,
            "mac_profile_receipts": [],
        }
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("uxm"),
    )
    result = _partial_uxm_mac_result(profile.profile_digest, str(execution.id))
    result = MacThroughputConfigResult(
        applied=result.applied,
        receipt=result.receipt,
        profile_digest=result.profile_digest,
        application_exchanges=tuple(mutate(list(result.application_exchanges))),
    )

    with pytest.raises(ValueError, match="MAC application evidence"):
        confirm_base_station_mac_profile(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease("uxm"),
            result=result,
        )


def test_mac_receipt_digest_drift_fails_closed(monkeypatch):
    execution = _execution(adapter="uxm")
    profile = frozen_mac_profile_from_adapter_freeze(_freeze())
    assert profile is not None
    execution.config["base_station_execution_evidence"].update(
        {
            "mac_profile_contract_version": 1,
            "mac_profile_digest": profile.profile_digest,
            "mac_profile_receipts": [],
        }
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("uxm"),
    )

    with pytest.raises(ValueError, match="digest"):
        confirm_base_station_mac_profile(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease("uxm"),
            result=_mac_result("0" * 64),
        )


def test_window_and_nr_mcs_inputs_come_from_the_same_frozen_profile():
    profile = frozen_mac_profile_from_adapter_freeze(_freeze())
    assert profile is not None

    assert _frozen_mac_measurement_basis(profile) == 5000
    assert _frozen_mcs_consistency_request(profile) == (28, False)


def test_lte_rmc_never_consumes_nr_mcs_inputs():
    requirements = build_measure_execution_requirements_from_configuration(
        {
            "component_carriers": [
                {
                    "radio_technology": "lte",
                    "frequency_hz": 1_842_500_000.0,
                    "bandwidth_mhz": 20.0,
                    "subcarrier_spacing_khz": None,
                    "band": "B3",
                    "duplex": "fdd",
                    "lte_dl_earfcn": 1575,
                    "lte_transmission_mode": "TM3",
                    "role": "pcell",
                }
            ],
            "mimo_layers": 2,
        }
    )
    profile = requirements.mac_profile
    assert profile is not None

    assert _frozen_mac_measurement_basis(profile) == 5000
    assert _frozen_mcs_consistency_request(profile) is None


def test_canonical_roundtrip_pcell_request_uses_frozen_nr_scheduler_truth():
    initial = MIMOOTAConfiguration.model_validate(
        {
            "sched_algo": "FULLBUFFER",
            "csi_rs_ports": 8,
            "mcs": 19,
        }
    )
    canonical = canonicalize_mimo_ota_configuration_payload(
        initial.model_dump(mode="json")
    )
    assert "sched_algo" not in canonical
    assert "csi_rs_ports" not in canonical
    reloaded = MIMOOTAConfiguration.model_validate(canonical)

    requested = _build_pcell_requested_config(
        reloaded,
        mac_profile=reloaded.mac_profile,
    )

    assert requested.scheduler_algorithm == "full_throughput"
    assert requested.csi_rs_ports == 8


def test_new_execution_evidence_freezes_the_same_profile_digest():
    requirements = build_measure_execution_requirements_from_configuration(
        {
            "component_carriers": [
                {
                    "radio_technology": "lte",
                    "frequency_hz": 1_842_500_000.0,
                    "bandwidth_mhz": 20.0,
                    "subcarrier_spacing_khz": None,
                    "band": "B3",
                    "duplex": "fdd",
                    "lte_dl_earfcn": 1575,
                    "lte_transmission_mode": "TM3",
                    "role": "pcell",
                }
            ],
            "mimo_layers": 2,
        }
    )
    verdict = evaluate_base_station_compatibility(
        requirements,
        RealCmw500Driver.adapter_manifest,
    )
    frozen = _cmw_frozen()
    frozen["compatibility"] = build_frozen_compatibility_payload(
        requirements,
        verdict,
    )
    frozen["digest"] = canonical_payload_digest(
        {key: value for key, value in frozen.items() if key != "digest"}
    )

    saved = initialize_base_station_execution_evidence(
        _new_execution(),
        frozen_adapter=frozen,
        requested_config=_cmw_request(),
        requested_positions=[POSITION],
        driver=_CmwDriver(),
    )

    assert saved["mac_profile_contract_version"] == 1
    assert saved["mac_profile_digest"] == (
        requirements.mac_profile.profile_digest
    )
    assert saved["mac_profile_receipts"] == []
