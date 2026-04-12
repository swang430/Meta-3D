"""
Probe Calibration Model Tests

TASK-P01 验收测试：
1. test_amplitude_calibration_model_fields - 验证模型字段
2. test_amplitude_calibration_json_fields - 验证 JSON 字段序列化
3. test_phase_calibration_model_fields - 验证相位校准模型
4. test_calibration_validity_default_status - 验证默认状态

参考: docs/features/calibration/IMPLEMENTATION-PLAN.md
"""

import pytest
from datetime import datetime, timedelta
from uuid import UUID
import json

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.probe_calibration import (
    ProbeAmplitudeCalibration,
    ProbePhaseCalibration,
    ProbePolarizationCalibration,
    ProbePattern,
    LinkCalibration,
    ProbeCalibrationValidity,
    CalibrationStatus,
    Polarization,
    ProbeType,
    LinkCalibrationType,
)


# ===== Test Fixtures =====

@pytest.fixture(scope="module")
def test_engine():
    """Create a test database engine (SQLite in-memory)"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def db_session(test_engine):
    """Create a new database session for each test"""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ===== Amplitude Calibration Tests =====

class TestProbeAmplitudeCalibration:
    """幅度校准模型测试"""

    def test_amplitude_calibration_model_fields(self, db_session):
        """验证 AmplitudeCalibration 模型包含所有必需字段"""
        required_fields = [
            'id', 'probe_id', 'polarization',
            'frequency_points_mhz', 'tx_gain_dbi', 'rx_gain_dbi',
            'tx_gain_uncertainty_db', 'rx_gain_uncertainty_db',
            'reference_antenna', 'reference_power_meter',
            'temperature_celsius', 'humidity_percent',
            'calibrated_at', 'calibrated_by',
            'valid_until', 'status'
        ]

        # 获取模型的所有列名
        mapper = inspect(ProbeAmplitudeCalibration)
        model_columns = [column.key for column in mapper.columns]

        # 验证所有必需字段存在
        for field in required_fields:
            assert field in model_columns, f"Missing required field: {field}"

    def test_amplitude_calibration_json_fields(self, db_session):
        """验证 JSONB 字段正确存储数组数据"""
        # 准备测试数据
        frequency_points = [3300, 3400, 3500, 3600, 3700, 3800]
        tx_gain = [5.2, 5.3, 5.1, 5.0, 5.2, 5.1]
        rx_gain = [5.1, 5.2, 5.0, 4.9, 5.1, 5.0]
        tx_uncertainty = [0.3, 0.3, 0.3, 0.3, 0.3, 0.3]
        rx_uncertainty = [0.3, 0.3, 0.3, 0.3, 0.3, 0.3]

        calibration = ProbeAmplitudeCalibration(
            probe_id=1,
            polarization="V",
            frequency_points_mhz=frequency_points,
            tx_gain_dbi=tx_gain,
            rx_gain_dbi=rx_gain,
            tx_gain_uncertainty_db=tx_uncertainty,
            rx_gain_uncertainty_db=rx_uncertainty,
            reference_antenna="Schwarzbeck BBHA 9120 D SN:12345",
            reference_power_meter="Keysight N1913A SN:67890",
            temperature_celsius=23.5,
            humidity_percent=45.0,
            calibrated_by="Test User",
            valid_until=datetime.utcnow() + timedelta(days=90),
            status=CalibrationStatus.VALID.value,
        )

        db_session.add(calibration)
        db_session.commit()

        # 查询并验证
        result = db_session.query(ProbeAmplitudeCalibration).filter_by(probe_id=1).first()

        assert result is not None
        assert result.frequency_points_mhz == frequency_points
        assert result.tx_gain_dbi == tx_gain
        assert result.rx_gain_dbi == rx_gain
        assert len(result.frequency_points_mhz) == 6
        assert result.tx_gain_dbi[0] == 5.2

    def test_amplitude_calibration_default_values(self, db_session):
        """验证默认值正确设置"""
        calibration = ProbeAmplitudeCalibration(
            probe_id=2,
            polarization="H",
            frequency_points_mhz=[3500],
            tx_gain_dbi=[5.0],
            rx_gain_dbi=[4.9],
            tx_gain_uncertainty_db=[0.3],
            rx_gain_uncertainty_db=[0.3],
            valid_until=datetime.utcnow() + timedelta(days=90),
        )

        db_session.add(calibration)
        db_session.commit()

        result = db_session.query(ProbeAmplitudeCalibration).filter_by(probe_id=2).first()

        # 验证默认状态为 'valid'
        assert result.status == CalibrationStatus.VALID.value
        # 验证 UUID 已生成
        assert result.id is not None
        assert isinstance(result.id, UUID)
        # 验证 calibrated_at 有默认值
        assert result.calibrated_at is not None


# ===== Phase Calibration Tests =====

class TestProbePhaseCalibration:
    """相位校准模型测试"""

    def test_phase_calibration_model_fields(self, db_session):
        """验证 PhaseCalibration 模型包含所有必需字段"""
        required_fields = [
            'id', 'probe_id', 'polarization', 'reference_probe_id',
            'frequency_points_mhz', 'phase_offset_deg', 'group_delay_ns',
            'phase_uncertainty_deg',
            'vna_model', 'vna_serial',
            'calibrated_at', 'calibrated_by',
            'valid_until', 'status'
        ]

        mapper = inspect(ProbePhaseCalibration)
        model_columns = [column.key for column in mapper.columns]

        for field in required_fields:
            assert field in model_columns, f"Missing required field: {field}"

    def test_phase_calibration_reference_probe(self, db_session):
        """验证参考探头默认为 0"""
        calibration = ProbePhaseCalibration(
            probe_id=5,
            polarization="V",
            # reference_probe_id 不指定，应该默认为 0
            frequency_points_mhz=[3500],
            phase_offset_deg=[12.5],
            group_delay_ns=[0.5],
            phase_uncertainty_deg=[1.0],
            valid_until=datetime.utcnow() + timedelta(days=90),
        )

        db_session.add(calibration)
        db_session.commit()

        result = db_session.query(ProbePhaseCalibration).filter_by(probe_id=5).first()
        assert result.reference_probe_id == 0

    def test_phase_calibration_json_fields(self, db_session):
        """验证相位数据正确存储"""
        frequency_points = [3300, 3400, 3500]
        phase_offsets = [-15.2, -14.8, -15.0]  # 度
        group_delays = [0.52, 0.51, 0.52]  # ns
        uncertainties = [1.0, 1.0, 1.0]  # 度

        calibration = ProbePhaseCalibration(
            probe_id=6,
            polarization="H",
            reference_probe_id=0,
            frequency_points_mhz=frequency_points,
            phase_offset_deg=phase_offsets,
            group_delay_ns=group_delays,
            phase_uncertainty_deg=uncertainties,
            vna_model="Keysight N5227B",
            vna_serial="MY12345678",
            valid_until=datetime.utcnow() + timedelta(days=90),
        )

        db_session.add(calibration)
        db_session.commit()

        result = db_session.query(ProbePhaseCalibration).filter_by(probe_id=6).first()
        assert result.phase_offset_deg == phase_offsets
        assert result.group_delay_ns == group_delays
        assert result.vna_model == "Keysight N5227B"


# ===== Polarization Calibration Tests =====

class TestProbePolarizationCalibration:
    """极化校准模型测试"""

    def test_polarization_calibration_linear(self, db_session):
        """验证线极化数据存储"""
        calibration = ProbePolarizationCalibration(
            probe_id=10,
            probe_type=ProbeType.DUAL_LINEAR.value,
            v_to_h_isolation_db=28.5,
            h_to_v_isolation_db=27.8,
            frequency_points_mhz=[3300, 3500, 3700],
            isolation_vs_frequency_db=[28.5, 28.0, 27.5],
            valid_until=datetime.utcnow() + timedelta(days=180),
        )

        db_session.add(calibration)
        db_session.commit()

        result = db_session.query(ProbePolarizationCalibration).filter_by(probe_id=10).first()
        assert result.v_to_h_isolation_db == 28.5
        assert result.probe_type == ProbeType.DUAL_LINEAR.value

    def test_polarization_calibration_circular(self, db_session):
        """验证圆极化数据存储"""
        calibration = ProbePolarizationCalibration(
            probe_id=11,
            probe_type=ProbeType.CIRCULAR.value,
            polarization_hand="LHCP",
            axial_ratio_db=1.5,
            frequency_points_mhz=[3500],
            axial_ratio_vs_frequency_db=[1.5],
            valid_until=datetime.utcnow() + timedelta(days=180),
        )

        db_session.add(calibration)
        db_session.commit()

        result = db_session.query(ProbePolarizationCalibration).filter_by(probe_id=11).first()
        assert result.axial_ratio_db == 1.5
        assert result.polarization_hand == "LHCP"


# ===== Pattern Calibration Tests =====

class TestProbePattern:
    """方向图校准模型测试"""

    def test_pattern_model_fields(self, db_session):
        """验证方向图模型字段"""
        required_fields = [
            'id', 'probe_id', 'polarization', 'frequency_mhz',
            'azimuth_deg', 'elevation_deg', 'gain_pattern_dbi',
            'peak_gain_dbi', 'peak_azimuth_deg', 'peak_elevation_deg',
            'hpbw_azimuth_deg', 'hpbw_elevation_deg', 'front_to_back_ratio_db',
            'valid_until', 'status'
        ]

        mapper = inspect(ProbePattern)
        model_columns = [column.key for column in mapper.columns]

        for field in required_fields:
            assert field in model_columns, f"Missing required field: {field}"

    def test_pattern_data_storage(self, db_session):
        """验证方向图数据存储"""
        # 简化的方向图数据 (实际应该是 72x36 = 2592 点)
        azimuth = list(range(0, 360, 45))  # 8 点
        elevation = list(range(0, 181, 45))  # 5 点
        # 模拟增益数据 (8x5 = 40 点，扁平数组)
        gain_pattern = [5.0 - 0.1 * i for i in range(40)]

        pattern = ProbePattern(
            probe_id=20,
            polarization="V",
            frequency_mhz=3500.0,
            azimuth_deg=azimuth,
            elevation_deg=elevation,
            gain_pattern_dbi=gain_pattern,
            peak_gain_dbi=5.0,
            peak_azimuth_deg=0.0,
            peak_elevation_deg=90.0,
            hpbw_azimuth_deg=65.0,
            hpbw_elevation_deg=60.0,
            front_to_back_ratio_db=15.0,
            measurement_distance_m=3.0,
            valid_until=datetime.utcnow() + timedelta(days=365),
        )

        db_session.add(pattern)
        db_session.commit()

        result = db_session.query(ProbePattern).filter_by(probe_id=20).first()
        assert result.peak_gain_dbi == 5.0
        assert len(result.azimuth_deg) == 8
        assert len(result.elevation_deg) == 5
        assert len(result.gain_pattern_dbi) == 40


# ===== Link Calibration Tests =====

class TestLinkCalibration:
    """链路校准模型测试"""

    def test_link_calibration_pass(self, db_session):
        """验证链路校准通过场景"""
        calibration = LinkCalibration(
            calibration_type=LinkCalibrationType.PRE_TEST.value,
            standard_dut_type="dipole",
            standard_dut_model="Standard Dipole",
            standard_dut_serial="SD-001",
            known_gain_dbi=2.15,
            frequency_mhz=3500.0,
            measured_gain_dbi=2.35,
            deviation_db=0.2,  # 在 ±1 dB 范围内
            validation_pass=True,
            threshold_db=1.0,
            probe_link_calibrations=[
                {"probe_id": 0, "link_loss_db": 25.3, "phase_offset_deg": 12.5},
                {"probe_id": 1, "link_loss_db": 25.5, "phase_offset_deg": 14.2},
            ],
        )

        db_session.add(calibration)
        db_session.commit()

        result = db_session.query(LinkCalibration).first()
        assert result.validation_pass == True
        assert result.deviation_db == 0.2
        assert len(result.probe_link_calibrations) == 2

    def test_link_calibration_fail(self, db_session):
        """验证链路校准失败场景"""
        calibration = LinkCalibration(
            calibration_type=LinkCalibrationType.WEEKLY_CHECK.value,
            standard_dut_type="horn",
            known_gain_dbi=10.0,
            frequency_mhz=3500.0,
            measured_gain_dbi=11.8,
            deviation_db=1.8,  # 超出 ±1 dB 阈值
            validation_pass=False,
            threshold_db=1.0,
        )

        db_session.add(calibration)
        db_session.commit()

        result = db_session.query(LinkCalibration).filter_by(
            calibration_type=LinkCalibrationType.WEEKLY_CHECK.value
        ).first()
        assert result.validation_pass == False
        assert result.deviation_db == 1.8


# ===== Calibration Validity Tests =====

class TestProbeCalibrationValidity:
    """校准有效性状态测试"""

    def test_calibration_validity_default_status(self, db_session):
        """验证新校准记录默认状态"""
        validity = ProbeCalibrationValidity(
            probe_id=30,
            amplitude_valid=True,
            amplitude_valid_until=datetime.utcnow() + timedelta(days=90),
            phase_valid=True,
            phase_valid_until=datetime.utcnow() + timedelta(days=90),
            polarization_valid=False,
            pattern_valid=False,
            link_valid=True,
            link_valid_until=datetime.utcnow() + timedelta(days=7),
            overall_status="valid",
        )

        db_session.add(validity)
        db_session.commit()

        result = db_session.query(ProbeCalibrationValidity).filter_by(probe_id=30).first()
        assert result.amplitude_valid == True
        assert result.polarization_valid == False
        assert result.overall_status == "valid"

    def test_calibration_validity_expiring(self, db_session):
        """验证即将过期状态"""
        validity = ProbeCalibrationValidity(
            probe_id=31,
            amplitude_valid=True,
            amplitude_valid_until=datetime.utcnow() + timedelta(days=3),  # 3 天后过期
            phase_valid=True,
            phase_valid_until=datetime.utcnow() + timedelta(days=30),
            overall_status="expiring_soon",
        )

        db_session.add(validity)
        db_session.commit()

        result = db_session.query(ProbeCalibrationValidity).filter_by(probe_id=31).first()
        assert result.overall_status == "expiring_soon"


# ===== Enum Tests =====

class TestEnums:
    """枚举类型测试"""

    def test_calibration_status_values(self):
        """验证校准状态枚举值"""
        assert CalibrationStatus.VALID.value == "valid"
        assert CalibrationStatus.EXPIRED.value == "expired"
        assert CalibrationStatus.INVALIDATED.value == "invalidated"
        assert CalibrationStatus.PENDING.value == "pending"

    def test_polarization_values(self):
        """验证极化类型枚举值"""
        assert Polarization.V.value == "V"
        assert Polarization.H.value == "H"
        assert Polarization.LHCP.value == "LHCP"
        assert Polarization.RHCP.value == "RHCP"

    def test_probe_type_values(self):
        """验证探头类型枚举值"""
        assert ProbeType.DUAL_LINEAR.value == "dual_linear"
        assert ProbeType.DUAL_SLANT.value == "dual_slant"
        assert ProbeType.CIRCULAR.value == "circular"

    def test_link_calibration_type_values(self):
        """验证链路校准类型枚举值"""
        assert LinkCalibrationType.WEEKLY_CHECK.value == "weekly_check"
        assert LinkCalibrationType.PRE_TEST.value == "pre_test"
        assert LinkCalibrationType.POST_MAINTENANCE.value == "post_maintenance"
