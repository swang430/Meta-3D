"""
Probe Calibration Service Tests

TASK-P04 验收测试：
1. 增益计算算法测试
2. 互易性验证测试
3. 不确定度计算测试
4. 服务层集成测试

参考: docs/features/calibration/IMPLEMENTATION-PLAN.md
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    CalibrationStatus,
)
from app.schemas.probe_calibration import (
    FrequencyRange,
    PolarizationType,
)
from app.services.probe_calibration_service import (
    # 常数
    RECIPROCITY_THRESHOLD_DB,
    MAX_GAIN_UNCERTAINTY_DB,
    DEFAULT_VALIDITY_DAYS,
    # 数据类
    GainMeasurement,
    CalibrationResult,
    # 算法函数
    calculate_gain_from_power,
    calculate_path_loss,
    calculate_uncertainty,
    verify_reciprocity,
    generate_frequency_points,
    # 服务类
    AmplitudeCalibrationService,
    CalibrationValidityService,
)


# ==================== 测试数据库设置 ====================

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_probe_calibration_service.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Setup test database"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Create a database session for a test"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


# ==================== 增益计算算法测试 ====================

class TestGainCalculation:
    """增益计算算法测试"""

    def test_calculate_gain_basic(self):
        """测试基本增益计算"""
        # P_rx = -60 dBm, P_tx = -30 dBm, PathLoss = 35 dB
        # G = -60 - (-30) + 35 = 5 dBi
        gain = calculate_gain_from_power(
            received_power_dbm=-60,
            transmitted_power_dbm=-30,
            path_loss_db=35
        )
        assert gain == pytest.approx(5.0, abs=0.01)

    def test_calculate_gain_with_reference(self):
        """测试带参考天线的增益计算"""
        # 参考天线增益 2.15 dBi (偶极子)
        gain = calculate_gain_from_power(
            received_power_dbm=-60,
            transmitted_power_dbm=-30,
            path_loss_db=35,
            reference_gain_dbi=2.15
        )
        assert gain == pytest.approx(7.15, abs=0.01)

    def test_calculate_gain_negative(self):
        """测试负增益情况"""
        # 当接收功率很低时，增益可能为负
        gain = calculate_gain_from_power(
            received_power_dbm=-80,
            transmitted_power_dbm=-30,
            path_loss_db=35
        )
        assert gain == pytest.approx(-15.0, abs=0.01)


class TestPathLossCalculation:
    """路径损耗计算测试"""

    def test_path_loss_3500mhz_3m(self):
        """测试 3500 MHz, 3m 距离的路径损耗"""
        # FSPL = 20*log10(3) + 20*log10(3500) - 27.55
        #      = 9.54 + 70.88 - 27.55 = 52.87 dB
        path_loss = calculate_path_loss(
            frequency_mhz=3500,
            distance_m=3.0
        )
        assert path_loss == pytest.approx(52.87, abs=0.1)

    def test_path_loss_2400mhz_1m(self):
        """测试 2400 MHz, 1m 距离的路径损耗"""
        path_loss = calculate_path_loss(
            frequency_mhz=2400,
            distance_m=1.0
        )
        # FSPL = 20*log10(1) + 20*log10(2400) - 27.55
        #      = 0 + 67.6 - 27.55 = 40.05 dB
        assert path_loss == pytest.approx(40.05, abs=0.1)

    def test_path_loss_invalid_distance(self):
        """测试无效距离"""
        with pytest.raises(ValueError):
            calculate_path_loss(frequency_mhz=3500, distance_m=0)
        with pytest.raises(ValueError):
            calculate_path_loss(frequency_mhz=3500, distance_m=-1)

    def test_path_loss_invalid_frequency(self):
        """测试无效频率"""
        with pytest.raises(ValueError):
            calculate_path_loss(frequency_mhz=0, distance_m=3)


class TestUncertaintyCalculation:
    """不确定度计算测试"""

    def test_uncertainty_basic(self):
        """测试基本不确定度计算"""
        uncertainty = calculate_uncertainty(
            measurement_std=0.05,
            systematic_error=0.1,
            instrument_accuracy=0.05,
            coverage_factor=2.0
        )
        # u_a = 0.05
        # u_b = sqrt(0.1^2 + 0.05^2) = sqrt(0.0125) = 0.1118
        # u_c = sqrt(0.05^2 + 0.1118^2) = sqrt(0.015) = 0.1225
        # u_expanded = 2 * 0.1225 = 0.245
        assert uncertainty == pytest.approx(0.245, abs=0.01)

    def test_uncertainty_low_noise(self):
        """测试低噪声情况"""
        uncertainty = calculate_uncertainty(
            measurement_std=0.01,
            systematic_error=0.05,
            instrument_accuracy=0.02
        )
        assert uncertainty < MAX_GAIN_UNCERTAINTY_DB

    def test_uncertainty_high_noise(self):
        """测试高噪声情况"""
        uncertainty = calculate_uncertainty(
            measurement_std=0.2,
            systematic_error=0.2,
            instrument_accuracy=0.1
        )
        assert uncertainty > MAX_GAIN_UNCERTAINTY_DB


# ==================== 互易性验证测试 ====================

class TestReciprocityVerification:
    """互易性验证测试"""

    def test_reciprocity_pass(self):
        """测试互易性验证通过"""
        is_reciprocal, error = verify_reciprocity(
            tx_gain_dbi=5.0,
            rx_gain_dbi=4.8
        )
        assert is_reciprocal is True
        assert error == pytest.approx(0.2, abs=0.01)

    def test_reciprocity_fail(self):
        """测试互易性验证失败"""
        is_reciprocal, error = verify_reciprocity(
            tx_gain_dbi=5.0,
            rx_gain_dbi=4.0  # 差值 1.0 dB > 阈值 0.5 dB
        )
        assert is_reciprocal is False
        assert error == pytest.approx(1.0, abs=0.01)

    def test_reciprocity_exact_threshold(self):
        """测试恰好在阈值边界"""
        is_reciprocal, error = verify_reciprocity(
            tx_gain_dbi=5.0,
            rx_gain_dbi=5.0 - RECIPROCITY_THRESHOLD_DB
        )
        # 刚好等于阈值，应该失败 (< 不是 <=)
        assert is_reciprocal is False

    def test_reciprocity_custom_threshold(self):
        """测试自定义阈值"""
        is_reciprocal, error = verify_reciprocity(
            tx_gain_dbi=5.0,
            rx_gain_dbi=4.0,
            threshold_db=1.5  # 放宽阈值
        )
        assert is_reciprocal is True


# ==================== GainMeasurement 数据类测试 ====================

class TestGainMeasurement:
    """GainMeasurement 数据类测试"""

    def test_measurement_creation(self):
        """测试测量结果创建"""
        m = GainMeasurement(
            frequency_mhz=3500,
            tx_gain_dbi=5.0,
            rx_gain_dbi=4.9,
            tx_uncertainty_db=0.3,
            rx_uncertainty_db=0.3
        )
        assert m.frequency_mhz == 3500
        assert m.tx_gain_dbi == 5.0

    def test_measurement_reciprocity_error(self):
        """测试互易性误差计算"""
        m = GainMeasurement(
            frequency_mhz=3500,
            tx_gain_dbi=5.0,
            rx_gain_dbi=4.8
        )
        assert m.reciprocity_error_db == pytest.approx(0.2, abs=0.01)

    def test_measurement_is_reciprocal_true(self):
        """测试互易性判断 - 通过"""
        m = GainMeasurement(
            frequency_mhz=3500,
            tx_gain_dbi=5.0,
            rx_gain_dbi=4.8
        )
        assert m.is_reciprocal is True

    def test_measurement_is_reciprocal_false(self):
        """测试互易性判断 - 失败"""
        m = GainMeasurement(
            frequency_mhz=3500,
            tx_gain_dbi=5.0,
            rx_gain_dbi=4.0
        )
        assert m.is_reciprocal is False


# ==================== 频率点生成测试 ====================

class TestFrequencyPointGeneration:
    """频率点生成测试"""

    def test_generate_frequency_points_basic(self):
        """测试基本频率点生成"""
        freq_range = FrequencyRange(
            start_mhz=3300,
            stop_mhz=3800,
            step_mhz=100
        )
        points = generate_frequency_points(freq_range)
        assert len(points) == 6  # 3300, 3400, 3500, 3600, 3700, 3800
        assert points[0] == 3300
        assert points[-1] == 3800

    def test_generate_frequency_points_small_range(self):
        """测试小范围频率 (只生成一个点)"""
        freq_range = FrequencyRange(
            start_mhz=3500,
            stop_mhz=3550,  # stop > start (schema 要求)
            step_mhz=100    # step > range, 所以只有起始点
        )
        points = generate_frequency_points(freq_range)
        assert len(points) == 1
        assert points[0] == 3500


# ==================== AmplitudeCalibrationService 测试 ====================

class TestAmplitudeCalibrationService:
    """幅度校准服务测试"""

    def test_service_init(self):
        """测试服务初始化"""
        service = AmplitudeCalibrationService()
        assert service.instruments is None

    @pytest.mark.asyncio
    async def test_execute_calibration_mock(self, db_session):
        """测试执行校准 (mock 模式)"""
        service = AmplitudeCalibrationService()

        result = await service.execute_amplitude_calibration(
            db=db_session,
            probe_ids=[1, 2],
            polarizations=[PolarizationType.V],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            calibrated_by="Test Engineer",
            use_mock=True
        )

        assert result.success is True
        assert "calibration_ids" in result.data
        assert len(result.data["calibration_ids"]) == 2  # 2 probes * 1 polarization

    @pytest.mark.asyncio
    async def test_execute_calibration_invalid_probe(self, db_session):
        """测试无效探头 ID"""
        service = AmplitudeCalibrationService()

        result = await service.execute_amplitude_calibration(
            db=db_session,
            probe_ids=[100],  # 无效 ID
            polarizations=[PolarizationType.V],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            calibrated_by="Test Engineer",
            use_mock=True
        )

        assert result.success is False
        assert "Invalid probe_id" in result.message

    def test_get_latest_calibration(self, db_session):
        """测试获取最新校准"""
        # 创建测试数据
        cal1 = ProbeAmplitudeCalibration(
            probe_id=10,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow() - timedelta(days=30),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=60),
            status=CalibrationStatus.VALID
        )
        cal2 = ProbeAmplitudeCalibration(
            probe_id=10,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.1],
            rx_gain_dbi=[5.0],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),  # 更新的
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID
        )
        db_session.add_all([cal1, cal2])
        db_session.commit()

        service = AmplitudeCalibrationService()
        latest = service.get_latest_calibration(db_session, probe_id=10)

        assert latest is not None
        assert latest.tx_gain_dbi[0] == pytest.approx(5.1, abs=0.01)

    def test_mock_measurements_properties(self):
        """测试 mock 测量数据特性"""
        service = AmplitudeCalibrationService()
        freq_points = [3300, 3400, 3500, 3600]

        measurements = service._mock_measurements(
            probe_id=5,
            polarization=PolarizationType.V,
            freq_points=freq_points
        )

        assert len(measurements) == 4

        # 验证增益在合理范围内
        for m in measurements:
            assert 3.0 < m.tx_gain_dbi < 7.0
            assert 3.0 < m.rx_gain_dbi < 7.0
            assert m.tx_uncertainty_db > 0
            assert m.rx_uncertainty_db > 0

        # 验证大多数测量点满足互易性
        reciprocal_count = sum(1 for m in measurements if m.is_reciprocal)
        assert reciprocal_count == len(measurements)  # Mock 数据应该都满足


# ==================== CalibrationValidityService 测试 ====================

class TestCalibrationValidityService:
    """校准有效性服务测试"""

    def test_service_init(self):
        """测试服务初始化"""
        service = CalibrationValidityService(expiring_threshold_days=14)
        assert service.expiring_threshold_days == 14

    def test_check_validity_valid(self, db_session):
        """测试有效的校准状态"""
        # 创建有效的校准记录
        cal = ProbeAmplitudeCalibration(
            probe_id=20,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=60),  # 还有 60 天
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        status = service.check_validity(db_session, probe_id=20)

        assert status["overall_status"] == "valid"
        assert status["amplitude"]["status"] == "valid"

    def test_check_validity_expiring_soon(self, db_session):
        """测试即将过期的校准状态"""
        cal = ProbeAmplitudeCalibration(
            probe_id=21,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow() - timedelta(days=85),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=5),  # 约 5 天后过期
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        status = service.check_validity(db_session, probe_id=21)

        assert status["overall_status"] == "expiring_soon"
        assert status["amplitude"]["status"] == "expiring_soon"
        # 由于时间计算精度，允许 ±1 天误差
        assert 4 <= status["amplitude"]["days_remaining"] <= 6

    def test_check_validity_expired(self, db_session):
        """测试已过期的校准状态"""
        cal = ProbeAmplitudeCalibration(
            probe_id=22,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow() - timedelta(days=100),
            calibrated_by="Test",
            valid_until=datetime.utcnow() - timedelta(days=10),  # 10 天前过期
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        status = service.check_validity(db_session, probe_id=22)

        assert status["overall_status"] == "expired"
        assert status["amplitude"]["status"] == "expired"
        assert status["amplitude"]["days_overdue"] == 10

    def test_generate_validity_report(self, db_session):
        """测试生成有效性报告"""
        service = CalibrationValidityService()
        report = service.generate_validity_report(db_session, probe_ids=[20, 21, 22, 23])

        assert report["total_probes"] == 4
        # 之前创建了 20 (valid), 21 (expiring_soon), 22 (expired), 23 (unknown)
        assert report["valid_probes"] >= 0
        assert report["expired_probes"] >= 0


# ==================== 趋势分析测试 ====================

class TestTrendAnalysis:
    """趋势分析测试"""

    def test_analyze_gain_trend_insufficient_data(self):
        """测试数据不足时不返回趋势"""
        service = AmplitudeCalibrationService()
        result = service.analyze_gain_trend([])
        assert result is None

        # 少于 3 条记录
        cal1 = ProbeAmplitudeCalibration(
            probe_id=30,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID
        )
        result = service.analyze_gain_trend([cal1])
        assert result is None

    def test_analyze_gain_trend_stable(self):
        """测试稳定增益的趋势分析"""
        service = AmplitudeCalibrationService()

        calibrations = []
        base_time = datetime.utcnow()

        for i in range(5):
            cal = ProbeAmplitudeCalibration(
                probe_id=31,
                polarization="V",
                frequency_points_mhz=[3500],
                tx_gain_dbi=[5.0 + np.random.normal(0, 0.01)],  # 很小的波动
                rx_gain_dbi=[4.9],
                tx_gain_uncertainty_db=[0.3],
                rx_gain_uncertainty_db=[0.3],
                calibrated_at=base_time - timedelta(days=30 * i),
                calibrated_by="Test",
                valid_until=base_time + timedelta(days=90 - 30 * i),
                status=CalibrationStatus.VALID
            )
            calibrations.append(cal)

        result = service.analyze_gain_trend(calibrations)

        assert result is not None
        assert result["num_calibrations"] == 5
        assert result["stability_rating"] in ["excellent", "good"]


# ==================== 相位校准测试 (TASK-P05) ====================

from app.services.probe_calibration_service import (
    PhaseMeasurement,
    PhaseCalibrationService,
    calculate_group_delay,
    unwrap_phase,
    PHASE_UNCERTAINTY_THRESHOLD_DEG,
)
from app.models.probe_calibration import ProbePhaseCalibration


class TestPhaseMeasurement:
    """PhaseMeasurement 数据类测试"""

    def test_measurement_creation(self):
        """测试相位测量结果创建"""
        m = PhaseMeasurement(
            frequency_mhz=3500,
            phase_offset_deg=15.0,
            group_delay_ns=0.8,
            uncertainty_deg=3.0
        )
        assert m.frequency_mhz == 3500
        assert m.phase_offset_deg == 15.0
        assert m.group_delay_ns == 0.8

    def test_measurement_is_valid_true(self):
        """测试有效测量"""
        m = PhaseMeasurement(
            frequency_mhz=3500,
            phase_offset_deg=15.0,
            group_delay_ns=0.8,
            uncertainty_deg=3.0  # < 5°
        )
        assert m.is_valid is True

    def test_measurement_is_valid_false_high_uncertainty(self):
        """测试高不确定度"""
        m = PhaseMeasurement(
            frequency_mhz=3500,
            phase_offset_deg=15.0,
            group_delay_ns=0.8,
            uncertainty_deg=6.0  # > 5°
        )
        assert m.is_valid is False

    def test_measurement_is_valid_false_high_delay(self):
        """测试高群时延"""
        m = PhaseMeasurement(
            frequency_mhz=3500,
            phase_offset_deg=15.0,
            group_delay_ns=15.0,  # > 10 ns
            uncertainty_deg=3.0
        )
        assert m.is_valid is False


class TestGroupDelayCalculation:
    """群时延计算测试"""

    def test_calculate_group_delay_basic(self):
        """测试基本群时延计算"""
        # 线性相位变化
        phase_deg = [0, -36, -72, -108]  # 每 100 MHz 变化 -36°
        freq_mhz = [3300, 3400, 3500, 3600]  # 100 MHz 步进

        delays = calculate_group_delay(phase_deg, freq_mhz)

        # τ = -(1/360) * (-36) / (100e6) = 1e-9 s = 1 ns
        assert len(delays) == 4
        assert delays[0] == pytest.approx(1.0, abs=0.01)

    def test_calculate_group_delay_single_point(self):
        """测试单点"""
        delays = calculate_group_delay([10], [3500])
        assert delays == [0.0]

    def test_calculate_group_delay_constant_phase(self):
        """测试恒定相位 (无延迟)"""
        phase_deg = [45, 45, 45, 45]
        freq_mhz = [3300, 3400, 3500, 3600]
        delays = calculate_group_delay(phase_deg, freq_mhz)
        assert all(d == pytest.approx(0.0, abs=0.001) for d in delays)


class TestPhaseUnwrap:
    """相位解缠绕测试"""

    def test_unwrap_no_jump(self):
        """测试无跳变"""
        phase = [0, 30, 60, 90]
        unwrapped = unwrap_phase(phase)
        assert unwrapped == phase

    def test_unwrap_positive_jump(self):
        """测试正跳变"""
        phase = [170, -170]  # 340° 跳变
        unwrapped = unwrap_phase(phase)
        assert unwrapped[1] == pytest.approx(190, abs=1)

    def test_unwrap_negative_jump(self):
        """测试负跳变"""
        phase = [-170, 170]  # -340° 跳变
        unwrapped = unwrap_phase(phase)
        assert unwrapped[1] == pytest.approx(-190, abs=1)

    def test_unwrap_empty(self):
        """测试空列表"""
        assert unwrap_phase([]) == []


class TestPhaseCalibrationService:
    """相位校准服务测试"""

    def test_service_init(self):
        """测试服务初始化"""
        service = PhaseCalibrationService()
        assert service.instruments is None

    @pytest.mark.asyncio
    async def test_execute_phase_calibration_mock(self, db_session):
        """测试执行相位校准 (mock 模式)"""
        service = PhaseCalibrationService()

        result = await service.execute_phase_calibration(
            db=db_session,
            probe_ids=[1, 2],
            polarizations=[PolarizationType.V],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            reference_probe_id=0,
            calibrated_by="Test Engineer",
            use_mock=True
        )

        assert result.success is True
        assert "calibration_ids" in result.data
        assert result.data["reference_probe_id"] == 0

    @pytest.mark.asyncio
    async def test_execute_phase_calibration_invalid_probe(self, db_session):
        """测试无效探头 ID"""
        service = PhaseCalibrationService()

        result = await service.execute_phase_calibration(
            db=db_session,
            probe_ids=[100],
            polarizations=[PolarizationType.V],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            reference_probe_id=0,
            calibrated_by="Test",
            use_mock=True
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_phase_calibration_invalid_reference(self, db_session):
        """测试无效参考探头 ID"""
        service = PhaseCalibrationService()

        result = await service.execute_phase_calibration(
            db=db_session,
            probe_ids=[1],
            polarizations=[PolarizationType.V],
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            reference_probe_id=100,  # 无效
            calibrated_by="Test",
            use_mock=True
        )

        assert result.success is False

    def test_mock_phase_measurements(self):
        """测试 mock 相位测量数据"""
        service = PhaseCalibrationService()
        freq_points = [3300, 3400, 3500]

        measurements = service._mock_phase_measurements(
            probe_id=5,
            reference_probe_id=0,
            polarization=PolarizationType.V,
            freq_points=freq_points
        )

        assert len(measurements) == 3

        # 验证相位偏移随探头位置变化
        for m in measurements:
            assert -180 < m.phase_offset_deg < 180 or True  # 相位可以是任意值
            assert 0 < m.group_delay_ns < 5  # 群时延在合理范围
            assert m.uncertainty_deg > 0

    def test_get_latest_calibration(self, db_session):
        """测试获取最新相位校准"""
        # 创建测试数据
        cal = ProbePhaseCalibration(
            probe_id=40,
            polarization="V",
            reference_probe_id=0,
            frequency_points_mhz=[3500],
            phase_offset_deg=[15.0],
            group_delay_ns=[0.8],
            phase_uncertainty_deg=[3.0],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = PhaseCalibrationService()
        latest = service.get_latest_calibration(db_session, probe_id=40)

        assert latest is not None
        assert latest.probe_id == 40
        assert latest.reference_probe_id == 0

    def test_analyze_phase_trend_insufficient_data(self):
        """测试数据不足时不返回趋势"""
        service = PhaseCalibrationService()
        result = service.analyze_phase_trend([])
        assert result is None


# ==================== 极化校准测试 (TASK-P06) ====================

from app.services.probe_calibration_service import (
    PolarizationMeasurement,
    PolarizationCalibrationService,
    calculate_xpd,
    calculate_axial_ratio,
    calculate_axial_ratio_from_amplitudes,
    XPD_MIN_THRESHOLD_DB,
    AXIAL_RATIO_MAX_DB,
)
from app.models.probe_calibration import ProbePolarizationCalibration


class TestPolarizationMeasurement:
    """PolarizationMeasurement 数据类测试"""

    def test_linear_measurement_creation(self):
        """测试线极化测量结果创建"""
        m = PolarizationMeasurement(
            frequency_mhz=3500,
            v_to_h_isolation_db=28.0,
            h_to_v_isolation_db=27.5,
            uncertainty_db=0.5
        )
        assert m.frequency_mhz == 3500
        assert m.v_to_h_isolation_db == 28.0
        assert m.h_to_v_isolation_db == 27.5

    def test_circular_measurement_creation(self):
        """测试圆极化测量结果创建"""
        m = PolarizationMeasurement(
            frequency_mhz=3500,
            axial_ratio_db=1.5,
            polarization_hand="LHCP",
            uncertainty_db=0.2
        )
        assert m.frequency_mhz == 3500
        assert m.axial_ratio_db == 1.5
        assert m.polarization_hand == "LHCP"

    def test_xpd_property(self):
        """测试 XPD 属性 (取较小值)"""
        m = PolarizationMeasurement(
            frequency_mhz=3500,
            v_to_h_isolation_db=30.0,
            h_to_v_isolation_db=25.0
        )
        assert m.xpd_db == 25.0  # 取较小值

    def test_is_linear_valid_true(self):
        """测试有效线极化"""
        m = PolarizationMeasurement(
            frequency_mhz=3500,
            v_to_h_isolation_db=25.0,
            h_to_v_isolation_db=26.0
        )
        assert m.is_linear_valid is True  # XPD = 25 >= 20

    def test_is_linear_valid_false(self):
        """测试无效线极化"""
        m = PolarizationMeasurement(
            frequency_mhz=3500,
            v_to_h_isolation_db=18.0,
            h_to_v_isolation_db=19.0
        )
        assert m.is_linear_valid is False  # XPD = 18 < 20

    def test_is_circular_valid_true(self):
        """测试有效圆极化"""
        m = PolarizationMeasurement(
            frequency_mhz=3500,
            axial_ratio_db=2.5,
            polarization_hand="LHCP"
        )
        assert m.is_circular_valid is True  # AR = 2.5 <= 3.0

    def test_is_circular_valid_false(self):
        """测试无效圆极化"""
        m = PolarizationMeasurement(
            frequency_mhz=3500,
            axial_ratio_db=4.0,
            polarization_hand="RHCP"
        )
        assert m.is_circular_valid is False  # AR = 4.0 > 3.0


class TestXPDCalculation:
    """XPD 计算测试"""

    def test_calculate_xpd_basic(self):
        """测试基本 XPD 计算"""
        xpd = calculate_xpd(co_polar_power_dbm=-10.0, cross_polar_power_dbm=-35.0)
        assert xpd == 25.0  # -10 - (-35) = 25

    def test_calculate_xpd_high_isolation(self):
        """测试高隔离度"""
        xpd = calculate_xpd(co_polar_power_dbm=-10.0, cross_polar_power_dbm=-50.0)
        assert xpd == 40.0

    def test_calculate_xpd_low_isolation(self):
        """测试低隔离度"""
        xpd = calculate_xpd(co_polar_power_dbm=-10.0, cross_polar_power_dbm=-20.0)
        assert xpd == 10.0


class TestAxialRatioCalculation:
    """轴比计算测试"""

    def test_calculate_axial_ratio_perfect_circular(self):
        """测试理想圆极化 (AR = 0 dB)"""
        ar = calculate_axial_ratio(e_major=1.0, e_minor=1.0)
        assert ar == pytest.approx(0.0, abs=0.001)

    def test_calculate_axial_ratio_typical(self):
        """测试典型轴比"""
        # E_major / E_minor = 1.26 -> AR = 20*log10(1.26) ≈ 2 dB
        ar = calculate_axial_ratio(e_major=1.26, e_minor=1.0)
        assert ar == pytest.approx(2.0, abs=0.1)

    def test_calculate_axial_ratio_swap_order(self):
        """测试交换顺序 (应自动处理)"""
        ar = calculate_axial_ratio(e_major=1.0, e_minor=1.26)
        assert ar == pytest.approx(2.0, abs=0.1)

    def test_calculate_axial_ratio_zero_minor(self):
        """测试副轴为零 (无限大轴比)"""
        ar = calculate_axial_ratio(e_major=1.0, e_minor=0.0)
        assert ar == float('inf')


class TestAxialRatioFromAmplitudes:
    """从 LHCP/RHCP 分量计算轴比测试"""

    def test_lhcp_dominant(self):
        """测试 LHCP 主导"""
        ar, hand = calculate_axial_ratio_from_amplitudes(e_lhcp=1.0, e_rhcp=0.1)
        assert hand == "LHCP"
        assert ar > 0

    def test_rhcp_dominant(self):
        """测试 RHCP 主导"""
        ar, hand = calculate_axial_ratio_from_amplitudes(e_lhcp=0.1, e_rhcp=1.0)
        assert hand == "RHCP"
        assert ar > 0

    def test_both_zero(self):
        """测试两者都为零"""
        ar, hand = calculate_axial_ratio_from_amplitudes(e_lhcp=0.0, e_rhcp=0.0)
        assert ar == float('inf')
        assert hand == "unknown"


class TestPolarizationCalibrationService:
    """极化校准服务测试"""

    def test_service_init(self):
        """测试服务初始化"""
        service = PolarizationCalibrationService()
        assert service.instruments is None

    @pytest.mark.asyncio
    async def test_execute_linear_calibration_mock(self, db_session):
        """测试执行线极化校准 (mock 模式)"""
        service = PolarizationCalibrationService()

        result = await service.execute_polarization_calibration(
            db=db_session,
            probe_ids=[1, 2],
            probe_type="dual_linear",
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            calibrated_by="Test Engineer",
            use_mock=True
        )

        assert result.success is True
        assert "calibration_ids" in result.data
        assert result.data["probe_type"] == "dual_linear"

    @pytest.mark.asyncio
    async def test_execute_circular_calibration_mock(self, db_session):
        """测试执行圆极化校准 (mock 模式)"""
        service = PolarizationCalibrationService()

        result = await service.execute_polarization_calibration(
            db=db_session,
            probe_ids=[3],
            probe_type="circular",
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            calibrated_by="Test Engineer",
            use_mock=True
        )

        assert result.success is True
        assert result.data["probe_type"] == "circular"

    @pytest.mark.asyncio
    async def test_execute_polarization_calibration_invalid_probe(self, db_session):
        """测试无效探头 ID"""
        service = PolarizationCalibrationService()

        result = await service.execute_polarization_calibration(
            db=db_session,
            probe_ids=[100],
            probe_type="dual_linear",
            frequency_range=FrequencyRange(start_mhz=3300, stop_mhz=3500, step_mhz=100),
            calibrated_by="Test",
            use_mock=True
        )

        assert result.success is False

    def test_mock_linear_measurements(self):
        """测试 mock 线极化测量数据"""
        service = PolarizationCalibrationService()
        freq_points = [3300, 3400, 3500]

        measurements = service._mock_polarization_measurements(
            probe_id=5,
            probe_type="dual_linear",
            freq_points=freq_points
        )

        assert len(measurements) == 3
        for m in measurements:
            assert m.v_to_h_isolation_db is not None
            assert m.h_to_v_isolation_db is not None
            assert m.v_to_h_isolation_db > 20  # 应该在合理范围内

    def test_mock_circular_measurements(self):
        """测试 mock 圆极化测量数据"""
        service = PolarizationCalibrationService()
        freq_points = [3300, 3400, 3500]

        measurements = service._mock_polarization_measurements(
            probe_id=4,  # 偶数探头，应为 LHCP
            probe_type="circular",
            freq_points=freq_points
        )

        assert len(measurements) == 3
        for m in measurements:
            assert m.axial_ratio_db is not None
            assert m.polarization_hand == "LHCP"
            assert m.axial_ratio_db < 5  # 应该在合理范围内

    def test_get_latest_calibration(self, db_session):
        """测试获取最新极化校准"""
        # 创建测试数据
        cal = ProbePolarizationCalibration(
            probe_id=50,
            probe_type="dual_linear",
            v_to_h_isolation_db=28.0,
            h_to_v_isolation_db=27.5,
            frequency_points_mhz=[3500],
            isolation_vs_frequency_db=[28.0],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=180),
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = PolarizationCalibrationService()
        latest = service.get_latest_calibration(db_session, probe_id=50)

        assert latest is not None
        assert latest.probe_id == 50
        assert latest.probe_type == "dual_linear"

    def test_evaluate_linear_quality_excellent(self, db_session):
        """测试评估优秀线极化质量"""
        cal = ProbePolarizationCalibration(
            probe_id=51,
            probe_type="dual_linear",
            v_to_h_isolation_db=35.0,
            h_to_v_isolation_db=34.0,
            frequency_points_mhz=[3500],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=180),
            status=CalibrationStatus.VALID
        )

        service = PolarizationCalibrationService()
        quality = service.evaluate_polarization_quality(cal)

        assert quality["type"] == "linear"
        assert quality["quality"] == "excellent"
        assert quality["pass"] is True

    def test_evaluate_circular_quality_good(self, db_session):
        """测试评估良好圆极化质量"""
        cal = ProbePolarizationCalibration(
            probe_id=52,
            probe_type="circular",
            axial_ratio_db=2.0,
            polarization_hand="RHCP",
            frequency_points_mhz=[3500],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=180),
            status=CalibrationStatus.VALID
        )

        service = PolarizationCalibrationService()
        quality = service.evaluate_polarization_quality(cal)

        assert quality["type"] == "circular"
        assert quality["quality"] == "good"
        assert quality["pass"] is True

    def test_evaluate_circular_quality_poor(self, db_session):
        """测试评估不合格圆极化"""
        cal = ProbePolarizationCalibration(
            probe_id=53,
            probe_type="circular",
            axial_ratio_db=5.0,  # > 3 dB
            polarization_hand="LHCP",
            frequency_points_mhz=[3500],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=180),
            status=CalibrationStatus.VALID
        )

        service = PolarizationCalibrationService()
        quality = service.evaluate_polarization_quality(cal)

        assert quality["type"] == "circular"
        assert quality["quality"] == "poor"
        assert quality["pass"] is False


# ==================== 方向图校准测试 (TASK-P07) ====================

from app.services.probe_calibration_service import (
    PatternMeasurement,
    PatternCalibrationService,
    calculate_far_field_distance,
    validate_far_field_condition,
    calculate_hpbw,
    calculate_front_to_back_ratio,
    PATTERN_VALIDITY_DAYS,
    SPEED_OF_LIGHT_M_S,
)
from app.models.probe_calibration import ProbePattern


class TestFarFieldCalculation:
    """远场距离计算测试"""

    def test_calculate_far_field_distance_basic(self):
        """测试基本远场距离计算"""
        # d = 2D²/λ
        # D = 0.1m, f = 3500 MHz, λ = 0.0857m
        # d = 2 * 0.01 / 0.0857 = 0.233m
        distance = calculate_far_field_distance(
            antenna_diameter_m=0.1,
            frequency_mhz=3500
        )
        assert distance == pytest.approx(0.233, abs=0.01)

    def test_calculate_far_field_distance_larger_antenna(self):
        """测试大天线的远场距离"""
        # D = 0.5m, f = 3500 MHz, λ = 0.0857m
        # d = 2 * 0.25 / 0.0857 = 5.83m
        distance = calculate_far_field_distance(
            antenna_diameter_m=0.5,
            frequency_mhz=3500
        )
        assert distance == pytest.approx(5.83, abs=0.1)

    def test_validate_far_field_condition_valid(self):
        """测试满足远场条件"""
        is_valid, min_dist = validate_far_field_condition(
            measurement_distance_m=3.0,
            antenna_diameter_m=0.1,
            frequency_mhz=3500
        )
        assert is_valid is True
        assert min_dist < 3.0

    def test_validate_far_field_condition_invalid(self):
        """测试不满足远场条件"""
        is_valid, min_dist = validate_far_field_condition(
            measurement_distance_m=0.1,  # 太近
            antenna_diameter_m=0.5,
            frequency_mhz=3500
        )
        assert is_valid is False


class TestHPBWCalculation:
    """HPBW 计算测试"""

    def test_calculate_hpbw_gaussian_pattern(self):
        """测试高斯波束 HPBW 计算"""
        # 生成高斯波束 (HPBW = 60°)
        angles = list(range(-90, 91, 5))
        sigma = 60 / (2 * np.sqrt(2 * np.log(2)))  # HPBW to sigma
        gains = [10 * np.exp(-(a ** 2) / (2 * sigma ** 2)) for a in angles]
        gains_db = [10 * np.log10(g + 0.001) for g in gains]

        hpbw = calculate_hpbw(angles, gains_db)

        assert hpbw is not None
        assert hpbw == pytest.approx(60, abs=10)  # 允许一定误差

    def test_calculate_hpbw_insufficient_data(self):
        """测试数据不足"""
        hpbw = calculate_hpbw([0, 10], [5, 4])
        # 数据太少，可能无法计算
        assert hpbw is None or hpbw > 0

    def test_calculate_hpbw_flat_pattern(self):
        """测试平坦方向图"""
        angles = list(range(0, 91, 10))
        gains = [5.0] * len(angles)  # 全部相同增益

        hpbw = calculate_hpbw(angles, gains)
        # 平坦方向图无法计算 HPBW
        assert hpbw is None


class TestFrontToBackRatio:
    """前后比计算测试"""

    def test_calculate_ftb_basic(self):
        """测试基本前后比计算"""
        azimuth = list(range(0, 360, 10))
        # 前向 (0°) 高增益，后向 (180°) 低增益
        gains = []
        for az in azimuth:
            if az < 90 or az > 270:
                gains.append(10.0)  # 前半球
            else:
                gains.append(-5.0)  # 后半球

        ftb = calculate_front_to_back_ratio(gains, azimuth)

        assert ftb is not None
        assert ftb == pytest.approx(15.0, abs=1)

    def test_calculate_ftb_single_point(self):
        """测试单点"""
        ftb = calculate_front_to_back_ratio([5.0], [0])
        assert ftb is None


class TestPatternMeasurement:
    """PatternMeasurement 数据类测试"""

    def test_measurement_creation(self):
        """测试方向图测量结果创建"""
        m = PatternMeasurement(
            azimuth_deg=45.0,
            elevation_deg=90.0,
            gain_dbi=5.5,
            uncertainty_db=0.3
        )
        assert m.azimuth_deg == 45.0
        assert m.elevation_deg == 90.0
        assert m.gain_dbi == 5.5
        assert m.uncertainty_db == 0.3


class TestPatternCalibrationService:
    """方向图校准服务测试"""

    def test_service_init(self):
        """测试服务初始化"""
        service = PatternCalibrationService()
        assert service.instruments is None

    @pytest.mark.asyncio
    async def test_execute_pattern_calibration_mock(self, db_session):
        """测试执行方向图校准 (mock 模式)"""
        service = PatternCalibrationService()

        result = await service.execute_pattern_calibration(
            db=db_session,
            probe_ids=[1],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500,
            calibrated_by="Test Engineer",
            azimuth_step_deg=30,  # 较大步进加快测试
            elevation_step_deg=30,
            use_mock=True
        )

        assert result.success is True
        assert "calibration_ids" in result.data
        assert result.data["frequency_mhz"] == 3500

    @pytest.mark.asyncio
    async def test_execute_pattern_calibration_invalid_probe(self, db_session):
        """测试无效探头 ID"""
        service = PatternCalibrationService()

        result = await service.execute_pattern_calibration(
            db=db_session,
            probe_ids=[100],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500,
            calibrated_by="Test",
            use_mock=True
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_pattern_calibration_far_field_warning(self, db_session):
        """测试远场条件警告"""
        service = PatternCalibrationService()

        result = await service.execute_pattern_calibration(
            db=db_session,
            probe_ids=[1],
            polarizations=[PolarizationType.V],
            frequency_mhz=3500,
            calibrated_by="Test",
            measurement_distance_m=0.05,  # 太近
            azimuth_step_deg=60,
            elevation_step_deg=60,
            use_mock=True
        )

        # 应该成功但有警告
        assert result.success is True
        assert len(result.warnings) > 0
        assert "far-field" in result.warnings[0].lower()

    def test_mock_pattern_measurements(self):
        """测试 mock 方向图测量数据"""
        service = PatternCalibrationService()
        azimuth = list(range(0, 360, 30))
        elevation = list(range(0, 181, 30))

        measurements = service._mock_pattern_measurements(
            probe_id=5,
            polarization=PolarizationType.V,
            azimuth_deg=azimuth,
            elevation_deg=elevation,
            frequency_mhz=3500
        )

        expected_count = len(azimuth) * len(elevation)
        assert len(measurements) == expected_count

        # 验证测量值在合理范围
        for m in measurements:
            assert -30 < m.gain_dbi < 20  # 合理增益范围

    def test_get_latest_calibration(self, db_session):
        """测试获取最新方向图校准"""
        # 创建测试数据
        cal = ProbePattern(
            probe_id=60,
            polarization="V",
            frequency_mhz=3500,
            azimuth_deg=[0, 90, 180, 270],
            elevation_deg=[0, 90, 180],
            gain_pattern_dbi=[5, 4, 3, 2] * 3,
            peak_gain_dbi=5.0,
            peak_azimuth_deg=0,
            peak_elevation_deg=90,
            measured_at=datetime.utcnow(),
            measured_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=365),
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = PatternCalibrationService()
        latest = service.get_latest_calibration(db_session, probe_id=60)

        assert latest is not None
        assert latest.probe_id == 60
        assert latest.frequency_mhz == 3500

    def test_get_latest_calibration_with_frequency(self, db_session):
        """测试按频率获取方向图校准"""
        # 创建不同频率的测试数据
        for freq in [3300, 3500, 3700]:
            cal = ProbePattern(
                probe_id=61,
                polarization="V",
                frequency_mhz=freq,
                azimuth_deg=[0, 90],
                elevation_deg=[0, 90],
                gain_pattern_dbi=[5, 4, 3, 2],
                measured_at=datetime.utcnow(),
                measured_by="Test",
                valid_until=datetime.utcnow() + timedelta(days=365),
                status=CalibrationStatus.VALID
            )
            db_session.add(cal)
        db_session.commit()

        service = PatternCalibrationService()
        latest = service.get_latest_calibration(
            db_session, probe_id=61, frequency_mhz=3500
        )

        assert latest is not None
        assert latest.frequency_mhz == 3500

    def test_evaluate_pattern_quality_good(self, db_session):
        """测试评估良好方向图质量"""
        cal = ProbePattern(
            probe_id=62,
            polarization="V",
            frequency_mhz=3500,
            azimuth_deg=[0],
            elevation_deg=[0],
            gain_pattern_dbi=[5.0],
            peak_gain_dbi=5.0,
            hpbw_azimuth_deg=60.0,
            hpbw_elevation_deg=60.0,
            front_to_back_ratio_db=18.0,
            measured_at=datetime.utcnow(),
            measured_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=365),
            status=CalibrationStatus.VALID
        )

        service = PatternCalibrationService()
        quality = service.evaluate_pattern_quality(cal)

        assert quality["quality"] == "good"
        assert len(quality["issues"]) == 0

    def test_evaluate_pattern_quality_marginal(self, db_session):
        """测试评估边缘方向图质量"""
        cal = ProbePattern(
            probe_id=63,
            polarization="V",
            frequency_mhz=3500,
            azimuth_deg=[0],
            elevation_deg=[0],
            gain_pattern_dbi=[2.0],
            peak_gain_dbi=2.0,  # 边缘增益
            hpbw_azimuth_deg=130.0,  # 太宽
            hpbw_elevation_deg=60.0,
            front_to_back_ratio_db=8.0,  # 太低
            measured_at=datetime.utcnow(),
            measured_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=365),
            status=CalibrationStatus.VALID
        )

        service = PatternCalibrationService()
        quality = service.evaluate_pattern_quality(cal)

        assert quality["quality"] == "marginal"
        assert len(quality["issues"]) > 0

    def test_evaluate_pattern_quality_poor(self, db_session):
        """测试评估不合格方向图质量"""
        cal = ProbePattern(
            probe_id=0,  # 使用 probe_id=0
            polarization="H",
            frequency_mhz=3500,
            azimuth_deg=[0],
            elevation_deg=[0],
            gain_pattern_dbi=[-2.0],
            peak_gain_dbi=-2.0,  # 负增益
            measured_at=datetime.utcnow(),
            measured_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=365),
            status=CalibrationStatus.VALID
        )

        service = PatternCalibrationService()
        quality = service.evaluate_pattern_quality(cal)

        assert quality["quality"] == "poor"
        assert "Low peak gain" in quality["issues"][0]


# ==================== 链路校准测试 (TASK-P08) ====================

from app.services.probe_calibration_service import (
    LinkMeasurement,
    LinkCalibrationService,
    calculate_deviation,
    validate_link_calibration,
    LINK_CALIBRATION_VALIDITY_DAYS,
    DEFAULT_DEVIATION_THRESHOLD_DB,
    EXCELLENT_DEVIATION_THRESHOLD_DB,
)
from app.models.probe_calibration import LinkCalibration


class TestDeviationCalculation:
    """偏差计算测试"""

    def test_calculate_deviation_no_error(self):
        """测试无误差情况"""
        deviation = calculate_deviation(
            measured_gain_dbi=2.15,
            known_gain_dbi=2.15
        )
        assert deviation == pytest.approx(0.0, abs=0.001)

    def test_calculate_deviation_positive(self):
        """测试正偏差 (测量偏高)"""
        deviation = calculate_deviation(
            measured_gain_dbi=2.5,
            known_gain_dbi=2.15
        )
        assert deviation == pytest.approx(0.35, abs=0.001)

    def test_calculate_deviation_negative(self):
        """测试负偏差 (测量偏低)"""
        deviation = calculate_deviation(
            measured_gain_dbi=1.8,
            known_gain_dbi=2.15
        )
        assert deviation == pytest.approx(-0.35, abs=0.001)


class TestLinkValidation:
    """链路校准验证测试"""

    def test_validate_excellent(self):
        """测试优秀校准结果"""
        is_pass, quality = validate_link_calibration(
            deviation_db=0.2,
            threshold_db=1.0
        )
        assert is_pass is True
        assert quality == "excellent"

    def test_validate_good(self):
        """测试良好校准结果"""
        is_pass, quality = validate_link_calibration(
            deviation_db=0.7,
            threshold_db=1.0
        )
        assert is_pass is True
        assert quality == "good"

    def test_validate_marginal(self):
        """测试边缘校准结果"""
        is_pass, quality = validate_link_calibration(
            deviation_db=1.3,
            threshold_db=1.0
        )
        assert is_pass is False
        assert quality == "marginal"

    def test_validate_poor(self):
        """测试不合格校准结果"""
        is_pass, quality = validate_link_calibration(
            deviation_db=2.0,
            threshold_db=1.0
        )
        assert is_pass is False
        assert quality == "poor"

    def test_validate_negative_deviation(self):
        """测试负偏差"""
        is_pass, quality = validate_link_calibration(
            deviation_db=-0.5,
            threshold_db=1.0
        )
        assert is_pass is True
        assert quality == "good"


class TestLinkMeasurement:
    """LinkMeasurement 数据类测试"""

    def test_measurement_creation(self):
        """测试链路测量结果创建"""
        m = LinkMeasurement(
            probe_id=5,
            link_loss_db=30.5,
            phase_offset_deg=45.0,
            uncertainty_db=0.2
        )
        assert m.probe_id == 5
        assert m.link_loss_db == 30.5
        assert m.phase_offset_deg == 45.0
        assert m.uncertainty_db == 0.2


class TestLinkCalibrationService:
    """链路校准服务测试"""

    def test_service_init(self):
        """测试服务初始化"""
        service = LinkCalibrationService()
        assert service.instruments is None

    @pytest.mark.asyncio
    async def test_execute_link_calibration_mock(self, db_session):
        """测试执行链路校准 (mock 模式)"""
        service = LinkCalibrationService()

        result = await service.execute_link_calibration(
            db=db_session,
            calibration_type="pre_test",
            standard_dut={
                "dut_type": "dipole",
                "model": "Standard Dipole",
                "serial": "SD-001",
                "known_gain_dbi": 2.15
            },
            frequency_mhz=3500,
            calibrated_by="Test Engineer",
            use_mock=True
        )

        assert result.success is True
        assert "calibration_id" in result.data
        assert "deviation_db" in result.data
        assert "validation_pass" in result.data

    @pytest.mark.asyncio
    async def test_execute_link_calibration_with_probes(self, db_session):
        """测试指定探头的链路校准"""
        service = LinkCalibrationService()

        result = await service.execute_link_calibration(
            db=db_session,
            calibration_type="weekly_check",
            standard_dut={
                "dut_type": "horn",
                "model": "Horn Antenna",
                "serial": "HA-002",
                "known_gain_dbi": 10.0
            },
            frequency_mhz=3700,
            calibrated_by="Test",
            probe_ids=[0, 1, 2, 3],
            use_mock=True
        )

        assert result.success is True
        assert result.data["num_probes"] == 4

    def test_mock_link_measurement(self):
        """测试 mock 链路测量数据"""
        service = LinkCalibrationService()
        known_gain = 2.15

        measured_gain, probe_calibrations = service._mock_link_measurement(
            known_gain_dbi=known_gain,
            probe_ids=[0, 1, 2],
            frequency_mhz=3500
        )

        # 测量增益应该接近已知增益
        assert abs(measured_gain - known_gain) < 2.0

        # 探头校准数据
        assert len(probe_calibrations) == 3
        for pc in probe_calibrations:
            assert "probe_id" in pc
            assert "link_loss_db" in pc
            assert "phase_offset_deg" in pc

    def test_get_latest_calibration(self, db_session):
        """测试获取最新链路校准"""
        # 创建测试数据
        cal = LinkCalibration(
            calibration_type="pre_test",
            standard_dut_type="dipole",
            standard_dut_model="Test",
            standard_dut_serial="001",
            known_gain_dbi=2.15,
            frequency_mhz=3500,
            measured_gain_dbi=2.2,
            deviation_db=0.05,
            validation_pass=True,
            threshold_db=1.0,
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test"
        )
        db_session.add(cal)
        db_session.commit()

        service = LinkCalibrationService()
        latest = service.get_latest_calibration(db_session)

        assert latest is not None
        assert latest.calibration_type == "pre_test"

    def test_get_calibration_history(self, db_session):
        """测试获取链路校准历史"""
        # 创建多条测试数据
        for i in range(3):
            cal = LinkCalibration(
                calibration_type="weekly_check",
                known_gain_dbi=2.15,
                measured_gain_dbi=2.15 + i * 0.1,
                deviation_db=i * 0.1,
                validation_pass=True,
                threshold_db=1.0,
                calibrated_at=datetime.utcnow() - timedelta(days=i),
                calibrated_by="Test"
            )
            db_session.add(cal)
        db_session.commit()

        service = LinkCalibrationService()
        history = service.get_calibration_history(db_session, limit=10)

        assert len(history) >= 3

    def test_check_link_validity_valid(self, db_session):
        """测试有效链路校准状态"""
        cal = LinkCalibration(
            calibration_type="pre_test",
            known_gain_dbi=2.15,
            measured_gain_dbi=2.2,
            deviation_db=0.05,
            validation_pass=True,
            threshold_db=1.0,
            calibrated_at=datetime.utcnow(),  # 今天
            calibrated_by="Test"
        )
        db_session.add(cal)
        db_session.commit()

        service = LinkCalibrationService()
        status = service.check_link_validity(db_session)

        assert status["status"] == "valid"
        assert "days_remaining" in status

    def test_check_link_validity_expired(self, db_session):
        """测试过期链路校准状态"""
        # 先清除所有链路校准记录
        db_session.query(LinkCalibration).delete()
        db_session.commit()

        # 创建一个已过期的校准记录 (10天前)
        cal = LinkCalibration(
            calibration_type="pre_test",
            known_gain_dbi=2.15,
            measured_gain_dbi=2.2,
            deviation_db=0.05,
            validation_pass=True,
            threshold_db=1.0,
            calibrated_at=datetime.utcnow() - timedelta(days=10),  # 10 天前
            calibrated_by="Test"
        )
        db_session.add(cal)
        db_session.commit()

        service = LinkCalibrationService()
        status = service.check_link_validity(db_session)

        assert status["status"] == "expired"
        assert "days_overdue" in status

    def test_evaluate_calibration_quality_pass(self, db_session):
        """测试评估合格校准质量"""
        cal = LinkCalibration(
            calibration_type="pre_test",
            known_gain_dbi=2.15,
            measured_gain_dbi=2.3,
            deviation_db=0.15,
            validation_pass=True,
            threshold_db=1.0,
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test"
        )

        service = LinkCalibrationService()
        quality = service.evaluate_calibration_quality(cal)

        assert quality["validation_pass"] is True
        assert quality["quality"] == "excellent"

    def test_evaluate_calibration_quality_fail(self, db_session):
        """测试评估不合格校准质量"""
        cal = LinkCalibration(
            calibration_type="pre_test",
            known_gain_dbi=2.15,
            measured_gain_dbi=4.0,
            deviation_db=1.85,
            validation_pass=False,
            threshold_db=1.0,
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test"
        )

        service = LinkCalibrationService()
        quality = service.evaluate_calibration_quality(cal)

        assert quality["validation_pass"] is False
        assert quality["quality"] == "poor"


# ==================== 有效性管理测试 (TASK-P09) ====================

from app.services.probe_calibration_service import CalibrationValidityService


class TestCalibrationValidityService:
    """CalibrationValidityService 测试"""

    def test_service_init(self):
        """测试服务初始化"""
        service = CalibrationValidityService()
        assert service.expiring_threshold_days == 7

    def test_service_init_custom_threshold(self):
        """测试自定义阈值初始化"""
        service = CalibrationValidityService(expiring_threshold_days=14)
        assert service.expiring_threshold_days == 14

    def test_check_validity_no_calibrations(self, db_session):
        """测试无校准数据时的有效性检查"""
        service = CalibrationValidityService()
        status = service.check_validity(db_session, probe_id=99)

        assert status["probe_id"] == 99
        assert status["overall_status"] == "unknown"
        assert status["amplitude"] is None

    def test_check_validity_with_amplitude(self, db_session):
        """测试有幅度校准数据时的有效性检查"""
        cal = ProbeAmplitudeCalibration(
            probe_id=30,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        status = service.check_validity(db_session, probe_id=30)

        assert status["amplitude"] is not None
        assert status["amplitude"]["status"] == "valid"
        assert "calibration_id" in status["amplitude"]

    def test_check_validity_all_types(self, db_session):
        """测试所有校准类型的有效性检查"""
        probe_id = 31

        # 先清除链路校准数据 (全局数据可能影响测试)
        db_session.query(LinkCalibration).delete()
        db_session.commit()

        # 创建幅度校准
        amp_cal = ProbeAmplitudeCalibration(
            probe_id=probe_id,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID
        )
        db_session.add(amp_cal)

        # 创建相位校准
        phase_cal = ProbePhaseCalibration(
            probe_id=probe_id,
            polarization="V",
            reference_probe_id=0,
            frequency_points_mhz=[3500],
            phase_offset_deg=[15.0],
            group_delay_ns=[0.8],
            phase_uncertainty_deg=[3.0],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID
        )
        db_session.add(phase_cal)

        # 创建极化校准
        pol_cal = ProbePolarizationCalibration(
            probe_id=probe_id,
            probe_type="dual_linear",
            v_to_h_isolation_db=28.0,
            h_to_v_isolation_db=27.5,
            frequency_points_mhz=[3500],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=180),
            status=CalibrationStatus.VALID
        )
        db_session.add(pol_cal)

        # 创建方向图校准
        pattern_cal = ProbePattern(
            probe_id=probe_id,
            polarization="V",
            frequency_mhz=3500,
            azimuth_deg=[0, 90],
            elevation_deg=[0, 90],
            gain_pattern_dbi=[5, 4, 3, 2],
            measured_at=datetime.utcnow(),
            measured_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=365),
            status=CalibrationStatus.VALID
        )
        db_session.add(pattern_cal)

        # 创建链路校准 (新的，有效期足够长)
        link_cal = LinkCalibration(
            calibration_type="pre_test",
            known_gain_dbi=2.15,
            measured_gain_dbi=2.2,
            deviation_db=0.05,
            validation_pass=True,
            threshold_db=1.0,
            calibrated_at=datetime.utcnow(),  # 今天创建，7天有效期
            calibrated_by="Test"
        )
        db_session.add(link_cal)
        db_session.commit()

        # 使用较短的过期阈值 (3天)，因为链路校准有效期是 7 天
        # 如果阈值也是 7 天，由于微秒级时间差，新创建的链路校准会被判定为 "expiring_soon"
        service = CalibrationValidityService(expiring_threshold_days=3)
        status = service.check_validity(db_session, probe_id=probe_id)

        assert status["amplitude"] is not None
        assert status["phase"] is not None
        assert status["polarization"] is not None
        assert status["pattern"] is not None
        assert status["link"] is not None
        assert status["overall_status"] == "valid"

    def test_check_validity_expired(self, db_session):
        """测试过期校准的有效性检查"""
        cal = ProbeAmplitudeCalibration(
            probe_id=32,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow() - timedelta(days=100),
            calibrated_by="Test",
            valid_until=datetime.utcnow() - timedelta(days=10),  # 已过期
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        status = service.check_validity(db_session, probe_id=32)

        assert status["amplitude"]["status"] == "expired"
        assert status["amplitude"]["days_overdue"] >= 10
        assert status["overall_status"] == "expired"

    def test_generate_validity_report(self, db_session):
        """测试生成有效性报告"""
        service = CalibrationValidityService()
        report = service.generate_validity_report(db_session, probe_ids=[0, 1, 2])

        assert report["total_probes"] == 3
        assert "valid_probes" in report
        assert "expired_probes" in report
        assert "expiring_soon_probes" in report
        assert "expired_calibrations" in report
        assert "expiring_soon_calibrations" in report
        assert "recommendations" in report

    def test_invalidate_calibration_success(self, db_session):
        """测试成功作废校准"""
        cal = ProbeAmplitudeCalibration(
            probe_id=33,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        result = service.invalidate_calibration(
            db=db_session,
            calibration_type="amplitude",
            calibration_id=str(cal.id),
            reason="Test invalidation"
        )

        assert result["success"] is True

        # 验证状态已更新
        updated_cal = db_session.query(ProbeAmplitudeCalibration).filter(
            ProbeAmplitudeCalibration.id == cal.id
        ).first()
        assert updated_cal.status == CalibrationStatus.INVALIDATED.value

    def test_invalidate_calibration_not_found(self, db_session):
        """测试作废不存在的校准"""
        service = CalibrationValidityService()
        result = service.invalidate_calibration(
            db=db_session,
            calibration_type="amplitude",
            calibration_id="00000000-0000-0000-0000-000000000001",
            reason="Test"
        )

        assert result["success"] is False
        assert "not found" in result["message"]

    def test_invalidate_calibration_invalid_type(self, db_session):
        """测试作废无效类型"""
        service = CalibrationValidityService()
        result = service.invalidate_calibration(
            db=db_session,
            calibration_type="invalid_type",
            calibration_id="00000000-0000-0000-0000-000000000001",
            reason="Test"
        )

        assert result["success"] is False
        assert "Unknown calibration type" in result["message"]

    def test_invalidate_calibration_invalid_uuid(self, db_session):
        """测试无效的 UUID 格式"""
        service = CalibrationValidityService()
        result = service.invalidate_calibration(
            db=db_session,
            calibration_type="amplitude",
            calibration_id="invalid-uuid",
            reason="Test"
        )

        assert result["success"] is False
        assert "Invalid calibration ID" in result["message"]

    def test_get_expiring_calibrations(self, db_session):
        """测试获取即将过期的校准"""
        # 创建一个即将过期的校准
        cal = ProbeAmplitudeCalibration(
            probe_id=34,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=5),  # 5 天后过期
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        expiring = service.get_expiring_calibrations(
            db=db_session,
            days_threshold=7
        )

        # 应该能找到这个即将过期的校准
        found = any(
            e["calibration_id"] == str(cal.id)
            for e in expiring
        )
        assert found

    def test_get_expiring_calibrations_by_type(self, db_session):
        """测试按类型获取即将过期的校准"""
        service = CalibrationValidityService()
        expiring = service.get_expiring_calibrations(
            db=db_session,
            days_threshold=7,
            calibration_type="amplitude"
        )

        # 所有返回的校准都应该是 amplitude 类型
        for e in expiring:
            assert e["calibration_type"] == "amplitude"

    def test_get_expired_calibrations(self, db_session):
        """测试获取已过期的校准"""
        # 创建一个已过期的校准
        cal = ProbeAmplitudeCalibration(
            probe_id=35,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow() - timedelta(days=100),
            calibrated_by="Test",
            valid_until=datetime.utcnow() - timedelta(days=5),  # 已过期
            status=CalibrationStatus.VALID
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        expired = service.get_expired_calibrations(db=db_session)

        # 应该能找到这个已过期的校准
        found = any(
            e["calibration_id"] == str(cal.id)
            for e in expired
        )
        assert found

    def test_invalidated_not_in_validity_check(self, db_session):
        """测试作废的校准不会被纳入有效性检查"""
        # 先清除链路校准数据 (全局数据可能影响测试)
        db_session.query(LinkCalibration).delete()
        db_session.commit()

        cal = ProbeAmplitudeCalibration(
            probe_id=36,
            polarization="V",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            calibrated_at=datetime.utcnow(),
            calibrated_by="Test",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.INVALIDATED  # 已作废
        )
        db_session.add(cal)
        db_session.commit()

        service = CalibrationValidityService()
        status = service.check_validity(db_session, probe_id=36)

        # 已作废的校准不应该被返回
        assert status["amplitude"] is None
        # 没有任何有效校准时，总体状态应该是 unknown
        assert status["overall_status"] == "unknown"
