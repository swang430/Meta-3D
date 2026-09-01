"""Vendor-neutral, execution-frozen BaseStation MAC test profiles.

The profile is platform-owned intent.  Adapter-specific command mapping stays
inside each driver and must cite its own manual sources; this module contains
no SCPI and never infers unsupported vendor semantics.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


UXM_NR_PROFILE_SOURCE = (
    "Instrument_API_Doc/Keysight UXM NR SCPI/"
    "5G_NR_Test_Application_SCPI_Reference.zip"
)
CMW500_LTE_PROFILE_SOURCE = (
    "Instrument_API_Doc/R&S CMW500/"
    "CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf"
)

_METRIC_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NR_V1_METRICS = (("dl_throughput_mbps", "pcell"),)
_LTE_RMC_V1_METRICS = (
    ("dl_throughput_mbps", "pcell"),
    ("dl_bler_percent", "pcell"),
)


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class MacStatisticalWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: Literal["subframes"]
    count: int = Field(gt=0)


class MacMetricRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    scope: Literal["pcell", "all_cells"]

    @field_validator("key")
    @classmethod
    def _stable_metric_key(cls, value: str) -> str:
        if not _METRIC_KEY_RE.fullmatch(value):
            raise ValueError("metric requirement key must be a stable token")
        return value


class _MacTestProfileBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    profile_version: Literal[1]
    test_intent: Literal["downlink_throughput"]
    mimo_layers: int = Field(ge=1, le=8)
    statistical_window: MacStatisticalWindow
    metric_requirements: tuple[MacMetricRequirement, ...]
    source_reference: str

    @field_validator("metric_requirements")
    @classmethod
    def _unique_metric_requirements(
        cls, values: tuple[MacMetricRequirement, ...]
    ) -> tuple[MacMetricRequirement, ...]:
        if not values:
            raise ValueError("metric_requirements must not be empty")
        identities = tuple((item.key, item.scope) for item in values)
        if len(set(identities)) != len(identities):
            raise ValueError("metric_requirements must be unique")
        return values


class NrMacTestProfileV1(_MacTestProfileBase):
    kind: Literal["nr_throughput"]
    rat: Literal["nr5g"]
    rb_allocation: Literal["all"]
    scheduler_algorithm: Literal["full_throughput"]
    mcs: int = Field(ge=0)
    enable_amc: bool
    tdd_pattern: str = Field(min_length=1)
    tdd_period: str = Field(min_length=1)
    harq_max_trans: int = Field(gt=0)
    harq_processes: int = Field(gt=0)
    subcarrier_spacing_khz: int = Field(gt=0)
    csi_rs_ports: int = Field(gt=0)
    source_reference: Literal[UXM_NR_PROFILE_SOURCE]

    @model_validator(mode="after")
    def _metric_contract_is_versioned(self) -> "NrMacTestProfileV1":
        actual = tuple((item.key, item.scope) for item in self.metric_requirements)
        if actual != _NR_V1_METRICS:
            raise ValueError("nr_throughput@1 metric requirements do not match its contract")
        return self


class LteRmcMacTestProfileV1(_MacTestProfileBase):
    """The exact, deliberately narrow LTE shape implemented today.

    It declares fixed FDD/full-resource RMC only.  Future LTE schedulers need a
    new profile version rather than silently borrowing NR controls.
    """

    kind: Literal["lte_rmc"]
    rat: Literal["lte"]
    scheduling_mode: Literal["rmc"]
    resource_allocation: Literal["full"]
    enable_amc: Literal[False]
    duplex: Literal["fdd"]
    transmission_mode: Literal["TM3"]
    mimo_layers: Literal[2]
    source_reference: Literal[CMW500_LTE_PROFILE_SOURCE]

    @model_validator(mode="after")
    def _metric_contract_is_versioned(self) -> "LteRmcMacTestProfileV1":
        actual = tuple((item.key, item.scope) for item in self.metric_requirements)
        if actual != _LTE_RMC_V1_METRICS:
            raise ValueError("lte_rmc@1 metric requirements do not match its contract")
        return self


MacTestProfile = Annotated[
    NrMacTestProfileV1 | LteRmcMacTestProfileV1,
    Field(discriminator="kind"),
]
_MAC_PROFILE_ADAPTER = TypeAdapter(MacTestProfile)


class FrozenMacTestProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: MacTestProfile
    profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def freeze(cls, profile: MacTestProfile) -> "FrozenMacTestProfile":
        # Revalidate model_copy(update=...) values too; Pydantic deliberately
        # does not validate those updates by default.
        validated = _MAC_PROFILE_ADAPTER.validate_python(
            profile.model_dump(mode="json")
        )
        payload = validated.model_dump(mode="json")
        return cls(profile=validated, profile_digest=_canonical_digest(payload))

    @model_validator(mode="after")
    def _digest_matches_profile(self) -> "FrozenMacTestProfile":
        expected = _canonical_digest(self.profile.model_dump(mode="json"))
        if self.profile_digest != expected:
            raise ValueError("profile_digest does not match the frozen profile")
        return self


def require_frozen_mac_profile(
    value: object,
    *,
    expected_kind: str,
    expected_rat: Literal["lte", "nr5g"],
) -> FrozenMacTestProfile:
    """Revalidate a frozen profile and narrow it before any adapter I/O."""

    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    try:
        frozen = FrozenMacTestProfile.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"invalid frozen MAC profile: {exc}") from exc
    if (
        frozen.profile.kind != expected_kind
        or frozen.profile.rat != expected_rat
    ):
        raise ValueError(
            "frozen MAC profile is incompatible with this adapter: "
            f"expected {expected_kind}@{expected_rat}, got "
            f"{frozen.profile.kind}@{frozen.profile.rat}"
        )
    return frozen
