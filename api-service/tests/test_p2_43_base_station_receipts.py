"""P2-43：vendor-neutral BaseStation apply receipt 不变量。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.hal.base_station import (
    BaseStationApplyReceipt,
    BaseStationFieldReceipt,
)


def _field(
    name: str,
    *,
    requested=1,
    applied=1,
    status: str = "confirmed",
    exchange_ids: tuple[str, ...] = ("exchange-1",),
) -> BaseStationFieldReceipt:
    return BaseStationFieldReceipt(
        field=name,
        requested=requested,
        applied=applied,
        status=status,
        reason=f"{name}:{status}",
        exchange_ids=exchange_ids,
    )


def test_confirmed_field_requires_exact_authoritative_readback():
    with pytest.raises(ValueError, match="confirmed field.*match"):
        _field("bandwidth_mhz", requested=20, applied=10)

    with pytest.raises(ValueError, match="confirmed field.*applied"):
        _field("bandwidth_mhz", requested=20, applied=None)


def test_unknown_field_cannot_carry_requested_or_cached_value_as_applied():
    with pytest.raises(ValueError, match="unknown field.*applied"):
        _field(
            "lte_transmission_mode",
            requested="TM3",
            applied="TM3",
            status="unknown",
        )

    receipt = _field(
        "lte_transmission_mode",
        requested="TM3",
        applied=None,
        status="unknown",
    )
    assert receipt.applied is None


def test_not_applicable_is_distinct_from_unknown_readback():
    receipt = _field(
        "route",
        requested=None,
        applied=None,
        status="not_applicable",
        exchange_ids=(),
    )
    assert receipt.status == "not_applicable"

    with pytest.raises(ValueError, match="not_applicable field"):
        _field(
            "route",
            requested={"port": "RF1"},
            applied=None,
            status="not_applicable",
            exchange_ids=(),
        )


def test_apply_confirmation_is_derived_from_every_applicable_field():
    confirmed = BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=(
            _field("bandwidth_mhz", requested=20, applied=20),
            _field(
                "route",
                requested=None,
                applied=None,
                status="not_applicable",
                exchange_ids=(),
            ),
        ),
        reason="authoritative readback complete",
        simulated=False,
    )
    assert confirmed.confirmed is True
    assert confirmed.exchange_ids == ("exchange-1",)

    partial = BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=(
            _field("bandwidth_mhz", requested=20, applied=20),
            _field(
                "mimo_layers",
                requested=2,
                applied=None,
                status="unknown",
                exchange_ids=("exchange-2",),
            ),
        ),
        reason="partial readback",
        simulated=False,
    )
    assert partial.confirmed is False
    assert partial.exchange_ids == ("exchange-1", "exchange-2")


def test_apply_receipt_rejects_duplicate_fields_but_allows_shared_evidence():
    with pytest.raises(ValueError, match="field names must be unique"):
        BaseStationApplyReceipt(
            schema_version=1,
            operation="config",
            fields=(_field("band"), _field("band")),
            reason="duplicate",
            simulated=False,
        )

    receipt = BaseStationApplyReceipt(
        schema_version=1,
        operation="config",
        fields=(
            _field("band", exchange_ids=("shared", "band-only")),
            _field("bandwidth", exchange_ids=("shared", "bandwidth-only")),
        ),
        reason="one authoritative query may prove multiple fields",
        simulated=False,
    )
    assert receipt.exchange_ids == (
        "shared",
        "band-only",
        "bandwidth-only",
    )


def test_receipts_are_immutable_and_adapter_id_is_not_vendor_literal():
    receipt = _field("band")
    with pytest.raises(FrozenInstanceError):
        receipt.status = "unknown"

    from app.hal.base_station import BaseStationIdentity

    third_party = BaseStationIdentity(
        adapter_id="future-bs",
        model="Future BS",
        firmware_version=None,
        options=(),
    )
    assert third_party.adapter_id == "future-bs"


@pytest.mark.parametrize("bad", ["", " ", "exchange-1"])
def test_exchange_ids_must_be_nonempty_and_unique_within_a_field(bad: str):
    exchange_ids = (bad,) if bad != "exchange-1" else (bad, bad)
    with pytest.raises(ValueError, match="exchange ids"):
        _field("band", exchange_ids=exchange_ids)
