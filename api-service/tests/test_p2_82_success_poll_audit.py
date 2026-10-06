"""P2-82：只省略精确 GET 轮询的成功审计行，不省略失败和下游证据。"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.core.audit_middleware import AuditMiddleware
from app.core.logging_config import ContextFilter, current_session_id


POLL_PATHS = (
    "/api/v1/test-executions",
    "/api/v1/instruments/hal/readiness",
    "/api/v1/dashboard/alerts/summary",
)


@pytest.fixture
def poll_app():
    app = FastAPI()
    app.add_middleware(AuditMiddleware)
    downstream = logging.getLogger("app.hal.scpi")
    audit = logging.getLogger("app.audit")
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    capture = Capture()
    capture.addFilter(ContextFilter())
    previous = {lg: (lg.level, lg.disabled, lg.propagate) for lg in (audit, downstream)}
    for lg in previous:
        lg.addHandler(capture)
        lg.setLevel(logging.INFO)
        lg.disabled = False  # 不受同进程 Alembic fileConfig 顺序影响。
        lg.propagate = False

    async def endpoint(status: int = 200, fail: bool = False):
        downstream.info("下游证据保持可见")
        if fail:
            raise RuntimeError("轮询处理失败")
        return Response(status_code=status)

    # 外部 HTTP 内容是受控输入；被测的是生产 AuditMiddleware，不连接 DB/HAL。
    app.add_api_route(
        "/{path:path}", endpoint,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, records
    finally:
        for lg, (level, disabled, propagate) in previous.items():
            lg.removeHandler(capture)
            lg.level, lg.disabled, lg.propagate = level, disabled, propagate


def audits(records):
    return [record for record in records if record.name == "app.audit"]


@pytest.mark.parametrize("path", POLL_PATHS)
@pytest.mark.parametrize("status", [200, 204, 299])
def test_exact_get_2xx_omits_only_summary(poll_app, path, status):
    """删掉白名单任一项或把它拼错 → 对应成功 GET 重新写出审计，测试变红。"""
    client, records = poll_app
    outer_id = current_session_id.get()
    response = client.get(path, params={"status": status, "limit": 5})
    assert response.status_code == status
    assert audits(records) == []
    assert len(records) == 1
    assert records[0].name == "app.hal.scpi"
    assert records[0].getMessage() == "下游证据保持可见"
    assert records[0].session_id not in ("-", outer_id)
    assert len(records[0].session_id) == 16
    assert current_session_id.get() == outer_id


@pytest.mark.parametrize("path", POLL_PATHS)
@pytest.mark.parametrize("status", [307, 400, 422, 500])
def test_poll_redirect_and_failure_still_audited(poll_app, path, status):
    """把 2xx 收窄条件去掉/放宽 → 重定向或失败的汇总行消失，测试变红。"""
    client, records = poll_app
    assert client.get(path, params={"status": status}, follow_redirects=False).status_code == status
    rows = audits(records)
    assert len(rows) == 1
    assert (rows[0].method, rows[0].path, rows[0].status) == ("GET", path, status)
    assert rows[0].levelno == (logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO)
    assert rows[0].session_id == records[0].session_id


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_same_path_non_get_success_still_audited(poll_app, method):
    """去掉 GET 条件 → 同路径的写入/其他方法成功时也静音，测试变红。"""
    client, records = poll_app
    path = "/api/v1/test-executions"
    assert client.request(method, path).status_code == 200
    rows = audits(records)
    assert len(rows) == 1
    assert (rows[0].method, rows[0].path, rows[0].status) == (method, path, 200)


@pytest.mark.parametrize("path", [
    "/api/v1/test-executions/exec-1",
    "/api/v1/test-executions/export",
    "/api/v1/instruments/hal/readiness/detail",
    "/api/v1/dashboard/alerts/summary/export",
    "/api/v1/system-logs/download/app.log",
    "/api/v1/system-logs/export/app.log",
    "/api/v1/instruments/hal/reload",
])
def test_neighbour_and_operator_paths_remain_audited(poll_app, path):
    """改成 startswith → 相邻读取/导出路径被吞，测试变红。"""
    client, records = poll_app
    assert client.get(path).status_code == 200
    rows = audits(records)
    assert len(rows) == 1
    assert (rows[0].method, rows[0].path, rows[0].status) == ("GET", path, 200)


@pytest.mark.parametrize("path", POLL_PATHS)
def test_uncaught_poll_exception_remains_error(poll_app, path):
    client, records = poll_app
    assert client.get(path, params={"fail": "true"}).status_code == 500
    rows = audits(records)
    assert len(rows) == 1
    assert rows[0].levelno == logging.ERROR
    assert rows[0].status == 500
    assert "轮询处理失败" in rows[0].getMessage()
    assert rows[0].session_id == records[0].session_id


def test_poll_whitelist_paths_are_live_read_only_routes():
    # 取真实注册 API，而不是把试验 app 的 catch-all 当作存在性证明。
    from app.main import app

    paths = app.openapi()["paths"]
    for path in POLL_PATHS:
        assert "get" in paths[path]
