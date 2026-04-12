"""
Path Loss Calibration Tests

测试探头路损校准、RF 链路校准和编排器功能
"""
import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta

from app.main import app
from app.db.database import Base, get_db
from app.models.chamber import ChamberConfiguration, ChamberType, CHAMBER_PRESETS, create_chamber_from_preset
from app.models.probe_calibration import ProbePathLossCalibration, RFChainCalibration
from app.services.path_loss_calibration_service import (
    ProbePathLossCalibrationService,
    RFChainCalibrationService,
    calculate_fspl,
)
from app.services.calibration_orchestrator import (
    CalibrationOrchestrator,
    CalibrationItem,
    CALIBRATION_CONFIG,
)
from app.services.measurement_compensation import MeasurementCompensator


# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test"""
    # Import all models to ensure they are registered with Base
    # This is necessary because SQLAlchemy's declarative_base only knows about
    # models that have been imported before create_all() is called
    from app.models.chamber import ChamberConfiguration
    from app.models.probe_calibration import (
        ProbePathLossCalibration, RFChainCalibration, MultiFrequencyPathLoss
    )

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Get a database session for tests"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def type_c_chamber(db_session):
    """Create a Type C chamber for testing"""
    chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Test Chamber C")
    db_session.add(chamber)
    db_session.commit()
    db_session.refresh(chamber)
    return chamber


@pytest.fixture
def type_d_chamber(db_session):
    """Create a Type D chamber for testing"""
    chamber = create_chamber_from_preset(ChamberType.TYPE_D.value, name="Test Chamber D")
    db_session.add(chamber)
    db_session.commit()
    db_session.refresh(chamber)
    return chamber


class TestFSPLCalculation:
    """Test Free Space Path Loss calculation"""

    def test_fspl_at_3500mhz_4m(self):
        """FSPL at 3.5 GHz, 4m distance"""
        fspl = calculate_fspl(3500, 4.0)
        # FSPL = 20*log10(4) + 20*log10(3500) - 27.55
        # = 12.04 + 70.88 - 27.55 = 55.37 dB
        assert 55.0 < fspl < 56.0

    def test_fspl_at_700mhz_2m(self):
        """FSPL at 700 MHz, 2m distance"""
        fspl = calculate_fspl(700, 2.0)
        # Should be lower than 3.5 GHz
        assert 35.0 < fspl < 45.0

    def test_fspl_invalid_distance(self):
        """Should raise error for invalid distance"""
        with pytest.raises(ValueError):
            calculate_fspl(3500, 0)

    def test_fspl_invalid_frequency(self):
        """Should raise error for invalid frequency"""
        with pytest.raises(ValueError):
            calculate_fspl(0, 4.0)


class TestProbePathLossCalibrationService:
    """Test probe path loss calibration service"""

    @pytest.mark.asyncio
    async def test_start_calibration_success(self, db_session, type_c_chamber):
        """Should successfully complete path loss calibration"""
        service = ProbePathLossCalibrationService(db_session, use_mock=True)

        result = await service.start_calibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            sgh_model="Test SGH",
            sgh_gain_dbi=10.0,
            calibrated_by="Test Engineer"
        )

        assert result.success is True
        assert "calibration_id" in result.data
        assert result.data["num_probes"] == type_c_chamber.num_probes

    @pytest.mark.asyncio
    async def test_calibration_creates_db_record(self, db_session, type_c_chamber):
        """Calibration should create database record"""
        service = ProbePathLossCalibrationService(db_session, use_mock=True)

        result = await service.start_calibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            sgh_model="Test SGH",
            sgh_gain_dbi=10.0,
            calibrated_by="Test Engineer"
        )

        # Verify database record
        calibration = db_session.query(ProbePathLossCalibration).filter(
            ProbePathLossCalibration.id == UUID(result.data["calibration_id"])
        ).first()

        assert calibration is not None
        assert calibration.frequency_mhz == 3500.0
        assert calibration.sgh_model == "Test SGH"
        assert calibration.status == "valid"

    @pytest.mark.asyncio
    async def test_get_latest_calibration(self, db_session, type_c_chamber):
        """Should retrieve latest calibration"""
        service = ProbePathLossCalibrationService(db_session, use_mock=True)

        # Create a calibration
        await service.start_calibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            sgh_model="Test SGH",
            sgh_gain_dbi=10.0,
            calibrated_by="Test Engineer"
        )

        # Get latest
        calibration = service.get_latest_calibration(type_c_chamber.id)
        assert calibration is not None
        assert calibration.frequency_mhz == 3500.0

    @pytest.mark.asyncio
    async def test_get_path_loss_for_probe(self, db_session, type_c_chamber):
        """Should get path loss for specific probe"""
        service = ProbePathLossCalibrationService(db_session, use_mock=True)

        await service.start_calibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            sgh_model="Test SGH",
            sgh_gain_dbi=10.0,
            calibrated_by="Test Engineer"
        )

        path_loss = service.get_path_loss_for_probe(
            type_c_chamber.id, probe_id=0, polarization="V"
        )

        assert path_loss is not None
        assert 40 < path_loss < 80  # Reasonable range


class TestRFChainCalibrationService:
    """Test RF chain calibration service"""

    @pytest.mark.asyncio
    async def test_uplink_calibration_with_lna(self, db_session, type_c_chamber):
        """Should calibrate uplink when LNA exists"""
        service = RFChainCalibrationService(db_session, use_mock=True)

        result = await service.calibrate_uplink(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            calibrated_by="Test Engineer"
        )

        assert result.success is True
        assert "calibration_id" in result.data
        assert "lna_gain_db" in result.data

    @pytest.mark.asyncio
    async def test_downlink_calibration_without_pa(self, db_session, type_c_chamber):
        """Type C has no PA, should skip downlink calibration"""
        service = RFChainCalibrationService(db_session, use_mock=True)

        result = await service.calibrate_downlink(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            calibrated_by="Test Engineer"
        )

        assert result.success is True
        assert result.data.get("has_pa") is False

    @pytest.mark.asyncio
    async def test_downlink_calibration_with_pa(self, db_session, type_d_chamber):
        """Type D has PA, should calibrate downlink"""
        service = RFChainCalibrationService(db_session, use_mock=True)

        result = await service.calibrate_downlink(
            chamber_id=type_d_chamber.id,
            frequency_mhz=3500.0,
            calibrated_by="Test Engineer"
        )

        assert result.success is True
        assert "pa_gain_db" in result.data

    @pytest.mark.asyncio
    async def test_get_uplink_gain(self, db_session, type_c_chamber):
        """Should retrieve uplink gain after calibration"""
        service = RFChainCalibrationService(db_session, use_mock=True)

        await service.calibrate_uplink(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            calibrated_by="Test Engineer"
        )

        gain = service.get_uplink_gain(type_c_chamber.id)
        assert gain is not None


class TestCalibrationOrchestrator:
    """Test calibration orchestrator"""

    def test_get_required_calibrations_type_a(self, db_session):
        """Type A should require minimal calibrations"""
        chamber = create_chamber_from_preset(ChamberType.TYPE_A.value)
        db_session.add(chamber)
        db_session.commit()

        orchestrator = CalibrationOrchestrator(db_session, use_mock=True)
        required = orchestrator.get_required_calibrations(chamber)

        # Type A: no LNA, no PA, no CE
        assert CalibrationItem.PROBE_PATH_LOSS in required
        assert CalibrationItem.QUIET_ZONE_UNIFORMITY in required
        assert CalibrationItem.UPLINK_CHAIN not in required  # No LNA
        assert CalibrationItem.DOWNLINK_CHAIN not in required  # No PA

    def test_get_required_calibrations_type_d(self, db_session):
        """Type D should require all calibrations"""
        chamber = create_chamber_from_preset(ChamberType.TYPE_D.value)
        db_session.add(chamber)
        db_session.commit()

        orchestrator = CalibrationOrchestrator(db_session, use_mock=True)
        required = orchestrator.get_required_calibrations(chamber)

        # Type D has everything
        assert CalibrationItem.PROBE_PATH_LOSS in required
        assert CalibrationItem.UPLINK_CHAIN in required
        assert CalibrationItem.DOWNLINK_CHAIN in required
        assert CalibrationItem.DUPLEXER_ISOLATION in required

    def test_calibration_plan_generation(self, db_session, type_c_chamber):
        """Should generate calibration plan"""
        orchestrator = CalibrationOrchestrator(db_session, use_mock=True)
        plan = orchestrator.get_calibration_plan(type_c_chamber.id, 3500.0)

        assert "items_to_calibrate" in plan
        assert "total_items" in plan
        assert plan["total_items"] > 0

    @pytest.mark.asyncio
    async def test_execute_calibration_plan(self, db_session, type_c_chamber):
        """Should execute calibration plan"""
        orchestrator = CalibrationOrchestrator(db_session, use_mock=True)

        # Execute just path loss calibration
        result = await orchestrator.execute_calibration_plan(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            items=[CalibrationItem.PROBE_PATH_LOSS],
            calibrated_by="Test Engineer"
        )

        assert result["overall_success"] is True
        assert result["successful"] >= 1

    def test_get_compensation_factors(self, db_session, type_c_chamber):
        """Should get compensation factors"""
        orchestrator = CalibrationOrchestrator(db_session, use_mock=True)
        factors = orchestrator.get_compensation_factors(
            type_c_chamber.id, probe_id=0, polarization="V", frequency_mhz=3500.0
        )

        # Without calibration, path_loss should be 0
        assert "path_loss_db" in factors
        assert "ul_gain_db" in factors
        assert "trp_compensation_db" in factors


class TestMeasurementCompensator:
    """Test measurement compensator"""

    def test_get_trp_compensation(self, db_session, type_c_chamber):
        """Should return TRP compensation values"""
        compensator = MeasurementCompensator(db_session, use_mock=True)
        compensation = compensator.get_trp_compensation(
            type_c_chamber.id, probe_id=0, polarization="V", frequency_mhz=3500.0
        )

        assert "path_loss_db" in compensation
        assert "ul_gain_db" in compensation
        assert "total_compensation_db" in compensation
        assert "valid" in compensation

    def test_get_tis_compensation(self, db_session, type_d_chamber):
        """Should return TIS compensation values"""
        compensator = MeasurementCompensator(db_session, use_mock=True)
        compensation = compensator.get_tis_compensation(
            type_d_chamber.id, probe_id=0, polarization="V", frequency_mhz=3500.0
        )

        assert "path_loss_db" in compensation
        assert "dl_gain_db" in compensation
        assert "total_compensation_db" in compensation

    @pytest.mark.asyncio
    async def test_compensate_trp_with_calibration(self, db_session, type_c_chamber):
        """Should compensate TRP measurement after calibration"""
        # First do calibration
        path_loss_service = ProbePathLossCalibrationService(db_session, use_mock=True)
        await path_loss_service.start_calibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            sgh_model="Test SGH",
            sgh_gain_dbi=10.0,
            calibrated_by="Test"
        )

        rf_service = RFChainCalibrationService(db_session, use_mock=True)
        await rf_service.calibrate_uplink(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            calibrated_by="Test"
        )

        # Now compensate
        compensator = MeasurementCompensator(db_session, use_mock=True)
        raw_power = -30.0  # dBm

        compensated, details = compensator.compensate_trp_measurement(
            raw_power,
            type_c_chamber.id,
            probe_id=0,
            polarization="V",
            frequency_mhz=3500.0
        )

        assert details["valid"] is True
        # Compensated should be different from raw
        assert compensated != raw_power


class TestPathLossCalibrationAPI:
    """Test path loss calibration API endpoints"""

    def test_api_get_presets(self):
        """GET /chambers/presets"""
        response = client.get("/api/v1/chambers/presets")
        assert response.status_code == 200
        assert len(response.json()["presets"]) == 4

    def test_api_orchestrator_required(self):
        """GET /calibration/orchestrator/required/{chamber_id}"""
        # Create chamber first
        response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_c"}
        )
        chamber_id = response.json()["id"]

        response = client.get(f"/api/v1/calibration/orchestrator/required/{chamber_id}")
        assert response.status_code == 200
        data = response.json()
        assert "required_calibrations" in data
        assert "probe_path_loss" in data["required_calibrations"]

    def test_api_orchestrator_status(self):
        """GET /calibration/orchestrator/status/{chamber_id}"""
        response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_d"}
        )
        chamber_id = response.json()["id"]

        response = client.get(
            f"/api/v1/calibration/orchestrator/status/{chamber_id}",
            params={"frequency_mhz": 3500}
        )
        assert response.status_code == 200
        data = response.json()
        assert "calibrations" in data

    def test_api_compensation_summary(self):
        """GET /calibration/compensation/summary/{chamber_id}"""
        response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_c"}
        )
        chamber_id = response.json()["id"]

        response = client.get(
            f"/api/v1/calibration/compensation/summary/{chamber_id}",
            params={"frequency_mhz": 3500}
        )
        assert response.status_code == 200
        data = response.json()
        assert "typical_compensation" in data
        assert "calibration_status" in data


class TestIntegration:
    """Integration tests for full calibration flow"""

    @pytest.mark.asyncio
    async def test_full_calibration_flow(self, db_session):
        """Test complete calibration workflow"""
        # 1. Create chamber
        chamber = create_chamber_from_preset(ChamberType.TYPE_D.value, name="Integration Test")
        db_session.add(chamber)
        db_session.commit()
        db_session.refresh(chamber)

        # 2. Get required calibrations
        orchestrator = CalibrationOrchestrator(db_session, use_mock=True)
        required = orchestrator.get_required_calibrations(chamber)
        assert len(required) > 0

        # 3. Execute calibration plan
        result = await orchestrator.execute_calibration_plan(
            chamber_id=chamber.id,
            frequency_mhz=3500.0,
            items=[
                CalibrationItem.PROBE_PATH_LOSS,
                CalibrationItem.UPLINK_CHAIN,
                CalibrationItem.DOWNLINK_CHAIN,
            ],
            calibrated_by="Integration Test"
        )

        assert result["overall_success"] is True

        # 4. Check calibration status
        statuses = orchestrator.check_calibration_status(chamber.id, 3500.0)

        # Path loss should be valid now
        assert statuses[CalibrationItem.PROBE_PATH_LOSS].is_valid is True

        # 5. Get compensation factors
        factors = orchestrator.get_compensation_factors(
            chamber.id, probe_id=0, polarization="V", frequency_mhz=3500.0
        )

        assert factors["path_loss_db"] > 0
        assert factors["ul_gain_db"] != 0 or factors["dl_gain_db"] != 0
