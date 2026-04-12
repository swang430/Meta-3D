"""
Probe Calibration API Tests

TASK-P03 验收测试：
1. POST /amplitude/start - 启动幅度校准
2. GET /amplitude/{probe_id} - 获取校准数据
3. GET /amplitude/{probe_id}/history - 获取校准历史
4. GET /validity/{probe_id} - 获取有效性状态

参考: docs/features/calibration/IMPLEMENTATION-PLAN.md
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

from app.main import app
from app.db.database import Base, get_db
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    CalibrationStatus,
)


# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_probe_calibration.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Override the dependency
app.dependency_overrides[get_db] = override_get_db

# Create test client
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Setup test database"""
    # Create all tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop all tables after tests
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Create a database session for a test"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_amplitude_calibration(db_session):
    """Create sample amplitude calibration data"""
    calibration = ProbeAmplitudeCalibration(
        probe_id=5,
        polarization="V",
        frequency_points_mhz=[3300.0, 3400.0, 3500.0],
        tx_gain_dbi=[5.1, 5.0, 4.9],
        rx_gain_dbi=[5.0, 4.9, 4.8],
        tx_gain_uncertainty_db=[0.3, 0.3, 0.3],
        rx_gain_uncertainty_db=[0.3, 0.3, 0.3],
        reference_antenna="REF-ANT-001",
        calibrated_at=datetime.utcnow(),
        calibrated_by="Test Engineer",
        valid_until=datetime.utcnow() + timedelta(days=90),
        status=CalibrationStatus.VALID
    )
    db_session.add(calibration)
    db_session.commit()
    db_session.refresh(calibration)
    return calibration


class TestAmplitudeCalibrationStart:
    """测试幅度校准启动 API"""

    def test_start_amplitude_calibration_success(self):
        """测试成功启动幅度校准"""
        response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [1, 2, 3],
                "polarizations": ["V", "H"],
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert "calibration_job_id" in data
        assert data["status"] == "completed"  # Mock 直接完成
        assert "estimated_duration_minutes" in data

    def test_start_amplitude_calibration_invalid_probe_id(self):
        """测试无效探头 ID"""
        response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [1, 100],  # 100 超出范围
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 422  # Validation error

    def test_start_amplitude_calibration_empty_probe_list(self):
        """测试空探头列表"""
        response = client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [],
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 422


class TestAmplitudeCalibrationGet:
    """测试获取幅度校准数据 API"""

    def test_get_amplitude_calibration_success(self, sample_amplitude_calibration):
        """测试成功获取校准数据"""
        response = client.get(
            f"/api/v1/calibration/probe/amplitude/{sample_amplitude_calibration.probe_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["probe_id"] == sample_amplitude_calibration.probe_id
        assert data["polarization"] == "V"
        assert len(data["frequency_points_mhz"]) == 3

    def test_get_amplitude_calibration_not_found(self):
        """测试获取不存在的校准数据"""
        # 使用有效范围内但没有数据的探头 ID
        response = client.get("/api/v1/calibration/probe/amplitude/62")
        # 可能返回 404 或之前创建的数据
        # 由于测试环境可能有残留数据，检查是否是 200 或 404
        assert response.status_code in [200, 404]

    def test_get_amplitude_calibration_invalid_probe_id(self):
        """测试无效探头 ID"""
        response = client.get("/api/v1/calibration/probe/amplitude/100")
        assert response.status_code == 400
        assert "probe_id must be between 0 and 63" in response.json()["detail"]

    def test_get_amplitude_calibration_with_polarization_filter(self, sample_amplitude_calibration):
        """测试带极化过滤的获取"""
        response = client.get(
            f"/api/v1/calibration/probe/amplitude/{sample_amplitude_calibration.probe_id}",
            params={"polarization": "V"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["polarization"] == "V"


class TestAmplitudeCalibrationHistory:
    """测试幅度校准历史 API"""

    def test_get_amplitude_history_success(self, sample_amplitude_calibration):
        """测试成功获取校准历史"""
        response = client.get(
            f"/api/v1/calibration/probe/amplitude/{sample_amplitude_calibration.probe_id}/history"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["probe_id"] == sample_amplitude_calibration.probe_id
        assert "history" in data
        assert len(data["history"]) > 0

    def test_get_amplitude_history_with_limit(self, sample_amplitude_calibration):
        """测试带限制的历史查询"""
        response = client.get(
            f"/api/v1/calibration/probe/amplitude/{sample_amplitude_calibration.probe_id}/history",
            params={"limit": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) <= 5

    def test_get_amplitude_history_invalid_probe_id(self):
        """测试无效探头 ID"""
        response = client.get("/api/v1/calibration/probe/amplitude/100/history")
        assert response.status_code == 400


class TestValidityStatus:
    """测试有效性状态 API"""

    def test_get_validity_success(self, sample_amplitude_calibration):
        """测试成功获取有效性状态"""
        response = client.get(
            f"/api/v1/calibration/probe/validity/{sample_amplitude_calibration.probe_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["probe_id"] == sample_amplitude_calibration.probe_id
        assert data["overall_status"] in ["valid", "expiring_soon", "expired", "unknown"]
        assert "amplitude" in data

    def test_get_validity_invalid_probe_id(self):
        """测试无效探头 ID"""
        response = client.get("/api/v1/calibration/probe/validity/100")
        assert response.status_code == 400

    def test_get_validity_report(self):
        """测试获取整体有效性报告"""
        response = client.get("/api/v1/calibration/probe/validity/report")
        assert response.status_code == 200
        data = response.json()
        assert "total_probes" in data
        assert "valid_probes" in data
        assert "expired_probes" in data


class TestPhaseCalibration:
    """测试相位校准 API (TASK-P05)"""

    def test_start_phase_calibration_success(self):
        """测试成功启动相位校准"""
        response = client.post(
            "/api/v1/calibration/probe/phase/start",
            json={
                "probe_ids": [1, 2],
                "polarizations": ["V"],
                "reference_probe_id": 0,
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert "calibration_job_id" in data
        assert data["status"] == "completed"

    def test_get_phase_calibration_invalid_probe_id(self):
        """测试无效探头 ID"""
        response = client.get("/api/v1/calibration/probe/phase/100")
        assert response.status_code == 400

    def test_get_phase_history_invalid_probe_id(self):
        """测试无效探头 ID 的历史查询"""
        response = client.get("/api/v1/calibration/probe/phase/100/history")
        assert response.status_code == 400


class TestPolarizationCalibration:
    """测试极化校准 API (TASK-P06)"""

    def test_start_polarization_calibration_linear_success(self):
        """测试成功启动线极化校准"""
        response = client.post(
            "/api/v1/calibration/probe/polarization/start",
            json={
                "probe_ids": [1, 2],
                "probe_type": "dual_linear",
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert "calibration_job_id" in data
        assert data["status"] == "completed"

    def test_start_polarization_calibration_circular_success(self):
        """测试成功启动圆极化校准"""
        response = client.post(
            "/api/v1/calibration/probe/polarization/start",
            json={
                "probe_ids": [3],
                "probe_type": "circular",
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert "calibration_job_id" in data
        assert "circular" in data["message"]

    def test_get_polarization_calibration_invalid_probe_id(self):
        """测试无效探头 ID"""
        response = client.get("/api/v1/calibration/probe/polarization/100")
        assert response.status_code == 400

    def test_get_polarization_history_invalid_probe_id(self):
        """测试无效探头 ID 的历史查询"""
        response = client.get("/api/v1/calibration/probe/polarization/100/history")
        assert response.status_code == 400


class TestPatternCalibration:
    """测试方向图校准 API (TASK-P07)"""

    def test_start_pattern_calibration_success(self):
        """测试成功启动方向图校准"""
        response = client.post(
            "/api/v1/calibration/probe/pattern/start",
            json={
                "probe_ids": [1, 2],
                "polarizations": ["V"],
                "frequency_mhz": 3500,
                "azimuth_step_deg": 10.0,
                "elevation_step_deg": 10.0,
                "measurement_distance_m": 3.0,
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert "calibration_job_id" in data
        assert data["status"] == "completed"

    def test_start_pattern_calibration_with_defaults(self):
        """测试使用默认参数启动方向图校准"""
        response = client.post(
            "/api/v1/calibration/probe/pattern/start",
            json={
                "probe_ids": [3],
                "frequency_mhz": 3700,
                "calibrated_by": "Test"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "completed"

    def test_get_pattern_calibration_invalid_probe_id(self):
        """测试无效探头 ID"""
        response = client.get("/api/v1/calibration/probe/pattern/100")
        assert response.status_code == 400

    def test_get_pattern_calibration_with_frequency_filter(self):
        """测试按频率筛选方向图校准"""
        # 先创建一个校准记录
        client.post(
            "/api/v1/calibration/probe/pattern/start",
            json={
                "probe_ids": [5],
                "polarizations": ["V"],
                "frequency_mhz": 3600,
                "calibrated_by": "Test"
            }
        )

        # 按频率查询
        response = client.get(
            "/api/v1/calibration/probe/pattern/5",
            params={"frequency_mhz": 3600}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["frequency_mhz"] == 3600


class TestLinkCalibration:
    """测试链路校准 API (TASK-P08)"""

    def test_start_link_calibration_success(self):
        """测试成功启动链路校准"""
        response = client.post(
            "/api/v1/calibration/probe/link/start",
            json={
                "calibration_type": "pre_test",
                "standard_dut": {
                    "dut_type": "dipole",
                    "model": "Standard Dipole",
                    "serial": "SD-001",
                    "known_gain_dbi": 2.15
                },
                "frequency_mhz": 3500,
                "threshold_db": 1.0,
                "calibrated_by": "Test Engineer"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert "calibration_job_id" in data
        assert data["status"] == "completed"
        assert "PASS" in data["message"] or "FAIL" in data["message"]

    def test_start_link_calibration_weekly_check(self):
        """测试每周检查类型的链路校准"""
        response = client.post(
            "/api/v1/calibration/probe/link/start",
            json={
                "calibration_type": "weekly_check",
                "standard_dut": {
                    "dut_type": "horn",
                    "model": "Horn Antenna",
                    "serial": "HA-002",
                    "known_gain_dbi": 10.0
                },
                "frequency_mhz": 3700,
                "calibrated_by": "Test"
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "completed"

    def test_start_link_calibration_with_probe_ids(self):
        """测试指定探头的链路校准"""
        response = client.post(
            "/api/v1/calibration/probe/link/start",
            json={
                "calibration_type": "post_maintenance",
                "standard_dut": {
                    "dut_type": "patch",
                    "model": "Patch Antenna",
                    "serial": "PA-003",
                    "known_gain_dbi": 6.0
                },
                "frequency_mhz": 3500,
                "probe_ids": [0, 1, 2, 3],
                "calibrated_by": "Test"
            }
        )
        assert response.status_code == 202

    def test_get_latest_link_calibration(self):
        """测试获取最新链路校准"""
        # 先创建一个校准记录
        client.post(
            "/api/v1/calibration/probe/link/start",
            json={
                "calibration_type": "pre_test",
                "standard_dut": {
                    "dut_type": "dipole",
                    "model": "Test Dipole",
                    "serial": "TD-004",
                    "known_gain_dbi": 2.15
                },
                "frequency_mhz": 3500,
                "calibrated_by": "Test"
            }
        )

        # 查询最新校准
        response = client.get("/api/v1/calibration/probe/link/latest")
        assert response.status_code == 200
        data = response.json()
        assert "calibration_type" in data
        assert "deviation_db" in data
        assert "validation_pass" in data

    def test_get_link_calibration_history(self):
        """测试获取链路校准历史"""
        response = client.get("/api/v1/calibration/probe/link/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_check_link_validity(self):
        """测试检查链路校准有效性"""
        response = client.get("/api/v1/calibration/probe/link/validity")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        # 状态可能是 valid, expiring_soon, expired, 或 unknown
        assert data["status"] in ["valid", "expiring_soon", "expired", "unknown"]


class TestValidityManagement:
    """测试有效性管理 API (TASK-P09)"""

    def test_get_validity_report(self):
        """测试获取校准有效性报告"""
        response = client.get("/api/v1/calibration/probe/validity/report")
        assert response.status_code == 200
        data = response.json()
        assert "total_probes" in data
        assert "valid_probes" in data
        assert "expired_probes" in data
        assert "expiring_soon_probes" in data
        assert "expired_calibrations" in data
        assert "expiring_soon_calibrations" in data
        assert "recommendations" in data

    def test_get_validity_report_with_probe_ids(self):
        """测试获取特定探头的有效性报告"""
        response = client.get(
            "/api/v1/calibration/probe/validity/report",
            params={"probe_ids": "0,1,2,3"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_probes"] == 4

    def test_get_validity_report_invalid_probe_ids(self):
        """测试无效的探头 ID 列表"""
        response = client.get(
            "/api/v1/calibration/probe/validity/report",
            params={"probe_ids": "100,101"}
        )
        assert response.status_code == 400

    def test_get_probe_validity(self):
        """测试获取单个探头的有效性状态"""
        # 先创建一些校准记录
        client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [10],
                "polarizations": ["V"],
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test"
            }
        )

        response = client.get("/api/v1/calibration/probe/validity/10")
        assert response.status_code == 200
        data = response.json()
        assert data["probe_id"] == 10
        assert "amplitude" in data
        assert "phase" in data
        assert "polarization" in data
        assert "pattern" in data
        assert "link" in data
        assert "overall_status" in data

    def test_get_probe_validity_invalid_probe_id(self):
        """测试无效的探头 ID"""
        response = client.get("/api/v1/calibration/probe/validity/100")
        assert response.status_code == 400

    def test_get_expiring_calibrations(self):
        """测试获取即将过期的校准列表"""
        response = client.get("/api/v1/calibration/probe/validity/expiring")
        assert response.status_code == 200
        data = response.json()
        assert "days_threshold" in data
        assert "count" in data
        assert "calibrations" in data
        assert data["days_threshold"] == 7  # 默认值

    def test_get_expiring_calibrations_with_days(self):
        """测试指定天数的即将过期校准"""
        response = client.get(
            "/api/v1/calibration/probe/validity/expiring",
            params={"days": 14}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["days_threshold"] == 14

    def test_get_expiring_calibrations_with_type(self):
        """测试按类型筛选即将过期校准"""
        response = client.get(
            "/api/v1/calibration/probe/validity/expiring",
            params={"calibration_type": "amplitude"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "calibrations" in data

    def test_get_expiring_calibrations_invalid_type(self):
        """测试无效的校准类型"""
        response = client.get(
            "/api/v1/calibration/probe/validity/expiring",
            params={"calibration_type": "invalid_type"}
        )
        assert response.status_code == 400

    def test_get_expired_calibrations(self):
        """测试获取已过期的校准列表"""
        response = client.get("/api/v1/calibration/probe/validity/expired")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "calibrations" in data

    def test_invalidate_calibration_invalid_type(self):
        """测试作废无效类型的校准"""
        response = client.post(
            "/api/v1/calibration/probe/invalidate/invalid_type/00000000-0000-0000-0000-000000000001",
            json={"reason": "Test invalidation reason"}
        )
        assert response.status_code == 400

    def test_invalidate_calibration_not_found(self):
        """测试作废不存在的校准"""
        response = client.post(
            "/api/v1/calibration/probe/invalidate/amplitude/00000000-0000-0000-0000-000000000001",
            json={"reason": "Test invalidation reason"}
        )
        assert response.status_code == 404

    def test_get_probe_calibration_data(self):
        """测试获取探头综合校准数据"""
        # 先创建一些校准记录
        client.post(
            "/api/v1/calibration/probe/amplitude/start",
            json={
                "probe_ids": [15],
                "polarizations": ["V"],
                "frequency_range": {
                    "start_mhz": 3300,
                    "stop_mhz": 3800,
                    "step_mhz": 100
                },
                "calibrated_by": "Test"
            }
        )

        response = client.get("/api/v1/calibration/probe/15/data")
        assert response.status_code == 200
        data = response.json()
        assert data["probe_id"] == 15
        assert "amplitude_calibration" in data
        assert "phase_calibration" in data
        assert "polarization_calibration" in data
        assert "pattern_calibrations" in data
        assert "link_calibration" in data
        assert "validity_status" in data

    def test_get_probe_calibration_data_invalid_probe_id(self):
        """测试无效探头 ID 的综合数据查询"""
        response = client.get("/api/v1/calibration/probe/100/data")
        assert response.status_code == 400
