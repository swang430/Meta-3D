"""
Channel Engine Service - FastAPI Application
OTA探头权重计算服务
"""

import logging
import logging.handlers
import json
import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import health, ota, hardware_pipeline


# ============================================================================
# 日志配置 — 写入 api-service/logs/ 以便统一管理
# ============================================================================

class _JsonFormatter(logging.Formatter):
    """与 api-service 的 JsonFormatter 格式一致的 JSON 日志格式化器"""
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.utcfromtimestamp(record.created).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "service": "channel-engine",
            "session_id": getattr(record, "session_id", "-"),
            "instrument_id": getattr(record, "instrument_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False, default=str)


def _setup_ce_logging():
    """
    初始化 Channel Engine 日志，写入 api-service/logs/channel_engine.log。
    
    这样 SystemLogViewer 的文件扫描就能自动发现 CE 日志，
    无需修改任何前端代码。
    """
    # 日志目录: ../api-service/logs/ (相对于 channel-engine-service/)
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "api-service", "logs"
    )
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "channel_engine.log")

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JsonFormatter())

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s │ %(levelname)-8s │ %(name)-40s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # 抑制第三方库噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


_setup_ce_logging()
logger = logging.getLogger("channel_engine.main")


# ============================================================================
# 创建FastAPI应用
# ============================================================================

app = FastAPI(
    title="Channel Engine Service",
    description="基于3GPP TR 38.901的OTA探头权重计算服务",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# ============================================================================
# CORS配置 - 允许Meta-3D前端访问
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite开发服务器
        "http://localhost:5174",  # Vite开发服务器（备用端口）
        "http://localhost:5175",  # Vite开发服务器（备用端口2）
        "http://localhost:3000",  # 备用端口
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
)

# ============================================================================
# 路由注册
# ============================================================================

# Health check
app.include_router(
    health.router,
    prefix="/api/v1",
    tags=["健康检查"]
)

# OTA endpoints
app.include_router(
    ota.router,
    prefix="/api/v1/ota",
    tags=["OTA探头权重"]
)

# Hardware Pipeline (Spec v1.0)
app.include_router(
    hardware_pipeline.router,
    prefix="/api/v1",
    tags=["硬件流水线"]
)

# ============================================================================
# 根端点
# ============================================================================

@app.get("/", tags=["根"])
async def root():
    """根端点 - 服务信息"""
    return {
        "service": "Channel Engine Service",
        "version": "1.0.0",
        "description": "OTA探头权重计算服务",
        "docs": "/api/docs",
        "health": "/api/v1/health"
    }


# ============================================================================
# 启动和关闭事件
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """服务启动时执行"""
    logger.info("=" * 60)
    logger.info("Channel Engine Service 正在启动...")
    logger.info("API文档: http://localhost:8001/api/docs")
    logger.info("健康检查: http://localhost:8001/api/v1/health")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时执行"""
    logger.info("Channel Engine Service 正在关闭...")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,  # 开发模式：自动重载
        log_level="info"
    )

