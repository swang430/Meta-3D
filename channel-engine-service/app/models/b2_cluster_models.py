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


# ==================== P2-16 S3-2a: F4 多快照轨迹 ====================

class B2TrajectoryRequest(BaseModel):
    """多快照 RT 轨迹 → ChannelEgine native_fit_trajectory (F4): 逐快照 native-fit + 跨快照
    贪心匹配跟踪 (簇身份 + 生灭)。仅吞吐/一致类 (B2 参数化路); 确定性相位类 (ISAC/波束) 走
    F5 phase_continuous → B-1 烘焙路, 非本端点。单快照用 cluster_b2_native。"""
    snapshots: List[List[MPCInput]] = Field(
        ..., min_length=2, description="≥2 快照, 每快照一组 RT 射线 (单快照用 cluster_b2_native)")
    ue_velocity_mps: Tuple[float, float, float] = Field(
        ..., description="共享 UE 速度矢量 (m/s); per-snapshot 速度 V0.1 暂不支持")
    center_frequency_hz: float = Field(..., gt=0.0)
    test_class: Literal['throughput_psd', 'consistency'] = Field(
        'throughput_psd', description="确定性类 (isac_sensing/beam_tracking) 走 F5 烘焙路, 非本端点")
    f64_profile: F64ProfileInput = Field(default_factory=F64ProfileInput)
    # 轨迹元数据 (RT 采样): native_fit_trajectory 必需关键字
    skeleton_rate_hz: float = Field(..., gt=0.0, description="快照采样率 (Hz)")
    delta_d_geo_m: float = Field(..., gt=0.0, description="相邻快照几何位移 (m)")
    route_len_m: float = Field(..., gt=0.0, description="轨迹总长 (m)")


class ClusterLifecycleOut(BaseModel):
    """一个跟踪簇在某快照的生命周期标注 (跨快照身份 + 生灭)。"""
    cluster_id: int
    power_ramp: str = Field(..., description="stable / birth / death / transient")
    birth_index: Optional[int] = None
    death_index: Optional[int] = None


class TrajectorySnapshotOut(BaseModel):
    """轨迹一帧: 该快照的 per-tap 参数表 + 簇生命周期标注。"""
    index: int
    time_s: Optional[float] = None
    tap_params: List[TapParamOut] = Field(default_factory=list)
    clusters: List[ClusterLifecycleOut] = Field(default_factory=list)


class B2TrajectoryResponse(BaseModel):
    num_snapshots: int
    num_tracked_clusters: int = Field(..., description="跨快照唯一 cluster_id 数 (跟踪到的簇总数)")
    snapshots: List[TrajectorySnapshotOut] = Field(default_factory=list)
    note: str = Field("", description=".tap 字节 / 多快照 .rtc 落地的现场依赖说明")
