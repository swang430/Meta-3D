"""ARCH-1 S2: 执行历史/报告换源到 test_executions 本表 — 六道门。

核心契约 (设计稿 docs/design/arch-1-s2-execution-history-resource.md):
  G-a 列表查的是执行行本表: case-runner 行查得到, case_name = 快照名,
      phases_done 与 config.phase_progress 逐条一致;
  G-b VRT 行 (mode IS NOT NULL) 不混进测试历史;
  G-c 报告断线接上: 列表返回的 id 交给报告收集器能查到执行行且摘要非空;
      同时钉死旧路是断的 (计划摘要表主键 → 收集器查 0 行 → 摘要为 None);
  G-d status=running 查得到在跑的行且带 source_test_case_id (C3 恢复入口);
  G-e 契约不变量: openapi.yaml TestExecutionItem 属性集合 ==
      Pydantic ExecutionHistoryItem 字段集合 ("契约 4 步"下沉成门);
  G-f 无 plan 执行的报告标题用快照用例名, 全文不含 "Unknown Plan"。

变异自验对应表 (⓪-④, 每条实跑红后还原):
- 列表 query 换回 TestPlanExecution → test_ga_* 红 (空列表)
- 砍 mode IS NULL 谓词 → test_gb_vrt_rows_excluded 红
- 收集器 _get_executions 改按 TestPlanExecution.id 语义 (即旧实况) →
  test_gc_report_id_reaches_collector 红
- 砍 status 过滤 / 不回填 source_test_case_id → test_gd_running_row 红
- ExecutionHistoryItem 加字段不同步 openapi.yaml → test_ge_contract_sync 红
- 还原 executors/report.py 写死标题 (忽略 case_name) → test_gf_report_title 红
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.lab_profile import LabProfile
from app.models.report import TestReport
from app.models.test_plan import TestCase, TestExecution, TestPlanExecution

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _db_schema():
    Base.metadata.create_all(bind=engine)
    prev = app.dependency_overrides.get(get_db)

    def _override():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    yield
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def lab(db):
    chamber = create_chamber_from_preset(
        ChamberType.TYPE_C.value, name="HistoryLab Chamber")
    db.add(chamber)
    db.commit()
    lp = LabProfile(
        name="History-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _make_case(db, lab, name="history-case"):
    from app.services.mimo_ota.factory import build_mimo_ota_test_case

    tc, _ = build_mimo_ota_test_case(
        db, name=name, lab_profile_id=lab.id,
        config_overrides={}, created_by="test",
    )
    return tc


def _case_runner_execution(
    db, snapshot, *, status="completed", phases_done=5, phases_failed=0,
    source_id=None,
):
    """按 case-runner 的真实写入形状造执行行 (test_case_runner.py:140)。"""
    progress = (
        [{"type": f"phase{i}", "status": "completed"} for i in range(phases_done)]
        + [{"type": "measure", "status": "failed"}] * phases_failed
    )
    execution = TestExecution(
        test_case_id=snapshot.id,
        status=status,
        started_at=datetime(2026, 7, 27, 10, 0, 0),
        completed_at=(
            datetime(2026, 7, 27, 10, 30, 0) if status != "running" else None
        ),
        duration_sec=1800.0 if status != "running" else None,
        config={
            "step_descriptors": [
                {"id": f"phase{i}", "type": f"phase{i}", "parameters": {}}
                for i in range(5)
            ],
            "source_test_case_id": str(source_id or snapshot.id),
            "phase_progress": progress,
        },
        executed_by="test_case_runner",
        measurements={"phases": {}},
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


# ── G-a 列表 = 执行行本表 ──────────────────────────────────────────


def test_ga_case_run_row_visible_with_snapshot_name(db, lab):
    snapshot = _make_case(db, lab, name="G-a 快照用例")
    execution = _case_runner_execution(db, snapshot, phases_done=3)

    client = TestClient(app)
    body = client.get("/api/v1/test-executions").json()

    assert body["total"] == 1
    row = body["items"][0]
    assert row["id"] == str(execution.id)
    # 生效端断言: 名字来自快照 TestCase 行 (join), 不是任何计划字段
    assert row["case_name"] == "G-a 快照用例"
    assert row["source_test_case_id"] == str(snapshot.id)
    # phases_done 与 config.phase_progress 逐条一致 (不变量)
    progress = execution.config["phase_progress"]
    assert row["phases_done"] == sum(
        1 for p in progress if p["status"] == "completed")
    assert row["phases_total"] == 5
    assert row["executed_by"] == "test_case_runner"


def test_ga_no_phase_progress_stays_none(db, lab):
    """暗室首测形状的行 (无 phase_progress 键) → phases_done/failed 是
    None 不是 0 — 三态语义, 不伪造进度。"""
    snapshot = _make_case(db, lab, name="commissioning-案例")
    execution = TestExecution(
        test_case_id=snapshot.id,
        status="completed",
        started_at=datetime(2026, 7, 27, 9, 0, 0),
        completed_at=datetime(2026, 7, 27, 9, 20, 0),
        config={
            "step_descriptors": [
                {"id": "s1", "type": "mimo_throughput", "parameters": {}}
            ]
        },
        executed_by="commissioning_api",
    )
    db.add(execution)
    db.commit()

    client = TestClient(app)
    row = client.get("/api/v1/test-executions").json()["items"][0]
    assert row["phases_done"] is None
    assert row["phases_failed"] is None
    assert row["phases_total"] == 1  # descriptors 有, 只是不记进度


# ── G-b VRT 行不混入 ───────────────────────────────────────────────


def test_gb_vrt_rows_excluded(db, lab):
    snapshot = _make_case(db, lab)
    _case_runner_execution(db, snapshot)
    vrt = TestExecution(
        status="completed",
        mode="digital_twin",  # VRT 行的判据 (vrt_execution_service.py:118 的镜像)
        scenario_id="scenario-1",
        executed_by="vrt-user",
    )
    db.add(vrt)
    db.commit()

    client = TestClient(app)
    body = client.get("/api/v1/test-executions").json()
    assert body["total"] == 1
    assert all(r["id"] != str(vrt.id) for r in body["items"])


# ── G-c 报告断线接上 (同时钉死旧路是断的) ──────────────────────────


def test_gc_report_id_reaches_collector(db, lab):
    from app.services.report_data_collector import ReportDataCollector

    snapshot = _make_case(db, lab, name="G-c 报告用例")
    _case_runner_execution(db, snapshot)

    client = TestClient(app)
    row = client.get("/api/v1/test-executions").json()["items"][0]

    # 新路: 列表返回的 id 直接当报告的 test_execution_ids
    report = TestReport(
        title="G-c 执行报告",
        report_type="single_execution",
        format="pdf",
        generated_by="test",
        test_plan_id=None,
        test_execution_ids=[row["id"]],
    )
    db.add(report)
    db.commit()

    data = ReportDataCollector().collect(db, report)
    # 生效端断言: 收集器真查到执行行, 摘要非空 (不是"传了 id"就算过)
    assert data.execution_summary is not None
    assert data.execution_summary.total_executions == 1
    # 无 plan 路径的步骤结果段从相位进度派生, 不再整段空缺
    assert len(data.step_results) == 5


def test_gc_legacy_summary_table_id_finds_nothing(db, lab):
    """钉死换源前的实况: 计划摘要表主键交给收集器 → 查 0 行 → 摘要 None。
    这条是"旧路是断的"的证据, 不许有人把列表悄悄换回摘要表。"""
    from app.services.report_data_collector import ReportDataCollector

    legacy = TestPlanExecution(
        test_plan_id=uuid.uuid4(),
        test_plan_name="旧计划",
        test_plan_version="1.0",
        status="completed",
        total_steps=5, completed_steps=5, failed_steps=0, skipped_steps=0,
        success_rate=1.0,
        started_at=datetime(2026, 7, 1, 9, 0, 0),
        completed_at=datetime(2026, 7, 1, 10, 0, 0),
        duration_minutes=60.0,
        started_by="operator",
    )
    db.add(legacy)
    db.commit()

    report = TestReport(
        title="断线对照",
        report_type="single_execution",
        format="pdf",
        generated_by="test",
        test_plan_id=None,
        test_execution_ids=[str(legacy.id)],  # 跨表主键 — 今天以前的实际行为
    )
    db.add(report)
    db.commit()

    data = ReportDataCollector().collect(db, report)
    assert data.execution_summary is None  # 命中 0 行, 摘要整段跳过


# ── G-d running 行可查 (C3 恢复入口) ──────────────────────────────


def test_gd_running_row_with_source_id(db, lab):
    source = _make_case(db, lab, name="原用例")
    snapshot = _make_case(db, lab, name="原用例 [执行 20260727-100000]")
    _case_runner_execution(
        db, snapshot, status="running", phases_done=2, source_id=source.id)
    # 干扰行: 已完成的不该被 running 过滤带出
    done_snap = _make_case(db, lab, name="已完成的")
    _case_runner_execution(db, done_snap)

    client = TestClient(app)
    body = client.get(
        "/api/v1/test-executions", params={"status": "running", "limit": 1}
    ).json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["status"] == "running"
    # C3 的关键: 徽标要挂回原用例行, source_test_case_id 必须回填
    assert row["source_test_case_id"] == str(source.id)
    assert row["phases_done"] == 2


# ── G-e 契约不变量 ─────────────────────────────────────────────────


def test_ge_contract_fields_match_pydantic():
    """openapi.yaml 的 TestExecutionItem 属性集合 == 后端
    ExecutionHistoryItem 字段集合 — Pydantic 加字段不同步契约当场红
    (memory "契约 4 步" 的第 1 步下沉成门)。"""
    import yaml

    from app.schemas.test_plan import ExecutionHistoryItem

    spec_path = Path(__file__).resolve().parents[2] / "api" / "openapi.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    contract_props = set(
        spec["components"]["schemas"]["TestExecutionItem"]["properties"])
    pydantic_fields = set(ExecutionHistoryItem.model_fields)
    assert contract_props == pydantic_fields, (
        f"契约与后端字段集合漂移: 只在契约 {contract_props - pydantic_fields}, "
        f"只在后端 {pydantic_fields - contract_props}"
    )


# ── G-f 报告标题用快照用例名 ──────────────────────────────────────


def test_gf_report_title_uses_case_name(db, lab):
    """无 plan 执行的报告内容: 标题含快照用例名, 全文不含 Unknown Plan。
    生效端 = 生成出来的 content_data, 不是"代码里没那个字符串"。"""
    import json

    from app.services.mimo_ota.executors.report import (
        _build_mimo_ota_content_data,
        _lookup_case_name,
    )

    snapshot = _make_case(db, lab, name="G-f 标题用例")
    execution = _case_runner_execution(db, snapshot)

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.db = db
    # 名字查询走真 DB (relationship 是注释掉的, helper 必须显式查)
    name = _lookup_case_name(ctx, execution)
    assert name == "G-f 标题用例"

    content = _build_mimo_ota_content_data(
        execution, datetime(2026, 7, 27, 12, 0, 0), name)
    assert "G-f 标题用例" in content["title"]
    assert content["test_plan"]["name"] == "G-f 标题用例"
    assert "Unknown Plan" not in json.dumps(content)


def test_gf_missing_snapshot_falls_back(db, lab):
    """快照被删 / 孤立执行 → 兜底"未命名用例", 仍不是 Unknown Plan。"""
    from app.services.mimo_ota.executors.report import _lookup_case_name

    execution = TestExecution(
        test_case_id=uuid.uuid4(),  # 指向不存在的 case
        status="completed",
        executed_by="test_case_runner",
        config={},
    )
    db.add(execution)
    db.commit()

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.db = db
    assert _lookup_case_name(ctx, execution) == "未命名用例"
