"""P2-34：正式执行失败告警的发布结果契约。

行为门（设计稿 docs/plans/2026-08-21-p2-34-failure-alert-contract-design.md §4）：
- 门A 发布成功 → outcome/alert_id/recorded_at 落 config，历史行透出 published；
- 门B 发布失败 → 执行终态不反噬 + 失败本身可观察（记录 outcome=failed + error）；
- 门B2 记录也写不进 → 不抛异常、终态不变、行保持未记录；
- 门C 历史行 / 畸形记录 → 未记录（None），绝不折叠成 published；
- 门D 生命周期去重保持，duplicate 仅补缺不覆盖 published 记录；
- 门E 跳过类各归各的 outcome，VRT 行 config 零污染。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.test_execution import _to_history_item
from app.models.alert import Alert, AlertStatus
from app.models.test_plan import TestExecution
from app.db.database import Base
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


def _execution(db, *, status="failed", source="test_case_runner", config=None):
    row = TestExecution(
        id=uuid.uuid4(),
        status=status,
        executed_by=source,
        config={"error_message": "相位配置失败"} if config is None else config,
    )
    db.add(row)
    db.commit()
    return row


def _reload(db, execution_id) -> TestExecution:
    db.expire_all()
    return db.query(TestExecution).filter(TestExecution.id == execution_id).one()


# ─────────────────────────── 门A：发布成功可观察 ───────────────────────────


@pytest.mark.parametrize("source", ["test_case_runner", "commissioning_api"])
def test_published_outcome_recorded_on_execution_row(db, source):
    execution = _execution(db, source=source)

    outcome = alerts.emit_execution_failed_alert(execution.id)
    assert outcome == alerts.OUTCOME_PUBLISHED

    alert = db.query(Alert).one()
    row = _reload(db, execution.id)
    record = (row.config or {}).get(alerts.CONFIG_RECORD_KEY)
    assert isinstance(record, dict)
    assert record["outcome"] == alerts.OUTCOME_PUBLISHED
    assert record["alert_id"] == str(alert.id)  # 指向真实告警行
    assert record.get("recorded_at")  # 何时记的可追溯

    # 真实生效端：执行历史行透出发布结果
    item = _to_history_item(row, case_name=None)
    assert item.failure_alert_outcome == alerts.OUTCOME_PUBLISHED

    # 记录不得抹掉行上既有的 config 内容（error_message 等）
    assert row.config.get("error_message") == "相位配置失败"


# ─────────────────────────── 门B：发布失败可观察且不反噬 ───────────────────────────


def _first_commit_failing_session():
    """第一个 commit（告警事务）炸，之后（记录事务）正常。"""
    session = TestingSessionLocal()
    real_commit = session.commit
    calls = {"n": 0}

    def _commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("alerts table unavailable")
        real_commit()

    session.commit = _commit
    return session


def test_publish_failure_keeps_terminal_state_and_is_observable(db, monkeypatch):
    execution = _execution(db)
    execution_id = execution.id
    monkeypatch.setattr(alerts, "SessionLocal", _first_commit_failing_session)

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_FAILED

    row = _reload(db, execution_id)
    assert row.status == "failed"  # 执行结论不反噬
    assert db.query(Alert).count() == 0

    record = (row.config or {}).get(alerts.CONFIG_RECORD_KEY)
    assert isinstance(record, dict)
    assert record["outcome"] == alerts.OUTCOME_FAILED
    assert record.get("error")  # 失败原因摘要可观察
    assert "alert_id" not in record  # 没有告警行就不许假装有

    item = _to_history_item(row, case_name=None)
    assert item.failure_alert_outcome == alerts.OUTCOME_FAILED


def test_record_write_failure_is_swallowed_and_row_stays_unrecorded(db, monkeypatch):
    """门B2：DB 全炸（告警 + 记录两个事务都失败）。"""
    execution = _execution(db)
    execution_id = execution.id

    def _always_failing_session():
        session = TestingSessionLocal()

        def _fail_commit():
            raise RuntimeError("database gone")

        session.commit = _fail_commit
        return session

    monkeypatch.setattr(alerts, "SessionLocal", _always_failing_session)

    outcome = alerts.emit_execution_failed_alert(execution_id)  # 不得抛异常
    assert outcome == alerts.OUTCOME_FAILED

    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert db.query(Alert).count() == 0
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})  # 未记录，不是错记

    item = _to_history_item(row, case_name=None)
    assert item.failure_alert_outcome is None


# ─────────────────────────── 门C：历史行 = 未记录，绝不折叠成成功 ───────────────────────────


@pytest.mark.parametrize("config", [
    None,                                              # 行连 config 都没有
    {"error_message": "老失败"},                        # P2-34 之前的历史失败行
    {"failure_alert": "published"},                    # 畸形：记录不是 dict
    {"failure_alert": {"outcome": "exploded"}},        # 畸形：outcome 越界值
    {"failure_alert": {}},                             # 畸形：没有 outcome
])
def test_history_rows_without_valid_record_resolve_to_unrecorded(db, config):
    execution = _execution(db, config=config)

    item = _to_history_item(_reload(db, execution.id), case_name=None)
    assert item.failure_alert_outcome is None  # 未记录 ≠ 发布成功

    assert alerts.resolve_recorded_outcome(config) is None


def test_resolver_passes_only_whitelisted_outcomes():
    for value in sorted(alerts.RECORDED_OUTCOMES):
        assert alerts.resolve_recorded_outcome(
            {"failure_alert": {"outcome": value}}
        ) == value
    # 跳过类 outcome 不落库，读方同样不放行
    assert alerts.resolve_recorded_outcome(
        {"failure_alert": {"outcome": "skipped_not_formal"}}
    ) is None


# ─────────────────────────── 门D：去重保持 + duplicate 仅补缺 ───────────────────────────


def test_duplicate_backfills_record_without_reopening_alert(db):
    execution = _execution(db)
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED

    alert = db.query(Alert).one()
    alert.status = AlertStatus.ACKNOWLEDGED.value
    db.commit()

    # 模拟"产线上线早于契约"的历史窗口：告警在、行上没有记录
    row = _reload(db, execution.id)
    cfg = dict(row.config or {})
    cfg.pop(alerts.CONFIG_RECORD_KEY, None)
    row.config = cfg
    db.commit()

    outcome = alerts.emit_execution_failed_alert(execution.id)
    assert outcome == alerts.OUTCOME_DUPLICATE
    assert db.query(Alert).count() == 1  # 不重开
    db.expire_all()
    assert db.query(Alert).one().status == AlertStatus.ACKNOWLEDGED.value

    record = (_reload(db, execution.id).config or {}).get(alerts.CONFIG_RECORD_KEY)
    assert isinstance(record, dict)
    assert record["outcome"] == alerts.OUTCOME_DUPLICATE  # 补记
    assert record["alert_id"] == str(alert.id)


def test_duplicate_does_not_overwrite_published_record(db):
    execution = _execution(db)
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED
    first_record = dict(
        (_reload(db, execution.id).config or {})[alerts.CONFIG_RECORD_KEY]
    )

    outcome = alerts.emit_execution_failed_alert(execution.id)  # 调用方重试
    assert outcome == alerts.OUTCOME_DUPLICATE

    record = (_reload(db, execution.id).config or {}).get(alerts.CONFIG_RECORD_KEY)
    assert record == first_record  # published 记录原样保留，不被 duplicate 覆盖


# ─────────────────────────── 门E：跳过类不落库、VRT 零污染 ───────────────────────────


def test_non_formal_source_skips_without_touching_config(db):
    execution = _execution(db, source="vrt", config={"scenario": "urban-a"})

    outcome = alerts.emit_execution_failed_alert(execution.id)
    assert outcome == alerts.OUTCOME_SKIPPED_NOT_FORMAL
    assert db.query(Alert).count() == 0

    row = _reload(db, execution.id)
    assert row.config == {"scenario": "urban-a"}  # VRT 行 config 零污染


def test_missing_and_not_failed_skip_outcomes(db):
    assert (
        alerts.emit_execution_failed_alert(uuid.uuid4())
        == alerts.OUTCOME_SKIPPED_MISSING
    )

    execution = _execution(db, status="completed")
    assert (
        alerts.emit_execution_failed_alert(execution.id)
        == alerts.OUTCOME_SKIPPED_NOT_FAILED
    )
    row = _reload(db, execution.id)
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})
