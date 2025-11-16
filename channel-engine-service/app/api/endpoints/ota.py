"""
OTA probe weight calculation endpoint
"""

from fastapi import APIRouter, HTTPException
from app.models.ota_models import ProbeWeightRequest, ProbeWeightResponse
from app.services.channel_engine import ChannelEngineService

router = APIRouter()


@router.post(
    "/generate-probe-weights",
    response_model=ProbeWeightResponse,
    summary="生成探头权重",
    description="基于3GPP信道模型和探头阵列配置，计算OTA测试所需的探头权重"
)
async def generate_probe_weights(request: ProbeWeightRequest):
    """
    生成探头权重端点

    处理流程:
    1. 验证请求参数
    2. 调用ChannelEngine生成信道模型
    3. 计算探头权重
    4. 返回结果

    Args:
        request: ProbeWeightRequest - 包含场景、探头阵列和MIMO配置

    Returns:
        ProbeWeightResponse - 包含探头权重和信道统计信息

    Raises:
        HTTPException: 如果计算失败
    """

    # 验证探头数量
    if len(request.probe_array.probe_positions) != request.probe_array.num_probes:
        raise HTTPException(
            status_code=400,
            detail=f"探头位置数量 ({len(request.probe_array.probe_positions)}) "
                   f"与配置的探头数量 ({request.probe_array.num_probes}) 不匹配"
        )

    # 验证探头ID唯一性
    probe_ids = [p.probe_id for p in request.probe_array.probe_positions]
    if len(probe_ids) != len(set(probe_ids)):
        raise HTTPException(
            status_code=400,
            detail="探头ID必须唯一"
        )

    # 调用服务
    service = ChannelEngineService()
    response = service.generate_probe_weights(request)

    # 检查是否成功
    if not response.success:
        raise HTTPException(
            status_code=500,
            detail=response.message or "权重计算失败"
        )

    return response
