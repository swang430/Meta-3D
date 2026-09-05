"""MIMO_OTA TestCase configuration schema.

Mirrors what the legacy `commissioning_config.StaticMIMOConfig` dataclass
held, but lives inside `TestCase.configuration` (JSON) so it travels with the
TestCase row instead of being a process-memory thing. Also defines the canonical
step-type strings used by the ExecutorRegistry.

═══════════════════════════════════════════════════════════════════════════
RECONCILIATION NOTE — read before adding a 2nd test_type schema (TRP/TIS/...)
═══════════════════════════════════════════════════════════════════════════

We deliberately did NOT factor out a shared `BaseRFTestConfig` parent class
when this schema was written, because at the time MIMO_OTA was the only
test_type using the new TestCase.configuration JSON shape. Rule-of-three
applies: refactor when the third user shows up.

When you build the next test_type schema (TRP / TIS / Throughput / ...), use
the names + units below as canonical. Discrepancies surface as "this should
have been `frequency_hz` not `freq_ghz`" — fix them at write time, do NOT
add another column with a different unit.

Canonical RF parameters (all test_types):
- frequency_hz: float        # always Hz, never MHz/GHz inside configuration
                             # (TestCase.frequency_mhz column stays as it is
                             # for filterability — it's a derived view)
- bandwidth_mhz: float       # always MHz here (legacy column matches)
- tx_power_dbm: float        # downlink BS transmit power; NOT DUT power
- target_rsrp_dbm: float     # absolute, signed (e.g. -85.0)
- target_snr_db: float       # SNR target at DUT input

Spatial sweep (TRP / TIS / MIMO_OTA when sampling specific positions):
- azimuths_deg: List[float]                  # MIMO_OTA-style: 4 discrete points
  OR
- spatial_grid: {theta_step_deg, phi_step_deg, theta_range, phi_range}
                                             # TRP/TIS-style: full sphere grid
  Use one OR the other, not both. Pick based on whether the test walks discrete
  azimuths (MIMO_OTA) or sweeps a sphere (TRP/TIS).

- settling_time_s: float
- num_samples_per_position: int              # rename `num_samples_per_azimuth`
                                             # to this when going generic

Channel model (MIMO_OTA / Throughput / VRT):
- cdl_model_name: str                        # 3GPP CDL profile, e.g. "CDL-A"
                                             # The TestCase.channel_model
                                             # column is a higher-level label
                                             # ("UMi-LOS"); both can coexist.

MIMO-specific (MIMO_OTA / Throughput / VRT-conducted):
- mimo_layers: int           # number of layers, NOT antennas
- modulation: str            # "256QAM" / "1024QAM"
- mcs: int                   # 3GPP MCS index
- tdd_pattern, tdd_period: str
- harq_max_trans, harq_processes: int

Pass criteria (every test_type):
- prefix with min_ / max_, suffix with the unit (e.g. min_throughput_mbps,
  max_rsrp_variance_db). Avoid bare names like `throughput` or `bler`.

If any of the above genuinely doesn't fit a new test_type's needs, document
the deviation here AND open a refactor ticket — do not silently diverge.

═══════════════════════════════════════════════════════════════════════════
REGISTERED DEVIATIONS (登记过的偏差)
═══════════════════════════════════════════════════════════════════════════

[2026-05-05, Phase 3a] TRP test_type schema:
  Field `tx_power_dbm` (canonical = downlink BS transmit power) does NOT
  apply to TRP. TRP measures DUT-side transmit power across a sphere; the
  BS is muted during the measurement. To avoid silent reuse, TRP schema
  defines a separate field `dut_tx_power_target_dbm` (the power level the
  DUT is commanded to transmit at via UL grant). Conversely, MIMO_OTA's
  `target_tx_power_dbm` is BS-side and stays as canonical.

  Refactor candidate (rule of three): if TIS / Throughput later also need
  separate "actor-side" power fields, abstract a Pydantic mixin class
  RFTransmitterConfig{role: "bs" | "dut", power_dbm: float}.

═══════════════════════════════════════════════════════════════════════════
"""
import math
from copy import deepcopy
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from app.hal.lte_earfcn import (
    normalize_lte_band,
    validate_lte_downlink_operating_point,
)
from app.hal.base_station import LteTransmissionMode
from app.hal.base_station_mac_profile import (
    CMW500_LTE_PROFILE_SOURCE,
    UXM_NR_PROFILE_SOURCE,
    FrozenMacTestProfile,
    LteRmcMacTestProfileV1,
    LteTddFrameStructureAuthoring,
    NrMacTestProfileV1,
    uxm_nr_tdd_period_for_pattern,
)
from app.hal.cmw500_command_profile import (
    CMW500_LTE_BANDWIDTH_TOKEN_BY_MHZ,
    CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH,
)
from app.hal.nr_arfcn import nr_arfcn_to_freq_mhz


# Canonical TestCase.test_type value
MIMO_OTA_TEST_TYPE = "MIMO_OTA"

_PCELL_MIRROR_FIELDS = (
    "frequency_hz",
    "bandwidth_mhz",
    "subcarrier_spacing_khz",
)
_PCELL_MIRROR_ADAPTERS = {
    "frequency_hz": TypeAdapter(float),
    "bandwidth_mhz": TypeAdapter(float),
    "subcarrier_spacing_khz": TypeAdapter(Optional[int]),
}


class MIMOOTAStepType(str, Enum):
    """Step types registered by mimo_ota executors. Used as step.type strings."""

    PRECHECK = "MIMO_OTA_PRECHECK"
    REFERENCE = "MIMO_OTA_REFERENCE"
    MEASURE = "MIMO_OTA_MEASURE"
    ANALYSIS = "MIMO_OTA_ANALYSIS"
    REPORT = "MIMO_OTA_REPORT"


# 5-phase canonical sequence — order matters
MIMO_OTA_DEFAULT_STEPS: List[MIMOOTAStepType] = [
    MIMOOTAStepType.PRECHECK,
    MIMOOTAStepType.REFERENCE,
    MIMOOTAStepType.MEASURE,
    MIMOOTAStepType.ANALYSIS,
    MIMOOTAStepType.REPORT,
]


class ComponentCarrierConfig(BaseModel):
    """Phase 2g: 单个 component carrier 配置(支持载波聚合 CA)。

    NR-CA 场景下 PCell + N 个 SCell 同时传输, 各自有独立频率/带宽。
    第一个 CC 自动作为 PCell, 后续作为 SCell, 由
    MIMOOTAConfiguration._resolve_component_carriers() 统一保证。

    单 CC (非 CA) 场景下 component_carriers 列表只有一个元素,
    或保持空让 backward-compat validator 从 frequency_hz/bandwidth_mhz
    自动构造。
    """

    model_config = ConfigDict(extra="allow")

    radio_technology: Literal["nr5g", "lte"] = Field(
        default="nr5g",
        description="PCell RAT；旧记录缺失时精确兼容为 nr5g",
    )
    frequency_hz: float = Field(..., description="中心频率 (Hz)")
    bandwidth_mhz: float = Field(..., description="信道带宽 (MHz)")
    subcarrier_spacing_khz: Optional[int] = Field(
        default=30,
        description="NR 子载波间隔 (kHz)；LTE 必须为空",
    )
    band: Optional[str] = Field(
        default=None,
        description="3GPP band，例如 NR n78 或 LTE B3",
    )
    duplex: Optional[Literal["fdd", "tdd"]] = Field(
        default=None,
        description="LTE PCell 双工模式；NR 本片不消费",
    )
    nr_arfcn: Optional[int] = Field(
        default=None,
        ge=0,
        description="可选显式 NR-ARFCN；LTE 禁止",
    )
    lte_dl_earfcn: Optional[int] = Field(
        default=None,
        ge=0,
        description="LTE 下行 EARFCN；LTE PCell 必填",
    )
    lte_transmission_mode: Optional[LteTransmissionMode] = Field(
        default=None,
        description="LTE transmission mode；LTE PCell 必填，NR 禁止",
    )
    role: Literal["pcell", "scell"] = Field(
        default="scell",
        description="PCell / SCell 角色; 由 _resolve_component_carriers 强制 cc[0]=pcell",
    )

    @model_validator(mode="before")
    @classmethod
    def _remove_nr_default_from_lte(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        data = deepcopy(raw)
        if data.get("radio_technology", "nr5g") == "lte" and (
            "subcarrier_spacing_khz" not in data
        ):
            data["subcarrier_spacing_khz"] = None
        return data

    @model_validator(mode="after")
    def _validate_rat_specific_identity(self) -> "ComponentCarrierConfig":
        if not math.isfinite(self.frequency_hz) or self.frequency_hz <= 0:
            raise ValueError("frequency_hz must be finite and positive")
        if not math.isfinite(self.bandwidth_mhz) or self.bandwidth_mhz <= 0:
            raise ValueError("bandwidth_mhz must be finite and positive")

        if self.radio_technology == "lte":
            if not self.band:
                raise ValueError("LTE PCell requires explicit band")
            if not self.duplex:
                raise ValueError("LTE PCell requires explicit duplex")
            if self.lte_dl_earfcn is None:
                raise ValueError("LTE PCell requires explicit lte_dl_earfcn")
            if self.lte_transmission_mode is None:
                raise ValueError(
                    "LTE PCell requires explicit lte_transmission_mode"
                )
            if self.nr_arfcn is not None:
                raise ValueError("LTE PCell must not set nr_arfcn")
            if self.subcarrier_spacing_khz is not None:
                raise ValueError("LTE PCell must not set subcarrier_spacing_khz")
            self.band = normalize_lte_band(self.band)
            validate_lte_downlink_operating_point(
                band=self.band,
                duplex=self.duplex,
                dl_earfcn=self.lte_dl_earfcn,
                frequency_mhz=self.frequency_hz / 1e6,
            )
            return self

        if self.lte_dl_earfcn is not None:
            raise ValueError("NR PCell must not set lte_dl_earfcn")
        if self.lte_transmission_mode is not None:
            raise ValueError("NR PCell must not set lte_transmission_mode")
        if self.subcarrier_spacing_khz is None:
            raise ValueError("NR PCell requires subcarrier_spacing_khz")
        if self.nr_arfcn is not None:
            expected_hz = nr_arfcn_to_freq_mhz(self.nr_arfcn) * 1e6
            if not math.isclose(
                self.frequency_hz, expected_hz, rel_tol=0.0, abs_tol=1.0
            ):
                raise ValueError(
                    "NR frequency_hz conflicts with explicit nr_arfcn"
                )
        return self


class MIMOOTAPassCriteria(BaseModel):
    """CTIA OTA pass/fail thresholds. Defaults are the historical Commissioning
    values; can be tightened via TestCase.pass_criteria override.
    """

    min_throughput_ratio: float = 0.70
    min_throughput_mbps: float = 300.0
    max_rsrp_variance_db: float = 3.0
    rsrp_range_dbm: tuple = (-95.0, -75.0)
    min_sinr_db: float = 10.0
    min_avg_rank_indicator: float = 1.8
    max_quiet_zone_ripple_db: float = 1.0


class MIMOOTAConfiguration(BaseModel):
    """Pydantic shape that lives inside TestCase.configuration for MIMO_OTA tests.

    All fields have CAICT-Lab-1-friendly defaults so omitting overrides on
    create is allowed; LabProfile-derived parameters can be merged in by the
    factory at TestCase build time.
    """

    model_config = ConfigDict(extra="allow")  # tolerate forward-compat extras

    # === 3GPP TR 38.901 channel ===
    cdl_model_name: str = "UMa CDL-C NLOS"
    # P2-15: 引用自定义 CDL 档案 (簇级参数)。设了 → ASC strategy 查 profile 装配簇走
    # input_mode=custom (优先于标称 cdl_model_name); 留空=标称 38.901 CDL。
    cdl_profile_id: Optional[str] = None
    # P2-16 S2: 统一信道引用 (收敛 scd_id/cdl_profile_id/asc_source_path/裸 RT)。设了 → measure
    # 前置解析读 ChannelAsset 按 source_type 推导 engine_mode + 信道字段。留空 = 走旧字段路
    # (backward-compat 方案 A: 旧 cdl_profile_id/scd_id 一行不改, 解析层只在本字段显式给时介入)。
    channel_asset_id: Optional[str] = None
    # ⚠ 这里是**全库通用默认**，不是某次现场的工作点。2026-08-07 一度被改成
    #   CAICT n78 基线（3549.99 MHz / BW40），当天即撤回 —— 共享 schema 的默认值
    #   会流进每一条新建用例，把一次现场的配置变成全项目的隐含前提。
    #   现场基线属于**暗室首测那一条路**，走 `CreateSessionRequest` 显式传，
    #   或由操作员在 GUI 上填；权威值备查：ARFCN 636666 = 3549.99 MHz、BW40、
    #   信道资产 MF_N78_636666_BW40_CDLC_UMa_4x4_DP_v1
    #   （2026-07-03 EMQuest .prm 破译；⚠ .smu 文件名标称 3600M 是错的，
    #    见 memory `project_f64_smu_filename_freq_mismatch`）。
    frequency_hz: float = 3.5e9
    bandwidth_mhz: float = 100.0

    # === Phase 2g: 载波聚合 (CA) ===
    # 为 None / 空时, _resolve_component_carriers() 自动从 frequency_hz +
    # bandwidth_mhz + subcarrier_spacing_khz 构造单 CC 列表 (向后兼容)。
    # CA 场景下显式传 ≥2 个 ComponentCarrierConfig, 第一个自动 pcell,
    # 余下 scell。空集合 / 传入但只 1 个的情况 = 单 CC 测试。
    component_carriers: Optional[List[ComponentCarrierConfig]] = None

    # === MIMO ===
    mimo_layers: int = 2
    modulation: str = "256QAM"
    subcarrier_spacing_khz: Optional[int] = 30

    # === Turntable ===
    azimuths_deg: List[float] = Field(
        default_factory=lambda: [0.0, 90.0, 180.0, 270.0],
        min_length=1,
        max_length=361,
    )
    measurement_duration_s: float = 10.0
    settling_time_s: float = 2.0

    # === Sampling ===
    num_samples_per_azimuth: int = 100
    sample_interval_ms: float = 100.0

    # === Power ===
    # ⚠️ **口径陷阱**：本字段最终写到 `BSE:CONFig:NR5G:<cell>:DL:POWer`，
    # 手册原文 `Unit : dBm/SCS`、`Range : -200 .. 10`、
    # `Description: Changes DL Power - energy per resource element`
    # (NotebookLM 2026-08-07 原文核对) —— 它是**每子载波 (EPRE)** 口径，
    # 不是整带宽总功率。默认 0.0 曾被原样发成 `0 dBm/SCS`，仪器当场回
    # `510,"Configuration warning;DL Power adjusted on NR Cell-1 from 0 dBm/SCS
    # to -25.12 dBm/SCS due to HW port limitations"` —— 即请求值根本没生效。
    # 想按「整带宽 dBm」配功率，用下面的 `uxm_dl_power_dbm_per_bw`，
    # **别在这里自己换算** (换算随带宽/SCS 变，是派生值)。
    target_tx_power_dbm: float = 0.0

    uxm_dl_power_dbm_per_bw: Optional[float] = None
    # 2026-08-07 现场（用户当场指定 -15 dBm/BW）。
    # 非 None = DL 功率改走**整带宽口径**的专用命令，**不再写** `DL:POWer`
    # (dBm/SCS)。手册原文（NotebookLM 2026-08-07 核对）：
    #   SCPI 变体① `BSE:CONFig:NR5G:<cell>:DL:POWer:CHANnel`  ← 推荐 (TA v15.26.6+)
    #   SCPI 变体② `BSE:CONFig:NR5G:<cell>:DL:POWer:DBmBw`    ← 旧别名，同行为
    #   Description: "Sets the total DL Reference Signal "Channel" Power
    #                 (i.e. the power integrated over the whole cell bandwidth) in dBm"
    #   Default : -23.0    Range : -168 .. 42    → -15 在范围内
    # ⚠ **为什么不在 target_tx_power_dbm 里填换算值**：dBm/SCS ↔ dBm/BW 的换算
    #   取决于带宽和 SCS（BW40/SCS30 差 31.0 dB，BW100 差 35.2 dB），是**派生值**。
    #   仪器自己有这条命令，就让仪器换算 —— 本项目在派生值上栽过（.smu 文件名
    #   频率，见 project_f64_smu_filename_freq_mismatch）。
    # ⚠ 手册标 `Application Mode : NSA | SA`，**没写 LTE_NR_IRAT** —— 跟
    #   band/ARFCN 那批一样，下发后必须查 `SYST:ERR?` 才知道认不认。
    # None = 回到旧行为（写 `DL:POWer` = target_tx_power_dbm，dBm/SCS）。

    target_rsrp_dbm: float = -85.0
    target_snr_db: float = 20.0

    # === Reference antenna (for Phase 2) ===
    reference_antenna_model: str = "SGA-3500"
    reference_antenna_gain_dbi: float = 6.1

    # === Base station MAC throughput parameters (for Phase 3) ===
    mcs: int = 28
    enable_amc: bool = False
    # 2026-08-07 现场（用户当场选定 DDDSUDDSUU）：原默认 `DDDSU` 是 **5 个 slot**，
    # 30 kHz SCS 下 5 × 0.5ms = **2.5ms**，跟 `tdd_period = "5MS"` 对不上 ——
    # 驱动因此**拒发整个 TDD 组**（照发不会被仪器拒，但 DL/UL 比例会静默变成
    # 另一个配置，测的不是那个量；见 test_p1_33 的 TestScsConsistency）。
    # `DDDDDDDSUU` = 7D + 1S + 2U = 10 slot × 0.5ms = 5.0ms，跟 period 自洽。
    #
    # ⚠️ **为什么不是 `DDDSUDDSUU`**（2026-08-07 现场先选了它，翻不了）：
    #   本仪器的 TDD 配置是**六个数**（DLSLots/DLSYmbols/ULSLots/ULSYmbols/
    #   PERiod/STATE），手册原文 "DL Slots … starting from the **left side**
    #   of the periodicity window" / "UL Slots … from the **right side**" ——
    #   六个数只能表达 **D…D [S] U…U** 这**一种**排布。
    #   `DDDSUDDSUU` = `DDD S U DD S UU`（S 后面还有 D、且两个 S）
    #   在 3GPP 里合法(那是 pattern1+pattern2 双段)，但**单段六个数表达不了**，
    #   驱动会拒发整组 TDD（拒得对：照发会静默变成另一个配置）。
    #   手册**确实支持**双段 `TDDPATtern:TWO:*`，但本驱动只实现了单段 ——
    #   要用双段得先扩驱动，别改这里的值去凑。
    # ✅ `DDDDDDDSUU` 恰好等于**手册自己的默认值** dslots=7 / dsym=6 /
    #   ulslots=2 / ulsym=4 / period=MS5（NotebookLM 2026-08-07 原文核对）。
    # ⚠ 换 SCS 就要重算：pattern 的含义**依赖 SCS**（手册把 SCS 列为
    #   `TDDPATtern:STATE` 的 Dependencies）。60 kHz 下同样 10 slot 只有 2.5ms。
    tdd_pattern: str = "DDDDDDDSUU"
    tdd_period: str = "5MS"
    harq_max_trans: int = 4
    harq_processes: int = 16
    stat_count: int = 5000

    # === UXM 端口路由 / 调度 TestCase 驱动 (P2-11 #1974, 2026-06-04) ===
    # path B (正式测试) measure 显式驱动这些, 避免残留 HAL-init 默认 topology profile 的
    # 值 (如 2x2 TestCase 跑在残留的 4x4 端口路由上, 跟频率/MCS 错配同等危害)。
    # ⚠️ 默认 None = "TestCase 未指定" (Codex P1 #127): measure **None 时不传**
    # set_cell_config → 保持 HAL profile, 旧 saved case (没这些字段, 反序列化得 None) 不被
    # 默认值覆盖 (否则旧 4x4 case 被默认 "2x2" 强制成 2x2 路由 → 静默 layer/port mismatch)。
    # 显式给才驱动 (堵残留)。⚠️ 不从 mimo_layers 自动派生 (diversity 配置 layers≠preset
    # 合法) —— 用户 2026-06-04 选方案 b。非法 preset 在 measure 前置 fail-loud (Codex P2
    # #127)。tdd_pattern/tdd_period 不在这里 (已由 configure_mac_throughput_test 驱动)。
    mimo_port_preset: Optional[str] = None  # siso / 2x2 / 4x4 / 2x2_alt
    sched_algo: Optional[str] = None  # PDSCH 调度算法 (e.g. FULLBUFFER)
    csi_rs_ports: Optional[int] = None  # CSI-RS 端口数
    # P2-54: execution-owned, RAT-discriminated MAC truth.  The flat fields
    # above remain input-compatible during migration, but canonical writers
    # persist only this frozen profile.
    mac_profile: FrozenMacTestProfile

    # === Channel generation engine ===
    # 2026-08-07 现场（用户当场指定「硬编码 GCM 以及指定的文件」）：
    # 默认改成 GCM 原生 —— 现场唯一验过的信道资产
    # `MF_N78_636666_BW40_CDLC_UMa_4x4_DP_v1` 是 `source_type=vendor_file`、
    # `allowed_targets=['gcm_native']`，走 ASC 合成**根本碰不到它**。
    # 原默认 `mimo_first_asc` 会让暗室首测拿 ChannelEgine 现场合成的 UMa CDL-C
    # 去测，跟 EMQuest 那套基线不同源，结果没法跟历史对比。
    # 配套的 .smu 路径见下方 `emulation_file`；两者必须同时改，改一个就自相矛盾。
    # ⚠ 撤回到 ASC（外审 #304 P1）。2026-08-07 现场把它改成 keysight_gcm，
    #   但 GCM 路**必须**有 `.smu`（`emulation_file` 或 `channel_asset_id`），
    #   而那两个字段昨天已随其它现场基线撤回成 None —— 于是默认会话会被
    #   measure 的 strict emulation-file 门在加载模型前全部拒掉。
    #   engine_mode 跟 frequency_hz / bandwidth_mhz 是同一批现场基线，
    #   撤回时漏了它。现场那条路（GCM + 指定 .smu）走 CreateSessionRequest 显式给。
    engine_mode: str = "mimo_first_asc"
    # Allowed: "mimo_first_asc" | "keysight_gcm" | "external_asc" | "b2_parametric_tdl"
    #   - mimo_first_asc:    api-service → channel-engine-service → ChannelEgine strict_pfs
    #   - keysight_gcm:      Keysight F64 GCM Studio (vendor native, no microservice)
    #   - external_asc:      operator-provided .asc directory (debug-only, see asc_source_path)
    #   - b2_parametric_tdl: P2-14 B-2 参数化 TDL + F64 硬件实时衰落 (RT 子径 → geometric_native_fit
    #                        聚类 → .tap; 需 rt_rays/test_class/f64_profile 经 extra 透传, 见 V1.0 §3.3)

    # === External ASC source (only when engine_mode == "external_asc") ===
    asc_source_path: Optional[str] = None
    # Absolute path on the api-service host pointing at a directory of
    # `channel_InX_OutY.asc` files (typically produced by operator running
    # ChannelEgine app.py Streamlit / gui.py Tkinter locally). 2026-05-18 P0-7:
    # formalizes the previously-implicit "manual asc handoff" workflow used
    # for debugging. Cross-validated by the _validate_external_asc_path
    # model_validator below to fail-fast on misconfiguration before measure
    # phase touches HAL.

    # === Theoretical reference for ratio calculations (3GPP 2x2 256QAM 100MHz ≈ 450 Mbps) ===
    theoretical_peak_throughput_mbps: Optional[float] = 450.0

    # === Precheck behavior (P1-8 / P1-9, 2026-05-19) ===
    precheck_strict_cal: bool = True
    # When True (production default): precheck FAILS if path_loss_calibration
    # is missing/invalid or if cal_cert exists but overall_pass=False. Prevents
    # commissioning from running on uncalibrated chambers and silently using
    # the typical_cable_loss_db fallback (see docs/architecture/
    # channel-engine-data-flow.md surprising #3).
    #
    # Set False to bypass the cal gate for lab dev / smoke / unit-test setups
    # where calibration data is intentionally absent. Bypass leaves an audit
    # trail in result_payload["cal_pass_reason"]. GUI commissioning workflow
    # does not expose this flag — bypass is intended for config/fixture-level
    # opt-in only, so an operator can't accidentally disable the safety gate.

    precheck_strict_dut: bool = True
    # True（生产默认）= DUT 动态门 fail-closed。标准 managed_rf_attach 执行不会在
    # PRECHECK 读取初始化前的旧 attach 状态；它在 MEASURE 按本次 TestCase 初始化
    # UXM/F64/开关矩阵并受控 attach 后，要求真实基站明确回传 connected。legacy /
    # unmanaged 执行仍在 PRECHECK 用 dut_attach + live BS query 判定。
    # 两条路径都防止“没有真实 DUT 仍产出看似合理的测量数值”。
    # See P1-8 audit finding #3 + docs/architecture/channel-engine-data-flow.md
    # surprising #3 (sibling gap to the cal-missing gate).
    #
    # False = 显式旁路对应路径的 DUT 动态门，仅供 lab dev / smoke / unit test；
    # managed 路径在 MEASURE 留痕，legacy 路径在 PRECHECK 的 dut_pass_reason 留痕。
    # 字段名保留 precheck_ 前缀只为配置兼容，不代表 managed 路径仍在 PRECHECK 判定。

    # === 仪表使用参数 (开关 3 块 2, 2026-07-20) — 全部 None = 现行为不变 ===
    #
    # ⭐ **默认必须是「不覆盖」**（2026-08-07 收窄）。这些字段跟数据库里**已经
    #   存在**的用例共用同一个 schema：老用例的 configuration JSON 里没有这些键，
    #   `model_validate()` 会拿**当前代码里的默认值**替它们补齐 —— 于是改一个
    #   默认值就等于改了全库既有用例的行为，而用例本身一个字节没动。
    #   实证：本字段一度默认 2，导致所有既有用例都被塞进"先直通→探 attach→
    #   再开衰落"的流程，而那道 attach 探针在真 UXM 上必然失败（判据当时用错成
    #   `query_ue_capability`，IRAT 方言上那几条命令是 None）→ 老用例全 FAILED。
    #   现场基线值属于**暗室首测这一条路**，已搬到 `CreateSessionRequest`
    #   （同 `engine_mode` 先例），不放在共享 schema 里。
    #   由 `test_rule_gates.py` 的 G16 守着请求侧与 schema 侧默认值不打架。

    f64_bypass_mode: Optional[int] = Field(default=None, ge=1, le=3)
    # **「扶一把」开关**：attach 之前先把 F64 设成直通，让 DUT 容易挂上；
    # 挂上之后撤掉直通、开衰落，再确认一次还在，然后才测。
    # None = 关（默认，正常流程：直接开衰落测量）。非 None = 开，值是直通档位。
    #
    # 为什么默认关（2026-08-07 用户定的方向）：不 bypass 才是正常测试流程，
    # bypass 是**例外处理** —— 有的 DUT 在衰落打开的情况下不容易 attach，
    # 拿直通扶一把让测试能开始。它是**调试辅助**，不是测试参数：
    # 频率/带宽/功率/信道模型定义"测的是什么"，本开关定义"怎么让它开始"。
    # 混进默认值会污染可比性（扶过的和没扶过的数能不能直接比？）。
    # ⚠ attach 超时时的错误消息会提示这个开关，不需要谁记住它存在。
    #
    # 档位（手册原文，NotebookLM 2026-08-07 核对 §20.4.6.25）：
    #   1 Channel model bypass — 衰减=平均衰减, 时延=最小路径时延, **相位为零**
    #   2 Butler bypass        — 衰减=平均衰减, 时延=最小路径时延,
    #                            **相位用 Butler Matrix 算, 取决于拓扑**
    #   3 Calibration bypass   — 所有通道衰减相同、时延相同、**相位为零**
    # 4x4 要用 2：1 和 3 的零相位会让 MIMO 秩塌掉。
    #
    # 流程（三个节点各留一条里程碑，进 result_payload 也进报告）：
    #   bypass_attach  扶着的时候挂上了吗
    #   fading_attach  **梯子撤掉之后还在吗** ← 判断"这个 DUT 到底需不需要扶"
    #   throughput     撤掉之后测出数来了吗
    # 跑够几轮就能用历史数据回答"要不要扶"，而不是靠猜。
    #
    # ⚠ 手册："When static model is enabled, **emulation is paused**"；
    #   而「设了 STATIC 之后需不需要 DIAG:SIMU:GO 才有射频输出」**手册未说明**
    #   —— 所以直通态下 DUT 到底能不能 attach 是**现场才知道**的。挂不上时
    #   里程碑如实停在 bypass_attach=False，**不假装往下走**。
    # ⚠ 直通稳态下 F64 输出功率显示冻结（07-03 实证），判据以 DUT 侧吞吐为准。
    #
    # 📌 待评估（不在本片做）：本字段与下面的 `f64_fade_after_attach` 其实是
    #    一件事的两半（开了直通就必然要撤掉，没有"开了不撤"这种用法），
    #    合成一个语义更达意的开关（如 `bypass_assist_attach`）更清楚。
    #    但改名波及 GUI 表单、`baseStation_attach_check` 的同名参数与两个测试
    #    文件，**一个故障都不修** —— 按 ⑦ 记入 Discovered 单独立项。

    f64_fade_after_attach: bool = True
    # 仅在 `f64_bypass_mode` 非 None（即开了"扶一把"）时有意义。
    # True  = 撤掉直通、开衰落、再确认一次 DUT 还在，然后测（默认，也是
    #         "扶一把"该有的完整语义）。
    # False = 停在直通态测量，全程不 GO、没有衰落 —— 无衰落基线专用。
    # ⚠ bypass 关掉时本字段被忽略（那条路本来就直接 start_emulation）。

    f64_input_ref_dbm: Optional[float] = None
    # 非 None = **手动定标**: 直接 set F64 输入参考 (INP:LEV:AMP × 全输入),
    # 跳过 AUTOSET 闭环; 读回 (measure_input) 进 input_level_calibration
    # payload 作反馈。None = AUTOSET 闭环。
    #
    # 2026-08-07 现场（用户当场指定 -17）：UXM 出 -15 dBm/BW，UXM→F64 路损
    # **按 2 dB 估**（尚未实测，见下方警告），故 F64 输入口实际 -17。
    # 手册原文（§20.4.4.3 / GUI「Input RF level」）："sets the average input
    # level ... in dBm"、"Defines the maximum RMS transmit power of the BS or MS
    # **without cables or external losses**"；limits 示例 `-23, 0` → -17 在范围内。
    # ⚠ **口径等价性**：手册把「发射端功率」和「线缆损耗 (In loss)」分成两个参数。
    #   这里把 2 dB 路损**吸收进参考值**(-15−2=-17)，**只在 In loss = 0 时等价**
    #   （2026-08-07 用户确认 In loss 未设过）。若哪天 F64 上填了 In loss，
    #   这个值必须改回 -15，否则路损被扣两次。
    # ⚠ **2 dB 是估计值不是实测** —— 真实路损要用 CE+SA 实测（P0-3 校准链），
    #   在那之前所有绝对电平结论都带这 2 dB 的不确定度。

    f64_crest_db: Optional[float] = None
    # 手动定标的峰均比 (随 f64_input_ref_dbm 使用; 单独给不生效 — crest 是
    # 定标的一部分, 不做独立下发路径)。
    # 2026-08-07 现场用户指定 15（07-03 那次用的是 12，工作点不同不要照抄）。

    f64_output_gain_db: Optional[float] = None
    # 非 None = 信道加载后对全部输出写 OUTP:GAIN (统一值)。None = 不写。
    # ⚠ 这是**增益 dB**不是绝对电平；手册 `OUTPut:GAIN:CH` limits 示例 `-45, 0`。
    # 要按绝对 dBm 设输出用下面的 `f64_output_level_dbm`。

    f64_output_level_dbm: Optional[float] = None
    # 2026-08-07 现场（用户当场指定 -50，"大一点没关系"）。
    # 非 None = 信道加载后对全部输出写 **绝对平均输出电平**
    # `OUTPut:LEVel:AMPlitude:CH <out>,<dBm>`（手册 §20.4.5.3 原文
    # "sets the average output level of the specific channel output in dBm"，
    # limits 由 `OUTP:LEV:AMP:LIM? <out>` 查，手册示例 `-68.8401,-23.8401`）。
    # ⚠ 跟 `f64_output_gain_db` 是**两条不同的命令**，手册对二者的换算关系
    # **未说明** —— 两个都给会写两次、互相覆盖，语义不可预测。同时给 = fail-loud。

    input_loop_initial_dl_power_dbm: Optional[float] = None
    # AUTOSET 闭环的 UXM 起点功率。None = controller 默认 -10 dBm (比 EMQuest
    # -46 基线热 36 dB, #216 门审 F3 披露); 现场可给温和起点 (如 -46) 免大
    # 功率起步冲 F64 输入。仅闭环模式消费 (手动定标不涉及)。

    base_station_config_mode: Literal["dispatch", "inherit"] = "dispatch"
    # 基站静态小区配置来源。dispatch（默认）主动下发并回读；inherit 是“基站当前态
    # 调试继承”，只用于显式诊断，结果不得进入正式 KPI / verdict。
    uxm_config_mode: Optional[Literal["dispatch", "inherit"]] = Field(
        default=None,
        deprecated="Use base_station_config_mode instead.",
    )
    # 旧 TestCase JSON 只读兼容键。新写方统一使用 base_station_config_mode；保留原键
    # 仅为历史审计，不允许执行器再自行回退。

    precheck_strict_input_level: bool = True
    # P0-8 Step 2 Phase 2b (2026-05-28): F64 输入操作点闭环 (InputLevelController)
    # 在 measure phase 内部、generator 载完 fading 后跑。CE+BS 同时具备 input-level
    # capability (hasattr 检测) 时启用; 缺一方自动跳过 (mock dry-run 不受影响)。
    # True (生产默认): 闭环不收敛 → measure phase FAILED (操作点是 RF 正确性前置,
    # 不收敛后续 RSRP/吞吐都不可信). False (opt-out): 不收敛降级为 warning, 继续
    # azimuth 扫描, 在 result_payload["input_level_calibration"] 留 audit 痕迹。
    # 同 precheck_strict_cal/dut: GUI 不暴露, fixture/config 级别 opt-in。

    precheck_strict_frequency: bool = True
    # P2-11 Phase 1 (2026-05-30): 多方频率一致性校验。measure phase 在 UXM
    # set_cell_config + F64 信道加载后，UXM 用完整 (中心 ARFCN, 带宽) 回读；
    # F64 用 live 中心频率 + ChannelAsset/SCD 声明带宽（无资产则 BW unknown），
    # 跟 TestCase 比对 (架构原则: ARFCN 是频率单一真值, 见
    # docs/architecture/testcase-driven-instrument-config.md)。
    # True (生产默认): 不一致 → measure phase FAILED (静默错配 = UXM/F64/TestCase 不
    # 同频 → 测试结果不可信, 如 GCM 模式 TestCase 3500 但 F64 默认 .smu 3600, 或 UXM
    # 标称 3500 实际下发 ARFCN 3489)。False (opt-out): 降级 warning, 留 audit 痕迹。
    # 同 precheck_strict_cal/dut/input_level: GUI 不暴露, fixture/config 级别 opt-in。

    # === F64 GCM .smu TestCase 驱动 (P2-11 Phase 2, 2026-05-31) ===
    emulation_file: Optional[str] = None
    # 2026-08-07 现场（用户当场给的 F64 本机路径，「硬编码指定的文件」）。
    # 对应资产 `MF_N78_636666_BW40_CDLC_UMa_4x4_DP_v1`
    # (id b328d53a-edfa-40a0-81e1-5efc759bcc5a, source_type=vendor_file)。
    # ⚠️ **文件名标称 3600M，工程真值是 3549.99 MHz / ARFCN 636666**
    #   （2026-07-03 现场纯净加载 + 面板实证；见
    #   project_f64_smu_filename_freq_mismatch）。**别拿文件名推频率** ——
    #   上面 `frequency_hz = 3.54999e9` 才是真值，两者不一致是预期的。
    # ⚠️ 这是**站点特定的硬编码**：换一台 F64 / 换一版 Scenario Pack 就得改。
    #   正规做法是传 `channel_asset_id`（资产的 associated_file_path 已登记同一
    #   路径，resolver 会覆盖本字段），但 GUI 暂无资产选择器 —— 2026-08-07
    #   用户明确要求「不用复杂，可以硬编码」，故先钉死，资产选择器留作后续。
    # GCM (keysight_gcm) 模式下 F64 加载的 .smu 仿真文件完整路径 (F64 Windows 主机上)。
    # None = 不由 TestCase 指定。
    # 路径 B (正式测试): 显式指定 → measure 经 sim_rules 透传给 F64 GCM, 优先于驱动
    # 默认 .smu。ASC 模式无关 (.asc 由 channel-engine 按 frequency_hz 生成, 不用 .smu)。

    precheck_strict_emulation_file: bool = True
    # P2-11 Phase 2: GCM 模式 TestCase 未指定 emulation_file 时的 measure 行为。
    # True (生产默认): measure FAILED —— GCM 正式测试 (路径 B) 必须由 TestCase 驱动
    # .smu, 不能静默 fallback 到 F64 驱动默认 (默认 .smu 频率可能跟 TestCase 错配, 见
    # docs/architecture/testcase-driven-instrument-config.md 路径 A/B 切分)。
    # False (opt-out): 降级 warning, 用 F64 驱动默认 .smu (路径 A bring-up / 暗室首测
    # 走捷径)。仅 GCM 模式生效 (ASC 不用 .smu)。同 precheck_strict_cal/dut/frequency:
    # GUI 不暴露, fixture/config 级别 opt-in。

    # === SCD 引用 (P2-12 slice 4, 2026-06-03) ===
    scd_id: Optional[str] = None
    # 引用 StandardChannelDefinition (按规范配置声明的标准信道) 的 UUID 字符串。优先于
    # 裸 emulation_file —— measure 查 SCD → associated_file_path 当 .smu, 并把 SCD 声明
    # ARFCN 作为一个 source 纳入 Phase 1 多方频率一致性网 (TestCase 频率 vs SCD 声明
    # cross-check, 抓"选了个频率错配的 .smu")。"3500 用哪个 .smu" 从赌文件名变查 SCD by
    # FrequencyIdentity (declared>inferred, 见架构文档 §9)。None = 用裸 emulation_file
    # (路径 A bring-up / legacy)。仅 GCM 模式相关 (ASC 按 frequency_hz 生成 .asc 不用 .smu)。

    # === RF 开关拓扑 operating mode TestCase 驱动 (P2-11 Phase 3, 2026-05-31) ===
    switch_mode_id: str = "mimo_ota"
    # 选 chamber 的 active SwitchTopology 里哪个 operating mode (RF 通路子集)。
    # 不同 mode = 不同 active_connections (e.g. "mimo_ota" 全 MIMO 通路 /
    # "cal_power_sweep" 校准通路 / 2x2 子集)。默认 "mimo_ota" = 现历史硬编码值
    # (backward-compat); TestCase 按测试类型覆盖。measure phase 2c 把它传给
    # orchestrate_switch_topology, 解析出 CE→probe 绑定供下游 channel-gen 消费。

    precheck_strict_switch_mode: bool = True
    # P2-11 Phase 3: chamber 有 active SwitchTopology 但其中**没有** switch_mode_id
    # 声明的 mode (或该 mode 无 active_connections) 时的 measure 行为。
    # True (生产默认): measure FAILED —— TestCase 显式请求的 RF 通路 mode 链路声明不
    # 提供 = 真错配 (e.g. 4x4 TestCase 请求的 mode 不在拓扑里)。
    # False (opt-out): 降级 warning, 继续 (probe 绑定可能空, 下游退回 chamber 几何)。
    # 注意: chamber **没有** active topology row (固定布线手工接线) → 始终只 warning
    # (不受本 flag 影响), 这是 CAICT 固定布线的既有语义。同 precheck_strict_*:
    # GUI 不暴露, fixture/config 级别 opt-in。

    precheck_strict_cell_config: bool = True
    # P2-11 Phase 6: measure 在 set_cell_config + RRC reconfig 后, 拿 **UE 协商能力**
    # (max_dl_layers) 跟 TestCase 请求层数比 —— Phase 1 频率回读校验在吞吐链上的延伸。
    # True (生产默认): 请求层数 > UE 能力上限 → measure FAILED。UE 撑不住请求层数时 UXM
    # 会把请求的 4 层静默 clamp 到 2 而不报错, 吞吐其实是 2 层却当 4 层测 (跟频率错配同等
    # 危害)。Codex on PR #114: 读 UE 协商能力, **不**读 CONF:...:LAY? 配置旋钮 (那个回读只
    # 会原样返回配置值, 抓不到 clamp)。
    # False (opt-out): 降级 warning。不可核对 (mock / UE 未 attach / firmware 不支持
    # UEINFO) → 始终跳过 (不受本 flag 影响, 同 Phase 1 mock-skip)。同 precheck_strict_*:
    # GUI 不暴露, fixture/config 级别 opt-in。

    dut_profile_id: Optional[str] = None
    # 关联的 DUTProfile id (str UUID); None = 不做声明校验。operator 在 GUI / API 设。
    precheck_strict_dut_capability: bool = True
    # DUTProfile 声明能力校验 (规划期, attach 前): config.dut_profile_id 指向一个 DUTProfile 时,
    # precheck 拿 TestCase 请求 (mimo_layers / modulation) 跟 DUT **声明**能力比 —— 请求 > 声明
    # (e.g. 请求 4 层但 DUT 声明 max 2) 提前 FAIL, 不浪费一次真跑 (跟 cell_config attach 后协商
    # 核对互补: 这个最早, 查 DB 声明, 不需硬件)。
    # True (生产默认): 请求 > 声明 → precheck FAILED。无 dut_profile_id / 声明项未填 → 跳过。
    # False (opt-out / 暗室首测 bring-up): 降级 warning。同 precheck_strict_* 走 bring-up bypass。

    sim_profile_id: Optional[str] = None
    # P2-13 阶段 1: 关联的 SIMProfile id (str UUID) —— 本次测试用哪张测试卡 (IMSI/PLMN/Ki/OPc)。
    # None = 不做 SIM 身份门。managed_rf_attach 在 MEASURE 受控 attach 后，用 UXM/UE 本次实测
    # IMSI 对照声明；legacy / unmanaged 仍由 PRECHECK 使用已有 attach 快照核对。
    precheck_strict_sim_identity: bool = True
    # P2-13 阶段 2: SIM 身份核对门 (防插错卡)。True（生产默认）时，managed 路径若
    # SIMProfile 不可用、无声明 IMSI、UXM/UE 没有本次实测 IMSI或两者不一致，均在 MEASURE
    # fail-closed；操作员登记 IMSI 只作未验证审计，不能替代实测。legacy / unmanaged 路径
    # 仍在 PRECHECK 核对已有 attach 身份。False（bring-up opt-out）= 降级 warning。
    # 字段名保留 precheck_ 前缀只为配置兼容。

    # === Pass/fail thresholds ===
    pass_criteria: MIMOOTAPassCriteria = Field(default_factory=MIMOOTAPassCriteria)

    # === Optional explicit per-step parameter overrides ===
    # Keyed by MIMOOTAStepType.value; merged into step.parameters by the factory.
    # Lets tests pin one phase without rewriting the whole config.
    step_overrides: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_mac_profile(cls, raw: Any) -> Any:
        """Translate legacy flat controls into one RAT-specific frozen truth."""
        if not isinstance(raw, dict):
            return raw

        data = deepcopy(raw)
        carriers = data.get("component_carriers")
        pcell: dict[str, Any] = {}
        if isinstance(carriers, (list, tuple)) and carriers:
            candidate = carriers[0]
            if isinstance(candidate, ComponentCarrierConfig):
                pcell = candidate.model_dump(mode="python")
            elif isinstance(candidate, dict):
                pcell = candidate
        rat = pcell.get("radio_technology", "nr5g")
        has_lte_tdd_authoring = "lte_tdd_frame_structure" in data

        if "mac_profile" in data:
            if has_lte_tdd_authoring:
                raise ValueError(
                    "mac_profile conflicts with lte_tdd_frame_structure"
                )
            frozen = FrozenMacTestProfile.model_validate(data["mac_profile"])
            profile = frozen.profile
            expected_legacy: dict[str, Any] = {
                "enable_amc": profile.enable_amc,
                "stat_count": profile.statistical_window.count,
            }
            if isinstance(profile, NrMacTestProfileV1):
                expected_legacy.update(
                    {
                        "mcs": profile.mcs,
                        "tdd_pattern": profile.tdd_pattern,
                        "tdd_period": profile.tdd_period,
                        "harq_max_trans": profile.harq_max_trans,
                        "harq_processes": profile.harq_processes,
                        "csi_rs_ports": profile.csi_rs_ports,
                    }
                )
                scheduler = data.get("sched_algo")
                if scheduler in {"FULLBUFFER", "FULL_TPUT"}:
                    scheduler = "full_throughput"
                if (
                    scheduler is not None
                    and scheduler != profile.scheduler_algorithm
                ):
                    raise ValueError(
                        "mac_profile conflicts with deprecated sched_algo"
                    )
            else:
                for field in (
                    "mcs",
                    "tdd_pattern",
                    "tdd_period",
                    "harq_max_trans",
                    "harq_processes",
                    "sched_algo",
                    "csi_rs_ports",
                ):
                    if field in data and data[field] is not None:
                        raise ValueError(
                            f"mac_profile conflicts with deprecated {field}"
                        )
            for field, expected in expected_legacy.items():
                if (
                    field in data
                    and data[field] is not None
                    and data[field] != expected
                ):
                    raise ValueError(
                        f"mac_profile conflicts with deprecated {field}"
                    )
        else:
            layers = data.get("mimo_layers", 2)
            count = data.get("stat_count", 5000)
            if rat == "lte":
                # Preserve the established PCell validation source and its
                # actionable field name for incomplete legacy LTE rows.
                transmission_mode = pcell.get("lte_transmission_mode")
                if (
                    not pcell.get("duplex")
                    or transmission_mode
                    not in {
                        "TM1",
                        "TM2",
                        "TM3",
                        "TM4",
                        "TM6",
                        "TM7",
                        "TM8",
                        "TM9",
                    }
                ):
                    return data
                # P1-77：LTE TDD 还需要配比与特殊子帧
                # （`CELL[:PCC]:ULDL` pp.687-688 / `SSUBframe` p.688）。
                # legacy 扁平字段没有这些真值，因此必须由操作员通过
                # request-only authoring input 明确提供；绝不从仪器 `*RST`
                # （ULDL=1 / SSUBframe=7）补真。服务端在这里构造并冻结唯一
                # profile，成功后不会持久化 authoring input。
                duplex = str(pcell.get("duplex")).strip().lower()
                tdd_authoring = None
                if duplex == "tdd":
                    if not has_lte_tdd_authoring:
                        raise ValueError(
                            "duplex=tdd 的 LTE 配置必须提供 "
                            "lte_tdd_frame_structure（含 uldl_configuration "
                            "与 special_subframe）：不从仪器 *RST 补真"
                        )
                    tdd_authoring = LteTddFrameStructureAuthoring.model_validate(
                        data["lte_tdd_frame_structure"]
                    )
                    bandwidth_token = CMW500_LTE_BANDWIDTH_TOKEN_BY_MHZ.get(
                        pcell.get("bandwidth_mhz")
                    )
                    rmc_plan = CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH.get(
                        bandwidth_token or ""
                    )
                    if rmc_plan is None:
                        raise ValueError(
                            "LTE TDD bandwidth has no audited CMW500 RMC plan"
                        )
                    if (
                        rmc_plan.tdd_dl_version_required
                        and tdd_authoring.rmc_version is None
                    ):
                        raise ValueError(
                            "lte_tdd_frame_structure.rmc_version is required "
                            "for this LTE TDD bandwidth"
                        )
                    if (
                        not rmc_plan.tdd_dl_version_required
                        and tdd_authoring.rmc_version is not None
                    ):
                        raise ValueError(
                            "lte_tdd_frame_structure.rmc_version must be omitted "
                            "for this LTE TDD bandwidth"
                        )
                elif has_lte_tdd_authoring:
                    raise ValueError(
                        "LTE FDD configuration must not carry "
                        "lte_tdd_frame_structure"
                    )
                profile = LteRmcMacTestProfileV1.model_validate(
                    {
                        "schema_version": 1,
                        "kind": "lte_rmc",
                        "profile_version": 1,
                        "rat": "lte",
                        "test_intent": "downlink_throughput",
                        "mimo_layers": layers,
                        "statistical_window": {
                            "unit": "subframes",
                            "count": count,
                        },
                        "metric_requirements": [
                            {"key": "dl_throughput_mbps", "scope": "pcell"},
                            {"key": "dl_bler_percent", "scope": "pcell"},
                        ],
                        "scheduling_mode": "rmc",
                        "resource_allocation": "full",
                        "enable_amc": data.get("enable_amc", False),
                        "duplex": duplex,
                        "transmission_mode": transmission_mode,
                        "uldl_configuration": (
                            tdd_authoring.uldl_configuration
                            if tdd_authoring is not None
                            else None
                        ),
                        "special_subframe": (
                            tdd_authoring.special_subframe
                            if tdd_authoring is not None
                            else None
                        ),
                        "rmc_version": (
                            tdd_authoring.rmc_version
                            if tdd_authoring is not None
                            else None
                        ),
                        "source_reference": CMW500_LTE_PROFILE_SOURCE,
                    }
                )
            else:
                if has_lte_tdd_authoring:
                    raise ValueError(
                        "NR configuration must not carry lte_tdd_frame_structure"
                    )
                scheduler = data.get("sched_algo")
                if scheduler in (
                    None,
                    "FULLBUFFER",
                    "FULL_TPUT",
                    "full_throughput",
                ):
                    scheduler = "full_throughput"
                tdd_pattern = data.get("tdd_pattern", "DDDDDDDSUU")
                scs_khz = pcell.get(
                    "subcarrier_spacing_khz",
                    data.get("subcarrier_spacing_khz", 30),
                )
                tdd_period = data.get("tdd_period")
                if (
                    tdd_period is None
                    and isinstance(tdd_pattern, str)
                    # 受理域与下游 schema 同源：pydantic 的 lax 模式会把 30.0 归一成
                    # 30，所以守卫必须一并放行 float，否则「值好到能进 Literal，却不
                    # 够格参与派生」——那是本 PR 引入的回归，不是收紧。
                    # bool 是 int 的子类，必须排除：True 会被静默当成 1。
                    and isinstance(scs_khz, (int, float))
                    and not isinstance(scs_khz, bool)
                ):
                    # 显式 null 不在这里补默认值：让它原样落进 payload，由
                    # NrMacTestProfileV1 给出字段级拒绝，与 mcs / harq_* 等
                    # 其余字段对 null 的处理保持一致（受控拒绝，不猜意图）。
                    tdd_period = uxm_nr_tdd_period_for_pattern(
                        tdd_pattern=tdd_pattern,
                        subcarrier_spacing_khz=scs_khz,
                    )
                profile = NrMacTestProfileV1.model_validate(
                    {
                        "schema_version": 1,
                        "kind": "nr_throughput",
                        "profile_version": 1,
                        "rat": "nr5g",
                        "test_intent": "downlink_throughput",
                        "mimo_layers": layers,
                        "statistical_window": {
                            "unit": "subframes",
                            "count": count,
                        },
                        "metric_requirements": [
                            {"key": "dl_throughput_mbps", "scope": "pcell"}
                        ],
                        "rb_allocation": "all",
                        "scheduler_algorithm": scheduler,
                        "mcs": data.get("mcs", 28),
                        "enable_amc": data.get("enable_amc", False),
                        "tdd_pattern": tdd_pattern,
                        "tdd_period": tdd_period,
                        "harq_max_trans": data.get("harq_max_trans", 4),
                        "harq_processes": data.get("harq_processes", 16),
                        "subcarrier_spacing_khz": scs_khz,
                        "csi_rs_ports": (
                            data["csi_rs_ports"]
                            if data.get("csi_rs_ports") is not None
                            else (
                                max(2, layers * 2)
                                if isinstance(layers, (int, float))
                                and not isinstance(layers, bool)
                                else None
                            )
                        ),
                        "source_reference": UXM_NR_PROFILE_SOURCE,
                    }
                )
            data["mac_profile"] = FrozenMacTestProfile.freeze(profile)
            data.pop("lte_tdd_frame_structure", None)
        return data

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_base_station_config_mode(cls, raw: Any) -> Any:
        """在唯一 schema 边界翻译旧键，并拒绝显式双写分叉。"""
        if not isinstance(raw, dict):
            return raw

        data = deepcopy(raw)
        has_current = "base_station_config_mode" in data
        has_legacy = "uxm_config_mode" in data
        current = data.get("base_station_config_mode")
        legacy = data.get("uxm_config_mode")

        if current is not None and legacy is not None and current != legacy:
            raise ValueError(
                "base_station_config_mode conflicts with deprecated "
                "uxm_config_mode"
            )
        if not has_current and has_legacy and legacy is not None:
            data["base_station_config_mode"] = legacy
        return data

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_rat_specific_defaults(cls, raw: Any) -> Any:
        """旧记录保持 NR 默认；显式 LTE 不继承 NR SCS/450 Mbps。"""
        if not isinstance(raw, dict):
            return raw
        data = deepcopy(raw)
        carriers = data.get("component_carriers")
        if not isinstance(carriers, (list, tuple)) or not carriers:
            return data
        pcell = carriers[0]
        if isinstance(pcell, ComponentCarrierConfig):
            pcell = pcell.model_dump(mode="python")
        if not isinstance(pcell, dict) or pcell.get("radio_technology", "nr5g") != "lte":
            return data

        if data.get("subcarrier_spacing_khz") is not None and (
            "subcarrier_spacing_khz" in data
        ):
            raise ValueError(
                "LTE PCell must not set top-level subcarrier_spacing_khz"
            )
        data["subcarrier_spacing_khz"] = None
        if "theoretical_peak_throughput_mbps" not in data:
            data["theoretical_peak_throughput_mbps"] = None
        return data

    @model_validator(mode="before")
    @classmethod
    def _reconcile_primary_carrier_mirrors(cls, raw: Any) -> Any:
        """让 PCell 成为运行参数真值，同时保留旧顶层镜像兼容。

        显式给出两份且不一致时必须拒绝，避免 UXM/F64/波形/校准分别读取
        不同工作点。旧数据缺顶层镜像时只从 PCell 回填；没有 CC 时仍由
        after validator 从旧顶层字段构造单 PCell。
        """
        if not isinstance(raw, dict):
            return raw

        data = deepcopy(raw)
        carriers = data.get("component_carriers")
        if not isinstance(carriers, (list, tuple)) or not carriers:
            return data
        pcell = carriers[0]
        if isinstance(pcell, ComponentCarrierConfig):
            pcell = pcell.model_dump(mode="python")
        if not isinstance(pcell, dict):
            return data

        pcell_rat = pcell.get("radio_technology", "nr5g")

        for field in _PCELL_MIRROR_FIELDS:
            if pcell_rat == "lte" and field == "subcarrier_spacing_khz":
                continue
            if field in pcell:
                raw_pcell_value = pcell[field]
            else:
                field_info = ComponentCarrierConfig.model_fields[field]
                if field_info.is_required():
                    continue
                raw_pcell_value = field_info.get_default(call_default_factory=True)
            if field not in data:
                data[field] = raw_pcell_value
                continue
            try:
                top_value = _PCELL_MIRROR_ADAPTERS[field].validate_python(data[field])
                pcell_value = _PCELL_MIRROR_ADAPTERS[field].validate_python(
                    raw_pcell_value
                )
            except ValidationError:
                # 具体类型/范围错误交给字段自身校验，避免在这里改写错误语义。
                continue
            if top_value != pcell_value:
                raise ValueError(
                    f"{field} conflicts with component_carriers[0].{field}; "
                    "PCell is the MIMO OTA operating-point truth"
                )
        return data

    @property
    def primary_carrier(self) -> ComponentCarrierConfig:
        """返回规范化后的 PCell；after validator 保证它一定存在。"""
        if not self.component_carriers:  # pragma: no cover - schema invariant
            raise RuntimeError("MIMO OTA configuration has no primary carrier")
        return self.component_carriers[0]

    @field_validator("azimuths_deg")
    @classmethod
    def _validate_azimuths(cls, values: List[float]) -> List[float]:
        """限制正式扫描规模并拒绝无穷值/等价重复角，避免证据 JSONB 写放大。"""
        if any(not math.isfinite(value) for value in values):
            raise ValueError("azimuths_deg must contain only finite angles")
        if any(value < -360.0 or value > 360.0 for value in values):
            raise ValueError("azimuths_deg angles must be within [-360, 360]")
        canonical = [round(value % 360.0, 9) for value in values]
        if len(canonical) != len(set(canonical)):
            raise ValueError("azimuths_deg must not contain equivalent duplicates")
        return values

    @model_validator(mode="after")
    def _resolve_component_carriers(self) -> "MIMOOTAConfiguration":
        """向后兼容 + 角色强制 (Phase 2g)。

        - component_carriers 为 None / 空 → 从 frequency_hz/bandwidth_mhz/scs
          构造一个单 CC 列表
        - 传入了列表 → 强制 cc[0].role='pcell', cc[1..].role='scell'
        - 列表长度必须 ≥ 1 (运行时这是 measure 的输入合同)
        """
        if not self.component_carriers:
            if (
                "subcarrier_spacing_khz" in self.model_fields_set
                and self.subcarrier_spacing_khz is None
            ):
                raise ValueError(
                    "NR PCell requires subcarrier_spacing_khz; explicit null "
                    "cannot use the legacy default"
                )
            self.component_carriers = [
                ComponentCarrierConfig(
                    frequency_hz=self.frequency_hz,
                    bandwidth_mhz=self.bandwidth_mhz,
                    subcarrier_spacing_khz=self.subcarrier_spacing_khz,
                    role="pcell",
                )
            ]
        else:
            normalized: List[ComponentCarrierConfig] = []
            for idx, cc in enumerate(self.component_carriers):
                target_role = "pcell" if idx == 0 else "scell"
                if cc.role != target_role:
                    cc = cc.model_copy(update={"role": target_role})
                normalized.append(cc)
            self.component_carriers = normalized
        return self

    @model_validator(mode="after")
    def _validate_rat_specific_configuration(self) -> "MIMOOTAConfiguration":
        primary = self.primary_carrier
        if primary.radio_technology == "lte" and len(self.component_carriers or []) != 1:
            raise ValueError("LTE MIMO OTA requires a single PCell and no SCell")
        peak = self.theoretical_peak_throughput_mbps
        if peak is not None and (not math.isfinite(peak) or peak <= 0):
            raise ValueError(
                "theoretical_peak_throughput_mbps must be finite and positive"
            )
        if primary.radio_technology == "nr5g" and peak is None:
            raise ValueError("NR requires theoretical_peak_throughput_mbps")
        return self

    @model_validator(mode="after")
    def _validate_mac_profile_alignment(self) -> "MIMOOTAConfiguration":
        primary = self.primary_carrier
        profile = self.mac_profile.profile
        if profile.rat != primary.radio_technology:
            raise ValueError("MAC profile RAT must match the PCell RAT")
        if profile.mimo_layers != self.mimo_layers:
            raise ValueError("MAC profile mimo_layers must match MIMO intent")
        if isinstance(profile, NrMacTestProfileV1):
            if profile.subcarrier_spacing_khz != primary.subcarrier_spacing_khz:
                raise ValueError("NR MAC profile SCS must match the PCell SCS")
        elif isinstance(profile, LteRmcMacTestProfileV1):
            if profile.duplex != primary.duplex:
                raise ValueError("LTE MAC profile duplex must match the PCell")
            if profile.transmission_mode != primary.lte_transmission_mode:
                raise ValueError(
                    "LTE MAC profile transmission mode must match the PCell"
                )
        return self

    @model_validator(mode="after")
    def _validate_external_asc_path(self) -> "MIMOOTAConfiguration":
        """external_asc 模式必须给路径; 其他模式忽略 (留空也允许)。

        2026-05-18 P0-7: 路径存在性 *不* 在 schema 校验 (host filesystem 跟
        测试机器可能不同, 也跟 dev/prod 部署不同)。运行时由
        ExternalAscPathStrategy.generate_and_load 防御性检查并 surface
        actionable error。schema 这里只保证 mode-vs-path 配对完整。
        """
        # channel_asset_id 设了 → measure resolver 会用资产派生 engine_mode 覆盖, stale
        # external_asc (asc_source_path 已清) 不应在此 fail (Codex 0b913fe P2: 本 validator
        # 在 resolver 覆盖 engine 之前跑; 资产路由交给 resolver)。
        if getattr(self, "channel_asset_id", None):
            return self
        if self.engine_mode == "external_asc":
            if not self.asc_source_path or not self.asc_source_path.strip():
                raise ValueError(
                    "engine_mode='external_asc' requires asc_source_path to be "
                    "set to an absolute path of a directory containing operator-"
                    "produced channel_InX_OutY.asc files."
                )
        return self


_DEPRECATED_MAC_INPUT_FIELDS = (
    "mcs",
    "enable_amc",
    "tdd_pattern",
    "tdd_period",
    "harq_max_trans",
    "harq_processes",
    "stat_count",
    "sched_algo",
    "csi_rs_ports",
    "lte_tdd_frame_structure",
)


def dump_canonical_mimo_ota_configuration(
    config: MIMOOTAConfiguration,
) -> dict:
    """Serialize a validated configuration without deprecated MAC mirrors."""

    payload = config.model_dump(mode="json")
    for field in _DEPRECATED_MAC_INPUT_FIELDS:
        payload.pop(field, None)
    return payload


def canonicalize_mimo_ota_configuration_payload(payload: dict) -> dict:
    """校验并只规范化载波真值字段，保留稀疏 JSON 与前向兼容扩展。"""
    validated = MIMOOTAConfiguration.model_validate(payload)
    canonical = deepcopy(payload)
    for legacy_mac_field in _DEPRECATED_MAC_INPUT_FIELDS:
        canonical.pop(legacy_mac_field, None)
    canonical["mac_profile"] = validated.mac_profile.model_dump(mode="json")
    canonical["base_station_config_mode"] = validated.base_station_config_mode
    primary = validated.primary_carrier
    for field in _PCELL_MIRROR_FIELDS:
        if primary.radio_technology == "lte" and field == "subcarrier_spacing_khz":
            canonical.pop(field, None)
        else:
            canonical[field] = getattr(primary, field)
    canonical["component_carriers"] = [
        carrier.model_dump(mode="json")
        for carrier in (validated.component_carriers or [])
    ]
    return canonical
