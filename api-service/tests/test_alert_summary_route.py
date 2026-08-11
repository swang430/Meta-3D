"""P1-29：驾驶舱告警 summary 静态路由必须真实可达。"""

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app


class _EmptyAlertQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return []

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


class _ChangingAlertQuery:
    """同时支持旧版连续 count 与新版单次 group-by 的并发夹具。"""

    def __init__(self):
        self._counts = iter([0, 0, 0, 0, 1])

    def filter(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def count(self) -> int:
        # 旧实现跨五条 SELECT：第一条看到空表，最后一条看到 critical 新行。
        return next(self._counts)

    def all(self):
        # 新实现只消费同一条聚合查询的一个结果集。
        return [("critical", 1)]


class _ChangingAlertDb:
    def __init__(self):
        self.query_result = _ChangingAlertQuery()

    def query(self, *_args, **_kwargs):
        return self.query_result


def test_alert_summary_counts_come_from_one_consistent_aggregate():
    """并发插入不能产生 total=0、critical=1 的假安全摘要。"""

    app.dependency_overrides[get_db] = lambda: _ChangingAlertDb()
    try:
        response = TestClient(app).get("/api/v1/dashboard/alerts/summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total_active": 1,
        "info_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "critical_count": 1,
    }
