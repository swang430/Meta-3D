from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

from dataclasses import FrozenInstanceError

import pytest

from app.hal.base_station import (
    BaseStationAttachReceipt,
    BaseStationAttachStageReceipt,
    MockBaseStation,
)


STAGES = (
    "cell_ready",
    "ue_registered",
    "rrc_connected",
    "data_bearer_established",
)


def _stage(
    stage: str,
    *,
    applied: bool | None = True,
    status: str = "confirmed",
    evidence: str = "authoritative",
    exchange_ids: tuple[str, ...] = ("exchange-1",),
) -> BaseStationAttachStageReceipt:
    return BaseStationAttachStageReceipt(
        stage=stage,
        requested=True if status != "not_applicable" else None,
        applied=applied,
        status=status,
        evidence=evidence,
        reason="test stage truth",
        exchange_ids=exchange_ids,
    )


def _receipt(
    stages: tuple[BaseStationAttachStageReceipt, ...],
    *,
    simulated: bool = False,
    operation_succeeded: bool | None = None,
) -> BaseStationAttachReceipt:
    return BaseStationAttachReceipt(
        schema_version=1,
        adapter_id="test-adapter",
        stages=stages,
        reason="test attach operation",
        simulated=simulated,
        operation_succeeded=operation_succeeded,
    )


def test_stage_receipt_distinguishes_confirmed_false_from_unknown_and_na():
    confirmed_false = _stage("cell_ready", applied=False)
    assert confirmed_false.status == "confirmed"
    assert confirmed_false.applied is False

    unknown = _stage(
        "ue_registered",
        applied=None,
        status="unknown",
        evidence="diagnostic_only",
        exchange_ids=(),
    )
    assert unknown.applied is None

    not_applicable = BaseStationAttachStageReceipt(
        stage="data_bearer_established",
        requested=None,
        applied=None,
        status="not_applicable",
        evidence="not_applicable",
        reason="stage does not apply",
    )
    assert not_applicable.status == "not_applicable"


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {"applied": None, "status": "confirmed"},
            "confirmed stage requires applied truth",
        ),
        (
            {"applied": True, "status": "unknown", "exchange_ids": ()},
            "unknown stage cannot carry applied truth",
        ),
        (
            {
                "applied": None,
                "status": "confirmed",
                "evidence": "unavailable",
            },
            "unavailable stage must be unknown",
        ),
        (
            {
                "applied": None,
                "status": "unknown",
                "evidence": "not_applicable",
                "exchange_ids": (),
            },
            "not-applicable evidence requires not-applicable status",
        ),
        (
            {"applied": True, "status": "confirmed", "exchange_ids": ()},
            "confirmed stage requires exchange ids",
        ),
    ],
)
def test_stage_receipt_rejects_inconsistent_truth(kwargs, match):
    with pytest.raises((TypeError, ValueError), match=match):
        _stage("cell_ready", **kwargs)


def test_attach_receipt_requires_the_exact_four_stage_order():
    valid = tuple(_stage(stage, exchange_ids=(f"exchange-{idx}",)) for idx, stage in enumerate(STAGES))
    assert _receipt(valid).terminal_stage == "data_bearer_established"

    with pytest.raises(ValueError, match="exact ordered attach stages"):
        _receipt(valid[:-1])
    with pytest.raises(ValueError, match="exact ordered attach stages"):
        _receipt(tuple(reversed(valid)))


def test_terminal_stage_and_formal_confirmation_preserve_evidence_strength():
    cmw = _receipt(
        (
            _stage("cell_ready", exchange_ids=("cell",)),
            _stage("ue_registered", exchange_ids=("registration",)),
            _stage(
                "rrc_connected",
                applied=None,
                status="unknown",
                evidence="unavailable",
                exchange_ids=(),
            ),
            _stage("data_bearer_established", exchange_ids=("bearer",)),
        )
    )
    assert cmw.terminal_stage == "data_bearer_established"
    assert cmw.diagnostic_execution_allowed is True
    assert cmw.formally_confirmed is True
    assert cmw.exchange_ids == ("cell", "registration", "bearer")

    uxm = _receipt(
        (
            _stage(
                "cell_ready",
                applied=None,
                status="unknown",
                evidence="diagnostic_only",
                exchange_ids=(),
            ),
            _stage(
                "ue_registered",
                applied=None,
                status="unknown",
                evidence="diagnostic_only",
                exchange_ids=(),
            ),
            _stage(
                "rrc_connected",
                evidence="diagnostic_only",
                exchange_ids=("connected",),
            ),
            _stage(
                "data_bearer_established",
                applied=None,
                status="unknown",
                evidence="unavailable",
                exchange_ids=(),
            ),
        )
    )
    assert uxm.terminal_stage == "rrc_connected"
    assert uxm.diagnostic_execution_allowed is True
    assert uxm.formally_confirmed is False


def test_receipt_is_immutable_and_cannot_be_implicitly_used_as_bool():
    receipt = _receipt(
        tuple(_stage(stage, exchange_ids=(f"exchange-{idx}",)) for idx, stage in enumerate(STAGES))
    )
    with pytest.raises(FrozenInstanceError):
        receipt.reason = "changed"
    with pytest.raises(TypeError, match="must not be used as bool"):
        bool(receipt)


@pytest.mark.asyncio
async def test_mock_attach_is_simulated_unknown_but_keeps_explicit_diagnostic_flow():
    driver = registered_mock_base_station("mock-bs", {"model": "UXM 5G E7515B"})
    receipt = await driver.attach(timeout_s=0.01)

    assert receipt.simulated is True
    assert receipt.operation_succeeded is True
    assert receipt.diagnostic_execution_allowed is True
    assert receipt.formally_confirmed is False
    assert all(stage.status == "unknown" for stage in receipt.stages)
    assert all(stage.applied is None for stage in receipt.stages)
    assert receipt.exchange_ids == ()
    assert await driver.start_signaling(timeout_s=0.01) is True
