"""P1-29：驾驶舱告警 summary 静态路由必须真实可达。"""

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


class _EmptyAlertQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def count(self) -> int:
        return 0


class _EmptyAlertDb:
    def query(self, *_args, **_kwargs):
        return _EmptyAlertQuery()


def test_alert_summary_static_route_is_reachable():
    """`summary` 不能先命中 `/alerts/{alert_id}` 并被当 UUID 解析。"""

    app.dependency_overrides[get_db] = lambda: _EmptyAlertDb()
    try:
        response = TestClient(app).get("/api/v1/dashboard/alerts/summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total_active": 0,
        "info_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "critical_count": 0,
    }
