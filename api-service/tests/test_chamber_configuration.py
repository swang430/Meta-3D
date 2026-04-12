"""
Chamber Configuration API Tests

测试暗室配置模型和 API 端点
"""
import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.models.chamber import ChamberConfiguration, ChamberType, CHAMBER_PRESETS, create_chamber_from_preset


# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestChamberPresets:
    """Test chamber preset templates"""

    def test_preset_type_a_exists(self):
        """Type A preset (small passive) should exist"""
        assert ChamberType.TYPE_A.value in CHAMBER_PRESETS
        preset = CHAMBER_PRESETS[ChamberType.TYPE_A.value]
        assert preset["has_lna"] is False
        assert preset["has_pa"] is False
        assert preset["supports_trp"] is True
        assert preset["supports_mimo_ota"] is False

    def test_preset_type_b_exists(self):
        """Type B preset (small MIMO) should exist"""
        assert ChamberType.TYPE_B.value in CHAMBER_PRESETS
        preset = CHAMBER_PRESETS[ChamberType.TYPE_B.value]
        assert preset["has_channel_emulator"] is True
        assert preset["supports_mimo_ota"] is True

    def test_preset_type_c_exists(self):
        """Type C preset (large unidirectional) should exist"""
        assert ChamberType.TYPE_C.value in CHAMBER_PRESETS
        preset = CHAMBER_PRESETS[ChamberType.TYPE_C.value]
        assert preset["has_lna"] is True
        assert preset["has_pa"] is False
        assert preset["chamber_radius_m"] == 4.0

    def test_preset_type_d_exists(self):
        """Type D preset (large bidirectional) should exist"""
        assert ChamberType.TYPE_D.value in CHAMBER_PRESETS
        preset = CHAMBER_PRESETS[ChamberType.TYPE_D.value]
        assert preset["has_lna"] is True
        assert preset["has_pa"] is True
        assert preset["has_duplexer"] is True
        assert preset["ce_bidirectional"] is True
        assert preset["supports_tis"] is True

    def test_create_chamber_from_preset(self):
        """Should create chamber from preset"""
        chamber = create_chamber_from_preset(ChamberType.TYPE_C.value)
        assert chamber.name == "大型单向暗室"
        assert chamber.chamber_radius_m == 4.0
        assert chamber.has_lna is True
        assert chamber.lna_gain_db == 20.0

    def test_create_chamber_from_preset_with_custom_name(self):
        """Should create chamber from preset with custom name"""
        chamber = create_chamber_from_preset(ChamberType.TYPE_D.value, name="My Custom Chamber")
        assert chamber.name == "My Custom Chamber"
        assert chamber.chamber_type == ChamberType.TYPE_D.value

    def test_create_chamber_from_invalid_preset(self):
        """Should raise error for invalid preset"""
        with pytest.raises(ValueError, match="Unknown preset type"):
            create_chamber_from_preset("invalid_type")


class TestChamberModel:
    """Test ChamberConfiguration model methods"""

    def test_get_supported_tests_trp_only(self):
        """Should return only TRP for basic chamber"""
        chamber = ChamberConfiguration(
            name="Test Chamber",
            chamber_radius_m=1.5,
            supports_trp=True,
            supports_tis=False,
            supports_mimo_ota=False
        )
        assert chamber.get_supported_tests() == ["TRP"]

    def test_get_supported_tests_all(self):
        """Should return all tests for full-featured chamber"""
        chamber = ChamberConfiguration(
            name="Full Chamber",
            chamber_radius_m=4.0,
            supports_trp=True,
            supports_tis=True,
            supports_mimo_ota=True
        )
        tests = chamber.get_supported_tests()
        assert "TRP" in tests
        assert "TIS" in tests
        assert "MIMO_OTA" in tests

    def test_calculate_max_radius_for_ul_basic(self):
        """Should calculate max radius for uplink"""
        chamber = ChamberConfiguration(
            name="Test Chamber",
            chamber_radius_m=4.0,
            probe_gain_dbi=8.0,
            typical_cable_loss_db=5.0,
            has_lna=False,
            ce_min_input_dbm=-30.0
        )
        max_radius = chamber.calculate_max_radius_for_ul(dut_tx_power_dbm=20.0)
        # Should return a positive value
        assert max_radius > 0

    def test_calculate_max_radius_for_ul_with_lna(self):
        """Max radius should be larger with LNA"""
        chamber_no_lna = ChamberConfiguration(
            name="No LNA",
            chamber_radius_m=4.0,
            probe_gain_dbi=8.0,
            typical_cable_loss_db=5.0,
            has_lna=False,
            ce_min_input_dbm=-30.0
        )
        chamber_with_lna = ChamberConfiguration(
            name="With LNA",
            chamber_radius_m=4.0,
            probe_gain_dbi=8.0,
            typical_cable_loss_db=5.0,
            has_lna=True,
            lna_gain_db=20.0,
            ce_min_input_dbm=-30.0
        )
        radius_no_lna = chamber_no_lna.calculate_max_radius_for_ul()
        radius_with_lna = chamber_with_lna.calculate_max_radius_for_ul()
        # LNA adds 20dB gain, so max radius should be ~10x larger
        assert radius_with_lna > radius_no_lna


class TestChamberAPI:
    """Test Chamber Configuration API endpoints"""

    def test_get_presets(self):
        """GET /chambers/presets should return all presets"""
        response = client.get("/api/v1/chambers/presets")
        assert response.status_code == 200
        data = response.json()
        assert "presets" in data
        assert len(data["presets"]) == 4  # Type A, B, C, D

    def test_create_chamber_from_preset(self):
        """POST /chambers/from-preset should create chamber"""
        response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_c", "name": "Test Chamber C"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Chamber C"
        assert data["chamber_type"] == "type_c"
        assert data["has_lna"] is True
        assert data["chamber_radius_m"] == 4.0

    def test_create_custom_chamber(self):
        """POST /chambers should create custom chamber"""
        response = client.post(
            "/api/v1/chambers",
            json={
                "name": "Custom Chamber",
                "description": "A custom test chamber",
                "chamber_radius_m": 3.5,
                "num_probes": 24,
                "has_lna": True,
                "lna_gain_db": 15.0,
                "has_pa": False,
                "supports_trp": True,
                "supports_tis": False,
                "supports_mimo_ota": True
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Custom Chamber"
        assert data["chamber_radius_m"] == 3.5
        assert data["has_lna"] is True
        assert data["lna_gain_db"] == 15.0

    def test_list_chambers(self):
        """GET /chambers should return chamber list"""
        # Create a chamber first
        client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_a"}
        )

        response = client.get("/api/v1/chambers")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_get_chamber_by_id(self):
        """GET /chambers/{id} should return specific chamber"""
        # Create a chamber
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_d"}
        )
        chamber_id = create_response.json()["id"]

        response = client.get(f"/api/v1/chambers/{chamber_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == chamber_id
        assert data["has_pa"] is True

    def test_update_chamber(self):
        """PUT /chambers/{id} should update chamber"""
        # Create a chamber
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_b"}
        )
        chamber_id = create_response.json()["id"]

        # Update it
        response = client.put(
            f"/api/v1/chambers/{chamber_id}",
            json={"name": "Updated Chamber", "lna_gain_db": 25.0}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Chamber"
        assert data["lna_gain_db"] == 25.0

    def test_activate_chamber(self):
        """POST /chambers/{id}/activate should set chamber as active"""
        # Create two chambers
        response1 = client.post("/api/v1/chambers/from-preset", json={"preset_type": "type_a"})
        response2 = client.post("/api/v1/chambers/from-preset", json={"preset_type": "type_b"})
        chamber_id_1 = response1.json()["id"]
        chamber_id_2 = response2.json()["id"]

        # Activate first chamber
        client.post(f"/api/v1/chambers/{chamber_id_1}/activate")

        # Activate second chamber
        response = client.post(f"/api/v1/chambers/{chamber_id_2}/activate")
        assert response.status_code == 200
        assert response.json()["is_active"] is True

        # First chamber should be deactivated
        response = client.get(f"/api/v1/chambers/{chamber_id_1}")
        assert response.json()["is_active"] is False

    def test_get_active_chamber(self):
        """GET /chambers/active should return active chamber"""
        # Create and activate a chamber
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_c"}
        )
        chamber_id = create_response.json()["id"]
        client.post(f"/api/v1/chambers/{chamber_id}/activate")

        response = client.get("/api/v1/chambers/active")
        assert response.status_code == 200
        assert response.json()["id"] == chamber_id

    def test_delete_chamber(self):
        """DELETE /chambers/{id} should delete non-active chamber"""
        # Create a chamber (it will be active by default)
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_a"}
        )
        chamber_id = create_response.json()["id"]

        # Deactivate it first by creating and activating another
        create_response2 = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_b"}
        )
        chamber_id_2 = create_response2.json()["id"]
        client.post(f"/api/v1/chambers/{chamber_id_2}/activate")

        # Now delete the first (inactive) chamber
        response = client.delete(f"/api/v1/chambers/{chamber_id}")
        assert response.status_code == 200

        # Verify it's deleted
        response = client.get(f"/api/v1/chambers/{chamber_id}")
        assert response.status_code == 404

    def test_cannot_delete_active_chamber(self):
        """DELETE /chambers/{id} should fail for active chamber"""
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_d"}
        )
        chamber_id = create_response.json()["id"]
        client.post(f"/api/v1/chambers/{chamber_id}/activate")

        response = client.delete(f"/api/v1/chambers/{chamber_id}")
        assert response.status_code == 400
        assert "active" in response.json()["detail"].lower()

    def test_get_required_calibrations_type_a(self):
        """Type A chamber should require basic calibrations only"""
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_a"}
        )
        chamber_id = create_response.json()["id"]

        response = client.get(f"/api/v1/chambers/{chamber_id}/required-calibrations")
        assert response.status_code == 200
        data = response.json()

        # Type A: no LNA, no PA, no duplexer, no CE
        assert "probe_path_loss" in data["required_calibrations"]
        assert "quiet_zone_uniformity" in data["required_calibrations"]
        assert "ul_chain_gain" in data["optional_calibrations"]  # No LNA
        assert "dl_chain_gain" in data["optional_calibrations"]  # No PA

    def test_get_required_calibrations_type_d(self):
        """Type D chamber should require all calibrations"""
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_d"}
        )
        chamber_id = create_response.json()["id"]

        response = client.get(f"/api/v1/chambers/{chamber_id}/required-calibrations")
        assert response.status_code == 200
        data = response.json()

        # Type D: has LNA, PA, duplexer, CE bidirectional
        assert "probe_path_loss" in data["required_calibrations"]
        assert "ul_chain_gain" in data["required_calibrations"]  # Has LNA
        assert "dl_chain_gain" in data["required_calibrations"]  # Has PA
        assert "duplexer_isolation" in data["required_calibrations"]  # Has duplexer
        assert "ce_bypass_calibration" in data["required_calibrations"]  # Has CE
        assert "ce_bidirectional_calibration" in data["required_calibrations"]  # CE bidirectional
        assert "probe_mutual_coupling" in data["required_calibrations"]  # MIMO OTA

    def test_calculate_link_budget(self):
        """GET /chambers/{id}/link-budget should calculate link budget"""
        create_response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_c"}
        )
        chamber_id = create_response.json()["id"]

        response = client.get(
            f"/api/v1/chambers/{chamber_id}/link-budget",
            params={
                "frequency_mhz": 3500,
                "dut_tx_power_dbm": 20,
                "dut_sensitivity_dbm": -100,
                "ce_output_dbm": -10
            }
        )
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "ul_system_gain_db" in data
        assert "ul_max_radius_m" in data
        assert "ul_margin_db" in data
        assert "ul_feasible" in data
        assert "dl_margin_db" in data
        assert "dl_feasible" in data
        assert "recommendations" in data


class TestChamberValidation:
    """Test input validation for chamber configuration"""

    def test_invalid_chamber_radius(self):
        """Chamber radius must be within valid range"""
        response = client.post(
            "/api/v1/chambers",
            json={
                "name": "Invalid Chamber",
                "chamber_radius_m": 100.0,  # Too large
                "num_probes": 32
            }
        )
        assert response.status_code == 422  # Validation error

    def test_invalid_num_probes(self):
        """Number of probes must be within valid range"""
        response = client.post(
            "/api/v1/chambers",
            json={
                "name": "Invalid Chamber",
                "chamber_radius_m": 4.0,
                "num_probes": 200  # Too many
            }
        )
        assert response.status_code == 422

    def test_invalid_preset_type(self):
        """Invalid preset type should return error"""
        response = client.post(
            "/api/v1/chambers/from-preset",
            json={"preset_type": "type_z"}  # Invalid
        )
        assert response.status_code == 422
