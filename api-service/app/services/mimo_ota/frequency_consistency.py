"""P2-11 Phase 1: 多方频率一致性 fail-loud 校验.

架构原则 (docs/architecture/testcase-driven-instrument-config.md): TestCase 是频率
单一真值源；有完整身份的仪表配置后归一到 (中心 ARFCN, 带宽) 规范标识，必须
跟 TestCase **精确一致**。只能证明中心频率的观察值仍严格比 ARFCN，但把带宽列为
unknown、``fully_verified=False``，绝不补一个默认带宽。不一致 = 静默错配
(e.g. GCM 模式 TestCase 3500 但 F64 用默认 .smu 3600,
或 UXM 标称 3500 但没传 arfcn 实际下发 band fallback 基线值), fail-loud 拦住。

这是 silent-failure 防护 (P1-8 cal / P1-9 DUT / P1-12 未验证标记 同族): 不管配置来自
TestCase 还是默认 fallback, 最后都校验多方同频, 保护测试结果可信度。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Union

from app.hal.lte_earfcn import (
    lte_dl_earfcn_to_frequency_mhz,
    normalize_lte_band,
)

from app.hal.nr_arfcn import (
    FrequencyIdentity,
    freq_mhz_to_nr_arfcn,
    nr_arfcn_to_freq_mhz,
)


RadioTechnology = Literal["nr5g", "lte"]
ChannelKind = Literal["nr_arfcn", "lte_dl_earfcn"]


@dataclass(frozen=True)
class ChannelFrequencyIdentity:
    """RAT-aware canonical channel identity used by formal frequency gates.

    ``channel_number`` is deliberately namespaced by ``radio_technology`` and
    ``channel_kind``.  LTE EARFCN and NR-ARFCN may have the same integer value;
    treating that integer as an untyped slot would silently compare different
    radio systems.
    """

    radio_technology: RadioTechnology
    channel_kind: ChannelKind
    channel_number: int
    bandwidth_mhz: float
    band: Optional[str] = None

    def __post_init__(self) -> None:
        if self.radio_technology == "nr5g":
            if self.channel_kind != "nr_arfcn" or self.band is not None:
                raise ValueError("NR identity must use nr_arfcn without LTE band")
            nr_arfcn_to_freq_mhz(self.channel_number)
        elif self.radio_technology == "lte":
            if self.channel_kind != "lte_dl_earfcn" or self.band is None:
                raise ValueError("LTE identity must use lte_dl_earfcn with band")
            object.__setattr__(self, "band", normalize_lte_band(self.band))
            lte_dl_earfcn_to_frequency_mhz(self.band, self.channel_number)
        else:  # pragma: no cover - Literal is not a runtime boundary
            raise ValueError(f"unsupported radio technology: {self.radio_technology!r}")
        if not isinstance(self.channel_number, int):
            raise ValueError("channel_number must be an integer")
        if not isinstance(self.bandwidth_mhz, (int, float)) or self.bandwidth_mhz <= 0:
            raise ValueError("bandwidth_mhz must be positive")
        object.__setattr__(self, "bandwidth_mhz", float(self.bandwidth_mhz))

    @classmethod
    def from_nr_arfcn(
        cls, *, nr_arfcn: int, bandwidth_mhz: float
    ) -> "ChannelFrequencyIdentity":
        return cls(
            radio_technology="nr5g",
            channel_kind="nr_arfcn",
            channel_number=nr_arfcn,
            bandwidth_mhz=bandwidth_mhz,
        )

    @classmethod
    def from_nr_center_freq_mhz(
        cls, *, center_freq_mhz: float, bandwidth_mhz: float
    ) -> "ChannelFrequencyIdentity":
        return cls.from_nr_arfcn(
            nr_arfcn=freq_mhz_to_nr_arfcn(center_freq_mhz),
            bandwidth_mhz=bandwidth_mhz,
        )

    @classmethod
    def from_lte_earfcn(
        cls, *, band: str, dl_earfcn: int, bandwidth_mhz: float
    ) -> "ChannelFrequencyIdentity":
        return cls(
            radio_technology="lte",
            channel_kind="lte_dl_earfcn",
            channel_number=dl_earfcn,
            bandwidth_mhz=bandwidth_mhz,
            band=band,
        )

    @property
    def center_freq_mhz(self) -> float:
        if self.radio_technology == "nr5g":
            return nr_arfcn_to_freq_mhz(self.channel_number)
        assert self.band is not None
        return lte_dl_earfcn_to_frequency_mhz(self.band, self.channel_number)

    @property
    def center_frequency_hz(self) -> int:
        return round(self.center_freq_mhz * 1e6)

    @property
    def center_arfcn(self) -> int:
        if self.channel_kind != "nr_arfcn":
            raise AttributeError("LTE identity has no NR center_arfcn")
        return self.channel_number

    @property
    def lte_dl_earfcn(self) -> int:
        if self.channel_kind != "lte_dl_earfcn":
            raise AttributeError("NR identity has no LTE DL EARFCN")
        return self.channel_number

    def describe(self) -> str:
        if self.radio_technology == "nr5g":
            number = f"NR-ARFCN {self.channel_number}"
        else:
            number = f"LTE {self.band} EARFCN {self.channel_number}"
        return (
            f"{number} ({self.center_freq_mhz:.2f} MHz) / "
            f"BW {self.bandwidth_mhz:g} MHz"
        )


TypedFrequencyIdentity = Union[ChannelFrequencyIdentity, FrequencyIdentity]


def as_channel_frequency_identity(
    identity: TypedFrequencyIdentity,
) -> ChannelFrequencyIdentity:
    """Translate only the pre-P1-73 NR identity shape.

    This is deliberately narrow: a legacy ``FrequencyIdentity`` can only have
    come from the NR-only schema, so it may be labelled NR.  Untyped dicts,
    filenames, and bare numbers are not accepted here.
    """

    if isinstance(identity, ChannelFrequencyIdentity):
        return identity
    if isinstance(identity, FrequencyIdentity):
        return ChannelFrequencyIdentity.from_nr_arfcn(
            nr_arfcn=identity.center_arfcn,
            bandwidth_mhz=identity.bandwidth_mhz,
        )
    raise TypeError(f"unsupported frequency identity: {type(identity).__name__}")


@dataclass(frozen=True)
class CenterFrequencyObservation:
    """只有中心频率有实时证据、带宽未知的仪表观察值。"""

    center_frequency_hz: int
    source: str

    @classmethod
    def from_center_freq_mhz(
        cls, center_freq_mhz: float, *, source: str
    ) -> "CenterFrequencyObservation":
        return cls(
            center_frequency_hz=round(float(center_freq_mhz) * 1e6),
            source=source,
        )

    @property
    def center_freq_mhz(self) -> float:
        return self.center_frequency_hz / 1e6

    def describe(self) -> str:
        return (
            f"{self.center_freq_mhz:.2f} MHz / "
            f"BW unknown ({self.source})"
        )


@dataclass(frozen=True)
class FrequencyMismatch:
    instrument: str
    expected: str  # TestCase identity describe (真值)
    actual: str    # 仪表 identity describe (实际)


@dataclass
class FrequencyConsistencyResult:
    consistent: bool
    testcase_identity: str
    per_instrument: Dict[str, str]  # name → describe / "未报告(跳过)"
    mismatches: List[FrequencyMismatch] = field(default_factory=list)
    unverified: List[str] = field(default_factory=list)

    @property
    def fully_verified(self) -> bool:
        """中心/带宽均有可核对来源且无 mismatch。"""
        return self.consistent and not self.unverified

    def failure_reason(self) -> Optional[str]:
        if self.consistent:
            return None
        parts = [
            f"{m.instrument}=实际 {m.actual} (≠ TestCase {m.expected})"
            for m in self.mismatches
        ]
        return (
            "频率不一致 — 各仪表中心 ARFCN/带宽必须跟 TestCase 一致: "
            + "; ".join(parts)
        )

    def to_payload(self) -> Dict[str, object]:
        return {
            "consistent": self.consistent,
            "testcase_identity": self.testcase_identity,
            "per_instrument": self.per_instrument,
            "fully_verified": self.fully_verified,
            "unverified": list(self.unverified),
            "mismatches": [
                {"instrument": m.instrument, "expected": m.expected, "actual": m.actual}
                for m in self.mismatches
            ],
        }


def check_frequency_consistency(
    testcase: TypedFrequencyIdentity,
    instruments: Dict[
        str, Optional[Union[TypedFrequencyIdentity, CenterFrequencyObservation]]
    ],
) -> FrequencyConsistencyResult:
    """校验各仪表频率规范标识跟 TestCase 精确一致。

    Args:
        testcase: TestCase 派生的频率规范标识 (真值源)。
        instruments: ``{仪表名: Optional[FrequencyIdentity]}``。``None`` = 该仪表无
            频率可报；不制造 mismatch，但必须列为 unverified，不能据此发布
            ``fully_verified=true``。

    Returns:
        FrequencyConsistencyResult: ``consistent`` + 每仪表 identity + mismatch 列表。
        比对是精确的 (FrequencyIdentity 相等 = ARFCN 整数 + 带宽都相等)。
    """
    expected = as_channel_frequency_identity(testcase)
    per_instrument: Dict[str, str] = {}
    mismatches: List[FrequencyMismatch] = []
    unverified: List[str] = []
    for name, ident in instruments.items():
        if ident is None:
            per_instrument[name] = "未报告(跳过)"
            unverified.append(name)
            continue
        per_instrument[name] = ident.describe()
        if isinstance(ident, CenterFrequencyObservation):
            unverified.append(name)
            matches = ident.center_frequency_hz == expected.center_frequency_hz
        else:
            ident = as_channel_frequency_identity(ident)
            matches = ident == expected
        if not matches:
            mismatches.append(
                FrequencyMismatch(
                    instrument=name,
                    expected=expected.describe(),
                    actual=ident.describe(),
                )
            )
    return FrequencyConsistencyResult(
        consistent=not mismatches,
        testcase_identity=expected.describe(),
        per_instrument=per_instrument,
        mismatches=mismatches,
        unverified=unverified,
    )
