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
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Canonical TestCase.test_type value
MIMO_OTA_TEST_TYPE = "MIMO_OTA"


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

    frequency_hz: float = Field(..., description="中心频率 (Hz)")
    bandwidth_mhz: float = Field(..., description="信道带宽 (MHz)")
    subcarrier_spacing_khz: int = Field(default=30, description="子载波间隔 (kHz)")
    band: Optional[str] = Field(
        default=None,
        description="3GPP NR 频段 e.g. 'n78' / 'n41' / 'n77' / 'n79'; 留空时由频率推断",
    )
    role: Literal["pcell", "scell"] = Field(
        default="scell",
        description="PCell / SCell 角色; 由 _resolve_component_carriers 强制 cc[0]=pcell",
    )


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
    subcarrier_spacing_khz: int = 30

    # === Turntable ===
    azimuths_deg: List[float] = Field(default_factory=lambda: [0.0, 90.0, 180.0, 270.0])
    measurement_duration_s: float = 10.0
    settling_time_s: float = 2.0

    # === Sampling ===
    num_samples_per_azimuth: int = 100
    sample_interval_ms: float = 100.0

    # === Power ===
    target_tx_power_dbm: float = 0.0
    target_rsrp_dbm: float = -85.0
    target_snr_db: float = 20.0

    # === Reference antenna (for Phase 2) ===
    reference_antenna_model: str = "SGA-3500"
    reference_antenna_gain_dbi: float = 6.1

    # === Base station MAC throughput parameters (for Phase 3) ===
    mcs: int = 28
    enable_amc: bool = False
    tdd_pattern: str = "DDDSU"
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

    # === Channel generation engine ===
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
    theoretical_peak_throughput_mbps: float = 450.0

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
    # When True (production default): precheck FAILS if dut_attach record is
    # missing or if rrc_connected != True. Prevents commissioning from running
    # without a DUT actually attached — measure phase otherwise still produces
    # numbers (synthesized RSRP from target + path-loss, BS-side mock metrics)
    # that look plausible but don't reflect any real DUT in the chamber.
    # See P1-8 audit finding #3 + docs/architecture/channel-engine-data-flow.md
    # surprising #3 (sibling gap to the cal-missing gate).
    #
    # Set False to bypass for lab dev / smoke / unit-test setups where the
    # 5-phase chain is tested without a DUT. Bypass leaves an audit trail in
    # result_payload["dut_pass_reason"]. GUI commissioning workflow does not
    # expose this flag — same opt-in-only contract as precheck_strict_cal.

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
    # set_cell_config + F64 信道加载后, 把各仪表归一到 (中心 ARFCN, 带宽) 规范标识,
    # 跟 TestCase 精确比对 (架构原则: ARFCN 是频率单一真值, 见
    # docs/architecture/testcase-driven-instrument-config.md)。
    # True (生产默认): 不一致 → measure phase FAILED (静默错配 = UXM/F64/TestCase 不
    # 同频 → 测试结果不可信, 如 GCM 模式 TestCase 3500 但 F64 默认 .smu 3600, 或 UXM
    # 标称 3500 实际下发 ARFCN 3489)。False (opt-out): 降级 warning, 留 audit 痕迹。
    # 同 precheck_strict_cal/dut/input_level: GUI 不暴露, fixture/config 级别 opt-in。

    # === F64 GCM .smu TestCase 驱动 (P2-11 Phase 2, 2026-05-31) ===
    emulation_file: Optional[str] = None
    # GCM (keysight_gcm) 模式下 F64 加载的 .smu 仿真文件完整路径 (F64 Windows 主机上,
    # e.g. "D:\\Scenario Packs\\...\\..._3600M.smu")。None = 不由 TestCase 指定。
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
    # None = 不做 SIM↔UXM 一致性校验。后续阶段: precheck 拿 SIMProfile vs UXM 小区 PLMN/HSS 比 +
    # attach 后实测认证 IMSI vs 声明核对 (防对错卡)。
    precheck_strict_sim_identity: bool = True
    # P2-13 阶段 2: SIM 身份核对门 (防插错卡)。config.sim_profile_id 指向声明卡时, precheck 拿
    # attach 记录 IMSI 跟 SIMProfile.imsi 比 —— 不一致 = 实际 attach 的卡跟 TestCase 选的卡对不上。
    # True (生产默认): 不一致 → precheck FAILED。无 sim_profile_id / 卡无声明 imsi / 无 dut_attach
    # → 跳过。False (opt-out / 暗室首测 bring-up): 降级 warning。同 precheck_strict_* 走 bypass。

    # === Pass/fail thresholds ===
    pass_criteria: MIMOOTAPassCriteria = Field(default_factory=MIMOOTAPassCriteria)

    # === Optional explicit per-step parameter overrides ===
    # Keyed by MIMOOTAStepType.value; merged into step.parameters by the factory.
    # Lets tests pin one phase without rewriting the whole config.
    step_overrides: Optional[dict] = None

    @model_validator(mode="after")
    def _resolve_component_carriers(self) -> "MIMOOTAConfiguration":
        """向后兼容 + 角色强制 (Phase 2g)。

        - component_carriers 为 None / 空 → 从 frequency_hz/bandwidth_mhz/scs
          构造一个单 CC 列表
        - 传入了列表 → 强制 cc[0].role='pcell', cc[1..].role='scell'
        - 列表长度必须 ≥ 1 (运行时这是 measure 的输入合同)
        """
        if not self.component_carriers:
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
    def _validate_external_asc_path(self) -> "MIMOOTAConfiguration":
        """external_asc 模式必须给路径; 其他模式忽略 (留空也允许)。

        2026-05-18 P0-7: 路径存在性 *不* 在 schema 校验 (host filesystem 跟
        测试机器可能不同, 也跟 dev/prod 部署不同)。运行时由
        ExternalAscPathStrategy.generate_and_load 防御性检查并 surface
        actionable error。schema 这里只保证 mode-vs-path 配对完整。
        """
        if self.engine_mode == "external_asc":
            if not self.asc_source_path or not self.asc_source_path.strip():
                raise ValueError(
                    "engine_mode='external_asc' requires asc_source_path to be "
                    "set to an absolute path of a directory containing operator-"
                    "produced channel_InX_OutY.asc files."
                )
        return self
