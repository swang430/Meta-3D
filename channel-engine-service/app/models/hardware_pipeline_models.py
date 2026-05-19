"""
Hardware Pipeline Data Models

基于 MIMO_First_Integration_Spec.md v1.0 定义的请求/响应模型。
严格对齐 §2.1 请求体和 §2.2 响应体。

CDL 模型命名规范
================
系统中的信道簇数据统一称为"CDL 模型数据"（CDL Model Data），
根据数据来源采用两种命名规则：

1. **3GPP 标准模型**:
   格式: ``{Scenario} {CDL_Model} {LOS/NLOS}``
   示例: ``UMa CDL-C NLOS``, ``UMi CDL-D LOS``, ``RMa CDL-A NLOS``

2. **Ray-Tracing 导出模型**:
   格式: ``{ScenarioName} CDL Snapshot-{N}``
   示例: ``Highway_Beijing CDL Snapshot-42``, ``Urban_Shanghai CDL Snapshot-7``

校准数据默认值
==============
当数据库中没有对应暗室的校准数据时，使用以下默认值：
- cable_loss_db:  从暗室配置表 ``ChamberConfiguration.typical_cable_loss_db`` 读取
                  (DB 列默认值 = 5.0 dB；预置暗室 Small/Medium = 3.0 dB, Large/Custom = 5.0 dB)
- cable_phase_deg: 0.0° (当前版本未接入相位校准表)
- probe_gain_dbi:  从暗室配置表 ``ChamberConfiguration.probe_gain_dbi`` 读取
                  (DB 列默认值 = 8.0 dBi；预置暗室 Small/Medium = 6.0 dBi, Large/Custom = 8.0 dBi)
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


# ==================== 请求体子模型 ====================

class ProbePosition(BaseModel):
    """单 probe 物理位置 (P1-10 / ChannelEgine Phase 8).

    跟 ChannelEgine ``mimo_ota_simulator.data_models.ProbePosition`` wire 完全
    一致 (azimuth_deg ∈ [-360, 360], elevation_deg ∈ [-90, 90], 默认 0)。
    MIMO-First 的 DB ``Probe.position`` 字段 (JSON {azimuth, elevation, radius})
    直接 map 到这里; radius 走 ChamberConfig.radius_m chamber-wide uniform。
    """
    azimuth_deg: float = Field(
        ..., ge=-360.0, le=360.0,
        description="方位角 (水平面, 度数, CCW from +x). DB Probe.position.azimuth.",
    )
    elevation_deg: float = Field(
        0.0, ge=-90.0, le=90.0,
        description="仰角 (度数, 0=水平). DB Probe.position.elevation, 缺省 0.",
    )


class ChamberConfig(BaseModel):
    """暗室物理配置.

    P1-10 (2026-05-19): ``distribution`` 取值跟 ChannelEgine Phase 8 对齐
    (``ring`` / ``multi-ring`` / ``custom``)。``probe_positions`` 仅当
    ``distribution != "ring"`` 时必填; ring 路径向后兼容, 走 ChannelEgine
    ``(p × 360°/N)`` 等距公式。
    """
    num_probes: int = Field(..., description="探头数量", ge=8, le=64)
    radius_m: float = Field(..., description="暗室半径 (m)", gt=0)
    dual_polarized: bool = Field(True, description="是否为双极化探头")
    distribution: Literal["ring", "multi-ring", "custom"] = Field(
        "ring",
        description=(
            "探头分布. 'ring' (默认): 等距单环, ChannelEgine 走 (p × 360°/N) 公式. "
            "'multi-ring' / 'custom': 任意几何, 必须显式传 probe_positions."
        ),
    )
    probe_positions: Optional[List[ProbePosition]] = Field(
        None,
        description=(
            "P1-10: 每 probe 物理 az/el. distribution != 'ring' 时必填且 "
            "len() == num_probes; ring 时可省略 (Pydantic validator 强制此规则)."
        ),
    )

    @model_validator(mode='after')
    def _check_distribution_consistency(self) -> 'ChamberConfig':
        """非 ring distribution 必须显式传 probe_positions 且长度等于 num_probes.

        Why: ChannelEgine Phase 8 ``ChamberConfig`` 也做同样 check (cross-repo
        spec). 在 MIMO-First 微服务侧也做一遍, 让 fail-loud 更早 (HTTP 422 vs
        ChannelEgine 内部 ValueError 包成 generic 500)。
        Ring 路径不要求 probe_positions, 保持现有 lab 8-probe ring smoke 向后
        兼容; 但允许显式传 (会被 ChannelEgine 忽略, 走 ring 公式)。
        """
        if self.distribution != "ring" and not self.probe_positions:
            raise ValueError(
                f"distribution={self.distribution!r} requires probe_positions "
                f"to be set (one per probe); got None."
            )
        if self.probe_positions is not None:
            if len(self.probe_positions) != self.num_probes:
                raise ValueError(
                    f"probe_positions length ({len(self.probe_positions)}) "
                    f"must match num_probes ({self.num_probes})."
                )
        return self


class CalibrationEntry(BaseModel):
    """
    单端口校准数据

    默认值来源:
    - cable_loss_db: ChamberConfiguration.typical_cable_loss_db (DB默认=5.0 dB)
    - cable_phase_deg: 固定 0.0° (TODO: 接入相位校准服务)
    - probe_gain_dbi: ChamberConfiguration.probe_gain_dbi (DB默认=8.0 dBi)
    """
    port_id: int = Field(..., description="端口 ID (1-based)")
    cable_loss_db: float = Field(5.0, description="电缆损耗 (dB), 默认=5.0")
    cable_phase_deg: float = Field(0.0, description="电缆相位偏移 (deg), 默认=0.0")
    probe_gain_dbi: float = Field(8.0, description="探头增益 (dBi), 默认=8.0")


class CalibrationData(BaseModel):
    """校准数据集"""
    entries: List[CalibrationEntry] = Field(
        default_factory=list,
        description="每端口校准条目"
    )


class AntennaConfig(BaseModel):
    """天线阵列配置"""
    array_type: Literal["ULA", "URA", "UCA"] = Field("ULA", description="阵列类型")
    num_rows: int = Field(1, description="行数", ge=1)
    num_cols: int = Field(2, description="列数", ge=1)
    spacing_h: float = Field(0.5, description="水平间距 (波长)")
    spacing_v: float = Field(0.5, description="垂直间距 (波长)")
    # 2026-05-18 P0-7 / Spec v2.0: ChannelEgine Phase 6 dual-pol synthesizer
    # 要求 Tx/Rx 各自显式声明 V 或 H. 历史默认 V 维持 back-compat (单 pol DUT).
    polarization: Literal["V", "H"] = Field(
        "V", description="天线极化方向 (V=垂直, H=水平). ChannelEgine Phase 6 dual-pol 必需."
    )


class SimulationRules(BaseModel):
    """仿真规则"""
    center_frequency_hz: float = Field(..., description="中心频率 (Hz)", gt=0)
    target_tx_power_dbm: float = Field(0.0, description="目标发射功率 (dBm)")
    target_rsrp_dbm: float = Field(-85.0, description="目标 RSRP (dBm)")
    target_snr_db: float = Field(20.0, description="目标 SNR (dB)")
    tx_antenna: AntennaConfig = Field(
        default_factory=AntennaConfig, description="发射天线配置"
    )
    rx_antenna: AntennaConfig = Field(
        default_factory=AntennaConfig, description="接收天线配置"
    )
    ue_velocity_kph: float = Field(0.0, description="UE 速度 (km/h)", ge=0)
    # 2026-05-18 P0-7 / Spec v2.0: 3-vector m/s, ChannelEgine 内部期望此形式
    # (kph scalar 是 1D 简化, 不能表达多普勒方向). None → adapter 从 kph 派生
    # [kph/3.6, 0, 0] 维持 back-compat.
    ue_velocity_mps: Optional[List[float]] = Field(
        None,
        description=(
            "UE 速度 3-vector (m/s) [vx, vy, vz]. 设置时优先于 ue_velocity_kph; "
            "None 时 adapter 从 kph 派生 [kph/3.6, 0, 0] (沿 x 轴运动)."
        ),
    )
    # 2026-05-18 P0-7 / Spec v2.0: 信道合成方法选择
    synthesis_method: Literal["strict_pfs", "ray", "cluster_legacy"] = Field(
        "strict_pfs",
        description=(
            "ChannelEgine 合成方法. strict_pfs (推荐, Phase 1+): per-(probe, cluster) "
            "独立 fading, 跟 phase cal 兼容. ray: 传统 20-sub-ray, 大平均统计场景. "
            "cluster_legacy: rank-1 outer product, DeprecationWarning, 仅 back-compat."
        ),
    )


class CDLCluster(BaseModel):
    """
    CDL 模型簇参数

    表示信道中一个多径簇的物理特征，可来自 3GPP 标准参数表
    或 Ray-Tracing 仿真输出。
    """
    delay_s: float = Field(..., description="时延 (s)")
    power_relative_linear: float = Field(..., description="相对功率 (线性)")
    aoa_deg: float = Field(..., description="到达方位角 (deg)")
    aod_deg: float = Field(0.0, description="出发方位角 (deg)")
    zoa_deg: float = Field(90.0, description="到达天顶角 (deg)")
    zod_deg: float = Field(90.0, description="出发天顶角 (deg)")
    as_aoa_deg: float = Field(2.0, description="到达角度扩展 (deg)")
    # 2026-05-18 P0-7 / Spec v2.0: ChannelEgine Phase 6 cross-pol ratio.
    # 7 dB 是 TR 38.901 §7.5 默认 (NLOS UMa/UMi/RMa); LOS 通常用 0 dB.
    xpr_db: float = Field(
        7.0,
        description="交叉极化比 (dB), TR 38.901 §7.5 默认 7 dB",
    )
    # 2026-05-18 P0-7 / Spec v2.0: ChannelEgine Phase 5 per-ray init phases.
    # 4-element vec 对应 [VV, VH, HV, HH] init phases. None → ChannelEgine 内部
    # 随机初始化 (跨 realization 不可重复); 显式给定则 trace 可复现.
    initial_phases_rad: Optional[List[float]] = Field(
        None,
        description=(
            "4-element 初始相位 (rad) [VV, VH, HV, HH], 控制 dual-pol 合成的 "
            "起始相位. None → 随机. Phase 5+ 才会被读."
        ),
    )


class CDLModelData(BaseModel):
    """
    CDL 模型数据

    信道簇数据的顶层容器。``model_name`` 字段遵循以下命名规范：

    - 3GPP 标准模型: ``{Scenario} {CDL_Model} {LOS/NLOS}``
      例如: "UMa CDL-C NLOS"
    - Ray-Tracing 数据: ``{ScenarioName} CDL Snapshot-{N}``
      例如: "Highway_Beijing CDL Snapshot-42"

    2026-05-19 P1-7: `clusters` 改 Optional. input_mode='custom' 时仍需 ≥1 簇;
    input_mode='standard' 时该字段被忽略 (ChannelEgine `Standard3GPPBuilder`
    内部从 38.901 表生成簇)。dispatch + 校验在 HardwarePipelineRequest model
    validator.
    """
    model_name: str = Field(
        ...,
        description="CDL 模型名称，遵循命名规范"
    )
    pathloss_db: float = Field(..., description="路径损耗 (dB)")
    is_los: bool = Field(False, description="是否为视距")
    clusters: Optional[List[CDLCluster]] = Field(
        None,
        description=(
            "多径簇列表。input_mode='custom' 时必填 (≥1 簇); "
            "input_mode='standard' 时忽略 (ChannelEgine 从 38.901 表生成)。"
        ),
    )
    # 2026-05-18 P0-7 / Spec v2.0: LOS K-factor (dB), only meaningful when is_los=True.
    # TR 38.901 §7.5.6 LOS-mode K-factor boost on cluster #0 power.
    k_factor_db: Optional[float] = Field(
        None,
        description=(
            "LOS K-factor (dB). 仅 is_los=True 时被读; None 用 ChannelEgine "
            "内部 TR 38.901 §7.5.6 默认值. NLOS 时该字段被忽略."
        ),
    )


# 2026-05-19 P1-7: ChannelEgine `Standard3GPPBuilder` 接受的 scenario / cluster_model
# 枚举值, 跟 [`ChannelEgine/mimo_ota_simulator/channel_builders.py`] 的常量对齐.
# 这里只是字符串规约 (不是 3GPP 数据本身) — 数据生成在 ChannelEgine 内部.
ScenarioName = Literal[
    "UMa", "UMi-StreetCanyon", "UMi-OpenArea", "RMa",
    "InH-Office", "SMa", "InF",
]
ClusterModelName = Literal[
    "Stochastic", "CDL-A", "CDL-B", "CDL-C", "CDL-D", "CDL-E", "SCME",
]
ForceCondition = Literal["LOS", "NLOS", "auto"]


class Standard3GPPConfig(BaseModel):
    """3GPP TR 38.901 standard-mode 输入参数 (input_mode='standard' 时必填).

    数据生成在 ChannelEgine 内部的 38.901 generator (`Standard3GPPBuilder`);
    MIMO-First 这一层只透传操作员的模型选择 + 几何配置, 不实现 38.901 表。
    """
    scenario_name: ScenarioName = Field(
        ...,
        description=(
            "Large-scale environment (TR 38.901 §7.2). 决定 path loss + LSP "
            "统计特性. 取值见 ScenarioName Literal."
        ),
    )
    cluster_model_name: ClusterModelName = Field(
        "Stochastic",
        description=(
            "Small-scale cluster model. `Stochastic` = 38.901 §7.5 default; "
            "CDL-A..E = §7.7.1 fixed clustered delay line; SCME = legacy."
        ),
    )
    force_condition: ForceCondition = Field(
        "auto",
        description=(
            "LOS / NLOS / auto. auto = 让 38.901 generator 按 scenario "
            "几何概率决定 (推荐); LOS/NLOS = 强制覆盖."
        ),
    )
    bs_position: List[float] = Field(
        default_factory=lambda: [0.0, 0.0, 25.0],
        description="BS position [x, y, z] (m). 默认 [0,0,25] (UMa 典型基站高度)",
        min_length=3, max_length=3,
    )
    ue_position: List[float] = Field(
        default_factory=lambda: [50.0, 0.0, 1.5],
        description="UE position [x, y, z] (m). 默认 [50,0,1.5] (UE 在 50m 外 1.5m 高)",
        min_length=3, max_length=3,
    )
    random_seed: Optional[int] = Field(
        None,
        description="38.901 generator 随机种子, None 时每次跑随机 realization",
    )


# ==================== 请求体 ====================

class HardwarePipelineRequest(BaseModel):
    """
    硬件流水线合成请求

    对应 Integration Spec v1.0 §2.1 + v2.1 (2026-05-19 P1-7 加 input_mode 分路)
    """
    chamber_config: ChamberConfig
    calibration_data: CalibrationData = Field(default_factory=CalibrationData)
    simulation_rules: SimulationRules
    cdl_model_data: CDLModelData = Field(
        ..., description="CDL 模型数据（3GPP 标准或 Ray-Tracing 导出）"
    )
    # 2026-05-19 P1-7: dispatch 入口
    input_mode: Literal["standard", "custom"] = Field(
        "custom",
        description=(
            "信道生成入口. 'standard' = ChannelEgine 内部 38.901 generator "
            "(用 standard_3gpp 字段). 'custom' = 操作员/上游提供 CDLCluster "
            "列表 (用 cdl_model_data.clusters). 默认 'custom' 保持 P0-7 行为."
        ),
    )
    standard_3gpp: Optional[Standard3GPPConfig] = Field(
        None,
        description="input_mode='standard' 时必填. ChannelEgine 38.901 输入参数.",
    )

    @model_validator(mode="after")
    def _validate_input_mode_consistency(self) -> "HardwarePipelineRequest":
        """input_mode 跟 clusters / standard_3gpp 必须一致 — fail-fast 比让
        ChannelEgine 那边返回 generic error 友好得多 (2026-05-19 P1-7)."""
        if self.input_mode == "standard":
            if self.standard_3gpp is None:
                raise ValueError(
                    "input_mode='standard' requires standard_3gpp config "
                    "(scenario_name + cluster_model_name + positions)."
                )
        else:  # custom
            if not self.cdl_model_data.clusters:
                raise ValueError(
                    "input_mode='custom' requires cdl_model_data.clusters "
                    "(≥1 cluster). For 38.901 standard models use "
                    "input_mode='standard' + standard_3gpp."
                )
        return self


# ==================== 响应体子模型 ====================

class HardwareArtifacts(BaseModel):
    """硬件驱动产物"""
    f64_asc_files_zip_base64: str = Field(
        ..., description=".asc 文件 ZIP 的 Base64 编码"
    )
    total_files_generated: int = Field(..., description="生成的 .asc 文件总数")
    cdl_model_name: str = Field(
        ..., description="生成此产物所使用的 CDL 模型名称"
    )


class ControlInstructions(BaseModel):
    """硬件控制指令"""
    f64_baseband_power_dbm: float = Field(
        ..., description="推荐的 F64 基带发射功率 (dBm)"
    )
    external_attenuators_db: List[float] = Field(
        default_factory=list, description="外部衰减器设置 (dB)"
    )
    target_achieved_rsrp_dbm: float = Field(
        ..., description="预期达到的 RSRP (dBm)"
    )


class Diagnostics(BaseModel):
    """诊断信息"""
    spatial_correlation: Optional[float] = Field(
        None, description="空间相关性"
    )
    matrix_energy_scaling_factor: Optional[float] = Field(
        None, description="矩阵能量缩放因子"
    )


# ==================== 响应体 ====================

class HardwarePipelineResponse(BaseModel):
    """
    硬件流水线合成响应

    对应 Integration Spec v1.0 §2.2 + v2.0 (mock_mode 字段, 2026-05-18 P0-7)
    """
    status: Literal["success", "error"] = Field(..., description="状态")
    computation_time_ms: float = Field(..., description="计算耗时 (ms)")
    hardware_artifacts: Optional[HardwareArtifacts] = None
    control_instructions: Optional[ControlInstructions] = None
    diagnostics: Optional[Diagnostics] = None
    error_message: Optional[str] = Field(None, description="错误信息")
    mock_mode: bool = Field(
        False,
        description=(
            "True 当且仅当服务以 MOCK_ASC_MODE=1 启动且本次响应是 mock 合成 "
            "(占位 .asc, 非真实 PFS)。生产模式永远 False。"
        ),
    )
