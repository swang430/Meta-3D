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
from app.services.mimo_ota.rf_kpi_trust import build_rf_kpi_trust

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
        # P2-19: token 对齐唯一写方 runner (StepExecutionStatus.SUCCESS.value =
        # "success") — fixture 原用 "completed" 与实现同错自洽, 门验了个寂寞
        [{"type": f"phase{i}", "status": "success"} for i in range(phases_done)]
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
        1 for p in progress if p["status"] == "success")
    assert row["phases_total"] == 5
    assert row["executed_by"] == "test_case_runner"


def test_ga_malformed_config_row_does_not_poison_list(db, lab):
    """内审 F1: 一行畸形 config (phase_progress 非 list / 元素非 dict /
    step_descriptors 非 list) 不许把整页列表毒成空 — 正常行照常返回,
    畸形行按三态 None 处理。变异 = 去掉 isinstance 收窄 → 畸形行抛
    AttributeError 被外层 except 吞成空表 → total 断言红。"""
    snapshot = _make_case(db, lab, name="正常行")
    _case_runner_execution(db, snapshot)
    poison = TestExecution(
        test_case_id=snapshot.id,
        status="completed",
        config={
            "step_descriptors": "abc",           # 非 list
            "phase_progress": ["oops", {"status": "success"}],  # 元素混杂
            "error_message": {"code": 500},      # 非串 (内审 F1: 会让
            # Pydantic 拒绝整行 → 外层 except 吞成空表)
        },
        executed_by="test_case_runner",
    )
    db.add(poison)
    db.commit()

    client = TestClient(app)
    body = client.get("/api/v1/test-executions").json()
    assert body["total"] == 2  # 正常行没被毒掉
    rows = {r["id"]: r for r in body["items"]}
    bad = rows[str(poison.id)]
    assert bad["phases_total"] is None      # "abc" 不许数出 3
    assert bad["phases_done"] == 1          # 非 dict 元素跳过
    good = [r for r in body["items"] if r["id"] != str(poison.id)][0]
    assert good["case_name"] == "正常行"


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


def test_ga_mimo_validation_requires_explicit_real_path_loss_provenance(db, lab, monkeypatch):
    # Isolate this path-loss contract from P1-64's independent quiet-zone gate.
    monkeypatch.setattr(
        "app.api.test_execution.quiet_zone_scope_is_formally_verified",
        lambda _precheck: True,
    )
    snapshot = _make_case(db, lab, name="MIMO provenance history")
    legacy = _case_runner_execution(db, snapshot)
    legacy.validation_pass = True
    legacy.measurements = {
        "phases": {"measure": {
            "measurement_source": "instrument",
            "measurement_verified": True,
            "simulated_sources": [],
            "path_loss_verified": True,
            "path_loss_certificate_id": "legacy-cert",
        }}
    }
    fresh = _case_runner_execution(db, snapshot)
    fresh.validation_pass = True
    fresh.measurements = {
        "phases": {"measure": {
            "measurement_source": "instrument",
            "measurement_verified": True,
            "simulated_sources": [],
            "path_loss_verified": True,
            "path_loss_calibration_use_mock": False,
            "path_loss_application": {
                "schema_version": 1,
                "status": "applied",
                "provenance": "real",
                "reason": "selected",
                "gate_mode": "strict",
                "certificate_id": "fresh-real-cert",
                "value_disclosure": "verified",
            },
            "throughput_verified": True,
            "throughput_scope": "pcell",
            "carrier_aggregation": {"num_component_carriers": 1},
            "azimuth_results": [{
                "azimuth_deg": 0.0,
                "measurement_source": "instrument",
                "measurement_verified": True,
                "rsrp_dbm": -80.0,
                "rsrp_valid": True,
                "sinr_db": 20.0,
                "sinr_valid": True,
                "rank_indicator": 2.0,
                "rank_indicator_valid": True,
                "throughput_valid": True,
                "throughput_scope": "pcell",
            }],
        }}
    }
    fresh_measure = fresh.measurements["phases"]["measure"]
    fresh_measure["rf_kpi_trust"] = build_rf_kpi_trust(
        requested_azimuths=[0.0],
        azimuth_results=fresh_measure["azimuth_results"],
        source="explicit_real",
    )
    fresh_measure["formal_rf_kpi_verified"] = True
    malformed = _case_runner_execution(db, snapshot)
    malformed.validation_pass = True
    malformed.measurements = {
        "phases": {"measure": {
            "path_loss_verified": True,
            "path_loss_calibration_use_mock": False,
            "path_loss_application": {
                "schema_version": 1,
                "status": "applied",
                "provenance": "simulated",
                "reason": "selected",
                "gate_mode": "strict",
                "certificate_id": "impossible-strict-simulated",
                "value_disclosure": "hidden_unverified",
            },
            "throughput_verified": True,
            "throughput_scope": "pcell",
            "carrier_aggregation": {"num_component_carriers": 1},
            "azimuth_results": [{
                "throughput_valid": True,
                "throughput_scope": "pcell",
            }],
        }}
    }
    db.commit()

    rows = {
        row["id"]: row
        for row in TestClient(app).get("/api/v1/test-executions").json()["items"]
    }

    assert rows[str(legacy.id)]["validation_pass"] is None
    assert rows[str(fresh.id)]["validation_pass"] is True
    assert rows[str(malformed.id)]["validation_pass"] is None


def test_ga_legacy_mimo_without_path_loss_markers_is_not_formal_fail(db, lab):
    snapshot = _make_case(db, lab, name="Legacy MIMO without provenance")
    legacy = _case_runner_execution(db, snapshot)
    legacy.validation_pass = False
    legacy.config = {
        **legacy.config,
        "step_descriptors": [
            {"id": "measure", "type": "MIMO_OTA_MEASURE", "parameters": {}}
        ],
    }
    legacy.measurements = {"phases": {"measure": {}}}
    db.commit()

    row = next(
        item
        for item in TestClient(app).get("/api/v1/test-executions").json()["items"]
        if item["id"] == str(legacy.id)
    )

    assert row["validation_pass"] is None


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


def test_gd_error_message_falls_back_to_config(db, lab):
    """Codex #238 迟到 C-1: case-runner 把失败文本写 config["error_message"]
    不写列 (三处写 config: 复位/异常/收尾; 五个终态写入点没有一处写列,
    另两处什么消息都不写) — 列表和报告都要能读到。
    fake 按真实 runner 形状造行 (列留空)。变异 = 去掉 fallback → 红。"""
    snapshot = _make_case(db, lab, name="失败的用例")
    execution = TestExecution(
        test_case_id=snapshot.id,
        status="failed",
        started_at=datetime(2026, 7, 27, 10, 0, 0),
        completed_at=datetime(2026, 7, 27, 10, 5, 0),
        config={
            "step_descriptors": [
                {"id": "p0", "type": "measure", "parameters": {}}],
            "source_test_case_id": str(snapshot.id),
            "phase_progress": [{"type": "measure", "status": "failed"}],
            "failed_phase": "measure",
            "error_message": "执行器异常: 探头 17 无响应",  # 真实 runner 只写这里
        },
        executed_by="test_case_runner",
        error_message=None,  # 列是空的 — 这就是真实形状
    )
    db.add(execution)
    db.commit()

    client = TestClient(app)
    row = client.get("/api/v1/test-executions").json()["items"][0]
    assert row["error_message"] == "执行器异常: 探头 17 无响应"

    # 报告的相位结果段同样要拿到
    from app.services.report_data_collector import ReportDataCollector
    phase_rows = ReportDataCollector()._get_phase_results([execution])
    assert phase_rows[0]["error_message"] == "执行器异常: 探头 17 无响应"


def test_gd_recovery_not_crowded_out_by_stale_plan_rows(db, lab):
    """Codex #238 迟到 C-3: plan-runner 的 stale running 行没人复位,
    堆多了不许把 case 执行挤出恢复窗口 — 服务端按 executed_by 收窄。
    变异 = 砍 executed_by 过滤 → total 断言红。"""
    source = _make_case(db, lab, name="被挤的用例")
    snapshot = _make_case(db, lab, name="被挤的用例 [执行]")
    case_run = _case_runner_execution(
        db, snapshot, status="running", phases_done=1, source_id=source.id)
    # executed_at 必须显式写 (内审 F1): server_default 的 CURRENT_TIMESTAMP
    # 在 SQLite 是秒分辨率, 同秒插入全部相等 → 平局按插入序返回, case 行
    # 反而排最前, "被挤出"根本不会发生, 招牌断言就成了恒真
    case_run.executed_at = datetime(2026, 7, 27, 10, 0, 0)
    db.commit()
    # 5 个明确更新的 plan-runner 僵尸 running 行 → 无收窄时占满 limit 窗口
    for i in range(5):
        db.add(TestExecution(
            status="running",
            executed_by="test_plan_runner",
            executed_at=datetime(2026, 7, 27, 11, i, 0),
            config={"step_descriptors": [], "test_step_id": f"step-{i}"},
        ))
    db.commit()

    client = TestClient(app)
    body = client.get(
        "/api/v1/test-executions",
        params={"status": "running", "executed_by": "test_case_runner",
                "limit": 5},
    ).json()
    assert body["total"] == 1  # 只剩 case 链的行
    assert body["items"][0]["source_test_case_id"] == str(source.id)


def test_gd_formal_chains_not_crowded_out_by_adhoc(db, lab):
    """Codex #239 迟到: 待归档列表要的是"正式执行", 而单相位诊断行收尾后
    也是 completed —— 诊断行一多就把正式执行挤出 limit 窗口 (客户端过滤
    在窗口之后跑, 救不回来)。多值 executed_by 让收窄回到服务端。
    变异 = 不传 executed_by (等价于旧的客户端过滤) → 正式行不在返回里。"""
    snapshot = _make_case(db, lab, name="正式执行用例")
    formal = _case_runner_execution(db, snapshot)
    # executed_at 显式写死 (内审 F1): 靠 server_default 在 SQLite 上是同秒
    # 平局, 平局按插入序返回反而让 formal 排最前 → "被挤出"不成立, 招牌
    # 断言恒真 (变异实证: 只留该断言 + 去收窄, 修复前不红修复后红)
    formal.executed_at = datetime(2026, 7, 27, 10, 0, 0)  # 最老
    db.commit()
    for i in range(6):  # 6 条明确更新的诊断行, 数量 > limit
        db.add(TestExecution(
            test_case_id=snapshot.id,
            status="completed",
            executed_by="commissioning_adhoc",
            executed_at=datetime(2026, 7, 27, 12, i, 0),
            config={"diagnostic_ad_hoc": True,
                    "step_descriptors": [{"id": f"d{i}", "type": "precheck",
                                          "parameters": {}}]},
        ))
    db.commit()

    client = TestClient(app)
    body = client.get(
        "/api/v1/test-executions",
        params={
            "status": "completed",
            "limit": 5,  # 小于诊断行数 — 不收窄的话正式行必被挤出
            "executed_by": ["test_case_runner", "test_plan_runner",
                            "commissioning_api"],
        },
    ).json()
    ids = [r["id"] for r in body["items"]]
    assert str(formal.id) in ids, "正式执行被诊断行挤出了 limit 窗口"
    assert body["total"] == 1
    assert all(r["executed_by"] != "commissioning_adhoc" for r in body["items"])


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
