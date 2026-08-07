"""P1-42: audit 汇总行必须属于执行链，且请求上下文不可串线。"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.core.audit_middleware import AuditMiddleware
from app.core.logging_config import (
    ContextFilter,
    current_execution_id,
    current_session_id,
)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def _call_asgi(app: Any, path: str, *, scope_type: str = "http") -> list[dict]:
    messages: list[dict] = []
    scope = {
        "type": scope_type,
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
        "subprotocols": [],
    }
    received = False

    async def receive() -> dict:
        nonlocal received
        if scope_type == "websocket":
            return {"type": "websocket.disconnect", "code": 1000}
        if not received:
            received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        messages.append(message)

    await app(scope, receive, send)
    return messages


@pytest.fixture
def audit_capture():
    logger = logging.getLogger("app.audit")
    capture = _Capture()
    capture.addFilter(ContextFilter())
    old_level = logger.level
    old_propagate = logger.propagate
    old_disabled = logger.disabled
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # Alembic's in-process fileConfig disables already-imported loggers.
    # Keep this fixture independent of full-suite collection/execution order.
    logger.disabled = False
    logger.addHandler(capture)
    try:
        yield capture
    finally:
        logger.removeHandler(capture)
        logger.setLevel(old_level)
        logger.propagate = old_propagate
        logger.disabled = old_disabled


@pytest.mark.asyncio
async def test_async_endpoint_execution_id_reaches_audit_summary(audit_capture):
    async def downstream(scope, receive, send):
        current_execution_id.set("exec-from-endpoint")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    await _call_asgi(AuditMiddleware(downstream), "/api/v1/test/execute")

    assert len(audit_capture.records) == 1
    assert audit_capture.records[0].execution_id == "exec-from-endpoint"


@pytest.mark.asyncio
async def test_same_task_requests_reset_execution_context(audit_capture):
    async def downstream(scope, receive, send):
        if scope["path"].endswith("execute"):
            current_execution_id.set("exec-first")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = AuditMiddleware(downstream)
    outer = current_execution_id.set("outer-context")
    try:
        await _call_asgi(middleware, "/execute")
        await _call_asgi(middleware, "/unrelated")
        assert [r.execution_id for r in audit_capture.records] == ["exec-first", "-"]
        assert current_execution_id.get() == "outer-context"
    finally:
        current_execution_id.reset(outer)


@pytest.mark.asyncio
async def test_sync_endpoint_can_return_execution_id_through_scope_state(audit_capture):
    async def downstream(scope, receive, send):
        # request.state writes into this same mutable scope mapping even when the
        # endpoint itself runs in a worker thread.
        scope["state"]["execution_id"] = "exec-from-sync-endpoint"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    await _call_asgi(AuditMiddleware(downstream), "/api/v1/test-executions/1/cancel")

    assert audit_capture.records[0].execution_id == "exec-from-sync-endpoint"


@pytest.mark.asyncio
async def test_request_boundary_closes_execution_after_audit(monkeypatch, audit_capture):
    closed: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "app.core.audit_middleware.close_execution_log",
        lambda execution_id: closed.append((execution_id, len(audit_capture.records))),
    )

    async def downstream(scope, receive, send):
        current_execution_id.set("exec-request-bound")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    await _call_asgi(AuditMiddleware(downstream), "/api/v1/test/execute")

    assert closed == [("exec-request-bound", 1)]


@pytest.mark.asyncio
async def test_websocket_downstream_receives_request_id():
    observed: list[str] = []

    async def downstream(scope, receive, send):
        observed.append(current_session_id.get())
        await send({"type": "websocket.close", "code": 1000})

    await _call_asgi(AuditMiddleware(downstream), "/api/v1/ws/monitoring", scope_type="websocket")

    assert len(observed[0]) == 16
    assert observed[0] != "-"


@pytest.mark.asyncio
async def test_websocket_disconnect_closes_bound_execution(monkeypatch):
    closed: list[str] = []
    monkeypatch.setattr(
        "app.core.audit_middleware.close_execution_log",
        closed.append,
    )

    async def downstream(scope, receive, send):
        current_execution_id.set("exec-vrt-websocket")
        await send({"type": "websocket.close", "code": 1000})

    await _call_asgi(
        AuditMiddleware(downstream),
        "/api/v1/road-test/executions/exec-vrt-websocket/ws",
        scope_type="websocket",
    )

    assert closed == ["exec-vrt-websocket"]
