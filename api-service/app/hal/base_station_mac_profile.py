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

# UXM NR profile v1 value domain.  These are the same manual-audited ranges
# consumed by RealUxmDriver; keeping them here makes the canonical TestCase
# boundary reject an impossible profile before any instrument I/O.
UXM_NR_TDD_PERIOD_TOKENS = {
    "0.5MS": "MS0P5",
    "0.625MS": "MS0P625",
    "1MS": "MS1",
    "1.25MS": "MS1P25",
    "2MS": "MS2",
    "2.5MS": "MS2P5",
    "3MS": "MS3",
    "4MS": "MS4",
    "5MS": "MS5",
    "10MS": "MS10",
}
UXM_NR_HARQ_MAX_TRANS_VALUES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 28)
UXM_NR_HARQ_PROCESSES_VALUES = (1, 2, 4, 6, 8, 10, 12, 13, 14, 16, 32)
UXM_NR_SCS_VALUES = (15, 30, 60, 120)
UXM_NR_CSI_RS_PORTS_VALUES = (1, 2, 4, 8, 12, 16, 24, 32)
UXM_NR_MIMO_LAYERS_VALUES = (1, 2, 4)
UXM_NR_TDD_PERIOD_MS = {
    "0.5MS": 0.5,
    "0.625MS": 0.625,
    "1MS": 1.0,
    "1.25MS": 1.25,
    "2MS": 2.0,
    "2.5MS": 2.5,
    "3MS": 3.0,
    "4MS": 4.0,
    "5MS": 5.0,
    "10MS": 10.0,
}
UXM_NR_SLOT_DURATION_MS = {15: 1.0, 30: 0.5, 60: 0.25, 120: 0.125}

UxmNrTddPeriod = Literal[*tuple(UXM_NR_TDD_PERIOD_TOKENS)]
UxmNrHarqMaxTrans = Literal[*UXM_NR_HARQ_MAX_TRANS_VALUES]
UxmNrHarqProcesses = Literal[*UXM_NR_HARQ_PROCESSES_VALUES]
UxmNrScs = Literal[*UXM_NR_SCS_VALUES]
UxmNrCsiRsPorts = Literal[*UXM_NR_CSI_RS_PORTS_VALUES]
UxmNrMimoLayers = Literal[*UXM_NR_MIMO_LAYERS_VALUES]


def uxm_nr_tdd_period_for_pattern(
    *,
    tdd_pattern: str,
    subcarrier_spacing_khz: int,
) -> str:
    """Return the audited period token implied by one single-pattern window."""

    if subcarrier_spacing_khz not in UXM_NR_SLOT_DURATION_MS:
        raise ValueError("subcarrier spacing is outside the audited UXM NR domain")
    duration_ms = (
        len(tdd_pattern) * UXM_NR_SLOT_DURATION_MS[subcarrier_spacing_khz]
    )
    matches = tuple(
        token
        for token, period_ms in UXM_NR_TDD_PERIOD_MS.items()
        if abs(duration_ms - period_ms) <= 1e-9
    )
    if len(matches) != 1:
        raise ValueError(
            "TDD pattern duration is not an audited UXM period for this "
            "subcarrier spacing"
        )
    return matches[0]


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
    mimo_layers: UxmNrMimoLayers
    mcs: int = Field(ge=0, le=28)
    enable_amc: Literal[False]
    tdd_pattern: str = Field(min_length=1, pattern=r"^D*S?U*$")
    tdd_period: UxmNrTddPeriod
    harq_max_trans: UxmNrHarqMaxTrans
    harq_processes: UxmNrHarqProcesses
    subcarrier_spacing_khz: UxmNrScs
    csi_rs_ports: UxmNrCsiRsPorts
    source_reference: Literal[UXM_NR_PROFILE_SOURCE]

    @field_validator("tdd_pattern", mode="before")
    @classmethod
    def _valid_tdd_pattern(cls, value: str) -> str:
        normalized = value.strip().upper()
        return normalized

    @field_validator("tdd_period", mode="before")
    @classmethod
    def _valid_tdd_period(cls, value: str) -> str:
        normalized = value.strip().upper()
        return normalized

    @model_validator(mode="after")
    def _metric_contract_is_versioned(self) -> "NrMacTestProfileV1":
        actual = tuple((item.key, item.scope) for item in self.metric_requirements)
        if actual != _NR_V1_METRICS:
            raise ValueError("nr_throughput@1 metric requirements do not match its contract")
        implied_period = uxm_nr_tdd_period_for_pattern(
            tdd_pattern=self.tdd_pattern,
            subcarrier_spacing_khz=self.subcarrier_spacing_khz,
        )
        if implied_period != self.tdd_period:
            raise ValueError(
                "TDD pattern duration does not match subcarrier spacing and period"
            )
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


def build_mac_throughput_command_inputs(
    value: object,
) -> dict[str, object]:
    """Pure projection shared by real adapters and their scoped mock.

    This intentionally stops before SCPI construction: vendor command strings,
    live readbacks, and error-queue handling remain inside the real driver.
    """

    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    frozen = FrozenMacTestProfile.model_validate(raw)
    profile = frozen.profile
    if isinstance(profile, NrMacTestProfileV1):
        return {
            "mimo_layers": profile.mimo_layers,
            "mcs": profile.mcs,
            "rb_alloc": "ALL" if profile.rb_allocation == "all" else "",
            "enable_amc": profile.enable_amc,
            "tdd_pattern": profile.tdd_pattern,
            "tdd_period": profile.tdd_period,
            "harq_max_trans": profile.harq_max_trans,
            "harq_processes": profile.harq_processes,
            "stat_count": profile.statistical_window.count,
            "scs_khz": profile.subcarrier_spacing_khz,
            "csi_rs_ports": profile.csi_rs_ports,
            "profile_payload": profile.model_dump(mode="json"),
            "profile_digest": frozen.profile_digest,
        }
    if isinstance(profile, LteRmcMacTestProfileV1):
        return {
            "mimo_layers": profile.mimo_layers,
            "enable_amc": profile.enable_amc,
            "rb_alloc": "ALL" if profile.resource_allocation == "full" else "",
            "profile_digest": frozen.profile_digest,
        }
    raise TypeError("unsupported frozen MAC profile")
