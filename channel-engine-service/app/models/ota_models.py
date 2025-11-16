"""
OTA Probe Weight Calculation Data Models
Based on 3GPP TR 38.901 channel modeling
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ============================================================================
# Request Models
# ============================================================================

class ProbePosition(BaseModel):
    """单个探头的物理位置（球坐标系）"""
    probe_id: int = Field(..., description="探头ID (1-based)")
    theta: float = Field(..., description="天顶角 (degrees, 0-180)")
    phi: float = Field(..., description="方位角 (degrees, 0-360)")
    r: float = Field(..., description="半径 (meters)")
    polarization: Literal["V", "H", "LHCP", "RHCP"] = Field(..., description="极化方式")


class ProbeArrayConfig(BaseModel):
    """探头阵列配置"""
    num_probes: int = Field(..., description="探头数量", ge=8, le=64)
    radius: float = Field(..., description="暗室半径 (meters)", gt=0)
    probe_positions: List[ProbePosition] = Field(..., description="所有探头的位置列表")


class ScenarioConfig(BaseModel):
    """测试场景配置"""
    scenario_type: Literal["UMa", "UMi", "RMa", "InH"] = Field(
        ...,
        description="3GPP 环境类型"
    )
    cluster_model: Optional[Literal["CDL-A", "CDL-B", "CDL-C", "CDL-D", "CDL-E", "TDL-A", "TDL-B", "TDL-C"]] = Field(
        None,
        description="簇模型类型（可选，用于混合模型）"
    )
    frequency_mhz: float = Field(..., description="中心频率 (MHz)", gt=0)
    use_median_lsps: bool = Field(
        False,
        description="是否使用中值LSP（确定性测试）"
    )


class MIMOConfig(BaseModel):
    """MIMO配置"""
    num_tx_antennas: int = Field(..., description="发射天线数", ge=1, le=8)
    num_rx_antennas: int = Field(..., description="接收天线数", ge=1, le=8)
    tx_antenna_spacing: float = Field(
        0.5,
        description="发射天线间距（波长）"
    )
    rx_antenna_spacing: float = Field(
        0.5,
        description="接收天线间距（波长）"
    )


class ProbeWeightRequest(BaseModel):
    """探头权重计算请求"""
    scenario: ScenarioConfig
    probe_array: ProbeArrayConfig
    mimo_config: MIMOConfig


# ============================================================================
# Response Models
# ============================================================================

class ComplexWeight(BaseModel):
    """复数权重（幅度 + 相位）"""
    magnitude: float = Field(..., description="幅度 (0-1)", ge=0, le=1)
    phase_deg: float = Field(..., description="相位 (degrees, 0-360)")


class ProbeWeight(BaseModel):
    """单个探头的权重"""
    probe_id: int = Field(..., description="探头ID")
    polarization: str = Field(..., description="极化方式")
    weight: ComplexWeight
    enabled: bool = Field(True, description="是否启用此探头")


class ChannelStatistics(BaseModel):
    """信道统计信息"""
    pathloss_db: float = Field(..., description="路径损耗 (dB)")
    rms_delay_spread_ns: Optional[float] = Field(None, description="RMS时延扩展 (ns)")
    angular_spread_deg: Optional[float] = Field(None, description="角度扩展 (degrees)")
    condition: Optional[str] = Field(None, description="信道条件 (LOS/NLOS)")
    num_clusters: int = Field(..., description="簇数量")


class ProbeWeightResponse(BaseModel):
    """探头权重计算响应"""
    probe_weights: List[ProbeWeight] = Field(..., description="所有探头的权重")
    channel_statistics: ChannelStatistics
    success: bool = Field(True, description="计算是否成功")
    message: Optional[str] = Field(None, description="额外信息或错误消息")


# ============================================================================
# Health Check Model
# ============================================================================

class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="服务版本")
    channel_engine_available: bool = Field(..., description="ChannelEngine是否可用")
