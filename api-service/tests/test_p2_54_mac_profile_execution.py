from __future__ import annotations

from copy import deepcopy

import pytest

from app.hal.base_station import (
    BaseStationApplyReceipt,
    BaseStationFieldReceipt,
    MacThroughputConfigResult,
)

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
        )
    }


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

    confirm_base_station_mac_profile(
        _Db(execution),
        execution.id,
        attempt_id="attempt-1",
        lease_identity=_lease("uxm"),
        result=_mac_result(profile.profile_digest),
    )

    stored = execution.config["base_station_execution_evidence"]
    lifecycle = valid_cmw_evidence()
    windows = deepcopy(lifecycle["measurement_windows"])
    for window in windows:
        window["adapter"] = "uxm"
        window["route_digest"] = None
    releases = deepcopy(lifecycle["control_releases"])
    for release in releases:
        release["adapter_id"] = "uxm"
    stored.update(
        {
            "config_confirmed": True,
            "current_measurement_attempt_state": "completed",
            "measurement_windows": windows,
            "control_releases": releases,
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
            _freeze(),
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
            _freeze(),
            require_formal_confirmation=True,
        )
        or ""
    )

    stored["mac_profile_digest"] = "f" * 64
    assert validate_frozen_mac_profile_evidence(
        execution.config,
        _freeze(),
        require_formal_confirmation=True,
    ) is not None


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
