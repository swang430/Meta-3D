"""Health check API endpoint"""
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.database import get_db
from app.schemas.calibration import HealthResponse
from app.config import settings
from app.services.channel_engine_client import CE_BASE_URL

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint

    Returns system status and configuration
    """
    # Check database connectivity
    database_connected = False
    try:
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception:
        pass

    # 只查询软件健康，不探测仪器；未得到明确成功响应时保持不可用。
    channel_engine_available = False
    try:
        with httpx.Client(timeout=2.0, follow_redirects=False) as client:
            response = client.get(f"{CE_BASE_URL.rstrip('/')}/api/v1/health")
            response.raise_for_status()
            payload = response.json()
            channel_engine_available = (
                isinstance(payload, dict)
                and payload.get("status") == "healthy"
                and payload.get("channel_engine_available") is True
            )
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        # 网络、超时或无效响应不能作为可用证据，数据库结果独立保留。
        pass

    return HealthResponse(
        status="healthy" if database_connected and channel_engine_available else "degraded",
        version=settings.app_version,
        database_connected=database_connected,
        mock_instruments=settings.use_mock_instruments,
        channel_engine_available=channel_engine_available
    )
