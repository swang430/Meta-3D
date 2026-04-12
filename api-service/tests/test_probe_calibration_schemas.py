"""
Probe Calibration Schemas Tests

TASK-P02 验收测试：
1. 请求参数验证测试
2. 响应序列化测试
3. 频率范围验证测试
4. 枚举值测试

参考: docs/features/calibration/IMPLEMENTATION-PLAN.md
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from pydantic import ValidationError

from app.schemas.probe_calibration import (
    # Enums
    PolarizationType,
    ProbeTypeEnum,
    CalibrationStatusEnum,
    LinkCalibrationTypeEnum,
    CalibrationJobStatus,
    # Common
    FrequencyRange,
    CalibrationJobResponse,
    CalibrationProgress,
    # Amplitude
    StartAmplitudeCalibrationRequest,
    AmplitudeCalibrationResponse,
    # Phase
    StartPhaseCalibrationRequest,
    PhaseCalibrationResponse,
    # Polarization
    StartPolarizationCalibrationRequest,
    PolarizationCalibrationResponse,
    # Pattern
    StartPatternCalibrationRequest,
    PatternCalibrationResponse,
    # Link
    StartLinkCalibrationRequest,
    LinkCalibrationResponse,
    StandardDUT,
    ProbeLinkCalibration,
    # Validity
    ProbeCalibrationStatus,
    CalibrationValidityReport,
    ExpiringCalibration,
    InvalidateCalibrationRequest,
    # History
    CalibrationHistoryQuery,
    CalibrationHistoryResponse,
    CalibrationHistoryItem,
    # Data Query
    ProbeCalibrationDataResponse,
)


# ===== Enum Tests =====

class TestEnums:
    """枚举类型测试"""

    def test_polarization_type_values(self):
        """验证极化类型枚举值"""
        assert PolarizationType.V.value == "V"
        assert PolarizationType.H.value == "H"
        assert PolarizationType.LHCP.value == "LHCP"
        assert PolarizationType.RHCP.value == "RHCP"

    def test_probe_type_enum_values(self):
        """验证探头类型枚举值"""
        assert ProbeTypeEnum.DUAL_LINEAR.value == "dual_linear"
        assert ProbeTypeEnum.DUAL_SLANT.value == "dual_slant"
        assert ProbeTypeEnum.CIRCULAR.value == "circular"

    def test_calibration_status_enum_values(self):
        """验证校准状态枚举值"""
        assert CalibrationStatusEnum.VALID.value == "valid"
        assert CalibrationStatusEnum.EXPIRED.value == "expired"
        assert CalibrationStatusEnum.INVALIDATED.value == "invalidated"
        assert CalibrationStatusEnum.PENDING.value == "pending"

    def test_link_calibration_type_enum_values(self):
        """验证链路校准类型枚举值"""
        assert LinkCalibrationTypeEnum.WEEKLY_CHECK.value == "weekly_check"
        assert LinkCalibrationTypeEnum.PRE_TEST.value == "pre_test"
        assert LinkCalibrationTypeEnum.POST_MAINTENANCE.value == "post_maintenance"

    def test_calibration_job_status_values(self):
        """验证校准任务状态枚举值"""
        assert CalibrationJobStatus.QUEUED.value == "queued"
        assert CalibrationJobStatus.RUNNING.value == "running"
        assert CalibrationJobStatus.COMPLETED.value == "completed"
        assert CalibrationJobStatus.FAILED.value == "failed"


# ===== Frequency Range Tests =====

class TestFrequencyRange:
    """频率范围验证测试"""

    def test_valid_frequency_range(self):
        """验证有效的频率范围"""
        freq_range = FrequencyRange(
            start_mhz=3300,
            stop_mhz=3800,
            step_mhz=100
        )
        assert freq_range.start_mhz == 3300
        assert freq_range.stop_mhz == 3800
        assert freq_range.step_mhz == 100

    def test_frequency_range_stop_must_be_greater_than_start(self):
        """验证 stop_mhz 必须大于 start_mhz"""
        with pytest.raises(ValidationError) as exc_info:
            FrequencyRange(
                start_mhz=3800,
                stop_mhz=3300,  # 小于 start
                step_mhz=100
            )
        assert "stop_mhz must be greater than start_mhz" in str(exc_info.value)

    def test_frequency_range_boundaries(self):
        """验证频率范围边界"""
        # 最小值
        with pytest.raises(ValidationError):
            FrequencyRange(start_mhz=50, stop_mhz=100, step_mhz=10)  # start < 100

        # 最大值
        with pytest.raises(ValidationError):
            FrequencyRange(start_mhz=100000, stop_mhz=150000, step_mhz=100)  # > 100000


# ===== Amplitude Calibration Request Tests =====

class TestAmplitudeCalibrationRequest:
    """幅度校准请求测试"""

    def test_valid_amplitude_request(self):
        """验证有效的幅度校准请求"""
        request = StartAmplitudeCalibrationRequest(
            probe_ids=[1, 2, 3],
            polarizations=[PolarizationType.V, PolarizationType.H],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
            calibrated_by="Test User"
        )
        assert request.probe_ids == [1, 2, 3]
        assert len(request.polarizations) == 2

    def test_amplitude_request_empty_probe_list(self):
        """验证空探头列表被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            StartAmplitudeCalibrationRequest(
                probe_ids=[],  # 空列表
                frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
                calibrated_by="Test User"
            )
        # pydantic v2 的错误消息格式
        assert "probe_ids" in str(exc_info.value)

    def test_amplitude_request_invalid_probe_id(self):
        """验证无效探头 ID 被拒绝"""
        with pytest.raises(ValidationError) as exc_info:
            StartAmplitudeCalibrationRequest(
                probe_ids=[1, 2, 100],  # 100 超出范围
                frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
                calibrated_by="Test User"
            )
        assert "probe_id must be between 0 and 63" in str(exc_info.value)

    def test_amplitude_request_default_polarizations(self):
        """验证默认极化类型"""
        request = StartAmplitudeCalibrationRequest(
            probe_ids=[1],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
            calibrated_by="Test User"
        )
        # 默认应该是 V 和 H
        assert PolarizationType.V in request.polarizations
        assert PolarizationType.H in request.polarizations


# ===== Phase Calibration Request Tests =====

class TestPhaseCalibrationRequest:
    """相位校准请求测试"""

    def test_valid_phase_request(self):
        """验证有效的相位校准请求"""
        request = StartPhaseCalibrationRequest(
            probe_ids=[1, 2, 3],
            reference_probe_id=0,
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
            calibrated_by="Test User"
        )
        assert request.reference_probe_id == 0

    def test_phase_request_default_reference_probe(self):
        """验证默认参考探头为 0"""
        request = StartPhaseCalibrationRequest(
            probe_ids=[1, 2, 3],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
            calibrated_by="Test User"
        )
        assert request.reference_probe_id == 0


# ===== Polarization Calibration Request Tests =====

class TestPolarizationCalibrationRequest:
    """极化校准请求测试"""

    def test_valid_polarization_request_linear(self):
        """验证线极化校准请求"""
        request = StartPolarizationCalibrationRequest(
            probe_ids=[1, 2],
            probe_type=ProbeTypeEnum.DUAL_LINEAR,
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
            calibrated_by="Test User"
        )
        assert request.probe_type == ProbeTypeEnum.DUAL_LINEAR

    def test_valid_polarization_request_circular(self):
        """验证圆极化校准请求"""
        request = StartPolarizationCalibrationRequest(
            probe_ids=[1],
            probe_type=ProbeTypeEnum.CIRCULAR,
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3800, step_mhz=100),
            calibrated_by="Test User"
        )
        assert request.probe_type == ProbeTypeEnum.CIRCULAR


# ===== Pattern Calibration Request Tests =====

class TestPatternCalibrationRequest:
    """方向图校准请求测试"""

    def test_valid_pattern_request(self):
        """验证有效的方向图校准请求"""
        request = StartPatternCalibrationRequest(
            probe_ids=[1],
            frequency_mhz=3500,
            azimuth_step_deg=5.0,
            elevation_step_deg=5.0,
            measurement_distance_m=3.0,
            calibrated_by="Test User"
        )
        assert request.frequency_mhz == 3500
        assert request.azimuth_step_deg == 5.0

    def test_pattern_request_step_boundaries(self):
        """验证步进角度边界"""
        # 太小
        with pytest.raises(ValidationError):
            StartPatternCalibrationRequest(
                probe_ids=[1],
                frequency_mhz=3500,
                azimuth_step_deg=0.5,  # < 1
                calibrated_by="Test User"
            )

        # 太大
        with pytest.raises(ValidationError):
            StartPatternCalibrationRequest(
                probe_ids=[1],
                frequency_mhz=3500,
                azimuth_step_deg=45,  # > 30
                calibrated_by="Test User"
            )


# ===== Link Calibration Request Tests =====

class TestLinkCalibrationRequest:
    """链路校准请求测试"""

    def test_valid_link_request(self):
        """验证有效的链路校准请求"""
        request = StartLinkCalibrationRequest(
            calibration_type=LinkCalibrationTypeEnum.PRE_TEST,
            standard_dut=StandardDUT(
                dut_type="dipole",
                model="Standard Dipole",
                serial="SD-001",
                known_gain_dbi=2.15
            ),
            frequency_mhz=3500,
            threshold_db=1.0,
            calibrated_by="Test User"
        )
        assert request.calibration_type == LinkCalibrationTypeEnum.PRE_TEST
        assert request.standard_dut.known_gain_dbi == 2.15

    def test_standard_dut_types(self):
        """验证标准 DUT 类型"""
        for dut_type in ["dipole", "horn", "patch"]:
            dut = StandardDUT(
                dut_type=dut_type,
                model="Test",
                serial="001",
                known_gain_dbi=5.0
            )
            assert dut.dut_type == dut_type

    def test_invalid_dut_type(self):
        """验证无效 DUT 类型被拒绝"""
        with pytest.raises(ValidationError):
            StandardDUT(
                dut_type="invalid",
                model="Test",
                serial="001",
                known_gain_dbi=5.0
            )


# ===== Response Serialization Tests =====

class TestResponseSerialization:
    """响应序列化测试"""

    def test_amplitude_response_serialization(self):
        """验证幅度校准响应序列化"""
        response = AmplitudeCalibrationResponse(
            id=uuid4(),
            probe_id=1,
            polarization="V",
            frequency_points_mhz=[3300, 3400, 3500],
            tx_gain_dbi=[5.0, 5.1, 5.2],
            rx_gain_dbi=[4.9, 5.0, 5.1],
            tx_gain_uncertainty_db=[0.3, 0.3, 0.3],
            rx_gain_uncertainty_db=[0.3, 0.3, 0.3],
            calibrated_at=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=90),
            status="valid"
        )
        # 转换为字典验证
        data = response.model_dump()
        assert data["probe_id"] == 1
        assert len(data["frequency_points_mhz"]) == 3

    def test_phase_response_serialization(self):
        """验证相位校准响应序列化"""
        response = PhaseCalibrationResponse(
            id=uuid4(),
            probe_id=1,
            polarization="V",
            reference_probe_id=0,
            frequency_points_mhz=[3300, 3400],
            phase_offset_deg=[12.5, 13.0],
            group_delay_ns=[0.5, 0.52],
            phase_uncertainty_deg=[1.0, 1.0],
            calibrated_at=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=90),
            status="valid"
        )
        data = response.model_dump()
        assert data["reference_probe_id"] == 0

    def test_calibration_job_response(self):
        """验证校准任务响应"""
        response = CalibrationJobResponse(
            calibration_job_id=uuid4(),
            status=CalibrationJobStatus.QUEUED,
            estimated_duration_minutes=15.0,
            message="Calibration job queued successfully"
        )
        assert response.status == CalibrationJobStatus.QUEUED


# ===== Validity Report Tests =====

class TestValidityReport:
    """有效性报告测试"""

    def test_validity_report_creation(self):
        """验证有效性报告创建"""
        report = CalibrationValidityReport(
            total_probes=32,
            valid_probes=28,
            expired_probes=2,
            expiring_soon_probes=2,
            expired_calibrations=[
                {"probe_id": 5, "calibration_type": "amplitude", "days_overdue": 3}
            ],
            expiring_soon_calibrations=[
                {"probe_id": 10, "calibration_type": "phase", "days_remaining": 5}
            ],
            recommendations=[
                {"probe_id": 5, "calibration_type": "amplitude", "action": "recalibrate_now", "priority": "critical"}
            ]
        )
        assert report.total_probes == 32
        assert report.valid_probes == 28
        assert len(report.expired_calibrations) == 1

    def test_expiring_calibration(self):
        """验证即将过期校准"""
        expiring = ExpiringCalibration(
            probe_id=10,
            calibration_type="phase",
            valid_until=datetime.utcnow() + timedelta(days=5),
            days_remaining=5
        )
        assert expiring.days_remaining == 5


# ===== Invalidate Request Tests =====

class TestInvalidateRequest:
    """作废请求测试"""

    def test_valid_invalidate_request(self):
        """验证有效的作废请求"""
        request = InvalidateCalibrationRequest(
            reason="Equipment damage detected during routine inspection"
        )
        assert len(request.reason) > 5

    def test_invalidate_request_reason_too_short(self):
        """验证原因过短被拒绝"""
        with pytest.raises(ValidationError):
            InvalidateCalibrationRequest(reason="bad")  # < 5 字符


# ===== History Query Tests =====

class TestHistoryQuery:
    """历史查询测试"""

    def test_valid_history_query(self):
        """验证有效的历史查询"""
        query = CalibrationHistoryQuery(
            probe_id=1,
            calibration_type="amplitude",
            limit=50
        )
        assert query.probe_id == 1
        assert query.limit == 50

    def test_history_query_default_limit(self):
        """验证默认查询限制"""
        query = CalibrationHistoryQuery(probe_id=1)
        assert query.limit == 20

    def test_history_query_limit_boundaries(self):
        """验证查询限制边界"""
        with pytest.raises(ValidationError):
            CalibrationHistoryQuery(probe_id=1, limit=200)  # > 100


# ===== Probe Calibration Status Tests =====

class TestProbeCalibrationStatus:
    """探头校准状态测试"""

    def test_probe_calibration_status(self):
        """验证探头校准状态"""
        status = ProbeCalibrationStatus(
            probe_id=1,
            amplitude={
                "status": "valid",
                "valid_until": datetime.utcnow() + timedelta(days=60),
                "calibration_id": str(uuid4())
            },
            phase={
                "status": "expiring_soon",
                "valid_until": datetime.utcnow() + timedelta(days=5),
            },
            overall_status="expiring_soon"
        )
        assert status.probe_id == 1
        assert status.overall_status == "expiring_soon"
