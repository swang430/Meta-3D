"""Vendor-neutral, execution-frozen BaseStation MAC test profiles.

The profile is platform-owned intent.  Adapter-specific command mapping stays
inside each driver and must cite its own manual sources; this module contains
no SCPI and never infers unsupported vendor semantics.

值域常量下方的出处注释里出现的命令名只是**手册坐标**（用来定位那一条 Range 原文），
不是可下发的命令模板 —— 模板仍然只住在 `uxm_command_profiles.py` / 各驱动里。
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

# ── UXM NR profile v1 值域 ──────────────────────────────────────────────
# 这些是 RealUxmDriver 消费的同一批范围；放在这里，让 TestCase 边界在任何仪表 I/O
# 之前就拒掉不可能的 profile。
#
# 出处坐标 = 归档内的 **Section 路径 + Setting Name + SCPI 命令**，Range 为原文摘录，
# 逐条核对日期 2026-09-02。归档即 UXM_NR_PROFILE_SOURCE，解开后是单个
# `5G_NR_Test_Application_SCPI_Reference.html`。
# ⚠️ 不用页码或行号：那份 HTML 没有稳定页码，本机把它转成的任何 markdown 都是
#    **未入库的中间产物**，行号只在转换者自己的机器上成立，别人 clone 后无从复现。
#
# ⚠️ 出处只写在这里，**不要改 UXM_NR_PROFILE_SOURCE 的字面值** —— 它是 profile 的
#    Literal 字段并进 `profile_digest`，改字面值会让所有已冻结的历史 profile
#    连 model_validate 都过不去。
#
# 手册：「NR Scheduling > TDD UL-DL Config > Pattern 1」
#       Setting Name `Tx Periodicity (P)`
#       SCPI `BSE:CONFig:NR5G:<cell>:SCHeduling:TDDPATtern:PERiod`
#       Type `Enum`，Default `MS5`
#       Range `MS0P5 | MS0P625 | MS1 | MS1P25 | MS2 | MS2P5 | MS3 | MS4 | MS5 | MS10`
#       ← 本字典的键 = 该 Range 全集，逐个对应。
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
# 手册：「NR PHY > HARQ > DL HARQ Configuration」Setting Name `Max DL HARQ Transmissions`
#       SCPI `BSE:CONFig:NR5G:<cell>:PHY:DL:HARQ:MAXTrans`
#       Type `Enum`，Default `N4`
#       Range `N1 | N2 | N3 | N4 | N5 | N6 | N7 | N8 | N10 | N12 | N16 | N20 | N24 | N28`
#       ← 本元组 = 该 Range 去掉 `N` 前缀后的全集（驱动侧再拼回 token）。
UXM_NR_HARQ_MAX_TRANS_VALUES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 28)
# 手册：「NR PHY > HARQ > DL HARQ Configuration」Setting Name `Number of DL HARQ Processes`
#       SCPI `BSE:CONFig:NR5G:<cell>:PHY:DL:HARQ:PROCesses`
#       Type `Enum`，Default `N16`
#       Range `N1 | N2 | N4 | N6 | N8 | N10 | N12 | N13 | N14 | N16 | N32`
#       Notes `n32 value only applied when running in release 17 mode`
#       ← 本元组 = 该 Range 全集；32 是否真正生效由仪器的 release 模式决定，
#         schema 放行它不等于任意固件都接受。
UXM_NR_HARQ_PROCESSES_VALUES = (1, 2, 4, 6, 8, 10, 12, 13, 14, 16, 32)
# 手册：「NR Scheduling > TDD UL-DL Config > Common Pattern Configuration」
#       Setting Name `Reference SCS`
#       SCPI `BSE:CONFig:NR5G:<cell>:SCHeduling:TDDPATtern:SUBCarrier:SPACing`
#       Type `Enum`，Default `MU1`，Range `MU0 | MU1 | MU2 | MU3`
#       μ→kHz 换算见「NR Cell > Config > RF Common」的 Subcarrier Spacing Common
#       表：`0 (15 kHz)` / `1 (30 kHz)` / `2 (60 kHz)` / `3 (120 kHz)`。
#       ← 本元组 = 该表的 kHz 列全集，与 MU0..MU3 一一对应。
UXM_NR_SCS_VALUES = (15, 30, 60, 120)
# 手册：「NR Beams > Config > NZP CSI-RS Resources」
#       Setting Name `NZP CSI-RS Resource RM Number Of Ports`
#       SCPI `BSE:CONFig:NR5G:<cell>:CSI:RESource:CONFig:NZP:<cri>:RM:NPORts`
#       Type `Enum`，Default `P1`
#       Range `P1 | P2 | P4 | P8 | P12 | P16 | P24 | P32`
#       GUI Range `1 | 2 | 4 | 8 | 12 | 16 | 24 | 32`
#       ← 本元组 = GUI Range 全集（裸整数），驱动侧拼成 `P<n>` token 下发。
UXM_NR_CSI_RS_PORTS_VALUES = (1, 2, 4, 8, 12, 16, 24, 32)
# 手册：「NR PHY > PDSCH > General」Setting Name `PDSCH Max MIMO Layers`
#       SCPI `BSE:CONFig:NR5G:<cell>:PHY:PDSCh:MAX:MIMOlayers`
#       Type `Integer`，Default `2`，**Range `0..8`**
# ⚠️ 本元组 (1, 2, 4) 是**平台侧收窄，不是手册限制**：手册允许 0..8 的任意整数。
#    1/2/4 是 HAL BaseStation 接口既有的层数契约（`base_station.py` 的
#    `configure_mac_throughput_test` docstring 写「mimo_layers: int, MIMO 层数 (1/2/4)」，
#    UXM/CMW500 两个驱动的 docstring 同口径），仓库内全部基线 TestCase profile
#    （`uxm_test_profiles.py`）的 mimo_layers 也只用到这三个值。本模块把这条既有约定
#    固化进 schema，既没放宽也没收紧。收窄方向是拒绝更多、不是放行更多，故 fail-closed。
#    要放开某一层数，先补齐该层数在驱动侧的下发与回读证据，别只改这里。
#
#    ⚠ 别把它跟 `mimo_port_preset`（siso / 2x2 / 2x2_alt / 4x4）当成同一个轴：那是
#      独立的配置键，走 `set_mimo_port_mapping`，跟本值域之间没有映射关系 ——
#      基线里就有 2 layer 配 `4x4` 预设的组合（`uxm_test_profiles.py` 的 N78 profile）。
UXM_NR_MIMO_LAYERS_VALUES = (1, 2, 4)
# 派生表：把上面 Range 里的 token 字面量翻成毫秒数值。手册对该设置的描述是
# “Specifies the periodicity of the TDD UL-DL pattern 1 in ms”，token 名即毫秒数
# （`MS0P625` = 0.625 ms），本表不引入手册以外的取值。
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
# 派生表：slot 时长 = 10 ms 帧长 / 每帧 slot 数。每帧 slot 数取自
# 「NR Cell > Config > RF Common」Subcarrier Spacing Common 表的 Slots Per Frame 列：15 kHz→10、30 kHz→20、60 kHz→40、120 kHz→80。
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
    # 与 NrMacTestProfileV1._valid_tdd_pattern 的规范化同源（strip().upper()）：
    # 该 validator 是 mode="before"，而本函数在 canonicalize 阶段先于它执行。
    # 不在这里 strip，`" DDDDDDDSUU "` 会按 12 个时隙算出 6 ms 而被拒，
    # 但同一个值配上显式 tdd_period 却能通过并被规范化成 10 个时隙 —— 自相矛盾。
    duration_ms = (
        len(tdd_pattern.strip()) * UXM_NR_SLOT_DURATION_MS[subcarrier_spacing_khz]
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


def _profile_payload_digest(profile: BaseModel) -> str:
    """frozen profile 的**唯一** digest 口径：omit-when-None。

    两件事各自要求它是唯一的一处：

    ① **omit-when-None**（与 `BaseStationExecutionRequirements.digest`、
       P1-74 statistical_basis 同款）：profile 以后每加一个可选字段，
       旧 payload 缺该键、新代码填默认 `None`，若 `None` 进 digest 就会让
       **所有升级前冻结的 profile** 重算出不同的 digest —— `FrozenMacTestProfile`
       的 `_digest_matches_profile` 当场拒，历史 TestCase 配置整体加载不了。
       实测对现存两条 digest 是 **no-op**：本片同时给 LTE profile 加的三个
       字段恒为 `None`，正好被 `exclude_none` 丢掉，dump 出来与加字段之前
       逐字相同（`6c0ebb0e…` / `2aa1dc79…`，门里钉了 hex 基线，退化会红）；
       两个 profile 的其余字段都不可为 `None`，嵌套里也没有别的 `None` 被
       顺带丢掉。

    ② **唯一**：`freeze()` 与 `_digest_matches_profile()` 是同一口径的两个
       站点。分开各写一次 `model_dump` 正是「改了值没追全下游」的形态 ——
       只给其中一处加 `exclude_none`，冻出来的 digest 与校验时算的对不上，
       每一条新冻结的 profile 都会自我拒绝。
    """

    return _canonical_digest(profile.model_dump(mode="json", exclude_none=True))


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
    def _valid_tdd_pattern(cls, value: object) -> object:
        # 非字符串（含显式 null）原样放行，由字段类型校验给出受控的字段级错误。
        # 直接 .strip() 会以 AttributeError 崩在校验之前，那既不是受控拒绝，
        # 报错也指不到是哪个字段。
        if not isinstance(value, str):
            return value
        return value.strip().upper()

    @field_validator("tdd_period", mode="before")
    @classmethod
    def _valid_tdd_period(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().upper()

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
    # ── P2-56：LTE TDD 专属维度。**今天只接受 None** ────────────────────
    # 取值域已按手册在 CMW500 能力矩阵里逐值声明（ULDL `0 to 6` p.687-688 /
    # SSUBframe `0 to 9` p.688 / RMC:VERSion:DL `0 to 1` p.803），但本驱动
    # **没有它们的下发路径** —— configure_mac_throughput_test 在活体
    # duplex≠FDD 时整体 fail-loud。
    #
    # 字段先存在，是因为能力矩阵的**维度名必须是 profile 上真实存在的字段**：
    # 判定器按 `dimension in type(profile).model_fields` 取值，声明一个
    # profile 没有的维度会把**每一条** LTE profile 判成不兼容
    # （见 base_station_compatibility._mac_dimension_rejections）。
    #
    # 用 `None` 而不是放开取值域，是为了让本片**不新增任何可达状态**：
    # 放开 Literal 会立刻造出「profile 说 TDD、仪器活体是 FDD」这一格，
    # 而驱动今天只拿活体 duplex 跟字面量 "FDD" 比、从不跟 profile 比 ——
    # 那会把 TDD 用例静默按 FDD 配掉。放开取值域属现场半，要连带补
    # 下发路径 + 活体 duplex 与本字段的一致性校验，两件一起做。
    uldl_configuration: None = None
    special_subframe: None = None
    rmc_version: None = None

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
        return cls(
            profile=validated, profile_digest=_profile_payload_digest(validated)
        )

    @model_validator(mode="after")
    def _digest_matches_profile(self) -> "FrozenMacTestProfile":
        expected = _profile_payload_digest(self.profile)
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
