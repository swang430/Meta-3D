"""Health check API endpoint"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.database import get_db
from app.schemas.calibration import HealthResponse
from app.config import settings

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

    return HealthResponse(
        status="healthy" if database_connected else "degraded",
        version=settings.app_version,
        database_connected=database_connected,
        mock_instruments=settings.use_mock_instruments
    )
