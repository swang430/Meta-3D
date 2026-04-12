"""
Channel Calibration Tests

测试信道校准服务和 API。
"""
import pytest
import numpy as np
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.channel_calibration import (
    ChannelCalibrationSession,
    TemporalChannelCalibration,
    DopplerCalibration,
    SpatialCorrelationCalibration,
    ChannelCalibrationStatus,
)
from app.services.channel_calibration_service import (
    # 算法函数
    calculate_rms_delay_spread,
    detect_clusters,
    compare_with_3gpp_reference,
    generate_mock_pdp,
    calculate_doppler_shift,
    generate_classical_doppler_spectrum,
    calculate_spectral_correlation,
    calculate_theoretical_correlation_laplacian,
    calculate_measured_correlation,
    fit_angular_power_spectrum,
    calculate_uniformity_stats,
    validate_quiet_zone_uniformity,
    # 服务类
    ChannelCalibrationService,
    # 常量
    RMS_DELAY_SPREAD_REFERENCE,
    CLUSTER_COUNT_REFERENCE,
)


# ==================== 测试数据库设置 ====================

@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话"""
    engine = create_engine(
        "sqlite:///./test_channel_calibration.db",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


# ==================== 时域校准算法测试 ====================

class TestTemporalCalibrationAlgorithms:
    """时域校准算法测试"""

    def test_calculate_rms_delay_spread_basic(self):
        """测试基本的 RMS 时延扩展计算"""
        # 创建简单的 PDP: 两个簇
        delay_bins = np.array([0, 100, 200, 300, 400, 500])  # ns
        power_db = np.array([-3, 0, -6, -10, -15, -20])  # dB

        rms_delay, max_delay = calculate_rms_delay_spread(delay_bins, power_db)

        assert rms_delay > 0
        assert max_delay > 0
        assert max_delay >= rms_delay
        assert max_delay <= 500  # 不超过最大时延

    def test_calculate_rms_delay_spread_single_cluster(self):
        """测试单簇情况"""
        delay_bins = np.array([0, 10, 20, 30, 40, 50])  # ns
        power_db = np.array([0, -30, -30, -30, -30, -30])  # 只有一个主簇

        rms_delay, max_delay = calculate_rms_delay_spread(delay_bins, power_db)

        # 单簇情况下 RMS 应该很小
        assert rms_delay < 20  # ns

    def test_detect_clusters(self):
        """测试簇检测"""
        # 生成有多个峰值的 PDP
        delay_bins = np.arange(0, 1000, 10)  # 0-1000 ns, 10 ns 步进
        power_db = np.full_like(delay_bins, -30.0, dtype=float)

        # 添加三个簇
        power_db[0] = 0    # 第一个簇在 0 ns
        power_db[20] = -3   # 第二个簇在 200 ns
        power_db[50] = -6   # 第三个簇在 500 ns

        cluster_delays, cluster_powers = detect_clusters(delay_bins, power_db)

        assert len(cluster_delays) >= 1
        assert len(cluster_powers) == len(cluster_delays)

    def test_compare_with_3gpp_reference_uma_los(self):
        """测试与 3GPP 参考值对比 - UMa LOS"""
        # UMa LOS 的参考 RMS 时延扩展约 93 ns
        result = compare_with_3gpp_reference(
            scenario_type="UMa",
            scenario_condition="LOS",
            measured_rms_delay_ns=90,  # 接近参考值
            measured_num_clusters=12,
            threshold_percent=10.0
        )

        assert result["reference_rms_delay_spread_ns"] == 93
        assert result["reference_num_clusters"] == 12
        assert result["rms_error_percent"] < 10
        assert result["cluster_count_match"] == True
        assert result["validation_pass"] == True

    def test_compare_with_3gpp_reference_uma_nlos(self):
        """测试与 3GPP 参考值对比 - UMa NLOS"""
        # UMa NLOS 的参考 RMS 时延扩展约 363 ns
        result = compare_with_3gpp_reference(
            scenario_type="UMa",
            scenario_condition="NLOS",
            measured_rms_delay_ns=500,  # 偏离较大
            measured_num_clusters=20,
            threshold_percent=10.0
        )

        assert result["reference_rms_delay_spread_ns"] == 363
        assert result["rms_error_percent"] > 10  # 超过阈值
        assert result["validation_pass"] == False

    def test_generate_mock_pdp(self):
        """测试模拟 PDP 生成"""
        delay_bins, power_db = generate_mock_pdp(
            scenario_type="UMa",
            scenario_condition="LOS",
            fc_ghz=3.5
        )

        assert len(delay_bins) > 0
        assert len(power_db) == len(delay_bins)
        assert np.max(power_db) == 0  # 归一化到 0 dB
        assert np.min(power_db) < -10  # 应该有动态范围


# ==================== 多普勒校准算法测试 ====================

class TestDopplerCalibrationAlgorithms:
    """多普勒校准算法测试"""

    def test_calculate_doppler_shift_120kmh(self):
        """测试 120 km/h 的多普勒频移"""
        fd = calculate_doppler_shift(velocity_kmh=120, fc_ghz=3.5)

        # 理论值: v * fc / c = 33.33 m/s * 3.5e9 Hz / 3e8 m/s ≈ 389 Hz
        expected_fd = (120 / 3.6) * (3.5e9) / 299792458
        assert abs(fd - expected_fd) < 1  # 误差小于 1 Hz

    def test_calculate_doppler_shift_high_speed_rail(self):
        """测试高铁速度的多普勒频移"""
        fd = calculate_doppler_shift(velocity_kmh=350, fc_ghz=3.5)

        # 高铁速度下多普勒频移应该更大
        fd_120 = calculate_doppler_shift(velocity_kmh=120, fc_ghz=3.5)
        assert fd > fd_120

    def test_generate_classical_doppler_spectrum(self):
        """测试经典多普勒频谱生成"""
        fd = 400  # Hz
        freq_bins, power_db = generate_classical_doppler_spectrum(fd, num_bins=512)

        assert len(freq_bins) == 512
        assert len(power_db) == 512
        # 频谱应该在 -fd 到 +fd 范围内有能量
        assert np.max(power_db) > np.min(power_db)

    def test_calculate_spectral_correlation_identical(self):
        """测试相同频谱的相关性"""
        spectrum = np.array([1, 2, 3, 4, 5, 4, 3, 2, 1])
        correlation = calculate_spectral_correlation(spectrum, spectrum)

        assert correlation > 0.99  # 应该接近 1

    def test_calculate_spectral_correlation_different(self):
        """测试不同频谱的相关性"""
        # 使用真正不相关的频谱
        np.random.seed(42)
        spectrum1 = np.array([1, 2, 3, 4, 5, 4, 3, 2, 1])
        spectrum2 = np.random.rand(9) * 5  # 随机频谱

        correlation = calculate_spectral_correlation(spectrum1, spectrum2)

        # 随机频谱的相关性应该低于完全匹配
        assert correlation < 0.95  # 相关性应该较低


# ==================== 空间相关性校准算法测试 ====================

class TestSpatialCorrelationAlgorithms:
    """空间相关性校准算法测试"""

    def test_theoretical_correlation_half_wavelength(self):
        """测试 0.5λ 间距的理论相关性"""
        # 小间距应该有高相关性
        correlation = calculate_theoretical_correlation_laplacian(
            antenna_spacing_wavelengths=0.5,
            angular_spread_deg=15
        )

        magnitude = abs(correlation)
        assert magnitude > 0.5  # 高相关性

    def test_theoretical_correlation_two_wavelengths(self):
        """测试 2λ 间距的理论相关性"""
        # 大间距应该有低相关性
        correlation = calculate_theoretical_correlation_laplacian(
            antenna_spacing_wavelengths=2.0,
            angular_spread_deg=15
        )

        magnitude = abs(correlation)
        assert magnitude < 0.5  # 低相关性

    def test_measured_correlation(self):
        """测试测量相关性计算"""
        # 生成相关的复数信道系数
        n = 1000
        h1 = np.random.randn(n) + 1j * np.random.randn(n)
        correlation_coef = 0.8
        h2 = correlation_coef * h1 + np.sqrt(1 - correlation_coef**2) * (
            np.random.randn(n) + 1j * np.random.randn(n)
        )

        magnitude, phase_deg, ci_width = calculate_measured_correlation(h1, h2)

        # 测量结果应该接近设定的相关性
        assert abs(magnitude - correlation_coef) < 0.1


# ==================== 角度扩展校准算法测试 ====================

class TestAngularSpreadAlgorithms:
    """角度扩展校准算法测试"""

    def test_fit_angular_power_spectrum_laplacian(self):
        """测试 Laplacian 分布拟合"""
        # 生成 Laplacian 分布的 APS
        azimuth = np.linspace(-60, 60, 121)  # 更窄的范围，更多点
        mean_az = 0
        sigma = 15  # 度
        power_linear = np.exp(-np.sqrt(2) * np.abs(azimuth - mean_az) / sigma)
        power_db = 10 * np.log10(power_linear + 1e-10)

        mean_deg, rms_deg, r_squared, dist_type = fit_angular_power_spectrum(
            azimuth, power_db, distribution_type="Laplacian"
        )

        # 拟合结果应该接近原始参数
        assert abs(mean_deg - mean_az) < 15  # 允许 15 度误差
        assert rms_deg > 0  # RMS 应该为正
        assert r_squared > 0.5  # 拟合优度应该合理


# ==================== 静区校准算法测试 ====================

class TestQuietZoneAlgorithms:
    """静区校准算法测试"""

    def test_calculate_uniformity_stats(self):
        """测试均匀性统计计算"""
        values = np.array([1.0, 1.1, 0.9, 1.05, 0.95])

        mean, std, (min_val, max_val) = calculate_uniformity_stats(values)

        assert abs(mean - 1.0) < 0.1
        assert std < 0.1
        assert min_val == 0.9
        assert max_val == 1.1

    def test_validate_quiet_zone_uniformity_pass(self):
        """测试静区均匀性验证 - 通过"""
        amp_pass, phase_pass, overall_pass = validate_quiet_zone_uniformity(
            amplitude_std_db=0.5,
            phase_std_deg=15,
            amplitude_threshold_db=1.0,
            phase_threshold_deg=30.0
        )

        assert amp_pass == True
        assert phase_pass == True
        assert overall_pass == True

    def test_validate_quiet_zone_uniformity_fail(self):
        """测试静区均匀性验证 - 失败"""
        amp_pass, phase_pass, overall_pass = validate_quiet_zone_uniformity(
            amplitude_std_db=1.5,  # 超过阈值
            phase_std_deg=35,      # 超过阈值
            amplitude_threshold_db=1.0,
            phase_threshold_deg=30.0
        )

        assert amp_pass == False
        assert phase_pass == False
        assert overall_pass == False


# ==================== 服务层测试 ====================

class TestChannelCalibrationService:
    """信道校准服务测试"""

    def test_create_session(self, db_session):
        """测试创建校准会话"""
        service = ChannelCalibrationService(db_session)

        session = service.create_session(
            name="Test Session",
            description="Test channel calibration session",
            created_by="test_user"
        )

        assert session.id is not None
        assert session.name == "Test Session"
        assert session.status == "running"
        assert session.progress_percent == 0

    def test_update_session_progress(self, db_session):
        """测试更新会话进度"""
        service = ChannelCalibrationService(db_session)

        session = service.create_session(
            name="Test Session",
            created_by="test_user"
        )

        updated = service.update_session_progress(
            session_id=session.id,
            progress_percent=50,
            current_stage="temporal_calibration"
        )

        assert updated.progress_percent == 50
        assert updated.current_stage == "temporal_calibration"

    def test_run_temporal_calibration(self, db_session):
        """测试执行时域校准"""
        service = ChannelCalibrationService(db_session)

        calibration = service.run_temporal_calibration(
            scenario_type="UMa",
            scenario_condition="LOS",
            fc_ghz=3.5,
            calibrated_by="test_user"
        )

        assert calibration.id is not None
        assert calibration.scenario_type == "UMa"
        assert calibration.scenario_condition == "LOS"
        assert calibration.measured_rms_delay_spread_ns is not None
        assert calibration.validation_pass is not None
        assert calibration.status == ChannelCalibrationStatus.VALID.value

    def test_run_doppler_calibration(self, db_session):
        """测试执行多普勒校准"""
        service = ChannelCalibrationService(db_session)

        calibration = service.run_doppler_calibration(
            velocity_kmh=120,
            fc_ghz=3.5,
            calibrated_by="test_user"
        )

        assert calibration.id is not None
        assert calibration.velocity_kmh == 120
        assert calibration.expected_doppler_hz > 0
        assert calibration.spectral_correlation is not None
        assert calibration.validation_pass is not None

    def test_run_spatial_correlation_calibration(self, db_session):
        """测试执行空间相关性校准"""
        service = ChannelCalibrationService(db_session)

        calibration = service.run_spatial_correlation_calibration(
            scenario_type="UMa",
            scenario_condition="NLOS",
            fc_ghz=3.5,
            antenna_spacing_wavelengths=0.5,
            calibrated_by="test_user"
        )

        assert calibration.id is not None
        assert calibration.antenna_spacing_wavelengths == 0.5
        assert calibration.measured_correlation_magnitude is not None
        assert calibration.reference_correlation_magnitude is not None
        assert calibration.validation_pass is not None

    def test_list_calibrations(self, db_session):
        """测试列出校准记录"""
        service = ChannelCalibrationService(db_session)

        # 创建几个校准记录
        service.run_temporal_calibration("UMa", "LOS", 3.5, calibrated_by="test")
        service.run_temporal_calibration("UMi", "NLOS", 3.5, calibrated_by="test")
        service.run_doppler_calibration(120, 3.5, calibrated_by="test")

        # 列出所有
        results = service.list_calibrations(limit=10)
        assert len(results) == 3

        # 只列出时域校准
        temporal_results = service.list_calibrations(calibration_type="temporal", limit=10)
        assert len(temporal_results) == 2

    def test_run_angular_spread_calibration(self, db_session):
        """测试执行角度扩展校准"""
        service = ChannelCalibrationService(db_session)

        calibration = service.run_angular_spread_calibration(
            scenario_type="UMa",
            scenario_condition="NLOS",
            fc_ghz=3.5,
            azimuth_step_deg=5.0,
            calibrated_by="test_user"
        )

        assert calibration.id is not None
        assert calibration.scenario_type == "UMa"
        assert calibration.scenario_condition == "NLOS"
        assert calibration.fitted_rms_angular_spread_deg is not None
        assert calibration.fitted_rms_angular_spread_deg > 0
        assert calibration.reference_rms_angular_spread_deg is not None
        assert calibration.validation_pass is not None
        assert calibration.status == ChannelCalibrationStatus.VALID.value

    def test_run_quiet_zone_calibration_sphere(self, db_session):
        """测试执行球形静区校准"""
        service = ChannelCalibrationService(db_session)

        calibration = service.run_quiet_zone_calibration(
            quiet_zone_shape="sphere",
            quiet_zone_diameter_m=1.0,
            fc_ghz=3.5,
            num_points=50,
            calibrated_by="test_user"
        )

        assert calibration.id is not None
        assert calibration.quiet_zone_shape == "sphere"
        assert calibration.quiet_zone_diameter_m == 1.0
        assert calibration.num_points > 0
        assert calibration.amplitude_std_db is not None
        assert calibration.phase_std_deg is not None
        assert calibration.validation_pass is not None
        assert calibration.status == ChannelCalibrationStatus.VALID.value

    def test_run_quiet_zone_calibration_cylinder(self, db_session):
        """测试执行圆柱形静区校准"""
        service = ChannelCalibrationService(db_session)

        calibration = service.run_quiet_zone_calibration(
            quiet_zone_shape="cylinder",
            quiet_zone_diameter_m=2.0,
            quiet_zone_height_m=3.0,
            fc_ghz=3.5,
            num_points=100,
            calibrated_by="test_user"
        )

        assert calibration.id is not None
        assert calibration.quiet_zone_shape == "cylinder"
        assert calibration.quiet_zone_diameter_m == 2.0
        assert calibration.quiet_zone_height_m == 3.0
        assert calibration.num_points == 100
        assert calibration.amplitude_uniformity_pass is not None
        assert calibration.phase_uniformity_pass is not None

    def test_run_eis_validation(self, db_session):
        """测试执行 EIS 验证"""
        service = ChannelCalibrationService(db_session)

        validation = service.run_eis_validation(
            fc_ghz=3.5,
            dut_model="TestVehicle-001",
            dut_type="vehicle",
            bandwidth_mhz=100,
            modulation="256QAM",
            target_throughput_percent=95.0,
            measured_by="test_user"
        )

        assert validation.id is not None
        assert validation.dut_model == "TestVehicle-001"
        assert validation.dut_type == "vehicle"
        assert validation.peak_eis_dbm is not None
        assert validation.median_eis_dbm is not None
        assert validation.eis_spread_db is not None
        assert validation.validation_pass is not None
        assert validation.status == ChannelCalibrationStatus.VALID.value

    def test_list_calibrations_with_new_types(self, db_session):
        """测试列出包含新类型的校准记录"""
        service = ChannelCalibrationService(db_session)

        # 创建各类校准记录
        service.run_angular_spread_calibration("UMa", "LOS", 3.5, calibrated_by="test")
        service.run_quiet_zone_calibration("sphere", 1.0, 3.5, calibrated_by="test")
        service.run_eis_validation(3.5, "TestDUT", measured_by="test")

        # 列出各类型
        angular_results = service.list_calibrations(calibration_type="angular_spread", limit=10)
        assert len(angular_results) == 1
        assert angular_results[0]["calibration_type"] == "angular_spread"

        qz_results = service.list_calibrations(calibration_type="quiet_zone", limit=10)
        assert len(qz_results) == 1
        assert qz_results[0]["calibration_type"] == "quiet_zone"

        eis_results = service.list_calibrations(calibration_type="eis", limit=10)
        assert len(eis_results) == 1
        assert eis_results[0]["calibration_type"] == "eis"


# ==================== 3GPP 参考数据测试 ====================

class TestReferenceData:
    """3GPP 参考数据测试"""

    def test_rms_delay_spread_reference_completeness(self):
        """测试 RMS 时延扩展参考数据完整性"""
        scenarios = ["UMa", "UMi", "RMa", "InH"]
        conditions = ["LOS", "NLOS"]

        for scenario in scenarios:
            for condition in conditions:
                key = (scenario, condition)
                assert key in RMS_DELAY_SPREAD_REFERENCE, f"Missing: {key}"
                ref = RMS_DELAY_SPREAD_REFERENCE[key]
                assert len(ref) == 3  # (median, min, max)
                assert ref[1] < ref[0] < ref[2]  # min < median < max

    def test_cluster_count_reference_completeness(self):
        """测试簇数量参考数据完整性"""
        scenarios = ["UMa", "UMi", "RMa", "InH"]
        conditions = ["LOS", "NLOS"]

        for scenario in scenarios:
            for condition in conditions:
                key = (scenario, condition)
                assert key in CLUSTER_COUNT_REFERENCE, f"Missing: {key}"
                count = CLUSTER_COUNT_REFERENCE[key]
                assert count > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
