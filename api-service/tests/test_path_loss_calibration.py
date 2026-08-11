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
    PathLossMeasurement,
    ProbePathLossCalibrationService,
    RFChainCalibrationService,
    calculate_fspl,
)
from app.schemas.probe_calibration import (
    PolarizationType,
    ProbePathLossCalibrationResponse,
)
from app.services.calibration_orchestrator import (
    CalibrationOrchestrator,
    CalibrationItem,
    CALIBRATION_CONFIG,
)
from app.services.measurement_compensation import MeasurementCompensator
from app.services.calibration_report_generator import CalibrationReportGenerator


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


@pytest.fixture(autouse=True, scope="module")
def _install_get_db_override():
    """Module-scoped: install the SQLite-backed ``get_db`` override for
    every test in this file, then remove it. Replacing the previous
    module-level mutation ensures the override doesn't bleed into other
    test modules (the conftest safety net also restores it per test)."""
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


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
def type_a_chamber(db_session):
    """Create a Type A chamber (no LNA, no PA)"""
    chamber = create_chamber_from_preset(ChamberType.TYPE_A.value, name="Test Chamber A")
    db_session.add(chamber)
    db_session.commit()
    db_session.refresh(chamber)
    return chamber


@pytest.fixture
def type_c_chamber(db_session):
    """Create a Type C chamber (no LNA, has PA)"""
    chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Test Chamber C")
    db_session.add(chamber)
    db_session.commit()
    db_session.refresh(chamber)
    return chamber


@pytest.fixture
def type_d_chamber(db_session):
    """Create a Type D chamber (has LNA, has PA)"""
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
        assert calibration.use_mock is True

    @pytest.mark.asyncio
    async def test_real_path_persists_explicit_real_provenance(
        self, db_session, type_c_chamber, monkeypatch,
    ):
        """The service mode, not a driver-name heuristic, is persisted."""
        service = ProbePathLossCalibrationService(db_session, use_mock=False)

        async def _real_like_measurement(*_args, **_kwargs):
            return PathLossMeasurement(
                probe_id=0,
                polarization="V",
                path_loss_db=55.0,
                uncertainty_db=0.2,
            )

        monkeypatch.setattr(
            service,
            "_real_path_loss_measurement",
            _real_like_measurement,
        )

        result = await service.start_calibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            sgh_model="Test SGH",
            sgh_gain_dbi=10.0,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            calibrated_by="Test Engineer",
        )

        calibration = db_session.get(
            ProbePathLossCalibration,
            UUID(result.data["calibration_id"]),
        )
        assert calibration is not None
        assert calibration.use_mock is False

    @pytest.mark.asyncio
    async def test_latest_response_exposes_mock_provenance(
        self, db_session, type_c_chamber,
    ):
        service = ProbePathLossCalibrationService(db_session, use_mock=True)
        await service.start_calibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            sgh_model="Test SGH",
            sgh_gain_dbi=10.0,
            probe_ids=[0],
            polarizations=[PolarizationType.V],
            calibrated_by="Test Engineer",
        )

        calibration = service.get_latest_calibration(type_c_chamber.id, 3500.0)
        payload = ProbePathLossCalibrationResponse.model_validate(
            calibration
        ).model_dump()

        assert payload["use_mock"] is True

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
    async def test_uplink_calibration_with_lna(self, db_session, type_d_chamber):
        """Should calibrate uplink when LNA exists. Type D has LNA — Type C
        does NOT (it only has PA), so the original test was paired with the
        wrong fixture and fell into the early-return short-circuit."""
        service = RFChainCalibrationService(db_session, use_mock=True)

        result = await service.calibrate_uplink(
            chamber_id=type_d_chamber.id,
            frequency_mhz=3500.0,
            calibrated_by="Test Engineer"
        )

        assert result.success is True
        assert "calibration_id" in result.data
        assert "lna_gain_db" in result.data

    @pytest.mark.asyncio
    async def test_downlink_calibration_without_pa(self, db_session, type_a_chamber):
        """Type A has no PA → should skip downlink calibration with
        data={'has_pa': False}. Original test used Type C which actually HAS
        a PA, so it fell into the full-calibration branch where 'has_pa' is
        not surfaced (calibration_id is)."""
        service = RFChainCalibrationService(db_session, use_mock=True)

        result = await service.calibrate_downlink(
            chamber_id=type_a_chamber.id,
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
    async def test_get_uplink_gain(self, db_session, type_d_chamber):
        """Should retrieve uplink gain after calibration. Need a chamber with
        LNA so calibrate_uplink actually creates a row to read back."""
        service = RFChainCalibrationService(db_session, use_mock=True)

        await service.calibrate_uplink(
            chamber_id=type_d_chamber.id,
            frequency_mhz=3500.0,
            calibrated_by="Test Engineer"
        )

        gain = service.get_uplink_gain(type_d_chamber.id)
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

    @pytest.mark.parametrize(
        "use_mock, expected_provenance",
        [(True, "simulated"), (None, "unknown")],
        ids=["mock", "legacy-unknown"],
    )
    def test_real_compensation_refuses_untrusted_path_loss_and_returns_no_kpi(
        self,
        db_session,
        type_c_chamber,
        use_mock,
        expected_provenance,
    ):
        now = datetime.utcnow()
        db_session.add(ProbePathLossCalibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            use_mock=use_mock,
            probe_path_losses={"0": {"path_loss_db": 123.45}},
            sgh_model="Known source",
            sgh_gain_dbi=10.0,
            avg_path_loss_db=123.45,
            status="valid",
            calibrated_at=now,
            valid_until=now + timedelta(days=1),
        ))
        db_session.commit()

        compensated, details = MeasurementCompensator(
            db_session, use_mock=False,
        ).compensate_trp_measurement(
            -50.0,
            type_c_chamber.id,
            probe_id=0,
            polarization="V",
            frequency_mhz=3500.0,
        )

        assert compensated is None
        assert details["valid"] is False
        assert details["path_loss_db"] is None
        assert details["total_compensation_db"] is None
        assert details["path_loss_provenance"] == expected_provenance

        status = CalibrationOrchestrator(
            db_session, use_mock=False,
        ).check_calibration_status(type_c_chamber.id, 3500.0)[
            CalibrationItem.PROBE_PATH_LOSS
        ]
        assert status.is_valid is False
        assert expected_provenance in status.message

    def test_apply_trp_api_does_not_publish_mock_compensated_value(
        self, db_session, type_c_chamber,
    ):
        now = datetime.utcnow()
        db_session.add(ProbePathLossCalibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            use_mock=True,
            probe_path_losses={"0": {"path_loss_db": 123.45}},
            sgh_model="Known mock",
            sgh_gain_dbi=10.0,
            avg_path_loss_db=123.45,
            status="valid",
            calibrated_at=now,
            valid_until=now + timedelta(days=1),
        ))
        db_session.commit()

        response = client.post(
            "/api/v1/calibration/compensation/apply-trp",
            params={
                "chamber_id": str(type_c_chamber.id),
                "probe_id": 0,
                "raw_power_dbm": -50.0,
                "frequency_mhz": 3500.0,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["compensated_power_dbm"] is None
        assert payload["compensation_applied_db"] is None
        assert payload["details"]["valid"] is False
        assert payload["details"]["path_loss_provenance"] == "simulated"

        probe_response = client.get(
            f"/api/v1/calibration/path-loss/probe/{type_c_chamber.id}/0",
            params={"frequency_mhz": 3500.0},
        )
        assert probe_response.status_code == 404

        status_response = client.get(
            f"/api/v1/calibration/orchestrator/status/{type_c_chamber.id}",
            params={"frequency_mhz": 3500.0},
        )
        assert status_response.status_code == 200
        path_status = status_response.json()["calibrations"]["probe_path_loss"]
        assert path_status["is_valid"] is False
        assert "simulated" in path_status["message"]

    def test_calibration_reports_disclose_and_fail_mock_path_loss(
        self, db_session, type_c_chamber,
    ):
        now = datetime.utcnow()
        db_session.add(ProbePathLossCalibration(
            chamber_id=type_c_chamber.id,
            frequency_mhz=3500.0,
            use_mock=True,
            probe_path_losses={"0": {"path_loss_db": 123.45}},
            sgh_model="Known mock",
            sgh_gain_dbi=10.0,
            avg_path_loss_db=123.45,
            status="valid",
            calibrated_at=now,
            valid_until=now + timedelta(days=1),
        ))
        db_session.commit()

        generator = CalibrationReportGenerator(db_session)
        chamber_data = generator._collect_chamber_calibration_data(
            type_c_chamber.id, 3500.0,
        )
        chamber_row = chamber_data["chamber_calibration"]["path_loss"][0]
        assert chamber_row["use_mock"] is True
        assert chamber_row["provenance"] == "simulated"
        assert chamber_row["validation_pass"] is False
        assert chamber_data["execution_summary"]["passed"] == 0

        probe_data = generator._collect_probe_data(
            calibration_type="path_loss",
        )
        probe_row = probe_data["probe_calibration"]["path_loss"][0]
        assert probe_row["use_mock"] is True
        assert probe_row["provenance"] == "simulated"
        assert probe_row["validation_pass"] is False
        assert probe_data["execution_summary"]["passed"] == 0


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

    def test_api_start_response_carries_warnings_field(self):
        """agent 复审 F2: POST /start 响应 wire 上必须有 warnings 字段 —
        钉 schema 字段 + return 传参 + response_model 不滤三件事 (mock 模式
        无告警 = 空列表; 非空内容由 service 级收割测试覆盖)。"""
        response = client.post(
            "/api/v1/chambers/from-preset", json={"preset_type": "type_c"}
        )
        chamber_id = response.json()["id"]

        response = client.post(
            "/api/v1/calibration/path-loss/start",
            json={
                "chamber_id": chamber_id,
                "frequency_mhz": 3500.0,
                "sgh_model": "SGH-01",
                "sgh_gain_dbi": 10.0,
                "calibrated_by": "wire-test",
                "use_mock": True,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["warnings"] == []


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
