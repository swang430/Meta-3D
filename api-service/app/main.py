"""
Meta-3D OTA Test System API Service

Main FastAPI application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.db.database import init_db
from app.api import health, calibration, test_plan

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    logger.info("Starting Meta-3D OTA API Service")
    logger.info(f"Version: {settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Mock instruments: {settings.use_mock_instruments}")

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.warning("Continuing with degraded functionality")

    yield

    # Shutdown
    logger.info("Shutting down Meta-3D OTA API Service")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    **Meta-3D MPAC OTA Test System API**

    This API provides endpoints for system-level calibration of MIMO OTA test systems.

    ## Features

    - **TRP Calibration**: Total Radiated Power validation
    - **TIS Calibration**: Total Isotropic Sensitivity validation
    - **Repeatability Testing**: Measurement precision validation
    - **Calibration Certificates**: Automated certificate generation

    ## Standards

    - 3GPP TS 34.114: 5G NR UE/BS OTA performance requirements
    - CTIA OTA Test Plan Ver. 4.0: Certification test requirements
    - ISO/IEC 17025: Laboratory accreditation requirements
    """,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(calibration.router, prefix=settings.api_v1_prefix)
app.include_router(test_plan.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Meta-3D OTA Test System API",
        "version": settings.app_version,
        "docs": "/api/docs",
        "health": f"{settings.api_v1_prefix}/health"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,  # API Service 使用 8001 端口，避免与 ChannelEngine (8000) 冲突
        reload=settings.debug,
        log_level="info" if settings.debug else "warning"
    )
