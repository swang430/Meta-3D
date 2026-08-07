"""
API 请求审计中间件

记录每个 HTTP 请求的方法、路径、状态码和耗时。
用于联调期间快速定位 "前端发了什么、后端怎么回的" 问题。

排除高频轮询路径（health, monitoring/metrics）以避免日志洪泛。
"""

import time
import logging
import uuid
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import current_execution_id, current_session_id

logger = logging.getLogger("app.audit")

# 每请求关联 id 的 hex 长度。16 = 64 bit，见 dispatch 里的碰撞算账。
REQUEST_ID_HEX_LEN = 16

# 不记录的路径前缀（高频轮询 + 静态资源）
#
# P1-34 新增末两条 —— 日志面板**自指的**轮询。面板按 5/10/30 秒轮询
# `/system-logs/tail`，而这次轮询本身又被审计成一行写进它正在读的那份
# app.log；`/system-logs/frontend` 是 GUI 回传前端日志，同理。实测：最近
# 400 行里 107 行是 app.audit，其中 `system-logs/*` 占大头 —— 操作员想找
# 自己刚做的那次操作，先得从"日志面板问了日志"里刨出来。
#
# ⚠ 只排除审计那**一行**，不影响这些请求的下游日志（见 dispatch：
# request id 在排除判断**之前**就设好了）。下载 / 导出属真实操作，不排除。
EXCLUDED_PATHS = (
    "/health",
    "/api/v1/health",
    "/api/v1/monitoring/metrics",
    "/api/v1/monitoring/instrument-status",
    "/favicon.ico",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/api/v1/system-logs/tail",
    "/api/v1/system-logs/frontend",
)


class AuditMiddleware:
    """
    HTTP 请求审计中间件

    为每个请求记录一行结构化日志：
    - method, path, status, duration_ms, client_ip
    - 对于 4xx/5xx 响应，日志级别提升为 WARNING/ERROR

    ⚠ `EXCLUDED_PATHS` 排掉的是**成功那一行**，不是整个请求的痕迹：
    这些路径上的 4xx/5xx 与未捕获异常照记不误（见 dispatch 里的收窄理由）。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        # ── P1-34: 把一次操作串成一条链 ──────────────────────────────
        # 每个请求生成一个 id 写进 contextvar。`ContextFilter` 已经在给
        # **每条** LogRecord 注入 `session_id`（`logging_config.py`），所以
        # 这一次赋值就让该请求下游的全部日志（audit / test_case_runner /
        # HAL / SCPI）自动带上同一个值 —— **零调用点改动**。
        #
        # 修之前实测：`current_session_id` 这个 ContextVar 定义好了但**全仓
        # 没有任何一处 `.set()`**，24372 行日志的 `session_id` 100% 是 "-"，
        # 字段纯装饰。同一次操作产生的多条日志无法聚在一起。
        #
        # ⚠ 放在排除判断**之前**：被排除的只是"审计那一行"，这些请求的下游
        # 日志照样需要能串起来。
        #
        # ⚠ 语义注记：这是**每请求**的关联 id，不是"用户会话"。复用既有的
        # `session_id` 键是为了不动 wire format / GUI / 契约（换源，不加机制）。
        # 将来真出现跨请求的会话概念时，它需要**自己的**字段，别覆盖这个。
        #
        # 纯 ASGI 中间件同时覆盖 HTTP 与 WebSocket；后者只建立 request_id 上下文，
        # 不伪造 HTTP 汇总行。
        # ⚠ 别缩短这个前缀（Codex #282 R1 P2）。8 位 hex = 32 bit，生日碰撞
        # 在一天的日志量级上是**必然**不是理论：GUI 光轮询就约 1 万请求/小时，
        # 十万条时碰撞概率 69%、五十万条 ~100%。而「只看这一次请求」是精确
        # 匹配 —— 一旦碰撞就把两条**不相干**的链合并显示，正是本片在治的那个
        # 母题（看起来对、其实是错的）。16 位 = 64 bit，五十万条时 6.8e-9。
        #
        # 尤其别拿"扫描窗口只有 20000 行"当理由：`/system-logs/export` 是
        # **全文件**流式过滤，根本不受那个上限约束。
        session_token = current_session_id.set(uuid.uuid4().hex[:REQUEST_ID_HEX_LEN])
        execution_token = current_execution_id.set("-")

        if scope["type"] == "websocket":
            try:
                await self.app(scope, receive, send)
            finally:
                current_execution_id.reset(execution_token)
                current_session_id.reset(session_token)
            return

        path = scope.get("path", "")
        # 高频轮询路径：**只在它成功时**不记审计行。
        #
        # 内审 F1 的收窄 —— 早前这里是 `return await call_next(request)` 直接早退，
        # 于是这些路径上的 4xx/5xx 也一并没了痕迹。对 `/system-logs/frontend`
        # 尤其致命：前端日志上报 422 时，`frontendLogger` 自己 catch 后静默丢批、
        # `api/client.ts` 又显式跳过该 URL 防回环 —— 审计这一行是**最后一处**痕迹，
        # 排掉它等于整条前端日志通道死了没人知道。
        #
        # 代价不对称，方向就明确：少记一条 200 = 零代价；少记一条 422 = 通道
        # 静默死亡。所以排除只对**成功**生效。
        excluded = path in EXCLUDED_PATHS or any(
            path.startswith(p) for p in EXCLUDED_PATHS
        )

        start_time = time.perf_counter()
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        method = scope.get("method", "UNKNOWN")
        status = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_status)
            except Exception as exc:
                # 未捕获异常永远记 —— 不管路径在不在排除名单里。
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"{method} {path} → 500 ({duration_ms:.0f}ms) [{client_ip}] exception: {exc}",
                    extra={"method": method, "path": path, "status": 500, "duration_ms": duration_ms},
                )
                raise

            # 同步端点在线程池里运行，ContextVar 的写入不会回传；允许那一个边界
            # 通过 request.state 把已经解析出的执行 ID 交回审计层。
            state = scope.get("state") or {}
            state_execution_id = state.get("execution_id") if isinstance(state, dict) else None
            if state_execution_id and current_execution_id.get("-") == "-":
                current_execution_id.set(str(state_execution_id))

            duration_ms = (time.perf_counter() - start_time) * 1000
            if excluded and status < 400:
                return

            log_msg = f"{method} {path} → {status} ({duration_ms:.0f}ms) [{client_ip}]"
            extra = {
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": round(duration_ms, 1),
            }

            if status >= 500:
                logger.error(log_msg, extra=extra)
            elif status >= 400:
                logger.warning(log_msg, extra=extra)
            else:
                logger.info(log_msg, extra=extra)
        finally:
            current_execution_id.reset(execution_token)
            current_session_id.reset(session_token)
