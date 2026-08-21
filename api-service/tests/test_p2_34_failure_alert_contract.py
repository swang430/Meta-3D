"""P2-34：正式执行失败告警的发布结果契约。

行为门（设计稿 docs/plans/2026-08-21-p2-34-failure-alert-contract-design.md §4）：
- 门A 发布成功 → outcome/alert_id/recorded_at 落 config，历史行透出 published；
- 门B 发布失败 → 执行终态不反噬 + 失败本身可观察（记录 outcome=failed + error）；
- 门B2 记录也写不进 → 不抛异常、终态不变、行保持未记录；
- 门C 历史行 / 畸形记录 → 未记录（None），绝不折叠成 published；
- 门D 生命周期去重保持；duplicate 保留 published/duplicate，推进 failed/畸形记录；
- 门E 跳过类各归各的 outcome，VRT 行 config 零污染。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event
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


def _first_commit_failing_factory():
    """跨新旧会话仅第一个 commit（告警事务）炸，之后恢复。"""
    calls = {"n": 0}

    def _factory():
        session = TestingSessionLocal()
        real_commit = session.commit

        def _commit():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("alerts table unavailable")
            real_commit()

        session.commit = _commit
        return session

    return _factory


def test_commit_exception_without_visible_alert_keeps_history_unrecorded(
    db, monkeypatch
):
    execution = _execution(db)
    execution_id = execution.id
    monkeypatch.setattr(alerts, "SessionLocal", _first_commit_failing_factory())

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_FAILED

    row = _reload(db, execution_id)
    assert row.status == "failed"  # 执行结论不反噬
    assert db.query(Alert).count() == 0
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})
    item = _to_history_item(row, case_name=None)
    assert item.failure_alert_outcome is None


def test_alert_commit_and_rollback_failure_never_commits_pending_alert_with_failed(
    db, monkeypatch
):
    """fresh 内审 P1：rollback 未清掉 pending Alert 时不得复用 session 记 failed。"""
    execution = _execution(db)
    execution_id = execution.id

    def _first_commit_and_rollback_failing_session():
        session = TestingSessionLocal()
        real_commit = session.commit
        real_rollback = session.rollback
        commit_calls = {"n": 0}
        rollback_calls = {"n": 0}

        def _commit():
            commit_calls["n"] += 1
            if commit_calls["n"] == 1:
                raise RuntimeError("alert commit transport lost before send")
            real_commit()

        def _rollback():
            rollback_calls["n"] += 1
            if rollback_calls["n"] == 1:
                raise RuntimeError("rollback transport lost")
            real_rollback()

        session.commit = _commit
        session.rollback = _rollback
        return session

    monkeypatch.setattr(
        alerts, "SessionLocal", _first_commit_and_rollback_failing_session
    )

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_FAILED
    assert db.query(Alert).count() == 0
    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})


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


def _second_commit_failing_session():
    """第一个 commit（告警事务）正常，第二个 commit（记录事务）炸。"""
    session = TestingSessionLocal()
    real_commit = session.commit
    calls = {"n": 0}

    def _commit():
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("config column locked")
        real_commit()

    session.commit = _commit
    return session


def test_record_failure_does_not_reverse_published_alert(db, monkeypatch):
    """门B3（内审 F2）：告警已发出、记录事务才失败 → 返回仍是 published，告警行在，
    行上"未记录"（不是 failed）。

    变异：`_record_publish_outcome` 的 except 改成 re-raise → 外层 except 接住后返回
    failed（告警明明已发出）→ 本门红。门B2 抓不到它：那里两个 commit 都炸，re-raise
    后返回的恰好也是 failed。
    """
    execution = _execution(db)
    execution_id = execution.id
    monkeypatch.setattr(alerts, "SessionLocal", _second_commit_failing_session)

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_PUBLISHED, "记录失败不得反噬已发出的告警结果"

    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert db.query(Alert).count() == 1  # 告警确实发出去了
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})  # 未记录，不是错记成 failed

    item = _to_history_item(row, case_name=None)
    assert item.failure_alert_outcome is None


def test_record_rollback_failure_does_not_reclassify_published_alert(
    db, monkeypatch
):
    """fresh 内审 P1：记录 commit+rollback 都炸，也不能落回外层错记 failed。"""
    execution = _execution(db)
    execution_id = execution.id

    def _record_commit_and_first_rollback_failing_session():
        session = TestingSessionLocal()
        real_commit = session.commit
        real_rollback = session.rollback
        commit_calls = {"n": 0}
        rollback_calls = {"n": 0}

        def _commit():
            commit_calls["n"] += 1
            if commit_calls["n"] == 2:
                raise RuntimeError("config column locked")
            real_commit()

        def _rollback():
            rollback_calls["n"] += 1
            if rollback_calls["n"] == 1:
                raise RuntimeError("rollback transport lost")
            real_rollback()

        session.commit = _commit
        session.rollback = _rollback
        return session

    monkeypatch.setattr(
        alerts,
        "SessionLocal",
        _record_commit_and_first_rollback_failing_session,
    )

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_PUBLISHED
    assert db.query(Alert).count() == 1
    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})


def test_post_commit_refresh_failure_cannot_reclassify_published_alert(
    db, monkeypatch
):
    """fresh 内审 P1：Alert commit 后断线，已发布事实不能被 ORM refresh 推翻。"""
    execution = _execution(db)
    execution_id = execution.id

    def _post_commit_reads_failing_session():
        session = TestingSessionLocal()
        real_commit = session.commit
        alert_committed = {"value": False}

        def _commit():
            real_commit()
            alert_committed["value"] = True

        def _forbid_post_commit_orm_read(_execute_state):
            if alert_committed["value"]:
                raise RuntimeError("post-commit connection lost")

        session.commit = _commit
        event.listen(session, "do_orm_execute", _forbid_post_commit_orm_read)
        return session

    monkeypatch.setattr(alerts, "SessionLocal", _post_commit_reads_failing_session)

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_PUBLISHED
    assert db.query(Alert).count() == 1
    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})


def test_commit_ack_loss_reconnects_and_records_existing_alert_as_published(
    db, monkeypatch
):
    """R2 P1：COMMIT 已落库但确认包丢失时，必须按冻结 alert_id 查证真值。

    若直接把 ``commit()`` 抛错当发布失败，历史会永久写成 failed，而告警行实际
    已存在。查证必须使用新会话，不能信任提交结果未知的旧连接。
    """
    execution = _execution(db)
    execution_id = execution.id
    factory_calls = {"n": 0}

    def _commit_ack_lost_then_fresh_sessions():
        factory_calls["n"] += 1
        session = TestingSessionLocal()
        if factory_calls["n"] == 1:
            real_commit = session.commit
            commit_calls = {"n": 0}

            def _commit_then_drop_ack():
                commit_calls["n"] += 1
                real_commit()
                if commit_calls["n"] == 1:
                    raise RuntimeError("commit acknowledgement lost")

            session.commit = _commit_then_drop_ack
        return session

    monkeypatch.setattr(alerts, "SessionLocal", _commit_ack_lost_then_fresh_sessions)

    outcome = alerts.emit_execution_failed_alert(execution_id)

    assert factory_calls["n"] >= 2, "提交结果未知时必须用新连接查证"
    assert outcome == alerts.OUTCOME_PUBLISHED
    alert = db.query(Alert).one()
    row = _reload(db, execution_id)
    record = (row.config or {}).get(alerts.CONFIG_RECORD_KEY)
    assert record["outcome"] == alerts.OUTCOME_PUBLISHED
    assert record["alert_id"] == str(alert.id)


def test_commit_ack_loss_with_unavailable_verifier_keeps_history_unrecorded(
    db, monkeypatch
):
    """查证连接也不可用时宁可未记录，不得把结果未知猜成 failed。"""
    execution = _execution(db)
    execution_id = execution.id
    factory_calls = {"n": 0}

    def _ambiguous_commit_then_unavailable_verifier():
        factory_calls["n"] += 1
        session = TestingSessionLocal()
        if factory_calls["n"] == 1:
            real_commit = session.commit

            def _commit_then_drop_ack():
                real_commit()
                raise RuntimeError("commit acknowledgement lost")

            session.commit = _commit_then_drop_ack
        else:
            def _query_unavailable(*_args, **_kwargs):
                raise RuntimeError("verification connection unavailable")

            session.query = _query_unavailable
        return session

    monkeypatch.setattr(
        alerts,
        "SessionLocal",
        _ambiguous_commit_then_unavailable_verifier,
    )

    outcome = alerts.emit_execution_failed_alert(execution_id)

    assert outcome == alerts.OUTCOME_FAILED
    assert db.query(Alert).count() == 1
    row = _reload(db, execution_id)
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})


def test_outer_guard_returns_failed_without_raising(db, monkeypatch):
    """门B4：告警链在查询阶段就炸（外层 except 路径）→ 不抛、返回 failed、会话关闭。

    变异：外层 except 返回 published → 本门红。
    """
    execution = _execution(db)
    execution_id = execution.id
    closed = {"n": 0}

    def _query_exploding_session():
        session = TestingSessionLocal()

        def _query(*_args, **_kwargs):
            raise RuntimeError("connection reset")

        real_close = session.close

        def _close():
            closed["n"] += 1
            real_close()

        session.query = _query
        session.close = _close
        return session

    monkeypatch.setattr(alerts, "SessionLocal", _query_exploding_session)

    outcome = alerts.emit_execution_failed_alert(execution_id)  # 不得抛异常
    assert outcome == alerts.OUTCOME_FAILED
    assert closed["n"] == 1

    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert db.query(Alert).count() == 0
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})


def test_outer_alert_lookup_failure_is_recorded_when_execution_store_is_writable(
    db, monkeypatch
):
    """门B5（Codex R1 P1）：告警查询炸、执行行仍可写 → failed 必须落库。

    生产调用方不会消费返回值；如果外层 except 只返回 failed，历史接口就会把本次
    发布尝试永久显示为“未记录”。这里让 Alert 查询单独失败，同时保留
    TestExecution 查询与 config 事务可写，覆盖真实的部分表故障形态。
    """
    execution = _execution(db)
    execution_id = execution.id

    def _alert_lookup_failing_session():
        session = TestingSessionLocal()
        real_query = session.query

        def _query(*entities, **kwargs):
            if entities and entities[0] is Alert.id:
                raise RuntimeError("alerts table unavailable")
            return real_query(*entities, **kwargs)

        session.query = _query
        return session

    monkeypatch.setattr(alerts, "SessionLocal", _alert_lookup_failing_session)

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_FAILED

    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert db.query(Alert).count() == 0
    record = (row.config or {}).get(alerts.CONFIG_RECORD_KEY)
    assert isinstance(record, dict)
    assert record["outcome"] == alerts.OUTCOME_FAILED
    assert "alerts table unavailable" in record["error"]
    assert "alert_id" not in record


def test_outer_rollback_failure_is_swallowed_without_reusing_dirty_session(
    db, monkeypatch
):
    execution = _execution(db)
    execution_id = execution.id

    def _lookup_and_first_rollback_failing_session():
        session = TestingSessionLocal()
        real_query = session.query
        real_rollback = session.rollback
        rollback_calls = {"n": 0}

        def _query(*entities, **kwargs):
            if entities and entities[0] is Alert.id:
                raise RuntimeError("alerts table unavailable")
            return real_query(*entities, **kwargs)

        def _rollback():
            rollback_calls["n"] += 1
            if rollback_calls["n"] == 1:
                raise RuntimeError("rollback transport lost")
            real_rollback()

        session.query = _query
        session.rollback = _rollback
        return session

    monkeypatch.setattr(
        alerts, "SessionLocal", _lookup_and_first_rollback_failing_session
    )

    outcome = alerts.emit_execution_failed_alert(execution_id)
    assert outcome == alerts.OUTCOME_FAILED
    row = _reload(db, execution_id)
    assert row.status == "failed"
    assert alerts.CONFIG_RECORD_KEY not in (row.config or {})


def test_session_close_failure_never_overrides_published_outcome(db, monkeypatch):
    execution = _execution(db)

    def _close_failing_session():
        session = TestingSessionLocal()

        def _close():
            raise RuntimeError("close transport lost")

        session.close = _close
        return session

    monkeypatch.setattr(alerts, "SessionLocal", _close_failing_session)

    outcome = alerts.emit_execution_failed_alert(execution.id)
    assert outcome == alerts.OUTCOME_PUBLISHED
    assert db.query(Alert).count() == 1
    record = (_reload(db, execution.id).config or {})[alerts.CONFIG_RECORD_KEY]
    assert record["outcome"] == alerts.OUTCOME_PUBLISHED


def test_session_factory_failure_is_best_effort_failed(monkeypatch):
    def _factory_failure():
        raise RuntimeError("session factory unavailable")

    monkeypatch.setattr(alerts, "SessionLocal", _factory_failure)

    outcome = alerts.emit_execution_failed_alert(uuid.uuid4())
    assert outcome == alerts.OUTCOME_FAILED


def test_non_object_historical_config_is_never_overwritten_by_alert_record(db):
    """fresh 内审 P1：brownfield 非对象 JSON 是证据，不能为了留痕整份抹掉。"""
    legacy_evidence = ["raw-scpi-evidence", {"response": "-113"}]
    execution = _execution(db, config=legacy_evidence)

    outcome = alerts.emit_execution_failed_alert(execution.id)
    assert outcome == alerts.OUTCOME_PUBLISHED
    assert db.query(Alert).count() == 1

    row = _reload(db, execution.id)
    assert row.status == "failed"
    assert row.config == legacy_evidence


# ─────────────────────────── 门C：历史行 = 未记录，绝不折叠成成功 ───────────────────────────


@pytest.mark.parametrize("config", [
    None,                                              # 行连 config 都没有
    {"error_message": "老失败"},                        # P2-34 之前的历史失败行
    {"failure_alert": "published"},                    # 畸形：记录不是 dict
    {"failure_alert": {"outcome": "exploded"}},        # 畸形：outcome 越界值
    {"failure_alert": {}},                             # 畸形：没有 outcome
    {"failure_alert": {"outcome": ["published"]}},    # 畸形：不可哈希（list），不许抛 TypeError 毒整页
    {"failure_alert": {"outcome": {"a": 1}}},         # 畸形：不可哈希（dict）
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


@pytest.mark.parametrize(
    "malformed_record",
    [{}, {"outcome": "exploded"}],
)
def test_duplicate_replaces_malformed_historical_record(db, malformed_record):
    """Codex R1 P2：畸形 dict 仍是未记录，不能挡住 duplicate 的安全回填。"""
    execution = _execution(db)
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED
    alert = db.query(Alert).one()

    row = _reload(db, execution.id)
    cfg = dict(row.config or {})
    cfg[alerts.CONFIG_RECORD_KEY] = malformed_record
    row.config = cfg
    db.commit()

    outcome = alerts.emit_execution_failed_alert(execution.id)
    assert outcome == alerts.OUTCOME_DUPLICATE
    assert db.query(Alert).count() == 1

    record = (_reload(db, execution.id).config or {})[alerts.CONFIG_RECORD_KEY]
    assert record["outcome"] == alerts.OUTCOME_DUPLICATE
    assert record["alert_id"] == str(alert.id)
    assert record.get("recorded_at")


def test_duplicate_advances_prior_failed_record_when_alert_now_exists(db):
    """fresh 内审 P1：现存 Alert 证伪旧 failed，结果必须推进且带真实关联。"""
    execution = _execution(db)
    assert alerts.emit_execution_failed_alert(execution.id) == alerts.OUTCOME_PUBLISHED
    alert = db.query(Alert).one()

    row = _reload(db, execution.id)
    cfg = dict(row.config or {})
    cfg[alerts.CONFIG_RECORD_KEY] = {
        "outcome": alerts.OUTCOME_FAILED,
        "recorded_at": "2026-08-21T00:00:00+00:00",
        "error": "OperationalError: commit acknowledgement lost",
    }
    row.config = cfg
    db.commit()

    outcome = alerts.emit_execution_failed_alert(execution.id)
    assert outcome == alerts.OUTCOME_DUPLICATE
    assert db.query(Alert).count() == 1

    record = (_reload(db, execution.id).config or {})[alerts.CONFIG_RECORD_KEY]
    assert record["outcome"] == alerts.OUTCOME_DUPLICATE
    assert record["alert_id"] == str(alert.id)
    assert "error" not in record


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
