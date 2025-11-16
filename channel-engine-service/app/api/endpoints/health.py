"""
Health check endpoint
"""

from fastapi import APIRouter
from app.models.ota_models import HealthCheckResponse
from app.services.channel_engine import ChannelEngineService

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="健康检查",
    description="检查服务是否正常运行以及ChannelEngine是否可用"
)
async def health_check():
    """健康检查端点"""

    service = ChannelEngineService()
    channel_engine_available = service.check_availability()

    return HealthCheckResponse(
        status="healthy" if channel_engine_available else "degraded",
        version=service.version,
        channel_engine_available=channel_engine_available
    )
