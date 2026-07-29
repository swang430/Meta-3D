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
from app.api import dashboard, probe, instrument, monitoring, report, road_test, alert, sync, topology, scenario, switch_topology
from app.api import probe_calibration, channel_calibration, workflow, calibration_report, chamber
from app.api import lab_profile, diagnostic_run, diagnostic_sequence
from app.api import standard_channel
from app.api import dut_profile
from app.api import sim_profile
from app.api import custom_cdl_profile
from app.api import channel_asset
from app.api.path_loss_calibration import router as path_loss_router, orchestrator_router, compensation_router, switch_router, e2e_router, phase_router, ce_router, baseline_router
from app.api.commissioning import router as commissioning_router
from app.api.system_logs import router as system_logs_router

# Configure logging — 集中式四路日志配置
from app.core.logging_config import setup_logging
setup_logging(
    debug=settings.debug,
    log_dir=settings.log_dir,
    log_retention_days=settings.log_retention_days,
    scpi_enabled=settings.log_scpi_enabled,
    db_log_enabled=settings.log_db_enabled,
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

    # DB 连通性 fail-loud 预检 (在 init_db 之前): 重启后 postgres 端口转发丢失等场景,
    # 立刻打一条含修复命令的显著 banner, 不再让根因被下面的 try/except 吞成满屏静默 500。
    # pytest 下 retries=0 + 不打 banner (避免拖慢 / 噪音; 测试用 SQLite 必然可达)。
    import sys as _sys
    from app.db.database import preflight_database
    _under_test = "pytest" in _sys.modules
    preflight_database(retries=0 if _under_test else 5, emit_fatal_log=not _under_test)

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.warning("Continuing with degraded functionality")

    # 门审 #217 F4 的后继: 复位计划链遗留的僵尸行。ARCH-1 S4b 删掉了
    # test_plan_runner, 该职责由 test_case_runner 接管 (三类行: TestPlan /
    # TestStep / TestExecution)。S4b 后不再产生新的这类行, 但**存量还在两台
    # 现场机器的库里** —— ①② 会被 dashboard 计进 active_test_plans 且已无
    # cancel/complete 端点可清, ③ 会永久 409 拦住 HAL reload。
    try:
        from app.services.test_case_runner import (
            reset_orphaned_plan_chain_rows,
        )
        reset_orphaned_plan_chain_rows()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"计划链僵尸行复位失败 (不阻塞启动): {e}")

    # ARCH-1 S1: 同理复位 case-runner 的 stale running 执行行 (谓词收窄到
    # executed_by=test_case_runner, 不碰暗室首测/VRT/计划链的执行行)。
    try:
        from app.services.test_case_runner import (
            reset_stale_running_case_executions,
        )
        reset_stale_running_case_executions()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"stale 用例执行复位失败 (不阻塞启动): {e}")

    # ARCH-1 S3: 暗室首测 / 单相位诊断的行现在也标 running (让 HAL reload
    # 闸门看得见), 所以它们的僵尸行同样要复位 —— 否则一次重启就留下永久
    # 拦死 reload 的行。相位同步跑在请求线程上, 启动时刻的 running 必是僵尸。
    try:
        from app.api.commissioning import (
            reset_stale_running_commissioning_executions,
        )
        reset_stale_running_commissioning_executions()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"stale 暗室首测执行复位失败 (不阻塞启动): {e}")

    # P0-1: auto-seed factory-defaults DB on startup (idempotent — re-runs
    # are no-ops via bootstrap_history version pinning). Without this an
    # empty deploy strands the operator on "create your first chamber"
    # until they remember to run `python -m scripts.bootstrap` manually.
    # Failure of one seeder does not abort the others; failure of the
    # whole bootstrap step does not abort app startup.
    if settings.bootstrap_on_startup:
        try:
            from app.db.database import SessionLocal
            from app.services.bootstrap import run_bootstrap_on_startup
            ok = run_bootstrap_on_startup(SessionLocal)
            if not ok:
                logger.warning(
                    "Bootstrap finished with at least one failed seeder — "
                    "see [bootstrap] log lines above for detail"
                )
        except Exception as e:
            logger.error(f"Bootstrap startup hook crashed: {e}")
            logger.warning("Continuing without auto-seeded defaults")
    else:
        logger.info("[bootstrap] BOOTSTRAP_ON_STARTUP=false — skipping auto-seed")

    # Initialize HAL service (Phase 2.4.5)
    from app.services.instrument_hal_service import initialize_hal_service, DriverMode
    try:
        hal_mode = DriverMode.MOCK if settings.use_mock_instruments else DriverMode.REAL
        await initialize_hal_service(mode=hal_mode)
        logger.info(f"Instrument HAL service initialized in {hal_mode.value} mode")
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

# API 请求审计日志
from app.core.audit_middleware import AuditMiddleware
app.add_middleware(AuditMiddleware)

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
app.include_router(switch_topology.router, prefix=settings.api_v1_prefix, tags=["Switch Topologies"])

# Scenario navigation
app.include_router(scenario.router, prefix=settings.api_v1_prefix, tags=["Scenario Navigation"])

# Calibration workflow engine
app.include_router(workflow.router, prefix=settings.api_v1_prefix, tags=["Calibration Workflows"])

# Calibration reports
app.include_router(calibration_report.router, prefix=settings.api_v1_prefix, tags=["Calibration Reports"])

# Chamber configuration
app.include_router(chamber.router, prefix=settings.api_v1_prefix, tags=["Chamber Configuration"])

# Lab profile (P2) — list + RF chain resolution for calibration UI preview
app.include_router(lab_profile.router, prefix=settings.api_v1_prefix)
app.include_router(standard_channel.router, prefix=settings.api_v1_prefix)
app.include_router(dut_profile.router, prefix=settings.api_v1_prefix, tags=["DUT Profile"])
app.include_router(sim_profile.router, prefix=settings.api_v1_prefix, tags=["SIM Profile"])
app.include_router(custom_cdl_profile.router, prefix=settings.api_v1_prefix, tags=["Custom CDL Profile"])
app.include_router(channel_asset.router, prefix=settings.api_v1_prefix, tags=["Channel Asset"])

# Diagnostic runs (P3) — workshop-tier audit trail for SCPI / Commissioning
app.include_router(diagnostic_run.router, prefix=settings.api_v1_prefix)

# Diagnostic sequences (P3 Phase 2) — list + run sequence modules
app.include_router(diagnostic_sequence.router, prefix=settings.api_v1_prefix)

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

# 3GPP Static MIMO OTA Commissioning Sandbox
app.include_router(commissioning_router, prefix=settings.api_v1_prefix, tags=["暗室首测"])

# System Logs Management
app.include_router(system_logs_router, prefix=settings.api_v1_prefix)


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
