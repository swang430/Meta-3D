"""
Channel Engine Service - FastAPI Application
OTA探头权重计算服务
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import health, ota

# 创建FastAPI应用
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
    print("="*60)
    print("Channel Engine Service 正在启动...")
    print("API文档: http://localhost:8001/api/docs")
    print("健康检查: http://localhost:8001/api/v1/health")
    print("="*60)


@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时执行"""
    print("Channel Engine Service 正在关闭...")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,  # 开发模式：自动重载
        log_level="info"
    )
