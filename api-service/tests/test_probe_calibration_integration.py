"""
探头校准集成测试 (TASK-P10)

测试完整的探头校准流程:
1. 完整校准流程: 幅度 → 相位 → 极化 → 方向图 → 链路
2. 过期处理流程: 创建 → 过期 → 作废 → 重新校准
3. 有效性报告流程
4. 综合数据查询流程

参考: docs/features/calibration/IMPLEMENTATION-PLAN.md
"""
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import Base, get_db
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    ProbePhaseCalibration,
    ProbePolarizationCalibration,
    ProbePattern,
    LinkCalibration,
    CalibrationStatus,
)


# 使用专用的测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_probe_calibration_integration.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """模块级别的数据库设置"""
    # 在 fixture 执行时捕获原始依赖（而不是在模块加载时）
    original_get_db = app.dependency_overrides.get(get_db)

    # 覆盖依赖
    app.dependency_overrides[get_db] = override_get_db

    # 创建所有表
    Base.metadata.create_all(bind=engine)
    yield
    # 测试完成后清理
    Base.metadata.drop_all(bind=engine)

    # 恢复原始依赖
    if original_get_db is not None:
        app.dependency_overrides[get_db] = original_get_db
    elif get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]


# 创建测试客户端
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_tables():
    """每个测试前清理表数据"""
    db = TestingSessionLocal()
    try:
        db.query(ProbeAmplitudeCalibration).delete()
        db.query(ProbePhaseCalibration).delete()
        db.query(ProbePolarizationCalibration).delete()
        db.query(ProbePattern).delete()
        db.query(LinkCalibration).delete()
        db.commit()
    finally:
        db.close()
    yield


# ==================== 完整校准流程测试 ====================

class TestCompleteCalibrationWorkflow:
    """测试完整的探头校准流程"""

    def test_full_calibration_workflow_single_probe(self):
        """
        测试单个探头的完整校准流程

        流程: 幅度校准 → 相位校准 → 极化校准 → 方向图校准 → 链路校准
        """
        probe_id = 5

        # Step 1: 幅度校准
        amp_response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V", "H"],
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Integration Test"
            }
        )
        assert amp_response.status_code == 202
        assert amp_response.json()["status"] == "completed"

        # 验证幅度校准数据
        amp_data = client.get(f"/api/v1/calibration/probe/amplitude/{probe_id}")
        assert amp_data.status_code == 200
        assert amp_data.json()["probe_id"] == probe_id

        # Step 2: 相位校准
        phase_response = client.post(
            "/api/v1/calibration/probe/phase/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "reference_probe_id": 0,
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Integration Test"
            }
        )
        assert phase_response.status_code == 202
        assert phase_response.json()["status"] == "completed"

        # 验证相位校准数据
        phase_data = client.get(f"/api/v1/calibration/probe/phase/{probe_id}")
        assert phase_data.status_code == 200
        assert phase_data.json()["reference_probe_id"] == 0

        # Step 3: 极化校准
        pol_response = client.post(
            "/api/v1/calibration/probe/polarization/start",
            json={
                "probe_ids": [probe_id],
                "probe_type": "dual_linear",
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Integration Test"
            }
        )
        assert pol_response.status_code == 202
        assert pol_response.json()["status"] == "completed"

        # 验证极化校准数据
        pol_data = client.get(f"/api/v1/calibration/probe/polarization/{probe_id}")
        assert pol_data.status_code == 200
        assert pol_data.json()["probe_type"] == "dual_linear"

        # Step 4: 方向图校准
        pattern_response = client.post(
            "/api/v1/calibration/probe/pattern/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "frequency_mhz": 3500,
                "azimuth_step_deg": 30.0,  # 较大步进加快测试
                "elevation_step_deg": 30.0,
                "measurement_distance_m": 3.0,
                "calibrated_by": "Integration Test"
            }
        )
        assert pattern_response.status_code == 202
        assert pattern_response.json()["status"] == "completed"

        # 验证方向图校准数据
        pattern_data = client.get(f"/api/v1/calibration/probe/pattern/{probe_id}")
        assert pattern_data.status_code == 200
        assert len(pattern_data.json()) >= 1

        # Step 5: 链路校准
        link_response = client.post(
            "/api/v1/calibration/probe/link/start",
            json={
                "calibration_type": "pre_test",
                "standard_dut": {
                    "dut_type": "dipole",
                    "model": "Standard Dipole",
                    "serial": "SD-INT-001",
                    "known_gain_dbi": 2.15
                },
                "frequency_mhz": 3500,
                "threshold_db": 1.0,
                "probe_ids": [probe_id],
                "calibrated_by": "Integration Test"
            }
        )
        assert link_response.status_code == 202
        assert link_response.json()["status"] == "completed"

        # 验证链路校准数据
        link_data = client.get("/api/v1/calibration/probe/link/latest")
        assert link_data.status_code == 200
        assert "deviation_db" in link_data.json()

        # Step 6: 验证有效性状态 (所有校准都应该有效)
        validity = client.get(f"/api/v1/calibration/probe/validity/{probe_id}")
        assert validity.status_code == 200
        validity_data = validity.json()

        assert validity_data["amplitude"] is not None
        assert validity_data["amplitude"]["status"] == "valid"
        assert validity_data["phase"] is not None
        assert validity_data["phase"]["status"] == "valid"
        assert validity_data["polarization"] is not None
        assert validity_data["polarization"]["status"] == "valid"
        assert validity_data["pattern"] is not None
        assert validity_data["pattern"]["status"] == "valid"
        assert validity_data["link"] is not None
        # 链路校准可能是 valid 或 expiring_soon (取决于时间差)
        assert validity_data["link"]["status"] in ["valid", "expiring_soon"]

        # Step 7: 获取综合校准数据
        full_data = client.get(f"/api/v1/calibration/probe/{probe_id}/data")
        assert full_data.status_code == 200
        full_data_json = full_data.json()

        assert full_data_json["probe_id"] == probe_id
        assert full_data_json["amplitude_calibration"] is not None
        assert full_data_json["phase_calibration"] is not None
        assert full_data_json["polarization_calibration"] is not None
        assert full_data_json["pattern_calibrations"] is not None
        assert full_data_json["link_calibration"] is not None
        assert full_data_json["validity_status"] is not None

    def test_multi_probe_calibration_workflow(self):
        """
        测试多探头批量校准流程

        同时对 4 个探头执行幅度和相位校准
        """
        probe_ids = [10, 11, 12, 13]

        # 批量幅度校准
        amp_response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": probe_ids,
                "polarizations": ["V"],
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3500,
                    "step_mhz": 100
                },
                "calibrated_by": "Multi-Probe Test"
            }
        )
        assert amp_response.status_code == 202

        # 验证每个探头都有幅度校准数据
        for pid in probe_ids:
            data = client.get(f"/api/v1/calibration/probe/amplitude/{pid}")
            assert data.status_code == 200
            assert data.json()["probe_id"] == pid

        # 批量相位校准
        phase_response = client.post(
            "/api/v1/calibration/probe/phase/start",
            json={
                "probe_ids": probe_ids,
                "polarizations": ["V"],
                "reference_probe_id": 0,
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3500,
                    "step_mhz": 100
                },
                "calibrated_by": "Multi-Probe Test"
            }
        )
        assert phase_response.status_code == 202

        # 验证每个探头都有相位校准数据
        for pid in probe_ids:
            data = client.get(f"/api/v1/calibration/probe/phase/{pid}")
            assert data.status_code == 200
            assert data.json()["probe_id"] == pid

        # 获取批量有效性报告
        report = client.get(
            "/api/v1/calibration/probe/validity/report",
            params={"probe_ids": ",".join(map(str, probe_ids))}
        )
        assert report.status_code == 200
        report_data = report.json()

        assert report_data["total_probes"] == len(probe_ids)


# ==================== 过期处理流程测试 ====================

class TestExpirationWorkflow:
    """测试校准过期处理流程"""

    def test_expiration_detection_and_recalibration(self):
        """
        测试过期检测和重新校准流程

        流程: 创建校准 → 模拟过期 → 检测过期 → 重新校准
        """
        probe_id = 20

        # Step 1: 创建初始校准
        client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "frequency_range": {
                    "start_mhz": 3500,
                    "stop_mhz": 3600,
                    "step_mhz": 100
                },
                "calibrated_by": "Expiration Test"
            }
        )

        # Step 2: 直接在数据库中创建一个过期的校准记录
        db = TestingSessionLocal()
        try:
            expired_cal = ProbeAmplitudeCalibration(
                probe_id=probe_id + 1,  # 使用不同的探头
                polarization="H",
                frequency_points_mhz=[3500],
                tx_gain_dbi=[5.0],
                rx_gain_dbi=[4.9],
                tx_gain_uncertainty_db=[0.3],
                rx_gain_uncertainty_db=[0.3],
                calibrated_at=datetime.utcnow() - timedelta(days=100),
                calibrated_by="Old Calibration",
                valid_until=datetime.utcnow() - timedelta(days=10),
                status=CalibrationStatus.VALID
            )
            db.add(expired_cal)
            db.commit()
            expired_cal_id = str(expired_cal.id)
        finally:
            db.close()

        # Step 3: 检测过期校准
        expired = client.get("/api/v1/calibration/probe/validity/expired")
        assert expired.status_code == 200
        expired_data = expired.json()

        # 应该能找到过期的校准
        assert expired_data["count"] >= 1
        expired_ids = [e["calibration_id"] for e in expired_data["calibrations"]]
        assert expired_cal_id in expired_ids

        # Step 4: 检查该探头的有效性状态
        validity = client.get(f"/api/v1/calibration/probe/validity/{probe_id + 1}")
        assert validity.status_code == 200
        assert validity.json()["amplitude"]["status"] == "expired"
        assert validity.json()["overall_status"] == "expired"

        # Step 5: 重新校准
        recal_response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [probe_id + 1],
                "polarizations": ["H"],
                "frequency_range": {
                    "start_mhz": 3500,
                    "stop_mhz": 3600,
                    "step_mhz": 100
                },
                "calibrated_by": "Recalibration Test"
            }
        )
        assert recal_response.status_code == 202

        # Step 6: 验证新校准已生效
        new_validity = client.get(f"/api/v1/calibration/probe/validity/{probe_id + 1}")
        assert new_validity.status_code == 200
        assert new_validity.json()["amplitude"]["status"] == "valid"

    def test_expiring_soon_detection(self):
        """测试即将过期校准的检测"""
        probe_id = 25

        # 创建一个即将过期的校准 (5 天后过期)
        db = TestingSessionLocal()
        try:
            expiring_cal = ProbeAmplitudeCalibration(
                probe_id=probe_id,
                polarization="V",
                frequency_points_mhz=[3500],
                tx_gain_dbi=[5.0],
                rx_gain_dbi=[4.9],
                tx_gain_uncertainty_db=[0.3],
                rx_gain_uncertainty_db=[0.3],
                calibrated_at=datetime.utcnow() - timedelta(days=85),
                calibrated_by="Expiring Soon Test",
                valid_until=datetime.utcnow() + timedelta(days=5),
                status=CalibrationStatus.VALID
            )
            db.add(expiring_cal)
            db.commit()
        finally:
            db.close()

        # 检测即将过期的校准
        expiring = client.get(
            "/api/v1/calibration/probe/validity/expiring",
            params={"days": 7}
        )
        assert expiring.status_code == 200
        expiring_data = expiring.json()

        # 应该能找到即将过期的校准
        assert expiring_data["count"] >= 1

        # 检查探头有效性状态
        validity = client.get(f"/api/v1/calibration/probe/validity/{probe_id}")
        assert validity.status_code == 200
        assert validity.json()["amplitude"]["status"] == "expiring_soon"
        assert validity.json()["overall_status"] == "expiring_soon"


# ==================== 作废流程测试 ====================

class TestInvalidationWorkflow:
    """测试校准作废流程"""

    def test_invalidation_and_recalibration(self):
        """
        测试作废和重新校准流程

        流程: 创建校准 → 作废 → 验证作废 → 重新校准
        """
        probe_id = 30

        # Step 1: 创建初始校准
        client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "frequency_range": {
                    "start_mhz": 3500,
                    "stop_mhz": 3600,
                    "step_mhz": 100
                },
                "calibrated_by": "Invalidation Test"
            }
        )

        # 获取校准 ID
        amp_data = client.get(f"/api/v1/calibration/probe/amplitude/{probe_id}")
        assert amp_data.status_code == 200
        cal_id = amp_data.json()["id"]

        # Step 2: 作废校准
        invalidate_response = client.post(
            f"/api/v1/calibration/probe/invalidate/amplitude/{cal_id}",
            json={"reason": "Test invalidation - suspected measurement error"}
        )
        assert invalidate_response.status_code == 200
        assert invalidate_response.json()["success"] is True

        # Step 3: 验证作废状态
        validity = client.get(f"/api/v1/calibration/probe/validity/{probe_id}")
        assert validity.status_code == 200

        # 作废后应该没有有效的幅度校准
        assert validity.json()["amplitude"] is None
        assert validity.json()["overall_status"] == "unknown"

        # Step 4: 重新校准
        recal_response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "frequency_range": {
                    "start_mhz": 3500,
                    "stop_mhz": 3600,
                    "step_mhz": 100
                },
                "calibrated_by": "Recalibration After Invalidation"
            }
        )
        assert recal_response.status_code == 202

        # Step 5: 验证新校准
        new_validity = client.get(f"/api/v1/calibration/probe/validity/{probe_id}")
        assert new_validity.status_code == 200
        assert new_validity.json()["amplitude"] is not None
        assert new_validity.json()["amplitude"]["status"] == "valid"


# ==================== 有效性报告流程测试 ====================

class TestValidityReportWorkflow:
    """测试有效性报告生成流程"""

    def test_generate_comprehensive_validity_report(self):
        """测试生成综合有效性报告"""
        # 创建多个探头的不同状态校准
        probe_ids = [40, 41, 42, 43]

        db = TestingSessionLocal()
        try:
            # 探头 40: 完全有效
            db.add(ProbeAmplitudeCalibration(
                probe_id=40,
                polarization="V",
                frequency_points_mhz=[3500],
                tx_gain_dbi=[5.0],
                rx_gain_dbi=[4.9],
                tx_gain_uncertainty_db=[0.3],
                rx_gain_uncertainty_db=[0.3],
                calibrated_at=datetime.utcnow(),
                calibrated_by="Valid",
                valid_until=datetime.utcnow() + timedelta(days=90),
                status=CalibrationStatus.VALID
            ))

            # 探头 41: 即将过期
            db.add(ProbeAmplitudeCalibration(
                probe_id=41,
                polarization="V",
                frequency_points_mhz=[3500],
                tx_gain_dbi=[5.0],
                rx_gain_dbi=[4.9],
                tx_gain_uncertainty_db=[0.3],
                rx_gain_uncertainty_db=[0.3],
                calibrated_at=datetime.utcnow() - timedelta(days=85),
                calibrated_by="Expiring",
                valid_until=datetime.utcnow() + timedelta(days=5),
                status=CalibrationStatus.VALID
            ))

            # 探头 42: 已过期
            db.add(ProbeAmplitudeCalibration(
                probe_id=42,
                polarization="V",
                frequency_points_mhz=[3500],
                tx_gain_dbi=[5.0],
                rx_gain_dbi=[4.9],
                tx_gain_uncertainty_db=[0.3],
                rx_gain_uncertainty_db=[0.3],
                calibrated_at=datetime.utcnow() - timedelta(days=100),
                calibrated_by="Expired",
                valid_until=datetime.utcnow() - timedelta(days=10),
                status=CalibrationStatus.VALID
            ))

            # 探头 43: 无校准数据

            db.commit()
        finally:
            db.close()

        # 生成有效性报告
        report = client.get(
            "/api/v1/calibration/probe/validity/report",
            params={"probe_ids": ",".join(map(str, probe_ids))}
        )
        assert report.status_code == 200
        report_data = report.json()

        # 验证报告内容
        assert report_data["total_probes"] == 4
        assert report_data["valid_probes"] >= 1  # 至少 1 个有效
        assert report_data["expiring_soon_probes"] >= 1  # 至少 1 个即将过期
        assert report_data["expired_probes"] >= 1  # 至少 1 个已过期

        # 验证过期校准列表
        assert "expired_calibrations" in report_data

        # 验证即将过期校准列表
        assert "expiring_soon_calibrations" in report_data

        # 验证建议
        assert "recommendations" in report_data


# ==================== 历史记录流程测试 ====================

class TestHistoryWorkflow:
    """测试校准历史记录流程"""

    def test_calibration_history_tracking(self):
        """测试校准历史跟踪"""
        probe_id = 50

        # 执行多次校准
        for i in range(3):
            response = client.post(
                "/api/v1/calibration/probe/amplitude/start",
                json={
                    "probe_ids": [probe_id],
                    "polarizations": ["V"],
                    "frequency_range": {
                        "start_mhz": 3500,
                        "stop_mhz": 3600,
                        "step_mhz": 100
                    },
                    "calibrated_by": f"History Test #{i + 1}"
                }
            )
            assert response.status_code == 202

        # 查询历史记录
        history = client.get(
            f"/api/v1/calibration/probe/amplitude/{probe_id}/history",
            params={"limit": 10}
        )
        assert history.status_code == 200
        history_data = history.json()

        # 应该有 3 条历史记录
        assert len(history_data["history"]) >= 3

        # 验证历史记录按时间倒序排列
        timestamps = [item["calibrated_at"] for item in history_data["history"]]
        assert timestamps == sorted(timestamps, reverse=True)


# ==================== 综合数据查询流程测试 ====================

class TestComprehensiveDataQuery:
    """测试综合数据查询流程"""

    def test_full_probe_data_query(self):
        """测试获取探头的完整校准数据"""
        probe_id = 55

        # 创建所有类型的校准数据
        # 幅度校准
        client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "frequency_range": {"start_mhz": 3500, "stop_mhz": 3600, "step_mhz": 100},
                "calibrated_by": "Data Query Test"
            }
        )

        # 相位校准
        client.post(
            "/api/v1/calibration/probe/phase/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "reference_probe_id": 0,
                "frequency_range": {"start_mhz": 3500, "stop_mhz": 3600, "step_mhz": 100},
                "calibrated_by": "Data Query Test"
            }
        )

        # 极化校准
        client.post(
            "/api/v1/calibration/probe/polarization/start",
            json={
                "probe_ids": [probe_id],
                "probe_type": "dual_linear",
                "frequency_range": {"start_mhz": 3500, "stop_mhz": 3600, "step_mhz": 100},
                "calibrated_by": "Data Query Test"
            }
        )

        # 方向图校准
        client.post(
            "/api/v1/calibration/probe/pattern/start",
            json={
                "probe_ids": [probe_id],
                "polarizations": ["V"],
                "frequency_mhz": 3500,
                "azimuth_step_deg": 30,  # 最大 30 度
                "elevation_step_deg": 30,  # 最大 30 度
                "calibrated_by": "Data Query Test"
            }
        )

        # 链路校准
        client.post(
            "/api/v1/calibration/probe/link/start",
            json={
                "calibration_type": "pre_test",
                "standard_dut": {
                    "dut_type": "dipole",
                    "model": "Test",
                    "serial": "001",
                    "known_gain_dbi": 2.15
                },
                "frequency_mhz": 3500,
                "calibrated_by": "Data Query Test"
            }
        )

        # 查询综合数据
        full_data = client.get(f"/api/v1/calibration/probe/{probe_id}/data")
        assert full_data.status_code == 200
        data = full_data.json()

        # 验证所有数据都存在
        assert data["probe_id"] == probe_id
        assert data["amplitude_calibration"] is not None
        assert data["amplitude_calibration"]["polarization"] == "V"

        assert data["phase_calibration"] is not None
        assert data["phase_calibration"]["reference_probe_id"] == 0

        assert data["polarization_calibration"] is not None
        assert data["polarization_calibration"]["probe_type"] == "dual_linear"

        assert data["pattern_calibrations"] is not None
        assert len(data["pattern_calibrations"]) >= 1

        assert data["link_calibration"] is not None

        assert data["validity_status"] is not None
        assert data["validity_status"]["probe_id"] == probe_id


# ==================== 边界条件测试 ====================

class TestEdgeCases:
    """测试边界条件"""

    def test_calibration_with_all_probes(self):
        """测试所有探头的有效性报告"""
        # 获取默认的 32 个探头的有效性报告
        report = client.get("/api/v1/calibration/probe/validity/report")
        assert report.status_code == 200
        report_data = report.json()

        assert report_data["total_probes"] == 32
        assert "valid_probes" in report_data
        assert "expired_probes" in report_data
        assert "expiring_soon_probes" in report_data

    def test_invalid_probe_id_handling(self):
        """测试无效探头 ID 处理"""
        # 超出范围的探头 ID
        response = client.get("/api/v1/calibration/probe/amplitude/100")
        assert response.status_code == 400

        response = client.get("/api/v1/calibration/probe/validity/100")
        assert response.status_code == 400

        response = client.get("/api/v1/calibration/probe/100/data")
        assert response.status_code == 400

    def test_nonexistent_calibration_handling(self):
        """测试不存在校准数据的处理"""
        # 使用一个没有任何校准数据的探头
        probe_id = 63

        # 获取有效性状态 (应该返回 unknown)
        validity = client.get(f"/api/v1/calibration/probe/validity/{probe_id}")
        assert validity.status_code == 200
        assert validity.json()["overall_status"] == "unknown"

        # 获取综合数据 (应该返回空数据)
        full_data = client.get(f"/api/v1/calibration/probe/{probe_id}/data")
        assert full_data.status_code == 200
        data = full_data.json()
        assert data["probe_id"] == probe_id
        assert data["amplitude_calibration"] is None
        assert data["phase_calibration"] is None
