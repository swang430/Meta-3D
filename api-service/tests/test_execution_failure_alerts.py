"""P3-19：正式执行终态失败进入一次性活动告警。"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.alert import create_alert, get_alert_summary
from app.db.database import Base
from app.models.alert import Alert, AlertStatus
from app.models.test_plan import TestExecution
from app.schemas.alert import AlertCreate
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


def test_duplicate_failure_refreshes_message_without_reopening_alert(db):
    execution = _execution(db)
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED

    alert = db.query(Alert).one()
    alert.status = AlertStatus.ACKNOWLEDGED.value
    db.commit()

    execution.error_message = (
        "仪表 Local 交接失败；此前业务失败：相位配置失败"
    )
    db.commit()

    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_DUPLICATE
    db.expire_all()
    refreshed = db.query(Alert).one()
    assert refreshed.status == AlertStatus.ACKNOWLEDGED.value
    assert "Local 交接失败" in refreshed.message
    assert "相位配置失败" in refreshed.message


def test_new_local_handoff_failure_reactivates_existing_alert(db):
    execution = _execution(db)
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED

    alert = db.query(Alert).one()
    alert.status = AlertStatus.RESOLVED.value
    alert.is_read = True
    db.commit()

    execution.config = {
        **execution.config,
        "local_control_handoff_failed": True,
        "error_message": (
            "仪表 Local 交接失败；此前业务失败：相位配置失败"
        ),
    }
    execution.error_message = execution.config["error_message"]
    db.commit()

    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_DUPLICATE
    db.expire_all()
    refreshed = db.query(Alert).one()
    assert refreshed.status == AlertStatus.ACTIVE.value
    assert refreshed.is_read is False
    assert "Local 交接失败" in refreshed.message

    # 交接失败已经进入同一告警正文后，操作员再次确认不得被普通重试重开。
    refreshed.status = AlertStatus.ACKNOWLEDGED.value
    db.commit()
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_DUPLICATE
    db.expire_all()
    assert db.query(Alert).one().status == AlertStatus.ACKNOWLEDGED.value


def test_local_handoff_reactivation_serializes_existing_alert(db, monkeypatch):
    execution = _execution(db)
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED

    alert = db.query(Alert).one()
    alert.status = AlertStatus.RESOLVED.value
    alert.is_read = True
    execution.config = {
        **execution.config,
        "local_control_handoff_failed": True,
    }
    db.commit()

    locked_entities = []
    original_with_for_update = Query.with_for_update

    def _record_lock(query, *args, **kwargs):
        locked_entities.append(query.column_descriptions[0]["entity"])
        return original_with_for_update(query, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", _record_lock)

    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_DUPLICATE
    # 先锁必然存在的 execution，覆盖查无→首建；再锁既有 alert，
    # 与操作员的 acknowledge/resolve/dismiss 更新排序。
    assert locked_entities == [TestExecution, Alert, TestExecution]


def test_first_failure_alert_creation_serializes_on_execution(db, monkeypatch):
    execution = _execution(db)
    locked_entities = []
    original_with_for_update = Query.with_for_update

    def _record_lock(query, *args, **kwargs):
        locked_entities.append(query.column_descriptions[0]["entity"])
        return original_with_for_update(query, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", _record_lock)

    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED
    assert db.query(Alert).count() == 1
    assert locked_entities == [TestExecution, TestExecution]


def test_public_alert_api_rejects_reserved_execution_failure_type():
    class _NoWriteDb:
        def add(self, _alert):
            raise AssertionError("保留的系统告警不得进入通用写路径")

    request = AlertCreate(
        message="伪造执行失败告警",
        type="execution_failed",
        source="external_client",
        related_entity_type="test_execution",
        related_entity_id=uuid.uuid4(),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_alert(request, db=_NoWriteDb())

    assert exc_info.value.status_code == 422


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
