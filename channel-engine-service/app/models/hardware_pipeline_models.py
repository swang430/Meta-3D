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
from pydantic import BaseModel, Field


# ==================== 请求体子模型 ====================

class ChamberConfig(BaseModel):
    """暗室物理配置"""
    num_probes: int = Field(..., description="探头数量", ge=8, le=64)
    radius_m: float = Field(..., description="暗室半径 (m)", gt=0)
    dual_polarized: bool = Field(True, description="是否为双极化探头")
    distribution: Literal["ring", "sphere", "custom"] = Field(
        "ring", description="探头分布类型"
    )


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


class CDLModelData(BaseModel):
    """
    CDL 模型数据

    信道簇数据的顶层容器。``model_name`` 字段遵循以下命名规范：

    - 3GPP 标准模型: ``{Scenario} {CDL_Model} {LOS/NLOS}``
      例如: "UMa CDL-C NLOS"
    - Ray-Tracing 数据: ``{ScenarioName} CDL Snapshot-{N}``
      例如: "Highway_Beijing CDL Snapshot-42"
    """
    model_name: str = Field(
        ...,
        description="CDL 模型名称，遵循命名规范"
    )
    pathloss_db: float = Field(..., description="路径损耗 (dB)")
    is_los: bool = Field(False, description="是否为视距")
    clusters: List[CDLCluster] = Field(
        ..., description="多径簇列表", min_length=1
    )


# ==================== 请求体 ====================

class HardwarePipelineRequest(BaseModel):
    """
    硬件流水线合成请求

    对应 Integration Spec v1.0 §2.1
    """
    chamber_config: ChamberConfig
    calibration_data: CalibrationData = Field(default_factory=CalibrationData)
    simulation_rules: SimulationRules
    cdl_model_data: CDLModelData = Field(
        ..., description="CDL 模型数据（3GPP 标准或 Ray-Tracing 导出）"
    )


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

    对应 Integration Spec v1.0 §2.2
    """
    status: Literal["success", "error"] = Field(..., description="状态")
    computation_time_ms: float = Field(..., description="计算耗时 (ms)")
    hardware_artifacts: Optional[HardwareArtifacts] = None
    control_instructions: Optional[ControlInstructions] = None
    diagnostics: Optional[Diagnostics] = None
    error_message: Optional[str] = Field(None, description="错误信息")
