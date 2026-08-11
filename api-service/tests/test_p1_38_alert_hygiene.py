"""P1-38：历史 ``test_suite`` 告警只允许按精确白名单清理。"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.alert import Alert


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_test_suite_alerts.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ZONE = _REPO_ROOT / "gui/src/features/Dashboard/ZoneLogsAlerts.tsx"


def _cleanup_module():
    assert _SCRIPT.is_file(), "P1-38 清理脚本尚未实现"
    spec = importlib.util.spec_from_file_location("cleanup_test_suite_alerts", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def sqlite_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    previous = app.dependency_overrides.get(get_db)

    def _override_get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield engine, factory
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _row(**overrides) -> Alert:
    fields = {
        "title": "WARNING: Alert",
        "message": "Test alert",
        "severity": "warning",
        "alert_type": "warning",
        "status": "active",
        "source": "test_suite",
        "created_by": "test_suite",
        "created_at": datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
    }
    fields.update(overrides)
    return Alert(**fields)


def _seed(factory):
    rows = {
        "warning_exact": _row(),
        "info_exact": _row(
            title="INFO: Alert",
            message="Alert to dismiss",
            severity="info",
            alert_type="info",
            status="dismissed",
        ),
        # 身份近似：只有 source 不同，不能因 created_by 命中就删除。
        "source_near_miss": _row(source="operator_console"),
        # 身份近似的另一端：source 命中但 created_by 不同也必须保留。
        "created_by_near_miss": _row(created_by="operator_console"),
        # cutoff 是严格小于；边界时刻及其后的任何数据都不可达。
        "cutoff_near_miss": _row(created_at=datetime(2026, 8, 2, tzinfo=timezone.utc)),
        # 内容近似：只差一个字符也不属于已知历史产物。
        "content_near_miss": _row(message="Test alert!"),
    }
    with factory() as db:
        db.add_all(rows.values())
        db.commit()
    return {name: row.id for name, row in rows.items()}


def _ids(factory):
    with factory() as db:
        return set(db.scalars(select(Alert.id)).all())


def test_cleanup_defaults_to_dry_run_and_does_not_mutate(sqlite_db):
    _engine, factory = sqlite_db
    ids = _seed(factory)
    module = _cleanup_module()

    with factory() as db:
        result = module.cleanup_test_suite_alerts(db)

    assert result.execute is False
    assert result.matched == 2
    assert result.deleted == 0
    assert set(result.candidate_ids) == {ids["warning_exact"], ids["info_exact"]}
    assert _ids(factory) == set(ids.values())


def test_execute_deletes_only_exact_historical_candidates(sqlite_db):
    _engine, factory = sqlite_db
    ids = _seed(factory)
    module = _cleanup_module()

    with factory() as db:
        result = module.cleanup_test_suite_alerts(db, execute=True)

    assert result.execute is True
    assert result.matched == 2
    assert result.deleted == 2
    assert _ids(factory) == {
        ids["source_near_miss"],
        ids["created_by_near_miss"],
        ids["cutoff_near_miss"],
        ids["content_near_miss"],
    }


def test_execute_rolls_back_when_commit_fails(sqlite_db):
    engine, factory = sqlite_db
    ids = _seed(factory)
    module = _cleanup_module()

    class FailingCommitSession(Session):
        rollback_called = False

        def commit(self):
            raise RuntimeError("injected commit failure")

        def rollback(self):
            self.rollback_called = True
            super().rollback()

    db = FailingCommitSession(bind=engine)
    try:
        with pytest.raises(RuntimeError, match="injected commit failure"):
            module.cleanup_test_suite_alerts(db, execute=True)
        assert db.rollback_called is True
    finally:
        db.close()

    assert _ids(factory) == set(ids.values())


def test_cli_requires_explicit_execute_flag():
    module = _cleanup_module()

    assert module.build_parser().parse_args([]).execute is False
    assert module.build_parser().parse_args(["--execute"]).execute is True


def test_dashboard_uses_alert_summary_badge_without_alert_detail_panel():
    """P1-38：告警只占实时日志标题栏，不再拉取或展示详情列表。"""
    source = _ZONE.read_text(encoding="utf-8")

    assert "fetchAlerts" not in source
    assert "function AlertPanel" not in source
    assert "DashboardAlert" not in source
    assert "SEVERITY_RANK" not in source

    assert "queryFn: fetchAlertSummary" in source
    assert "refetchInterval: 10_000" in source
    assert "summaryQuery.isLoading" in source
    assert "summaryQuery.error" in source
    assert "告警计数不可用" in source
    assert "告警计数不一致" in source
    assert "knownTotal !== summary.total_active" in source
    assert "无活动告警" in source
    assert "活动告警 {summary.total_active}" in source
    assert "严重 {summary.critical_count}" in source
    assert "错误 {summary.error_count}" in source
    assert "警告 {summary.warning_count}" in source
    assert "信息 {summary.info_count}" in source

    assert "Grid.Col" not in source
    assert "lg: 7" not in source
    assert "lg: 5" not in source
    assert "return <LogPanel />" in source
