"""B-2 native-fit 聚类端点的请求/响应模型 (PR-5, P2-14)。

POST /api/v1/cluster_b2_native: RT 射线 → ChannelEgine geometric_native_fit 聚类 +
§6 路径判决 → per-tap 参数表。.tap 字节序列化需现场 Channel Studio (手册 §21:
.tap 专有格式), 本端点到【参数表层】。
"""
from typing import List, Optional, Literal, Tuple

from pydantic import BaseModel, Field


class MPCInput(BaseModel):
    """一条 RT 射线 (多径分量)。phase_rad: 确定性相位类 (ISAC/beam_tracking) 必需。"""
    delay_s: float = Field(..., ge=0.0)
    power_linear: float = Field(..., gt=0.0)
    aoa_deg: float
    aod_deg: float
    zoa_deg: float = 90.0
    zod_deg: float = 90.0
    phase_rad: Optional[float] = None


class F64ProfileInput(BaseModel):
    """F64 能力档 (聚类约束 + 判决门); 现场标定 V1.0 §9。"""
    name: str = 'default'
    tap_budget: int = 24
    rho_thresh: float = 0.06
    delay_resolution_s: float = 5e-9
    has_gcm: bool = False
    large_centroid_thresh_hz: float = 200e3
    fr2_freq_thresh_hz: float = 24e9
    fr2_high_speed_mps: float = 30.0


class B2ClusterRequest(BaseModel):
    rt_rays: List[MPCInput] = Field(..., min_length=1, description="RT 射线 (MPC)")
    ue_velocity_mps: Tuple[float, float, float] = Field(..., description="UE 速度矢量 (m/s)")
    center_frequency_hz: float = Field(..., gt=0.0)
    test_class: Literal['throughput_psd', 'consistency', 'isac_sensing', 'beam_tracking'] = 'throughput_psd'
    f64_profile: F64ProfileInput = Field(default_factory=F64ProfileInput)


class TapParamOut(BaseModel):
    """一个 F64 .tap per-tap 参数行 (镜像 ChannelEgine TapParameter)。"""
    tap_index: int
    delay_s: float
    power_linear: float
    doppler_kind: str
    doppler_shape: str
    doppler_centroid_hz: float
    doppler_spread_hz: float
    doppler_params: dict = {}
    aoa_deg: float
    aod_deg: float
    zoa_deg: float
    zod_deg: float
    as_aoa_deg: float
    as_aod_deg: float
    as_zoa_deg: float
    as_zod_deg: float
    xpr_db: Optional[float] = None
    native_fit_residual: float


class B2ClusterResponse(BaseModel):
    target_path: str = Field(..., description="§6 判决: B2_parametric / B1_baked / GCM_native")
    clustering_algo: str
    reason: str
    f_d_max_hz: float
    is_escalation: bool = False
    tap_params: List[TapParamOut] = Field(
        default_factory=list,
        description="per-tap 参数表 (仅 B2_parametric 路非空; B1/GCM 走烘焙路无 tap)")
    note: str = Field("", description=".tap 字节生成的现场依赖说明")
