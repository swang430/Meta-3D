"""DEL-01：通过真实路由验证服务健康，外部传输和数据库完全隔离。"""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import health
from app.db.database import get_db
from app.main import app
from app.schemas.calibration import HealthResponse


@pytest.fixture
def probe(monkeypatch):
    calls = []
    state = {"database": True, "reply": httpx.Response(
        200, json={"status": "healthy", "channel_engine_available": True}
    )}

    class Database:
        def execute(self, statement):
            assert str(statement) == "SELECT 1"
            if not state["database"]:
                raise OperationalError("SELECT 1", {}, Exception("数据库不可用"))

    def transport(request):
        calls.append(request)
        reply = state["reply"]
        if isinstance(reply, Exception):
            raise reply
        return reply

    mock = httpx.MockTransport(transport)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda self, req: mock.handle_request(req))
    monkeypatch.setattr(health, "CE_BASE_URL", "http://ce.invalid:8123/", raising=False)
    app.dependency_overrides[get_db] = lambda: Database()
    # 不进入 lifespan，不初始化硬件。
    client = TestClient(app)
    yield client, state, calls
    client.close()


@pytest.mark.parametrize("database,available", [(True, True), (True, False), (False, True), (False, False)])
def test_independent_health(probe, database, available):
    client, state, calls = probe
    state["database"] = database
    state["reply"] = httpx.Response(200, json={
        "status": "healthy" if available else "degraded",
        "channel_engine_available": available,
    })
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    result = response.json()
    assert result["channel_engine_available"] is available
    assert result["database_connected"] is database
    assert result["status"] == ("healthy" if database and available else "degraded")
    assert set(result) == {"status", "version", "database_connected", "mock_instruments", "channel_engine_available"}
    assert result["mock_instruments"] is True
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert str(calls[0].url) == "http://ce.invalid:8123/api/v1/health"
    assert all(0 < value <= 2 for value in calls[0].extensions["timeout"].values())


@pytest.mark.parametrize("reply", [
    httpx.ConnectError("服务未启动"),
    httpx.ConnectTimeout("连接超时"), httpx.ReadTimeout("读取超时"),
    httpx.WriteTimeout("写入超时"), httpx.PoolTimeout("等待超时"),
    httpx.RemoteProtocolError("响应协议错误"),
    httpx.Response(503, json={"status": "healthy", "channel_engine_available": True}),
    httpx.Response(302, headers={"location": "http://other.invalid/"}),
    httpx.Response(200, text="not json"),
    *[httpx.Response(200, json=body) for body in [
        [], None, "healthy", {}, {"status": "healthy"},
        {"channel_engine_available": True},
        {"status": "degraded", "channel_engine_available": True},
        *[{"status": "healthy", "channel_engine_available": value} for value in [False, None, "true", 1]],
    ]],
])
def test_unconfirmed_service_is_unavailable(probe, reply):
    client, state, calls = probe
    state["reply"] = reply
    result = client.get("/api/v1/health").json()
    assert result["channel_engine_available"] is False
    assert result["database_connected"] is True
    assert result["status"] == "degraded"
    assert len(calls) == 1


def test_schema_does_not_assume_availability():
    result = HealthResponse(status="degraded", version="test", database_connected=True, mock_instruments=True)
    assert result.channel_engine_available is False
