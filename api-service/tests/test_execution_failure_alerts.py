"""P3-19：正式执行终态失败进入一次性活动告警。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.alert import get_alert_summary
from app.db.database import Base
from app.models.alert import Alert, AlertStatus
from app.models.test_plan import TestExecution
from app.services import execution_failure_alerts as alerts

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _db_schema(monkeypatch):
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(alerts, "SessionLocal", TestingSessionLocal)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _execution(db, *, status="failed", source="test_case_runner", validation_pass=None):
    row = TestExecution(
        id=uuid.uuid4(),
        status=status,
        executed_by=source,
        validation_pass=validation_pass,
        config={"error_message": "相位配置失败"},
    )
    db.add(row)
    db.commit()
    return row


def test_formal_failure_is_counted_once_across_alert_lifecycle(db):
    execution = _execution(db)

    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED
    summary = get_alert_summary(db)
    assert summary.total_active == 1
    assert summary.error_count == 1

    alert = db.query(Alert).one()
    alert.status = AlertStatus.ACKNOWLEDGED.value
    db.commit()

    # P2-34: 返回值从混叠 bool 改为 outcome 枚举 — 去重命中是 duplicate
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_DUPLICATE
    assert db.query(Alert).count() == 1
    assert get_alert_summary(db).total_active == 0


@pytest.mark.parametrize("status,source,validation_pass,expected", [
    ("completed", "test_case_runner", False, "skipped_not_failed"),
    ("failed", "commissioning_adhoc", None, "skipped_not_formal"),
    ("failed", "test_plan_runner", None, "skipped_not_formal"),
    ("failed", "vrt", None, "skipped_not_formal"),
])
def test_non_system_failure_sources_do_not_create_alerts(
    db, status, source, validation_pass, expected,
):
    execution = _execution(
        db,
        status=status,
        source=source,
        validation_pass=validation_pass,
    )

    assert alerts.emit_execution_failed_alert(execution.id) == expected
    assert db.query(Alert).count() == 0


def test_alert_commit_failure_does_not_rollback_execution_terminal_state(
    db, monkeypatch,
):
    execution = _execution(db)
    execution_id = execution.id

    def _failing_session():
        session = TestingSessionLocal()

        def _fail_commit():
            raise RuntimeError("alerts table unavailable")

        session.commit = _fail_commit
        return session

    monkeypatch.setattr(alerts, "SessionLocal", _failing_session)

    assert alerts.emit_execution_failed_alert(execution_id) == alerts.OUTCOME_FAILED
    db.expire_all()
    assert db.query(TestExecution).get(execution_id).status == "failed"
    assert db.query(Alert).count() == 0
