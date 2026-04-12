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
from app.api import health, calibration, test_plan, test_execution, test_sequence
from app.api import dashboard, probe, instrument, monitoring, report, road_test, alert, sync, topology, scenario
from app.api import probe_calibration, channel_calibration, workflow, calibration_report, chamber
from app.api.path_loss_calibration import router as path_loss_router, orchestrator_router, compensation_router, switch_router, e2e_router, phase_router, ce_router, baseline_router

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

    # Initialize HAL service (Phase 2.4.5)
    from app.services.instrument_hal_service import initialize_hal_service, DriverMode
    try:
        await initialize_hal_service(mode=DriverMode.MOCK)
        logger.info("Instrument HAL service initialized with mock drivers")
    except Exception as e:
        logger.error(f"HAL service initialization failed: {e}")
        logger.warning("Continuing without HAL - monitoring will use fallback data")

    # Start background tasks
    import asyncio
    from app.api.monitoring import monitoring_data_broadcaster

    broadcaster_task = asyncio.create_task(monitoring_data_broadcaster())
    logger.info("Monitoring data broadcaster started")

    yield

    # Shutdown
    logger.info("Shutting down Meta-3D OTA API Service")

    # Cancel background tasks
    broadcaster_task.cancel()
    try:
        await broadcaster_task
    except asyncio.CancelledError:
        logger.info("Monitoring broadcaster stopped")

    # Shutdown HAL service
    from app.services.instrument_hal_service import shutdown_hal_service
    try:
        await shutdown_hal_service()
        logger.info("HAL service shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down HAL service: {e}")

    logger.info("All background tasks terminated")


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
app.include_router(probe_calibration.router, prefix=settings.api_v1_prefix)
app.include_router(channel_calibration.router, prefix=settings.api_v1_prefix)
app.include_router(test_plan.router, prefix=settings.api_v1_prefix)
app.include_router(test_execution.router, prefix=settings.api_v1_prefix)
app.include_router(test_sequence.router, prefix=settings.api_v1_prefix)

# Phase 1: New routers for dashboard, probes, instruments, monitoring
app.include_router(dashboard.router, prefix=settings.api_v1_prefix, tags=["Dashboard"])
app.include_router(probe.router, prefix=settings.api_v1_prefix, tags=["Probes"])
app.include_router(instrument.router, prefix=settings.api_v1_prefix, tags=["Instruments"])
app.include_router(monitoring.router, prefix=settings.api_v1_prefix, tags=["Monitoring"])

# Phase 3: Report generation and management
app.include_router(report.router, prefix=settings.api_v1_prefix, tags=["Reports"])

# Phase 3.7: Virtual Road Test
app.include_router(road_test.router, prefix=settings.api_v1_prefix, tags=["Virtual Road Test"])

# Alert system
app.include_router(alert.router, prefix=settings.api_v1_prefix, tags=["Dashboard Alerts"])

# Hardware synchronization
app.include_router(sync.router, prefix=settings.api_v1_prefix, tags=["Hardware Synchronization"])

# Topology configuration
app.include_router(topology.router, prefix=settings.api_v1_prefix, tags=["Topologies"])

# Scenario navigation
app.include_router(scenario.router, prefix=settings.api_v1_prefix, tags=["Scenario Navigation"])

# Calibration workflow engine
app.include_router(workflow.router, prefix=settings.api_v1_prefix, tags=["Calibration Workflows"])

# Calibration reports
app.include_router(calibration_report.router, prefix=settings.api_v1_prefix, tags=["Calibration Reports"])

# Chamber configuration
app.include_router(chamber.router, prefix=settings.api_v1_prefix, tags=["Chamber Configuration"])

# Path loss calibration
app.include_router(path_loss_router, prefix=settings.api_v1_prefix)
app.include_router(orchestrator_router, prefix=settings.api_v1_prefix)
app.include_router(compensation_router, prefix=settings.api_v1_prefix)

# RF Switch calibration (CAL-02)
app.include_router(switch_router, prefix=settings.api_v1_prefix)

# E2E Calibration (CAL-03)
app.include_router(e2e_router, prefix=settings.api_v1_prefix)

# Phase Calibration (CAL-04)
app.include_router(phase_router, prefix=settings.api_v1_prefix)

# CE Internal Calibration (CAL-06)
app.include_router(ce_router, prefix=settings.api_v1_prefix)

# Relative Calibration (Baseline)
app.include_router(baseline_router, prefix=settings.api_v1_prefix)


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
        port=8000,  # API Service 使用 8000 端口
        reload=settings.debug,
        log_level="info" if settings.debug else "warning"
    )
