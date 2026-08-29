from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from app.hal.base_station import (
    BaseStationMetricObservation,
    BaseStationMetricRegistry,
)
from app.hal.base_station_manifest import BaseStationMetricCapability


def _metric(
    key: str = "dl_bler_ratio",
    *,
    direction: str = "downlink",
    unit: str = "ratio",
    scopes: tuple[str, ...] = ("pcell",),
    evidence: str = "authoritative",
    source_reference: str | None = "UXM NR BLER/Tput > DL OTA",
) -> BaseStationMetricCapability:
    return BaseStationMetricCapability(
        key=key,
        direction=direction,
        unit=unit,
        scopes=scopes,
        evidence=evidence,
        source_reference=source_reference,
    )


def _registry(
    *metrics: BaseStationMetricCapability,
) -> BaseStationMetricRegistry:
    return BaseStationMetricRegistry(
        schema_version=1,
        adapter_id="uxm",
        profile_id="lte_nr_irat",
        metrics=metrics or (_metric(),),
    )


def test_metric_capability_accepts_ratio_without_relabeling_as_percent():
    metric = _metric()

    assert metric.key == "dl_bler_ratio"
    assert metric.unit == "ratio"


@pytest.mark.parametrize("field,value", [("adapter_id", ""), ("profile_id", "NR 5G")])
def test_metric_registry_rejects_invalid_identity(field: str, value: str):
    payload = {
        "schema_version": 1,
        "adapter_id": "uxm",
        "profile_id": "lte_nr_irat",
        "metrics": (_metric(),),
    }
    payload[field] = value

    with pytest.raises(ValueError):
        BaseStationMetricRegistry(**payload)


def test_metric_registry_requires_unique_stably_sorted_keys():
    dl = _metric(key="dl_throughput_mbps", unit="mbps")
    ul = _metric(
        key="ul_throughput_mbps",
        direction="uplink",
        unit="mbps",
    )

    with pytest.raises(ValueError, match="sorted"):
        _registry(ul, dl)
    with pytest.raises(ValueError, match="unique"):
        _registry(dl, dl)


def test_metric_registry_digest_is_canonical_and_content_sensitive():
    first = _registry(_metric())
    same = _registry(_metric())
    changed = _registry(
        _metric(evidence="diagnostic_only", source_reference=None)
    )

    assert first.digest == same.digest
    assert first.digest != changed.digest
    assert len(first.digest) == 64
    with pytest.raises(TypeError, match="must not be used as bool"):
        bool(first)


def test_metric_registry_is_deeply_immutable():
    registry = _registry()

    with pytest.raises(FrozenInstanceError):
        registry.profile_id = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        registry.metrics[0].unit = "percent"  # type: ignore[misc]


def test_metric_observation_binds_declared_key_scope_and_registry_digest():
    registry = _registry()

    observation = BaseStationMetricObservation(
        schema_version=1,
        registry=registry,
        registry_digest=registry.digest,
        key="dl_bler_ratio",
        scope="pcell",
        value=0.125,
        simulated=False,
        exchange_ids=("exchange-1",),
        reason="authoritative current-window readback",
    )

    assert observation.value == pytest.approx(0.125)
    assert observation.capability.unit == "ratio"
    assert observation.metric_semantics_confirmed is True
    with pytest.raises(TypeError, match="must not be used as bool"):
        bool(observation)


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"registry_digest": "0" * 64}, "digest"),
        ({"key": "ul_bler_ratio"}, "declared"),
        ({"scope": "all_cells"}, "scope"),
        ({"value": float("nan")}, "finite"),
        ({"value": float("inf")}, "finite"),
        ({"exchange_ids": ("same", "same")}, "unique"),
        ({"exchange_ids": ("",)}, "non-empty"),
    ],
)
def test_metric_observation_rejects_untrusted_shapes(overrides, match: str):
    registry = _registry()
    payload = {
        "schema_version": 1,
        "registry": registry,
        "registry_digest": registry.digest,
        "key": "dl_bler_ratio",
        "scope": "pcell",
        "value": 0.125,
        "simulated": False,
        "exchange_ids": ("exchange-1",),
        "reason": "current-window readback",
    }
    payload.update(overrides)

    with pytest.raises((TypeError, ValueError), match=match):
        BaseStationMetricObservation(**payload)


def test_unknown_and_simulated_observations_never_confirm_metric_semantics():
    registry = _registry()

    unknown = BaseStationMetricObservation(
        schema_version=1,
        registry=registry,
        registry_digest=registry.digest,
        key="dl_bler_ratio",
        scope="pcell",
        value=None,
        simulated=False,
        exchange_ids=("query-failed",),
        reason="instrument query failed",
    )
    simulated = BaseStationMetricObservation(
        schema_version=1,
        registry=registry,
        registry_digest=registry.digest,
        key="dl_bler_ratio",
        scope="pcell",
        value=0.125,
        simulated=True,
        exchange_ids=("mock-exchange",),
        reason="simulated diagnostic value",
    )

    assert unknown.metric_semantics_confirmed is False
    assert simulated.metric_semantics_confirmed is False


def test_diagnostic_capability_cannot_confirm_metric_semantics():
    registry = _registry(
        _metric(evidence="diagnostic_only", source_reference=None)
    )
    observation = BaseStationMetricObservation(
        schema_version=1,
        registry=registry,
        registry_digest=registry.digest,
        key="dl_bler_ratio",
        scope="pcell",
        value=0.125,
        simulated=False,
        exchange_ids=("exchange-1",),
        reason="diagnostic-only instrument value",
    )

    assert observation.metric_semantics_confirmed is False
