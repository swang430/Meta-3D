"""P2-47: attach receipts are bound to one execution attempt and lease."""

from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

from copy import deepcopy

import pytest

from app.hal.base_station import (
    BaseStationAttachReceipt,
    BaseStationAttachStageReceipt,
    MockBaseStation,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services import execution_scpi_evidence as evidence_writer
from app.services.execution_scpi_evidence import confirm_base_station_attach
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota.base_station_execution_evidence import (
    base_station_execution_evidence_is_formally_acceptable,
    parse_base_station_execution_evidence,
)
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence
from tests.test_p2_43_base_station_adapter_evidence import _Db, _execution


def _lease(adapter: str = "cmw500") -> ActiveBaseStationLeaseIdentity:
    return ActiveBaseStationLeaseIdentity(
        lease_id="lease-1",
        measurement_attempt_id="attempt-1",
        adapter_id=adapter,
        session_token="session-1",
    )


def _receipt(adapter: str = "cmw500") -> BaseStationAttachReceipt:
    manifest = (
        RealCmw500Driver.adapter_manifest
        if adapter == "cmw500"
        else RealUxmDriver.adapter_manifest
    )
    capabilities = {item.stage: item for item in manifest.attach_stages}
    stages = []
    for index, stage in enumerate(
        ("cell_ready", "ue_registered", "rrc_connected", "data_bearer_established")
    ):
        capability = capabilities[stage]
        if capability.evidence == "authoritative":
            stages.append(
                BaseStationAttachStageReceipt(
                    stage=stage,
                    requested=True,
                    applied=True,
                    status="confirmed",
                    evidence=capability.evidence,
                    reason="instrument-confirmed",
                    exchange_ids=(f"attach-{index}",),
                )
            )
        else:
            observed_diagnostic = (
                stage == "rrc_connected"
                and capability.evidence == "diagnostic_only"
            )
            stages.append(
                BaseStationAttachStageReceipt(
                    stage=stage,
                    requested=True,
                    applied=(True if observed_diagnostic else None),
                    status=("confirmed" if observed_diagnostic else "unknown"),
                    evidence=capability.evidence,
                    reason=capability.reason,
                    exchange_ids=((f"attach-{index}",) if observed_diagnostic else ()),
                )
            )
    return BaseStationAttachReceipt(
        schema_version=1,
        adapter_id=adapter,
        stages=tuple(stages),
        reason="current attach operation",
        simulated=False,
    )


@pytest.mark.parametrize(
    ("adapter", "manifest"),
    [
        ("cmw500", RealCmw500Driver.adapter_manifest),
        ("uxm", RealUxmDriver.adapter_manifest),
    ],
)
def test_writer_persists_same_vendor_neutral_attach_shape(
    adapter, manifest, monkeypatch
):
    execution = _execution(adapter=adapter)
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease(adapter),
    )

    confirm_base_station_attach(
        _Db(execution),
        execution.id,
        attempt_id="attempt-1",
        lease_identity=_lease(adapter),
        manifest=manifest,
        receipt=_receipt(adapter),
    )

    stored = execution.config["base_station_execution_evidence"]
    assert len(stored["attach_operations"]) == 1
    operation = stored["attach_operations"][0]
    assert operation["measurement_attempt_id"] == "attempt-1"
    assert operation["lease_id"] == "lease-1"
    assert operation["session_token"] == "session-1"
    assert operation["adapter"] == adapter
    assert [item["stage"] for item in operation["stages"]] == [
        "cell_ready",
        "ue_registered",
        "rrc_connected",
        "data_bearer_established",
    ]
    assert operation["formally_confirmed"] is (adapter == "cmw500")
    assert set(operation["exchange_ids"]).issubset(stored["exchange_ids"])


def test_writer_rejects_manifest_or_active_lease_mismatch(monkeypatch):
    execution = _execution(adapter="cmw500")
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("cmw500"),
    )

    with pytest.raises(ValueError, match="manifest"):
        confirm_base_station_attach(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease("cmw500"),
            manifest=RealUxmDriver.adapter_manifest,
            receipt=_receipt("cmw500"),
        )

    with pytest.raises(ValueError, match="lease identity"):
        confirm_base_station_attach(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=ActiveBaseStationLeaseIdentity(
                "lease-other", "attempt-1", "cmw500", "session-1"
            ),
            manifest=RealCmw500Driver.adapter_manifest,
            receipt=_receipt("cmw500"),
        )
    assert execution.config["base_station_execution_evidence"].get(
        "attach_operations", []
    ) == []


def test_writer_rejects_receipt_evidence_that_disagrees_with_manifest(monkeypatch):
    execution = _execution(adapter="cmw500")
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("cmw500"),
    )
    valid = _receipt("cmw500")
    stages = list(valid.stages)
    stages[0] = BaseStationAttachStageReceipt(
        stage="cell_ready",
        requested=True,
        applied=True,
        status="confirmed",
        evidence="diagnostic_only",
        reason="wrong evidence strength",
        exchange_ids=("attach-0",),
    )
    forged = BaseStationAttachReceipt(
        schema_version=1,
        adapter_id="cmw500",
        stages=tuple(stages),
        reason="forged",
        simulated=False,
    )

    with pytest.raises(ValueError, match="manifest"):
        confirm_base_station_attach(
            _Db(execution),
            execution.id,
            attempt_id="attempt-1",
            lease_identity=_lease("cmw500"),
            manifest=RealCmw500Driver.adapter_manifest,
            receipt=forged,
        )


@pytest.mark.asyncio
async def test_writer_accepts_simulated_unknown_attach_but_never_marks_it_formal(
    monkeypatch,
):
    execution = _execution(adapter="cmw500")
    execution.config["base_station_execution_evidence"]["execution_mode"] = (
        "simulated"
    )
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("cmw500"),
    )
    receipt = await registered_mock_base_station("mock-cmw", {"model": "CMW500"}).attach()

    confirm_base_station_attach(
        _Db(execution),
        execution.id,
        attempt_id="attempt-1",
        lease_identity=_lease("cmw500"),
        manifest=RealCmw500Driver.adapter_manifest,
        receipt=receipt,
    )

    operation = execution.config["base_station_execution_evidence"][
        "attach_operations"
    ][0]
    assert operation["simulated"] is True
    assert operation["formally_confirmed"] is False
    assert {item["status"] for item in operation["stages"]} == {"unknown"}
    assert {item["applied"] for item in operation["stages"]} == {None}
    assert (
        base_station_execution_evidence_is_formally_acceptable(
            execution.config["base_station_execution_evidence"]
        )
        is False
    )


def test_writer_rejects_duplicate_attach_for_same_attempt_and_lease(monkeypatch):
    execution = _execution(adapter="cmw500")
    db = _Db(execution)
    monkeypatch.setattr(
        evidence_writer,
        "active_base_station_lease_identity",
        lambda: _lease("cmw500"),
    )
    kwargs = {
        "attempt_id": "attempt-1",
        "lease_identity": _lease("cmw500"),
        "manifest": RealCmw500Driver.adapter_manifest,
        "receipt": _receipt("cmw500"),
    }
    confirm_base_station_attach(db, execution.id, **kwargs)

    with pytest.raises(ValueError, match="already persisted"):
        confirm_base_station_attach(db, execution.id, **kwargs)


def test_explicit_attach_evidence_is_a_formal_gate_but_legacy_absence_is_preserved():
    legacy = valid_cmw_evidence()
    assert "attach_operations" not in legacy
    assert parse_base_station_execution_evidence(legacy) == legacy
    assert base_station_execution_evidence_is_formally_acceptable(legacy) is True

    explicit_missing = deepcopy(legacy)
    explicit_missing["attach_operations"] = []
    assert parse_base_station_execution_evidence(explicit_missing) == explicit_missing
    assert (
        base_station_execution_evidence_is_formally_acceptable(explicit_missing)
        is False
    )

    explicit_current = deepcopy(legacy)
    explicit_current["attach_operations"] = [
        {
            "schema_version": 1,
            "measurement_attempt_id": "attempt-1",
            "lease_id": "lease-1",
            "adapter": "cmw500",
            "session_token": "session-1",
            "stages": [
                {
                    "stage": stage.stage,
                    "requested": stage.requested,
                    "applied": stage.applied,
                    "status": stage.status,
                    "evidence": stage.evidence,
                    "reason": stage.reason,
                    "exchange_ids": list(stage.exchange_ids),
                }
                for stage in _receipt("cmw500").stages
            ],
            "terminal_stage": "data_bearer_established",
            "formally_confirmed": True,
            "simulated": False,
            "reason": "current attach operation",
            "exchange_ids": ["attach-0", "attach-1", "attach-3"],
        }
    ]
    explicit_current["exchange_ids"].extend(
        ["attach-0", "attach-1", "attach-3"]
    )
    assert parse_base_station_execution_evidence(explicit_current) == explicit_current
    assert base_station_execution_evidence_is_formally_acceptable(explicit_current) is True

    explicit_current["attach_operations"][0]["session_token"] = "stale-session"
    assert base_station_execution_evidence_is_formally_acceptable(explicit_current) is False
