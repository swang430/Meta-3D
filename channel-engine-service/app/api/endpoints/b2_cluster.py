"""B-2 native-fit 聚类端点 (PR-5, P2-14)。

POST /api/v1/cluster_b2_native: RT 射线 → ChannelEgine `geometric_native_fit` 聚类 +
§6 `select_path_and_clustering` 路径判决 → `extract_tap_parameters` per-tap 参数表。

边界: `.tap` 字节序列化需现场 Channel Studio (手册 §21: `.tap` 专有格式无法离线生成);
本端点产出到【参数表层】, 现场用 Channel Studio 把参数表落成 `.tap`。
B1_baked/GCM_native 判决 → 走烘焙路 (`.asc`), 本端点不出 tap; ESCALATE → 422 fail-loud。

ChannelEgine 算法经 CHANNEL_ENGINE_PATH 运行时 import (同 hardware_pipeline.py)。
"""
import os
import sys
import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.models.b2_cluster_models import (
    B2ClusterRequest, B2ClusterResponse, TapParamOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()

CHANNEL_ENGINE_PATH = os.environ.get('CHANNEL_ENGINE_PATH', '').strip()


def _import_b2_modules():
    """运行时 import ChannelEgine B-2 算法 (注入 CHANNEL_ENGINE_PATH 到 sys.path)。
    失败 raise → 端点 503 (同 hardware_pipeline 的 fail-fast, 不静默 mock)。"""
    if not CHANNEL_ENGINE_PATH:
        raise RuntimeError(
            "CHANNEL_ENGINE_PATH env var 未设置; B-2 聚类端点需要本地 ChannelEgine clone "
            "(含 P2-14 PR-3/4: path_decision + b2_tap_params)。"
        )
    if CHANNEL_ENGINE_PATH not in sys.path:
        sys.path.insert(0, CHANNEL_ENGINE_PATH)
    from mimo_ota_simulator.geometric_native_fit import (  # type: ignore
        MPC, F64CapabilityProfile, geometric_native_fit,
    )
    from mimo_ota_simulator.b2_tap_params import extract_tap_parameters  # type: ignore
    from mimo_ota_simulator.path_decision import select_path_and_clustering  # type: ignore
    return (MPC, F64CapabilityProfile, geometric_native_fit,
            extract_tap_parameters, select_path_and_clustering)


@router.post(
    "/cluster_b2_native",
    response_model=B2ClusterResponse,
    summary="B-2 native-fit 聚类 + per-tap 参数表",
    description="RT 射线 → geometric_native_fit 聚类 → §6 路径判决 → per-tap 参数表。"
                ".tap 字节生成需现场 Channel Studio。",
)
async def cluster_b2_native(request: B2ClusterRequest) -> B2ClusterResponse:
    try:
        (MPC, F64CapabilityProfile, geometric_native_fit,
         extract_tap_parameters, select_path_and_clustering) = _import_b2_modules()
    except Exception as e:
        logger.error("B-2 modules unavailable: %s", e)
        raise HTTPException(status_code=503, detail=f"ChannelEgine B-2 算法不可用: {e}")

    mpcs = [
        MPC(delay_s=r.delay_s, power_linear=r.power_linear,
            aoa_deg=r.aoa_deg, aod_deg=r.aod_deg, zoa_deg=r.zoa_deg, zod_deg=r.zod_deg,
            phase_rad=r.phase_rad)
        for r in request.rt_rays
    ]
    f64 = F64CapabilityProfile(**request.f64_profile.model_dump())
    v = request.ue_velocity_mps
    fc = request.center_frequency_hz

    # §6 路径判决 (test_class 驱动); ValueError (未知 class / 确定性类缺 phase_rad / 空) → 422
    try:
        decision = select_path_and_clustering(request.test_class, mpcs, v, fc, f64)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"路径判决拒绝: {e}")

    # ESCALATE = 需 GCM 但无 license → fail-loud, 绝不静默回落 (设计 §6)
    if decision.is_escalation:
        raise HTTPException(status_code=422, detail=f"路径判决 ESCALATE (需现场升级): {decision.reason}")

    tap_params = []
    if decision.target_path == 'B2_parametric':
        annotated = geometric_native_fit(mpcs, v, fc, f64)
        taps = extract_tap_parameters(annotated)
        tap_params = [TapParamOut(**asdict(t)) for t in taps]
        note = (f".tap 字节序列化需现场 Channel Studio (手册 §21: .tap 专有格式无法离线生成); "
                f"本端点产出 {len(tap_params)} 行 per-tap 参数表, 现场用 Channel Studio 落成 .tap。")
    else:
        # B1_baked / GCM_native → 走烘焙路 (.asc / GCM .smu), 非参数化 .tap
        note = (f"判决为 {decision.target_path} (非 B-2 参数化): 走 "
                f"{'B-1 烘焙 .asc (b1_annotated_baker)' if decision.target_path == 'B1_baked' else 'GCM .smu'}, "
                f"无 tap 参数表。")

    logger.info(
        "B-2 聚类: test_class=%s → %s (%s), f_D,max=%.0fHz, %d taps",
        request.test_class, decision.target_path, decision.clustering_algo,
        decision.f_d_max_hz, len(tap_params),
    )
    return B2ClusterResponse(
        target_path=decision.target_path,
        clustering_algo=decision.clustering_algo,
        reason=decision.reason,
        f_d_max_hz=decision.f_d_max_hz,
        is_escalation=False,
        tap_params=tap_params,
        note=note,
    )
