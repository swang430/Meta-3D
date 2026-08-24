# -*- coding: utf-8 -*-
"""P1-72 门：对比换源 execution 级 + repeatability_tests 激活。

设计出处：docs/plans/2026-08-24-p1-69-calibration-design.md §5。

门清单（④ 每门配变异，见 PR 记录）：
  G-A 行为门：create+analyze 闭环——指标差分数值正确、summary 统计正确
  G-B 行为门：formal 判定按 provenance（全 verified→True；任一 simulated→False+注记）
  G-C 行为门：同 TestCase 落 repeatability 对齐行（字段完整）；异 case 不落
  G-D 行为门：fail-loud——缺 execution 拒建、缺指标拒析、plan 级历史行拒析
  G-E API 门：POST /calibration/repeatability 恒 503 且零落库
  G-F 不变量门：analyze 不写 significant_differences（单次运行无分布，不造显著性）
  G-G 注释门（粗筛）：repeatability 列注释 ⊇ 活写点值（G-A/C 为其配套行为门）
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.calibration import RepeatabilityTest
from app.models.report import ReportComparison
from app.models.test_plan import TestCase, TestExecution
from app.services.report_service import (
    COMPARISON_METRIC_KEYS,
    ReportComparisonService,
)

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _analysis_payload(throughput, sinr, rsrp_var, verified=True):
    return {
        "verdict": "PASS" if verified else "UNKNOWN",
        "measurement_verified": verified,
        "throughput_verified": verified,
        "rf_kpi_verified": verified,
        "avg_throughput_mbps": throughput,
        "throughput_ratio": throughput / 1000.0,
        "rsrp_variance_db": rsrp_var,
        "avg_sinr_db": sinr,
    }


def _mk_case(db, name="P1-72 case"):
    case = TestCase(
        id=uuid.uuid4(),
        name=name,
        test_type="Throughput",
        configuration={},
        created_by="p1-72-gate",
    )
    db.add(case)
    db.commit()
    return case


def _mk_execution(db, case, analysis, started_at=None):
    execution = TestExecution(
        id=uuid.uuid4(),
        test_case_id=case.id if case else None,
        status="completed",
        started_at=started_at or datetime(2026, 8, 25, 10, 0, 0),
        measurements={"phases": {"analysis": analysis}} if analysis else None,
    )
    db.add(execution)
    db.commit()
    return execution


def _svc():
    return ReportComparisonService()


class TestExecutionComparisonLoop:
    """G-A / G-B / G-F：create + analyze 闭环。"""

    def test_deltas_and_summary_are_correct(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        comp = _mk_execution(db, case, _analysis_payload(910.0, 24.5, 1.2))
        svc = _svc()
        row = svc.create_comparison(
            db, name="c1", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="p1-72-gate",
        )
        analyzed = svc.perform_comparison_analysis(db, row.id)
        results = analyzed.comparison_results
        assert results["mode"] == "execution"
        assert results["baseline"]["execution_id"] == str(base.id)
        deltas = results["deltas"][0]["deltas"]
        assert deltas["avg_throughput_mbps"] == pytest.approx(60.0)
        assert deltas["avg_sinr_db"] == pytest.approx(2.5)
        assert deltas["rsrp_variance_db"] == pytest.approx(-0.3)
        summary = analyzed.summary_statistics
        assert summary["avg_throughput_mbps"]["mean"] == pytest.approx(880.0)
        assert summary["avg_throughput_mbps"]["spread"] == pytest.approx(60.0)
        assert summary["avg_sinr_db"]["n"] == 2
        # G-B：两个都 verified → formal
        assert results["formal"] is True
        assert results["formal_note"] is None
        # G-F：不造显著性
        assert analyzed.significant_differences is None
        # 封存 plan 列恒空数组
        assert analyzed.comparison_plan_ids == []

    def test_simulated_provenance_marks_not_formal(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        comp = _mk_execution(
            db, case, _analysis_payload(910.0, 24.5, 1.2, verified=False)
        )
        svc = _svc()
        row = svc.create_comparison(
            db, name="c2", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="p1-72-gate",
        )
        analyzed = svc.perform_comparison_analysis(db, row.id)
        assert analyzed.comparison_results["formal"] is False
        assert "模拟仪器 provenance" in analyzed.comparison_results["formal_note"]

    def test_truthy_but_not_true_provenance_is_not_formal(self, db):
        # 内审 F7：formal 判定必须是严格 is True —— "yes"/1 这类 truthy
        # 值放宽成 truthy 判定时本门要红
        case = _mk_case(db)
        payload = _analysis_payload(910.0, 24.5, 1.2)
        payload["measurement_verified"] = "yes"
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        comp = _mk_execution(db, case, payload)
        svc = _svc()
        row = svc.create_comparison(
            db, name="c-truthy", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="g",
        )
        analyzed = svc.perform_comparison_analysis(db, row.id)
        assert analyzed.comparison_results["formal"] is False


class TestRepeatabilityAlignment:
    """G-C：同 case 落对齐行；异 case 不落。"""

    def test_same_case_writes_alignment_row(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        comp = _mk_execution(db, case, _analysis_payload(910.0, 24.5, 1.2))
        svc = _svc()
        row = svc.create_comparison(
            db, name="c3", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="p1-72-gate",
        )
        analyzed = svc.perform_comparison_analysis(db, row.id)
        reps = db.query(RepeatabilityTest).all()
        assert len(reps) == 1
        rep = reps[0]
        assert rep.test_type == "execution_metrics"
        assert rep.test_case_id == case.id
        assert rep.num_runs == 2
        assert rep.execution_ids == [str(base.id), str(comp.id)]
        assert rep.metric_deltas["baseline_execution_id"] == str(base.id)
        assert rep.metric_deltas["deltas"][0]["deltas"][
            "avg_throughput_mbps"
        ] == pytest.approx(60.0)
        # execution_metrics 行不填 dBm 语义列、不造判决
        assert rep.mean_dbm is None
        assert rep.std_dev_db is None
        assert rep.validation_pass is None
        # measurements 为 execution 形态
        assert rep.measurements[0]["execution_id"] == str(base.id)
        assert "metrics" in rep.measurements[0]
        # 对比结果回填对齐行 id
        assert analyzed.comparison_results["repeatability_test_id"] == str(rep.id)

    def test_different_cases_do_not_write_alignment_row(self, db):
        case_a, case_b = _mk_case(db, "case A"), _mk_case(db, "case B")
        base = _mk_execution(db, case_a, _analysis_payload(850.0, 22.0, 1.5))
        comp = _mk_execution(db, case_b, _analysis_payload(910.0, 24.5, 1.2))
        svc = _svc()
        row = svc.create_comparison(
            db, name="c4", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="p1-72-gate",
        )
        analyzed = svc.perform_comparison_analysis(db, row.id)
        assert db.query(RepeatabilityTest).count() == 0
        assert "repeatability_test_id" not in analyzed.comparison_results


class TestFailLoud:
    """G-D：三条 fail-loud 路径。"""

    def test_create_rejects_missing_execution(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        with pytest.raises(ValueError, match="不建悬空对比"):
            _svc().create_comparison(
                db, name="cx", baseline_execution_id=base.id,
                comparison_execution_ids=[uuid.uuid4()], created_by="g",
            )
        assert db.query(ReportComparison).count() == 0

    def test_analyze_rejects_execution_without_metrics(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        comp = _mk_execution(db, case, analysis=None)
        svc = _svc()
        row = svc.create_comparison(
            db, name="c5", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="g",
        )
        with pytest.raises(ValueError, match="无指标可对比"):
            svc.perform_comparison_analysis(db, row.id)
        db.rollback()
        assert db.query(RepeatabilityTest).count() == 0

    def test_analyze_rejects_sealed_plan_level_row(self, db):
        row = ReportComparison(
            name="legacy", comparison_plan_ids=[str(uuid.uuid4())],
            created_by="history",
        )
        db.add(row)
        db.commit()
        with pytest.raises(ValueError, match="计划链已封存"):
            _svc().perform_comparison_analysis(db, row.id)


class TestRepeatabilityMockEndpointClosed:
    """G-E：mock 合成口恒 503 且零落库。"""

    def test_post_returns_503_and_writes_nothing(self, db, monkeypatch):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.database import get_db

        # generator 依赖必须用 generator function（内审 F6：lambda 返回
        # iterator 会被原样注入成 db 参数）
        def _override():
            yield db

        app.dependency_overrides[get_db] = _override
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/calibration/repeatability",
                json={
                    "test_type": "TRP",
                    "dut_model": "M",
                    "dut_serial": "S",
                    "num_runs": 5,
                    "frequency_mhz": 3550.0,
                    "tested_by": "gate",
                },
            )
            assert resp.status_code == 503
            assert "不生成模拟数值" in resp.json()["detail"]
            assert db.query(RepeatabilityTest).count() == 0
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestReviewFindingsGates:
    """内审 F1-F5 修复的行为门。"""

    def _analyzed_pair(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        comp = _mk_execution(db, case, _analysis_payload(910.0, 24.5, 1.2))
        svc = _svc()
        row = svc.create_comparison(
            db, name="rf", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="p1-72-gate",
        )
        return svc, row

    def test_f1_get_list_survives_alignment_row(self, db):
        # F1(P1)：落首行对齐记录后 GET 列表必须 200 且能读回对齐字段
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.database import get_db

        svc, row = self._analyzed_pair(db)
        svc.perform_comparison_analysis(db, row.id)

        def _override():
            yield db

        app.dependency_overrides[get_db] = _override
        try:
            resp = TestClient(app).get("/api/v1/calibration/repeatability")
            assert resp.status_code == 200, resp.text
            items = resp.json()
            assert len(items) == 1
            item = items[0]
            assert item["test_type"] == "execution_metrics"
            assert item["mean_dbm"] is None
            assert item["test_case_id"] is not None
            assert len(item["execution_ids"]) == 2
            assert item["metric_deltas"]["deltas"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_f2_self_comparison_rejected(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        with pytest.raises(ValueError, match="重复"):
            _svc().create_comparison(
                db, name="self", baseline_execution_id=base.id,
                comparison_execution_ids=[base.id], created_by="g",
            )
        assert db.query(ReportComparison).count() == 0

    def test_f3_reanalyze_does_not_multiply_alignment_rows(self, db):
        svc, row = self._analyzed_pair(db)
        first = svc.perform_comparison_analysis(db, row.id)
        first_rep_id = first.comparison_results["repeatability_test_id"]
        second = svc.perform_comparison_analysis(db, row.id)
        assert db.query(RepeatabilityTest).count() == 1
        second_rep_id = second.comparison_results["repeatability_test_id"]
        assert db.get(RepeatabilityTest, uuid.UUID(second_rep_id)) is not None
        # 旧行必须已被替换删除（重分析产新行、旧 id 查无此行）
        assert first_rep_id != second_rep_id
        assert db.get(RepeatabilityTest, uuid.UUID(first_rep_id)) is None

    def test_f4_certificate_rejects_alignment_row(self, db):
        from datetime import datetime as _dt
        from app.models.calibration import (
            SystemTISCalibration,
            SystemTRPCalibration,
        )
        from app.services.system_calibration import (
            CalibrationCertificateService,
        )

        svc, row = self._analyzed_pair(db)
        analyzed = svc.perform_comparison_analysis(db, row.id)
        rep_id = analyzed.comparison_results["repeatability_test_id"]

        trp = SystemTRPCalibration(
            standard_dut_model="M", standard_dut_serial="S",
            reference_trp_dbm=20.0, frequency_mhz=3550.0,
            measured_trp_dbm=20.2, trp_error_db=0.2, absolute_error_db=0.2,
            validation_pass=True, tested_at=_dt.utcnow(),
        )
        tis = SystemTISCalibration(
            standard_dut_model="M", standard_dut_serial="S",
            reference_tis_dbm=-95.0, frequency_mhz=3550.0,
            measured_tis_dbm=-94.8, tis_error_db=0.2, absolute_error_db=0.2,
            validation_pass=True, tested_at=_dt.utcnow(),
        )
        db.add_all([trp, tis])
        db.commit()
        with pytest.raises(ValueError, match="execution_metrics"):
            CalibrationCertificateService().generate_certificate(
                db=db,
                trp_calibration_id=trp.id,
                tis_calibration_id=tis.id,
                repeatability_test_id=uuid.UUID(rep_id),
                lab_name="L", lab_address="A", lab_accreditation="C",
                calibrated_by="g", reviewed_by="g",
            )

    def test_f5_analysis_without_metric_keys_rejected(self, db):
        case = _mk_case(db)
        base = _mk_execution(db, case, _analysis_payload(850.0, 22.0, 1.5))
        bare = {"verdict": "PASS", "measurement_verified": True}
        comp = _mk_execution(db, case, bare)
        svc = _svc()
        row = svc.create_comparison(
            db, name="c-bare", baseline_execution_id=base.id,
            comparison_execution_ids=[comp.id], created_by="g",
        )
        with pytest.raises(ValueError, match="无指标可对比"):
            svc.perform_comparison_analysis(db, row.id)


class TestColumnCommentsCoverWriteValues:
    """G-G：列注释 ⊇ 活写点值（粗筛；行为在 G-A/G-C）。"""

    def test_test_type_comment_covers_execution_metrics(self):
        comment = RepeatabilityTest.__table__.c.test_type.comment or ""
        assert "execution_metrics" in comment
        measurements_comment = RepeatabilityTest.__table__.c.measurements.comment or ""
        assert "execution_id" in measurements_comment

    def test_metric_keys_match_real_analysis_shape(self):
        # 判定器自测：指标键集与本文件构造的 analysis payload 键集一致，
        # 防服务端改键后门用旧键喂数据恒 None 假绿
        payload = _analysis_payload(1.0, 2.0, 3.0)
        for key in COMPARISON_METRIC_KEYS:
            assert key in payload, f"指标键 {key} 不在 analysis 形态里"
