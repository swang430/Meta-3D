"""
API 请求审计中间件

记录每个 HTTP 请求的方法、路径、状态码和耗时。
用于联调期间快速定位 "前端发了什么、后端怎么回的" 问题。

排除高频轮询路径（health, monitoring/metrics）以避免日志洪泛。
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.audit")

# 不记录的路径前缀（高频轮询 + 静态资源）
EXCLUDED_PATHS = (
    "/health",
    "/api/v1/health",
    "/api/v1/monitoring/metrics",
    "/api/v1/monitoring/instrument-status",
    "/favicon.ico",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    HTTP 请求审计中间件

    为每个非排除路径的请求记录一行结构化日志：
    - method, path, status, duration_ms, client_ip
    - 对于 4xx/5xx 响应，日志级别提升为 WARNING/ERROR
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 跳过高频无意义路径
        if path in EXCLUDED_PATHS or any(path.startswith(p) for p in EXCLUDED_PATHS):
            return await call_next(request)

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"
        method = request.method

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{method} {path} → 500 ({duration_ms:.0f}ms) [{client_ip}] exception: {exc}",
                extra={"method": method, "path": path, "status": 500, "duration_ms": duration_ms},
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        status = response.status_code

        log_msg = f"{method} {path} → {status} ({duration_ms:.0f}ms) [{client_ip}]"
        extra = {"method": method, "path": path, "status": status, "duration_ms": round(duration_ms, 1)}

        if status >= 500:
            logger.error(log_msg, extra=extra)
        elif status >= 400:
            logger.warning(log_msg, extra=extra)
        else:
            logger.info(log_msg, extra=extra)

        return response
